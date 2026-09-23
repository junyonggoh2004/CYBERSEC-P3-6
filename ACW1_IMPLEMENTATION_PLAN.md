# INF2005 ACW1 Implementation Plan

## Steganographic Image and Audio Integrity Verification

| Document field | Value |
|---|---|
| Team | P3-6 |
| Members | Jun Yong, Gabriel, Jian Xuan, Matthias, Kim, Gerome |
| Related specification | `ACW1_SYSTEM_SPECIFICATION.md` |
| Target submission | 30 September 2026 |
| Target demonstration | 1 October 2026 |
| Initial plan date | 15 September 2026 |
| Plan status | Ready to begin |

## 1. Purpose

This plan turns the system specification into ordered, owned, and testable work. It records what must be built first, what can wait, who leads each area, how work is reviewed, and what evidence proves completion.

The plan is expected to change as the team learns. The system specification should change only when requirements or important design decisions change.

## 2. Delivery strategy

The team will work in three levels of priority:

1. **Mandatory core:** reliable PNG and WAV protection, extraction, hashing, signatures, variable starts, verdicts, GUI comparison/playback, and required cases.
2. **Selected innovation:** correct and evaluated chi-square and RS steganalysis.
3. **Enhancements:** encryption, pseudorandom distributed positions, richer visualisations, packaging polish, and additional formats only after the first two levels are safe.

The central rule is that a feature is not complete when it first appears to work. It is complete after it has a repeatable test, documented behaviour, handled failure cases, and a team member other than its author has reviewed it.

AI-assisted development may shorten initial coding time, but the schedule retains time for integration, review, testing, and rehearsal. Generated code is not accepted solely because it runs once.

## 3. Initial project status

At plan creation:

- The repository contains only a minimal `README.md`.
- No implementation is assumed to exist.
- No existing deleted task-plan content will be recovered or reused.
- No sample image or audio files have been selected.
- Lecturer answers listed in the system specification remain pending.
- All tasks begin as `Not started` unless updated by the team.

Allowed task statuses are:

```text
Not started -> In progress -> In review -> Verified -> Done
                       \-> Blocked
```

`Done` requires acceptance criteria and evidence, not only code completion.

## 4. Proposed technology stack

| Area | Initial choice | Reason |
|---|---|---|
| Language | Python 3.12 or team-agreed supported Python 3 version | Good library support and rapid testing |
| GUI | Flask backend + vanilla HTML/CSS/JS | Single-page, drag-and-drop browser interface served by the Flask app |
| Images | Pillow | Reliable decoded PNG pixel access |
| Numeric processing | NumPy | Efficient carrier and steganalysis calculations |
| Cryptography | `cryptography` | Established RSA, hashing, and PEM support |
| Audio format | Standard `wave` module plus NumPy | PCM WAV access without lossy conversion |
| Audio playback | Native HTML5 `<audio>` element | Fits the browser-based GUI stack, no extra dependency |
| Statistics | SciPy if needed; otherwise reviewed local formulas | Chi-square probability calculations and evaluation |
| Tests | pytest, pytest-cov | Parameterised and integration testing |
| Formatting/linting | Ruff | Fast consistent checks |
| Packaging | `requirements.txt`, virtual environment | Reproducible `pip install` + `python backend/app.py` setup |

Versions shall be pinned before the first release candidate. A dependency shall not be added when the standard library or an existing dependency safely covers the requirement.

## 5. Planned repository structure

```text
CYBERSEC-P3-6/
├── README.md
├── ACW1_SYSTEM_SPECIFICATION.md
├── ACW1_IMPLEMENTATION_PLAN.md
├── pyproject.toml
├── src/
│   └── stegverify/
│       ├── __init__.py
│       ├── app.py
│       ├── models/
│       │   ├── payload.py
│       │   ├── results.py
│       │   └── settings.py
│       ├── core/
│       │   ├── bitstream.py
│       │   ├── capacity.py
│       │   ├── framing.py
│       │   ├── positions.py
│       │   └── verdicts.py
│       ├── carriers/
│       │   ├── base.py
│       │   ├── png.py
│       │   └── wav.py
│       ├── security/
│       │   ├── hashing.py
│       │   ├── signatures.py
│       │   ├── encryption.py
│       │   └── keys.py
│       ├── analysis/
│       │   ├── chi_square.py
│       │   ├── rs_analysis.py
│       │   └── combined.py
│       └── services/
│           ├── protect.py
│           ├── verify.py
│           ├── analyse.py
│           └── reports.py
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── analysis.js
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── steganalysis/
│   └── fixtures/
├── samples/
│   ├── originals/
│   ├── protected/
│   ├── tampered/
│   └── payloads/
├── evidence/
│   ├── reports/
│   ├── screenshots/
│   └── test-results/
├── keys/
│   ├── public/
│   └── DEMO_KEYS_README.md
└── docs/
    ├── TEST_AND_EVIDENCE_PLAN.md
    ├── DEMO_PLAN.md
    ├── CONTRIBUTIONS.md
    └── decisions/
```

Private keys shall be ignored by version control unless the team intentionally includes a clearly labelled assignment-only key after confirming that this is permitted.

## 6. Team ownership model

No preferences were provided, so this allocation balances the major assessed areas. It is provisional and may be rebalanced by agreement.

| Member | Primary ownership | Secondary review responsibility | Demo emphasis |
|---|---|---|---|
| Jun Yong | Architecture, payload/framing, stable hashing, integration coordination | GUI/verdict integration | Security design and end-to-end architecture |
| Gabriel | PNG carrier, image capacity, image comparison metrics | WAV carrier review | Image encode/decode and image cases |
| Jian Xuan | WAV carrier, audio capacity, playback integration support | PNG carrier review | Audio encode/decode and audio cases |
| Matthias | Flask/web shell, Protect/Verify workflow integration, accessibility | Payload and reports review | GUI workflow and Party A-to-B handoff |
| Kim | Chi-square, RS analysis, evaluation dataset and interpretation | Cryptographic test review | Innovation and limitations |
| Gerome | Verdict engine, automated integration tests, evidence/release coordination | Steganalysis result review | Negative cases, reproducibility, ethics |

### 6.1 Shared obligations

Every member shall:

- Implement or materially review code in their assigned area.
- Write or review tests for that area.
- Update relevant documentation.
- Produce evidence for at least one test or demonstration step.
- Review at least one other member's work.
- Understand the end-to-end security workflow.
- Prepare an individual technical explanation and answer likely questions.
- Record AI assistance and personally validate generated work.

