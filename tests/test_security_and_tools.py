import os

import pytest

from security.approvals import ApprovalGate, ApprovalRejected
from security.paths import PathDenied, PathSecurity
from tools.apps import AppTools
from tools.files import FileTools, name_matches


def _sec(sandbox):
    return PathSecurity([sandbox / "Documents", sandbox / "Downloads"])



def test_shorthand_resolves_inside_allowed_folder(sandbox):
    (sandbox / "Documents" / "a.txt").write_text("x")
    assert _sec(sandbox).resolve("Documents/a.txt") == (sandbox / "Documents" / "a.txt").resolve()


@pytest.mark.parametrize("bad", ["../Outside", "Documents/../Outside", "Outside/x.txt", "\\\\server\\share\\x", ""])
def test_paths_outside_or_unsafe_are_denied(sandbox, bad):
    with pytest.raises(PathDenied):
        _sec(sandbox).resolve(bad, must_exist=False)


def test_absolute_path_outside_is_denied(sandbox):
    with pytest.raises(PathDenied):
        _sec(sandbox).resolve(str(sandbox / "Outside"))


def test_symlink_escape_is_denied(sandbox):
    link = sandbox / "Documents" / "escape"
    try:
        os.symlink(sandbox / "Outside", link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not allowed on this account")
    with pytest.raises(PathDenied):
        _sec(sandbox).resolve("Documents/escape")


def test_reserved_names_and_streams_are_denied(sandbox):
    for bad in ("Documents/CON.txt", "Documents/a.txt:secret"):
        with pytest.raises(PathDenied):
            _sec(sandbox).resolve(bad, must_exist=False)



def test_find_tolerates_typos_and_searches_all_roots(sandbox):
    (sandbox / "Downloads" / "Vikash_Resume_2026.pdf").write_bytes(b"%PDF")
    tools = FileTools(_sec(sandbox), ApprovalGate())
    found = tools.find_files("resme", ".pdf")
    assert [m["name"] for m in found["matches"]] == ["Vikash_Resume_2026.pdf"]
    assert name_matches("cuda-image-processing", "cuda image")


def test_read_is_truncated_to_budget(sandbox):
    (sandbox / "Documents" / "big.txt").write_text("a" * 20000)
    text = FileTools(_sec(sandbox), ApprovalGate()).read_file("Documents/big.txt")
    assert len(text) < 4200 and "truncated" in text


def test_create_folder_needs_approval(sandbox):
    target = sandbox / "Documents" / "AI Projects"
    asked = []
    tools = FileTools(_sec(sandbox), ApprovalGate(lambda r: asked.append(r) or False))
    with pytest.raises(ApprovalRejected):
        tools.create_folder("Documents/AI Projects")
    assert not target.exists()
    assert asked[0].details["Location"] == str(target.resolve())
    tools = FileTools(_sec(sandbox), ApprovalGate(lambda r: True))
    assert tools.create_folder("Documents/AI Projects")["verified"] is True


def test_new_file_approval_shows_full_content(sandbox):
    seen = []
    tools = FileTools(_sec(sandbox), ApprovalGate(lambda r: seen.append(r) or True))
    tools.create_text_file("Documents/n.txt", "x" * 1000)
    assert seen[0].preview == "x" * 1000


def test_scripts_are_never_opened_with_default_app(sandbox):
    (sandbox / "Documents" / "run.py").write_text("print(1)")
    with pytest.raises(PathDenied):
        FileTools(_sec(sandbox), ApprovalGate()).open_document("Documents/run.py")


def test_editor_receives_path_as_argument(sandbox, monkeypatch):
    (sandbox / "Documents" / "run.bat").write_text("echo hi")
    calls = []
    monkeypatch.setattr("tools.files.subprocess.Popen", lambda args, shell: calls.append((args, shell)))
    FileTools(_sec(sandbox), ApprovalGate()).open_with_editor("Documents/run.bat")
    args, shell = calls[0]
    assert shell is False and args[-1].endswith("run.bat") and args[0].lower().endswith(("code.exe", "notepad.exe"))



class FakeProcs:
    def __init__(self, sequence):
        self.sequence = list(sequence)

    def __call__(self, _name):
        return self.sequence.pop(0) if len(self.sequence) > 1 else self.sequence[0]


REG = {"notepad": {"label": "Notepad", "candidates": ["notepad.exe"], "process": "Notepad.exe"}}


@pytest.mark.parametrize("procs,expected", [
    ([{1}], "already_running"),
    ([set(), set(), {7}], "launched"),
    ([set()], "failed"),
])
def test_launch_statuses(monkeypatch, procs, expected):
    monkeypatch.setattr("tools.apps.subprocess.Popen", lambda *a, **k: None)
    monkeypatch.setattr("tools.apps.LAUNCH_WAIT_SECONDS", 0.5)
    tools = AppTools(ApprovalGate(), registry=REG, process_ids=FakeProcs(procs))
    assert tools.open_app("notepad")["status"] == expected


def test_launch_error_is_reported(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("not installed")
    monkeypatch.setattr("tools.apps.subprocess.Popen", boom)
    result = AppTools(ApprovalGate(), registry=REG, process_ids=lambda _n: set()).open_app("Notepad")
    assert result["status"] == "failed" and "not installed" in result["reason"]


def test_close_app_only_registered_and_needs_approval(monkeypatch):
    ran = []
    monkeypatch.setattr("tools.apps.subprocess.run", lambda *a, **k: ran.append(a))
    tools = AppTools(ApprovalGate(lambda r: False), registry=REG, process_ids=lambda _n: {3})
    with pytest.raises(ValueError):
        tools.close_app("svchost")
    with pytest.raises(ApprovalRejected):
        tools.close_app("notepad")
    assert ran == []


def test_web_fetch_blocks_local_addresses():
    from tools.web import fetch_page
    for url in ("http://localhost:11434/api/tags", "http://192.168.1.1/", "http://127.0.0.1/x", "file:///C:/x"):
        with pytest.raises(ValueError):
            fetch_page(url)
