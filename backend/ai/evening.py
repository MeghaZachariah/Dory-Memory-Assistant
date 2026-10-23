"""The evening call, one turn at a time.

The phone app (or browser) sends the conversation so far; evening_turn()
returns Dory's next line. The first line is always the fixed greeting, so the
call starts instantly. After that the model holds a natural conversation
(EVENING_SYSTEM in prompts.py): it reacts to what the person said, follows up,
and asks them to repeat a name or day that speech recognition garbled. Code
still decides when the call ends (goodbye words, or a cap on questions), checks
every model line (short, no health talk), and falls back to the fixed QUESTIONS
whenever the model fails or DORY_EVENING_LLM=0. When the call ends, the whole
conversation is passed to extract_facts() and saved.

Plans stored for today ("Anu is visiting on Sunday") are brought up during the
call. Dory tells rather than quizzes: "I had a note for today: Anu is visiting.
How did that go?" If the person's answer is saved as a fact about it, that's
it. If not (unsure, or it didn't happen), the family is asked instead.

Anything urgent the person says ("I fell") is sent to the family straight away.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from . import config, prompts
from .client import ModelError, call_json
from .dates import WEEKDAYS
from .db_interface import get_db
from .extraction import Transcript, _split_transcript, extract_facts
from .medical import classify, is_health_text
from .schemas import Fact

QUESTIONS = [
    "Good evening{name}. It's Dory. How was your day today?",
    "Did anyone visit you today, or did you talk to anyone?",
    "What did you have to eat today?",
    "Is anything planned for tomorrow, or later this week?",
]
FOLLOW_UP = "I had a note for today: {event}. How did that go?"
MAX_FOLLOW_UPS = 2
MAX_SAY_CHARS = 300  # about three short sentences; longer model lines are not used
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
    followed_up: list[int] = Field(default_factory=list)  # plan fact ids Dory asked about
    family_question_ids: list[int] = Field(default_factory=list)  # plans the family is asked to confirm
    model_written: bool = False  # True when `say` came from the model, not the fixed script


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

    plans = _plans_for(person_id, conversation_date)
    script = QUESTIONS[:1] + [FOLLOW_UP.format(event=p.event.rstrip(".")) for p in plans] + QUESTIONS[1:]
    limit = config.EVENING_MAX_QUESTIONS if config.EVENING_LLM else len(script)

    finished = asked >= limit or bool(last_person and _STOP_WORDS.search(last_person))
    if not finished:
        if asked and config.EVENING_LLM:
            line = _model_line(turn_list, plans, person_name, conversation_date)
            if line == "":
                finished = True  # the model judged the chat complete
            elif line is not None:
                return EveningTurn(say=prefix + line, done=False, step=asked + 1, alerted_family=alerted,
                                   model_written=True)
        if not finished and asked < len(script):
            ack = (ACKS[(asked - 1) % len(ACKS)] + " ") if asked else ""
            return EveningTurn(say=prefix + ack + script[asked].format(name=name_part), done=False,
                               step=asked + 1, alerted_family=alerted)

    report = extract_facts(turn_list, conversation_date, person_id, person_name or "the person")
    dory_lines = [t["text"] for t in turn_list if t["speaker"].lower() == "dory"]
    followed_up = [p for p in plans if any(_mentions(line, p) for line in dory_lines)]
    question_ids = []
    for plan in followed_up:
        if any(_same_event(plan, f) for f in report.kept):
            continue  # what they said was saved as a fact
        try:
            question_ids.append(get_db().create_pending_question(
                person_id, f"Did this happen today: {plan.event.rstrip('.')}?", "plan_follow_up"))
        except Exception:  # noqa: BLE001
            pass
    return EveningTurn(
        say=prefix + CLOSING.format(name=name_part),
        done=True,
        step=asked,
        facts_saved=len(report.kept),
        facts_rejected=len(report.rejected),
        fact_ids=[f.fact_id for f in report.kept if f.fact_id is not None],
        alerted_family=alerted,
        followed_up=[p.fact_id for p in followed_up if p.fact_id is not None],
        family_question_ids=question_ids,
    )


def _model_line(turn_list: list[dict], plans: list[Fact], person_name: str, day: date) -> Optional[str]:
    """Dory's next line written by the model. "" means end the call; None means don't use
    the model this turn (error, or a line that failed the checks)."""
    plan_lines = "\n".join(f'  - "{p.event.rstrip(".")}"' for p in plans) or "  - none"
    messages = [
        {"role": "system", "content": prompts.EVENING_SYSTEM.format(
            person_name=person_name or "them",
            today=f"{WEEKDAYS[day.weekday()].title()}, {day.day} {day.strftime('%B')}",
            plans=plan_lines,
            max_questions=config.EVENING_MAX_QUESTIONS,
        )},
        {"role": "user", "content": prompts.EVENING_USER.format(
            transcript="\n".join(f"{t['speaker']}: {t['text']}" for t in turn_list))},
    ]
    try:
        data, _ = call_json(config.TIER_FOR["evening"], messages, purpose="evening", max_tokens=200)
    except (ModelError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("done") is True:
        return ""
    say = str(data.get("say") or "").strip()
    if not say or len(say) > MAX_SAY_CHARS or is_health_text(say):
        return None
    return say


def _plans_for(person_id: str, day: date) -> list[Fact]:
    """Confirmed, shareable plans for `day` that were known before that day."""
    try:
        facts = get_db().get_facts(person_id, since=day, until=day)
    except Exception:  # noqa: BLE001
        return []
    plans = [
        f for f in facts
        if f.event_date == day and f.verification == "confirmed" and f.sensitivity == "normal"
        and f.source != "family_answer" and (f.conversation_date is None or f.conversation_date < day)
        and not is_health_text(f.event)
    ]
    return plans[:MAX_FOLLOW_UPS]


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 3}


def _mentions(line: str, plan: Fact) -> bool:
    """Did this Dory line bring the plan up? A name from the plan, or (no names) a shared word."""
    if plan.who:
        return any(re.search(rf"\b{re.escape(w)}\b", line, re.IGNORECASE) for w in plan.who)
    return bool(_words(plan.event) & _words(line))


def _same_event(plan: Fact, fact: Fact) -> bool:
    """Does a fact saved tonight look like the plan happening? Same day, plus a shared name
    (or, for plans with no names, a shared word)."""
    if fact.event_date != plan.event_date:
        return False
    if plan.who:
        return bool({w.lower() for w in plan.who} & {w.lower() for w in fact.who})
    return bool(_words(plan.event) & _words(fact.event))


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
