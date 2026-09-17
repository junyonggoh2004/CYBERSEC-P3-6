# Stego Integrity Verifier

INF2005 ACW1 — Steganographic Image and Audio Integrity Verification with Digital Signature-Based Authentication (Team P3-6)

A single-page, drag-and-drop web app (Flask backend + vanilla HTML/CSS/JS frontend) that hides a signed verification payload inside a PNG image, a WAV/PCM audio file, or a video file (via its audio track) using LSB replacement steganography, then lets a second party extract and verify it.

## What it does

- **Embed (encode)**: drop a cover file — PNG image, 16/32-bit PCM WAV, or a video file (MP4/MKV/MOV/AVI/WebM) with an audio track — pick a payload (typed text, any file, or an audio/MP3 file), pick how many LSBs to use (1–8) and where to start embedding, and produce a signed stego file.
- **Extract (decode)**: drop a received stego file, supply the same LSB depth / start-location secret and a public key, and get back a clear verdict: **Authentic, Tampered, Signature Invalid, Payload Missing, Wrong Start Location,** or **Cannot Verify** — plus the recovered payload.
- **One drop zone, any file**: you don't pick "image" or "audio" or "video" first — drop (or click-to-browse) any supported cover/stego file into the single drop zone and the app detects the type from the file itself and switches to the matching tab automatically. The tabs still work for manually forcing a type if you want to.
- Everything happens on one page via drag-and-drop; nothing is hard-coded (cover files, payload, bit depth, start location and keys are all chosen at runtime).

## Quick start

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt

python scripts/make_samples.py   # optional: generates sample PNG/WAV/MP4 covers in samples/
python backend/app.py            # starts the server on http://127.0.0.1:5000
```

Open `http://127.0.0.1:5000` in a browser. A fresh RSA-2048 key pair is generated automatically on first run under `backend/keys/` (the private key is **not** committed to git — see `.gitignore`).

To run the automated positive/negative test cases (no browser needed):

```bash
python tests/run_demo.py
```

This writes `test_evidence/demo_log.json` and the stego files it produced, and prints a PASS/FAIL table for every required case.

## How the required features map to the implementation

| Spec requirement | Where |
|---|---|
| Selectable LSBs 1–8 | `backend/stego/bitstream.py` (generic `embed_bits`/`extract_bits`), GUI slider |
| 16-bit / 32-bit PCM audio | `backend/stego/audio_lsb.py` auto-detects sample width from the WAV header |
| Selectable, secured start location (FR7) | `backend/stego/start_location.py` — manual offset **or** passphrase-derived (see "Innovation" below) |
| Payload = media ID, timestamp, hash, nonce, team metadata (FR3) | `backend/stego/payload.py` container format |
| Digital signature sign/verify (FR4) | `backend/stego/crypto_utils.py`, RSA-2048 / PKCS#1v1.5 / SHA-256 |
| Image & audio embed/extract (FR5/FR6/FR8) | `backend/stego/image_lsb.py`, `backend/stego/audio_lsb.py`, `backend/stego/pipeline.py` |
| Video cover object (optional challenge) | `backend/stego/video_lsb.py` — audio-track embedding, see below |
| Auto-detecting single drop zone (no cover-type pre-selection) | `frontend/app.js` `detectCoverType()`, wired into the cover/stego dropzones |
| Hash verification (FR9) | payload hash **and** a "stable cover hash" (LSBs masked) — see below |
| Verdict generation (FR10) | `payload.read_and_verify()` / `pipeline.decode()` |
| Positive & negative cases (FR11) | `tests/run_demo.py`, and the GUI's built-in "negative-case tools" (tamper button, decoy-key button, wrong-passphrase field) |
| Payload types incl. hiding an audio/MP3 file | GUI "Payload type" selector (text / file / audio); any binary payload is supported generically |
| Drag-and-drop, single page, no hard-coding | `frontend/index.html` + `frontend/app.js` |
| Synchronous and asynchronous decode | `/api/decode?mode=sync` (blocks and returns the result) vs `mode=async` (returns a `job_id`, worked on a background thread pool in `backend/stego/jobs.py`, polled via `/api/jobs/<id>`) |
| Cover/payload capacity check | `/api/capacity`, live capacity bar in the Encode panel |
| No crashes | every route in `backend/app.py` and every stage of `pipeline.decode()` catches its own exceptions and returns a structured verdict/error instead of a 500/traceback |

## Design: the verification payload and verdicts

