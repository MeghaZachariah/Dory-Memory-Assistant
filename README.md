# 🧠 Dory

### A Trustworthy AI Memory Companion for Early Memory Loss

Dory helps people with early memory loss remember important moments, answer questions using verified information, and safely involve family members when the system is uncertain.

Unlike traditional AI assistants, Dory does not guess. Every answer is grounded in stored facts, family-provided memories, or caregiver-confirmed records.

---

# ✨ Features

## 🎤 Voice-First Patient Experience

- Large accessibility-focused interface
- Speech-to-text conversation
- Text-to-speech responses
- Morning briefing
- Evening memory check-in
- Typed fallback for accessibility

## 📚 Verified Memories

Dory stores:

- Daily memories
- Family-provided facts
- Memory Book entries
- Caregiver-approved records

Every answer can be traced to a source.

## 👨‍👩‍👧 Family-in-the-Loop

When Dory cannot answer a question:

1. Dory says it does not know.
2. The question is sent to family members.
3. Family members provide an answer.
4. The answer becomes a verified memory.
5. Dory can answer correctly next time.

## 💊 Medication Safety

Dory never guesses medication information.

Medication questions are routed only through caregiver-confirmed logs.

## 📱 Telegram Family Assistant

Family members receive:

- Memory questions
- Safety notifications
- Daily summaries

Responses flow directly into Dory's memory system.

## 📊 Family Dashboard

Monitor:

- Verified memories
- Family responses
- Medication records
- Pending questions
- Dory answer logs
- Telegram activity

---

# 🏗 Architecture

```text
Patient
   │
   ▼
Voice Interface
   │
   ▼
FastAPI Backend
   │
   ▼
Dory AI Pipeline
   │
 ┌─┴───────────────┐
 │                 │
 ▼                 ▼

Known Fact      Unknown Question
 │                 │
 ▼                 ▼

Answer        Telegram Family Bot
 │                 │
 ▼                 ▼

Patient      Family Response
                   │
                   ▼

            Memory Stored
                   │
                   ▼

           Future Answers

# 🤖 AI Pipeline

## Fact Extraction

- Extracts structured memories from conversations
- Preserves source quotes
- Normalizes dates
- Validates evidence before storage

## Grounded Answering

Dory only answers using:

- Stored facts
- Memory Book entries
- Family-provided memories

If evidence is missing:

> "I'm not sure. Would you like me to ask your family?"

## Verification Layer

All answers are checked before being shown.

Unsupported answers are blocked and replaced with a safe response.

---

# 🖥 Frontend

Built with:

- React
- Vite
- Tailwind CSS

## Includes

- Landing Page
- Login & Signup
- Patient Portal
- Family Dashboard
- Telegram Assistant Center

---

# ⚙ Backend

Built with:

- FastAPI
- Python
- SQLite / PostgreSQL

## Authentication Includes

- Login
- Signup
- Session Management
- Family Account Linking

---

# 📱 Telegram Bot

## Supported Commands

```text
/start
/join
/pending
/summary
/briefing
/gave
```

## Used For

- Family responses
- Medication logging
- Question escalation
- Status notifications

---

# 🧪 Safety Principles

## Dory Will Never

❌ Invent memories

❌ Guess medication instructions

❌ Answer without evidence

❌ Override caregiver-confirmed records

## Dory Will Always

✅ Answer using verified facts

✅ Cite memory sources

✅ Ask family when uncertain

✅ Escalate medication questions safely

---

# 🚀 Running the Project

## Backend

```bash
pip install -r backend/requirements.txt

uvicorn backend.api.main:app --reload --port 8000
```

## Frontend

```bash
cd Frontend

npm install

npm run dev
```

## Telegram Bot

```bash
cd backend/bot

python bot.py
```

---

# 🔒 Important Disclaimer

Dory is a memory aid and family communication tool.

It is **not**:

- A medical device
- A diagnostic tool
- A treatment platform

The project is designed to support people with early memory loss and their families by improving communication, memory recall, and safety.

---

# 👥 Team

Built for the **NVIDIA × Nebius Hackathon**.

## Project Vision

> **"What must an AI never say?"**

Dory is designed around trust, verification, and safe uncertainty.

Instead of guessing, Dory either provides a verified answer or asks the family for help.

Every answer should be:

- Explainable
- Traceable
- Grounded in evidence
- Safe for memory-care scenarios
