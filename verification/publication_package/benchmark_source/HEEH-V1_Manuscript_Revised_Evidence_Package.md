# HEEH-V1(TM) DICOM Viewer
## Revised manuscript and evidence package

**Purpose.** This document is a publication-oriented rewrite and evidence
package for the research-software manuscript. It uses only claims that are
supported by the repository and its recorded validation. It deliberately does
not invent clinical accuracy, patient-level performance, external validation,
or IBSI benchmark results.

**Current software release.** HEEH-V1(TM) DICOM Viewer, version 1.0.1.

**Reproducible release identifiers**

- GitHub release: `v1.0.1`
- Git commit: `1af5bd295f17b6f463062cd858b025e0ee8b724c`
- Zenodo record: https://zenodo.org/records/22937413
- Version DOI: https://doi.org/10.5281/zenodo.22937413
- Concept DOI: https://doi.org/10.5281/zenodo.22768910
- Release archive SHA-256:
  `794894109816441ED3AA18750DAABCD88AE0D762029C5EA6DE1CBE6F2A320DF3`

---

## Proposed title

**HEEH-V1(TM) DICOM Viewer: A Reproducible Research Workflow for Quantitative
Medical-Image Analysis, Privacy-Aware Export, and Exploratory AI**

This title is intentionally narrower than “integrated platform.” The paper
should present the software as a research workflow and validation artifact,
not as a clinical workstation or diagnostic system.

## Structured abstract

**Background:** Research teams frequently combine DICOM viewing, calibrated
measurements, quantitative image analysis, exploratory machine learning, and
data export using disconnected tools. This can make provenance, privacy
review, and reproducibility difficult to audit.

**Objective:** We developed HEEH-V1(TM) DICOM Viewer, a Streamlit-based research
software workflow that keeps source intensities separate from display data,
records analysis provenance, validates privacy-aware exports, and exposes
experimental AI workflows without presenting them as clinical findings.

**Methods:** The application supports DICOM and common volumetric-image
loading, modality-aware display, physical measurements, selected
radiomics-style features, export validation, and optional model inference.
The CT radiomics subset uses a declared fixed-bin-width policy with 25 HU
bins, a shared -1024 HU origin, and explicit provenance. Non-CT intensity
analysis uses a separately labeled research min-max policy and does not claim
CT calibration or full IBSI compliance. Export validation checks archive
structure, manifest hashes, path safety, DICOM privacy markers, private tags,
and selected PHI fields. The software release was tested using automated unit
and integration tests, linting, dependency checks, compilation checks, and a
headless Streamlit health check.

**Results:** Release 1.0.1 passed 367 automated tests. Ruff linting,
`pip check`, and Python compilation checks passed. The release archive was
reproducibly generated from the Git tag and its MD5 checksum matched the file
published by Zenodo. The tested export contract rejects unsafe archive members,
manifest mismatches, private DICOM tags, missing de-identification markers,
and selected residual PHI. These results establish software-behavior
verification; they do not establish clinical accuracy, diagnostic value,
generalizability, or regulatory compliance.

**Conclusions:** HEEH-V1(TM) provides a documented research-software workflow
for quantitative medical-image exploration and privacy-aware export review.
Its value is reproducibility and explicit safety boundaries. Formal IBSI
benchmarking, independent clinical validation, prospective evaluation, and
deployment security assessment remain outside the present release.

**Keywords:** medical imaging; DICOM; research software; radiomics;
reproducibility; de-identification; exploratory AI; Streamlit.

---

## 1. Introduction

Medical-image research often requires a sequence of operations that are
implemented in different applications: DICOM ingestion, modality-specific
display, physical measurement, quantitative summaries, feature extraction,
model experimentation, and export. When these operations are not connected by
explicit provenance, it is difficult to determine whether a reported result
was calculated from calibrated source data or from a presentation derivative.
Exported data may also retain private DICOM elements, unsafe paths, or
identifiers that are not visible in a routine visual review.

