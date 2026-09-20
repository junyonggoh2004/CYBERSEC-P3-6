"""ACW1 demo verdicts using temporary keys; never change stored PEM files."""
import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from stego import crypto_utils, pipeline


@pytest.fixture
def demo(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(crypto_utils, "load_private_key", lambda: key)
    original_loader = crypto_utils.load_public_key
    monkeypatch.setattr(crypto_utils, "load_public_key", lambda pem=None: original_loader(pem) if pem else key.public_key())
    image = io.BytesIO()
    Image.fromarray(np.zeros((128, 128, 3), dtype=np.uint8)).save(image, format="PNG")
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(np.zeros(44100, dtype="<i2").tobytes())
    return {"image": image.getvalue(), "audio": audio.getvalue()}


def encode(kind, cover, data=b"ACW1 verification demo"):
    return pipeline.encode(cover_type=kind, cover_bytes=cover, payload_type="text",
        data=data, filename=None, mime="text/plain", num_lsb=1, start_mode="manual",
        manual_offset=700, passphrase=None, media_id="demo", team_metadata={},
        stego_out_name="stego.png" if kind == "image" else "stego.wav")


def decode(kind, data, key=None, offset=700):
    return pipeline.decode(cover_type=kind, stego_bytes=data, num_lsb=1,
        start_mode="manual", manual_offset=offset, passphrase=None, public_key_pem=key)


@pytest.mark.parametrize("kind", ["image", "audio"])
def test_positive_cases(demo, kind):
    message = b"Short learning objective" if kind == "image" else b"Project overview paragraph. " * 20
    result = decode(kind, encode(kind, demo[kind], message).stego_bytes)
    assert result.verdict == "Authentic"
    assert result.data == message
    assert result.signature_valid and result.payload_hash_match and result.cover_hash_match


def test_png_wrong_signer(demo):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = other.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    result = decode("image", encode("image", demo["image"]).stego_bytes, public)
    assert result.verdict == "Signature Invalid"
    assert result.payload_hash_match and not result.signature_valid


def test_wav_tamper_and_reset(demo):
    original = encode("audio", demo["audio"]).stego_bytes
    altered = bytearray(original)
    offset = max(64, min(len(altered) - 8, int(len(altered) * .55)))
    altered[offset] ^= 0x80  # Same alteration as the GUI's local-copy tool.
    result = decode("audio", bytes(altered))
    assert result.verdict == "Tampered"
    assert result.payload_hash_match and result.signature_valid and not result.cover_hash_match
    assert decode("audio", original).verdict == "Authentic"


def test_unencoded_png_missing_payload(demo):
    assert decode("image", demo["image"], offset=0).verdict == "Payload Missing"


def test_invalid_key_and_oversized_payload(demo):
    stego = encode("image", demo["image"]).stego_bytes
    assert decode("image", stego, b"INVALID PUBLIC KEY").verdict == "Cannot Verify"
    with pytest.raises(pipeline.StegoError):
        encode("image", demo["image"], b"X" * 100000)
