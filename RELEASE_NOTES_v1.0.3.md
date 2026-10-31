# HEEH-V1 DICOM Viewer 1.0.3

HEEH-V1 is research and education software for medical-image viewing,
measurement, exploratory analysis, and structured reporting. It is not a
medical device and is not validated for patient care.

## Release identity

The package and application version is `1.0.3`. This source release has not
yet been assigned a version-specific Zenodo record or DOI. Until one is
assigned, cite the version-family DOI
[10.5281/zenodo.22768910](https://doi.org/10.5281/zenodo.22768910).
The existing [Zenodo v1.0.2 record](https://zenodo.org/records/23020151)
remains the record for that earlier version.

## Changes

- Extended the independent PyRadiomics comparison on the IBSI Configuration D
  phantom from 66 to 75 directly comparable feature rows; all 75 passed.
- Added per-row assessment statuses and categorized reasons for the 195
  reference rows that remain not assessed. These are not treated as passes or
  failures.
- Updated the corresponding validation evidence and regression tests.

## Verification

The targeted IBSI validation module passed: 30 tests passed. Ruff passed for
the updated verifier and tests. The 75 PyRadiomics comparisons are limited to
the pinned IBSI CT phantom and the stated Configuration D processing profile;
they do not establish full IBSI conformance, clinical accuracy, or
generalizability.
