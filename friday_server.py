"""Friday's server: thin routes, auth and lifespan. The thinking lives in the friday/ package."""
import asyncio
import json
import logging
import os
import secrets
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from friday import config, db, logging_setup, memory, personas

logging_setup.setup()
logger = logging.getLogger("friday")

import friday.tools  # noqa: E402,F401  (registers every tool)
from friday.agent import Agent  # noqa: E402
from friday.events import bus  # noqa: E402
from friday.llm import GeminiLLM  # noqa: E402
from friday.proactive import Proactive  # noqa: E402
from friday.sessions import sessions  # noqa: E402
from friday.tools import screen  # noqa: E402
from friday.tools.system import read_system  # noqa: E402

VERSION = "2.0.0"

try:
    llm = GeminiLLM()
except RuntimeError as e:
    logger.critical("Startup failed: %s", e)
    raise
screen.set_llm(llm)
agent = Agent(llm)


def load_token():
    """Generated once, kept in data/session_token (gitignored, owner-only). Never printed."""
    config.DATA_DIR.mkdir(exist_ok=True)
    if config.TOKEN_PATH.exists():
        return config.TOKEN_PATH.read_text().strip()
    tok = secrets.token_urlsafe(32)
    config.TOKEN_PATH.write_text(tok)
    config.TOKEN_PATH.chmod(0o600)
    return tok


TOKEN = load_token()
SCHEME = "https" if config.ENABLE_HTTPS else "http"
ALLOWED_HOSTS = {f"localhost:{config.PORT}", f"127.0.0.1:{config.PORT}"}
ALLOWED_ORIGINS = {f"{SCHEME}://{h}" for h in ALLOWED_HOSTS}


def guard(request: Request):
    """Host check (DNS rebinding), Origin check (other websites), then the token."""
    if request.headers.get("host", "") not in ALLOWED_HOSTS:
        raise HTTPException(403, "Bad host.")
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(403, "Bad origin.")
    tok = request.cookies.get("friday_token") or request.headers.get("x-friday-token") or ""
    if not secrets.compare_digest(tok, TOKEN):
        logger.warning("Rejected request without a valid token: %s", request.url.path)
        raise HTTPException(401, "Invalid session token.")


@asynccontextmanager
async def lifespan(app):
    psutil.cpu_percent(interval=None)  # first reading is always 0, prime it
    task = asyncio.create_task(Proactive(agent).run())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
    token = logging_setup.request_id.set(rid)
    path, start = request.url.path, time.time()
    quiet = path in ("/health", "/api/health", "/api/events", "/api/state")
    try:
        if not quiet:
            logger.info("Incoming %s %s", request.method, path)
        response = await call_next(request)
        if not quiet:
            logger.info("Completed %s %s status=%s duration=%dms", request.method, path,
                        response.status_code, (time.time() - start) * 1000)
        response.headers["X-Request-ID"] = rid
        return response
    except Exception:
        logger.exception("Failed %s %s", request.method, path)
        return JSONResponse({"detail": "An internal error occurred.", "request_id": rid}, status_code=500)
    finally:
        logging_setup.request_id.reset(token)


class CommandRequest(BaseModel):
    text: str
    model: str | None = None
    session_id: str | None = None
    persona: str | None = None


class ConfirmRequest(BaseModel):
    session_id: str
    action_id: str
    approve: bool


def _session(session_id):
    if session_id and len(session_id) > 64:
        raise HTTPException(400, "Bad session id.")
    return sessions.get(session_id)


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "online", "version": VERSION, "gemini_configured": True,
            "model": config.DEFAULT_MODEL, "timestamp": datetime.now().isoformat()}


@app.get("/")
async def serve_ui(request: Request):
    if request.headers.get("host", "") not in ALLOWED_HOSTS:
        raise HTTPException(403, "Bad host.")
    resp = FileResponse(config.ROOT / "index.html", headers={"Cache-Control": "no-store"})
    # ponytail: any local process can GET / and read this cookie. It stops other WEBSITES, not local malware.
    resp.set_cookie("friday_token", TOKEN, httponly=True, samesite="strict", secure=config.ENABLE_HTTPS)
    return resp


@app.get("/api/models", dependencies=[Depends(guard)])
async def list_models():
    try:
        models = await asyncio.to_thread(llm.list_models)
    except Exception:
        logger.exception("model listing failed")
        models = []
    models = sorted(set(models) | {config.DEFAULT_MODEL, *config.FALLBACK_MODELS})
    return {"models": models, "default": config.DEFAULT_MODEL}


@app.post("/api/command", dependencies=[Depends(guard)])
async def command(req: CommandRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Command text cannot be empty.")
    if len(text) > 4000:
        raise HTTPException(400, "Command text exceeds 4000 characters.")
    logger.info("Processing command length=%d persona=%s", len(text), req.persona)
    return await agent.run_turn(_session(req.session_id), text, req.model, req.persona)


@app.post("/api/confirm", dependencies=[Depends(guard)])
async def confirm(req: ConfirmRequest):
    return await agent.confirm(_session(req.session_id), req.action_id, req.approve)


@app.post("/api/brief", dependencies=[Depends(guard)])
async def brief():
    from friday.tools.productivity import briefing_facts
    return {"response": await agent.narrate(briefing_facts())}


@app.get("/api/state", dependencies=[Depends(guard)])
async def state():
    with db.db() as c:
        reminders = [dict(r) for r in c.execute(
            "SELECT id,text,due_at,repeat_rule FROM reminders WHERE status='pending' ORDER BY due_at LIMIT 10")]
        tasks = [dict(r) for r in c.execute(
            "SELECT id,title,due_at FROM tasks WHERE status='open' ORDER BY due_at IS NULL, due_at LIMIT 10")]
    return {"system": read_system(), "reminders": reminders, "tasks": tasks, "memory": memory.list_facts()[-20:],
            "focus_until": float(db.meta_get("focus_until", 0)),
            "personas": {k: v["label"] for k, v in personas.PERSONAS.items()}}


@app.delete("/api/memory/{fact_id}", dependencies=[Depends(guard)])
async def delete_memory(fact_id: int):
    return {"deleted": memory.forget(fact_id)}


@app.get("/api/events", dependencies=[Depends(guard)])
async def events(request: Request):
    q = bus.subscribe()

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn

    logger.info("FRIDAY BRAIN ONLINE (%s:%s, https=%s, model=%s)", config.HOST, config.PORT,
                config.ENABLE_HTTPS, config.DEFAULT_MODEL)
    kwargs = {"host": config.HOST, "port": config.PORT, "log_level": "warning"}
    if config.ENABLE_HTTPS:
        cert, key = config.SSL_CERTFILE, config.SSL_KEYFILE
        if not (cert and key and os.path.exists(cert) and os.path.exists(key)):
            cert_dir = config.ROOT / "certs"
            cert_dir.mkdir(exist_ok=True)
            cert, key = str(cert_dir / "cert.pem"), str(cert_dir / "key.pem")
            if not (os.path.exists(cert) and os.path.exists(key)):
                subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key, "-out", cert,
                                "-days", "365", "-nodes", "-subj", "/CN=localhost"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kwargs.update(ssl_certfile=cert, ssl_keyfile=key)
    uvicorn.run(app, **kwargs)
