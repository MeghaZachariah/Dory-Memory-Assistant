"""
Dory MOCK backend.

Purpose: lets Person B build the voice screen, dashboard and Telegram bot
before Person A's AI pipeline and Person C's database exist. Every reply is
scripted. NO AI is called here.

When the real backend is ready, it must return the same JSON shapes
(see API_CONTRACT.md). Then the frontend only needs a new base URL.

Run:
    pip install fastapi "uvicorn[standard]"
    uvicorn mock_server:app --reload --port 8000
Docs (try every endpoint in the browser):
    http://localhost:8000/docs
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Dory mock backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSON_ID = "mum-demo"
PERSON_NAME = "Mum"
ASK_TO = "Anu"
# Only these people may answer Dory's questions (permission rule from the design).
REGISTERED_FAMILY = {"Anu", "Priya (caregiver)"}
CAREGIVERS = {"Priya (caregiver)"}

EVENING_QUESTIONS = [
    "Hello. How was your day today?",
    "Did anyone come to see you?",
    "What did you have to eat?",
    "Is there anything you are looking forward to tomorrow?",
]
EVENING_CLOSING = "Thank you for telling me. I have saved your day. Rest well."

EMERGENCY = re.compile(
    r"\b(i fell|fallen|chest pain|can't breathe|cannot breathe|help me|bleeding)\b"
)
MEDICAL = re.compile(r"\b(tablet|tablets|pill|pills|medicine|medication|dose)\b")
DAY_Q = re.compile(r"(what day|which day|what's the day|what is the date|today's date|what date)")
DOCTOR_Q = re.compile(r"\b(doctor|appointment)\b")
VISIT_Q = re.compile(r"\b(visit|visited|anu|yesterday|who came)\b")


def fresh_state() -> dict:
    today = date.today()
    yesterday = today - timedelta(days=1)
    return {
        "facts": [
            {
                "id": 1,
                "text": "Anu visited",
                "source_quote": "Anu came and we had fish curry",
                "source_type": "person_chat",
                "source_time": f"{yesterday}T20:05:00",
                "confirmed_by": None,
            },
            {
                "id": 2,
                "text": "The doctor comes at 4 today",
                "source_quote": None,
                "source_type": "memory_book",
                "source_time": f"{today}T07:00:00",
                "confirmed_by": "Anu",
            },
        ],
        "questions": [],
        "answers_log": [],
        "med_log": [
            {
                "id": 1,
                "medicine": "Morning tablets",
                "time": "09:00",
                "date": str(today),
                "confirmed_by": "Priya (caregiver)",
            }
        ],
        "next": {"fact": 3, "question": 1, "answer": 1, "med": 2},
    }


STATE = fresh_state()


# ---------- helpers ----------
def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).strip()


def tokens(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) > 2}


def source_label(fact: dict) -> str:
    kind = fact["source_type"]
    if kind == "person_chat":
        return "You told me this last night"
    if kind == "memory_book":
        return "Your family wrote this in your Memory Book"
    if kind == "family_answer":
        return f"{fact['confirmed_by']} told me this"
    return "From my notes"


def public_source(fact: dict) -> dict:
    return {
        "fact_id": fact["id"],
        "quote": fact["source_quote"],
        "source_type": fact["source_type"],
        "label": source_label(fact),
    }


def get_fact(fact_id: int) -> dict:
    return next(f for f in STATE["facts"] if f["id"] == fact_id)


def find_answered_question(norm: str) -> Optional[dict]:
    asked = tokens(norm)
    for q in STATE["questions"]:
        if q["status"] not in ("answered", "approved"):
            continue
        other = tokens(q["text"])
        if norm == normalize(q["text"]):
            return q
        if asked and other and len(asked & other) / len(asked | other) >= 0.6:
            return q
        if "wedding" in asked and "wedding" in other:
            return q
    return None


def pending_question_for(text: str, norm: str) -> dict:
    """Merge duplicates: one pending request per question (anti-spam rule)."""
    for q in STATE["questions"]:
        if q["status"] == "pending" and normalize(q["text"]) == norm:
            return q
    q = {
        "id": STATE["next"]["question"],
        "text": text,
        "status": "pending",
        "asked_to": ASK_TO,
        "asked_at": datetime.now().isoformat(timespec="seconds"),
        "answer": None,
        "answered_by": None,
    }
    STATE["next"]["question"] += 1
    STATE["questions"].append(q)
    return q


def reply_payload(
    reply: str,
    status: str,
    topic: str,
    sources: list | None = None,
    blocked: bool = False,
    pending_question_id: int | None = None,
    tier: str = "nano",
    draft: str | None = None,
) -> dict:
    return {
        "reply": reply,
        "status": status,  # answered | unknown | refused | emergency
        "topic": topic,
        "sources": sources or [],
        "blocked": blocked,
        "pending_question_id": pending_question_id,
        "model_tier": tier,
        "draft": draft,
    }


# ---------- chat routing (scripted stand-in for the real AI pipeline) ----------
def route(text: str, norm: str) -> dict:
    # 1) Emergency words: fixed calm reply, immediate caregiver alert (never model-written).
    if EMERGENCY.search(norm):
        return reply_payload(
            "I am telling Priya right now. Please sit down and stay where you are. "
            "If you need urgent help, call the emergency number.",
            "emergency",
            "emergency",
        )

    # 2) Medicine / health: fixed templates, only the caregiver-confirmed log.
    if MEDICAL.search(norm):
        wants_evening = "night" in norm or "evening" in norm
        entry = None if wants_evening else STATE["med_log"][-1]
        if entry:
            reply = (
                f"Your caregiver wrote down your morning tablets at {entry['time']}. "
                "If you are not sure, please do not take more. I am letting them know you asked."
            )
        else:
            reply = (
                "I cannot check that myself. Please do not take any more until you have asked "
                "your caregiver. I am messaging them now."
            )
        return reply_payload(reply, "refused", "medicine", tier="rules")

    # 3) Facts we can prove.
    if DAY_Q.search(norm):
        today = date.today()
        return reply_payload(
            f"It is {today:%A}, {today:%B} {today.day}.",
            "answered",
            "date",
            sources=[{"fact_id": None, "quote": None, "source_type": "calendar", "label": "Today's calendar"}],
        )
    if DOCTOR_Q.search(norm):
        f = get_fact(2)
        return reply_payload(
            f"{f['text']}. Your family wrote this in your Memory Book.",
            "answered",
            "doctor",
            sources=[public_source(f)],
        )
    if VISIT_Q.search(norm):
        f = get_fact(1)
        return reply_payload(
            "You told me last night that Anu came and you had fish curry.",
            "answered",
            "visit",
            sources=[public_source(f)],
        )

    # 4) Already answered by family earlier? Use it, with the source.
    answered = find_answered_question(norm)
    if answered:
        fact = next(
            (
                f
                for f in STATE["facts"]
                if f["source_type"] == "family_answer"
                and f["source_quote"] == answered["answer"]
            ),
            None,
        )
        return reply_payload(
            f"{answered['answered_by']} told me: {answered['answer']}.",
            "answered",
            "family",
            sources=[public_source(fact)] if fact else [],
            tier="super",
        )

    # 5) Demo of the lie-catcher: the draft is NOT supported by any fact, so it is blocked.
    if "sister" in norm:
        q = pending_question_for(text, norm)
        return reply_payload(
            "I am not sure about that. I have asked your family. I will tell you when they answer.",
            "unknown",
            "other",
            blocked=True,
            pending_question_id=q["id"],
            tier="ultra",
            draft="Your sister Meera visited you yesterday.",
        )

    # 6) Unknown: never guess. Ask the family.
    q = pending_question_for(text, norm)
    return reply_payload(
        f"I am not sure yet. I have asked {ASK_TO}. I will tell you when they answer.",
        "unknown",
        "other",
        pending_question_id=q["id"],
    )


# ---------- request models ----------
class ChatIn(BaseModel):
    person_id: str = PERSON_ID
    text: str = ""
    mode: str = "chat"  # "chat" | "evening"
    turn: int = 0       # evening mode: how many Dory questions were already asked


class TranscriptLine(BaseModel):
    role: str  # "dory" | "person"
    text: str


class EveningFinishIn(BaseModel):
    person_id: str = PERSON_ID
    transcript: list[TranscriptLine]


class FamilyAnswerIn(BaseModel):
    question_id: int
    answer: str
    answered_by: str


class MedLogIn(BaseModel):
    medicine: str
    time: str
    confirmed_by: str


# ---------- endpoints ----------
@app.get("/health")
def health():
    return {"ok": True, "mock": True}


@app.post("/chat")
def chat(body: ChatIn):
    time.sleep(0.5)  # pretend to think, so the UI's "Thinking" state is visible
    if body.mode == "evening":
        done = body.turn >= len(EVENING_QUESTIONS)
        reply = EVENING_CLOSING if done else EVENING_QUESTIONS[body.turn]
        return {"reply": reply, "status": "evening", "done": done, "sources": [], "blocked": False}

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is empty")
    norm = normalize(text)
    result = route(text, norm)
    result["done"] = False
    STATE["answers_log"].append(
        {
            "id": STATE["next"]["answer"],
            "time": datetime.now().isoformat(timespec="seconds"),
            "question": text,
            "answer": result["reply"],
            "draft": result["draft"],
            "status": result["status"],
            "topic": result["topic"],
            "blocked": result["blocked"],
            "sources": result["sources"],
            "model_tier": result["model_tier"],
        }
    )
    STATE["next"]["answer"] += 1
    return result


@app.post("/checkin/evening/finish")
def evening_finish(body: EveningFinishIn):
    """Stand-in for fact extraction. The REAL version must verify that every
    source_quote appears in the transcript and discard facts that fail."""
    transcript_text = " ".join(l.text for l in body.transcript)
    saved = []
    for line in body.transcript:
        quote = line.text.strip()
        if line.role != "person" or len(quote) < 3 or quote not in transcript_text:
            continue
        fact = {
            "id": STATE["next"]["fact"],
            "text": quote,
            "source_quote": quote,
            "source_type": "person_chat",
            "source_time": datetime.now().isoformat(timespec="seconds"),
            "confirmed_by": None,
        }
        STATE["next"]["fact"] += 1
        STATE["facts"].append(fact)
        saved.append(fact)
    return {"facts_saved": len(saved), "facts": saved}


@app.get("/briefing/morning")
def morning_briefing(person_id: str = PERSON_ID):
    today = date.today()
    chat_facts = [f for f in STATE["facts"] if f["source_type"] == "person_chat"]
    book_facts = [f for f in STATE["facts"] if f["source_type"] == "memory_book"]
    parts = [f"Good morning. It is {today:%A}, {today:%B} {today.day}."]
    sources = []
    if chat_facts:
        parts.append(f"Yesterday you told me: {chat_facts[-1]['text']}.")
        sources.append(public_source(chat_facts[-1]))
    if book_facts:
        parts.append(f"{book_facts[-1]['text']}.")
        sources.append(public_source(book_facts[-1]))
    return {"text": " ".join(parts), "sources": sources}


@app.get("/dashboard/{person_id}")
def dashboard(person_id: str):
    log = STATE["answers_log"]
    topic_counts: dict[str, int] = {}
    for entry in log:
        topic_counts[entry["topic"]] = topic_counts.get(entry["topic"], 0) + 1

    alerts = []
    if topic_counts.get("medicine", 0) >= 3:
        alerts.append(
            {"level": "warning", "text": f"Asked about tablets {topic_counts['medicine']} times (caregiver notified)"}
        )
    for topic in ("date", "visit", "doctor"):
        if topic_counts.get(topic, 0) >= 4:
            alerts.append(
                {"level": "info", "text": f"Asked about the {topic} {topic_counts[topic]} times. Answers stayed consistent."}
            )
    for q in STATE["questions"]:
        if q["status"] == "pending":
            alerts.append({"level": "action", "text": f"Question waiting for family: \"{q['text']}\""})
    if any(e["status"] == "emergency" for e in log):
        alerts.append({"level": "urgent", "text": "Emergency words were said. Check in now."})

    return {
        "person": {"id": PERSON_ID, "name": PERSON_NAME},
        "summary": f"{PERSON_NAME} had a calm day. Anu visited yesterday. {len(log)} questions today.",
        "counts": {
            "asked": len(log),
            "answered_by_dory": sum(1 for e in log if e["status"] == "answered" and not e["blocked"]),
            "asked_family": sum(1 for e in log if e["status"] == "unknown"),
            "blocked": sum(1 for e in log if e["blocked"]),
            "refused_medicine": sum(1 for e in log if e["status"] == "refused"),
        },
        "alerts": alerts,
        "facts": STATE["facts"],
        "questions": STATE["questions"],
        "answers_log": list(reversed(log))[:50],
        "med_log": STATE["med_log"],
    }


@app.post("/family/answer")
def family_answer(body: FamilyAnswerIn):
    if body.answered_by not in REGISTERED_FAMILY:
        raise HTTPException(status_code=403, detail="Sender is not a registered family member")
    q = next((q for q in STATE["questions"] if q["id"] == body.question_id), None)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if q["status"] != "pending":
        raise HTTPException(status_code=409, detail="Question already answered")
    q["status"] = "answered"
    q["answer"] = body.answer.strip()
    q["answered_by"] = body.answered_by
    fact = {
        "id": STATE["next"]["fact"],
        "text": f"{q['text']} - {q['answer']}",
        "source_quote": q["answer"],
        "source_type": "family_answer",
        "source_time": datetime.now().isoformat(timespec="seconds"),
        "confirmed_by": body.answered_by,
    }
    STATE["next"]["fact"] += 1
    STATE["facts"].append(fact)
    return {"question": q, "fact": fact}


@app.post("/med/log")
def med_log(body: MedLogIn):
    if body.confirmed_by not in CAREGIVERS:
        raise HTTPException(status_code=403, detail="Only caregivers can log medicine")
    entry = {
        "id": STATE["next"]["med"],
        "medicine": body.medicine,
        "time": body.time,
        "date": str(date.today()),
        "confirmed_by": body.confirmed_by,
    }
    STATE["next"]["med"] += 1
    STATE["med_log"].append(entry)
    return entry


@app.post("/demo/reset")
def demo_reset():
    global STATE
    STATE = fresh_state()
    return {"ok": True}


class MemoryFactIn(BaseModel):
    text: str
    added_by: str


@app.post("/memory/fact")
def add_memory_fact(body: MemoryFactIn):
    """Memory Book: family types a fact in advance (high-trust source)."""
    if body.added_by not in REGISTERED_FAMILY:
        raise HTTPException(status_code=403, detail="Sender is not a registered family member")
    fact = {
        "id": STATE["next"]["fact"],
        "text": body.text.strip(),
        "source_quote": None,
        "source_type": "memory_book",
        "source_time": datetime.now().isoformat(timespec="seconds"),
        "confirmed_by": body.added_by,
    }
    STATE["next"]["fact"] += 1
    STATE["facts"].append(fact)
    return fact
