"""Grounded answering and the lie-catcher.

answer_question(): Nemotron answers using ONLY the stored facts, and must say
which fact ids it used.
check_answer(): code checks (guards.py) + a second Nemotron call that judges
"supported" or "unsupported". Any failure blocks the answer.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Optional

from pydantic import ValidationError

from . import config, prompts
from .client import ModelError, ModelResult, call_json
from .dates import WEEKDAYS
from .guards import code_check_answer
from .schemas import AnswerDraft, CheckResult, Fact


def _relative_label(d: date, today: date) -> str:
    delta = (d - today).days
    return {0: "today", -1: "yesterday", 1: "tomorrow"}.get(
        delta, f"{abs(delta)} days {'ago' if delta < 0 else 'from now'}"
    )


def format_fact(f: Fact, today: date) -> str:
    when = ""
    if f.event_date:
        when = f"{f.event_date.isoformat()}, {WEEKDAYS[f.event_date.weekday()].title()}, {_relative_label(f.event_date, today)}"
    if f.event_time:
        when = f"{when}, {f.event_time}" if when else f.event_time
    tag = " [tell gently]" if f.sensitivity == "tell_gently" else ""
    src = {"conversation": "they said", "memory_book": "family's Memory Book", "family_answer": f"family answer by {f.answered_by or 'family'}"}[f.source]
    when_part = f" ({when})" if when else ""
    return f'[{f.fact_id}]{when_part} {f.event}{tag} — source: {src}: "{f.source_quote}"'


def select_facts(facts: list[Fact]) -> list[Fact]:
    """Facts shown to the model: confirmed only, never 'do not share', newest first, capped in number."""
    usable = [f for f in facts if f.sensitivity != "do_not_share" and f.verification == "confirmed" and f.fact_id is not None]
    usable.sort(key=lambda f: (f.event_date or date.min, f.fact_id or 0), reverse=True)
    return usable[: config.MAX_FACTS_IN_PROMPT]


def answer_question(question: str, facts: list[Fact], today: date, person_name: str) -> tuple[AnswerDraft, Optional[ModelResult]]:
    shown = select_facts(facts)
    if not shown:
        return AnswerDraft(answer=config.SAFE_UNKNOWN_REPLY, fact_ids_used=[], status="unknown"), None

    system = prompts.ANSWER_SYSTEM.format(
        person_name=person_name,
        today=today.isoformat(),
        weekday=WEEKDAYS[today.weekday()].title(),
        facts="\n".join(format_fact(f, today) for f in shown),
    )
    try:
        data, result = call_json(
            config.TIER_FOR["answer"],
            [{"role": "system", "content": system}, {"role": "user", "content": question}],
            purpose="answer",
            max_tokens=250,
        )
    except ValueError:  # not JSON even after a retry
        return AnswerDraft(answer=config.SAFE_UNKNOWN_REPLY, fact_ids_used=[], status="unknown"), None
    try:
        draft = AnswerDraft.model_validate(data)
    except ValidationError:
        # A reply in the wrong shape is treated as "don't know", never shown as-is.
        draft = AnswerDraft(answer=config.SAFE_UNKNOWN_REPLY, fact_ids_used=[], status="unknown")
    return draft, result


def check_answer(
    question: str,
    draft: AnswerDraft,
    facts_by_id: dict[int, Fact],
    today: date,
    allowed_names: Iterable[str] = (),
    person_name: str = "",
) -> tuple[CheckResult, Optional[ModelResult]]:
    """The lie-catcher. Returns passed=False if the answer must not be spoken."""
    if draft.status != "answered":
        return CheckResult(passed=True, model_verdict="skipped", reasons=["not an answer; fixed reply used"]), None

    problems = code_check_answer(draft, facts_by_id, today, allowed_names)
    if problems:
        return CheckResult(passed=False, code_passed=False, reasons=problems, model_verdict="skipped"), None

    if not config.MODEL_CHECK_ENABLED:
        return CheckResult(passed=True, model_verdict="skipped", reasons=["code checks passed; model check off"]), None

    cited = [facts_by_id[i] for i in draft.fact_ids_used if i in facts_by_id]
    user = prompts.CHECK_USER.format(
        today=today.isoformat(),
        weekday=WEEKDAYS[today.weekday()].title(),
        person_name=person_name or "the person",
        question=question,
        answer=draft.answer,
        facts="\n".join(format_fact(f, today) for f in cited),
    )
    try:
        data, result = call_json(
            config.TIER_FOR["check"],
            [{"role": "system", "content": prompts.CHECK_SYSTEM}, {"role": "user", "content": user}],
            purpose="check",
            max_tokens=120,
        )
    except (ModelError, ValueError) as e:
        if config.CHECKER_FAIL_CLOSED:
            return CheckResult(passed=False, model_verdict="error", reasons=[f"checker unavailable: {e}"]), None
        return CheckResult(passed=True, model_verdict="error", reasons=[f"checker unavailable (fail open): {e}"]), None

    verdict = str(data.get("verdict", "")).lower() if isinstance(data, dict) else ""
    reason = str(data.get("reason", "")) if isinstance(data, dict) else ""
    if verdict == "supported":
        return CheckResult(passed=True, model_verdict="supported", reasons=[reason] if reason else []), result
    return CheckResult(
        passed=False,
        model_verdict="unsupported",
        reasons=[reason or f"checker returned {verdict!r}"],
    ), result


def yesterday(today: date) -> date:
    return today - timedelta(days=1)
