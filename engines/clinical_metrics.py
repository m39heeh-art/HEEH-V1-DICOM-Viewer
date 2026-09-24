"""
Clinical Metrics Engine for Segmentation Evaluation.

Provides standard medical imaging evaluation metrics:
- Sensitivity (Recall)
- Specificity
- Precision (PPV)
- Dice Coefficient (F1)
- IoU (Jaccard Index)
- Hausdorff Distance
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt

from core.metric_results import (
    MetricResult,
    defined_metric,
    undefined_metric,
)


class ClinicalMetrics:
    """
    Clinical Evaluation Metrics for Medical Image Segmentation.
    
    Implements standard metrics per:
    - RSNA/ACR Guidelines
    - MICCAI Challenge Standards
    - Radiomics Quality Score (RQS)
    
    All metrics handle edge cases (empty predictions/targets) gracefully.
    """

    @staticmethod
    def _validated_masks(
        pred: np.ndarray, target: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Validate and normalize masks before calculating any metric."""
        pred_arr = np.asarray(pred)
        target_arr = np.asarray(target)
        if pred_arr.shape != target_arr.shape:
            raise ValueError(
                f"Prediction and target shapes must match: "
                f"{pred_arr.shape} != {target_arr.shape}."
            )
        if pred_arr.size == 0:
            raise ValueError("Prediction and target masks must not be empty.")
        if not np.isfinite(pred_arr).all() or not np.isfinite(target_arr).all():
            raise ValueError("Prediction and target masks must contain finite values.")
        return pred_arr > 0, target_arr > 0
    
    @staticmethod
    def sensitivity(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Sensitivity (Recall, True Positive Rate).
        
        TP / (TP + FN) - Fraction of actual positives correctly identified.
        
        Args:
            pred: Binary prediction mask
            target: Binary ground truth mask
            
        Returns:
            Sensitivity in [0, 1]
        """
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        tp = np.sum(pred & target)
        fn = np.sum(~pred & target)
        return float(tp / max(tp + fn, 1e-9))

    @staticmethod
    def sensitivity_result(
        pred: np.ndarray, target: np.ndarray
    ) -> MetricResult[float]:
        """Return sensitivity without hiding an absent-positive denominator."""
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        denominator = int(np.sum(target))
        if denominator == 0:
            return undefined_metric("target contains no positive samples")
        return defined_metric(float(np.sum(pred & target) / denominator))
    
    @staticmethod
    def specificity(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Specificity (True Negative Rate).
        
        TN / (TN + FP) - Fraction of actual negatives correctly identified.
        
        Args:
            pred: Binary prediction mask
            target: Binary ground truth mask
            
        Returns:
            Specificity in [0, 1]
        """
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        tn = np.sum(~pred & ~target)
        fp = np.sum(pred & ~target)
        return float(tn / max(tn + fp, 1e-9))

    @staticmethod
    def specificity_result(
        pred: np.ndarray, target: np.ndarray
    ) -> MetricResult[float]:
        """Return specificity without hiding an absent-negative denominator."""
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        denominator = int(np.sum(~target))
        if denominator == 0:
            return undefined_metric("target contains no negative samples")
        return defined_metric(float(np.sum(~pred & ~target) / denominator))
    
    @staticmethod
    def precision(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Precision (Positive Predictive Value).
        
        TP / (TP + FP) - Fraction of predicted positives that are actual positives.
        
        Args:
            pred: Binary prediction mask
            target: Binary ground truth mask
            
        Returns:
            Precision in [0, 1]
        """
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        tp = np.sum(pred & target)
        fp = np.sum(pred & ~target)
        return float(tp / max(tp + fp, 1e-9))

    @staticmethod
    def precision_result(
        pred: np.ndarray, target: np.ndarray
    ) -> MetricResult[float]:
        """Return precision without hiding an absent-prediction denominator."""
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        denominator = int(np.sum(pred))
        if denominator == 0:
            return undefined_metric("prediction contains no positive samples")
        return defined_metric(float(np.sum(pred & target) / denominator))
    
    @staticmethod
    def iou_score(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Intersection over Union (Jaccard Index).
        
        |X ∩ Y| / |X ∪ Y| - Overlap between prediction and ground truth.
        
        Args:
            pred: Binary prediction mask
            target: Binary ground truth mask
            
        Returns:
            IoU in [0, 1]
        """
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        intersection = np.sum(pred & target)
        union = np.sum(pred | target)
        return float(intersection / max(union, 1e-9))
    
    @staticmethod
    def dice_score(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Dice Similarity Coefficient (F1 Score).
        
        2 * |X ∩ Y| / (|X| + |Y|) - Harmonic mean of precision and recall.
        
        Args:
            pred: Binary prediction mask
            target: Binary ground truth mask
            
        Returns:
            Dice score in [0, 1]
        """
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        intersection = np.sum(pred & target)
        sum_pred = np.sum(pred)
        sum_target = np.sum(target)
        
        if sum_pred + sum_target == 0:
            return 1.0
            
        return float(2.0 * intersection / (sum_pred + sum_target))
    
    @staticmethod
    def _surface_points(mask: np.ndarray) -> np.ndarray:
        """Return boundary voxels, retaining a single voxel object."""
        if not np.any(mask):
            return np.empty((0, mask.ndim), dtype=np.intp)
        structure = np.ones((3,) * mask.ndim, dtype=bool)
        surface = mask & ~binary_erosion(mask, structure=structure, border_value=0)
        return np.argwhere(surface)

    @staticmethod
    def _surface_distance_metric(
        pred: np.ndarray,
        target: np.ndarray,
        *,
        spacing: tuple[float, ...] | None,
        percentile: float | None,
    ) -> float:
        """Compute a symmetric physical surface distance."""
        pred_pts = ClinicalMetrics._surface_points(pred)
        target_pts = ClinicalMetrics._surface_points(target)

        if len(pred_pts) == 0 or len(target_pts) == 0:
            return float('inf')

        sampling = tuple(float(value) for value in (spacing or (1.0,) * pred.ndim))
        if len(sampling) != pred.ndim or any(value <= 0 for value in sampling):
            raise ValueError("spacing must contain one positive value per mask dimension")
        pred_to_target = distance_transform_edt(
            ~target, sampling=sampling
        )[tuple(pred_pts.T)]
        target_to_pred = distance_transform_edt(
            ~pred, sampling=sampling
        )[tuple(target_pts.T)]
        distances = np.concatenate((pred_to_target, target_to_pred))
        if percentile is None:
            return float(np.mean(distances))
        return float(np.percentile(distances, percentile))

    @staticmethod
    def hausdorff_distance(
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> float:
        """Maximum true surface distance in physical units."""
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        return ClinicalMetrics._surface_distance_metric(
            pred, target, spacing=spacing, percentile=100.0
        )

    @staticmethod
    def hausdorff_distance_result(
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> MetricResult[float]:
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        if not np.any(pred) or not np.any(target):
            return undefined_metric("surface distance requires two non-empty masks")
        return defined_metric(
            ClinicalMetrics._surface_distance_metric(
                pred, target, spacing=spacing, percentile=100.0
            )
        )

    @staticmethod
    def hausdorff95(
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> float:
        """Robust 95th-percentile symmetric surface distance."""
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        return ClinicalMetrics._surface_distance_metric(
            pred, target, spacing=spacing, percentile=95.0
        )

    @staticmethod
    def hausdorff95_result(
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> MetricResult[float]:
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        if not np.any(pred) or not np.any(target):
            return undefined_metric("surface distance requires two non-empty masks")
        return defined_metric(
            ClinicalMetrics._surface_distance_metric(
                pred, target, spacing=spacing, percentile=95.0
            )
        )

    @staticmethod
    def average_surface_distance(
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> float:
        """
        Average Symmetric Surface Distance (ASSD).
        
        Mean of distances from each surface point to the nearest point
        on the other surface.
        """
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        return ClinicalMetrics._surface_distance_metric(
            pred, target, spacing=spacing, percentile=None
        )

    @staticmethod
    def average_surface_distance_result(
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> MetricResult[float]:
        pred, target = ClinicalMetrics._validated_masks(pred, target)
        if not np.any(pred) or not np.any(target):
            return undefined_metric("surface distance requires two non-empty masks")
        return defined_metric(
            ClinicalMetrics._surface_distance_metric(
                pred, target, spacing=spacing, percentile=None
            )
        )

    @classmethod
    def report_results(
        cls,
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> dict[str, MetricResult[float]]:
        """Return status-aware metrics while keeping :meth:`report` numeric."""
        pred_arr, target_arr = cls._validated_masks(pred, target)
        dice = int(np.sum(pred_arr & target_arr))
        dice_denominator = int(np.sum(pred_arr) + np.sum(target_arr))
        iou_denominator = int(np.sum(pred_arr | target_arr))
        dice_result = (
            defined_metric(1.0)
            if dice_denominator == 0
            else defined_metric(2.0 * dice / dice_denominator)
        )
        iou_result = (
            defined_metric(1.0)
            if iou_denominator == 0
            else defined_metric(float(dice / iou_denominator))
        )
        return {
            "Dice": dice_result,
            "IoU": iou_result,
            "Sensitivity": cls.sensitivity_result(pred_arr, target_arr),
            "Specificity": cls.specificity_result(pred_arr, target_arr),
            "Precision": cls.precision_result(pred_arr, target_arr),
            "Hausdorff_Distance": cls.hausdorff_distance_result(
                pred_arr, target_arr, spacing
            ),
            "Hausdorff95_Distance": cls.hausdorff95_result(
                pred_arr, target_arr, spacing
            ),
            "Avg_Surface_Distance": cls.average_surface_distance_result(
                pred_arr, target_arr, spacing
            ),
        }

    @classmethod
    def report(
        cls,
        pred: np.ndarray,
        target: np.ndarray,
        spacing: tuple[float, ...] | None = None,
    ) -> dict[str, float]:
        """
        Generate comprehensive metrics report.
        
        Args:
            pred: Binary prediction mask
            target: Binary ground truth mask
            
        Returns:
            Dictionary with all metrics
        """
        iou = cls.iou_score(pred, target)
        return {
            "Dice": cls.dice_score(pred, target),
            "IoU": iou,
            "Sensitivity": cls.sensitivity(pred, target),
            "Specificity": cls.specificity(pred, target),
            "Precision": cls.precision(pred, target),
            "Hausdorff_Distance": cls.hausdorff_distance(pred, target, spacing),
            "Hausdorff95_Distance": cls.hausdorff95(pred, target, spacing),
            "Avg_Surface_Distance": cls.average_surface_distance(pred, target, spacing),
        }