"""Split module: ImageQualityMetrics, LongitudinalAnalyzer, PerfusionAnalyzer."""
from typing import Dict
import numpy as np
import matplotlib.pyplot as plt

class ImageQualityMetrics:
    """
    مقاييس جودة الصورة الطبية.
    المرجع: AAPM TG-150, IEC 61223.
    """

    @staticmethod
    def snr(signal_region: np.ndarray, noise_region: np.ndarray) -> float:
        """Signal-to-Noise Ratio: mean(signal) / std(noise)."""
        if signal_region.size == 0 or noise_region.size < 2:
            return 0.0
        s_mean = float(np.mean(signal_region))
        n_std = float(np.std(noise_region, ddof=1))
        if not np.isfinite(s_mean) or not np.isfinite(n_std):
            return 0.0
        return round(s_mean / max(n_std, 1e-9), 4)

    @staticmethod
    def cnr(signal_region: np.ndarray, bg_region: np.ndarray, noise_region: np.ndarray = None) -> float:
        """Contrast-to-Noise Ratio."""
        if signal_region.size == 0 or bg_region.size == 0:
            return 0.0
        s_mean = float(np.mean(signal_region))
        bg_mean = float(np.mean(bg_region))
        if noise_region is not None:
            if noise_region.size < 2:
                return 0.0
            n_std = float(np.std(noise_region, ddof=1))
        else:
            if bg_region.size < 2:
                return 0.0
            n_std = float(np.std(bg_region, ddof=1))
        if not np.isfinite(s_mean) or not np.isfinite(bg_mean) or not np.isfinite(n_std):
            return 0.0
        return round(abs(s_mean - bg_mean) / max(n_std, 1e-9), 4)

    @staticmethod
    def uniformity(hu_data: np.ndarray, center_fraction: float = 0.25) -> float:
        """Uniformity: الانحراف المعياري النسبي في منطقة مركزية."""
        h, w = hu_data.shape
        cy, cx = h // 2, w // 2
        half = max(int(min(h, w) * center_fraction), 1)
        y0, y1 = max(cy - half, 0), min(cy + half, h)
        x0, x1 = max(cx - half, 0), min(cx + half, w)
        roi = hu_data[y0:y1, x0:x1]
        if roi.size < 2:
            return 0.0
        mean_v = float(np.mean(roi))
        std_v = float(np.std(roi, ddof=1))
        if not np.isfinite(mean_v) or not np.isfinite(std_v):
            return 0.0
        return round(std_v / max(abs(mean_v), 1e-9) * 100, 4)

    @staticmethod
    def noise_estimate(hu_data: np.ndarray) -> Dict[str, float]:
        """تقدير الضوضاء المحلية باستخدام الفروق بين البكسلات المجاورة."""
        diff_h = np.diff(hu_data, axis=1)
        diff_v = np.diff(hu_data, axis=0)
        noise_h = float(np.std(diff_h, ddof=1) / np.sqrt(2)) if diff_h.size >= 2 else 0.0
        noise_v = float(np.std(diff_v, ddof=1) / np.sqrt(2)) if diff_v.size >= 2 else 0.0
        if not np.isfinite(noise_h):
            noise_h = 0.0
        if not np.isfinite(noise_v):
            noise_v = 0.0
        return {
            "noise_horizontal": round(noise_h, 4),
            "noise_vertical": round(noise_v, 4),
            "noise_mean": round((noise_h + noise_v) / 2, 4),
        }