### 6.2 Ownership rules

- The primary owner drives design and delivery but does not work alone.
- The secondary reviewer checks correctness and comprehension before `Done`.
- Cross-module interface changes require notification to affected owners.
- Cryptographic, framing, and stable-hash changes require two-person review.
- No member should be assigned only slides, forms, or administrative work.

## 7. Milestones and schedule

Dates are targets, not permission to leave integration until the end.

| Milestone | Target | Exit condition |
|---|---|---|
| M0 — Foundation frozen | 16 Sep | Environment, architecture, frame proposal, interfaces, and baseline test command exist |
| M1 — Carrier round trips | 19 Sep | PNG and WAV can embed/extract framed test bytes at multiple LSB settings |
| M2 — Mandatory security core | 22 Sep | Stable hash, Ed25519, start modes, protection, verification, and verdicts work without GUI |
| M3 — Mandatory GUI complete | 24 Sep | Both carriers work end to end through GUI, including display/playback and capacity rejection |
| M4 — Steganalysis implemented | 26 Sep | Chi-square and RS run with reviewed test vectors and initial evaluation |
| M5 — Feature freeze | 27 Sep | Mandatory scope and innovation pass integration tests; only fixes/documentation after this point |
| M6 — Evidence/release candidate | 28 Sep | Samples, test reports, screenshots, README, key instructions, and Windows clean-run complete |
| M7 — Demo-ready | 29 Sep | Full timed rehearsal succeeds with backup files and every member's segment |
| M8 — Submission | 30 Sep | Required package and one-day-before demo documents uploaded and verified |
| M9 — Demonstration | 1 Oct | Team completes ≤25-minute demonstration and answers questions |

### 7.1 Suggested daily focus

| Date | Main work |
|---|---|
| 15 Sep | Repository setup, specification review, interfaces, payload/frame design, sample strategy |
| 16 Sep | Bitstream, capacity, result models, keys/signature spike, GUI wireframe |
| 17–19 Sep | PNG and WAV adapters in parallel; unit and round-trip tests |
| 20–22 Sep | Stable hash, location derivation, signatures, verdicts, headless end-to-end integration |
| 23–24 Sep | Full GUI integration, image comparison, audio playback, sender/receiver workflow |
| 25–26 Sep | Chi-square, RS, dataset evaluation, fixes to mandatory workflows |
| 27 Sep | Negative/malformed tests, feature freeze, complete security review |
| 28 Sep | Windows clean setup, packaging, screenshots, reports, sample finalisation |
| 29 Sep | README, forms, timed demo rehearsal, individual questions, backup plan |
| 30 Sep | Final verification and submission; no unreviewed feature additions |
| 1 Oct | Demonstration |

## 8. Dependency map

```text
SETUP
  ├── DATA MODELS
  │     ├── FRAMING ──┬── PNG ADAPTER ──┐
  │     │             └── WAV ADAPTER ──┤
  │     ├── CAPACITY ────────────────────┤
  │     ├── POSITIONS ───────────────────┤
  │     └── CRYPTO + STABLE HASH ────────┤
  │                                      v
  └────────────────────────────── PROTECT/VERIFY
                                         │
                        ┌────────────────┼───────────────┐
                        v                v               v
                       GUI          VERDICT/REPORT   INTEGRATION TESTS
                                                          │
                                                          v
                                              EVIDENCE + DEMO + RELEASE

PNG ADAPTER ──> CHI-SQUARE + RS ──> STEGANALYSIS EVALUATION
```

The GUI may be prototyped early using fake service responses, but it cannot be declared complete until it calls the verified application services.

## 9. Ordered task backlog

### Phase A — Foundation and design

#### `SETUP-001` — Create Python project structure

- Owner: Jun Yong
- Reviewer: Matthias
- Priority: Critical
- Depends on: None
- Status: Not started
- Related requirements: `NFR-MNT-001`–`NFR-MNT-003`, `REP-FR-001`

Work:

- Create the planned source and test layout.
- Add `pyproject.toml`, runtime dependencies, development dependencies, and commands.
- Configure Ruff and pytest.
- Add `.gitignore` entries for virtual environments, caches, generated evidence, and real private keys as appropriate.
- Provide an application entry point that can start a bare Flask server and serve an empty page.

Acceptance:

- A new Windows checkout can create an environment and install the project.
- `pytest` and the lint command run successfully.
- The application entry point starts without import errors.

#### `DES-001` — Freeze carrier interfaces and shared result models

- Owner: Jun Yong
- Reviewer: Gabriel and Jian Xuan
- Priority: Critical
- Depends on: `SETUP-001`
- Status: Not started
- Related requirements: Section 10 of the specification

Work:

- Define carrier metadata, bit-selection, position-plan, protection-result, verification-result, and stage-status models.
- Define adapter methods shared by PNG and WAV.
- Ensure the models do not import GUI classes.

Acceptance:

- Both carrier owners approve the interface.
- Result models can represent every required verdict and supporting stage.
- Unit tests cover validation of invalid settings.

#### `PAY-001` — Define payload schema and deterministic serialization

- Owner: Jun Yong
- Reviewer: Matthias
- Priority: Critical
- Depends on: `SETUP-001`
- Status: Not started
- Related requirements: `PAY-FR-001`–`PAY-FR-005`

Work:

- Decide canonical JSON or CBOR.
- Represent text and arbitrary file payloads.
- Bound field and content sizes.
- Create known serialized test vectors.

Acceptance:

- Equivalent logical data always produces identical signed bytes.
- Round-trip serialization preserves every supported field.
- Unsupported versions, types, and oversized fields are rejected.

#### `PAY-002` — Freeze bootstrap and variable-frame version 1

- Owner: Jun Yong
- Reviewer: Gerome
- Priority: Critical
- Depends on: `PAY-001`, `DES-001`
- Status: Not started
- Related requirements: `PAY-FR-006`–`PAY-FR-008`, `LOC-FR-004`–`LOC-FR-006`

Work:

- Specify exact field offsets, byte order, lengths, flags, magic values, and authentication rules.
- Define how bootstrap positions are reserved for PNG and WAV.
- Define the two-pass size calculation.
- Add version-1 encode/decode test vectors.

Acceptance:

- A table documents every byte field.
- Frame decoding rejects bad magic, unknown versions, impossible lengths, and unsupported flags.
- Existing version-1 test vectors will reveal accidental incompatible changes.

#### `CORE-001` — Implement generic bitstream packing

