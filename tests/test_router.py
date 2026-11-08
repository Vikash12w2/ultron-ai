import pytest

from core.router import Route, Router

DEVICE = [
    "open chrome", "Ultron, open VS Code and find my CUDA image processing project", "find my resume",
    "what's in my downloads folder", "how much RAM is free right now", "read C:\\Users\\me\\notes.txt",
    "summarize report.pdf", "create a folder called AI Projects in Documents", "close notepad",
    "check my battery", "search my notes for cuda kernels", "open my github project folder",
    "look up my CUDA project in VS Code", "show me the files in downloads", "open youtube in chrome",
    "list all pdf files", "which apps are running", "open the second one",
]
WEB = ["what's the latest news about AI", "search the web for python 3.15 changes", "weather in Delhi today",
       "current price of bitcoin", "who won the match yesterday"]
CHAT = ["explain how CUDA shared memory works", "why is my cuda code not working?", "write a short poem about rain",
        "what is the difference between a list and a tuple", "how do I read a file in python?"]


@pytest.mark.parametrize("text", DEVICE)
def test_device_requests_stay_local(text):
    assert Router().decide(text).route is Route.DEVICE


@pytest.mark.parametrize("text", WEB)
def test_current_info_goes_to_web(text):
    assert Router().decide(text).route is Route.WEB


@pytest.mark.parametrize("text", CHAT)
def test_general_questions_go_to_chat(text):
    assert Router().decide(text).route is Route.CHAT


def test_overrides_force_local():
    r = Router()
    assert r.decide("explain recursion", cloud_enabled=False).route is Route.DEVICE
    assert r.decide("/local explain recursion").route is Route.DEVICE


def _bag_of_words(texts):
    vocab = ["apps", "memory", "using", "most", "news", "latest", "explain", "works", "file", "folder", "battery",
             "hogging", "eating", "headlines"]
    synonyms = {"hogging": "using", "eating": "using", "headlines": "news"}
    out = []
    for t in texts:
        words = [synonyms.get(w, w) for w in t.lower().replace("?", "").split()]
        out.append([float(words.count(v)) for v in vocab] + [0.01])
    return out


def test_embedding_check_catches_device_requests_without_keywords():
    r = Router()
    r.set_embedder(_bag_of_words)
    assert r.decide("which apps are hogging the most memory").route is Route.DEVICE
    assert r.decide("give me the headlines").route is Route.WEB
