from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ApprovalRequest:
    tool: str
    title: str
    details: dict[str, str]
    reason: str = ""
    preview: str = ""
    editable: tuple[str, ...] = ()
    warning: str = ""
    edits: dict[str, str] = field(default_factory=dict)

    def value(self, key: str) -> str:
        if key in self.edits:
            return self.edits[key]
        return self.preview if key == "Preview" else self.details.get(key, "")


@dataclass
class ApprovalGate:
    """`ask` blocks the calling (worker) thread until the user answers. Defaults to rejecting."""
    ask: Callable[[ApprovalRequest], bool] = field(default=lambda _req: False)

    def require(self, request: ApprovalRequest) -> ApprovalRequest:
        if not self.ask(request):
            raise ApprovalRejected(f"You rejected: {request.title}.")
        return request


class ApprovalRejected(PermissionError):
    pass
