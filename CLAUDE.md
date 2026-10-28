# FRIDAY → EDITH: working rules for Claude Code

The big plan is in `EDITH_PLAN.md`. Read it before doing anything. Work one phase at a time.

## Who you are working with
The owner is a student building this to **truly understand** it, not just to have it built. The goal is to be the person who could build the whole thing from scratch. Treat teaching as part of the job, not an extra.

## Working agreement (applies to every task)
1. **Before building a phase:** give a short "what you need to understand" map in simple words: what the topic is, the core ideas, why it works. Keep it under one screen.
2. **While building:** for each file, explain in a few plain sentences why it is written that way. Once per phase, stop and ask the owner to predict what a function will do or to write a first attempt of one small function. Then fill in the gaps.
3. **After building:** ask the 3 to 5 teach-back questions from the plan. Wait for the answers. Correct gently and explain. Do **not** start the next phase until the owner says "next".
4. **Simple language.** Short sentences. No jargon without a one-line explanation.
5. **Whole files.** When you create or change a code file, write the **complete file**, not a patch or a snippet. Small quoted snippets are fine for explaining, but the file on disk is always complete.
6. **Always state the exact path** of every file you create (for example `friday/agent.py`), and of every file you change.
7. Be honest about uncertainty. If you are not sure an SDK name or behavior is right, check the installed version's docs or test it, and say what you verified.

## Project facts
- macOS. Python 3.14 virtualenv at `friday_env/`. Use `friday_env/bin/python` and `friday_env/bin/pip`.
- Server: `friday_server.py` (FastAPI, HTTPS on `127.0.0.1:3000`). The menu-bar app `friday_menubar.py` launches it by that exact filename, so **do not rename it**.
- UI: `index.html` (Three.js + browser speech). Do not break the existing look.
- LLM: Google Gemini through `google-genai`. Keep Gemini-specific code in one place.

## Never
- Read, print, log, commit or send `.env`, `certs/key.pem` or any other secret.
- Run destructive commands (`rm -rf`, `sudo`, force-push, history rewrites) without asking first.
- Delete the owner's files. Move them to `experiments/` instead.
- Skip the smoke test (`scripts/smoke.py`) before committing a phase.
- Commit to the main branch directly. Use one branch per phase.