- Owner: Gabriel
- Reviewer: Jian Xuan
- Priority: Critical
- Depends on: `SETUP-001`
- Status: Not started
- Related requirements: `CAP-FR-005`–`CAP-FR-006`

Work:

- Implement bytes-to-bits and bits-to-bytes functions.
- Implement deterministic mapping across selected bit positions.
- Make bit ordering explicit.

Acceptance:

- Parameterised tests cover empty input, arbitrary bytes, non-byte-aligned reads, and settings 1–8.
- Known vectors verify ordering independently of a carrier.

#### `CORE-002` — Implement exact capacity calculator

- Owner: Jian Xuan
- Reviewer: Gabriel
- Priority: Critical
- Depends on: `DES-001`, `CORE-001`
- Status: Not started
- Related requirements: `CAP-FR-001`–`CAP-FR-007`

Work:

- Calculate actual usable positions after bootstrap, start, and exclusions.
- Include frame, signature, and encryption overhead.
- Return human-readable capacity details.

Acceptance:

- Exact-fit packages are accepted.
- Packages one byte over capacity are rejected.
- Tests cover both sequential and planned pseudorandom position representations.

### Phase B — Security primitives and positions

#### `SIG-001` — Implement Ed25519 key handling and signatures

- Owner: Jun Yong
- Reviewer: Kim
- Priority: Critical
- Depends on: `PAY-001`
- Status: Not started
- Related requirements: `SIG-FR-001`–`SIG-FR-008`

Work:

- Generate demo key pairs.
- Import/export supported PEM forms.
- Sign exact serialized payload bytes.
- Verify and expose public-key fingerprints without exposing secrets.

Acceptance:

- Correct key and message verify.
- Wrong public key, modified message, and modified signature fail.
- Private keys never appear in normal logs or reports.

#### `KEY-001` — Implement password KDF and purpose-separated keys

- Owner: Jun Yong
- Reviewer: Kim
- Priority: Critical
- Depends on: `SETUP-001`
- Status: Not started
- Related requirements: `LOC-FR-003`, `LOC-FR-006`, `ENC-FR-002`, `ENC-FR-004`

Work:

- Select and parameterise a standard password KDF supported by the cryptographic library.
- Derive independent location, bootstrap-authentication, and encryption keys using documented context labels.
- Encode the KDF identifier, parameters, and random salt needed for reproduction.

Acceptance:

- The same passphrase, salt, parameters, and label derive the same key.
- Different purpose labels produce different keys.
- Invalid or excessive parameters are rejected safely.
- Test vectors lock the version-1 behaviour.

#### `ENC-001` — Implement AES-256-GCM and purpose-separated keys

- Owner: Jun Yong
- Reviewer: Kim
- Priority: High after signature baseline
- Depends on: `SIG-001`, `PAY-002`, `KEY-001`
- Status: Not started
- Related requirements: `ENC-FR-001`–`ENC-FR-006`

Work:

- Support AES-256-GCM encryption/decryption.
- Add passphrase KDF and/or raw-key input.
- Use labels to separate encryption, bootstrap authentication, and location keys.
- Define associated authenticated data for immutable bootstrap fields.

Acceptance:

- Correct secret round trips.
- Wrong secret and one-bit ciphertext/tag changes fail closed.
- Repeated encryptions use different nonces.
- No unauthenticated plaintext is parsed.

#### `LOC-001` — Implement manual start validation

- Owner: Gabriel
- Reviewer: Gerome
- Priority: Critical
- Depends on: `CORE-002`
- Status: Not started
- Related requirements: `LOC-FR-001`, `LOC-FR-007`, `LOC-FR-009`

Acceptance:

- Valid starts produce non-overlapping position plans.
- Negative and too-late starts are rejected before embedding.
- Boundary tests cover first and last valid starts.

#### `LOC-002` — Implement passphrase-derived automatic start

- Owner: Jun Yong
- Reviewer: Gerome
- Priority: Critical
- Depends on: `KEY-001`, `CORE-002`
- Status: Not started
- Related requirements: `LOC-FR-002`–`LOC-FR-009`

Work:

- Generate and encode salt.
- Derive a purpose-specific location key.
- Generate a deterministic valid start from stable public properties.
- Authenticate recoverable configuration.

Acceptance:

- Same media properties, salt, passphrase, and version reproduce the same start.
- Different salts or passphrases produce different outputs in tests.
- Invalid bootstrap authentication fails safely.
- The start value is not stored directly in automatic mode.

#### `HSH-001` — Implement stable-media hashing interface

- Owner: Jun Yong
- Reviewer: Gabriel and Jian Xuan
- Priority: Critical
- Depends on: `DES-001`, `PAY-002`, carrier position interfaces
- Status: Not started
- Related requirements: `HSH-FR-001`–`HSH-FR-006`

Work:

- Define how exact bootstrap and package bit positions are normalised.
- Include relevant stable media properties.
- Implement SHA-256 over streamed/canonical bytes.
- Create tests proving valid embedding does not change the stable hash.

Acceptance:

- Pre-embedding and post-embedding stable hashes match for valid outputs.
- A change outside normalised positions causes a mismatch.
- Hash rules are documented separately for PNG and WAV.

### Phase C — PNG carrier

#### `IMG-001` — Implement PNG validation and carrier enumeration

- Owner: Gabriel
- Reviewer: Jian Xuan
- Priority: Critical
- Depends on: `DES-001`
- Status: Not started
- Related requirements: `MED-FR-001`–`MED-FR-002`, `IMG-FR-001`–`IMG-FR-002`

Acceptance:

- RGB and RGBA PNGs load.
- Unsupported/corrupt inputs are rejected clearly.
- RGB positions have deterministic ordering.
- RGBA alpha values are excluded.

#### `IMG-002` — Implement PNG LSB embedding and extraction

- Owner: Gabriel
- Reviewer: Jian Xuan
- Priority: Critical
- Depends on: `IMG-001`, `CORE-001`, `CORE-002`, `LOC-001`
- Status: Not started
- Related requirements: `IMG-FR-003`–`IMG-FR-005`, assignment FR5 and FR8

Acceptance:

- Arbitrary framed bytes round trip after save and reopen.
- Tests cover lowest-N values 1–8.
- Selected bit positions only are changed.
- Image dimensions, RGB values outside selected positions, and alpha values are preserved as specified.
- Oversized packages are rejected before output.

#### `IMG-003` — Add PNG stable hash and comparison metrics

- Owner: Gabriel
- Reviewer: Jun Yong
- Priority: Critical for hash; medium for metrics
- Depends on: `IMG-002`, `HSH-001`
- Status: Not started
- Related requirements: `HSH-FR-002`–`HSH-FR-005`, `IMG-FR-006`–`IMG-FR-007`

