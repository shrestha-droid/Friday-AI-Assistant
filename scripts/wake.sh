#!/bin/zsh
# Wake Friday: start the server if it is asleep, greet out loud, open the interface.
# Friday.app runs this. You can also run it directly.
DIR="${0:A:h:h}"
PORT="${PORT:-3000}"
URL="https://127.0.0.1:$PORT"
cd "$DIR" || exit 1
mkdir -p logs

if ! curl -sk -m 2 "$URL/health" >/dev/null; then
  nohup friday_env/bin/python friday_server.py >> logs/server.out 2>&1 &
  for _ in {1..60}; do curl -sk -m 1 "$URL/health" >/dev/null && break; sleep 0.5; done
fi

# The token file is owner-only; it never leaves this machine.
curl -sk -m 20 -X POST -H "X-Friday-Token: $(cat data/session_token 2>/dev/null)" "$URL/api/wake" >/dev/null &
open "$URL"