HEEH-V1(TM) was designed as research and education software to make those
boundaries explicit. The software separates source representations from
display representations, records selected processing parameters, applies
conservative export checks, and labels optional AI outputs as exploratory.
The contribution of this work is therefore not a claim of diagnostic
performance. It is a reproducible, inspectable workflow contract for
quantitative image research.

The specific contributions are:

1. A modality-aware viewer and quantitative analysis workflow that preserves
   calibrated source data separately from display images.
2. A declared CT radiomics subset with fixed-bin-width discretisation and
   provenance, plus a distinct non-CT research policy.
3. An offline export validator covering archive integrity, manifest hashes,
   path safety, DICOM privacy markers, private tags, and selected PHI fields.
4. A release and validation process that links source code, tests, metadata,
   and a permanent Zenodo archive.

---

## 2. Materials and methods

### 2.1 Software architecture

The application is implemented in Python with Streamlit. Shared functionality
is divided into core domain modules, processing engines, and UI helpers.
Inputs are decoded and validated before analysis. DICOM rescale slope and
intercept are applied where appropriate. A calibrated source array is retained
for quantitative operations, while an independent display representation is
used for rendering and model-image preparation.

The software is research-only. It does not provide authentication,
authorization, TLS termination, PACS certification, clinical decision support,
or medical-device certification.

### 2.2 Quantitative image analysis

The application provides first-order summaries, selected texture summaries,
shape calculations, quality metrics, and measurement helpers. Outputs are
reported with units where a physical calibration is available. If calibration
is unavailable, the software does not silently label pixel distances as
millimetres.

### 2.3 Radiomics policy

The CT profile is `CT_IBSI_SUBSET_V1`. It uses:

- fixed-bin-width discretisation;
- bin width: 25 HU by default;
- shared bin origin: -1024 HU;
- 256 levels by default;
- finite-value validation;
- optional spacing validation, resampling, and resegmentation through the
  explicit preprocessing helper.

Values outside the declared CT bin range are rejected rather than silently
clipped. This prevents a hidden patient-specific change of bin origin.
Continuous first-order quantities remain in the source intensity domain;
entropy is calculated from the declared discretised histogram.

For non-CT modalities, the profile is
`NON_CT_RESEARCH_INTENSITY_V1`. It uses a min-max discretisation policy for
research exploration and records that modality-specific calibration and
preprocessing are required. It must not be described as CT/HU radiomics or as
full IBSI compliance.

The current implementation is an IBSI-aligned subset, not an official IBSI
benchmark implementation. Publication claims should use “IBSI-aligned” or
“IBSI-informed” only.

### 2.4 Privacy-aware export

Export archives contain a manifest and SHA-256 file hashes. Validation checks
include safe member paths, readable ZIP members, manifest completeness and
hashes, DICOM private tags, the status of `PatientIdentityRemoved`, selected PHI
keywords, pseudonymous patient identifiers, DICOM SR content, local path
leakage, and measurement-unit semantics. An absent identity-removal marker
produces a manual-review warning; an explicit `NO` is rejected. A `YES` marker
does not establish that a complete confidentiality profile was applied.

The helper removes private tags and remaps UIDs, but handles only the declared
identifier subset; it does not apply the full DICOM PS3.15 Annex E Basic
Application Level Confidentiality Profile or automatically remove burned-in
text from pixels. Pixel-level and complete-object privacy review remains a
study-specific responsibility. ZIP encryption is not automatically applied.

### 2.5 Exploratory AI

Optional Hugging Face image-classification models are loaded only when
available and are modality-gated. The processor creates model tensors from a
display image. A post-processing gate verifies the presence of `pixel_values`,
the `[batch, 3, height, width]` layout, positive dimensions, finite values,
and compatibility with a declared model image size when available. Shape
errors are reported explicitly as `MODEL_INPUT_SHAPE_ERROR`.