Each stego file carries a small binary container (see the docstring in `backend/stego/payload.py`) with a magic marker, metadata (media ID, ISO timestamp, nonce, filename/mime, team metadata, and the cover's "stable hash"), a SHA-256 hash of the hidden data, an RSA signature, and the data itself. Header length fields are 16-bit (they're always small); the payload's own length field is 32-bit so a hidden file (e.g. an MP3) is not limited to 64KB.

Three independent checks produce the verdict:

1. **Signature valid?** — verifies `sign(payload_hash ‖ sha256(metadata))` with the public key. Catches metadata/hash forgery and "wrong signer".
2. **Payload hash match?** — recomputed SHA-256 of the *extracted* data vs. the signed hash. Catches corruption/edits to the hidden data itself, even though the signature (over the hash, not the data) still checks out.
3. **Cover hash match?** — the metadata carries a SHA-256 of the cover with its lowest `num_lsb` bits masked to zero, taken *before* embedding. Because masking removes exactly the bits embedding will change, this hash is identical immediately after embedding and lets a verifier detect whether the *visible/audible* part of the file (i.e., everything except the hidden payload) was altered after signing — something a naive "hash the whole file" approach cannot do, since embedding itself always changes the whole-file hash.

If the magic marker isn't found at the derived/typed start location at all, the verdict is **Wrong Start Location** (passphrase mode) or **Payload Missing** (manual mode); any other malformed/unreadable container is **Cannot Verify**.

## Start-location design & security (FR7, Learning Outcome 6)

Two interchangeable modes, chosen in the GUI:

- **Manual offset** — an exact carrier-unit index (not top-left/index 0). Transparent for teaching the mechanics, but the offset must be communicated to the verifier out-of-band; guessing it means a brute-force search over the whole file.
- **Passphrase-derived (default/recommended)** — `offset = HMAC-SHA256(passphrase, stable_cover_hash) mod usable_capacity`. The offset is **never stored anywhere**; it is re-derived independently by encoder and verifier from a shared secret passphrase and the cover's own content hash. This means (a) an attacker without the passphrase must brute-force the passphrase space rather than a small offset space, and (b) a stego file cannot be replayed against a different cover file to fool a verifier, since the offset is bound to that specific cover's hash.

**Limitation, honestly stated**: this is security by a shared secret, not perfect secrecy — a sufficiently weak/short passphrase is brute-forceable, and neither mode hides the *existence* of a payload from steganalysis (see "Limitations" below).

## Video cover object (optional challenge, spec section 8)

Rather than embedding in video *frames* — which would need a lossless video codec and a much larger/more fragile pipeline, since standard H.264/MP4 compression would destroy any LSBs written into pixels — this hides the payload in the video's **audio track**, reusing the exact same, already-tested audio LSB code:

```
encode: video --[ffmpeg: demux audio as PCM16 WAV]--> normal audio LSB embed
             --[ffmpeg: remux stego WAV back, video stream copied bit-for-bit]--> stego video (.mkv)

decode: stego video --[ffmpeg: demux audio as PCM16 WAV]--> normal audio LSB extract/verify
```

The video stream is always stream-copied (`-c:v copy`, never re-encoded), so picture quality is completely unaffected. ffmpeg itself is not a system dependency — it ships as a portable binary via the `imageio-ffmpeg` pip package (see `backend/stego/video_lsb.py`). Trade-offs, stated honestly:

- The source video must already **have an audio track** — a silent video has nothing to embed into and is rejected with a clear error.
- Because standard containers like MP4 don't support raw PCM audio, the stego output is always produced as a **Matroska (.mkv)** file (playable in VLC and most modern players/browsers, though not universally — e.g. not natively in Safari).
- The remux deliberately does **not** use ffmpeg's `-shortest` flag: encoders like AAC pad/prime the audio stream by a handful of samples relative to the video's nominal duration, and trimming to the shorter stream risks silently cutting off part of the embedded container. The full audio track (with payload) is always preserved, at the cost of a sub-frame, inaudible audio/video duration mismatch in rare cases.

## Innovation (FR13, Learning Outcome 7)

Beyond the baseline fixed-location/single-LSB demo, this implementation adds:

