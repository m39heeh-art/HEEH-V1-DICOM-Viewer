# Standards Traceability Matrix — HEEH-V1 DICOM Research Toolkit

**Scope:** every calculation, input, and output that participates in a research result, mapped to the standard it follows, with verification status.
**Companion documents:** `NeuoroProject_Error_Notes.md` (fix log) · `docs/standards_traceability.md` (this file, in-repo copy)
**Verification basis:** project test suite (272/272), independent `dicom-validator` (DICOM edition **2026d**) validation of exported SRs, and functional round-trip tests run 2026-09-26.

---

## 1. Inputs

| Input | Standard / clause | Status | Verification |
|---|---|---|---|
| DICOM files | PS3.5/PS3.10; TransferSyntaxUID required; pixel decoding errors rejected, not guessed | ✅ Conformant | `process_dicom` rejection paths; suite |
| CT stored values → HU | PS3.3 C.7.6.2.1.1 formula `HU = pixel × RescaleSlope + RescaleIntercept` | ✅ Conformant | Synthetic-CT round trip (mean 975.5 vs 976 expected) |
| PixelPaddingValue/RangeLimit | PS3.3 C.7.6.2 padding semantics; padding excluded from statistics | ✅ Conformant | `process_dicom` padding paths; suite |
| Non-CT modalities | Signal intensity preserved; no HU mapping applied | ✅ Conformant | Modality calculator tests |
| MONOCHROME1 | PS3.3 C.7.6.2.1.1-1; inversion display-only; analysis consumes raw stored values | ✅ Conformant | Code + suite |
| PixelSpacing (row/column) | PS3.3 C.7.6.2.1.1: row spacing → y, column spacing → x; first pixel **center** = origin | ✅ Conformant | Anisotropic distance test; hover readout fixed |
| NIfTI scl_slope/scl_inter | NIfTI-1 scaling semantics applied on load | ✅ Conformant | Loader tests |
| CT HU physiological range | Values outside valid HU band rejected (`INTEGRITY_HALT`) | ✅ Conformant | Negative test (fixture rejected as designed) |
| Manual mm/pixel calibration | Labelled `calib_source: manual`; must be phantom-derived (AAPM guidance) | ✅ Disclosed | Per-measurement provenance fields |

## 2. Calculations

