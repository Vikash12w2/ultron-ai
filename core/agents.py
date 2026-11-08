from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic_ai import Agent, RunContext

from config import APPLICATIONS, TOOL_TIMEOUT_SECONDS
from core.prompts import CHAT_PROMPT, DEVICE_PROMPT, WEB_PROMPT
from security.approvals import ApprovalRejected
from tools import system as system_tools
from tools import web as web_tools
from tools.apps import AppTools
from tools.email import EmailTools
from tools.email import find_contact as _find_contact
from tools.files import FileTools, truncate
from tools.keyboard import KeyboardTools

APPROVAL_TOOLS = {"create_folder", "create_text_file", "close_app", "send_email", "press_keys"}

DATA_TOOLS = {"list_files", "find_files", "read_file", "system_info", "find_contact", "voice_message"}

CONTENT_TOOLS = {"list_files", "find_files", "read_file", "system_info"}


@dataclass
class DeviceDeps:
    files: FileTools
    apps: AppTools
    keyboard: KeyboardTools
    email: EmailTools
    contacts: list[dict]
    request: str
    chat_used_device_data: bool = False
    whatsapp: Any = None
    scheduler: Any = None
    writer: Any = None
    used_device_content: bool = False
    status: Callable[[str], None] = lambda _m: None
    log: Callable[..., None] = lambda *_a, **_k: None
    read_device_data: bool = False
    tool_notes: list[str] = field(default_factory=list)
    approval_events: list[str] = field(default_factory=list)


@dataclass
class WebDeps:
    status: Callable[[str], None] = lambda _m: None
    log: Callable[..., None] = lambda *_a, **_k: None


def _run_tool(deps, tool: str, args: dict, fn: Callable[[], Any], status_text: str):
    deps.status(status_text)
    events = getattr(deps, "approval_events", [])
    seen = len(events)
    try:
        result = fn()
        status = "completed"
        if isinstance(deps, DeviceDeps) and tool in DATA_TOOLS:
            deps.read_device_data = True
        if isinstance(deps, DeviceDeps) and tool in CONTENT_TOOLS:
            deps.used_device_content = True
    except ApprovalRejected as exc:
        result, status = {"error": f"{exc} Do not retry this action."}, "rejected"
    except Exception as exc:
        result, status = {"error": f"{type(exc).__name__}: {exc}"}, "failed"
    if len(events) > seen:
        approval = events[-1]
    else:
        approval = "not_asked" if tool in APPROVAL_TOOLS else "not_required"
    deps.log(tool, args, approval, status, result)
    if isinstance(deps, DeviceDeps):
        deps.tool_notes.append(f"{tool}({json.dumps(args, ensure_ascii=False)}) -> "
                               + truncate(json.dumps(result, ensure_ascii=False, default=str), 700))
    return result



def list_files(ctx: RunContext[DeviceDeps], directory: str, extension: str = "") -> Any:
    """List what is inside an allowed folder. directory can be a full path or Downloads, Documents, Desktop.
    extension optionally filters, e.g. ".pdf"."""
    return _run_tool(ctx.deps, "list_files", {"directory": directory, "extension": extension},
                     lambda: ctx.deps.files.list_files(directory, extension), f"Listing {directory}…")


def find_files(ctx: RunContext[DeviceDeps], query: str, extension: str = "", directory: str = "") -> Any:
    """Search file names (tolerates small typos). Leave directory empty to search the user profile and allowed folders.
    query is part of the file name, e.g. "resume"; extension is optional, e.g. ".pdf"."""
    where = directory or "your user profile and allowed folders"
    return _run_tool(ctx.deps, "find_files", {"query": query, "extension": extension, "directory": directory},
                     lambda: ctx.deps.files.find_files(query, extension, directory), f"Searching {where} for “{query}”…")


def read_file(ctx: RunContext[DeviceDeps], path: str) -> Any:
    """Read a text file or PDF inside an allowed folder (long files are truncated)."""
    return _run_tool(ctx.deps, "read_file", {"path": path}, lambda: ctx.deps.files.read_file(path), "Reading file…")


def open_document(ctx: RunContext[DeviceDeps], path: str) -> Any:
    """Open a document (PDF, Word, image, text...) in its default app. Refuses programs and scripts."""
    return _run_tool(ctx.deps, "open_document", {"path": path}, lambda: ctx.deps.files.open_document(path), "Opening file…")


