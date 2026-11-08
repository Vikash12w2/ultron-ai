import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

import shutil
import time
import uuid
from pathlib import Path

import pytest

from config import MODEL,OLLAMA_HOST
from core.agent import Agent
from memory.database import Database
from security.path_security import PathSecurity
from tools.registry import ToolRegistry

pytestmark=pytest.mark.skipif(os.environ.get("ULTRON_RUN_LIVE_TESTS")!="1",reason="Live checks require explicit opt-in.")


@pytest.fixture(scope="module")
def live_sandbox():
    root=Path(__file__).parent/".test-data"/("live-"+uuid.uuid4().hex)
    roots=[]
    for name in ("Desktop","Documents","Downloads"):
        folder=root/name;folder.mkdir(parents=True);roots.append(folder)
    try:yield root,roots
    finally:shutil.rmtree(root,ignore_errors=True)


@pytest.fixture
def live_agent(live_sandbox):
    root,roots=live_sandbox
    db=Database(root/"state"/(uuid.uuid4().hex+".db"));ident=db.new_conversation()
    agent=Agent(db,model=MODEL,host=OLLAMA_HOST)
    agent.registry=ToolRegistry(roots)
    return agent,ident,db


def test_live_qwen_chat_memory_and_worker_responsiveness(live_agent,record_property):
    from PySide6.QtCore import QCoreApplication,QEventLoop,QThreadPool,QTimer
    from gui.workers import ChatWorker
    import psutil

    app=QCoreApplication.instance() or QCoreApplication([])
    agent,ident,_=live_agent
    threading=__import__("threading");main_thread=threading.get_ident();state={"ticks":0,"ram_peak_gb":0.0}
    start=time.perf_counter();baseline=psutil.virtual_memory().used
    original_chat=agent.provider.chat
    def track_model_thread(*args,**kwargs):
        state["model_thread"]=threading.get_ident()
        return original_chat(*args,**kwargs)
    agent.provider.chat=track_model_thread
    worker=ChatWorker(agent,ident,"Remember this test token: ORANGE-742. Reply with the token only.")
    loop=QEventLoop();worker.signals.result.connect(lambda _conversation,value:state.update(first=value));worker.signals.error.connect(lambda _conversation,value:state.update(error=value))
    def finished():state.update(finished=True);loop.quit()
    worker.signals.finished.connect(lambda _conversation:finished())
    heartbeat=QTimer();heartbeat.setInterval(50);heartbeat.timeout.connect(lambda:state.update(ticks=state["ticks"]+1,ram_peak_gb=max(state["ram_peak_gb"],(psutil.virtual_memory().used-baseline)/1024**3)));heartbeat.start()
    timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(loop.quit);timeout.start(180000)
    pool=QThreadPool();pool.start(worker);loop.exec();heartbeat.stop()
    if not state.get("finished"):pool.waitForDone(1000)
    assert state.get("finished"),"Qwen inference exceeded the 180 second live-test limit."
    assert "error" not in state and state.get("first")
    assert state.get("ticks",0)>0 and state.get("model_thread")!=main_thread
    assert state.get("first") and "ORANGE" in state["first"].upper()
    response_start=time.perf_counter();followup=agent.respond(ident,"What test token did I ask you to remember? Reply with the token only.")
    duration=time.perf_counter()-start
    assert "ORANGE-742" in followup.upper()
    record_property("qwen_first_response_seconds",round(response_start-start,2))
    record_property("qwen_total_two_turns_seconds",round(duration,2))
    record_property("system_ram_peak_increase_gb",round(state["ram_peak_gb"],2))
    assert app is not None and main_thread!=0


@pytest.mark.parametrize("app_name",["chrome","vscode","notepad"])
def test_live_registered_app_launches_and_verifies(app_name):
    from tools.applications import ApplicationTools
    result=ApplicationTools().open_app(app_name)
    assert result["status"] in ("launched","already_running"),result


def test_live_chatgpt_opens_in_chrome(live_agent):
    agent,ident,_=live_agent
    answer=agent.respond(ident,"Open ChatGPT in Chrome")
    assert "https://chatgpt.com" in answer and ("Chrome" in answer or "chrome" in answer)


def test_live_file_search_read_and_open_fixture(live_agent,live_sandbox):
    agent,ident,_=live_agent
    _,roots=live_sandbox;downloads=roots[2]
    older=downloads/"resume-older.txt";latest=downloads/"resume-v1-live-fixture.txt"
    older.write_text("older fixture",encoding="utf-8");latest.write_text("ULTRON live acceptance fixture",encoding="utf-8")
    os.utime(older,(100,100));os.utime(latest,(200,200))
    listed=agent.respond(ident,"List the files in my Downloads folder")
    assert "resume-v1-live-fixture.txt" in listed
    found=agent.respond(ident,"Find my resume in Downloads")
    assert "resume-v1-live-fixture.txt" in found
    reader=agent.registry.fs.read_file(str(latest))
    assert "acceptance fixture" in reader
    opened=agent.respond(ident,"Open my latest resume")
    assert "resume-v1-live-fixture.txt" in opened and "Opened" in opened


def test_live_web_search_returns_results_and_discloses_query(live_agent):
    agent,ident,db=live_agent;status=[];agent.status=status.append
    query="CUDA programming tutorials NVIDIA"
    answer=agent.respond(ident,f"Search the web for {query}")
    assert status==[f"Searching the web: {query}"]
    assert "Web results for" in answer and "https://" in answer
    assert db.action_logs()[0]["tool"]=="web_search"


def test_live_system_info_reads_cpu_and_memory(live_agent):
    agent,ident,_=live_agent
    from tools.system_info import system_info
    current=system_info("overview")
    assert 0<=current["cpu_percent"]<=100 and current["ram_total_gb"]>0
    assert current["ram_available_gb"]>=0
