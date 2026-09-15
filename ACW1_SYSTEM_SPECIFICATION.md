# INF2005 ACW1 System Specification

## Steganographic Image and Audio Integrity Verification

| Document field | Value |
|---|---|
| Team | P3-6 |
| Members | Jun Yong, Gabriel, Jian Xuan, Matthias, Kim, Gerome |
| Document purpose | Define what the system must do, how it behaves, and how assignment compliance will be demonstrated |
| Target platform | Windows |
| Implementation language | Python 3 |
| GUI framework | PySide6 |
| Submission date | 30 September 2026 |
| Demonstration date | 1 October 2026 |
| Status | Initial implementation baseline |

## 1. Purpose and reading guide

This document is the source of truth for the behaviour and security design of the P3-6 INF2005 ACW1 system. It translates the assignment specification into implementable, testable requirements while retaining the mandatory scope, functional requirements, required security workflow, and assessment expectations.

This is not a task tracker. Work ownership, dependencies, dates, and progress are maintained in `ACW1_IMPLEMENTATION_PLAN.md`.

Requirement words have the following meanings:

- **Shall** indicates a mandatory requirement.
- **Should** indicates a recommended requirement that may be deferred only with a recorded reason.
- **May** indicates an optional capability.
- **Provisional** indicates a decision that can change after lecturer clarification.

## 2. Project overview

The system is a Windows desktop application that hides a security-verification package inside an image or audio cover object using LSB replacement. Party A protects a media file by creating a payload, hashing a stable representation of the media, digitally signing the payload, optionally encrypting it, and embedding the result. Party B receives the stego media, extracts the package, validates the signature and media hash, and receives a clear verdict with supporting reasons.

The mandatory cover objects are:

- PNG images, using RGB channel data as the initial supported representation.
- Uncompressed WAV audio, using PCM sample data as the initial supported representation.

The chosen optional challenge is steganalysis. The application will use two established techniques—chi-square pairs-of-values analysis and RS analysis—to estimate whether an image shows statistical signs of LSB replacement. Supporting WAV LSB statistics may be provided, but the assessed two-method implementation will focus on PNG, where both selected methods are appropriate and defensible.

## 3. Goals and success criteria

The project is successful when the team can reproducibly demonstrate all of the following:

1. Protect and verify a PNG image through the complete Party A-to-Party B workflow.
2. Protect and verify a PCM WAV file through the same workflow.
3. Select one to eight least-significant bits and, where practical, individual bit positions through the GUI.
4. Reject a payload that exceeds the usable carrier capacity.
5. Select a manual start location or securely derive one from a passphrase.
6. Extract an intact payload after the stego file has been saved, transferred, downloaded, and reopened.
7. Validate a digital signature using the sender's public key.
8. Recompute the relevant stable-media hash and compare it with the signed value.
9. Distinguish successful verification from representative failure cases using clear verdicts.
10. Demonstrate at least two positive cases and at least three negative cases, including at least one positive and one negative case for each mandatory cover type.
11. Analyse a PNG with chi-square and RS steganalysis and explain the probabilistic result and limitations.
12. Provide source code, samples, tests, evidence, setup instructions, key instructions, originality documentation, contribution information, and a rehearsed demonstration plan.

## 4. Scope

### 4.1 Mandatory scope

The system shall provide:

- PNG input, protection, saving, display, extraction, and verification.
- PCM WAV input, protection, saving, playback, extraction, and verification.
- Text and file-based payload input.
- Compact verification metadata containing a media ID, timestamp, hash, nonce, and team-defined metadata.
- Cryptographic hashing.
- Digital signing with a private key and verification with the corresponding public key.
- LSB replacement embedding and extraction.
- A GUI selection for one to eight LSBs.
- A defensible variable payload start-location design.
- Capacity checking before embedding.
- Clear verification results and diagnostic details.
- Positive, negative, boundary, and malformed-input testing.
- Reproducible source code, sample files, and evidence.
- Original-versus-stego image display and audio playback.
- A demonstrable transfer from Party A to Party B, such as sending the stego file by email and downloading it into a different folder.

### 4.2 Selected innovation: steganalysis

The system shall implement:

- Chi-square pairs-of-values analysis for conventional LSB replacement.
- RS analysis for conventional image LSB replacement.
- A combined, explainable likelihood assessment.
- Results for clean and stego samples across multiple payload sizes.
- Honest reporting of false positives, false negatives, and environmental sensitivity.

### 4.3 Additional planned features

The following features support the mandatory work but must not delay it:

- AES-256-GCM authenticated encryption for confidential payloads.
- Manual and automatic start-location modes.
- Key generation and key import.
- Exportable verification reports.
- Image difference views and audio quality measurements for test evidence.
- Pseudorandom non-contiguous embedding positions after the reliable sequential baseline works.

### 4.4 Out of scope for the initial submission

- Video cover objects.
- JPEG or MP3 embedding.
- Surviving lossy compression, resizing, resampling, or format conversion.
- Network accounts, cloud storage, or a server backend.
- Claims that steganalysis proves the presence or absence of hidden information.
- Production-grade certificate authorities or public-key infrastructure.
- Protection against a fully privileged attacker who can replace the application or trusted public key.

## 5. Stakeholders and operating scenario

### 5.1 Party A: protector and signer

Party A selects an original PNG or WAV file, supplies a payload and metadata, chooses the LSB and start-location settings, signs the verification payload, optionally encrypts the signed package, embeds it, and saves a new stego file. Party A controls the signing private key.

### 5.2 Party B: receiver and verifier

Party B obtains the stego file through a separate transfer, opens it from a receiver folder, supplies any required extraction secret, loads Party A's trusted public key, extracts the package, verifies it, and reviews the final verdict and supporting checks.

### 5.3 Evaluator

The evaluator may provide an unknown payload during the demonstration. Its exact content, size, key material, and key format are not yet known. The application therefore needs flexible text/file payload input, capacity feedback, and importable key handling.

## 6. Confirmed decisions, assumptions, and lecturer questions

### 6.1 Confirmed team decisions

