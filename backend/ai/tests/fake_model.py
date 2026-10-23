"""A scripted stand-in for Nemotron so tests run offline, fast and repeatably.

It recognises which job a call is for from the system prompt, and returns
whatever the test set up for that job. It also records every call.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Union

Handler = Union[str, dict, list, Callable[[list], Any], Exception]

JOBS = {
    "extract": "pull out FACTS",
    "evening": "evening phone call",
    "answer": "gentle memory assistant",
    "check": "strict fact-checker",
    "verify": "You cross-check something",
    "classify": "Classify a message",
    "briefing": "morning greeting",
    "summary": "daily update for the family",
}


class FakeModel:
    def __init__(self) -> None:
        self.handlers: dict[str, Handler] = {}
        self.calls: list[dict] = []

    def on(self, job: str, handler: Handler) -> "FakeModel":
        self.handlers[job] = handler
        return self

    def job_of(self, messages: list) -> str:
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        for job, marker in JOBS.items():
            if marker in system:
                return job
        return "unknown"

    def calls_for(self, job: str) -> list[dict]:
        return [c for c in self.calls if c["job"] == job]

    def __call__(self, model: str, messages: list, options: dict) -> tuple:
        job = self.job_of(messages)
        self.calls.append({"job": job, "model": model, "messages": messages, "options": options})
        handler = self.handlers.get(job)
        if handler is None:
            raise AssertionError(f"FakeModel got an unexpected '{job}' call")
        if isinstance(handler, Exception):
            raise handler
        out = handler(messages) if callable(handler) else handler
        text = out if isinstance(out, str) else json.dumps(out)
        return text, 100, 20
