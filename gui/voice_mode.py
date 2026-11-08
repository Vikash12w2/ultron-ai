from __future__ import annotations

import re
import threading
import time

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config import DEFAULT_MIC_SENSITIVITY
from gui.orb import OrbWidget
from gui.theme import C

EXIT_PHRASES = re.compile(r"^\W*(stop( listening)?|exit( voice mode)?|goodbye|bye|that'?s all|close voice mode)\W*$", re.I)


class LoopSignals(QObject):
    level = Signal(float)
    heard = Signal(str)
    nothing = Signal()
    error = Signal(str)
    spoken = Signal()


class ListenWorker(QRunnable):
    def __init__(self, stt, cancel: threading.Event, listen_fn=None, sensitivity: int = DEFAULT_MIC_SENSITIVITY):
        super().__init__()
        self.stt, self.cancel = stt, cancel
        self.listen_fn = listen_fn
        self.sensitivity = sensitivity
        self.signals = LoopSignals()

    def run(self):
        try:
            if self.listen_fn is None:
                from voice.listen import listen
                self.listen_fn = listen
            audio = self.listen_fn(level_cb=self.signals.level.emit, cancel=self.cancel,
                                   sensitivity=self.sensitivity)
            if audio is None or self.cancel.is_set():
                self.signals.nothing.emit()
                return
            self.signals.level.emit(0.0)
            self.signals.heard.emit(self.stt.transcribe(audio))
        except Exception as exc:
            self.signals.error.emit(str(exc))


class SpeakWorker(QRunnable):
    """Synthesizes the reply, plays it, and reports the loudness so the core pulses with the voice."""

    def __init__(self, text: str, voice_path: str, cancel: threading.Event):
        super().__init__()
        self.text, self.voice_path, self.cancel = text, voice_path, cancel
        self.signals = LoopSignals()

    def run(self):
        try:
            import numpy as np
            import sounddevice as sd
            from voice.tts import synthesize
            audio, rate = synthesize(self.text, self.voice_path)
            step = int(rate * 0.05)
            envelope = [float(np.sqrt(np.mean(audio[i:i + step] ** 2))) for i in range(0, len(audio), step)]
            sd.play(audio, rate)
            start = time.monotonic()
            for i, e in enumerate(envelope):
                if self.cancel.is_set():
                    sd.stop()
                    break
                self.signals.level.emit(min(1.0, e * 6))
                delay = start + (i + 1) * 0.05 - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            sd.wait()
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.level.emit(0.0)
            self.signals.spoken.emit()


class VoiceModeWindow(QWidget):
    """`submit(text, on_reply)` is the main window's normal pipeline (routing, approvals, history)."""

    def __init__(self, submit, threads, db, palette: str = "crimson", parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.submit, self.threads, self.db = submit, threads, db
        self.setWindowTitle("ULTRON · Voice mode")
        self.resize(760, 760)
        self.setStyleSheet(f"background: #05070A; color: {C['text']};")
        self.cancel = threading.Event()
        self.paused = False
        self.active = False
        self._keep: set = set()
        self.stt = None
        self._listen_retries = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        top = QHBoxLayout()
        title = QLabel("ULTRON")
        title.setStyleSheet("font-size: 15px; font-weight: 700; letter-spacing: 6px; color: #C9CFD9;")
        top.addWidget(title)
        top.addStretch()
        hint = QLabel("Esc to exit")
        hint.setStyleSheet(f"color: {C['dim']}; font-size: 12px;")
        top.addWidget(hint)
        lay.addLayout(top)
        self.orb = OrbWidget(palette=palette)
        lay.addWidget(self.orb, 1)
        self.state_label = QLabel("Starting…")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("font-size: 20px; font-weight: 600; letter-spacing: 2px;")
        lay.addWidget(self.state_label)
        self.you = QLabel("")
        self.you.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.you.setWordWrap(True)
        self.you.setStyleSheet(f"color: {C['muted']}; font-size: 14px;")
        lay.addWidget(self.you)
        self.reply = QLabel("")
        self.reply.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reply.setWordWrap(True)
        self.reply.setStyleSheet("font-size: 15px;")
        lay.addWidget(self.reply)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        end = QPushButton("End voice mode")
        end.clicked.connect(self.close)
        for b in (self.pause_btn, end):
            b.setStyleSheet(f"background: #11151C; border: 1px solid {C['line']}; border-radius: 10px; padding: 9px 16px;")
            buttons.addWidget(b)
        buttons.addStretch()
        lay.addLayout(buttons)
        QShortcut(QKeySequence("Esc"), self, activated=self.close)
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_pause)


    def start(self):
        if self.db.get("low_memory", False):
            self._set("off", "Voice is off in low-memory mode (Settings → Voice & data).")
            return
        from voice.stt import SpeechToText
        self.stt = self.stt or SpeechToText("base")
        self.active = True
        self.cancel.clear()
        self.listen()

    def _set(self, state: str, text: str):
        self.orb.set_state(state if state in ("idle", "listening", "thinking", "speaking") else "idle")
        self.state_label.setText(text)

    def _run(self, worker):
        self._keep.add(worker)
        self.threads.start(worker)

    def listen(self):
        if not self.active or self.paused:
            return
        self._set("listening", "Listening…")
        sensitivity = int(self.db.get("mic_sensitivity", DEFAULT_MIC_SENSITIVITY))
        w = ListenWorker(self.stt, self.cancel, sensitivity=sensitivity)
        w.signals.level.connect(self.orb.set_level)
        w.signals.heard.connect(self.on_heard)
        w.signals.nothing.connect(self.on_nothing)
        w.signals.error.connect(self.on_error)
        self._run(w)

    def on_nothing(self):
        if self.active and not self.paused:
            self.listen()

    def on_heard(self, text: str):
        if not self.active:
            return
        self._listen_retries = 0
        self.you.setText(f"“{text}”")
        if EXIT_PHRASES.match(text.strip()):
            self.close()
            return
        self._set("thinking", "Thinking…")
        self.reply.setText("")
        self.submit(text, self.on_reply)

    def on_reply(self, reply_text: str):
        if not self.active:
            return
        short = reply_text if len(reply_text) < 400 else reply_text[:400] + "…"
        self.reply.setText(short)
        voice = self.db.get("piper_voice", "")
        if not voice:
            self._set("idle", "Choose a Piper voice in Settings to hear replies")
            self.listen_later()
            return
        self._set("speaking", "Speaking…")
        w = SpeakWorker(reply_text, voice, self.cancel)
        w.signals.level.connect(self.orb.set_level)
        w.signals.error.connect(lambda e: self.state_label.setText(f"Couldn't speak: {e}"))
        w.signals.spoken.connect(self.listen_later)
        self._run(w)

    def listen_later(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(400, self.listen)

    def on_error(self, message: str):
        lower = message.casefold()
        recoverable = ("buffer overrun" in lower or "dropped audio" in lower
                       or "couldn't make out any speech" in lower or "microphone" in lower or "portaudio" in lower)
        if self.active and recoverable and self._listen_retries < 2:
            self._listen_retries += 1
            self._set("listening", "Audio was interrupted · retrying…")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(800, self.listen)
            return
        self._set("idle", "Voice problem")
        self.reply.setText(message)
        self.active = False

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.setText("Resume" if self.paused else "Pause")
        if self.paused:
            self.cancel.set()
            self._set("idle", "Paused · press Space to resume")
        else:
            self.cancel.clear()
            self.listen()

    def closeEvent(self, event):
        self.active = False
        self.cancel.set()
        if self.stt:
            self.stt.unload()
        super().closeEvent(event)
