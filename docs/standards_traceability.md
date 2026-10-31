# Standards and conformance boundaries

This document maps selected HEEH-V1 behaviors to relevant standards and
records the scope of available evidence. A standards reference or passing
software test does not establish formal conformance, certification, clinical
validity, or interoperability with a particular system.

## DICOM image handling

| Behavior | Relevant standard | Evidence in this release | Boundary |
|---|---|---|---|
| Stored pixel values and rescale slope/intercept | DICOM PS3.3, Image Pixel Module | Synthetic CT tests cover selected rescale cases | Does not validate every modality, vendor, transfer syntax, or image object |
| Pixel spacing and calibrated measurements | DICOM PS3.3, Pixel Measures Macro | Unit tests cover selected isotropic and anisotropic top-level spacing cases; shared and uniform per-frame spacing are resolved; malformed spacing is rejected and CT NPS is withheld without spacing | Varying or incomplete per-frame spacing is withheld; independent phantom accuracy is not established |
| Windowing and monochrome presentation | DICOM PS3.3, VOI LUT Module | Tests cover LINEAR, LINEAR_EXACT, SIGMOID, selectable VOI LUTs, and MONOCHROME1 display handling | Presentation States, GSDF calibration, and end-to-end display conformance are not established |
| DICOM file reading and exported objects | DICOM PS3.5 and PS3.10 | Automated tests cover selected file parsing, export, and re-import paths | No formal DICOM conformance statement or live PACS interoperability claim |
| Structured Report output | DICOM PS3.16 | The project records an independent `dicom-validator` check for a test SR fixture | A fixture-level result does not validate every SR content combination or receiving system |

## Measurement and data formats

| Behavior | Relevant standard | Evidence in this release | Boundary |
|---|---|---|---|
| Measurement units | Unified Code for Units of Measure (UCUM) | Unit tests and export round trips cover selected units including `mm`, `cm`, `px`, and `deg` | Does not certify every unit-bearing field or downstream consumer |
| CSV output | RFC 4180 conventions | Export tests cover the implemented CSV structure and encoding | RFC 4180 is informational and implementations vary |
| JSON output | RFC 8259 | JSON exports and manifests are parsed in tests | Schema compatibility is project-specific unless a schema is separately published |
| XLSX output | Office Open XML | Export tests cover generated workbooks | Does not certify compatibility with every spreadsheet application |
| NIfTI and other volume formats | Format-specific specifications and library behavior | Synthetic fixtures cover selected NIfTI, NRRD, and MetaImage paths | The full format and orientation space is not validated |

For constant or machine-precision-degenerate samples, the exploratory
skewness/kurtosis output uses the application's finite `0.0` sentinel instead
of evaluating undefined standardized moments. Treat that sentinel as
degenerate, not as an estimated moment.

The cohort CSV records a SHA-256 hash of each source file's bytes. This
fingerprint supports integrity and reproducibility checks; it is not
de-identification, and known public images may be matched by hash.

The cohort export does not apply ComBat harmonization. It does not collect
validated scanner/site batch identifiers or biological covariates, and
modality is not a valid batch label for harmonizing unlike signal scales.
Requests through the compatibility API are refused and raw statistics are
preserved. The standalone harmonization engine does not validate this cohort
workflow.

## Radiomics and quantitative analysis

The default slice-based radiomics view is exploratory. It does not use the
three-dimensional image, aligned ROI mask, and processing configuration
required for the reported IBSI Configuration D comparison. Do not describe
default-viewer results as IBSI-compliant.

IBSI 1 Configurations A-E are implemented as opt-in workflows on the
imported-mask CT path. A applies 2D extraction on the source grid with
[-500, 400] HU re-segmentation; B applies 2D in-plane 2 x 2 mm interpolation
and [-500, 400] HU re-segmentation; C applies 3D isotropic 2 mm interpolation
and [-1000, 400] HU re-segmentation; D applies 3-SD outlier re-segmentation;
E uses cubic B-spline image interpolation, fixed-range plus 3-SD
re-segmentation, and 1000-bin IVH. The A-E official CT-phantom comparison
reports 346/346, 346/346, 210/210, 270/270, and 210/210 populated feature
rows, respectively; 60 diagnostic rows per A/B/C/E are not assessed. These
use the same Z-Rad reference engine as the application and are not independent
implementation validation. None of these results
establishes full IBSI compliance, patient-data performance, or
generalizability; no compliance statement can be derived from them. When a
degenerate ROI makes a feature family
mathematically undefined, the report lists that family under
`unsupported_families` with the engine's reason instead of silently
omitting it.

