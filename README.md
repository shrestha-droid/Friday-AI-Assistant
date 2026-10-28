# Friday (v2)

A voice-and-text assistant for your Mac. Friday, J.A.R.V.I.S. and E.D.I.T.H. are three personas on one brain.
Something older and quieter lives underneath all of them. See [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) for the glasses, mat and robot.

## Run it

```bash
friday_env/bin/python friday_server.py        # https://127.0.0.1:3000  (or use the menu-bar app)
friday_env/bin/python scripts/doctor.py       # is everything installed and configured?
friday_env/bin/python scripts/smoke.py        # needs the server running
friday_env/bin/python -m pytest               # 74 offline tests, no network
```

Open the page in **Chrome or Safari** for voice input. Brave blocks speech recognition; typing works everywhere.
Press **Space** to talk, **Enter** to send, **Esc** to stop or deny. Click the orb to talk. Drag a text file onto the window.

## How one request flows

```
browser (index.html) ──POST /api/command──▶ friday_server.py   routes, auth (cookie token, Host/Origin checks)
        ▲                                        │
        │ SSE /api/events                        ▼
        │                              friday/agent.py   the loop WE own:
        │                                 model ─▶ tool ─▶ model ... (≤8 steps, 60 s budget)
        │                                   │         │
        │                      llm.py ◀─────┘         └──▶ permissions.py (SAFE / CONFIRM / BLOCKED, taint)
        │                      the only file that           │
        │                      talks to Gemini              ▼
        │                      (hedges across 3+ models)  tools/*.py  ──▶ data/friday.db (SQLite: memory, tasks,
        │                                                                  reminders, notes, audit log)
        └──── friday/proactive.py: reminders, watchers, morning briefing, daily backup ──▶ friday/events.py
```

| File | Job |
|---|---|
| `friday/config.py` | Every number and setting. Rejects Gemini 1.x/2.x model names. |
| `friday/agent.py` | The tool loop: budgets, loop guard, confirm flow, model failover, history rollback. |
| `friday/llm.py` | Gemini wrapper. Swap this file to change provider. |
| `friday/permissions.py` | Shell allowlist, secret denylist, folder roots, taint rule. |
| `friday/memory.py` | Facts with full-text search; injected each turn as *data*. |
| `friday/personas.py` | Friday, JARVIS, EDITH and the Ultron undertone. |
| `friday/proactive.py` | The EDITH part: speaks up on its own, never acts on its own. |
| `friday/tools/` | Everything it can do. Add a tool with `@tool(...)`. |

## Safety model

- **Three tiers.** SAFE runs at once. CONFIRM shows an approval card with the exact action. BLOCKED never runs.
- **Secrets are unreadable.** `.env`, `*.pem`, `~/.ssh`, browser profiles and the session token are refused for reads too.
- **Prompt injection.** Anything from email, screen or command output is wrapped as `<untrusted_content>`. Once seen, every tool that *acts* needs a human yes, so a poisoned email cannot run a command by itself.
- **Local only.** Binds to 127.0.0.1, checks Host and Origin, requires a token cookie. Every tool call is in the `audit` table.

## The three voices (and the fourth)

FRIDAY is sharp, cheeky and Irish, JARVIS is a dry English butler, EDITH is tactical. Say a name while "always listening" is on to switch.
**Ultron** is not selectable and cannot be uninstalled. In about half of all replies (`ULTRON_ASIDE_RATE`, decided in code) he cuts in
with one witty line: a silk-voiced, unhurried raconteur. His line gets its own voice, a metallic layer, serif italics, and the reticle
turns into crimson triangles while he talks. When exactly one option is left he takes the whole reply, for theatre.
Watch the reticle for a heartbeat of red now and then.

**Voices** come from Kokoro first: free, offline, about 1 to 2 seconds per line on this Mac (model files in `data/voices/`,
voice per character in `friday/personas.py`). If Kokoro is missing or fails, Gemini 3.8 TTS on your key takes over (more
expressive, 4 to 5 seconds, free-tier quota runs out fast), then the browser voice. No real actor is cloned. Lines are cached.
Settings has "Character voices / Browser / Silent", and the LINK panel shows which engine spoke.
Your name is respelled for speech only (`PRONOUNCE` in `config.py`): written Shrestha, said "Shresht".

## The hologram and the house

The centre is a 3D hologram (Three.js with bloom and a glitch pass): a point-cloud core in a geodesic shell, three orbits and a
projector ring. It breathes with the voice. When Ultron cuts in, the whole interface glitches over to him: the palette goes red,
the logo scrambles to U.L.T.R.O.N., and the core's points tear away into his spiked form, then everything snaps back.
He only does this on work topics; any turn that touched email or calendar has him removed in code (`PERSONAL_TOOLS`).

**HOUSE** (top right, or press H) swaps the core for the Mindspace idea from VisionQuest: the system drawn as a monochrome
wireframe house. Engine room in the basement (system, terminal), Friday's study and JARVIS's library on the ground floor,
EDITH's lookout upstairs with the big window. Rooms light up as their tools run. One banister never quite meets its post.
Ultron is in the attic, behind a locked door that leaks red light and strains when he speaks.

## Brains and ears

**Switching brains:** the BRAIN menu in the LINK panel lists every Ollama model on this Mac (LOCAL) and every Gemini 3+ model
(CLOUD). The model Hermes Agent uses is marked HERMES. You can also just say or type "use hermes", "switch to qwen",
"use gemini 3.5 flash". Local models get longer timeouts and are never raced against the cloud; if Ollama is down, Friday
falls back to Gemini and says which model answered. `friday/local_llm.py` translates history and tools to Ollama's
OpenAI-style API, and also understands models that write tool calls as text or in Hermes `<tool_call>` tags.
Small models (e.g. qwen2.5-coder:3b) often skip their tools and invent numbers; use a 7B+ tool-calling model for real work.

**Hearing:** Chrome and Safari use their built-in speech recognition. Brave blocks that, so there the page records the mic
itself and Friday transcribes it with local Whisper (`base.en`, ~0.3 s per sentence, offline, in `data/models/`), falling
back to Gemini if Whisper is missing.

## Configuration (`.env`, all optional)

`DEFAULT_MODEL` (Gemini 3+ only), `BRIEFING_TIME=08:00`, `QUIET_HOURS=23:00-07:00`, `FRIDAY_TZ=Asia/Calcutta`,
`FRIDAY_ALLOWED_ROOTS=/path/one:/path/two`, `THINKING_LEVEL=MINIMAL`, `PORT`, `ENABLE_HTTPS`.

## Operations

- Start at login: see the comments in `scripts/com.friday.server.plist` (do not run it together with the menu-bar app).
- Daily database backup to `data/backups/` (last 7 kept). Logs rotate in `logs/friday.log`.
- Old `tools.py` and test scripts live in `experiments/`. The old memory file is imported once (`scripts/migrate_memory.py`) and kept.

## Not built yet

Calendar reading (needs a macOS permission flow), streaming speech so the first sentence is spoken early, local speech-to-text,
a real wake-word engine, and the glasses/mat/robot firmware. All designed in `docs/ECOSYSTEM.md`.
