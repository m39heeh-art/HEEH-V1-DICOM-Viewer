# HEEH-V1 DICOM Viewer 1.0.2

HEEH-V1 is research and education software for medical-image viewing,
measurement, exploratory analysis, and structured reporting. It is not a
medical device and is not validated for patient care.

## Release identity

This package is identified as version `1.0.2` in its package metadata.

The repository's `v1.0.1` tag was reassigned to a commit whose package
metadata identifies version `1.1.1`, at the author's request. The `v1.1.1`
tag was removed. The `v1.0.1` tag is therefore a legacy alias, not a
version-matched `1.0.1` package. Do not infer a package version from that tag
name.

## Included

- Streamlit application with DICOM, selected volumetric-image, measurement,
  analysis, and export workflows.
- Selected DICOM ingestion, export, and Structured Report tests; TCIA download
  flow fixes; cohort ComBat harmonization; and viewer regression fixes.
- Research evidence and limits in `docs/VERIFICATION_EVIDENCE.md`,
  `docs/standards_traceability.md`, and
  `verification/publication_package/02_Evidence/`.
- Citation metadata in `CITATION.cff`.

## Zenodo archive

The v1.0.2 Zenodo record is available at
<https://zenodo.org/records/23020151>. Its assigned version DOI,
[10.5281/zenodo.23020151](https://doi.org/10.5281/zenodo.23020151), identifies
the record; cite the version-family DOI,
[10.5281/zenodo.22768910](https://doi.org/10.5281/zenodo.22768910), when
referring to all software versions. `CITATION.cff` records the version DOI,
while `.zenodo.json` identifies the family DOI in its `isVersionOf`
relation. The revised upload archive retains the requested version label
`1.0.2` and contains code, documentation, tests, and evidence updated after
the original base commit `9042e58750425a5d6960ec27eada6adf891c957e`; it is not
byte-identical to that historical Git snapshot. The version label and DOI
have not been changed.

## Verification

The original release snapshot collected 324 tests. The recorded Windows run
reported 320 passed and 4 skipped; those skips required optional licensed
reference or benchmark data not included in that snapshot. The GitHub Actions
run for that base commit passed on Python 3.11 and 3.12, including dependency,
compilation, Ruff, test, and Docker smoke-test jobs. The revised upload
package was separately checked locally: 335 passed, 0 failed, 0 skipped.

See `docs/VERIFICATION_EVIDENCE.md` for the scope and limitations of the
automated tests and quantitative benchmarks. Passing tests do not establish
clinical accuracy, privacy effectiveness, standards certification, or
generalizability.

## Install and run

```powershell
python -m pip install -r requirements.lock
python -m pip install -e .
python -m pytest verification/tests -q
streamlit run app.py
```

Optional validation data are not distributed with this release. See
`verification/README_DATA.md` for acquisition instructions and licensing
information. Some tests skip when required optional data or dependencies are
unavailable.

## Integrity

`SHA256SUMS.txt` covers files in the current repository snapshot, excluding
the manifest itself; it is not a checksum list for the immutable Zenodo
archive. Verify with `sha256sum -c SHA256SUMS.txt` or
`python scripts/generate_sha256_manifest.py --check`. Regenerate after
repository-file changes with `python scripts/generate_sha256_manifest.py`.
