# Scientific Benchmark Dossier

## 1. Objective
This benchmark package was designed to evaluate HEEH-V1 under a conservative, reproducible, public-data-aware framework while avoiding unsupported claims. The objective was to measure only what could be verified with the available data, code, and environment: (i) radiomics agreement on a synthetic CT phantom ROI, (ii) export/privacy validation on challenge fixtures with defined ground truth, and (iii) runtime and memory behavior under a fixed workload. The package explicitly records unavailable comparator experiments rather than fabricating results.

## 2. Scope of inference
This dossier supports only the following conclusions:
- the project produces numerically reproducible results under the specified phantom and fixture protocols,
- the export/privacy validator correctly separates valid and invalid archives under the designed challenge set,
- the fixed runtime/memory benchmark is stable over repeated runs,
- the project does not establish clinical accuracy, patient-level performance, or external comparator superiority.

No claim is made regarding diagnostic accuracy, patient risk classification, or full IBSI compliance.

## 3. Public data provenance and legal status
Public dataset provenance was recorded from the TCIA/NBIA collection interface for the CT radiomics phantom collection.

### Provenance record
- Collection name: CT-Phantom4Radiomics
- Collection metadata endpoint: https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getSeries?Collection=CT-Phantom4Radiomics&format=json
- SeriesInstanceUID: 1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879
- StudyInstanceUID: 1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971
- Modality: CT
- Site: HES-SO Valais
- License: Creative Commons Attribution 4.0 International License
- License URL: https://creativecommons.org/licenses/by/4.0/
- DataDescriptionURI: https://doi.org/10.7937/a1v1-rc66

### Legal interpretation
This dataset is public and metadata was retrieved from the public API. The archive itself was not downloaded in this environment, and therefore the full-file hash and image-level benchmark score are not reported for the public collection. The provenance record is exact and legally traceable, but limited to metadata-level evidence.

## 4. Benchmark protocol
### 4.1 Radiomics benchmark
The radiomics benchmark used the repository’s synthetic ACR-style CT phantom ROI, which has known numerical ground truth. The pipeline measured first-order statistics (mean, std, min, max) after applying a fixed preprocessing policy:
- levels = 256
- discretization = fixed_bin_width
- bin_width = 2.0
- spacing = [1.0, 1.0]

The measured values were compared with pre-specified tolerances:
- mean: ±3.0 HU
- std: ±2.0 HU
- min: ±10.0 HU
- max: ±10.0 HU

This benchmark does not depend on any patient labels, and it does not claim clinical validity.

### 4.2 Export/privacy benchmark
The export/privacy benchmark used generated valid and invalid archive fixtures with explicit labels. Valid archives contained a compliant manifest and correct measurement encoding; invalid archives contained at least one of the following failure modes:
- archive path traversal or unsafe archive members,
- local path leakage,
- non-pseudonymous DICOM metadata,
- private-tag presence,
- legacy angle semantics violating the required schema.

Ground truth was defined by the fixture specification, and performance was reported as sensitivity and specificity.

### 4.3 Runtime/memory benchmark
The runtime and memory benchmark used a fixed synthetic workload with repeated execution:
- image_count = 8
- operations = 128
- cache_size = 3
- repetitions = 20

Measurements included:
- elapsed time per run,
- median elapsed time,
- mean elapsed time,
- peak memory via tracemalloc,
- cache hit rate under the fixed protocol.

## 5. Measurement results
### 5.1 Radiomics results
Measured values for the synthetic water ROI:
- mean = -0.04 HU
- std = 10.02 HU
- min = -45.02 HU
- max = 37.47 HU

Ground-truth targets:
- mean target = 0.00 ± 3.00 HU
- std target = 10.00 ± 2.00 HU
- min target = -45.00 HU
- max target = 37.00 HU

Interpretation: the measured values satisfy the pre-specified tolerance and are thus classified as passing within the documented protocol. This supports numerical reproducibility for the tested phantom ROI, not clinical validity.

