# Steganalysis evaluation

Selected thresholds: `{'chi_square': 0.8, 'rs': 0.1}`.

Split by source image. Thresholds fitted only on calibration clean/1-LSB cases.
Only High indication counts as detection; inconclusive cases count as misses for stego images.

| Split/settings | TP | FP | TN | FN | Inconclusive |
|---|---:|---:|---:|---:|---:|
| calibration_1lsb | 2 | 0 | 2 | 10 | 4 |
| calibration_2lsb | 2 | 0 | 2 | 10 | 4 |
| calibration_4lsb | 0 | 0 | 2 | 12 | 2 |
| calibration_8lsb | 0 | 0 | 2 | 12 | 2 |
| holdout_1lsb | 4 | 0 | 2 | 8 | 0 |
| holdout_2lsb | 4 | 0 | 2 | 8 | 1 |
| holdout_4lsb | 0 | 0 | 2 | 12 | 4 |
| holdout_8lsb | 0 | 0 | 2 | 12 | 4 |

## Limitations

- Small demonstration dataset; correlated derivatives are not independent evidence.
- Raw random payloads test the existing embed_bits function, not signed container overhead.
- Higher LSB settings are exploratory, outside the formal 1-LSB model.
- Calibrated values are evaluation-only; GUI retains explicit provisional defaults.

See evaluation.csv for every false alarm, miss, and inconclusive case; raw_results.json retains both techniques and windows.
