# Input data provenance — TCIA CT-Phantom4Radiomics

This use case analyzes a **public, citable dataset** obtained from The Cancer
Imaging Archive (TCIA) and already cached locally by the v1.0.2 real-data
study. No bulk image data are committed to this repository.

## Dataset identity

| Field | Value |
| --- | --- |
| Collection | `CT-Phantom4Radiomics` |
| License | CC BY 4.0 (<https://creativecommons.org/licenses/by/4.0/> ) |
| Data DOI | <https://doi.org/10.7937/a1v1-rc66> |
| SeriesInstanceUID | `1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879` |
| StudyInstanceUID | `1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971` |
| Download method | NBIA API v4 `getImage` (real archive; 173 ZIP entries: LICENSE + 172 DICOM slices) |

The collection is a task-based anthropomorphic CT phantom scan published for
research use (as recorded by the prior project study). No human-subject
identifiable data are stored in this repository.

## Local cache and fingerprint verification

- Cached archive: `verification/data/tcia_real_evaluation/series.zip`
  (unextracted DICOM slices in `verification/data/tcia_real_evaluation/dcm/`).
- Verified SHA-256 of the cached archive:
  `579233ebf30ce41985ad6971f150bf6e56a94a3944af6ee123737896b7590f17`
- Reported download SHA-256 (from the archived project study):
  `579233ebf30ce41985ad6971f150bf6e56a94a3944af6ee123737896b7590f17`
- **Result: the cached bytes are byte-identical to the verified download
  (fingerprint match confirmed by `research_case/scripts/run_small_roi_robustness.py`
  before analysis; see `inputs/data_provenance.json` for the refreshed record).**
- Aggregate SHA-256 over the 172 sorted slice files, entity counts, and the
  loaded volume geometry (172 x 512 x 512, in-plane spacing 0.68359375 mm,
  slice spacing 2.0 mm, HU range −1024…919) are recorded automatically in
  `inputs/data_provenance.json` on each run.

## Re-downloading the series

If the cache is absent, re-fetch the series by the NBIA UID recorded above and
in `scripts/tcia_real_evaluation.py` (which documents the exact API call, the
44,282,129-byte archive size, and its SHA-256). Then re-run
`python research_case/scripts/run_small_roi_robustness.py`; the script refuses
nothing silently — it recomputes and re-records the fingerprint, and the README
quote of `cached_zip_matches_recorded_download` must be `true`.

## Privacy statement

The phantom series contains no named human subjects; the images are published
under CC BY 4.0. Derived figure PNGs and result JSON/CSV in this directory are
research outputs computed from the phantom pixels only.
