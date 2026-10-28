"""One-off: import the old friday_memory.json into the SQLite memory. The old file is kept as a backup."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from friday import config, memory  # noqa: E402

old = config.ROOT / "friday_memory.json"
if not old.exists():
    sys.exit("No friday_memory.json to migrate.")
n = 0
for topic, content in json.loads(old.read_text()).items():
    for part in str(content).split(" | "):
        memory.remember(f"{topic}: {part}", category="migrated", source="friday_memory.json")
        n += 1
print(f"Imported {n} facts. {old.name} left untouched as a backup.")
