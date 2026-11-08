from __future__ import annotations

import queue
import threading
from collections import deque

from voice.audio import TARGET_RATE, resample


class SpeechSegmenter:
    """Feed it audio blocks; it decides when an utterance starts and ends.

    - The first `calibrate` seconds measure background noise, using a median to ignore brief sounds.
    - Sensitivity adjusts the threshold above that noise (higher values detect quieter speech).
    - Two of the last three blocks must cross the threshold before recording starts.
    - The utterance ends after `silence_after` seconds of quiet, or at `max_seconds`.
    - If nobody speaks within `start_timeout` seconds it gives up ("timeout").
    """

    def __init__(self, rate: int, *, calibrate=0.6, silence_after=1.8, start_timeout=15.0, max_seconds=45.0,
                 sensitivity=70, preroll=0.4):
        self.rate = rate
        self.calibrate, self.silence_after = calibrate, silence_after
        self.start_timeout, self.max_seconds = start_timeout, max_seconds
        self.sensitivity = max(0, min(100, int(sensitivity)))
        self.preroll = preroll
        self.elapsed = 0.0
        self.noise = []
        self.noise_floor = 0.0
        self.threshold = self._threshold(0.0)
        self.speaking = False
        self.quiet_for = 0.0
        self.speech_time = 0.0
        self.blocks: list = []
        self.level = 0.0
        self._recent_rms = deque(maxlen=3)
        self._start_hits = deque(maxlen=3)

    def _threshold(self, noise_floor: float) -> float:

        amount = self.sensitivity / 100.0
        floor = 0.0035 - amount * 0.0029
        multiplier = 3.0 - amount * 1.75
        return max(floor, noise_floor * multiplier)

    def feed(self, block) -> str | None:
        import numpy as np
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        dur = len(block) / self.rate
        self.elapsed += dur
        rms = float(np.sqrt(np.mean(block * block))) if len(block) else 0.0
        self._recent_rms.append(rms)
        smoothed = sorted(self._recent_rms)[len(self._recent_rms) // 2]
        self.level = min(1.0, smoothed * 12)
        if self.elapsed <= self.calibrate:
            self.noise.append(rms)
            self.blocks.append(block)
            return None
        if self.noise:
            self.noise_floor = float(np.median(self.noise))
            self.threshold = self._threshold(self.noise_floor)
            self.noise = []
        self.blocks.append(block)
        if not self.speaking:
            keep = int(self.preroll * self.rate)
            total = sum(len(b) for b in self.blocks)
            while self.blocks and total - len(self.blocks[0]) >= keep:
                total -= len(self.blocks.pop(0))
            self._start_hits.append(smoothed > self.threshold)
            if sum(self._start_hits) >= 2:
                self.speaking = True
                self._start_hits.clear()
            else:

                if smoothed <= self.threshold * 1.4:
                    self.noise_floor = self.noise_floor * 0.97 + smoothed * 0.03
                    self.threshold = self._threshold(self.noise_floor)
            if not self.speaking and self.elapsed > self.start_timeout:
                return "timeout"
            if not self.speaking:
                return None
        self.speech_time += dur

        quiet_threshold = max(self.noise_floor * 1.12, self.threshold * 0.65)
        self.quiet_for = 0.0 if smoothed > quiet_threshold else self.quiet_for + dur
        if self.quiet_for >= self.silence_after or self.speech_time >= self.max_seconds:
            return "done"
        return None

    def audio(self):
        import numpy as np
        return np.concatenate(self.blocks) if self.blocks else np.zeros(0, dtype=np.float32)


def listen(level_cb=lambda _l: None, cancel: threading.Event | None = None, **segmenter_options):
    """Blocks until one utterance is captured. Returns 16 kHz float32 audio, or None if nobody spoke / cancelled."""
    import sounddevice as sd
    try:
        rate = int(sd.query_devices(kind="input").get("default_samplerate") or 48000)
    except Exception as exc:
        raise RuntimeError("No microphone found. Check Windows Settings → Privacy & security → Microphone.") from exc
    seg = SpeechSegmenter(rate, **segmenter_options)
    blocks: queue.Queue = queue.Queue(maxsize=120)
    cancel = cancel or threading.Event()
    overflow = threading.Event()

    def callback(data, _frames, _time, status):
        if status and getattr(status, "input_overflow", False):
            overflow.set()
        try:
            blocks.put_nowait(data[:, 0].copy())
        except queue.Full:
            overflow.set()

    with sd.InputStream(samplerate=rate, channels=1, dtype="float32", blocksize=int(rate * 0.03),
                        callback=callback):
        while not cancel.is_set():
            if overflow.is_set():
                raise RuntimeError("Microphone audio was interrupted by a buffer overrun. Please try again.")
            try:
                block = blocks.get(timeout=0.1)
            except queue.Empty:
                continue
            result = seg.feed(block)
            level_cb(seg.level)
            if result == "timeout":
                return None
            if result == "done":
                return resample(seg.audio(), rate, TARGET_RATE)
    return None