These models are exploratory demonstrations. Their labels are not clinical
findings and no claim of clinical validity is made.

### 2.6 Reproducible release and validation

The release was created from a Git tag and archived on Zenodo. The repository
contains dependency specifications, a citation file, Zenodo metadata, a
research-only README, tests, and standards-boundary documentation.

The release validation included:

- 367 automated tests;
- Ruff linting;
- `pip check`;
- Python compilation checks;
- headless Streamlit startup and health endpoint;
- archive-content inspection for local environments, caches, and local
  medical-image files;
- local-versus-Zenodo archive checksum comparison.

---

## 3. Results

### 3.1 Software verification

All 367 automated tests passed for release 1.0.1. The test suite covers
scientific helpers, measurements, image preservation, DICOM ordering,
modality detection, volume loading, export validation, privacy helpers,
accessibility contracts, logging, radiomics provenance, AI input-shape
validation, and fine-tuning plumbing.

Ruff reported no findings. `pip check` reported no broken requirements.
Python compilation completed without errors. The Streamlit health endpoint
returned `ok` during a headless startup smoke test.

These are verification results for the released software. They are not
accuracy measurements against patients or clinical reference standards.

### 3.2 Reproducibility and archive integrity

The published archive contains 106 tracked project files and excludes virtual
environments, Git metadata, Python caches, test caches, local environment
files, and local DICOM/NIfTI/NRRD/MHA files. The local release archive and the
Zenodo file have identical size and MD5 checksum:

| Item | Value |
|---|---|
| Archive | `HEEH-V1-DICOM-Viewer-v1.0.1.zip` |
| Size | 2,113,206 bytes |
| MD5 | `10815E06EADA5843EC0D128E04C9C4F2` |
| SHA-256 | `794894109816441ED3AA18750DAABCD88AE0D762029C5EA6DE1CBE6F2A320DF3` |

### 3.3 Privacy and export verification

The export validator is tested against accepted and rejected archive cases.
The implemented contract rejects unsafe archive members, missing or
inconsistent manifest entries, hash mismatches, private DICOM tags, missing
de-identification markers, non-pseudonymous patient identifiers, selected
PHI fields, local-path leakage, and invalid measurement-unit semantics.

The result is a software contract and a pre-release safeguard. It is not a
claim that an arbitrary clinical dataset is anonymous or that the application
is HIPAA, GDPR, IHE, or DICOM certified.

### 3.4 Radiomics and AI verification

The tests verify that CT reports record their discretisation parameters and
that non-CT reports use a separately labeled policy. They also verify that a
processor/model image-size mismatch is rejected before model inference.
These tests establish deterministic handling of declared inputs; they do not
establish agreement with an IBSI reference dataset or model performance on a
clinical cohort.

### 3.5 Summary tables

**Table 1. Reproducible release and software-verification evidence.**

| Evidence item | Measured or declared value | Interpretation |
|---|---:|---|
| Release | 1.0.1 | Frozen research-software artifact |
| Git commit | `1af5bd295f17b6f463062cd858b025e0ee8b724c` | Exact source revision |
| Automated tests | 367 passed | Software behavior verified against repository fixtures |
| Ruff | Passed | Selected static checks passed |
| Dependency check | No broken requirements | Installed dependency graph was consistent |
| Python compilation | Passed | Changed Python modules compiled successfully |
| Streamlit smoke test | Health endpoint returned `ok` | Application started in headless mode |
| Archive contents | 106 tracked files | Release archive was inspected |
| Local/Zenodo MD5 | `10815E06EADA5843EC0D128E04C9C4F2` | Published archive matched local archive |

**Table 2. Implemented quantitative and safety contracts.**

