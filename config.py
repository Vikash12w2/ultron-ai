from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "ULTRON"
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


DATA_DIR = Path(os.environ.get("ULTRON_DATA_DIR", Path.home() / "AppData" / "Local" / "ULTRON"))
DATABASE = DATA_DIR / "ultron.db"
MODEL_CACHE = DATA_DIR / "models"
VOICE_NOTES = DATA_DIR / "voice_notes"


LOCAL_MODEL = "qwen3:1.7b"
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


HISTORY_CHARS = 6000
TOOL_OUTPUT_CHARS = 4000
MAX_MODEL_REQUESTS = 6
TOOL_TIMEOUT_SECONDS = 30
DEFAULT_MIC_SENSITIVITY = 70


DEFAULT_ALLOWED_ROOTS = [str(Path.home() / name) for name in ("Desktop", "Documents", "Downloads")]


APPLICATIONS = {
    "chrome": {
        "label": "Chrome",
        "candidates": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
        ],
        "process": "chrome.exe",
    },
    "vscode": {
        "label": "VS Code",
        "candidates": [
            str(Path.home() / "AppData/Local/Programs/Microsoft VS Code/Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        ],
        "process": "Code.exe",
    },
    "notepad": {"label": "Notepad", "candidates": ["notepad.exe"], "process": "Notepad.exe"},

    "calculator": {"label": "Calculator", "candidates": ["calc.exe"], "process": "CalculatorApp.exe",
                   "window_title": "Calculator"},
    "explorer": {"label": "File Explorer", "candidates": ["explorer.exe"], "process": "explorer.exe"},
    "settings": {"label": "Windows Settings", "uri": "ms-settings:", "process": "SystemSettings.exe",
                 "window_title": "Settings"},
}
APP_ALIASES = {
    "googlechrome": "chrome", "browser": "chrome", "visualstudiocode": "vscode", "code": "vscode",
    "calc": "calculator", "fileexplorer": "explorer", "files": "explorer",
    "windowssettings": "settings", "controlpanel": "settings",
}



GMAIL_SMTP = ("smtp.gmail.com", 587)
GMAIL_APP_PASSWORD_KEY = "GMAIL_APP_PASSWORD"
MAX_EMAIL_RECIPIENTS = 10


def load_providers() -> dict:
    """Cloud provider models and the order they are tried for each task."""
    with open(ROOT / "providers.json", encoding="utf-8") as f:
        return json.load(f)
