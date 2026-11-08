from urllib.parse import parse_qs, urlparse

import pytest

from core.router import Route, Router
from security.approvals import ApprovalGate, ApprovalRejected
from tools.email import EmailTools, find_contact
from tools.keyboard import KeyboardTools, parse_combo


class FakeBackend:
    def __init__(self, lose_focus_after=None):
        self.typed, self.combos, self.focused = [], [], []
        self.calls = 0
        self.lose_focus_after = lose_focus_after

    def focus(self, process, title=None):
        self.focused.append((process, title))

    def is_foreground(self, process, title=None):
        self.calls += 1
        return self.lose_focus_after is None or self.calls <= self.lose_focus_after

    def type(self, text):
        self.typed.append(text)

    def combo(self, codes):
        self.combos.append(codes)


def _kb(answer=None, backend=None):
    asked = []

    def ask(req):
        asked.append(req)
        if callable(answer):
            return answer(req)
        return bool(answer)

    return KeyboardTools(ApprovalGate(ask), backend=backend or FakeBackend()), asked



def test_plain_typing_needs_no_approval():
    kb, asked = _kb(False)
    assert kb.type_text("notepad", "hello world")["status"] == "typed"
    assert asked == [] and "".join(kb.backend.typed) == "hello world"


def test_line_breaks_count_as_enter_and_need_approval():
    kb, asked = _kb(False)
    with pytest.raises(ApprovalRejected):
        kb.type_text("chrome", "line one\nline two")
    assert kb.backend.typed == []


def test_line_breaks_are_fine_in_editors_and_vscode_cursor_moves_to_editor_first():
    kb, asked = _kb(False)
    kb.type_text("vscode", "def f():\n    return 1\n")
    kb.type_text("notepad", "line one\nline two")
    assert asked == []
    assert kb.backend.combos[0] == [0x11, ord("1")]


def test_user_can_edit_text_before_it_is_typed():
    def approve_with_edit(req):
        req.edits["Preview"] = "edited\ntext"
        return True
    kb, _ = _kb(approve_with_edit)
    kb.type_text("chrome", "original\ntext")
    assert "".join(kb.backend.typed) == "edited\ntext"


def test_browser_typing_after_reading_files_needs_approval():
    kb, asked = _kb(False)
    kb.type_text("chrome", "public text")
    with pytest.raises(ApprovalRejected):
        kb.type_text("chrome", "secret", device_data_in_chat=True)
    assert len(asked) == 1


def test_every_key_press_needs_approval_and_win_key_is_blocked():
    kb, asked = _kb(False)
    with pytest.raises(ApprovalRejected):
        kb.press_keys("chrome", "ctrl+enter")
    assert kb.backend.combos == [] and asked[0].details["Keys"] == "ctrl+enter"
    with pytest.raises(ValueError):
        parse_combo("win+r")
    kb, _ = _kb(True)
    kb.press_keys("chrome", "ctrl+enter")
    assert kb.backend.combos == [[0x11, 0x0D]]


def test_typing_stops_when_focus_is_lost():
    kb, _ = _kb(True, FakeBackend(lose_focus_after=1))
    result = kb.type_text("notepad", "x" * 100)
    assert result["status"] == "stopped" and result["typed_chars"] < 100


def test_store_apps_are_focused_by_window_title():
    kb, _ = _kb(True)
    kb.type_text("calculator", "12+3")
    assert kb.backend.focused[0] == ("CalculatorApp.exe", "Calculator")



class FakeSMTP:
    sent = []

    def __init__(self, host, port, **_kw):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context):
        pass

    def login(self, user, password):
        assert password == "app-pass"

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def _mail(answer, address="me@gmail.com"):
    opened = []
    tools = EmailTools(ApprovalGate(answer), open_url=lambda url: opened.append(url) or {"status": "launched"},
                       gmail_address=address, get_key=lambda _k: "app-pass", smtp_factory=FakeSMTP)
    return tools, opened


def test_compose_opens_prefilled_draft_and_sends_nothing():
    FakeSMTP.sent = []
    tools, opened = _mail(lambda r: False)
    result = tools.compose_email("rahul@example.com", "Notes", "Hi Rahul, can you share the notes?")
    q = parse_qs(urlparse(opened[0]).query)
    assert q["to"] == ["rahul@example.com"] and q["su"] == ["Notes"] and q["tf"] == ["cm"]
    assert result["status"] == "draft_opened" and FakeSMTP.sent == []


def test_send_uses_exactly_the_approved_edited_version():
    FakeSMTP.sent = []

    def approve(req):
        req.edits.update({"To": "prof@uni.edu", "Subject": "Extension request", "Preview": "Edited body"})
        return True
    tools, _ = _mail(approve)
    tools.send_email("wrong@uni.edu", "subj", "model body")
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "prof@uni.edu" and msg["Subject"] == "Extension request"
    assert msg.get_content().strip() == "Edited body"


def test_rejected_or_unconfigured_email_is_not_sent():
    FakeSMTP.sent = []
    tools, _ = _mail(lambda r: False)
    with pytest.raises(ApprovalRejected):
        tools.send_email("a@b.com", "s", "b")
    tools, _ = _mail(lambda r: True, address="")
    with pytest.raises(RuntimeError):
        tools.send_email("a@b.com", "s", "b")
    with pytest.raises(ValueError):
        _mail(lambda r: True)[0].compose_email("not an address", "s", "b")
    assert FakeSMTP.sent == []


def test_contacts_lookup():
    contacts = [{"name": "Rahul Sharma", "email": "rahul@example.com"}]
    assert find_contact(contacts, "rahul")["matches"][0]["email"] == "rahul@example.com"
    assert find_contact(contacts, "priya")["matches"] == []


@pytest.mark.parametrize("text", ["write a mail to Rahul asking for the DSA notes", "send it",
                                  "draft an email for my professor", "type hello in notepad",
                                  "press ctrl+s in vs code"])
def test_email_and_keyboard_requests_stay_local(text):
    assert Router().decide(text).route is Route.DEVICE
