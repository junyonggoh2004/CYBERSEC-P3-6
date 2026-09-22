"""Small deterministic media for frontend_workflow.cjs; no real user data."""
from pathlib import Path
import wave
import numpy as np
from PIL import Image

folder = Path(__file__).resolve().parents[1] / "test_evidence"
folder.mkdir(exist_ok=True)
Image.fromarray(np.random.default_rng(8).integers(0, 256, (160, 160, 3), dtype=np.uint8)).save(folder / "frontend-cover.png")
Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(folder / "frontend-payload.png")
with wave.open(str(folder / "frontend-cover.wav"), "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(16000)
    output.writeframes((np.sin(np.arange(32000) / 31) * 2000).astype("<i2").tobytes())
