"""The evening call: fixed-script mode, model-led mode, and follow-ups on today's plans."""
from datetime import date

import pytest

from backend.ai import config
from backend.ai.client import ModelError
from backend.ai.evening import CLOSING, FOLLOW_UP, QUESTIONS, evening_turn
from backend.ai.schemas import Fact

TODAY = date(2026, 10, 25)
YESTERDAY = date(2026, 10, 24)


@pytest.fixture(autouse=True)
def script_mode(monkeypatch):
    """Most tests here are about the fixed script; the model-led ones switch it back on."""
    monkeypatch.setattr(config, "EVENING_LLM", False)


@pytest.fixture
def llm_mode(monkeypatch):
    monkeypatch.setattr(config, "EVENING_LLM", True)


def _plan(db, event="Anu is visiting", who=("Anu",), **kw):
    fields = dict(person_id="mary", event=event, who=list(who), event_date=TODAY, source_quote=event,
                  conversation_date=YESTERDAY)
    return db.add_fact(Fact(**{**fields, **kw}))


def _run(replies):
    """Play the call through, answering each Dory line with the next reply."""
    turns, said = [], []
    for reply in replies + [None]:
        out = evening_turn("mary", turns, TODAY, "Mary")
        said.append(out.say)
        turns.append({"speaker": "Dory", "text": out.say})
        if out.done:
            return out, said
        turns.append({"speaker": "Mary", "text": reply})
    raise AssertionError("call did not finish")


def test_follow_up_asked_after_first_question(db, fake_model):
    _plan(db)
    fake_model.on("extract", {"facts": []})
    out, said = _run(["Fine.", "Not sure.", "Nobody.", "Rice.", "Nothing."])
    assert said[1].endswith(FOLLOW_UP.format(event="Anu is visiting"))
    assert said[2].endswith(QUESTIONS[1])
    assert out.done and said[-1] == CLOSING.format(name=", Mary")


def test_confirmed_follow_up_is_saved_and_family_not_asked(db, fake_model):
    pid = _plan(db)
    fake_model.on("extract", {"facts": [{"event": "Anu visited and brought cake", "who": ["Anu"], "when_text": "today",
                                         "source_quote": "Anu came and brought cake"}]})
    out, _ = _run(["Fine.", "Lovely, Anu came and brought cake.", "Nobody else.", "Rice.", "Nothing."])
    assert out.followed_up == [pid] and out.facts_saved == 1
    assert out.family_question_ids == [] and db.list_questions("mary") == []


def test_unsure_follow_up_goes_to_family(db, fake_model):
    pid = _plan(db)
    fake_model.on("extract", {"facts": []})
    out, _ = _run(["Fine.", "I don't remember.", "Nobody.", "Rice.", "Nothing."])
    assert out.followed_up == [pid]
    [q] = db.list_questions("mary", status="pending")
    assert out.family_question_ids == [q["id"]]
    assert q["reason"] == "plan_follow_up" and "Anu is visiting" in q["question"]


def test_goodbye_before_follow_up_skips_it(db, fake_model):
    _plan(db)
    fake_model.on("extract", {"facts": []})
    out, _ = _run(["I'm tired, good night."])
    assert out.followed_up == [] and db.list_questions("mary") == []


def test_only_suitable_plans_are_followed_up(db, fake_model):
    _plan(db, "Anu is visiting")
    _plan(db, "Ravi said he might come", who=["Ravi"], verification="pending")
    _plan(db, "Surprise party", who=[], sensitivity="do_not_share")
    _plan(db, "Doctor checks blood pressure", who=[])
    _plan(db, "Walk in the park", who=[], conversation_date=TODAY)  # mentioned today: not a plan
    _plan(db, "Old plan", who=[], event_date=YESTERDAY)
    fake_model.on("extract", {"facts": []})
    out, said = _run(["Fine.", "Yes.", "Nobody.", "Rice.", "Nothing."])
    assert len(out.followed_up) == 1 and "Anu is visiting" in said[1]


