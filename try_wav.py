"""Try the WAV carrier on any file from the command line.

Usage:
    python try_wav.py <input.wav> [bits] [message]

    bits     LSBs per sample, 1-8 (default 2)
    message  text to hide (default a sample payload)

Embeds the message, saves <input>.stego.wav, reopens it, extracts, and reports
whether the payload survived plus the distortion metrics. If the input is not a
supported 16-bit PCM WAV, it says so and how to fix it rather than crashing.
"""

import os
import sys

import wav
import audio_metrics as metrics

DEFAULT_BITS = 2
DEFAULT_MESSAGE = b"P3-6 INF2005 ACW1 - hidden verification payload"


def main(argv):
    if len(argv) < 2:
        print("Usage: python try_wav.py <input.wav> [bits] [message]")
        return 1

    in_path = argv[1]
    try:
        bits = int(argv[2]) if len(argv) > 2 else DEFAULT_BITS
    except ValueError:
        print(f"Bad setting: bits must be a whole number 1-8 (got {argv[2]!r}).")
        return 1
    message = argv[3].encode("utf-8") if len(argv) > 3 else DEFAULT_MESSAGE

    # 1. load + validate
    try:
        original = wav.load(in_path)
    except wav.UnsupportedWavError as exc:
        print(f"Cannot use this file: {exc}")
        print("This carrier needs 16-bit PCM WAV (mono or stereo).")
        print("Fix in Audacity: File > Export > WAV, 'WAV (Microsoft) signed 16-bit PCM'.")
        return 1
    except FileNotFoundError:
        print(f"File not found: {in_path}")
        return 1

    print(f"loaded    : {original.info.channels}ch, {original.info.sample_rate} Hz, "
          f"{original.eligible_units} samples")

    # 2. embed
    try:
        stego = wav.embed(original, message, num_lsb=bits)
    except wav.WavCapacityError as exc:
        print(f"Message too large for this file at {bits} LSB(s): {exc}")
        return 1
    except ValueError as exc:
        print(f"Bad setting: {exc}")
        return 1

    out_path = os.path.splitext(in_path)[0] + ".stego.wav"
    wav.save(stego, out_path)
    print(f"embedded  : {len(message)} bytes at {bits} LSB(s) -> {out_path}")

    # 3. reopen the saved file and extract (proves it survives disk)
    reopened = wav.load(out_path)
    recovered = wav.extract(reopened, byte_count=len(message), num_lsb=bits)
    print(f"recovered : {recovered.decode('utf-8', errors='replace')!r}")
    print(f"survived  : {recovered == message}")

    # 4. distortion vs original
    m = metrics.compare(original.samples, reopened.samples)
    print(f"changed   : {m.changed_samples}/{m.total_samples} ({m.changed_fraction:.2%})")
    print(f"MSE       : {m.mse:.4f}")
    print(f"SNR       : {m.snr_display}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))