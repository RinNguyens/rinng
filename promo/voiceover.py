"""Add an English Kokoro voiceover to rinng-promo.mp4.

Usage: python voiceover.py MODEL_DIR [voice] [speed] [out.mp4]
MODEL_DIR holds kokoro-v1.0.onnx and voices-v1.0.bin (kokoro-onnx model files).
Needs: kokoro-onnx, soundfile, ffmpeg.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
# (start second, line). "Ring" is how the voice should say rinng.
LINES = [
    (0.25, "Stop guessing the market. Start measuring it."),
    (3.6, "Ring collects every bar and every tick from Binance and OKX. No API keys."),
    (9.7, "It maps order blocks, fair value gaps, liquidity, and volume profile."),
    (16.2, "It forecasts the next bars as a probability cone, validated walk-forward."),
    (21.9, "Then it backtests your strategy, with fees and slippage included."),
    (27.5, "And it streams everything live, into one multi-pane dashboard."),
    (33.4, "Ring. Open-source quant analysis. Not investment advice."),
]

model = Path(sys.argv[1])
voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
out = sys.argv[4] if len(sys.argv) > 4 else str(HERE / "rinng-promo-voice.mp4")

kokoro = Kokoro(str(model / "kokoro-v1.0.onnx"), str(model / "voices-v1.0.bin"))
with tempfile.TemporaryDirectory() as tmp:
    inputs, parts = [], []
    for i, (start, text) in enumerate(LINES):
        samples, rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        wav = f"{tmp}/{i}.wav"
        sf.write(wav, samples, rate)
        print(f"{start:5.1f}s -> {start + len(samples) / rate:5.1f}s  {text}")
        inputs += ["-i", wav]
        ms = int(start * 1000)
        parts.append(f"[{i + 1}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(LINES)))
    graph = ";".join(parts) + f";{mix}amix=inputs={len(LINES)}:normalize=0,loudnorm=I=-16:TP=-1.5,apad[a]"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(HERE / "rinng-promo.mp4"), *inputs,
         "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
        check=True,
    )
print("video ->", out)
