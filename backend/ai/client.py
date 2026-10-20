"""Token Factory client: one function, call_model(tier, messages).

- Picks the model for the tier from config.MODELS.
- Logs latency and token use for every call (JSONL file + in-memory list),
  which Person C's scorecard reads.
- Strips <think> blocks, and can ask for JSON output.
- Tests replace the network with set_backend(fake) so nothing calls the API.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import config

log = logging.getLogger("dory.ai")

VALID_TIERS = ("nano", "super", "ultra")


@dataclass
class ModelResult:
    text: str
    tier: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    purpose: str = ""
    raw: Any = field(default=None, repr=False)


class ModelError(RuntimeError):
    """Raised when the model cannot be reached or returns nothing usable."""


# A backend takes (model, messages, options) and returns (text, prompt_tokens, completion_tokens).
Backend = Callable[[str, list, dict], tuple]

_backend: Optional[Backend] = None
_client = None
_lock = threading.Lock()
CALL_LOG: list[dict] = []  # in-memory copy of this process's calls


def set_backend(backend: Optional[Backend]) -> None:
    """Swap in a fake model for tests. Pass None to go back to Token Factory."""
    global _backend
    _backend = backend


def _openai_client():
    global _client
    if _client is None:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise ModelError("The 'openai' package is not installed. Run: pip install openai") from e
        key = os.getenv(config.API_KEY_ENV)
        if not key:
            raise ModelError(f"Set the {config.API_KEY_ENV} environment variable to your Token Factory key.")
        _client = OpenAI(
            base_url=config.BASE_URL,
            api_key=key,
            timeout=config.REQUEST_TIMEOUT_S,
            max_retries=config.MAX_RETRIES,
        )
    return _client


def _token_factory_backend(model: str, messages: list, options: dict) -> tuple:
    client = _openai_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": options.get("temperature", 0.0),
        "max_tokens": options.get("max_tokens", 800),
    }
    extra_body: dict[str, Any] = {}
    if config.DISABLE_THINKING:
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    if options.get("json"):
        kwargs["response_format"] = {"type": "json_object"}

    # Some models reject response_format or chat_template_kwargs. Try the full
    # request first, then drop the optional parts one at a time.
    attempts = [(kwargs, extra_body)]
    if "response_format" in kwargs:
        attempts.append(({k: v for k, v in kwargs.items() if k != "response_format"}, extra_body))
    if extra_body:
        attempts.append(({k: v for k, v in kwargs.items() if k != "response_format"}, {}))

    last_err: Optional[Exception] = None
    for kw, eb in attempts:
        try:
            resp = client.chat.completions.create(**kw, extra_body=eb or None)
            msg = resp.choices[0].message
            text = msg.content or ""
            usage = getattr(resp, "usage", None)
            return (
                text,
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        except Exception as e:  # noqa: BLE001 - try the next, simpler request
            last_err = e
            log.warning("Token Factory call failed (%s); retrying with a simpler request", e)
    raise ModelError(f"Token Factory call failed: {last_err}")


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def clean_text(text: str) -> str:
    """Remove reasoning blocks and stray whitespace from a model reply."""
    text = _THINK_RE.sub("", text or "")
    if "</think>" in text:  # an opening tag was cut off
        text = text.split("</think>", 1)[1]
    return text.strip()


def parse_json(text: str) -> Any:
    """Pull the first JSON object or array out of a reply, even if wrapped in prose or ``` fences."""
    text = clean_text(text)
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Model reply was not valid JSON: {text[:200]!r}")


def _record(entry: dict) -> None:
    with _lock:
        CALL_LOG.append(entry)
        try:
            config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(config.LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:  # logging must never break a reply
            log.warning("Could not write model call log: %s", e)


def call_model(
    tier: str,
    messages: list[dict],
    *,
    purpose: str = "",
    json_mode: bool = False,
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> ModelResult:
    """Call the Nemotron model for `tier` ("nano", "super" or "ultra").

    `purpose` is a short label ("answer", "extract", ...) saved in the log so the
    scorecard can show which tier handled what.
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"tier must be one of {VALID_TIERS}, got {tier!r}")
    model = config.MODELS[tier]
    backend = _backend or _token_factory_backend
    options = {"json": json_mode, "temperature": temperature, "max_tokens": max_tokens}

    start = time.perf_counter()
    error: Optional[str] = None
    text, p_tok, c_tok = "", 0, 0
    try:
        text, p_tok, c_tok = backend(model, messages, options)
    except ModelError as e:
        error = str(e)
        raise
    except Exception as e:  # noqa: BLE001
        error = str(e)
        raise ModelError(str(e)) from e
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _record(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "tier": tier,
                "model": model,
                "purpose": purpose,
                "latency_ms": latency_ms,
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "ok": error is None,
                "error": error,
                "over_latency_target": latency_ms > config.LATENCY_TARGET_MS,
            }
        )

    return ModelResult(
        text=clean_text(text),
        tier=tier,
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=p_tok,
        completion_tokens=c_tok,
        purpose=purpose,
    )


def call_json(tier: str, messages: list[dict], *, purpose: str = "", max_tokens: int = 1200) -> tuple[Any, ModelResult]:
    """call_model + parse_json. If the first reply isn't JSON, ask once more."""
    result = call_model(tier, messages, purpose=purpose, json_mode=True, max_tokens=max_tokens)
    try:
        return parse_json(result.text), result
    except ValueError:
        retry_msgs = messages + [
            {"role": "assistant", "content": result.text},
            {"role": "user", "content": "That was not valid JSON. Reply again with ONLY the JSON, nothing else."},
        ]
        result = call_model(tier, retry_msgs, purpose=f"{purpose}:retry", json_mode=True, max_tokens=max_tokens)
        return parse_json(result.text), result
