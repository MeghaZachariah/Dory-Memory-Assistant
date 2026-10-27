# Family accounts: API for the web sign-up and login pages

One account per family, linked to the one person Dory helps. The family signs up on the
website; the **same email and password** sign in on the person's phone (the app has no sign-up)
and on the dashboard. The server code is `backend/api/auth.py`.

All requests are JSON. In development the web app reaches the server through the Vite proxy,
so the paths below start with `/api` there (e.g. `POST /api/auth/signup`).

## Sign up

```
POST /auth/signup
{
  "email": "anu@example.com",
  "password": "at-least-8-characters",
  "person_name": "Mary",              // the person Dory helps
  "family_names": ["Anu", "Ravi"],    // may answer Dory's questions (optional)
  "caregivers": ["Priya"]             // may also log medicine (optional)
}
```

`201` →

```json
{
  "token": "…",
  "account": {
    "email": "anu@example.com",
    "person_id": "mary-3f9a1c",
    "person_name": "Mary",
    "family_names": ["Anu", "Ravi"],
    "caregivers": ["Priya"]
  }
}
```

Errors come back as `{"detail": "message to show the user"}`:
- `400`: bad email, a password under 8 characters, or no person name
- `409`: the email is already registered

## Log in

```
POST /auth/login
{"email": "...", "password": "...", "device": "web dashboard"}
```

`200` → same shape as sign-up. `401` means "Wrong email or password". `429` means too many tries; wait a few minutes.

## After logging in

Keep `token` (e.g. in `localStorage`) and send it on **every** request:

```
Authorization: Bearer <token>
```

Use `account.person_id` wherever the old code used `PERSON_ID` (`Frontend/src/config.js`).
For example, `GET /dashboard/{person_id}` and the `person_id` in `/chat`.

- `GET /auth/me` returns the account, or `401` if the session ended. Then show the login page.
- `PATCH /auth/me` with `{"person_name"?, "family_names"?, "caregivers"?}` edits the family's details.
- `POST /auth/logout` ends this session only. The phone stays signed in.

## What the server enforces

- With a token, a family can only reach **its own** person. Any other `person_id` in the
  path, query or body gets `403`.
- `/family/answer`, `/med/log`, `/memory/fact`, `/checkin/evening/finish` and
  `/briefing/morning` automatically use the signed-in family's person.
- `/demo/*` and `/voice-server` are refused for family accounts (they're shared settings).
- The server currently also accepts requests **without** a token, so the old screens and the
  bot keep working. Once the web app sends tokens everywhere, set `DORY_REQUIRE_LOGIN=1` on
  the server to make login compulsory.

## Demo login

A ready-made account for the sample person Mary (created when the server starts):
**demo@dory.app / dory-demo-2026**. You can change it with `DORY_DEMO_EMAIL` and `DORY_DEMO_PASSWORD`.
