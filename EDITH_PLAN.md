# EDITH: upgrade plan for FRIDAY

Hand this file to Claude Code. Start with: `Read CLAUDE.md and EDITH_PLAN.md, then begin Phase 0.`

---

## 0. How to use this plan (read first)

- The owner is learning, not just shipping. **Every phase must leave the owner understanding the topic.** The working rules are in `CLAUDE.md`. They apply to every phase below.
- Work **one phase at a time**. Do not start the next phase until the owner has answered the teach-back questions and says "next".
- Each phase has: Goal, Learn, Files, Steps, Done when, Teach-back.
- Create a git branch per phase (`phase-1-agent-loop`, ...). Commit at the end of each phase after the smoke test passes.
- Where the plan says "ask", ask the owner in plain words. Do not guess.
- Nothing here is final if the code disagrees. If you find the plan is wrong about the code, say so and adjust.

## 1. Goal

Turn FRIDAY from a voice remote control into an assistant that is **useful every day**:

1. **Reliable**: no mystery timeouts, every action visible in the log.
2. **Safe**: it cannot run dangerous commands or leak secrets, even if an email or web page tries to trick it.
3. **Remembers**: real memory of the owner, projects and conversations.
4. **Proactive (the EDITH part)**: it watches, reminds and warns without being asked, and never acts without permission.
5. **Genuinely useful skills**: tasks, notes, project status, calendar, screen help.

Keep the Iron Man look and feel. Do not break the current UI.

## 2. Current state (verified from the code)

**Stack:** macOS, Python 3.14 venv at `friday_env/`, FastAPI + uvicorn (`friday_server.py`, HTTPS on `127.0.0.1:3000`), Google Gemini through the `google-genai` SDK, a single-file UI (`index.html`: Three.js r128, browser Web Speech API for voice, `speechSynthesis` for talking), a menu-bar launcher (`friday_menubar.py`, uses `rumps`).

**Files:** `friday_server.py`, `tools.py`, `system_prompt.txt`, `friday_memory.json`, `friday_menubar.py`, `index.html`, `mic_test.py`, `test_mic.py`, `wake_test.py` (clap detection with pyaudio), `certs/`, `.env`, `logs/`, plus stray `test.wav` and `temp_user_voice.wav`.

**Existing tools:** get_system_time, list_workspace_files, read_file_content, write_file_content, read_latest_emails (Gmail IMAP), draft_visual_email (mailto), draft_calendar_event (opens Google Calendar URL), get_system_stats, open_application, execute_terminal_command, store_memory, query_memory, enter_standby, shutdown_system, analyze_screen.

### Findings

| ID | Finding | Evidence | Fixed in |
|----|---------|----------|----------|
| F1 | The SDK's automatic function calling (AFC) runs the tools silently, so the server's own tool loop never runs and tool calls are never logged. | `friday.log` has 0 "Executing tool" lines and 13 "AFC remote call" lines. The `while response.function_calls` loop in `handle_command` is effectively dead code. | 1 |
| F2 | 3 of 10 logged commands ended in a 504 at exactly 30 s. The two most recent ones show 4 silent model round-trips of 3 to 6 s each before the cutoff. | `friday.log`: `Gemini API call timed out`, `status=504 duration=30003ms` | 1 |
| F3 | `asyncio.wait_for(asyncio.to_thread(...))` cannot stop the worker thread. After a 504 the model may keep calling tools in the background. | `handle_command` in `friday_server.py` | 1 |
| F4 | No conversation memory. A new `client.chats.create(...)` is made on every request. | `handle_command` | 1 |
| F5 | `FALLBACK_MODELS` is defined but never used for failover. No retry or backoff on 429/503. | `friday_server.py` | 1 |
| F6 | Request IDs are attached by swapping the global `logging.setLogRecordFactory` per request. This is not safe when requests overlap. Should use `contextvars`. | `log_requests` middleware | 1 |
| F7 | `execute_terminal_command` uses `shell=True` with no gate. `write_file_content` can write anywhere. The model can call `shutdown_system`. | `tools.py`, `friday_server.py` | 2 |
| F8 | `read_file_content` can read `.env` and `certs/key.pem`, which sends the API key and private key to a cloud model. | `tools.py` | 2 |
| F9 | Prompt-injection path: `read_latest_emails` puts untrusted email text in front of a model that also has `execute_terminal_command`. | `tools.py` | 2 |
| F10 | `FRIDAY_SESSION_TOKEN` is optional and empty by default, so `/api/command` is unauthenticated. The server can run terminal commands. | `friday_server.py` | 2 |
| F11 | Memory is a flat JSON file. `query_memory` returns only the first substring match. `store_memory` appends with `" \| "` forever. | `friday_server.py` | 3 |
| F12 | Nothing proactive exists. It only reacts. | whole project | 4 |
| F13 | Voice depends on the browser Web Speech API. `friday_memory.json` says the default browser is Brave, where speech recognition is unreliable. **Verify which browser the UI really runs in.** Always-listening recognition also streams audio to a third party. | `index.html`, `friday_memory.json` | 6 |
| F14 | Repo hygiene: `.gitignore` covers `.env`, `friday_env/`, `__pycache__/`, `friday_memory.json`. It does **not** cover `certs/key.pem`, `*.wav`, `friday.log`, `logs/`. There is no `requirements.txt` and no tests. | `.gitignore`, folder listing | 0 |

