# Standards and conformance boundaries

This document maps selected HEEH-V1 behaviors to relevant standards and
records the scope of available evidence. A standards reference or passing
software test does not establish formal conformance, certification, clinical
validity, or interoperability with a particular system.

## DICOM image handling

| Behavior | Relevant standard | Evidence in this release | Boundary |
|---|---|---|---|
| Stored pixel values and rescale slope/intercept | DICOM PS3.3, Image Pixel Module | Synthetic CT tests cover selected rescale cases | Does not validate every modality, vendor, transfer syntax, or image object |
| Pixel spacing and calibrated measurements | DICOM PS3.3, Pixel Measures Macro | Unit tests cover selected isotropic and anisotropic spacing cases | Independent phantom validation is required before using measurements as research endpoints |
| Windowing and monochrome presentation | DICOM PS3.3, VOI LUT Module | Tests cover the implemented LINEAR window function and MONOCHROME1 display handling | Alternative VOI LUT functions and presentation states are not established |
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

## Radiomics and quantitative analysis

The default slice-based radiomics view is exploratory. It does not use the
three-dimensional image, aligned ROI mask, and processing configuration
required for the reported IBSI Configuration D comparison. Do not describe
default-viewer results as IBSI-compliant.

The release evidence package reports 270 of 270 populated Configuration D
reference rows passing in the configured CT-phantom comparison workflow. The
comparison uses licensed reference materials and the Z-Rad reference
pipeline. The evidence package also reports a separate PyRadiomics comparison
with 58 of 66 comparable rows passing, 8 failing, and 204 unsupported. These
are distinct comparisons; neither result establishes full IBSI Phase 1 or
Phase 2 compliance, performance on patient data, or generalizability.

See `ibsi_ct_subset.md` and
`../verification/publication_package/02_Evidence/public_benchmark_report.md`
for methods, result artifacts, and limitations.

## Privacy and security

The export code applies a selected set of DICOM attribute transformations and
UID remapping. It does not implement the complete DICOM PS3.15 Basic
Application Level Confidentiality Profile. Sequence contents, unlisted
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

- `../RELEASE_NOTES_v1.0.2.md` for software version and validation summary
- `VERIFICATION_EVIDENCE.md` for the measured evidence and test scope
- `../verification/publication_package/02_Evidence/` for machine-readable results and reports
- `../verification/README_DATA.md` for optional licensed reference data
