"""Server tests. Offline: the AI calls go to the scripted fake model."""
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("DORY_LOG_PATH", str(Path(tempfile.gettempdir()) / "dory_test_calls.jsonl"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.ai import client as ai_client  # noqa: E402
from backend.ai.evening import CLOSING, QUESTIONS  # noqa: E402
from backend.ai.tests.fake_model import FakeModel  # noqa: E402
from backend.api import main  # noqa: E402


@pytest.fixture
def api():
    fm = FakeModel()
    ai_client.set_backend(fm)
    c = TestClient(main.app)
    c.post("/demo/reset")
    yield c, fm
    ai_client.set_backend(None)


def test_health(api):
    c, _ = api
    assert c.get("/health").json()["ok"] is True


def test_demo_load_and_facts(api):
    c, fm = api
    r = c.post("/demo/load").json()
    assert r["facts_loaded"] == 15
    facts = c.get("/facts/mary").json()
    assert len(facts) == 15 and all(f["source_quote"] for f in facts)
    assert fm.calls == []  # demo load uses no credits


def test_chat_answer_and_answers_log(api):
    c, fm = api
    c.post("/demo/load")
    fact = next(f for f in c.get("/facts/mary").json() if "banana chips" in f["event"])
    fid = fact["fact_id"]
    fm.on("answer", {"answer": fact["event"], "fact_ids_used": [fid], "status": "answered"})
    fm.on("check", {"verdict": "supported"})
    r = c.post("/chat", json={"person_id": "mary", "message": "What's happening?"}).json()
    assert r["status"] == "answered" and r["reply"] == fact["event"]
    log = c.get("/answers/mary").json()
    assert log[0]["badge"] == "passed"


def test_medication_uses_med_log(api):
    c, fm = api
    c.post("/demo/load")
    r = c.post("/chat", json={"person_id": "mary", "message": "Did I take my tablets?"}).json()
    assert r["route"] == "medication" and "caregiver logged your morning tablets at" in r["reply"]
    assert fm.calls == []
    assert c.get("/questions/mary?status=pending").json()[0]["reason"] == "medication"


def test_ask_family_loop(api):
    c, fm = api
    fm.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    r = c.post("/chat", json={"person_id": "mary", "message": "When was my wedding?"}).json()
    qid = r["pending_question_id"]
    assert qid and r["status"] == "unknown"
    saved = c.post(f"/questions/{qid}/answer", json={"answer": "12 June 1989", "answered_by": "Anu"}).json()
    assert c.get("/questions/mary?status=answered").json()[0]["answered_by"] == "Anu"
    # Next time Dory can answer from the family's reply.
    fm.on("answer", {"answer": "You were married on 12 June 1989.", "fact_ids_used": [saved["fact_id"]], "status": "answered"})
    fm.on("check", {"verdict": "supported"})
    r2 = c.post("/chat", json={"person_id": "mary", "message": "When was my wedding?"}).json()
    assert r2["status"] == "answered" and "1989" in r2["reply"]


def test_memory_book_and_med_log_endpoints(api):
    c, _ = api
    fid = c.post("/facts/mary", json={"event": "Her husband George passed away", "sensitivity": "do_not_share"}).json()["fact_id"]
    assert any(f["fact_id"] == fid and f["source"] == "memory_book" for f in c.get("/facts/mary").json())
    c.post("/med-log", json={"person_id": "mary", "medicine": "evening tablets", "logged_by": "Ravi"})
    assert c.get("/med-log/mary").json()[0]["medicine"] == "evening tablets"


def test_full_evening_call(api):
    c, fm = api
    fm.on("extract", {"facts": [{"event": "Anu visited", "who": ["Anu"], "when_text": "today",
                                 "source_quote": "Anu came to see me"}]})
    turns = []
    replies = ["It was nice.", "Anu came to see me.", "Rice and fish.", "Nothing planned."]
    for i in range(len(QUESTIONS) + 1):
        out = c.post("/evening/turn", json={"person_id": "mary", "turns": turns,
                                            "conversation_date": "2026-10-21"}).json()
        turns.append({"speaker": "Dory", "text": out["say"]})
        if out["done"]:
            break
        assert QUESTIONS[i].format(name=", Mary") in out["say"]
        turns.append({"speaker": "Mary", "text": replies[i]})
    assert out["done"] and out["say"] == CLOSING.format(name=", Mary")
    assert out["facts_saved"] == 1
    assert c.get("/facts/mary").json()[0]["event_date"] == "2026-10-21"


def test_evening_call_stops_on_goodbye(api):
    c, fm = api
    fm.on("extract", {"facts": []})
    turns = [{"speaker": "Dory", "text": "How was your day?"}, {"speaker": "Mary", "text": "I'm tired, good night."}]
    out = c.post("/evening/turn", json={"person_id": "mary", "turns": turns}).json()
    assert out["done"]


def test_evening_call_urgent_alerts_family(api):
    c, fm = api
    turns = [{"speaker": "Dory", "text": "How was your day?"}, {"speaker": "Mary", "text": "I fell in the kitchen."}]
    out = c.post("/evening/turn", json={"person_id": "mary", "turns": turns}).json()
    assert out["alerted_family"] and "letting your family know" in out["say"]
    assert c.get("/questions/mary?status=pending").json()[0]["reason"] == "urgent"


def test_briefing_and_summary(api):
    c, fm = api
    c.post("/demo/load")
    fm.on("briefing", "Good morning, Mary.")
    b = c.get("/briefing/mary").json()
    assert b["text"].startswith("Good morning, Mary")
    fm.on("summary", "A quiet day.")
    assert c.get("/summary/mary").json()["text"] == "A quiet day."


def test_token_required_when_set(api, monkeypatch):
    c, _ = api
    monkeypatch.setattr(main, "APP_TOKEN", "secret")
    assert c.get("/facts/mary").status_code == 401
    assert c.get("/facts/mary", headers={"X-Dory-Token": "secret"}).status_code == 200
    assert c.get("/health").status_code == 200
