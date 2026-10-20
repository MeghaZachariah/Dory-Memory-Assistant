"""Talk to Dory in the terminal with the sample persona loaded.

    python -m backend.ai.scripts.demo_chat

Loads all 10 sample conversations as facts (via the real extraction model),
adds a med-log entry, then lets you type questions. Type 'brief' for the
morning briefing, 'summary' for the family summary, 'quit' to stop.
"""
import json
from datetime import date, datetime
from pathlib import Path

from backend.ai import briefing, chat, extract_facts, summary
from backend.ai.db_interface import set_db
from backend.ai.fake_db import FakeDB
from backend.ai.schemas import MedLogEntry

SAMPLES = json.loads((Path(__file__).parent.parent / "samples" / "conversations.json").read_text())


def main() -> None:
    db = FakeDB()
    set_db(db)
    p = SAMPLES["persona"]
    print("Loading sample conversations (this calls the extraction model)...")
    for conv in SAMPLES["conversations"]:
        r = extract_facts(conv["turns"], date.fromisoformat(conv["conversation_date"]), p["person_id"], p["person_name"])
        print(f"  {conv['id']}: kept {len(r.kept)}, threw away {len(r.rejected)}")
    now = datetime(2026, 10, 22, 10, 0)
    db.add_med(MedLogEntry(person_id=p["person_id"], medicine="morning tablets", given_at=now.replace(hour=9), logged_by="Anu"))
    print(f"\nPretending it is {now:%A %d %B, %I:%M %p}. Ask Mary's questions.\n")
    while True:
        try:
            msg = input("Mary> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg in ("quit", "exit", ""):
            break
        if msg == "brief":
            print("Dory>", briefing(p["person_id"], person_name=p["person_name"], today=now.date()).text)
            continue
        if msg == "summary":
            s = summary(p["person_id"], person_name=p["person_name"])
            print("Family>", s.text, "\nAlerts:", s.alerts)
            continue
        r = chat(p["person_id"], msg, person_name=p["person_name"], family_names=p["family"], now=now)
        print("Dory>", r.reply)
        extra = f"[{r.route}/{r.status}, facts {r.fact_ids_used}, {r.latency_ms} ms, tiers {r.tiers_used}]"
        if r.blocked:
            extra += f"\n      BLOCKED draft: {r.draft_answer!r} because {r.checker.reasons}"
        print("     ", extra)


if __name__ == "__main__":
    main()
