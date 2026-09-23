# Natural-image sample provenance

Downloaded from the tagged scikit-image v0.18.3 sample collection. These are
natural photographs, not synthetic gradients. No resizing, colour conversion,
or recompression is performed when downloading. Evaluation serializes decoded
pixels as PNG using the existing carrier adapter. Historical processing of
these familiar benchmark images is not controlled, limiting generalisation.

| Sample | Credit and rights | Assigned split (sorted source names) |
|---|---|---|
| astronaut.png | NASA, Eileen Collins photograph; public domain | Calibration |
| chelsea.png | Stefan van der Walt; CC0 | Holdout |
| clock_motion.png | Stefan van der Walt; public domain | Calibration |
| coffee.png | Rachel Michetti, courtesy of Pikolo Espresso Bar; CC0 | Holdout |

Rights and descriptions are recorded in the upstream
[sample loader documentation](https://github.com/scikit-image/scikit-image/blob/v0.19.3/skimage/data/_fetchers.py).
`manifest.json` records source URLs and SHA-256 hashes of the downloaded files.
`python scripts/fetch_analysis_samples.py` downloads missing files only.
No team-created or team-licensed provenance is claimed for these external samples.
