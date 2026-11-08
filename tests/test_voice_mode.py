import numpy as np
import pytest

from voice.listen import SpeechSegmenter
from voice.tts import apply_effect

RATE = 16000


def _blocks(seconds, amp):
    n = int(RATE * 0.03)
    t = np.arange(n) / RATE
    return [amp * np.sin(2 * np.pi * 220 * t).astype("float32") for _ in range(int(seconds / 0.03))]


def test_segmenter_captures_speech_and_stops_after_silence():
    seg = SpeechSegmenter(RATE, silence_after=0.5)
    feed = _blocks(0.5, 0.002) + _blocks(1.0, 0.2) + _blocks(1.0, 0.002)
    result = None
    for b in feed:
        result = seg.feed(b)
        if result:
            break
    assert result == "done"
    audio = seg.audio()
    assert 1.0 <= len(audio) / RATE <= 2.0


def test_segmenter_times_out_when_nobody_speaks():
    seg = SpeechSegmenter(RATE, start_timeout=1.0)
    results = [seg.feed(b) for b in _blocks(1.5, 0.002)]
    assert "timeout" in results


def test_synthetic_voice_effect_is_deeper_and_safe():
    tone = np.sin(2 * np.pi * 200 * np.arange(RATE) / RATE).astype("float32") * 0.5
    out = apply_effect(tone, RATE, "synthetic")
    assert len(out) > len(tone) and np.max(np.abs(out)) <= 0.91
    assert apply_effect(tone, RATE, "none") is tone


pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_voice_loop_listens_thinks_and_listens_again(app, db):
    from PySide6.QtCore import QThreadPool
    from gui.voice_mode import VoiceModeWindow

    submitted = []

    def submit(text, on_reply):
        submitted.append(text)
        on_reply("It's 3 PM.")
        return True

    w = VoiceModeWindow(submit, QThreadPool.globalInstance(), db)
    w.active = True
    w.listen = lambda: setattr(w, "listened", getattr(w, "listened", 0) + 1)
    w.on_heard("what time is it")
    assert submitted == ["what time is it"] and "3 PM" in w.reply.text()
    w.listen_later()
    w.on_heard("goodbye")
    assert submitted == ["what time is it"] and not w.active


def test_main_window_hides_to_tray_and_submit_calls_back(app, db, monkeypatch):
    from gui.main_window import MainWindow
    db.set("smart_routing", False)
    w = MainWindow(db=db)
    w.show()
    replies = []

    class FakeReply:
        text, provider, note = "hello back", "Local · test", ""

    w._reply_callback = replies.append
    w.busy_cid = w.cid
    w.on_reply(w.cid, FakeReply())
    assert replies == ["hello back"]
    if w.tray:
        w.close()
        assert not w.isVisible()
    w.timer.stop()
    w.schedule_timer.stop()
    w._quitting = True
    w.close()
