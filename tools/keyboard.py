from __future__ import annotations

import os
import re
import time

from config import APPLICATIONS
from security.approvals import ApprovalGate, ApprovalRequest

VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
      "backspace": 0x08, "delete": 0x2E, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24,
      "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "space": 0x20,
      **{f"f{i}": 0x6F + i for i in range(1, 13)}}
MODIFIERS = {"ctrl", "shift", "alt"}
BLOCKED_KEYS = {"win", "windows", "lwin", "rwin", "super", "cmd", "meta"}
BROWSERS = {"chrome"}


EDITORS = {"vscode": [0x11, ord("1")], "notepad": None}
CHUNK = 24


def parse_combo(keys: str) -> list[int]:
    parts = [p.strip().casefold() for p in re.split(r"\s*\+\s*", keys.strip()) if p.strip()]
    if not parts:
        raise ValueError("No keys given.")
    if any(p in BLOCKED_KEYS for p in parts):
        raise ValueError("The Windows key can't be used (it can open the Run dialog).")
    codes = []
    for p in parts:
        if p in VK:
            codes.append(VK[p])
        elif len(p) == 1 and p.isalnum():
            codes.append(ord(p.upper()))
        else:
            raise ValueError(f"Unknown key: {p}")
    if not any(c not in (VK["ctrl"], VK["shift"], VK["alt"]) for c in codes):
        raise ValueError("A shortcut needs at least one non-modifier key.")
    return codes


class KeyboardTools:
    def __init__(self, gate: ApprovalGate, backend=None, registry: dict | None = None):
        self.gate = gate
        self.registry = registry or APPLICATIONS
        self.backend = backend or WindowsKeyboard()

    def _spec(self, app: str) -> tuple[str, dict]:
        from tools.apps import AppTools
        return AppTools(self.gate, registry=self.registry).resolve(app)

    def type_text(self, app: str, text: str, *, device_data_in_chat: bool = False, reason: str = "") -> dict:
        key, spec = self._spec(app)
        if not text:
            raise ValueError("Nothing to type.")
        needs_ok = ("\n" in text or "\r" in text or "\t" in text) and key not in EDITORS
        why = "The text contains line breaks or tabs, which act like pressing Enter/Tab."
        if not spec.get("registered", True):
            needs_ok, why = True, "ULTRON hasn't used this application before. Review the exact text before it is typed."
        if key in BROWSERS and device_data_in_chat:
            needs_ok, why = True, "This chat has read your files, and text typed into a web page can leave your PC."
        if needs_ok:
            req = self.gate.require(ApprovalRequest(
                "type_text", f"Type into {spec['label']}", {"App": spec["label"]}, reason,
                preview=text, editable=("Preview",), warning=why))
            text = req.value("Preview")
        target = (spec["process"], spec.get("window_title"))
        self.backend.focus(*target)
        if EDITORS.get(key):
            self.backend.combo(EDITORS[key])
        typed = 0
        for i in range(0, len(text), CHUNK):
            if not self.backend.is_foreground(*target):
                return {"status": "stopped", "typed_chars": typed,
                        "reason": f"{spec['label']} lost focus, so typing stopped."}
            chunk = text[i:i + CHUNK]
            self.backend.type(chunk)
            typed += len(chunk)
        return {"status": "typed", "app": spec["label"], "typed_chars": typed}

    def press_keys(self, app: str, keys: str, reason: str = "") -> dict:
        _key, spec = self._spec(app)
        codes = parse_combo(keys)
        self.gate.require(ApprovalRequest(
            "press_keys", f"Press {keys.upper()} in {spec['label']}", {"App": spec["label"], "Keys": keys},
            reason, warning="Keys like Enter or Ctrl+Enter can send or submit things."))
        target = (spec["process"], spec.get("window_title"))
        self.backend.focus(*target)
        if not self.backend.is_foreground(*target):
            return {"status": "failed", "reason": f"Couldn't bring {spec['label']} to the front."}
        self.backend.combo(codes)
        return {"status": "pressed", "app": spec["label"], "keys": keys}


class WindowsKeyboard:
    """Windows implementation using user32 (no extra packages)."""

    def __init__(self):
        if os.name != "nt":
            self.user32 = None
            return
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wt = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

        ulong_ptr = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self.KEYBDINPUT, self.INPUT = KEYBDINPUT, INPUT

    def _require(self):
        if self.user32 is None:
            raise RuntimeError("Keyboard control only works on Windows.")

    def _pid_of(self, hwnd) -> int:
        pid = self.wt.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid))
        return pid.value

    def _process_name(self, pid: int) -> str:
        import psutil
        try:
            return psutil.Process(pid).name()
        except Exception:
            return ""

    def _title(self, hwnd) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        buf = self.ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _matches(self, hwnd, process: str, title: str | None) -> bool:
        name = self._process_name(self._pid_of(hwnd)).casefold()
        if title:
            return name in (process.casefold(), "applicationframehost.exe") and title.casefold() in self._title(hwnd).casefold()
        return name == process.casefold()

    def is_foreground(self, process: str, title: str | None = None) -> bool:
        self._require()
        hwnd = self.user32.GetForegroundWindow()
        return bool(hwnd) and self._matches(hwnd, process, title)

    def focus(self, process: str, title: str | None = None) -> None:
        self._require()
        found = []
        proto = self.ctypes.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)

        def callback(hwnd, _lparam):
            if self.user32.IsWindowVisible(hwnd) and self.user32.GetWindowTextLengthW(hwnd) > 0:
                if self._matches(hwnd, process, title):
                    found.append(hwnd)
            return True

        self.user32.EnumWindows(proto(callback), 0)
        if not found:
            raise RuntimeError(f"No open {process} window. Open the app first.")
        hwnd = found[0]
        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, 9)

        self._key(VK["alt"], down=True)
        self._key(VK["alt"], down=False)
        self.user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)

    def _send(self, inputs) -> None:
        arr = (self.INPUT * len(inputs))(*inputs)
        if self.user32.SendInput(len(inputs), arr, self.ctypes.sizeof(self.INPUT)) != len(inputs):
            raise RuntimeError("Windows blocked the key input (is an admin window in front?).")

    def _key(self, vk: int, down: bool) -> None:
        ki = self.KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0 if down else 0x0002, time=0, dwExtraInfo=0)
        self._send([self.INPUT(type=1, ki=ki)])

    def type(self, text: str) -> None:
        self._require()
        inputs = []
        data = text.encode("utf-16-le")
        for i in range(0, len(data), 2):
            unit = int.from_bytes(data[i:i + 2], "little")
            for flags in (0x0004, 0x0004 | 0x0002):
                inputs.append(self.INPUT(type=1, ki=self.KEYBDINPUT(wVk=0, wScan=unit, dwFlags=flags, time=0,
                                                                     dwExtraInfo=0)))
        self._send(inputs)
        time.sleep(0.02)

    def combo(self, codes: list[int]) -> None:
        self._require()
        for c in codes:
            self._key(c, down=True)
        for c in reversed(codes):
            self._key(c, down=False)
