"""Family voice: Dory API <-> voice server (the real voice_server code in VOICE_FAKE mode)."""
import io
import os
import tempfile
import wave
from pathlib import Path

import pytest

os.environ.setdefault("DORY_LOG_PATH", str(Path(tempfile.gettempdir()) / "dory_test_calls.jsonl"))
os.environ["DORY_DB"] = "memory"
os.environ["VOICE_FAKE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import main, voice  # noqa: E402
from voice_server import server as vs  # noqa: E402


def _wav(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "VOICE_DIR", tmp_path / "dory")
    monkeypatch.setattr(vs, "VOICE_DIR", tmp_path / "colab")
    monkeypatch.setattr(vs, "_voices", {})
    (tmp_path / "colab").mkdir()
    calls = []

    def fake_http():  # the Dory server reaches the voice server through this
        client = TestClient(vs.app)
        original = client.request

        def request(method, url, *a, **kw):
            calls.append((method, str(url)))
            kw.pop("timeout", None)  # real httpx takes it; the in-process test client doesn't
            return original(method, url, *a, **kw)

        client.request = request
        return client

    monkeypatch.setattr(voice, "_http", fake_http)
    c = TestClient(main.app)
    c.put("/voice-server", json={"url": "http://colab.test", "token": ""})
    return c, calls


def _record(c, seconds=15.0, **params):
    q = {"speaker_name": "Anu", "consent": "true", **params}
    return c.put("/voice/mary", params=q, content=_wav(seconds), headers={"Content-Type": "audio/wav"})


def test_record_then_speak(api):
    c, calls = api
    r = _record(c)
    assert r.status_code == 200
    assert r.json() == {**r.json(), "enabled": True, "speaker_name": "Anu", "seconds": 15.0, "server_online": True}
    assert ("PUT", "http://colab.test/voices/mary") in calls
    out = c.post("/voice/mary/speak", json={"text": "Good evening, Mary. It's Dory.", "locale": "en-IN"})
    assert out.status_code == 200 and out.headers["content-type"] == "audio/wav"
    assert out.content[:4] == b"RIFF"


def test_repeated_lines_come_from_cache(api):
    c, calls = api
    _record(c)
    body = {"text": "How was your day today?", "locale": "en-IN"}
    first = c.post("/voice/mary/speak", json=body).content
    n = len(calls)
    assert c.post("/voice/mary/speak", json=body).content == first
    assert len(calls) == n  # second time never reached the voice server


def test_voice_server_restart_resends_the_recording(api):
    c, calls = api
    _record(c)
    vs._voices.clear()  # Colab restarted: the voice server forgot everything
    for f in vs.VOICE_DIR.glob("*.wav"):
        f.unlink()
    out = c.post("/voice/mary/speak", json={"text": "Hello again.", "locale": "en-IN"})
    assert out.status_code == 200
    assert [m for m, u in calls if u.endswith("/voices/mary")].count("PUT") == 2


def test_consent_and_length_are_required(api):
    c, _ = api
    assert _record(c, consent="false").status_code == 400
    assert _record(c, seconds=4).status_code == 400
    bad = c.put("/voice/mary", params={"speaker_name": "Anu", "consent": "true"}, content=b"not audio" * 200)
    assert bad.status_code == 400
    assert c.get("/voice/mary").json()["enabled"] is False


def test_fallbacks_tell_the_app_to_use_the_phone_voice(api):
    c, _ = api
    assert c.post("/voice/mary/speak", json={"text": "Hi"}).status_code == 404  # nothing recorded
    _record(c)
    assert c.post("/voice/mary/speak", json={"text": "Hi", "locale": "ml-IN"}).status_code == 422  # language
    c.put("/voice-server", json={"url": "", "token": ""})
    assert c.post("/voice/mary/speak", json={"text": "Not cached yet"}).status_code == 503  # server off


def test_delete_removes_everything(api):
    c, calls = api
    _record(c)
    c.post("/voice/mary/speak", json={"text": "Hi"})
    assert c.delete("/voice/mary").json()["ok"]
    assert c.get("/voice/mary").json()["enabled"] is False
    assert not (voice.VOICE_DIR / "mary").exists()
    assert ("DELETE", "http://colab.test/voices/mary") in calls
    assert c.post("/voice/mary/speak", json={"text": "Hi"}).status_code == 404


def test_voice_server_token(api, monkeypatch):
    c, _ = api
    monkeypatch.setattr(vs, "TOKEN", "s3cret")
    assert _record(c).json()["enabled"] is True  # saved on the Dory side either way
    assert c.post("/voice/mary/speak", json={"text": "Hi"}).status_code == 503  # wrong token -> phone voice
    c.put("/voice-server", json={"url": "http://colab.test", "token": "s3cret"})
    assert c.post("/voice/mary/speak", json={"text": "Hi"}).status_code == 200
