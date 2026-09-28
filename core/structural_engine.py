"""Split module: StructuralEngine."""
from typing import Optional
import numpy as np
from skimage.feature import hessian_matrix, hessian_matrix_eigvals
from core.base_analysis import BaseAnalysis

class StructuralEngine(BaseAnalysis):
    """
    Medical Docstring: تحليل التكامل الهيكلي (L6) باستخدام مصفوفة Hessian.
    الهدف: تحديد الأنماط الهيكلية للأنسجة دون التلاعب بالقيم الخام (Raw Values).
    """

    def execute(self, roi_hu: np.ndarray) -> Optional[np.ndarray]:
        """
        تحليل مصفوفة Hessian لاستخراج معالم الأنسجة.
        Assertion Layer: Physiological Stability Check.
        """
        try:
            # 1. تحليل Hessian Matrix لاستخراج معالم الأنسجة (Structural Force F)
            # sigma=1.2 تم اختيارها بناءً على المعايير السريرية لتقليل ضجيج الـ CT
            h_matrix = hessian_matrix(roi_hu, sigma=1.2, order='rc',
                                      use_gaussian_derivatives=False)
            eigenvalues = hessian_matrix_eigvals(h_matrix)

            # 2. Use the largest-magnitude eigenvalue as the structure response.
            l2_abs = np.abs(eigenvalues[0])

            # Use the 99.5th percentile for a stable normalization robust to artifacts.
            l2_max = np.percentile(l2_abs, 99.5) + 1e-9

            # 3. Guard against degenerate input (no structural variation).
            if l2_max > 15000 or not np.isfinite(l2_max) or l2_max <= 1e-9:
                return None

            normalized_response = np.clip(l2_abs / l2_max, 0, 1)
            return (normalized_response * 255).astype(np.uint8)

        except (IndexError, TypeError, ValueError) as e:
            # التقاط أخطاء المصفوفات أو القيم غير المنطقية (Research Gap)
            print(f"Medical Image Processing Error: {e}")
            return None

        except RuntimeWarning:
            # التعامل مع حالات الانفجار الرياضي (Mathematical Explosion) أو المصفوفات الصفرية
            return None
