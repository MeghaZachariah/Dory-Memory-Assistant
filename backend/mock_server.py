# backend/mock_server.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="DORY Mock API Contract")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_input: str
    mode: Optional[str] = "chat"

class ChatResponse(BaseModel):
    answer: str
    status: str
    fact_ids_used: List[int]
    passed_checker: bool
    source_quotes: List[str]

MOCK_FACTS = [
    {"id": 1, "text": "Anu visited on Tuesday and ate fish curry.", "source_quote": "Anu visited, we had fish curry", "created_at": "2026-10-19 19:30"},
    {"id": 2, "text": "Doctor appointment scheduled for 4 PM on Tuesday.", "source_quote": "The doctor comes at 4", "created_at": "2026-10-19 19:32"}
]

MOCK_LOGS = [
    {"id": 101, "question": "Who visited yesterday?", "answer": "Anu visited yesterday, and you had fish curry together.", "passed": True, "timestamp": "10:15 AM"},
    {"id": 102, "question": "When is my doctor coming?", "answer": "Your doctor is arriving today at 4:00 PM.", "passed": True, "timestamp": "11:00 AM"}
]

MOCK_QUESTIONS = [
    {"id": 1, "question": "When was my wedding?", "status": "pending", "asked_by": "User", "answer": None, "answered_by": None}
]

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    text = req.user_input.lower()
    
    if "tablet" in text or "med" in text or "pill" in text:
        return ChatResponse(
            answer="I can't check that directly. Your caregiver logged your morning tablets at 9:00 AM.",
            status="refused",
            fact_ids_used=[],
            passed_checker=True,
            source_quotes=["Caregiver Med Log Entry"]
        )
    
    if "wedding" in text or "key" in text:
        return ChatResponse(
            answer="I'm not completely sure about that. I have messaged your family to double check!",
            status="unknown",
            fact_ids_used=[],
            passed_checker=True,
            source_quotes=[]
        )
        
    return ChatResponse(
        answer="Anu visited yesterday evening, and you enjoyed fish curry together.",
        status="answered",
        fact_ids_used=[1],
        passed_checker=True,
        source_quotes=["Anu visited, we had fish curry"]
    )

@app.get("/api/dashboard/summary")
def get_dashboard_summary():
    return {
        "today_summary": "Anu visited yesterday. Doctor appointment scheduled at 4 PM.",
        "alerts": ["Asked about tablets 2 times today"],
        "facts_count": len(MOCK_FACTS),
        "pending_questions": len([q for q in MOCK_QUESTIONS if q["status"] == "pending"])
    }

@app.get("/api/dashboard/facts")
def get_facts():
    return MOCK_FACTS

@app.get("/api/dashboard/logs")
def get_logs():
    return MOCK_LOGS

@app.get("/api/dashboard/questions")
def get_questions():
    return MOCK_QUESTIONS