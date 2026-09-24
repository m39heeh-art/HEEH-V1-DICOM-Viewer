"""Cached loaders for volumetric images and demonstration models."""
from __future__ import annotations

import os

import streamlit as st
import nibabel as nib
import numpy as np
import torch
import SimpleITK as sitk

from core.logging_config import get_logger

logger = get_logger(__name__)

@st.cache_data(show_spinner=False, max_entries=16)
def _load_volume_file_cached(load_path: str, mtime: float):
    """Read a volumetric image (NIfTI/NRRD/MHA) keyed on path + mtime so that
    repeated slice-viewer interactions do not re-read the entire file from disk."""
    try:
        img = nib.load(load_path)
        data = np.asarray(img.dataobj, dtype=np.float32)
        slope = float(getattr(img, 'scl_slope', 1.0) or 1.0)
        intercept = float(getattr(img, 'scl_inter', 0.0) or 0.0)
        if slope != 1.0 or intercept != 0.0:
            data = data * slope + intercept
        return data
    except (OSError, ValueError, nib.filebasedimages.ImageFileError) as nib_error:
        try:
            sitk_img = sitk.ReadImage(load_path)
        except (OSError, RuntimeError, ValueError) as sitk_error:
            raise RuntimeError(
                f"Unable to read volume with NIfTI or SimpleITK loaders: "
                f"{nib_error}"
            ) from sitk_error
        return sitk.GetArrayFromImage(sitk_img).astype(np.float32)


@st.cache_resource(show_spinner=False)
def _load_medical_model_cached(model_id: str):
    """
    Medical Docstring: تحميل الموارد مع التخزين المؤقت وإدارة الحوسبة المتوازية.
    البروتوكول: التحقق من الوصول للمستودع لضمان استمرارية الخدمة السريرية.
    """
    token = os.environ.get("HF_TOKEN", "")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        processor = AutoImageProcessor.from_pretrained(model_id, token=token) if token else AutoImageProcessor.from_pretrained(model_id)
        model = AutoModelForImageClassification.from_pretrained(model_id, token=token).to(device) if token else AutoModelForImageClassification.from_pretrained(model_id).to(device)

        # تحويل النموذج لوضع التقييم لضمان القيمة التشخيصية الخام (Raw Value Preservation)
        model.eval()

        # Freeze weights for inference
        for param in model.parameters():
            param.requires_grad = False

        return processor, model, device

    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("Medical AI model unavailable: %s", exc, exc_info=True)
        return None, None, device
