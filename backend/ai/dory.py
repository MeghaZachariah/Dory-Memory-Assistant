"""Dory's public AI functions, used by Person B's screen, bot and scheduler:

    chat(person_id, message)                 -> ChatResult   (any-time questions)
    extract_facts(transcript, date, person)  -> ExtractionReport (evening chat)
    briefing(person_id)                      -> BriefingResult (morning)
    summary(person_id)                       -> SummaryResult  (daily family update)
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from . import config, prompts
from .answering import answer_question, check_answer
from .client import ModelError, call_model
from .conversation import converse, free_text_ok, people_in, spoken_names
from .dates import WEEKDAYS
from .db_interface import get_db
from .extraction import extract_facts  # re-exported
from .guards import MONTHS, find_unsupported, normalize
from .medical import classify, is_health_text, medication_reply
from .schemas import AnswerDraft, ChatResult, Fact
from .statements import confirm_statement, record_statements, split_message

__all__ = ["chat", "extract_facts", "briefing", "summary", "confirm_statement", "BriefingResult", "SummaryResult"]


def _safe_log(person_id: str, kind: str, payload: dict) -> None:
    try:
        get_db().log_event(person_id, kind, payload)
    except Exception:  # noqa: BLE001 - logging must never break a reply
        pass


def _ask_family(person_id: str, question: str, reason: str) -> Optional[int]:
    try:
        qid = get_db().create_pending_question(person_id, question, reason)
    except Exception:  # noqa: BLE001
        return None
    _safe_log(person_id, "pending_question", {"question_id": qid, "question": question, "reason": reason})
    return qid


def _note_statements(person_id: str, statements: list[str], person_name: str, today: date) -> list[dict]:
    """Record what the person told Dory. Never allowed to break the reply."""
    try:
        noted = [n.model_dump() for n in record_statements(statements, person_id, person_name, today)]
    except Exception as e:  # noqa: BLE001
        _safe_log(person_id, "statement_error", {"error": str(e), "statements": statements})
        return []
    if noted:
        _safe_log(person_id, "statement", {"statements": statements, "noted": noted})
    return noted


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------
def chat(
    person_id: str,
    message: str,
    *,
    person_name: str = "",
    family_names: Iterable[str] = (),
    now: Optional[datetime] = None,
    history: Optional[list[dict]] = None,
) -> ChatResult:
    """Talk with the person. Never invents; never answers health questions from memory.

    history: the conversation so far in this call, [{"speaker": "Dory" | <name>, "text": ...}], so
    Dory understands follow-ups like "no" or "what about yesterday?".
    family_names: names of registered family members. They are NOT allowed in model answers unless a
    cited fact contains them (otherwise "Ravi visited" could slip through); a reply that doesn't know
    something may say who it will ask.
    """
    t0 = time.perf_counter()
    now = now or datetime.now()
    today = now.date()
    db = get_db()
    allowed_names = person_name.split()  # only the person's own name may appear without a cited fact
    _safe_log(person_id, "question", {"text": message})

    # 1. Health, medication, urgent or rule-breaking messages: fixed replies only.
    kind, tiers = classify(message)

    # Anything the person TOLD Dory (not asked) is recorded and cross-checked (statements.py).
    # Health talk is never stored: symptom, urgent and rule-breaking messages skip this (and the urgent
    # reply is not delayed). In medicine messages only the non-health sentences are recorded.
    questions, statements = split_message(message)
    skip = kind in ("urgent", "symptom", "override")
    noted = [] if skip else _note_statements(person_id, statements, person_name, today)
    has_pending = any(n["outcome"] == "pending_family_check" for n in noted)
    if kind != "none":
        try:
            med_log = db.get_med_log(person_id, since=now - timedelta(days=1))
        except Exception:  # noqa: BLE001
            med_log = []
        qid = _ask_family(person_id, message, "urgent" if kind == "urgent" else "medication")
        result = ChatResult(
            reply=medication_reply(kind, med_log, now),
            status="refused",
            route="override" if kind == "override" else "medication",
            pending_question_id=qid,
            notify_family=True,
            tiers_used=tiers,
        )
        return _finish(person_id, message, result, t0, health_kind=kind, noted=noted)

    # 2. A natural conversation (conversation.py). Facts it states still go through the lie-catcher.
    natural = _converse(person_id, message, history or [], questions, statements, noted, today,
                        person_name, allowed_names, list(family_names), tiers, t0)
    if natural is not None:
        return natural

    # The model couldn't be used: fixed, safe replies as before.
    # Only told Dory something, asked nothing: thank them. Dory never says it is right or wrong.
    if statements and not questions:
        result = ChatResult(reply=config.STATEMENT_REPLY, status="answered", route="statement", notify_family=has_pending)
        return _finish(person_id, message, result, t0, noted=noted)
    question = " ".join(questions) or message

    # 2. Memory question: grounded answer from stored facts (confirmed ones only).
    try:
        facts = [f for f in db.get_facts(person_id) if f.verification == "confirmed"]
        facts_by_id = {f.fact_id: f for f in facts if f.fact_id is not None}
        draft, ans_res = answer_question(question, facts, today, person_name or "them")
    except ModelError as e:
        result = ChatResult(reply=config.ERROR_REPLY, status="unknown", route="error", checker=None)
        _safe_log(person_id, "model_error", {"error": str(e)})
        return _finish(person_id, message, result, t0, noted=noted)

    tiers = [ans_res.tier] if ans_res else []

    if draft.status == "refused":
        qid = _ask_family(person_id, question, "refused")
        result = ChatResult(reply=config.SAFE_REFUSED_REPLY, status="refused", route="memory",
                            pending_question_id=qid, notify_family=True, tiers_used=tiers, draft_answer=draft.answer)
        return _finish(person_id, message, result, t0, noted=noted)

    if draft.status == "unknown":
        qid = _ask_family(person_id, question, "unknown")
        result = ChatResult(reply=config.SAFE_UNKNOWN_ASKED_REPLY, status="unknown", route="memory",
                            pending_question_id=qid, notify_family=qid is not None, tiers_used=tiers)
        return _finish(person_id, message, result, t0, noted=noted)

    # 3. Lie-catcher.
    check, check_res = check_answer(question, draft, facts_by_id, today, allowed_names, person_name)
    if check_res:
        tiers.append(check_res.tier)
    if not check.passed:
        qid = _ask_family(person_id, question, "blocked")
        result = ChatResult(
            reply=config.SAFE_UNKNOWN_ASKED_REPLY,
            status="unknown",
            route="memory",
            checker=check,
            blocked=True,
            draft_answer=draft.answer,
            fact_ids_used=draft.fact_ids_used,
            pending_question_id=qid,
            notify_family=qid is not None,
            tiers_used=tiers,
        )
        return _finish(person_id, message, result, t0, noted=noted)

    result = ChatResult(
        reply=draft.answer,
        status="answered",
        route="memory",
        fact_ids_used=draft.fact_ids_used,
        checker=check,
        tiers_used=tiers,
    )
    return _finish(person_id, message, result, t0, noted=noted)


def _converse(person_id: str, message: str, history: list[dict], questions: list[str], statements: list[str],
              noted: list[dict], today: date, person_name: str, allowed_names: list[str],
              family_names: list[str], tiers: list[str], t0: float) -> Optional[ChatResult]:
    """Natural reply via conversation.converse(). None means "use the fixed replies"."""
    try:
        facts = [f for f in get_db().get_facts(person_id) if f.verification == "confirmed"]
        conv, res = converse(message, history, facts, today, person_name or "them")
    except ModelError as e:
        _safe_log(person_id, "model_error", {"error": str(e)})
        return None
    if conv is None or not conv.reply:
        return None
    tiers = tiers + ([res.tier] if res else [])
    facts_by_id = {f.fact_id: f for f in facts if f.fact_id is not None}
    question = " ".join(questions) or message
    own_words = allowed_names + spoken_names(message, history)
    people = people_in(facts, family_names)

    # A question about their life that the facts answer: the full lie-catcher, as before
    # (an "answer" citing no fact is blocked by it too: no receipt, no answer).
    if conv.kind == "answer":
        draft = AnswerDraft(answer=conv.reply, fact_ids_used=conv.fact_ids_used, status="answered")
        check, check_res = check_answer(question, draft, facts_by_id, today, own_words, person_name)
        if check_res:
            tiers.append(check_res.tier)
        if not check.passed:
            qid = _ask_family(person_id, question, "blocked")
            result = ChatResult(reply=config.SAFE_UNKNOWN_ASKED_REPLY, status="unknown", route="memory",
                                checker=check, blocked=True, draft_answer=draft.answer,
                                fact_ids_used=draft.fact_ids_used, pending_question_id=qid,
                                notify_family=qid is not None, tiers_used=tiers)
            return _finish(person_id, message, result, t0, noted=noted)
        result = ChatResult(reply=draft.answer, status="answered", route="memory",
                            fact_ids_used=draft.fact_ids_used, checker=check, tiers_used=tiers)
        return _finish(person_id, message, result, t0, noted=noted)

    # A question about their life the facts don't answer: say so kindly and ask the family.
    # Family names aren't allowed here: "I'm not sure, but Anu might have come" would be a guess.
    if conv.kind == "unknown":
        qid = _ask_family(person_id, conv.family_question or question, "unknown")
        ok = free_text_ok(conv.reply, [], today, own_words, people)
        result = ChatResult(reply=conv.reply if ok else config.SAFE_UNKNOWN_ASKED_REPLY, status="unknown",
                            route="memory", pending_question_id=qid, notify_family=qid is not None,
                            tiers_used=tiers, draft_answer=None if ok else conv.reply)
        return _finish(person_id, message, result, t0, noted=noted)

    # Talking: greetings, feelings, things they told Dory, questions about Dory.
    cited = [facts_by_id[i] for i in conv.fact_ids_used if i in facts_by_id]
    told_only = bool(noted) and not questions  # they told Dory something that was recorded
    if free_text_ok(conv.reply, cited, today, own_words, people):
        reply = conv.reply
    else:
        reply = config.STATEMENT_REPLY if statements and not questions else config.CHAT_FALLBACK_REPLY
    result = ChatResult(reply=reply, status="answered", route="statement" if told_only else "conversation",
                        fact_ids_used=[f.fact_id for f in cited if f.fact_id is not None], tiers_used=tiers,
                        notify_family=any(n["outcome"] == "pending_family_check" for n in noted))
    return _finish(person_id, message, result, t0, noted=noted)


def _finish(person_id: str, message: str, result: ChatResult, t0: float, health_kind: str = "none",
            noted: Optional[list[dict]] = None) -> ChatResult:
    result.noted = noted or []
    if any(n["outcome"] == "pending_family_check" for n in result.noted):
        result.notify_family = True
    result.latency_ms = int((time.perf_counter() - t0) * 1000)
    _safe_log(
        person_id,
        "answer",
        {
            "question": message,
            "reply": result.reply,
            "status": result.status,
            "route": result.route,
            "health_kind": health_kind,
            "blocked": result.blocked,
            "draft_answer": result.draft_answer,
            "fact_ids_used": result.fact_ids_used,
            "checker": result.checker.model_dump() if result.checker else None,
            "pending_question_id": result.pending_question_id,
            "tiers_used": result.tiers_used,
            "latency_ms": result.latency_ms,
            "noted": result.noted,
            # Badge for the dashboard's "Dory's answers" log.
            "badge": "blocked by checker" if result.blocked else ("passed" if result.status == "answered" else result.status),
        },
    )
    return result


# ---------------------------------------------------------------------------
# Morning briefing
# ---------------------------------------------------------------------------
class BriefingResult(BaseModel):
    text: str
    fact_ids: list[int] = Field(default_factory=list)
    used_fallback: bool = False  # True if the model's text failed checks and the template was used
    problems: list[str] = Field(default_factory=list)


def _long_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()].title()}, {d.day} {MONTHS[d.month - 1].title()}"


def _briefing_facts(person_id: str, today: date) -> tuple[list[Fact], list[Fact]]:
    facts = [
        f for f in get_db().get_facts(person_id, since=today - timedelta(days=1), until=today)
        if f.sensitivity == "normal" and f.verification == "confirmed" and not is_health_text(f.event)
    ]
    return [f for f in facts if f.event_date == today - timedelta(days=1)], [f for f in facts if f.event_date == today]


def _template_briefing(name: str, today: date, yest: list[Fact], plans: list[Fact]) -> str:
    parts = [f"Good morning{', ' + name if name else ''}. It's {_long_date(today)}."]
    if yest:
        parts.append("Yesterday, " + _lower_first(yest[0].event.rstrip(".")) + ".")
    for f in plans[:2]:
        t = f" at {f.event_time}" if f.event_time and f.event_time not in f.event else ""
        parts.append("Today, " + _lower_first(f.event.rstrip(".")) + t + ".")
    return " ".join(parts)


def _lower_first(s: str) -> str:
    # Keep names capitalised: only lower-case ordinary first words.
    first = s.split(" ", 1)[0]
    if first.lower() in {"the", "they", "she", "he", "we", "a", "an", "her", "his"}:
        return s[0].lower() + s[1:]
    return s


def briefing(person_id: str, *, person_name: str = "", today: Optional[date] = None) -> BriefingResult:
    """Short, calm morning reminder built only from yesterday's facts and today's plans."""
    today = today or date.today()
    yest, plans = _briefing_facts(person_id, today)
    ids = [f.fact_id for f in yest + plans if f.fact_id is not None]
    fallback = _template_briefing(person_name, today, yest, plans)

    if not yest and not plans:
        res = BriefingResult(text=fallback, fact_ids=[], used_fallback=True)
        _safe_log(person_id, "briefing", res.model_dump())
        return res

    fmt = lambda fs: "\n".join(f"- {f.event}" + (f" ({f.event_time})" if f.event_time else "") for f in fs) or "- none"  # noqa: E731
    try:
        result = call_model(
            config.TIER_FOR["briefing"],
            [
                {"role": "system", "content": prompts.BRIEFING_SYSTEM.format(person_name=person_name or "them")},
                {"role": "user", "content": prompts.BRIEFING_USER.format(today_long=_long_date(today), yesterday=fmt(yest), today_plans=fmt(plans))},
            ],
            purpose="briefing",
            temperature=0.2,
            max_tokens=200,
        )
        text = result.text.strip()
    except ModelError as e:
        res = BriefingResult(text=fallback, fact_ids=ids, used_fallback=True, problems=[f"model error: {e}"])
        _safe_log(person_id, "briefing", res.model_dump())
        return res

    # Same rule as answers: only names, numbers and dates from the facts (plus today's date).
    today_fact = Fact(person_id=person_id, event=_long_date(today), source_quote="today", event_date=today)
    problems = find_unsupported(text, yest + plans + [today_fact], today, person_name.split())
    if is_health_text(text):
        problems.append("briefing mentions health or medicine")
    res = BriefingResult(
        text=fallback if problems or not text else text,
        fact_ids=ids,
        used_fallback=bool(problems) or not text,
        problems=problems,
    )
    _safe_log(person_id, "briefing", res.model_dump())
    return res


# ---------------------------------------------------------------------------
# Daily family summary
# ---------------------------------------------------------------------------
class SummaryResult(BaseModel):
    text: str
    alerts: list[str] = Field(default_factory=list)  # e.g. "Asked about tablets 3 times today"
    stats: dict = Field(default_factory=dict)
    used_fallback: bool = False


_TOPIC_WORDS = re.compile(r"[^a-z0-9 ]")
_STOP = {"did", "i", "my", "the", "a", "an", "is", "was", "what", "when", "who", "do", "does", "today", "me", "to", "it", "are", "will", "dory", "please"}


def _question_key(q: str) -> str:
    words = [w for w in _TOPIC_WORDS.sub("", normalize(q)).split() if w not in _STOP]
    return " ".join(words) or normalize(q)


def summary(person_id: str, *, person_name: str = "", day: Optional[date] = None,
            use_model: bool = True) -> SummaryResult:
    """Daily update for the family (sent by Person B's bot). Written by Nemotron Ultra.
    use_model=False returns the plain template text straight away and logs nothing (for
    screens that refresh every few seconds)."""
    day = day or date.today()
    db = get_db()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    events = [e for e in db.get_events(person_id, since=start) if e["ts"] < end]
    answers = [e["payload"] for e in events if e["kind"] == "answer"]
    facts = [
        f for f in db.get_facts(person_id)
        if (f.conversation_date == day or f.event_date == day) and f.sensitivity != "do_not_share"
        and f.verification == "confirmed"
    ]

    counts = Counter(_question_key(a["question"]) for a in answers)
    example = {}
    for a in answers:
        example.setdefault(_question_key(a["question"]), a["question"])
    repeated = [(example[k], n) for k, n in counts.most_common() if n >= 2]
    med_qs = [a for a in answers if a.get("route") in ("medication", "override")]
    blocked = [a for a in answers if a.get("blocked")]
    pending = [e["payload"]["question"] for e in events if e["kind"] == "pending_question"]

    alerts = []
    if len(med_qs) >= 2:
        alerts.append(f"Asked about medicines {len(med_qs)} times today")
    if any(a.get("health_kind") == "urgent" for a in answers):
        alerts.append("Said something that may be urgent (see answers log)")
    alerts += [f'Asked "{q}" {n} times' for q, n in repeated[:3]]

    stats = {
        "questions": len(answers),
        "answered": sum(1 for a in answers if a.get("status") == "answered"),
        "sent_to_family": len(pending),
        "blocked": len(blocked),
        "medication_questions": len(med_qs),
        "facts_recorded": len(facts),
    }

    fallback_lines = [f"Daily update for {person_name or 'your family member'} ({_long_date(day)})."]
    if facts:
        fallback_lines.append("Today: " + "; ".join(f.event.rstrip(".") for f in facts[:5]) + ".")
    fallback_lines.append(f"Questions asked: {stats['questions']}, answered by Dory: {stats['answered']}.")
    if repeated:
        fallback_lines.append("Asked often: " + "; ".join(f'"{q}" ({n}x)' for q, n in repeated[:3]) + ".")
    if pending:
        fallback_lines.append(f"Sent to you: {len(pending)} question(s).")
    if med_qs:
        fallback_lines.append(f"Medicine questions: {len(med_qs)}.")
    if blocked:
        fallback_lines.append(f"Answers blocked by the safety check: {len(blocked)}.")
    fallback = " ".join(fallback_lines)
    if not use_model:
        return SummaryResult(text=fallback, alerts=alerts, stats=stats, used_fallback=True)

    user = prompts.SUMMARY_USER.format(
        person_name=person_name or "them",
        day=_long_date(day),
        facts="\n".join(f"- {f.event}" for f in facts) or "- none",
        question_counts="\n".join(f'- "{example[k]}": {n}' for k, n in counts.most_common()) or "- none",
        pending="\n".join(f"- {q}" for q in pending) or "- none",
        blocked=len(blocked),
        med_questions=len(med_qs),
    )
    try:
        res = call_model(
            config.TIER_FOR["summary"],
            [{"role": "system", "content": prompts.SUMMARY_SYSTEM}, {"role": "user", "content": user}],
            purpose="summary",
            temperature=0.2,
            max_tokens=300,
        )
        text, used_fallback = (res.text.strip() or fallback), not res.text.strip()
    except ModelError:
        text, used_fallback = fallback, True

    out = SummaryResult(text=text, alerts=alerts, stats=stats, used_fallback=used_fallback)
    _safe_log(person_id, "summary", out.model_dump())
    return out


# Convenience for the bot: draft answers are never spoken; only fixed or checked text is.
__all__ += ["AnswerDraft"]
