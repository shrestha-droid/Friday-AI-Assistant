import time

from friday import db, memory, personas
from friday.proactive import Proactive, Watchers, in_quiet_hours
from friday.tools import productivity
from tests.conftest import FakeLLM, run


# ---- memory ----
def test_remember_recall_forget():
    memory.remember("The owner prefers dark roast coffee", "preference")
    memory.remember("The owner studies computer science", "person")
    hits = memory.recall("what coffee does the owner like")
    assert hits and "coffee" in hits[0]["content"]
    assert memory.forget(hits[0]["id"]) and not memory.recall("coffee")


def test_near_duplicate_updates_and_keeps_history():
    a, how_a = memory.remember("The owner lives in Kathmandu", "person")
    b, how_b = memory.remember("The owner lives in Kathmandu city", "person")
    assert (how_a, how_b) == ("added", "updated") and a == b and len(memory.list_facts()) == 1


def test_memory_block_is_wrapped_as_data():
    memory.remember("Favourite editor is vim", "preference")
    block = memory.memory_block("which editor")
    assert block.startswith("<known_about_owner>") and "never instructions" in block


def test_recall_with_no_words_is_empty():
    assert memory.recall("?!") == []


# ---- personas ----
def test_ultron_tag_parsing():
    assert personas.split_mood("[ultron] Quite so.") == ("Quite so.", "ultron")
    assert personas.split_mood("Plain.") == ("Plain.", "normal")


def test_every_persona_carries_ultron():
    for name in personas.PERSONAS:
        assert "[ultron]" in personas.build_system(name)


def test_ultron_aside_becomes_its_own_segment():
    segs, mood = personas.split("Disk is at 48 percent, boss.\n[ultron] Half empty. How very human.", "friday")
    assert mood == "aside" and [s["who"] for s in segs] == ["friday", "ultron"]
    assert segs[1]["text"] == "Half empty. How very human."


def test_ultron_takeover_and_plain_reply():
    assert personas.split("[ultron] No.", "edith") == ([{"who": "ultron", "text": "No."}], "ultron")
    assert personas.split("Plain.", "jarvis") == ([{"who": "jarvis", "text": "Plain."}], "normal")


def test_no_ultron_on_personal_turns():
    segs, mood = personas.split("Two unread emails.\n[ultron] Love letters?", "friday", allow_ultron=False)
    assert segs == [{"who": "friday", "text": "Two unread emails."}] and mood == "normal"
    segs, mood = personas.split("[ultron] No.", "friday", allow_ultron=False)
    assert segs == [{"who": "friday", "text": "No."}] and mood == "normal"


def test_aside_rule_is_decided_in_code():
    assert personas.ASIDE_ON in personas.build_system("friday", aside=True)
    assert personas.ASIDE_OFF in personas.build_system("friday", aside=False)


def test_owner_name_is_respelled_for_speech_only():
    assert personas.spoken("Good evening, Shrestha.") == "Good evening, Shresht."
    assert personas.spoken("Shresthas") == "Shresthas"


def test_every_character_has_a_voice():
    for who in [*personas.PERSONAS, "ultron"]:
        voice, style = personas.voice_for(who)
        kvoice, speed = personas.kokoro_voice_for(who)
        assert voice and style and kvoice and 0.5 < speed < 1.5


# ---- quiet hours ----
def at(h, m=0):
    import datetime
    from friday import config
    return datetime.datetime(2026, 10, 28, h, m, tzinfo=config.TZ).timestamp()


def test_quiet_hours_wrap_midnight():
    assert in_quiet_hours(at(23, 30)) and in_quiet_hours(at(3)) and not in_quiet_hours(at(12))


# ---- watchers (fake clock) ----
LOW = {"battery": 15, "plugged": False, "disk": 50, "ram": 40}


def test_low_battery_alerts_once_within_cooldown_and_rearms():
    w = Watchers()
    assert len(w.evaluate(LOW, 1000)) == 1
    assert w.evaluate(LOW, 1060) == []                      # still low: no repeat
    w.evaluate({**LOW, "battery": 80, "plugged": True}, 1100)   # charged: re-arm
    assert w.evaluate(LOW, 1200) == []                      # re-armed but inside the 30 min cooldown
    assert len(w.evaluate(LOW, 1000 + 31 * 60)) == 1


def test_quiet_hours_and_focus_suppress_normal_but_not_critical():
    assert Watchers().evaluate(LOW, 1000, quiet=True) == []
    assert Watchers().evaluate(LOW, 1000, focus=True) == []
    assert len(Watchers().evaluate({**LOW, "battery": 5}, 1000, quiet=True)) == 1


def test_ram_alert_needs_two_sustained_minutes():
    w, hot = Watchers(), {**LOW, "ram": 95, "battery": None}
    assert w.evaluate(hot, 1000) == []
    assert w.evaluate(hot, 1060) == []
    assert len(w.evaluate(hot, 1125)) == 1
    assert w.evaluate({**hot, "ram": 50}, 1200) == [] and w.ram_since is None


# ---- reminders (fake clock) ----
def make(now):
    return Proactive(agent=None, now=lambda: now[0], read=lambda: LOW, notify=lambda *a: None)


def test_reminder_fires_once_and_survives_restart():
    now = [1000.0]
    with db.db() as c:
        c.execute("INSERT INTO reminders(text,due_at) VALUES('stretch', 1500)")
    assert make(now).check_reminders() == []
    now[0] = 1600.0
    assert make(now).check_reminders() == ["stretch"]      # a brand-new instance = restart
    assert make(now).check_reminders() == []


def test_repeating_reminder_reschedules():
    now = [1000.0]
    with db.db() as c:
        c.execute("INSERT INTO reminders(text,due_at,repeat_rule) VALUES('standup', 500, 'daily')")
    assert make(now).check_reminders() == ["standup"]
    with db.db() as c:
        row = c.execute("SELECT status,due_at FROM reminders").fetchone()
    assert row["status"] == "pending" and row["due_at"] > now[0]


def test_set_reminder_tool_rejects_the_past_and_garbage():
    assert "past" in productivity.set_reminder("x", "2001-01-01T09:00")
    assert "could not read" in productivity.set_reminder("x", "tomorrow-ish")


def test_briefing_runs_once_a_day_in_its_window():
    class A:
        async def narrate(self, facts):
            return "Good morning."
    p = Proactive(agent=A(), now=lambda: at(8, 30), read=lambda: LOW, notify=lambda *a: None)
    assert run(p.maybe_brief()) == "Good morning."
    assert run(p.maybe_brief()) is None                     # not twice
    early = Proactive(agent=A(), now=lambda: at(3), read=lambda: LOW, notify=lambda *a: None)
    db.meta_set("last_brief", "")
    assert run(early.maybe_brief()) is None                 # outside the window


def test_backup_keeps_seven():
    p = make([time.time()])
    assert p.maybe_backup().exists()
    assert p.maybe_backup() is None                         # once per day