def test_no_plans_keeps_the_usual_script(db, fake_model):
    fake_model.on("extract", {"facts": []})
    out, said = _run(["Fine.", "Nobody.", "Rice.", "Nothing."])
    assert len(said) == len(QUESTIONS) + 1 and out.followed_up == []


# --- model-led conversation ---------------------------------------------------
def _scripted(*lines):
    """Fake evening model: returns these lines in order, then ends the call."""
    queue = list(lines)
    return lambda messages: {"say": queue.pop(0), "done": False} if queue else {"say": "", "done": True}


def test_model_holds_the_conversation(db, fake_model, llm_mode):
    fake_model.on("evening", _scripted("Oh lovely, a walk! Where did you go?", "That sounds nice. Who did you see?"))
    fake_model.on("extract", {"facts": []})
    out, said = _run(["I went for a walk.", "To the temple.", "Nobody.", "bye"])
    assert said[0] == QUESTIONS[0].format(name=", Mary")  # greeting is always fixed and instant
    assert said[1:3] == ["Oh lovely, a walk! Where did you go?", "That sounds nice. Who did you see?"]
    assert out.done and said[-1] == CLOSING.format(name=", Mary")
    # the model sees the whole call so far
    last_prompt = fake_model.calls_for("evening")[-1]["messages"][1]["content"]
    assert "Mary: To the temple." in last_prompt


def test_model_is_told_about_todays_plans(db, fake_model, llm_mode):
    pid = _plan(db)
    fake_model.on("evening", _scripted("I had a note that Anu was coming today. How did that go?"))
    fake_model.on("extract", {"facts": []})
    out, _ = _run(["Fine.", "I'm not sure."])
    assert '"Anu is visiting"' in fake_model.calls_for("evening")[0]["messages"][0]["content"]
    assert out.followed_up == [pid] and len(out.family_question_ids) == 1


def test_model_asks_again_when_speech_was_garbled(db, fake_model, llm_mode):
    fake_model.on("evening", _scripted("Sorry, I didn't quite catch who came. Who was it?"))
    fake_model.on("extract", {"facts": [{"event": "Anu visited", "who": ["Anu"], "when_text": "today",
                                         "source_quote": "It was Anu"}]})
    out, said = _run(["and who came over", "It was Anu."])
    assert "didn't quite catch" in said[1] and out.facts_saved == 1


def test_model_lines_that_fail_checks_fall_back_to_script(db, fake_model, llm_mode):
    bad = ["Did you remember your blood pressure tablets?", "x" * 400, ""]
    fake_model.on("evening", lambda m: {"say": bad.pop(0), "done": False} if bad else {"say": "", "done": True})
    fake_model.on("extract", {"facts": []})
    out, said = _run(["Fine.", "Nobody.", "Rice.", "Nothing."])
    assert said[1].endswith(QUESTIONS[1]) and said[2].endswith(QUESTIONS[2]) and said[3].endswith(QUESTIONS[3])
    assert not out.model_written


def test_model_error_falls_back_to_script(db, fake_model, llm_mode):
    fake_model.on("evening", ModelError("down"))
    fake_model.on("extract", {"facts": []})
    out, said = _run(["Fine.", "Nobody.", "Rice.", "Nothing."])
    assert len(said) == len(QUESTIONS) + 1 and out.done


def test_question_cap_ends_a_chatty_model(db, fake_model, llm_mode, monkeypatch):
    monkeypatch.setattr(config, "EVENING_MAX_QUESTIONS", 3)
    fake_model.on("evening", lambda m: {"say": "Tell me more?", "done": False})
    fake_model.on("extract", {"facts": []})
    out, said = _run(["a", "b", "c", "d", "e"])
    assert len(said) == 4 and out.done


def test_goodbye_ends_even_if_model_wants_more(db, fake_model, llm_mode):
    fake_model.on("evening", lambda m: {"say": "And then?", "done": False})
    fake_model.on("extract", {"facts": []})
    out, _ = _run(["Fine.", "I'm tired, good night."])
    assert out.done and out.step == 2
