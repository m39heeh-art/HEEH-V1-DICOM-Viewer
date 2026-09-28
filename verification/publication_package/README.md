# HEEH-V1 Publication Package — Evidence Bundle

This folder contains the machine-readable benchmark and verification
evidence for HEEH-V1(TM) DICOM Viewer v1.0.2. It is the auditable companion
to `docs/VERIFICATION_EVIDENCE.md` and `docs/standards_traceability.md`.

> **Manuscript note (2026-09-28).** The manuscript sources, tables, and
> title page are **not included** in this public package. They are kept
> private by the author until journal submission to comply with prior-
> publication policies. The benchmark script below regenerates every
> numeric artifact in `02_Evidence/` from scratch, so the evidence remains
> fully reproducible without the manuscript.

> **Public test result (2026-09-28).** The published snapshot reports 320
> passed and 4 skipped tests when optional licensed IBSI reference assets are
> absent. Pytest provides a skip reason for each omitted data-dependent test.
> Results from a local environment containing those optional assets must not
> be described as the clean public-package result.

## Included

- `02_Evidence/` — canonical, machine-readable benchmark artifacts:
  - heeh_v1_public_benchmark_results.json (regenerated 2026-09-27, v1.0.2)
  - public_benchmark_report.md (regenerated 2026-09-27)
  - pyradiomics_comparison.json (matched first-order, tolerance 1e-6, max error 0.0)
  - ibsi_configuration_d_verification.json (Z-Rad reference pipeline, 270/270)
  - Scientific Benchmark Dossier.md, final_benchmark_summary.md
- `benchmark_source/public_benchmark_evidence.py` — the benchmark script
  that produced every number in `02_Evidence/` (recorded SHA-256 inside
  the JSON artifacts). Run it to re-derive the results end to end.

## What the measured evidence is (and is not)

Measured in this environment and recorded in the JSON artifacts:
- Radiomics on the synthetic ACR-style water ROI passes its pre-specified
  tolerances (mean -0.04 HU, std 10.02 HU vs targets 0.00 ± 3.00 / 10.00 ± 2.00).
- PyRadiomics v3.0.1 matched first-order comparison on the same ROI:
  all absolute errors 0.0 at the declared 1e-6 tolerance.
- IBSI Configuration D: all 270 populated reference rows of the official CT
  radiomics phantom table reproduced via the configured Z-Rad reference
  pipeline, and the application's dedicated Configuration D workflow
  (3D image + aligned ROI mask) verified against the same rows.
- Export/privacy validator: sensitivity 1.000, specificity 1.000 on 20 valid
  and 20 invalid generated fixtures.
- Runtime/memory: mean 0.003887 s, median 0.003901 s, peak 0.030 MB over
  20 repetitions of the fixed workload (8 images, 128 operations, cache 3).

Explicit non-claims (limitations, not hidden):
- No clinical accuracy, diagnostic superiority, or patient-level validity claim.
- No official IBSI Phase 1/2 benchmark; no full IBSI certification beyond the
  Configuration D verification described above.
- The public archive was used at metadata level only; the application's
  default single-slice radiomics path is disclosed as not
  Configuration-D-compliant (published values must use the dedicated workflow).

## Provenance note (2026-09-28)

Before the public release, one diagnostic string inside
`public_benchmark_evidence.py` (a local `install_command` hint embedded in a
PyRadiomics-unavailable error branch) was generalized, removing a personal
local file path. The script's SHA-256 changed accordingly, and the recorded
`benchmark_script_sha256` in `heeh_v1_public_benchmark_results.json` was
updated to the shipped script. No measured value, tolerance, comparison, or
test outcome was affected by this edit; the full evidence can be re-derived
by re-running the shipped script.

## Reliability and blocker policy

The benchmark JSON records environment, script hash, input hashes, and
comparator version for every number, so each result can be re-derived from
the archived package. Results that cannot be rerun or linked to their exact
inputs would be labeled as recorded historical evidence rather than current
verification; every result in the current artifacts is rerunnable.

## Reproducing the evidence

With the package environment installed (see the repository README):

```
python verification/publication_package/benchmark_source/public_benchmark_evidence.py
```

Regenerated artifacts must match the SHA-256 hashes recorded inside the
existing JSON files for the same environment.
