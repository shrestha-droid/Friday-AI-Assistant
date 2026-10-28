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

FRIDAY is sharp and cheeky, JARVIS is a dry butler, EDITH is tactical. Say a name while "always listening" is on to switch.
**Ultron** is not selectable. By default every persona stays witty. Only when exactly one viable option is left (a hard refusal,
the single path that works) the reply starts with `[ultron]`: a silk-voiced, unhurried raconteur, and the whole UI turns crimson.
Look closely at the orb every minute or so.

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