Acceptance:

- Stable hashes match before/after valid embedding.
- Non-reserved pixel change is detected.
- Changed-channel count, MSE, and PSNR are correct against small known arrays.

#### `IMG-004` — Build required PNG cases and evidence fixtures

- Owner: Gabriel
- Reviewer: Gerome
- Priority: Critical
- Depends on: `IMG-003`, integrated protection service
- Status: Not started

Acceptance:

- Authentic, tampered, wrong-key, missing-payload, and capacity cases are reproducible.
- Original, protected, and tampered samples have descriptive names.
- Expected outcomes are recorded in fixture metadata.

### Phase D — WAV carrier

#### `AUD-001` — Implement WAV validation and sample enumeration

- Owner: Jian Xuan
- Reviewer: Gabriel
- Priority: Critical
- Depends on: `DES-001`
- Status: Not started
- Related requirements: `MED-FR-003`–`MED-FR-004`, `AUD-FR-001`–`AUD-FR-004`

Acceptance:

- Supported 16-bit PCM mono and stereo WAVs load.
- Unsupported compression/sample widths and truncated files are rejected clearly.
- Signed little-endian sample conversion is verified with known values.
- Header bytes are never returned as eligible carrier data.

#### `AUD-002` — Implement WAV LSB embedding and extraction

- Owner: Jian Xuan
- Reviewer: Gabriel
- Priority: Critical
- Depends on: `AUD-001`, `CORE-001`, `CORE-002`, `LOC-001`
- Status: Not started
- Related requirements: `AUD-FR-001`–`AUD-FR-005`, assignment FR6 and FR8

Acceptance:

- Arbitrary framed bytes round trip after save and reopen.
- Tests cover settings 1–8 of the documented sample region.
- WAV format parameters are preserved.
- The saved output remains playable.
- Oversized packages are rejected before output.

#### `AUD-003` — Add WAV stable hash and comparison metrics

- Owner: Jian Xuan
- Reviewer: Jun Yong
- Priority: Critical for hash; medium for metrics
- Depends on: `AUD-002`, `HSH-001`
- Status: Not started
- Related requirements: `HSH-FR-002`–`HSH-FR-005`, `AUD-FR-006`–`AUD-FR-007`

Acceptance:

- Stable hashes match before/after valid embedding.
- Non-reserved sample modification is detected.
- Changed-sample count, MSE, and SNR match known-array calculations.

#### `AUD-004` — Build required WAV cases and evidence fixtures

- Owner: Jian Xuan
- Reviewer: Gerome
- Priority: Critical
- Depends on: `AUD-003`, integrated protection service
- Status: Not started

Acceptance:

- Authentic, tampered, wrong-start, missing-payload, and capacity cases are reproducible.
- Original, protected, and tampered samples have descriptive names.
- Expected outcomes are recorded in fixture metadata.

### Phase E — Application services and verdicts

#### `APP-001` — Implement headless protection service

- Owner: Jun Yong
- Reviewer: Matthias
- Priority: Critical
- Depends on: `PAY-002`, `SIG-001`, `LOC-001`, carrier embed functions, `HSH-001`
- Status: Not started
- Related requirements: Section 13 of the specification

Acceptance:

- One service request can protect either supported carrier.
- Capacity is checked before hashing/signing/output.
- The output is saved safely and then self-checked.
- Encrypted mode is additive; plaintext-signed mode remains available for debugging and required signature explanation.

#### `VER-001` — Implement central verdict engine

- Owner: Gerome
- Reviewer: Jun Yong
- Priority: Critical
- Depends on: `DES-001`
- Status: Not started
- Related requirements: `VER-FR-002`–`VER-FR-008`, Section 15

Work:

- Encode verdict precedence as pure, table-driven logic.
- Preserve stage details.
- Avoid claims that cannot be distinguished from available evidence.

Acceptance:

- Unit tests cover every verdict row and ambiguous combinations.
- `Authentic` is impossible without both valid signature and matching media hash.
- GUI-independent structured results are returned.

#### `APP-002` — Implement headless extraction and verification service

- Owner: Gerome
- Reviewer: Jun Yong
- Priority: Critical
- Depends on: `VER-001`, `SIG-001`, `LOC-002`, carrier extract functions, `HSH-001`
- Status: Not started
- Related requirements: Section 14 of the specification

Acceptance:

- PNG and WAV outputs from `APP-001` verify as `Authentic` after reopening.
- Wrong key, wrong start/secret, missing payload, corrupted frame, and changed media return controlled structured results.
- Untrusted lengths are bounded before reads/allocations.
- Verification never requires a signing private key.

#### `REP-001` — Implement safe report export

- Owner: Gerome
- Reviewer: Matthias
- Priority: High
- Depends on: `APP-002`
- Status: Not started
- Related requirements: `VER-FR-008`, `REP-FR-004`

Acceptance:

- JSON or text report includes verdict, stage results, hashes, algorithms, metadata, and public-key fingerprint.
- Passphrases, raw secret keys, private keys, and confidential plaintext are absent by default.
- Report schema has a version.

### Phase F — GUI

#### `GUI-001` — Build navigable Flask + browser application shell

- Owner: Matthias
- Reviewer: Jun Yong
- Priority: Critical
- Depends on: `SETUP-001`, `DES-001`
- Status: Not started

Acceptance:

- Protect, Verify, Steganalysis, and Keys/Settings sections are reachable on the single page.
- Status area, error presentation, and drag-and-drop file zones behave consistently.
- Keyboard navigation follows a sensible order.

#### `GUI-002` — Implement Protect view

- Owner: Matthias
- Reviewer: Gabriel and Jian Xuan
- Priority: Critical
- Depends on: `GUI-001`, `APP-001`
- Status: Not started
- Related requirements: Section 16.1

Acceptance:

- User can select PNG/WAV, payload, bit settings, start mode, keys, and encryption mode.
- Capacity updates before protection.
- Invalid combinations prevent execution with a readable reason.
- Original and protected image previews work.
- Original and protected WAV playback works through integrated controls.
- Output selection does not silently overwrite input.

#### `GUI-003` — Implement Verify view

- Owner: Matthias
- Reviewer: Gerome
- Priority: Critical
- Depends on: `GUI-001`, `APP-002`, `REP-001`
- Status: Not started
- Related requirements: Section 16.2

Acceptance:

