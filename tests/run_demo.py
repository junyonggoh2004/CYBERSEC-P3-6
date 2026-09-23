"""
Reproducible positive/negative test-case runner (FR11, FR12, "test evidence"
submission item). Exercises the pipeline directly (no browser needed) so a
marker can run `python tests/run_demo.py` and see every required case:

  positive image case             -> Authentic
  positive audio case             -> Authentic
  positive video case (optional)  -> Authentic (audio-track embedding)
  negative: tampered payload      -> Tampered
  negative: tampered cover        -> Tampered
  negative: wrong signature/key   -> Signature Invalid
  negative: wrong start location  -> Wrong Start Location
  negative: wrong video passphrase -> Wrong Start Location
  negative: oversized payload     -> rejected at encode time (capacity check)

Writes a JSON summary and the stego files it produced to test_evidence/, and
prints a pass/fail table to the console.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from stego import crypto_utils, pipeline  # noqa: E402

SAMPLES = ROOT / "samples"
EVIDENCE = ROOT / "test_evidence"
EVIDENCE.mkdir(exist_ok=True)

SHORT_MSG = "Explain how steganography can be used to embed hidden verification data in image and audio cover objects."
LARGE_MSG = (
    "This undergraduate project requires student teams to design, implement and demonstrate a "
    "GUI-based LSB Replacement steganography program (window-based or web-based) that protects and "
    "verifies both image and audio cover objects using steganography, hashing and digital signatures. "
    "The project focuses on practical cybersecurity concepts: hiding a verification payload inside an "
    "image and an audio file, signing relevant verification data, extracting the hidden payload, "
    "checking the digital signature, and demonstrating positive and negative verification cases."
)
CUSTOM_MSG = "CONFIDENTIAL - Team P3-6 release note: approved for release; verify signature before trusting this file."

results = []


def record(name, expected_verdict, actual_verdict, extra=""):
    ok = expected_verdict == actual_verdict
    results.append({"case": name, "expected": expected_verdict, "actual": actual_verdict, "pass": ok, "extra": extra})
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: expected={expected_verdict!r} actual={actual_verdict!r} {extra}")


def require_samples():
    img = SAMPLES / "cover_image.png"
    wav16 = SAMPLES / "cover_audio_16.wav"
    if not img.exists() or not wav16.exists():
        print("Sample files missing - generating them now via scripts/make_samples.py ...")
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_samples.py")], check=True)


def main():
    require_samples()
    crypto_utils.generate_keypair(overwrite=False)

    cover_image = (SAMPLES / "cover_image.png").read_bytes()
    cover_audio = (SAMPLES / "cover_audio_16.wav").read_bytes()

    # ---------------- Positive case: image, short message, passphrase start ----------------
    enc = pipeline.encode(
        cover_type="image", cover_bytes=cover_image, payload_type="text", data=SHORT_MSG.encode(),
        filename=None, mime="text/plain", num_lsb=2, start_mode="passphrase", manual_offset=None,
        passphrase="team-p3-6-secret", media_id="IMG-POS-001", team_metadata={"team": "P3-6"},
        stego_out_name="stego_image_positive.png",
    )
    (EVIDENCE / enc.stego_filename).write_bytes(enc.stego_bytes)
    dec = pipeline.decode(
        cover_type="image", stego_bytes=enc.stego_bytes, num_lsb=2, start_mode="passphrase",
        manual_offset=None, passphrase="team-p3-6-secret", public_key_pem=None,
    )
    record("Positive - image, short text payload", "Authentic", dec.verdict)

    # ---------------- Positive case: audio, large message, manual start ----------------
    enc2 = pipeline.encode(
        cover_type="audio", cover_bytes=cover_audio, payload_type="text", data=LARGE_MSG.encode(),
        filename=None, mime="text/plain", num_lsb=3, start_mode="manual", manual_offset=1000,
        passphrase=None, media_id="AUD-POS-001", team_metadata={"team": "P3-6"},
        stego_out_name="stego_audio_positive.wav",
    )
    (EVIDENCE / enc2.stego_filename).write_bytes(enc2.stego_bytes)
    dec2 = pipeline.decode(
        cover_type="audio", stego_bytes=enc2.stego_bytes, num_lsb=3, start_mode="manual",
        manual_offset=1000, passphrase=None, public_key_pem=None,
    )
    record("Positive - audio, large text payload", "Authentic", dec2.verdict)

    # ---------------- Positive/negative: video (optional challenge, audio-track embedding) ----------------
    video_path = SAMPLES / "cover_video.mp4"
    if video_path.exists():
        cover_video = video_path.read_bytes()
        enc_v = pipeline.encode(
            cover_type="video", cover_bytes=cover_video, payload_type="text", data=CUSTOM_MSG.encode(),
            filename=None, mime="text/plain", num_lsb=2, start_mode="passphrase", manual_offset=None,
            passphrase="video-secret", media_id="VID-POS-001", team_metadata={"team": "P3-6"},
            stego_out_name="stego_video_positive.mkv",
        )
        (EVIDENCE / enc_v.stego_filename).write_bytes(enc_v.stego_bytes)
        dec_v = pipeline.decode(
            cover_type="video", stego_bytes=enc_v.stego_bytes, num_lsb=2, start_mode="passphrase",
            manual_offset=None, passphrase="video-secret", public_key_pem=None,
        )
        record("Positive - video (audio-track embedding)", "Authentic", dec_v.verdict)

        dec_v_wrong = pipeline.decode(
            cover_type="video", stego_bytes=enc_v.stego_bytes, num_lsb=2, start_mode="passphrase",
            manual_offset=None, passphrase="WRONG-secret", public_key_pem=None,
        )
        record("Negative - video, wrong passphrase / start location", "Wrong Start Location", dec_v_wrong.verdict)
    else:
        print("(skipping video cases - samples/cover_video.mp4 not available, likely no local ffmpeg/codec support)")

    # ---------------- Negative: cover tampered *after* signing (payload untouched) ----------------
    # Uses the uncompressed WAV cover, where a raw file byte maps predictably
    # to one PCM sample - unlike PNG, whose IDAT stream is DEFLATE-compressed,
    # so a raw-byte flip there can land anywhere after decompression. We flip
    # a high bit (0x80) of a sample chosen well *past* the embedded container,
    # so the hidden payload itself is never touched - only "visible" (audible)
    # content changes, which the stable cover-hash check is designed to catch.
    num_lsb_neg = 4
    start_offset_neg = 500
    enc3 = pipeline.encode(
        cover_type="audio", cover_bytes=cover_audio, payload_type="text", data=CUSTOM_MSG.encode(),
        filename=None, mime="text/plain", num_lsb=num_lsb_neg, start_mode="manual", manual_offset=start_offset_neg,
        passphrase=None, media_id="AUD-NEG-TAMPER", team_metadata={"team": "P3-6"},
        stego_out_name="stego_audio_tampered.wav",
    )
    payload_bits = enc3.container_size_bytes * 8
    samples_used = -(-payload_bits // num_lsb_neg)  # ceil
    safe_sample = start_offset_neg + samples_used + 5000  # comfortably past the payload
    wav_header_len = 44  # standard PCM WAV header written by Python's wave module
    sampwidth = 2
    tampered = bytearray(enc3.stego_bytes)
    byte_offset = wav_header_len + safe_sample * sampwidth + (sampwidth - 1)  # high byte of the sample
    if byte_offset >= len(tampered):
        byte_offset = len(tampered) - 1
    tampered[byte_offset] ^= 0x80
    (EVIDENCE / "stego_audio_tampered.wav").write_bytes(bytes(tampered))
    dec3 = pipeline.decode(
        cover_type="audio", stego_bytes=bytes(tampered), num_lsb=num_lsb_neg, start_mode="manual",
        manual_offset=start_offset_neg, passphrase=None, public_key_pem=None,
    )
    record("Negative - cover tampered after signing (payload intact)", "Tampered", dec3.verdict, dec3.detail[:90])

    # ---------------- Negative: hidden payload itself corrupted ----------------
    enc3b = pipeline.encode(
        cover_type="audio", cover_bytes=cover_audio, payload_type="text", data=CUSTOM_MSG.encode(),
        filename=None, mime="text/plain", num_lsb=num_lsb_neg, start_mode="manual", manual_offset=start_offset_neg,
        passphrase=None, media_id="AUD-NEG-PAYLOAD", team_metadata={"team": "P3-6"},
        stego_out_name="stego_audio_payload_tampered.wav",
    )
    meta_len = len(json.dumps(enc3b.metadata, separators=(",", ":")).encode("utf-8"))
    header_bytes = 4 + 1 + 1 + 2 + meta_len + 32 + 2 + 256 + 4  # magic..data_len, see payload.py format
    data_offset_bytes = header_bytes + 20  # 20 bytes into DATA itself
    sample_in_payload = start_offset_neg + (-(-(data_offset_bytes * 8) // num_lsb_neg))
    byte_offset2 = wav_header_len + sample_in_payload * sampwidth
    tampered3 = bytearray(enc3b.stego_bytes)
    if byte_offset2 >= len(tampered3):
        byte_offset2 = len(tampered3) - 1
    tampered3[byte_offset2] ^= 0x01
    (EVIDENCE / "stego_audio_payload_tampered.wav").write_bytes(bytes(tampered3))
    dec3b = pipeline.decode(
        cover_type="audio", stego_bytes=bytes(tampered3), num_lsb=num_lsb_neg, start_mode="manual",
        manual_offset=start_offset_neg, passphrase=None, public_key_pem=None,
    )
    record("Negative - hidden payload corrupted", "Tampered", dec3b.verdict, dec3b.detail[:90])

    # ---------------- Negative: wrong public key ----------------
    decoy_pub = crypto_utils.generate_decoy_public_key_pem()
    dec4 = pipeline.decode(
        cover_type="image", stego_bytes=enc.stego_bytes, num_lsb=2, start_mode="passphrase",
        manual_offset=None, passphrase="team-p3-6-secret", public_key_pem=decoy_pub,
    )
    record("Negative - wrong public key", "Signature Invalid", dec4.verdict)

    # ---------------- Negative: wrong start location (wrong passphrase) ----------------
    dec5 = pipeline.decode(
        cover_type="image", stego_bytes=enc.stego_bytes, num_lsb=2, start_mode="passphrase",
        manual_offset=None, passphrase="WRONG-passphrase", public_key_pem=None,
    )
    record("Negative - wrong passphrase / start location", "Wrong Start Location", dec5.verdict)

    # ---------------- Negative: payload larger than capacity ----------------
    huge_payload = b"X" * (10 * 1024 * 1024)  # 10MB into a small PNG - guaranteed to overflow
    try:
        pipeline.encode(
            cover_type="image", cover_bytes=cover_image, payload_type="file", data=huge_payload,
            filename="huge.bin", mime="application/octet-stream", num_lsb=1, start_mode="manual",
            manual_offset=0, passphrase=None, media_id="IMG-NEG-CAPACITY", team_metadata={},
            stego_out_name="unused.png",
        )
        record("Negative - oversized payload rejected", "rejected", "not-rejected")
    except pipeline.StegoError as exc:
        record("Negative - oversized payload rejected", "rejected", "rejected", str(exc)[:80])

    summary_path = EVIDENCE / "demo_log.json"
    summary_path.write_text(json.dumps({"generated_at": time.time(), "results": results}, indent=2))
    print(f"\nSummary written to {summary_path}")
    n_fail = sum(1 for r in results if not r["pass"])
    print(f"{len(results) - n_fail}/{len(results)} cases matched expected verdicts.")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
