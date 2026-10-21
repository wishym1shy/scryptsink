"""GUI-test-only recogniser: replays ground truth (truth.json beside the clip) as if a good model heard it."""
import json, os
def transcribe(path, language, hint, progress, cancel):
    import time
    truth = json.load(open(os.path.join(os.path.dirname(path), "truth.json")))
    words = []
    for i in range(10):
        progress(0.1 + i * 0.07, "Listening to the clip"); time.sleep(0.05)
    for seg in truth:
        ws = seg["text"].split(); step = (seg["end"] - seg["start"]) / len(ws)
        for k, w in enumerate(ws):
            if w == "Sorento": w = "Sorrento"
            if os.environ.get("FAKE_NOISY") and (len(words) % 4 == 3): w = "banana"
            if os.environ.get("FAKE_NOISY") and w == "brand": continue
            words.append((w, seg["start"] + k * step, seg["start"] + (k + 1) * step - 0.03, 0.9))
    return words, truth[-1]["end"] + 0.7, "en"
