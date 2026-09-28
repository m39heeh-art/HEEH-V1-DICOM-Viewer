"""
Modality Detector - Automatic DICOM modality identification.

Reads the DICOM Modality tag (0008,0060) and, when present, the SOP Class
UID (0008,0016), then resolves the canonical modality through
core.modality_registry.  When the Modality tag is absent, the SOP Class
UID is used as a fallback source of inference.

Reference: DICOM PS3.3 Table C.3-1 (Defined Terms for Modality) and
DICOM PS3.6 (SOP Class UIDs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.modality_registry import (
    MODALITY_REGISTRY,
    ModalitySpec,
    get_spec,
    is_rejected,
    is_supported,
    resolve_modality,
)


@dataclass(frozen=True)
class ModalityDetection:
    """Result of a modality detection pass over one DICOM object."""

    detected_modality: Optional[str]
    raw_modality: Optional[str]
    sop_class_uid: Optional[str]
    spec: Optional[ModalitySpec]
    supported: bool
    rejected: bool
    sop_class_match: bool
    reason: str
    source: str = ""

    @property
    def modality(self) -> Optional[str]:
        """Canonical registry key of the detected modality (if any)."""
        return self.detected_modality

    @property
    def display_name(self) -> str:
        """Human-readable modality name for UI display."""
        if self.spec is not None:
            return self.spec.name
        return (self.raw_modality or "Unknown").strip() or "Unknown"

    @property
    def is_displayable(self) -> bool:
        """True when the object may be displayed and analyzed."""
        return self.supported and not self.rejected

    def to_dict(self) -> dict:
        """Return a JSON-serializable summary for Streamlit display."""
        return {
            "detected_modality": self.detected_modality,
            "raw_modality": self.raw_modality,
            "sop_class_uid": self.sop_class_uid,
            "display_name": self.display_name,
            "supported": self.supported,
            "rejected": self.rejected,
            "sop_class_match": self.sop_class_match,
            "is_displayable": self.is_displayable,
            "reason": self.reason,
            "source": self.source,
        }

    @property
    def required_dicom_tags(self) -> tuple[str, ...]:
        """Return the registry-declared tags required for this modality."""
        if self.spec is None:
            return ()
        return tuple(self.spec.required_dicom_tags)


class ModalityDetector:
    """
    Detect the imaging modality of a DICOM object.

    Detection is primary-keyed on the Modality tag (0008,0060) and
    cross-checked against the SOP Class UID (0008,0016) from the registry.
    """

    TAG_MODALITY = (0x0008, 0x0060)
    TAG_SOP_CLASS_UID = (0x0008, 0x0016)

    # ------------------------------------------------------------------
    # Detection entry points
    # ------------------------------------------------------------------
    def detect(self, dataset) -> ModalityDetection:
        """Detect the modality from a pydicom Dataset (or dict-like object)."""
        modality = self._read_keyword(dataset, "Modality")
        sop_class_uid = self._read_keyword(dataset, "SOPClassUID")
        return self.detect_from_tags(modality, sop_class_uid)

    @classmethod
    def detect_from_tags(
        cls, modality: Optional[str] = None, sop_class_uid: Optional[str] = None
    ) -> ModalityDetection:
        """Detect the modality from raw tag values (no dataset required)."""
        modality = cls._normalize(modality)
        sop_class_uid = cls._normalize(sop_class_uid)

        if not modality and not sop_class_uid:
            return ModalityDetection(
                detected_modality=None,
                raw_modality=modality,
                sop_class_uid=sop_class_uid,
                spec=None,
                supported=False,
                rejected=False,
                sop_class_match=False,
                reason=(
                    "Cannot identify imaging modality: both Modality tag "
                    "(0008,0060) and SOP Class UID (0008,0016) are missing."
                ),
            )

        # Resolve canonical modality, preferring the Modality tag and
        # falling back to SOP Class UID inference.
        source = ""
        canonical = resolve_modality(modality) if modality else None
        if canonical is not None:
            source = "modality_tag"
        else:
            canonical = cls._infer_from_sop(sop_class_uid)
            if canonical is not None:
                source = "sop_class_inference"

        if canonical is None:
            unknown = modality or sop_class_uid or "value"
            return ModalityDetection(
                detected_modality=None,
                raw_modality=modality,
                sop_class_uid=sop_class_uid,
                spec=None,
                supported=False,
                rejected=False,
                sop_class_match=False,
                reason=(
                    f"Unknown or unsupported modality "
                    f"'{unknown}' (check DICOM registry)."
                ),
                source=source,
            )

        spec = get_spec(canonical)
        if spec is None:
            return ModalityDetection(
                detected_modality=canonical,
                raw_modality=modality,
                sop_class_uid=sop_class_uid,
                spec=None,
                supported=False,
                rejected=False,
                sop_class_match=False,
                reason=f"Modality '{canonical}' resolved but has no registry spec.",
                source=source,
            )

        sop_match = False
        if sop_class_uid and spec.sop_classes:
            sop_match = sop_class_uid in spec.sop_classes

        displayable = is_supported(canonical)
        rejected = is_rejected(canonical)
        reason = cls._build_reason(
            spec, sop_class_uid, sop_match, displayable, rejected
        )

        return ModalityDetection(
            detected_modality=canonical,
            raw_modality=modality,
            sop_class_uid=sop_class_uid,
            spec=spec,
            supported=displayable,
            rejected=rejected,
            sop_class_match=sop_match,
            reason=reason,
            source=source,
        )

    def detect_supported(self, dataset) -> bool:
        """Return True only when the object is displayable and analyzable."""
        detection = self.detect(dataset)
        return detection.is_displayable and not missing_required_tags(
            dataset, detection
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @classmethod
    def _build_reason(
        cls,
        spec: ModalitySpec,
        sop_class_uid: Optional[str],
        sop_match: bool,
        displayable: bool,
        rejected: bool,
    ) -> str:
        """Compose a human-readable verdict for the detection result."""
        if rejected:
            return (
                f"{spec.name}: structural DICOM object "
                "(RT structure/plan, SR, encapsulated); not displayable."
            )
        if sop_class_uid and not sop_match:
            return (
                f"{spec.name}: Modality tag '{spec.dicom_modality}' resolved, "
                f"but SOP Class UID {sop_class_uid} does not match the "
                f"registered SOP classes for this modality."
            )
        if not displayable:
            return f"{spec.name}: recognized but not enabled for analysis."
        return f"{spec.name}: modality detected and supported."

    @classmethod
    def _infer_from_sop(cls, sop_class_uid: Optional[str]) -> Optional[str]:
        """Return the registry key owning the given SOP Class UID, if any."""
        if not sop_class_uid:
            return None
        for key, candidate in MODALITY_REGISTRY.items():
            if sop_class_uid in candidate.sop_classes:
                return key
        return None

    @staticmethod
    def _read_keyword(dataset, keyword: str) -> Optional[str]:
        """Read a DICOM keyword from a Dataset, tolerating missing tags."""
        if dataset is None:
            return None
        try:
            value = getattr(dataset, keyword)
        except Exception:
            return None
        return ModalityDetector._normalize(value)

    @staticmethod
    def _normalize(value) -> Optional[str]:
        """Normalize a raw tag value to a clean uppercase string or None."""
        if value is None:
            return None
        text = str(value).replace("\x00", "").strip()
        if not text:
            return None
        return text


# Module-level convenience API (mirrors registry module helpers).
def detect(dataset) -> ModalityDetection:
    """Detect the modality of a DICOM object.  See ModalityDetector.detect."""
    return ModalityDetector().detect(dataset)


def missing_required_tags(dataset, detection: ModalityDetection) -> tuple[str, ...]:
    """Return registry-required DICOM keywords absent from ``dataset``."""
    if detection.spec is None:
        return ()
    missing = []
    for keyword in detection.spec.required_dicom_tags:
        value = getattr(dataset, keyword, None) if dataset is not None else None
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(keyword)
    return tuple(missing)