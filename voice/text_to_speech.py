from __future__ import annotations
import io
import wave
from pathlib import Path


class PiperSpeaker:
    def __init__(self,voice_model_path,audio_manager):
        self.voice_model_path=Path(voice_model_path).expanduser() if voice_model_path else None
        self.audio_manager=audio_manager

    def speak(self,text):
        if not self.voice_model_path or not self.voice_model_path.is_file():
            raise RuntimeError("Choose a local Piper .onnx voice model in Settings before using speech output.")
        if not self.voice_model_path.with_suffix(self.voice_model_path.suffix+".json").is_file():
            raise RuntimeError("The Piper voice's matching .onnx.json configuration file is missing.")
        try:from piper import PiperVoice
        except ImportError as exc:raise RuntimeError("Speech output needs the optional piper-tts package.") from exc
        try:
            voice=PiperVoice.load(self.voice_model_path)
            buffer=io.BytesIO()
            with wave.open(buffer,"wb") as wav:voice.synthesize_wav(text[:4000],wav)
            buffer.seek(0)
            with wave.open(buffer,"rb") as wav:
                width=wav.getsampwidth();channels=wav.getnchannels();rate=wav.getframerate();raw=wav.readframes(wav.getnframes())
            import numpy as np
            dtype={1:np.int8,2:np.int16,4:np.int32}.get(width)
            if dtype is None:raise RuntimeError(f"Unsupported Piper audio sample width: {width} bytes.")
            audio=np.frombuffer(raw,dtype=dtype).astype(np.float32)/(2**(width*8-1))
            if channels>1:audio=audio.reshape(-1,channels)
            self.audio_manager.play(audio,rate)
        except RuntimeError:raise
        except Exception as exc:raise RuntimeError(f"Piper speech generation failed: {exc}") from exc
