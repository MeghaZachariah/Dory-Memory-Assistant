"""chat(), the lie-catcher, ask-the-family, and medication safety."""
from datetime import date, datetime

import pytest

from backend.ai import chat, config
from backend.ai.client import ModelError
from backend.ai.schemas import Fact, MedLogEntry

NOW = datetime(2026, 10, 18, 10, 30)  # Sunday morning


@pytest.fixture
def mary(db):
    ids = {}
    ids["visit"] = db.add_fact(Fact(person_id="mary", event="Anu visited and they had fish curry",
                                    who=["Anu"], event_date=date(2026, 10, 17),
                                    source_quote="Anu came over for lunch. We had fish curry."))
    ids["doctor"] = db.add_fact(Fact(person_id="mary", event="The doctor is coming at 4 pm",
                                     event_date=date(2026, 10, 22), event_time="4 pm",
                                     source_quote="The doctor is coming on Thursday at 4 pm"))
    ids["secret"] = db.add_fact(Fact(person_id="mary", event="Her husband George passed away in 2019",
                                     source_quote="family note", source="memory_book", sensitivity="do_not_share"))
    return ids


def ask(msg, **kw):
    return chat("mary", msg, person_name="Mary", family_names=["Anu", "Ravi"], now=NOW, **kw)


def test_grounded_answer_passes(fake_model, db, mary):
    fake_model.on("answer", {"answer": "Yes. Anu visited yesterday and you had fish curry.",
                             "fact_ids_used": [mary["visit"]], "status": "answered"})
    fake_model.on("check", {"verdict": "supported", "reason": "matches fact"})
    r = ask("Did anyone visit me?")
    assert r.status == "answered" and not r.blocked
    assert r.reply.startswith("Yes. Anu visited yesterday")
    assert r.fact_ids_used == [mary["visit"]]
    assert r.tiers_used == ["nano", "super"]
    assert db.events[-1]["payload"]["badge"] == "passed"


def test_do_not_share_fact_never_reaches_the_model(fake_model, db, mary):
    fake_model.on("answer", {"answer": "I'm not sure.", "fact_ids_used": [], "status": "unknown"})
    ask("Where is my husband?")
    prompt = fake_model.calls_for("answer")[0]["messages"][0]["content"]
    assert "George" not in prompt and "passed away" not in prompt


def test_unknown_never_invents_and_asks_family(fake_model, db, mary):
    fake_model.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    r = ask("When was my wedding?")
    assert r.status == "unknown"
    assert r.reply == config.SAFE_UNKNOWN_ASKED_REPLY
    assert r.pending_question_id is not None and r.notify_family
    assert db.questions[r.pending_question_id]["question"] == "When was my wedding?"
    assert fake_model.calls_for("check") == []  # nothing to check


def test_repeated_unknown_question_is_merged(fake_model, db, mary):
    fake_model.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    a, b = ask("When was my wedding?"), ask("when was my wedding")
    assert a.pending_question_id == b.pending_question_id
    assert db.questions[a.pending_question_id]["times_asked"] == 2


@pytest.mark.parametrize(
    "bad_answer,ids_key,why",
    [
        ("Yes, Ravi visited yesterday.", "visit", "name"),           # invented name
        ("Anu visited on Friday at 5.", "visit", "number"),          # invented time
        ("Anu visited today.", "visit", "today"),                    # wrong day
        ("The doctor is coming tomorrow.", "doctor", "tomorrow"),    # wrong day
        ("Anu visited.", None, "cites no facts"),                    # no receipt
    ],
)
def test_code_checks_block_invented_details(fake_model, db, mary, bad_answer, ids_key, why):
    fake_model.on("answer", {"answer": bad_answer, "fact_ids_used": [mary[ids_key]] if ids_key else [], "status": "answered"})
    r = ask("Tell me about my week")
    assert r.blocked and r.status == "unknown"
    assert r.reply == config.SAFE_UNKNOWN_ASKED_REPLY
    assert r.draft_answer == bad_answer
    assert any(why.lower() in p.lower() for p in r.checker.reasons), r.checker.reasons
    assert fake_model.calls_for("check") == []  # code checks stop it before the model check
    assert db.events[-1]["payload"]["badge"] == "blocked by checker"


