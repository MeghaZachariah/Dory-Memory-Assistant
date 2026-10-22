"""The evening call, one turn at a time.

The phone app (or browser) sends the conversation so far; evening_turn()
returns Dory's next line. Dory's questions are a fixed, gentle script rather
than model-written, so the call is fast, predictable and never asks something
the person could "get wrong". When the script ends, the whole conversation is
passed to extract_facts() and saved.

Anything urgent the person says ("I fell") is sent to the family straight away.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from .db_interface import get_db
from .extraction import Transcript, _split_transcript, extract_facts
from .medical import classify

QUESTIONS = [
    "Good evening{name}. It's Dory. How was your day today?",
    "Did anyone visit you today, or did you talk to anyone?",
    "What did you have to eat today?",
    "Is anything planned for tomorrow, or later this week?",
]
ACKS = ["Thank you for telling me.", "Thank you.", "All right, thank you."]
CLOSING = "Thank you{name}. I've noted all that down. Sleep well, and I'll talk to you in the morning."
URGENT_NOTE = "That sounds important. I'm letting your family know right away."
_STOP_WORDS = re.compile(r"\b(bye|goodbye|good night|stop|that's all|that is all|no more|i'm tired|i am tired)\b", re.IGNORECASE)


class EveningTurn(BaseModel):
    say: str  # what Dory says next
    done: bool  # True after the closing line: hang up
    step: int  # how many questions Dory has asked so far
    facts_saved: int = 0
    facts_rejected: int = 0
    fact_ids: list[int] = Field(default_factory=list)
    alerted_family: bool = False


def evening_turn(
    person_id: str,
    turns: Transcript,
    conversation_date: Optional[date] = None,
    person_name: str = "",
) -> EveningTurn:
    """Return Dory's next line in the evening call.

    turns: the conversation so far, [{"speaker": "Dory" | <name>, "text": "..."}].
    Send an empty list to start the call.
    """
    conversation_date = conversation_date or date.today()
    turn_list = _as_turns(turns, person_name)
    name_part = f", {person_name}" if person_name else ""
    asked = sum(1 for t in turn_list if t["speaker"].lower() == "dory")
    last_person = next((t["text"] for t in reversed(turn_list) if t["speaker"].lower() != "dory"), "")

    alerted = False
    prefix = ""
    if last_person:
        kind, _ = classify(last_person, use_model=False)
        if kind == "urgent":
            alerted = True
            prefix = URGENT_NOTE + " "
            try:
                get_db().create_pending_question(person_id, f"During the evening call they said: {last_person}", "urgent")
            except Exception:  # noqa: BLE001
                pass

    finished = asked >= len(QUESTIONS) or bool(last_person and _STOP_WORDS.search(last_person))
    if not finished:
        ack = (ACKS[(asked - 1) % len(ACKS)] + " ") if asked else ""
        return EveningTurn(say=prefix + ack + QUESTIONS[asked].format(name=name_part), done=False,
                           step=asked + 1, alerted_family=alerted)

    report = extract_facts(turn_list, conversation_date, person_id, person_name or "the person")
    return EveningTurn(
        say=prefix + CLOSING.format(name=name_part),
        done=True,
        step=asked,
        facts_saved=len(report.kept),
        facts_rejected=len(report.rejected),
        fact_ids=[f.fact_id for f in report.kept if f.fact_id is not None],
        alerted_family=alerted,
    )


def _as_turns(turns: Transcript, person_name: str) -> list[dict]:
    if isinstance(turns, list):
        return [{"speaker": str(t.get("speaker") or t.get("role") or person_name or "Person"),
                 "text": str(t.get("text") or t.get("content") or "")} for t in turns]
    full, _ = _split_transcript(turns, person_name or "Person")
    out = []
    for line in full.splitlines():
        speaker, _, text = line.partition(": ")
        out.append({"speaker": speaker, "text": text})
    return out
