# HEEH-V1 v1.0.2 public benchmark report

This report presents measured results and identifies experiments that were
not performed. It does not claim clinical accuracy, diagnostic superiority,
or generalizability.

## Public provenance
- Collection: `CT-Phantom4Radiomics`
- SeriesInstanceUID: `1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879`
- License: `Creative Commons Attribution 4.0 International License` (https://creativecommons.org/licenses/by/4.0/)
- DataDescriptionURI: `https://doi.org/10.7937/a1v1-rc66`
- Download status: `metadata_only`; no file hash was generated because the archive was not downloaded.

## Execution environment
- Project version: `1.0.2`
- Python: `CPython 3.11.9`
- Platform: `Windows-10-10.0.26200-SP0`
- Architecture: `AMD64`
- Processor: `Intel64 Family 6 Model 154 Stepping 3, GenuineIntel`
- Dependency lock SHA-256: `034e31309cbfcc5c4d567ae125c9b9731e6ad428d9e69e67834fdbe2a7847614`
- Benchmark script SHA-256: `23f48ac147e103362ddd8200aa3413e621defec2210940c9c804ae81b92005b0`
- Source revision: `unavailable; this workspace has no Git metadata`

## Radiomics benchmark (synthetic CT phantom ROI)
- ROI: `water ROI from ACR-style digital phantom`
- Preprocessing: 256 levels, fixed bin width of 2.0, spacing of 1.0 × 1.0
- Measured mean/std: -0.04 / 10.02 HU
- Ground-truth targets: mean 0.00 ± 3.00; std 10.00 ± 2.00
- Pass: True (absolute errors: mean 0.04, std 0.02)

## Matched PyRadiomics comparison
- Status: `measured`
- Scope: Matched first-order comparison on a synthetic ROI only.
- PyRadiomics version: `v3.0.1`
- ROI shape/SHA-256: `[87, 87]` / `5a3f4a3405bf7cf1ad32e3877c14319cb807d894675908cf67b855879d02ab86`
- Absolute errors (mean/std/min/max): `{'max': 0.0, 'mean': 0.0, 'min': 0.0, 'std': 0.0}`
- Within tolerance: `True`
- Environment: `Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.43`; Python `3.10.21`
- Result artifact: `pyradiomics_comparison.json` (SHA-256 `7e07bee8a4275709f015a2ddcbaef403c395614facb9322302c31d109413483a`)

## IBSI Configuration D reference verification
- Status: `configuration_d_reference_verified`
- Reference dataset: `ibsi_1_ct_radiomics_phantom` at `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`; license `CC BY-NC 3.0`
- Configuration D Z-Rad comparison: `270` compared; `270` passed; `0` failed; `0` unsupported.
- PyRadiomics reference comparison (separate from Z-Rad): `66` compared; `58` passed; `8` failed; `204` unsupported.
- Z-Rad statistics rows: `18` compared; `17` passed; `1` failed.
- Default viewer slice radiomics: `not_configuration_d_compliant`. It uses a 2D unmasked slice, so no Configuration D pass/fail comparison is made for this path.
- Boundary: All populated IBSI Configuration D reference rows were compared with the configured Z-Rad reference pipeline. This result is configuration-specific and does not certify the application's separate radiomics implementation or full IBSI compliance.
- Result artifact: `ibsi_configuration_d_verification.json` (SHA-256 `0212285040cbfc6ce017e91ed380f3b511727d40b671b1df54f2debd466b7e21`)

## Export/privacy validation benchmark
- Fixture set: 20 valid and 20 invalid generated challenge archives.
- Interpretation: Constructed fixtures only; not a real-world performance estimate.
- Sensitivity: 1.000
- Specificity: 1.000
- TP/TN/FP/FN: 20/20/0/0

## Runtime and memory benchmark
- Mean elapsed: 0.003887 s
- Median elapsed: 0.003901 s
- Mean Python allocation peak: 0.030 MB
- Cache hit rate over fixed protocol: 0.000
- Scope: Synthetic navigation-cache workload only. Peak memory is Python allocation memory measured by tracemalloc; it excludes native library allocations, process RSS, image decoding, model inference, and end-to-end application workloads.

## Unavailable experiments
- Full IBSI Phase 1/2 compliance certification was not performed.
- Image-level evaluation on CT-Phantom4Radiomics was not performed; only collection metadata is recorded.

## Limitation statement
Measurements above are limited to the stated synthetic ROIs, Configuration D
reference table and Z-Rad pipeline, generated challenge fixtures, and
synthetic navigation-cache workload. They are not clinical validation, do not
establish generalizability or superiority, and do not constitute full IBSI
compliance.