| Topic | Decision |
|---|---|
| Language | Python 3 |
| GUI | PySide6 desktop GUI |
| Platform | Windows |
| Image baseline | Lossless PNG, RGB and RGBA |
| Audio baseline | Uncompressed 16-bit PCM WAV, mono and stereo |
| Hash | SHA-256 |
| Signature | Ed25519 |
| Encryption | AES-256-GCM for encrypted payload mode |
| Start modes | Manual and passphrase-derived automatic mode |
| Steganalysis | Chi-square pairs-of-values and RS analysis |
| Delivery priority | Finish and prove all mandatory functions before adding complexity |

### 6.2 Questions to clarify with the lecturer

These questions shall remain visible until answered. Implemented assumptions should be configurable so that clarification does not require a redesign.

| Question | Current team response or provisional decision |
|---|---|
| Does “selectable LSBs from bits 1 to 8” mean a count of consecutive low-order bits, selection of an individual bit plane, or an arbitrary set of bit positions? | Provide “lowest N bits” presets from 1–8 and, where practical, an advanced individual bit-position selector. |
| Must the start location be selected manually, automatically derived, or both? | Implement both manual and automatic modes. |
| Are established cryptographic and media-processing libraries permitted? | Assume yes. |
| May Party A and Party B share an extraction passphrase out of band? | Assume yes. The public key and passphrase serve different purposes. |
| Must the application operate completely offline? | Implement it so that core protection and verification work offline. |
| What form will the unknown demonstration payload take? | Accept UTF-8 text and arbitrary file bytes. |
| What encryption technique is expected for the unknown demonstration payload? | Use AES-256-GCM unless instructed otherwise. |
| Will the evaluator provide signing or encryption keys? | Unknown; support locally generated and imported keys. |
| If keys are supplied, which algorithms and encodings will be used? | Pending. Initially support Ed25519 keys in PEM form and a raw or encoded 256-bit AES key where safe. |
| Is passphrase-based encryption acceptable when no raw key is supplied? | Assume yes; derive purpose-separated keys using a standard KDF. |
| Must steganalysis cover both mandatory media types? | Focus the two formal techniques on PNG; add WAV LSB statistics if time permits. |
| Must an emailed file transfer occur live, or is a prepared sender/receiver-folder demonstration acceptable? | Plan for a real transfer if network conditions allow and retain a local fallback. |

## 7. Terminology

| Term | Meaning in this project |
|---|---|
| Cover object | Original image or audio file before hidden data is embedded |
| Stego object | Output media containing an embedded package |
| Payload | Verification data and optional user message before framing |
| Frame | The byte-level structure embedded into the carrier |
| Carrier unit | An eligible RGB channel value or PCM sample value used to store bits |
| LSB | Least-significant bit of a carrier value |
| Stable media representation | Deterministic media data with intentional embedding positions normalised or excluded before hashing |
| Bootstrap | Small fixed-location structure used to recover the settings needed to find the variable payload |
| Nonce | A value that should not repeat for a given cryptographic key and operation |
| Salt | Public random input used during key derivation |
| Digital signature | Private-key operation verified with a public key to establish payload origin and integrity |
| Steganalysis | Statistical estimation of whether a carrier may contain hidden data |

## 8. Functional requirements

### 8.1 Media input and output

| ID | Requirement |
|---|---|
| `MED-FR-001` | The system shall open and validate PNG images. |
| `MED-FR-002` | The system shall support RGB PNG and RGBA PNG while leaving the alpha channel unchanged. |
| `MED-FR-003` | The system shall open and validate uncompressed PCM WAV audio. |
| `MED-FR-004` | The initial WAV implementation shall support 16-bit mono and stereo files. |
| `MED-FR-005` | The system shall reject unsupported, malformed, or truncated media with a readable reason. |
| `MED-FR-006` | The system shall save protected media as a new file and shall not overwrite the input without explicit confirmation. |
| `MED-FR-007` | The system shall display original and stego images side by side or through an equivalent comparison view. |
| `MED-FR-008` | The system shall play original and stego WAV audio through separate labelled controls. |
| `MED-FR-009` | The system shall preserve image dimensions and supported WAV format parameters. |
| `MED-FR-010` | A saved stego object shall remain decodable after the application closes and reopens it. |

These requirements expand assignment FR1, FR2, FR5, FR6, and the mandatory display/playback requirement.

### 8.2 Payload creation and framing

| ID | Requirement |
|---|---|
| `PAY-FR-001` | The system shall accept a UTF-8 text message. |
| `PAY-FR-002` | The system shall accept an arbitrary file as the user payload, subject to capacity and safe-size limits. |
| `PAY-FR-003` | The verification payload shall include a schema version, media type, media ID, UTC timestamp, SHA-256 media hash, random nonce, and team-defined metadata. |
| `PAY-FR-004` | The system shall provide presets for the required short and large demonstration messages and allow a custom payload. |
| `PAY-FR-005` | Payload serialization shall be deterministic so that signed bytes can be reconstructed exactly. |
| `PAY-FR-006` | The embedded frame shall contain a magic identifier, version, flags, length information, payload package, and integrity fields required by the selected mode. |
| `PAY-FR-007` | The decoder shall validate every declared length against available capacity and configured resource limits before allocating or reading data. |
| `PAY-FR-008` | Unknown frame versions shall be rejected as unsupported rather than interpreted as the current version. |

These requirements expand assignment FR3 and the required variable-payload demonstrations.

### 8.3 Capacity and bit selection

| ID | Requirement |
|---|---|
| `CAP-FR-001` | The system shall calculate usable capacity before embedding. |
| `CAP-FR-002` | Capacity shall account for bootstrap bits, payload start, selected bit positions, framing, signature, encryption overhead, and unavailable carrier regions. |
| `CAP-FR-003` | The GUI shall show available capacity, required package size, and remaining capacity. |
| `CAP-FR-004` | Embedding shall be blocked when the package does not fit. |
| `CAP-FR-005` | The GUI shall offer lowest-N-bit presets for values 1 through 8. |
| `CAP-FR-006` | The advanced design should allow one or more individual bit positions from 1 through 8 to be selected. |
| `CAP-FR-007` | The GUI shall warn that using higher bit positions or many bits increases visible or audible distortion. |

