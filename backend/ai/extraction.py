"""Evening conversation -> verified facts.

Pipeline:
  1. Nemotron (Super) proposes facts as JSON.
  2. pydantic validates the shape; malformed facts are dropped.
  3. Code checks every source_quote against what the PERSON said. No match -> thrown away.
  4. Names and clock times not found in the person's words are removed.
  5. Time phrases are turned into real dates in code (dates.resolve_when).
  6. Health/medicine statements are never stored as facts.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional, Union

from pydantic import ValidationError

from . import config, prompts
from .client import ModelError, call_json
from .dates import WEEKDAYS, resolve_when
from .db_interface import get_db
from .guards import normalize, verify_quote
from .medical import is_health_text
from .schemas import ExtractedFact, ExtractionReport, Fact, RejectedFact

Transcript = Union[str, list[dict]]
DORY_SPEAKERS = {"dory", "assistant", "bot", "system"}


def _split_transcript(transcript: Transcript, person_name: str) -> tuple[str, str]:
    """Return (full text for the prompt, only the person's words for quote checks)."""
    lines: list[tuple[str, str]] = []
    if isinstance(transcript, str):
        for raw in transcript.splitlines():
            if not raw.strip():
                continue
            m = re.match(r"\s*([^:]{1,30}):\s*(.*)", raw)
            if m:
                lines.append((m.group(1).strip(), m.group(2).strip()))
            else:
                lines.append((person_name, raw.strip()))
    else:
        for turn in transcript:
            speaker = str(turn.get("speaker") or turn.get("role") or person_name)
            lines.append((speaker, str(turn.get("text") or turn.get("content") or "")))

    full = "\n".join(f"{'Dory' if s.lower() in DORY_SPEAKERS else s}: {t}" for s, t in lines)
    person_only = "\n".join(t for s, t in lines if s.lower() not in DORY_SPEAKERS)
    return full, person_only


def _names_in_text(names: list[str], text: str) -> tuple[list[str], list[str]]:
    keep, dropped = [], []
    low = normalize(text)
    for n in names:
        n = (n or "").strip()
        if not n:
            continue
        if re.search(rf"\b{re.escape(n.lower())}\b", low):
            keep.append(n)
        else:
            dropped.append(n)
    return keep, dropped


def _time_supported(event_time: Optional[str], text: str) -> bool:
    if not event_time:
        return True
    digits = re.findall(r"\d+", event_time)
    if digits:
        return all(re.search(rf"\b{d}\b", text) for d in digits)
    return normalize(event_time) in normalize(text)  # "noon", "lunchtime"


def extract_facts(
    transcript: Transcript,
    conversation_date: date,
    person_id: str,
    person_name: str = "the person",
    *,
    save: bool = True,
) -> ExtractionReport:
    """Turn an evening conversation into verified facts (and save them unless save=False).

    `transcript` is either a list of {"speaker": "Dory" | <name>, "text": "..."}
    or plain text with one "Speaker: words" line per turn.
    """
    full, person_only = _split_transcript(transcript, person_name)
    report = ExtractionReport()
    if not person_only.strip():
        return report

    messages = [
        {"role": "system", "content": prompts.EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": prompts.EXTRACT_USER.format(
                conversation_date=conversation_date.isoformat(),
                weekday=WEEKDAYS[conversation_date.weekday()].title(),
                person_name=person_name,
                transcript=full,
            ),
        },
    ]
    try:
        data, result = call_json(config.TIER_FOR["extract"], messages, purpose="extract", max_tokens=2000)
        report.model_latency_ms = result.latency_ms
    except (ModelError, ValueError) as e:
        report.rejected.append(RejectedFact(fact={}, reason=f"extraction failed: {e}"))
        _log(person_id, report)
        return report

    raw_facts = data.get("facts", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    seen: set[str] = set()

    for raw in raw_facts:
        if not isinstance(raw, dict):
            report.rejected.append(RejectedFact(fact={"value": str(raw)}, reason="not a JSON object"))
            continue
        try:
            ef = ExtractedFact.model_validate(raw)
        except ValidationError as e:
            report.rejected.append(RejectedFact(fact=raw, reason=f"bad format: {e.errors()[0]['msg']}"))
            continue

        ok, why = verify_quote(ef.source_quote, person_only)
        if not ok:
            report.rejected.append(RejectedFact(fact=raw, reason=why))
            continue
        if is_health_text(ef.source_quote) or is_health_text(ef.event):
            report.rejected.append(RejectedFact(fact=raw, reason="health/medicine info is never stored from conversation"))
            continue

        who, dropped_names = _names_in_text(ef.who, person_only)
        if any(re.search(rf"\b{re.escape(n)}\b", ef.event, re.IGNORECASE) for n in dropped_names):
            report.rejected.append(
                RejectedFact(fact=raw, reason=f"event mentions names the person never said: {dropped_names}")
            )
            continue
        event_time = ef.event_time if _time_supported(ef.event_time, person_only) else None

        # The event sentence must not introduce names the person never said.
        # (The first word is skipped: it is capitalised only because it starts the sentence.)
        event_words = re.findall(r"\b[A-Z][a-z]+\b", ef.event.split(" ", 1)[1] if " " in ef.event else "")
        allowed_extra = {w.lower() for w in person_name.split()} | _COMMON_CAPS
        _, event_bad_names = _names_in_text([w for w in event_words if w.lower() not in allowed_extra], person_only)
        if event_bad_names:
            report.rejected.append(
                RejectedFact(fact=raw, reason=f"event mentions names the person never said: {event_bad_names}")
            )
            continue

        event_date = resolve_when(ef.when_text, conversation_date, ef.source_quote)
        key = normalize(ef.source_quote) + "|" + normalize(ef.event)
        if key in seen:
            continue
        seen.add(key)
        if save:
            dup_id = _already_stored(person_id, ef.event, ef.source_quote, event_date)
            if dup_id is not None:
                report.rejected.append(RejectedFact(fact=raw, reason=f"already stored as fact #{dup_id}"))
                continue

        fact = Fact(
            person_id=person_id,
            event=ef.event.strip(),
            who=who,
            event_date=event_date,
            event_time=event_time,
            source_quote=ef.source_quote.strip(),
            source="conversation",
            conversation_date=conversation_date,
        )
        if save:
            fact.fact_id = get_db().add_fact(fact)
        report.kept.append(fact)
        if dropped_names or (ef.event_time and not event_time):
            report.rejected.append(
                RejectedFact(
                    fact=raw,
                    reason=f"kept fact but removed unsupported details: names={dropped_names}, "
                    f"time={'removed' if ef.event_time and not event_time else 'ok'}",
                )
            )

    _log(person_id, report)
    return report


def _already_stored(person_id: str, event: str, quote: str, event_date: Optional[date]) -> Optional[int]:
    """Id of a saved fact for the same event on the same date (same event text or same quote), else None.
    A different date means a new event (e.g. a second visit), so it is stored."""
    ev, q = normalize(event), normalize(quote)
    for f in get_db().get_facts(person_id, since=event_date, until=event_date):
        if f.event_date == event_date and (normalize(f.event) == ev or normalize(f.source_quote) == q):
            return f.fact_id
    return None


# Capitalised words allowed in an event sentence that are not names.
_COMMON_CAPS = {
    "she", "he", "they", "the", "her", "his", "their", "mum", "mom", "dad", "doctor", "dr",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "person", "it", "we", "a", "an", "i",
}


def _log(person_id: str, report: ExtractionReport) -> None:
    try:
        get_db().log_event(
            person_id,
            "extraction",
            {
                "kept": len(report.kept),
                "rejected": [r.model_dump() for r in report.rejected],
                "fact_ids": [f.fact_id for f in report.kept],
                "latency_ms": report.model_latency_ms,
            },
        )
    except Exception:  # noqa: BLE001 - logging must not break extraction
        pass
