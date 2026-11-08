from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

from config import HISTORY_CHARS

GENERAL = "general"
DEVICE = "device"


def select_rows(rows: list[dict], *, for_cloud: bool) -> list[dict]:
    """Cloud history can include local assistant replies, never local prompts or tool records."""
    if for_cloud:
        return [r for r in rows if
                (r["route"] == GENERAL and r["role"] in ("user", "assistant")) or
                (r["route"] in (DEVICE, "local") and r["role"] == "assistant" and
                 r.get("provider", "").startswith("Local · "))]
    return [r for r in rows if r["role"] in ("user", "assistant", "context")]


def build_history(rows: list[dict], *, for_cloud: bool, budget: int = HISTORY_CHARS) -> list[ModelMessage]:
    selected = select_rows(rows, for_cloud=for_cloud)

    merged: list[dict] = []
    pending_context: list[str] = []
    for r in selected:
        if r["role"] == "context":
            pending_context.append(r["content"])
            continue
        content = r["content"]
        if r["role"] == "assistant" and pending_context:
            content = "[My tool results, for reference]\n" + "\n".join(pending_context) + "\n\n" + content
            pending_context = []
        merged.append({"role": r["role"], "content": content, "route": r["route"]})

    kept: list[dict] = []
    used = 0
    for m in reversed(merged):
        size = len(m["content"])
        if kept and used + size > budget:
            break
        if not kept and size > budget:
            m = {**m, "content": m["content"][-budget:]}
            size = budget
        kept.append(m)
        used += size
    kept.reverse()
    while kept and kept[0]["role"] != "user":
        if kept[0]["role"] == "assistant" and kept[0]["route"] in (DEVICE, "local"):
            kept.insert(0, {"role": "user", "route": GENERAL,
                            "content": "[The next assistant message is an earlier local ULTRON reply, shared as context.]"})
            break
        kept.pop(0)
    out: list[ModelMessage] = []
    for m in kept:
        if m["role"] == "user":
            out.append(ModelRequest(parts=[UserPromptPart(m["content"])]))
        else:
            out.append(ModelResponse(parts=[TextPart(m["content"])]))
    return out
