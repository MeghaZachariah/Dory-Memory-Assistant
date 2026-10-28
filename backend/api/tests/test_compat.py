"""The web screen, dashboard and bot's API (mock_server shapes) on the real backend."""
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("DORY_LOG_PATH", str(Path(tempfile.gettempdir()) / "dory_test_calls.jsonl"))
os.environ["DORY_DB"] = "memory"

from fastapi.testclient import TestClient  # noqa: E402

from backend.ai import client as ai_client  # noqa: E402
from backend.ai.tests.fake_model import FakeModel  # noqa: E402
from backend.api import compat, main  # noqa: E402


@pytest.fixture
def api():
    fm = FakeModel()
    ai_client.set_backend(fm)
    c = TestClient(main.app)
    c.post("/demo/reset")
    c.post("/demo/load")
    compat._evenings.clear()
    yield c, fm
    ai_client.set_backend(None)


def test_chat_takes_the_web_screens_shape(api):
    c, _ = api
    r = c.post("/chat", json={"person_id": "mary", "text": "Did I take my tablets?", "mode": "chat"}).json()
    assert r["status"] == "refused" and r["topic"] == "medicine" and r["model_tier"] == "rules"
    assert r["done"] is False and r["sources"] == [] and "morning tablets" in r["reply"]
    # the app's shape still works, with the same extra fields
    r2 = c.post("/chat", json={"person_id": "mary", "message": "Did I take my tablets?"}).json()
    assert r2["route"] == "medication" and r2["topic"] == "medicine"


def test_emergency_is_flagged_for_the_bot(api):
    c, _ = api
    r = c.post("/chat", json={"person_id": "mary", "text": "I fell in the kitchen"}).json()
    assert r["status"] == "emergency" and r["topic"] == "emergency"
    log = c.get("/dashboard/mary").json()["answers_log"]
    assert log[0]["status"] == "emergency" and log[0]["question"] == "I fell in the kitchen"


def test_sources_carry_the_receipts(api):
    c, _ = api
    fact = c.get("/dashboard/mary").json()["facts"][0]
    [src] = compat._sources("mary", [fact["id"], 99999])  # unknown ids are dropped
    assert src == {"fact_id": fact["id"], "quote": fact["source_quote"], "source_type": "person_chat",
                   "label": "You told me this"}


def test_blocked_answer_shows_no_sources(api):
    c, fm = api
    fid = c.get("/dashboard/mary").json()["facts"][0]["id"]
    fm.on("classify", {"kind": "none"})
    fm.on("answer", {"answer": "Yes, Zed visited on Friday.", "fact_ids_used": [fid], "status": "answered"})
    fm.on("check", {"verdict": "unsupported", "reasons": ["not in the fact"]})
    r = c.post("/chat", json={"person_id": "mary", "text": "Did anyone visit me?"}).json()
    assert r["blocked"] and r["sources"] == [] and r["draft"] == "Yes, Zed visited on Friday."
    assert c.get("/dashboard/mary").json()["answers_log"][0]["sources"] == []


