"""Dory's family-voice server: speaks text in a family member's voice with OpenVoice v2.

MeloTTS (MIT) says the line in a base English voice, then OpenVoice v2's tone-colour
converter (MIT) makes it sound like the family member's recording. A GPU makes it quick
enough for a call (Google Colab's free one is fine); a laptop CPU works but is slow.
Only the Dory API server talks to it; the phone never does. Start it with
dory_voice_colab.ipynb in this folder, or by hand:

    VOICE_TOKEN=some-secret OPENVOICE_CKPT=checkpoints_v2 uvicorn voice_server.server:app --port 8001

OPENVOICE_CKPT is the folder with converter/ and base_speakers/ses/ from
huggingface.co/myshell-ai/OpenVoiceV2. VOICE_BASE_SPEAKER picks the base accent
(EN_INDIA, EN-US, EN-BR, EN-AU, EN-Default). VOICE_FAKE=1 skips the models and answers
with a short tone, for testing anywhere.
"""
from __future__ import annotations

import io
import math
import os
import re
import struct
import tempfile
import threading
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

TOKEN = os.getenv("VOICE_TOKEN", "")
FAKE = os.getenv("VOICE_FAKE", "") == "1"
VOICE_DIR = Path(os.getenv("VOICE_DIR", Path(tempfile.gettempdir()) / "dory_voices"))
CKPT_DIR = Path(os.getenv("OPENVOICE_CKPT", "checkpoints_v2"))
BASE_SPEAKER = os.getenv("VOICE_BASE_SPEAKER", "EN_INDIA")
SPEED = float(os.getenv("VOICE_SPEED", "0.9"))  # a little slower than normal, easier to follow
SAMPLE_RATE = 22050  # OpenVoice v2 output rate
# MeloTTS base voices exist for these; Dory only sends English for now.
LANGUAGES = {"en"}

_tts: Any = None  # MeloTTS, English
_converter: Any = None  # OpenVoice ToneColorConverter
_speaker_id: Optional[int] = None
_source_se: Any = None  # the base voice's tone colour
_voices: dict[str, Any] = {}  # voice_id -> the family member's tone colour
_lock = threading.Lock()  # one synthesis at a time


def _load_models() -> None:
    global _tts, _converter, _speaker_id, _source_se
    if FAKE or _converter is not None:
        return
    import torch
    from melo.api import TTS
    from openvoice.api import ToneColorConverter

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    converter = ToneColorConverter(str(CKPT_DIR / "converter" / "config.json"), device=device, enable_watermark=False)
    converter.load_ckpt(str(CKPT_DIR / "converter" / "checkpoint.pth"))
    tts = TTS(language="EN", device=device)
    speakers = tts.hps.data.spk2id
    if BASE_SPEAKER not in speakers:
        raise RuntimeError(f"VOICE_BASE_SPEAKER must be one of {list(speakers)}")
    se_file = CKPT_DIR / "base_speakers" / "ses" / f"{BASE_SPEAKER.lower().replace('_', '-')}.pth"
    _source_se = torch.load(str(se_file), map_location=device)
    _speaker_id = speakers[BASE_SPEAKER]
    _tts, _converter = tts, converter


@asynccontextmanager
async def lifespan(_: FastAPI):
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    _load_models()  # a minute or two the first time (downloads the English voice model)
    yield


app = FastAPI(title="Dory voice server", lifespan=lifespan)


def check_token(x_voice_token: Optional[str] = Header(default=None)) -> None:
    if TOKEN and x_voice_token != TOKEN:
        raise HTTPException(status_code=401, detail="Missing or wrong X-Voice-Token header")


secured = [Depends(check_token)]


def _sample_path(voice_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", voice_id):
        raise HTTPException(status_code=400, detail="voice_id may only use letters, digits, _ and -")
    return VOICE_DIR / f"{voice_id}.wav"


def _register(voice_id: str) -> None:
    path = _sample_path(voice_id)
    if FAKE:
        _voices[voice_id] = True
        return
    with _lock:
        _voices[voice_id] = _converter.extract_se([str(path)])


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model_loaded": FAKE or _converter is not None, "fake": FAKE, "voices": len(_voices)}


@app.put("/voices/{voice_id}", dependencies=secured)
async def put_voice(voice_id: str, request: Request) -> dict:
    """Body: the family member's recording (WAV). Replaces any earlier one."""
    data = await request.body()
    if len(data) < 1000:
        raise HTTPException(status_code=400, detail="The recording is empty or too short")
    _sample_path(voice_id).write_bytes(data)
    try:
        _register(voice_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not use this recording: {e}") from e
    return {"ok": True, "voice_id": voice_id}


@app.delete("/voices/{voice_id}", dependencies=secured)
def delete_voice(voice_id: str) -> dict:
    _sample_path(voice_id).unlink(missing_ok=True)
    _voices.pop(voice_id, None)
    return {"ok": True}


class SpeakRequest(BaseModel):
    text: str
    language: str = "en"


@app.post("/voices/{voice_id}/speak", dependencies=secured)
def speak(voice_id: str, body: SpeakRequest) -> Response:
    """Returns audio/wav of `text` in that voice. 404 if the voice isn't registered here
    (for example after Colab restarted): the caller re-uploads the sample and retries."""
    if body.language not in LANGUAGES:
        raise HTTPException(status_code=422, detail=f"Language {body.language!r} isn't supported")
    if voice_id not in _voices:
        if not _sample_path(voice_id).exists():
            raise HTTPException(status_code=404, detail="Unknown voice")
        _register(voice_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text")
    if FAKE:
        return Response(_wav(_tone(0.3)), media_type="audio/wav")

    import numpy as np

    with _lock, tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "base.wav")
        _tts.tts_to_file(text, _speaker_id, base, speed=SPEED, quiet=True)  # MeloTTS splits sentences itself
        audio = _converter.convert(audio_src_path=base, src_se=_source_se, tgt_se=_voices[voice_id])
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    return Response(_wav(pcm), media_type="audio/wav")


def _tone(seconds: float) -> bytes:
    n = int(SAMPLE_RATE * seconds)
    return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE))) for i in range(n))


def _wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()
