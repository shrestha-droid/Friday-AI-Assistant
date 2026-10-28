"""Smoke test: talks to a RUNNING Friday server. Starts nothing itself.

Run the server first, then:  friday_env/bin/python scripts/smoke.py
"""
import json
import ssl
import sys
import urllib.request

BASE = "https://127.0.0.1:3000"

# The dev server uses a self-signed certificate, so we skip verification here.
# Safe only because we talk to 127.0.0.1 on our own machine.
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=10, context=CTX) as r:
        return json.load(r)


def post_json(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.load(r)


def check(name, fn):
    try:
        fn()
        print(f"PASS  {name}")
        return True
    except Exception as e:
        print(f"FAIL  {name}: {e}")
        return False


def health():
    assert get_json("/health")["status"] == "online"


def harmless_command():
    # A harmless question that needs no tools and no file access.
    assert post_json("/api/command", {"text": "Say the word ready."})["response"]


if __name__ == "__main__":
    results = [check("health", health), check("harmless command", harmless_command)]
    sys.exit(0 if all(results) else 1)
