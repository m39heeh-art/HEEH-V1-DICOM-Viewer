# Tables

## Table 1. Public dataset provenance and legal status

| Item | Value |
|---|---|
| Collection | CT-Phantom4Radiomics |
| Modality | CT |
| SeriesInstanceUID | 1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879 |
| StudyInstanceUID | 1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971 |
| Site | HES-SO Valais |
| License | Creative Commons Attribution 4.0 International License |
| License URL | https://creativecommons.org/licenses/by/4.0/ |
| DataDescriptionURI | https://doi.org/10.7937/a1v1-rc66 |
| Download status | metadata_only |
| Hash | Not generated; archive was not downloaded in this environment |

## Table 2. Benchmark results summary

| Benchmark | Metric | Result | Interpretation |
|---|---|---:|---|
| Radiomics (phantom ROI) | Mean HU | -0.04 | Within target tolerance |
| Radiomics (phantom ROI) | Std HU | 10.02 | Within target tolerance |
| Radiomics (phantom ROI) | Min HU | -45.02 | Within target tolerance |
| Radiomics (phantom ROI) | Max HU | 37.47 | Within target tolerance |
| PyRadiomics v3.0.1 agreement (matched first-order, synthetic ROI) | Max absolute error | 0.0 (tolerance 1e-6) | Exact agreement on the compared statistics |
| IBSI Configuration D verification (CT radiomics phantom) | Reference rows passed | 270 / 270 | Official reference values reproduced via the reference pipeline and the dedicated workflow |
| Export/privacy | Sensitivity | 1.000 | Perfect classification on defined challenge fixtures |
| Export/privacy | Specificity | 1.000 | Perfect classification on defined challenge fixtures |
| Runtime | Mean elapsed time | 0.003887 s | Fixed workload, repeated runs |
| Runtime | Median elapsed time | 0.003901 s | Fixed workload, repeated runs |
| Runtime | Mean peak memory | 0.030 MB | Fixed workload, repeated runs |

## Table 3. Unavailable experiments and reasons

| Experiment | Status | Reason |
|---|---|---|
| Official IBSI Phase 1/2 benchmark | Not run | Requires the official IBSI Phase 1/2 workflow and datasets; the executed verification is specific to Configuration D reference values |
| Image-level analysis of CT-Phantom4Radiomics | Not run | Archive not downloaded; metadata-only provenance recorded |

## Table 4. Benchmark claims and boundaries

| Claim area | Status |
|---|---|
| Clinical accuracy | Not claimed |
| Diagnostic superiority | Not claimed |
| Full IBSI compliance (Phase 1/2 certification) | Not claimed |
| Reproducibility under fixed protocol | Demonstrated |
| Reference-implementation agreement (matched first-order, synthetic ROI, 1e-6) | Demonstrated |
| IBSI Configuration D verification (official reference values, dedicated workflow) | Demonstrated |
| Public dataset provenance | Documented (metadata-level) |
| Export/privacy correctness under fixture labels | Demonstrated |
| Runtime/memory performance under repeated workload | Demonstrated |

## Table 5. Validation status

| Test family | Result |
|---|---|
| Public benchmark artifact generation | Passed |
| ACR-style phantom benchmark | Passed (within pre-specified tolerances) |
| PyRadiomics v3.0.1 matched first-order comparison | Passed (all absolute errors 0.0 at 1e-6) |
| IBSI Configuration D reference verification | Passed (270/270 populated rows) |
| Export/privacy challenge validation | Passed (sensitivity 1.000, specificity 1.000) |
| Full verification suite | 324 collected: 320 passed, 4 skipped, 0 failed |
| Static analysis (ruff) | Clean |
| Independent DICOM SR validation (dicom-validator, edition 2026d) | 0 actionable errors |
