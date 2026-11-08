from __future__ import annotations

import os
import re
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable

from voice.notes import note_path, write_voice_note


def normalize_phone(phone: str, default_country: str = "91") -> str:
    digits = re.sub(r"\D", "", phone or "")
    if (phone or "").strip().startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        digits = default_country + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = default_country + digits[1:]
    if not 11 <= len(digits) <= 15:
        raise ValueError(f"'{phone}' doesn't look like a phone number. Include the country code, e.g. +91 98765 43210.")
    return digits


def resolve_recipient(to: str, contacts: list[dict], default_country: str = "91") -> tuple[str, str]:
    """Returns (display name, phone digits)."""
    if re.search(r"\d{7,}", re.sub(r"[\s\-()+]", "", to or "")):
        return to.strip(), normalize_phone(to, default_country)
    wanted = (to or "").casefold().strip()
    matches = [c for c in contacts if wanted and wanted in c.get("name", "").casefold() and c.get("phone")]
    if not matches:
        raise ValueError(f"No saved contact named '{to}' with a WhatsApp number. Ask the user for the number "
                         "(they can save it in Settings → Email & contacts).")
    if len(matches) > 1 and not any(c["name"].casefold() == wanted for c in matches):
        names = ", ".join(c["name"] for c in matches[:5])
        raise ValueError(f"Several contacts match '{to}': {names}. Ask which one.")
    contact = next((c for c in matches if c["name"].casefold() == wanted), matches[0])
    return contact["name"], normalize_phone(contact["phone"], default_country)


def default_opener(phone: str) -> str:
    """Opens the chat in WhatsApp Desktop, or wa.me in the browser if the app isn't installed."""
    if os.name == "nt":
        try:
            os.startfile(f"whatsapp://send?phone={phone}")
            return "WhatsApp Desktop"
        except OSError:
            pass
    webbrowser.open(f"https://wa.me/{phone}")
    return "browser (wa.me)"


class WhatsAppTools:
    def __init__(self, notes_dir: Path, contacts: list[dict], *, default_country: str = "91",
                 synthesize: Callable | None = None, voice_path: str = "", record: Callable | None = None,
                 writer: Callable | None = None, scheduler=None, conversation_id: str = "",
                 opener: Callable[[str], str] = default_opener, copy_files: Callable | None = None):
        self.notes_dir = notes_dir
        self.contacts = contacts
        self.default_country = default_country
        self.synthesize = synthesize
        self.voice_path = voice_path
        self.record = record
        self.writer = writer
        self.scheduler = scheduler
        self.conversation_id = conversation_id
        self.opener = opener
        if copy_files is None:
            from tools.clipboard import copy_files as _copy
            copy_files = _copy
        self.copy_files = copy_files

    def _make_note(self, name: str, message: str, own_voice: bool) -> tuple[Path, str]:
        out = note_path(self.notes_dir, name)
        if own_voice:
            if not self.record:
                raise RuntimeError("Recording isn't available here.")
            recorded = self.record(f"Record your voice message for {name}")
            if not recorded:
                raise RuntimeError("You cancelled the recording.")
            audio, rate = recorded
            return write_voice_note(audio, rate, out), "(your own recording)"
        text = (message or "").strip()
        if self.writer:
            text = self.writer("voice_message").get("text", "").strip() or text
        if not text:
            raise ValueError("What should the voice message say?")
        if not self.synthesize:
            raise RuntimeError("Speech output isn't available.")
        audio, rate = self.synthesize(text, self.voice_path)
        return write_voice_note(audio, rate, out), text

    def deliver(self, name: str, phone: str, path: str) -> dict:
        if not Path(path).is_file():
            raise FileNotFoundError(f"The voice note is missing: {path}")
        opened_in = self.opener(phone)
        try:
            self.copy_files([path])
            how = "Press Ctrl+V in the chat, then Send."
        except Exception as exc:
            from tools.clipboard import show_in_explorer
            show_in_explorer(path)
            how = f"Couldn't copy it ({exc}); drag the highlighted file into the chat, then Send."
        return {"status": "ready_to_send", "to": name, "opened_in": opened_in, "file": path, "next": how}

    def voice_message(self, to: str, message: str = "", own_voice: bool = False, when: str = "") -> dict:
        name, phone = resolve_recipient(to, self.contacts, self.default_country)
        run_at = None
        if when.strip():
            from core.scheduler import parse_when
            run_at = parse_when(when)
        path, spoken = self._make_note(name, message, own_voice)
        if run_at and self.scheduler:
            task_id = self.scheduler.add("whatsapp_voice", f"Voice message for {name}",
                                         {"name": name, "phone": phone, "file": str(path)}, run_at, self.conversation_id)
            return {"status": "scheduled", "task_id": task_id, "to": name, "when": run_at.strftime("%a %d %b, %I:%M %p"),
                    "says": spoken, "note": "At that time ULTRON opens the chat and copies the voice note; "
                                            "the user presses Ctrl+V and Send. ULTRON must be running."}
        result = self.deliver(name, phone, str(path))
        return {**result, "says": spoken}


def describe_task(task: dict) -> str:
    when = datetime.fromisoformat(task["run_at"]).strftime("%a %d %b, %I:%M %p")
    return f"#{task['id']} · {task['title']} · {when}"
