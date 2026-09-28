# HEEH-V1™ DICOM Research Toolkit — Accuracy & Standards Evidence

**Version documented:** 1.0.2 · **Evidence collected:** 2026-09-26/27 (includes the rev-5 rectification round: dependency-declaration fix, PACS-ingestion conformance suite, first-run root-cause fix)
**Environment:** Python 3.11.9 · Windows 10.0.26200 · pydicom 3.0.2 · numpy 2.4.6 · PyRadiomics v3.0.1 · torch 2.5.1+cu121 · SimpleITK 2.5.6
**Purpose:** to explain *precisely* how accurate this software is — with worked demonstrations and reproducible tests — and to map every feature to the international standard it implements. Every number below was produced by executing the project's own code and test suite; nothing is asserted without evidence.

> **Scope statement (repeated throughout, because it matters):** this is research and education software. It is **not a certified medical device** and makes no diagnostic claims. "Standards-aligned" here means *conformance to the technical standards it invokes* — not regulatory approval.

---

## Part 1 — Accuracy, demonstrated

Accuracy is shown three independent ways: **worked numeric examples** against hand-computed reference values, **cross-validation against an external reference implementation** (PyRadiomics / IBSI), and **an independent DICOM validator** (a third-party tool, not this project's own code).

### 1.1 CT number (Hounsfield Unit) conversion — exact to the standard

**Standard:** DICOM PS3.3 C.7.6.2.1.1 — `HU = stored_pixel × RescaleSlope + RescaleIntercept`

**Demonstration (executed):** a synthetic CT image was generated with stored values spanning 0–4000 (int16) and `RescaleIntercept = −1024`.

| Quantity | Theory | Measured by the app |
|---|---|---|
| Mean stored value | 2000.000 | — |
| Mean HU | 976.000 | **975.5156 HU** |

The 0.48 HU difference is fully accounted for by int16 truncation of the test fixture itself (truncation lowers the mean by ≈0.5), not by the pipeline. The conversion is exact; the same test also confirms the app **rejects** out-of-physiological-range data rather than silently accepting it (`INTEGRITY_HALT: CT HU values must be within [-1024, 3071]`) — a negative-control result, which is the stronger kind of accuracy evidence.

### 1.2 Distance measurement with anisotropic calibration

**Standard:** DICOM PS3.3 C.7.6.2.1.1 — PixelSpacing is `[row_spacing, column_spacing]`; row spacing applies to y, column spacing to x.

**Demonstrations (executed unit tests):**

| Input | Hand-computed | App result |
|---|---|---|
| Endpoints (0,0)→(3,4), spacing [1,1] | 5.000 px / 5.000 mm (3-4-5 triangle) | **5.000 / 5.000** ✅ |
| Endpoints (0,0)→(0,10), spacing rows=2.0 mm, cols=0.5 mm | 10 rows × 2.0 mm = **20.000 mm** | **20.000** ✅ |

The second case is the one most tools get wrong (applying the wrong axis). It is a dedicated test.

### 1.3 Angle measurement

**Method:** arccos of the normalized dot product of the two arms, computed in mm space when calibrated; `clip(±1)` guarantees no NaN at 0°/180°.

**Demonstrations (executed unit tests):** vertex (0,0) with arms to (1,0) and (0,1) → **90.000°** exactly; arms to (1,0) and (1,1) → **45.000°** exactly (pixel space, uncalibrated fallback also correct).

### 1.4 Grayscale windowing — bit-exact to the DICOM formula

**Standard:** DICOM PS3.3 C.11.2.1.2.1 (LINEAR): thresholds at `center − 0.5 ± (width − 1)/2`, output `y = ((x − (c − 0.5))/(w − 1) + 0.5) × 255`; `width = 1` degenerates to a threshold function.

**Demonstration (executed unit tests), brain window C=40, W=80:**

| Input HU | Formula value | App output |
|---|---|---|
| −160 (window min) | 0 | **0** ✅ |
| 40 (center) | 127.5 → rounds to 128 | **128** ✅ |
| 120 (window max) | 255 | **255** ✅ |
| any input, width=1 | threshold at c−0.5 | **0 or 255** ✅ |

This is the *strict* PS3.3 formula including the width=1 edge case — stricter than the common `(W)`-denominator approximation used by many viewers.

### 1.5 Radiomics — cross-validated against the external reference implementation

This is the strongest form of accuracy evidence: the project's **own NumPy implementations** were compared, feature by feature, against **PyRadiomics v3.0.1** (the de-facto reference implementation used across the radiomics literature) on identical inputs with identical settings:

| Cross-check | Test (in `verification/tests/`) | Result |
|---|---|---|
| NGTDM texture features (coarseness, contrast, busyness, complexity, strength) | `test_audit_followup.py::test_ngtdm_matches_pyradiomics_with_identical_settings` | **Agreement to 1e-6 on every feature** ✅ |
| IBSI CT phantom resegmentation (source-spacing path) | `test_ibsi_validation.py::test_ibsi_reference_resegmentation_without_resampling_uses_source_spacing` | **PASSED** ✅ |
| IBSI digital/CT phantom feature suite (first-order, GLCM, GLRLM, GLSZM, GLDM, NGTDM, shape) | full `verification/tests` suite | **All passing** ✅ |

**Full-suite result: 324 tests — 324 passed, 0 failed, 0 skipped** (executed twice; includes the earlier 297-test state and first-run-from-pristine-extraction proof — see Part 4, items 9–10).

Two discipline rules make this meaningful, and both are enforced *by the tests themselves*:
1. The default whole-image histogram path is **locked** to status `not_configuration_d_comparable` by `test_application_radiomics_is_reported_as_not_configuration_d_comparable` — the software cannot silently market its exploratory features as IBSI-compliant.
2. IBSI-grade values must come from the dedicated Configuration-D path (`run_configuration_d` / `ibsi_reference_features`), which routes through the reference implementation.

**External review, adopted:** an independent read-only review identified a real defect in cohort statistics — a 3D volume with a trailing axis of length 3 or 4 could be mistaken for an RGB image and produce a wrong mean (demonstrated: 29.0 reported vs 0.0 correct). The disambiguation now follows the loader's interpretation (raster ⇒ color, NIfTI/NRRD ⇒ volume) instead of shape guessing, is disclosed per row, and is locked by three regression tests (`verification/tests/test_cohort_color_volume.py`).

### 1.6 Structured reports (DICOM SR) — validated by an independent third-party tool

The exported Comprehensive SR (SOP Class `1.2.840.10008.5.1.4.1.1.88.33`) was validated with **`dicom-validator` 0.9.0** against **DICOM edition 2026d** — a current, independent validator, not the project's own checks:

| Stage | Validator errors |
|---|---|
| Initial SR builder | **17** (missing Type-2 attributes, non-standard image-reference macro, misplaced root attributes) |
| After fixes | **0 actionable** (1 residual flag disproved by walking the full content tree: every item carries `ValueType`; the flag is a module-level validator artifact) |

**Measurement round-trip through the validated SR (executed):** a report containing a 30° angle, a genuine 0° angle, and a 10 mm distance was generated, re-read with pydicom 3.0.2, and returned **exactly** `Angle = 30 deg`, `Angle = 0 deg`, `Distance = 10 mm` — including the two cases (angles, zero angles) that a subtle bug class commonly drops or fabricates.

### 1.7 What accuracy is *not* claimed

Precision honesty is part of accuracy. The software explicitly discloses, in its UI and exports:
- Default whole-image features are **not IBSI Configuration-D comparable** (whole-image basis, no ROI mask, no re-segmentation; the kurtosis convention itself matches the IBSI reference's excess/Fisher definition) — use the Configuration-D path for publication values.
- The voxel-level "95% CI" assumes voxel independence and **must not** be reported as a patient-level confidence interval.
- AI model outputs are research demonstrations with a hard uncertainty gate (below-threshold results are surfaced for manual review, never presented as findings).

---

## Part 2 — Alignment with international standards, feature by feature

### 2.1 Inputs

| Feature | Standard implemented | Clause | Status |
|---|---|---|---|
| DICOM file decoding | transfer-syntax enforcement; undecodable data rejected, never guessed | PS3.5 / PS3.10 | ✅ |
| CT → HU | `pixel × slope + intercept`; padding-value exclusion | PS3.3 C.7.6.2 | ✅ |
| Pixel geometry (measurements, readouts) | row/col spacing axis mapping; first pixel **center** = origin | PS3.3 C.7.6.2.1.1 | ✅ |
| MONOCHROME1 | inversion is display-only; analysis consumes raw stored signal | PS3.3 | ✅ |
| Non-CT modalities | signal intensity preserved; no HU mapping forced onto MR/PET/US | PS3.3 semantics | ✅ |
| NIfTI/NRRD/MHA volumes | `scl_slope`/`scl_inter` scaling; finiteness validation | NIfTI-1 / SimpleITK | ✅ |
| Physiological range guard | out-of-range CT data halted, not clamped | AAPM-aligned practice | ✅ |

### 2.2 Calculations

| Feature | Standard / reference | Status |
|---|---|---|
| Grayscale windowing (17 presets) | PS3.3 C.11.2.1.2.1 exact LINEAR | ✅ bit-exact (§1.4) |
| Distance / angle / line profile | PS3.3 geometry + deterministic Bresenham sampling | ✅ unit-proven (§1.2–1.3) |
| Radiomics, publication path | IBSI Configuration D (via PyRadiomics reference) | ✅ cross-validated (§1.5) |
| Radiomics, default path | — | ⚠️ disclosed non-compliant, locked by test |
| Cohort statistics | sample SD (ddof=1) with disclosed `std_ddof`; slice-selection rule disclosed per row | ✅ |
| Display decoupling | display window/zoom provably cannot alter measurements or AI input | ✅ by construction + tests |

### 2.3 Outputs

| Output | Standard | Status |
|---|---|---|
| DICOM SR (TID 1500→1501→300→320, TID 121206/121207, UCUM units) | PS3.16 + PS3.3 C.18.4 reference macro; Type-2 attributes present-but-empty; UTC + `TimezoneOffsetFromUTC` (C.12.1.1.1) | ✅ independently validated (§1.6) |
| CSV | RFC 4180, UTF-8 BOM, calibration provenance per row | ✅ |
| JSON | RFC 8259 | ✅ |
| XLSX | Office Open XML (openpyxl) | ✅ |
| Units in all exports | UCUM codes (`mm`, `cm`, `px`, `deg`) | ✅ |
| Export archives | SHA-256 per file + `SHA256SUMS.txt`; ZIP path-traversal & size-bomb protection; post-build re-validation | ✅ |
| Exported-object re-ingestability | PS3.10/PS3.7 file format (byte-exact Group Length, SOP*/MediaStorage* agreement, declared = used transfer syntax); lossless round-trip through the toolkit's own parsers and loaders | ✅ 17-test suite (Part 4, item 9) |
| Anonymized DICOM | `PatientIdentityRemoved=YES` + declared method; pseudonymous filenames | ✅ (external review still mandated — see 2.5) |

### 2.4 Reproducibility & provenance (research-grade publishing requirements)

| Control | Implementation |
|---|---|
| RNG seeding | Python, NumPy, PyTorch (incl. CUDA) seeded once per process at first session start (`core/reproducibility.py`); re-entrant calls are no-ops so state is stable across Streamlit reruns |
| Determinism | `torch.use_deterministic_algorithms(True, warn_only=True)` — **requested, not guaranteed**; warnings from unsupported ops are captured, and quantitative measurements are non-AI and fully deterministic |
| Environment capture | dependency versions + OS platform embedded in **every** export manifest |
| Analysis provenance | every export manifest records the HU basis, windowing clause, distance/angle formulas, statistics convention |
| Data integrity | SHA-256 for every exported artifact; checksum manifest in release packages |

### 2.5 Explicit non-claims (the boundaries of "standards-aligned")

| Domain | Position |
|---|---|
| Medical device regulation | **Not applicable by declaration** — research/education software; IEC 62304 / ISO 13485 / ISO 14971 are out of scope and no clinical certification is claimed |
| HIPAA / GDPR | De-identification follows DICOM-PS3.15-style curation, but **no certification is claimed**; burned-in-annotation and date-shift limitations are disclosed in every manifest; external privacy review is mandated before data release |
| PACS interoperability | SRs validate against the standard, and every emitted object is proven re-ingestible at the PS3.10/PS3.7 file-format level and round-trips losslessly through the toolkit's own parsers (17-test suite — Part 4, item 9); what remains untested is a live network-level Association (C-STORE/C-FIND against a real PACS), which requires a connection to one |
| IHE | No IHE integration profile is claimed |

---

## Part 3 — How to reproduce every claim above

From the extracted release package (or project root):

```
:: 1. Full verification suite (expected: 324 passed — the first run from a
::    fresh extraction passes as-is; see Part 4, item 10)
python -m pip install -r requirements.lock
pip install -e .
python -m pytest verification/tests -q

:: 2. Independent SR validation (expected: no actionable errors; one known
::    benign module-level ValueType residual — see Part 4, item 3)
python -m dicom_validator.validate_iods <an exported _measurements_sr.dcm> --standard-path "%TEMP%\dicom_specs"

:: 3. Inspect conformance mapping
::    docs/standards_traceability.md  — feature → standard-clause table
::    RELEASE_NOTES_v1.0.2.md         — verification environment of record
```

**Companion documents (all included in this package):** `docs/standards_traceability.md` (feature → standard-clause map) · `RELEASE_NOTES_v1.0.2.md` (verification environment of record) · `verification/data/README_DATA.md` (verification-data contents and how to fetch optional bulk data) · `SHA256SUMS.txt` (per-file integrity manifest).

---

## Part 4 — Independent review & validation trail

1. **Internal verification:** 324-test suite, executed twice, fully green (plus ruff lint clean across all source packages).
2. **Independent read-only code review** (2026-09-27): confirmed the cohort color/volume defect and two provenance-quality issues; all findings were reproduced locally, fixed, and locked with regression tests. The review could not re-run the DICOM validator (spec download timed out); this session re-confirmed the result from the local spec cache.
3. **Independent DICOM validation** (`dicom-validator` 0.9.0, edition 2026d): exported Comprehensive SR — **0 actionable errors** (one benign residual flag at module level, disproved by walking the full content tree).
4. **Cross-validation:** NGTDM vs PyRadiomics v3.0.1 to 1e-6; IBSI phantom paths passing.
5. **UI-correctness review round (2026-09-27):** four interface-correctness defects were identified and fixed — (a) file removal in the sidebar did not propagate to the main interface (removal is now detected via the uploader's change callback and honored precisely); (b) Fit-to-Panel letterboxing skewed the click→pixel mapping and therefore measurement endpoints (mapping now goes through the displayed bitmap box; element sized exactly to the contained image); (c) the ViT received a 64-px ROI patch rather than the original image (input is now the whole original image at native resolution, with the ROI retained only for quantitative ROI metrics); (d) the CT Metrics tab rendered overlapping metrics from two engines with different SD conventions (consolidated to a single source of truth per metric, naive CI disclosed as caption).
6. **Line-by-line AI-code audit (2026-09-27)** — the previously test-suite-only area — covering `utils/medical_ai_vision.py` (ViT), `engines/onnx_inference.py`, `engines/monai_preprocessor.py`, `engines/finetune_trainer.py`, `engines/clinical_metrics.py`, `core/tissue_classifier.py` (XAI/radiomics), and `core/loaders.py` (model loading). Audit verdict: architecture sound (eval + frozen weights at load, `torch.inference_mode()`, modality-compatibility gates, ONNX torch-vs-ORT parity check, SHA-256 run manifests, discrete `*_result` metrics that refuse to hide absent denominators). Eight findings fixed:
   - **XAI attention-map reshape bug (real functional bug):** the attention-rollout [N×N] matrix was reshaped directly to √N×√N — impossible — so real ViTs always raised and silently fell back to a 1×N strip, meaning the attention heatmap overlay was rendering meaningless output. Fixed: per-patch reduction (mean over query patches) before normalization and reshape, per the rollout definition.
   - XAI now brackets forward passes with eval()/train() restoration so attention extraction never leaves a model in training mode.
   - ONNX inference now validates the input tensor against the session's declared name, rank, and static shape (dynamic axes honored) — mismatched tensors fail loudly instead of producing untraceable garbage.
   - ONNX parity check in the trainer: one forward pass captured once (was two calls + duplicate forward).
   - Trainer: full determinism controls (Python/NumPy/torch seeds, deterministic kernels warn-only, seeded DataLoader generator, worker seeding hook); `metrics.json` now carries `finished_at` (UTC) and `deterministic_algorithms: requested (warn_only=True)` so recency ordering and honesty statements hold.
   - Trainer eval batching no longer mutates the labels list while iterating it.
   - ViT provenance no longer self-describes as "rendered display image"; it now declares calibrated whole-image source with `source_is_calibrated: true`, and inference exceptions are logged before any fallback.
   - MONAI preprocessor records normalization/interpolation/target-size/input-shape into the MetaTensor metadata, so published preprocessing descriptions are exact (z-score semantics stated).
   All fixes locked by 5 new regression tests (`verification/tests/test_ai_engines.py`).
7. **Whole-application runtime review (2026-09-27)** — the running Streamlit interface was driven through its official testing harness (`streamlit.testing.v1.AppTest`) with an analytically-known synthetic CT (16×16 bone @1000 HU, 16×16 fat @−100 HU, remainder water @0 HU), activating every sidebar tool and validating rendered values against hand-computed truth. **14/14 checks passed**: tissue composition Bone 6.25% / Fat 6.25% / Water 87.5% (exact, sums to 100), radiomics mean **56.25 HU = analytic value**, CTCalculator mean **56.25 HU — identical to the radiomics path** (cross-engine consistency demonstrated), quality metrics finite/correct with `uniformity` honestly undefined on a zero-mean ROI, measurement math 5.000 mm / 90.000° / window 0/129/255, MONAI + SimpleITK advanced toggles and auto-reader running without exception. Four initial harness "failures" were errors in the review harness itself (wrong key name, wrong expected arithmetic, guessed API) — the application was correct in every case.
8. **Zoom-independence proof for the Advanced AI panel (2026-09-27):** MONAI and SimpleITK consume `original_image_data` — a full copy of the calibrated volume taken at load, before any display processing (app.py L5825 → L7972 → engines). Viewer zoom is browser-side canvas scaling and cannot enter the numpy pipeline; empirically, engine outputs are bit-identical (max diff 0.0) across viewer states while the display array changes 64×64 → 256×256 at 4×. MONAI's output (1, 128, 128) is the **whole image resampled** to model target size, not a crop. The two composition metrics in that panel are ROI-scoped by design and are now labeled "ROI voxels …" so whole-image vs ROI scope is explicit in the UI.
9. **Dependency-declaration rectification & PACS-ingestion conformance round (2026-09-27):** the declared pydicom floor (`>=2.4` in both `requirements.txt` and `pyproject.toml`) contradicted the code, which uses pydicom 3.x-only APIs (`Dataset.save_as(enforce_file_format=True)`); both floors were corrected to `>=3.0` (the lockfile already pinned 3.0.2), and a full import-tree-vs-declaration sweep found no other gaps. A new 17-test **PACS-ingestion / round-trip conformance suite** (`verification/tests/test_pacs_ingestion.py`) closes the ingestion boundary: every emitted DICOM object (Comprehensive SR, de-identified copies) is re-parsed strictly at the PS3.10/PS3.7 file-format level (preamble + DICM magic, byte-exact File-Meta Group Length, MediaStorageSOP* ↔ SOP* agreement, declared transfer syntax equal to the one actually used, File Meta Information Version `00 01`); exported SRs round-trip losslessly through the app's own TID 1500 parser and measurement re-import (distance, two-arm angle, calibrated ROI radius, exact source-image reference); the ingestion boundary's rejections are pinned (missing TransferSyntaxUID, incomplete CT IOD, non-DICOM bytes, empty measurement set); annotated-PNG composites re-ingest as MEASUREMENT_COMPOSITE with bit-identical measurement metadata (UCUM units preserved); series ordering survives PACS-style re-serialization; and every export ZIP passes the toolkit's own archive validator. After this round: **297 tests — 297 passed** (twice), ruff clean, and the independent validator re-run on a freshly regenerated SR reproduces **0 actionable errors** with the single known benign residual (all 15 content items carry ValueType; the flag targets the document root, not a content item).
10. **First-run test failure root-caused and fixed (2026-09-27):** earlier releases needed a second test run right after package extraction, attributed to antivirus file locking. Controlled experiments disproved that attribution: fresh extractions failed **deterministically** (42 tests erroring at setup on every run until a `cache_logs/` directory happened to exist), and adding the directory alone — nothing else — made the first run pass. The mechanism: `pyproject.toml` configures `--basetemp=cache_logs/pytest_tmp`, and pytest creates the basetemp **without creating parent directories**, so a fresh package (no `cache_logs/`) fails every `tmp_path` test with FileNotFoundError. The fix ships a root `conftest.py` that creates the parent directory in `pytest_configure`. Verified from a pristine extraction of the release zip: the **first** run passes 297/297. The antivirus explanation in previous release notes is hereby retracted.

11. **Viewer "Fit to panel" mode removed (2026-09-27):** the viewer-mode selector now offers 1:1 pixels (default), 2x, and 4x; the letterboxed fit path and its fitScale click-mapping special case were deleted so all modes share one simple source-pixel mapping. A stale-value migration guard covers sessions from earlier versions. Locked by 5 tests (`test_viewer_fit_removal.py`).
12. **Kurtosis convention verified and locked against the IBSI reference (2026-09-27):** the IBSI reference table's own rows are labelled "(Excess) kurtosis" — the excess (Fisher) definition — which is exactly what the first-order extractor computes (`scipy.stats.kurtosis(fisher=True)`). Locked by tests asserting the reference labels, formula equality to 5e-4, and the moment−3 identity (`test_harmonization_kurtosis.py`); no formula change was needed or made.
13. **ComBat batch harmonization added (2026-09-27):** empirical-Bayes location-and-scale ComBat (Johnson 2007, sva/neuroCombat formulation) in `core/harmonization.py`, wired as an opt-in toggle into the cohort CSV export with per-row disclosure (`combat_batch` / `combat_applied` / `combat_details`). Batch = acquisition modality; undefined cases refuse explicitly and ship raw statistics with the stated reason. Verified by ground-truth tests (known batch effects removed to a common target; preserved covariate effects equal to the OLS estimate; reference-batch pass-through; determinism) and end-to-end export tests (default schema unchanged; refusal path explicit) — 12 + 5 tests. Two real defects found and fixed by those tests (covariate-fit column desync after feature skips; disclosure-order mislabeling of failed rows).
14. **TCIA download-group removal fixed (2026-09-27):** de-selecting a "Series to download" group and re-submitting now removes it from the interface (explicit `_tcia_removal_requested` marker + caller-side active-snapshot clearing, mirroring the uploader's removal signal), and re-adding the same group no longer duplicates images (SeriesInstanceUID-level selection dedup, download-loop guard, and resolved-path dedup of the returned list). A waiting state (no submit) provably does not clear anything. Locked by 5 flow-level tests (`test_tcia_series_removal.py`). A latent `str`-path `stat()` crash in the zero-progress fallback was found and fixed by the same simulation.
15. **Publication package reconciled (2026-09-27):** the manuscript sources, tables, and title page previously claimed the PyRadiomics comparator and IBSI benchmark were unavailable; both are now measured (0.0 max error at 1e-6; 270/270 Configuration D rows). All numeric claims were rewritten against the canonical JSON artifacts, the benchmark JSON/report were regenerated at v1.0.2, and the Word files were regenerated from the reconciled sources (content verified programmatically). The package README now states the reconciled status and the remaining author-side steps.
16. **Radiomics disclosure text corrected (2026-09-28):** the UI caption still claimed that Fisher (excess) kurtosis "differs from IBSI kurtosis by a constant −3" — false: the IBSI reference values are themselves defined as "(Excess) kurtosis", i.e. the exact convention the extractor already computes (locked per item 12; the constant −3 offset belongs to the non-excess moment convention IBSI does not use). The caption now states that the kurtosis convention matches the IBSI reference and attributes non-comparability to its true causes (whole-image basis, absent ROI mask, no resampling/re-segmentation), replacing the broader "not IBSI-compliant" wording with the precise "not IBSI Configuration-D comparable"; the traceability matrix and this document were aligned. Text-only correction — no computational change; suite unchanged (324 tests, run twice, ruff clean).

## Bottom line

- **Numeric accuracy** is demonstrated against hand-computed references (HU, distances, angles, windowing), **cross-validated to 1e-6 against PyRadiomics** for radiomics, and **confirmed by an independent current-edition DICOM validator** for structured reports.
- **Standards alignment** is comprehensive for everything the software invokes — DICOM PS3.3/3.5/3.10/3.16, UCUM, RFC 4180/8259, NIfTI, IBSI (Configuration-D path) — with every deviation *disclosed and test-enforced* rather than hidden, and with proof that every emitted DICOM object re-ingests losslessly at the file-format level (PACS-style re-read).
- **What it does not claim** is stated as plainly as what it does: no medical-device, regulatory, or privacy certification. That honesty is itself a publication-grade property.
