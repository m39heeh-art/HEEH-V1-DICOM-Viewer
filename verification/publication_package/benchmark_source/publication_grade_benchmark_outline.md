# Publication-grade benchmark outline for HEEH-V1

## 1. Study objective
To evaluate the reproducibility and computational behavior of HEEH-V1 radiomics and export/privacy safeguards using public benchmark data and generated challenge fixtures, without claiming clinical validity or superiority beyond the defined protocol.

## 2. Scope and claims
This benchmark assesses:
- radiomics reproducibility on a synthetic CT phantom ROI,
- export/privacy compliance using generated valid/invalid archive fixtures,
- runtime and memory behavior under a fixed workload.

This benchmark does not claim:
- patient-level clinical accuracy,
- diagnostic superiority,
- full IBSI compliance,
- medical-device readiness.

## 3. Data provenance and legal use
### Public benchmark metadata
- Dataset: CT-Phantom4Radiomics
- Collection: TCIA/NBIA
- SeriesInstanceUID: 1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879
- StudyInstanceUID: 1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971
- License: Creative Commons Attribution 4.0 International License
- License URL: https://creativecommons.org/licenses/by/4.0/
- DataDescriptionURI: https://doi.org/10.7937/a1v1-rc66
- Download status: metadata_only in this environment

### Interpretation
The public dataset is recorded with exact metadata and licensing provenance, but no public archive was downloaded, and no full-image benchmarking result is reported beyond the metadata provenance.

## 4. Benchmark design
### Radiomics benchmark
- ROI: synthetic water ROI from an ACR-style phantom
- Preprocessing: fixed bin width discretization, levels=256, bin_width=2.0, spacing=[1.0, 1.0]
- Comparator: ground-truth values from the known synthetic phantom configuration
- Tolerance: mean ±3.0 HU, std ±2.0 HU, min/max ±10.0 HU

### Export/privacy benchmark
- Challenge fixtures generated from valid/invalid archive scenarios
- Ground truth: valid archive vs invalid archive label
- Metrics: sensitivity and specificity

### Runtime/memory benchmark
- Fixed protocol: 8 images, 128 operations, cache size 3, repeated 20 times
- Metrics: elapsed time, peak memory, cache hit rate

## 5. Statistical reporting
Report values as:
- mean ± standard deviation
- median
- minimum/maximum
- confidence intervals where applicable
- exact count of true positives/true negatives/false positives/false negatives

## 6. Results summary
### Radiomics reproducibility
- Mean: -0.04 HU
- Std: 10.02 HU
- Min: -45.02 HU
- Max: 37.47 HU
- Pass under the pre-specified tolerance

### Export/privacy validation
- Sensitivity: 1.000
- Specificity: 1.000
- Accuracy: 1.000

### Runtime/memory
- Mean elapsed time: 0.004038 s
- Mean peak memory: 0.030 MB

## 7. Unavailable experiments
The following were explicitly marked unavailable or not run:
- direct PyRadiomics comparison,
- official IBSI Phase 1/2 benchmark,
- full public dataset comparison using downloaded radiomics reference data.

## 8. Limitations
- The radiomics result is obtained on a synthetic phantom and does not establish clinical accuracy.
- The public TCIA metadata is recorded but not fully downloaded as a benchmark archive in this environment.
- The direct reference comparator is blocked, so no external radiomics superiority claim is made.
- The export/privacy benchmark uses generated challenge fixtures and is not equivalent to patient-level validation.

## 9. Recommended publication framing
A suitable manuscript framing is:
> This work evaluates the reproducibility and computational behavior of HEEH-V1 under a conservative, public-data-aware benchmark protocol. Results are limited to the defined synthetic phantom, generated challenge fixtures, and fixed runtime workload. No clinical claims are made, and direct external comparator benchmarking remains blocked pending access to a compatible reference implementation and the relevant public dataset archive.

## 10. Suggested section headings for a paper
- Data provenance and licensing
- Benchmark protocol
- Radiomics reproducibility results
- Export/privacy validation results
- Runtime and memory profiling
- Limitations and blocked comparators
- Conclusion and scope of inference
