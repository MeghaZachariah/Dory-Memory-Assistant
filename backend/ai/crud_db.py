"""Person C's SQLite database (db/crud.py) behind the functions in db_interface.py.

Her `facts` table, crud.add_fact() and crud.get_connection() are used as they are.
What her table does not hold yet is kept next to it in the same db/dory.db:

- fact_details: the full Fact (dates, names, verification...) keyed by her text id,
  plus the integer fact_id the answer checker cites.
- family_questions, med_given, event_log: questions for the family, the caregiver's
  medicine log and the events log.

Facts she adds with crud.add_fact() directly show up too (as plain confirmed facts).
Turn it on for the server with DORY_DB=sqlite in .env.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator, Optional

from db import crud

from .schemas import Fact, MedLogEntry

_TABLES = """
CREATE TABLE IF NOT EXISTS fact_details (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    crud_id TEXT UNIQUE NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS family_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    question TEXT NOT NULL,
    key TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    times_asked INTEGER NOT NULL DEFAULT 1,
    answer TEXT,
    answered_by TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS med_given (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    medicine TEXT NOT NULL,
    given_at TEXT NOT NULL,
    logged_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""

_SOURCES = {"conversation", "memory_book", "family_answer"}


@contextmanager
def _connect() -> Iterator[Any]:
    """Her connection, committed (or rolled back) and closed afterwards."""
    conn = crud.get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class CrudDB:
    def __init__(self) -> None:
        crud.init_db()
        with _connect() as conn:
            conn.executescript(_TABLES)

    # --- facts -------------------------------------------------------------
    def add_fact(self, fact: Fact) -> int:
        crud_id = crud.add_fact(fact.person_id, fact.event, fact.source, fact.source_quote)
        fact = fact.model_copy(update={"created_at": fact.created_at or datetime.now()})
        with _connect() as conn:
            cur = conn.execute("INSERT INTO fact_details (crud_id, data) VALUES (?, ?)",
                               (crud_id, fact.model_dump_json(exclude={"fact_id"})))
            return cur.lastrowid

    def get_facts(self, person_id: str, since: Optional[date] = None, until: Optional[date] = None) -> list[Fact]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT f.id, f.persona_id, f.fact_text, f.source_type, f.source_quote, d.fact_id, d.data "
                "FROM facts f LEFT JOIN fact_details d ON d.crud_id = f.id WHERE f.persona_id = ?",
                (person_id,),
            ).fetchall()
            out = []
            for r in rows:
                if r["data"] is None:  # added straight through crud.add_fact(): give it details now
                    fact = Fact(person_id=r["persona_id"], event=r["fact_text"],
                                source_quote=r["source_quote"] or r["fact_text"],
                                source=r["source_type"] if r["source_type"] in _SOURCES else "conversation")
                    cur = conn.execute("INSERT INTO fact_details (crud_id, data) VALUES (?, ?)",
                                       (r["id"], fact.model_dump_json(exclude={"fact_id"})))
                    fact.fact_id = cur.lastrowid
                else:  # her columns win for the text, in case she edits them
                    fact = Fact.model_validate_json(r["data"]).model_copy(
                        update={"fact_id": r["fact_id"], "event": r["fact_text"], "source_quote": r["source_quote"]})
                if fact.event_date is not None:
                    if since and fact.event_date < since:
                        continue
                    if until and fact.event_date > until:
                        continue
                out.append(fact)
        return sorted(out, key=lambda f: f.fact_id)

    def update_fact(self, fact_id: int, changes: dict[str, Any]) -> None:
        with _connect() as conn:
            row = conn.execute("SELECT crud_id, data FROM fact_details WHERE fact_id = ?", (fact_id,)).fetchone()
            if row is None:
                raise KeyError(fact_id)
            fact = Fact.model_validate_json(row["data"]).model_copy(update=changes)
            conn.execute("UPDATE fact_details SET data = ? WHERE fact_id = ?",
                         (fact.model_dump_json(exclude={"fact_id"}), fact_id))
            conn.execute("UPDATE facts SET fact_text = ?, source_type = ?, source_quote = ? WHERE id = ?",
                         (fact.event, fact.source, fact.source_quote, row["crud_id"]))

    # --- ask the family ----------------------------------------------------
    def create_pending_question(self, person_id: str, question: str, reason: str = "unknown") -> int:
        key = question.strip().lower().rstrip("?")
        with _connect() as conn:
            row = conn.execute(  # merge duplicates, as Person C's rules say
                "SELECT id FROM family_questions WHERE person_id = ? AND status = 'pending' AND key = ?",
                (person_id, key),
            ).fetchone()
            if row:
                conn.execute("UPDATE family_questions SET times_asked = times_asked + 1 WHERE id = ?", (row["id"],))
                return row["id"]
            cur = conn.execute(
                "INSERT INTO family_questions (person_id, question, key, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (person_id, question, key, reason, datetime.now().isoformat()),
            )
            return cur.lastrowid

    def record_family_answer(self, question_id: int, answer: str, answered_by: str) -> int:
        q = self._question(question_id)
        self.close_question(question_id, answer, answered_by)
        return self.add_fact(
            Fact(
                person_id=q["person_id"],
                event=f"{q['question']} Answer: {answer}",
                source_quote=answer,
                source="family_answer",
                answered_by=answered_by,
            )
        )

    def close_question(self, question_id: int, answer: str, answered_by: str) -> None:
        self._question(question_id)
        with _connect() as conn:
            conn.execute("UPDATE family_questions SET status = 'answered', answer = ?, answered_by = ? WHERE id = ?",
                         (answer, answered_by, question_id))

    def list_questions(self, person_id: str, status: Optional[str] = None) -> list[dict]:
        sql, args = "SELECT * FROM family_questions WHERE person_id = ?", [person_id]
        if status is not None:
            sql, args = sql + " AND status = ?", args + [status]
        with _connect() as conn:
            rows = [self._question_dict(r) for r in conn.execute(sql + " ORDER BY id", args)]
        return sorted(rows, key=lambda q: q["created_at"], reverse=True)

    def _question(self, question_id: int) -> dict:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM family_questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            raise KeyError(question_id)
        return self._question_dict(row)

    @staticmethod
    def _question_dict(row: Any) -> dict:
        q = dict(row)
        q["created_at"] = datetime.fromisoformat(q["created_at"])
        return q

    # --- medication --------------------------------------------------------
    def add_med_log(self, entry: MedLogEntry) -> None:
        with _connect() as conn:
            conn.execute("INSERT INTO med_given (person_id, medicine, given_at, logged_by) VALUES (?, ?, ?, ?)",
                         (entry.person_id, entry.medicine, entry.given_at.isoformat(), entry.logged_by))

    add_med = add_med_log  # older name used in tests

    def get_med_log(self, person_id: str, since: Optional[datetime] = None) -> list[MedLogEntry]:
        with _connect() as conn:
            rows = conn.execute("SELECT * FROM med_given WHERE person_id = ?", (person_id,)).fetchall()
        entries = [MedLogEntry(person_id=r["person_id"], medicine=r["medicine"],
                               given_at=datetime.fromisoformat(r["given_at"]), logged_by=r["logged_by"]) for r in rows]
        entries = [m for m in entries if since is None or m.given_at >= since]
        return sorted(entries, key=lambda m: m.given_at, reverse=True)

    # --- events ------------------------------------------------------------
    def log_event(self, person_id: str, kind: str, payload: dict[str, Any]) -> None:
        with _connect() as conn:
            conn.execute("INSERT INTO event_log (person_id, kind, payload, ts) VALUES (?, ?, ?, ?)",
                         (person_id, kind, json.dumps(payload, default=str), datetime.now().isoformat()))

    def get_events(self, person_id: str, since: Optional[datetime] = None, kind: Optional[str] = None) -> list[dict]:
        sql, args = "SELECT * FROM event_log WHERE person_id = ?", [person_id]
        if kind is not None:
            sql, args = sql + " AND kind = ?", args + [kind]
        with _connect() as conn:
            rows = conn.execute(sql + " ORDER BY id", args).fetchall()
        events = [{"person_id": r["person_id"], "kind": r["kind"], "payload": json.loads(r["payload"]),
                   "ts": datetime.fromisoformat(r["ts"])} for r in rows]
        return [e for e in events if since is None or e["ts"] >= since]

    # --- demo --------------------------------------------------------------
    def reset(self) -> None:
        """Wipe everything, her facts table included (POST /demo/reset)."""
        with _connect() as conn:
            for table in ("facts", "fact_details", "family_questions", "med_given", "event_log"):
                conn.execute(f"DELETE FROM {table}")
