"""Smoke test: talks to a RUNNING Friday server. Starts nothing itself.

    friday_env/bin/python scripts/smoke.py            # https://127.0.0.1:3000
    FRIDAY_URL=http://127.0.0.1:3001 friday_env/bin/python scripts/smoke.py

It never reads .env: it gets its session token the same way the browser does, from the cookie on GET /.
"""
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

BASE = os.getenv("FRIDAY_URL", "https://127.0.0.1:3000")

# The dev server uses a self-signed certificate. Skipping verification is safe only because this talks to 127.0.0.1.
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=CTX))
anon = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))


def call(path, body=None, client=opener, timeout=90):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with client.open(req, timeout=timeout) as r:
        return json.load(r) if "json" in r.headers.get("content-type", "") else r.read()


def check(name, fn):
    try:
        fn()
        print(f"PASS  {name}")
        return True
    except Exception as e:
        print(f"FAIL  {name}: {e}")
        return False


def health():
    assert call("/health")["status"] == "online"


def ui_sets_token():
    call("/")
    assert any(c.name == "friday_token" for c in jar), "no session cookie"


def rejects_without_token():
    try:
        call("/api/state", client=anon)
    except urllib.error.HTTPError as e:
        assert e.code == 401, f"expected 401, got {e.code}"
        return
    raise AssertionError("an unauthenticated request was accepted")


def state():
    assert "system" in call("/api/state")


def harmless_command():
    r = call("/api/command", {"text": "Say the word ready.", "session_id": "smoke"})
    assert r["status"] == "ok" and r["response"], f"status={r.get('status')}: {r.get('response')}"


if __name__ == "__main__":
    results = [check("health", health), check("UI sets session token", ui_sets_token),
               check("rejects requests without token", rejects_without_token), check("state", state),
               check("harmless command", harmless_command)]
    sys.exit(0 if all(results) else 1)
