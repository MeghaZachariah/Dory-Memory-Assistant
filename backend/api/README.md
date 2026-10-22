# backend/api — Dory's web server

Puts the AI functions in `backend/ai` on the web, so the Android app, browser screen, Telegram bot and family dashboard can all use them.

```bash
pip install -r backend/ai/requirements.txt -r backend/api/requirements.txt
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive docs, where you can try every endpoint: http://localhost:8000/docs

## Endpoints

| Who uses it | Method and path | What it does |
|---|---|---|
| App | `POST /chat` `{person_id, message}` | Answer a question (grounded, checked, health-safe) |
| App | `POST /evening/turn` `{person_id, turns, conversation_date?}` | Next line of the evening call; on the last turn, saves the facts |
| App | `GET /briefing/{person_id}` | Morning reminder text |
| Bot | `GET /summary/{person_id}` | Daily family update, with alerts and stats |
| Dashboard | `GET /facts/{person_id}` | All facts with their source quotes (the "receipts") |
| Dashboard | `POST /facts/{person_id}` | Memory Book: family adds a fact (can be `tell_gently` or `do_not_share`) |
| Dashboard | `GET /answers/{person_id}` | Dory's answers log with `passed` / `blocked by checker` badges |
| Bot, dashboard | `GET /questions/{person_id}?status=pending` | Questions waiting for the family |
| Bot | `POST /questions/{id}/answer` `{answer, answered_by}` | Save a family reply as a fact Dory can use next time |
| Bot, dashboard | `POST /med-log`, `GET /med-log/{person_id}` | Caregiver-confirmed medicines |
| Anyone | `GET/PUT /people/{person_id}` | Name and family names |
| Demo | `POST /demo/load`, `POST /demo/reset` | Load the sample person (no credits used) / wipe everything |
| Anyone | `GET /health` | Is the server up? |

## Settings

- `DORY_APP_TOKEN`: if set, every request except `/health` needs the header `X-Dory-Token`. Set it when the server is on the internet.
- Set the server's time zone to India when hosting (`TZ=Asia/Kolkata`), so "today" and "yesterday" match the person's day.
- Data is kept in memory (`backend/ai/fake_db.py`) and is lost when the server restarts. Plug in Person C's database with `set_db()` at startup.

## Hosting

For a URL anyone can reach, deploy this server, for example on **Nebius Serverless Endpoints** (the Apps and Agents track encourages it). Start command:

```
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

## Tests

```bash
python -m pytest backend -q
```
