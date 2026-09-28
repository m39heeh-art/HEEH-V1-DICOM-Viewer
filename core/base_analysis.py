"""Split module: BaseAnalysis."""
from abc import ABC, abstractmethod
from typing import Union
import numpy as np
from skimage.feature import hessian_matrix, hessian_matrix_eigvals

class BaseAnalysis(ABC):
    """
    Multi-scale Hessian-based vessel/structure enhancement for 2D/3D images.

    This uses the Frangi-style vesselness idea: at each scale we compute the
    Hessian matrix and keep the largest-magnitude eigenvalue response. There
    is NO physics equation involved - it is a standard image-processing
    operator. The result is normalized to [0, 1] for grayscale display.
    """

    @abstractmethod
    def execute(self, roi_hu: np.ndarray,
                pixel_spacing: np.ndarray = None) -> Union[np.ndarray, str]:
        """
        Multi-scale Hessian analysis producing a normalized response image.

        pixel_spacing: optional voxel spacing (mm) used to rescale the
        analysis scales to match the physical size of the input. When this
        is a valid positive array, the default scales are multiplied by the
        median spacing; otherwise the standard scales are used.
        """
        try:
            # 1. Multi-scale Hessian response
            scales = [0.5, 1.5, 3.0]
            if pixel_spacing is not None:
                spacing = float(np.median(
                    np.asanyarray(pixel_spacing, dtype=np.float64)))
                if np.isfinite(spacing) and spacing > 0:
                    scales = [0.5 * spacing, 1.5 * spacing, 3.0 * spacing]
            roi_hu_safe = np.asanyarray(roi_hu, dtype=np.float32)

            # Guard against degenerate input (e.g. constant region) early, before
            # any scale-space response is computed: a constant ROI yields only
            # floating-point noise in the Hessian eigenvalues, so the percentile
            # guard below cannot reliably detect it.
            if not np.all(np.isfinite(roi_hu_safe)) or np.ptp(roi_hu_safe) == 0:
                return "UNCERTAIN_DATA_ALERT: Degenerate input (no structural variation)."

            max_response = np.zeros_like(roi_hu_safe, dtype=np.float32)

            for sigma in scales:
                h_matrix = hessian_matrix(roi_hu_safe, sigma=sigma, order='rc',
                                          use_gaussian_derivatives=False)
                eigenvalues = hessian_matrix_eigvals(h_matrix)
                # Largest-magnitude eigenvalue (absolute value) at this scale
                l2_abs = np.abs(eigenvalues[0])
                max_response = np.maximum(max_response, l2_abs)

            # 2. Normalize for display using the 99.5th percentile (robust to outliers)
            l2_max_val = float(np.percentile(max_response, 99.5)) + 1e-9

            # Guard against degenerate input (e.g. constant region -> divide by ~0)
            if not np.isfinite(l2_max_val) or l2_max_val <= 1e-9:
                return "UNCERTAIN_DATA_ALERT: Degenerate input (no structural variation)."

            # 3. Final normalized grayscale output in [0, 255]
            normalized = np.divide(max_response, l2_max_val)
            constrained = np.clip(normalized, 0, 1)

            final_view = np.multiply(constrained, 255)

            return final_view.astype(np.uint8)

        except Exception as e:
            return f"UNCERTAIN_DATA_ALERT: Structural matrix failure - {str(e)}"


# --- [LAYER 3: COMPUTATIONAL ENGINES] ---
