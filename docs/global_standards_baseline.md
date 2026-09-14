# Global standards baseline

This project is a research and education application. The controls below are
implementation safeguards and integration boundaries; they do not constitute
HIPAA or GDPR certification, a SNOMED CT/LOINC license, IHE certification, or
medical-device approval.

## HIPAA and GDPR technical safeguards

- Direct patient identifiers are not rendered by default.
- Audit events use pseudonymous image references and redact PHI-like fields.
- The existing encryption helpers require an explicitly configured key and do
  not provide an insecure default.
- Production deployment must still provide identity and access management,
  least privilege, TLS, secure secrets, retention/deletion procedures, backup
  protection, incident response, risk analysis, and processor/controller
  agreements where applicable.

## SNOMED CT and LOINC

`core/standards.py` centralizes terminology integration points. The project
does not invent clinical codes: production code systems must use licensed,
versioned SNOMED CT and LOINC value sets appropriate to the implementation.
The application must not present local placeholders as clinical codes.

## IHE and DICOMweb

The planned interoperability boundary is explicitly documented for
XDS-I.b, XCA-I, WADO-RS, STOW-RS, QIDO-RS, ATNA, and the IHE CT profile.
Actual conformance requires endpoint configuration, TLS certificates,
authentication, transaction validation, audit transport, and interoperability
testing against the target PACS/EHR.

## Export provenance and interoperability

Consolidated exports include `export_manifest.json`. The manifest records UTC
generation time, SHA-256
hashes, media types, source label, measurement count, encoding conventions,
privacy limitations, and the standards boundary. Measurement CSV/JSON files
preserve native-pixel coordinates, calibration, units, and measurement values.
CSV uses UTF-8 with BOM and RFC 4180-compatible quoting; JSON is RFC 8259
compatible; XLSX is Office Open XML; PNG overlays carry embedded measurement
JSON; DICOM SR uses UCUM units and the implemented TID 1500/1501/300/320
content structure where applicable.

These are interoperability safeguards, not a formal conformance statement.
Each deployment must validate exported DICOM and SR against its target
validator/PACS, inspect burned-in annotations, confirm privacy requirements,
and document the applicable terminology licenses and profiles.

## Required deployment controls

Before any clinical or identifiable-data deployment, complete a documented
security risk assessment, privacy impact assessment, access-control review,
retention policy, audit-log review, vulnerability management process, and
independent interoperability and display-quality validation.
