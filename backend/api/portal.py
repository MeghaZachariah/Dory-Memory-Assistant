"""The family website's API (Frontend/src/AuthenticatedApp.jsx): patient portal and care center.

Every endpoint here works on the signed-in family's person (Authorization: Bearer <token>),
so the website never sends a person_id. The data comes from the same database the phone app
and the Telegram bot use, and nothing here calls a model: the pages refresh every 15 seconds.

    GET  /dashboard/summary      today's summary, counts, week trend, activity
    GET  /dashboard/facts        memory receipts          POST /dashboard/facts  add to the Memory Book
    GET  /dashboard/logs         Dory's answers, with the checker's verdict
    GET  /dashboard/questions    questions sent to the family
    GET  /dashboard/medications  caregiver-confirmed medicines
    GET  /patient/today          today's plans, for the patient portal
    GET  /telegram/status        the family bot

Must be registered before compat.router, whose /dashboard/{person_id} would otherwise take
/dashboard/summary as a person called "summary".
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.ai import summary
from backend.ai.db_interface import get_db
from backend.ai.schemas import Fact
from backend.api.auth import Account

router = APIRouter()


def _account(request: Request) -> Account:
    account: Optional[Account] = getattr(request.state, "account", None)
    if account is None:
        raise HTTPException(status_code=401, detail="Please sign in")
    return account


def _when(value) -> Optional[str]:
    """"Oct 28, 3:40 PM", or "Oct 28" for a plain date."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return f"{value:%b} {value.day}, {value.strftime('%I:%M %p').lstrip('0')}"
    return f"{value:%b} {value.day}"


def _answers(person_id: str) -> list[dict]:
    """Every answer Dory gave, oldest first, with a stable id."""
    return [{"id": i, "ts": e["ts"], **e["payload"]}
            for i, e in enumerate(get_db().get_events(person_id, kind="answer"), start=1)]


def _verdict(a: dict) -> str:
    if a.get("health_kind") == "urgent":
        return "Emergency"
    if a.get("blocked"):
        return "Blocked by checker"
    return {"answered": "Passed", "unknown": "Asked family", "refused": "Medicine rule"}.get(a.get("status"), "Unknown")


_SOURCE = {"conversation": "Said by {name}", "memory_book": "Memory Book", "family_answer": "Told by {who}"}


def _fact_out(f: Fact, name: str) -> dict:
    source = _SOURCE.get(f.source, "Verified fact").format(name=name or "them", who=f.answered_by or "family")
    when = f.event_date or f.conversation_date or (f.created_at.date() if f.created_at else None)
    return {
        "id": f.fact_id,
        "fact": f.event,
        "text": f.event,
        "quote": f.source_quote,
        "source_quote": f.source_quote,
        "source": source,
        "source_type": f.source,
        "tag": "Waiting for family" if f.verification == "pending" else source,
        "date": _when(when),
        "created_at": _when(f.created_at),
        "verification": f.verification,
    }


