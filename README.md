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