- User can load received media, required secret/settings, and trusted public key.
- All verification stages and the final verdict are visible.
- Verdict meaning does not depend on colour alone.
- Extracted metadata and safe report export work.

#### `GUI-004` — Implement key/settings view

- Owner: Matthias
- Reviewer: Jun Yong
- Priority: High
- Depends on: `SIG-001`, `ENC-001`, `GUI-001`
- Status: Not started

Acceptance:

- Demo Ed25519 keys can be generated and supported keys imported.
- Public-key fingerprint is displayed.
- Secret fields are masked and never copied into logs.

#### `GUI-005` — Add workers, progress, and cancellation safety

- Owner: Matthias
- Reviewer: Gerome
- Priority: High
- Depends on: `GUI-002`, `GUI-003`
- Status: Not started

Acceptance:

- Material file and analysis operations do not freeze the GUI.
- The user cannot start conflicting operations.
- Cancellation leaves input and existing output files intact.

### Phase G — Steganalysis innovation

#### `SA-001` — Establish steganalysis references and test vectors

- Owner: Kim
- Reviewer: Gerome
- Priority: Critical for innovation
- Depends on: `IMG-001`
- Status: In review
- Related requirements: `SA-FR-001`–`SA-FR-007`

Work:

- Record authoritative descriptions of chi-square pairs-of-values and RS analysis.
- Define hypotheses, equations, score direction, grouping, masks, and boundary handling.
- Find or independently create small verifiable test vectors.

Acceptance:

- A team member can explain each formula and assumption.
- Expected small-vector results are calculated independently of production code.
- Sources are cited without copying code blindly.

Implementation note (19 Sep 2026): Code and repeatable evidence added with Codex assistance. See `docs/STEGANALYSIS_GUIDE.md` and `docs/STEGANALYSIS_IMPLEMENTATION.md`; named teammate review is still pending.

#### `SA-002` — Implement chi-square pairs-of-values analysis

- Owner: Kim
- Reviewer: Jun Yong
- Priority: Critical for innovation
- Depends on: `SA-001`
- Status: In review

Acceptance:

- Paired histograms and test statistics match known or independent calculations.
- Full-image and documented windowed configurations are reproducible.
- Raw statistic, score, and interpretation are returned separately.
- Empty, constant, tiny, RGB, and RGBA images are handled safely.

Implementation note (19 Sep 2026): Code and repeatable evidence added with Codex assistance. See `docs/STEGANALYSIS_GUIDE.md` and `docs/STEGANALYSIS_IMPLEMENTATION.md`; named teammate review is still pending.

#### `SA-003` — Implement RS analysis

- Owner: Kim
- Reviewer: Gabriel
- Priority: Critical for innovation
- Depends on: `SA-001`
- Status: In review

Acceptance:

- Regular, singular, and unusable counts match reviewed small vectors.
- Positive and inverse flipping masks are implemented correctly.
- Original arrays are not modified.
- Raw results and interpretation are returned separately.

Implementation note (19 Sep 2026): Code and repeatable evidence added with Codex assistance. See `docs/STEGANALYSIS_GUIDE.md` and `docs/STEGANALYSIS_IMPLEMENTATION.md`; named teammate review is still pending.

#### `SA-004` — Calibrate and evaluate combined interpretation

- Owner: Kim
- Reviewer: Gerome
- Priority: Critical for innovation
- Depends on: `SA-002`, `SA-003`, `IMG-004`
- Status: In review

Work:

- Build a clean/stego evaluation matrix across payload sizes and LSB settings.
- Choose transparent thresholds based on recorded data.
- Identify false positives and false negatives.
- Create plots or tables suitable for the demo.

Acceptance:

- Neither method's output is hidden by the combined category.
- Threshold choices are documented.
- Evaluation includes natural images and does not use only the training/calibration samples as proof.
- Limitations are included alongside results.

Implementation note (19 Sep 2026): Code and repeatable evidence added with Codex assistance. See `docs/STEGANALYSIS_GUIDE.md` and `docs/STEGANALYSIS_IMPLEMENTATION.md`; named teammate review is still pending.

#### `SA-005` — Integrate Steganalysis view and report

- Owner: Matthias
- Reviewer: Kim
- Priority: High
- Depends on: `SA-004`, `GUI-001`
- Status: In review

Acceptance:

- The GUI shows both technique results, combined indication, and limitations.
- Analysis remains separate from the cryptographic verdict.
- A secret-safe analysis report can be exported.

Implementation note (19 Sep 2026): Code and repeatable evidence added with Codex assistance. See `docs/STEGANALYSIS_GUIDE.md` and `docs/STEGANALYSIS_IMPLEMENTATION.md`; named teammate review is still pending.

#### `SA-006` — Add supplementary WAV LSB statistics

- Owner: Kim
- Reviewer: Jian Xuan
- Priority: Optional after all required work
- Depends on: `AUD-002`, `SA-002`
- Status: Not started

Acceptance:

- Results are labelled supplementary and are not described as the two formal methods unless validated for the audio model.
- Bit balance, entropy, or pairs-of-values calculations have reviewed tests.

### Phase H — Testing, evidence, and release

#### `TEST-001` — Create automated core regression suite

- Owner: Gerome
- Reviewer: All primary owners for their areas
- Priority: Critical
- Depends on: Work begins with first core module
- Status: Not started

Acceptance:

- Unit and integration tests cover core, PNG, WAV, crypto, location, verdict, and steganalysis modules.
- Tests use fixed seeds or known vectors where deterministic results are expected.
- The documented test command passes from a clean environment.
- Coverage gaps in security-critical branches are reviewed rather than treated as a percentage-only target.

#### `TEST-002` — Complete required scenario matrix

- Owner: Gerome
- Reviewer: Gabriel, Jian Xuan, and Matthias
- Priority: Critical
- Depends on: `APP-001`, `APP-002`, `GUI-003`
- Status: Not started

Required cases:

- PNG authentic.
- WAV authentic.
- PNG media tamper.
- WAV media tamper.
- Wrong public key/signature invalid.
- Wrong start or secret.
- Payload missing.
- Oversized PNG payload.
- Oversized WAV payload.
- Short Learning Outcome message.
- Large Project Overview message.
- Confidential custom payload.
- Values 1–8 for the required bit interpretation.

Acceptance:

- Expected and actual outcomes are recorded.
- Each failure is caused deliberately and reproducibly.
- At least one positive and negative demonstration is selected for each cover type.

#### `DATA-001` — Create and source sample assets

- Owner: Gerome
- Reviewer: Kim
- Priority: High
- Depends on: Format constraints known
- Status: Not started

