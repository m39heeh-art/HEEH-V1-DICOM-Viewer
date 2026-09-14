"""Interoperability and privacy safeguards used by the research application.

These declarations and helpers support standards-aware implementation. They
do not constitute HIPAA/GDPR certification, a SNOMED CT/LOINC license, or
IHE integration certification.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


# SNOMED CT concept identifiers for the image modalities represented here.
SNOMED_CT_MODALITY_CONCEPTS = {
    "CT": "77477000",       # Computed tomography
    "MR": "113091000",      # Magnetic resonance imaging
    "CR": "39714003",       # Plain radiography
    "DX": "39714003",       # Plain radiography
    "US": "IMG-ULTRASOUND", # Local placeholder: bind to licensed terminology
    "PT": "363680008",      # Positron emission tomography
}

# LOINC identifiers are intentionally represented as extension points. A
# modality is not itself a universal LOINC observation code; deployments must
# select the licensed observation/profile code for their use case.
LOINC_OBSERVATION_PROFILES = {
    "image_quality": "LOINC-IMAGE-QUALITY-PROFILE",
    "radiology_report": "LOINC-RADIOLOGY-REPORT-PROFILE",
}

# IHE profiles relevant to a future PACS/EHR boundary.
IHE_INTEGRATION_PROFILES = (
    "XDS-I.b",
    "XCA-I",
    "WADO-RS",
    "STOW-RS",
    "QIDO-RS",
    "ATNA",
    "CT",
)

PHI_FIELD_NAMES = frozenset({
    "PatientName",
    "PatientID",
    "IssuerOfPatientID",
    "OtherPatientIDs",
    "OtherPatientNames",
    "PatientBirthDate",
    "PatientSex",
    "AccessionNumber",
    "StudyID",
    "ReferringPhysicianName",
    "InstitutionName",
    "InstitutionAddress",
    "InstitutionalDepartmentName",
    "StationName",
    "PerformingPhysicianName",
    "OperatorsName",
    "DeviceSerialNumber",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "StudyDate",
    "SeriesDate",
    "AcquisitionDate",
    "ContentDate",
    "StudyTime",
    "SeriesTime",
    "AcquisitionTime",
    "ContentTime",
})


def pseudonymous_identifier(value: Any, *, namespace: str = "neuroproject") -> str:
    """Create a non-reversible identifier for logs and internal references."""
    digest = hashlib.sha256(
        f"{namespace}:{value}".encode("utf-8", errors="replace")
    ).hexdigest()
    return digest[:16]


def redact_phi_mapping(values: dict[str, Any]) -> dict[str, Any]:
    """Return a log-safe copy with direct DICOM identifiers removed."""
    result = {}
    for key, value in values.items():
        if key in PHI_FIELD_NAMES or re.search(
            r"(patient|name|birth|accession|physician|institution)",
            str(key),
            re.IGNORECASE,
        ):
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


def compliance_boundary() -> dict[str, str]:
    """Describe what the application enforces versus deployment obligations."""
    return {
        "HIPAA": (
            "Application supports minimum-necessary display, PHI-safe logs, "
            "encrypted-byte helpers, and access-control integration points; "
            "deployment must provide authentication, authorization, TLS, "
            "retention, backups, incident response, and risk analysis."
        ),
        "GDPR": (
            "Application minimizes displayed identifiers and supports "
            "pseudonymous audit references; deployment must establish a lawful "
            "basis, notices, data-subject rights, retention, DPIA, and DPA."
        ),
        "SNOMED_CT_LOINC": (
            "Identifiers are centralized as terminology integration points; "
            "production clinical coding requires the applicable licenses and "
            "versioned value sets."
        ),
        "IHE": (
            "Relevant profiles are declared for integration planning; actual "
            "XDS-I/IHE and DICOMweb conformance requires validated endpoints, "
            "certificates, transactions, and interoperability testing."
        ),
    }
