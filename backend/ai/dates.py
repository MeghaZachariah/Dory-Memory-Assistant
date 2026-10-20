"""Turn spoken time phrases ("yesterday", "on Tuesday") into real dates.

This is done in code, not by the model, so dates are always consistent.
If a phrase is vague ("last week", "the other day"), the date is left empty
rather than guessed.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "a": 1, "an": 1}

_FUTURE_HINTS = re.compile(
    r"\b(will|'ll|going to|gonna|is coming|are coming|comes|coming|tomorrow|next|is visiting|"
    r"will visit|plan|planned|appointment|is due|due on|has to|have to)\b",
    re.IGNORECASE,
)


def _weekday_index(text: str) -> Optional[int]:
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", text) or re.search(rf"\b{name[:3]}\b", text):
            return i
    return None


def _num(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def resolve_when(when_text: Optional[str], conversation_date: date, quote: str = "") -> Optional[date]:
    """Return the date a time phrase refers to, or None if it is vague or missing.

    `quote` is the sentence the phrase came from; it decides whether a bare
    weekday ("on Thursday") means the past or the future.
    """
    if not when_text:
        return None
    t = when_text.strip().lower()
    d = conversation_date

    # Absolute ISO date: 2026-10-18
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    if re.search(r"\bday before yesterday\b", t):
        return d - timedelta(days=2)
    if re.search(r"\bday after tomorrow\b", t):
        return d + timedelta(days=2)
    if re.search(r"\byesterday\b|\blast night\b", t):
        return d - timedelta(days=1)
    if re.search(r"\btomorrow\b", t):
        return d + timedelta(days=1)
    if re.search(r"\b(today|tonight|this morning|this afternoon|this evening|earlier|just now)\b", t):
        return d

    # "3 days ago", "two days ago"
    m = re.search(r"\b(\w+) days? ago\b", t)
    if m and _num(m.group(1)):
        return d - timedelta(days=_num(m.group(1)))
    # "in 3 days"
    m = re.search(r"\bin (\w+) days?\b", t)
    if m and _num(m.group(1)):
        return d + timedelta(days=_num(m.group(1)))

    # Absolute day + month: "12 June", "June 12th"
    for pattern in (r"\b(\d{1,2})(?:st|nd|rd|th)? (?:of )?([a-z]+)\b", r"\b([a-z]+) (\d{1,2})(?:st|nd|rd|th)?\b"):
        for m in re.finditer(pattern, t):
            a, b = m.group(1), m.group(2)
            day_s, month_s = (a, b) if a.isdigit() else (b, a)
            if month_s in MONTHS and day_s.isdigit():
                try:
                    return date(d.year, MONTHS[month_s], int(day_s))
                except ValueError:
                    return None

    wd = _weekday_index(t)
    if wd is not None:
        today_wd = d.weekday()
        if re.search(r"\blast\b", t):
            back = (today_wd - wd) % 7 or 7
            return d - timedelta(days=back)
        if re.search(r"\b(next|this coming|coming)\b", t):
            fwd = (wd - today_wd) % 7 or 7
            return d + timedelta(days=fwd)
        if wd == today_wd:
            return d
        if _FUTURE_HINTS.search(quote or "") or _FUTURE_HINTS.search(t):
            return d + timedelta(days=(wd - today_wd) % 7)
        return d - timedelta(days=(today_wd - wd) % 7)

    return None  # vague: "last week", "recently", "the other day"