For a carrier with `U` eligible carrier units and `B` selected positions per unit, a starting approximation is:

```text
available_bits = (U * B) - reserved_bootstrap_bits - unavailable_prefix_bits
available_bytes = floor(available_bits / 8)
fits = framed_package_bytes <= available_bytes
```

The implementation shall use the actual generated position sequence rather than relying only on this approximation.

### 8.4 Start-location design

| ID | Requirement |
|---|---|
| `LOC-FR-001` | The system shall support a user-selected manual payload start location. |
| `LOC-FR-002` | The system shall support automatic passphrase-derived payload start locations. |
| `LOC-FR-003` | An automatic start location shall be derived with a standard password KDF and keyed pseudorandom function, not Python's non-cryptographic `hash()` function. |
| `LOC-FR-004` | A small bootstrap shall provide the salt, payload length, mode, and bit-selection data necessary for authorised recovery. |
| `LOC-FR-005` | The bootstrap shall not store the derived start offset directly in automatic mode. |
| `LOC-FR-006` | The bootstrap shall be authenticated so accidental corruption and incorrect secrets do not silently produce plausible settings. |
| `LOC-FR-007` | Derived positions shall exclude the bootstrap and invalid carrier locations. |
| `LOC-FR-008` | Party A and Party B shall derive the same location from the same supported media properties, salt, passphrase, and version. |
| `LOC-FR-009` | The verifier shall explain whether a location was entered manually, recovered, or derived. |

The baseline automatic derivation is conceptually:

```text
master_key   = KDF(passphrase, bootstrap_salt)
location_key = HKDF(master_key, info="P3-6/location/v1")
seed         = HMAC-SHA-256(location_key, stable_public_media_properties)
start        = integer(seed) mod valid_start_count
```

The initial reliable version may embed sequentially from `start`. A later enhancement may seed a cryptographically suitable deterministic generator to distribute the package over unique pseudorandom positions.

### 8.5 Hashing and stable-media verification

| ID | Requirement |
|---|---|
| `HSH-FR-001` | The system shall use SHA-256 as the cryptographic media hash. |
| `HSH-FR-002` | The system shall define a deterministic stable representation for each supported carrier. |
| `HSH-FR-003` | The representation shall normalise or exclude the exact carrier bit positions reserved for the bootstrap and framed package. |
| `HSH-FR-004` | All other protected media data and relevant format properties shall contribute to the hash. |
| `HSH-FR-005` | The verifier shall reconstruct the same representation and compare the computed hash with the value contained in the signed payload. |
| `HSH-FR-006` | The GUI shall show expected and computed hashes without presenting a match as sufficient proof by itself. |

A whole-file hash is unsuitable because embedding intentionally changes the output file. Clearing every LSB in the whole carrier is also unnecessarily weak. The recommended representation normalises only the exact bit positions intentionally used by the bootstrap and package. This produces the same hash before and after valid embedding while retaining coverage of the remaining media data.

The package size and carrier positions must be determined before the final media hash is calculated. Fixed-length hash and signature fields allow a two-pass construction:

1. Build a package template with fixed-size placeholders.
2. Determine its final length and all embedding positions.
3. Compute the stable-media hash with those positions normalised.
4. insert the hash into the payload.
5. Sign, optionally encrypt, frame, and embed without changing the determined length.

### 8.6 Digital signatures and keys

| ID | Requirement |
|---|---|
| `SIG-FR-001` | The system shall generate or import an Ed25519 signing key pair. |
| `SIG-FR-002` | Party A shall sign the deterministic serialized verification payload or its documented hash using the private key. |
| `SIG-FR-003` | Party B shall verify the signature using the corresponding trusted public key. |
| `SIG-FR-004` | The application shall never claim a signature is valid merely because the payload was extracted or decrypted. |
| `SIG-FR-005` | A different public key, modified signed field, or modified signature shall cause signature verification to fail. |
| `SIG-FR-006` | Private-key contents shall not be written to normal logs or verification reports. |
| `SIG-FR-007` | The public key or its fingerprint used during verification shall be shown in the detailed result. |
| `SIG-FR-008` | Demo keys shall be clearly labelled as assignment-only keys. |

Signing proves payload origin relative to the trusted public key and protects signed fields from undetected modification. It does not provide secrecy.

### 8.7 Optional authenticated encryption

| ID | Requirement |
|---|---|
| `ENC-FR-001` | The system should provide an encrypted payload mode using AES-256-GCM. |
| `ENC-FR-002` | The encryption key shall be imported directly or derived from a passphrase using a standard KDF and random salt. |
| `ENC-FR-003` | A fresh nonce shall be generated for each AES-GCM encryption under a given key. |
| `ENC-FR-004` | Key derivation shall produce purpose-separated encryption, bootstrap-authentication, and location keys. |
| `ENC-FR-005` | Decryption authentication failure shall stop parsing, signature checking, and hash comparison of untrusted plaintext. |
| `ENC-FR-006` | The application shall not log passphrases, raw encryption keys, or decrypted confidential payloads unless the user explicitly exports them. |

Recommended protection ordering:

```text
verification payload -> Ed25519 signature -> signed package -> AES-GCM -> frame -> LSB embedding
```

Recommended verification ordering:

```text
LSB extraction -> frame validation -> AES-GCM authentication/decryption
-> payload parsing -> Ed25519 verification -> media-hash comparison
```

### 8.8 Image embedding and extraction

| ID | Requirement |
|---|---|
| `IMG-FR-001` | Image embedding shall operate on decoded RGB channel values rather than compressed PNG file bytes. |
| `IMG-FR-002` | RGBA alpha values shall remain unchanged. |
| `IMG-FR-003` | The encoder shall replace only selected bit positions at generated eligible positions. |
| `IMG-FR-004` | The decoder shall enumerate carrier positions in exactly the same documented order. |
| `IMG-FR-005` | The saved PNG shall retain the original dimensions and supported colour mode. |
| `IMG-FR-006` | The GUI shall display original and stego images with dimensions, file size, bit settings, and payload size. |
| `IMG-FR-007` | The system should calculate changed-channel count, mean squared error, and PSNR for comparison evidence. |

