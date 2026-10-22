"""The functions the AI layer needs from Person C's database code.

Until Person C's db/crud.py is ready, an in-memory FakeDB (fake_db.py) is used.
When it is ready, plug it in once at startup:

    from backend.ai.db_interface import set_db
    from db import crud
    set_db(crud)          # any object or module with these functions works

Only these names are used. Agree them with Person C.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Protocol

from .schemas import Fact, MedLogEntry


class DoryDB(Protocol):
    def add_fact(self, fact: Fact) -> int:
        """Save a fact and return its new fact_id."""

    def get_facts(self, person_id: str, since: Optional[date] = None, until: Optional[date] = None) -> list[Fact]:
        """Facts for a person. since/until filter on event_date (facts with no date are always included)."""

    def create_pending_question(self, person_id: str, question: str, reason: str = "unknown") -> int:
        """Queue a question for the family (Person B's bot sends it). Returns the question id.
        Person C merges duplicates, so calling this twice for the same question is fine."""

    def record_family_answer(self, question_id: int, answer: str, answered_by: str) -> int:
        """Called by the bot. Saves the answer as a family_answer fact and returns its fact_id."""

    def update_fact(self, fact_id: int, changes: dict[str, Any]) -> None:
        """Change fields of a stored fact (used to confirm or reject a pending fact)."""

    def close_question(self, question_id: int, answer: str, answered_by: str) -> None:
        """Mark a family question answered WITHOUT saving a new fact (used for "verify_statement" questions)."""

    def get_med_log(self, person_id: str, since: Optional[datetime] = None) -> list[MedLogEntry]:
        """Caregiver-confirmed medication entries, newest first."""

    def log_event(self, person_id: str, kind: str, payload: dict[str, Any]) -> None:
        """Append to the events/audit log (answers, blocks, model calls...)."""

    def get_events(self, person_id: str, since: Optional[datetime] = None, kind: Optional[str] = None) -> list[dict]:
        """Read the events log back (used for the daily summary)."""


_db: Optional[Any] = None


def get_db() -> Any:
    global _db
    if _db is None:
        from .fake_db import FakeDB

        _db = FakeDB()
    return _db


def set_db(db: Any) -> None:
    global _db
    _db = db