| Component | Implemented contract | Evidence status | Not demonstrated |
|---|---|---|---|
| Source/display separation | Quantitative paths use source arrays; display rendering is separate | Tested in image-preservation suite | Clinical display conformance |
| CT radiomics | 25 HU fixed width, -1024 HU shared origin, 256 levels by default | Provenance and regression tests | Full IBSI benchmark agreement |
| Non-CT radiomics | Explicit research min-max policy | Modality-policy regression test | Modality-specific scientific calibration |
| AI input preparation | RGB processor path plus tensor-shape and finite-value gate | Shape-mismatch regression test | Diagnostic accuracy or clinical utility |
| DICOM de-identification | Declared identifier subset, private-tag removal, UID remapping; not a full PS3.15 profile | Unit and export-validation tests | Complete-object de-identification or removal of burned-in pixel identifiers |
| Export archive | Manifest hashes, safe paths, privacy and unit checks | Positive and negative validator tests | Formal anonymity or regulatory certification |

**Table 3. Export-validation challenge matrix.**

| Challenge category | Expected behavior | Current evidence |
|---|---|---|
| Unsafe member path | Reject | Automated validator test |
| Missing manifest | Reject | Automated validator test |
| Manifest hash mismatch | Reject | Automated validator test |
| Unmanifested file | Reject | Automated validator test |
| DICOM private tag | Reject | Automated validator test |
| Missing `PatientIdentityRemoved` | Warn for manual review; explicit `NO` is rejected | Automated validator tests |
| Non-pseudonymous PatientID | Reject | Automated validator test |
| Selected residual PHI keyword | Reject | Automated validator test |
| Local filesystem path in text export | Reject | Automated validator test |
| Invalid angle/distance units | Reject | Automated validator test |
| Burned-in annotation in pixels | Requires human/protocol review | Not automatically removed |

**Table 4. Scope comparison with established research tools.** This is a
capability-scope comparison, not a head-to-head performance benchmark. A
checkmark means that the named capability is an explicit project goal or
documented workflow surface; it does not mean that the implementations are
equivalent in maturity or validation.

| Capability | HEEH-V1 | 3D Slicer | OHIF Viewer | PyRadiomics | MONAI Label |
|---|:---:|:---:|:---:|:---:|:---:|
| Interactive DICOM viewing | Yes | Yes | Yes | No | Limited/integration-dependent |
| Physical measurements | Yes | Yes | Yes | No | Integration-dependent |
| Selected radiomics calculations | Yes | Via extensions | Via extensions | Yes, dedicated | Via integration |
| Explicit CT bin-origin policy in this release | Yes | Configuration-dependent | Not the primary scope | Configuration-dependent | Configuration-dependent |
| Privacy-aware export validator in this release | Yes | Extension/workflow-dependent | Deployment-dependent | No primary scope | Deployment-dependent |
| Exploratory model inference | Yes | Extensions | Extensions/integration | No primary scope | Yes, dedicated |
| Official clinical certification claimed | No | No general claim | No general claim | No | No |
| Official IBSI compliance claimed by this paper | No | Not assessed here | Not assessed here | Not assessed here | Not assessed here |

This table should be retained only if the manuscript clearly states that it
is a scope map. It must not be converted into claims of superiority. A true
comparison requires identical inputs, versions, configurations, reference
outputs, and pre-registered metrics.

**Table 5. Results table to complete after practical experiments.** Empty cells
are intentional and must be filled only from saved experiment outputs.

| Experiment | Dataset/configuration | Metric | HEEH-V1 result | Comparator/reference | Result file |
|---|---|---|---:|---:|---|
| CT radiomics agreement | To be declared | MAE / relative error | TBD | Reference implementation | TBD |
| CT radiomics reproducibility | To be declared | ICC / coefficient of variation | TBD | Independent rerun | TBD |
| Export validator | Synthetic challenge set | Sensitivity / specificity | TBD | Ground-truth labels | TBD |
| Cold-start performance | Declared machine and cohort | Seconds per case | TBD | Baseline workflow | TBD |
| Warm-cache performance | Declared machine and cohort | Seconds per case | TBD | Baseline workflow | TBD |
| Peak memory | Declared machine and cohort | GB | TBD | Baseline workflow | TBD |
| Exploratory AI | Governed labeled dataset | Macro-F1 / AUROC | TBD | Declared baseline | TBD |