| Calculation | Standard | Status | Verification |
|---|---|---|---|
| Distance measurement | Euclidean on source pixel indices; per-axis spacing scaling | ✅ Conformant | Unit tests (3-4-5, anisotropic 20 mm) |
| Angle measurement | Arccos of normalized dot product; `clip(±1)` NaN guard; mm-space when calibrated | ✅ Conformant | Unit tests (90°, 45°) |
| Line profile | Bresenham raster walk; non-finite exclusion counted | ✅ Conformant | Unit tests incl. NaN exclusion |
| CT windowing (display only) | PS3.3 C.11.2.1.2.1 LINEAR exact: `center−0.5`, `width−1`, width=1 threshold | ✅ Conformant | Boundary unit tests (0/128/255) |
| First-order statistics | Sample SD (ddof=1) disclosed via `std_ddof` column; slice-selection rule disclosed per row | ✅ Conformant + disclosed | Cohort CSV synthetic-CT test |
| Radiomics (default path) | Whole-image, native voxel space: no resampling, no ROI re-segmentation; entropy discretized (declared scheme, recorded in provenance); kurtosis in Fisher (excess) convention (matches the IBSI reference values' own "(Excess) kurtosis" definition) — **disclosed as NOT Configuration-D comparable** in UI/manifest | ⚠️ Non-conformant by design, precisely disclosed | UI caption + manifest + `test_application_radiomics_is_reported_as_not_configuration_d_comparable` |
| AI engines (ViT / ONNX / MONAI) | Inference discipline: eval + frozen weights, `torch.inference_mode()`, ONNX input-contract validation, deterministic-training controls, XAI per-patch rollout reduction | ✅ Line-by-line audited 2026-09-27; 8 findings fixed; 5 regression tests (`test_ai_engines.py`) |
| Kurtosis convention | IBSI reference values define kurtosis as **(Excess) kurtosis** (Fisher; moment − 3) | ✅ Locked: extractor equals scipy `fisher=True` to 5e-4 and the shipped config-D phantom comparison (270/270, incl. `stat_kurt` 4.35, `ih_kurt` 4.31) verifies it (`test_harmonization_kurtosis.py`) |
| Cohort batch harmonization (opt-in) | Empirical-Bayes ComBat (Johnson 2007, sva/neuroCombat formulation) with covariate preservation and explicit per-row disclosure or refusal | ✅ Ground-truth tests: known batch location/scale removed, covariate effects preserved (equal to the OLS estimate), reference-batch mode passes the reference through; refusals explicit, never silent (`core/harmonization.py`, `test_harmonization_kurtosis.py`, `test_cohort_combat_export.py`) |
| Running interface (all sidebar tools) | Runtime value verification against analytic references via `streamlit.testing.v1.AppTest` | ✅ 14/14 checks passed (tissue 6.25/6.25/87.5%, radiomics = CTCalculator = 56.25 HU) |
| Radiomics (IBSI path) | IBSI Configuration D via PyRadiomics reference; NGTDM cross-checked to 1e-6 | ✅ Conformant (use this path for publication) | `test_ngtdm_matches_pyradiomics…` **PASSED**; IBSI phantom test **PASSED** |
| Voxel 95% CI | Labelled "naive voxel-independence"; not a patient-level CI | ⚠️ Disclosed limitation | UI help text |

## 3. Outputs

| Output | Standard | Status | Verification |
|---|---|---|---|
| DICOM SR (TID 1500/1501/300/320, Comprehensive SR IOD) | PS3.16 TID structure; C.18.4 Image Reference Macro (refs in `ReferencedSOPSequence`); Type-2 attributes present-but-empty; UTC + `TimezoneOffsetFromUTC` (C.12.1.1.1) | ✅ Conformant | **Independent validator `dicom-validator` 0.9.0, edition 2026d: 0 actionable errors** (17 → 1 benign residual, a validator false-positive on top-level `ValueType` — tree walk proved all items carry it) |
| Angles in SR | TID 121207 "Angle" with two POLYLINE SCOORDs; 0° encoded honestly | ✅ Conformant | Round-trip: Angle 30° and 0° parse back |
| UCUM units | `mm`, `cm`, `px`, `deg` code schemes in SR + CSV + JSON | ✅ Conformant | Round-trip tests |
| CSV | RFC 4180, UTF-8 BOM, explicit calibration provenance columns | ✅ Conformant | Cohort CSV test |
| JSON | RFC 8259 | ✅ Conformant | Manifest parse |
| XLSX | Office Open XML via openpyxl | ✅ Conformant | Excel export tests |
| Export manifest | SHA-256 per file; **dependencies + platform**; **reproducibility block** (seeding, deterministic algorithms, UTC basis, calibration); **analysis_parameters block** (HU basis, windowing, distance/angle formulas, statistics) | ✅ Conformant | E2E manifest test (pydicom 3.0.2, numpy 2.4.6, torch 2.5.1+cu121 recorded) |
| ZIP archives | Size-bomb limits, path-traversal rejection, post-build re-validation | ✅ Conformant | `validate_export_archive` tests |
| Anonymized DICOM | `PatientIdentityRemoved=YES` + method; Type-2 attrs emptied, not deleted | ✅ Conformant, review required | Privacy tests; external review still mandated |
| PNG composites | Measurement metadata embedded; UCUM-tagged | ✅ Conformant | Composite round-trip tests |
| Exported DICOM objects (ingestability) | PS3.10 file format + PS3.7 file meta (Group Length, MediaStorageSOP* ↔ SOP*, declared = used transfer syntax); lossless round-trip through the toolkit's own TID 1500 parser, measurement re-import, and loaders | ✅ Conformant | 17-test PACS-ingestion suite (`test_pacs_ingestion.py`); dicom-validator re-run: 0 actionable errors |

## 4. Reproducibility (new)

| Control | Implementation | Verification |
|---|---|---|
| RNG seeding | Python `random`, NumPy, PyTorch (incl. CUDA) seeded at session start | `apply_reproducibility()` smoke test: `{'numpy': True, 'torch': True}` |
| Deterministic algorithms | `torch.use_deterministic_algorithms(True, warn_only=True)` | Same test |
| Environment capture | Dependency versions + OS platform recorded in every export manifest | E2E manifest test |
| Module | `core/reproducibility.py` (single source of truth) | Syntax + runtime check |

## 5. Known boundaries (honest limits — do not overclaim)

1. **Not a medical device** — IEC 62304 / ISO 13485 / ISO 14971 out of scope by declared purpose; no clinical certification is claimed or implied.
2. **HIPAA/GDPR** — de-identification is DICOM-PS3.15-style curation; the manifest itself states no certification and mandates external privacy review before release (burned-in annotations, no date-shift).
3. **PACS interoperability** — every emitted object is proven re-ingestible at the PS3.10/PS3.7 file-format level and round-trips losslessly through the toolkit's own parsers (17-test suite, 2026-09-27); what remains untested is a live network-level Association (C-STORE/C-FIND against a real PACS), which requires a connection to one.
4. **Default radiomics path** — not IBSI-compliant (disclosed); use `run_configuration_d` for published values.
5. **Voxel-level CI** — never report as patient-level inference.
6. **dicom-validator residual** — 1 benign "ValueType missing" flag remains, traced to a validator module-level check (false positive; all content items verified to carry `ValueType`).

## 6. Verification log (2026-09-26)

- `pytest verification/tests -q` → **272 passed, 0 failed, 0 skipped** (incl. pyradiomics cross-validation after the DLL policy stopped blocking it)
- `dicom_validator.validate_iods` (edition 2026d) on app-generated Comprehensive SR → **Errors: 0 actionable** (17 initial → fixed: Type-2 attributes, image-reference macro, root-item placement, root `RelationshipType`)
- Functional SR round-trip (angle + distance) → PASS
- Synthetic-CT cohort CSV round-trip → PASS (mean 975.5 HU vs 976 theory)
- Manifest provenance test → PASS

## 7. Verification log addendum (2026-09-27 — rectification round)

- Dependency-declaration rectification: pydicom floor `>=2.4` → `>=3.0` in `requirements.txt` and `pyproject.toml` (code requires pydicom 3.x APIs); import-tree sweep found no other declaration gaps
- `pytest verification/tests -q` → **297 passed, 0 failed, 0 skipped** (twice; 280 baseline + 17 new `test_pacs_ingestion.py`)
- `ruff check .` → clean
- `dicom_validator.validate_iods` (edition 2026d) on freshly regenerated Comprehensive SR → **0 actionable errors**; residual re-disproved by tree walk (15/15 content items carry `ValueType`; flag targets the document root)
- First-run-after-extraction failure root-caused: pytest `--basetemp=cache_logs/pytest_tmp` is created without parents, so fresh packages failed 42 `tmp_path` tests deterministically (earlier antivirus attribution disproved by controlled experiment); fixed by root `conftest.py` creating the parent — first run from a pristine extraction now passes 297/297
