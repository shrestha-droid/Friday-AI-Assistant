import os
import subprocess
import tempfile

from ..registry import tool

_llm = None  # set by the server at startup; keeps Gemini code in llm.py


def set_llm(llm):
    global _llm
    _llm = llm


@tool(untrusted=True)
def analyze_screen():
    """Takes a screenshot of the Mac screen and describes what is visible (apps, text, code)."""
    if _llm is None:
        return "Screen analysis is not available."
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        subprocess.run(["screencapture", "-x", "-t", "jpg", path], check=True, timeout=10)
        data = open(path, "rb").read()
        prompt = "Describe exactly what is on this screen: open apps, visible text, code, and the likely task."
        return "SCREEN: " + _llm.describe_image(data, prompt)
    finally:
        os.remove(path)
