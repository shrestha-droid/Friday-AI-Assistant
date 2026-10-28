"""The only file that talks to Gemini. Swap this file to change provider."""
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
        self.client = genai.Client(api_key=config.API_KEY)

    def _cfg(self, system, tools):
        kw = dict(
            system_instruction=system,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=config.THINKING_LEVEL),
        )
        if tools:
            kw["tools"] = tools
        return types.GenerateContentConfig(**kw)

    async def generate(self, model, contents, system, tools=None):
        try:
            resp = await self.client.aio.models.generate_content(
                model=model, contents=contents, config=self._cfg(system, tools))
        except errors.APIError as e:
            code = getattr(e, "code", 0) or 0
            raise LLMError(f"{model}: {code} {getattr(e, 'message', e)}"[:300],
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


def user_text(text):
    return types.Content(role="user", parts=[types.Part(text=text)])


def tool_results(results):
    """results: [(name, call_id, result_str)] -> one user Content holding every function response."""
    return types.Content(role="user", parts=[
        types.Part(function_response=types.FunctionResponse(id=cid, name=name, response={"result": res}))
        for name, cid, res in results])
