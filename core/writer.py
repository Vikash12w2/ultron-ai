from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from pydantic_ai import Agent, UsageLimits

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{6,}\d")

PROMPTS = {
    "voice_message": (
        "Write the words for a short spoken WhatsApp voice message (under 60 words) that ULTRON, {user}'s AI "
        "assistant, will say to the recipient on {user}'s behalf, based on the request below. Start by saying it's a "
        "message from {user}. Plain spoken sentences only: no emojis, no markdown, no quotation marks, no stage "
        "directions. Output only the words to say."),
    "email": (
        "Write the email described in the request below, from {user}. Natural, clear, polite; match the tone the "
        "request implies. Output exactly this format and nothing else:\nSubject: <subject>\n\n<body>\n"
        "Sign the body as {user}. No markdown. If the request mentions an earlier draft you can't see, write a "
        "complete new email from the request."),
}


def scrub(text: str) -> str:
    return PHONE_RE.sub("[number]", EMAIL_RE.sub("[email]", text or ""))


def parse_email(text: str) -> dict:
    m = re.match(r"\s*subject\s*:\s*(.+?)\s*\n(.*)", text or "", re.I | re.S)
    if not m:
        return {"subject": "", "body": (text or "").strip()}
    return {"subject": m.group(1).strip(), "body": m.group(2).strip()}


class Writer:
    def __init__(self, pool, request: str, *, user_name: str = "", allow_cloud: bool = True,
                 status: Callable[[str], None] = lambda _m: None):
        self.pool, self.request = pool, request
        self.user = user_name.strip() or "the user"
        self.allow_cloud = allow_cloud
        self.status = status
        self.last_writer = ""

    def __call__(self, kind: str) -> dict:
        instructions = PROMPTS[kind].format(user=self.user)
        prompt = "Request: " + scrub(self.request)
        chain = self.pool.chain("chat") if self.allow_cloud else ["local"]
        problems = []
        for name in chain:
            ok, why = self.pool.availability(name)
            if not ok:
                problems.append(f"{self.pool.label(name)}: {why}")
                continue
            try:
                self.status(f"Writing the {kind.replace('_', ' ')} with {self.pool.label(name)}…")
                model, settings = self.pool.build(name)
                agent = Agent(model, model_settings=settings, instructions=instructions)


                with ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(agent.run_sync, prompt,
                                         usage_limits=UsageLimits(request_limit=2)).result(timeout=120)
                text = str(result.output).strip().strip('"')
                if not text:
                    raise ValueError("empty answer")
                self.last_writer = f"{self.pool.label(name)} · {self.pool.model_name(name)}"
                out = {"text": text, "written_by": self.last_writer}
                if kind == "email":
                    out.update(parse_email(text))
                return out
            except Exception as exc:
                problems.append(f"{self.pool.label(name)}: {self.pool.report_failure(name, exc)}")
        raise RuntimeError("Couldn't write the text: " + "; ".join(problems))
