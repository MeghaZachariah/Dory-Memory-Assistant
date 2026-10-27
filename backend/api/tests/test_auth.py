"""Family accounts: sign up on the web, log in on the phone, and each family only sees its own person."""
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("DORY_LOG_PATH", str(Path(tempfile.gettempdir()) / "dory_test_calls.jsonl"))
os.environ["DORY_DB"] = "memory"

from fastapi.testclient import TestClient  # noqa: E402

from backend.ai import client as ai_client  # noqa: E402
from backend.ai.tests.fake_model import FakeModel  # noqa: E402
from backend.api import auth, main  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_DB", tmp_path / "auth.db")
    monkeypatch.setattr(auth, "_failures", {})
    ai_client.set_backend(FakeModel())
    c = TestClient(main.app)
    c.post("/demo/reset")
    c.post("/demo/load")
    yield c
    ai_client.set_backend(None)


def _signup(c, email="anu@example.com", name="Joseph"):
    r = c.post("/auth/signup", json={"email": email, "password": "correct-horse", "person_name": name,
                                     "family_names": ["Sam", " "], "caregivers": ["Leela"]})
    assert r.status_code == 201, r.text
    return r.json()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_then_login_on_the_phone(api):
    out = _signup(api)
    acct = out["account"]
    assert acct["person_name"] == "Joseph" and acct["person_id"].startswith("joseph-")
    assert acct["family_names"] == ["Sam"] and acct["caregivers"] == ["Leela"]
    login = api.post("/auth/login", json={"email": "ANU@example.com", "password": "correct-horse", "device": "phone"})
    assert login.status_code == 200 and login.json()["account"]["person_id"] == acct["person_id"]
    assert login.json()["token"] != out["token"]  # the phone gets its own session
    me = api.get("/auth/me", headers=_bearer(login.json()["token"])).json()
    assert me["email"] == "anu@example.com"


def test_signup_checks(api):
    _signup(api)
    dup = api.post("/auth/signup", json={"email": "anu@example.com", "password": "correct-horse", "person_name": "X"})
    assert dup.status_code == 409
    assert api.post("/auth/signup", json={"email": "bad", "password": "correct-horse", "person_name": "X"}).status_code == 400
    assert api.post("/auth/signup", json={"email": "b@x.io", "password": "short", "person_name": "X"}).status_code == 400


def test_wrong_password_and_lockout(api):
    _signup(api)
    for _ in range(5):
        assert api.post("/auth/login", json={"email": "anu@example.com", "password": "nope-nope"}).status_code == 401
    assert api.post("/auth/login", json={"email": "anu@example.com", "password": "correct-horse"}).status_code == 429


def test_password_is_not_stored_in_plain_text(api):
    _signup(api)
    raw = auth.AUTH_DB.read_bytes()
    assert b"correct-horse" not in raw


def test_family_only_reaches_its_own_person(api):
    out = _signup(api)
    pid, h = out["account"]["person_id"], _bearer(out["token"])
    assert api.get(f"/dashboard/{pid}", headers=h).status_code == 200
    assert api.get("/dashboard/mary", headers=h).status_code == 403  # another family's person
    assert api.get("/facts/mary", headers=h).status_code == 403
    assert api.post("/chat", headers=h, json={"person_id": "mary", "message": "hi"}).status_code == 403
    assert api.get("/briefing/morning", headers=h, params={"person_id": "mary"}).status_code == 403
    assert api.post("/voice-server", headers=h, json={"url": "x"}).status_code in (403, 405)
    assert api.put("/voice-server", headers=h, json={"url": "http://evil"}).status_code == 403
    assert api.post("/demo/reset", headers=h).status_code == 403
    # the profile comes from the account
    assert api.get(f"/people/{pid}", headers=h).json()["name"] == "Joseph"


def test_endpoints_without_person_id_use_the_signed_in_person(api):
    out = _signup(api)
    pid, h = out["account"]["person_id"], _bearer(out["token"])
    f = api.post("/memory/fact", headers=h, json={"text": "Joseph likes jazz", "added_by": "Sam"}).json()
    assert any(x["id"] == f["id"] for x in api.get(f"/dashboard/{pid}", headers=h).json()["facts"])
    assert not any(x["text"] == "Joseph likes jazz" for x in api.get("/dashboard/mary").json()["facts"])
    # Mary's family names aren't registered for Joseph
    assert api.post("/memory/fact", headers=h, json={"text": "x", "added_by": "Anu"}).status_code == 403
    m = api.post("/med/log", headers=h, json={"medicine": "B12", "time": "08:00", "confirmed_by": "Leela (caregiver)"})
    assert m.status_code == 200


def test_cannot_answer_another_familys_question(api):
    qid = main.get_db().create_pending_question("mary", "Where is my umbrella?")
    out = _signup(api)
    h = _bearer(out["token"])
    assert api.post(f"/questions/{qid}/answer", headers=h, json={"answer": "x", "answered_by": "Sam"}).status_code == 404
    assert api.post("/family/answer", headers=h, json={"question_id": qid, "answer": "x", "answered_by": "Sam"}).status_code == 404


def test_logout_and_bad_tokens(api):
    out = _signup(api)
    h = _bearer(out["token"])
    assert api.post("/auth/logout", headers=h).json()["ok"]
    assert api.get("/auth/me", headers=h).status_code == 401
    assert api.get("/dashboard/mary", headers=_bearer("made-up")).status_code == 401


def test_profile_update(api):
    out = _signup(api)
    h = _bearer(out["token"])
    r = api.patch("/auth/me", headers=h, json={"family_names": ["Sam", "Tara"]}).json()
    assert r["family_names"] == ["Sam", "Tara"] and r["person_name"] == "Joseph"


def test_login_required_switch(api, monkeypatch):
    monkeypatch.setattr(auth, "REQUIRE_LOGIN", True)
    assert api.get("/health").status_code == 200
    assert api.get("/dashboard/mary").status_code == 401
    auth.ensure_demo_account()
    tok = api.post("/auth/login", json={"email": auth.DEMO_EMAIL, "password": auth.DEMO_PASSWORD}).json()["token"]
    assert api.get("/dashboard/mary", headers=_bearer(tok)).status_code == 200
    assert api.post("/demo/load", headers=_bearer(tok)).status_code == 200  # the demo account may reload its demo
