# Steganalysis implementation guide

## Scope and status

Implemented within the existing Flask/browser architecture, not the proposed
PySide6 layout. Kim's SA-001/002/003 code, SA-004 evaluation, and an SA-005
integration are ready for team review. No teammate review is claimed. Optional
WAV statistics (SA-006) are deferred. This is AI-assisted code requiring Kim's
own understanding and the named reviewers' checks before marking tasks Done.

## Run

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests/test_steganalysis.py -q
.\.venv\Scripts\python.exe backend/app.py
```

Open http://127.0.0.1:5000 and scroll to **PNG Steganalysis**. Choose a clean or
stego PNG, click **Analyse PNG**, inspect both techniques, then export JSON.
Reports contain file hashes/settings/statistics, never signing keys or payloads.
The existing app generates its signing keys on first launch; the new analysis
does not require keys. `requirements-tested.txt` records the exact tested
environment as an optional reproducibility alternative to the dependency ranges.

## Mathematics and implementation choices

Chi-square follows the even-category pairs-of-values convention in
[Westfeld and Pfitzmann, section 4.1](https://users.ece.cmu.edu/~adrian/487-s06/westfeld-pfitzmann-ihw99.pdf).
For pair `(2i, 2i+1)`, `E_i=(h[2i]+h[2i+1])/2` and
`X²=sum((h[2i]-E_i)²/E_i)`, with `df=k-1` for k retained pairs.
This implementation omits pairs with E<5 and reports omitted pairs and retained
samples. SciPy's survival function returns the tail score. Large scores mean
compatibility with pair equalisation, not posterior probability of a payload.

RS uses the group discrimination and flips described by
[Fridrich, Goljan and Du, sections 2–3](https://dde.binghamton.edu/publications/acmwrkshp_version.pdf).
For each group, `f=sum(abs(x[i+1]-x[i]))`. Use masks `(0,1,1,0)` and
`(0,-1,-1,0)`, with `F1(x)=x XOR 1` and `F-1(x)=((x+1) XOR 1)-1`.
An increased f is regular, decreased f singular, and equal f unusable.
Signed arithmetic retains -1 and 256 without clipping or wrapping.

Project-specific choices: nonoverlapping horizontal groups of four within each
colour plane, dropping row tails. R/S counts are taken on the image and again
after flipping every LSB, and the four R-S differences are fitted with the
paper's quadratic (Fridrich, Goljan and Du) to estimate the fraction of values
carrying 1-LSB replacement; a straight-line fallback is used when the quadratic
has no real root. The RS score is that estimate's magnitude bounded to 0-1. It
is an estimate, not a calibrated probability. At least 64 groups, nonconstant
data, and usable positive-mask groups are required for a score.

Chi-square per channel uses the stronger of its whole-channel tail score and the
median usable-window tail score, so sustained regional embedding (as written by
this project's contiguous encoder) is not diluted by the untouched remainder. A
single high window is not used, because scanning many windows gives chance peaks.

RGB planes stay separate; RGBA alpha is excluded. L-mode PNG uses a single plane.
PNG palette, 16-bit, animated, malformed, over-200-MiB and over-50-million-pixel
inputs are rejected. No input file/array is modified. Full-channel scores are
combined using their median; any unavailable channel makes that method
inconclusive. The report preserves all channels. Chi-square windows cover
consecutive values per plane with a default size of 65,536; it increases if
necessary to keep at most 128 windows. Windows do not alter the combined score.

## Independent vectors

Chi-square histogram pairs `(12,8),(6,14),(10,10)` give E=10 for each pair,
X²=2, df=2, and score `exp(-1)=0.36787944117`.

For groups `[0,0,0,0]`, `[0,1,1,0]`, `[0,1,2,3]`, original f is 0,2,3.
The positive mask gives f=2,0,3 (R=1,S=1,U=1). The inverse mask gives
f=2,4,5 (R=3,S=0,U=0). Tests also compare thousands of seeded groups
against an independent scalar parity implementation, including 0/255 edges.

## Evaluation and threshold policy

Included: four public-domain/CC0 natural images, 100 cases, seeds, source hashes,
1/2/4/8-LSB settings, 1%/50%/95% payload occupancy, starts at 0/3%, and clean
controls. Files and rights are documented in `samples/steganalysis/PROVENANCE.md`.
The evaluator embeds random bytes with the project's existing `embed_bits`,
saves/reopens PNG, and performs blind analysis. This isolates carrier statistics;
separate integration tests exercise the signed encode/decode pipeline.

```powershell
python scripts/evaluate_steganalysis.py
# Optional, only if the included natural covers are missing:
python scripts/fetch_analysis_samples.py
# Use another independent image collection and keep its evidence separate:
python scripts/evaluate_steganalysis.py --covers path/to/pngs --output evidence/my-dataset
```

Cover identities alternate between calibration and holdout after filename sorting.
All variants of a cover stay in one split. Duplicate decoded images are rejected.
Grid-search thresholds are fitted only on calibration clean/1-LSB cases,
minimizing mean FPR/FNR, with ties preferring fewer false positives then stricter
thresholds. The held-out covers are not used for tuning. More covers and truly
independent camera sources are needed for meaningful deployment claims.

The GUI defaults remain explicitly provisional (`chi_square=0.95`, `rs=0.05`).
The evaluation stores its selected thresholds separately, and records both default
and calibrated categories for every case. No global threshold is silently tuned
to this tiny dataset. Either method crossing its threshold gives High
indication; both available and below threshold gives Low indication; otherwise
Inconclusive. None of these categories affects signature/hash verdicts.

`evidence/steganalysis/RESULTS.md` summarizes results. CSV lists every miss/false
alarm; JSON retains all scores, raw counts, histograms and windows. In confusion
tables only High indication is positive. Inconclusive stego cases count as false
negatives and are also tallied separately, avoiding optimistic exclusion.
The results show major misses, particularly at small payload sizes and higher
LSB settings. Do not describe this small evaluation as proof of detector accuracy.

## Existing-code integration observations / crypto review

- The existing crypto code uses RSA-2048/PKCS#1 v1.5, not the plan's Ed25519.
  Tests cover valid signatures, changed messages, changed signatures and wrong
  keys using ephemeral keys, leaving stored keys untouched.
- AES-GCM encryption and the planned purpose-separated KDF are absent; ENC-002
  and KEY-001 cannot be validated yet. A passphrase currently selects an offset;
  it does not encrypt the payload. No encryption implementation is claimed here.
- The existing PNG adapter includes alpha in RGBA carriers; this analysis excludes
  alpha. A payload mainly in alpha may therefore be missed. Carrier format changes
  need coordination with Gabriel, so this addition preserves existing compatibility.
- The existing stable hash masks the selected low bits across the entire carrier.
  At 8 LSBs, all image byte values are masked away; it cannot establish pixel
  integrity. This predates Kim's changes and should be reviewed by the core owners.

## Audio and video: sample-pair analysis

Implemented in `backend/stego/audio_analysis.py`; the Steganalysis page routes
WAV files and the audio track of a video there (PNGs still use chi-square/RS).

**Why not chi-square.** A 16-bit recording's value histogram is already smooth
at the LSB scale, so neighbouring values such as 100/101 occur about equally
often in clean audio. Chi-square then reports clean recordings as embedded
(p = 1.00 on clean noise-like audio and on the sample video's clean track).

**Method.** Consecutive samples in one channel form pairs (u, v). The trace
m = floor(v/2) − floor(u/2) is unchanged by LSB replacement. Within trace m,
b_m counts (even, odd) pairs, c_m (odd, even) pairs and T_m all pairs. Cover
assumption: an odd difference d = 2m+1 is equally likely to start on an even
or odd value, so b_m = c_{m+1}. This project's encoder writes one contiguous
block, so replacing the LSBs of a share p of samples gives, in expectation,
b'_m − c'_{m+1} = (p/4)(T_m − T_{m+1}) for every m. The estimate is a weighted
least-squares fit of that line (Dumitrescu, Wu & Wang, 2003, adapted from their
random-scatter model to block embedding).

**Cross-fitting.** The slope T_m − T_{m+1} is counted from pairs at even
positions and the residual from pairs at odd positions, then vice versa.
Counting both from the same pairs shares their noise, which drags loud,
uninformative audio towards p = 1 (a false alarm); cross-fitting drags it
towards 0 with a wide standard error instead. The time map fits each of 16
segments against the whole file's slope.

**Decision (provisional).** Standard error above 0.1: *Inconclusive*. Otherwise
*High indication* when the lower end of the 95% interval exceeds 3%, else *Low
indication*.

**Measured on this project's encoder (1 LSB, manual offset 100).** True share
0 / 5 / 25 / 50 / 100%:

| Source | Estimates | Standard error |
|---|---|---:|
| Sample sine tone (16-bit) | 0.00 / 0.03 / 0.22 / 0.47 / 0.97 | ≈0.01 |
| Speech-like 16-bit (synthetic) | −0.01 / 0.03 / 0.23 / 0.47 / 0.96 | ≈0.02 |
| Sample video audio track | −0.01 / 0.01 / 0.17 / 0.35 / 0.70 | ≈0.04 |
| Loud music-like / pink noise | inconclusive | 1–7 |
| 32-bit audio | inconclusive | >2 |

**Limits.** It needs neighbouring samples that are close in value (quiet
passages, pauses), so loud, noisy or 32-bit audio is usually inconclusive
rather than detected. Partial 2+ LSB payloads are underestimated (25% at 2 LSB
reads 0.04–0.15). The sample audio files are pure tones and the other sources
are synthetic; validate on real recordings before relying on the thresholds.

## Likelihood of hidden data

After every analysis the page shows one headline figure: the chance that the
file carries hidden data. It comes from sample-pair analysis (`backend/stego/spa.py`),
which now also runs on PNGs, over horizontally adjacent pixels within each row
of the R, G and B planes (alpha excluded). Chi-square and RS still decide the
PNG verdict; their tail score and payload-fraction estimate cannot be turned
into a probability, so the likelihood is reported alongside them.

**Calculation.** Two hypotheses are compared: *clean* (true share 0) and
*hidden data* (true share uniform between 1% and 100% of values). Both start at
50%. The SPA estimate is treated as normal around the true share, with its
standard error widened by a natural cover bias (images ±2.5, audio ±2.0
percentage points), because clean covers do not estimate exactly 0: the clean
astronaut image reads 0.050 ± 0.005. Bayes' rule gives the posterior chance.
With little evidence it stays near 50% instead of guessing.

**Bands:** Unlikely (≤ 20%), Uncertain, Likely (≥ 80%); Unknown when no estimate
is possible (for example a pure-noise image).

**Measured on this project's encoder (1 LSB):**

| Cover | Clean | 1 KB message | 25% full | 95% full |
|---|---:|---:|---:|---:|
| chelsea / clock_motion / coffee | 3–4% | 15–21% | 100% | 100% |
| astronaut (naturally biased) | 30% | 62% | 100% | 100% |
| cover_image.png | 2% | 8% | 100% | 100% |
| Sample WAV (sine tone) | 2% | 99% | 100% | 100% |

**Limits.** The prior, share range and cover-bias allowance are provisional
choices, not calibrated on real-world files. Short messages in photographs are
often missed. The figure is about hidden data, not tampering: tampering is
decided on Verify by the signature and hashes.

## Short demo explanation

1. Load a clean image from `evidence/steganalysis/demo` and export its report.
2. Load the same cover's short and large 1-LSB variants. Compare raw counts and
   scores, including misses; the demo filenames identify ground truth.
3. Explain pair equalisation and positive/inverse-mask group changes.
4. Show the held-out results table and explain the small sample size and errors.
5. Explain that cryptographic verification is separate and that the RS output is
   an estimated LSB-replacement fraction, not a probability of hidden data.

Before submission: Kim validates the explanation, Gerome reviews evidence,
Jun Yong reviews chi-square, and Gabriel reviews RS. No emails, submission,
originality signatures, or teammate approvals have been performed automatically.