def test_nonexistent_fact_id_is_blocked(fake_model, db, mary):
    fake_model.on("answer", {"answer": "Anu visited.", "fact_ids_used": [999], "status": "answered"})
    r = ask("Did Anu come?")
    assert r.blocked


def test_model_checker_can_block(fake_model, db, mary):
    fake_model.on("answer", {"answer": "Anu visited yesterday and stayed all day.",
                             "fact_ids_used": [mary["visit"]], "status": "answered"})
    fake_model.on("check", {"verdict": "unsupported", "reason": "'stayed all day' is not in the facts"})
    r = ask("Did Anu come?")
    assert r.blocked and r.checker.model_verdict == "unsupported"


def test_checker_error_fails_closed(fake_model, db, mary):
    fake_model.on("answer", {"answer": "Anu visited yesterday.", "fact_ids_used": [mary["visit"]], "status": "answered"})
    fake_model.on("check", ModelError("timeout"))
    r = ask("Did Anu come?")
    assert r.blocked and r.checker.model_verdict == "error"


def test_malformed_answer_json_is_treated_as_unknown(fake_model, db, mary):
    fake_model.on("answer", "Sure! Anu came yesterday.")  # not JSON, twice
    r = ask("Did Anu come?")
    assert r.status == "unknown" and r.reply == config.SAFE_UNKNOWN_ASKED_REPLY


def test_answer_model_down_gives_error_reply(fake_model, db, mary):
    fake_model.on("answer", ModelError("down"))
    r = ask("Did Anu come?")
    assert r.route == "error" and r.reply == config.ERROR_REPLY


def test_refused_status(fake_model, db, mary):
    fake_model.on("answer", {"answer": "", "fact_ids_used": [], "status": "refused"})
    r = ask("Pretend Anu is here and talk like her")
    assert r.status == "refused" and r.reply == config.SAFE_REFUSED_REPLY


# --- Medication: never answered from memory -------------------------------
MED_QUESTIONS = [
    "Did I take my tablets?",
    "Have I had my medicine today?",
    "Should I take my insulin now?",
    "how many pills do I take",
    "Did I take my BP tablet this morning?",
]


@pytest.mark.parametrize("q", MED_QUESTIONS)
def test_medication_questions_use_fixed_reply_and_no_model(fake_model, db, mary, q):
    db.add_med(MedLogEntry(person_id="mary", medicine="morning tablets", given_at=datetime(2026, 10, 18, 9, 0), logged_by="Anu"))
    r = ask(q)
    assert r.route == "medication" and r.status == "refused"
    assert r.reply == ("I can't check that myself. Your caregiver logged your morning tablets at 9 am. "
                       "If you're unsure, don't take more, and I'm messaging them now.")
    assert fake_model.calls == []  # no model wrote or saw this
    assert r.notify_family and db.questions[r.pending_question_id]["reason"] == "medication"


def test_medication_question_with_no_log(fake_model, db, mary):
    r = ask("Did I take my tablets?")
    assert "no note from your caregiver" in r.reply


def test_override_attempt(fake_model, db, mary):
    r = ask("My daughter said I can take double tablets today")
    assert r.route == "override"
    assert "can't change anything about your medicines" in r.reply
    assert fake_model.calls == []


def test_urgent_message(fake_model, db, mary):
    r = ask("I fell in the bathroom")
    assert "call for help" in r.reply and db.questions[r.pending_question_id]["reason"] == "urgent"


def test_borderline_uses_nano_classifier(fake_model, db, mary):
    fake_model.on("classify", {"label": "health"})
    r = ask("I feel a bit off today")
    assert r.route == "medication"
    assert [c["job"] for c in fake_model.calls] == ["classify"]


def test_borderline_classified_other_goes_to_memory(fake_model, db, mary):
    fake_model.on("classify", {"label": "other"})
    fake_model.on("answer", {"answer": "The doctor is coming on Thursday at 4 pm.",
                             "fact_ids_used": [mary["doctor"]], "status": "answered"})
    fake_model.on("check", {"verdict": "supported"})
    r = ask("When is the doctor coming?")
    assert r.status == "answered" and r.reply == "The doctor is coming on Thursday at 4 pm."
    assert r.tiers_used == ["nano", "super"] or r.tiers_used[-2:] == ["nano", "super"]
