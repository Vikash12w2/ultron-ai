from __future__ import annotations

import io
import re
import wave
from pathlib import Path

from voice.audio import play


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:1500]


def apply_effect(audio, rate: int, effect: str = "none"):
    """"synthetic": ULTRON's own AI voice. Deeper and a little slower, with a faint metallic edge and a
    short digital echo."""
    import numpy as np
    if effect != "synthetic" or len(audio) == 0:
        return audio
    from voice.audio import resample
    slowed = resample(audio, rate, int(rate / 0.9))
    t = np.arange(len(slowed)) / rate
    metallic = slowed * np.sin(2 * np.pi * 55 * t)
    out = 0.85 * slowed + 0.22 * metallic
    delay = int(rate * 0.035)
    echo = np.zeros_like(out)
    echo[delay:] = out[:-delay] * 0.28
    out = out + echo
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.9).astype(np.float32)


def synthesize(text: str, voice_path: str, effect: str | None = None):
    """Returns (float32 mono audio, sample_rate). effect: "none" or "synthetic" (default: the saved setting)."""
    path = Path(voice_path or "")
    if not path.is_file():
        raise RuntimeError("Choose a Piper voice (.onnx) in Settings → Voice & data first.")
    if not Path(str(path) + ".json").is_file():
        raise RuntimeError("The Piper voice's matching .onnx.json file is missing.")
    import numpy as np
    from piper import PiperVoice
    voice = PiperVoice.load(str(path))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        voice.synthesize_wav(clean_for_speech(text), wav)
    buffer.seek(0)
    with wave.open(buffer, "rb") as wav:
        rate, width = wav.getframerate(), wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise RuntimeError(f"Unexpected Piper audio format ({width * 8}-bit).")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if effect is None:
        effect = _saved_effect()
    return apply_effect(audio, rate, effect), rate


def _saved_effect() -> str:
    try:
        from config import DATABASE
        from memory.database import Database
        return Database(DATABASE).get("voice_effect", "synthetic")
    except Exception:
        return "none"


def speak(text: str, voice_path: str) -> None:
    audio, rate = synthesize(text, voice_path)
    play(audio, rate)
