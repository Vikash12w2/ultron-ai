from __future__ import annotations
import threading


class AudioManager:
    def __init__(self,sample_rate=16000,max_seconds=30):
        self.sample_rate=sample_rate;self.max_samples=sample_rate*max_seconds
        self._lock=threading.Lock();self._chunks=[];self._samples=0;self._stream=None;self._callback_error=None

    def start_recording(self):
        try:import sounddevice as sd
        except ImportError as exc:raise RuntimeError("Voice recording needs the optional sounddevice package.") from exc
        if self._stream is not None:raise RuntimeError("A recording is already in progress.")
        with self._lock:self._chunks=[];self._samples=0;self._callback_error=None
        try:
            self._stream=sd.InputStream(samplerate=self.sample_rate,channels=1,dtype="float32",callback=self._record_callback)
            self._stream.start()
        except Exception as exc:
            self._stream=None
            raise RuntimeError(f"Couldn't start microphone recording: {exc}") from exc

    def _record_callback(self,indata,frames,_time_info,status):
        with self._lock:
            if status:self._callback_error=str(status)
            available=max(0,self.max_samples-self._samples)
            if available:
                chunk=indata[:available,0].copy()
                self._chunks.append(chunk);self._samples+=len(chunk)

    def stop_recording(self):
        stream,self._stream=self._stream,None
        if stream is None:raise RuntimeError("No microphone recording is active.")
        try:stream.stop();stream.close()
        except Exception as exc:raise RuntimeError(f"Couldn't stop microphone recording cleanly: {exc}") from exc
        import numpy as np
        with self._lock:
            chunks,self._chunks=self._chunks,[];count=self._samples;error=self._callback_error
        if error:raise RuntimeError(f"Microphone recording failed: {error}")
        if count<int(self.sample_rate*0.25):raise RuntimeError("Recording was too short. Hold the microphone button while speaking.")
        return np.concatenate(chunks) if chunks else np.zeros(0,dtype=np.float32)

    @staticmethod
    def play(audio,sample_rate):
        try:import sounddevice as sd
        except ImportError as exc:raise RuntimeError("Voice playback needs the optional sounddevice package.") from exc
        try:sd.play(audio,samplerate=sample_rate,blocking=True)
        except Exception as exc:raise RuntimeError(f"Couldn't play voice audio: {exc}") from exc
