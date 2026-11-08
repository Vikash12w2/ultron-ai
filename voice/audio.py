from __future__ import annotations

import threading

TARGET_RATE = 16000


class AudioRecorder:
    def __init__(self, max_seconds: int = 30):
        self.max_seconds = max_seconds
        self._lock = threading.Lock()
        self._chunks: list = []
        self._sample_count = 0
        self._stream = None
        self._rate = TARGET_RATE
        self._error = None

    def start(self) -> None:
        import sounddevice as sd
        if self._stream is not None:
            raise RuntimeError("Already recording.")
        try:
            device = sd.query_devices(kind="input")
        except Exception as exc:
            raise RuntimeError("No microphone found. Check Windows Settings → Privacy & security → Microphone "
                               "→ 'Let desktop apps access your microphone'.") from exc
        self._rate = int(device.get("default_samplerate") or 48000)
        with self._lock:
            self._chunks, self._sample_count, self._error = [], 0, None
        try:
            self._stream = sd.InputStream(samplerate=self._rate, channels=1, dtype="float32", callback=self._callback)
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise RuntimeError(f"Couldn't open the microphone ({exc}). Check Windows Settings → Privacy & security "
                               "→ Microphone → 'Let desktop apps access your microphone'.") from exc

    def _callback(self, indata, _frames, _time, status):
        with self._lock:
            if status and getattr(status, "input_overflow", False):
                self._error = "The microphone dropped audio while recording. Please try again."
            remaining = self._rate * self.max_seconds - self._sample_count
            if remaining > 0:
                chunk = indata[:remaining, 0].copy()
                self._chunks.append(chunk)
                self._sample_count += len(chunk)

    def stop(self):
        """Returns float32 mono audio at 16 kHz."""
        import numpy as np
        stream, self._stream = self._stream, None
        if stream is None:
            raise RuntimeError("Not recording.")
        stream.stop()
        stream.close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
            error, self._error = self._error, None
            self._sample_count = 0
        if error:
            raise RuntimeError(error)
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        if len(audio) < self._rate * 0.3:
            raise RuntimeError("That was too short. Hold the mic button while you speak.")
        return resample(audio, self._rate, TARGET_RATE)


def resample(audio, rate: int, target: int = TARGET_RATE):
    import numpy as np
    if rate == target or len(audio) == 0:
        return audio.astype(np.float32)
    duration = len(audio) / rate
    new_len = int(round(duration * target))
    old_t = np.linspace(0.0, duration, num=len(audio), endpoint=False)
    new_t = np.linspace(0.0, duration, num=new_len, endpoint=False)
    return np.interp(new_t, old_t, audio).astype(np.float32)


def play(audio, rate: int) -> None:
    import sounddevice as sd
    sd.play(audio, samplerate=rate, blocking=True)
