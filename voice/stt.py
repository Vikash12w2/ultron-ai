from __future__ import annotations

import gc

from config import MODEL_CACHE


class SpeechToText:
    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self._model = None

    def transcribe(self, audio) -> str:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8",
                                       download_root=str(MODEL_CACHE / "whisper"))
        segments, _info = self._model.transcribe(audio, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            raise RuntimeError("I couldn't make out any speech. Try again or type it.")
        return text

    def unload(self) -> None:
        self._model = None
        gc.collect()
