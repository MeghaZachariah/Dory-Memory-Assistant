"""Things the person TELLS Dory during the day (not questions) -> recorded, cross-checked, then stored.

Pipeline for each message passed to chat():
  1. Split it into sentences. Questions go to answering; everything else that is not
     filler ("ok", "thank you", "hmm") or health talk is a statement.
  2. Statements go through the same checks as the evening chat (extraction.py): the quote
     must be the person's own words, names/times must be ones they said, dates are worked
     out in code, health is never stored.
  3. Each fact is cross-checked:
     - same fact already recorded (code check)       -> nothing stored
     - model says it matches a confirmed fact         -> nothing stored, already known
     - model says it is new or contradicts a fact     -> stored as "pending" and the family
       is asked "Mary said ..., is this true?"
  4. Pending facts are never used in answers, briefings or summaries until a family member
     confirms them with confirm_statement().
"""
from __future__ import annotations

import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import config, prompts
from .answering import format_fact
from .client import ModelError, call_json
from .dates import WEEKDAYS
from .db_interface import get_db
from .extraction import _already_stored, extract_facts
from .medical import is_health_text
from .schemas import Fact

_QUESTION_START = {
    "who", "what", "when", "where", "why", "how", "which", "whose", "did", "do", "does", "is", "are",
    "was", "were", "can", "could", "will", "would", "should", "shall", "have", "has", "am", "may",
    # requests are answered too, not recorded
    "tell", "remind", "pretend", "talk", "say", "speak", "act", "read", "call", "show", "give", "help",
    "let", "explain", "repeat", "find", "ask", "play", "sing",
}
# "I wonder if...", "I don't remember who..." are questions in disguise.
_INDIRECT_QUESTION = re.compile(
    r"\bi (?:wonder|want to know|would like to know|don'?t (?:remember|know)|can'?t remember|forgot|forget)\b"
)
_LEAD_INS = {"dory", "so", "and", "but", "oh", "well", "um", "uh", "hey", "please"}
_FILLER = {
    "ok", "okay", "yes", "yeah", "no", "nope", "hmm", "hm", "mm", "um", "uh", "oh", "ah", "thanks", "thank",
    "you", "good", "morning", "hello", "hi", "hey", "dory", "right", "alright", "fine", "well", "sure",
    "bye", "goodbye", "see", "later", "nice", "lovely", "great", "i", "see", "really", "wow",
}


def split_message(message: str) -> tuple[list[str], list[str]]:
    """Return (questions, statements). Speech-to-text often drops '?', so question words count too."""
    questions, statements = [], []
    for s in re.split(r"(?<=[.!?])\s+|\n+", message or ""):
        s = s.strip()
        words = re.findall(r"[a-z']+", s.lower())
        if not words:
            continue
        first = next((w for w in words if w not in _LEAD_INS), "")
        if s.endswith("?") or first in _QUESTION_START or _INDIRECT_QUESTION.search(s.lower()):
            questions.append(s)
        elif not all(w in _FILLER for w in words):
            statements.append(s)
    return questions, statements


class NotedStatement(BaseModel):
    """What happened to one fact the person told Dory (for the dashboard and the bot)."""

    event: str
    source_quote: str
    outcome: Literal["already_known", "already_recorded", "pending_family_check"]
    fact_id: Optional[int] = None  # the pending fact, or the existing fact it matched
    verify_question_id: Optional[int] = None  # family question; answer it with confirm_statement()
    contradicts_fact_ids: list[int] = Field(default_factory=list)
    reason: str = ""


