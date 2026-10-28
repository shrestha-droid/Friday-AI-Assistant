"""The only file that talks to Gemini. Swap this file to change provider."""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import errors, types

from . import config

log = logging.getLogger("friday.llm")

RETRYABLE = {429, 500, 502, 503, 504}


class LLMError(Exception):
    def __init__(self, message, retryable=False, auth=False):
        super().__init__(message)
        self.retryable = retryable
        self.auth = auth


@dataclass
class LLMResult:
    content: Any          # appended to history UNCHANGED (Gemini attaches thought signatures to it)
    text: str
    calls: list           # [(name, args_dict, call_id)]


class GeminiLLM:
    def __init__(self):
        if not config.API_KEY:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required (put it in .env).")
        # attempts=1: the SDK's own silent retries made every 503 cost seconds. Failover is ours (agent hedging).
        self.client = genai.Client(api_key=config.API_KEY,
                                   http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
        self.no_minimal = set()   # models that reject thinking_level=MINIMAL (learned at runtime)
        from .local_llm import OllamaLLM   # here, not at the top: local_llm imports this module
        self.local = OllamaLLM()

    def _cfg(self, model, system, tools):
        level = "LOW" if model in self.no_minimal and config.THINKING_LEVEL == "MINIMAL" else config.THINKING_LEVEL
        kw = dict(
            system_instruction=system,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=level),
        )
        if tools:
            kw["tools"] = tools
        return types.GenerateContentConfig(**kw)

    async def generate(self, model, contents, system, tools=None):
        if config.is_local(model):
            return await self.local.generate(model, contents, system, tools)
        for attempt in (1, 2):
            try:
                resp = await self.client.aio.models.generate_content(
                    model=model, contents=contents, config=self._cfg(model, system, tools))
                break
            except errors.APIError as e:
                code = getattr(e, "code", 0) or 0
                msg = str(getattr(e, "message", e))
                if code == 400 and "thinking level" in msg.lower() and attempt == 1:
                    self.no_minimal.add(model)   # e.g. gemini-3.8-flash: retry once with LOW
                    continue
                raise LLMError(f"{model}: {code} {msg}"[:300],
                               retryable=code in RETRYABLE, auth=code in (401, 403)) from e
        if not resp.candidates or not resp.candidates[0].content:
            raise LLMError(f"{model}: empty response")
        content = resp.candidates[0].content
        parts = content.parts or []
        text = "".join(p.text for p in parts if p.text and not p.thought)
        calls = [(p.function_call.name, dict(p.function_call.args or {}), p.function_call.id)
                 for p in parts if p.function_call]
        return LLMResult(content=content, text=text.strip(), calls=calls)

    def describe_image(self, image_bytes, prompt, mime="image/jpeg"):
        """Blocking on purpose: it is called from a tool's worker thread."""
        resp = self.client.models.generate_content(
            model=config.DEFAULT_MODEL,
            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime)])
        return resp.text or ""

    async def speak(self, text, voice, style):
        """Text -> WAV bytes in a prebuilt Gemini voice, steered by a plain-English style line."""
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
        last = None
        for model in config.TTS_MODELS:
            try:
                resp = await self.client.aio.models.generate_content(model=model, contents=f"{style}: {text}", config=cfg)
                data = resp.candidates[0].content.parts[0].inline_data.data
                return data if data[:4] == b"RIFF" else _wav(data)
            except Exception as e:  # noqa: BLE001  any failure -> next model, then the browser voice
                last = e
                log.warning("tts model=%s failed: %s", model, str(e)[:160])
        raise LLMError(f"tts failed: {last}"[:200])

    async def transcribe(self, data, mime="audio/wav"):
        """Speech -> text, for browsers without speech recognition (Brave). Tries a few models, first answer wins."""
        prompt = ("Transcribe the speech exactly, in English. Reply with only the words spoken, "
                  "no quotes or labels. If there is no speech, reply with nothing. Names you may hear: Shrestha "
                  "(said 'Shresht'), Friday, JARVIS, EDITH, Ultron.")
        last = None
        for model in config.STT_MODELS:
            try:
                async with asyncio.timeout(12):
                    resp = await self.client.aio.models.generate_content(
                        model=model, contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt])
                return (resp.text or "").strip()
            except (errors.APIError, TimeoutError) as e:
                last = e
                log.warning("stt model=%s failed: %s", model, str(e)[:120])
        raise LLMError(f"transcription failed: {last}"[:200])

    def list_models(self):
        names = [m.name.replace("models/", "") for m in self.client.models.list()]
        ok = []
        for n in names:
            if not n.startswith("gemini") or any(x in n for x in ("embedding", "image", "tts", "live", "audio", "transcribe", "robotics", "omni", "banana")):
                continue
            m = re.match(r"gemini-(\d+)", n)
            if m and int(m.group(1)) < 3:
                continue  # Gemini 2.x and older do not work for this account
            ok.append(n)
        return sorted(set(ok))


def _wav(pcm, rate=24000):
    """Raw 16-bit mono PCM -> WAV (in case the API ever returns L16 instead of a WAV file)."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def user_text(text):
    return types.Content(role="user", parts=[types.Part(text=text)])


def tool_results(results):
    """results: [(name, call_id, result_str)] -> one user Content holding every function response."""
    return types.Content(role="user", parts=[
        types.Part(function_response=types.FunctionResponse(id=cid, name=name, response={"result": res}))
        for name, cid, res in results])
