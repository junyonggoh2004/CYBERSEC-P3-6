# Stego Integrity Verifier

INF2005 ACW1 · Team P3-6. First draft on Junyong's branch, based on Gabriel's
`54a5789` frontend and Kim's PNG steganalysis implementation.

## Run locally

From this directory, with Python 3.11+:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python backend/app.py
```

Open **http://127.0.0.1:5000**. Keep the terminal running. This is a local assignment
demo, not a public multi-user key-management service.

## Pages and user journey

1. **Protect — Alice:** select the original PNG or WAV, choose hidden content,
   select SHA-256 (default) or SHA-512, select Alice's signing pair, choose 1–8
   lowest bits and a manual or passphrase-derived start location.
2. Review exact capacity and the draft verification record. The app includes
   metadata, signature, header and field-padding overhead. It shows each depth's
   capacity and the minimum sufficient depth without changing the user's choice.
3. Sign and create the stego object. Inspect/download the result and its final
   record. The draft nonce/timestamp are regenerated for the final file.
4. **Verify — Bob:** upload the received object, use the agreed LSB depth/location,
   and explicitly supply Alice's trusted public key. No Bob key pair is required.
   An in-app shortcut helps local testing; the assignment demonstration must also
   show an actual Alice-to-Bob transfer and verification of Bob's downloaded copy.
5. **Compare:** original/stego previews, hidden-content preview for the last
   generated pair, linked image zoom, RGB(A) overlaid histograms, amplified
   difference image, or aligned audio waveform envelopes. Independently uploaded
   pairs do not claim to know the hidden content.
6. **Steganalysis:** independent PNG chi-square and RS containers, per-channel
   measurements, provisional thresholds, explanations and JSON export.
   Histograms stay on Compare.
7. **Alice's keys:** view fingerprints/public keys, export public keys, import
   demo RSA private keys, and generate additional pairs without replacing old ones.

Selections and generated files persist across pages in memory, not across reloads.
Secrets are excluded from downloaded reports. A new analysis/verification input
invalidates the displayed result.

## Supported first-draft combinations

| Cover | Hidden content | Output |
|---|---|---|
| PNG | Text | PNG |
| PNG | Audio file | PNG |
| WAV/PCM | Text | WAV |
| WAV/PCM | Image file | WAV |

Audio covers support signed 16-bit and 32-bit PCM. Payload files are carried as
bytes, so an MP3 payload can be hidden in PNG although MP3 is not a supported
cover. Legacy video functions remain in the backend library but are not exposed
in this first-draft workflow.

## What is signed and hashed

New files use container **version 2**. The verification record contains media ID,
UTC timestamp, random nonce, filename/MIME, content length/type, team metadata,
hash algorithm, stable cover hash, signer fingerprint and embedding settings.

The existing RSA PKCS#1 v1.5 signature scheme is retained through the cryptography
library. New pairs are RSA-2048; imported RSA pairs must be at least 2048 bits.
The selected SHA-256/SHA-512 algorithm is used for content hashing, record hashing
and the signature. The signed message binds the expected content hash and
verification record. No custom cryptographic primitive is implemented.

The stable cover hash masks the lowest selected bits of every carrier value and
also binds carrier properties in V2. It does **not** hash the PNG/WAV container
bytes. The receiver repeats the same normalisation. V1 SHA-256 records remain
readable using their original layout and stable-hash rule.

The record viewer shows the expected and recomputed hashes, signature, key
fingerprint, metadata and trust status. Signature verification establishes a link
to the supplied public key, not that the key independently belongs to Alice.

### LSB semantics and capacity

For an 8-bit image channel, depth 3 changes the three rightmost bits.
For audio it changes the three lowest bits of a **PCM sample**, not of each byte.
Carrier traversal is row-major channel order for images and interleaved sample
order for WAV. The current image carrier includes alpha for RGBA images;
steganalysis excludes alpha and reports that limitation.

Each container field rounds up to a whole carrier unit. Exact fit is therefore
the sum of `ceil(field_bits / depth)`, not simply the raw package byte length.
The API and UI use the same calculation before writing.

The start-location derivation always uses a SHA-256 stable cover hash,
independently of the selected content hash. Bob can reproduce it before reading
the record. Changing depth or cover values may change a derived location.
Passphrases are not stored in the record, and hidden locations are not encryption:
candidate offsets may still be searched.

## Verification results

Every returned verdict contains the same evidence fields and six check slots:
extraction, record binding, signature, content integrity, cover integrity and
decryption (not applicable). States include Passed, Failed, Not run and Not
applicable; unavailable values are shown explicitly.

- **Authentic:** the signature and required integrity checks pass.
- **Signature Invalid:** the supplied key does not validate the signed record;
  this does not uniquely identify whether the key, signature or record is wrong.
- **Tampered:** a valid signed reference exists, but the content, stable cover or
  signed record binding differs.
- **Payload Missing:** no recognised package at the attempted settings. This may
  mean incorrect depth/location, damaged header or no supported payload.
- **Cannot Verify:** missing/invalid key, unsupported media/settings, malformed
  package, or another condition that prevents completing verification.

The app does not claim **Wrong Start Location** merely because extraction fails.
That label needs independent evidence unavailable to a blind verifier. The
negative-case tools alter a copy's hidden content or a protected carrier bit;
the original generated file remains available.

## Scope and limitations

- Signing and hiding **do not encrypt** the content. No recipient encryption or
  Bob private-key workflow is included. The brief's custom-payload confidentiality
  requirement still needs an explicit team decision before claiming full coverage.
- A stable cover hash excludes selected low bits. At depth 8 in an 8-bit image,
  no channel-value bits remain protected by that hash. Content integrity is still
  checked separately. Geometry remains bound by the V2 representation.
- Metadata/timestamps/nonces alone do not prevent replay.
- LSB replacement is fragile under lossy compression, resampling and conversion.
  Decoding does not restore the overwritten original carrier bits.
- Comparison metrics describe changes, not authenticity.
- Chi-square p-values are not probabilities that secret data exists. RS uses
  mask asymmetry, not an estimated payload length. Thresholds are provisional;
  both false positives and missed payloads are possible. Higher-depth analysis is
  exploratory. An Authentic file can also show hidden-data indicators.
- Demo private keys are stored unencrypted locally. Additional pairs live in
  ignored `backend/keys/saved/`; existing legacy key files are preserved.
  Import/export public keys separately and check their fingerprints.

For the detector mathematics and existing evaluation, see
[Steganalysis guide](docs/STEGANALYSIS_GUIDE.md) and
[evaluation results](evidence/steganalysis/RESULTS.md).

## Verification and tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_steganalysis.py tests/test_workflow.py -q
```

The tests isolate keys in temporary directories. They cover both hashes at all
eight depths, both carriers and cross-media payloads, 32-bit PCM, exact capacity,
legacy compatibility, deterministic verdict evidence, non-destructive keys and
paired statistics. If the system temporary directory is restricted, create
`test_evidence/` and add `--basetemp test_evidence/pytest-temp`.

Optional frontend DOM integration test (Node.js and jsdom required):

```powershell
npm install --no-save --package-lock=false jsdom
python tests/make_ui_fixtures.py
# Start the app in another terminal first.
$env:STEGO_TEST_URL = 'http://127.0.0.1:5000'
node tests/frontend_workflow.cjs
```

This exercises app handlers and real HTTP APIs with browser file/canvas adapters.
It is **not** a rendered-layout or real-browser test. Visual review of desktop,
mobile, focus behaviour and media playback remains necessary.

The older `python tests/run_demo.py` demonstration runner remains available,
including legacy video cases when sample video is present.
