"""Split module: TissueClassifier, EdgeDetector, RadiomicsExtractor, XAIExplainer."""
from typing import Dict
import numpy as np
import torch
from scipy import stats
from skimage.feature import graycomatrix, graycoprops, canny as sk_canny
from core.constants import TISSUE_RANGES
from skimage.filters import sobel

class TissueClassifier:
    """
    تصنيف أنسجة الجسم بناءً على وحدات هاونسفيلد (HU).
    المرجع: معايير التصوير المقطعي المحوسب (CT Number Standards).
    
    النطاقات المعتمدة (قيم تقريبية مقبولة للتثقيف — لا تُستخدم للتشخيص):
        Air:        [-1024, -950] HU
        Lung:       [-950,  -500] HU
        Fat:        [-150,   -50] HU
        Water/CSF:  [  -10,    15] HU
        SoftTissue: [   15,   100] HU
        Bone:       [  200,  1500] HU
        DenseBone:  [ 1500,  3071] HU

    ملاحظة: هذه النطاقات تقريبية للتوجيه التعليمي فقط. يمكن أن تتداخل قيم
    HU المتطابقة بين أنسجة وأعضاء ومسارات مرضية مختلفة، والتشخيص الحقيقي
    يتطلب تقييم اختصاصي الأشعة.
    """

    @staticmethod
    def classify(data: np.ndarray) -> Dict[str, float]:
        """تصنيف كل voxel حسب نطاق HU وإرجاع النسب المئوية."""
        total = max(data.size, 1)
        assigned = np.zeros_like(data, dtype=bool)
        result: Dict[str, float] = {}
        for tissue, (lo, hi) in TISSUE_RANGES.items():
            upper_edge = data == hi if tissue == "DenseBone" else False
            mask = (data >= lo) & ((data < hi) | upper_edge)
            assigned |= mask
            result[tissue] = float(np.sum(mask) / total * 100.0)
        outside = np.sum((data < -1024) | (data > 3071))
        if outside > 0:
            result["OutsideRange"] = float(outside / total * 100.0)
        unclassified = np.sum(~assigned & (data >= -1024) & (data <= 3071))
        if unclassified > 0:
            result["Unclassified"] = float(unclassified / total * 100.0)
        return result

    @staticmethod
    def classify_with_volume(
        data: np.ndarray, voxel_volume_mm3: float
    ) -> Dict[str, Dict[str, float]]:
        """تصنيف مع حساب الحجم لكل نسيج (بالمليمتر المكعب والسنتيمتر المكعب)."""
        total_voxels = max(data.size, 1)
        assigned = np.zeros_like(data, dtype=bool)
        result: Dict[str, Dict[str, float]] = {}
        for tissue, (lo, hi) in TISSUE_RANGES.items():
            upper_edge = data == hi if tissue == "DenseBone" else False
            mask = (data >= lo) & ((data < hi) | upper_edge)
            assigned |= mask
            count = float(np.sum(mask))
            pct = count / total_voxels * 100.0
            vol_mm3 = count * voxel_volume_mm3
            vol_cm3 = vol_mm3 / 1000.0
            result[tissue] = {"pct": round(pct, 2), "mm3": round(vol_mm3, 2), "cm3": round(vol_cm3, 2)}
        unclassified = np.sum(~assigned & (data >= -1024) & (data <= 3071))
        if unclassified > 0:
            result["Unclassified"] = {"pct": round(unclassified / total_voxels * 100.0, 2), "mm3": 0.0, "cm3": 0.0}
        return result

    @staticmethod
    def dominant_tissue(data: np.ndarray) -> str:
        """النسيج الأكثر انتشاراً."""
        cls = TissueClassifier.classify(data)
        return max(cls, key=cls.get)


