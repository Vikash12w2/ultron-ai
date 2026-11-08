from __future__ import annotations

import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from config import APP_ALIASES, APPLICATIONS
from security.approvals import ApprovalGate, ApprovalRequest

LAUNCH_WAIT_SECONDS = 4.0


def _process_ids(name: str) -> set[int]:
    import psutil
    wanted = name.casefold()
    return {p.pid for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").casefold() == wanted}


class AppTools:
    def __init__(self, gate: ApprovalGate, registry: dict | None = None, process_ids=_process_ids):
        self.gate = gate
        self.registry = registry or APPLICATIONS
        self.process_ids = process_ids

    def resolve(self, app: str) -> tuple[str, dict]:
        app = str(app or "").strip()
        key = "".join(ch for ch in app.casefold() if ch.isalnum())
        key = APP_ALIASES.get(key, key)
        if key in self.registry:
            return key, {**self.registry[key], "registered": True}

        raw = os.path.expandvars(str(app or "").strip().strip('"').strip("'"))
        if not raw:
            raise ValueError("Give the application name or its .exe path.")
        candidate = Path(raw).expanduser()
        target = candidate if candidate.is_file() else None
        if target is None and not any(sep in raw for sep in ("/", "\\")):
            target_text = shutil.which(raw) or shutil.which(raw + ".exe")
            target = Path(target_text) if target_text else None
            if target is None:
                import psutil
                wanted = {raw.casefold(), (raw if raw.casefold().endswith(".exe") else raw + ".exe").casefold()}
                for proc in psutil.process_iter(["name", "exe"]):
                    try:
                        info = proc.info
                        executable = info.get("exe")
                        if ((info.get("name") or "").casefold() in wanted and isinstance(executable, str)):
                            candidate = Path(executable)
                            if candidate.is_file():
                                target = candidate
                                break
                    except (psutil.Error, OSError):
                        continue
        if target is None:
            raise FileNotFoundError(f"Couldn't find '{app}'. Give an executable name on PATH or its full .exe path.")
        target = target.resolve()
        if target.suffix.casefold() != ".exe":
            raise ValueError("Only application .exe files can be launched or controlled by name/path.")
        return key, {"label": target.stem, "candidates": [str(target)], "process": target.name,
                     "registered": False}

    def _target(self, spec: dict) -> str:
        for c in spec.get("candidates", []):
            if Path(c).is_absolute() and Path(c).is_file():
                return c
        for c in spec.get("candidates", []):
            if not Path(c).is_absolute():
                return c
        raise FileNotFoundError(f"{spec['label']} wasn't found. Checked: {', '.join(spec['candidates'])}")

    def _launch_and_verify(self, spec: dict, args: list[str]) -> dict:
        """launched = a new process appeared; already_running = it was open before
        (Chrome/VS Code hand the request to the running instance); failed = nothing to show for it."""
        label, process = spec["label"], spec["process"]
        was_running = bool(self.process_ids(process))
        try:
            if spec.get("uri"):
                if os.name != "nt":
                    raise RuntimeError("Only supported on Windows.")
                os.startfile(spec["uri"])
            else:
                subprocess.Popen([self._target(spec), *args], shell=False)
        except Exception as exc:
            return {"status": "failed", "app": label, "reason": str(exc)}
        if was_running:
            return {"status": "already_running", "app": label,
                    "note": f"{label} was already running; the request was sent to it."}
        deadline = time.monotonic() + LAUNCH_WAIT_SECONDS
        while time.monotonic() < deadline:
            if self.process_ids(process):
                return {"status": "launched", "app": label}
            time.sleep(0.2)
        return {"status": "failed", "app": label, "reason": f"No {process} process appeared."}

    def open_app(self, app: str, reason: str = "") -> dict:
        _key, spec = self.resolve(app)
        if not spec.get("registered", True):
            target = self._target(spec)
            self.gate.require(ApprovalRequest(
                "open_app", f"Open {spec['label']}", {"Executable": target}, reason,
                warning="This application isn't in ULTRON's built-in list. Confirm before opening it."))
        return self._launch_and_verify(spec, [])

    def open_website(self, url: str, browser: str = "default") -> dict:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in parsed.netloc:
            raise ValueError("That isn't a valid http(s) web address.")
        if (browser or "default").casefold() == "chrome":
            result = self._launch_and_verify(self.registry["chrome"], [url])
            return {**result, "url": url}
        if not webbrowser.open(url):
            raise RuntimeError("Windows didn't accept the request to open the default browser.")
        return {"status": "opened", "url": url, "browser": "default"}

    def close_app(self, app: str, reason: str = "") -> dict:
        _key, spec = self.resolve(app)
        process = spec["process"]
        if not self.process_ids(process):
            return {"status": "not_running", "app": spec["label"]}
        self.gate.require(ApprovalRequest(
            "close_app", f"Close {spec['label']}", {"Process": process,
            "How": "Asks the app to close normally (unsaved work prompts still appear)"}, reason))

        subprocess.run(["taskkill", "/IM", process], shell=False, capture_output=True, timeout=10)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self.process_ids(process):
                return {"status": "closed", "app": spec["label"]}
            time.sleep(0.3)
        return {"status": "still_running", "app": spec["label"],
                "reason": "It may be waiting for you to save or confirm."}
