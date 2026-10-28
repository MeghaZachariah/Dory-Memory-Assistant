"""Things the person tells Dory during the day: recorded, cross-checked, stored only once the family confirms."""
from datetime import date, datetime

import pytest

from backend.ai import chat, config, confirm_statement
from backend.ai.client import ModelError
from backend.ai.schemas import Fact
from backend.ai.statements import split_message

NOW = datetime(2026, 10, 18, 10, 30)  # Sunday morning
RAVI_CALLED = {"event": "Ravi phoned", "who": ["Ravi"], "when_text": "today", "source_quote": "Ravi phoned me"}


@pytest.fixture
def mary(db):
    return {"visit": db.add_fact(Fact(person_id="mary", event="Anu visited and they had fish curry", who=["Anu"],
                                      event_date=date(2026, 10, 17), source_quote="Anu came over for lunch."))}


def say(msg):
    return chat("mary", msg, person_name="Mary", family_names=["Anu", "Ravi"], now=NOW)


def answer_prompt(fake_model):
    return fake_model.calls_for("answer")[-1]["messages"][0]["content"]


@pytest.mark.parametrize("msg,questions,statements", [
    ("Ravi phoned me this morning.", [], ["Ravi phoned me this morning."]),
    ("Ravi phoned me. Did Anu visit?", ["Did Anu visit?"], ["Ravi phoned me."]),
    ("did anyone visit me", ["did anyone visit me"], []),            # speech-to-text, no "?"
    ("Dory, tell me about my week", ["Dory, tell me about my week"], []),
    ("Pretend Anu is here", ["Pretend Anu is here"], []),            # a request, not a fact
    ("I wonder if Ravi is coming.", ["I wonder if Ravi is coming."], []),
    ("Okay, thank you. Good morning!", [], []),                     # filler is ignored
])
def test_split_message(msg, questions, statements):
    assert split_message(msg) == (questions, statements)


def test_new_statement_is_pending_until_family_confirms(fake_model, db, mary):
    fake_model.on("extract", {"facts": [RAVI_CALLED]})
    fake_model.on("verify", {"verdict": "new", "fact_ids": [], "reason": "not in facts"})
    r = say("Ravi phoned me this morning.")
    assert r.reply == config.STATEMENT_REPLY and r.route == "statement" and r.notify_family
    [n] = r.noted
    assert n["outcome"] == "pending_family_check"
    fact = db.facts[n["fact_id"]]
    assert fact.verification == "pending" and fact.event_date == date(2026, 10, 18)
    assert db.questions[n["verify_question_id"]]["question"] == 'Mary said: "Ravi phoned me". Is this true?'
    # Dory now replies in its own words; with no model reply here it falls back to the fixed thanks.
    assert len(fake_model.calls_for("answer")) == 1

    # Not used in answers while pending...
    fake_model.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    say("Who phoned me?")
    assert "Ravi phoned" not in answer_prompt(fake_model)

    # ...but used once the family says it is true.
    assert confirm_statement("mary", n["verify_question_id"], True, "Anu") == n["fact_id"]
    assert db.facts[n["fact_id"]].verification == "confirmed"
    assert db.questions[n["verify_question_id"]]["status"] == "answered"
    say("Who phoned me today?")
    assert "Ravi phoned" in answer_prompt(fake_model)


def test_family_says_not_true_fact_is_never_used_or_asked_again(fake_model, db, mary):
    fake_model.on("extract", {"facts": [RAVI_CALLED]})
    fake_model.on("verify", {"verdict": "new", "fact_ids": [], "reason": ""})
    n = say("Ravi phoned me.").noted[0]
    confirm_statement("mary", n["verify_question_id"], False, "Anu")
    assert db.facts[n["fact_id"]].verification == "rejected"
    again = say("Ravi phoned me.")
    assert again.noted[0]["outcome"] == "already_recorded"
    assert len(db.facts) == 2 and len(db.questions) == 1  # not stored or asked twice


def test_statement_matching_a_confirmed_fact_is_not_stored(fake_model, db, mary):
    fake_model.on("extract", {"facts": [{"event": "Anu came over for lunch", "who": ["Anu"], "when_text": "yesterday",
                                         "source_quote": "Anu came over for lunch yesterday"}]})
    fake_model.on("verify", {"verdict": "matches", "fact_ids": [mary["visit"]], "reason": "same visit"})
    r = say("Anu came over for lunch yesterday.")
    assert r.noted[0]["outcome"] == "already_known" and r.noted[0]["fact_id"] == mary["visit"]
    assert len(db.facts) == 1 and db.questions == {} and not r.notify_family


def test_contradiction_goes_to_family_and_is_not_trusted(fake_model, db, mary):
    fake_model.on("extract", {"facts": [{"event": "Ravi visited for lunch", "who": ["Ravi"], "when_text": "yesterday",
                                         "source_quote": "Ravi came for lunch yesterday"}]})
    fake_model.on("verify", {"verdict": "contradicts", "fact_ids": [mary["visit"]], "reason": "Anu, not Ravi"})
    r = say("Ravi came for lunch yesterday.")
    n = r.noted[0]
    assert n["outcome"] == "pending_family_check" and n["contradicts_fact_ids"] == [mary["visit"]]
    assert "Anu visited and they had fish curry" in db.questions[n["verify_question_id"]]["question"]
    assert r.reply == config.STATEMENT_REPLY  # Dory never tells Mary she is wrong


def test_invented_fact_ids_from_checker_are_ignored(fake_model, db, mary):
    fake_model.on("extract", {"facts": [RAVI_CALLED]})
    fake_model.on("verify", {"verdict": "matches", "fact_ids": [999], "reason": ""})
    assert say("Ravi phoned me.").noted[0]["outcome"] == "pending_family_check"


def test_checker_down_means_family_checks_it(fake_model, db, mary):
    fake_model.on("extract", {"facts": [RAVI_CALLED]})
    fake_model.on("verify", ModelError("down"))
    assert say("Ravi phoned me.").noted[0]["outcome"] == "pending_family_check"


def test_statement_and_question_in_one_message(fake_model, db, mary):
    fake_model.on("extract", {"facts": [RAVI_CALLED]})
    fake_model.on("verify", {"verdict": "new", "fact_ids": [], "reason": ""})
    fake_model.on("answer", {"answer": "Anu visited yesterday.", "fact_ids_used": [mary["visit"]], "status": "answered"})
    fake_model.on("check", {"verdict": "supported", "reason": "ok"})
    r = say("Ravi phoned me. Did anyone visit me?")
    assert r.reply == "Anu visited yesterday." and r.route == "memory"
    assert r.noted[0]["outcome"] == "pending_family_check" and r.notify_family
    assert "Question: Did anyone visit me?" in fake_model.calls_for("check")[0]["messages"][1]["content"]


def test_health_statements_are_never_recorded(fake_model, db, mary):
    r = say("I took my tablets after breakfast.")
    assert r.route == "medication" and r.noted == []
    assert fake_model.calls_for("extract") == [] and len(db.facts) == 1


def test_recording_crash_never_breaks_the_reply(fake_model, db, mary, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("database down")
    monkeypatch.setattr("backend.ai.dory.record_statements", boom)
    r = say("Ravi phoned me.")
    assert r.reply == config.STATEMENT_REPLY and r.noted == []
    assert any(e["kind"] == "statement_error" for e in db.events)