def test_unknown_goes_to_family_and_family_answers(api):
    c, fm = api
    fm.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    fm.on("classify", {"kind": "none"})
    r = c.post("/chat", json={"person_id": "mary", "text": "Where is my blue umbrella?"}).json()
    assert r["status"] == "unknown" and r["pending_question_id"]
    d = c.get("/dashboard/mary").json()
    q = next(q for q in d["questions"] if q["id"] == r["pending_question_id"])
    assert q["status"] == "pending" and q["text"] == "Where is my blue umbrella?" and q["asked_to"] == "Anu"
    assert any(a["level"] == "action" and "umbrella" in a["text"] for a in d["alerts"])
    assert d["counts"]["asked_family"] == 1

    stranger = c.post("/family/answer", json={"question_id": q["id"], "answer": "Hall", "answered_by": "Bob"})
    assert stranger.status_code == 403
    ok = c.post("/family/answer", json={"question_id": q["id"], "answer": "By the front door", "answered_by": "Anu"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["question"]["status"] == "answered" and body["fact"]["source_type"] == "family_answer"
    assert body["fact"]["confirmed_by"] == "Anu"
    again = c.post("/family/answer", json={"question_id": q["id"], "answer": "x", "answered_by": "Anu"})
    assert again.status_code == 409


def test_only_caregivers_log_medicine(api):
    c, _ = api
    bad = c.post("/med/log", json={"medicine": "Evening tablets", "time": "20:00", "confirmed_by": "Anu"})
    assert bad.status_code == 403
    ok = c.post("/med/log", json={"medicine": "Evening tablets", "time": "20:00", "confirmed_by": "Priya (caregiver)"})
    assert ok.status_code == 200 and ok.json()["time"] == "20:00" and ok.json()["confirmed_by"] == "Priya (caregiver)"
    meds = c.get("/dashboard/mary").json()["med_log"]
    assert [m["medicine"] for m in meds][-1] == "Evening tablets"


def test_memory_book(api):
    c, _ = api
    assert c.post("/memory/fact", json={"text": "x", "added_by": "Stranger"}).status_code == 403
    f = c.post("/memory/fact", json={"text": "Mary's wedding was on June 12, 1989", "added_by": "Ravi"}).json()
    assert f["source_type"] == "memory_book" and f["confirmed_by"] == "Ravi"
    assert any(x["id"] == f["id"] for x in c.get("/dashboard/mary").json()["facts"])


def test_dashboard_shape_and_no_model_calls(api):
    c, fm = api
    d = c.get("/dashboard/mary").json()
    assert set(d) == {"person", "summary", "counts", "alerts", "facts", "questions", "answers_log", "med_log"}
    assert d["person"] == {"id": "mary", "name": "Mary"}
    assert len(d["facts"]) == 15 and d["med_log"][0]["confirmed_by"] == "Anu"
    assert set(d["counts"]) == {"asked", "answered_by_dory", "asked_family", "blocked", "refused_medicine"}
    assert fm.calls == []  # polled every few seconds: must never call the model


def test_evening_call_through_chat_then_finish(api):
    c, fm = api
    lines = iter(["Who came to see you today?", "Lovely. What did you eat?"])
    fm.on("evening", lambda m: {"say": next(lines, ""), "done": False})  # "" -> fixed script / end
    fm.on("extract", {"facts": [{"event": "Ravi visited", "who": ["Ravi"], "when_text": "today",
                                 "source_quote": "Ravi came over"}]})
    said = []
    turn, text = 0, ""
    while True:
        r = c.post("/chat", json={"person_id": "mary", "text": text, "mode": "evening", "turn": turn}).json()
        said.append(r["reply"])
        if r["done"]:
            break
        text = ["It was fine.", "Ravi came over.", "Rice.", "bye"][turn]
        turn += 1
    assert said[0].startswith("Good evening") and said[1] == "Who came to see you today?"
    # the model saw the whole call, not just the last answer
    assert "Mary: It was fine." in fm.calls_for("evening")[-1]["messages"][1]["content"]
    out = c.post("/checkin/evening/finish", json={"person_id": "mary", "transcript": []}).json()
    assert out["facts_saved"] == 1 and out["facts"][0]["text"] == "Ravi visited"


def test_evening_finish_after_stopping_early(api):
    c, fm = api
    fm.on("extract", {"facts": [{"event": "Anu phoned", "who": ["Anu"], "when_text": "today",
                                 "source_quote": "Anu phoned me"}]})
    transcript = [{"role": "dory", "text": "How was your day?"}, {"role": "person", "text": "Anu phoned me"}]
    out = c.post("/checkin/evening/finish", json={"person_id": "mary", "transcript": transcript}).json()
    assert out["facts_saved"] == 1 and out["facts"][0]["source_type"] == "person_chat"


def test_morning_briefing(api):
    c, fm = api
    fm.on("briefing", "Good morning, Mary.")
    b = c.get("/briefing/morning", params={"person_id": "mary"}).json()
    assert b["text"] and isinstance(b["sources"], list)