Work:

- Generate small deterministic fixtures for automated tests.
- Create team-owned natural samples where practical, such as a team photograph/test graphic and recorded speech/tone WAV.
- If external samples are downloaded, retain source URL, licence, author, and retrieval date.
- Avoid copyrighted assets without appropriate permission.

Acceptance:

- Samples include enough capacity for required payload sizes.
- Natural images support meaningful steganalysis evaluation.
- Provenance is documented.
- No test relies only on an external network resource.

#### `TEST-003` — Perform malformed-input and security review

- Owner: Gerome
- Reviewer: Jun Yong and Kim
- Priority: Critical
- Depends on: `TEST-001`, `APP-002`
- Status: Not started

Acceptance:

- Bad magic, version, lengths, flags, media headers, keys, tags, signatures, and truncation fail safely.
- Private keys, passphrases, and confidential content are absent from ordinary logs.
- No untrusted embedded filename can escape the selected output directory.
- Verification cannot return `Authentic` after any required stage fails.

#### `REL-001` — Validate clean Windows installation and execution

- Owner: Gerome
- Reviewer: Matthias
- Priority: Critical
- Depends on: Feature freeze
- Status: Not started

Acceptance:

- A clean Windows environment follows README commands successfully.
- GUI, image display, WAV playback, protection, verification, analysis, and tests run.
- Dependency versions and known platform limitations are recorded.
- An optional executable is created only if it is reliable and does not replace source-based instructions.

#### `DOC-001` — Complete README and key instructions

- Owner: Gerome
- Reviewer: All members
- Priority: Critical
- Depends on: Interfaces and commands frozen
- Status: Not started

Acceptance:

- README contains overview, supported formats, installation, launch, test, protect, verify, and analysis instructions.
- Security limitations and troubleshooting are included.
- Public-key and safe demo-key handling are explained.
- Commands are copied from a successful clean-run record.

#### `EVD-001` — Capture final evidence package

- Owner: Gerome
- Reviewer: Matthias
- Priority: Critical
- Depends on: `TEST-002`, `REL-001`
- Status: Not started

Acceptance:

- Every selected demo/test case has a report and screenshot or equivalent evidence.
- Original, protected, and tampered filenames are unambiguous.
- Evidence shows inputs/settings and final result, not only a cropped verdict word.
- Dates, app version, and test IDs are identifiable.

#### `ADM-001` — Complete originality, contribution, and AI-use requirements

- Owner: Jun Yong
- Reviewer: All members
- Priority: Critical
- Depends on: Contributions recorded throughout development
- Status: Not started

Acceptance:

- All members approve the contribution statement.
- Originality form is signed.
- AI tools and verification practices are disclosed.
- Required email with subject `ACW1 used in genAI query` and device/source details is sent and retained as evidence.

#### `DEMO-001` — Write and rehearse the ≤25-minute demo

- Owner: Matthias
- Reviewer: All members
- Priority: Critical
- Depends on: Feature freeze, selected cases
- Status: Not started

Acceptance:

- Sequence, speaker, machine, file, settings, expected result, and fallback are recorded for every step.
- Every member has meaningful speaking and demonstration time.
- A full uninterrupted rehearsal finishes within 25 minutes.
- Unknown-payload and key-import rehearsals are performed.
- The required demo plan is uploaded one day before the demonstration.

#### `REL-002` — Produce and verify submission archive

- Owner: Gerome
- Reviewer: Jun Yong
- Priority: Critical
- Depends on: All submission tasks
- Status: Not started

Acceptance:

- Archive contains source, README, supported samples, evidence, public key/instructions, required forms, and contribution statement.
- It excludes caches, virtual environments, accidental secrets, and unnecessary large files.
- The archive is extracted to a new directory and tested before upload.
- Uploaded contents are downloaded or reopened and compared with the intended package.

## 10. Testing and evidence matrix

This table is the minimum traceability baseline. Detailed actual results will move to `docs/TEST_AND_EVIDENCE_PLAN.md` when execution begins.

| Test ID | Requirement/rubric target | Input/action | Expected result | Owner |
|---|---|---|---|---|
| `T-IMG-001` | FR1, FR5, image rubric | Protect and verify valid RGB PNG | `Authentic` | Gabriel |
| `T-IMG-002` | RGBA preservation | Protect RGBA PNG | Alpha unchanged; `Authentic` | Gabriel |
| `T-IMG-003` | Image negative | Modify non-reserved pixel bit | `Tampered` | Gabriel |
| `T-AUD-001` | FR2, FR6, audio rubric | Protect and verify mono PCM WAV | Playable; `Authentic` | Jian Xuan |
| `T-AUD-002` | Stereo handling | Protect and verify stereo PCM WAV | Parameters preserved; `Authentic` | Jian Xuan |
| `T-AUD-003` | Audio negative | Modify non-reserved sample bit | `Tampered` | Jian Xuan |
| `T-CAP-001` | Mandatory capacity | Exact-fit package | Accepted and recoverable | Jian Xuan |
| `T-CAP-002` | Mandatory capacity | Package one byte too large | Rejected before output | Jian Xuan |
| `T-BIT-001` | Settings 1–8 | Parameterised round trips | All supported settings recover exact payload | Gabriel |
| `T-LOC-001` | Variable start | Manual valid position | Successful round trip | Gabriel |
| `T-LOC-002` | Secure start | Correct passphrase-derived start | Successful round trip | Jun Yong |
| `T-LOC-003` | Start negative | Wrong manual start/secret | Controlled non-authentic verdict | Gerome |
| `T-SIG-001` | FR4 | Correct Ed25519 public key | Signature valid | Jun Yong |
| `T-SIG-002` | Failed verification | Wrong public key | `Signature Invalid` | Gerome |
| `T-SIG-003` | Failed verification | Modify signed metadata | `Signature Invalid` | Gerome |
| `T-HSH-001` | FR9 | Valid intentional embedding | Stable hashes match | Jun Yong |
| `T-HSH-002` | Tamper detection | Modify protected media region | Hash mismatch; `Tampered` | Gerome |
| `T-ENC-001` | Confidential payload | Correct AES-GCM secret | Decrypts and verifies | Jun Yong |
| `T-ENC-002` | Encryption failure | Wrong secret/changed tag | `Cannot Verify`; no plaintext parsing | Kim |
| `T-MISS-001` | Verdict | Clean supported file | `Payload Missing` | Gerome |
| `T-FRAME-001` | Safe parsing | Impossible embedded length | `Cannot Verify`; bounded handling | Gerome |
| `T-PAY-001` | Payload variation | Learning Outcome text | Exact recovery | Matthias |
| `T-PAY-002` | Payload variation | Project Overview text | Exact recovery | Matthias |
| `T-PAY-003` | Confidentiality/integrity | Custom encrypted file payload | Exact recovery and valid checks | Jun Yong |
| `T-SA-001` | Innovation | Clean natural image set | Raw and combined results recorded | Kim |
| `T-SA-002` | Innovation | Short 1-LSB payloads | Detection results and misses recorded | Kim |
| `T-SA-003` | Innovation | Large/near-capacity payloads | Detection results recorded | Kim |
| `T-SA-004` | Innovation correctness | Independent small vectors | Chi-square and RS calculations match | Kim |
| `T-GUI-001` | GUI comparison | Protect image through GUI | Both images displayed and labelled | Matthias |
| `T-GUI-002` | GUI playback | Protect WAV through GUI | Both WAVs playable and labelled | Matthias |
| `T-XFER-001` | Party A to B | Transfer/download and verify in receiver folder | Exact payload; `Authentic` | Matthias |
| `T-REPRO-001` | FR12 | Clean Windows setup from README | Install, launch, tests succeed | Gerome |

