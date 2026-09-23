# Encoder-to-analysis workflow update

## What changed

- After successfully encoding a PNG, **Analyse this stego PNG** loads and analyses
  the same bytes as the existing download link. The button is hidden for audio/video.
- The selected filename, byte length and PNG SHA-256 are visible. The browser hashes
  the selected bytes and requires the server's reported hash to match before showing
  or exporting a result. This checks file identity, not authenticity or extraction.
- Small nonzero scores use scientific notation. A returned zero tail score is
  labelled below numerical precision, not rounded into a claim of no hidden data.
- Each channel's full-image statistic, degrees of freedom and tail score remain
  visible. RS zero remains a normal zero; it is not labelled numerical underflow.
- The visible window table shows channel, index, start/end, sample count, statistic,
  degrees of freedom, tail score and threshold observation. A summary reports the
  effective window size, usable windows, peak and count above the reference threshold.
- Window peaks are exploratory, with a multiple-comparisons caution. They do not
  silently replace the whole-image classifier or change its provisional thresholds.
- Encoder settings are captured from the completed response: LSB depth, start,
  signed-container size, capacity and occupancy. This is known encoding context,
  not blind detection or independent proof of payload recovery. Use Verify for that.
- Manual file selection clears encoder context. Editing the window size clears old
  results/export but retains the selected file so the user can rerun it.
- Concurrent analysis clicks are blocked. Errors and hash mismatches clear stale
  reports and restore controls. The exported JSON includes file identity, source,
  explicitly labelled context and display version, without private keys/passphrases
  or hidden payload bytes.

## Try it

1. Run the updated project from the GitHub clone, then hard-refresh the page (Ctrl+F5).
2. Protect: upload a PNG, add text or a file payload, select settings and encode.
3. Click **Analyse this stego PNG** in the result panel.
4. Check the encoder source label, hash and known encoding information.
5. Inspect the whole-image score and window table. Change window size and click
   **Analyse PNG** again. Whole-image results stay the same; windows change.
6. Upload a PNG manually. The encoder-information box should disappear.
7. Export JSON. Use the separate Verify panel if you need to prove exact recovery.

The existing PNG mode, 32-MiB and 8-million-pixel analysis limits still apply.
The original and stego image comparison requirement is a separate GUI feature.

## Validation on 23 September 2026

- 30 Python tests passed, including two new HTTP encode/save/reopen/analyse/decode
  round trips: repeated text and an actual PNG as a file payload. Both checks
  recover the payload exactly and compare the analysed SHA-256 with saved bytes.
- Five Node tests passed: exact-byte handoff/export/context allowlist, window rerun
  and source reset, underflow wording, hash-mismatch rejection, API error recovery.
- Both frontend scripts passed Node syntax checks.
- Browser: encoded repeated text into coffee.png, then clicked the direct-analysis
  button. Hash comparison succeeded. The whole-image score was 2.5752e-167 and
  capacity usage 14.29%. Switching 65,536 to 4,096 values changed the window table
  from 12 to 177 rows without changing the whole-image score. No console errors.
- JSON contents/export handler are unit tested; OS download completion was not
  independently verified in the in-app browser.

```powershell
python -m pytest tests/test_steganalysis.py -q -p no:cacheprovider
node tests/test_analysis_ui.cjs
```

Node 20+ is needed only for the frontend unit tests, not for running the Flask app.
This update does not claim improved statistical sensitivity: genuine embedded
payloads can still yield low scores. Regional findings need independent calibration
before being used as an alternative detection rule.