class EdgeDetector:
    """
    كشف الحواف في الصور الطبية باستخدام طرق متعددة.
    المرجع: Canny, Sobel, Scharr, Prewitt, Roberts — خوارزميات معالجة الصور الكلاسيكية.
    """

    @staticmethod
    def _ensure_2d(image: np.ndarray) -> np.ndarray:
        """Return the 2D slice of a volume at the middle axial index."""
        if image.ndim == 3:
            if image.shape[-1] <= 4:
                return image[..., 0]
            return image[image.shape[0] // 2, ...]
        return image

    @staticmethod
    def sobel(image: np.ndarray) -> np.ndarray:
        """Sobel Edge Detection (اتجاهين X/Y)."""
        img = EdgeDetector._ensure_2d(image).astype(np.float64)
        return sobel(img)

    @staticmethod
    def sobel_xy(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Sobel في اتجاه X و Y معاً."""
        from skimage.filters import sobel_h, sobel_v
        img = EdgeDetector._ensure_2d(image).astype(np.float64)
        return sobel_h(img), sobel_v(img)

    @staticmethod
    def canny(image: np.ndarray, sigma: float = 1.0, low_threshold: float = 0.1, high_threshold: float = 0.3) -> np.ndarray:
        """Canny Edge Detection مع عتبات قابلة للتعديل."""
        img = EdgeDetector._ensure_2d(image)
        # تطبيع إلى [0, 1] إذا كانت الصورة uint8
        if img.dtype == np.uint8:
            img_norm = img.astype(np.float64) / 255.0
        else:
            img_norm = img
        return sk_canny(img_norm, sigma=sigma, low_threshold=low_threshold, high_threshold=high_threshold)

    @staticmethod
    def gradient_magnitude(image: np.ndarray) -> np.ndarray:
        """حجم التدرج (Gradient Magnitude) باستخدام Sobel."""
        from skimage.filters import sobel_h, sobel_v
        img = EdgeDetector._ensure_2d(image).astype(np.float64)
        gx = sobel_h(img)
        gy = sobel_v(img)
        return np.hypot(gx, gy)

    @staticmethod
    def laplacian(image: np.ndarray) -> np.ndarray:
        """Laplacian of Gaussian للكشف عن الحواف."""
        from scipy.ndimage import gaussian_laplace
        img = EdgeDetector._ensure_2d(image).astype(np.float64)
        return gaussian_laplace(img, sigma=1.0)


class RadiomicsExtractor:
    """
    استخراج الميزات النسيجية (Radiomics) من الصور الطبية.
    المرجع: Image Biomarker Standardisation Initiative (IBSI) لضبط تعاريف
    المؤشرات الحيوية التصويرية (pyradiomics/docs/ibsi).
    تشمل: ميزات النسيج (GLCM)، الشكل (Shape)، والتوزيع الإحصائي (Histogram).

    ملاحظة: هذه الميزات أداة تعليمية/بحثية ولا تشكل بحد ذاتها تشخيصاً طبياً.
    """

    @staticmethod
    def histogram_features(
        data: np.ndarray,
        *,
        levels: int = 64,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
    ) -> Dict[str, float]:
        """First-order features with an explicit, reproducible discretization.

        Fixed-width binning is the default for CT-like intensity data. The
        continuous first-order statistics remain unchanged; only histogram
        entropy uses the declared discretization.
        """
        f = data.ravel().astype(np.float64)
        if f.size == 0:
            return {}
        if levels < 2:
            raise ValueError("levels must be at least 2")
        if discretization not in {"min_max", "fixed_bin_width"}:
            raise ValueError(
                "discretization must be 'min_max' or 'fixed_bin_width'"
            )
        if discretization == "fixed_bin_width" and (
            bin_width is None or not np.isfinite(bin_width) or bin_width <= 0
        ):
            raise ValueError(
                "bin_width must be a positive finite number for fixed_bin_width"
            )
        mean_v = float(np.mean(f))
        std_v = float(np.std(f, ddof=1)) if f.size >= 2 else 0.0
        skew_v = float(stats.skew(f)) if f.size >= 3 else 0.0
        kurt_v = float(stats.kurtosis(f, fisher=True)) if f.size >= 4 else 0.0
        # Guard against NaN for tiny inputs (single voxel, uniform slices).
        if not np.isfinite(std_v):
            std_v = 0.0
        if not np.isfinite(skew_v):
            skew_v = 0.0
        if not np.isfinite(kurt_v):
            kurt_v = 0.0
        if discretization == "fixed_bin_width":
            minimum = float(np.min(f))
            maximum = float(np.max(f))
            edges = np.arange(
                minimum,
                maximum + float(bin_width) * 2,
                float(bin_width),
                dtype=np.float64,
            )
            histogram, _ = np.histogram(f, bins=edges)
        else:
            histogram, _ = np.histogram(f, bins=levels)
        probabilities = histogram / f.size
        entropy = -np.sum(
            probabilities * np.log2(probabilities + 1e-12)
        )
        result = {
            "mean": round(mean_v, 2),
            "median": round(float(np.median(f)), 2),
            "min": round(float(f.min()), 2),
            "max": round(float(f.max()), 2),
            "energy": round(float(np.sum(f * f)), 4),
            "std": round(std_v, 2),
            "variance": round(std_v * std_v, 2),
            "skewness": round(skew_v, 4),
            "kurtosis": round(kurt_v, 4),
            "p10": round(float(np.percentile(f, 10)), 2),
            "p25": round(float(np.percentile(f, 25)), 2),
            "p50": round(float(np.percentile(f, 50)), 2),
            "p75": round(float(np.percentile(f, 75)), 2),
            "p90": round(float(np.percentile(f, 90)), 2),
            "entropy": round(float(entropy), 4),
        }
        if include_provenance:
            result["provenance"] = {
                "discretization": discretization,
                "levels": int(levels),
                "bin_width": (
                    None if bin_width is None else float(bin_width)
                ),
                "entropy_definition": (
                    "Shannon entropy of discretized first-order histogram"
                ),
            }
        return result

    @staticmethod
    def glcm_features(
        data: np.ndarray,
        distances: list = None,
        angles: list = None,
        *,
        levels: int = 64,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
    ) -> Dict[str, float]:
        """ميزات GLCM (Gray-Level Co-occurrence Matrix).

        ``discretization`` is explicit so texture results can be reproduced:
        ``"min_max"`` preserves the historical behavior, while
        ``"fixed_bin_width"`` requires ``bin_width``.
        """
        if distances is None:
            distances = [1, 2, 4]
        if angles is None:
            angles = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
        if levels < 2 or levels > 256:
            raise ValueError("levels must be between 2 and 256")
        if discretization not in {"min_max", "fixed_bin_width"}:
            raise ValueError(
                "discretization must be 'min_max' or 'fixed_bin_width'"
            )
        img = EdgeDetector._ensure_2d(data).astype(np.float64, copy=False)
        if not np.isfinite(img).all():
            raise ValueError("GLCM input must contain only finite values")
        if discretization == "fixed_bin_width":
            if bin_width is None:
                raise ValueError(
                    "bin_width is required for fixed_bin_width discretization"
                )
            if not np.isfinite(bin_width) or bin_width <= 0:
                raise ValueError("bin_width must be a positive finite number")
            minimum = float(np.min(img))
            img_norm = np.floor((img - minimum) / bin_width)
            img_norm = np.clip(img_norm, 0, levels - 1).astype(np.uint8)
        else:
            img_norm = np.clip(
                (img - img.min()) / max(img.max() - img.min(), 1e-9)
                * (levels - 1),
                0,
                levels - 1,
            ).astype(np.uint8)
        glcm = graycomatrix(
            img_norm,
            distances=distances,
            angles=angles,
            levels=levels,
            symmetric=True,
            normed=True,
        )
        props = {
            "contrast": graycoprops(glcm, 'contrast').mean(),
            "dissimilarity": graycoprops(glcm, 'dissimilarity').mean(),
            "homogeneity": graycoprops(glcm, 'homogeneity').mean(),
            "energy": graycoprops(glcm, 'energy').mean(),
            "correlation": graycoprops(glcm, 'correlation').mean(),
            "ASM": graycoprops(glcm, 'ASM').mean(),
        }
        result = {k: round(float(v), 6) for k, v in props.items()}
        if include_provenance:
            result["provenance"] = {
                "discretization": discretization,
                "levels": int(levels),
                "bin_width": None if bin_width is None else float(bin_width),
                "distances": [int(value) for value in distances],
                "angles": [float(value) for value in angles],
            }
        return result

    @staticmethod
    def shape_features(
        binary_mask: np.ndarray,
        spacing: float | tuple[float, ...] = 1.0,
    ) -> Dict[str, float]:
        """ميزات الشكل من قناع ثنائي."""
        from skimage.measure import label, regionprops
        mask = np.asarray(binary_mask)
        if mask.ndim < 2:
            raise ValueError("binary_mask must have at least two dimensions")
        if isinstance(spacing, (int, float)):
            spacing_tuple = (float(spacing),) * mask.ndim
        else:
            spacing_tuple = tuple(float(value) for value in spacing)
        if (
            len(spacing_tuple) != mask.ndim
            or not np.isfinite(spacing_tuple).all()
            or any(value <= 0 for value in spacing_tuple)
        ):
            raise ValueError("spacing must contain one positive value per mask dimension")
        labeled = label(mask > 0)
        props_list = regionprops(labeled, spacing=spacing_tuple)
        if not props_list:
            return {}
        r = props_list[0]
        result = {
            "area_px": int(np.sum(labeled == r.label)),
            "perimeter_px": round(float(r.perimeter), 2),
            "circularity": round(float(4 * np.pi * r.area / max(r.perimeter ** 2, 1e-9)), 4),
            "eccentricity": round(float(r.eccentricity), 4),
            "solidity": round(float(r.solidity), 4),
            "extent": round(float(r.extent), 4),
            "major_axis": round(float(r.major_axis_length), 2),
            "minor_axis": round(float(r.minor_axis_length), 2),
        }
        if mask.ndim == 2:
            result["area_mm2"] = round(float(r.area), 4)
        elif mask.ndim == 3:
            result["volume_mm3"] = round(float(r.area), 4)
        return result

    @classmethod
    def full_report(
        cls,
        data: np.ndarray,
        binary_mask: np.ndarray = None,
        *,
        levels: int = 64,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        spacing: float | tuple[float, ...] = 1.0,
        include_provenance: bool = True,
    ) -> Dict[str, Dict[str, float]]:
        """تقرير كامل بجميع الميزات."""
        report = {
            "histogram": cls.histogram_features(
                data,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
        }
        if data.ndim == 2 and data.size >= 64:
            report["glcm"] = cls.glcm_features(
                data,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
        if binary_mask is not None:
            report["shape"] = cls.shape_features(binary_mask, spacing=spacing)
        if include_provenance:
            report["provenance"] = {
                "levels": int(levels),
                "bin_width": None if bin_width is None else float(bin_width),
                "discretization": discretization,
                "spacing": (
                    [float(spacing)] * np.asarray(binary_mask).ndim
                    if isinstance(spacing, (int, float)) and binary_mask is not None
                    else [float(value) for value in spacing]
                    if binary_mask is not None
                    else (
                        [float(value) for value in spacing]
                        if not isinstance(spacing, (int, float))
                        else [float(spacing)] * np.asarray(data).ndim
                    )
                ),
            }
        return report


class XAIExplainer:
    """
    الذكاء الاصطناعي القابل للتفسير (XAI) لنماذج الرؤية.
    يستخدم Attention Rollout لـ Vision Transformer.
    """

    @staticmethod
    def compute_attention_map(model, pixel_values: torch.Tensor) -> np.ndarray:
        """استخراج خريطة الانتباه من ViT باستخدام Attention Rollout."""
        with torch.no_grad():
            outputs = model(pixel_values, output_attentions=True)
            attentions = outputs.attentions
        # Attention Rollout: ضرب مصفوفات الانتباه عبر الطبقات
        attn = attentions[0][0, :, 1:, 1:].mean(dim=0)  # [num_patches, num_patches]
        for layer in attentions[1:]:
            layer_attn = layer[0, :, 1:, 1:].mean(dim=0)
            attn = attn @ layer_attn
        # تطبيع
        attn = (attn - attn.min()) / max(attn.max() - attn.min(), 1e-9)
        # إعادة تشكيل إلى أبعاد الصورة
        side = int(np.sqrt(attn.shape[0]))
        if side * side == attn.shape[0]:
            return attn.cpu().numpy().reshape(side, side)
        return attn.cpu().numpy().reshape(1, -1)

    @staticmethod
    def overlay_heatmap(image: np.ndarray, attention_map: np.ndarray, alpha: float = 0.5) -> np.ndarray:
        """دمج خريطة الانتباه مع الصورة الأصلية كخريطة حرارية."""
        import matplotlib.cm as cm
        # تكبير خريطة الانتباه لحجم الصورة
        from PIL import Image as PILImage
        attn_resized = np.array(PILImage.fromarray((attention_map * 255).astype(np.uint8)).resize(
            (image.shape[1], image.shape[0]), PILImage.NEAREST
        )) / 255.0
        # تطبيق colormap
        heatmap = cm.inferno(attn_resized)[:, :, :3] * 255
        overlay = (1 - alpha) * image[:, :, None] + alpha * heatmap if image.ndim == 2 else (1 - alpha) * image + alpha * heatmap
        return np.clip(overlay, 0, 255).astype(np.uint8)
