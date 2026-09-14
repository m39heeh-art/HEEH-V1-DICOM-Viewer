"""Modality-safe descriptive measurements for non-CT image data.

These measurements intentionally do not invent clinical biomarkers.  MR, US,
projection radiography, nuclear medicine, ophthalmic, and microscopy pixel
values are only physically meaningful when their acquisition and calibration
metadata are available.  This calculator therefore reports validated native
intensity statistics and the calibration basis explicitly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from engines.modality_calculators.base_calculator import ModalityCalculator


class GenericIntensityCalculator(ModalityCalculator):
    """Calculate modality-neutral statistics without mislabeling the units."""

    def calculate(self, dataset: Any, roi: Optional[Any] = None) -> Dict[str, Any]:
        pixels = self._physical_pixels(dataset)
        if roi is not None:
            mask = np.asarray(roi, dtype=bool)
            if mask.shape != pixels.shape:
                raise ValueError(
                    f"ROI shape {mask.shape} does not match pixel shape "
                    f"{pixels.shape}."
                )
            pixels = pixels[mask]
        if pixels.size == 0:
            raise ValueError("ROI must contain at least one voxel.")

        spacing = self.get_pixel_spacing(dataset)
        calibration = self._calibration_basis(dataset)
        return {
            "modality": self.modality_key,
            "intensity_units": self._reported_units(dataset),
            "calibration": calibration,
            "statistics": {
                "min": float(np.min(pixels)),
                "max": float(np.max(pixels)),
                "mean": float(np.mean(pixels)),
                "median": float(np.median(pixels)),
                "std": float(np.std(pixels, ddof=1)) if pixels.size > 1 else 0.0,
                "p05": float(np.percentile(pixels, 5)),
                "p95": float(np.percentile(pixels, 95)),
                "n_voxels": int(pixels.size),
            },
            "shape": tuple(int(value) for value in pixels.shape),
            "pixel_spacing_mm": spacing,
            # Registry equations describe the modality's scientific scope;
            # do not report them as calculated when this safe generic
            # calculator only produced native-intensity statistics.
            "implemented_metrics": [
                "minimum",
                "maximum",
                "mean",
                "median",
                "standard_deviation",
                "percentiles_5_95",
            ],
            "reference_standards": self.get_reference(),
            "status": (
                "Descriptive native-intensity measurement; "
                "not a calibrated clinical biomarker."
            ),
        }

    def _calibration_basis(self, dataset: Any) -> str:
        """Describe whether DICOM metadata supports physical calibration."""
        if self.modality_key == "RTDOSE" and hasattr(dataset, "DoseGridScaling"):
            return "DICOM DoseGridScaling applied"
        if hasattr(dataset, "RealWorldValueMappingSequence"):
            return "DICOM real-world value mapping present"
        if hasattr(dataset, "RescaleSlope") or hasattr(dataset, "RescaleIntercept"):
            return "DICOM rescale tags applied"
        return "stored pixel values; no modality calibration metadata"

    def _physical_pixels(self, dataset: Any) -> np.ndarray:
        """Apply only calibrations that are unambiguous from DICOM tags."""
        pixels = self.extract_pixel_array(dataset)
        if self.modality_key == "RTDOSE":
            scaling = getattr(dataset, "DoseGridScaling", None)
            if scaling is None:
                raise ValueError("RT Dose requires DoseGridScaling for Gy values.")
            pixels = self.rescale_to_float(pixels, float(scaling), 0.0)
        else:
            pixels = self.to_physical_intensity(dataset, pixels)
        return self.ensure_finite(self.ensure_minimum_size(pixels))

    def _reported_units(self, dataset: Any) -> str:
        if self.modality_key == "RTDOSE":
            return "Gy"
        return self.spec.intensity_units
