"""The web screen, family dashboard and Telegram bot's API (the shapes in backend/mock_server.py),
served from the real AI and database.

Person B built Frontend/ and backend/bot/ against the mock. These endpoints return the same
JSON, so they now get real answers, the lie-catcher, family questions and the SQLite data
without changing their code. /chat lives in main.py and takes both request shapes.

Only registered people may answer Dory's questions or add memories: the person's family
(Profile.family_names) and caregivers (Profile.caregivers). Only caregivers log medicine.
The bot sends caregivers as "Name (caregiver)".
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.ai import briefing, confirm_statement, evening_turn, summary
from backend.ai.db_interface import get_db
from backend.ai.extraction import extract_facts
from backend.ai.schemas import ChatResult, Fact, MedLogEntry
from backend.api.auth import person_of

DEFAULT_PERSON = os.getenv("DORY_DEFAULT_PERSON", "mary")
router = APIRouter()

# Evening calls in progress from the web screen, which sends one answer per request.
_evenings: dict[str, dict[str, Any]] = {}


def _profile(person_id: str):
    from backend.api.main import profile  # late import: main imports this module

    return profile(person_id)


def _base_name(name: str) -> str:
    return re.sub(r"\s*\(caregiver\)\s*$", "", name.strip(), flags=re.IGNORECASE).lower()


def _is_registered(person_id: str, name: str) -> bool:
    p = _profile(person_id)
    return _base_name(name) in {n.lower() for n in p.family_names + p.caregivers}


def _is_caregiver(person_id: str, name: str) -> bool:
    return _base_name(name) in {n.lower() for n in _profile(person_id).caregivers}


# --- shapes ---------------------------------------------------------------------
_SOURCE_TYPE = {"conversation": "person_chat", "memory_book": "memory_book", "family_answer": "family_answer"}


def fact_out(f: Fact) -> dict:
    when = f.created_at or (datetime.combine(f.conversation_date, datetime.min.time()) if f.conversation_date else None)
    return {
        "id": f.fact_id,
        "text": f.event,
        "source_quote": f.source_quote,
        "source_type": _SOURCE_TYPE.get(f.source, f.source),
        "source_time": when.isoformat(timespec="seconds") if when else None,
        "confirmed_by": f.answered_by,
        "verification": f.verification,
    }


def _source(f: Fact) -> dict:
    label = {
        "conversation": "You told me this",
        "memory_book": "Your family wrote this in your Memory Book",
        "family_answer": f"{f.answered_by or 'Your family'} told me this",
    }.get(f.source, "From my notes")
    return {"fact_id": f.fact_id, "quote": f.source_quote, "source_type": _SOURCE_TYPE.get(f.source, f.source),
            "label": label}


def _spoken_fact_ids(payload: dict) -> list[int]:
    """Receipts only for answers Dory actually gave: a blocked draft's facts are not shown as sources."""
    if payload.get("blocked") or payload.get("status") != "answered":
        return []
    return payload.get("fact_ids_used") or []


def _sources(person_id: str, fact_ids: list[int]) -> list[dict]:
    if not fact_ids:
        return []
    by_id = {f.fact_id: f for f in get_db().get_facts(person_id)}
    return [_source(by_id[i]) for i in fact_ids if i in by_id]


def _topic(payload: dict) -> str:
    if payload.get("health_kind") == "urgent":
        return "emergency"
    route = payload.get("route")
    if route in ("medication", "override"):
        return "medicine"
    if route == "memory":
        return "memory" if payload.get("status") == "answered" else "other"
    return route or "other"


def _status(payload: dict) -> str:
    return "emergency" if payload.get("health_kind") == "urgent" else payload.get("status", "unknown")


def _tier(payload: dict) -> str:
    tiers = payload.get("tiers_used") or []
    return tiers[-1] if tiers else ("rules" if payload.get("route") in ("medication", "override") else "nano")


def chat_extras(person_id: str, result: ChatResult) -> dict:
    """The web screen's extra /chat fields, from the answer chat() just logged."""
    answers = get_db().get_events(person_id, kind="answer")
    payload = answers[-1]["payload"] if answers else {"status": result.status, "route": result.route}
    return {
        "status": _status(payload),
        "topic": _topic(payload),
        "sources": _sources(person_id, _spoken_fact_ids(payload)),
        "model_tier": _tier(payload),
        "draft": result.draft_answer,
        "done": False,
    }


