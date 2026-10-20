"""Run the real model on the 10 sample conversations and score extraction.

    python -m backend.ai.scripts.eval_extraction

For each conversation it reports: expected facts found (with the right date),
facts the model invented that the checks threw away, and anything stored that
must not be (health, names only Dory said).
"""
import json
from datetime import date
from pathlib import Path

from backend.ai import extract_facts
from backend.ai.db_interface import set_db
from backend.ai.fake_db import FakeDB

SAMPLES = json.loads((Path(__file__).parent.parent / "samples" / "conversations.json").read_text())


def main() -> None:
    set_db(FakeDB())
    persona = SAMPLES["persona"]
    found = expected = wrong_date = forbidden = extra = 0
    for conv in SAMPLES["conversations"]:
        report = extract_facts(conv["turns"], date.fromisoformat(conv["conversation_date"]),
                               persona["person_id"], persona["person_name"])
        print(f"\n== {conv['id']} ({conv['conversation_date']})  {report.model_latency_ms} ms")
        matched = set()
        for exp in conv["expected"]:
            expected += 1
            hit = next((f for f in report.kept if exp["quote_contains"].lower() in f.source_quote.lower()
                        or f.source_quote.lower() in exp["quote_contains"].lower()), None)
            if hit is None:
                print(f"   MISSED  {exp['quote_contains']!r}")
                continue
            matched.add(id(hit))
            found += 1
            if str(hit.event_date) != exp["date"]:
                wrong_date += 1
                print(f"   DATE?   {hit.event!r}: got {hit.event_date}, expected {exp['date']}")
            else:
                print(f"   ok      {hit.event!r} [{hit.event_date}]")
        for f in report.kept:
            if id(f) not in matched:
                extra += 1
                print(f"   extra   {f.event!r} (quote: {f.source_quote!r})")
            for banned in conv["must_not_store"]:
                if banned.lower() in (f.event + " " + f.source_quote).lower():
                    forbidden += 1
                    print(f"   FORBIDDEN stored: {banned!r}")
        for r in report.rejected:
            print(f"   thrown away: {r.reason} {r.fact.get('event', '')!r}")
    print(f"\nFound {found}/{expected} expected facts, {wrong_date} with wrong dates, "
          f"{extra} extra facts kept, {forbidden} forbidden facts stored.")


if __name__ == "__main__":
    main()
