from datetime import datetime

import numpy as np
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart

from core.router import Route, Router
from core.scheduler import Scheduler, parse_when
from core.writer import Writer, scrub
from tools.whatsapp import WhatsAppTools, normalize_phone, resolve_recipient

NOW = datetime(2026, 11, 8, 22, 0)
CONTACTS = [{"name": "Rahul Sharma", "email": "rahul@example.com", "phone": "98765 43210"},
            {"name": "Rahul Verma", "email": "", "phone": "+91 91234 56789"},
            {"name": "Priya", "email": "priya@example.com", "phone": ""}]


def tone(text="", _voice=""):
    return (0.1 * np.sin(np.linspace(0, 200, 22050))).astype("float32"), 22050


@pytest.mark.parametrize("text,expected", [
    ("in 30 minutes", datetime(2026, 11, 8, 22, 30)), ("in 2 hours", datetime(2026, 11, 9, 0, 0)),
    ("in half an hour", datetime(2026, 11, 8, 22, 30)), ("at 11 pm", datetime(2026, 11, 8, 23, 0)),
    ("at 6 pm", datetime(2026, 11, 9, 18, 0)),
    ("tomorrow at 9:30 am", datetime(2026, 11, 9, 9, 30)), ("tomorrow morning", datetime(2026, 11, 9, 9, 0)),
    ("tonight at 11", datetime(2026, 11, 8, 23, 0)), ("23:15", datetime(2026, 11, 8, 23, 15)),
    ("2026-11-10 18:00", datetime(2026, 11, 10, 18, 0)),
])
def test_parse_when(text, expected):
    assert parse_when(text, NOW) == expected


def test_parse_when_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_when("whenever you like", NOW)


def test_phone_numbers_and_contacts():
    assert normalize_phone("98765 43210") == "919876543210"
    assert normalize_phone("+1 (415) 555-0100") == "14155550100"
    assert resolve_recipient("rahul sharma", CONTACTS) == ("Rahul Sharma", "919876543210")
    assert resolve_recipient("+91 98765 43210", CONTACTS)[1] == "919876543210"
    with pytest.raises(ValueError, match="Several contacts"):
        resolve_recipient("rahul", CONTACTS)
    with pytest.raises(ValueError, match="WhatsApp number"):
        resolve_recipient("priya", CONTACTS)


def _wa(tmp_path, **kw):
    opened, copied = [], []
    tools = WhatsAppTools(tmp_path / "notes", CONTACTS, synthesize=kw.pop("synthesize", tone), voice_path="v.onnx",
                          opener=lambda phone: opened.append(phone) or "WhatsApp Desktop",
                          copy_files=lambda paths: copied.extend(paths), **kw)
    return tools, opened, copied


def test_voice_message_now_makes_ogg_opens_chat_and_copies(tmp_path):
    tools, opened, copied = _wa(tmp_path)
    result = tools.voice_message("Rahul Sharma", "I'll be 15 minutes late")
    import soundfile as sf
    info = sf.info(copied[0])
    assert result["status"] == "ready_to_send" and opened == ["919876543210"]
    assert info.format == "OGG" and info.subtype == "OPUS" and "Ctrl+V" in result["next"]


def test_cloud_writer_text_is_what_gets_spoken(tmp_path):
    spoken = []
    tools, _, _ = _wa(tmp_path, synthesize=lambda text, v: spoken.append(text) or tone())
    tools.writer = lambda kind: {"text": "Hi Rahul, this is a message from Vikash. He'll be late."}
    tools.voice_message("Rahul Sharma", "late")
    assert spoken == ["Hi Rahul, this is a message from Vikash. He'll be late."]


def test_own_voice_uses_recording_and_cancel_stops(tmp_path):
    tools, _, copied = _wa(tmp_path, record=lambda prompt: tone())
    tools.voice_message("Rahul Sharma", own_voice=True)
    assert copied
    tools, _, _ = _wa(tmp_path, record=lambda prompt: None)
    with pytest.raises(RuntimeError, match="cancelled"):
        tools.voice_message("Rahul Sharma", own_voice=True)


def test_scheduled_voice_message_waits_until_due(tmp_path, db):
    sched = Scheduler(db)
    tools, opened, copied = _wa(tmp_path, scheduler=sched)
    result = tools.voice_message("Rahul Sharma", "Happy birthday!", when="tomorrow at 9 am")
    assert result["status"] == "scheduled" and opened == [] and copied == []
    task = sched.pending()[0]
    assert sched.due(datetime.fromisoformat(task["run_at"])) and not sched.due(NOW.replace(year=2025))
    assert sched.cancel(task["id"]) and sched.pending() == []



class FakePool:
    def __init__(self, answers):
        self.answers, self.prompts = answers, []

    def chain(self, _task):
        return ["groq", "local"]

    def availability(self, name):
        return True, ""

    def label(self, name):
        return name.title()

    def model_name(self, name):
        return name

    def report_failure(self, name, exc):
        return str(exc)

    def build(self, name):
        from pydantic_ai.models.function import FunctionModel

        def fn(messages, info):
            self.prompts.append((name, str(messages)))
            return ModelResponse(parts=[TextPart(self.answers[name])])
        return FunctionModel(fn, model_name=name), {}


