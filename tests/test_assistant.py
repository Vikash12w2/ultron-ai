import json
from datetime import datetime, timezone

import httpx
from pydantic_ai import exceptions as E
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import config
from core.assistant import Assistant
from core.history import build_history
from core.providers import ProviderPool, seconds_until_midnight_pacific
from core.router import Router


def _pool(models, keys=True):
    pool = ProviderPool(config.load_providers(), get_key=lambda _k: "key" if keys else "")
    pool.build = lambda name: (FunctionModel(models[name], model_name=name), {})
    return pool


def _text(answer):
    return lambda messages, info: ModelResponse(parts=[TextPart(answer)])


def _tool_then_answer(tool, args, answer="done"):
    def fn(messages, info: AgentInfo):
        if any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            return ModelResponse(parts=[TextPart(answer)])
        return ModelResponse(parts=[ToolCallPart(tool, args)])
    return fn


def test_cloud_sees_local_replies_but_not_device_prompts_or_tool_results(db):
    seen = {}

    def groq(messages, info):
        raise E.ModelQuotaExceededError("gpt-oss", "daily limit")

    def gemini(messages, info):
        seen["messages"], seen["tools"] = messages, [t.name for t in info.function_tools]
        return ModelResponse(parts=[TextPart("Shared memory is on-chip.")])

    pool = _pool({"local": _tool_then_answer("system_info", {"kind": "ram"}, "1.5 GB free"),
                  "groq": groq, "gemini": gemini})
    a = Assistant(db, Router(), pool)
    cid = db.new_conversation()
    assert a.respond(cid, "how much ram is free").route == "device"
    reply = a.respond(cid, "/local hi")
    cid2 = db.new_conversation()
    db.add_message(cid2, "user", "LOCAL_USER_PROMPT", route="device")
    db.add_message(cid2, "assistant", "LOCAL_ASSISTANT_REPLY", route="device", provider="Local · qwen3:1.7b")
    db.add_message(cid2, "assistant", "LOCAL_ERROR_MESSAGE", route="device", provider="Local error · qwen3:1.7b")
    db.add_message(cid2, "context", "LOCAL_RAW_TOOL_RESULT", route="device", provider="Local · qwen3:1.7b")
    reply = a.respond(cid2, "explain cuda shared memory")
    assert reply.provider.startswith("Gemini") and "Groq" in reply.note
    sent = json.dumps([str(m) for m in seen["messages"]])
    assert "LOCAL_ASSISTANT_REPLY" in sent
    assert "LOCAL_ERROR_MESSAGE" not in sent
    assert "LOCAL_USER_PROMPT" not in sent
    assert "LOCAL_RAW_TOOL_RESULT" not in sent
    assert seen["tools"] == []
    assert pool.availability("groq")[0] is False


def test_reading_device_data_still_allows_cloud_with_only_local_reply_history(db, sandbox):
    (sandbox / "Documents" / "resume.pdf").write_bytes(b"%PDF")
    seen = {}
    def cloud(messages, _info):
        seen["history"] = json.dumps([str(m) for m in messages])
        return ModelResponse(parts=[TextPart("Cloud reply")])
    pool = _pool({"local": _tool_then_answer("find_files", {"query": "resume"}, "Found resume.pdf"),
                  "groq": cloud, "gemini": cloud})
    a = Assistant(db, Router(), pool)
    cid = db.new_conversation()
    a.respond(cid, "find my resume")
    assert db.is_local_only(cid)
    assert a.respond(cid, "explain recursion").route == "general"
    assert "Found resume.pdf" in seen["history"]
    assert "find my resume" not in seen["history"]
    assert str(sandbox) not in seen["history"]

    history = build_history(db.messages(cid), for_cloud=False)
    assert any("resume.pdf" in str(m) for m in history)


def test_rejected_approval_is_logged_and_nothing_created(db, sandbox):
    pool = _pool({"local": _tool_then_answer("create_folder", {"path": "Documents/New"}, "ok")})
    a = Assistant(db, Router(), pool)
    cid = db.new_conversation()
    a.respond(cid, "create a folder called New in Documents", approve=lambda req: False)
    assert not (sandbox / "Documents" / "New").exists()
    log = db.action_logs()[0]
    assert log["tool"] == "create_folder" and log["status"] == "rejected" and log["approval"] == "rejected"


