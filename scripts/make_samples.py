"""
Generates a few sample cover files under samples/ so the app can be demoed
without needing to source real-world image/audio files first:

  samples/cover_image.png    - 512x384 RGB gradient/checker pattern (PNG)
  samples/cover_audio_16.wav - ~3s 16-bit PCM mono sine tone
  samples/cover_audio_32.wav - ~3s 32-bit PCM mono sine tone
  samples/cover_video.mp4    - ~4s test-pattern video with a sine-tone audio
                               track (for the video/audio-track-embedding
                               optional-challenge demo)

Run: python scripts/make_samples.py
"""
from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from stego import video_lsb  # noqa: E402 - gives us the bundled ffmpeg path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(exist_ok=True)


def make_image():
    w, h = 512, 384
    x = np.linspace(0, 1, w)
    y = np.linspace(0, 1, h)
    xv, yv = np.meshgrid(x, y)
    r = (xv * 255).astype(np.uint8)
    g = (yv * 255).astype(np.uint8)
    b = (((np.sin(xv * 12) * np.cos(yv * 12)) * 0.5 + 0.5) * 255).astype(np.uint8)
    arr = np.stack([r, g, b], axis=-1)
    Image.fromarray(arr, mode="RGB").save(SAMPLES / "cover_image.png")
    print("wrote", SAMPLES / "cover_image.png")


def make_tone(path: Path, sampwidth: int, seconds: float = 3.0, freq: float = 440.0, rate: int = 44100):
    n = int(seconds * rate)
    t = np.arange(n) / rate
    tone = np.sin(2 * math.pi * freq * t) * 0.5
    # gentle fade in/out to avoid clicks
    fade = min(2000, n // 10)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    tone *= env

    if sampwidth == 2:
        data = (tone * (2 ** 15 - 1)).astype(np.int16)
    elif sampwidth == 4:
        data = (tone * (2 ** 31 - 1)).astype(np.int32)
    else:
        raise ValueError("sampwidth must be 2 or 4")

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())
    print("wrote", path)


def make_video(path: Path, seconds: float = 4.0):
    ffmpeg = video_lsb.ffmpeg_path()
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=480x270:rate=15",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(path),
    ]
    subprocess.run(cmd, check=True)
    print("wrote", path)


if __name__ == "__main__":
    make_image()
    make_tone(SAMPLES / "cover_audio_16.wav", sampwidth=2)
    make_tone(SAMPLES / "cover_audio_32.wav", sampwidth=4)
    try:
        make_video(SAMPLES / "cover_video.mp4")
    except Exception as exc:
        print(f"(skipped cover_video.mp4 - ffmpeg test-pattern generation failed: {exc})")
