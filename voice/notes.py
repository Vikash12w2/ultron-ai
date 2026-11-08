from __future__ import annotations

from datetime import datetime
from pathlib import Path

from voice.audio import resample

OPUS_RATES = (8000, 12000, 16000, 24000, 48000)


def note_path(folder: Path, recipient: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch for ch in recipient if ch.isalnum() or ch in " _-").strip().replace(" ", "_") or "contact"
    return folder / f"ULTRON_{safe}_{datetime.now():%Y%m%d_%H%M%S}.ogg"


def write_voice_note(audio, rate: int, out: Path) -> Path:
    import numpy as np
    import soundfile as sf
    if len(audio) == 0:
        raise ValueError("The recording is empty.")
    target = rate if rate in OPUS_RATES else 24000
    data = resample(np.asarray(audio, dtype=np.float32), rate, target)
    peak = float(np.max(np.abs(data))) or 1.0
    if peak > 1.0:
        data = data / peak
    sf.write(str(out), data, target, format="OGG", subtype="OPUS")
    return out
