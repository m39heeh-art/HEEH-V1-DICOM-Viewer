# HEEH-V1 DICOM Viewer 1.0.2

HEEH-V1 is research and education software for medical-image viewing,
measurement, exploratory analysis, and structured reporting. It is not a
medical device and is not validated for patient care.

## Release identity

This release is identified as version `1.0.2` in its package metadata and by
the [`v1.0.2` GitHub release](https://github.com/m39heeh-art/HEEH-V1-DICOM-Viewer/releases/tag/v1.0.2).

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

The version-specific v1.0.2 record is
[10.5281/zenodo.23015732](https://doi.org/10.5281/zenodo.23015732). Its
version-family record is
[10.5281/zenodo.22768910](https://doi.org/10.5281/zenodo.22768910).
The version-specific record identifies the GitHub `v1.0.2` tag at commit
`9042e58750425a5d6960ec27eada6adf891c957e`. Documentation changes made
after that tagged archive are present on the publication branch but are not
part of the Zenodo v1.0.2 file.

## Verification

The release snapshot collected 324 tests. The recorded Windows run reported
320 passed and 4 skipped; the skipped tests require optional licensed
reference or benchmark data not included in the public package. The
GitHub Actions run for this release passed on Python 3.11 and 3.12, including
dependency, compilation, Ruff, test, and Docker smoke-test jobs.

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

`SHA256SUMS.txt` lists SHA-256 hashes for the packaged files. On Unix-like
systems, verify them with `sha256sum -c SHA256SUMS.txt`; on Windows, compare
the listed values with `Get-FileHash`.
