"""Optional network setup for four public-domain/CC0 natural-image samples.

Existing files are preserved. Normal analysis/evaluation works offline.
Source/license notes: samples/steganalysis/PROVENANCE.md.
"""
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "samples" / "steganalysis"
BASE = "https://raw.githubusercontent.com/scikit-image/scikit-image/v0.18.3/skimage/data/"
FILES = ("astronaut.png", "chelsea.png", "clock_motion.png", "coffee.png")


def main():
    covers = ROOT / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name in FILES:
        path = covers / name
        if not path.exists():
            with urlopen(BASE + name, timeout=60) as response:
                data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024:
                raise ValueError("Unexpectedly large sample download.")
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG":
                    raise ValueError("Expected a PNG sample.")
                image.verify()
            path.write_bytes(data)
        manifest.append({"file": name, "url": BASE + name,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(name, flush=True)
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
