# Pull request checklist

Thank you for contributing to HEEH-V1(TM) DICOM Viewer. Please confirm:

## Code
- [ ] The change is scoped to one clear purpose.
- [ ] `python -m pytest -q` passes locally.
- [ ] `python -m ruff check .` passes.
- [ ] `python -m pip check` passes.
- [ ] If file contents changed, `scripts/generate_sha256_manifest.py` was
      re-run so `SHA256SUMS.txt` matches (CI verifies this).
- [ ] Text files use the repository CRLF convention (`.gitattributes`).

## Evidence wording
- [ ] Any new capability uses the project's evidence labels
      (Implemented / Tested / Independently validated / Not established).
- [ ] No claim of clinical accuracy, full IBSI compliance, regulatory
      certification, or anonymization is introduced.
- [ ] New measured numbers are traceable to a script, input, configuration,
      and stored output.

## Documentation
- [ ] README/docs updated where behavior or boundaries changed.
- [ ] No patient data, secrets, or large binaries are added.
