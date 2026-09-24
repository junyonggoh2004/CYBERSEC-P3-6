# Audio metrics and WAV validation

What the `jx_wav-metrics` branch (PR #5) adds for the audio cover object, how to
check it, and what it does not cover.

| Part | Delivered work | Review status |
|---|---|---|
| Audio metrics | `backend/stego/audio_metrics.py`: changed samples, MSE, SNR and max sample change for a cover/stego WAV pair; SNR tile on the Compare page | Awaiting review |
| WAV validation | `load_audio_carrier()` in `backend/stego/audio_lsb.py`: clear messages for unsupported or damaged WAV files | Awaiting Potana (file owner) |
| Tests | `tests/test_audio_metrics.py` (24), `tests/test_audio_lsb.py` (77) | All 181 project tests pass at commit `a2354cc` |

## Run the checks

```
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_audio_metrics.py tests/test_audio_lsb.py
python -m pytest
```

To see the metrics in the app: start `python backend/app.py`, protect a WAV on
**01 Protect**, then open **Compare** and click **Load last protected pair**. The
SNR tile appears after PSNR, and **Exact comparison measurements** lists the full
`audio_metrics` object.

## Audio metrics

`audio_metrics.compare(cover, stego)` takes the two sample arrays (16- or 32-bit
PCM, same length and type) and returns:

| Field | Meaning |
|---|---|
| `changed_samples` / `total_samples` | Samples whose value differs, out of all samples (every channel counted) |
| `mse` | Mean squared error, `sum((cover - stego)^2) / N` |
| `snr_db` | `10 * log10(mean(cover^2) / mse)`: the change measured against the audio's own level |
| `snr_reference` | Which reference the SNR used: `signal`, `full_scale` or `identical` |
| `max_sample_change` | Largest change to any single sample |

**Why SNR as well as PSNR.** PSNR compares the change with the largest possible
sample value, so it is the same for a quiet and a loud recording. SNR compares
the change with the recording's actual level, which is the better indication of
whether the change could be heard. A higher SNR means less distortion.

**Edge cases are labelled rather than hidden:**

- A silent cover has no signal to compare with. Full scale (`2^(bits-1)`, i.e.
  32768 for 16-bit) is used instead and the value is shown as
  `... dB vs full scale (cover is silent, so this is not a true SNR)`.
- An identical stego has no noise, so the SNR is infinite. It is shown as
  `inf (stego is identical to the cover)` and sent as `null` in JSON, because
  `Infinity` is not valid JSON and would break the browser's `res.json()`.

**Max sample change and the LSB depth.** LSB replacement only rewrites the lowest
*k* bits, so no sample can move by more than `2^k - 1` (1, 3, 15 ... 255 for
1, 2, 4 ... 8 LSBs). The measured value can be lower when the payload is short.

**Memory.** The arrays are processed in chunks of 1,048,576 samples, so memory
stays flat for long audio: about 17 MB extra for a 10-minute stereo 44.1 kHz
track, compared with about 1.27 GB when the whole track is converted to float64
at once.

**Example (16-bit WAV, 1 LSB, from the Compare page):** 2.3598% of samples
changed, max change 1, MSE 0.02360, SNR 97.5 dB. With 1 LSB every changed sample
moves by exactly 1, so the MSE equals the fraction of samples changed.

`/api/compare` returns these values as `audio_metrics` for WAV pairs, alongside
the existing paired measurements from `comparison.py`. The changed count, max
difference and MSE agree with those measurements; a test checks this.

## WAV validation

Supported covers: uncompressed **16-bit or 32-bit PCM WAV**, any number of
channels. Anything else is rejected with a `ValueError` whose message the GUI
shows directly (HTTP 400 on Protect and Compare, a **Cannot Verify** result with
the same explanation on Verify). Previously some of these files produced
`Unexpected server error: ...` (HTTP 500).

| File | Message |
|---|---|
| Not a WAV (e.g. a renamed text file) | This file is not a WAV file. Please choose a 16-bit or 32-bit PCM WAV. |
| Empty, or cut off in the header | This WAV file is empty or cut off before its audio data. Please use a complete WAV file. |
| 32-bit float WAV | 32-bit float WAV is not supported (LSB embedding needs integer samples). Please export it as 16-bit or 32-bit PCM WAV. |
| Compressed (e.g. mu-law) | This WAV uses a compressed or non-PCM encoding. Please export it as 16-bit or 32-bit PCM WAV. |
| 24-bit PCM | Unsupported WAV sample width: 24-bit PCM. Supported: 16-bit and 32-bit PCM. |
| 8-bit PCM | 8-bit PCM WAV is not supported (too little headroom for reliable LSB embedding). Please use 16-bit or 32-bit PCM WAV. |
| Audio data ends part-way through a sample | This WAV file is truncated or damaged: its audio data stops part-way through a sample. Please use a complete WAV file. |
| No audio samples | This WAV file contains no audio samples. |
| Extensible header on Python 3.11 | This WAV uses the extensible header format, which this Python version cannot read (Python 3.12 or newer can). Please re-export it as a standard 16-bit PCM WAV. |

**Frame count.** When a file is cut off at a sample boundary, its header still
claims the original length. The loader now counts the frames that are actually
present, so the reported length of a cover matches the stego file written back
out. Previously the two could differ, and because the cover description is part
of the stable cover hash, a genuine file could then be reported as Tampered.

## Tests

`tests/test_audio_metrics.py` (24 tests):

- Hand-calculated values: MSE 2.5, SNR 40 dB, no int16 overflow, silent and
  identical covers and their labels.
- Rejection of mismatched shapes, empty arrays, mixed or non-integer sample types.
- Max sample change: a known value, and the `2^k - 1` limit at every depth 1-8.
- Chunked results match the whole-array formulas (tested with a 7-sample chunk
  so many chunk boundaries are crossed).
- `/api/compare`: audio pairs return `audio_metrics` matching an independent
  recompute; an identical pair sends `snr_db: null`; image pairs have none.

`tests/test_audio_lsb.py` (77 test cases):

- Loading 16- and 32-bit, mono and stereo WAV as signed little-endian samples;
  `describe()` output.
- Save and reload keep channels, sample width, sample rate and samples
  (8, 44.1 and 48 kHz).
- Hidden bytes survive save and reload at every LSB depth 1-8.
- Embedding changes only the chosen low bits, and nothing before the start
  location or after the payload.
- Every rejected file type above, plus a check that `/api/prepare` answers
  HTTP 400 with the message rather than a server error.

The tests were checked against deliberately broken copies of the code (a chunk
loop that skipped the last chunk, the Compare route not returning the metrics,
`Infinity` in the JSON, the old loader, a save that dropped the sample width,
frame count taken from the header); each break made tests fail.

## Limitations

- SNR is a signal measure, not a model of human hearing. A high SNR suggests,
  but does not prove, that the change is inaudible.
- The metrics describe how much the file changed. They do not show that data is
  hidden or that a file is authentic.
- 24-bit and float WAVs must be converted to 16- or 32-bit PCM first.
- The Compare page accepts PNG and WAV only, so the audio track of a video cover
  is not measured in the GUI.
- The browser test `tests/frontend_workflow.cjs` needs Node.js and was not run
  for this change.

## Short demo explanation

- Protect a 16-bit WAV at 1 LSB, then compare: about 2% of samples change, each
  by at most 1, and the SNR is around 97 dB, far below anything audible.
- Repeat at 8 LSBs: the max change rises towards 255 and the SNR drops, showing
  the capacity/distortion trade-off of the LSB setting.
- Pick a float WAV as a cover: the app explains what is wrong and how to export
  a supported file, instead of failing with a server error.
