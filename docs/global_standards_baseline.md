# Global standards baseline

This project is a research and education application. The controls below are
implementation safeguards and integration boundaries; they do not constitute
HIPAA or GDPR certification, a SNOMED CT/LOINC license, IHE certification, or
medical-device approval.

## HIPAA and GDPR technical safeguards

- Direct patient identifiers are not rendered by default.
- The DICOM de-identification helper blanks or pseudonymizes only the
  attribute subset in `core.standards.PHI_FIELD_NAMES`; it does not apply the
  full DICOM PS3.15 Annex E Basic Application Level Confidentiality Profile.
  Identity-bearing elements inside sequences are not blanked (only their UIDs
  are remapped), and top-level attributes beyond `PHI_FIELD_NAMES` (e.g.
  StudyDescription, AdmittingDiagnosesDescription) are out of scope. The
  helper therefore deletes any inherited `PatientIdentityRemoved` marker
  instead of asserting `YES`; a `YES` assertion must come from a review of
  the complete output object. Generated synthetic DICOM SR reports are a
  separate path: they contain no source patient data and record their own
  accurate `DeidentificationMethod` (`Selected Identifiers Removed;
  UID Remapping`).
- Audit events use pseudonymous image references and redact PHI-like fields.
- The stable patient reference currently uses an unkeyed deterministic hash.
  It is susceptible to guessing for low-entropy identifiers and is not
  anonymization; keyed pseudonymization or a controlled random mapping needs a
  separately designed and reviewed migration before use where resistance to
  guessing is required.
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

## Research-readiness evidence status

Use these terms narrowly in project materials:

- **Implemented** means a code path exists.
- **Tested** means automated tests exercise the stated behavior on identified
  fixtures.
- **Independently validated** means an external reference, dataset, or
  validator was used and the exact protocol and results are reported.
- **Not established** means adequate evidence is not available.

Current evidence and its limits:

| Area | Status | Evidence and limit |
| --- | --- | --- |
| Core regression and static checks | Tested | The repository test suite, Ruff, and dependency consistency checks run locally and in the configured CI matrix; these do not establish scientific validity. |
| Image loading and display | Tested, format-specific | Synthetic DICOM CT/MR, compressed DICOM, NIfTI, NRRD, and MetaImage fixtures cover selected paths; they do not cover all encodings, vendors, SOP classes, orientations, or modalities. See the README support table. |
| IBSI radiomics | Independently validated, narrow scope | 270/270 comparisons are reported for the tested IBSI Configuration D CT phantom workflow. This is not full IBSI compliance or patient/population validation. |
| Public dataset benchmark | Partially validated, phantom only | The IBSI CT phantom image/mask are recorded with source commit and SHA-256; all 270 populated Configuration D rows passed through the configured Z-Rad reference pipeline. CT-Phantom4Radiomics remains metadata-only; no patient-level/generalization study is reported. |
| External radiomics comparison | Independently compared, narrow scope | PyRadiomics 3.0.1 matched four first-order features within 1e-6 on one deterministic synthetic 2D ROI. After a coarseness formula correction, all five NGTDM features matched PyRadiomics 3.0.1 within 1e-6 on one deterministic synthetic 2D ROI (8-neighborhood, force2D, matched fixed-bin-width settings); the comparison runs as a regression test gated on the optional `ibsi` dependency group. This does not validate other features, 3D aggregation, image encodings, patient data, or application-wide outputs. |
| Default viewer slice radiomics | Not Configuration D compliant | The viewer's default call analyzes a 2D unmasked slice; it is intentionally reported as not comparable, with no Configuration D pass/fail comparison. Separately, the PyRadiomics reference adapter assesses 66 IBSI reference-table rows and all 66 pass. Another 204 rows were not assessed because a defensible mapping was not established for this comparison; they are neither passes nor failures. The Z-Rad result must not be transferred to the default viewer path. Neither comparison establishes full IBSI compliance. |
| Export/privacy challenge checks | Tested on generated fixtures | The reported 20/20 valid and 20/20 invalid fixture results describe a small, constructed challenge set, not real-world privacy or de-identification performance. |
| Analysis run provenance | Partially implemented | IBSI Configuration D JSON includes image/mask fingerprints, application and dependency versions, environment, lockfile hash, UTC time, and a result digest. Other workflows do not yet emit this complete run record; local builds without revision metadata report source revision as unavailable. |
| Runtime and memory | Tested, synthetic microbenchmark only | Existing timing is for a synthetic navigation-cache workload. Python `tracemalloc` excludes native allocations, process RSS, decoding, inference, and end-to-end analysis. |
| Broad portability and accessibility | Partially tested | Current CI covers Ubuntu with Python 3.11 and 3.12. Accessibility helper tests are not a complete WCAG audit or assistive-technology evaluation. |
| Resistance of pseudonymous identifiers to guessing | Not established | Current identifiers are deterministic, unkeyed hashes; low-entropy identifiers may be guessed. Do not treat them as anonymized or resistant to re-identification. |
| Formal standards or clinical conformance | Not established | No ISO/IEC certification, DICOM/PACS conformance statement, clinical validation, or medical-device approval is claimed. |

## Prioritized research-readiness work

1. **Bound support claims.** Maintain the README's format and evidence matrix;
   add modalities, encodings, or operations only with a named implementation
   path and regression fixtures.
2. **Make benchmarks reproducible.** Treat the generated JSON and
   `public_benchmark_report.md` as the source of measured values. Record
   environment and dependency-lock fingerprint; label synthetic fixtures and
   allocation-only memory measurements. Do not merge results from different
   runs into a single claim.
3. **Extend end-to-end run provenance.** The IBSI Configuration D path now
   records versioned run provenance. Extend the same contract to each
   analysis/export, recording the application revision, exact dependency
   environment, input fingerprint, model/version/revision, preprocessing and
   analysis parameters, random seeds where relevant, and output hashes.
   Preserve privacy and avoid patient data in logs/manifests.
4. **Validate against independent evidence.** Use legally accessible,
   representative datasets, independent implementations, pre-specified
   methods, and uncertainty reporting. For generalizability claims, test
   relevant sites, scanners, populations, and modality-specific workflows;
   synthetic tests alone are insufficient.
5. **Measure portability and usability.** Define supported OS/Python/hardware
   combinations and representative low-resource devices; measure installation,
   startup, wall time, process memory, and task completion. Perform a WCAG
   2.2 AA assessment with keyboard and assistive-technology testing before
   claiming conformance.
6. **Obtain external review.** Independent domain, statistical, privacy, and
   interoperability review is required for publication claims that depend on
   those judgments. Dataset access, licensing, ethics approvals, and external
   validation cannot be manufactured by code changes.

## Required deployment controls

Before any clinical or identifiable-data deployment, complete a documented
security risk assessment, privacy impact assessment, access-control review,
retention policy, audit-log review, vulnerability management process, and
independent interoperability and display-quality validation.