PNG compression parameters or metadata may change on save without representing visual tampering. Verification is therefore based on the documented decoded pixel representation and selected stable properties, not byte-for-byte PNG container equality.

### 8.9 Audio embedding and extraction

| ID | Requirement |
|---|---|
| `AUD-FR-001` | Audio embedding shall operate only on PCM sample data and shall not place payload data in the WAV header. |
| `AUD-FR-002` | The encoder and decoder shall use the same little-endian signed-sample interpretation. |
| `AUD-FR-003` | WAV channels, sample rate, sample width, frame count, and compression type shall be validated and preserved. |
| `AUD-FR-004` | The initial implementation shall support 16-bit mono and stereo PCM. |
| `AUD-FR-005` | The saved WAV shall remain playable and decodable. |
| `AUD-FR-006` | The GUI shall provide labelled playback controls for original and stego audio. |
| `AUD-FR-007` | The system should calculate changed-sample count, mean squared error, and signal-to-noise ratio for evidence. |

The precise mapping between the selected 1–8 settings and a 16-bit sample shall be documented in the GUI and README. The preferred interpretation is positions 1–8 of the sample's least-significant byte, preserving the upper byte in baseline mode.

### 8.10 Extraction, verification, and verdicts

| ID | Requirement |
|---|---|
| `VER-FR-001` | The system shall extract the bootstrap, payload frame, payload, and signature from both supported carrier types. |
| `VER-FR-002` | Each verification stage shall return a structured status and explanation. |
| `VER-FR-003` | The final verdict shall be determined by a central verdict engine rather than GUI-specific conditionals. |
| `VER-FR-004` | The application shall support `Authentic`, `Tampered`, `Signature Invalid`, `Payload Missing`, `Wrong Start Location`, and `Cannot Verify` outcomes where evidence distinguishes them. |
| `VER-FR-005` | `Authentic` shall require a valid frame, successful decryption when enabled, a valid signature, and a matching stable-media hash. |
| `VER-FR-006` | Ambiguous failures shall be reported as `Cannot Verify` with stage-specific details rather than an unsupported claim. |
| `VER-FR-007` | The application shall safely handle missing payloads, bad magic, unsupported versions, impossible lengths, wrong secrets, corrupted frames, wrong public keys, and modified media. |
| `VER-FR-008` | The user shall be able to save a verification report without secrets or private-key material. |

Verdict precedence is defined in Section 15.

### 8.11 Steganalysis

| ID | Requirement |
|---|---|
| `SA-FR-001` | The system shall implement chi-square pairs-of-values analysis for PNG LSB replacement. |
| `SA-FR-002` | The system shall implement RS analysis for PNG LSB replacement. |
| `SA-FR-003` | Each technique shall return its raw statistic, interpreted score, and a plain-language explanation. |
| `SA-FR-004` | The system shall combine the two outputs into a cautious likelihood category such as low, inconclusive, or high indication of LSB replacement. |
| `SA-FR-005` | The application shall not equate a high steganalysis score with cryptographic tampering or a low score with authenticity. |
| `SA-FR-006` | The evaluation shall include clean and stego images, multiple payload sizes, and multiple LSB settings. |
| `SA-FR-007` | The evidence shall report false-positive and false-negative observations. |
| `SA-FR-008` | Supporting WAV analysis may report LSB bit balance, entropy, and pairs-of-values statistics, clearly labelled as supplementary. |

### 8.12 Evidence and reproducibility

| ID | Requirement |
|---|---|
| `REP-FR-001` | A clean Windows environment shall be able to install dependencies and run the application using the README. |
| `REP-FR-002` | The repository shall contain or reference licensed sample originals, protected outputs, tampered outputs, and expected results. |
| `REP-FR-003` | Automated tests shall be runnable with one documented command. |
| `REP-FR-004` | Test evidence shall include screenshots, saved reports, or logs for required positive and negative cases. |
| `REP-FR-005` | Public keys and safe reproduction instructions shall be included. Assignment-only private keys may be included only if clearly labelled and permitted. |
| `REP-FR-006` | The project shall include the signed originality and contribution documents required by the assignment. |
| `REP-FR-007` | AI use shall be disclosed and important generated code or claims shall be checked by team members. |

## 9. Non-functional requirements

### 9.1 Usability

- `NFR-USA-001`: A first-time user shall be guided through protection and verification in an obvious order.
- `NFR-USA-002`: Controls that are not valid for the current stage shall be disabled or accompanied by actionable validation.
- `NFR-USA-003`: Errors shall state what failed, likely causes, and safe corrective action.
- `NFR-USA-004`: Security terminology shall have tooltips or brief explanations.
- `NFR-USA-005`: Destructive defaults, silent overwrites, and hidden key assumptions shall be avoided.

### 9.2 Reliability

- `NFR-REL-001`: Valid files protected by the application shall round-trip through save, close, reopen, extract, and verify.
- `NFR-REL-002`: The same input, extraction settings, and secret shall generate the same position sequence where deterministic behaviour is required.
- `NFR-REL-003`: Partially written output files shall not replace a previously valid result.
- `NFR-REL-004`: Malformed input shall produce a controlled failure rather than a crash.

### 9.3 Security

- `NFR-SEC-001`: The system shall use established cryptographic library implementations.
- `NFR-SEC-002`: Random salts, nonces, and demo keys shall come from a cryptographically secure random source.
- `NFR-SEC-003`: Secrets shall be masked in the GUI by default and omitted from normal logs.
- `NFR-SEC-004`: Untrusted length fields and metadata shall be bounded before use.
- `NFR-SEC-005`: No verification result shall implicitly establish that a public key belongs to a real-world person; public-key trust is an external assumption.

### 9.4 Performance