---

## 4. Discussion

The principal strength of HEEH-V1 is explicitness. Source data, display data,
radiomics policy, export validation, and AI input preparation are represented
as separate contracts rather than being implied by the user interface. The
release is also directly citable and its archived file can be matched to the
local release through a checksum.

The main limitation is that software verification is not clinical validation.
The present results show that the implementation behaves according to its
tests and release contract. They do not show that measurements are accurate
in a patient population, that radiomics features agree with an IBSI reference
implementation, or that exploratory model labels are diagnostically useful.
The CT profile also requires study-specific decisions about acquisition,
reconstruction, segmentation, spacing, resampling, and resegmentation.

The software should therefore be used as a research and education workflow.
Deployment with identifiable data requires authenticated infrastructure,
least privilege, retention and deletion controls, secure transport, audit
controls, and a documented privacy risk assessment. Burned-in pixel text
requires manual or validated pixel-level review.

---

## 5. Required experiments before claiming practical scientific performance

The following experiments are not represented by invented numbers in this
document. They should be run and inserted as measured results before
submitting a performance-focused paper:

1. **Radiomics reference agreement:** run the same CT phantom or IBSI reference
   cases through HEEH-V1 and a trusted reference implementation. Report
   absolute error, relative error, correlation, and Bland-Altman limits for
   every claimed feature.
2. **Patient-level reproducibility:** run two independent processes or
   environments on the same de-identified cases. Report feature-wise
   intraclass correlation or exact agreement, together with the full
   preprocessing manifest.
3. **Cohort leakage control:** document patient identifiers, study/series
   grouping, train/validation/test separation, and the number of unique
   patients in each split.
4. **Export challenge set:** create a non-PHI synthetic challenge set
   containing unsafe paths, private tags, incorrect hashes, missing markers,
   local paths, burned-in text flags, and malformed archives. Report
   sensitivity and specificity of the validator for each challenge category.
5. **Performance benchmark:** report cold-load and warm-cache latency, peak
   memory, archive-validation time, and throughput on a declared machine.
6. **Exploratory AI evaluation:** only if labels and governance are available,
   report patient-level accuracy, macro-F1, AUROC with confidence intervals,
   calibration, abstention/uncertainty behavior, and an untouched test set.
7. **External validation:** repeat the primary analysis on a dataset from a
   different institution or acquisition protocol.

Until these experiments are completed, the manuscript should use “software
verification,” “research workflow,” and “exploratory” rather than “clinical
validation,” “diagnostic,” “accurate,” or “generalizable.”

---

## 6. Recommended submission positioning

The strongest resubmission should be a research-software or methods paper
centered on reproducibility and privacy-aware workflow design. It should not
present the project as a collection of dozens of clinical capabilities.

The abstract and cover letter should state:

- what problem is solved;
- what is measured;
- what reference or comparator is used;
- what the software verification demonstrates;
- what it does not demonstrate.

The manuscript should include a public repository, permanent release DOI,
environment specification, test command, dataset governance statement, and a
clear limitations section. Any numerical result added after this document
must be traceable to a script, input dataset, configuration, and stored
output.

---

## 7. Claims that must not be used

Do not describe the project as:

- fully IBSI-compliant without official benchmark evidence;
- HIPAA, GDPR, IHE, or DICOM certified;
- clinical-grade, diagnostic, or a medical device;
- validated merely because the automated tests pass;
- anonymous merely because DICOM metadata were removed;
- externally validated without an independent external dataset;
- accurate or generalizable without patient-level quantitative evidence.
