# Benchmark summary for HEEH-V1 v1.0.2

This summary indexes the measurements available in this evidence bundle. It
does not claim clinical accuracy, diagnostic superiority, or generalizability.
See `public_benchmark_report.md` and
`heeh_v1_public_benchmark_results.json` for methods, provenance, and
machine-readable results.

## Evaluations

1. A synthetic CT phantom water ROI was compared with prespecified mean and
   standard-deviation targets.
2. Four first-order features from a deterministic synthetic ROI were compared
   with PyRadiomics 3.0.1.
3. The configured Z-Rad pipeline was compared with populated IBSI
   Configuration D reference rows. A separate PyRadiomics reference-table
   comparison is reported independently.
4. A generated challenge set of valid and invalid archives was used to test
   the export validator.
5. A synthetic navigation-cache workload was timed. Python allocations were
   measured with `tracemalloc`; process memory and end-to-end performance were
   not measured.
6. Public TCIA/NBIA collection metadata was recorded. The image archive was
   not downloaded or evaluated.

## Results at a glance

| Evaluation | Result | Scope |
|---|---|---|
| Synthetic CT water ROI | Mean `-0.04 HU`; standard deviation `10.02 HU` | Synthetic phantom ROI |
| PyRadiomics 3.0.1 comparison | Four values matched; maximum absolute error `0.0` at tolerance `1e-6` | One deterministic synthetic ROI |
| IBSI Configuration D reference table | 270/270 populated rows passed using the configured Z-Rad reference pipeline | Does not certify the application's separate radiomics implementation or full IBSI compliance |
| Separate PyRadiomics reference comparison | 58/66 comparable rows passed; 8 failed; 204 unsupported | Separate from the Z-Rad comparison |
| Generated archive fixtures | 20/20 valid and 20/20 invalid fixtures classified as expected | Constructed fixtures only; not real-world sensitivity or specificity |
| Navigation-cache microbenchmark | Mean `0.003887 s`; median `0.003901 s`; mean Python allocation peak `0.030 MB` | Synthetic workload only; not end-to-end performance or process memory |

The synthetic CT phantom and the PyRadiomics comparison are separate
evaluations. The TCIA/NBIA metadata record is provenance only and must not be
described as an image-level benchmark.

## Evidence files

- `heeh_v1_public_benchmark_results.json` — combined machine-readable results
- `public_benchmark_report.md` — methods, environment, and limitations
- `pyradiomics_comparison.json` — matched first-order comparison
- `ibsi_configuration_d_verification.json` — reference-table comparison
- `../benchmark_source/public_benchmark_evidence.py` — evidence-generation script

The reports in this folder are the included evidence artifacts. The recorded
benchmark workspaces lacked Git metadata, so the measurements cannot be tied
to an exact source revision.

## Limitations

Full IBSI Phase 1/2 compliance, image-level evaluation on
CT-Phantom4Radiomics, patient-level evaluation, clinical validation, and
multi-site generalizability studies were not performed. These measurements
are limited to the protocols and synthetic/reference data stated above.
