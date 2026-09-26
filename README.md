# Stego Integrity Verifier

INF2005 ACW1 · Team P3-6. First draft on Junyong's branch, based on Gabriel's `54a5789` frontend and Kim's PNG steganalysis implementation.

## Run locally

From this directory, with Python 3.11+:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python backend/app.py
```

Open **http://127.0.0.1:5000**. Keep the terminal running. This is a local assignment demo, not a public multi-user key-management service.

## Pages and user journey

1. **Protect — Alice:** select or drag in the original PNG, WAV or video, choose hidden content, select SHA-256 (default) or SHA-512, select Alice's signing pair, choose 1–8 lowest bits and a manual or passphrase-derived start location.
2. Review exact capacity and the draft verification record. The app includes metadata, signature, header and field-padding overhead. It shows each depth's
capacity and the minimum sufficient depth without changing the user's choice.
3. Sign and create the stego object. Inspect/download the result and its final record. The draft nonce/timestamp are regenerated for the final file.
4. **Verify — Bob:** upload the received object, use the agreed LSB depth/location, and explicitly supply Alice's trusted public key. No Bob key pair is required. An in-app shortcut helps local testing; the assignment demonstration must also show an actual Alice-to-Bob transfer and verification of Bob's downloaded copy.
5. **Compare:** original/stego previews, hidden-content preview for the last generated pair, linked image zoom, RGB(A) overlaid histograms, amplified difference image, or aligned audio waveform envelopes. Independently uploaded pairs do not claim to know the hidden content.
6. **Steganalysis:** independent PNG chi-square and RS containers, per-channel measurements, provisional thresholds, explanations and JSON export. WAV files and video audio tracks use sample-pair analysis instead (estimated share of samples carrying hidden bits, 95% interval and a time map). Histograms stay on Compare.
7. **Alice's keys:** view fingerprints/public keys, export public keys, import
demo RSA private keys, and generate additional pairs without replacing old ones.

Selections and generated files persist across pages in memory, not across reloads. Secrets are excluded from downloaded reports. A new analysis/verification input invalidates the displayed result.

## Supported first-draft combinations

| Cover | Hidden content | Output |
|---|---|---|
| PNG | Text, or a text/image/audio/video file | PNG |
| WAV/PCM | Text, or a text/image/audio/video file | WAV |
| Video with an audio track (MP4/MKV/MOV/WebM/AVI) | Text, or a text/image/audio/video file | MKV |

Audio covers support signed 16-bit and 32-bit PCM. Payload files are carried as bytes, so any supported content file (TXT, PNG/JPEG, WAV/MP3, MP4/MKV, ...) can be hidden in any cover that has the capacity. Video covers embed into the video's audio track; the video stream is copied untouched and the output is MKV so the
PCM audio survives. Covers and content files can be dragged onto the drop zones.

## What is signed and hashed

New files use container **version 2**. The verification record contains media ID, UTC timestamp, random nonce, filename/MIME, content length/type, team metadata, hash algorithm, stable cover hash, signer fingerprint and embedding settings.

The existing RSA PKCS#1 v1.5 signature scheme is retained through the cryptography library. New pairs are RSA-2048; imported RSA pairs must be at least 2048 bits. The selected SHA-256/SHA-512 algorithm is used for content hashing, record hashing and the signature. The signed message binds the expected content hash and
verification record. No custom cryptographic primitive is implemented.

The stable cover hash masks the lowest selected bits of every carrier value and also binds carrier properties in V2. It does **not** hash the PNG/WAV container bytes. The receiver repeats the same normalisation. V1 SHA-256 records remain readable using their original layout and stable-hash rule.

The record viewer shows the expected and recomputed hashes, signature, key fingerprint, metadata and trust status. Signature verification establishes a link to the supplied public key, not that the key independently belongs to Alice.

### LSB semantics and capacity

For an 8-bit image channel, depth 3 changes the three rightmost bits. For audio it changes the three lowest bits of a **PCM sample**, not of each byte. Carrier traversal is row-major channel order for images and interleaved sample order for WAV. The current image carrier includes alpha for RGBA images; steganalysis excludes alpha and reports that limitation.

Each container field rounds up to a whole carrier unit. Exact fit is therefore the sum of `ceil(field_bits / depth)`, not simply the raw package byte length. The API and UI use the same calculation before writing.

The start-location derivation always uses a SHA-256 stable cover hash, independently of the selected content hash. Bob can reproduce it before reading the record. Changing depth or cover values may change a derived location. Passphrases are not stored in the record, and hidden locations are not encryption:
candidate offsets may still be searched.

## Verification results 
Every returned verdict contains the same evidence fields and six check slots:
extraction, record binding, signature, content integrity, cover integrity and decryption (not applicable). States include Passed, Failed, Not run and Not applicable; unavailable values are shown explicitly.

- **Authentic:** the signature and required integrity checks pass.
- **Signature Invalid:** the supplied key does not validate the signed record;
  this does not uniquely identify whether the key, signature or record is wrong.
- **Tampered:** a valid signed reference exists, but the content, stable cover or signed record binding differs.
- **Payload Missing:** no recognised package at the attempted settings. This may mean incorrect depth/location, damaged header or no supported payload.
- **Cannot Verify:** missing/invalid key, unsupported media/settings, malformed package, or another condition that prevents completing verification.

The app does not claim **Wrong Start Location** merely because extraction fails.
That label needs independent evidence unavailable to a blind verifier. The negative-case tools alter a copy's hidden content or a protected carrier bit; the original generated file remains available.

## Scope and limitations

- Signing and hiding **do not encrypt** the content. No recipient encryption or Bob private-key workflow is included. The brief's custom-payload confidentiality requirement still needs an explicit team decision before claiming full coverage.
- A stable cover hash excludes selected low bits. At depth 8 in an 8-bit image, no channel-value bits remain protected by that hash. Content integrity is still checked separately. Geometry remains bound by the V2 representation.
- Metadata/timestamps/nonces alone do not prevent replay.
- LSB replacement is fragile under lossy compression, resampling and conversion. Decoding does not restore the overwritten original carrier bits.
- Comparison metrics describe changes, not authenticity.
- Chi-square p-values are not probabilities that secret data exists. Each channel uses the stronger of its whole-channel and median-window tail score. RS reports the Fridrich/Goljan/Du estimate of the LSB-replacement fraction (bounded 0–1), not a probability. Either method crossing its threshold gives High indication. Thresholds are provisional; both false positives and missed payloads are possible. Higher-depth analysis is outside the formal model. An Authentic file can also show hidden-data indicators.
- Demo private keys are stored unencrypted locally. Additional pairs live in ignored `backend/keys/saved/`; existing legacy key files are preserved. Import/export public keys separately and check their fingerprints.

For the detector mathematics and existing evaluation, see
[Steganalysis guide](docs/STEGANALYSIS_GUIDE.md) and
[evaluation results](evidence/steganalysis/RESULTS.md).

## Verification and tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_steganalysis.py tests/test_audio_steganalysis.py tests/test_workflow.py -q
```