def test_web_fallback_agent_only_has_web_tools(db):
    seen = {}

    def groq(messages, info):
        seen["tools"] = sorted(t.name for t in info.function_tools)
        return ModelResponse(parts=[TextPart("news")])

    pool = _pool({"groq": groq, "gemini": None, "local": None})
    pool.config["tasks"]["web"] = ["groq", "local"]
    Assistant(db, Router(), pool).respond(db.new_conversation(), "latest news about AI")
    assert seen["tools"] == ["read_web_page", "search_web"]


def test_missing_keys_go_straight_to_local(db):
    pool = _pool({"local": _text("local answer")}, keys=False)
    reply = Assistant(db, Router(), pool).respond(db.new_conversation(), "explain recursion")
    assert reply.provider.startswith("Local") and "no API key" in reply.note


def test_cooldowns():
    pool = ProviderPool(config.load_providers(), get_key=lambda _k: "key", clock=lambda: 1000.0)
    pool.report_failure("groq", E.ModelRateLimitError("m", "slow down", retry_after=20))
    assert pool.status["groq"].cooldown_until == 1020.0
    pool.report_failure("gemini", E.ModelAuthenticationError("m", "bad key"))
    assert "rejected" in pool.availability("gemini")[1]
    pool.report_failure("groq", ValueError("odd response"))
    assert pool.status["groq"].cooldown_until == 1020.0


def test_gemini_quota_resets_at_midnight_pacific():
    noon_utc = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)
    assert abs(seconds_until_midnight_pacific(noon_utc) - 12 * 3600) < 10


def test_local_model_request_enables_thinking():
    from openai import AsyncOpenAI
    from pydantic_ai import Agent
    from pydantic_ai.models.ollama import OllamaModel
    from pydantic_ai.providers.ollama import OllamaProvider
    _model, settings = ProviderPool(config.load_providers()).build("local")
    body = {}

    def handler(request):
        body.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": "hi"}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    client = AsyncOpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    Agent(OllamaModel("qwen3:1.7b", provider=OllamaProvider(openai_client=client)), model_settings=settings).run_sync("hi")
    assert body["reasoning_effort"] == "medium"


def test_history_budget_keeps_newest_and_starts_with_user():
    rows = []
    for i in range(30):
        rows.append({"role": "user", "content": f"q{i} " + "x" * 400, "route": "general"})
        rows.append({"role": "assistant", "content": f"a{i} " + "y" * 400, "route": "general"})
    history = build_history(rows, for_cloud=True, budget=2000)
    assert sum(len(str(m)) for m in history) < 4000
    assert "q29" in str(history[-2]) and type(history[0]).__name__ == "ModelRequest"


def test_email_request_end_to_end_uses_contact_and_approval(db, monkeypatch):
    from security.approvals import ApprovalRequest
    from tests.test_email_keyboard import FakeSMTP
    FakeSMTP.sent = []
    monkeypatch.setattr("tools.email.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("core.secrets.get_key", lambda k: "app-pass")
    db.set("contacts", [{"name": "Rahul", "email": "rahul@example.com"}])
    db.set("gmail_address", "me@gmail.com")
    db.set("email_mode", "send")

    def local(messages, info):
        returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not returns:
            return ModelResponse(parts=[ToolCallPart("find_contact", {"name": "Rahul"})])
        if len(returns) == 1:
            return ModelResponse(parts=[ToolCallPart("send_email", {"to": "rahul@example.com", "subject": "Notes",
                                                                    "body": "Hi Rahul, please share the notes."})])
        return ModelResponse(parts=[TextPart("Sent.")])

    seen: list[ApprovalRequest] = []
    a = Assistant(db, Router(), _pool({"local": local}))
    cid = db.new_conversation()
    reply = a.respond(cid, "write a mail to Rahul asking for the notes and send it",
                      approve=lambda req: seen.append(req) or True)
    assert reply.route == "device" and seen[0].tool == "send_email"
    assert FakeSMTP.sent and FakeSMTP.sent[0]["To"] == "rahul@example.com"
    assert db.is_local_only(cid)
