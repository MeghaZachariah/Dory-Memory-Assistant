"""Daily copy of the Dory database, kept for 7 days (runs in the `backup` container).

Uses SQLite's own backup, which is safe while the server is writing. Copies land in
server-data/backups/ on the server; download one with scp if you ever need it.
"""
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DB = Path(os.getenv("DORY_DB_PATH", "/data/dory.db"))
OUT = DB.parent / "backups"
KEEP = 7

while True:
    if DB.exists():
        OUT.mkdir(exist_ok=True)
        target = OUT / f"dory-{datetime.now():%Y-%m-%d}.db"
        src, dst = sqlite3.connect(DB), sqlite3.connect(target)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        for old in sorted(OUT.glob("dory-*.db"))[:-KEEP]:
            old.unlink()
        print(f"backed up to {target}", flush=True)
    time.sleep(24 * 60 * 60)