The tests isolate keys in temporary directories. They cover both hashes at all eight depths, both carriers and cross-media payloads, 32-bit PCM, exact capacity, legacy compatibility, deterministic verdict evidence, non-destructive keys and paired statistics. If the system temporary directory is restricted, create
`test_evidence/` and add `--basetemp test_evidence/pytest-temp`.

Optional frontend DOM integration test (Node.js and jsdom required):

```powershell
npm install --no-save --package-lock=false jsdom
python tests/make_ui_fixtures.py
# Start the app in another terminal first.
$env:STEGO_TEST_URL = 'http://127.0.0.1:5000'
node tests/frontend_workflow.cjs
```

This exercises app handlers and real HTTP APIs with browser file/canvas adapters. It is **not** a rendered-layout or real-browser test. Visual review of desktop, mobile, focus behaviour and media playback remains necessary.

The older `python tests/run_demo.py` demonstration runner remains available, including legacy video cases when sample video is present.
# PNG / WAV LSB Steganography Prototype

## Purpose
A simple educational GUI prototype that hides and extracts UTF-8 text in:
- PNG images
- uncompressed PCM WAV audio

It supports selectable 1–8 LSBs and a user-selected start carrier index.

## Install and run

```bash
pip install -r requirements.txt
python steg_app.py
```

## Encode flow
1. Select a PNG or PCM WAV file.
2. Choose the number of LSBs (1–8).
3. Choose the start carrier index.
4. Type the hidden text.
5. Click **Encode → Save Stego File**.
6. Save the new PNG/WAV.