# --- today's summary -----------------------------------------------------------
def _key(question: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()


@router.get("/dashboard/summary")
def dashboard_summary(request: Request) -> dict:
    account = _account(request)
    person, name = account.person_id, account.person_name
    today = date.today()
    answers = _answers(person)
    todays = [a for a in answers if a["ts"].date() == today]
    report = summary(person, person_name=name, use_model=False)

    passed = sum(1 for a in todays if a.get("status") == "answered" and not a.get("blocked"))
    blocked = sum(1 for a in todays if a.get("blocked"))
    repeated = sum(1 for n in Counter(_key(a.get("question", "")) for a in todays).values() if n >= 2)

    # Questions asked on each of the last 7 days, scaled so the busiest day is 100.
    days = [today - timedelta(days=d) for d in range(6, -1, -1)]
    per_day = [sum(1 for a in answers if a["ts"].date() == d) for d in days]
    busiest = max(per_day) or 1

    questions = get_db().list_questions(person)
    answered_today = [q for q in questions if q["status"] == "answered" and q.get("created_at")
                      and q["created_at"].date() == today]
    activity = [{"id": a["id"], "text": f'Asked “{a.get("question", "")}” · {_verdict(a)}'}
                for a in reversed(todays[-5:])]
    responses = [{"id": q["id"], "text": f'{q.get("answered_by") or "Family"}: “{q.get("answer")}”',
                  "person": q.get("answered_by"), "question": q["question"]} for q in answered_today[:5]]

    # NB: no "summary" key. The website reads `payload.summary || payload` as the summary object.
    return {
        "headline": f"{name}’s day so far" if name else "Today so far",
        "briefing": report.text,
        "confidence": round(100 * passed / (passed + blocked)) if passed + blocked else None,
        "week": [round(100 * n / busiest) for n in per_day],
        "week_labels": [d.strftime("%a") for d in days],
        "repeated_questions": repeated,
        "unknown_questions": sum(1 for a in todays if a.get("status") == "unknown"),
        "medication_alerts": sum(1 for a in todays if a.get("route") in ("medication", "override")),
        "family_response_count": len(answered_today),
        "alerts": report.alerts,
        "activity": activity,
        "family_responses": responses,
    }


# --- memories -------------------------------------------------------------------
@router.get("/dashboard/facts")
def dashboard_facts(request: Request) -> dict:
    account = _account(request)
    facts = [f for f in get_db().get_facts(account.person_id) if f.verification != "rejected"]
    facts.sort(key=lambda f: (f.created_at or datetime.min, f.fact_id or 0), reverse=True)
    return {"facts": [_fact_out(f, account.person_name) for f in facts]}


class MemoryIn(BaseModel):
    fact: str  # e.g. "Mary's wedding was on June 12, 1989"
    quote: str = ""  # optional description or source words
    source_type: str = "family_added"


@router.post("/dashboard/facts")
def add_fact(body: MemoryIn, request: Request) -> dict:
    """Memory Book: the family adds something Dory may use (a trusted source)."""
    account = _account(request)
    text = body.fact.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Please write the memory first")
    fact_id = get_db().add_fact(Fact(person_id=account.person_id, event=text, source_quote=body.quote.strip() or text,
                                     source="memory_book", answered_by="Family"))
    saved = next(f for f in get_db().get_facts(account.person_id) if f.fact_id == fact_id)
    return _fact_out(saved, account.person_name)


# --- Dory's answers -------------------------------------------------------------
@router.get("/dashboard/logs")
def dashboard_logs(request: Request) -> dict:
    account = _account(request)
    by_id = {f.fact_id: f for f in get_db().get_facts(account.person_id)}
    logs = []
    for a in reversed(_answers(account.person_id)[-100:]):
        spoken = a.get("status") == "answered" and not a.get("blocked")
        ids = a.get("fact_ids_used") or [] if spoken else []
        sources = sorted({_fact_out(by_id[i], account.person_name)["source"] for i in ids if i in by_id})
        logs.append({
            "id": a["id"],
            "question": a.get("question"),
            "answer": a.get("reply"),
            "draft": a.get("draft_answer") if a.get("blocked") else None,
            "status": _verdict(a),
            "source": " · ".join(sources) if sources else {
                "medication": "Caregiver medicine log", "override": "Safety rule", "statement": "Noted for family check",
                "conversation": "Conversation (no facts claimed)",
            }.get(a.get("route"), "No source: not answered"),
            "route": a.get("route"),
            "fact_ids": ids,
            "timestamp": _when(a["ts"]),
        })
    return {"logs": logs}


# --- questions for the family ---------------------------------------------------
@router.get("/dashboard/questions")
def dashboard_questions(request: Request) -> dict:
    account = _account(request)
    out = []
    for q in get_db().list_questions(account.person_id):
        answered = q["status"] == "answered"
        out.append({
            "id": q["id"],
            "question": q["question"],
            "text": q["question"],
            "status": "Answered" if answered else "Pending",
            "reason": q.get("reason"),
            "answer": q.get("answer"),
            "answered_by": q.get("answered_by"),
            "asked_at": _when(q.get("created_at")),
            "date": _when(q.get("created_at")),
            "times_asked": q.get("times_asked", 1),
            # A family answer becomes a fact Dory can use next time (not for yes/no checks).
            "memory_created": answered and q.get("reason") != "verify_statement",
            "flagged": q.get("reason") in ("urgent", "medication"),
        })
    return {"questions": out}


# --- medicines ------------------------------------------------------------------
@router.get("/dashboard/medications")
def dashboard_medications(request: Request) -> dict:
    account = _account(request)
    meds = sorted(get_db().get_med_log(account.person_id), key=lambda m: m.given_at, reverse=True)
    return {"medications": [{
        "id": i,
        "name": m.medicine,
        "time": m.given_at.strftime("%I:%M %p").lstrip("0"),
        "date": _when(m.given_at.date()),
        "caregiver": m.logged_by,
        "status": "Verified",
        "verified": True,
    } for i, m in enumerate(meds, start=1)]}


# --- the patient portal ---------------------------------------------------------
@router.get("/patient/today")
def patient_today(request: Request) -> dict:
    """Plans for today that Dory may tell the person about (confirmed and shareable)."""
    account = _account(request)
    today = date.today()
    facts = [f for f in get_db().get_facts(account.person_id, since=today, until=today)
             if f.event_date == today and f.verification == "confirmed" and f.sensitivity != "do_not_share"]
    return {"events": [{
        "id": f.fact_id,
        "title": f.event,
        "description": f.event_time or "Today",
        "time": f.event_time,
        "type": "visit" if f.who else "reminder",
    } for f in facts]}


# --- the family's Telegram bot --------------------------------------------------
@router.get("/telegram/status")
def telegram_status(request: Request) -> dict:
    account = _account(request)
    # The bot keeps who has joined in backend/bot/registry.json (read directly: importing the
    # bot would need a Telegram token).
    registry = Path(os.getenv("DORY_REGISTRY") or Path(__file__).resolve().parents[1] / "bot" / "registry.json")
    try:
        reg = json.loads(registry.read_text())
    except (OSError, ValueError):
        reg = {}
    members = reg.get("members", {})
    questions = get_db().list_questions(account.person_id)
    today = date.today()
    return {
        "status": "Connected" if members else "Not connected",
        "family_members_connected": len(members),
        "bot_username": None,
        "questions_sent_today": sum(1 for q in questions if q.get("created_at") and q["created_at"].date() == today),
        "resolved_questions": sum(1 for q in questions if q["status"] == "answered"),
        "last_activity": _when(max((q["created_at"] for q in questions if q.get("created_at")), default=None)),
    }
