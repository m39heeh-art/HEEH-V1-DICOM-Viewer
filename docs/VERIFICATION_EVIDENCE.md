# Verification evidence for release v1.0.2

This document summarizes the verification evidence published with HEEH-V1
DICOM Viewer v1.0.2. It distinguishes automated software tests from
reference comparisons and states what each result does not establish.

## Release identity and reproducibility

- **Version:** 1.0.2
- **Release tag:** [`v1.0.2`](https://github.com/m39heeh-art/HEEH-V1-DICOM-Viewer/releases/tag/v1.0.2)
- **Release commit:** `9042e58750425a5d6960ec27eada6adf891c957e`
- **Zenodo record:** <https://zenodo.org/records/23020151>
- **Citable version-family DOI:** [10.5281/zenodo.22768910](https://doi.org/10.5281/zenodo.22768910)
- **License:** MIT
- **Citation metadata:** `CITATION.cff`
- **File integrity:** `SHA256SUMS.txt` lists SHA-256 hashes for packaged files

The benchmark artifacts record their inputs, parameters, dependencies, and
limitations. The public package does not include licensed IBSI reference
datasets. Follow `../verification/README_DATA.md` to obtain optional
reference data from its source and under its terms.

The version-specific Zenodo record archives the tagged release commit above.
Subsequent documentation-only updates on the publication branch are not part
of that archived file.

Zenodo assigned version DOI `10.5281/zenodo.23020151`, but DOI.org and
DataCite returned 404 at the latest check. Use the resolvable family DOI
above until the version DOI resolves. The earlier duplicate DOI
`10.5281/zenodo.23015732` is not the identifier for this record.

## Automated verification

The GitHub Actions run for the release commit passed on Python 3.11 and 3.12.
The workflow completed its dependency, compilation, Ruff, test, and Docker
smoke-test jobs successfully.

On Windows, the release snapshot collected 324 tests: 320 passed and 4 were
skipped. Those skips require optional licensed IBSI reference data or recorded
benchmark data that the public package does not include. The test run also
reported two non-failing floating-point precision warnings for a nearly
constant synthetic color fixture.

These tests exercise the documented fixtures and code paths. They do not
establish clinical accuracy, safety, privacy, or regulatory compliance.

## Quantitative benchmark results

The public evidence bundle in
`../verification/publication_package/02_Evidence/` contains the source
reports and machine-readable results. The reported measurements are limited
to these protocols:

| Evaluation | Reported result | Interpretation |
|---|---|---|
| Synthetic CT water ROI | Mean `-0.04 HU`; standard deviation `10.02 HU` | Compared with prespecified phantom targets; synthetic data only |
| Matched PyRadiomics 3.0.1 first-order comparison | Four values; maximum absolute error `0.0` at tolerance `1e-6` | One deterministic synthetic ROI; no other feature families or patient data |
| IBSI Configuration D CT phantom comparison | 270 of 270 populated reference rows passed using the configured Z-Rad pipeline | One reference configuration; not full IBSI compliance |
| Separate PyRadiomics reference-table comparison | 58 of 66 comparable rows passed, 8 failed, and 204 unsupported | Separate from the Z-Rad comparison; unsupported rows are not passes |
| Generated archive challenge fixtures | 20 valid and 20 invalid fixtures classified correctly | Constructed test fixtures; not real-world sensitivity or specificity |
| Navigation-cache microbenchmark | Mean elapsed time `0.003887 s`; mean Python allocation peak `0.030 MB` | Synthetic cache workload using `tracemalloc`; not end-to-end runtime or process memory |

The CT-Phantom4Radiomics collection appears only in the metadata-level
provenance record. Its image archive was not downloaded or used for image-level
evaluation.

## DICOM Structured Report check

The evidence package records an independent `dicom-validator` check of a
generated Structured Report (SR) fixture. It reports zero actionable errors
after review of a residual validator flag. This result applies only to the
tested object and validator configuration. It does not establish compatibility
with every DICOM consumer, PACS, or SR content combination.

## Scope and non-claims

The evidence does not establish:

- Clinical accuracy, diagnostic utility, or patient-level validity
- Full IBSI Phase 1 or Phase 2 compliance
- Real-world de-identification effectiveness or anonymity
- Generalizability across institutions, scanners, populations, or modalities
- Superiority to established imaging platforms
- Formal DICOM, IHE, HIPAA, GDPR, ISO, or medical-device certification

Use the release evidence only within the stated protocols. For standards
boundaries and further detail, see `standards_traceability.md`,
`global_standards_baseline.md`, and `ibsi_ct_subset.md`.
