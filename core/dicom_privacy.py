"""Explicit DICOM de-identification helpers for research workflows.

This is a convenience safeguard, not a certification of anonymization. The
caller remains responsible for validating the resulting files and handling
burned-in pixel annotations according to the study protocol.

Scope of the de-identification: only the selected attribute set listed in
:data:`core.standards.PHI_FIELD_NAMES` is blanked or pseudonymized, including
matching elements nested in sequences. This does NOT apply the full DICOM
PS3.15 Annex E Basic Application Level Confidentiality Profile: unlisted
attributes, free-text values, and burned-in pixel text may still identify a
person. Accordingly, ``deidentify_dataset`` deletes any inherited
``PatientIdentityRemoved`` marker instead of asserting ``YES``: the removal
must be attested by whoever reviews the complete output object. When
``BurnedInAnnotation`` is present its value is left unchanged because pixel
data is not reviewed here.
"""

from __future__ import annotations

from copy import deepcopy
import secrets
from typing import Any

import pydicom
from pydicom.uid import generate_uid

from core.standards import PHI_FIELD_NAMES, pseudonymous_identifier

_RETAINABLE_DATE_KEYWORDS = frozenset(
    {
        "StudyDate",
        "SeriesDate",
        "AcquisitionDate",
        "ContentDate",
        "PerformedProcedureStepStartDate",
        "PerformedProcedureStepEndDate",
    }
)


def requires_pixel_review(dataset: pydicom.dataset.Dataset) -> bool:
    """Return whether pixel-level privacy review is mandatory before release."""
    if not isinstance(dataset, pydicom.dataset.Dataset):
        raise TypeError("dataset must be a pydicom Dataset")
    return str(getattr(dataset, "BurnedInAnnotation", "") or "").upper() != "NO"


def deidentify_dataset(
    dataset: pydicom.dataset.Dataset,
    *,
    replacement_prefix: str = "NEURO",
    keep_dates: bool = False,
) -> pydicom.dataset.Dataset:
    """Return a de-identified copy without changing pixel data.

    Private tags are removed. Direct identifiers are blanked, while the
    patient ID is replaced with a stable, deterministic hash of the original
    identifier. This is not anonymization and may be vulnerable to guessing
    attacks. Date elements are removed by default because temporal shifting
    requires a study-specific protocol. When ``keep_dates=True`` only the
    selected study, series, acquisition, content, and procedure-step dates are
    retained; patient-specific and unlisted date elements remain removed.
    Time elements are always blanked. ``DeidentificationMethod`` reports this
    partial retention so exported metadata never claims complete date removal.
    This helper does not attest that all identifying
    information has been removed, so it removes any inherited
    ``PatientIdentityRemoved`` marker. Burned-in annotation status is left
    unchanged because pixel data is not reviewed here.
    """
    if not isinstance(dataset, pydicom.dataset.Dataset):
        raise TypeError("dataset must be a pydicom Dataset")

    result = deepcopy(dataset)
    result.remove_private_tags()
    original_id = str(getattr(result, "PatientID", "") or "")
    pseudo_id = (
        f"{replacement_prefix}_{pseudonymous_identifier(original_id)}"
        if original_id
        else f"{replacement_prefix}_{secrets.token_hex(8)}"
    )

    def _clean_identifiers(_container, element) -> None:
        keyword = element.keyword
        if element.VR in {"DA", "DT", "TM"}:
            if (
                element.VR == "DA"
                and keep_dates
                and keyword in _RETAINABLE_DATE_KEYWORDS
            ):
                return
            element.value = ""
            return
        if keyword in PHI_FIELD_NAMES or element.VR == "PN":
            if element.VR == "SQ":
                element.value = []
            elif keyword == "PatientID":
                element.value = pseudo_id
            else:
                element.value = ""

    # Use replacement UIDs so an exported object cannot be linked to the
    # original study through globally unique DICOM instance identifiers.
    uid_map = {}

    def _remap_uid(_dataset, element) -> None:
        keyword = element.keyword
        if (
            element.VR != "UI"
            or keyword.endswith("SOPClassUID")
            or keyword in {"TransferSyntaxUID", "ImplementationClassUID"}
        ):
            return
        value = element.value
        if isinstance(value, (list, tuple)):
            element.value = [
                uid_map.setdefault(str(uid), generate_uid()) for uid in value
            ]
        elif value:
            element.value = uid_map.setdefault(str(value), generate_uid())

    result.walk(_clean_identifiers)
    result.walk(_remap_uid)
    if getattr(result, "file_meta", None) is not None:
        result.file_meta.walk(_remap_uid)

    result.PatientName = "ANONYMOUS"
    result.PatientID = pseudo_id
    if "PatientIdentityRemoved" in result:
        del result.PatientIdentityRemoved
    # Only selected *Date* elements honor keep_dates; *Time* elements are
    # always blanked. DeidentificationMethod (LO, VM 1-n) is multi-valued.
    date_handled = (
        ["Selected Dates Retained", "Other Dates Removed"]
        if keep_dates
        else ["Dates Removed"]
    )
    date_handled.extend(["DateTime Removed", "Times Removed"])
    result.DeidentificationMethod = [
        "Selected Identifiers Removed",
        "UID Remap",
        *date_handled,
        "Burned-In Annotation Review Required",
    ]
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
