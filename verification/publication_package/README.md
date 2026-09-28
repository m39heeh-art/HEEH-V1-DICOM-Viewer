# HEEH-V1 Publication Package — Evidence Bundle

This folder contains the machine-readable benchmark and verification
evidence for HEEH-V1(TM) DICOM Viewer v1.0.2. It is the auditable companion
to `docs/VERIFICATION_EVIDENCE.md` and `docs/standards_traceability.md`.

> **Manuscript note (2026-09-28).** The manuscript sources, tables, and
> title page are **not included** in this public package. They are kept
> private by the author pending journal submission. Their absence does not
> affect the evidence artifacts listed below.

> **Public test result.** The recorded Windows run for this snapshot reported
> 320 passed and 4 skipped tests. Skips require optional licensed reference
> assets or benchmark inputs not included in the public package. Pytest
> reports a reason for each skip.

## Included

- `02_Evidence/` — canonical, machine-readable benchmark artifacts:
  - heeh_v1_public_benchmark_results.json (regenerated 2026-09-27, v1.0.2)
  - public_benchmark_report.md (regenerated 2026-09-27)
  - pyradiomics_comparison.json (matched first-order, tolerance 1e-6, max error 0.0)
  - ibsi_configuration_d_verification.json (Z-Rad reference pipeline, 270/270)
  - Scientific Benchmark Dossier.md, final_benchmark_summary.md
- `benchmark_source/public_benchmark_evidence.py` — regenerates the synthetic
  CT phantom, generated archive-fixture, and navigation-cache measurements.
  It does not regenerate the separately recorded PyRadiomics or IBSI
  reference-comparison artifacts.

## What the measured evidence is (and is not)

Measured in this environment and recorded in the JSON artifacts:
- Radiomics on the synthetic ACR-style water ROI passes its pre-specified
  tolerances (mean -0.04 HU, std 10.02 HU vs targets 0.00 ± 3.00 / 10.00 ± 2.00).
- PyRadiomics v3.0.1 matched first-order comparison on the same ROI:
  all absolute errors 0.0 at the declared 1e-6 tolerance.
- IBSI Configuration D: 270/270 populated reference rows passed in the
  configured Z-Rad reference pipeline. This result does not certify the
  application's separate radiomics implementation or full IBSI compliance.
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

## Reproducing selected measurements

From the repository root, run the script in the project environment:

```powershell
.\.venv\Scripts\python.exe `
 verification\publication_package\benchmark_source\public_benchmark_evidence.py
```

The script writes a JSON result under `results/` and a Markdown report under
`docs/`; it does not overwrite the checked-in evidence files. Its output
covers the synthetic phantom, generated archive fixtures, and the fixed
navigation-cache workload. Reproducing the PyRadiomics and IBSI reference
comparisons requires their separately documented software and reference
inputs. Licensed data are not redistributed in this package.

The JSON artifacts record environment details, script fingerprints, and
input fingerprints where available. The benchmark workspace did not provide
Git metadata, so its source revision is recorded as unavailable; the
reported package version does not identify an exact source revision.

The test result and benchmark measurements are separate evidence types.
Neither establishes clinical accuracy, privacy effectiveness, regulatory
compliance, or generalizability.