The digital-phantom reference check compares all 482 populated reference
rows: 481 pass and `szm_lzhge_3D` does not (1494.6 measured vs. 1490
published, tolerance 0). PyRadiomics 3.0.1 independently returns 1494.6.
The tag-level inventory maps all 172 definitions. All 167 definitions with
published reference values have implementation outputs. The other five have
no reference values and the official IBSI feature manual explicitly says they
should not be used: OMBB volume/area density (`ZH1A`, `IQYR`), MVEE
volume/area density (`SWZ1`, `BRI8`), and IVH AUC (`9CMM`). Their absence is
therefore not a missing recommended implementation. See the
[official feature manual](https://ibsi.readthedocs.io/en/latest/03_Image_features.html).
The manual lists permanent identifiers for 171 definitions, omits the
identifier for `szm_sze`, and repeats `1PR8` for `ih_min` and `ih_p10`. The
inventory records these source inconsistencies rather than inferring a
replacement identifier. Each A–E result also exports an IBSI reporting
checklist for items 1–76, with values sourced from the configuration and an
allowlist of DICOM acquisition/reconstruction tags; unavailable study-level
information is explicitly marked. This checklist is not complete reporting
or a compliance claim.
Two IVH difference values are additional derived outputs outside the
172-definition inventory. The `szm_lzhge_3D` reference discrepancy
is internally inconsistent with IBSI's own published digital-phantom GLSZM
matrix: applying the specified feature formula to that five-zone matrix
yields 1494.6, matching both Z-Rad and PyRadiomics, while the feature table
lists 1490. The discrepancy is root-caused as an upstream-internal
inconsistency — the currently published IBSI-1 submission workbook is
byte-identical to the pinned copy — and the row is deliberately still
reported as a mismatch rather than forced to pass; see
[the resolution document](ibsi_digital_phantom_glszm_lzhge_resolution.md).
Lack of broader independent validation still blocks a full
feature-validation claim.

The release evidence package reports 270 of 270 populated Configuration D
reference rows passing in the configured CT-phantom comparison workflow. The
comparison uses licensed reference materials and the same Z-Rad pipeline as
the application. The evidence package also reports a separate PyRadiomics comparison
with all 75 assessed rows passing. The remaining 195 reference rows are
categorized in the machine-readable verifier output; they are neither passes
nor failures. This is distinct from the
Z-Rad comparison; neither result establishes full IBSI Phase 1 or Phase 2
compliance, performance on patient data, or generalizability. Shape features
are computed from the original ROI mask; intensity re-segmentation is applied
to intensity features only.

See `ibsi_ct_subset.md` and `VERIFICATION_EVIDENCE.md` for methods and
limitations. Rebuild machine-readable benchmark results with
`../scripts/public_benchmark_evidence.py`; generated result files are local
and Git-ignored.

## Privacy and security

The export code applies a selected set of DICOM attribute transformations,
including recursive cleaning of selected identifier fields, and UID remapping
that preserves SOP Class UIDs. It does not implement the complete DICOM PS3.15
Basic Application Level Confidentiality Profile. Free-text values, unlisted
attributes, burned-in pixel text, and date-shift requirements need separate
review.

Deterministic, unkeyed identifiers are pseudonyms, not anonymization. Archive
validation and generated challenge fixtures do not measure real-world
de-identification performance. Do not place identifiable health information
in this application unless an organization has approved the deployment,
access controls, data handling, and privacy review.

## Clinical, regulatory, and deployment boundaries

HEEH-V1 is research and education software. The project does not claim
clinical validation, medical-device approval, HIPAA or GDPR certification,
formal IHE conformance, or formal DICOM conformance. Standards references in
the code and documentation identify implementation targets or technical
conventions; they are not endorsements or certificates.

Before an organization uses exported data in a research workflow, it should
independently validate the applicable privacy profile, DICOM/SR outputs,
display chain, terminology licenses, and receiving systems. Clinical use is
outside the stated scope.

## Release evidence

For reproducible release-specific results, see:

- `../RELEASE_NOTES_v1.0.3.md` for software version and validation summary
- `VERIFICATION_EVIDENCE.md` for the measured evidence and test scope
- `../scripts/public_benchmark_evidence.py` for regenerating machine-readable benchmark results
- `../verification/README_DATA.md` for optional licensed reference data
