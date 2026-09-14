"""
PhysiologicalValidator - Physiological Norms Validation Layer.

Assertion Layer: Enforces CT Hounsfield Unit (HU) range validation.
Reference: Standard CT HU scale (water = 0 HU, air = -1000 HU); see the
ACR CT Accreditation Program physics guidance and Kalender,
"Computed Tomography", 2nd ed.
Practical display range: [-1024, 3071] HU (12-bit signed CT storage).
"""

from __future__ import annotations

import numpy as np
import streamlit as st

from core.constants import HU_MIN, HU_MAX


class PhysiologicalValidator:
    """
    Physiological Norms Validation for Medical Imaging Data.
    
    Enforces hard constraints on HU values to prevent non-physiological
    artifacts from propagating through the analysis pipeline.
    """
    
    HU_MIN: float = HU_MIN
    HU_MAX: float = HU_MAX
    PROBABILITY_THRESHOLD: float = 0.80
    MODALITY_RANGES: dict[str, tuple[float, float]] = {
        "ct": (HU_MIN, HU_MAX),
        "mri": (0.0, 4095.0),
        "pet": (0.0, 30.0),
        "us": (0.0, 255.0),
        "nm": (0.0, 65535.0),
    }
    MODALITY_ALIASES: dict[str, str] = {
        "mr": "mri",
        "mri_t1": "mri",
        "mri_t2": "mri",
        "mri_flair": "mri",
        "pt": "pet",
        "pet_suv": "pet",
        "ultrasound": "us",
        "spect": "nm",
    }

    @staticmethod
    def _canonical_modality(modality: str | None) -> str | None:
        """Map a modality label to its canonical key.

        Returns None for unregistered/non-CT modalities, which routes the
        caller to the finite-only (non-CT safe) validation path.
        """
        if modality is None:
            return None
        mod = modality.strip().lower()
        if mod in ("ct", "dicom"):
            return "ct"
        if mod in PhysiologicalValidator.MODALITY_ALIASES:
            return PhysiologicalValidator.MODALITY_ALIASES[mod]
        if mod in PhysiologicalValidator.MODALITY_RANGES:
            return mod
        return None

    @staticmethod
    def validate_physiological_norms(
        data: np.ndarray, modality: str | None = "ct"
    ) -> bool:
        """
        Validate that all data values fall within physiological range.

        For CT data (default) this enforces the Hounsfield Unit (HU) range.
        Registered non-CT modalities use their own modality-specific span.
        When a modality key cannot be resolved, validation degrades to a
        finite-only safe path (NaN/Inf rejection).

        Args:
            data: Input array of intensity values
            modality: Optional modality key (ct, mri, pet, us, nm, ...)

        Returns:
            True if validation passes

        Raises:
            ValueError: If data contains values outside the physiological
                       range for the resolved modality, or contains NaN/Inf
                       values
        """
        resolved = PhysiologicalValidator._canonical_modality(modality)

        if resolved is not None:
            lo, hi = PhysiologicalValidator.MODALITY_RANGES[resolved]
            unit = "HU" if resolved == "ct" else "IU"
            # Vectorized assertion check for performance
            if np.any(data < lo) or np.any(data > hi):
                error_msg = (
                    f"OUT_OF_RANGE: Physiological outlier detected. "
                    f"Range found: [{np.min(data):.1f}, {np.max(data):.1f}] {unit}. "
                    f"Expected PhysiologicalValidator: [{lo}, {hi}] {unit}."
                )
                st.error(f"**Range check failed:** {error_msg}")
                raise ValueError(
                    "Input data outside the physiological range."
                )

        # Check for non-numeric values
        if np.isnan(data).any() or np.isinf(data).any():
            st.error("NON_FINITE: Non-numeric values (NaN/Inf) detected in input.")
            raise ValueError("Non-finite values detected in input sequence.")

        return True

    @staticmethod
    def validate_median_hu(data: np.ndarray, tolerance: float = 1.0) -> bool:
        """
        Validate median HU value falls within expected physiological range.
        
        Used as a quick sanity check for DICOM data integrity.
        
        Args:
            data: Input HU array
            tolerance: Allowed deviation from standard bounds
            
        Returns:
            True if validation passes
            
        Raises:
            ValueError: If median HU falls outside the physiological range
        """
        median_hu = float(np.median(data))
        if not (PhysiologicalValidator.HU_MIN - tolerance <= median_hu <= PhysiologicalValidator.HU_MAX + tolerance):
            raise ValueError(
                f"OUT_OF_RANGE: Median HU ({median_hu:.1f}) outside the valid CT range."
            )
        return True

    @staticmethod
    def check_finite(data: np.ndarray) -> bool:
        """
        Check for NaN/Inf values in data.
        
        Args:
            data: Input array
            
        Returns:
            True if all values are finite
            
        Raises:
            ValueError: If non-finite values detected
        """
        if not np.isfinite(data).all():
            raise ValueError("Non-physiological noise (NaN/Inf) detected.")
        return True