If a cover has a `.png` filename but contains another image format (such as WebP), the encoder converts its pixels and saves a genuine, lossless PNG. The original cover is unchanged when you save to a new file. To decode, select the exported stego PNG; renaming a WebP or JPEG file to `.png` does not make it a PNG or restore hidden data lost through lossy compression.

## Decode flow
1. Select the generated stego file.
2. Enter the same LSB count.
3. Enter the same start carrier index.
4. Click **Decode Selected File**.

## Packet format
Before embedding, the program converts the message to UTF-8 and builds:

```text
[ "STEG1" | 4-byte length | 4-byte CRC32 | UTF-8 message ]
```

The fixed header is 13 bytes.

- `STEG1` helps the decoder recognise a payload.
- `length` tells it how many bytes to extract.
- `CRC32` detects corruption or wrong settings.
- CRC32 is **not** a cryptographic hash.

## Core functions

The functions in `steg_app.py` separate file handling from hiding data. PNG and WAV loaders expose a sequence of usable **carrier units**, so the same packet encoder and decoder work for both formats.

| Parameter | Meaning |
| --- | --- |
| `raw` | Mutable `bytearray` of decoded pixel bytes or PCM audio bytes, excluding file headers. |
| `carrier_count` | Total number of usable RGB channel values or individual audio samples. |
| `mapper` | Function that translates a carrier index into an index in `raw`. It skips alpha bytes or the higher bytes of audio samples. |
| `packet` | Header and UTF-8 message bytes returned by `build_packet`. |
| `start` | Zero-based carrier index where embedding or extraction begins; defaults to `0` in the public encode/decode functions. |
| `lsb_count` | Number of lowest bits used per carrier byte, from `1` to `8`; defaults to `1` in the public encode/decode functions. |

An LSB is a least-significant bit: changing it changes a byte's numeric value
less than changing a higher bit. Using more LSBs increases capacity but can
cause more visible image changes or audible audio changes. `start` counts
carrier units, not file bytes, pixels, or seconds. Neither setting is stored
in the packet, so decoding needs the same values used during encoding.

### `StegError`

This custom exception identifies expected application errors, such as an invalid setting, insufficient capacity, or a missing payload. The GUI catches exceptions and displays their messages. Direct callers of the core functions can catch `StegError`; file and image libraries can also raise their own errors.

### `build_packet(message: str) -> bytes`

Input: Python text string.  
Output: framed bytes containing marker, length, CRC32 and UTF-8 message.

The function encodes the string as UTF-8, calculates `zlib.crc32(data)`, and uses `HEADER.pack(...)` to prepend the marker, byte length, and checksum.
`HEADER = struct.Struct(">5sII")` means big-endian storage (`>`) of a five-byte
marker (`5s`) and two unsigned four-byte integers (`II`). The length counts UTF-8 bytes rather than characters: `"Hi"` produces a 15-byte packet, while characters such as emoji can require multiple bytes each.

### `_bits(data: bytes) -> str`

Converts each byte to eight binary digits, including leading zeroes, then joins them into one string. For example, `b"A"` becomes `"01000001"`. Within each byte, the most-significant bit comes first. This establishes the bit order used by both embedding and extraction.

### `embed_packet(raw, carrier_count, mapper, packet, start=0, lsb_count=1)`

Output: the same `raw` bytearray, modified in place.

It first checks that the LSB count is `1..8`, the start index is inside the carrier, and the entire packet fits. It then:

1. converts packet bytes to bits;
2. groups bits according to the chosen LSB count;
3. clears those low-order bits in each carrier;
4. inserts the payload bits.

For each selected byte, `mask = (1 << lsb_count) - 1` selects its lowest bits, and `clear_mask = 0xFF ^ mask` selects the bits to preserve. The update is:

```python
raw[raw_index] = (raw[raw_index] & clear_mask) | int(chunk, 2)
```

For example, with two LSBs, embedding `01` into `11010110` produces `11010101`.
If the last chunk is short, it is padded with zeroes on the right. Processing stops once the packet is embedded; earlier carriers and later unused carriers are untouched.

### `extract_bytes(raw, carrier_count, mapper, start, lsb_count, byte_count) -> bytes`

Input: raw stego bytes, carrier mapping, matching settings, and the number of bytes to recover. Output: reconstructed bytes, without modifying `raw`.