- `NFR-PER-001`: The GUI shall remain responsive during material file processing, using a worker thread or progress reporting where necessary.
- `NFR-PER-002`: A representative classroom PNG or WAV should protect and verify within a practical demonstration time on the target Windows laptop.
- `NFR-PER-003`: Capacity calculation shall complete before expensive signing or encryption work.

### 9.5 Maintainability and auditability

- `NFR-MNT-001`: GUI, carrier adapters, payload framing, cryptography, location generation, verification, and steganalysis shall be separate modules.
- `NFR-MNT-002`: Core services shall be callable without the GUI so they can be unit tested.
- `NFR-MNT-003`: Algorithms, frame versions, and key encodings shall be named explicitly rather than inferred.
- `NFR-MNT-004`: Important verification stages shall generate inspectable, secret-safe diagnostic records.

## 10. Proposed architecture

```text
PySide6 GUI
├── Protect workflow controller
├── Verify workflow controller
└── Steganalysis controller
        │
Application services
├── Protection service
├── Verification and verdict service
├── Steganalysis service
└── Report service
        │
Security and data services
├── Payload serializer and frame codec
├── Capacity calculator
├── Stable-media hasher
├── Ed25519 signing service
├── AES-GCM encryption service
├── KDF and key-loading service
└── Start-position generator
        │
Carrier abstraction
├── PNG carrier adapter
└── WAV/PCM carrier adapter
```

Carrier adapters expose a common conceptual interface:

```text
validate(file)
describe(file)
eligible_units(file)
capacity(bit_selection, reserved_positions)
read_selected_bits(positions, bit_selection)
replace_selected_bits(positions, bit_selection, data)
stable_representation(normalised_positions)
save(output_path)
```

The GUI shall call application services rather than manipulating pixel channels, samples, signatures, or keys directly.

## 11. Input and output specification

### 11.1 Inputs

| Input | Required validation |
|---|---|
| PNG file | Signature/type, decodability, colour mode, dimensions, safe size |
| WAV file | RIFF/WAVE structure, PCM encoding, supported sample width/channels, safe size |
| Text payload | Valid UTF-8 after application encoding and within capacity |
| File payload | Readable, bounded, filename treated as metadata rather than an output path |
| Media ID | Non-empty, length-bounded, valid Unicode text |
| Metadata | Supported fields, bounded lengths, deterministic serialization |
| LSB/bit selection | At least one supported position and no invalid index |
| Manual start | Integer within the carrier-specific valid range |
| Passphrase | Non-empty in modes that require it; no silent trimming |
| Signing key | Supported Ed25519 private or public key for the requested operation |
| Encryption key | Valid 256-bit key or supported passphrase mode |

### 11.2 Outputs

| Output | Contents |
|---|---|
| Stego PNG | Original decoded image with selected carrier bits replaced |
| Stego WAV | Original PCM audio with selected sample bits replaced |
| Verification result | Final verdict plus per-stage statuses and explanations |
| Verification report | Safe JSON or text representation excluding secrets |
| Steganalysis report | Method statistics, scores, interpretation, configuration, limitations |
| Test evidence | Screenshots, logs, metrics, hashes, and filenames needed to reproduce cases |

Default names should be descriptive and collision-safe, for example `photo.protected.png` and `speech.protected.wav`.

## 12. Payload and frame design

### 12.1 Logical signed payload

The initial logical payload schema is:

```json
{
  "schema_version": 1,
  "media_type": "image/png",
  "media_id": "IMG-DEMO-001",
  "created_at_utc": "2026-09-15T14:30:00Z",
  "stable_media_hash_algorithm": "SHA-256",
  "stable_media_hash": "hex-or-bytes",
  "payload_nonce": "random-value",
  "content_type": "text/plain; charset=utf-8",
  "content_name": "message.txt",
  "content": "encoded-user-content",
  "metadata": {
    "issuer": "P3-6",
    "purpose": "INF2005 ACW1"
  }
}
```

The actual serialization may use canonical JSON or CBOR. The chosen representation shall be locked by automated test vectors before integration. Binary payload content should not be expanded inefficiently unless capacity permits; CBOR is preferred if the team is comfortable validating it.

### 12.2 Signed package

```text
signature algorithm identifier
signer public-key fingerprint
serialized logical payload
Ed25519 signature (64 bytes)
```

The public key itself need not be embedded. Embedding only its fingerprint forces the verifier to use an independently trusted public key instead of trusting a key supplied by the suspicious media.

### 12.3 Bootstrap and frame

An exact byte layout shall be frozen during the framing task. It shall include at least:

```text
Bootstrap:
  magic
  bootstrap version
  media adapter identifier
  flags
  selected bit positions or lowest-N setting
  KDF identifier and salt
  framed package length
  bootstrap authenticator or checksum appropriate to mode

Variable-location frame:
  frame magic
  frame version
  encryption identifier
  encryption nonce when enabled
  signed package or ciphertext
  AES-GCM authentication tag when enabled
```

The bootstrap is discoverable and therefore is not a confidentiality boundary. It exists to support decoding. Automatic-mode location security comes from the passphrase-derived key and authenticated configuration, not from hiding the bootstrap format.

## 13. Required protection workflow

This workflow implements and expands the assignment's Required Security Workflow.

1. Party A selects an original PNG or supported WAV cover object.
2. The system validates the file and presents its properties and preview/playback control.
3. Party A selects a required payload preset, enters text, or chooses a payload file.
4. Party A enters the media ID and team-defined metadata.
5. Party A chooses a lowest-N LSB preset or supported bit-position selection.
6. Party A chooses manual or automatic start-location mode.
7. In automatic mode, Party A enters a passphrase and the system generates a random KDF salt.
8. Party A chooses plaintext-signed or encrypted-signed payload mode.
9. The system constructs a fixed-length package template and calculates the complete framed size.
10. The system calculates actual usable capacity and stops with an explanation if the package cannot fit.
11. The system determines bootstrap and payload positions, excluding overlaps and invalid regions.
12. The system constructs the stable media representation and computes SHA-256.
13. The system completes the payload using the media ID, UTC timestamp, hash, nonce, content, and metadata.
14. The system deterministically serializes the payload.
15. The system signs the serialized bytes using Party A's Ed25519 private key.
16. If enabled, the system encrypts and authenticates the signed package using AES-256-GCM.
17. The system creates the bootstrap and variable-location frame.
18. The selected carrier adapter embeds the two structures using LSB replacement.
19. The system saves a new PNG or WAV file without overwriting the original by default.
20. The GUI displays or plays both original and stego objects and shows capacity, cryptographic, start-mode, and quality summaries.
21. Party A transfers the stego object to Party B through the demonstrated channel.

