"""
MONAI Preprocessing Engine for Medical Imaging.

Provides standardized preprocessing pipelines using MONAI transforms.
Includes volume preprocessing, segmentation preparation.
Metrics computation is delegated to ClinicalMetrics.
"""

from __future__ import annotations

import logging

import numpy as np
from monai.data import MetaTensor

from core.constants import DEFAULT_TARGET_SIZE
from engines.clinical_metrics import ClinicalMetrics

logger = logging.getLogger(__name__)

try:
    from monai.transforms import Compose, EnsureChannelFirst, NormalizeIntensity, Resize
    MONAI_TRANSFORMS_AVAILABLE = True
except ImportError:
    MONAI_TRANSFORMS_AVAILABLE = False
    logger.warning("MONAI transforms unavailable; MONAI preprocessing is disabled.")


class MONAIPreprocessor:
    """
    Medical Open Network for AI (MONAI) Preprocessing Pipeline.
    
    Provides standardized transforms for medical image preprocessing:
    - Channel dimension handling
    - Spatial resizing (trilinear for 3D, bilinear for 2D - auto-detected)
    - Intensity normalization (non-zero, channel-wise)
    
    Reference: MONAI documentation (Project MONAI, https://monai.io).
    """
    
    def __init__(self, target_size: tuple = DEFAULT_TARGET_SIZE):
        """Initialize the MONAI preprocessing pipeline."""
        self.target_size = target_size
    
    def preprocess_volume(self, volume: np.ndarray) -> MetaTensor:
        """
        Preprocess a 2D or 3D volume using MONAI transforms.
        
        Automatically detects input dimensionality and selects the
        appropriate interpolation mode (trilinear for 3D, bilinear for 2D).
        
        Args:
            volume: Input numpy array (H, W) for 2D or (H, W, D) / (C, H, W, D) for 3D
            
        Returns:
            Preprocessed MetaTensor ready for model inference

        Raises:
            RuntimeError: If MONAI transforms are not installed.
        """
        if not MONAI_TRANSFORMS_AVAILABLE:
            raise RuntimeError(
                "MONAI transforms are not installed; MONAI preprocessing is unavailable. "
                "Install the optional 'monai' dependency to use this feature."
            )

        volume = np.asarray(volume)
        if volume.ndim not in (2, 3):
            raise ValueError(
                "MONAI preprocessing requires a 2D or 3D original image; "
                f"received {volume.ndim}D data."
            )
        if volume.size == 0 or not np.isfinite(volume).all():
            raise ValueError(
                "MONAI preprocessing requires a non-empty image with finite values."
            )
        if min(volume.shape) < 2:
            raise ValueError(
                "MONAI preprocessing requires at least two samples on each axis."
            )

        is_3d = volume.ndim >= 3
        spatial = self.target_size if is_3d else self.target_size[:2]
        mode = 'trilinear' if is_3d else 'bilinear'
        # 2D slices are single-channel; a channel-wise percentile would be a no-op.
        channel_wise = is_3d

        transforms = Compose([
            EnsureChannelFirst(channel_dim='no_channel'),
            Resize(spatial_size=spatial, mode=mode),
            NormalizeIntensity(nonzero=True, channel_wise=channel_wise),
        ])
        return transforms(volume)
    
    def segment_with_monai(self, volume: np.ndarray) -> MetaTensor:
        """
        Prepare volume for MONAI-based segmentation (e.g., UNet).
        
        Args:
            volume: Input 3D numpy array
            
        Returns:
            Preprocessed volume ready for segmentation model
        """
        return self.preprocess_volume(volume)
    
    @staticmethod
    def compute_dice_score(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Compute Dice Similarity Coefficient (DSC) via ClinicalMetrics.
        
        Delegates to ClinicalMetrics.dice_score for single source of truth.
        """
        return ClinicalMetrics.dice_score(pred, target)
    
    @staticmethod
    def compute_hausdorff_distance(pred: np.ndarray, target: np.ndarray) -> float:
        """
        Compute Hausdorff Distance between two binary masks via ClinicalMetrics.
        
        Delegates to ClinicalMetrics.hausdorff_distance for single source of truth.
        """
        return ClinicalMetrics.hausdorff_distance(pred, target)