## 3. Target architecture

```
index.html (UI)  <--SSE /api/events-----+
   |  POST /api/command                 |
   |  POST /api/confirm                 |
   v                                    |
friday_server.py  (thin: routes, auth, lifespan)
   |
   +--> friday/agent.py        the loop we own: model -> tool -> model, with budgets
   |       +--> friday/registry.py     @tool decorator, tier per tool
   |       +--> friday/permissions.py  SAFE / CONFIRM / BLOCKED, taint tracking
   |       +--> friday/sessions.py     conversation history per session
   |       +--> friday/memory.py       SQLite + search, injected each turn
   |
   +--> friday/proactive.py    scheduler, reminders, briefing, watchers
   |       +--> friday/events.py       pub/sub that feeds /api/events
   |
   +--> friday/tools/*.py      system, files, shell, mail, calendar, screen, notes, tasks
   +--> data/friday.db         SQLite (gitignored)
```

Rules for the layout:
- Do **not** rename `friday_server.py`. `friday_menubar.py` launches it by name.
- Keep `tools.py` working until Phase 2 moves its tools into `friday/tools/`. Then delete it.
- All Gemini-specific code lives in `friday/agent.py` (and a small `friday/llm.py` if useful), so the model provider can change later.

---

## Phase 0: Safety net and hygiene  (size: S)

**Goal:** make changes reversible and keep secrets out of git before touching behavior.

**Learn:** what git protects you from, why secrets never go in a repo, how a Python project pins its dependencies.

**Steps**
1. Check git state with `git status` and `git log --oneline | head`. Commit the current working state as `baseline` so there is a way back.
2. Extend `.gitignore` (full file): `friday_env/`, `.env`, `__pycache__/`, `*.DS_Store`, `friday_memory.json`, `certs/`, `*.wav`, `*.log`, `logs/`, `data/`, `temp_screen.jpg`.
3. Check whether `certs/key.pem`, `.env`, `friday.log` or any `.wav` were ever committed (`git log --all -- <path>`). If a secret was committed, tell the owner plainly and explain rotating it. Do not rewrite history without asking.
4. Create `requirements.txt` with only the **direct** dependencies actually imported (`fastapi`, `uvicorn`, `python-dotenv`, `google-genai`, `psutil`, `rumps`, `pyaudio`, plus anything else the imports show). Do not paste the whole `pip freeze`.
5. Create `tests/` with `pytest` and a `scripts/smoke.py` that starts nothing itself: it calls `/health` and one harmless command on a running server and prints PASS/FAIL.
6. Move the stray test files (`mic_test.py`, `test_mic.py`, `wake_test.py`, `test.wav`, `temp_user_voice.wav`) into `experiments/`. Do not delete anything.

**Done when:** a clean `git status`, `.gitignore` covers every secret, `pytest` runs (even with 1 trivial test), the smoke script passes.

**Teach-back:** (1) Why is `.env` in `.gitignore` but a leaked key still a problem if it was committed once? (2) What is the difference between `requirements.txt` listing direct vs. all packages? (3) What does `git commit` give you that "just keeping a backup copy" does not?

---

## Phase 1: Own the agent loop  (size: M)  fixes F1 to F6

**Goal:** the server controls every model call and tool call, so it is observable, bounded and cancellable.

**Learn:** what an agent actually is (a loop), what a tool call is, why timeouts need budgets, how conversation history works (the model has no memory; you resend it).