Protection succeeds only after the saved output has been reopened and a local verification self-check has passed. A self-check does not replace the separate Party B demonstration.

## 14. Required verification workflow

1. Party B downloads or copies the stego object into a receiver-controlled folder.
2. Party B selects the received file in the verification interface.
3. The system validates its media format.
4. The system reads the reserved bootstrap positions.
5. If no supported bootstrap marker exists, the system reports `Payload Missing` unless corruption makes the result ambiguous.
6. Party B supplies a manual location or extraction passphrase according to the bootstrap mode.
7. The system validates or authenticates the bootstrap and derives the correct variable position sequence.
8. The system extracts only the bounded number of bytes declared by the validated configuration.
9. The system validates the frame magic, version, flags, and internal lengths.
10. If encryption is enabled, the system authenticates and decrypts using AES-256-GCM.
11. The system parses the signed package and logical payload.
12. Party B loads Party A's independently trusted Ed25519 public key.
13. The system checks that its fingerprint matches the signed-package reference where applicable.
14. The system verifies the Ed25519 signature over the exact serialized payload bytes.
15. The system recreates the stable media representation using the validated embedded positions.
16. The system recomputes SHA-256 and compares it with the signed hash.
17. The central verdict engine evaluates the ordered results.
18. The GUI shows the final verdict, explanation, extracted metadata, signature status, and hash comparison.
19. Party B may save a secret-safe verification report.
20. Steganalysis may be run separately; it does not replace or override cryptographic verification.

## 15. Verdict model

### 15.1 Required output structure

```text
final_verdict
summary
media_validation_status
bootstrap_status
location_status
frame_status
decryption_status
signature_status
stable_hash_status
public_key_fingerprint
extracted_metadata
diagnostic_details
```

### 15.2 Decision rules and precedence

| Highest applicable condition | Verdict | Explanation |
|---|---|---|
| Unsupported, malformed, truncated, unsafe, or internally inconsistent input prevents reliable processing | `Cannot Verify` | Verification could not be completed safely. |
| No supported bootstrap or payload marker is present in an otherwise valid carrier | `Payload Missing` | No P3-6 payload was detected under the supported format. |
| Authenticated configuration is valid but the package is not recoverable at the derived or supplied position | `Wrong Start Location` | The configured location does not contain the expected frame; corruption remains a possible cause. |
| Encrypted frame authentication fails | `Cannot Verify` | The secret may be wrong or ciphertext may be damaged; the application cannot safely distinguish them. |
| Payload parses but Ed25519 verification fails, or the trusted key fingerprint is wrong | `Signature Invalid` | The signed payload is altered or the supplied public key is not the expected key. |
| Signature is valid but the stable-media hash differs | `Tampered` | The legitimate signed record does not match the current protected media representation. |
| Required stages succeed, signature is valid, and the stable-media hash matches | `Authentic` | The received media and signed verification record pass the implemented checks. |

`Authentic` means authentic relative to the trusted public key and implemented stable representation. It does not prove who physically controlled the key or whether excluded embedding bits were untouched.

## 16. GUI specification

### 16.1 Protect view

The Protect view shall contain:

- Media selector and validated file properties.
- Image preview or WAV playback.
- Text/file payload selector.
- Short, large, and custom payload choices.
- Media ID and metadata fields.
- Lowest-N-bit selector from 1–8 and an advanced bit-position option if implemented.
- Manual/automatic start-location selector.
- Passphrase control for automatic location and encryption modes.
- Plaintext-signed/encrypted-signed selector.
- Signing-private-key selector.
- Live capacity summary and distortion warning.
- Protect, cancel, and save controls.
- Original-versus-stego preview/playback.
- Safe operation details and self-check status.

### 16.2 Verify view

The Verify view shall contain:

- Received-media selector.
- Image preview or audio playback.
- Start mode/settings recovered from the bootstrap when safe.
- Manual position or passphrase input when required.
- Trusted-public-key selector and fingerprint.
- Extract and Verify action.
- Stage-by-stage status display.
- Prominent final verdict with text and icon, not colour alone.
- Extracted metadata and payload display/save control.
- Verification report export.

### 16.3 Steganalysis view

The Steganalysis view shall contain:

- Suspicious PNG selector.
- Optional original-cover selector for comparison evidence.
- Analysis controls and progress.
- Chi-square result and explanation.
- RS result and explanation.
- Combined indication category.
- LSB-plane or supporting plots where useful.
- Explicit warning that statistical indications are not proof.
- Exportable result.

### 16.4 Keys and settings view

The application should provide:

- Generate assignment-only Ed25519 keys.
- Import supported private and public keys.
- Show public-key fingerprint.
- Select raw encryption key or passphrase mode if both are implemented.
- Reveal passphrase only after an explicit user action.
- Prevent private-key values from appearing in ordinary UI logs.

### 16.5 Accessibility and feedback

- Verdicts shall use labels and icons in addition to colour.
- Keyboard focus order shall follow the workflow.
- Long operations shall show progress or busy state.
- Validation shall identify the affected field.
- Technical details shall be expandable so beginners see a clear summary while evaluators can inspect evidence.

## 17. Steganalysis design

### 17.1 Method 1: chi-square pairs-of-values

Conventional LSB replacement tends to redistribute frequencies within value pairs that differ only in their least-significant bit, such as `(0,1)`, `(2,3)`, and `(254,255)`. The analyser shall:

