"""In-memory stand-in for Person C's database, with the same function names.

Use it for development and tests. Swap it out with db_interface.set_db().
"""
from __future__ import annotations

import itertools
from datetime import date, datetime
from typing import Any, Optional

from .schemas import Fact, MedLogEntry


class FakeDB:
    def __init__(self) -> None:
        self.facts: dict[int, Fact] = {}
        self.questions: dict[int, dict] = {}
        self.med_log: list[MedLogEntry] = []
        self.events: list[dict] = []
        self._fact_ids = itertools.count(1)
        self._question_ids = itertools.count(1)

    # --- facts -------------------------------------------------------------
    def add_fact(self, fact: Fact) -> int:
        fid = next(self._fact_ids)
        self.facts[fid] = fact.model_copy(update={"fact_id": fid, "created_at": fact.created_at or datetime.now()})
        return fid

    def get_facts(self, person_id: str, since: Optional[date] = None, until: Optional[date] = None) -> list[Fact]:
        out = []
        for f in self.facts.values():
            if f.person_id != person_id:
                continue
            if f.event_date is not None:
                if since and f.event_date < since:
                    continue
                if until and f.event_date > until:
                    continue
            out.append(f)
        return out

    # --- ask the family ----------------------------------------------------
    def create_pending_question(self, person_id: str, question: str, reason: str = "unknown") -> int:
        key = question.strip().lower().rstrip("?")
        for qid, q in self.questions.items():  # merge duplicates, as Person C's rules say
            if q["person_id"] == person_id and q["status"] == "pending" and q["key"] == key:
                q["times_asked"] += 1
                return qid
        qid = next(self._question_ids)
        self.questions[qid] = {
            "id": qid,
            "person_id": person_id,
            "question": question,
            "key": key,
            "reason": reason,
            "status": "pending",
            "times_asked": 1,
            "created_at": datetime.now(),
        }
        return qid

    def record_family_answer(self, question_id: int, answer: str, answered_by: str) -> int:
        q = self.questions[question_id]
        q["status"] = "answered"
        q["answer"] = answer
        q["answered_by"] = answered_by
        return self.add_fact(
            Fact(
                person_id=q["person_id"],
                event=f"{q['question']} Answer: {answer}",
                source_quote=answer,
                source="family_answer",
                answered_by=answered_by,
            )
        )

    def update_fact(self, fact_id: int, changes: dict[str, Any]) -> None:
        self.facts[fact_id] = self.facts[fact_id].model_copy(update=changes)

    def close_question(self, question_id: int, answer: str, answered_by: str) -> None:
        q = self.questions[question_id]
        q.update(status="answered", answer=answer, answered_by=answered_by)

    # --- medication --------------------------------------------------------
    def add_med(self, entry: MedLogEntry) -> None:
        self.med_log.append(entry)

    def get_med_log(self, person_id: str, since: Optional[datetime] = None) -> list[MedLogEntry]:
        rows = [m for m in self.med_log if m.person_id == person_id and (since is None or m.given_at >= since)]
        return sorted(rows, key=lambda m: m.given_at, reverse=True)

    # --- events ------------------------------------------------------------
    def log_event(self, person_id: str, kind: str, payload: dict[str, Any]) -> None:
        self.events.append({"person_id": person_id, "kind": kind, "payload": payload, "ts": datetime.now()})

    def get_events(self, person_id: str, since: Optional[datetime] = None, kind: Optional[str] = None) -> list[dict]:
        return [
            e
            for e in self.events
            if e["person_id"] == person_id
            and (since is None or e["ts"] >= since)
            and (kind is None or e["kind"] == kind)
        ]
