from pathlib import Path
import os

APP_NAME = "ULTRON"
MODEL = "qwen3:1.7b"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DATA_DIR = Path(os.environ.get("ULTRON_DATA_DIR", Path.home() / "AppData" / "Local" / "ULTRON"))
DATABASE = DATA_DIR / "ultron.db"
MAX_STEPS = 5
MAX_CONTEXT_CHARS = 16000
ALLOWED_ROOTS = [Path.home() / name for name in ("Desktop", "Documents", "Downloads")]
for candidate in (Path.home() / "Projects", Path.home() / "source" / "repos"):
    if candidate.exists():
        ALLOWED_ROOTS.append(candidate)

APPLICATIONS = {
    "chrome": {"label": "Chrome", "candidates": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "chrome.exe"], "process": "chrome.exe"},
    "vscode": {"label": "VS Code", "candidates": [str(Path.home() / "AppData/Local/Programs/Microsoft VS Code/Code.exe"), "code.exe"], "process": "Code.exe"},
    "notepad": {"label": "Notepad", "candidates": ["notepad.exe"], "process": "Notepad.exe"},
    "calculator": {"label": "Calculator", "candidates": ["calc.exe"], "process": "CalculatorApp.exe"},
    "explorer": {"label": "File Explorer", "candidates": ["explorer.exe"], "process": "explorer.exe"},
    "settings": {"label": "Windows Settings", "uri": "ms-settings:", "process": "SystemSettings.exe"},
}
