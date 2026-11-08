from dataclasses import dataclass, field
from typing import Any

@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

class ModelProvider:
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ModelReply:
        raise NotImplementedError

class OllamaProvider(ModelProvider):
    def __init__(self, model: str, host: str):
        self.model, self.host = model, host

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ModelReply:
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError("The optional 'ollama' Python package is not installed. Install the requirements to enable local AI.") from exc
        try:
            client = ollama.Client(host=self.host)
            opts = {"model": self.model, "messages": messages, "think": False, "options": {"num_ctx": 4096, "temperature": 0.2}}
            if tools:
                opts["tools"] = tools
            response = client.chat(**opts)
        except Exception as exc:
            raise RuntimeError(f"Couldn't reach Ollama at {self.host} with model {self.model}: {exc}") from exc
        msg = getattr(response, "message", None)
        if msg is None:
            msg = response.get("message", {})
        calls = []
        raw_calls = getattr(msg, "tool_calls", None)
        if raw_calls is None:
            raw_calls = msg.get("tool_calls", []) or []
        for call in raw_calls:
            fn = getattr(call, "function", None)
            if fn is None:
                fn = call.get("function", {})
            name = getattr(fn, "name", None)
            arguments = getattr(fn, "arguments", None)
            if name is None:
                name = fn.get("name", "")
            if arguments is None:
                arguments = fn.get("arguments", {})
            if hasattr(arguments, "model_dump"):
                arguments = arguments.model_dump()
            calls.append({"name": name, "arguments": arguments})
        content = getattr(msg, "content", None)
        if content is None:
            content = msg.get("content", "")
        return ModelReply(content or "", calls)
