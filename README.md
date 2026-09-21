[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22768910.svg)](https://doi.org/10.5281/zenodo.22768910)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0004--2729--443X-a6ce39?logo=orcid&logoColor=white)](https://orcid.org/0009-0004-2729-443X)

# HEEH-V1(TM) DICOM Viewer

HEEH-V1(TM) DICOM Viewer is a Streamlit web application for **medical-image
research and education**. It supports DICOM and common volumetric-image
workflows, calibrated measurements, image-quality and radiomics-style
calculations, experimental AI integrations, privacy-aware exports, and
provenance reporting.

**Protected project identity:** the public product name is exactly
**HEEH-V1(TM) DICOM Viewer** (display form: **HEEH-V1™ DICOM Viewer**).
Do not rename or substitute this identity in the application, launchers,
exports, package metadata, documentation, or publication assets.

ORCID contributor identifier: [0009-0004-2729-443X](https://orcid.org/0009-0004-2729-443X).

The official project logo is stored at `assets/heeh-v1-logo.jpg` and is used
as the application page icon and header mark. Keep the logo with the project
identity when publishing or redistributing the application.

> **Research and education disclaimer**
>
> This software is **not a certified medical device** and must not be used for
> diagnosis, prognosis, treatment planning, triage, or any patient-care
> decision. Model labels and overlays describe image or model behavior only;
> they are not medical findings. A qualified clinician must independently
> interpret all images and results.

## Browser access and compatibility

The public repository, release files, and Zenodo record are delivered through standard HTTPS and can be opened in current versions of Chrome, Microsoft Edge, Firefox, Safari, and other standards-compliant browsers. The DOI badge links directly to the permanent Zenodo record.

When running the application locally, start Streamlit with one of the included launchers and open the displayed `http://localhost:8501` address in a current desktop browser. JavaScript, cookies, and local storage must be enabled for Streamlit controls, uploads, downloads, and interactive Plotly visualizations. Use a recent browser release for large image sets and WebGL-based 3D views; browser extensions, restrictive enterprise policies, or disabled WebGL can limit individual features but do not affect repository or DOI access.

The application is responsive for standard desktop and tablet layouts. It is research software, not a hosted clinical service, and browser compatibility does not imply clinical certification or diagnostic suitability.
## Contents

- [Capabilities](#capabilities)
- [Input and navigation](#input-and-navigation)
- [Measurements and calibration](#measurements-and-calibration)
- [Analysis and scientific tools](#analysis-and-scientific-tools)
- [AI, segmentation, and acceleration](#ai-segmentation-and-acceleration)
- [Export and interoperability](#export-and-interoperability)
- [Privacy and security](#privacy-and-security)
- [Standards boundary](#standards-boundary)
- [Installation](#installation)
- [Running the application](#running-the-application)
- [Testing and validation](#testing-and-validation)
- [Project structure](#project-structure)
- [Publication sample set](#publication-sample-set)
- [Known limitations](#known-limitations)

## Capabilities

### Image ingestion

- DICOM files with `.dcm`, `.dicom`, `.ima`, `.img`, or no extension.
- NIfTI files: `.nii` and `.nii.gz`.
- NRRD files: `.nrrd`.
- MetaImage files: `.mha` and `.mhd`.
- Raster research images: PNG, JPEG, BMP, TIFF, and WebP.
- ZIP archives containing exported or measured images.
- TCIA/NBIA manifest and cached-series workflows.
- Multiple uploaded files and large image sets.
- Physical DICOM ordering using Image Orientation/Position metadata, with
  Instance Number and stable-input fallbacks.
- Detection of DICOM Modality and SOP Class UID before exposing
  modality-specific tools.
- Safe ZIP extraction and archive path checks.

The primary input surface handles both new studies and exported/measured
content. Exported JSON, PNG measurement metadata, de-identified DICOM, and
measurement composites are detected and restored automatically.

### Viewer and navigation

- 2D grayscale display with modality-aware presentation.
- CT window center/width and named window presets.
- Native-intensity percentile display for non-CT images.
- MONOCHROME1 inversion handling.
- Color-image display without applying grayscale CT assumptions.
- Slice navigation for volumetric and multi-frame data.
- Image navigation, series browsing, and side-by-side comparison.
- Interactive pixel coordinate and value feedback.
- 1:1 pixel inspection and enlarged display views.
- Accessibility-oriented captions, landmarks, skip links, keyboard hints, and
  contrast helpers.
- Silent background automatic reading for detected exported/measured image
  sets; it is not exposed as a separate visible workflow.

### Volumetric visualization

- Maximum Intensity Projection (MIP).
- Multi-Planar Reconstruction (MPR).
- Interactive Plotly 3D isosurface visualization.
- 2D, 3D, and selected 4D volume normalization.
- Safe handling of empty, non-finite, constant, or out-of-range volume data.
- Full-volume MIP/MPR processing while the normal viewer displays the selected
  middle or navigated slice.

MIP/MPR/3D are research visualizations. They do not replace a validated
diagnostic workstation, calibrated display, or clinical 3D review pipeline.

## Input and navigation

The application keeps physical source data separate from display data:

1. The source array is read and validated.
2. DICOM rescale slope/intercept and modality-specific interpretation are
   applied where appropriate.
3. Measurements and quantitative calculations use the source representation.
4. A separate 8-bit display image is generated for presentation only.

Navigation uses bounded caches for source arrays, rendered display images,
quality results, radiomics, derived CT reports, and pixel-hover payloads.
Cache keys include file identity, input fingerprint, slice, modality,
windowing, inversion, color state, and measurement-composite state. Caches are
bounded to protect memory during large imports.

The application does not impose an arbitrary image-count limit. Large cohorts
are still limited by available memory, upload transport, disk space, decoder
cost, and browser rendering capacity.

## Measurements and calibration

Supported interactive measurements include:

- Point-to-point distance.
- Angle measurement.
- ROI circle and ROI statistics.
- Line-intensity profile.
- Measurement undo and clear operations.
- Per-file and per-slice measurement persistence.
- Reopening of saved measurements from JSON, PNG metadata, composites, and
  export archives.

Measurement rules:

- Coordinates are stored in native source-pixel space.
- DICOM Pixel Spacing is interpreted as row spacing followed by column
  spacing; x uses column spacing and y uses row spacing.
- Distances use physical distance fields in `mm` or `cm`, or `px` when
  physical calibration is unavailable.
- Angles use degrees with the explicit UCUM unit `deg`.
- The first angle point is the vertex.
- Manual calibration is explicitly research-only and must be independently
  validated before use.

Measurement overlays are rendered as presentation products. The original
source pixels remain authoritative for quantitative calculations.

## Analysis and scientific tools

### CT and intensity analysis

- CT Hounsfield Unit conversion using DICOM rescale metadata.
- CT windowing and display presets.
- Tissue classification from documented HU ranges.
- Native-intensity analysis for MR, PET, US, projection radiography, and other
  non-CT modalities where supported.
- Finiteness, physiological-range, and minimum-size validation.
- Whole-image HU statistics.
- Noise and uniformity summaries.
- Research SNR and CNR proxies.
- Noise Power Spectrum (NPS) summaries where spatial data are sufficient.
- MTF-related research summaries derived from available NPS information.
- Low-contrast detectability proxy.
- Dose metadata display such as CTDIvol when present.
- Exposure-index metadata where available.
- Research tissue-composition summaries.

### Image processing

- Sobel edges.
- Canny edges.
- Gradient magnitude.
- Laplacian processing.
- Windowed overlays and tissue-composition maps.
- ROI crops and line profiles.
- Difference maps and percentage-change helpers.
- Perfusion time-intensity and color-map helpers.
- Vessel-enhancement research processing.

### Metrics

- Dice coefficient.
- Intersection over Union.
- Sensitivity.
- Specificity.
- Precision.
- Hausdorff distance.
- 95th-percentile Hausdorff distance (HD95).
- Average symmetric surface distance (ASSD).
- Explicit defined/undefined/invalid metric result states.
- Mask finiteness, shape, and validity checks.

These are mathematical or research metrics. They do not establish clinical
accuracy, segmentation quality in a patient population, or regulatory
performance.

### Radiomics-style features

- Histogram features including percentiles, skewness, kurtosis, and entropy.
- GLCM-style texture features.
- Shape features.
- Combined radiomics-style reports.
- CSV and XLSX export.

The current implementation is **IBSI-aligned in selected definitions**, not a
claim of full IBSI compliance. Reproducible radiomics requires documented
acquisition, reconstruction, interpolation, discretization, segmentation,
preprocessing, and feature-version choices.

### Longitudinal analysis

- Before/after difference maps.
- Percentage-change summaries.
- Research comparison views.

Longitudinal outputs are not a RECIST implementation or a validated treatment
response assessment.

## AI, segmentation, and acceleration

### PyTorch and Hugging Face models

- Demonstration chest X-ray, brain/MR, and age-classification model paths.
- Modality-gated model availability.
- Cached model loading.
- CPU fallback.
- CUDA device selection when PyTorch reports CUDA availability.
- Frozen evaluation-mode inference for loaded demonstration models.
- Attention overlays for exploratory model-behavior visualization.

ViT preprocessing operates on a rendered display image and may resize it to a
checkpoint input size. It is not super-resolution, reconstruction, or a
replacement for calibrated source data.

### MONAI and SimpleITK

- Lazy MONAI preprocessing to reduce startup cost.
- Volume preprocessing and research segmentation preparation.
- SimpleITK isotropic resampling.
- N4 bias-correction helper.
- Rigid and affine registration helpers.

### Anatomical segmentation

- Optional TotalSegmentator integration when separately installed.
- Optional MONAI Label integration through `MONAI_LABEL_URL`.
- Backend availability reporting.
- Source-volume validation.
- Returned-mask shape validation.
- Empty-mask rejection.

TotalSegmentator and MONAI Label are not bundled by default. The current
application does not claim automatic identification of all organs or bones.

### ONNX Runtime

The ONNX engine prefers `CUDAExecutionProvider` when the installed ONNX Runtime
build exposes it and otherwise falls back to `CPUExecutionProvider`. The
Research compute panel reports:

- PyTorch CUDA availability.
- GPU name and device count.
- Active ONNX provider.
- Providers exposed by ONNX Runtime.

CUDA availability is environment-dependent. The installed package, CUDA
runtime, cuDNN, NVIDIA driver, and model build must be mutually compatible.

## Export and interoperability

The unified Export dialog provides:

- De-identified DICOM PS3.10 file.
- Measurement-data CSV.
- Measurement-data JSON.
- Annotated PNG with measurements and ROI.
- DICOM Structured Report (DICOM SR).
- Radiomics CSV.
- Radiomics XLSX.
- Self-contained HTML research report.
- Cohort metrics CSV.
- All measured images ZIP.
- Machine-readable export provenance manifest.

### Export package contents

Consolidated ZIP exports can contain:

- Pseudonymous filenames such as `heeh_<hash>_image_0001`.
- De-identified DICOM and remapped UIDs.
- DICOM SR using the implemented TID 1500-based measurement structure.
- UCUM units: `mm`, `cm`, `px`, and `deg`.
- RFC 4180-compatible UTF-8 CSV with BOM.
- RFC 8259-compatible JSON.
- Office Open XML XLSX.
- PNG metadata containing normalized measurement JSON.
- Self-contained HTML with HEEH-V1(TM) product identification.
- Per-file cohort status, error code, error message, and source hash fields.
- `export_manifest.json` containing UTC generation time, media types, byte
  counts, SHA-256 hashes, encoding declarations, privacy boundaries, and
  validation requirements.

### Export validation

Run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_export.py path\to\export.zip
```

The validator checks:

- ZIP readability.
- Unsafe absolute and traversal member paths.
- Required export manifest.
- Manifest SHA-256 hashes.
- Unmanifested archive members.
- Common local-path and cache-path leakage.
- Basic DICOM readability.
- Presence of DICOM SR content.
- Measurement angle and distance semantics.
- Cohort status schema.
- Nested export archives.

The validator is a package-integrity tool. It is not a substitute for an
independent DICOM/DICOM SR validator, PACS testing, burned-in annotation
inspection, clinical validation, or regulatory certification.

## Privacy and security

The application provides:

- Curated PHI-field blanking.
- Private-tag removal in de-identified DICOM exports.
- Pseudonymized PatientID.
- UID remapping except required class, transfer, and implementation UIDs.
- PHI-safe audit-context redaction.
- Pseudonymous export stems and source labels.
- SHA-256 integrity hashes.
- Optional Fernet encryption helpers for controlled application integrations.
- Localhost-only launcher defaults.

The application does **not** automatically:

- Remove burned-in identifiers from pixels.
- Apply a validated DICOM date-shift profile.
- Encrypt ZIP archives.
- Provide authentication, authorization, TLS termination, or access control.
- Prove that an export is anonymous.
- Provide HIPAA, GDPR, IHE, DICOM, SNOMED CT, LOINC, or medical-device
  certification.

For identifiable data, deployment must provide authenticated HTTPS, least
privilege, secure transfer, retention and deletion policy, backups, incident
response, audit controls, and a documented privacy risk assessment.

## Standards boundary

The project is standards-aware and documents relevant boundaries, including:

- DICOM PS3.3, PS3.5, PS3.6, PS3.10, and PS3.16 concepts used by the
  application.
- DICOM Modality, SOP Class, transfer syntax, pixel spacing, windowing, and
  rescale metadata.
- DICOM SR TID 1500/1501/300/320 implementation scope.
- UCUM measurement units.
- DICOM Part 14/GSDF display-calibration boundary.
- RFC 4180-compatible CSV and RFC 8259-compatible JSON.
- Office Open XML XLSX.
- HIPAA/GDPR deployment-control boundaries.
- SNOMED CT and LOINC terminology licensing/version boundaries.
- IHE XDS-I.b, XCA-I, WADO-RS, STOW-RS, QIDO-RS, and ATNA integration
  planning boundaries.
- ACR/AAPM-oriented CT quality references.
- IBSI radiomics reference boundaries.

Relevant reference and boundary documentation is in
`docs/global_standards_baseline.md`. Standards references describe design
intent and implemented conventions; they do not by themselves establish
certification or clinical validation.

## Requirements

- Python 3.11 through 3.14.
- A working installation of `requirements.lock` or `requirements.txt`.
- Windows, macOS, or Linux.
- Optional NVIDIA GPU with compatible CUDA/PyTorch runtime.
- Optional TotalSegmentator installation.
- Optional MONAI Label server.
- Optional network access for Hugging Face, TCIA/NBIA, or MONAI Label
  integrations.

## Installation

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.lock
pip install -e ".[dev]"
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.lock
pip install -e ".[dev]"
```

Optional extras:

```bash
pip install -e ".[finetune]"
pip install -e ".[segmentation]"
```

Use `requirements.txt` rather than the lock file when intentionally updating
the dependency set.

## Running the application

Direct Streamlit launch:

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

Included launchers:

- Windows batch: `app.bat`
- Windows PowerShell: `HEEH-V1 DICOM Viewer.ps1`
- Compatibility PowerShell launcher: `launch.ps1`
- Linux/macOS shell launcher: `HEEH-V1 DICOM Viewer.sh`
- Compatibility shell launcher: `launch.sh`

The launchers bind to `127.0.0.1` by default. Do not expose the application to
a network without an authenticated HTTPS reverse proxy and deployment
security controls.

Useful environment variables:

- `HF_TOKEN`: optional Hugging Face access token.
- `MONAI_LABEL_URL`: optional MONAI Label server URL.
- Encryption-key variables documented by `core/security.py`.

## Fine-tuning

The optional fine-tuning path supports:

- Automatic CPU/CUDA device selection.
- Explicit `--device cpu|cuda|auto`.
- FP16 automatic mixed precision on CUDA.
- Gradient accumulation.
- Optional full fine-tuning.
- Layer freezing.
- Accuracy, Macro F1, ROC-AUC, confusion matrix, device, precision, seed, and
  package-version reporting.
- ONNX export and Torch/ONNX parity checks.
- Series-aware validation splitting when series identifiers are available.

Example:

```powershell
.\.venv\Scripts\python.exe scripts\finetune.py --help
```

Fine-tuning remains research-only and requires independent dataset governance,
split review, model validation, and reproducibility documentation.

## Testing and validation

Run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run linting:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

Check dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Run the navigation benchmark:

```powershell
.\.venv\Scripts\python.exe scripts\navigation_benchmark.py
```

The tests cover scientific helpers, metrics, DICOM privacy, export validation,
image preservation, modality detection, DICOM ordering, volume loading,
volumetric visualization, navigation caches, UI helpers, accessibility
contracts, logging, and fine-tuning plumbing. Passing tests demonstrate
software behavior against the test fixtures; they do not prove clinical
accuracy or regulatory compliance.

## Project structure

```text
.
|-- app.py                         # Active Streamlit application
|-- app.bat                        # Windows launcher
|-- HEEH-V1 DICOM Viewer.ps1      # Windows launcher
|-- HEEH-V1 DICOM Viewer.sh       # Linux/macOS launcher
|-- launch.ps1 / launch.sh        # Compatibility launchers
|-- core/                          # Shared domain and safety primitives
|   |-- dicom_ordering.py          # Physical DICOM slice ordering
|   |-- dicom_privacy.py           # De-identification and UID remapping
|   |-- export_validation.py       # Offline ZIP/export validator
|   |-- loaders.py                 # Cached volume/model loaders
|   |-- modality_detector.py       # DICOM modality and SOP detection
|   |-- modality_registry.py       # Capability registry
|   |-- navigation_benchmark.py   # Synthetic navigation benchmark
|   |-- standards.py               # Terminology/privacy boundaries
|   |-- tissue_classifier.py       # Tissue, edge, radiomics, XAI helpers
|   |-- volume_visualizer.py       # MIP/MPR/Plotly 3D
|   `-- security.py                # Optional encryption helpers
|-- engines/                       # Processing and inference engines
|   |-- clinical_metrics.py        # Segmentation and comparison metrics
|   |-- ct_calculator.py           # CT quantitative calculations
|   |-- finetune_trainer.py        # Research fine-tuning
|   |-- monai_preprocessor.py      # MONAI preprocessing
|   |-- onnx_inference.py          # ONNX provider selection
|   |-- sitk_registration.py       # SimpleITK resampling/registration
|   |-- tcia_dataset.py             # TCIA/cache dataset helpers
|   `-- anatomical_segmentation.py # Optional segmentation backends
|-- ui/                            # Compatibility UI exports
|-- utils/                         # Shared utility and AI helpers
|-- scripts/                       # Validation, benchmark, and maintenance CLIs
|-- tests/                         # Automated regression tests
|-- docs/                          # Standards and project documentation
|-- samples/                       # Optional publication demonstration assets
|-- data/                          # Development/sample data
|-- models/                        # Optional model assets and outputs
|-- requirements.txt               # Range-based dependencies
|-- requirements.lock              # Locked dependencies
|-- pyproject.toml                 # Package, pytest, and Ruff configuration
`-- .gitignore                     # Medical data, secrets, and runtime artifacts
```

`app.py` is the single active Streamlit runtime. `ui/clinical_app.py` is a
compatibility import and does not contain a second UI implementation.

## Publication sample set

The optional `samples/` directory contains a pseudonymous export archive,
interface screenshots, and a short demonstration video. It helps researchers
review the workflow without supplying patient data. The sample archive
contains representative DICOM, annotated image, measurement, radiomics, XLSX,
HTML, DICOM SR, and manifest outputs.

Validate the archive locally before redistribution:

```text
python scripts/validate_export.py samples/HEEH-V1_DICOM_Viewer_export.zip
```

The sample set is not a clinical dataset and must not be extended with
identifiable or unreviewed medical data.

## Known limitations

- The application is not a medical device and is not cleared or approved for
  patient care.
- Clinical accuracy is not established by unit tests or standards references.
- DICOM SR and PACS compatibility require independent validation.
- Burned-in pixel annotations require manual review or a validated redaction
  workflow.
- ZIP exports are not encrypted or access-controlled.
- SHA-256 provides integrity, not confidentiality or authenticity.
- Display calibration and DICOM GSDF conformance are deployment concerns.
- Non-DICOM volumes are generic unless modality metadata is supplied.
- Radiomics is not guaranteed to be fully IBSI-compliant.
- Demonstration AI models are not clinically validated.
- MIP/MPR/3D visualizations are research tools, not diagnostic workstation
  replacements.
- Large imports remain bounded by hardware, browser, upload, and storage
  limits.

## License

MIT. See [LICENSE](LICENSE).
