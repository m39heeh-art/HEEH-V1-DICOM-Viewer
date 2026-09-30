# Verification evidence for release v1.0.2

This document summarizes the verification evidence published with HEEH-V1
DICOM Viewer v1.0.2. It distinguishes automated software tests from
reference comparisons and states what each result does not establish.

## Release identity and reproducibility

- **Version:** 1.0.2
- **Release tag:** [`v1.0.2`](https://github.com/m39heeh-art/HEEH-V1-DICOM-Viewer/releases/tag/v1.0.2)
- **Release commit:** `9042e58750425a5d6960ec27eada6adf891c957e`
- **Zenodo record:** <https://zenodo.org/records/23020151>
- **Version DOI:** [10.5281/zenodo.23020151](https://doi.org/10.5281/zenodo.23020151) (resolves to this record as of 2026-09-28)
- **Version-family DOI:** [10.5281/zenodo.22768910](https://doi.org/10.5281/zenodo.22768910) (use when referring to all software versions)
- **License:** MIT
- **Citation metadata:** `CITATION.cff`
- **File integrity:** `SHA256SUMS.txt` hashes files in the current repository snapshot, not the immutable Zenodo archive

The benchmark artifacts record their inputs, parameters, dependencies, and
limitations. The public package does not include licensed IBSI reference
datasets. Follow `../verification/README_DATA.md` to obtain optional
reference data from its source and under its terms.

The version-specific Zenodo record archives the tagged release commit above.
Subsequent documentation-only updates on the publication branch are not part
of that archived file.

Zenodo assigned version DOI `10.5281/zenodo.23020151`; it resolves to this
record as of 2026-09-28. Use the version-family DOI above when citing the
software across all versions. `CITATION.cff` records the version DOI;
`.zenodo.json` records the family DOI as the `isVersionOf` relation. The
earlier duplicate DOI
`10.5281/zenodo.23015732` is not the identifier for this record.

The SHA-256 manifest is maintained for this repository snapshot, including
post-tag documentation and evidence updates. It is not a replacement for
checksums accompanying the immutable Zenodo archive. Run
`python scripts/generate_sha256_manifest.py --check` to verify it.

## Automated verification

The GitHub Actions run for the release commit passed on Python 3.11 and 3.12.
The workflow completed its dependency, compilation, Ruff, test, and Docker
smoke-test jobs successfully.

The current full suite collects 328 tests: 328 passed and 0 skipped locally
(2026-09-30). The release snapshot had collected 324 tests: 320 passed and 4 were
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

The synthetic and fixture benchmarks use metadata-level provenance for the
CT-Phantom4Radiomics collection. In addition, the exact recorded series was
downloaded (44,282,129 bytes) and evaluated on real image data (see the
full-series study below); the remainder of the collection was not used for image-level
evaluation.

## DICOM Structured Report check

The evidence package records an independent `dicom-validator` check of a
generated Structured Report (SR) fixture. It reports zero actionable errors
after review of a residual validator flag. This result applies only to the
tested object and validator configuration. It does not establish compatibility
with every DICOM consumer, PACS, or SR content combination.

## Real-data full-series study (2026-09-30)

The recorded TCIA series (CT-Phantom4Radiomics; CC BY 4.0;
DOI 10.7937/a1v1-rc66) was downloaded in full via the NBIA API and
evaluated with the application's own loading, radiomics, de-identification,
and export-validation code paths. Artifacts:
`verification/results/tcia_real_evaluation.json` (single-slice protocol) and
`verification/results/tcia_full_series_study.json` (full series), with
human-readable reports under `docs/` and mirrored evidence copies in
`verification/publication_package/02_Evidence/`.

- First-order agreement with PyRadiomics v3.0.1: 172/172 slice ROIs exact
  (max absolute error 0.0 at 1e-6); unchanged across ROI radii 12/18/24/30/36 mm.
- Air-region CT-number calibration: every slice within +/-30 HU of -1000 HU
  (worst-slice deviation 14.39 HU).
- Export/privacy round trips: 172/172 de-identified slices accepted;
  11/11 deterministic manifest-corruption probes rejected.
- Recorded IBSI morphology disagreements (58/66 passing): data-driven
  decomposition shows signed, convention-shaped deviations (volumes
  -3.34% to -3.23%; surface area +8.31%; surface-derived ratios -9.71% to
  +12.00%; PCA -2.83% to +0.45%), while PyRadiomics' internal mesh-vs-voxel
  volume gap on a smooth real 3D ROI is 0.09%. Full reconciliation with the
  official reference segmentation remains out of scope.

These results describe this single public phantom series and geometric
ROIs; they do not establish clinical accuracy or generalizability.

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