# --- evening call, one answer per request ---------------------------------------
def evening_chat(person_id: str, text: str, turn: int) -> dict:
    p = _profile(person_id)
    session = _evenings.get(person_id)
    if turn == 0 or session is None:
        session = _evenings[person_id] = {"turns": [], "result": None}
    elif text.strip():
        session["turns"].append({"speaker": p.name or "Person", "text": text.strip()})
    out = evening_turn(person_id, session["turns"], date.today(), p.name)
    session["turns"].append({"speaker": "Dory", "text": out.say})
    if out.done:
        session["result"] = out
    return {"reply": out.say, "status": "evening", "done": out.done, "sources": [], "blocked": False}


class TranscriptLine(BaseModel):
    role: str  # "dory" | "person"
    text: str


class EveningFinishIn(BaseModel):
    person_id: str = DEFAULT_PERSON
    transcript: list[TranscriptLine]


@router.post("/checkin/evening/finish")
def evening_finish(body: EveningFinishIn, request: Request) -> dict:
    """Facts were already saved when the call ended normally. If it was stopped early,
    whatever was said is checked and saved now."""
    body.person_id = person_of(request, body.person_id)  # a signed-in family: always its own person
    session = _evenings.pop(body.person_id, None)
    if session and session["result"] is not None:
        ids = set(session["result"].fact_ids)
        facts = [f for f in get_db().get_facts(body.person_id) if f.fact_id in ids]
    else:
        name = _profile(body.person_id).name or "Person"
        turns = [{"speaker": "Dory" if line.role == "dory" else name, "text": line.text} for line in body.transcript]
        facts = extract_facts(turns, date.today(), body.person_id, name).kept
    return {"facts_saved": len(facts), "facts": [fact_out(f) for f in facts]}


# --- morning briefing -------------------------------------------------------------
@router.get("/briefing/morning")
def morning_briefing(request: Request, person_id: str = DEFAULT_PERSON) -> dict:
    person_id = person_of(request, person_id)
    res = briefing(person_id, person_name=_profile(person_id).name)
    return {"text": res.text, "sources": _sources(person_id, res.fact_ids)}


# --- family dashboard (polled every few seconds: no model calls here) --------------
def _question_out(q: dict, asked_to: str) -> dict:
    created = q.get("created_at")
    return {
        "id": q["id"],
        "text": q["question"],
        "status": q["status"],
        "reason": q.get("reason"),
        "asked_to": asked_to,
        "asked_at": created.isoformat(timespec="seconds") if isinstance(created, datetime) else created,
        "answer": q.get("answer"),
        "answered_by": q.get("answered_by"),
    }


def _med_out(i: int, m: MedLogEntry) -> dict:
    return {"id": i, "medicine": m.medicine, "time": m.given_at.strftime("%H:%M"),
            "date": m.given_at.date().isoformat(), "confirmed_by": m.logged_by}


def _alert_level(text: str) -> str:
    if "urgent" in text:
        return "urgent"
    return "warning" if "medicine" in text else "info"


@router.get("/dashboard/{person_id}")
def dashboard(person_id: str) -> dict:
    db = get_db()
    p = _profile(person_id)
    asked_to = p.family_names[0] if p.family_names else "your family"
    events = db.get_events(person_id, kind="answer")
    by_id = {f.fact_id: f for f in db.get_facts(person_id)}

    log = []
    for i, e in enumerate(events, start=1):
        a = e["payload"]
        log.append({
            "id": i,
            "time": e["ts"].isoformat(timespec="seconds"),
            "question": a.get("question"),
            "answer": a.get("reply"),
            "draft": a.get("draft_answer"),
            "status": _status(a),
            "topic": _topic(a),
            "blocked": a.get("blocked", False),
            "sources": [_source(by_id[f]) for f in _spoken_fact_ids(a) if f in by_id],
            "model_tier": _tier(a),
        })
    today = [entry for entry in log if entry["time"].startswith(date.today().isoformat())]

    report = summary(person_id, person_name=p.name, use_model=False)
    questions = sorted(db.list_questions(person_id), key=lambda q: q["id"])
    alerts = [{"level": _alert_level(a), "text": a} for a in report.alerts]
    alerts += [{"level": "action", "text": f'Question waiting for family: "{q["question"]}"'}
               for q in questions if q["status"] == "pending"]

    meds = sorted(db.get_med_log(person_id), key=lambda m: m.given_at)
    return {
        "person": {"id": person_id, "name": p.name or person_id},
        "summary": report.text,
        "counts": {
            "asked": len(today),
            "answered_by_dory": sum(1 for e in today if e["status"] == "answered" and not e["blocked"]),
            "asked_family": sum(1 for e in today if e["status"] == "unknown"),
            "blocked": sum(1 for e in today if e["blocked"]),
            "refused_medicine": sum(1 for e in today if e["status"] == "refused"),
        },
        "alerts": alerts,
        "facts": [fact_out(f) for f in by_id.values() if f.verification != "rejected"],
        "questions": [_question_out(q, asked_to) for q in questions],
        "answers_log": list(reversed(log))[:50],
        "med_log": [_med_out(i, m) for i, m in enumerate(meds, start=1)],
    }


