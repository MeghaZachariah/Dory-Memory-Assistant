"""Family accounts: one login per family, linked to one person (the patient).

The family signs up once on the website (name + email + password + who the person is).
The same login is used on the person's phone (the app has no sign-up) and on the dashboard.
Each login gets its own session token; send it as `Authorization: Bearer <token>`.

A request that carries a token may only touch that account's person: any person_id in the
path, query or JSON body must match, or the server answers 403. DORY_REQUIRE_LOGIN=1 makes
the token compulsory (except /health and /auth/*); leave it off while the bot and the older
screens are moved over.

    POST  /auth/signup   {email, password, person_name, family_names?, caregivers?} -> {token, account}
    POST  /auth/login    {email, password, device?}                               -> {token, account}
    GET   /auth/me                                                                 -> account
    PATCH /auth/me       {person_name?, family_names?, caregivers?}                -> account
    POST  /auth/logout   (ends this session only)                                  -> {ok}

Accounts live in db/dory.db (tables `accounts` and `sessions`). Passwords are stored as
scrypt hashes and tokens as SHA-256 hashes, so neither can be read back from the database.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

AUTH_DB = Path(os.getenv("DORY_AUTH_DB", Path(__file__).resolve().parents[2] / "db" / "dory.db"))
REQUIRE_LOGIN = os.getenv("DORY_REQUIRE_LOGIN", "0") == "1"
SESSION_DAYS = int(os.getenv("DORY_SESSION_DAYS", "180"))  # phones stay signed in for months
MIN_PASSWORD = 8
# A ready-made login for the demo person (Mary), so judges and the team can sign in straight away.
DEMO_EMAIL = os.getenv("DORY_DEMO_EMAIL", "demo@dory.app")
DEMO_PASSWORD = os.getenv("DORY_DEMO_PASSWORD", "dory-demo-2026")
DEMO_PERSON = "mary"
# Shared settings, not one family's: never reachable with a family's token.
ADMIN_PATHS = ("/voice-server",)
DEMO_PATHS = ("/demo/",)

router = APIRouter(prefix="/auth")

_TABLES = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    person_id TEXT NOT NULL UNIQUE,
    person_name TEXT NOT NULL,
    family_names TEXT NOT NULL DEFAULT '[]',
    caregivers TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    device TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            conn.executescript(_TABLES)
            yield conn
    finally:
        conn.close()


# --- passwords and tokens -------------------------------------------------------
def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, bytes.fromhex(salt_hex)), stored)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- accounts -------------------------------------------------------------------
class Account(BaseModel):
    email: str
    person_id: str
    person_name: str
    family_names: list[str] = Field(default_factory=list)
    caregivers: list[str] = Field(default_factory=list)


def _account(row: sqlite3.Row) -> Account:
    return Account(email=row["email"], person_id=row["person_id"], person_name=row["person_name"],
                   family_names=json.loads(row["family_names"]), caregivers=json.loads(row["caregivers"]))


def _new_person_id(conn: sqlite3.Connection, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "person"
    while True:
        candidate = f"{base}-{secrets.token_hex(3)}"
        if not conn.execute("SELECT 1 FROM accounts WHERE person_id = ?", (candidate,)).fetchone():
            return candidate


def _names(names: list[str]) -> list[str]:
    return [n.strip() for n in names if n and n.strip()]


def create_account(email: str, password: str, person_name: str, family_names: list[str] = (),
                   caregivers: list[str] = (), person_id: Optional[str] = None) -> Account:
    email = email.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(status_code=400, detail=f"The password needs at least {MIN_PASSWORD} characters")
    if not person_name.strip():
        raise HTTPException(status_code=400, detail="Please enter the name of the person Dory will help")
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        conn.execute(
            "INSERT INTO accounts (email, password_hash, person_id, person_name, family_names, caregivers, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email, _hash_password(password), person_id or _new_person_id(conn, person_name), person_name.strip(),
             json.dumps(_names(family_names)), json.dumps(_names(caregivers)), datetime.now().isoformat()),
        )
        return _account(conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone())


def _start_session(conn: sqlite3.Connection, account_id: int, device: str = "") -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    conn.execute("INSERT INTO sessions (token_hash, account_id, device, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                 (_token_hash(token), account_id, device[:80], now.isoformat(),
                  (now + timedelta(days=SESSION_DAYS)).isoformat()))
    return token


def account_for_token(token: str) -> Optional[Account]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT a.* FROM sessions s JOIN accounts a ON a.id = s.account_id"
            " WHERE s.token_hash = ? AND s.expires_at > ?",
            (_token_hash(token), datetime.now().isoformat()),
        ).fetchone()
    return _account(row) if row else None


def account_for_person(person_id: str) -> Optional[Account]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE person_id = ?", (person_id,)).fetchone()
    return _account(row) if row else None


def ensure_demo_account() -> None:
    """The demo login for Mary (the sample person). Set DORY_DEMO_EMAIL="" to skip it."""
    if not DEMO_EMAIL:
        return
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM accounts WHERE email = ? OR person_id = ?",
                              (DEMO_EMAIL, DEMO_PERSON)).fetchone()
    if not exists:
        create_account(DEMO_EMAIL, DEMO_PASSWORD, "Mary", ["Anu", "Ravi"], ["Priya"], person_id=DEMO_PERSON)


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


# Failed logins per email: at most 5 tries in 10 minutes.
_failures: dict[str, list[float]] = {}


def _too_many_failures(email: str) -> bool:
    recent = [t for t in _failures.get(email.lower(), []) if t > time.time() - 600]
    _failures[email.lower()] = recent
    return len(recent) >= 5


# --- endpoints ------------------------------------------------------------------
class SignupIn(BaseModel):
    email: str
    password: str
    person_name: str  # the person Dory helps, e.g. "Mary"
    family_names: list[str] = Field(default_factory=list)  # may answer Dory's questions
    caregivers: list[str] = Field(default_factory=list)  # may also log medicine


class LoginIn(BaseModel):
    email: str
    password: str
    device: str = ""  # e.g. "Mary's phone", shown nowhere yet but kept with the session


@router.post("/signup", status_code=201)
def signup(body: SignupIn) -> dict:
    account = create_account(body.email, body.password, body.person_name, body.family_names, body.caregivers)
    with _connect() as conn:
        account_id = conn.execute("SELECT id FROM accounts WHERE email = ?", (account.email,)).fetchone()["id"]
        token = _start_session(conn, account_id, "signup")
    return {"token": token, "account": account.model_dump()}


@router.post("/login")
def login(body: LoginIn) -> dict:
    email = body.email.strip()
    if _too_many_failures(email):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a few minutes and try again.")
    with _connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        if row is None or not _check_password(body.password, row["password_hash"]):
            _failures.setdefault(email.lower(), []).append(time.time())
            raise HTTPException(status_code=401, detail="Wrong email or password")
        token = _start_session(conn, row["id"], body.device)
        return {"token": token, "account": _account(row).model_dump()}


def _require(authorization: Optional[str]) -> Account:
    token = _bearer(authorization)
    account = account_for_token(token) if token else None
    if account is None:
        raise HTTPException(status_code=401, detail="Please sign in again")
    return account


@router.get("/me")
def me(authorization: Optional[str] = Header(default=None)) -> Account:
    return _require(authorization)


class ProfileIn(BaseModel):
    person_name: Optional[str] = None
    family_names: Optional[list[str]] = None
    caregivers: Optional[list[str]] = None


@router.patch("/me")
def update_me(body: ProfileIn, authorization: Optional[str] = Header(default=None)) -> Account:
    account = _require(authorization)
    changes = {}
    if body.person_name is not None and body.person_name.strip():
        changes["person_name"] = body.person_name.strip()
    if body.family_names is not None:
        changes["family_names"] = json.dumps(_names(body.family_names))
    if body.caregivers is not None:
        changes["caregivers"] = json.dumps(_names(body.caregivers))
    if changes:
        with _connect() as conn:
            conn.execute(f"UPDATE accounts SET {', '.join(f'{k} = ?' for k in changes)} WHERE person_id = ?",
                         (*changes.values(), account.person_id))
    return account_for_person(account.person_id)


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None)) -> dict:
    token = _bearer(authorization)
    if token:
        with _connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    return {"ok": True}


# --- the guard on every other endpoint ------------------------------------------
async def login_guard(request: Request, authorization: Optional[str] = Header(default=None)) -> None:
    """Keeps each family to its own person. Runs before every endpoint except /health and /auth/*."""
    path = request.url.path
    token = _bearer(authorization)
    if token is None:
        if REQUIRE_LOGIN and not path.startswith(ADMIN_PATHS):
            raise HTTPException(status_code=401, detail="Please sign in")
        return
    account = account_for_token(token)
    if account is None:
        raise HTTPException(status_code=401, detail="Please sign in again")
    if path.startswith(ADMIN_PATHS) or (path.startswith(DEMO_PATHS) and account.person_id != DEMO_PERSON):
        raise HTTPException(status_code=403, detail="Not allowed for a family account")
    request.state.account = account

    asked = {request.path_params.get("person_id"), request.query_params.get("person_id")}
    if request.method in ("POST", "PUT", "PATCH") and "json" in request.headers.get("content-type", ""):
        try:
            body = await request.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            asked.add(body.get("person_id"))
    asked.discard(None)
    if any(p != account.person_id for p in asked):
        raise HTTPException(status_code=403, detail="This account can only see its own person")


def person_of(request: Request, given: Optional[str]) -> Optional[str]:
    """The signed-in family's person, for endpoints where person_id is optional."""
    account: Optional[Account] = getattr(request.state, "account", None)
    return account.person_id if account else given
