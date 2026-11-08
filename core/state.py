from dataclasses import dataclass, field

@dataclass
class AppState:
    busy: bool = False
    voice_active: bool = False
    pending_approval: dict | None = None
    current_conversation: str | None = None
    messages: list[dict] = field(default_factory=list)
