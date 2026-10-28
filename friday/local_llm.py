"""Models served by Ollama on this Mac (OpenAI-compatible API). Model ids look like 'ollama/qwen2.5-coder:3b'.

History stays in Gemini's Content format (the agent's lingua franca); this file translates both ways.
"""
import inspect
import json
import logging
import re
import uuid

import httpx
from google.genai import types

from . import config
from .llm import LLMError, LLMResult

log = logging.getLogger("friday.local")
PREFIX = "ollama/"
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}
_TOOL_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)   # Hermes-style
_THINK = re.compile(r"<think>.*?</think>", re.S)


def schema(fn):
    """Python signature -> OpenAI tool schema."""
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {"type": _JSON_TYPES.get(p.annotation, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "function", "function": {"name": fn.__name__, "description": (fn.__doc__ or "").strip(),
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


def to_messages(contents, system):
    msgs = [{"role": "system", "content": system}]
    for c in contents:
        texts = [p.text for p in c.parts or [] if p.text and not p.thought]
        calls = [p.function_call for p in c.parts or [] if p.function_call]
        results = [p.function_response for p in c.parts or [] if p.function_response]
        if results:
            msgs += [{"role": "tool", "tool_call_id": r.id or r.name, "name": r.name,
                      "content": str((r.response or {}).get("result", r.response))} for r in results]
        elif c.role == "model":
            m = {"role": "assistant", "content": " ".join(texts)}
            if calls:
                m["tool_calls"] = [{"id": f.id or f.name, "type": "function",
                                    "function": {"name": f.name, "arguments": json.dumps(dict(f.args or {}))}} for f in calls]
            msgs.append(m)
        else:
            msgs.append({"role": "user", "content": " ".join(texts)})
    return msgs


def text_tool_calls(text, known):
    """Small models often write the call as text instead of using the API. Accept the common shapes."""
    found = [m.group(1) for m in _TOOL_TAG.finditer(text)] or [text.strip().strip("`").removeprefix("json").strip()]
    calls = []
    for raw in found:
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        for o in obj if isinstance(obj, list) else [obj]:
            if isinstance(o, dict) and o.get("name") in known:
                args = o.get("arguments", o.get("parameters", {}))
                calls.append((o["name"], json.loads(args) if isinstance(args, str) else dict(args or {})))
    return calls


class OllamaLLM:
    def __init__(self, base=None):
        self.base = (base or config.OLLAMA_URL).rstrip("/")
        self.http = httpx.AsyncClient(timeout=config.LOCAL_CALL_TIMEOUT_S)

    async def generate(self, model, contents, system, tools=None):
        name = model.removeprefix(PREFIX)
        body = {"model": name, "messages": to_messages(contents, system), "stream": False}
        if tools:
            body["tools"] = [schema(f) for f in tools]
        try:
            r = await self.http.post(f"{self.base}/v1/chat/completions", json=body)
            if r.status_code == 400 and tools and "does not support tools" in r.text:
                body.pop("tools")           # chat-only model: still usable, just without tools
                r = await self.http.post(f"{self.base}/v1/chat/completions", json=body)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise LLMError(f"{model}: {type(e).__name__} {str(e)[:150]}") from e

        text = _THINK.sub("", msg.get("content") or "").strip()
        calls = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            calls.append((tc["function"]["name"], json.loads(args) if isinstance(args, str) else dict(args), tc.get("id")))
        if not calls and tools:
            calls = [(n, a, None) for n, a in text_tool_calls(text, {f.__name__ for f in tools})]
            if calls:
                text = _TOOL_TAG.sub("", text).strip() if "<tool_call>" in text else ""
        calls = [(n, a, cid or f"call_{uuid.uuid4().hex[:8]}") for n, a, cid in calls]
        parts = ([types.Part(text=text)] if text else []) + [
            types.Part(function_call=types.FunctionCall(id=cid, name=n, args=a)) for n, a, cid in calls]
        return LLMResult(content=types.Content(role="model", parts=parts or [types.Part(text="")]), text=text, calls=calls)

    async def list_models(self):
        """Chat-capable models Ollama knows about (cloud-backed ones included, marked by their name)."""
        try:
            r = await self.http.get(f"{self.base}/api/tags", timeout=3)
            r.raise_for_status()
        except httpx.HTTPError:
            return []
        return sorted(PREFIX + m["name"] for m in r.json().get("models", [])
                      if "completion" in (m.get("capabilities") or ["completion"]))
