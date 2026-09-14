import pytest

from core.security import (
    EncryptionConfigurationError,
    decrypt_bytes,
    encrypt_bytes,
    encryption_key_from_environment,
    generate_key,
)
from core.dicom_privacy import deidentify_dataset
from core.standards import (
    compliance_boundary,
    pseudonymous_identifier,
    redact_phi_mapping,
)
from pydicom.dataset import Dataset


def test_standards_helpers_minimize_phi_in_audit_context():
    redacted = redact_phi_mapping({
        "PatientName": "Example^Patient",
        "PatientID": "123",
        "modality": "CT",
    })
    assert redacted["PatientName"] == "[REDACTED]"
    assert redacted["PatientID"] == "[REDACTED]"
    assert redacted["modality"] == "CT"
    assert pseudonymous_identifier("123") != "123"
    assert set(compliance_boundary()) == {"HIPAA", "GDPR", "SNOMED_CT_LOINC", "IHE"}


def test_encrypt_decrypt_round_trip():
    key = generate_key()
    payload = b"medical image bytes"
    token = encrypt_bytes(payload, key)
    assert token != payload
    assert decrypt_bytes(token, key) == payload


def test_decrypt_rejects_wrong_key():
    token = encrypt_bytes(b"protected", generate_key())
    with pytest.raises(ValueError, match="invalid or the key"):
        decrypt_bytes(token, generate_key())


def test_environment_key_is_required(monkeypatch):
    monkeypatch.delenv("NEUROPROJECT_ENCRYPTION_KEY", raising=False)
    with pytest.raises(EncryptionConfigurationError):
        encryption_key_from_environment()


def test_dicom_deidentification_preserves_pixel_data_and_replaces_identifiers():
    dataset = Dataset()
    dataset.PatientName = "Example^Patient"
    dataset.PatientID = "patient-123"
    dataset.StudyID = "study-456"
    dataset.InstitutionName = "Example Hospital"
    dataset.PixelData = b"\x01\x02"

    clean = deidentify_dataset(dataset)

    assert clean.PatientName == "ANONYMOUS"
    assert clean.PatientID.startswith("NEURO_")
    assert clean.StudyID == ""
    assert clean.InstitutionName == ""
    assert clean.PixelData == dataset.PixelData


def test_dicom_deidentification_marks_burned_in_annotation_review():
    dataset = Dataset()
    dataset.PatientID = "patient-123"
    dataset.BurnedInAnnotation = "YES"

    clean = deidentify_dataset(dataset)

    assert clean.BurnedInAnnotation == "YES"
    assert "Burned-In Review" in clean.DeidentificationMethod
