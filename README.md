# WAV carrier (LSB steganography)

Library for hiding and recovering bytes inside 16-bit uncompressed PCM WAV files (mono or stereo). It loads and validates a WAV, embeds bytes into the lowest 1 to 8 bits of each PCM sample from a chosen sample index, saves the result, and extracts the bytes back. Every sample is a carrier unit (both channels, interleaved), and the WAV header never carries payload.

This is a library, not an app. It will be integrated into the wider project on the `Matthias_Claude` branch, which has the GUI and the full pipeline.

## Setup

Python 3.12 or newer.

```
pip install numpy pytest
```

## Tests

From this folder:

```
python -m pytest
```

Use `python -m pytest` rather than bare `pytest`, since the shim only works when the Python `Scripts` folder is on `PATH` (activating a virtualenv usually handles this).

## Quick demo

`try_wav.py` embeds a message, saves the stego file, reopens it from disk and extracts the message again, so the payload is proved to survive the save. It then prints the distortion metrics from `audio_metrics.py`: changed sample count, mean squared error and signal-to-noise ratio. One command gives both correctness and distortion evidence.

```
python try_wav.py original.wav 2 "hello"
```

`original.wav` is included in this branch, so the command above runs as written. Any other 16-bit PCM WAV works too. `try_wav.py` is a demo script, not the application.

## Example

```python
import wav

carrier = wav.load("cover.wav")
message = b"hidden verification payload"

stego = wav.embed(carrier, message, num_lsb=2, start_index=0)
wav.save(stego, "cover.stego.wav")

# extract needs the payload length and the same settings used to embed
reopened = wav.load("cover.stego.wav")
recovered = wav.extract(reopened, byte_count=len(message), num_lsb=2, start_index=0)
assert recovered == message
```

## Notes

Extra WAV chunks (LIST, id3 and similar) are dropped on save, because the standard library `wave` writer does not preserve them.

`bitstream.py` is shared with the image carrier and defines the bit format: payload bytes are expanded MSB-first, packed `num_lsb` bits per carrier unit, and the final unit's unused low bits are zero-padded.

This branch contains a fix in `wav.py`: `num_lsb` was passed through `bitstream.validate_num_lsb` but the return value was discarded, so the unvalidated value was used in later arithmetic. It is now captured at all four call sites. A related point, that `bitstream.validate_num_lsb` coerces floats with `int()` rather than rejecting them, is Matthias's call and has not been changed here.