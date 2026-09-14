"""
Modality Calculator Base - Abstract foundation for modality-specific calculators.

Every concrete calculator in this package implements validated quantitative
measurements for a single imaging modality and is instantiated through the
modality factory.  This base class centralizes DICOM pixel extraction, HU /
intensity rescaling, pixel-spacing access, and reference-standard metadata so
subclasses focus on the modality-specific physics.

Reference: DICOM PS3.3 (Pixel Data, Rescale Slope/Intercept) and the IEC/ACR/NEMA
standards listed in each ModalitySpec.reference_standards entry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:  # pydicom is a hard dependency, kept importable for tooling-only use
    import pydicom
    from pydicom.dataset import Dataset
except ImportError:  # pragma: no cover
    pydicom = None
    Dataset = None

from core.modality_registry import ModalitySpec, get_spec, resolve_modality


class ModalityCalculator(ABC):
    """
    Abstract base class for all modality-specific calculators.

    Subclasses MUST implement :meth:`calculate` and set the ``modality`` class
    attribute to the canonical registry key (e.g. ``"CT"``, ``"MR"``).
    """

    modality: str = ""

    def __init__(self, modality: Optional[str] = None) -> None:
        """
        Resolve the canonical modality key and its ModalitySpec.

        Args:
            modality: Optional modality key/alias; falls back to the subclass
                ``modality`` class attribute.

        Raises:
            ValueError: If the modality is unknown or structural-only.
        """
        key = resolve_modality(modality or self.modality)
        spec = get_spec(key) if key else None
        if key is None or spec is None:
            raise ValueError(
                f"Unknown modality '{modality or self.modality}'. "
                f"Register it in core.modality_registry before use."
            )
        if spec.reject_display or not spec.supported:
            raise ValueError(
                f"Modality '{key}' is structural-only and has no quantitative "
                f"calculator."
            )
        self.modality_key: str = key
        self.spec: ModalitySpec = spec

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def calculate(
        self,
        dataset: Any,
        roi: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Compute the quantitative metrics for this modality.

        Args:
            dataset: A pydicom Dataset, a DICOM file path, or a raw numpy
                pixel array (subclasses document which inputs they accept).
            roi: Optional region of interest.  May be a boolean mask, a tuple
                of slice indices, or a segmentation result.

        Returns:
            Dictionary of computed metric name -> value.
        """

    # ------------------------------------------------------------------
    # Metadata helpers (from the modality registry)
    # ------------------------------------------------------------------

    def get_equations(self) -> List[str]:
        """Return the list of quantitative equations for this modality."""
        return list(self.spec.quantitative_metrics)

    def get_reference(self) -> List[str]:
        """Return the reference standards governing this modality."""
        return list(self.spec.reference_standards)

    @property
    def display_name(self) -> str:
        """Human-readable modality name from the registry."""
        return self.spec.name

    def supports(self, modality: str) -> bool:
        """True if this calculator was built for the given modality key."""
        return resolve_modality(modality) == self.modality_key

    # ------------------------------------------------------------------
    # Pixel extraction and rescaling
    # ------------------------------------------------------------------

    @staticmethod
    def extract_pixel_array(dataset: Any) -> np.ndarray:
        """
        Return a numpy array of raw pixel values.

        Accepts a pydicom Dataset (reads Pixel Data), a DICOM file path, or a
        raw numpy array (returned unchanged).

        Args:
            dataset: pydicom Dataset, path string, or ndarray.

        Returns:
            NumPy array of the raw stored pixel values.

        Raises:
            TypeError: If the input cannot be interpreted as pixel data.
        """
        if isinstance(dataset, np.ndarray):
            return dataset

        if pydicom is not None and isinstance(dataset, Dataset):
            return dataset.pixel_array  # type: ignore[attr-defined]

        if isinstance(dataset, (str, bytes, os.PathLike)):
            if pydicom is None:
                raise ImportError("pydicom is required to read DICOM files.")
            ds = pydicom.dcmread(dataset)
            return ds.pixel_array

        raise TypeError(
            f"Unsupported pixel-source type '{type(dataset).__name__}'. "
            "Provide a pydicom Dataset, a DICOM path, or a numpy array."
        )

    @staticmethod
    def rescale_to_float(
        pixels: np.ndarray,
        slope: float = 1.0,
        intercept: float = 0.0,
    ) -> np.ndarray:
        """Apply RescaleSlope/RescaleIntercept to raw stored pixel values."""
        return pixels.astype(np.float64) * float(slope) + float(intercept)

    @classmethod
    def to_physical_intensity(
        cls, dataset: Any, pixels: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Convert raw pixels to physical intensity units for this modality.

        Applies DICOM RescaleSlope/RescaleIntercept when the modality requires
        rescaling (e.g. CT -> HU).  Returns float64 pixel data.

        Args:
            dataset: pydicom Dataset or path with rescaler tags.
            pixels: Raw pixel array; fetched from the dataset when omitted.

        Returns:
            Float array in the modality's physical intensity units.
        """
        if pixels is None:
            pixels = cls.extract_pixel_array(dataset)

        if not cls._requires_rescale(dataset):
            return pixels.astype(np.float64)

        slope = cls._tag_float(dataset, "RescaleSlope", default=1.0)
        intercept = cls._tag_float(dataset, "RescaleIntercept", default=0.0)
        return cls.rescale_to_float(pixels, slope, intercept)

    @classmethod
    def _requires_rescale(cls, dataset: Any) -> bool:
        """True when the input carries DICOM rescale tags."""
        if cls._spec_of(dataset) is not None:
            return cls._spec_of(dataset).rescale_required
        return cls._tag_exists(dataset, "RescaleSlope") or cls._tag_exists(
            dataset, "RescaleIntercept"
        )

    @classmethod
    def _spec_of(cls, dataset: Any) -> Optional[ModalitySpec]:
        """Best-effort ModalitySpec lookup for the input dataset."""
        if pydicom is not None and isinstance(dataset, Dataset):
            return get_spec(str(getattr(dataset, "Modality", "")))
        return None

    # ------------------------------------------------------------------
    # Generic DICOM tag access
    # ------------------------------------------------------------------

    @classmethod
    def _tag_float(cls, dataset: Any, keyword: str, default: float = 0.0) -> float:
        """Read a numeric DICOM tag as float, falling back to default."""
        value = getattr(dataset, keyword, None)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _tag_exists(dataset: Any, keyword: str) -> bool:
        """True when the DICOM dataset defines the given tag."""
        return hasattr(dataset, keyword) and getattr(dataset, keyword) is not None

    @staticmethod
    def get_pixel_spacing(dataset: Any) -> Optional[Tuple[float, float]]:
        """
        Return (row_spacing, col_spacing) in mm, or None if not specified.

        Handles both the single-tuple ``PixelSpacing`` and the 6-element
        ``ImageOrientationPatient``-independent per-slice encodings.
        """
        spacing = getattr(dataset, "PixelSpacing", None)
        if spacing is None or len(spacing) < 2:
            return None
        try:
            return (float(spacing[0]), float(spacing[1]))
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Data integrity guards (shared by all subclasses)
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_finite(pixels: np.ndarray, metric_name: str = "pixel data") -> np.ndarray:
        """
        Reject NaN/Inf values that would propagate through the metrics.

        Args:
            pixels: Input array.
            metric_name: Label used in the error message.

        Returns:
            The input array unchanged (validated).

        Raises:
            ValueError: If any value is non-finite.
        """
        if not np.isfinite(pixels).all():
            raise ValueError(
                f"Non-physiological noise (NaN/Inf) detected in {metric_name}."
            )
        return pixels

    @staticmethod
    def ensure_minimum_size(pixels: np.ndarray, min_side: int = 2) -> np.ndarray:
        """Guard against degenerate arrays that break spatial statistics."""
        if pixels.ndim < 2 or min(pixels.shape[:2]) < min_side:
            raise ValueError(
                f"Pixel array too small for metric computation: shape {pixels.shape}."
            )
        return pixels

    @classmethod
    def prepare_pixels(
        cls, dataset: Any, pixels: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Full preprocessing pipeline shared by concrete calculators.

        Extract -> rescale to physical intensity -> validate finiteness and
        minimum size.  Raises on any integrity failure.

        Args:
            dataset: pydicom Dataset, DICOM path, or ndarray.
            pixels: Optional pre-extracted raw pixel array.

        Returns:
            Float64 physical-intensity array, ready for quantification.
        """
        physical = cls.to_physical_intensity(dataset, pixels)
        return cls.ensure_minimum_size(cls.ensure_finite(physical))