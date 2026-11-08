from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic_ai import UsageLimits
from pydantic_ai import exceptions as E

from config import DEFAULT_ALLOWED_ROOTS, MAX_MODEL_REQUESTS
from core.agents import DeviceDeps, WebDeps, chat_agent, device_agent, web_agent
from core.history import DEVICE, GENERAL, build_history
from core.providers import ProviderPool, describe_error
from core.router import Decision, Route, Router
from memory.database import Database
from security.approvals import ApprovalGate, ApprovalRequest
from security.paths import PathSecurity
from tools.apps import AppTools
from config import VOICE_NOTES
from core.scheduler import Scheduler
from core.writer import Writer
from tools.email import EmailTools
from tools.files import FileTools
from tools.keyboard import KeyboardTools
from tools.whatsapp import WhatsAppTools


@dataclass
class Reply:
    text: str
    route: str
    provider: str
    note: str = ""
    reason: str = ""


class Assistant:
    def __init__(self, db: Database, router: Router, pool: ProviderPool, keyboard_factory=KeyboardTools):
        self.db, self.router, self.pool = db, router, pool
        self.keyboard_factory = keyboard_factory
        self.scheduler = Scheduler(db)
        self.whatsapp_options: dict = {}

    def allowed_roots(self) -> list[str]:
        return self.db.get("allowed_roots", DEFAULT_ALLOWED_ROOTS) or DEFAULT_ALLOWED_ROOTS

    def respond(self, conversation_id: str, text: str, *,
                approve: Callable[[ApprovalRequest], bool] = lambda _r: False,
                status: Callable[[str], None] = lambda _m: None,
                record: Callable[[str], object] | None = None) -> Reply:
        rows = self.db.messages(conversation_id)
        decision = self.router.decide(text, cloud_enabled=self.db.get("cloud_enabled", True))
        prompt = text.strip()
        if prompt.casefold().startswith("/local"):
            prompt = prompt[len("/local"):].strip() or "Hello"
        route = DEVICE if decision.route is Route.DEVICE else GENERAL
        self.db.add_message(conversation_id, "user", text.strip(), route=route)
        if decision.route is Route.DEVICE:
            reply = self._device(conversation_id, prompt, rows, approve, status, decision, record)
        else:
            reply = self._cloud(conversation_id, prompt, rows, status, decision)
        self.db.add_message(conversation_id, "assistant", reply.text, route=reply.route, provider=reply.provider)
        return reply


    def _device(self, cid, prompt, rows, approve, status, decision: Decision, record=None) -> Reply:
        events: list[str] = []

        def ask(request: ApprovalRequest) -> bool:
            ok = bool(approve(request))
            events.append("approved" if ok else "rejected")
            return ok

        gate = ApprovalGate(ask)
        security = PathSecurity(self.allowed_roots())
        apps = AppTools(gate)
        used_device_data = self.db.is_local_only(cid)
        writer = Writer(self.pool, prompt, user_name=self.db.get("user_name", ""),
                        allow_cloud=bool(self.db.get("cloud_enabled", True)) and not used_device_data, status=status)
        contacts = self.db.get("contacts", []) or []
        options = {"synthesize": self._synthesize, **self.whatsapp_options}
        whatsapp = WhatsAppTools(
            VOICE_NOTES, contacts, default_country=self.db.get("default_country", "91") or "91",
            voice_path=self.db.get("piper_voice", ""), record=record,
            scheduler=self.scheduler, conversation_id=cid, **options)
        deps = DeviceDeps(
            files=FileTools(security, gate), apps=apps, keyboard=self.keyboard_factory(gate),
            email=EmailTools(gate, open_url=lambda url: apps.open_website(url, "chrome"),
                             gmail_address=self.db.get("gmail_address", "")),
            contacts=contacts, chat_used_device_data=used_device_data, whatsapp=whatsapp, scheduler=self.scheduler,
            writer=writer, request=prompt, status=status,
            log=lambda tool, args, approval, st, result: self.db.log_action(cid, prompt, tool, args, approval, st, result),
            approval_events=events)
        label = f"Local · {self.pool.local_model}"
        provider = label
        status("Thinking locally…")
        try:
            model, settings = self.pool.build("local")
            agent = device_agent(model, settings, security.describe_roots(), self.db.get("email_mode", "draft"))
            result = agent.run_sync(prompt, deps=deps, message_history=build_history(rows, for_cloud=False),
                                    usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS))
            text = str(result.output).strip()
            if not text:
                provider = f"Local error · {self.pool.local_model}"
                text = "(The local model returned an empty answer.)"
        except E.ModelConnectionError:
            provider = f"Local error · {self.pool.local_model}"
            text = (f"I can't reach the local model. Make sure Ollama is running at {self.pool.ollama_url} "
                    f"and the model is installed (`ollama pull {self.pool.local_model}`).")
        except E.UsageLimitExceeded:
            provider = f"Local error · {self.pool.local_model}"
            text = "I stopped after too many steps so I wouldn't get stuck. Tell me what to do next."
        except (E.ModelNotFoundError, E.ModelHTTPError) as exc:
            provider = f"Local error · {self.pool.local_model}"
            if getattr(exc, "status_code", None) == 404 or isinstance(exc, E.ModelNotFoundError):
                text = f"The local model `{self.pool.local_model}` isn't installed. Run `ollama pull {self.pool.local_model}`."
            else:
                text = f"The local model returned an error: {describe_error(exc)}"
        except Exception as exc:
            provider = f"Local error · {self.pool.local_model}"
            text = f"Something went wrong in local mode: {describe_error(exc)}"
        if deps.read_device_data:
            self.db.mark_local_only(cid)
        if deps.tool_notes:
            self.db.add_message(cid, "context", "\n".join(deps.tool_notes)[-1500:], route=DEVICE)
        return Reply(text, DEVICE, provider, reason=decision.reason)

    @staticmethod
    def _synthesize(text, voice_path):
        from voice.tts import synthesize
        return synthesize(text, voice_path)


    def _cloud(self, cid, prompt, rows, status, decision: Decision) -> Reply:
        task = "web" if decision.route is Route.WEB else "chat"
        history = build_history(rows, for_cloud=True)
        skipped: list[str] = []
        log = lambda tool, args, approval, st, result: self.db.log_action(cid, prompt, tool, args, approval, st, result)
        for name in self.pool.chain(task):
            label = self.pool.label(name)
            ok, why = self.pool.availability(name)
            if not ok:
                skipped.append(f"{label}: {why}")
                continue
            try:
                model, settings = self.pool.build(name)
                deps = None
                if task == "chat":
                    agent = chat_agent(model, settings)
                    status(f"Asking {label}…")
                elif name == "gemini":
                    agent = web_agent(model, settings, native_search=True)
                    status("Searching the web with Gemini (Google Search)…")
                else:
                    agent = web_agent(model, settings, native_search=False)
                    deps = WebDeps(status=status, log=log)
                    status(f"Researching with {label}…")
                result = agent.run_sync(prompt, deps=deps, message_history=history,
                                        usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS))
                text = str(result.output).strip() or "(Empty answer.)"
                return Reply(text, GENERAL, f"{label} · {self.pool.model_name(name)}", note="; ".join(skipped),
                             reason=decision.reason)
            except Exception as exc:
                reason = self.pool.report_failure(name, exc)
                skipped.append(f"{label}: {reason}")
                status(f"{label} unavailable ({reason}), trying the next option…")
        detail = "; ".join(skipped)
        if any(s.startswith("Local:") for s in skipped):
            detail += f". For the local model, make sure Ollama is running (`ollama pull {self.pool.local_model}`)."
        return Reply(f"I couldn't get an answer from any AI provider. {detail}", GENERAL, "None", note=detail,
                     reason=decision.reason)