The function validates the settings and checks that `byte_count * 8` bits fit.
It reads each selected carrier byte, masks off its higher bits, and formats the remaining bits as a string of exactly `lsb_count` digits. It joins these chunks, trims to the requested bit length, and converts each group of eight bits back to a byte. Trimming removes any padding added during embedding.

### `decode_packet(raw, carrier_count, mapper, start=0, lsb_count=1) -> str`

This function coordinates extraction and returns the recovered Python string:

1. extracts the 13-byte header;
2. checks for `STEG1`;
3. reads the stored payload length;
4. extracts the complete packet;
5. checks CRC32;
6. converts UTF-8 bytes back to text.

The second extraction starts again at `start` and reads the header plus the message. Reading the complete packet this way also handles LSB counts where the header ends partway through a carrier's bit chunk. The header is then removed before checking the message checksum and decoding UTF-8.

A wrong marker, insufficient carrier data, mismatched CRC, or invalid UTF-8 raises `StegError`. CRC detects accidental corruption; it does not authenticate the sender or prevent someone from changing a message and recalculating it.

## PNG implementation

### `_load_png(path, *, allow_conversion=False)`

Returns `(image, raw, carrier_count, mapper)` for an image opened with Pillow.
`image` contains the image mode and dimensions, and `raw` holds its decoded pixel bytes. The source file is closed before returning.

By default, the function checks the actual image format and rejects non-PNG data. Encoding and capacity calculation pass `allow_conversion=True`, allowing readable cover images such as a WebP saved with a `.png` filename. Decoding keeps the strict check and expects the exported PNG.

RGB and RGBA images are copied. Other modes, such as grayscale or palette images, are converted to RGB or RGBA, retaining an alpha channel when the source has alpha or transparency information.

Each red, green or blue channel value is one carrier unit. RGBA alpha values are skipped.

| Image mode | Mapping from carrier index `i` to raw byte index |
| --- | --- |
| RGB | `i`, because every byte is an R, G, or B value. |
| RGBA | `(i // 3) * 4 + (i % 3)`, skipping every fourth byte (alpha). |

For RGBA, carrier indices `0, 1, 2, 3` map to raw byte indices `0, 1, 2, 4`.
Both modes provide `width * height * 3` carriers.

### `encode_png(input_path, output_path, message, start=0, lsb_count=1)`

Loads the cover with conversion enabled, builds the message packet, and embeds it into the RGB channel bytes. `Image.frombytes(...)` rebuilds an image using the original loaded dimensions and normalized mode. Saving with the explicit `"PNG"` format writes a genuine, lossless PNG regardless of the cover's actual
format. The function writes to `output_path` and returns `None`.

Example with 1 LSB:

```text
original channel: 11010110
hidden bit:              1
result:           11010111
```

### `decode_png(input_path, start=0, lsb_count=1) -> str`

Loads a genuine PNG with `_load_png`, then passes its bytes and RGB mapping to
`decode_packet`. It returns the hidden text after packet validation succeeds.

PNG is used because it is lossless. JPEG conversion would normally destroy simple pixel-LSB data.

## WAV implementation

### `_load_wav(path)`

Opens the file with Python's `wave` module and returns `(params, raw, carrier_count, mapper)`. `params` holds audio properties such as channel count, sample width, sample rate, and frame count. `raw` holds the PCM
sample bytes read from all frames.

It requires uncompressed PCM and a sample width of `1`, `2`, `3`, or `4` bytes (8, 16, 24, or 32 bits). It also checks that the byte count is divisible by the sample width. The carrier count is `len(raw) // params.sampwidth`, and themapper is `i * params.sampwidth`.

One carrier is one channel's sample. For stereo audio, samples are interleaved as left, right, left, right, so one frame normally contains two carriers.

### `encode_wav(input_path, output_path, message, start=0, lsb_count=1)`

Calls `_load_wav`, builds the packet, and embeds it using the audio mapper. It opens the output WAV, copies the audio parameters with `setparams`, and writes the modified sample bytes with `writeframes`. It returns `None`.

For each PCM sample, the prototype modifies only its least-significant byte. WAV PCM is little-endian, so that byte contains the actual low-order sample bits.

For 16-bit PCM:

```text
[least-significant byte][most-significant byte]
```

With `LSBs = 1`, only the lowest bit of each sample changes.

