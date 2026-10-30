# 🧠 Dory

### A trustworthy AI memory companion for people with early memory loss, and their families

Dory phones the person every morning and evening, talks with them like a friend, and helps them remember: who visited, what's planned, where things are kept. It never guesses. Every answer about their life comes from a stored fact. A second model checks the answer before it is spoken. When Dory doesn't know something, it says so and asks the family. Once the family answers, Dory knows it next time.

Built on **NVIDIA Nemotron 3 (Nano, Super and Ultra)**, served by **Nebius Token Factory**.

---

## 🔗 For judges: try it in 2 minutes

| | |
|---|---|
| 🌐 **Live website** | **https://129-225-92-241.sslip.io/** |
| 📱 **Android app (APK)** | **[Download dory.apk](https://github.com/MeghaZachariah/Dory-Memory-Assistant/releases/latest/download/dory.apk)** (from [Releases](https://github.com/MeghaZachariah/Dory-Memory-Assistant/releases)) |
| 🔑 **Demo logins** (website and app) | `demo@dory.app` / `dory-demo-2026` (Mary)<br>`arun@gmail.com` / `12345678` (Kavitha, a second family) |
| 🎬 **Demo video** | _add link_ |
| 📖 **API docs (live)** | https://129-225-92-241.sslip.io/api/docs |

The demo account belongs to **Mary**, an older woman with memory loss. Her family has already added some of her memories. The second account is a different family (Kavitha's): sign in with both to see that each family only ever sees its own person.

### Test the website

1. Open the live website, click **Login**, and sign in with the demo account.
2. Click **Open Patient Portal**. This is what Mary sees.
   - Click **Play Morning Briefing**. Nemotron writes a short greeting from Mary's memories.
   - Ask something her memories cover, by typing or with the microphone: *"Who visited me?"*, *"What's happening today?"*
   - Ask something Dory can't know: *"Where did I keep my red scarf?"* Dory says it doesn't know and asks the family. It doesn't guess.
   - Click **Start Evening Chat** and tell Dory about your day. When you finish, it saves what you said as memories.
3. Click **Family view**. This is the family's care center.
   - **Questions**: answer Mary's question, e.g. *"In the wardrobe"*.
   - **Facts**: the answer is now a verified memory.
   - **Medication**: a caregiver logs a medicine. Dory only ever answers medicine questions from these logs.
   - **Today**: click **Write today's update with Nemotron** for a daily family summary (Nemotron Ultra).
4. Go back to **Patient view** and ask the question again. Dory now gives the family's answer.

### Test the Android app

1. On an Android phone, download **dory.apk** from the link above and open it. If asked, allow installing apps from your browser.
2. Sign in with the demo account. The app is already pointed at the live server.
3. Tap **Talk to Dory** and speak naturally. You can also try **Morning briefing** or **Evening chat**.
4. Dory also rings like a phone call at the morning and evening times set on the Home screen. **Test ring · 10s** shows a call in 10 seconds.

> The app and the website share the same account and the same memories. Anything the family adds on the website is immediately known to the app.

---

## ✨ What Dory does

- **Talks like a person, not a robot.** Small talk, feelings and follow-ups ("what about yesterday?") are answered naturally by Nemotron, using the conversation so far.
- **Never invents facts.** Answers about the person's life must cite stored facts and pass the lie-catcher. If they don't, Dory says it doesn't know.
- **Family in the loop.** Unknown questions go to the family (on the website, or optionally by Telegram). Each answer becomes a verified memory.
- **Checks what the person says.** If they tell Dory something new, or something that contradicts a known fact, it is saved as *pending* and the family is asked "is this true?". Pending facts are never used in answers.
- **Morning and evening calls.** A morning briefing of today's plans and yesterday's highlights. An evening chat about the day, with follow-ups on plans ("I had a note Anu was coming today, how did that go?"). Memories are extracted from the conversation, with exact source quotes.
- **Medicine safety.** Medicine and dose questions are never answered by the model. Dory only reads back caregiver-confirmed logs, and urgent phrases get a fixed safe reply.
- **Daily family summary.** Nemotron Ultra writes a short update for the family: what happened, frequent questions, unanswered questions, blocked answers.
- **Family voice (optional).** A family member records a short paragraph, and Dory can speak in their voice (free and open-source OpenVoice v2, run on Colab).
- **Private per family.** One account per family. The website and the app sign in with it, and every request only sees that family's person.

---

## 🤖 How Nemotron is used

| Job | Model (Nebius Token Factory) | Why |
|---|---|---|
| Live conversation and answers | Nemotron 3 **Nano** (30B-A3B) | Fast replies during a spoken conversation |
| Evening call, one line at a time | Nemotron 3 **Nano** | Feels like a natural phone call |
| Health or medicine triage | Nemotron 3 **Nano** | Quick classification before any reply |
| **Lie-catcher** (answer checker) | Nemotron 3 **Super** (120B-A12B) | A stronger second model judges every answer |
| Memory extraction from the evening chat | Nemotron 3 **Super** | Accurate facts with word-for-word quotes |
| Morning briefing | Nemotron 3 **Super** | |
| Daily family summary | Nemotron 3 **Ultra** (550B-A55B) | Best writing quality, not time-critical |

Thinking mode is off for speed. Every call is logged with its latency and token counts (`backend/ai/logs/model_calls.jsonl`).

### The lie-catcher: "What must an AI never say?"

Before an answer about the person's life is spoken, it must pass **both** of these checks:

1. **Code checks** (`backend/ai/guards.py`): the answer must cite at least one stored fact. Every name, number, date and "yesterday/today/tomorrow" must appear in the cited facts. Medicine content is blocked.
2. **Model check**: Nemotron Super reads the question, the answer and the cited facts, and returns `supported` or `unsupported`.

If either check fails, or the checker is unavailable, the answer is **blocked**. Dory says it doesn't know and asks the family. Every answer is logged with a badge (`passed`, `blocked by checker`, `unknown`, `refused`) that the family sees in the Dory Answers log.

---

## 🏗 Architecture

```text
 Android app (Flutter)          Family website (React)          Telegram bot (optional)
 rings morning and evening;     patient portal and family       questions and answers,
 speech in and out              care center                     daily summary
            \                            |                            /
             \__________ HTTPS, family login (Bearer token) _________/
                                         |
                              FastAPI backend (backend/api)
                                         |
                     Dory AI pipeline (backend/ai)  ──>  Nemotron 3 on Nebius Token Factory
                     converse · answer · lie-catcher ·
                     extract · verify · briefing · summary
                                         |
                              SQLite (db/crud.py via adapter)
```

**Deployment:** one free Oracle Cloud "Always Free" VM running Docker Compose: the API, the website behind Caddy (automatic HTTPS), a nightly database backup, and an optional bot.

---

## 📁 Repository layout

| Folder | What it is |
|---|---|
| `backend/ai/` | Dory's brain: Nemotron client, conversation, grounded answers, lie-catcher, extraction, medicine safety. See [backend/ai/README.md](backend/ai/README.md) |
| `backend/api/` | FastAPI server: auth, chat, briefing, evening check-in, family dashboard, voice. See [backend/api/README.md](backend/api/README.md) |
| `backend/bot/` | Telegram family bot |
| `db/` | SQLite database layer (`crud.py`) |
| `Frontend/` | React + Vite + Tailwind website |
| `mobile/dory_app/` | Flutter Android app. See [mobile/dory_app/README.md](mobile/dory_app/README.md) |
| `voice_server/` | Optional family-voice server (OpenVoice v2 + MeloTTS) with a Colab notebook |
| `deploy/`, `docker-compose.yml` | Production deployment (Docker, Caddy, setup script) |
| `docs/AUTH_API.md` | Login and sign-up API |

---

## 🚀 Run it yourself

You need Python 3.10+, Node 18+, and a [Nebius Token Factory](https://studio.nebius.com/) API key.

```bash
git clone https://github.com/MeghaZachariah/Dory-Memory-Assistant.git
cd Dory-Memory-Assistant
cp env.example .env            # then set NEBIUS_API_KEY=... in .env (never commit it)

# Backend
pip install -r backend/ai/requirements.txt -r backend/api/requirements.txt
uvicorn backend.api.main:app --port 8000          # API docs: http://localhost:8000/docs

# Website (in a second terminal)
cd Frontend
npm ci
npm run dev                                         # http://localhost:5173
```

The demo account (`demo@dory.app` / `dory-demo-2026`) is created automatically when the server starts.

**Android app:** install Flutter, then `cd mobile/dory_app && flutter build apk --release`. Change the server address in the app's Settings if you're not using the live server.

**Telegram bot (optional):** set `TELEGRAM_BOT_TOKEN` in `.env`, then run `python backend/bot/bot.py`.

**Deploy to a free server:** on an Ubuntu VM, clone the repo, create `.env`, then run `bash deploy/setup.sh`. It installs Docker, opens the firewall, and gets an HTTPS address.

---

## 🧪 Tests

```bash
python -m pytest backend -q
```

**172 tests**, offline, using a scripted fake model, so they spend no credits. They cover:

- unknown questions are never answered;
- answers without a cited fact are blocked;
- medicine questions are never answered from memory;
- invented names, dates and times are caught;
- extraction from 10 sample conversations keeps exact quotes;
- evening follow-ups;
- family login and per-family data isolation.

With a real key, `python -m backend.ai.scripts.demo_chat` lets you talk to Dory in the terminal, and `python -m backend.ai.scripts.eval_extraction` runs extraction on the sample conversations.

---

## 🔒 Disclaimer

Dory is a memory aid and family communication tool. It is **not** a medical device, it does not diagnose or treat, and it is not a replacement for professional care.

## 👥 Team

Built for the **NVIDIA × Nebius Hackathon**, Best Apps and Agents track.

- **Megha Zachariah**: website and Telegram bot
- **Joan Elizabeth Bino**: AI layer (Nemotron pipeline and lie-catcher), API, Android app, deployment
- _add name_: database layer

## 📄 License

[MIT](LICENSE)
