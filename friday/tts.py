"""Local, free, offline voices (Kokoro). Gemini TTS in llm.py is the fallback."""
import io
import logging
import threading
import wave

from . import config

log = logging.getLogger("friday.tts")
_engine = None
_lock = threading.Lock()   # one synthesis at a time; the ONNX session is shared


def available():
    return config.KOKORO_MODEL.exists() and config.KOKORO_VOICES.exists()


def _load():
    global _engine
    if _engine is None:
        from kokoro_onnx import Kokoro
        _engine = Kokoro(str(config.KOKORO_MODEL), str(config.KOKORO_VOICES))
    return _engine


def speak(text, voice, speed):
    """Blocking: text -> WAV bytes. Call it from a worker thread."""
    import numpy as np
    with _lock:
        samples, rate = _load().create(text, voice=voice, speed=speed, lang="en-gb" if voice[0] == "b" else "en-us")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()
