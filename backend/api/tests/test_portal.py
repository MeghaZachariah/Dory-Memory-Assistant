"""The family website's endpoints: always the signed-in family's person, in the shapes the pages read."""
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

os.environ.setdefault("DORY_LOG_PATH", str(Path(tempfile.gettempdir()) / "dory_test_calls.jsonl"))
os.environ["DORY_DB"] = "memory"

from fastapi.testclient import TestClient  # noqa: E402

from backend.ai import client as ai_client  # noqa: E402
from backend.ai.schemas import Fact  # noqa: E402
from backend.ai.tests.fake_model import FakeModel  # noqa: E402
from backend.api import auth, main  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_DB", tmp_path / "auth.db")
    fm = FakeModel()
    ai_client.set_backend(fm)
    c = TestClient(main.app)
    c.post("/demo/reset")
    c.post("/demo/load")
    auth.ensure_demo_account()
    token = c.post("/auth/login", json={"email": auth.DEMO_EMAIL, "password": auth.DEMO_PASSWORD}).json()["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    yield c, fm
    ai_client.set_backend(None)


def test_needs_a_login(api):
    c, _ = api
    for path in ("/dashboard/summary", "/dashboard/facts", "/dashboard/logs", "/dashboard/questions",
                 "/dashboard/medications", "/patient/today", "/telegram/status"):
        assert TestClient(main.app).get(path).status_code == 401, path
        assert c.get(path).status_code == 200, path


def test_routes_are_not_taken_by_the_bot_dashboard(api):
    c, _ = api
    s = c.get("/dashboard/summary").json()
    assert "person" not in s and "headline" in s  # not compat's /dashboard/{person_id}


def test_facts_receipts_and_memory_book(api):
    c, _ = api
    facts = c.get("/dashboard/facts").json()["facts"]
    assert len(facts) == 15
    f = facts[0]
    assert {"id", "fact", "quote", "source", "date"} <= set(f) and f["source"] == "Said by Mary"
    saved = c.post("/dashboard/facts", json={"fact": "Mary's wedding was on June 12, 1989", "quote": "From Anu",
                                             "source_type": "family_added"}).json()
    assert saved["source"] == "Memory Book" and saved["quote"] == "From Anu"
    assert c.get("/dashboard/facts").json()["facts"][0]["id"] == saved["id"]  # newest first
    assert c.post("/dashboard/facts", json={"fact": "  "}).status_code == 400


def test_chat_then_logs_questions_and_summary(api):
    c, fm = api
    fm.on("classify", {"kind": "none"})
    fm.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    r = c.post("/chat", json={"person_id": "mary", "message": "Where is my blue umbrella?"}).json()
    assert r["answer"] == r["reply"] and r["asking_family"] is True  # what the website's voice screen reads
    med = c.post("/chat", json={"person_id": "mary", "message": "Did I take my tablets?"}).json()
    assert med["asking_family"] is False and "9" in med["answer"]

    logs = c.get("/dashboard/logs").json()["logs"]
    assert [l["status"] for l in logs[:2]] == ["Medicine rule", "Asked family"]
    assert logs[0]["source"] == "Caregiver medicine log" and logs[0]["timestamp"]

    qs = c.get("/dashboard/questions").json()["questions"]
    umbrella = next(q for q in qs if "umbrella" in q["question"])
    assert umbrella["status"] == "Pending" and umbrella["asked_at"]
    c.post(f"/questions/{umbrella['id']}/answer", json={"answer": "In the hall cupboard", "answered_by": "Anu"})
    umbrella = next(q for q in c.get("/dashboard/questions").json()["questions"] if q["id"] == umbrella["id"])
    assert umbrella["status"] == "Answered" and umbrella["memory_created"] and umbrella["answered_by"] == "Anu"

    s = c.get("/dashboard/summary").json()
    assert "summary" not in s  # the page would mistake it for the whole summary
    assert s["unknown_questions"] == 1 and s["medication_alerts"] == 1 and s["family_response_count"] == 1
    assert len(s["week"]) == 7 and s["week"][-1] == 100 and len(s["week_labels"]) == 7
    assert s["activity"] and s["family_responses"][0]["text"].startswith("Anu:")


def test_medications_and_today(api):
    c, _ = api
    meds = c.get("/dashboard/medications").json()["medications"]
    assert meds and meds[0]["verified"] and meds[0]["caregiver"] == "Anu" and meds[0]["name"] == "morning tablets"
    main.get_db().add_fact(Fact(person_id="mary", event="Ravi is visiting", who=["Ravi"], event_date=date.today(),
                                event_time="4 pm", source_quote="Ravi is coming", conversation_date=date(2026, 1, 1)))
    events = c.get("/patient/today").json()["events"]
    ravi = next(e for e in events if e["title"] == "Ravi is visiting")
    assert ravi["type"] == "visit" and ravi["description"] == "4 pm"


def test_another_family_sees_only_its_own(api):
    c, _ = api
    other = TestClient(main.app)
    tok = other.post("/auth/signup", json={"email": "sam@example.com", "password": "jazz-and-tea",
                                           "person_name": "Joseph"}).json()["token"]
    other.headers["Authorization"] = f"Bearer {tok}"
    assert other.get("/dashboard/facts").json()["facts"] == []
    other.post("/dashboard/facts", json={"fact": "Joseph likes jazz"})
    assert not any(f["fact"] == "Joseph likes jazz" for f in c.get("/dashboard/facts").json()["facts"])


def test_telegram_status_without_bot(api, monkeypatch):
    c, _ = api
    t = c.get("/telegram/status").json()
    assert t["status"] in ("Connected", "Not connected") and "resolved_questions" in t