1. Extract eligible RGB channel values from the image.
2. Build observed frequencies for even/odd value pairs.
3. Calculate expected paired frequencies under the LSB-replacement hypothesis.
4. Compute a chi-square statistic and a documented probability or normalised indication score.
5. Optionally repeat the calculation over windows to show where the signal changes.
6. Present the statistic, configuration, and cautious interpretation.

The implementation shall document its null hypothesis and score direction carefully. A threshold shall be calibrated using the team's clean and stego evaluation set rather than copied without testing.

### 17.2 Method 2: RS analysis

RS analysis partitions neighbouring carrier values into groups, applies a discrimination function, flips selected LSBs using regular and inverse masks, and counts regular, singular, and unusable groups. LSB replacement changes the relationships between these counts. The analyser shall:

1. Form deterministic groups of eligible image values.
2. Define and test a discrimination function, such as the sum of absolute neighbouring differences.
3. Apply positive and negative LSB-flipping masks without modifying the source file.
4. Count regular, singular, and unusable groups for the required masks.
5. Calculate the documented RS indicators or embedding-rate estimate.
6. Report raw counts and the interpretation used by the combined classifier.

Test vectors and independent calculations are required because errors in inverse flipping, grouping, or equation implementation can produce convincing but incorrect output.

### 17.3 Combined interpretation

The two methods remain independently visible. A simple calibrated combination may classify results as:

- **Low indication:** neither method crosses its calibrated threshold.
- **Inconclusive:** one method crosses its threshold or results conflict.
- **High indication:** both methods cross their calibrated thresholds.

The report shall state that:

- Statistical detection does not recover or authenticate the payload.
- Natural image processing can trigger false positives.
- Small payloads may escape detection.
- Pseudorandom or adaptive embedding may reduce the signal.
- Results depend on the image source and calibration dataset.
- An original-versus-stego difference is useful evidence but is not blind steganalysis.

## 18. Testing requirements

### 18.1 Test levels

- Unit tests for serialization, bit packing, capacity, position generation, hashing, crypto, verdict logic, and steganalysis calculations.
- Adapter tests for PNG and WAV load/save invariants.
- Integration tests for protect-save-reopen-extract-verify.
- GUI workflow tests or recorded manual checks.
- Negative and malformed-input tests.
- Cross-folder sender/receiver tests.
- Steganalysis evaluation across clean and embedded samples.

### 18.2 Mandatory demonstration cases

| ID | Cover | Case | Expected outcome |
|---|---|---|---|
| `DEMO-POS-IMG` | PNG | Protect, transfer, extract, verify with correct settings and key | `Authentic` |
| `DEMO-POS-AUD` | WAV | Protect, transfer, extract, verify with correct settings and key | `Authentic` |
| `DEMO-NEG-IMG` | PNG | Modify protected pixel data outside reserved payload positions | `Tampered` |
| `DEMO-NEG-AUD` | WAV | Modify protected PCM data outside reserved payload positions | `Tampered` |
| `DEMO-NEG-KEY` | Either | Verify intact signed payload using a different public key | `Signature Invalid` |
| `DEMO-NEG-LOC` | Either | Supply an incorrect manual location or automatic-mode secret | `Wrong Start Location` or `Cannot Verify`, according to observable evidence |
| `DEMO-NEG-MISSING` | Either | Verify a supported but unprotected file | `Payload Missing` |
| `DEMO-CAPACITY` | Both | Attempt to embed a package larger than capacity | Operation blocked before modification |

At least two positive and three negative cases shall be included in the final demo, with at least one positive and one negative case for both image and audio.

### 18.3 Required payload variants

- Short message: one assignment Learning Outcome.
- Large message: the assignment Project Overview paragraph.
- Custom message/file: a relevant team-defined payload protected with confidentiality and integrity.
- Unknown payload rehearsal: an unprepared text or file chosen immediately before a practice run.

### 18.4 LSB and boundary coverage

- Round trip with settings 1 through 8.
- Exact-fit payload.
- One byte over capacity.
- Minimum valid carrier.
- Start at the earliest valid automatic/manual position.
- Start at the latest valid position for the package.
- Empty optional metadata.
- Maximum allowed metadata and file-name lengths.

### 18.5 Cryptographic negative coverage

- Wrong public key.
- Modified signed field.
- Modified signature byte.
- Wrong encryption key/passphrase.
- Modified AES-GCM ciphertext or tag.
- Corrupted or replayed bootstrap.
- Valid signed payload substituted into a different media object.

### 18.6 Steganalysis evaluation

The evaluation set should contain natural team-created or appropriately licensed images rather than only synthetic noise. For each image, record:

- Clean analysis results.
- Short, medium, and near-capacity embeddings.
- At least 1-LSB and 2-LSB configurations.
- Chi-square statistic and interpreted score.
- RS counts and interpreted score.
- Combined result.
- Expected class and actual class.

The final evidence shall include at least one limitation or misclassification if one occurs. Thresholds and samples shall not be selected only to make the technique appear perfect.

## 19. Security analysis and limitations

### 19.1 Threats addressed

| Threat | Primary control |
|---|---|
| Payload alteration | Ed25519 signature; AES-GCM authentication when encrypted |
| Media alteration outside reserved positions | Signed SHA-256 stable-media hash |
| Wrong or substituted signer key | Independently trusted public key and fingerprint display |
| Casual payload discovery | LSB concealment and keyed start derivation |
| Start-location guessing | Passphrase-derived keyed pseudorandom function |
| Oversized or malicious length | Capacity checks and bounded parsing |
| Confidential payload disclosure | AES-256-GCM encrypted mode |

### 19.2 Known limitations

