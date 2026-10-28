"""Local, free, offline speech-to-text (faster-whisper). Gemini transcription in llm.py is the fallback."""
import io
import threading
import wave

from . import config

_model = None
_lock = threading.Lock()


def available():
    return any(config.WHISPER_DIR.glob(f"models--Systran--faster-whisper-{config.WHISPER_MODEL}"))


def transcribe(wav_bytes):
    """Blocking: 16-bit mono WAV -> text. Call it from a worker thread. The page always sends 16 kHz."""
    import numpy as np
    global _model
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("expected 16 kHz mono 16-bit WAV")
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8", download_root=str(config.WHISPER_DIR))
        segments, _ = _model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                        initial_prompt="Shrestha, Friday, JARVIS, EDITH, Ultron.")
        return " ".join(s.text.strip() for s in segments).strip()
