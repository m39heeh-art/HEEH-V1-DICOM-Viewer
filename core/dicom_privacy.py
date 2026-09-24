"""Explicit DICOM de-identification helpers for research workflows.

This is a convenience safeguard, not a certification of anonymization. The
caller remains responsible for validating the resulting files and handling
burned-in pixel annotations according to the study protocol.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pydicom
from pydicom.datadict import tag_for_keyword
from pydicom.uid import generate_uid

from core.standards import PHI_FIELD_NAMES, pseudonymous_identifier


def requires_pixel_review(dataset: pydicom.dataset.Dataset) -> bool:
    """Return whether pixel-level privacy review is mandatory before release."""
    if not isinstance(dataset, pydicom.dataset.Dataset):
        raise TypeError("dataset must be a pydicom Dataset")
    return str(getattr(dataset, "BurnedInAnnotation", "") or "").upper() == "YES"


def deidentify_dataset(
    dataset: pydicom.dataset.Dataset,
    *,
    replacement_prefix: str = "NEURO",
    keep_dates: bool = False,
) -> pydicom.dataset.Dataset:
    """Return a de-identified copy without changing pixel data.

    Private tags are removed. Direct identifiers are blanked, while the
    patient ID is replaced with a stable pseudonymous value derived from the
    original identifier. Dates are removed by default because temporal
    shifting requires a study-specific protocol.
    """
    if not isinstance(dataset, pydicom.dataset.Dataset):
        raise TypeError("dataset must be a pydicom Dataset")

    result = deepcopy(dataset)
    result.remove_private_tags()
    original_id = str(getattr(result, "PatientID", "") or "")
    pseudo_id = (
        f"{replacement_prefix}_{pseudonymous_identifier(original_id)}"
        if original_id
        else f"{replacement_prefix}_{pseudonymous_identifier('missing-patient-id')}"
    )

    for keyword in PHI_FIELD_NAMES:
        tag = tag_for_keyword(keyword)
        if tag is None or tag not in result:
            continue
        if keyword in result:
            if keyword == "PatientID":
                result.PatientID = pseudo_id
            elif keyword in {"PatientSex"}:
                result.PatientSex = ""
            elif keyword.endswith("Date") and keep_dates:
                continue
            else:
                result[keyword].value = ""

    # Use replacement UIDs so an exported object cannot be linked to the
    # original study through globally unique DICOM identifiers.
    uid_map = {}
    preserved_uid_keywords = {
        "SOPClassUID",
        "TransferSyntaxUID",
        "ImplementationClassUID",
        "MediaStorageSOPClassUID",
    }

    def _remap_uid(_dataset, element) -> None:
        keyword = element.keyword
        if element.VR != "UI" or keyword in preserved_uid_keywords:
            return
        value = element.value
        if isinstance(value, (list, tuple)):
            element.value = [
                uid_map.setdefault(str(uid), generate_uid()) for uid in value
            ]
        elif value:
            element.value = uid_map.setdefault(str(value), generate_uid())

    result.walk(_remap_uid)
    if getattr(result, "file_meta", None) is not None:
        result.file_meta.walk(_remap_uid)

    result.PatientName = "ANONYMOUS"
    result.PatientID = pseudo_id
    result.PatientIdentityRemoved = "YES"
    result.DeidentificationMethod = (
        "Descriptors; UID Remap; Dates Removed; Burned-In Review"
    )
    if hasattr(result, "BurnedInAnnotation"):
        result.BurnedInAnnotation = "YES" if requires_pixel_review(result) else "UNKNOWN"
    result.remove_private_tags()
    return result


def deidentify_bytes(data: bytes, **kwargs: Any) -> bytes:
    """De-identify a DICOM byte payload and return a serialized payload."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    from io import BytesIO

    dataset = pydicom.dcmread(BytesIO(data))
    output = BytesIO()
    deidentify_dataset(dataset, **kwargs).save_as(output)
    return output.getvalue()
