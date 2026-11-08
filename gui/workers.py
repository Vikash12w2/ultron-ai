from PySide6.QtCore import QObject, QRunnable, Signal
import threading

class WorkerSignals(QObject):
    result=Signal(object)
    error=Signal(str)
    finished=Signal()
    approval_requested=Signal(str,str,object)
    status=Signal(str)

class ChatWorker(QRunnable):
    def __init__(self,agent,conversation_id,text):
        super().__init__(); self.agent,self.conversation_id,self.text=agent,conversation_id,text; self.signals=WorkerSignals()
        self.agent.approval=lambda n,a,d:self.ask_approval(n,a,d)
        self.agent.status=self.signals.status.emit
    def ask_approval(self,name,args,description):
        event=threading.Event(); state={"approved":False}
        self.signals.approval_requested.emit(name,description,(event,state)); event.wait(); return state["approved"]
    def run(self):
        try: self.signals.result.emit(self.agent.respond(self.conversation_id,self.text))
        except Exception as exc: self.signals.error.emit(str(exc))
        finally: self.signals.finished.emit()
