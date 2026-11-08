from __future__ import annotations

import os
import subprocess
import time
from difflib import SequenceMatcher
from pathlib import Path

from config import APPLICATIONS, TOOL_OUTPUT_CHARS
from security.approvals import ApprovalGate, ApprovalRequest
from security.paths import PathDenied, PathSecurity

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".cpp", ".c", ".h", ".hpp", ".cu", ".java", ".json", ".csv",
                   ".log", ".yaml", ".yml", ".toml", ".ini", ".html", ".css", ".js", ".ts"}

EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".py", ".pyw", ".lnk", ".msi", ".vbs", ".vbe",
                         ".js", ".jse", ".wsf", ".wsh", ".com", ".scr", ".cpl", ".hta", ".reg", ".jar"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "env", ".cache", "AppData"}
SEARCH_TIME_LIMIT = 6.0
MAX_RESULTS = 50


def truncate(text: str, limit: int = TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[… truncated: showing {limit} of {len(text)} characters]"


def _words(value: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return cleaned.split()


def name_matches(name: str, query: str) -> bool:
    """Every query word must appear in the file name, allowing small typos."""
    q_words = _words(query)
    if not q_words:
        return True
    n_words = _words(Path(name).stem) or _words(name)
    joined = "".join(n_words)
    if "".join(q_words) in joined:
        return True
    for word in q_words:
        if word in joined:
            continue
        if len(word) >= 4 and any(SequenceMatcher(None, word, part).ratio() >= 0.8 for part in n_words):
            continue
        return False
    return True


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


class FileTools:
    def __init__(self, security: PathSecurity, gate: ApprovalGate):
        self.security = security
        self.gate = gate


    def list_files(self, directory: str, extension: str = "") -> list[dict]:
        root = self.security.resolve(directory)
        if not root.is_dir():
            raise ValueError(f"Not a folder: {root}")
        ext = _norm_ext(extension)
        out = []
        for item in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
            if ext and item.suffix.casefold() != ext:
                continue
            out.append({"name": item.name, "type": "folder" if item.is_dir() else "file", "path": str(item)})
            if len(out) >= MAX_RESULTS:
                break
        return out

    def find_files(self, query: str, extension: str = "", directory: str = "") -> dict:
        if directory:
            roots = [self.security.resolve(directory)]
        else:
            candidates = list(self.security.roots)
            profile = Path.home().resolve()
            if any(root == profile or root.is_relative_to(profile) for root in self.security.roots):
                candidates.append(profile)
            else:
                try:
                    common = Path(os.path.commonpath([str(root) for root in candidates])).resolve()

                    if len(common.parts) > 1:
                        candidates.append(common)
                except (ValueError, OSError):
                    pass
            roots = []
            for candidate in sorted(set(candidates), key=lambda p: len(p.parts)):
                if not any(candidate == root or candidate.is_relative_to(root) for root in roots):
                    roots.append(candidate)
        ext = _norm_ext(extension)
        matches: list[dict] = []
        deadline = time.monotonic() + SEARCH_TIME_LIMIT
        stopped_early = False
        skipped = {name.casefold() for name in SKIP_DIRS}
        for root in roots:
            for base, dirs, files in os.walk(root):
                base_path = Path(base)
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.casefold() not in skipped
                           and not _is_link(base_path / d)]
                for name in files:
                    p = base_path / name
                    if (not ext or p.suffix.casefold() == ext) and name_matches(name, query):
                        matches.append({"name": name, "path": str(p)})
                if len(matches) >= MAX_RESULTS or time.monotonic() > deadline:
                    stopped_early = True
                    break
            if stopped_early:
                break
        result = {"searched": [str(r) for r in roots], "matches": matches[:MAX_RESULTS]}
        if stopped_early:
            result["note"] = "Search stopped early (time or result limit). Results may be incomplete."
        return result

    def read_file(self, path: str) -> str:
        p = self.security.resolve(path)
        if not p.is_file():
            raise ValueError(f"Not a file: {p}")
        suffix = p.suffix.casefold()
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
            return truncate(text.strip() or "[This PDF has no extractable text. It may be a scanned image.]")
        if suffix not in TEXT_EXTENSIONS:
            raise ValueError(f"Reading {suffix or 'this'} files isn't supported.")
        if p.stat().st_size > 5_000_000:
            raise ValueError("That file is larger than the 5 MB reading limit.")
        return truncate(p.read_text(encoding="utf-8", errors="replace"))


    def open_document(self, path: str) -> dict:
        p = self.security.resolve(path)
        if p.suffix.casefold() in EXECUTABLE_EXTENSIONS:
            raise PathDenied(f"{p.name} is a program or script. Opening it would run it. "
                             "Use open_with_editor to view it instead.")
        if os.name != "nt":
            raise RuntimeError("Opening documents is only supported on Windows.")
        os.startfile(str(p))
        return {"opened": str(p)}

    def open_with_editor(self, path: str) -> dict:
        p = self.security.resolve(path)
        editor = next((c for c in APPLICATIONS["vscode"]["candidates"] if Path(c).is_file()), None)
        editor = editor or "notepad.exe"
        try:
            subprocess.Popen([editor, str(p)], shell=False)
        except OSError as exc:
            raise RuntimeError(f"Couldn't start {editor}: {exc}") from exc
        return {"opened": str(p), "editor": "VS Code" if editor.lower().endswith("code.exe") else "Notepad"}


    def create_folder(self, path: str, reason: str = "") -> dict:
        p = self.security.resolve(path, must_exist=False)
        if p.exists():
            raise FileExistsError(f"Already exists: {p}")
        self.gate.require(ApprovalRequest("create_folder", "Create a folder", {"Location": str(p)}, reason))
        p = self.security.resolve(path, must_exist=False)
        p.mkdir(parents=True, exist_ok=False)
        return {"created": str(p), "verified": p.is_dir()}

    def create_text_file(self, path: str, content: str, reason: str = "") -> dict:
        p = self.security.resolve(path, must_exist=False)
        if p.exists():
            raise FileExistsError(f"Already exists: {p}")
        if p.suffix.casefold() in EXECUTABLE_EXTENSIONS:
            raise PathDenied("ULTRON doesn't create scripts or programs.")
        self.gate.require(ApprovalRequest(
            "create_text_file", "Create a text file",
            {"Location": str(p), "Size": f"{len(content)} characters"}, reason, preview=content))
        p = self.security.resolve(path, must_exist=False)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        return {"created": str(p), "verified": p.is_file()}


def _norm_ext(extension: str) -> str:
    ext = (extension or "").strip().casefold()
    return ext if not ext or ext.startswith(".") else "." + ext