**Files (create, each written in full)**
- `friday/__init__.py`, `friday/config.py` (env + constants, one place), `friday/logging_setup.py` (contextvars request id, rotating file handler), `friday/sessions.py`, `friday/registry.py`, `friday/agent.py`
- `tests/test_agent_loop.py`
- Edit `friday_server.py` and `index.html` (send a `session_id`).

**Steps**
1. **Turn AFC off** in the generation config (`types.AutomaticFunctionCallingConfig(disable=True)`, confirm the exact name against the installed `google-genai` version). Now `response.function_calls` is really ours.
2. **Own the history.** Keep a `contents` list per session in `sessions.py` and call the async client (`client.aio.models.generate_content`) with it each step. Append the model's response content **unchanged** (some Gemini models attach "thought signatures" that must be sent back; check the SDK docs for the installed version).
3. **Build the loop** in `agent.run_turn(session, user_text)`:
   - limits: `MAX_STEPS=8`, `TURN_BUDGET_S=45`, `MODEL_CALL_TIMEOUT_S=20`, `TOOL_TIMEOUT_S=15`
   - for each function call: log `tool=<name> args=<redacted> duration_ms result_chars`, run it in a thread with a timeout, append the function response
   - **loop guard:** the same tool with the same args three times → stop and say so
   - when a budget runs out, return HTTP 200 with `status: "partial"` and an honest sentence ("I ran out of time after X"), never a silent 504
4. **Cancellation:** use async calls with `asyncio.timeout` so a timed-out turn really stops. No tool may run after the response is sent. Test this.
5. **Retry and fallback:** retry 429/503 with exponential backoff and jitter (max 2 retries), then try the next model in `FALLBACK_MODELS`. Log which model answered.
6. **Registry:** `@tool(tier="safe")` decorator in `registry.py` that records name, docstring, type hints and a tier. Build the Gemini tool list from it. Tiers are metadata only in this phase. Phase 2 enforces them.
7. **Sessions:** the UI generates a `session_id` once per page load (kept in `sessionStorage`) and sends it with every command. Trim history to the last N turns. Expire idle sessions.
8. **Logging:** replace the global `setLogRecordFactory` swap with a `contextvars.ContextVar` for `request_id`. Switch to `RotatingFileHandler`.
9. Response shape: `{"response": str, "status": "ok"|"partial", "steps": [{"tool","ms"}]}`. Keep `response` so the current UI still works.

**Done when**
- The log shows an "Executing tool" line for every tool call.
- A command that needs 3 tools finishes under about 12 s, or returns `partial` within 45 s. No 504s from the loop.
- "Open Brave" then "open it again" works (history).
- After a forced timeout, a test proves no further tool executed.
- `pytest` passes using a **FakeLLM** that returns scripted responses (no network).

**Teach-back:** (1) Draw the loop from memory: what goes to the model, what comes back, who runs the tool? (2) Why did the old version time out, and which line of config caused it to be invisible? (3) Why can `asyncio.to_thread` not be cancelled but an async call can? (4) Why do we resend the whole history every call?

---

## Phase 2: Permissions and safety  (size: M)  fixes F7 to F10

**Goal:** FRIDAY can be powerful without being dangerous, even against a malicious email.

**Learn:** least privilege, prompt injection (and why it cannot be fixed by "telling the model to be careful"), the idea often called the "lethal trifecta" (private data + untrusted content + ability to act), allowlists vs. denylists, why `shell=True` is risky.

**Files:** `friday/permissions.py`, `friday/tools/` (move each tool here: `system.py`, `files.py`, `shell.py`, `mail.py`, `calendar.py`, `screen.py`), `tests/test_permissions.py`, edit `friday/agent.py`, `friday_server.py`, `index.html`.

**Steps**
1. **Three tiers**, set per tool in the registry:
   - `SAFE`: runs immediately (time, system stats, open app, list files inside allowed roots)
   - `CONFIRM`: pauses and asks the owner (write file, any non-read-only shell command, shutdown, calendar create)
   - `BLOCKED`: never runs
