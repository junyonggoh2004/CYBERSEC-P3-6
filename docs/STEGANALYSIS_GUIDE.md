# Steganalysis implementation guide

## Scope and status

This guide focuses explicitly on the Steganalysis functionality and implementation.

## Run

From the project root in PowerShell:

# Windows
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python backend/app.py
```

# For MacOS:
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python backend/app.py
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
colour plane, dropping row tails. The RS score is
`(|R+ - R-| + |S+ - S-|)/(2N)`. This normalized mask-asymmetry indicator is our
heuristic, not the paper's quadratic message-length estimator. It should not be
described as percent payload or a calibrated probability. At least 64 groups,
nonconstant data, and usable positive-mask groups are required for a score.

RGB planes stay separate; RGBA alpha is excluded. L-mode PNG uses a single plane.
PNG palette, 16-bit, animated, malformed, over-32-MiB and over-8-million-pixel
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
to this tiny dataset. Both methods crossing gives High indication; neither gives
Low indication; disagreement or insufficient data gives Inconclusive. None of
these categories affects signature/hash verdicts.

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

## Short demo explanation

1. Load a clean image from `evidence/steganalysis/demo` and export its report.
2. Load the same cover's short and large 1-LSB variants. Compare raw counts and
   scores, including misses; the demo filenames identify ground truth.
3. Explain pair equalisation and positive/inverse-mask group changes.
4. Show the held-out results table and explain the small sample size and errors.
5. Explain that cryptographic verification is separate and that the RS output is
   an asymmetry indicator, not an embedding-rate estimate.

