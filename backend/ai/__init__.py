"""Dory's AI layer (Person A, "The Brain").

Person B imports these:
    from backend.ai import chat, extract_facts, briefing, summary
"""
from .client import call_model, set_backend
from .db_interface import get_db, set_db
from .dory import briefing, chat, confirm_statement, extract_facts, summary
from .evening import evening_turn

__all__ = ["chat", "confirm_statement", "extract_facts", "briefing", "summary", "evening_turn", "call_model", "set_backend", "get_db", "set_db"]
