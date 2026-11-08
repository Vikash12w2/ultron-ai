from __future__ import annotations

import html
import json
import re

from PySide6.QtCore import QEvent, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSystemTrayIcon,
                               QMenu, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from config import APP_NAME, ASSETS, DATABASE, LOCAL_MODEL, MODEL_CACHE, OLLAMA_URL, VOICE_NOTES, load_providers
from core.assistant import Assistant
from core.providers import ProviderPool
from core.router import Router
from gui.dialogs import ActionLogDialog, ApprovalDialog, RecordDialog, SettingsDialog
from gui.theme import C, STYLE, icon
from gui.workers import ChatWorker, FunctionWorker, StatusWorker

SUGGESTIONS = ["How much RAM is free?", "Open VS Code", "Latest AI news", "Explain CUDA shared memory",
               "Send a voice message", "What's scheduled?"]
HOTKEY_VOICE, HOTKEY_SHOW = 1, 2
from memory.database import Database


def markdown_html(text: str) -> str:
    doc = QTextDocument()
    doc.setMarkdown(text)
    body = re.search(r"<body[^>]*>(.*)</body>", doc.toHtml(), re.S)
    return body.group(1) if body else html.escape(text)


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None, providers_config: dict | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(1000, 640)
        if (ASSETS / "ultron.ico").exists():
            self.setWindowIcon(QIcon(str(ASSETS / "ultron.ico")))
        self.db = db or Database(DATABASE)
        self.providers_config = providers_config or load_providers()
        self.pool = ProviderPool(self.providers_config)
        self.router = Router()
        self.assistant = Assistant(self.db, self.router, self.pool)
        self.threads = QThreadPool(self)
        self.threads.setMaxThreadCount(4)
        self._keep: set = set()
        self.busy_cid: str | None = None
        self.unread: set[str] = set()
        self.status_running = False
        self.recorder = None
        self.stt = None
        self.speak_next_reply = False
        self.apply_settings()

        convs = self.db.conversations()
        self.cid = convs[0]["id"] if convs else self.db.new_conversation()
        self.setStyleSheet(STYLE)
        self._build()
        self.refresh_chats()
        self.render()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)
        self.timer.start(5000)
        self.poll_status()
        QTimer.singleShot(300, self.load_router_model)
        self.voice_window = None
        self._reply_callback = None
        self._quitting = False
        self._told_background = False
        self.tray = QSystemTrayIcon(self.windowIcon(), self) if QSystemTrayIcon.isSystemTrayAvailable() else None
        if self.tray:
            self.tray.setToolTip("ULTRON · running")
            menu = QMenu()
            for label, slot in (("Open ULTRON", self.show_window), ("Voice mode  (Ctrl+Alt+Space)", self.open_voice_mode),
                                ("Quit ULTRON", self.quit_app)):
                action = QAction(label, menu)
                action.triggered.connect(slot)
                menu.addAction(action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_window()
                                        if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()
        self.register_hotkeys()
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.run_due_tasks)
        self.schedule_timer.start(20000)
        QTimer.singleShot(1500, self.run_due_tasks)


    def apply_settings(self):
        self.pool.local_model = self.db.get("local_model", LOCAL_MODEL) or LOCAL_MODEL
        self.pool.ollama_url = self.db.get("ollama_url", OLLAMA_URL) or OLLAMA_URL
        self.pool.model_overrides = {k: v for k, v in (("groq", self.db.get("groq_model", "")),
                                                       ("gemini", self.db.get("gemini_model", ""))) if v}
        self.low_memory = bool(self.db.get("low_memory", False))


    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame(objectName="header")
        header.setFixedHeight(56)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 6, 18, 6)
        logo = QLabel()
        if (ASSETS / "ultron.svg").exists():
            logo.setPixmap(QIcon(str(ASSETS / "ultron.svg")).pixmap(28, 28))
        hl.addWidget(logo)
        name = QLabel("ULTRON")
        name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        name.setStyleSheet("letter-spacing: 3px;")
        hl.addWidget(name)
        self.pill = QLabel("Checking local AI…")
        self.pill.setStyleSheet(self._pill_style(C["blue"]))
        hl.addWidget(self.pill)
        hl.addStretch()
        voice_btn = QPushButton(" Voice mode", objectName="primary")
        voice_btn.setIcon(icon("mic", "#FFFFFF"))
        voice_btn.setToolTip("Talk hands-free (Ctrl+Alt+Space from anywhere)")
        voice_btn.clicked.connect(self.open_voice_mode)
        hl.addWidget(voice_btn)
        log_btn = QPushButton(" Action log")
        log_btn.setIcon(icon("action-log"))
        log_btn.clicked.connect(lambda: ActionLogDialog(self.db, self).exec())
        settings_btn = QPushButton(" Settings")
        settings_btn.setIcon(icon("settings"))
        settings_btn.clicked.connect(self.open_settings)
        hl.addWidget(log_btn)
        hl.addWidget(settings_btn)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)


        side = QFrame(objectName="sidebar")
        side.setFixedWidth(260)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 14, 12, 12)
        new_btn = QPushButton(" New chat", objectName="newchat")
        new_btn.setIcon(icon("new-chat", "#FFD9DA"))
        new_btn.clicked.connect(self.new_chat)
        sl.addWidget(new_btn)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search chats")
        self.search.textChanged.connect(self.refresh_chats)
        sl.addWidget(self.search)
        lab = QLabel("CHATS", objectName="section")
        sl.addWidget(lab)
        self.chat_list = QListWidget()
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.chat_list.itemClicked.connect(lambda item: self.open_chat(item.data(Qt.ItemDataRole.UserRole)))
        sl.addWidget(self.chat_list, 1)
        delete = QPushButton(" Delete this chat")
        delete.setIcon(icon("delete", C["muted"]))
        delete.clicked.connect(self.delete_chat)
        sl.addWidget(delete)
        body.addWidget(side)


        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(28, 14, 28, 14)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.document().setDefaultStyleSheet(f"a {{ color: #7DBBFF; }} code {{ color: {C['amber']}; }}")
        cl.addWidget(self.view, 1)
        self.privacy = QLabel()
        self.privacy.setObjectName("muted")
        cl.addWidget(self.privacy)
        self.chips = QWidget()
        from PySide6.QtWidgets import QGridLayout
        chip_grid = QGridLayout(self.chips)
        chip_grid.setContentsMargins(0, 0, 0, 6)
        chip_grid.setHorizontalSpacing(6)
        chip_grid.setVerticalSpacing(6)
        for i, text in enumerate(SUGGESTIONS):
            chip = QPushButton(text)
            chip.setStyleSheet(f"background: {C['card']}; border: 1px solid {C['line']}; border-radius: 14px; "
                               f"padding: 6px 12px; color: {C['muted']}; font-size: 12px;")
            chip.setToolTip(text)
            chip.clicked.connect(lambda _c=False, t=text: (self.input.setPlainText(t), self.input.setFocus()))
            chip_grid.addWidget(chip, i // 3, i % 3)
        cl.addWidget(self.chips)
        composer = QFrame(objectName="card")
        cr = QHBoxLayout(composer)
        cr.setContentsMargins(8, 8, 8, 8)
        self.input = QTextEdit()
        self.input.setPlaceholderText("Message ULTRON…  (Enter to send, Shift+Enter for a new line, /local to keep it on this PC)")
        self.input.setFixedHeight(64)
        self.input.setStyleSheet("border: 0; background: transparent;")
        self.input.installEventFilter(self)
        cr.addWidget(self.input, 1)
        self.mic = QPushButton()
        self.mic.setIcon(icon("mic"))
        self.mic.setFixedSize(44, 44)
        self.mic.setToolTip("Hold to talk (speech is transcribed on this PC)")
        self.mic.setAccessibleName("Hold to talk")
        self.mic.pressed.connect(self.start_recording)
        self.mic.released.connect(self.stop_recording)
        cr.addWidget(self.mic)
        self.send_btn = QPushButton(objectName="primary")
        self.send_btn.setIcon(icon("send", "#FFFFFF"))
        self.send_btn.setFixedSize(44, 44)
        self.send_btn.setAccessibleName("Send")
        self.send_btn.clicked.connect(self.send)
        cr.addWidget(self.send_btn)
        cl.addWidget(composer)
        below = QHBoxLayout()
        self.task_line = QLabel("Ready")
        self.task_line.setObjectName("muted")
        below.addWidget(self.task_line, 1)
        self.cloud_box = QCheckBox("Allow cloud AI for general && web questions")
        self.cloud_box.setChecked(bool(self.db.get("cloud_enabled", True)))
        self.cloud_box.toggled.connect(lambda on: (self.db.set("cloud_enabled", on), self.update_privacy()))
        below.addWidget(self.cloud_box)
        cl.addLayout(below)
        body.addWidget(center, 1)


        right = QFrame(objectName="right")
        right.setFixedWidth(280)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(10)
        rl.addWidget(QLabel("SYSTEM", objectName="section"))
        self.cpu_value, self.cpu_bar = self._metric(rl, "CPU")
        self.ram_value, self.ram_bar = self._metric(rl, "RAM")
        rl.addWidget(QLabel("AI", objectName="section"))
        ai = QFrame(objectName="card")
        al = QVBoxLayout(ai)
        al.setContentsMargins(12, 10, 12, 10)
        self.ai_label = QLabel("…")
        self.ai_label.setWordWrap(True)
        self.ai_label.setTextFormat(Qt.TextFormat.RichText)
        al.addWidget(self.ai_label)
        rl.addWidget(ai)
        rl.addWidget(QLabel("TASK", objectName="section"))
        task = QFrame(objectName="card")
        tl = QVBoxLayout(task)
        tl.setContentsMargins(12, 10, 12, 10)
        self.task_card = QLabel("Waiting for your next command")
        self.task_card.setWordWrap(True)
        tl.addWidget(self.task_card)
        rl.addWidget(task)
        rl.addWidget(QLabel("SCHEDULED", objectName="section"))
        sched = QFrame(objectName="card")
        sc = QVBoxLayout(sched)
        sc.setContentsMargins(12, 10, 12, 10)
        self.schedule_label = QLabel("Nothing scheduled")
        self.schedule_label.setWordWrap(True)
        self.schedule_label.setObjectName("muted")
        sc.addWidget(self.schedule_label)
        rl.addWidget(sched)
        rl.addStretch()
        body.addWidget(right)
        self.routing_state = "Keyword routing (smart routing loading…)" if self.db.get("smart_routing", True) \
            else "Keyword routing"
        self.ollama_state = "checking…"
        self.update_ai_card()

    def _metric(self, layout, title):
        card = QFrame(objectName="card")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        row = QHBoxLayout()
        row.addWidget(QLabel(title))
        row.addStretch()
        value = QLabel("—")
        row.addWidget(value)
        v.addLayout(row)
        bar = QProgressBar()
        bar.setTextVisible(False)
        v.addWidget(bar)
        layout.addWidget(card)
        return value, bar

    @staticmethod
    def _pill_style(color):
        return (f"color: {color}; border: 1px solid {color}; border-radius: 12px; padding: 4px 10px; "
                "font-size: 12px; margin-left: 10px;")


    def refresh_chats(self):
        text = self.search.text().strip() if hasattr(self, "search") else ""
        convs = self.db.search_conversations(text) if text else self.db.conversations()
        self.chat_list.clear()
        for c in convs:
            title = ("● " if c["id"] in self.unread else "") + c["title"]
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            if c["local_only"]:
                item.setToolTip("This chat used device data. Cloud requests may include ULTRON's local replies, "
                                "but not your device prompts or raw tool results. Local replies may contain "
                                "summaries of device information.")
            self.chat_list.addItem(item)
            if c["id"] == self.cid:
                self.chat_list.setCurrentItem(item)

    def open_chat(self, cid):
        self.cid = cid
        self.unread.discard(cid)
        self.refresh_chats()
        self.render()

    def new_chat(self):
        self.cid = self.db.new_conversation()
        self.refresh_chats()
        self.render()
        self.input.setFocus()

    def delete_chat(self):
        if self.busy_cid == self.cid:
            return
        if QMessageBox.question(self, "Delete chat", "Delete this chat and its messages?") != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_conversation(self.cid)
        convs = self.db.conversations()
        self.cid = convs[0]["id"] if convs else self.db.new_conversation()
        self.refresh_chats()
        self.render()


    def render(self, pending: str | None = None):
        parts = ["<div style='font-size:14px'>"]
        rows = [r for r in self.db.messages(self.cid) if r["role"] in ("user", "assistant")]
        if not rows and not pending:
            parts.append(f"<p style='color:{C['muted']}; margin-top:40px' align='center'>Good to see you. "
                         "What would you like me to do?</p>")
        for r in rows:
            parts.append(self._bubble(r["role"], r["content"], r.get("provider", ""), r.get("route", "")))
        if pending:
            parts.append(self._bubble("user", pending, "", ""))
            parts.append(f"<p style='color:{C['dim']}'>ULTRON is working…</p>")
        parts.append("</div>")
        self.view.setHtml("".join(parts))
        if hasattr(self, "chips"):
            self.chips.setVisible(not rows and not pending)
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self.update_privacy()

    def _bubble(self, role, content, provider, route):
        if role == "user":
            text = html.escape(content).replace("\n", "<br>")
            return ("<table width='100%' cellspacing='0' cellpadding='0' style='margin:10px 0'><tr>"
                    "<td width='22%'></td>"
                    f"<td bgcolor='{C['user']}' style='padding:10px 14px'>{text}</td></tr></table>")
        if provider.startswith("Local"):
            tag = f"<span style='color:{C['muted']}'>{html.escape(provider)} · stayed on this PC</span>"
        elif provider and provider != "None":
            tag = f"<span style='color:{C['blue']}'>Cloud · {html.escape(provider)}</span>"
        else:
            tag = f"<span style='color:{C['orange']}'>No provider answered</span>"
        return (f"<p style='margin:14px 0 2px; font-size:12px'><b style='color:{C['accent']}'>ULTRON</b>"
                f"&nbsp;&nbsp;{tag}</p><div style='color:{C['text']}'>{markdown_html(content)}</div>")

    def update_privacy(self):
        if not self.cloud_box.isChecked():
            text = "Cloud AI is off. Everything stays on this PC."
        elif self.db.is_local_only(self.cid):
            text = ("This chat used device data. Local requests and raw tool results stay on this PC; later cloud "
                    "requests may include the local model's final reply, which may summarize device information.")
        else:
            text = ("Device prompts and raw tool results stay on this PC. General and web questions may use Groq or "
                    "Gemini and can include the local model's earlier final replies.")
        self.privacy.setText(text)


    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send()
            return True
        return super().eventFilter(obj, event)

    def send(self):
        text = self.input.toPlainText().strip()
        if text and self.submit(text):
            self.input.clear()

    def submit(self, text: str, on_reply=None) -> bool:
        """Runs a message through ULTRON. on_reply(text) is called with the answer (used by voice mode)."""
        if self.busy_cid:
            self.set_task("Still working on the previous request…")
            if on_reply:
                on_reply("I'm still working on the previous request.")
            return False
        self._reply_callback = on_reply
        self.busy_cid = self.cid
        self.send_btn.setEnabled(False)
        self.render(pending=text)
        self.set_task("Thinking…")
        worker = ChatWorker(self.assistant, self.cid, text)
        worker.signals.status.connect(lambda cid, m: self.set_task(m) if cid == self.busy_cid else None)
        worker.signals.approval.connect(self.ask_approval)
        worker.signals.record.connect(self.ask_recording)
        worker.signals.reply.connect(self.on_reply)
        worker.signals.error.connect(self.on_error)
        worker.signals.done.connect(lambda _cid, w=worker: self._finish(w))
        self._keep.add(worker)
        self.threads.start(worker)
        return True

    def ask_approval(self, request, handshake):
        event, holder = handshake
        try:
            holder["ok"] = ApprovalDialog(request, self).exec() == QDialog.DialogCode.Accepted
        finally:
            event.set()

    def ask_recording(self, prompt, handshake):
        event, holder = handshake
        try:
            dialog = RecordDialog(prompt, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                holder["audio"] = dialog.result_audio
        finally:
            event.set()


    def run_due_tasks(self):
        from datetime import datetime

        from tools.whatsapp import WhatsAppTools
        scheduler = self.assistant.scheduler
        for task in scheduler.due():
            payload = json.loads(task["payload"])
            due = datetime.fromisoformat(task["run_at"])
            late = (datetime.now() - due).total_seconds() > 180
            try:
                if task["kind"] != "whatsapp_voice":
                    raise ValueError(f"Unknown task type {task['kind']}")
                result = WhatsAppTools(VOICE_NOTES, []).deliver(payload["name"], payload["phone"], payload["file"])
                text = (f"Reminder: {'(was due at ' + due.strftime('%I:%M %p') + ') ' if late else ''}"
                        f"Your voice message for **{payload['name']}** is ready. WhatsApp is open on their chat: "
                        f"{result['next']}")
                scheduler.finish(task["id"], "done")
            except Exception as exc:
                text = f"Reminder: couldn't prepare the scheduled voice message for {payload.get('name', '?')}: {exc}"
                scheduler.finish(task["id"], "failed")
            cid = task["conversation_id"] if task["conversation_id"] and self.db.conversation(task["conversation_id"]) \
                else self.cid
            self.db.add_message(cid, "assistant", text, route="device", provider="Local · scheduler")
            if cid == self.cid:
                self.render()
            else:
                self.unread.add(cid)
                self.refresh_chats()
            if self.tray:
                self.tray.showMessage("ULTRON", text.replace("**", "").strip()[:220])
            self.raise_()
        self.update_schedule_card()

    def update_schedule_card(self):
        from tools.whatsapp import describe_task
        pending = self.assistant.scheduler.pending()
        self.schedule_label.setText("\n".join(describe_task(t) for t in pending[:4]) or "Nothing scheduled")

    def on_reply(self, cid, reply):
        if cid == self.cid:
            self.render()
        else:
            self.unread.add(cid)
        note = f" · {reply.note}" if reply.note else ""
        self.set_task(f"Done · {reply.provider}{note}")
        self.update_schedule_card()
        self.refresh_chats()
        callback, self._reply_callback = self._reply_callback, None
        if callback:
            callback(reply.text)
            return
        if self.speak_next_reply:
            self.speak_next_reply = False
            self.speak(reply.text)

    def on_error(self, cid, message):
        self.db.add_message(cid, "assistant", f"Something went wrong: {message}", route="device", provider="Local")
        if cid == self.cid:
            self.render()
        self.set_task("Failed · see the message above")
        callback, self._reply_callback = self._reply_callback, None
        if callback:
            callback(f"Something went wrong: {message}")

    def _finish(self, worker):
        self._keep.discard(worker)
        self.busy_cid = None
        self.send_btn.setEnabled(True)
        self.refresh_chats()

    def set_task(self, text):
        self.task_line.setText(text)
        self.task_card.setText(text)


    def poll_status(self):
        if self.status_running:
            return
        self.status_running = True
        worker = StatusWorker(self.pool.ollama_url, self.pool.local_model)
        worker.signals.ready.connect(self.on_status)
        self._keep.add(worker)
        worker.signals.ready.connect(lambda _i, w=worker: self._keep.discard(w))
        self.threads.start(worker)

    def on_status(self, info):
        self.status_running = False
        if "cpu" in info:
            self.cpu_value.setText(f"{info['cpu']:.0f}%")
            self.cpu_bar.setValue(int(info["cpu"]))
            self.ram_value.setText(f"{info['ram_used']:.1f} / {info['ram_total']:.1f} GB")
            self.ram_bar.setValue(int(info["ram_percent"]))
            self.ram_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {C['amber']}; }}"
                                       if info["ram_percent"] >= 80 else "")
        online = info.get("ollama") == "online"
        self.pill.setText("Local AI online" if online else "Local AI offline")
        self.pill.setStyleSheet(self._pill_style(C["blue"] if online else C["orange"]))
        self.ollama_state = info.get("model_state", "")
        self.update_ai_card()

    def update_ai_card(self):
        lines = [f"<b>Local</b> · {html.escape(self.pool.local_model)}<br>"
                 f"<span style='color:{C['muted']}'>{html.escape(self.ollama_state)}</span>"]
        for name, state in self.pool.summary().items():
            color = C["blue"] if state == "ready" else C["muted"]
            lines.append(f"<b>{self.pool.label(name)}</b> · <span style='color:{color}'>{html.escape(state)}</span>")
        lines.append(f"<span style='color:{C['muted']}'>{html.escape(self.routing_state)}</span>")
        self.ai_label.setText("<br>".join(lines))

    def load_router_model(self):
        if not self.db.get("smart_routing", True) or self.router.has_embedder:
            return
        worker = FunctionWorker(self.router.load_default_embedder, MODEL_CACHE)
        worker.signals.result.connect(lambda _r: self._routing("Smart routing on (local embedding model)"))
        worker.signals.error.connect(lambda e: self._routing("Keyword routing (smart routing unavailable)", e))
        self._keep.add(worker)
        self.threads.start(worker)

    def _routing(self, text, error=""):
        self.routing_state = text
        if error:
            self.ai_label.setToolTip(error)
        self.update_ai_card()

    def open_settings(self):
        if SettingsDialog(self.db, self.providers_config, self).exec() == QDialog.DialogCode.Accepted:
            self.apply_settings()
            self.cloud_box.setChecked(bool(self.db.get("cloud_enabled", True)))
            self.update_ai_card()
            self.update_privacy()
            self.load_router_model()
            self.poll_status()
            if self.voice_window:
                self.voice_window.orb.set_palette(self.db.get("orb_palette", "crimson"))


    def open_voice_mode(self):
        from gui.voice_mode import VoiceModeWindow
        if self.voice_window and self.voice_window.isVisible():
            self.voice_window.raise_()
            self.voice_window.activateWindow()
            return
        if self.db.messages(self.cid):
            self.new_chat()
        self.voice_window = VoiceModeWindow(self.submit, self.threads, self.db,
                                            palette=self.db.get("orb_palette", "crimson"))
        self.voice_window.show()
        self.voice_window.raise_()
        self.voice_window.activateWindow()
        self.voice_window.start()


    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        if self.voice_window:
            self.voice_window.close()
        self.close()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        if not self._quitting and self.tray and self.db.get("run_in_background", True):
            event.ignore()
            self.hide()
            if not self._told_background:
                self._told_background = True
                self.tray.showMessage("ULTRON", "Still running in the background. Ctrl+Alt+Space for voice, "
                                                "Ctrl+Alt+U to open. Right-click the tray icon to quit.")
            return
        self.unregister_hotkeys()
        if self.tray:
            self.tray.hide()
        super().closeEvent(event)

    def register_hotkeys(self):
        """Ctrl+Alt+Space = voice mode, Ctrl+Alt+U = open ULTRON, from any app (Windows only)."""
        self.hotkeys_ok = False
        import os
        if os.name != "nt":
            return
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = int(self.winId())
        mods = 0x0001 | 0x0002 | 0x4000
        ok1 = user32.RegisterHotKey(hwnd, HOTKEY_VOICE, mods, 0x20)
        ok2 = user32.RegisterHotKey(hwnd, HOTKEY_SHOW, mods, ord("U"))
        self.hotkeys_ok = bool(ok1 and ok2)

    def unregister_hotkeys(self):
        import os
        if os.name == "nt":
            import ctypes
            for hk in (HOTKEY_VOICE, HOTKEY_SHOW):
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), hk)

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:
                if msg.wParam == HOTKEY_VOICE:
                    self.open_voice_mode()
                elif msg.wParam == HOTKEY_SHOW:
                    self.show_window()
                return True, 0
        return super().nativeEvent(event_type, message)


    def start_recording(self):
        if self.low_memory:
            self.set_task("Voice is off in low-memory mode (Settings → Voice & data).")
            return
        if self.busy_cid:
            self.set_task("Wait for the current request to finish before talking.")
            return
        try:
            from voice.audio import AudioRecorder
            self.recorder = self.recorder or AudioRecorder()
            self.recorder.start()
            self.mic.setIcon(icon("mic", C["accent"]))
            self.set_task("Listening… release the button when you're done.")
        except Exception as exc:
            self.set_task(f"Microphone unavailable: {exc}")

    def stop_recording(self):
        if not self.recorder or self.recorder._stream is None:
            return
        self.mic.setIcon(icon("mic"))
        try:
            audio = self.recorder.stop()
        except Exception as exc:
            self.set_task(str(exc))
            return
        from voice.stt import SpeechToText
        self.stt = self.stt or SpeechToText("base")

        def transcribe(a):
            try:
                return self.stt.transcribe(a)
            finally:
                self.stt.unload()

        self.set_task("Transcribing on this PC…")
        worker = FunctionWorker(transcribe, audio)
        worker.signals.result.connect(self.on_transcript)
        worker.signals.error.connect(lambda e: self.set_task(f"Voice input failed: {e}"))
        self._keep.add(worker)
        self.threads.start(worker)

    def on_transcript(self, text):
        self.input.setPlainText(text)
        self.speak_next_reply = True
        self.send()

    def speak(self, text):
        voice = self.db.get("piper_voice", "")
        if self.low_memory or not voice:
            return
        from voice.tts import speak
        worker = FunctionWorker(speak, text, voice)
        worker.signals.error.connect(lambda e: self.set_task(f"Couldn't speak the reply: {e}"))
        self._keep.add(worker)
        self.threads.start(worker)
