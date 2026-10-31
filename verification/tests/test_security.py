import pytest

from core.security import (
    EncryptionConfigurationError,
    decrypt_bytes,
    encrypt_bytes,
    encryption_key_from_environment,
    generate_key,
)
from core.dicom_privacy import deidentify_dataset, requires_pixel_review
from core.standards import (
    compliance_boundary,
    pseudonymous_identifier,
    redact_phi_mapping,
)
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import CTImageStorage, generate_uid


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
    assert "PatientIdentityRemoved" not in clean


def test_dicom_deidentification_cleans_nested_identifiers_and_preserves_sop_class():
    dataset = Dataset()
    dataset.PatientID = "patient-123"
    dataset.StudyDescription = "Patient Example"
    observer = Dataset()
    observer.PersonName = "Example^Observer"
    observer.VerifyingObserverName = "Example^Verifier"
    observer.InstitutionName = "Example Hospital"
    observer.ReferencedSOPClassUID = CTImageStorage
    original_instance_uid = generate_uid()
    observer.ReferencedSOPInstanceUID = original_instance_uid
    dataset.VerifyingObserverSequence = Sequence([observer])

    clean = deidentify_dataset(dataset)
    clean_observer = clean.VerifyingObserverSequence[0]

    assert clean.StudyDescription == ""
    assert clean_observer.PersonName == ""
    assert clean_observer.VerifyingObserverName == ""
    assert clean_observer.InstitutionName == ""
    assert clean_observer.ReferencedSOPClassUID == CTImageStorage
    assert clean_observer.ReferencedSOPInstanceUID != original_instance_uid


def test_deidentification_retains_only_selected_da_on_request():
    dataset = Dataset()
    dataset.PatientID = "patient-123"
    dataset.StudyDate = "20240101"
    dataset.PatientBirthDate = "19700101"
    dataset.LastMenstrualDate = "20240101"
    dataset.InstanceCreationDate = "20240101"
    dataset.AcquisitionDateTime = "20240101123456+0000"
    dataset.AcquisitionTime = "123456"

    cleaned = deidentify_dataset(dataset)
    retained = deidentify_dataset(dataset, keep_dates=True)

    assert cleaned.StudyDate == ""
    assert cleaned.AcquisitionDateTime == ""
    assert cleaned.AcquisitionTime == ""
    assert retained.StudyDate == "20240101"
    assert retained.PatientBirthDate == ""
    assert retained.LastMenstrualDate == ""
    assert retained.InstanceCreationDate == ""
    assert retained.AcquisitionDateTime == ""
    assert retained.AcquisitionTime == ""
    assert "Selected Dates Retained" in retained.DeidentificationMethod
    assert "Other Dates Removed" in retained.DeidentificationMethod


def test_dicom_deidentification_marks_burned_in_annotation_review():
    dataset = Dataset()
    dataset.PatientID = "patient-123"
    dataset.BurnedInAnnotation = "YES"

    clean = deidentify_dataset(dataset)

    assert clean.BurnedInAnnotation == "YES"
    assert "Burned-In Annotation Review Required" in clean.DeidentificationMethod
    assert "PatientIdentityRemoved" not in clean
    assert requires_pixel_review(clean)


def test_dicom_without_burned_in_annotation_does_not_require_pixel_review():
    dataset = Dataset()
    dataset.PatientID = "patient-123"
    dataset.BurnedInAnnotation = "NO"

    assert not requires_pixel_review(dataset)


def test_missing_or_unknown_burned_in_annotation_requires_pixel_review():
    dataset = Dataset()
    assert requires_pixel_review(dataset)

    dataset.BurnedInAnnotation = "UNKNOWN"
    assert requires_pixel_review(dataset)


def test_deidentification_preserves_burned_in_annotation_status():
    dataset = Dataset()
    dataset.PatientID = "patient-123"
    dataset.BurnedInAnnotation = "NO"

    clean = deidentify_dataset(dataset)

    assert clean.BurnedInAnnotation == "NO"
    assert not requires_pixel_review(clean)