### `decode_wav(input_path, start=0, lsb_count=1) -> str`

Calls `_load_wav` and passes the sample bytes and mapper to `decode_packet`. It reads sample LSBs in the same order as encoding and returns the validated hidden text.

## Capacity

### `carrier_info(path, start, lsb_count)`

Chooses `_load_png(..., allow_conversion=True)` or `_load_wav(...)` using the file's lowercase suffix. Other suffixes are rejected. It checks that `start` is inside the carrier and returns `(kind, unit, count, usable)`:

| Return value | Meaning |
| --- | --- |
| `kind` | `"PNG"` or `"WAV"`, identifying the selected carrier workflow. |
| `unit` | `"RGB channel values"` or `"PCM samples"`. |
| `count` | Total carrier units before accounting for `start`. |
| `usable` | Maximum message bytes after subtracting the packet header, clamped to zero. |

The GUI validates the LSB count through `settings()` before calling this function; `carrier_info` itself only validates the start index.
Approximate usable capacity:

```text
available bits = (carrier_count - start) × LSB_count
```

Then divide by 8 and subtract the 13-byte header.

The exact calculation used for the display is:

```python
usable = max(0, ((carrier_count - start) * lsb_count) // 8 - HEADER_SIZE)
```

For a 256 × 256 RGB image, start `0`, and one LSB, there are 196,608 available bits: 24,576 packet bytes, leaving 24,563 message bytes. Compare this limit with `len(message.encode("utf-8"))`, not the number of characters. A displayed capacity of zero can also mean the carrier cannot fit even the header;
`embed_packet` performs the final check.

For RGB/RGBA PNG:

```text
carrier_count = width × height × 3
```

For WAV:

```text
carrier_count = number of interleaved PCM samples
```

## GUI functions and application flow

`App` inherits from `tk.Tk`. Its methods connect the interface to the file and
packet functions above.

