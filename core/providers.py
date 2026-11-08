from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic_ai import exceptions as E

from config import LOCAL_MODEL, OLLAMA_URL
from core import secrets


@dataclass
class ProviderStatus:
    cooldown_until: float = 0.0
    last_error: str = ""


def seconds_until_midnight_pacific(now: datetime | None = None) -> float:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
    except Exception:
        return 6 * 3600
    now = now.astimezone(tz) if now else datetime.now(tz)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
    return (midnight - now).total_seconds()


class ProviderPool:
    """Builds models and remembers which cloud providers are cooling down."""

    def __init__(self, config: dict, *, get_key=secrets.get_key, clock=time.time):
        self.config = config
        self.get_key = get_key
        self.clock = clock
        self.status = {name: ProviderStatus() for name in config["providers"]}
        self.local_model = LOCAL_MODEL
        self.ollama_url = OLLAMA_URL
        self.model_overrides: dict[str, str] = {}


    def label(self, name: str) -> str:
        if name == "local":
            return "Local"
        return self.config["providers"][name]["label"]

    def model_name(self, name: str) -> str:
        if name == "local":
            return self.local_model
        return self.model_overrides.get(name) or self.config["providers"][name]["model"]

    def chain(self, task: str) -> list[str]:
        return list(self.config["tasks"][task])

    def availability(self, name: str) -> tuple[bool, str]:
        if name == "local":
            return True, ""
        spec = self.config["providers"][name]
        if not self.get_key(spec["key_name"]):
            return False, "no API key"
        st = self.status[name]
        remaining = st.cooldown_until - self.clock()
        if remaining > 0:
            return False, f"{st.last_error} (retry in {_fmt(remaining)})"
        return True, ""

    def summary(self) -> dict[str, str]:
        out = {}
        for name in self.config["providers"]:
            ok, why = self.availability(name)
            out[name] = "ready" if ok else why
        return out


    def build(self, name: str):
        """Returns (model, model_settings)."""
        if name == "local":
            from pydantic_ai.models.ollama import OllamaModel
            from pydantic_ai.providers.ollama import OllamaProvider
            model = OllamaModel(self.local_model, provider=OllamaProvider(base_url=f"{self.ollama_url}/v1"))

            return model, {"openai_reasoning_effort": "medium", "temperature": 0.2}
        key = self.get_key(self.config["providers"][name]["key_name"])
        if name == "groq":
            from pydantic_ai.models.groq import GroqModel
            from pydantic_ai.providers.groq import GroqProvider
            return GroqModel(self.model_name(name), provider=GroqProvider(api_key=key)), {"thinking": "low", "temperature": 0.3}
        if name == "gemini":
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider
            return GoogleModel(self.model_name(name), provider=GoogleProvider(api_key=key)), {"thinking": "low", "temperature": 0.3}
        raise ValueError(f"Unknown provider: {name}")


    def report_failure(self, name: str, exc: BaseException) -> str:
        """Puts a cloud provider on cooldown when appropriate. Returns a short human reason."""
        if name == "local":
            return describe_error(exc)
        spec = self.config["providers"][name]
        reason, cooldown = describe_error(exc), 60.0
        retry_after = getattr(exc, "retry_after", None)
        status_code = getattr(exc, "status_code", None)
        if isinstance(exc, E.ModelQuotaExceededError):
            if spec.get("quota_resets") == "midnight_pacific":
                cooldown = seconds_until_midnight_pacific()
            else:
                cooldown = 60 * float(spec.get("quota_cooldown_minutes", 60))
            reason = "free daily limit reached"
        elif isinstance(exc, E.ModelRateLimitError) or status_code == 429:
            cooldown = float(retry_after or 60)
            reason = "rate limit reached"
        elif isinstance(exc, E.ModelAuthenticationError) or status_code in (401, 403):
            cooldown = 24 * 3600
            reason = "API key was rejected (check it in Settings)"
        elif isinstance(exc, (E.ModelConnectionError, E.ModelServerError, E.ModelUnavailableError)):
            cooldown = 60.0
        elif not isinstance(exc, E.ModelAPIError):
            cooldown = 0.0
        if cooldown:
            self.status[name] = ProviderStatus(self.clock() + cooldown, reason)
        return reason


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, E.ModelConnectionError):
        return "couldn't connect"
    if isinstance(exc, E.ModelQuotaExceededError):
        return "free daily limit reached"
    if isinstance(exc, E.ModelRateLimitError):
        return "rate limit reached"
    if isinstance(exc, E.ModelAuthenticationError):
        return "API key was rejected"
    if isinstance(exc, E.UsageLimitExceeded):
        return "stopped after too many steps"
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:160]


def _fmt(seconds: float) -> str:
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"