class LongitudinalAnalyzer:
    """
    تحليل طولي — مقارنة صورتين متتاليتين في الزمن (قبل/بعد العلاج).

    ملاحظة طبية: تعتمد هذه الأداة على مقارنة شدة البكسلات (Pixel/Voxel
    Intensity) بين صورتين، وهي أداة تعليمية/بحثية فقط. لا تعادل ولا تحل محل
    بروتوكول RECIST 1.1 أو أي معيار سريري لقياس الاستجابة للعلاج، ونتائجها
    يجب تفسيرها من قبل اختصاصي الأشعة فقط.
    """

    @staticmethod
    def difference_map(before: np.ndarray, after: np.ndarray) -> np.ndarray:
        """خريطة الفرق: after - before."""
        if before.shape != after.shape:
            raise ValueError("Images must have same shape for longitudinal comparison.")
        return after.astype(np.float64) - before.astype(np.float64)

    @staticmethod
    def percentage_change(before: np.ndarray, after: np.ndarray) -> Dict[str, float]:
        """نسبة التغير الإحصائية بين الصورتين."""
        diff = LongitudinalAnalyzer.difference_map(before, after)
        b_mean = float(np.mean(before))
        return {
            "mean_diff": round(float(np.mean(diff)), 2),
            "std_diff": round(float(np.std(diff, ddof=1)), 2),
            "pct_change_mean": round(float(np.mean(diff) / max(abs(b_mean), 1e-9) * 100), 2),
            "pct_positive": round(float(np.sum(diff > 0) / max(diff.size, 1) * 100), 2),
            "pct_negative": round(float(np.sum(diff < 0) / max(diff.size, 1) * 100), 2),
        }

    @staticmethod
    def render_difference_overlay(before: np.ndarray, after: np.ndarray, threshold_hu: float = 50.0) -> np.ndarray:
        """تراكب ملون يظهر مناطق التغير فوق عتبة معينة."""
        diff = LongitudinalAnalyzer.difference_map(before, after)
        # مناطق الزيادة (أحمر)، مناطق النقصان (أزرق)
        overlay = np.zeros((*before.shape, 3), dtype=np.uint8)
        after_norm = np.clip((after - after.min()) / max(after.max() - after.min(), 1e-9) * 255, 0, 255).astype(np.uint8)
        overlay[..., 0] = after_norm
        overlay[..., 1] = after_norm
        overlay[..., 2] = after_norm
        increase = diff > threshold_hu
        decrease = diff < -threshold_hu
        overlay[increase] = [255, 60, 60]   # أحمر للزيادة
        overlay[decrease] = [60, 60, 255]   # أزرق للنقصان
        return overlay


class PerfusionAnalyzer:
    """
    تحليل التروية (Perfusion) باستخدام منحنيات الكثافة الزمنية.

    ملاحظة طبية: تحسب هذه الأداة منحنيات الكثافة الزمنية (Time-Intensity
    Curve) للأغراض التعليمية فقط. لا تحسب معاملات التروية السريرية المعتمدة
    (مثل CBF / CBV / MTT / TTP) ولا تصلح لأي قرار طبي.
    """

    @staticmethod
    def time_intensity_curve(time_series: np.ndarray, roi_mask: np.ndarray = None) -> Dict[str, np.ndarray]:
        """منحنى الكثافة الزمنية (TIC) لسلسلة زمنية من الصور."""
        if time_series.ndim != 3:
            raise ValueError("Time series must be 3D: (time, height, width)")
        if roi_mask is not None:
            means = [float(np.mean(time_series[t][roi_mask > 0])) for t in range(time_series.shape[0])]
        else:
            means = [float(np.mean(time_series[t])) for t in range(time_series.shape[0])]
        return {"time_points": np.arange(len(means)), "mean_hu": np.array(means)}

    @staticmethod
    def perfusion_color_map(parameter_map: np.ndarray, colormap: str = 'jet') -> np.ndarray:
        """تحويل خريطة معامل تروية إلى خريطة ملونة."""
        norm = (parameter_map - parameter_map.min()) / max(parameter_map.max() - parameter_map.min(), 1e-9)
        colored = plt.colormaps.get_cmap(colormap)(norm)[:, :, :3] * 255
        return colored.astype(np.uint8)

    @staticmethod
    def enhance_vessels(data: np.ndarray, window_center: int = 200, window_width: int = 600) -> np.ndarray:
        """تعزيز الأوعية الدموية في صورة التروية."""
        lo = window_center - window_width // 2
        hi = window_center + window_width // 2
        enhanced = np.clip((data.astype(np.float64) - lo) / max(hi - lo, 1.0) * 255, 0, 255)
        return enhanced.astype(np.uint8)