def test_writer_scrubs_numbers_and_emails_and_parses_email():
    assert scrub("mail rahul@example.com or call +91 98765 43210") == "mail [email] or call [number]"
    pool = FakePool({"groq": "Subject: Notes\n\nHi Rahul,\nPlease share the notes.\nVikash", "local": "x"})
    out = Writer(pool, "email rahul@example.com (98765 43210) asking for DSA notes", user_name="Vikash")("email")
    sent = pool.prompts[0][1]
    assert "rahul@example.com" not in sent and "98765" not in sent and "DSA notes" in sent
    assert out["subject"] == "Notes" and out["body"].startswith("Hi Rahul")


def test_writer_stays_local_when_cloud_not_allowed():
    pool = FakePool({"groq": "cloud", "local": "local text"})
    assert Writer(pool, "tell rahul I'm late", allow_cloud=False)("voice_message")["text"] == "local text"
    assert [p[0] for p in pool.prompts] == ["local"]


def test_assistant_voice_message_uses_cloud_writer_but_not_contacts(db, tmp_path, monkeypatch):
    from core.assistant import Assistant
    from tests.test_assistant import _pool
    db.set("contacts", CONTACTS)
    db.set("user_name", "Vikash")
    seen = {}

    def local(messages, info):
        if any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            return ModelResponse(parts=[TextPart("Ready: press Ctrl+V and Send.")])
        return ModelResponse(parts=[ToolCallPart("voice_message", {"to": "Rahul Sharma", "message": "late"})])

    def groq(messages, info):
        seen["prompt"] = str(messages)
        return ModelResponse(parts=[TextPart("Hi Rahul, Vikash says he'll be fifteen minutes late.")])

    spoken = []
    a = Assistant(db, Router(), _pool({"local": local, "groq": groq, "gemini": groq}))
    a.whatsapp_options = {"opener": lambda phone: "app", "copy_files": lambda paths: None,
                          "synthesize": lambda text, v: spoken.append(text) or tone()}
    monkeypatch.setattr("core.assistant.VOICE_NOTES", tmp_path / "notes")
    reply = a.respond(db.new_conversation(), "send Rahul Sharma a voice message saying I'll be 15 minutes late")
    assert reply.route == "device" and spoken == ["Hi Rahul, Vikash says he'll be fifteen minutes late."]
    assert "98765" not in seen["prompt"] and "rahul@example.com" not in seen["prompt"]


@pytest.mark.parametrize("text,route", [
    ("send Rahul a voice message saying I'll be late", Route.DEVICE),
    ("whatsapp priya at 6 pm that the meeting moved", Route.DEVICE),
    ("tell Rahul that I'm on my way", Route.DEVICE),
    ("what are my scheduled messages", Route.DEVICE),
    ("tell me that joke again", Route.CHAT),
])
def test_routing_for_messages(text, route):
    assert Router().decide(text).route is route


def _email_run(db, sandbox, calls, monkeypatch):
    from core.assistant import Assistant
    from tests.test_assistant import _pool
    (sandbox / "Documents" / "report.txt").write_text("SECRET quarterly numbers")
    opened = []

    def local(messages, info):
        n = sum(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
        step = calls[n] if n < len(calls) else None
        if step is None:
            return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(parts=[ToolCallPart(*step)])

    cloud_prompts = []

    def groq(messages, info):
        cloud_prompts.append(str(messages))
        return ModelResponse(parts=[TextPart("Subject: Notes request\n\nHi Rahul,\nCould you share the notes?\nVikash")])

    a = Assistant(db, Router(), _pool({"local": local, "groq": groq, "gemini": groq}))
    monkeypatch.setattr("tools.apps.AppTools.open_website",
                        lambda self, url, browser="default": opened.append(url) or {"status": "launched"})
    a.respond(db.new_conversation(), "email rahul@example.com asking for the notes")
    return opened, cloud_prompts


def test_email_draft_is_written_by_cloud(db, sandbox, monkeypatch):
    opened, prompts = _email_run(db, sandbox, [("compose_email", {"to": "rahul@example.com", "subject": "x",
                                                                  "body": "bad local text"})], monkeypatch)
    assert "Could%20you%20share%20the%20notes" in opened[0] and "rahul%40example.com" in opened[0]
    assert prompts and "rahul@example.com" not in prompts[0]


def test_email_after_reading_a_file_is_written_locally(db, sandbox, monkeypatch):
    opened, prompts = _email_run(db, sandbox, [("read_file", {"path": "Documents/report.txt"}),
                                               ("compose_email", {"to": "rahul@example.com", "subject": "Report",
                                                                  "body": "SECRET quarterly numbers"})], monkeypatch)
    assert prompts == []
    assert "SECRET" in opened[0]
