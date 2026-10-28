"""Data shapes shared by the AI layer and the rest of the team.

Agree these field names with Person C (database) and Person B (bot/dashboard).
If the real schema differs, change the field names here only.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

FactSource = Literal["conversation", "memory_book", "family_answer"]
Sensitivity = Literal["normal", "tell_gently", "do_not_share"]
AnswerStatus = Literal["answered", "unknown", "refused"]
Verification = Literal["confirmed", "pending", "rejected"]


class Fact(BaseModel):
    """One stored fact. `fact_id` is set by the database."""

    fact_id: Optional[int] = None
    person_id: str
    event: str  # plain sentence: "Anu visited and they had fish curry"
    who: list[str] = Field(default_factory=list)
    event_date: Optional[date] = None
    event_time: Optional[str] = None  # "4 pm", kept as text
    source_quote: str  # exact words the fact came from
    source: FactSource = "conversation"
    conversation_date: Optional[date] = None
    answered_by: Optional[str] = None  # family member, for family_answer facts
    sensitivity: Sensitivity = "normal"
    created_at: Optional[datetime] = None
    # Facts the person told Dory during the day stay "pending" until the family confirms them.
    # Only "confirmed" facts are used in answers, briefings and summaries.
    verification: Verification = "confirmed"
    verify_question_id: Optional[int] = None  # the family question that confirms a pending fact


class ExtractedFact(BaseModel):
    """What the extraction model must return for each fact (before checks)."""

    event: str
    who: list[str] = Field(default_factory=list)
    when_text: Optional[str] = None  # the time phrase as spoken: "yesterday", "on Tuesday"
    event_date: Optional[str] = None  # model's own ISO guess; code re-resolves when_text
    event_time: Optional[str] = None
    source_quote: str


class ExtractionOutput(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


class RejectedFact(BaseModel):
    fact: dict
    reason: str


class ExtractionReport(BaseModel):
    """Result of extract_facts(): facts that passed every check, and the ones thrown away."""

    kept: list[Fact] = Field(default_factory=list)
    rejected: list[RejectedFact] = Field(default_factory=list)
    model_latency_ms: int = 0


class AnswerDraft(BaseModel):
    """What the answering model must return."""

    answer: str
    fact_ids_used: list[int] = Field(default_factory=list)
    status: AnswerStatus


class CheckResult(BaseModel):
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    code_passed: bool = True
    model_verdict: Optional[Literal["supported", "unsupported", "skipped", "error"]] = None


class MedLogEntry(BaseModel):
    """A caregiver-confirmed medication entry (owned by Person C's med_log table)."""

    person_id: str
    medicine: str
    given_at: datetime
    logged_by: str


class ChatResult(BaseModel):
    """What chat() returns to Person B's screen and bot.

    `reply` is what Dory says aloud. Everything else is for the dashboard.
    """

    reply: str
    status: AnswerStatus
    route: Literal["memory", "medication", "override", "statement", "conversation", "error"]
    fact_ids_used: list[int] = Field(default_factory=list)
    checker: Optional[CheckResult] = None
    blocked: bool = False  # True when the lie-catcher replaced the model's answer
    draft_answer: Optional[str] = None  # the model's answer before blocking, for the "blocked" badge
    pending_question_id: Optional[int] = None
    notify_family: bool = False
    tiers_used: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    # Things the person told Dory in this message (statements.NotedStatement as dicts).
    noted: list[dict] = Field(default_factory=list)
