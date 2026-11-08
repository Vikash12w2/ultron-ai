from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum



class Route(str, Enum):
    DEVICE = "device"
    WEB = "web"
    CHAT = "chat"


@dataclass(frozen=True)
class Decision:
    route: Route
    reason: str

    @property
    def is_cloud_eligible(self) -> bool:
        return self.route in (Route.WEB, Route.CHAT)



_APP_WORDS = sorted({"chrome", "google chrome", "vs code", "vscode", "visual studio code", "notepad", "calculator",
                     "file explorer", "task manager", "windows settings"}, key=len, reverse=True)
_APP_RE = "|".join(re.escape(w) for w in _APP_WORDS)
_DEVICE_NOUNS = (r"files?|folders?|directory|directories|documents|downloads|desktop|pc|laptop|computer|system|"
                 r"machine|device|drive|disk|projects?|resume|cv|notes?|assignments?|screenshots?|photos?|pictures?|"
                 r"apps?|applications?|programs?|processes|storage|battery|ram|cpu|screen")
_FILE_EXT = r"pdf|docx?|txt|md|py|cpp|cu|c|h|java|json|csv|xlsx?|pptx?|png|jpe?g|zip|exe|bat|ps1|log|ini|yaml|yml"

DEVICE_PATTERNS = [
    (re.compile(r"[a-z]:[\\/]|(^|\s)~[\\/]|\\\\|%[a-z]+%", re.I), "mentions a local path"),
    (re.compile(rf"\b[\w\-]+\.({_FILE_EXT})\b", re.I), "mentions a file name"),
    (re.compile(rf"\b(my|this|our)\s+([\w\-]+\s+){{0,2}}({_DEVICE_NOUNS})\b", re.I), "refers to your device or files"),
    (re.compile(rf"\b(in|with|using)\s+({_APP_RE})\b", re.I), "involves an app on this PC"),
    (re.compile(r"\b(in|from|on|to|inside|under)\s+(my\s+|the\s+)?(downloads|documents|desktop)\b", re.I),
     "refers to a local folder"),
    (re.compile(r"^\W*(please\s+|ultron\W+|hey\s+ultron\W+|can\s+you\s+|could\s+you\s+)*"
                r"(open|launch|close|quit|kill)\b", re.I), "asks to open/close something"),
    (re.compile(rf"\b(open|launch|start|close|quit|run|exit)\b.*\b({_APP_RE})\b", re.I), "asks to control an app"),
    (re.compile(r"\b(create|make|new|delete|remove|rename|move|copy|save|write)\b.{0,30}\b(file|folder|directory|note)s?\b",
                re.I), "asks to change files"),
    (re.compile(r"\b(find|search|look\s+for|locate|list|show)\b.{0,40}\b(files?|folders?|pdfs?|docs?|documents)\b", re.I),
     "asks to find local files"),
    (re.compile(r"\b(read|summari[sz]e|open|show)\b.{0,20}\b(the|this|that|these)\s+(file|pdf|document|folder)s?\b", re.I),
     "asks about a local file"),
    (re.compile(r"\b(how\s+much|free|available|used|usage|left|remaining|right\s+now|currently)\b.{0,25}"
                r"\b(ram|memory|cpu|disk|storage|space|battery)\b", re.I), "asks about this PC's state"),
    (re.compile(r"\b(ram|memory|cpu|disk|storage|battery)\b.{0,25}\b(usage|used|free|left|available|level|status)\b", re.I),
     "asks about this PC's state"),
    (re.compile(r"\b(running|open)\s+(apps|applications|programs|processes|windows)\b", re.I), "asks about running apps"),
    (re.compile(r"\b(e-?mail|mail|gmail|draft)\b.{0,60}\b(to|for)\b|\b(send|write|draft|compose|reply)\b.{0,30}"
                r"\b(e-?mails?|mails?|gmail)\b", re.I), "involves your email"),
    (re.compile(r"\b(type|press|hit)\b.{0,40}\b(in|into|on)\b", re.I), "asks to type or press keys"),
    (re.compile(r"^\W*(send|submit)\s+(it|this|that)\b", re.I), "asks to send something"),
    (re.compile(r"\b(whats\s?app|voice\s+(message|note|msg)|voice\s*mail)\b", re.I), "involves WhatsApp / voice messages"),
    (re.compile(r"\b(schedul\w*|remind\s+me|reminders?)\b", re.I), "involves your schedule"),
    (re.compile(r"\b(tell|message|text|ping)\s+(?!me\b|us\b)\w+\s+(that|to)\b", re.I), "asks to message someone"),
    (re.compile(r"\b(apps|applications|programs|processes)\b.{0,15}\b(running|open)\b", re.I), "asks about running apps"),
]