def open_with_editor(ctx: RunContext[DeviceDeps], path: str) -> Any:
    """Open any file, including scripts, in VS Code (or Notepad) to view it. Never runs it."""
    return _run_tool(ctx.deps, "open_with_editor", {"path": path},
                     lambda: ctx.deps.files.open_with_editor(path), "Opening in editor…")


def create_folder(ctx: RunContext[DeviceDeps], path: str) -> Any:
    """Create a new folder inside an allowed folder, e.g. "Documents/AI Projects". The user must approve."""
    return _run_tool(ctx.deps, "create_folder", {"path": path},
                     lambda: ctx.deps.files.create_folder(path, reason=ctx.deps.request), "Waiting for your approval…")


def create_text_file(ctx: RunContext[DeviceDeps], path: str, content: str) -> Any:
    """Create a new UTF-8 text file inside an allowed folder. The user must approve."""
    return _run_tool(ctx.deps, "create_text_file", {"path": path, "chars": len(content)},
                     lambda: ctx.deps.files.create_text_file(path, content, reason=ctx.deps.request),
                     "Waiting for your approval…")


def open_app(ctx: RunContext[DeviceDeps], app: str) -> Any:
    """Open a registered app or any installed .exe by executable name/full path. Unregistered apps ask first."""
    return _run_tool(ctx.deps, "open_app", {"app": app},
                     lambda: ctx.deps.apps.open_app(app, reason=ctx.deps.request), f"Opening {app}…")


def close_app(ctx: RunContext[DeviceDeps], app: str) -> Any:
    """Close any registered app or app executable normally (it can still ask to save). The user must approve."""
    return _run_tool(ctx.deps, "close_app", {"app": app},
                     lambda: ctx.deps.apps.close_app(app, reason=ctx.deps.request), "Waiting for your approval…")


def open_website(ctx: RunContext[DeviceDeps], url: str, browser: str = "default") -> Any:
    """Open a website. browser is "default" or "chrome" (use chrome when the user names Chrome)."""
    return _run_tool(ctx.deps, "open_website", {"url": url, "browser": browser},
                     lambda: ctx.deps.apps.open_website(url, browser), f"Opening {url}…")


def system_info(ctx: RunContext[DeviceDeps], kind: str = "overview") -> Any:
    """Live PC information. kind: overview, cpu, ram, disk, battery or processes."""
    return _run_tool(ctx.deps, "system_info", {"kind": kind}, lambda: system_tools.system_info(kind),
                     "Reading system information…")


def find_contact(ctx: RunContext[DeviceDeps], name: str) -> Any:
    """Look up a saved contact's email address by name."""
    return _run_tool(ctx.deps, "find_contact", {"name": name}, lambda: _find_contact(ctx.deps.contacts, name),
                     f"Looking up {name}…")


def _cloud_writer(deps: DeviceDeps):
    """The cloud writer is used only when no file/system content is involved in this chat."""
    if deps.writer is None or deps.chat_used_device_data or deps.used_device_content:
        return None
    return deps.writer


def _better_email(deps: DeviceDeps, subject: str, body: str) -> tuple[str, str]:
    writer = _cloud_writer(deps)
    if writer is None:
        return subject, body
    try:
        written = writer("email")
        return written.get("subject") or subject, written.get("body") or body
    except Exception:
        return subject, body


def compose_email(ctx: RunContext[DeviceDeps], to: str, subject: str, body: str) -> Any:
    """Open a prefilled Gmail draft in Chrome. Nothing is sent; the user sends it (or asks you to press Ctrl+Enter).
    Give your best subject/body; ULTRON may rewrite them with a better writing model."""
    def run():
        s, b = _better_email(ctx.deps, subject, body)
        return ctx.deps.email.compose_email(to, s, b)
    return _run_tool(ctx.deps, "compose_email", {"to": to, "subject": subject}, run, "Writing and opening a Gmail draft…")


def send_email(ctx: RunContext[DeviceDeps], to: str, subject: str, body: str) -> Any:
    """Send an email from the user's Gmail. The user sees, can edit, and must approve it first.
    Give your best subject/body; ULTRON may rewrite them with a better writing model."""
    def run():
        s, b = _better_email(ctx.deps, subject, body)
        return ctx.deps.email.send_email(to, s, b, reason=ctx.deps.request)
    return _run_tool(ctx.deps, "send_email", {"to": to, "subject": subject}, run, "Writing the email…")


