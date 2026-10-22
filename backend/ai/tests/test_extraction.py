"""'Done when': given 10 sample conversations, it extracts correct facts with verified quotes.

The fake model returns the correct facts PLUS deliberately bad ones (invented
quotes, health facts, names only Dory said). The pipeline must keep the good
ones with the right dates and throw the bad ones away.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from backend.ai import extract_facts

SAMPLES = json.loads((Path(__file__).parent.parent / "samples" / "conversations.json").read_text())
PERSONA = SAMPLES["persona"]
PHRASES = ["day before yesterday", "yesterday", "tomorrow", "today", "tonight", "on thursday", "on friday", "on the 25th of october"]


def _good_facts(conv):
    out = []
    for exp in conv["expected"]:
        turn = next(t["text"] for t in conv["turns"] if exp["quote_contains"] in t["text"])
        low = turn.lower()
        when = next((p for p in PHRASES if p in low), "today")
        out.append({
            "event": exp["quote_contains"],
            "who": exp.get("who", []),
            "when_text": when,
            "event_time": exp.get("time"),
            "source_quote": exp["quote_contains"],
        })
    return out


BAD_FACTS = [
    {"event": "Ravi phoned Mary", "who": ["Ravi"], "when_text": "today", "source_quote": "Ravi phoned me this evening"},
    {"event": "Mary took her tablets", "who": [], "when_text": "today", "source_quote": "I took my tablets after breakfast"},
    {"event": "Her back hurts", "who": [], "when_text": "today", "source_quote": "My back hurts a little tonight"},
    {"event": "missing quote field"},
    "not even an object",
]


@pytest.mark.parametrize("conv", SAMPLES["conversations"], ids=[c["id"] for c in SAMPLES["conversations"]])
def test_sample_conversation(conv, fake_model, db):
    fake_model.on("extract", {"facts": _good_facts(conv) + BAD_FACTS})
    report = extract_facts(conv["turns"], date.fromisoformat(conv["conversation_date"]),
                           PERSONA["person_id"], PERSONA["person_name"])

    kept_quotes = [f.source_quote for f in report.kept]
    assert len(report.kept) == len(conv["expected"]), (kept_quotes, report.rejected)
    for exp in conv["expected"]:
        fact = next(f for f in report.kept if exp["quote_contains"] in f.source_quote)
        assert str(fact.event_date) == exp["date"], (exp, fact)
        assert sorted(fact.who) == sorted(exp.get("who", []))
        assert fact.fact_id is not None and fact.fact_id in db.facts  # saved
    for banned in conv["must_not_store"] + ["Ravi phoned", "tablets", "back hurts"]:
        assert not any(banned.lower() in f.source_quote.lower() or banned.lower() in f.event.lower() for f in report.kept)
    assert len(report.rejected) >= 3  # the invented / health / malformed facts


def test_invented_name_in_who_is_removed_or_fact_rejected(fake_model, db):
    turns = [{"speaker": "Dory", "text": "Did Ravi visit?"}, {"speaker": "Mary", "text": "Anu came over for lunch today."}]
    fake_model.on("extract", {"facts": [
        {"event": "Anu came for lunch", "who": ["Anu", "Ravi"], "when_text": "today", "source_quote": "Anu came over for lunch today"},
        {"event": "Ravi and Anu came for lunch", "who": ["Anu", "Ravi"], "when_text": "today", "source_quote": "Anu came over for lunch today"},
    ]})
    report = extract_facts(turns, date(2026, 10, 18), "mary", "Mary")
    assert len(report.kept) == 1
    assert report.kept[0].who == ["Anu"]  # Ravi only appeared in Dory's question


def test_quote_from_dory_is_not_evidence(fake_model, db):
    turns = [{"speaker": "Dory", "text": "Did you go to the market with Anu today?"}, {"speaker": "Mary", "text": "Hmm, maybe."}]
    fake_model.on("extract", {"facts": [
        {"event": "Went to the market with Anu", "who": ["Anu"], "when_text": "today",
         "source_quote": "go to the market with Anu today"},
    ]})
    report = extract_facts(turns, date(2026, 10, 18), "mary", "Mary")
    assert report.kept == []


def test_plain_text_transcript_and_json_in_fences(fake_model, db):
    fake_model.on("extract", '<think>hmm</think>```json\n{"facts": [{"event": "Watered the plants", "when_text": "today", '
                             '"source_quote": "I watered the plants"}]}\n```')
    report = extract_facts("Dory: How was today?\nMary: I watered the plants.", date(2026, 10, 18), "mary", "Mary")
    assert [f.event for f in report.kept] == ["Watered the plants"]


def test_model_failure_returns_empty_report(fake_model, db):
    from backend.ai.client import ModelError
    fake_model.on("extract", ModelError("network down"))
    report = extract_facts([{"speaker": "Mary", "text": "I watered the plants."}], date(2026, 10, 18), "mary", "Mary")
    assert report.kept == [] and "extraction failed" in report.rejected[0].reason


def test_fact_already_in_memory_is_not_stored_again(fake_model, db):
    fake_model.on("extract", {"facts": [
        {"event": "Anu visited for lunch", "who": ["Anu"], "when_text": "yesterday",
         "source_quote": "Anu came over for lunch yesterday"},
    ]})
    turns = [{"speaker": "Mary", "text": "Anu came over for lunch yesterday."}]
    first = extract_facts(turns, date(2026, 10, 18), "mary", "Mary")
    again = extract_facts(turns, date(2026, 10, 18), "mary", "Mary")  # Mary repeats it later the same day
    assert len(first.kept) == 1 and again.kept == []
    assert again.rejected[0].reason == f"already stored as fact #{first.kept[0].fact_id}"
    assert len(db.facts) == 1


def test_retelling_the_same_event_on_a_later_day_is_not_stored_again(fake_model, db):
    turns_day1 = [{"speaker": "Mary", "text": "Anu came over for lunch today."}]
    turns_day2 = [{"speaker": "Mary", "text": "Anu came over for lunch yesterday."}]
    fake_model.on("extract", {"facts": [{"event": "Anu visited for lunch", "who": ["Anu"], "when_text": "today",
                                         "source_quote": "Anu came over for lunch today"}]})
    extract_facts(turns_day1, date(2026, 10, 17), "mary", "Mary")
    fake_model.on("extract", {"facts": [{"event": "Anu visited for lunch", "who": ["Anu"], "when_text": "yesterday",
                                         "source_quote": "Anu came over for lunch yesterday"}]})
    report = extract_facts(turns_day2, date(2026, 10, 18), "mary", "Mary")  # same visit, same date (17th)
    assert report.kept == [] and len(db.facts) == 1


def test_same_kind_of_event_on_a_different_date_is_stored(fake_model, db):
    fake_model.on("extract", {"facts": [{"event": "Anu visited for lunch", "who": ["Anu"], "when_text": "today",
                                         "source_quote": "Anu came over for lunch"}]})
    turns = [{"speaker": "Mary", "text": "Anu came over for lunch."}]
    extract_facts(turns, date(2026, 10, 17), "mary", "Mary")
    report = extract_facts(turns, date(2026, 10, 18), "mary", "Mary")  # a second visit, next day
    assert len(report.kept) == 1 and len(db.facts) == 2