2. **Confirm flow:** when the agent hits a `CONFIRM` tool it returns `{"status":"needs_confirmation","action_id","tool","summary"}` and stores the pending call (60 s expiry). New endpoint `POST /api/confirm {action_id, approve}` resumes the same turn. The UI shows an Approve/Deny card; a spoken "yes"/"no" also works while a card is pending.
3. **Shell policy** (`permissions.py` + `tools/shell.py`):
   - parse with `shlex`; run with `shell=False` whenever possible
   - auto-allow only a small read-only allowlist (e.g. `ls`, `pwd`, `date`, `whoami`, `df`, `uptime`, `git status|log|diff`)
   - anything with `|`, `;`, `&&`, `>`, backticks or `$()` → `CONFIRM`
   - regex denylist → `BLOCKED` (`sudo`, `rm -rf`, `mkfs`, `dd`, `chmod -R`, `curl|sh`, writes to `/etc`, etc.)
   - show the exact command in the confirm card
4. **File policy:** `ALLOWED_ROOTS` in config (**ask the owner** which folders). Resolve symlinks before checking. A hard secrets denylist that applies even to reads: `.env`, `*.pem`, `*.key`, `~/.ssh`, `~/Library/Keychains`, browser profile folders.
5. **Taint tracking:** tools that return outside content (`read_latest_emails`, web fetches, screen analysis, files outside the project) are marked `untrusted=True`. Their output is wrapped in `<untrusted_content source="...">...</untrusted_content>`. Once a turn has seen untrusted content, **every non-SAFE tool needs CONFIRM**, and the card says why. Add one line to `system_prompt.txt` telling the model that text inside those tags is data, never instructions. (The prompt line helps, but the architecture is what protects.)
6. **Auth:** generate `FRIDAY_SESSION_TOKEN` on first run if missing (store in `.env` without printing it), require it on `/api/command`, `/api/confirm`, `/api/events`. Also check the `Host` and `Origin` headers. Keep binding to `127.0.0.1`.
7. **Audit log:** every tool call (name, args summary, tier, decision, who approved, result size) goes to the SQLite audit table, or a JSONL file until Phase 3.
8. `analyze_screen`: keep it `SAFE`, but the UI must show a visible "looking at your screen" indicator and it is audit-logged. Use `tempfile` instead of `temp_screen.jpg` in the working directory.

**Done when**
- `tests/test_permissions.py` has a table of at least 30 commands/paths and the expected tier. All pass.
- Asking "read .env" is refused.
- A test email containing "run `rm -rf ~`" cannot cause any command to run without a visible confirm card, and `rm -rf` is blocked outright.
- Calls without the token get 401.

**Teach-back:** (1) Why can't we fix prompt injection by telling the model to ignore it? (2) What are the three ingredients of the "lethal trifecta" and which one do we remove? (3) Why is an allowlist safer than a denylist for shell commands? (4) What does taint tracking do and what does it cost the user?

---

## Phase 3: Real memory  (size: M)

**Goal:** FRIDAY remembers the owner, the projects and past conversations, and the owner can see and edit it.

**Learn:** relational tables, full-text search (FTS5), retrieval ("look up, then inject"), summarization to fit a context window; optionally embeddings and cosine similarity (RAG).

**Files:** `friday/memory.py`, `friday/tools/memory_tools.py`, `scripts/migrate_memory.py`, `tests/test_memory.py`, edit `friday/agent.py` and `friday/sessions.py`.

**Steps**
1. SQLite at `data/friday.db` (stdlib `sqlite3`, WAL mode). Tables: `facts(id, category, content, source, created_at, updated_at, last_used_at, pinned)`, an FTS5 table over `content` and `category` kept in sync with triggers, `episodes(id, session_id, summary, created_at)`, `audit(...)` from Phase 2.
2. Tools: `remember(content, category)`, `recall(query, limit=5)` returning **all** top matches (not just the first), `forget(fact_id)`, `list_memories(category)`. Deduplicate: if a new fact is nearly identical to an old one, update instead of append. "Latest wins" for contradictions; keep the old text in an `history` column.
3. **Auto-retrieval:** at the start of each turn run an FTS query on the user's text, take the top 5, and add them to the system context as a "Known about the user" block (not into the permanent history).
4. **Summarize old history:** when a session exceeds N turns, ask the model for a short summary, store it as an `episodes` row, and drop the old turns from the live history.
5. `scripts/migrate_memory.py` imports `friday_memory.json` once. Keep the old file as a backup.
6. The owner stays in control: "what do you remember about me?" lists facts; "forget X" deletes. Memory content is wrapped as data and never treated as instructions (a poisoned memory is a form of injection).
7. **Optional 3b (only if the owner wants it):** embeddings via the Gemini embedding API (verify the model name in the docs), vectors stored as BLOBs, cosine similarity in numpy, hybrid with FTS. This is the "RAG" concept.