def _cross_check(fact: Fact, confirmed: list[Fact], today: date) -> tuple[str, list[int], str]:
    """Ask the model whether a new fact matches, contradicts, or adds to the confirmed facts.
    Any failure counts as "new", so a person (the family) checks it."""
    if not confirmed:
        return "new", [], "nothing stored yet to compare with"
    by_id = {f.fact_id: f for f in confirmed}
    try:
        data, _ = call_json(
            config.TIER_FOR["check"],
            [
                {"role": "system", "content": prompts.VERIFY_SYSTEM},
                {"role": "user", "content": prompts.VERIFY_USER.format(
                    today=today.isoformat(),
                    weekday=WEEKDAYS[today.weekday()].title(),
                    statement=f'{fact.event} (they said: "{fact.source_quote}")'
                    + (f" [date: {fact.event_date.isoformat()}]" if fact.event_date else ""),
                    facts="\n".join(format_fact(f, today) for f in confirmed),
                )},
            ],
            purpose="verify_statement",
            max_tokens=150,
        )
    except (ModelError, ValueError) as e:
        return "new", [], f"cross-check failed: {e}"
    verdict = str(data.get("verdict", "")).lower() if isinstance(data, dict) else ""
    ids = [i for i in (data.get("fact_ids") or []) if i in by_id] if isinstance(data, dict) else []
    reason = str(data.get("reason", "")) if isinstance(data, dict) else ""
    if verdict in ("matches", "contradicts") and ids:
        return verdict, ids, reason
    return "new", [], reason  # unknown verdict or no valid receipts -> let the family decide


def record_statements(statements: list[str], person_id: str, person_name: str, today: date) -> list[NotedStatement]:
    """Record facts from things the person said. Nothing is stored as true until the family confirms."""
    statements = [s for s in statements if not is_health_text(s)]
    if not statements:
        return []
    db = get_db()
    name = person_name or "the person"
    report = extract_facts([{"speaker": name, "text": " ".join(statements)}], today, person_id, name, save=False)
    noted: list[NotedStatement] = []
    for fact in report.kept:
        dup = _already_stored(person_id, fact.event, fact.source_quote, fact.event_date)
        if dup is not None:
            noted.append(NotedStatement(event=fact.event, source_quote=fact.source_quote, outcome="already_recorded",
                                        fact_id=dup, reason=f"same as fact #{dup}"))
            continue
        confirmed = [f for f in db.get_facts(person_id) if f.verification == "confirmed"
                     and f.sensitivity != "do_not_share" and f.fact_id is not None]
        verdict, ids, reason = _cross_check(fact, confirmed, today)
        if verdict == "matches":
            noted.append(NotedStatement(event=fact.event, source_quote=fact.source_quote, outcome="already_known",
                                        fact_id=ids[0], reason=reason))
            continue
        question = f'{name} said: "{fact.source_quote}". Is this true?'
        if verdict == "contradicts":
            known = "; ".join(f.event for f in confirmed if f.fact_id in ids)
            question = f'{name} said: "{fact.source_quote}". Dory has this instead: "{known}". Is what {name} said true?'
        qid = db.create_pending_question(person_id, question, "verify_statement")
        fact.verification = "pending"
        fact.verify_question_id = qid
        fact.fact_id = db.add_fact(fact)
        noted.append(NotedStatement(event=fact.event, source_quote=fact.source_quote, outcome="pending_family_check",
                                    fact_id=fact.fact_id, verify_question_id=qid,
                                    contradicts_fact_ids=ids if verdict == "contradicts" else [], reason=reason))
    return noted


def confirm_statement(person_id: str, question_id: int, is_true: bool, answered_by: str) -> Optional[int]:
    """Called by the bot when the family answers a "verify_statement" question.
    True -> the pending fact becomes a normal fact. False -> it is kept as "rejected" (never used,
    and not asked about again). Returns the fact id, or None if no pending fact has this question."""
    db = get_db()
    fact = next((f for f in db.get_facts(person_id) if f.verify_question_id == question_id), None)
    if fact is None:
        return None
    db.update_fact(fact.fact_id, {"verification": "confirmed" if is_true else "rejected", "answered_by": answered_by})
    db.close_question(question_id, "yes" if is_true else "no", answered_by)
    return fact.fact_id
