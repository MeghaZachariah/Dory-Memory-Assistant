import json
from datetime import date, datetime

from backend.ai import briefing, chat, config, summary
from backend.ai.client import CALL_LOG, call_model, parse_json
from backend.ai.schemas import Fact

TODAY = date(2026, 10, 19)  # Monday


def _seed(db):
    db.add_fact(Fact(person_id="mary", event="Anu visited and they made payasam", who=["Anu"],
                     event_date=date(2026, 10, 18), source_quote="Today I made payasam with Anu"))
    db.add_fact(Fact(person_id="mary", event="Anu will visit", who=["Anu"], event_date=TODAY,
                     event_time="11", source_quote="Anu says she will visit tomorrow at 11"))


def test_briefing_uses_model_text_when_grounded(fake_model, db):
    _seed(db)
    fake_model.on("briefing", "Good morning, Mary. It's Monday, 19 October. Yesterday you made payasam with Anu. "
                              "Anu is visiting today at 11.")
    r = briefing("mary", person_name="Mary", today=TODAY)
    assert not r.used_fallback, r.problems
    assert "payasam" in r.text and len(r.fact_ids) == 2


def test_briefing_falls_back_when_model_invents(fake_model, db):
    _seed(db)
    fake_model.on("briefing", "Good morning, Mary. Ravi is coming at 3 today.")
    r = briefing("mary", person_name="Mary", today=TODAY)
    assert r.used_fallback and r.problems
    assert r.text.startswith("Good morning, Mary. It's Monday, 19 October.")
    assert "Ravi" not in r.text


def test_briefing_with_no_facts_needs_no_model(fake_model, db):
    r = briefing("mary", person_name="Mary", today=TODAY)
    assert r.text == "Good morning, Mary. It's Monday, 19 October." and fake_model.calls == []


def test_summary_alerts_and_stats(fake_model, db):
    _seed(db)
    now = datetime.combine(date.today(), datetime.min.time()).replace(hour=10)
    for _ in range(3):
        chat("mary", "Did I take my tablets?", person_name="Mary", now=now)
    fake_model.on("answer", {"answer": "", "fact_ids_used": [], "status": "unknown"})
    chat("mary", "When was my wedding?", person_name="Mary", now=now)
    chat("mary", "When was my wedding?", person_name="Mary", now=now)
    fake_model.on("summary", "Mary had a calm day.")
    r = summary("mary", person_name="Mary")
    assert "Asked about medicines 3 times today" in r.alerts
    assert any("wedding" in a for a in r.alerts)
    assert r.stats["questions"] == 5 and r.stats["medication_questions"] == 3
    assert r.text == "Mary had a calm day." and not r.used_fallback
    assert fake_model.calls_for("summary")[0]["model"] == config.MODELS["ultra"]


def test_summary_falls_back_if_ultra_fails(fake_model, db):
    from backend.ai.client import ModelError
    fake_model.on("summary", ModelError("down"))
    r = summary("mary", person_name="Mary")
    assert r.used_fallback and r.text.startswith("Daily update for Mary")


def test_call_model_logs_latency_tokens_and_tier(fake_model, tmp_path, monkeypatch):
    log_file = tmp_path / "calls.jsonl"
    monkeypatch.setattr(config, "LOG_PATH", log_file)
    fake_model.on("unknown", "<think>planning</think>Hello")
    r = call_model("nano", [{"role": "user", "content": "hi"}], purpose="smoke")
    assert r.text == "Hello" and r.tier == "nano" and r.model == config.MODELS["nano"]
    entry = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert entry["tier"] == "nano" and entry["purpose"] == "smoke"
    assert entry["prompt_tokens"] == 100 and entry["completion_tokens"] == 20 and "latency_ms" in entry
    assert CALL_LOG[-1]["purpose"] == "smoke"


def test_call_model_rejects_bad_tier():
    import pytest
    with pytest.raises(ValueError):
        call_model("mega", [])


def test_parse_json_variants():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('Here you go:\n```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json('<think>x</think> {"a": 3} thanks') == {"a": 3}
    assert parse_json('[1, 2]') == [1, 2]