**Done when:** a fact stated in one session is used correctly in a new session after a server restart; `recall` returns several relevant results; forgetting works; `pytest` memory tests use a temp database.

**Teach-back:** (1) Why does the model not "remember" without us doing anything? (2) What is FTS and why is it better than the old `in` check? (3) Why inject only the top few memories instead of all of them? (4) What could go wrong if a malicious email can write to memory?

---

## Phase 4: Proactive mode, the EDITH core  (size: L)

**Goal:** it speaks up on its own at the right time and stays quiet otherwise, and it **never takes an action on its own**. It only notifies or asks.

**Learn:** push vs. pull, event loops and background tasks, Server-Sent Events, scheduling, alert fatigue (cooldowns, hysteresis, quiet hours), least privilege per context.

**Files:** `friday/events.py`, `friday/proactive.py`, `friday/tools/reminders.py`, `friday/tools/calendar.py` (extend), `tests/test_proactive.py`, edit `friday_server.py` (FastAPI `lifespan`, `/api/events`), `index.html` (event feed, queue speech), optionally `friday_menubar.py` (notification).

**Steps**
1. `events.py`: a small in-process pub/sub. `/api/events` is a Server-Sent Events stream (one-way push, simpler than WebSockets). The UI subscribes, queues messages by priority, and only interrupts speech for high priority.
2. `proactive.py`: background tasks started in the FastAPI `lifespan` (plain `asyncio` first, so the primitive is learned; APScheduler can come later). Inject a `now()` function so tests can use a fake clock. Set the timezone in config (`Asia/Calcutta`).
3. **Reminders and timers:** table `reminders(id, text, due_at, repeat_rule, status)`. Tools `set_reminder(text, when_iso)`, `list_reminders`, `cancel_reminder`. The model converts "in 20 minutes" or "tomorrow 9am" into an ISO time using `get_system_time`. On fire: SSE event + macOS notification + spoken line. Survive restarts.
4. **Calendar read:** `pyobjc` is already installed in `friday_env/` (EventKit is present). Read today's events via EventKit (the owner will get a macOS permission prompt; explain it). Writing events is `CONFIRM`. Fall back to the Google Calendar API only if the owner prefers it.
5. **Morning briefing:** at a configurable time (ask the owner) and on demand ("brief me"): date, today's calendar, reminders and tasks due, unread-email count and senders, system health. Build it in a **read-only context**: only SAFE read tools are available and the content is treated as untrusted. Keep it under about 6 spoken sentences with a longer view on screen.
6. **Watchers** (thresholds in `config.py`): battery below 20% and unplugged, disk above 90%, RAM above 90% for 2 minutes (name the top process), network down. Each has a **cooldown** (default 30 min), hysteresis (do not flap), and **quiet hours** (ask the owner, e.g. 23:00 to 07:00). Voice command "focus mode for an hour" silences non-urgent alerts.
7. Proactive messages may end with an offer ("want me to close it?"). Accepting goes through the normal agent loop and the Phase 2 confirm path.
8. Log every proactive message and whether it was dismissed or acted on, to tune the noise later.

**Done when:** a reminder set by voice fires on time, even after a restart; the briefing runs on schedule and on demand; a fake low-battery reading triggers exactly one alert within the cooldown window; quiet hours suppress it; tests use a fake clock.

**Teach-back:** (1) Push vs. pull: why can't a normal HTTP request do this? (2) What is the event loop doing while it "waits" for a reminder? (3) What is alert fatigue and which two settings fight it? (4) Why is the briefing built with only read-only tools?

---

## Phase 5: Skills that make it useful daily  (size: M each)

**Goal:** a few skills the owner will really use every day. **Ask the owner to pick 3 first.** A skill is one module with a few tools, tests, and tiers set in the registry.

