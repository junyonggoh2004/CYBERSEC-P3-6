





# Steganalysis implementation record — prepared for review

| Task | Delivered work | Review status |
|---|---|---|
| SA-001 | Source references, documented formulas and independent vectors | Awaiting Gerome |
| SA-002 | PoV histograms, chi-square statistic/tail score, full and window modes | Awaiting Jun Yong |
| SA-003 | Positive/inverse RS masks, R/S/U counts, asymmetry indicator | Awaiting Gabriel |
| SA-004 | Natural covers, source-level split, threshold search, 100-case evidence | Awaiting Gerome; larger evaluation needed |
| SA-005 support | Flask API, asynchronous browser view and JSON export control | Awaiting Matthias/Kim review |
| Crypto test review support | Correct/wrong key, changed message/signature checks | Existing RSA tested; Ed25519/AES/KDF not implemented |

## Automated checks

- 28 tests passed in `tests/test_steganalysis.py`, recorded in `evidence/steganalysis-tests.xml`.
- Existing `tests/run_demo.py`: 9/9 expected results, run in an isolated copy to
  avoid replacing the supplied public key. `evidence/existing-demo-log.json` is
  the copied result log. Its paths refer to the temporary test environment.
- Browser check: asynchronous upload/analysis displays both methods and their
  combined indication, and changing window settings hides stale results and
  disables export. No JavaScript errors observed. The JSON export button was
  clicked, but the in-app browser did not report a download event; verify the
  saved-download interaction in Chrome/Edge during team acceptance.
- Evaluation reports both false positives and false negatives. No natural-image
  accuracy claim is justified by just four covers.

## Main files

- `backend/stego/analysis.py`: statistics, image validation, report and combination.
- `backend/app.py`: `/api/analyse` route reusing existing background jobs.
- `frontend/analysis.js`, `frontend/index.html`: independent analysis view.
- `scripts/evaluate_steganalysis.py`: seeded evaluation and calibration.
- `scripts/fetch_analysis_samples.py`: optional public-sample download.
- `tests/test_steganalysis.py`: mathematical, API, crypto and pipeline checks.
- `docs/STEGANALYSIS_GUIDE.md`: formulas, assumptions, limitations and demo guide.
