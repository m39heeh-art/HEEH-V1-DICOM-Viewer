"""
SimpleITK Registration Engine for Medical Image Alignment.

Provides image registration, resampling, and bias field correction.
Supports rigid, affine, and BSpline transformations.
"""

from __future__ import annotations

import numpy as np
import SimpleITK as sitk


class SimpleITKRegistration:
    """
    SimpleITK-based Medical Image Registration.
    
    Supports:
    - Isotropic resampling
    - N4 Bias Field Correction (MRI)
    - Rigid registration (Euler3D)
    - Extensible to Affine and BSpline
    
    Reference: SimpleITK Documentation, ITK Software Guide.
    """
    
    @staticmethod
    def resample_to_isotropic(
        image_np: np.ndarray, 
        spacing: tuple[float, float, float] = (1.0, 1.0, 1.0)
    ) -> np.ndarray:
        """
        Resample image to isotropic voxel spacing.
        
        Computes new size to preserve physical dimensions while
        making voxel spacing equal in all dimensions.
        
        Args:
            image_np: Input image as numpy array
            spacing: Original voxel spacing (sx, sy, sz)
            
        Returns:
            Resampled isotropic image as numpy array
        """
        image_np = np.asarray(image_np)
        if image_np.ndim not in (2, 3):
            raise ValueError(
                "SimpleITK resampling requires a 2D or 3D original image; "
                f"received {image_np.ndim}D data."
            )
        if image_np.size == 0 or not np.isfinite(image_np).all():
            raise ValueError(
                "SimpleITK resampling requires a non-empty image with finite values."
            )
        if len(spacing) != image_np.ndim or any(
            not np.isfinite(value) or value <= 0 for value in spacing
        ):
            raise ValueError(
                "Spacing must contain one positive finite value per image dimension."
            )
        if min(image_np.shape) < 2:
            raise ValueError(
                "SimpleITK resampling requires at least two samples on each axis."
            )
        img = sitk.GetImageFromArray(image_np.astype(np.float32, copy=False))
        img.SetSpacing(spacing)
        
        original_size = img.GetSize()
        original_spacing = img.GetSpacing()
        
        # Target: minimum spacing across all dimensions
        new_spacing = [min(original_spacing)] * img.GetDimension()
        
        new_size = [
            int(round(orig_sz * orig_spc / new_spc))
            for orig_sz, orig_spc, new_spc in zip(original_size, original_spacing, new_spacing)
        ]
        
        resampler = sitk.ResampleImageFilter()
        resampler.SetSize(new_size)
        resampler.SetOutputSpacing(new_spacing)
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetDefaultPixelValue(0)
        
        resampled = resampler.Execute(img)
        return sitk.GetArrayFromImage(resampled)
    
    @staticmethod
    def n4_bias_correction(image_np: np.ndarray) -> np.ndarray:
        """
        Apply N4 Bias Field Correction for MRI inhomogeneity.
        
        Corrects low-frequency intensity non-uniformity caused
        by RF field inhomogeneities in MRI.
        
        Args:
            image_np: Input MRI image as numpy array
            
        Returns:
            Bias-corrected image as numpy array
        """
        img = sitk.GetImageFromArray(image_np.astype(np.float32))
        corrector = sitk.N4BiasFieldCorrectionImageFilter()
        corrected = corrector.Execute(img)
        return sitk.GetArrayFromImage(corrected)
    
    @staticmethod
    def register_rigid(
        fixed: np.ndarray, 
        moving: np.ndarray
    ) -> tuple[np.ndarray, sitk.Transform]:
        """
        Rigid registration (translation + rotation) of moving to fixed image.
        
        Uses Mean Squares metric with Regular Step Gradient Descent optimizer.
        Initial transform centered on image geometry.
        
        Args:
            fixed: Reference image (target)
            moving: Image to be aligned
            
        Returns:
            Tuple of (registered_image, transform)
        """
        fixed_img = sitk.GetImageFromArray(fixed.astype(np.float32))
        moving_img = sitk.GetImageFromArray(moving.astype(np.float32))
        
        registration_method = sitk.ImageRegistrationMethod()
        registration_method.SetMetricAsMeanSquares()
        registration_method.SetInterpolator(sitk.sitkLinear)
        registration_method.SetOptimizerAsRegularStepGradientDescent(
            learningRate=1.0,
            minStep=1e-4,
            numberOfIterations=200,
            gradientMagnitudeTolerance=1e-6
        )
        
        # Initialize transform at geometric center
        transform = sitk.CenteredTransformInitializer(
            fixed_img, 
            moving_img, 
            sitk.Euler3DTransform()
        )
        registration_method.SetInitialTransform(transform)
        
        final_transform = registration_method.Execute(fixed_img, moving_img)
        
        # Resample moving image to fixed space
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(fixed_img)
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetTransform(final_transform)
        resampler.SetDefaultPixelValue(0)
        
        result = resampler.Execute(moving_img)
        return sitk.GetArrayFromImage(result), final_transform
    
    @staticmethod
    def register_affine(
        fixed: np.ndarray,
        moving: np.ndarray
    ) -> tuple[np.ndarray, sitk.Transform]:
        """
        Affine registration (translation + rotation + scaling + shear).
        
        More flexible than rigid, allows for global scaling/shear differences.
        """
        fixed_img = sitk.GetImageFromArray(fixed.astype(np.float32))
        moving_img = sitk.GetImageFromArray(moving.astype(np.float32))
        
        registration_method = sitk.ImageRegistrationMethod()
        registration_method.SetMetricAsMeanSquares()
        registration_method.SetInterpolator(sitk.sitkLinear)
        registration_method.SetOptimizerAsRegularStepGradientDescent(
            learningRate=1.0,
            minStep=1e-4,
            numberOfIterations=300
        )
        
        transform = sitk.CenteredTransformInitializer(
            fixed_img,
            moving_img,
            sitk.AffineTransform(3)
        )
        registration_method.SetInitialTransform(transform)
        
        final_transform = registration_method.Execute(fixed_img, moving_img)
        
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(fixed_img)
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetTransform(final_transform)
        resampler.SetDefaultPixelValue(0)
        
        result = resampler.Execute(moving_img)
        return sitk.GetArrayFromImage(result), final_transform