WEB_PATTERN = re.compile(
    r"\b(search\s+(the\s+)?(web|internet|online)|google\s+(it|this|that|for)|look\s+(it\s+|this\s+)?up|online|"
    r"on\s+the\s+(web|internet)|latest|newest|recent(ly)?|today'?s?|tonight|tomorrow|yesterday|this\s+(week|month|year)|"
    r"news|headlines|current(ly)?|right\s+now|weather|forecast|(will\s+it|going\s+to)\s+rain|raining|temperature\s+(in|at|today)|price\s+of|stock|"
    r"exchange\s+rate|score|what'?s\s+new|"
    r"release\s+date|released|just\s+(came\s+out|launched)|20(2[5-9]|3\d))\b", re.I)


EXAMPLES = {
    Route.DEVICE: [
        "open chrome", "launch vs code", "find my resume", "what's in my downloads folder",
        "how much ram is free", "read the pdf I just found", "create a folder for my project",
        "close notepad", "show my files", "open the second one", "summarize that document",
        "check my battery", "which apps are using the most memory", "search my laptop for notes",
    ],
    Route.WEB: [
        "what's the latest news about AI", "search the web for python 3.15 changes",
        "what is the weather in Delhi", "who won the match yesterday", "current price of bitcoin",
        "find recent articles about CUDA 13", "what happened today", "look up the release date of the new iPhone",
    ],
    Route.CHAT: [
        "explain how CUDA shared memory works", "what is the difference between a list and a tuple",
        "write a poem about rain", "help me debug this python error", "summarize the french revolution",
        "translate this sentence to Hindi", "give me tips for an interview", "what is recursion",
    ],
}


class Router:
    DEVICE_THRESHOLD = 0.62
    DEVICE_MARGIN = 0.04

    def __init__(self, embedder=None):
        self._embedder = embedder
        self._example_vectors = None
        self._lock = threading.Lock()


    @property
    def has_embedder(self) -> bool:
        return self._embedder is not None

    def set_embedder(self, embedder) -> None:
        """embedder: callable(list[str]) -> list[vector]."""
        vectors = {route: [_unit(v) for v in embedder(texts)] for route, texts in EXAMPLES.items()}
        with self._lock:
            self._embedder, self._example_vectors = embedder, vectors

    def load_default_embedder(self, cache_dir) -> None:
        """Loads a small local embedding model (fastembed, ~130 MB, runs on CPU). Safe to call in a thread."""
        from fastembed import TextEmbedding
        model = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=str(cache_dir))
        self.set_embedder(lambda texts: list(model.embed(list(texts))))


    def decide(self, text: str, *, cloud_enabled: bool = True) -> Decision:
        stripped = text.strip()
        if stripped.casefold().startswith("/local"):
            return Decision(Route.DEVICE, "you asked for local (/local)")
        if not cloud_enabled:
            return Decision(Route.DEVICE, "cloud AI is turned off")
        for pattern, reason in DEVICE_PATTERNS:
            if pattern.search(stripped):
                return Decision(Route.DEVICE, reason)
        if WEB_PATTERN.search(stripped):
            return Decision(Route.WEB, "needs current information")
        with self._lock:
            embedder, examples = self._embedder, self._example_vectors
        if embedder is not None and examples:
            query = _unit(embedder([stripped])[0])
            scores = {route: max(_dot(query, v) for v in vecs) for route, vecs in examples.items()}
            best = max(scores, key=scores.get)
            device = scores[Route.DEVICE]
            if device >= self.DEVICE_THRESHOLD and device >= scores[best] - self.DEVICE_MARGIN:
                return Decision(Route.DEVICE, f"sounds like a device request ({device:.2f})")
            if best is Route.WEB:
                return Decision(Route.WEB, f"sounds like it needs the web ({scores[best]:.2f})")
        return Decision(Route.CHAT, "general question, no device data involved")


def _dot(a, b) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


def _unit(v):
    v = [float(x) for x in v]
    norm = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / norm for x in v]
