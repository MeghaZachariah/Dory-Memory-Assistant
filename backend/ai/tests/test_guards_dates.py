from datetime import date

import pytest

from backend.ai.dates import resolve_when
from backend.ai.guards import code_check_answer, find_unsupported, verify_quote
from backend.ai.schemas import AnswerDraft, Fact

SUN = date(2026, 10, 18)  # a Sunday


@pytest.mark.parametrize(
    "phrase,quote,expected",
    [
        ("yesterday", "", date(2026, 10, 17)),
        ("last night", "", date(2026, 10, 17)),
        ("day before yesterday", "", date(2026, 10, 16)),
        ("today", "", SUN),
        ("this morning", "", SUN),
        ("tomorrow", "", date(2026, 10, 19)),
        ("on Thursday", "The doctor is coming on Thursday", date(2026, 10, 22)),
        ("on Thursday", "I saw the doctor on Thursday", date(2026, 10, 15)),
        ("last Friday", "", date(2026, 10, 16)),
        ("next Monday", "", date(2026, 10, 19)),
        ("Sunday", "", SUN),
        ("3 days ago", "", date(2026, 10, 15)),
        ("on the 25th of October", "", date(2026, 10, 25)),
        ("June 12", "", date(2026, 6, 12)),
        ("2026-11-02", "", date(2026, 11, 2)),
        ("at 4 pm on the 3rd of November", "", date(2026, 11, 3)),
        ("last week", "", None),
        ("the other day", "", None),
        (None, "", None),
    ],
)
def test_resolve_when(phrase, quote, expected):
    assert resolve_when(phrase, SUN, quote) == expected


def test_verify_quote_accepts_exact_and_minor_differences():
    said = "Anu came over for lunch. We had fish curry and rice.\nI watered the plants."
    assert verify_quote("Anu came over for lunch", said)[0]
    assert verify_quote("anu came over for LUNCH.", said)[0]
    assert verify_quote("We had fish curry and rice", said)[0]
    assert verify_quote("Anu came over for lunch We had fish curry", said)[0]  # punctuation dropped


def test_verify_quote_rejects_invented_or_tiny_quotes():
    said = "Anu came over for lunch."
    assert not verify_quote("Ravi came over for lunch", said)[0]
    assert not verify_quote("Anu came over for dinner", said)[0]
    assert not verify_quote("Anu", said)[0]  # too short to count as evidence


def _fact(fid, event, quote, d=None, t=None, who=(), sens="normal"):
    return Fact(fact_id=fid, person_id="p", event=event, source_quote=quote, event_date=d,
                event_time=t, who=list(who), sensitivity=sens)


def test_find_unsupported_names_numbers_dates():
    f = _fact(1, "Anu visited and they had fish curry", "Anu came over for lunch", date(2026, 10, 17), who=["Anu"])
    ok = "Yes, Anu came yesterday. You had fish curry."
    assert find_unsupported(ok, [f], SUN) == []
    assert any("Ravi" in p for p in find_unsupported("Ravi came yesterday.", [f], SUN))
    assert any("today" in p for p in find_unsupported("Anu came today.", [f], SUN))
    assert any("5" in p for p in find_unsupported("Anu came at 5.", [f], SUN))
    assert any("Monday" in p for p in find_unsupported("Anu came on Monday.", [f], SUN))
    assert find_unsupported("Yes, Anu's visit was yesterday.", [f], SUN) == []


def test_code_check_rules():
    facts = {1: _fact(1, "The doctor is coming at 4 pm", "The doctor is coming on Thursday at 4 pm", date(2026, 10, 22), "4 pm"),
             2: _fact(2, "Her husband passed away", "family note", sens="do_not_share")}
    good = AnswerDraft(answer="The doctor is coming on Thursday at 4 pm.", fact_ids_used=[1], status="answered")
    assert code_check_answer(good, facts, SUN) == []
    no_cite = AnswerDraft(answer="The doctor is coming.", fact_ids_used=[], status="answered")
    assert code_check_answer(no_cite, facts, SUN)
    bad_id = AnswerDraft(answer="The doctor is coming.", fact_ids_used=[99], status="answered")
    assert any("do not exist" in p for p in code_check_answer(bad_id, facts, SUN))
    secret = AnswerDraft(answer="Your husband passed away.", fact_ids_used=[2], status="answered")
    assert any("do not share" in p for p in code_check_answer(secret, facts, SUN))
    wrong_time = AnswerDraft(answer="The doctor is coming on Thursday at 3 pm.", fact_ids_used=[1], status="answered")
    assert code_check_answer(wrong_time, facts, SUN)
