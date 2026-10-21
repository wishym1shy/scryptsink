"""Make a test clip with KNOWN line timings from espeak-ng speech. Usage: make_test_clip.py outdir"""
import subprocess, sys, os, wave, json
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
SPOKEN = [  # what is actually said
 "Hey guys welcome to Riverside Auto today",
 "Quick tip before we start",                       # ad-lib, not in script
 "We have the brand new Sorento with a three row interior",
 "It starts at twenty five thousand dollars",
 "This line is in the script but nobody says it" if False else None,
 "Come visit us today",
]
SPOKEN = [s for s in SPOKEN if s]
rate = 22050
segs, truth, t = [], [], 0.6
silence = lambda sec: b"\x00\x00" * int(rate * sec)
pcm = silence(0.6)
for i, line in enumerate(SPOKEN):
    wav = os.path.join(out, f"l{i}.wav")
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", wav, line], check=True)
    w = wave.open(wav); assert w.getframerate() == rate, w.getframerate(); data = w.readframes(w.getnframes()); w.close()
    dur = len(data) / 2 / rate
    truth.append({"text": line, "start": t, "end": t + dur})
    pcm += data + silence(0.7); t += dur + 0.7
w = wave.open(os.path.join(out, "all.wav"), "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm); w.close()
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x203040:s=270x480:d={t:.2f}:r=30", "-i", os.path.join(out, "all.wav"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(out, "testclip.mp4")], check=True)
json.dump(truth, open(os.path.join(out, "truth.json"), "w"), indent=1)
open(os.path.join(out, "testclip.txt"), "w").write(
 "Hey guys, welcome to Riverside Auto today.\n"
 "We have the brand new Sorento with a three-row interior.\n"
 "It starts at $25,000.\n"
 "Comes with a free oil change for life!\n"       # in script, never spoken
 "Come visit us today!\n")
print("ok", t)
