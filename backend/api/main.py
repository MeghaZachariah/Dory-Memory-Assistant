"""Dory's web server: wraps backend.ai so the Android app, browser screen,
Telegram bot and dashboard can all reach it over HTTP.

Run from the repo root (dory-hackathon/):
    uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

Interactive docs: http://localhost:8000/docs

If DORY_APP_TOKEN is set, every request (except /health) must send the
header  X-Dory-Token: <that value>.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.ai import briefing, chat, evening_turn, summary
from backend.ai.db_interface import get_db, set_db
from backend.ai.schemas import Fact, MedLogEntry

SAMPLES_PATH = Path(__file__).resolve().parents[1] / "ai" / "samples" / "conversations.json"
APP_TOKEN = os.getenv("DORY_APP_TOKEN", "")

# DORY_DB=sqlite keeps everything in Person C's db/dory.db; otherwise it is in memory.
if os.getenv("DORY_DB", "").lower() == "sqlite":
    from backend.ai.crud_db import CrudDB

    set_db(CrudDB())


def check_token(x_dory_token: Optional[str] = Header(default=None)) -> None:
    if APP_TOKEN and x_dory_token != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or wrong X-Dory-Token header")


app = FastAPI(title="Dory API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
secured = [Depends(check_token)]


# ---------------------------------------------------------------------------
# People (name and family, used to personalise replies). In memory for now;
# move to Person C's database later.
# ---------------------------------------------------------------------------
class Profile(BaseModel):
    person_id: str
    name: str = ""
    family_names: list[str] = Field(default_factory=list)


PROFILES: dict[str, Profile] = {}


def _load_default_profile() -> None:
    try:
        persona = json.loads(SAMPLES_PATH.read_text())["persona"]
        PROFILES[persona["person_id"]] = Profile(
            person_id=persona["person_id"], name=persona["person_name"], family_names=persona["family"]
        )
    except (OSError, KeyError, ValueError):
        pass


_load_default_profile()


def profile(person_id: str) -> Profile:
    return PROFILES.get(person_id) or Profile(person_id=person_id)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/people/{person_id}", dependencies=secured)
def get_person(person_id: str) -> Profile:
    return profile(person_id)


@app.put("/people/{person_id}", dependencies=secured)
def put_person(person_id: str, body: Profile) -> Profile:
    PROFILES[person_id] = body.model_copy(update={"person_id": person_id})
    return PROFILES[person_id]


# ---------------------------------------------------------------------------
# What the person's app uses
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    person_id: str
    message: str


@app.post("/chat", dependencies=secured)
def post_chat(body: ChatRequest) -> dict:
    p = profile(body.person_id)
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message is empty")
    return chat(body.person_id, body.message, person_name=p.name, family_names=p.family_names).model_dump(mode="json")


class EveningRequest(BaseModel):
    person_id: str
    turns: list[dict] = Field(default_factory=list)  # [{"speaker": "Dory" | name, "text": "..."}]
    conversation_date: Optional[date] = None  # defaults to today


@app.post("/evening/turn", dependencies=secured)
def post_evening_turn(body: EveningRequest) -> dict:
    p = profile(body.person_id)
    return evening_turn(body.person_id, body.turns, body.conversation_date, p.name).model_dump(mode="json")


@app.get("/briefing/{person_id}", dependencies=secured)
def get_briefing(person_id: str, today: Optional[date] = None) -> dict:
    return briefing(person_id, person_name=profile(person_id).name, today=today).model_dump(mode="json")


@app.get("/summary/{person_id}", dependencies=secured)
def get_summary(person_id: str, day: Optional[date] = None) -> dict:
    return summary(person_id, person_name=profile(person_id).name, day=day).model_dump(mode="json")


# ---------------------------------------------------------------------------
# What the family dashboard and Telegram bot use
# ---------------------------------------------------------------------------
@app.get("/facts/{person_id}", dependencies=secured)
def get_facts(person_id: str) -> list[dict]:
    facts = sorted(get_db().get_facts(person_id), key=lambda f: (f.event_date or date.min, f.fact_id or 0), reverse=True)
    return [f.model_dump(mode="json") for f in facts]


class MemoryBookEntry(BaseModel):
    event: str
    event_date: Optional[date] = None
    event_time: Optional[str] = None
    who: list[str] = Field(default_factory=list)
    added_by: str = "family"
    sensitivity: str = "normal"  # "normal" | "tell_gently" | "do_not_share"


@app.post("/facts/{person_id}", dependencies=secured)
def add_memory_book_fact(person_id: str, body: MemoryBookEntry) -> dict:
    fact = Fact(person_id=person_id, event=body.event, who=body.who, event_date=body.event_date,
                event_time=body.event_time, source_quote=body.event, source="memory_book",
                answered_by=body.added_by, sensitivity=body.sensitivity)  # type: ignore[arg-type]
    return {"fact_id": get_db().add_fact(fact)}


@app.get("/answers/{person_id}", dependencies=secured)
def get_answers(person_id: str, limit: int = 100) -> list[dict]:
    events = get_db().get_events(person_id, kind="answer")
    return [{"ts": e["ts"].isoformat(timespec="seconds"), **e["payload"]} for e in reversed(events[-limit:])]


@app.get("/questions/{person_id}", dependencies=secured)
def get_questions(person_id: str, status: Optional[str] = None) -> list[dict]:
    return [{k: (v.isoformat(timespec="seconds") if isinstance(v, datetime) else v) for k, v in q.items()}
            for q in get_db().list_questions(person_id, status)]


class FamilyAnswer(BaseModel):
    answer: str
    answered_by: str


@app.post("/questions/{question_id}/answer", dependencies=secured)
def answer_question(question_id: int, body: FamilyAnswer) -> dict:
    try:
        fact_id = get_db().record_family_answer(question_id, body.answer, body.answered_by)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such question")
    return {"fact_id": fact_id}


class MedLogRequest(BaseModel):
    person_id: str
    medicine: str
    logged_by: str
    given_at: Optional[datetime] = None


@app.post("/med-log", dependencies=secured)
def add_med_log(body: MedLogRequest) -> dict:
    get_db().add_med_log(MedLogEntry(person_id=body.person_id, medicine=body.medicine,
                                     given_at=body.given_at or datetime.now(), logged_by=body.logged_by))
    return {"ok": True}


@app.get("/med-log/{person_id}", dependencies=secured)
def get_med_log(person_id: str) -> list[dict]:
    return [m.model_dump(mode="json") for m in get_db().get_med_log(person_id)]


# ---------------------------------------------------------------------------
# Demo helpers (no model calls, no credits used)
# ---------------------------------------------------------------------------
@app.post("/demo/reset", dependencies=secured)
def demo_reset() -> dict:
    from backend.ai.fake_db import FakeDB

    db = get_db()
    if hasattr(db, "reset"):  # the SQLite database: empty it rather than swap it out
        db.reset()
    else:
        set_db(FakeDB())
    PROFILES.clear()
    _load_default_profile()
    return {"ok": True}


@app.post("/demo/load", dependencies=secured)
def demo_load() -> dict:
    """Load the sample persona's facts directly (skips the model). Dates move forward by whole
    weeks, so weekdays in the facts stay correct and the last conversation falls in the past week.
    Also logs her morning tablets at 9 am today (or 30 minutes ago if it isn't 9 yet)."""
    data = json.loads(SAMPLES_PATH.read_text())
    persona, convs = data["persona"], data["conversations"]
    last = max(date.fromisoformat(c["conversation_date"]) for c in convs)
    gap = ((date.today() - timedelta(days=1)) - last).days
    shift = timedelta(days=gap - (gap % 7))
    db = get_db()
    count = 0
    for c in convs:
        conv_date = date.fromisoformat(c["conversation_date"]) + shift
        for exp in c["expected"]:
            db.add_fact(Fact(person_id=persona["person_id"], event=exp["quote_contains"], who=exp.get("who", []),
                             event_date=date.fromisoformat(exp["date"]) + shift, event_time=exp.get("time"),
                             source_quote=exp["quote_contains"], source="conversation", conversation_date=conv_date))
            count += 1
    now = datetime.now()
    nine = now.replace(hour=9, minute=0, second=0, microsecond=0)
    db.add_med_log(MedLogEntry(person_id=persona["person_id"], medicine="morning tablets",
                               given_at=nine if now >= nine else now - timedelta(minutes=30),
                               logged_by=persona["family"][0]))
    return {"ok": True, "facts_loaded": count, "person_id": persona["person_id"]}