## 11. Evidence standards

Each manual or demonstration case should record:

```text
test ID
application version or commit
date and operator
original filename and SHA-256 file hash
payload type and size
carrier type and properties
selected bit positions
start-location mode
encryption/signature mode
expected result
actual stage results and verdict
output/report paths
evidence screenshot or recording reference
notes and limitations
```

Evidence should show enough context to prove the cause of a result. For example, a screenshot containing only `Tampered` is weaker than one showing the received filename, signature status, expected hash, computed hash, and final verdict.

## 12. Demonstration plan outline

The detailed sequence belongs in `docs/DEMO_PLAN.md`. The following allocation keeps all six members involved and stays under 25 minutes.

| Time | Lead | Demonstration content |
|---:|---|---|
| 0:00–2:30 | Jun Yong | Scenario, architecture, payload, hash/signature distinction, start-location design |
| 2:30–6:15 | Gabriel | PNG protection, capacity, bit selection, manual/automatic start, visual comparison |
| 6:15–10:00 | Jian Xuan | WAV protection, capacity, saved playback, sample preservation |
| 10:00–13:15 | Matthias | Party A-to-B transfer/download, extraction GUI, valid public-key verification |
| 13:15–16:30 | Gerome | Image/audio tamper, wrong-key or missing-payload cases, verdict reasoning |
| 16:30–20:15 | Kim | Chi-square and RS methods, clean/stego results, limitations and false classifications |
| 20:15–22:30 | Jun Yong and Matthias | Unknown payload/key flexibility, innovation value, security limitations and ethics |
| 22:30–24:30 | All as allocated | Concise technical questions or controlled backup demonstration |

The live sequence shall include at least:

- One authentic PNG.
- One authentic WAV.
- One negative PNG.
- One negative WAV.
- A third meaningful negative case, preferably wrong public key.
- Capacity rejection.
- The short, large, and custom confidential payloads across prepared cases.
- Party A-to-B transfer evidence.
- Both steganalysis methods.

If live email or network transfer is unreliable, use a prepared email/download recording plus an actual copy into a clean receiver folder. The fallback must still demonstrate that verification uses a saved and reopened file, not an in-memory object.

## 13. Risk register

| Risk | Probability | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Whole-file hash cannot match after embedding | High if designed incorrectly | Critical | Use and test the exact stable-media representation before GUI integration | Jun Yong |
| Circular dependency between payload length, hash, signature, and positions | Medium | Critical | Fixed-size fields and two-pass package construction; freeze test vectors | Jun Yong |
| PNG save changes container bytes | High | High | Hash decoded pixel representation and stable properties, not raw PNG bytes | Gabriel |
| WAV sample sign/byte-order error | Medium | High | Known-value tests and cross-review with PNG owner | Jian Xuan |
| Values 7–8 cause severe distortion | High | Medium | Support for compliance, show warning, use 1–2 for normal demos | Matthias |
| Start bootstrap creates a recovery/security conflict | Medium | High | Keep bootstrap minimal, authenticate it, never store derived automatic offset directly | Jun Yong |
| Wrong secret and corruption are indistinguishable | High | Medium | Use `Cannot Verify` where evidence is ambiguous and explain limitation | Gerome |
| Public key is trusted from stego file itself | Medium | Critical | Require independently selected key; embed only fingerprint | Jun Yong |
| GUI integration begins before services stabilise | Medium | High | Use service interfaces and headless integration tests first | Matthias |
| Qt audio playback differs across Windows machines | Medium | Medium | Test early on demo laptop; keep external-player fallback evidence | Jian Xuan |
| Steganalysis implementation looks plausible but is mathematically wrong | Medium | High | Reference equations, independent small vectors, two-person review | Kim |
| Steganalysis performs poorly on natural samples | Medium | Medium | Report honest results, calibrate transparently, explain limitations | Kim |
| Unknown demo payload exceeds carrier capacity | Medium | High | Live capacity display and several high-capacity prepared covers | Gerome |
| Evaluator supplies unsupported key format | Medium | High | Seek clarification; support common PEM import and retain key-generation fallback | Jun Yong |
| Downloaded assets have unclear rights | Medium | Medium | Prefer team-created assets and record provenance/licence | Gerome |
| AI-generated work cannot be explained | Medium | High | Require author review, tests, peer review, and individual rehearsal | All |
| Late feature additions break compatibility | High | High | Freeze on 27 Sep; version frame; require regression tests | Jun Yong |
| Submission archive omits required files or includes secrets | Medium | Critical | Checklist plus clean extraction/retest and two-person review | Gerome |

## 14. Pull-request and review checklist

Before merging or accepting a material change, the author and reviewer should confirm:

- The change maps to a requirement or documented decision.
- New behaviour has tests or a recorded reason why automated testing is impractical.
- Existing regression tests pass.
- Input sizes and embedded lengths are bounded.
- No secret is logged, committed, or placed in evidence accidentally.
- File operations do not silently overwrite user inputs.
- GUI code does not duplicate cryptographic or carrier logic.
- Errors have useful, non-misleading messages.
- Algorithm/version compatibility has been considered.
- Documentation and test vectors are updated where necessary.
- The reviewer can explain the change independently of the author or AI tool.

## 15. Definition of done

### 15.1 Task done

A task is `Done` when:

