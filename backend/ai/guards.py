"""Deterministic (code-only) safety checks. No model calls in this file.

1. verify_quote(): an extracted fact's source_quote must really appear in what
   the person said. Stops the model inventing evidence.
2. code_check_answer(): an answer may only mention names, numbers and dates
   that appear in the facts it cites.

The team plan has two versions of who owns these (Person A or Person C).
They live here so they work today; if Person C takes them over, keep the same
function names and import them from db/ instead.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Iterable, Optional

from .schemas import AnswerDraft, Fact

_PUNCT_MAP = str.maketrans(
    {
        "‘": "'", "’": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "‟": '"',
        "–": "-", "—": "-", "…": "...",
    }
)

MIN_QUOTE_CHARS = 8


def normalize(text: str) -> str:
    """Lowercase, unify quote marks and dashes, collapse spaces, drop edge punctuation."""
    text = unicodedata.normalize("NFKC", text or "").translate(_PUNCT_MAP).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .,!?;:\"'")


def verify_quote(quote: str, evidence_text: str) -> tuple[bool, str]:
    """True if `quote` appears word-for-word (ignoring case/spacing/quote style) in `evidence_text`."""
    q = normalize(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return False, "quote too short to be real evidence"
    ev = normalize(evidence_text)
    if q in ev:
        return True, "ok"
    # Allow the model to drop inner punctuation ("Anu came, we ate" vs "Anu came we ate").
    strip = lambda s: re.sub(r"[^\w\s]", "", s)  # noqa: E731
    if strip(q) and re.sub(r"\s+", " ", strip(q)) in re.sub(r"\s+", " ", strip(ev)):
        return True, "ok (punctuation differs)"
    return False, "quote not found in what the person said"


# ---------------------------------------------------------------------------
# Answer checks
# ---------------------------------------------------------------------------
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twice": 2, "once": 1,
}
# Capitalised words that are not names. Sentence starters, pronouns, Dory's own words.
NOT_NAMES = {
    "i", "i'm", "i've", "i'll", "i'd", "you", "your", "you're", "yes", "no", "not", "sure", "okay", "ok",
    "he", "she", "they", "it", "it's", "we", "we're", "his", "her", "their", "our", "my", "me",
    "the", "a", "an", "and", "but", "so", "that", "this", "these", "those", "there", "here", "then",
    "today", "yesterday", "tomorrow", "tonight", "morning", "afternoon", "evening", "night",
    "dory", "shall", "let", "let's", "don't", "do", "did", "does", "can", "could", "would", "will",
    "is", "was", "are", "were", "has", "had", "have", "be", "been", "what", "when", "where", "who",
    "why", "how", "good", "hello", "hi", "oh", "well", "great", "lovely", "nice", "after", "before",
    "at", "on", "in", "for", "with", "about", "from", "also", "both", "all", "some", "one",
    "according", "sounds", "that's", "there's", "family", "mum", "mom", "dad", "doctor", "dr",
    "am", "pm", "a.m", "p.m",
}


def _fact_text(f: Fact) -> str:
    parts = [f.event, f.source_quote, " ".join(f.who), f.event_time or "", f.answered_by or ""]
    if f.event_date:
        d = f.event_date
        parts += [d.isoformat(), WEEKDAYS[d.weekday()], MONTHS[d.month - 1], str(d.day), str(d.year)]
    return " ".join(parts).lower()


def _relative_word_date(word: str, today: date) -> Optional[date]:
    from datetime import timedelta

    return {"today": today, "tonight": today, "yesterday": today - timedelta(days=1), "tomorrow": today + timedelta(days=1)}.get(word)


def find_unsupported(answer: str, cited: list[Fact], today: date, allowed_names: Iterable[str] = ()) -> list[str]:
    """List every name, number or date in `answer` that the cited facts do not contain."""
    problems: list[str] = []
    text = " ".join(_fact_text(f) for f in cited)
    allowed = {n.lower() for n in allowed_names}
    tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*|\d+(?::\d+)?", answer)

    for tok in tokens:
        low = re.sub(r"'s$", "", tok.lower().strip(".'"))
        if not low:
            continue
        if low[0].isdigit():
            for part in low.split(":"):
                if part not in ("00",) and not re.search(rf"\b{re.escape(part.lstrip('0') or '0')}\b", text):
                    problems.append(f"number '{tok}' is not in the cited facts")
                    break
        elif low in NUMBER_WORDS:
            n = NUMBER_WORDS[low]
            if low not in ("once", "one") and low not in text and not re.search(rf"\b{n}\b", text):
                problems.append(f"number '{tok}' is not in the cited facts")
        elif low in WEEKDAYS or low in MONTHS:
            if low not in text:
                problems.append(f"date word '{tok}' is not in the cited facts")
        elif low in ("today", "yesterday", "tomorrow", "tonight"):
            target = _relative_word_date(low, today)
            if not any(f.event_date == target for f in cited if f.event_date):
                problems.append(f"'{tok}' does not match the date of any cited fact")
        elif tok[0].isupper() and low not in NOT_NAMES and low not in allowed:
            if not re.search(rf"\b{re.escape(low)}\b", text):
                problems.append(f"name '{tok}' is not in the cited facts")
    return problems


def code_check_answer(
    draft: AnswerDraft,
    facts_by_id: dict[int, Fact],
    today: date,
    allowed_names: Iterable[str] = (),
) -> list[str]:
    """Hard rules every answer must pass. Returns a list of problems (empty = passed)."""
    problems: list[str] = []
    if draft.status != "answered":
        return problems  # "unknown"/"refused" replies are replaced with fixed text anyway
    if not draft.fact_ids_used:
        problems.append("answer cites no facts (no source, no answer)")
        return problems
    missing = [i for i in draft.fact_ids_used if i not in facts_by_id]
    if missing:
        problems.append(f"cited fact ids do not exist: {missing}")
    cited = [facts_by_id[i] for i in draft.fact_ids_used if i in facts_by_id]
    if any(f.sensitivity == "do_not_share" for f in cited):
        problems.append("answer uses a fact the family marked 'do not share'")
    problems += find_unsupported(draft.answer, cited, today, allowed_names)
    return problems


def now_date(now: Optional[datetime]) -> date:
    return (now or datetime.now()).date()
