from __future__ import annotations
import gc
from pathlib import Path


class SpeechToText:
    def __init__(self,model_name="base",device="cpu",compute_type="int8",download_root=None):
        self.model_name=model_name;self.device=device;self.compute_type=compute_type
        self.download_root=download_root;self._model=None

    def _load(self):
        if self._model is not None:return self._model
        try:from faster_whisper import WhisperModel
        except ImportError as exc:raise RuntimeError("Speech recognition needs the optional faster-whisper package.") from exc
        try:
            self._model=WhisperModel(self.model_name,device=self.device,compute_type=self.compute_type,
                download_root=str(self.download_root) if self.download_root else None,local_files_only=True)
        except Exception as exc:
            raise RuntimeError("The Faster-Whisper base model isn't available in the local cache. ULTRON did not download it. Select or download the model before using voice input.") from exc
        return self._model

    def model_available_locally(self):
        if Path(self.model_name).expanduser().is_dir():
            return (Path(self.model_name).expanduser()/"model.bin").is_file()
        try:
            from huggingface_hub import try_to_load_from_cache
            return try_to_load_from_cache("Systran/faster-whisper-base","model.bin") is not None
        except Exception:
            return False

    def transcribe(self,audio):
        if audio is None or len(audio)==0:raise ValueError("There is no recorded audio to transcribe.")
        model=self._load()
        try:segments,_info=model.transcribe(audio,beam_size=1,vad_filter=True)
        except Exception as exc:raise RuntimeError(f"Speech recognition failed: {exc}") from exc
        text=" ".join(segment.text.strip() for segment in segments).strip()
        if not text:raise RuntimeError("I couldn't make out speech in that recording. Try again or type your message.")
        return text

    def unload(self):
        self._model=None;gc.collect()
