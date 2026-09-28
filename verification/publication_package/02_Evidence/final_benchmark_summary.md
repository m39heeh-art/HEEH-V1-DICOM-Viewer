# Final benchmark summary for HEEH-V1

## Scope and constraints
This benchmark package was generated under strict evidence rules:
- public data only,
- no fabricated results,
- no clinical superiority claim without labels and a prespecified comparator,
- no release-claim change for v1.0.1,
- new development benchmark outputs only.

## What was measured

1. Radiomics benchmark on a reproducible synthetic CT phantom ROI.
2. Export/privacy validation benchmark using generated valid/invalid challenge fixtures.
3. Synthetic navigation-cache microbenchmark using repeated runs. It measures
   Python allocations with `tracemalloc`, not process memory or end-to-end
   image-processing performance.
4. Public dataset provenance from TCIA/NBIA metadata.

## Public provenance
- Collection: CT-Phantom4Radiomics
- SeriesInstanceUID: 1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879
- StudyInstanceUID: 1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971
- License: Creative Commons Attribution 4.0 International License
- License URL: https://creativecommons.org/licenses/by/4.0/
- DataDescriptionURI: https://doi.org/10.7937/a1v1-rc66
- Download status: metadata_only; the archive was not downloaded in this environment.

## Measured results

The current generated measurements are in `docs/public_benchmark_report.md`;
the machine-readable result is
`verification/results/heeh_v1_public_benchmark_results.json`. Treat those
artifacts as the single source of run-specific values. Earlier copies of
benchmark values are intentionally not repeated here because they came from
different runs and the runtime/memory workload was previously easy to
over-interpret.

The export validator's 20/20 and 20/20 results are counts on generated
challenge fixtures only. They are not real-world sensitivity/specificity
estimates. The allocation measurement does not include native-library
allocations, process RSS, image decoding, model inference, or complete
application workloads.

## Reference comparison and limits

- PyRadiomics 3.0.1 was rerun in WSL on a deterministic synthetic ROI; four
  first-order values matched within the specified `1e-6` tolerance. See
  `verification/results/pyradiomics_comparison.json`.
- All 270 populated IBSI Configuration D rows passed using the configured
  Z-Rad reference pipeline. The separate PyRadiomics reference extraction
  comparison reports 58/66 comparable rows passing, 8 failing, and 204
  unsupported. The default viewer's 2D unmasked slice path is non-comparable
  to Configuration D and has no pass/fail result. See
  `verification/results/ibsi_configuration_d_verification.json`.
- Full IBSI Phase 1/2 compliance, image-level benchmarking on
  CT-Phantom4Radiomics, and clinical/generalizability studies remain
  unperformed.

## Evidence artifacts
- JSON results: results/heeh_v1_public_benchmark_results.json
- Human report: docs/public_benchmark_report.md
- Supporting code: scripts/public_benchmark_evidence.py
- Focused validation tests: tests/test_public_benchmark_evidence.py

## Validation status
Focused benchmark validation passed:
- 16 passed in 8.55s

The current project test-suite status is reported by the CI run for the
corresponding source revision.

## Limitation statement
These are reproducible research/engineering measurements only. They do not establish clinical accuracy, regulatory compliance, or superiority over any external comparator. They are valid only within the explicit benchmark protocol and public provenance recorded above.
