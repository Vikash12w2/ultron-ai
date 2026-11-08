from __future__ import annotations

import json
import threading
import urllib.request

from PySide6.QtCore import QObject, QRunnable, Signal


class ChatSignals(QObject):
    reply = Signal(str, object)
    error = Signal(str, str)
    status = Signal(str, str)
    approval = Signal(object, object)
    record = Signal(str, object)
    done = Signal(str)


class ChatWorker(QRunnable):
    def __init__(self, assistant, conversation_id: str, text: str):
        super().__init__()
        self.assistant, self.cid, self.text = assistant, conversation_id, text
        self.signals = ChatSignals()

    def _approve(self, request) -> bool:
        event, holder = threading.Event(), {"ok": False}
        self.signals.approval.emit(request, (event, holder))
        event.wait()
        return holder["ok"]

    def _record(self, prompt: str):
        event, holder = threading.Event(), {"audio": None}
        self.signals.record.emit(prompt, (event, holder))
        event.wait()
        return holder["audio"]

    def run(self):
        try:
            reply = self.assistant.respond(self.cid, self.text, approve=self._approve, record=self._record,
                                           status=lambda m: self.signals.status.emit(self.cid, m))
            self.signals.reply.emit(self.cid, reply)
        except Exception as exc:
            self.signals.error.emit(self.cid, f"{type(exc).__name__}: {exc}")
        finally:
            self.signals.done.emit(self.cid)


class StatusSignals(QObject):
    ready = Signal(dict)


class StatusWorker(QRunnable):
    """CPU/RAM plus Ollama state, read in the background (short timeouts)."""

    def __init__(self, ollama_url: str, model: str):
        super().__init__()
        self.url, self.model = ollama_url, model
        self.signals = StatusSignals()

    def _get(self, path: str):
        with urllib.request.urlopen(self.url + path, timeout=1.5) as r:
            return json.loads(r.read().decode())

    def run(self):
        info: dict = {}
        try:
            import psutil
            mem = psutil.virtual_memory()
            info.update(cpu=psutil.cpu_percent(interval=0.3), ram_used=mem.used / 1024 ** 3,
                        ram_total=mem.total / 1024 ** 3, ram_percent=mem.percent)
        except Exception:
            pass
        try:
            installed = [m.get("name", "") for m in self._get("/api/tags").get("models", [])]
            loaded = [m.get("name", "") for m in self._get("/api/ps").get("models", [])]
            base = self.model if ":" in self.model else self.model + ":latest"
            info["ollama"] = "online"
            info["model_state"] = ("loaded" if base in loaded else
                                   "installed · not loaded" if base in installed else "not installed")
        except Exception:
            info["ollama"] = "offline"
            info["model_state"] = "Ollama not running"
        self.signals.ready.emit(info)


class TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class FunctionWorker(QRunnable):
    """Runs any callable off the GUI thread (router model loading, transcription, speech)."""

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = TaskSignals()

    def run(self):
        try:
            value = self.fn(*self.args)
        except Exception as exc:
            _safe_emit(self.signals.error, str(exc))
        else:
            _safe_emit(self.signals.result, value)


def _safe_emit(signal, *args):
    try:
        signal.emit(*args)
    except RuntimeError:
        pass
