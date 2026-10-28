"""Talking naturally (conversation.py) without ever inventing facts about the person's life."""
from datetime import date, datetime

import pytest

from backend.ai import chat, config
from backend.ai.client import ModelError
from backend.ai.schemas import Fact

NOW = datetime(2026, 10, 18, 19, 30)  # Sunday evening


@pytest.fixture
def mary(db):
    return db.add_fact(Fact(person_id="mary", event="Anu visited and they had fish curry", who=["Anu"],
                            event_date=date(2026, 10, 17), source_quote="Anu came over. We had fish curry."))


def say(msg, history=None):
    return chat("mary", msg, person_name="Mary", family_names=["Anu", "Ravi"], now=NOW, history=history)


def test_small_talk_gets_a_natural_reply_and_bothers_nobody(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "I'm doing well, thank you for asking! How has your evening been?"})
    r = say("hi how are you doing")
    assert r.reply.startswith("I'm doing well") and r.route == "conversation" and r.status == "answered"
    assert db.questions == {}  # nothing sent to the family
    assert fake_model.calls_for("check") == []  # no facts claimed, nothing to check


def test_questions_about_dory_are_answered(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "I'm Dory, and yes, I can hear you clearly."})
    assert say("what is your name").reply == "I'm Dory, and yes, I can hear you clearly."
    assert db.questions == {}


def test_history_is_sent_so_short_replies_make_sense(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "That's all right. We can talk about something else."})
    history = [{"speaker": "Dory", "text": "Would you like to hear about yesterday?"}]
    r = say("no", history=history)
    prompt = fake_model.calls_for("answer")[0]["messages"][1]["content"]
    assert "Dory: Would you like to hear about yesterday?" in prompt and "Mary now says: no" in prompt
    assert r.route == "conversation" and db.questions == {}


def test_chat_reply_may_repeat_her_own_words(fake_model, db, mary):
    fake_model.on("extract", {"facts": [{"event": "Mohini came by", "who": ["Mohini"], "when_text": "this morning",
                                         "source_quote": "Mohini came by this morning"}]})
    fake_model.on("verify", {"verdict": "new", "fact_ids": [], "reason": ""})
    fake_model.on("answer", {"kind": "chat", "reply": "How lovely that Mohini came by! I'll remember that."})
    r = say("Mohini came by this morning")
    assert r.reply.startswith("How lovely that Mohini") and r.route == "statement"
    assert r.noted and r.noted[0]["outcome"] == "pending_family_check"  # still checked with the family


def test_chat_reply_inventing_a_name_is_not_spoken(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "Ravi said he would call you later."})
    r = say("hello")
    assert r.reply == config.CHAT_FALLBACK_REPLY


def test_chat_reply_about_health_is_not_spoken(fake_model, db, mary):
    fake_model.on("classify", {"kind": "none"})
    fake_model.on("answer", {"kind": "chat", "reply": "Maybe take a tablet and rest."})
    assert say("I feel a bit off").reply in (config.CHAT_FALLBACK_REPLY, config.STATEMENT_REPLY)


def test_unknown_is_said_in_dorys_own_words_and_family_is_asked(fake_model, db, mary):
    fake_model.on("answer", {"kind": "unknown", "reply": "I don't know where your glasses are yet, but I'll ask your family.",
                             "family_question": "Where are Mary's glasses?"})
    r = say("Where are my glasses?")
    assert r.reply.startswith("I don't know where your glasses") and r.status == "unknown"
    [q] = db.questions.values()
    assert q["question"] == "Where are Mary's glasses?"


def test_unknown_reply_that_guesses_a_name_falls_back(fake_model, db, mary):
    fake_model.on("answer", {"kind": "unknown", "reply": "I'm not sure, but maybe Ravi has them."})
    r = say("Where are my glasses?")
    assert r.reply == config.SAFE_UNKNOWN_ASKED_REPLY and r.pending_question_id


def test_answers_still_go_through_the_lie_catcher(fake_model, db, mary):
    fake_model.on("answer", {"kind": "answer", "reply": "Anu came yesterday and you had fish curry together.",
                             "fact_ids_used": [mary]})
    fake_model.on("check", {"verdict": "supported"})
    r = say("Who came yesterday?")
    assert r.status == "answered" and r.fact_ids_used == [mary] and len(fake_model.calls_for("check")) == 1
    fake_model.on("check", {"verdict": "unsupported", "reason": "adds details"})
    assert say("Who came yesterday?").blocked


def test_medicine_is_never_model_written(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "Yes, take two."})
    r = say("Can I take my tablets twice?")
    assert r.route in ("medication", "override") and fake_model.calls_for("answer") == []


def test_model_down_means_the_old_fixed_replies(fake_model, db, mary):
    fake_model.on("answer", ModelError("down"))
    r = say("Mohini came by this morning")
    assert r.reply == config.STATEMENT_REPLY


def test_ordinary_word_starting_a_sentence_is_not_a_name(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "That sounds lovely! Mangoes are such a treat."})
    assert say("my neighbour brought me some mangoes").reply.startswith("That sounds lovely")


def test_known_person_starting_a_sentence_is_still_checked(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "Ravi will call you tonight."})
    assert say("hello").reply == config.CHAT_FALLBACK_REPLY  # Ravi is family: an invented plan


def test_kindness_about_feelings_is_allowed(fake_model, db, mary):
    fake_model.on("answer", {"kind": "chat", "reply": "I'm sorry you're not feeling great. I'm here with you."})
    assert say("not really").reply.startswith("I'm sorry you're not feeling great")