def voice_message(ctx: RunContext[DeviceDeps], to: str, message: str = "", own_voice: bool = False,
                  when: str = "") -> Any:
    """Prepare a WhatsApp voice message. to: contact name or phone number. message: what to say (ULTRON's voice).
    own_voice=True records the user's own voice instead. when: empty for now, or e.g. "at 6 pm", "in 30 minutes",
    "tomorrow at 9 am". ULTRON opens the chat and copies the voice note; the user presses Ctrl+V and Send."""
    deps = ctx.deps
    deps.whatsapp.writer = _cloud_writer(deps)
    return _run_tool(deps, "voice_message", {"to": to, "own_voice": own_voice, "when": when},
                     lambda: deps.whatsapp.voice_message(to, message, own_voice, when),
                     "Preparing the voice message…")


def list_scheduled(ctx: RunContext[DeviceDeps]) -> Any:
    """List pending scheduled tasks (id, what, when)."""
    from tools.whatsapp import describe_task
    return _run_tool(ctx.deps, "list_scheduled", {},
                     lambda: [describe_task(t) for t in ctx.deps.scheduler.pending()] or "Nothing scheduled.",
                     "Checking your schedule…")


def cancel_scheduled(ctx: RunContext[DeviceDeps], task_id: int) -> Any:
    """Cancel a pending scheduled task by its id (see list_scheduled)."""
    return _run_tool(ctx.deps, "cancel_scheduled", {"task_id": task_id},
                     lambda: {"cancelled": ctx.deps.scheduler.cancel(int(task_id))}, "Cancelling…")


def type_text(ctx: RunContext[DeviceDeps], app: str, text: str) -> Any:
    """Type into an app window by registered name or executable name/path. Unregistered apps require text approval.
    In VS Code it goes into the editor; line breaks are fine in VS Code and Notepad."""
    tainted = ctx.deps.read_device_data or ctx.deps.chat_used_device_data
    return _run_tool(ctx.deps, "type_text", {"app": app, "chars": len(text)},
                     lambda: ctx.deps.keyboard.type_text(app, text, device_data_in_chat=tainted, reason=ctx.deps.request),
                     f"Typing into {app}…")


def press_keys(ctx: RunContext[DeviceDeps], app: str, keys: str) -> Any:
    """Press a key or shortcut in an app identified by registered name or executable name/path. Always approved."""
    return _run_tool(ctx.deps, "press_keys", {"app": app, "keys": keys},
                     lambda: ctx.deps.keyboard.press_keys(app, keys, reason=ctx.deps.request),
                     "Waiting for your approval…")


DEVICE_TOOLS = [list_files, find_files, read_file, open_document, open_with_editor, create_folder,
                create_text_file, open_app, close_app, open_website, system_info,
                find_contact, compose_email, send_email, type_text, press_keys,
                voice_message, list_scheduled, cancel_scheduled]



def search_web(ctx: RunContext[WebDeps], query: str) -> Any:
    """Search the web. Returns titles, links and snippets."""
    return _run_tool(ctx.deps, "web_search", {"query": query}, lambda: web_tools.web_search(query),
                     f"Searching the web: {query}")


def read_web_page(ctx: RunContext[WebDeps], url: str) -> Any:
    """Read the main text of a public web page."""
    return _run_tool(ctx.deps, "fetch_page", {"url": url}, lambda: web_tools.fetch_page(url), f"Reading {url}…")



def device_agent(model, settings: dict, roots_description: str, email_mode: str = "draft") -> Agent:
    apps = ", ".join(spec["label"] for spec in APPLICATIONS.values())
    email = ("send_email (direct send after the user approves)" if email_mode == "send"
             else "compose_email (opens a Gmail draft the user sends)")
    return Agent(model, deps_type=DeviceDeps, model_settings=settings, tools=DEVICE_TOOLS, retries=2,
                 instructions=DEVICE_PROMPT.format(roots=roots_description, apps=apps, email=email))


def chat_agent(model, settings: dict) -> Agent:
    return Agent(model, model_settings=settings, instructions=CHAT_PROMPT)


def web_agent(model, settings: dict, *, native_search: bool) -> Agent:
    if native_search:

        from pydantic_ai.capabilities import WebSearch
        return Agent(model, model_settings=settings, instructions=WEB_PROMPT,
                     capabilities=[WebSearch(local=False)])
    return Agent(model, deps_type=WebDeps, model_settings=settings, instructions=WEB_PROMPT,
                 tools=[search_web, read_web_page], tool_timeout=TOOL_TIMEOUT_SECONDS, retries=2)