### 5.2 Export/privacy validation results
Ground-truth challenge set:
- valid archives = 20
- invalid archives = 20

Measured results:
- true positives = 20
- true negatives = 20
- false positives = 0
- false negatives = 0
- sensitivity = 1.000
- specificity = 1.000
- accuracy = 1.000

Interpretation: the validation logic correctly classifies the generated challenge fixtures under the defined and explicit ground truth.

### 5.3 Runtime/memory results
Measured over 20 repeated runs:
- mean elapsed time = 0.004038 s
- median elapsed time = 0.003958 s
- mean peak memory = 0.030 MB
- mean hit rate = 0.000 under the fixed synthetic cache workload

Interpretation: the workload is computationally inexpensive in this environment and stable across the repeated runs. This is a system-level performance measurement only, not a patient-level clinical benchmark.

## 6. External verification and remaining limits
The following measurements are reported separately from the synthetic benchmark and do not imply clinical validity, superiority, or certification.

### Direct PyRadiomics comparator
Status: measured.
PyRadiomics 3.0.1 was executed in the WSL comparator environment on the deterministic synthetic ROI with matched mask, spacing, and bin width. Absolute differences for mean, standard deviation, minimum, and maximum were 0.00413, 0.00187, 0.00222, and 0.00173 HU, respectively. The 1e-6 tolerance was not met; this is not exact agreement.

### Official IBSI phantom verification
Status: measured, not certified.
The official `ibsi_1_ct_radiomics_phantom` was acquired from `theibsi/data_sets` at commit `6da96021bc91faf4c0cb7fd7fa56a4225d2064a8` under CC BY-NC 3.0. A matched first-order run produced absolute differences of 0.00272, 0.00116, 0, and 0 HU for mean, standard deviation, minimum, and maximum. The complete IBSI Phase 1/2 reference workflow and all reference values were not executed, so this is not an IBSI compliance certificate.

### Full public archive benchmark
Status: not executed.
Reason: the public archive itself was not downloaded; only metadata provenance was captured. No image-level or archive-level public benchmark result is claimed from the full dataset.

## 7. Reproducibility and auditability
All measured results were generated from the project code under a fixed protocol and recorded in the project outputs:
- results/heeh_v1_public_benchmark_results.json
- docs/public_benchmark_report.md
- docs/final_benchmark_summary.md
- scripts/public_benchmark_evidence.py

These files provide the exact benchmark values and the provenance trail for the public dataset record.

## 8. Limitations
This benchmark package is intentionally conservative in scope. The main limitations are:
1. The radiomics benchmark is synthetic; it does not establish clinical validity for real patient data.
2. The public dataset record is metadata-only; no full archive benchmark was completed.
3. The external comparator was limited to first-order features under an explicit matched protocol; therefore, no superiority claim is made.
4. The export/privacy benchmark uses generated fixtures rather than real clinical export pipelines.
5. Runtime and memory results are environment-dependent and should be interpreted only under the fixed workload protocol.

## 9. Scientific interpretation
The evidence supports the conclusion that HEEH-V1 behaves reproducibly under the measured synthetic CT phantom and generated fixture benchmark protocols. The results are scientifically defensible because they are quantified, bounded, repeated, and explicitly limited in scope. They are not sufficient to support any clinical or comparative claim beyond the stated benchmark conditions.

## 10. Recommended manuscript framing
A defensible scientific framing is:
> This work evaluates the reproducibility and computational behavior of HEEH-V1 under a conservative, metadata-aware public-data and synthetic-phantom benchmark protocol. The measured results were obtained under pre-specified tolerances and fixed runtime conditions. No claim is made regarding clinical accuracy, diagnostic superiority, or IBSI compliance because the corresponding comparator and official external benchmark workflows were unavailable in this environment.

## 11. Final statement of evidence
This benchmark package is suitable as a transparent scientific evidence record for research and supplementary documentation. It is not a clinical validation dataset and it does not provide evidence that the software is safe or superior in patient care. It is valid only within the benchmark protocol documented above.
