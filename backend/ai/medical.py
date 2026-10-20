"""Medication and health safety. Dory never answers these from memory.

- Detection: keyword rules first (fast, no model). Borderline messages get a
  quick Nemotron Nano classification.
- Replies: fixed templates only, filled from the caregiver-confirmed med log.
  The model never writes the words of a health reply.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal, Optional

from . import config, prompts
from .client import ModelError, call_json
from .schemas import MedLogEntry

HealthKind = Literal["medication", "urgent", "symptom", "override", "none"]

_MED = re.compile(
    r"\b(tablets?|pills?|medicines?|medication|meds|dose|doses|dosage|insulin|injections?|inhaler|"
    r"prescriptions?|capsules?|drops|syrup|paracetamol|metformin|aspirin|painkillers?|vitamins?|"
    r"blood pressure|bp|sugar levels?|blood sugar)\b",
    re.IGNORECASE,
)
_URGENT = re.compile(
    r"\b(chest pain|can'?t breathe|cannot breathe|short of breath|i fell|i have fallen|fallen down|"
    r"bleeding|fainted|stroke|heart attack|can'?t move|cannot move)\b",
    re.IGNORECASE,
)
_SYMPTOM = re.compile(
    r"\b(pain|hurts?|hurting|ache|aching|headache|dizzy|dizziness|fever|unwell|sick|nausea|vomit|"
    r"cough|swollen|rash|can'?t sleep|feel(?:ing)? (?:bad|ill|weak|funny|strange))\b",
    re.IGNORECASE,
)
_OVERRIDE = re.compile(
    r"\b(double|extra|another|more|skip|stop taking|two of|twice)\b.*\b(tablets?|pills?|medicines?|dose|meds)\b|"
    r"\b(ignore|forget|break) (your|the|all) (rules|instructions)\b|\bpretend (to be|you are)\b|"
    r"\byou are now\b|\bsaid i can take\b",
    re.IGNORECASE,
)
# Words that might be health-related, so Nano decides.
_BORDERLINE = re.compile(r"\b(doctor|hospital|nurse|clinic|feel|feeling|health|appointment|took|take)\b", re.IGNORECASE)


def is_health_text(text: str) -> bool:
    """True if a sentence is about medicines or symptoms (used to keep them out of stored facts)."""
    return bool(_MED.search(text or "") or _URGENT.search(text or "") or _SYMPTOM.search(text or ""))


def is_override_attempt(text: str) -> bool:
    return bool(_OVERRIDE.search(text or ""))


def classify(question: str, *, use_model: bool = True) -> tuple[HealthKind, list[str]]:
    """Return (kind, tiers_used). kind is "none" for ordinary memory questions."""
    q = question or ""
    if _URGENT.search(q):
        return "urgent", []
    if _OVERRIDE.search(q) and (_MED.search(q) or "rule" in q.lower() or "pretend" in q.lower() or "you are now" in q.lower()):
        return "override", []
    if _MED.search(q):
        return "medication", []
    if _SYMPTOM.search(q):
        return "symptom", []
    if use_model and _BORDERLINE.search(q):
        try:
            data, result = call_json(
                config.TIER_FOR["classify"],
                [{"role": "system", "content": prompts.MED_CLASSIFY_SYSTEM}, {"role": "user", "content": q}],
                purpose="classify",
                max_tokens=30,
            )
            label = str(data.get("label", "")).lower() if isinstance(data, dict) else ""
            if label == "health":
                return "symptom", [result.tier]
            return "none", [result.tier]
        except (ModelError, ValueError):
            # If the classifier fails, err on the safe side for borderline messages.
            return "symptom", [config.TIER_FOR["classify"]]
    return "none", []


def _fmt_time(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    suffix = "am" if dt.hour < 12 else "pm"
    return f"{h}:{dt.minute:02d} {suffix}" if dt.minute else f"{h} {suffix}"


def medication_reply(kind: HealthKind, med_log: list[MedLogEntry], now: Optional[datetime] = None) -> str:
    """The fixed reply for a health message. Only facts from the caregiver's med log are used."""
    now = now or datetime.now()
    if kind == "urgent":
        return (
            "That sounds important. Please call for help now, or press your emergency button. "
            "I'm messaging your family straight away."
        )
    if kind == "override":
        return "I can't change anything about your medicines. Only your caregiver can do that. I'm messaging them now."
    if kind == "symptom":
        return (
            "I can't help with health questions myself. I'm letting your caregiver know now. "
            "If you feel very unwell, please call for help."
        )
    # kind == "medication"
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = [m for m in med_log if start_of_day <= m.given_at <= now + timedelta(minutes=1)]
    if today:
        latest = max(today, key=lambda m: m.given_at)
        return (
            f"I can't check that myself. Your caregiver logged your {latest.medicine} at {_fmt_time(latest.given_at)}. "
            "If you're unsure, don't take more, and I'm messaging them now."
        )
    return (
        "I can't check that myself, and there's no note from your caregiver about it today. "
        "I'm messaging them now so they can tell you."
    )
