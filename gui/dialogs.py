from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
                               QPushButton, QSlider,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from config import (DATABASE, DEFAULT_ALLOWED_ROOTS, DEFAULT_MIC_SENSITIVITY, GMAIL_APP_PASSWORD_KEY, LOCAL_MODEL,
                    OLLAMA_URL)
from core import secrets
from gui.theme import C, icon
from security.approvals import ApprovalRequest


class ApprovalDialog(QDialog):
    def __init__(self, request: ApprovalRequest, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ULTRON · Permission request")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        badge = QLabel()
        badge.setPixmap(icon("permission", C["amber"], 26).pixmap(26, 26))
        head.addWidget(badge)
        title = QLabel(f"<b style='font-size:17px'>Permission request</b><br>"
                       f"<span style='color:{C['muted']}'>ULTRON wants to make a change</span>")
        head.addWidget(title, 1)
        lay.addLayout(head)
        self.request = request
        self.fields: dict = {}
        if request.warning:
            warn = QLabel(request.warning)
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {C['amber']}; border: 1px solid #5a4a1f; border-radius: 8px; padding: 8px;")
            lay.addWidget(warn)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        rows = [("Action", request.title), ("Tool", request.tool), *request.details.items()]
        if request.reason:
            rows.append(("Your request", f"“{request.reason}”"))
        for i, (k, v) in enumerate(rows):
            key = QLabel(k)
            key.setObjectName("muted")
            if k in request.editable:
                val = QLineEdit(str(v))
                self.fields[k] = val
            else:
                val = QLabel(str(v))
                val.setWordWrap(True)
                val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if k in ("Location", "Tool", "Process", "Keys"):
                val.setStyleSheet("font-family: Consolas, 'JetBrains Mono', monospace;")
            grid.addWidget(key, i, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val, i, 1)
        lay.addLayout(grid)
        if request.preview:
            editable = "Preview" in request.editable
            label = QLabel("Content (you can edit it before approving):" if editable else "Full content:")
            label.setObjectName("muted")
            lay.addWidget(label)
            box = QPlainTextEdit(request.preview)
            box.setReadOnly(not editable)
            box.setMinimumHeight(180)
            lay.addWidget(box)
            if editable:
                self.fields["Preview"] = box
        note = QLabel("If anything about this action changes, ULTRON will ask again.")
        note.setObjectName("muted")
        lay.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        reject = QPushButton("Reject")
        approve = QPushButton("Approve")
        approve.setObjectName("primary")
        reject.clicked.connect(self.reject)
        approve.clicked.connect(self.accept)
        buttons.addWidget(reject)
        buttons.addWidget(approve)
        lay.addLayout(buttons)
        reject.setDefault(True)

    def accept(self):

        for key, widget in self.fields.items():
            self.request.edits[key] = widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()
        super().accept()


class RecordDialog(QDialog):
    """Record / stop / play / use. Returns (audio, rate) in self.result_audio."""

    def __init__(self, prompt: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ULTRON · Record a voice message")
        self.setMinimumWidth(420)
        self.result_audio = None
        self.recorder = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        title = QLabel(f"<b style='font-size:16px'>{prompt}</b>")
        title.setWordWrap(True)
        lay.addWidget(title)
        self.info = QLabel("Press Record, speak, then Stop. You can listen before using it.")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        row = QHBoxLayout()
        self.rec = QPushButton(" Record")
        self.rec.setIcon(icon("mic", C["accent"]))
        self.rec.clicked.connect(self._toggle)
        self.play_btn = QPushButton(" Play")
        self.play_btn.setIcon(icon("speaker"))
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play)
        row.addWidget(self.rec)
        row.addWidget(self.play_btn)
        row.addStretch()
        lay.addLayout(row)
        bottom = QHBoxLayout()
        bottom.addStretch()
        cancel = QPushButton("Cancel")
        self.use = QPushButton("Use this recording")
        self.use.setObjectName("primary")
        self.use.setEnabled(False)
        cancel.clicked.connect(self.reject)
        self.use.clicked.connect(self.accept)
        bottom.addWidget(cancel)
        bottom.addWidget(self.use)
        lay.addLayout(bottom)

    def _toggle(self):
        from voice.audio import AudioRecorder, TARGET_RATE
        try:
            if self.recorder is None or self.recorder._stream is None:
                self.recorder = AudioRecorder(max_seconds=120)
                self.recorder.start()
                self.rec.setText(" Stop")
                self.info.setText("Recording… press Stop when you're done (up to 2 minutes).")
                self.use.setEnabled(False)
                self.play_btn.setEnabled(False)
            else:
                audio = self.recorder.stop()
                self.result_audio = (audio, TARGET_RATE)
                self.rec.setText(" Record again")
                self.info.setText(f"Recorded {len(audio) / TARGET_RATE:.1f} s.")
                self.use.setEnabled(True)
                self.play_btn.setEnabled(True)
        except Exception as exc:
            self.info.setText(f"Microphone problem: {exc}")
            self.rec.setText(" Record")

    def _play(self):
        import threading
        from voice.audio import play
        if self.result_audio:
            threading.Thread(target=play, args=self.result_audio, daemon=True).start()


class SettingsDialog(QDialog):
    def __init__(self, db, providers_config: dict, parent=None):
        super().__init__(parent)
        self.db, self.cfg = db, providers_config
        self.setWindowTitle("ULTRON · Settings")
        self.resize(640, 600)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)


        ai = QWidget()
        form = QFormLayout(ai)
        self.cloud = QCheckBox("Use cloud AI for general/web questions (local model replies may be included)")
        self.cloud.setChecked(bool(db.get("cloud_enabled", True)))
        form.addRow(self.cloud)
        self.groq_key = self._key_field("GROQ_API_KEY")
        self.gemini_key = self._key_field("GEMINI_API_KEY")
        form.addRow("Groq API key", self.groq_key)
        form.addRow("Gemini API key", self.gemini_key)
        self.groq_model = QLineEdit(db.get("groq_model", "") or providers_config["providers"]["groq"]["model"])
        self.gemini_model = QLineEdit(db.get("gemini_model", "") or providers_config["providers"]["gemini"]["model"])
        form.addRow("Groq model", self.groq_model)
        form.addRow("Gemini model", self.gemini_model)
        self.local_model = QLineEdit(db.get("local_model", LOCAL_MODEL))
        self.ollama_url = QLineEdit(db.get("ollama_url", OLLAMA_URL))
        form.addRow("Local model (Ollama)", self.local_model)
        form.addRow("Ollama address", self.ollama_url)
        self.smart = QCheckBox("Smart routing: small local embedding model (downloads ~130 MB once)")
        self.smart.setChecked(bool(db.get("smart_routing", True)))
        form.addRow(self.smart)
        hint = QLabel("Keys are stored in Windows Credential Manager, never in files. Leave a key field empty to "
                      "keep the saved key; type a single space to remove it.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        form.addRow(hint)
        tabs.addTab(ai, "AI")


        gen = QWidget()
        gf = QFormLayout(gen)
        self.background = QCheckBox("Keep running in the background when I close the window (tray icon)")
        self.background.setChecked(bool(db.get("run_in_background", True)))
        gf.addRow(self.background)
        self.startup = QCheckBox("Start ULTRON when I sign in to Windows (starts hidden in the tray)")
        self.startup.setChecked(startup_enabled())
        gf.addRow(self.startup)
        self.palette = QComboBox()
        for label, key in (("Crimson", "crimson"), ("Ice", "ice"), ("Gold", "gold")):
            self.palette.addItem(label, key)
        self.palette.setCurrentIndex(max(0, self.palette.findData(db.get("orb_palette", "crimson"))))
        gf.addRow("Voice-mode core color", self.palette)
        self.effect = QComboBox()
        self.effect.addItem("ULTRON synthetic voice (deeper, digital edge)", "synthetic")
        self.effect.addItem("Plain Piper voice", "none")
        self.effect.setCurrentIndex(max(0, self.effect.findData(db.get("voice_effect", "synthetic"))))
        gf.addRow("Spoken voice", self.effect)
        keys = QLabel("Hotkeys (work from any app): Ctrl+Alt+Space → voice mode · Ctrl+Alt+U → open ULTRON")
        keys.setObjectName("muted")
        keys.setWordWrap(True)
        gf.addRow(keys)
        tabs.insertTab(0, gen, "General")
        tabs.setCurrentIndex(0)


        folders = QWidget()
        fl = QVBoxLayout(folders)
        info = QLabel("With the standard folders, ULTRON searches file names across your user profile. It can read or change files only inside these folders.")
        info.setObjectName("muted")
        fl.addWidget(info)
        self.roots = QListWidget()
        for r in db.get("allowed_roots", DEFAULT_ALLOWED_ROOTS) or DEFAULT_ALLOWED_ROOTS:
            self.roots.addItem(r)
        fl.addWidget(self.roots, 1)
        row = QHBoxLayout()
        add, remove = QPushButton("Add folder…"), QPushButton("Remove selected")
        add.clicked.connect(self._add_root)
        remove.clicked.connect(lambda: [self.roots.takeItem(self.roots.row(i)) for i in self.roots.selectedItems()])
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        fl.addLayout(row)
        tabs.addTab(folders, "Allowed folders")


        mail = QWidget()
        ml = QVBoxLayout(mail)
        mf = QFormLayout()
        self.email_mode = QComboBox()
        self.email_mode.addItem("Open a Gmail draft in Chrome (I press Send)", "draft")
        self.email_mode.addItem("Send directly after I approve it (needs app password)", "send")
        self.email_mode.setCurrentIndex(1 if db.get("email_mode", "draft") == "send" else 0)
        mf.addRow("When I ask for an email", self.email_mode)
        self.gmail = QLineEdit(db.get("gmail_address", ""))
        self.gmail.setPlaceholderText("you@gmail.com")
        mf.addRow("Gmail address", self.gmail)
        self.app_password = self._key_field(GMAIL_APP_PASSWORD_KEY)
        self.app_password.setPlaceholderText(
            "saved ✓ (leave empty to keep)" if secrets.has_key(GMAIL_APP_PASSWORD_KEY) else "16-character app password")
        mf.addRow("Gmail app password", self.app_password)
        self.user_name = QLineEdit(db.get("user_name", ""))
        self.user_name.setPlaceholderText("used to sign emails and voice messages")
        mf.addRow("Your name", self.user_name)
        self.country = QLineEdit(db.get("default_country", "91"))
        self.country.setMaximumWidth(80)
        mf.addRow("Default country code", self.country)
        ml.addLayout(mf)
        how = QLabel("Direct sending needs 2-Step Verification on your Google account, then an app password from "
                     "myaccount.google.com/apppasswords. It's stored in Windows Credential Manager. Every email is "
                     "shown for approval (and editing) before it's sent.")
        how.setWordWrap(True)
        how.setObjectName("muted")
        ml.addWidget(how)
        ml.addWidget(QLabel("Contacts (so you can say “mail Rahul” or “voice message Rahul”)"))
        self.contacts = QTableWidget(0, 3)
        self.contacts.setHorizontalHeaderLabels(["Name", "Email", "WhatsApp number"])
        self.contacts.horizontalHeader().setStretchLastSection(True)
        for c in db.get("contacts", []) or []:
            self._add_contact_row(c.get("name", ""), c.get("email", ""), c.get("phone", ""))
        ml.addWidget(self.contacts, 1)
        cr = QHBoxLayout()
        add_c, rm_c = QPushButton("Add contact"), QPushButton("Remove selected")
        add_c.clicked.connect(lambda: self._add_contact_row("", "", ""))
        rm_c.clicked.connect(lambda: [self.contacts.removeRow(r) for r in
                                      sorted({i.row() for i in self.contacts.selectedIndexes()}, reverse=True)])
        cr.addWidget(add_c)
        cr.addWidget(rm_c)
        cr.addStretch()
        ml.addLayout(cr)
        tabs.addTab(mail, "Email & contacts")


        voice = QWidget()
        vf = QFormLayout(voice)
        self.low_memory = QCheckBox("Low-memory mode (turns voice off, frees ~0.5 GB)")
        self.low_memory.setChecked(bool(db.get("low_memory", False)))
        vf.addRow(self.low_memory)
        self.piper = QLineEdit(db.get("piper_voice", ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self.piper.setText(
            QFileDialog.getOpenFileName(self, "Choose a Piper voice", "", "Piper voice (*.onnx)")[0] or self.piper.text()))
        pr = QHBoxLayout()
        pr.addWidget(self.piper, 1)
        pr.addWidget(browse)
        pw = QWidget()
        pw.setLayout(pr)
        vf.addRow("Piper voice (.onnx)", pw)
        vnote = QLabel("Speech recognition (Whisper base) always runs locally. It downloads ~150 MB on first use.")
        vnote.setWordWrap(True)
        vnote.setObjectName("muted")
        vf.addRow(vnote)
        self.mic_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self.mic_sensitivity.setRange(0, 100)
        self.mic_sensitivity.setTickInterval(10)
        self.mic_sensitivity.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.mic_sensitivity.setValue(int(db.get("mic_sensitivity", DEFAULT_MIC_SENSITIVITY)))
        self.mic_sensitivity_label = QLabel()
        self.mic_sensitivity.valueChanged.connect(self._update_mic_sensitivity_label)
        self._update_mic_sensitivity_label(self.mic_sensitivity.value())
        sensitivity_row = QHBoxLayout()
        sensitivity_row.addWidget(self.mic_sensitivity, 1)
        sensitivity_row.addWidget(self.mic_sensitivity_label)
        sensitivity_widget = QWidget()
        sensitivity_widget.setLayout(sensitivity_row)
        vf.addRow("Hands-free mic sensitivity", sensitivity_widget)
        sensitivity_hint = QLabel("Higher sensitivity detects quieter speech. ULTRON calibrates room noise each time it listens.")
        sensitivity_hint.setWordWrap(True)
        sensitivity_hint.setObjectName("muted")
        vf.addRow(sensitivity_hint)
        vf.addRow("Data folder", QLabel(str(DATABASE.parent)))
        tabs.addTab(voice, "Voice & data")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _key_field(self, name: str) -> QLineEdit:
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText("saved ✓ (leave empty to keep)" if secrets.has_key(name) else "paste your free API key")
        field.setProperty("key_name", name)
        return field

    def _add_contact_row(self, name: str, email: str, phone: str = ""):
        row = self.contacts.rowCount()
        self.contacts.insertRow(row)
        for col, value in enumerate((name, email, phone)):
            self.contacts.setItem(row, col, QTableWidgetItem(value))

    def _add_root(self):
        path = QFileDialog.getExistingDirectory(self, "Choose an allowed folder", str(Path.home()))
        if path and path not in [self.roots.item(i).text() for i in range(self.roots.count())]:
            self.roots.addItem(path)

    def _save(self):
        roots = [self.roots.item(i).text() for i in range(self.roots.count())]
        if not roots:
            QMessageBox.warning(self, "Allowed folders", "Add at least one allowed folder.")
            return
        contacts = []
        for row in range(self.contacts.rowCount()):
            cell = lambda col: (self.contacts.item(row, col).text() if self.contacts.item(row, col) else "").strip()
            name, email, phone = cell(0), cell(1), cell(2)
            if name and (email or phone):
                contacts.append({"name": name, "email": email, "phone": phone})
        self.db.set("contacts", contacts)
        self.db.set("user_name", self.user_name.text().strip())
        self.db.set("default_country", "".join(ch for ch in self.country.text() if ch.isdigit()) or "91")
        self.db.set("email_mode", self.email_mode.currentData())
        self.db.set("gmail_address", self.gmail.text().strip())
        for field in (self.groq_key, self.gemini_key, self.app_password):
            value = field.text()
            if value == " ":
                secrets.set_key(field.property("key_name"), "")
            elif value.strip():
                secrets.set_key(field.property("key_name"), value.strip())
        self.db.set("run_in_background", self.background.isChecked())
        self.db.set("orb_palette", self.palette.currentData())
        self.db.set("voice_effect", self.effect.currentData())
        if self.startup.isChecked() != startup_enabled():
            try:
                set_startup(self.startup.isChecked())
            except Exception as exc:
                QMessageBox.warning(self, "Start with Windows", f"Couldn't change this: {exc}")
        self.db.set("cloud_enabled", self.cloud.isChecked())
        self.db.set("groq_model", self.groq_model.text().strip())
        self.db.set("gemini_model", self.gemini_model.text().strip())
        self.db.set("local_model", self.local_model.text().strip() or LOCAL_MODEL)
        self.db.set("ollama_url", self.ollama_url.text().strip().rstrip("/") or OLLAMA_URL)
        self.db.set("smart_routing", self.smart.isChecked())
        self.db.set("allowed_roots", roots)
        self.db.set("low_memory", self.low_memory.isChecked())
        self.db.set("piper_voice", self.piper.text().strip())
        self.db.set("mic_sensitivity", self.mic_sensitivity.value())
        self.accept()

    def _update_mic_sensitivity_label(self, value: int):
        if value < 34:
            label = "Low"
        elif value < 68:
            label = "Balanced"
        else:
            label = "High"
        self.mic_sensitivity_label.setText(f"{label} · {value}")


class ActionLogDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ULTRON · Action log")
        self.resize(980, 520)
        lay = QVBoxLayout(self)
        cols = ("created_at", "tool", "arguments", "approval", "status", "result")
        table = QTableWidget(0, len(cols))
        table.setHorizontalHeaderLabels(["Time (UTC)", "Tool", "Arguments", "Approval", "Status", "Result"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        for row in db.action_logs():
            i = table.rowCount()
            table.insertRow(i)
            for j, key in enumerate(cols):
                table.setItem(i, j, QTableWidgetItem(str(row.get(key, ""))[:300]))
        table.resizeColumnsToContents()
        lay.addWidget(table)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        lay.addWidget(close)


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_command() -> str:
    import sys
    from config import ROOT
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" "{ROOT / "main.py"}" --background'


def startup_enabled() -> bool:
    import os
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, "ULTRON")
            return True
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    """Adds/removes ULTRON in your user's startup list (HKCU\...\Run). No admin rights needed."""
    import os
    if os.name != "nt":
        raise RuntimeError("Only available on Windows.")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, "ULTRON", 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, "ULTRON")
            except OSError:
                pass


def separator() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {C['line']};")
    return line
