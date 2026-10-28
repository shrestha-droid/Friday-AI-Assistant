import pytest

from friday import fast
from friday.agent import Agent
from friday.sessions import Session
from tests.conftest import FakeLLM, run


@pytest.fixture(autouse=True)
def machine(monkeypatch):
    monkeypatch.setattr(fast, "read_system", lambda: {"cpu": 12.0, "ram": 81.0, "disk": 49.0, "battery": 77, "plugged": False})


@pytest.mark.parametrize("q,expect", [
    ("How's my battery?", "Battery's at 77 percent, boss."),
    ("how full is my disk", "Disk is 49 percent full, boss."),
    ("How much RAM am I using?", "Memory's at 81 percent, boss."),
    ("What's the CPU at?", "CPU is at 12 percent, boss."),
    ("How's my Mac?", "CPU 12, memory 81, disk 49 percent, battery 77 percent, boss."),
])
def test_status_questions_are_instant(q, expect):
    assert fast.answer(q, "friday") == expect


@pytest.mark.parametrize("q", [
    "Remind me when the battery is low",       # an action, not a question
    "What's in your memory?",                  # memory as in remembered facts, not RAM
    "Write the disk report to a file",
    "How's my battery and disk?",              # two intents: let the model answer properly
    "Why is my CPU so high and what is eating it, can you look into the processes for me please?",
])
def test_everything_else_goes_to_the_model(q):
    assert fast.answer(q, "friday") is None


def test_instant_answer_skips_the_model_and_keeps_history():
    llm = FakeLLM([])        # any model call would fail: the script is empty
    s = Session("s")
    r = run(Agent(llm).run_turn(s, "How's my battery?"))
    assert r["response"].startswith("Battery's at 77") and r["model"] == "instant" and len(s.contents) == 2