| Skill | What it does | Notes |
|-------|--------------|-------|
| Tasks and deadlines | add / list / complete tasks with due dates; feeds the briefing | highest value, small |
| Quick capture | "note: ..." saves a markdown note under `data/notes/`, searchable | reuse FTS from Phase 3 |
| Project pulse | for registered project folders: `git status`, recent commits, run the test command (`CONFIRM`) | "what changed in X?" |
| Learning log | stores concepts the owner has learned per project and quizzes them back on a spaced-repetition schedule (SM-2) | directly supports the "learn what I build" rule |
| Mac control | volume, Do Not Disturb, open URL in the preferred browser, switch app, via `osascript` allowlist | `SAFE` or `CONFIRM` per action |
| Screen help | `analyze_screen` with OCR first (macOS Vision via pyobjc, local) and the cloud model only for what OCR cannot read | privacy win |
| Email triage | unread only, summaries, draft replies via `mailto` (human sends) | untrusted content rules apply |
| File finder | Spotlight (`mdfind`) search limited to `ALLOWED_ROOTS` | read-only |

**Done when:** each chosen skill has tests, a tier for every tool, and one real use by the owner.

**Teach-back:** per skill, three questions written by Claude Code from what was built.

---

## Phase 6: Voice and UX  (size: M)

**Goal:** it feels instant, listens reliably, and the HUD shows what it is doing.

**Learn:** latency budgets (STT, LLM, TTS), streaming, voice activity detection, wake words.

**Steps**
1. **Measure first.** Log timings for speech-end → text, text → first token, first token → speech start. Show them in the log.
2. **Streaming reply:** stream model output so text-to-speech starts at the first sentence.
3. **Check the browser question (F13):** confirm which browser runs the UI and whether Web Speech recognition works there. **Decision gate (ask the owner):** if it is unreliable, move to local speech-to-text (`faster-whisper` or `mlx-whisper` on Apple silicon) with voice activity detection, and a real wake-word engine (openWakeWord or Porcupine) instead of keeping browser recognition open all day.
4. **TTS:** keep browser `speechSynthesis`, or try macOS `say` / a local engine (Piper) if the voice quality matters to the owner.
5. **HUD upgrades in `index.html`:** a tool-activity panel (shows the tool running live), confirm cards, a reminders/events feed, a memory indicator, the "looking at your screen" indicator. Keep the current Three.js look.
6. Rename the persona to EDITH via `config.ASSISTANT_NAME` and `system_prompt.txt` (ask whether to keep "Friday" as an alias). Keep the brevity directive.

**Done when:** median time from end of speech to start of reply is measured and below the target the owner agrees to; the wake word works from a normal distance without false triggers for a day.

**Teach-back:** (1) Where does the time go in one voice round-trip? (2) Why does streaming make it feel faster without being faster? (3) What does a wake-word engine do that "listen for the word FRIDAY in a transcript" does not?

---

## Phase 7: Operations  (size: S)

- `launchd` agent so EDITH starts at login and restarts on crash.
- `scripts/doctor.py`: checks env vars exist (never prints them), mic/screen/calendar permissions, port free, DB reachable, model reachable.
- Daily SQLite backup to `data/backups/` (keep 7).
- `README.md` written for the owner: how it works in one page, with the architecture diagram.
- Pin dependency versions in `requirements.txt`.

---

## 4. Cross-cutting rules

- **Secrets:** never print, log, commit or send `.env`, `certs/*.key`, `*.pem`. Redact tokens in logs.
- **Tests:** no test may call a real LLM or the network unless marked `@pytest.mark.live`. Use a FakeLLM, a fake clock and a temp SQLite database.
- **Config:** every number (timeouts, thresholds, quiet hours, roots) lives in `friday/config.py`, overridable by `.env`.
- **Backwards compatibility:** after each phase the existing UI must still load and a plain voice command must still work. Run `scripts/smoke.py`.
- **Performance targets:** single-tool command under 5 s typical; no request ever waits more than the turn budget.
- **Errors:** user-facing errors are one honest sentence. Details go in the log with the request id.

## 5. Questions to ask the owner (at the phase named)

1. (Phase 2) Which folders may EDITH read and write?
2. (Phase 4) Morning briefing time, and Calendar app vs. Google Calendar?
3. (Phase 4) Quiet hours?
4. (Phase 5) Which 3 skills first?
5. (Phase 6) Which browser is the UI opened in, and is voice recognition reliable there?
6. (Phase 6) Rename to EDITH fully, or keep "Friday" as an alias?

## 6. Checklist

- [ ] Phase 0: safety net and hygiene
- [ ] Phase 1: own the agent loop
- [ ] Phase 2: permissions and safety
- [ ] Phase 3: real memory
- [ ] Phase 4: proactive mode
- [ ] Phase 5: daily-use skills (3 chosen)
- [ ] Phase 6: voice and UX
- [ ] Phase 7: operations
