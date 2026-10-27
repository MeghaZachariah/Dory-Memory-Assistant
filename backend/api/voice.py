"""Family voice (optional): Dory speaks in a family member's voice.

A family member reads a short paragraph in the app (the first sentence is their
consent). The recording is kept here, in DORY_VOICE_DIR, and sent to the voice
server (voice_server/, OpenVoice v2 on a GPU such as free Colab). During calls the app
asks /voice/{person_id}/speak for each line; any failure means the app uses the
phone's own voice instead, so calls never depend on the voice server.

Where the voice server is: DORY_VOICE_URL and DORY_VOICE_TOKEN in .env, or
PUT /voice-server (handy because a Colab tunnel gets a new address each session).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

VOICE_DIR = Path(os.getenv("DORY_VOICE_DIR", Path(__file__).resolve().parents[1] / "voices"))
SPEAK_TIMEOUT_S = float(os.getenv("DORY_VOICE_TIMEOUT_S", "20"))
MIN_SECONDS = 10  # shorter recordings clone poorly
MAX_BYTES = 10 * 1024 * 1024
# The phone's language setting (en-IN, hi-IN, ...) -> what the voice server speaks.
LANGUAGES = {"en": "en"}  # other languages use the phone voice

router = APIRouter()


def _http() -> httpx.Client:
    return httpx.Client(timeout=SPEAK_TIMEOUT_S)


def _person_dir(person_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", person_id):
        raise HTTPException(status_code=400, detail="person_id may only use letters, digits, _ and -")
    return VOICE_DIR / person_id


def _meta(person_id: str) -> Optional[dict]:
    path = _person_dir(person_id) / "meta.json"
    return json.loads(path.read_text()) if path.exists() else None


def _server() -> tuple[str, str]:
    path = VOICE_DIR / "server.json"
    if path.exists():
        saved = json.loads(path.read_text())
        return saved.get("url", "").rstrip("/"), saved.get("token", "")
    return os.getenv("DORY_VOICE_URL", "").rstrip("/"), os.getenv("DORY_VOICE_TOKEN", "")


def _server_online() -> bool:
    url, _ = _server()
    if not url:
        return False
    try:
        with _http() as h:
            return h.get(f"{url}/health", timeout=5).json().get("model_loaded") is True
    except Exception:  # noqa: BLE001
        return False


def _upload(person_id: str) -> bool:
    """Send the stored recording to the voice server. False if it isn't reachable."""
    url, token = _server()
    if not url:
        return False
    sample = (_person_dir(person_id) / "sample.wav").read_bytes()
    try:
        with _http() as h:
            r = h.put(f"{url}/voices/{person_id}", content=sample,
                      headers={"X-Voice-Token": token, "Content-Type": "audio/wav"}, timeout=60)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _status(person_id: str) -> dict:
    meta = _meta(person_id)
    return {
        "enabled": meta is not None,
        "speaker_name": meta["speaker_name"] if meta else None,
        "seconds": meta["seconds"] if meta else None,
        "created_at": meta["created_at"] if meta else None,
        "server_online": _server_online(),
    }


# --- where the voice server is ------------------------------------------------
class VoiceServer(BaseModel):
    url: str
    token: str = ""


@router.get("/voice-server")
def get_voice_server() -> dict:
    url, _ = _server()
    return {"url": url, "online": _server_online()}


@router.put("/voice-server")
def put_voice_server(body: VoiceServer) -> dict:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    (VOICE_DIR / "server.json").write_text(json.dumps({"url": body.url.rstrip("/"), "token": body.token}))
    return {"url": body.url.rstrip("/"), "online": _server_online()}


# --- one person's family voice -----------------------------------------------
@router.get("/voice/{person_id}")
def get_voice(person_id: str) -> dict:
    return _status(person_id)


@router.put("/voice/{person_id}")
async def put_voice(person_id: str, request: Request, speaker_name: str, consent: bool = False) -> dict:
    """Body: the WAV recording. `consent` must be true: the speaker agreed, in the app and in
    the first sentence they read, to Dory using their voice for this person."""
    if not consent:
        raise HTTPException(status_code=400, detail="The speaker's consent is required")
    if not speaker_name.strip():
        raise HTTPException(status_code=400, detail="speaker_name is required")
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too large")
    try:
        with wave.open(io.BytesIO(data)) as w:
            seconds = w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError) as e:
        raise HTTPException(status_code=400, detail="The recording must be a WAV file") from e
    if seconds < MIN_SECONDS:
        raise HTTPException(status_code=400, detail=f"Please record at least {MIN_SECONDS} seconds")

    folder = _person_dir(person_id)
    shutil.rmtree(folder, ignore_errors=True)  # a new recording replaces the old one and its cache
    folder.mkdir(parents=True)
    (folder / "sample.wav").write_bytes(data)
    (folder / "meta.json").write_text(json.dumps({
        "speaker_name": speaker_name.strip(),
        "seconds": round(seconds, 1),
        "consent": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }))
    _upload(person_id)  # if the voice server is off, it's sent on the first /speak instead
    return _status(person_id)


@router.delete("/voice/{person_id}")
def delete_voice(person_id: str) -> dict:
    shutil.rmtree(_person_dir(person_id), ignore_errors=True)
    url, token = _server()
    if url:
        try:
            with _http() as h:
                h.delete(f"{url}/voices/{person_id}", headers={"X-Voice-Token": token}, timeout=10)
        except httpx.HTTPError:
            pass
    return {"ok": True}


class SpeakBody(BaseModel):
    text: str
    locale: str = "en-IN"


@router.post("/voice/{person_id}/speak")
def speak(person_id: str, body: SpeakBody) -> Response:
    """audio/wav of `text` in the family voice. Errors (no voice, unsupported language,
    voice server off) tell the app to use the phone's voice for this line."""
    meta = _meta(person_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="No family voice recorded")
    language = LANGUAGES.get(body.locale.split("-")[0].lower())
    if language is None:
        raise HTTPException(status_code=422, detail=f"The family voice can't speak {body.locale} yet")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text")

    # Most of Dory's lines repeat (greetings, questions), so each one is made once.
    key = hashlib.sha1(f"{language}|{text}".encode()).hexdigest()
    cached = _person_dir(person_id) / "cache" / f"{key}.wav"
    if cached.exists():
        return Response(cached.read_bytes(), media_type="audio/wav")

    url, token = _server()
    if not url:
        raise HTTPException(status_code=503, detail="No voice server set")
    try:
        with _http() as h:
            def ask() -> httpx.Response:
                return h.post(f"{url}/voices/{person_id}/speak", json={"text": text, "language": language},
                              headers={"X-Voice-Token": token})

            r = ask()
            if r.status_code == 404 and _upload(person_id):  # voice server restarted and forgot the voice
                r = ask()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Voice server unreachable: {e}") from e
    if r.status_code != 200:
        raise HTTPException(status_code=503, detail=f"Voice server error {r.status_code}")
    cached.parent.mkdir(exist_ok=True)
    cached.write_bytes(r.content)
    return Response(r.content, media_type="audio/wav")
