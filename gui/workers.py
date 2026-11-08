from PySide6.QtCore import QObject, QRunnable, Signal
import threading

class WorkerSignals(QObject):
    result=Signal(str,object)
    error=Signal(str,str)
    finished=Signal(str)
    approval_requested=Signal(str,str,object)
    status=Signal(str,str)

class VoiceSignals(QObject):
    result=Signal(str)
    error=Signal(str)
    finished=Signal()

class ChatWorker(QRunnable):
    def __init__(self,agent,conversation_id,text):
        super().__init__(); self.agent,self.conversation_id,self.text=agent,conversation_id,text; self.signals=WorkerSignals()
        self.agent.approval=lambda n,a,d:self.ask_approval(n,a,d)
        self.agent.status=lambda message:self.signals.status.emit(self.conversation_id,message)
    def ask_approval(self,name,args,description):
        event=threading.Event(); state={"approved":False}
        self.signals.approval_requested.emit(name,description,(event,state)); event.wait(); return state["approved"]
    def run(self):
        try: self.signals.result.emit(self.conversation_id,self.agent.respond(self.conversation_id,self.text))
        except Exception as exc: self.signals.error.emit(self.conversation_id,str(exc))
        finally: self.signals.finished.emit(self.conversation_id)

class SpeechWorker(QRunnable):
    def __init__(self,transcriber,audio):
        super().__init__();self.transcriber,self.audio=transcriber,audio;self.signals=VoiceSignals()
    def run(self):
        try:self.signals.result.emit(self.transcriber.transcribe(self.audio))
        except Exception as exc:self.signals.error.emit(str(exc))
        finally:
            self.transcriber.unload();self.signals.finished.emit()

class SpeechOutputWorker(QRunnable):
    def __init__(self,voice_path,audio_manager,text):
        super().__init__();self.voice_path,self.audio_manager,self.text=voice_path,audio_manager,text;self.signals=VoiceSignals()
    def run(self):
        try:
            from voice.text_to_speech import PiperSpeaker
            PiperSpeaker(self.voice_path,self.audio_manager).speak(self.text)
        except Exception as exc:self.signals.error.emit(str(exc))
        finally:self.signals.finished.emit()
