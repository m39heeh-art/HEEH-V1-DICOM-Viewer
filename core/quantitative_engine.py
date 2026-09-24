"""Split module: QuantitativeEngine."""
from typing import Dict, Any, Union
import numpy as np
from scipy import stats

class QuantitativeEngine:
    """
    Medical Docstring: Advanced Biophysical Analysis Engine for Large-Scale Imaging.
    Assertion Layer: Integrated Physiological Norms Check.
    """

    @staticmethod
    def execute(roi_hu: np.ndarray) -> Union[Dict[str, Any], str]:
        """
        Calculates high-fidelity density metrics while preserving Raw Diagnostic Value.
        Assertion Layer: Physiological range check [-1024, 3071] HU.
        """
        try:
            values = np.asarray(roi_hu, dtype=np.float64)
            if values.size == 0:
                return "CANNOT_BE_CONFIRMED: Empty ROI"
            if not np.isfinite(values).all():
                return "CANNOT_BE_CONFIRMED: Non-finite voxel values detected"

            # 1. طبقة كفاءة الذاكرة (Memory Stability Layer)
            # استخدام .ravel() لضمان عدم استهلاك الـ 32GB RAM بنسخ مكررة (View-only)
            flat_data = values.ravel()
            n_samples = flat_data.size

            # 2. التحقق من القوة الإحصائية (Statistical Power Check)
            if n_samples < 100:
                return "CANNOT_BE_CONFIRMED: Statistical Power Below Clinical Threshold (< 100 Voxels)"

            # 3. Vectorized descriptive statistics
            mean_val = float(np.mean(flat_data))
            std_val = float(np.std(flat_data, ddof=1))  # Unbiased standard deviation

            # 4. 95% confidence interval for the mean (Student's t-distribution)
            standard_error = std_val / np.sqrt(n_samples)
            confidence_interval = stats.t.interval(
                confidence=0.95,
                df=n_samples - 1,
                loc=mean_val,
                scale=standard_error
            )

            # 5. Validate every voxel, not only the mean. A balanced mean can
            # hide severe outliers or corrupted pixels.
            if np.any((flat_data < -1024.0) | (flat_data > 3071.0)):
                return "CANNOT_BE_CONFIRMED: Physiological Range Violation (Out of Range HU)"

            # 6. اختبار المصداقية الثلاثي (Triple Credibility Test)
            # معامل الاختلاف (CV) للكشف عن الضوضاء التي تتجاوز النطاق الحيوي
            mean_epsilon = 1e-6
            cv_val = None
            cv_status = "defined"
            if abs(mean_val) <= mean_epsilon:
                cv_status = "undefined: mean is too close to zero"
            else:
                cv_val = (std_val / abs(mean_val)) * 100

            # التحقق من خلو النتائج من اللانهائيات (Infinities) أو القيم الفارغة
            if np.isnan(confidence_interval).any() or np.isinf(confidence_interval).any():
                return "CANNOT_BE_CONFIRMED: Statistical Instability Detected"

            # 7. المخرجات النهائية (Pure-Gray Clinical Interface)
            # إرجاع النتائج بدقة تقريبية ثنائية لمنع التشتت البصري
            return {
                "mean": round(mean_val, 2),
                "std": round(std_val, 2),
                "ci": (round(float(confidence_interval[0]), 2), round(float(confidence_interval[1]), 2)),
                "ci_method": "Student t interval",
                "ci_assumption": (
                    "Descriptive voxel-level interval; voxels are treated as "
                    "independent and it is not a patient-level uncertainty estimate."
                ),
                "cv_percentage": None if cv_val is None else round(float(cv_val), 2),
                "cv_status": cv_status,
                "n_voxels": int(n_samples),
                "status": "Quantitative analysis (research/education only)"
            }

        except (ValueError, TypeError, RuntimeWarning) as e:
            # معالجة أخطاء محددة (Granular) بدلاً من الاستثناء العام لضمان استقرار النظام
            return f"CRITICAL_STABILITY_ERROR: Evaluation halted: {str(e)}"
        except Exception as e:
            # خط دفاع أخير لضمان استقرار واجهة NeuroAI في الحالات غير المتوقعة
            return f"QUANT_ERROR: Unexpected failure during quantitative analysis - {str(e)}"
