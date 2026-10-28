"""Talking with the person like a kind friend, without ever making up facts about their life.

converse() is one Nemotron call that sees the stored facts and the conversation so far, and
returns a natural reply plus what kind of moment this is:
  "chat"    greetings, feelings, small talk, questions about Dory, things they tell Dory
  "answer"  a question about their life that the facts answer (the lie-catcher then checks it)
  "unknown" a question about their life the facts don't answer (the family is asked)

Code still decides what may be said: free-text replies are checked for names, numbers and dates
that are neither in the cited facts nor in the person's own words (free_text_ok), and anything
health-related is never model-written. dory.chat() falls back to the fixed replies whenever this
fails, so a model problem never breaks the conversation.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, Field

from . import config, prompts
from .answering import format_fact, select_facts
from .client import ModelResult, call_json
from .dates import WEEKDAYS
from .guards import find_unsupported
from .medical import mentions_medicine_or_emergency
from .schemas import Fact

MAX_HISTORY = 8  # earlier turns sent with each message
MAX_REPLY_CHARS = 420  # about three short sentences, read aloud
_STATUS_TO_KIND = {"answered": "answer", "unknown": "unknown", "refused": "unknown"}


class ConvReply(BaseModel):
    kind: Literal["chat", "answer", "unknown"] = "chat"
    reply: str = ""
    fact_ids_used: list[int] = Field(default_factory=list)
    family_question: Optional[str] = None


def converse(
    message: str,
    history: list[dict],
    facts: list[Fact],
    today: date,
    person_name: str,
) -> tuple[Optional[ConvReply], Optional[ModelResult]]:
    """One natural reply. Raises ModelError if the model can't be reached; returns None if the
    reply isn't usable JSON (the caller then uses the fixed replies)."""
    shown = select_facts(facts)
    name = person_name or "the person"
    system = prompts.CONVERSE_SYSTEM.format(
        person_name=name,
        today=today.isoformat(),
        weekday=WEEKDAYS[today.weekday()].title(),
        facts="\n".join(format_fact(f, today) for f in shown) or "- none yet",
    )
    lines = [f"{'Dory' if _is_dory(t) else name}: {t.get('text', '').strip()}" for t in history[-MAX_HISTORY:]
             if t.get("text", "").strip()]
    user = prompts.CONVERSE_USER.format(history="\n".join(lines) or "(this is the start of the conversation)",
                                        person_name=name, message=message)
    try:
        data, result = call_json(config.TIER_FOR["answer"],
                                 [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                 purpose="converse", max_tokens=300)
    except ValueError:  # not JSON even after a retry
        return None, None
    if not isinstance(data, dict):
        return None, result
    reply = str(data.get("reply") or data.get("answer") or "").strip()
    kind = data.get("kind") or _STATUS_TO_KIND.get(str(data.get("status", "")), "chat")
    if kind not in ("chat", "answer", "unknown"):
        kind = "chat"
    ids = [i for i in data.get("fact_ids_used") or [] if isinstance(i, int)]
    question = data.get("family_question")
    return ConvReply(kind=kind, reply=reply, fact_ids_used=ids,
                     family_question=str(question).strip() if question else None), result


def _is_dory(turn: dict) -> bool:
    return str(turn.get("speaker") or turn.get("role") or "").lower() in ("dory", "assistant")


def spoken_names(message: str, history: Iterable[dict]) -> list[str]:
    """Every word the person said themselves: Dory may repeat them back ("Lakshmi", "mangoes")."""
    said = [message] + [t.get("text", "") for t in history if not _is_dory(t)]
    return re.findall(r"[A-Za-z][A-Za-z'-]*", " ".join(said))


def people_in(facts: Iterable[Fact], family_names: Iterable[str] = ()) -> set[str]:
    """Names known to be people: family, and anyone mentioned in the stored facts."""
    names = {n.lower() for n in family_names}
    for f in facts:
        names |= {w.lower() for w in f.who}
        names |= {w.lower() for w in re.findall(r"\b[A-Z][a-z]+\b", f.event)}
    return names


def _sentence_start_lowered(reply: str, people: set[str]) -> str:
    """Lower-case the first word of each sentence unless it is a known person, so "Mangoes are a
    treat" isn't mistaken for a name while "Ravi called you" still is."""
    def fix(m: re.Match) -> str:
        word = m.group(2)
        return m.group(1) + (word if word.lower().removesuffix("'s") in people else word.lower())

    return re.sub(r"(^|[.!?]\s+)([A-Z][A-Za-z']*)", fix, reply)


def free_text_ok(reply: str, cited: list[Fact], today: date, allowed_names: Iterable[str],
                 known_people: Iterable[str] = ()) -> bool:
    """A model-written reply may be spoken only if it is short, never about medicines, doses or
    emergencies, and every name, number and date in it is in the cited facts or in the person's own
    words. A kind "I'm sorry you're not feeling well" is fine (symptom messages never reach here:
    they get the fixed health replies). "Today"/"tonight" are fine in small talk."""
    if not reply or len(reply) > MAX_REPLY_CHARS or mentions_medicine_or_emergency(reply):
        return False
    text = _sentence_start_lowered(reply, {p.lower() for p in known_people})
    problems = find_unsupported(text, cited, today, list(allowed_names) + ["Dory"])
    return not [p for p in problems if "'today'" not in p and "'tonight'" not in p]