1. Its acceptance criteria pass.
2. Relevant automated tests pass.
3. A named reviewer has reviewed the result.
4. Documentation and comments explain non-obvious security decisions.
5. Evidence or reproducible commands exist.
6. No critical unresolved defect is hidden behind a success status.

### 15.2 Milestone done

A milestone is complete when every exit condition passes on integrated code in the shared repository. Separate local prototypes do not satisfy an integration milestone.

### 15.3 Project ready for submission

The project is ready only when:

- Mandatory PNG and WAV workflows pass from the GUI and headless tests.
- At least two positive and three negative demo cases are stable.
- Each cover has at least one positive and negative case.
- Capacity and three payload-size requirements are evidenced.
- Both start-location modes work and are explained.
- Hash, signature, encryption if used, and verdict ordering have reviewed negative tests.
- Chi-square and RS implementations have correctness evidence and an honest evaluation.
- README instructions work on a clean Windows environment.
- Required samples, reports, screenshots, keys/instructions, forms, contributions, and demo plan are present.
- The final archive has been extracted and rerun.
- Every team member has rehearsed their segment.

## 16. Submission checklist

### Source and execution

- [ ] Complete source code with clear structure.
- [ ] `pyproject.toml` and pinned dependency information.
- [ ] README with Windows installation and launch instructions.
- [ ] Documented automated test command.
- [ ] Optional executable only if verified reliable.

### Media and evidence

- [ ] Original PNG samples.
- [ ] Protected PNG samples.
- [ ] Tampered PNG samples.
- [ ] Original PCM WAV samples.
- [ ] Protected PCM WAV samples.
- [ ] Tampered PCM WAV samples.
- [ ] Short Learning Outcome payload.
- [ ] Large Project Overview payload.
- [ ] Custom confidential payload.
- [ ] Capacity rejection evidence for image and audio.
- [ ] At least two positive and three negative case reports.
- [ ] Steganalysis dataset, results, thresholds, and limitations.
- [ ] Asset provenance and licences.

### Security material

- [ ] Public verification key.
- [ ] Public-key fingerprint documented.
- [ ] Safe key-generation/import instructions.
- [ ] No unintended private keys or passphrases in repository/evidence.
- [ ] Assignment-only private key clearly labelled if intentionally permitted and included.

### Administrative material

- [ ] Signed Declaration of Originality.
- [ ] Agreed contribution/distribution statement covering all six members.
- [ ] AI use and checking process disclosed.
- [ ] Required lecturer email sent with correct subject and device/source details.
- [ ] ≤25-minute demo plan with speaker sequence and air time.
- [ ] Demo plan and originality form uploaded one day before demo as required.
- [ ] Final package uploaded by the confirmed deadline.
- [ ] Uploaded files reopened or downloaded and checked.

## 17. Lecturer clarification tracker

The questions below are copied from the system specification because their answers may create implementation tasks. The system specification remains authoritative for the current assumptions.

| ID | Question | Current action | Owner | Needed by |
|---|---|---|---|---|
| `Q-001` | Does bits 1–8 mean lowest-N count, individual position, or arbitrary selection? | Design presets plus advanced selection; avoid freezing GUI labels until clarified | Jun Yong | Before M3 |
| `Q-002` | Is an out-of-band passphrase acceptable? | Implement configurable passphrase-derived mode | Jun Yong | Before final demo plan |
| `Q-003` | What payload type and maximum size may be supplied live? | Support text/file bytes and prepare high-capacity covers | Matthias | Before M6 |
| `Q-004` | Which encryption algorithm is expected? | Implement AES-256-GCM and document it | Jun Yong | Before M2 |
| `Q-005` | Will keys be supplied, and in what format? | Support Ed25519 PEM plus local generation; keep import adapter isolated | Jun Yong | Before M6 |
| `Q-006` | Must the email transfer be live? | Prepare live path and recorded/local fallback | Matthias | Before M7 |
| `Q-007` | Must both media types receive formal steganalysis? | Implement both selected methods for PNG; supplementary WAV statistics only after mandatory scope | Kim | Before M4 |

When an answer arrives:

1. Record the date and exact answer.
2. Update the corresponding assumption in `ACW1_SYSTEM_SPECIFICATION.md`.
3. Create or modify affected implementation tasks.
4. Add regression tests for changed behaviour.
5. Reassess schedule and demo impact.

## 18. Decision log

| Date | Decision | Reason | Revisit condition |
|---|---|---|---|
| 15 Sep 2026 | Use two documents: specification and implementation plan | Separates stable behaviour from changing tasks/status | Only if submission format demands consolidation |
| 15 Sep 2026 | Use Python with a Flask backend and a vanilla HTML/CSS/JS single-page frontend | Team choice; a browser-based GUI needs no desktop framework and demos on any machine with a browser | Requirement for an installable desktop application |
| 15 Sep 2026 | Prioritise complete mandatory workflows before enhancements | PNG and WAV carry most marks and optional work must not displace them | Mandatory acceptance achieved |
| 15 Sep 2026 | Use SHA-256, Ed25519, and AES-256-GCM | Established, explainable primitives with library support | Lecturer specifies alternatives |
| 15 Sep 2026 | Provide manual and automatic start modes | Meets teaching/demo needs and security-design requirement | Lecturer narrows requirement |
| 15 Sep 2026 | Use chi-square and RS as the two assessed steganalysis techniques | Complementary established methods for image LSB replacement | Evaluation shows implementation is unsuitable or lecturer requires audio coverage |
| 15 Sep 2026 | Treat steganalysis as probabilistic and separate from verification verdict | Statistical suspicion is not cryptographic authenticity | Never silently change |

## 19. Progress summary

This section should be updated at least once per working session.

| Area | Owner | Current status | Next verifiable outcome |
|---|---|---|---|
| Foundation and architecture | Jun Yong | Not started | Tests and empty GUI run |
| Payload, framing, crypto, hash | Jun Yong | Not started | Frozen vectors and headless signed payload |
| PNG carrier | Gabriel | Not started | Save/reopen byte round trip |
| WAV carrier | Jian Xuan | Not started | Playable save/reopen byte round trip |
| GUI | Matthias | Not started | Navigable shell using service stubs |
| Steganalysis | Kim | In review | 28 automated checks and 100 evaluation cases recorded; obtain peer review and expand natural-image evaluation |
| Verdicts, tests, evidence | Gerome | Not started | Verdict table unit tests and fixture layout |

The next project action is `SETUP-001`, followed immediately by `DES-001`, `PAY-001`, `CORE-001`, and the first PNG/WAV validation spikes.
