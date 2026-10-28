import json

from google.genai import types

from friday import config
from friday.llm import tool_results, user_text
from friday.local_llm import OllamaLLM, schema, text_tool_calls, to_messages
from tests.conftest import run


def add_task(title: str, due_iso: str = ""):
    """Adds a to-do."""


def test_schema_from_signature():
    s = schema(add_task)["function"]
    assert s["name"] == "add_task" and s["parameters"]["required"] == ["title"]
    assert s["parameters"]["properties"]["title"]["type"] == "string"


def test_history_translates_both_ways():
    model_turn = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(id="c1", name="add_task", args={"title": "x"}))])
    msgs = to_messages([user_text("add x"), model_turn, tool_results([("add_task", "c1", "Task #1 added.")])], "SYS")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"]) == {"title": "x"}
    assert msgs[3]["tool_call_id"] == "c1" and msgs[3]["content"] == "Task #1 added."


def test_tool_calls_written_as_text_are_understood():
    known = {"get_system_time", "add_task"}
    assert text_tool_calls('{"name": "get_system_time", "arguments": {}}', known) == [("get_system_time", {})]
    assert text_tool_calls('<tool_call>{"name": "add_task", "arguments": {"title": "milk"}}</tool_call>', known) == [("add_task", {"title": "milk"})]
    assert text_tool_calls('{"name": "rm_everything", "arguments": {}}', known) == []      # unknown tools are ignored
    assert text_tool_calls("Just a normal sentence.", known) == []


def test_local_models_are_routed_and_never_hedged():
    assert config.is_local("ollama/qwen2.5-coder:3b") and not config.is_local("gemini-3.8-flash")
    assert config.pick_model("ollama/qwen2.5-coder:3b", "gemini-3.8-flash") == "ollama/qwen2.5-coder:3b"


def test_ollama_down_is_an_llm_error_not_a_crash():
    from friday.llm import LLMError
    llm = OllamaLLM(base="http://127.0.0.1:9")   # nothing listens on port 9
    try:
        run(llm.generate("ollama/x", [user_text("hi")], "SYS"))
    except LLMError:
        return
    raise AssertionError("expected LLMError")
