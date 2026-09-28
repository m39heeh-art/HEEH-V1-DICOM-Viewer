# HEEH-V1(TM) DICOM Viewer v1.0.2 — Release Notes (rev 6b)

Research and education software for DICOM measurement, tissue analysis,
radiomics, and structured reporting. **Not a medical device.**

## What's in this revision

- Application: Streamlit app (`app.py`) + `core/`, `engines/`, `utils/`, `ui/`
- Verification: **324 tests, all passing (run twice)**, including the
  PACS-ingestion conformance suite, ComBat harmonization ground-truth and
  integration tests, TCIA removal-flow tests, and viewer regression locks;
  the first run from a fresh extraction passes as-is
- Publication package reconciled: manuscript sources, tables, and title page
  rewritten against the canonical measured evidence; benchmark JSON/report
  regenerated at v1.0.2; Word files regenerated from the reconciled sources
- Evidence: `docs/VERIFICATION_EVIDENCE.md` (accuracy & standards trail,
  Part 4 items 1-16), `docs/standards_traceability.md` (conformance matrix)

## Changes since rev 5

- Viewer: "Fit to panel" mode removed; modes are 1:1 pixels (default), 2x,
  4x — one unified source-pixel click mapping; legacy sessions migrate.
- Kurtosis: verified against the IBSI reference table's own convention
  ("(Excess) kurtosis" = Fisher/excess); locked by tests, no code change.
- ComBat batch harmonization (empirical-Bayes, Johnson 2007): opt-in for the
  cohort metrics CSV, batch = acquisition modality, per-row disclosure
  (`combat_batch` / `combat_applied` / `combat_details`); undefined cases
  refuse explicitly and ship raw statistics with the reason.
- TCIA: de-selecting a "Series to download" group and re-submitting now
  removes it from the interface; re-adding the same group no longer
  duplicates images (UID-level selection dedup + resolved-path dedup).
- pydicom floor corrected to >=3.0 in requirements.txt and pyproject.toml;
  launcher version banners corrected to 1.0.2 (app.bat, launch.ps1).
- First-run test failure after extraction root-caused (pytest basetemp
  parents) and fixed via a shipped root conftest.py; the earlier
  antivirus-lock attribution was disproved and retracted.

## Changes since rev 6

- Disclosure text corrected: the radiomics caption no longer claims Fisher
  (excess) kurtosis "differs from IBSI kurtosis by a constant -3" (false -
  the IBSI reference values are themselves "(Excess) kurtosis"); it now
  states the convention matches the IBSI reference and attributes
  non-comparability to the whole-image basis, absent ROI mask, and missing
  resampling/re-segmentation ("not IBSI Configuration-D comparable").
  `docs/standards_traceability.md` aligned. Text-only change; 324 tests
  green twice, ruff clean.
- Evidence doc gains Part 4 item 16 documenting the correction.

## Quick start

```
python -m pip install -r requirements.lock
pip install -e .
python -m pytest verification/tests -q   # expected: 324 passed, first run
streamlit run app.py
```

## Optional bulk data (not shipped)

No third-party validation data ship with this release. The test suite
passes without them; the IBSI phantom tests skip automatically when the
licensed data are absent. See `verification/README_DATA.md` for the exact
fetch commands and the required directory layout.

## Integrity

`SHA256SUMS.txt` lists the SHA-256 of every packaged file. Verify with:
`sha256sum -c SHA256SUMS.txt` (or `Get-FileHash` on Windows).
