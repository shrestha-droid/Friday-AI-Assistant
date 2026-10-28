from .. import memory
from ..registry import tool


@tool(effects=True)
def remember(content: str, category: str = "general"):
    """Saves a fact about the owner or their projects (category e.g. 'preference', 'project', 'person')."""
    fid, how = memory.remember(content, category, source="assistant")
    return f"Memory {how} (#{fid})."


@tool()
def recall(query: str):
    """Searches long-term memory and returns all relevant facts."""
    hits = memory.recall(query)
    return "\n".join(f"#{h['id']} [{h['category']}] {h['content']}" for h in hits) or "Nothing relevant in memory."


@tool(effects=True)
def forget(fact_id: int):
    """Deletes one remembered fact by its number."""
    return "Forgotten." if memory.forget(fact_id) else "No such memory."


@tool()
def list_memories(category: str = ""):
    """Lists everything remembered about the owner, optionally for one category."""
    facts = memory.list_facts(category or None)
    return "\n".join(f"#{f['id']} [{f['category']}] {f['content']}" for f in facts) or "Memory is empty."
