"""CrudDB on top of Person C's db/crud.py, using a throwaway dory.db."""
from datetime import date, datetime, timedelta

import pytest

from backend.ai import chat
from backend.ai.crud_db import CrudDB
from backend.ai.db_interface import set_db
from backend.ai.schemas import Fact, MedLogEntry
from db import crud


@pytest.fixture
def sql(tmp_path, monkeypatch):
    monkeypatch.setattr(crud, "DB_PATH", str(tmp_path / "dory.db"))
    d = CrudDB()
    set_db(d)
    yield d
    set_db(None)


def test_fact_round_trip_keeps_every_field(sql):
    fid = sql.add_fact(Fact(person_id="mary", event="Anu visited", who=["Anu"], event_date=date(2026, 10, 20),
                            event_time="4 pm", source_quote="Anu came over", sensitivity="tell_gently"))
    assert isinstance(fid, int)
    [f] = sql.get_facts("mary")
    assert (f.fact_id, f.who, f.event_date, f.event_time, f.sensitivity) == (fid, ["Anu"], date(2026, 10, 20), "4 pm", "tell_gently")
    assert isinstance(f.created_at, datetime)
    assert crud.get_facts("mary") == ["Anu visited"]  # her own function sees it too


def test_date_filter_keeps_undated_facts(sql):
    sql.add_fact(Fact(person_id="mary", event="old", event_date=date(2026, 1, 1), source_quote="old"))
    sql.add_fact(Fact(person_id="mary", event="new", event_date=date(2026, 10, 20), source_quote="new"))
    sql.add_fact(Fact(person_id="mary", event="undated", source_quote="undated"))
    assert [f.event for f in sql.get_facts("mary", since=date(2026, 10, 1))] == ["new", "undated"]


def test_facts_added_through_her_crud_are_picked_up(sql):
    crud.add_fact("mary", "Ravi phoned", "evening_chat", "Ravi phoned")
    [f] = sql.get_facts("mary")
    assert isinstance(f.fact_id, int) and f.source == "conversation" and f.verification == "confirmed"
    assert sql.get_facts("mary")[0].fact_id == f.fact_id  # same id the second time


def test_update_fact(sql):
    fid = sql.add_fact(Fact(person_id="mary", event="Ravi phoned", source_quote="Ravi phoned", verification="pending"))
    sql.update_fact(fid, {"verification": "confirmed"})
    assert sql.get_facts("mary")[0].verification == "confirmed"


def test_questions_merge_and_answer(sql):
    q1 = sql.create_pending_question("mary", "Did Anu visit?")
    assert sql.create_pending_question("mary", "did anu visit") == q1
    [q] = sql.list_questions("mary", status="pending")
    assert q["times_asked"] == 2 and isinstance(q["created_at"], datetime)
    fid = sql.record_family_answer(q1, "Yes, on Sunday", "Ravi")
    assert sql.list_questions("mary", status="pending") == []
    [f] = sql.get_facts("mary")
    assert (f.fact_id, f.source, f.answered_by) == (fid, "family_answer", "Ravi")

    q2 = sql.create_pending_question("mary", "Did Ravi phone?", reason="verify_statement")
    sql.close_question(q2, "yes", "Anu")
    assert len(sql.get_facts("mary")) == 1  # closing saves no fact


def test_med_log_newest_first(sql):
    now = datetime.now()
    sql.add_med_log(MedLogEntry(person_id="mary", medicine="Metformin", given_at=now - timedelta(hours=5), logged_by="Anu"))
    sql.add_med_log(MedLogEntry(person_id="mary", medicine="Amlodipine", given_at=now, logged_by="Anu"))
    assert [m.medicine for m in sql.get_med_log("mary")] == ["Amlodipine", "Metformin"]
    assert [m.medicine for m in sql.get_med_log("mary", since=now - timedelta(hours=1))] == ["Amlodipine"]


def test_events(sql):
    sql.log_event("mary", "answer", {"question": "Did Anu visit?", "status": "answered"})
    sql.log_event("mary", "pending_question", {"question": "Where is my car?"})
    [e] = sql.get_events("mary", kind="answer")
    assert e["payload"]["status"] == "answered" and isinstance(e["ts"], datetime)
    assert len(sql.get_events("mary", since=datetime.now() - timedelta(minutes=1))) == 2


def test_reset_empties_everything(sql):
    sql.add_fact(Fact(person_id="mary", event="x", source_quote="x"))
    sql.create_pending_question("mary", "y?")
    sql.reset()
    assert sql.get_facts("mary") == [] and sql.list_questions("mary") == []


def test_chat_works_on_sqlite(sql, fake_model):
    sql.add_med_log(MedLogEntry(person_id="mary", medicine="Metformin", given_at=datetime.now(), logged_by="Anu"))
    r = chat("mary", "Did I take my tablets?", person_name="Mary")
    assert r.route == "medication" and "Metformin" in r.reply
    assert sql.get_events("mary", kind="answer")
