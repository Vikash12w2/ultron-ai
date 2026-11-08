import pytest

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_window_builds_and_renders_provider_labels(app, db):
    from gui.main_window import MainWindow
    db.set("smart_routing", False)
    w = MainWindow(db=db)
    db.add_message(w.cid, "user", "hi", route="general")
    db.add_message(w.cid, "assistant", "**Hello** [docs](https://example.com)", route="general",
                   provider="Groq · openai/gpt-oss-120b")
    w.render()
    html = w.view.toHtml()
    assert "Cloud · Groq" in html and "Hello" in html
    w.timer.stop()
    w.close()


def test_approval_dialog_shows_full_preview(app):
    from gui.dialogs import ApprovalDialog
    from security.approvals import ApprovalRequest
    from PySide6.QtWidgets import QPlainTextEdit
    d = ApprovalDialog(ApprovalRequest("create_text_file", "Create a text file", {"Location": "C:\\x.txt"},
                                       "make a note", preview="line\n" * 300))
    assert d.findChild(QPlainTextEdit).toPlainText().count("line") == 300


def test_due_voice_message_is_prepared_and_announced(app, db, monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    from gui.main_window import MainWindow
    db.set("smart_routing", False)
    w = MainWindow(db=db)
    note = tmp_path / "n.ogg"
    note.write_bytes(b"x")
    w.assistant.scheduler.add("whatsapp_voice", "Voice message for Rahul",
                              {"name": "Rahul", "phone": "919876543210", "file": str(note)},
                              datetime.now() - timedelta(minutes=1), w.cid)
    delivered = []
    monkeypatch.setattr("tools.whatsapp.WhatsAppTools.deliver",
                        lambda self, n, p, f: delivered.append((n, p)) or {"next": "Press Ctrl+V in the chat, then Send."})
    w.run_due_tasks()
    assert delivered == [("Rahul", "919876543210")]
    assert "voice message for" in w.view.toPlainText() and w.assistant.scheduler.pending() == []
    w.timer.stop()
    w.schedule_timer.stop()
    w.close()