| Method | What it does |
| --- | --- |
| `App.__init__()` | Creates the window, initializes variables for the selected file, settings, capacity, and status, then calls `_ui()`. Defaults are start `0` and one LSB. |
| `App._ui()` | Builds the file picker, settings fields, text box, action buttons, and status area. Connects buttons to their handlers and settings edits to `refresh()`. The Clear Text button deletes the text box contents. |
| `App.settings()` | Reads and converts the start and LSB values to integers, checks `start >= 0` and `1 <= lsb <= 8`, and returns `(start, lsb)`. Carrier-specific bounds are checked when the file is loaded. |
| `App.browse()` | Opens the file selection dialog, stores the chosen path, and calls `refresh()`. Cancelling leaves the selection unchanged. |
| `App.refresh()` | Calls `settings()` and `carrier_info()` to update the capacity label. Displays errors in that label; returns immediately if no path is selected. |
| `App.encode()` | Reads the path, settings, and text (excluding Tk's automatic final newline). Uses the `.png` or `.wav` suffix to choose a save dialog and encoder. Cancelling the dialog stops the operation. Success or failure updates the status and shows a message box. |
| `App.decode()` | Reads the path and settings, selects the decoder by suffix, and replaces the text box contents with recovered text only after decoding succeeds. Errors appear in the status and a message box. |

The GUI and `carrier_info` route files by extension, while the loaders inspect their contents. Thus, a WebP cover named `.png` can be encoded via the PNG workflow, but the GUI does not currently route a `.webp` filename to that workflow. Encoding also leaves the selected path pointing to the cover:
browse to the exported file before decoding.

```text
Encode button → App.encode() → settings() → save dialog
    → encode_png() / encode_wav()
    → loader → build_packet() → embed_packet() → write output file

Decode button → App.decode() → settings()
    → decode_png() / decode_wav()
    → loader → decode_packet() → extract_bytes() → validate → display text
```

The `if __name__ == "__main__":` block runs `App().mainloop()` when the script is launched directly. The event loop waits for user actions and runs the connected handlers. Importing `steg_app` lets another script use its functions without opening the GUI.

## Using the functions without the GUI

Run this from the project directory to use the included sample cover:

```python
from steg_app import carrier_info, encode_png, decode_png

start = 7
lsb_count = 2
print(carrier_info("sample_cover.png", start, lsb_count))

encode_png(
    "sample_cover.png", "sample_cover_stego.png", "Hello, hidden world!",
    start=start, lsb_count=lsb_count,
)
message = decode_png("sample_cover_stego.png", start=start, lsb_count=lsb_count)
print(message)  # Hello, hidden world!
```

For WAV, use `encode_wav` and `decode_wav` with WAV paths and the same argument
pattern. Always decode the exported file with the matching start and LSB count.

## Tests

Run the regression tests from the project directory:

```bash
python -m unittest -v
```

`test_steg_app.py` verifies that a WebP cover named `.png` exports as a genuine PNG, preserves its source file, and recovers the hidden text. It also verifies that decoding rejects that original WebP, and checks PNG round trips across. seven image modes and all eight LSB settings, including alpha preservation.
These tests exercise the PNG functions; they do not automate the GUI or test
the WAV workflow.

## Chi-square steganalysis

The separate `steg_analysis.py` module performs basic steganalysis without changing the analysed file. `steg_analysis_cli.py` provides its command-line interface. Run it with:

```bash
python steg_analysis_cli.py sample_cover.png
python steg_analysis_cli.py sample_cover.wav
```

Useful options include:

```text
--block-size 4096       carrier values tested in each block
--max-lsb 8             highest LSB depth tested
--threshold 0.99        p-value that marks a block as suspicious
--no-packet-search      use blind chi-square analysis only
--json                  return structured JSON
```

For PNG files, the analyser reads RGB channel values and excludes alpha. For WAV files, it reads the least-significant byte of every interleaved PCM sample.
This matches the carrier mapping used by `steg_app.py`.

### How the chi-square test works

LSB replacement tends to make related values occur at similar rates. At one LSB, the analyser compares pairs such as `(0, 1)`, `(2, 3)`, and `(254, 255)`.
At two LSBs it compares groups of four, and at higher depths it compares groups
of `2 ** lsb_count` values. For each block it calculates:

```text
chi-square = sum((observed - expected)² / expected)
```

The p-value estimates how closely the values inside those groups match. A value near `1` means the frequencies are unusually equal and therefore consistent with LSB replacement. The report shows the number and fraction of
flagged blocks, maximum p-value, and longest consecutive run for every depth.
Blocks are used because a payload may occupy only part of a file; one test over
the entire carrier could dilute that local signal.

### Packet confirmation

Chi-square analysis is probabilistic. Natural or computer-generated media can already contain evenly distributed values and cause false positives. Small, repetitive, or non-random messages may cause false negatives. Compression, editing, and a payload occupying much less than one block also weaken the
signal. A statistical verdict therefore does not prove that data is hidden.

To detect short outputs from this specific prototype, the analyser also checks all eight LSB depths for an intact `STEG1` marker at an unknown start index. It then reads the declared message length and validates its CRC32 and UTF-8 data.
A valid result is reported as `confirmed`; it also reveals the start index,
LSB count, and message byte length without displaying the message. Disable
this compatibility check with `--no-packet-search` for blind chi-square-only
analysis.

The core API returns dataclasses that can be used by another Python program:

```python
from steg_analysis import analyse_file

result = analyse_file("sample_cover_stego.png")
print(result.verdict, result.confidence)
for packet in result.packet_evidence:
    print(packet.start, packet.lsb_count, packet.crc_valid)
```

`test_steg_analysis.py` verifies detection of PNG outputs at every supported LSB depth, detection of a WAV output, statistical flagging of a larger payload, absence of packet confirmation for the clean cover, and input validation.

## Important limitations
This is only a steganography prototype, not the complete assignment.

It does **not** yet provide:
- encryption/confidentiality
- SHA-256 or another cryptographic integrity hash
- digital signatures
- protected/derived start locations
- robust survival through JPEG, MP3/AAC, resizing or resampling
- attack simulation
- resistance to advanced or format-independent steganalysis

Anyone who knows the encoding method, LSB count and start location can extract the message.

## Suggested full-assignment architecture

```text
verification metadata / message
            ↓
       cryptographic hash
            ↓
        digital signature
            ↓
          packet
        ↙        ↘
   PNG embed    WAV embed
```

Verification reverses the process:

```text
PNG/WAV extract
      ↓
    packet
      ↓
verify signature
      ↓
verify cryptographic hash
      ↓
verdict
```

Keeping the cryptographic layer separate from the PNG/WAV carrier functions means the prototype can be extended without rewriting the steganography core.
