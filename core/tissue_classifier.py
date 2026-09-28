"""Split module: TissueClassifier, EdgeDetector, RadiomicsExtractor, XAIExplainer."""
from typing import Any, Dict
import numpy as np
try:
    import torch
except ImportError:  # Radiomics utilities do not require the optional XAI dependency.
    torch = None
from scipy import stats
from scipy.ndimage import zoom
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
    def feature_coverage() -> Dict[str, Dict[str, str]]:
        """Return the coverage matrix for the feature classes actually claimed."""
        return {
            "first_order": {
                "status": "supported",
                "implementation": "RadiomicsExtractor.histogram_features",
                "note": "Computed from the declared sample discretization and source intensities.",
            },
            "glcm": {
                "status": "supported",
                "implementation": "RadiomicsExtractor.glcm_features",
                "note": "2D co-occurrence statistics using explicit levels/bin-width discretization.",
            },
            "glrlm": {
                "status": "supported",
                "implementation": "RadiomicsExtractor.glrlm_features",
                "note": "2D run-length matrix averaged over cardinal coordinates using the declared discretized image and connectivity 1.",
            },
            "glszm": {
                "status": "supported",
                "implementation": "RadiomicsExtractor.glszm_features",
                "note": "2D size-zone matrix over connected regions in the declared discretized image.",
            },
            "gldm": {
                "status": "supported",
                "implementation": "RadiomicsExtractor.gldm_features",
                "note": "2D dependence matrix using a declared gray-level tolerance and 4- or 8-neighborhood; not a 3D IBSI result.",
            },
            "ngtdm": {
                "status": "supported",
                "implementation": "RadiomicsExtractor.ngtdm_features",
                "note": "2D neighborhood gray-tone difference features using a declared 4- or 8-neighborhood; not a 3D IBSI result.",
            },
        }

    @staticmethod
    def _discretize_image(
        image: np.ndarray,
        *,
        levels: int,
        bin_width: float | None,
        discretization: str,
    ) -> np.ndarray:
        """Discretize the image exactly once and keep the same policy across texture features."""
        img = np.asarray(image, dtype=np.float64)
        if levels < 2:
            raise ValueError("levels must be at least 2")
        if discretization not in {"min_max", "fixed_bin_width"}:
            raise ValueError("discretization must be 'min_max' or 'fixed_bin_width'")
        if discretization == "fixed_bin_width":
            if bin_width is None:
                raise ValueError("bin_width is required for fixed_bin_width discretization")
            if not np.isfinite(bin_width) or bin_width <= 0:
                raise ValueError("bin_width must be a positive finite number")
            minimum = float(np.min(img))
            levels_array = np.floor((img - minimum) / bin_width).astype(np.int64)
            return np.clip(levels_array, 0, levels - 1).astype(np.int32)
        img_min = float(np.min(img))
        img_max = float(np.max(img))
        if img_max <= img_min:
            return np.zeros_like(img, dtype=np.int32)
        scaled = (img - img_min) / max(img_max - img_min, 1e-9)
        return np.clip(np.floor(scaled * (levels - 1)), 0, levels - 1).astype(np.int32)

    @staticmethod
    def _intensity_block_stats(matrix: np.ndarray, *, axis: int = 1) -> tuple[np.ndarray, np.ndarray]:
        gray_sums = matrix.sum(axis=axis)
        run_sums = matrix.sum(axis=1 - axis)
        return gray_sums, run_sums

    @staticmethod
    def histogram_features(
        data: np.ndarray,
        *,
        levels: int = 256,
        bin_width: float = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
    ) -> Dict[str, float]:
        """Compute reproducible first-order features for the CT subset.

        Continuous statistics remain in the source intensity domain. Entropy is
        calculated from the explicitly declared IBSI-style discretisation.
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
            not np.isfinite(bin_width) or bin_width <= 0
        ):
            raise ValueError("bin_width must be positive and finite")
        mean_v = float(np.mean(f))
        # Match PyRadiomics FirstOrder StandardDeviation (population variance).
        std_v = float(np.std(f, ddof=0)) if f.size >= 2 else 0.0
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
            origin = float(np.min(f))
            bins = np.floor((f - origin) / bin_width).astype(np.int64)
            if int(np.max(bins)) >= levels:
                raise ValueError(
                    "levels is too small for the declared fixed bin width and data range"
                )
            histogram = np.bincount(bins, minlength=levels)
        else:
            histogram, _ = np.histogram(f, bins=levels)
        probabilities = histogram / f.size
        entropy = -np.sum(
            probabilities * np.log2(probabilities + 1e-12)
        )
        result = {
            "mean": mean_v,
            "median": round(float(np.median(f)), 2),
            "min": float(f.min()),
            "max": float(f.max()),
            "energy": round(float(np.sum(f * f)), 4),
            "std": std_v,
            "variance": std_v * std_v,
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
                "bin_width": float(bin_width),
                "entropy_definition": (
                    "Shannon entropy of the declared discretised histogram"
                ),
            }
        return result

    @staticmethod
    def glcm_features(
        data: np.ndarray,
        distances: list = None,
        angles: list = None,
        *,
        levels: int = 256,
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
    def glrlm_features(
        data: np.ndarray,
        *,
        levels: int = 256,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
        connectivity: int = 1,
    ) -> Dict[str, float]:
        """Compute a 2D gray-level run-length matrix (GLRLM) summary with IBSI-aligned settings."""
        img = EdgeDetector._ensure_2d(data)
        if not np.isfinite(img).all():
            raise ValueError("GLRLM input must contain only finite values")
        img_norm = RadiomicsExtractor._discretize_image(
            img,
            levels=levels,
            bin_width=bin_width,
            discretization=discretization,
        )
        matrix = np.zeros((levels, max(img_norm.shape)), dtype=np.float64)
        for direction in ("row", "column"):
            if direction == "row":
                scan_axes = [img_norm]
                for row in scan_axes[0]:
                    values = row.astype(np.int64, copy=False)
                    boundaries = np.flatnonzero(np.diff(values, prepend=np.array([values[0] - 1], dtype=np.int64)))
                    run_starts = boundaries
                    run_ends = np.concatenate((boundaries[1:], np.array([values.size], dtype=np.int64)))
                    for start_idx, end_idx in zip(run_starts, run_ends):
                        run_length = int(end_idx - start_idx)
                        if run_length <= 0:
                            continue
                        current = int(values[start_idx])
                        matrix[current, run_length - 1] += 1.0
            else:
                for column in img_norm.T:
                    values = column.astype(np.int64, copy=False)
                    if values.size == 0:
                        continue
                    boundaries = np.flatnonzero(np.diff(values, prepend=np.array([values[0] - 1], dtype=np.int64)))
                    run_starts = boundaries
                    run_ends = np.concatenate((boundaries[1:], np.array([values.size], dtype=np.int64)))
                    for start_idx, end_idx in zip(run_starts, run_ends):
                        run_length = int(end_idx - start_idx)
                        if run_length <= 0:
                            continue
                        current = int(values[start_idx])
                        matrix[current, run_length - 1] += 1.0
        total = float(matrix.sum())
        if total <= 0:
            return {"short_run_emphasis": 0.0, "long_run_emphasis": 0.0, "gray_level_non_uniformity": 0.0, "run_length_non_uniformity": 0.0, "run_percentage": 0.0, "low_gray_level_run_emphasis": 0.0, "high_gray_level_run_emphasis": 0.0, "short_run_low_gray_level_emphasis": 0.0, "short_run_high_gray_level_emphasis": 0.0, "long_run_low_gray_level_emphasis": 0.0, "long_run_high_gray_level_emphasis": 0.0}
        p = matrix / total
        lengths = np.arange(1, matrix.shape[1] + 1, dtype=np.float64)[None, :]
        gray_levels = np.arange(levels, dtype=np.float64)[:, None]
        gray_sum = p.sum(axis=1)
        run_sum = p.sum(axis=0)
        result = {
            "short_run_emphasis": float(np.sum(p / (lengths**2 + 1e-12))),
            "long_run_emphasis": float(np.sum(p * (lengths**2))),
            "gray_level_non_uniformity": float(np.sum(gray_sum**2)),
            "run_length_non_uniformity": float(np.sum(run_sum**2)),
            "run_percentage": float(total / img.size),
            "low_gray_level_run_emphasis": float(np.sum(p / ((gray_levels + 1.0) ** 2 + 1e-12))),
            "high_gray_level_run_emphasis": float(np.sum(p * (gray_levels + 1.0) ** 2)),
            "short_run_low_gray_level_emphasis": float(np.sum(p / ((gray_levels + 1.0) ** 2 + 1e-12) / (lengths**2 + 1e-12))),
            "short_run_high_gray_level_emphasis": float(np.sum(p * (gray_levels + 1.0) ** 2 / (lengths**2 + 1e-12))),
            "long_run_low_gray_level_emphasis": float(np.sum(p * (lengths**2) / ((gray_levels + 1.0) ** 2 + 1e-12))),
            "long_run_high_gray_level_emphasis": float(np.sum(p * (gray_levels + 1.0) ** 2 * (lengths**2))),
        }
        if include_provenance:
            result["provenance"] = {
                "discretization": discretization,
                "levels": int(levels),
                "bin_width": None if bin_width is None else float(bin_width),
                "connectivity": int(connectivity),
                "orientation": ["row", "column"],
            }
        return result

    @staticmethod
    def glszm_features(
        data: np.ndarray,
        *,
        levels: int = 256,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
        connectivity: int = 1,
    ) -> Dict[str, float]:
        """Compute a 2D gray-level size-zone matrix (GLSZM) summary from connected homogeneous zones."""
        img = EdgeDetector._ensure_2d(data)
        if not np.isfinite(img).all():
            raise ValueError("GLSZM input must contain only finite values")
        img_norm = RadiomicsExtractor._discretize_image(
            img,
            levels=levels,
            bin_width=bin_width,
            discretization=discretization,
        )
        if connectivity not in (1, 2):
            raise ValueError(
                "connectivity must be 1 (4-neighborhood) or 2 (8-neighborhood)"
            )
        matrix = np.zeros((levels, img_norm.size + 1), dtype=np.float64)
        from scipy import ndimage
        structure = ndimage.generate_binary_structure(2, connectivity)
        for gray in range(levels):
            mask = img_norm == gray
            if not np.any(mask):
                continue
            labeled, _ = ndimage.label(mask, structure=structure)
            counts = np.bincount(labeled[labeled > 0], minlength=labeled.max() + 1)
            for size in counts[1:]:
                if size > 0:
                    matrix[gray, size - 1] += 1.0
        total = float(matrix.sum())
        if total <= 0:
            return {"small_zone_emphasis": 0.0, "large_zone_emphasis": 0.0, "gray_level_non_uniformity": 0.0, "zone_size_non_uniformity": 0.0, "zone_percentage": 0.0, "low_gray_level_zone_emphasis": 0.0, "high_gray_level_zone_emphasis": 0.0, "small_zone_low_gray_level_emphasis": 0.0, "small_zone_high_gray_level_emphasis": 0.0, "large_zone_low_gray_level_emphasis": 0.0, "large_zone_high_gray_level_emphasis": 0.0}
        p = matrix / total
        size_index = np.arange(1, matrix.shape[1] + 1, dtype=np.float64)[None, :]
        gray_index = np.arange(levels, dtype=np.float64)[:, None]
        gray_sum = p.sum(axis=1)
        size_sum = p.sum(axis=0)
        result = {
            "small_zone_emphasis": float(np.sum(p / (size_index**2 + 1e-12))),
            "large_zone_emphasis": float(np.sum(p * (size_index**2))),
            "gray_level_non_uniformity": float(np.sum(gray_sum**2)),
            "zone_size_non_uniformity": float(np.sum(size_sum**2)),
            "zone_percentage": float(total / img.size),
            "low_gray_level_zone_emphasis": float(np.sum(p / ((gray_index + 1.0) ** 2 + 1e-12))),
            "high_gray_level_zone_emphasis": float(np.sum(p * (gray_index + 1.0) ** 2)),
            "small_zone_low_gray_level_emphasis": float(np.sum(p / (((gray_index + 1.0) ** 2 + 1e-12) * (size_index**2 + 1e-12)))),
            "small_zone_high_gray_level_emphasis": float(np.sum(p * ((gray_index + 1.0) ** 2) / (size_index**2 + 1e-12))),
            "large_zone_low_gray_level_emphasis": float(np.sum(p * (size_index**2) / ((gray_index + 1.0) ** 2 + 1e-12))),
            "large_zone_high_gray_level_emphasis": float(np.sum(p * (gray_index + 1.0) ** 2 * (size_index**2))),
        }
        if include_provenance:
            result["provenance"] = {
                "discretization": discretization,
                "levels": int(levels),
                "bin_width": None if bin_width is None else float(bin_width),
                "connectivity": int(connectivity),
            }
        return result

    @staticmethod
    def gldm_features(
        data: np.ndarray,
        *,
        levels: int = 256,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
        connectivity: int = 1,
        alpha: int = 0,
    ) -> Dict[str, float]:
        """Compute 2D GLDM summaries with alpha tolerance and 4/8-neighborhood."""
        img = EdgeDetector._ensure_2d(data)
        if not np.isfinite(img).all():
            raise ValueError("GLDM input must contain only finite values")
        if connectivity not in (1, 2):
            raise ValueError("connectivity must be 1 (4-neighborhood) or 2 (8-neighborhood)")
        if not isinstance(alpha, (int, np.integer)) or isinstance(alpha, bool) or alpha < 0:
            raise ValueError("alpha must be a non-negative integer")
        img_norm = RadiomicsExtractor._discretize_image(
            img,
            levels=levels,
            bin_width=bin_width,
            discretization=discretization,
        )
        from scipy import ndimage
        structure = ndimage.generate_binary_structure(2, connectivity)
        offsets = [
            (row - 1, column - 1)
            for row, column in np.argwhere(structure)
            if (row, column) != (1, 1)
        ]
        max_dependence = len(offsets) + 1
        dependence = np.ones(img_norm.shape, dtype=np.int32)
        padded = np.pad(img_norm, 1, mode="constant", constant_values=-levels - 1)
        for row_offset, column_offset in offsets:
            neighbor = padded[
                1 + row_offset : 1 + row_offset + img_norm.shape[0],
                1 + column_offset : 1 + column_offset + img_norm.shape[1],
            ]
            dependence += np.abs(img_norm - neighbor) <= alpha
        flat_indices = img_norm.ravel() * max_dependence + (dependence.ravel() - 1)
        matrix = np.bincount(
            flat_indices, minlength=levels * max_dependence
        ).reshape(levels, max_dependence).astype(np.float64)
        total = float(matrix.sum())
        if total <= 0:
            return {
                "small_dependence_emphasis": 0.0,
                "large_dependence_emphasis": 0.0,
                "gray_level_non_uniformity": 0.0,
                "dependence_non_uniformity": 0.0,
                "dependence_percentage": 0.0,
                "low_gray_level_dependence_emphasis": 0.0,
                "high_gray_level_dependence_emphasis": 0.0,
                "small_dependence_low_gray_level_emphasis": 0.0,
                "small_dependence_high_gray_level_emphasis": 0.0,
                "large_dependence_low_gray_level_emphasis": 0.0,
                "large_dependence_high_gray_level_emphasis": 0.0,
            }
        p = matrix / total
        dependence_index = np.arange(1, max_dependence + 1, dtype=np.float64)[None, :]
        gray_index = np.arange(levels, dtype=np.float64)[:, None]
        gray_sum = p.sum(axis=1)
        dep_sum = p.sum(axis=0)
        result = {
            "small_dependence_emphasis": float(np.sum(p / (dependence_index**2 + 1e-12))),
            "large_dependence_emphasis": float(np.sum(p * (dependence_index**2))),
            "gray_level_non_uniformity": float(np.sum(gray_sum**2)),
            "dependence_non_uniformity": float(np.sum(dep_sum**2)),
            "dependence_percentage": float(total / img.size),
            "low_gray_level_dependence_emphasis": float(np.sum(p / ((gray_index + 1.0) ** 2 + 1e-12))),
            "high_gray_level_dependence_emphasis": float(np.sum(p * (gray_index + 1.0) ** 2)),
            "small_dependence_low_gray_level_emphasis": float(np.sum(p / (((gray_index + 1.0) ** 2 + 1e-12) * (dependence_index**2 + 1e-12)))),
            "small_dependence_high_gray_level_emphasis": float(np.sum(p * ((gray_index + 1.0) ** 2) / (dependence_index**2 + 1e-12))),
            "large_dependence_low_gray_level_emphasis": float(np.sum(p * (dependence_index**2) / ((gray_index + 1.0) ** 2 + 1e-12))),
            "large_dependence_high_gray_level_emphasis": float(np.sum(p * (gray_index + 1.0) ** 2 * (dependence_index**2))),
        }
        if include_provenance:
            result["provenance"] = {
                "discretization": discretization,
                "levels": int(levels),
                "bin_width": None if bin_width is None else float(bin_width),
                "connectivity": int(connectivity),
                "alpha": int(alpha),
            }
        return result

    @staticmethod
    def ngtdm_features(
        data: np.ndarray,
        *,
        levels: int = 256,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        include_provenance: bool = False,
        connectivity: int = 1,
    ) -> Dict[str, float]:
        """Compute vectorized 2D NGTDM summaries for a 4- or 8-neighborhood."""
        from scipy import ndimage

        img = EdgeDetector._ensure_2d(data)
        if not np.isfinite(img).all():
            raise ValueError("NGTDM input must contain only finite values")
        if connectivity not in (1, 2):
            raise ValueError("connectivity must be 1 (4-neighborhood) or 2 (8-neighborhood)")
        img_norm = RadiomicsExtractor._discretize_image(
            img,
            levels=levels,
            bin_width=bin_width,
            discretization=discretization,
        )
        structure = ndimage.generate_binary_structure(2, connectivity).astype(np.float64)
        structure[1, 1] = 0.0
        neighbor_sum = ndimage.convolve(img_norm.astype(np.float64), structure, mode="constant")
        neighbor_count = ndimage.convolve(
            np.ones(img_norm.shape, dtype=np.float64), structure, mode="constant"
        )
        valid = neighbor_count > 0
        gray_values = img_norm[valid]
        if gray_values.size == 0:
            return {
                "coarseness": 0.0,
                "contrast": 0.0,
                "busyness": 0.0,
                "complexity": 0.0,
                "strength": 0.0,
            }
        differences = np.abs(
            gray_values - neighbor_sum[valid] / neighbor_count[valid]
        )
        counts = np.bincount(gray_values, minlength=levels).astype(np.float64)
        sums = np.bincount(
            gray_values, weights=differences, minlength=levels
        ).astype(np.float64)
        active = counts > 0
        gray_idx = np.flatnonzero(active).astype(np.float64) + 1.0
        p = counts[active] / float(gray_values.size)
        s = sums[active]
        # s is the sum of absolute neighborhood differences per gray level
        # (IBSI/Amadasun definition, matching PyRadiomics). Do not normalize
        # by the per-level voxel count; coarseness consumes the raw sums.
        pair_difference = np.abs(gray_idx[:, None] - gray_idx[None, :])
        coarseness_denominator = float(np.sum(p * s))
        coarseness = (
            1.0 / coarseness_denominator
            if coarseness_denominator > 0
            else 1e6
        )
        gray_level_count = len(gray_idx)
        contrast = 0.0
        if gray_level_count > 1:
            contrast = float(
                np.sum(p[:, None] * p[None, :] * pair_difference**2)
                / (gray_level_count * (gray_level_count - 1))
                * np.sum(s)
                / gray_values.size
            )
        busyness_denominator = float(
            np.sum(
                np.abs(
                    gray_idx[:, None] * p[:, None]
                    - gray_idx[None, :] * p[None, :]
                )
            )
        )
        busyness = (
            float(np.sum(p * s) / busyness_denominator)
            if busyness_denominator > 0
            else 0.0
        )
        weighted_difference = pair_difference * (
            p[:, None] * s[:, None] + p[None, :] * s[None, :]
        )
        complexity_denominator = p[:, None] + p[None, :]
        complexity = float(
            np.sum(
                np.divide(
                    weighted_difference,
                    complexity_denominator,
                    out=np.zeros_like(weighted_difference),
                    where=complexity_denominator > 0,
                )
            )
            / gray_values.size
        )
        strength_denominator = float(np.sum(s))
        strength = (
            float(
                np.sum((p[:, None] + p[None, :]) * pair_difference**2)
                / strength_denominator
            )
            if strength_denominator > 0
            else 0.0
        )
        result = {
            "coarseness": float(coarseness),
            "contrast": float(contrast),
            "busyness": float(busyness),
            "complexity": float(complexity),
            "strength": float(strength),
        }
        if include_provenance:
            result["provenance"] = {
                "discretization": discretization,
                "levels": int(levels),
                "bin_width": None if bin_width is None else float(bin_width),
                "connectivity": int(connectivity),
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
        result: Dict[str, Any] = {
            "solidity": round(float(r.solidity), 4),
            "extent": round(float(r.extent), 4),
        }
        if mask.ndim == 2:
            result["area_px"] = int(np.sum(labeled == r.label))
            result["perimeter_px"] = round(float(r.perimeter), 2)
            result["circularity"] = round(
                float(4 * np.pi * r.area / max(r.perimeter**2, 1e-9)), 4
            )
            result["eccentricity"] = round(float(r.eccentricity), 4)
            # skimage >= 0.26 renamed major/minor_axis_length.
            major_axis = getattr(r, "axis_major_length", None)
            if major_axis is None:
                major_axis = r.major_axis_length
            minor_axis = getattr(r, "axis_minor_length", None)
            if minor_axis is None:
                minor_axis = r.minor_axis_length
            result["major_axis"] = round(float(major_axis), 2)
            result["minor_axis"] = round(float(minor_axis), 2)
            result["area_mm2"] = round(float(r.area), 4)
        else:
            # 3D: perimeter, circularity, and eccentricity are 2D concepts and
            # skimage does not implement them for volumes. Report dimension-wise
            # axis lengths and the feret diameter instead of pretending 2D
            # properties apply to a volume. The element count is a voxel count,
            # not a pixel area.
            from scipy import ndimage

            result["voxel_count"] = int(np.sum(labeled == r.label))
            result["feret_diameter_max"] = round(
                float(r.feret_diameter_max), 2
            )
            result["major_axis"] = round(float(r.axis_major_length), 2)
            slices = ndimage.find_objects(labeled)
            extent_slices = slices[r.label - 1]
            axis_lengths = [
                int(sl.stop - sl.start) * float(spacing)
                for sl, spacing in zip(extent_slices, spacing_tuple)
            ]
            for axis_index, length in enumerate(axis_lengths):
                result[f"axis_length_{axis_index}"] = round(float(length), 2)
            result["volume_mm3"] = round(float(r.area), 4)
        return result

    @staticmethod
    def ibsi_reference_features(
        image_path: str,
        mask_path: str,
        *,
        bin_width: float | None = None,
        bin_count: int | None = None,
        label: int = 1,
        resampled_pixel_spacing: tuple[float, float, float] | None = None,
        resegment_range: tuple[float, float] | None = None,
        resegment_outlier_sigma: float | None = None,
        interpolator: Any | None = None,
        round_resampled_intensities: bool = False,
        feature_classes: tuple[str, ...] = (
            "firstorder",
            "glcm",
            "glrlm",
            "glszm",
            "gldm",
            "ngtdm",
            "shape",
        ),
    ) -> Dict[str, Any]:
        """Extract a 3-D reference report through PyRadiomics.

        The local NumPy implementations are educational summaries and are not
        a substitute for the IBSI reference implementation.  This adapter
        makes the compliance path explicit and keeps all image/mask handling
        in one reproducible configuration.  Requested resampling is performed
        on the complete image volume before PyRadiomics crops the ROI. Either
        fixed bin width or fixed bin count may be selected, and resampled
        intensities can be rounded to the nearest integer when required by
        the selected IBSI configuration.
        """
        if bin_count is not None:
            if (
                not isinstance(bin_count, int)
                or isinstance(bin_count, bool)
                or bin_count < 2
            ):
                raise ValueError("bin_count must be an integer of at least 2")
            if bin_width is not None:
                raise ValueError("choose either bin_width or bin_count")
        elif bin_width is None:
            bin_width = 25.0
        elif not np.isfinite(bin_width) or bin_width <= 0:
            raise ValueError("bin_width must be a positive finite number")
        if resegment_outlier_sigma is not None and (
            not np.isfinite(resegment_outlier_sigma) or resegment_outlier_sigma <= 0
        ):
            raise ValueError("resegment_outlier_sigma must be positive and finite")
        try:
            import SimpleITK as sitk
            from radiomics import featureextractor
        except ImportError as exc:
            raise ImportError(
                "IBSI reference extraction requires the optional 'ibsi' dependencies "
                "(SimpleITK and PyRadiomics)."
            ) from exc

        image = sitk.ReadImage(str(image_path))
        mask = sitk.ReadImage(str(mask_path))
        if image.GetDimension() != mask.GetDimension():
            raise ValueError("image and mask dimensions must match")
        if image.GetSize() != mask.GetSize():
            raise ValueError("image and mask sizes must match")

        processing_image = image
        processing_mask = mask
        effective_spacing = list(image.GetSpacing())
        resampled_resegmented_mask = None
        if resegment_range is not None and resegment_outlier_sigma is not None:
            raise ValueError("choose either resegment_range or resegment_outlier_sigma")
        if resegment_range is not None:
            lower, upper = (float(value) for value in resegment_range)
            if not np.isfinite([lower, upper]).all() or lower >= upper:
                raise ValueError("resegment_range must be a finite ascending interval")
            image_array = sitk.GetArrayFromImage(image)
            mask_array = sitk.GetArrayFromImage(mask) == int(label)
            intensity_mask = sitk.GetImageFromArray(
                ((image_array >= lower) & (image_array <= upper) & mask_array).astype(
                    np.uint8
                )
            )
            intensity_mask.CopyInformation(mask)
        else:
            intensity_mask = mask
        if resampled_pixel_spacing is not None:
            spacing = tuple(float(value) for value in resampled_pixel_spacing)
            if len(spacing) != 3 or any(
                not np.isfinite(value) or value <= 0 for value in spacing
            ):
                raise ValueError("resampled_pixel_spacing must contain three positive values")
            output_size = tuple(
                max(
                    1,
                    int(
                        np.ceil(
                            image.GetSize()[axis]
                            * image.GetSpacing()[axis]
                            / spacing[axis]
                        )
                    ),
                )
                for axis in range(3)
            )
            output_origin = tuple(
                image.GetOrigin()[axis]
                + (
                    image.GetSpacing()[axis] * (image.GetSize()[axis] - 1)
                    - spacing[axis] * (output_size[axis] - 1)
                )
                / 2
                for axis in range(3)
            )
            image_interpolator = (
                sitk.sitkLinear if interpolator is None else interpolator
            )
            resampler = sitk.ResampleImageFilter()
            resampler.SetOutputSpacing(spacing)
            resampler.SetSize(output_size)
            resampler.SetOutputOrigin(output_origin)
            resampler.SetOutputDirection(image.GetDirection())
            resampler.SetTransform(sitk.Transform())
            resampler.SetInterpolator(image_interpolator)
            resampler.SetDefaultPixelValue(0)
            resampler.SetOutputPixelType(sitk.sitkFloat32)
            processing_image = resampler.Execute(image)
            if round_resampled_intensities:
                rounded_array = np.rint(
                    sitk.GetArrayFromImage(processing_image)
                ).astype(np.int16)
                rounded_image = sitk.GetImageFromArray(rounded_array)
                rounded_image.CopyInformation(processing_image)
                processing_image = rounded_image

            mask_resampler = sitk.ResampleImageFilter()
            mask_resampler.SetOutputSpacing(spacing)
            mask_resampler.SetSize(output_size)
            mask_resampler.SetOutputOrigin(output_origin)
            mask_resampler.SetOutputDirection(mask.GetDirection())
            mask_resampler.SetTransform(sitk.Transform())
            mask_resampler.SetInterpolator(sitk.sitkLinear)
            mask_resampler.SetDefaultPixelValue(0)
            mask_resampler.SetOutputPixelType(sitk.sitkFloat32)
            resampled_mask = mask_resampler.Execute(intensity_mask)
            resampled_resegmented_mask = sitk.BinaryThreshold(
                resampled_mask,
                lowerThreshold=0.5,
                upperThreshold=1.0,
                insideValue=int(label),
                outsideValue=0,
            )
            processing_mask = resampled_resegmented_mask
            if resegment_outlier_sigma is not None:
                image_values = sitk.GetArrayFromImage(processing_image)
                mask_values = sitk.GetArrayFromImage(processing_mask) == int(label)
                valid_values = image_values[mask_values]
                mean = float(np.mean(valid_values))
                std = float(np.std(valid_values))
                lower = mean - float(resegment_outlier_sigma) * std
                upper = mean + float(resegment_outlier_sigma) * std
                processing_mask = sitk.BinaryThreshold(
                    processing_image,
                    lowerThreshold=lower,
                    upperThreshold=upper,
                    insideValue=int(label),
                    outsideValue=0,
                ) * processing_mask
        elif resegment_range is not None:
            processing_mask = intensity_mask
            effective_spacing = list(image.GetSpacing())

        extractor_settings: dict[str, Any] = {"label": int(label)}
        if bin_count is not None:
            extractor_settings["binCount"] = int(bin_count)
        else:
            extractor_settings["binWidth"] = float(bin_width)
        extractor = featureextractor.RadiomicsFeatureExtractor(
            **extractor_settings
        )
        if resegment_range is not None and resampled_pixel_spacing is None:
            extractor.settings["resegmentRange"] = [lower, upper]
        extractor.disableAllFeatures()
        for feature_class in feature_classes:
            extractor.enableFeatureClassByName(feature_class)
        raw = extractor.execute(processing_image, processing_mask, label=int(label))
        features = {}
        for key, value in raw.items():
            if key.startswith("diagnostics_"):
                continue
            scalar = np.asarray(value)
            if scalar.size != 1:
                continue
            numeric = float(scalar.reshape(-1)[0])
            if np.isfinite(numeric):
                features[key] = numeric
        diagnostics = {
            key: value
            for key, value in raw.items()
            if key.startswith("diagnostics_")
        }
        return {
            "implementation": "PyRadiomics",
            "version": str(diagnostics.get("diagnostics_Versions_PyRadiomics", "unknown")),
            "features": features,
            "diagnostics": diagnostics,
            "configuration": {
                "discretization": (
                    "fixed_bin_number"
                    if bin_count is not None
                    else "fixed_bin_size"
                ),
                "bin_count": None if bin_count is None else int(bin_count),
                "bin_width": (
                    None if bin_width is None else float(bin_width)
                ),
                "label": int(label),
                "feature_classes": list(feature_classes),
                "dimension": processing_image.GetDimension(),
                "spacing": effective_spacing,
                "resampled_full_volume": resampled_pixel_spacing is not None,
                "resampled_size": list(processing_image.GetSize()),
                "resegment_outlier_sigma": (
                    None
                    if resegment_outlier_sigma is None
                    else float(resegment_outlier_sigma)
                ),
                "round_resampled_intensities": bool(
                    round_resampled_intensities
                ),
            },
        }

    @classmethod
    def full_report(
        cls,
        data: np.ndarray,
        binary_mask: np.ndarray = None,
        *,
        levels: int = 256,
        bin_width: float | None = 25.0,
        discretization: str = "fixed_bin_width",
        spacing: float | tuple[float, ...] = 1.0,
        include_provenance: bool = True,
    ) -> Dict[str, Dict[str, float]]:
        """تقرير كامل بجميع الميزات."""
        if np.ma.isMaskedArray(data):
            image = np.ma.asarray(data, dtype=np.float64).filled(np.nan)
        else:
            image = np.asarray(data, dtype=np.float64)
        finite = image[np.isfinite(image)]
        if finite.size == 0:
            raise ValueError("Radiomics requires at least one finite image value.")
        has_invalid_pixels = finite.size != image.size
        # Keep the histogram section numeric; provenance belongs at report level.
        histogram = cls.histogram_features(
            finite if has_invalid_pixels else image,
            levels=levels,
            bin_width=float(bin_width or 25.0),
            discretization=discretization,
            include_provenance=False,
        )
        report = {
            "histogram": {
                key: value
                for key, value in histogram.items()
                if isinstance(value, (int, float, np.integer, np.floating))
            }
        }
        if image.ndim == 2 and not has_invalid_pixels:
            report["glcm"] = cls.glcm_features(
                image,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
            report["glrlm"] = cls.glrlm_features(
                data,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
            report["glszm"] = cls.glszm_features(
                data,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
            report["gldm"] = cls.gldm_features(
                data,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
            report["ngtdm"] = cls.ngtdm_features(
                image,
                levels=levels,
                bin_width=bin_width,
                discretization=discretization,
                include_provenance=include_provenance,
            )
        if binary_mask is not None and not has_invalid_pixels:
            report["shape"] = cls.shape_features(binary_mask, spacing=spacing)
        if has_invalid_pixels:
            report["masking"] = {
                "status": (
                    "first_order_only; spatial_features_not_computed_because_"
                    "validity_mask_is_not_supported"
                ),
                "excluded_pixel_count": int(image.size - finite.size),
                "included_pixel_count": int(finite.size),
            }
        feature_coverage = cls.feature_coverage()
        supported = [name for name, info in feature_coverage.items() if info["status"] == "supported"]
        unsupported = [name for name, info in feature_coverage.items() if info["status"] != "supported"]
        if include_provenance:
            report["provenance"] = {
                "profile": "CT_IBSI_SUBSET_V1",
                "status": (
                    "Selected IBSI-aligned features; official benchmark "
                    "validation is required before claiming full compliance."
                ),
                "levels": int(levels),
                "bin_width": float(bin_width or 25.0),
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
                "feature_coverage": feature_coverage,
                "supported_feature_classes": supported,
                "unsupported_feature_classes": unsupported,
            }
        report["feature_coverage"] = feature_coverage
        return report

    @staticmethod
    def preprocess_ct(
        data: np.ndarray,
        *,
        spacing: tuple[float, ...],
        target_spacing: tuple[float, ...] | None = None,
        resegment: tuple[float, float] | None = None,
        interpolation_order: int = 1,
    ) -> tuple[np.ndarray | np.ma.MaskedArray, dict]:
        """Apply an explicit, reproducible CT radiomics preprocessing policy.

        Resampling is opt-in because IBSI makes processing scheme choices
        study-specific. Resegmentation returns a shape-preserving masked array;
        pass it to ``full_report`` so excluded voxels remain excluded. The
        returned provenance must accompany features, and official IBSI
        benchmarking is still required for compliance claims.
        """
        image = np.asarray(data, dtype=np.float64)
        source_spacing = tuple(float(value) for value in spacing)
        if image.ndim != len(source_spacing) or any(
            not np.isfinite(value) or value <= 0 for value in source_spacing
        ):
            raise ValueError("spacing must match data dimensions and be positive")
        if not np.isfinite(image).all():
            raise ValueError("CT data must contain only finite values")
        if target_spacing is not None:
            destination = tuple(float(value) for value in target_spacing)
            if len(destination) != image.ndim or any(
                not np.isfinite(value) or value <= 0 for value in destination
            ):
                raise ValueError("target_spacing must match data dimensions")
            factors = tuple(
                source / target for source, target in zip(source_spacing, destination)
            )
            if any(abs(factor - 1.0) > 1e-12 for factor in factors):
                image = zoom(image, factors, order=interpolation_order)
            output_spacing = destination
        else:
            output_spacing = source_spacing
        if resegment is not None:
            lower, upper = (float(value) for value in resegment)
            if not np.isfinite([lower, upper]).all() or lower >= upper:
                raise ValueError("resegment must be a finite (lower, upper) interval")
            resegmentation_mask = (image >= lower) & (image <= upper)
            if not np.any(resegmentation_mask):
                raise ValueError("resegment removed all voxels")
            image = np.ma.array(image, mask=~resegmentation_mask, copy=False)
        provenance = {
            "profile": "CT_IBSI_SUBSET_V1",
            "source_spacing": list(source_spacing),
            "target_spacing": list(output_spacing),
            "resampled": target_spacing is not None,
            "interpolation_order": (
                int(interpolation_order) if target_spacing is not None else None
            ),
            "resegmentation": (
                None if resegment is None else [float(resegment[0]), float(resegment[1])]
            ),
        }
        return image, provenance


class XAIExplainer:
    """
    الذكاء الاصطناعي القابل للتفسير (XAI) لنماذج الرؤية.
    يستخدم Attention Rollout لـ Vision Transformer.
    """

    @staticmethod
    def compute_attention_map(model, pixel_values: Any) -> np.ndarray:
        """استخراج خريطة الانتباه من ViT باستخدام Attention Rollout.

        Attention Rollout averages attention HEADS within each layer and then
        composes layers by matrix multiplication (Abnar & Zuidema, 2020).
        That composition is the published 'rollout' approximation — it is
        reported here as such, not as per-pixel ground truth.
        """
        if torch is None:
            raise ImportError("compute_attention_map requires the optional torch dependency")
        was_training = bool(getattr(model, "training", False))
        if was_training:
            model.eval()
        try:
            with torch.no_grad():
                outputs = model(pixel_values, output_attentions=True)
                attentions = outputs.attentions
        finally:
            if was_training:
                model.train()
        # Attention Rollout: ضرب مصفوفات الانتباه عبر الطبقات
        attn = attentions[0][0, :, 1:, 1:].mean(dim=0)  # [num_patches, num_patches]
        for layer in attentions[1:]:
            layer_attn = layer[0, :, 1:, 1:].mean(dim=0)
            attn = attn @ layer_attn
        # Reduce the [N, N] rollout matrix to one attention value per patch:
        # the mean attention each patch RECEIVES across all query patches.
        # (The previous code reshaped the whole N x N matrix directly, which
        # can only ever fail or fall back to a meaningless 1 x N strip.)
        patch_attention = attn.mean(dim=0)
        # تطبيع
        patch_attention = (patch_attention - patch_attention.min()) / max(
            patch_attention.max() - patch_attention.min(), 1e-9
        )
        # إعادة تشكيل إلى أبعاد الصورة (patch grid)
        side = int(round(float(np.sqrt(patch_attention.shape[0]))))
        if side > 0 and side * side == patch_attention.shape[0]:
            return patch_attention.cpu().numpy().reshape(side, side)
        return patch_attention.cpu().numpy().reshape(1, -1)

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