- Steganography conceals data but does not guarantee secrecy; encryption is needed for confidential content.
- LSB payloads are fragile under JPEG/MP3 conversion, image resizing, filtering, audio resampling, or other transformations.
- The stable hash deliberately normalises embedded positions, so those exact bits depend on frame authentication and signatures for protection.
- If an attacker obtains the signing private key, they can produce payloads that verify under that key.
- If the verifier accepts a public key supplied by an attacker, signature validation does not establish the expected sender.
- Weak passphrases can be guessed offline when sufficient validation information is available.
- A discoverable bootstrap reveals that the P3-6 format may be present even if the variable payload remains difficult to locate.
- Using upper bit positions or many bits creates visible/audible distortion and makes detection easier.
- Sequential embedding is easier to detect than adaptive or distributed methods.
- Steganalysis produces statistical evidence, not proof.
- A verdict does not establish legal authorship, chain of custody, or the truth of the embedded metadata.

### 19.3 Ethical use and AI reflection

The application is intended for educational integrity verification. It should not be represented as a production forensic tool or used to conceal harmful content. Sources and external algorithms shall be acknowledged. AI-assisted code and documentation shall be reviewed, tested, understood, and disclosed according to the assignment rules. Each member remains responsible for explaining their own technical contribution.

The assignment specifically requires an email to the lecturer with subject `ACW1 used in genAI query` and device/source details in the body. The team shall complete and retain evidence of this administrative action.

## 20. Assignment traceability

### 20.1 Mandatory scope and functional requirements

| Assignment requirement | Specification coverage | Planned evidence |
|---|---|---|
| FR1 Image input | `MED-FR-001`–`MED-FR-002`, Section 8.8 | PNG positive and rejection tests |
| FR2 Audio input | `MED-FR-003`–`MED-FR-004`, Section 8.9 | WAV positive and rejection tests |
| FR3 Payload generation | `PAY-FR-001`–`PAY-FR-005`, Section 12 | Extracted payload and metadata report |
| FR4 Digital signature | `SIG-FR-001`–`SIG-FR-008` | Valid and wrong-key demonstrations |
| FR5 Image embedding | `IMG-FR-001`–`IMG-FR-007` | Original/stego PNG and round trip |
| FR6 Audio embedding | `AUD-FR-001`–`AUD-FR-007` | Original/stego WAV and round trip |
| FR7 Variable start | `LOC-FR-001`–`LOC-FR-009` | Manual and derived-location demonstrations |
| FR8 Extraction and decoding | `VER-FR-001`–`VER-FR-002`, Section 14 | Party B extraction |
| FR9 Hash verification | `HSH-FR-001`–`HSH-FR-006` | Matching and mismatching hashes |
| FR10 Verdict generation | `VER-FR-003`–`VER-FR-008`, Section 15 | Verdict matrix evidence |
| FR11 Positive/negative cases | Section 18.2 | At least two positive and three negative cases |
| FR12 Evidence/reproducibility | `REP-FR-001`–`REP-FR-007` | README, samples, tests, screenshots, reports |
| FR13 Innovation | Section 17 | Two-method steganalysis and evaluation |
| Capacity check | `CAP-FR-001`–`CAP-FR-004` | Oversized payload rejection for PNG and WAV |
| Payload sizes | `PAY-FR-004`, Section 18.3 | Short, large, and confidential custom cases |
| Selectable bits 1–8 | `CAP-FR-005`–`CAP-FR-007` | Round-trip parameterised tests and GUI evidence |
| Display/play cover and stego | `MED-FR-007`–`MED-FR-008` | Protect-view demo |
| Party A-to-Party B transfer | Sections 13–14 | Transfer/download recording or screenshots |
| Originality and contribution | `REP-FR-006`–`REP-FR-007` | Signed forms and AI disclosure |

### 20.2 Rubric alignment

| Rubric criterion | What the implementation must demonstrate | Primary specification sections |
|---|---|---|
| Security design and problem framing, 5 marks | Coherent payload, start-location security, recovery explanation, and authenticity model for both carriers | Sections 6, 8.2–8.7, 10–15, 19 |
| Image embedding/extraction/cases, 9 marks | Working PNG encode/decode, variable location, positive verification, and tamper detection | Sections 8.8, 13–15, 18 |
| Audio embedding/extraction/cases, 10 marks | Working WAV encode/decode, variable location, positive verification, and tamper detection | Sections 8.9, 13–15, 18 |
| Hashing/signatures/failure handling, 5 marks | Correct hashing and signing, public-key verification, altered payload/key failure, and clear verdict linkage | Sections 8.5–8.7, 14–15, 18.5 |
| Innovation, 4 marks | Implemented, evaluated, useful steganalysis with remaining limitations explained | Sections 8.11, 17, 18.6, 19 |
| Individual technical explanation, 5 marks | Each member owns, tests, documents, and demonstrates a technical area | Implementation plan and demo plan |
| Limitations, ethics, and AI reflection, 2 marks | Honest limitations, responsible-use statement, acknowledged sources, and verified AI use | Section 19 |

## 21. System acceptance criteria

The system is ready for submission only when:

1. All mandatory requirements are implemented or explicitly recorded as unresolved with lecturer approval.
2. Both carrier types complete a protect-save-reopen-extract-verify round trip.
3. At least one positive and one negative test pass for each carrier.
4. Total demonstrated cases include at least two positive and three negative cases.
5. Capacity rejection and all required payload-size variants are evidenced.
6. `Authentic` requires both a valid signature and matching stable-media hash.
7. Manual and automatic start-location workflows are tested and explainable.
8. GUI image display and WAV playback work on the demonstration laptop.
9. Chi-square and RS methods run on the evaluation set and produce documented results.
10. Automated tests pass from a clean checkout using documented commands.
11. The README, sample files, reports, screenshots, public key/instructions, originality form, contribution statement, and demo plan are complete.
12. Every member can explain their implementation, tests, security assumptions, and limitations without relying on generated text they do not understand.

## 22. Change control

Changes to cryptographic algorithms, frame layout, stable-hash rules, carrier ordering, or position derivation can make existing stego files incompatible. Such changes shall:

1. Be recorded in this document.
2. Increment the relevant format or algorithm version where necessary.
3. Add or update test vectors.
4. Identify migration or incompatibility effects.
5. Be reflected in `ACW1_IMPLEMENTATION_PLAN.md` and the README.

Lecturer answers shall replace provisional decisions in Section 6 without silently changing already implemented assumptions.