1. **Passphrase-derived, cover-bound start location** (above) instead of a fixed or purely-manual offset — turns "where is the payload" into a keyed secret rather than a constant.
2. **The stable/LSB-masked cover hash**, letting the verifier distinguish "the payload was tampered" from "the cover itself was tampered" from "everything is fine" — three distinct, individually meaningful failure modes instead of one generic "hash mismatch".
3. **Generic payload container** — the same format and code path hides a short text string, an arbitrary file, or an audio/MP3 file; the GUI exposes this as one payload-type selector rather than three separate tools.
4. **Video cover object via audio-track embedding** (optional challenge, above) — reuses the audio pipeline unchanged rather than building a second, riskier frame-based system.
5. **Auto-detecting drop zones** — one drop target per side (encode/decode) accepts any supported file and figures out image/audio/video for itself, instead of requiring the type to be pre-selected.
6. **Synchronous vs. asynchronous decode** as a first-class, user-visible choice (not just an implementation detail), demonstrating both a blocking verification call and a background-threaded one with progress polling.
7. **Built-in negative-case tooling in the GUI itself** (bit-flip tamper button, decoy-key button, wrong-passphrase field) so all required negative cases can be produced live during the demo without pre-preparing corrupted files.

## Limitations (Learning Outcome 8, spec section 11 criterion 7)

- **LSB replacement is not robust**: any re-compression, resampling, or format conversion of the stego file destroys the payload (this is why PNG/WAV — lossless formats — are required, not JPEG/MP3 covers).
- **Not steganalysis-resistant**: naive LSB replacement is statistically detectable (e.g. chi-square/RS analysis) by anyone looking for it; this project does not attempt to defeat steganalysis (see "Optional Challenge" in the spec).
- **When `num_lsb = 8`**, every bit of every carrier byte is available to the payload, so there is no "untouched high bits" region left for the cover-hash check to protect — cover-level tampering then can only be caught if it happens to land inside the embedded container. This is a direct, explainable trade-off between capacity and the cover-integrity check.
- **Passphrase strength is the user's responsibility**: a weak passphrase makes the derived start location guessable via brute force.
- **Single symmetric passphrase / single RSA key pair** in this demo — a production system would want per-file keys/passphrases and a proper PKI instead of one local key pair.
- **Video capacity is limited by the audio track alone** (video frames carry no payload), and a video with no audio track cannot be used as a cover at all.

## Project structure

```
backend/
  app.py                 Flask routes (REST API + serves frontend/)
  stego/
    bitstream.py          generic LSB read/write over a numpy carrier array
    crypto_utils.py        SHA-256, RSA-2048 keygen/sign/verify, stable cover hash
    start_location.py      manual / passphrase-derived start-location resolution
    payload.py              container format, build + verify logic, verdicts
    image_lsb.py            PNG cover loading/saving as a carrier array
    audio_lsb.py             WAV 16/32-bit cover loading/saving as a carrier array
    video_lsb.py              video <-> audio-track demux/remux via bundled ffmpeg
    pipeline.py                 ties the above into encode()/decode()/capacity_check()
    jobs.py                       background job registry for async decode
  keys/                    generated RSA key pair (private key git-ignored)
frontend/
  index.html / style.css / app.js    single-page drag-and-drop GUI (auto-detects cover type)
scripts/make_samples.py    generates sample PNG/WAV/MP4 cover files
tests/run_demo.py          scripted positive/negative test-case runner
docs/                       declaration-of-originality / contribution-statement templates
samples/                    generated sample cover files (git-ignored content, folder kept)
test_evidence/              output of tests/run_demo.py (screenshots from the live demo go here too)
```

## Suggested demo flow (fits the 25-minute slot)

1. Show the empty GUI, generate a key pair, briefly explain the payload container and start-location design (Learning Outcomes 1, 3, 6).
2. **Positive — image**: drag `samples/cover_image.png`, pick a short (Learning-Outcome) message, encode, send to Party B, decode → Authentic.
3. **Positive — audio**: same with `samples/cover_audio_16.wav` and the large (Project-Overview) message, using a manual start offset this time.
4. **Capacity check negative**: try to embed something clearly too large for a cover; show the rejection message.
5. **Negative — tampered payload**: use the "flip a bit" tool after encoding, decode → Tampered.
6. **Negative — wrong signer**: use the "decoy key" tool, decode → Signature Invalid.
7. **Negative — wrong start location**: change the passphrase before decoding → Wrong Start Location.
8. **Payload variety**: hide an MP3/audio file as the payload inside the image cover, extract it, play it back.
9. **Optional challenge — video**: drop `samples/cover_video.mp4` straight into the drop zone (no tab click needed — it auto-detects as video), encode, decode → Authentic; mention the audio-track-embedding design and its trade-offs.
10. Wrap up with limitations and each member's contribution.
