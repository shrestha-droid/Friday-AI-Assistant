import email
import imaplib
import os
import subprocess
import urllib.parse
from email.header import decode_header

from ..registry import CONFIRM, tool


def _subject(msg):
    raw, enc = decode_header(msg["Subject"] or "")[0]
    return raw.decode(enc or "utf-8", errors="ignore") if isinstance(raw, bytes) else raw


def _body(msg):
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode(errors="ignore")
    return ""


@tool(untrusted=True)
def read_latest_emails():
    """Reads the 5 newest UNREAD emails (sender, subject, start of body) and the unread count."""
    user, pw = os.getenv("FRIDAY_EMAIL"), os.getenv("FRIDAY_EMAIL_PASSWORD")
    if not user or not pw:
        return "Email is not set up. Tell the owner to add FRIDAY_EMAIL and FRIDAY_EMAIL_PASSWORD to .env."
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, pw)
        mail.select("inbox", readonly=True)   # reading must never mark mail as read
        ids = mail.search(None, "UNSEEN")[1][0].split()
        out = []
        for i in ids[-5:]:
            msg = email.message_from_bytes(mail.fetch(i, "(BODY.PEEK[])")[1][0][1])
            out.append(f"From: {msg.get('From')}\nSubject: {_subject(msg)}\nBody: {_body(msg)[:400]}")
        mail.logout()
        return f"{len(ids)} unread.\n\n" + "\n---\n".join(out) if out else "No unread email."
    except imaplib.IMAP4.error:
        return "Email login failed. The app password may be wrong."


@tool(effects=True)
def draft_visual_email(to_email: str, subject: str, body: str):
    """Opens a draft email on screen. The owner reads it and presses send."""
    q = urllib.parse.quote
    url = f"mailto:{to_email}?subject={q(subject)}&body={q(body)}"
    if len(url) > 2000:
        return "Draft is too long for a pop-up. Ask the owner to shorten it."
    subprocess.run(["open", url])
    return f"Opened an email draft to {to_email}."


@tool(tier=CONFIRM, effects=True, describe=lambda a: f"Open a calendar event draft: {a.get('title')}")
def draft_calendar_event(title: str, description: str):
    """Opens a pre-filled Google Calendar event for the owner to save."""
    q = urllib.parse.quote
    subprocess.run(["open", f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={q(title)}&details={q(description)}"])
    return "Opened the calendar draft."