# --- family and caregiver actions -------------------------------------------------
class FamilyAnswerIn(BaseModel):
    question_id: int
    answer: str
    answered_by: str
    person_id: str = DEFAULT_PERSON


_YES = re.compile(r"^\s*(yes|yeah|yep|true|correct|right|it did|she did|he did)\b", re.IGNORECASE)
_NO = re.compile(r"^\s*(no|nope|false|wrong|not|didn't|did not|it didn't|she didn't|he didn't)\b", re.IGNORECASE)


@router.post("/family/answer")
def family_answer(body: FamilyAnswerIn, request: Request) -> dict:
    body.person_id = person_of(request, body.person_id)  # a signed-in family: always its own person
    if not _is_registered(body.person_id, body.answered_by):
        raise HTTPException(status_code=403, detail="Sender is not a registered family member")
    db = get_db()
    q = next((q for q in db.list_questions(body.person_id) if q["id"] == body.question_id), None)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if q["status"] != "pending":
        raise HTTPException(status_code=409, detail="Question already answered")
    answer = body.answer.strip()

    fact: Optional[Fact] = None
    if q.get("reason") == "verify_statement" and (_YES.match(answer) or _NO.match(answer)):
        # Something the person told Dory: the family confirms or rejects it.
        confirm_statement(body.person_id, body.question_id, is_true=bool(_YES.match(answer)),
                          answered_by=body.answered_by)
    else:
        fact_id = db.record_family_answer(body.question_id, answer, body.answered_by)
        fact = next((f for f in db.get_facts(body.person_id) if f.fact_id == fact_id), None)
    q = next(q for q in db.list_questions(body.person_id) if q["id"] == body.question_id)
    asked_to = (_profile(body.person_id).family_names or ["your family"])[0]
    return {"question": _question_out(q, asked_to), "fact": fact_out(fact) if fact else None}


class MedLogIn(BaseModel):
    medicine: str
    time: str  # "HH:MM", today
    confirmed_by: str
    person_id: str = DEFAULT_PERSON


@router.post("/med/log")
def med_log(body: MedLogIn, request: Request) -> dict:
    body.person_id = person_of(request, body.person_id)  # a signed-in family: always its own person
    if not _is_caregiver(body.person_id, body.confirmed_by):
        raise HTTPException(status_code=403, detail="Only caregivers can log medicine")
    try:
        hour, minute = (int(x) for x in body.time.strip().split(":")[:2])
        given_at = datetime.combine(date.today(), datetime.min.time()).replace(hour=hour, minute=minute)
    except ValueError:
        given_at = datetime.now()
    entry = MedLogEntry(person_id=body.person_id, medicine=body.medicine.strip(), given_at=given_at,
                        logged_by=body.confirmed_by)
    get_db().add_med_log(entry)
    meds = sorted(get_db().get_med_log(body.person_id), key=lambda m: m.given_at)
    return _med_out(meds.index(entry) + 1 if entry in meds else len(meds), entry)


class MemoryFactIn(BaseModel):
    text: str
    added_by: str
    person_id: str = DEFAULT_PERSON


@router.post("/memory/fact")
def add_memory_fact(body: MemoryFactIn, request: Request) -> dict:
    """Memory Book: the family types a fact in advance (a trusted source)."""
    body.person_id = person_of(request, body.person_id)  # a signed-in family: always its own person
    if not _is_registered(body.person_id, body.added_by):
        raise HTTPException(status_code=403, detail="Sender is not a registered family member")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    fact = Fact(person_id=body.person_id, event=text, source_quote=text, source="memory_book",
                answered_by=body.added_by)
    fact_id = get_db().add_fact(fact)
    saved = next(f for f in get_db().get_facts(body.person_id) if f.fact_id == fact_id)
    return fact_out(saved)
