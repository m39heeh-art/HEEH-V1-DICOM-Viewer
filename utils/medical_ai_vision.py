"""Split module: MedicalAIVisionEngine (from app.py)."""
import streamlit as st
import numpy as np
import torch
from PIL import Image
from skimage.feature import graycomatrix, graycoprops

from core.loaders import _load_medical_model_cached
from core.constants import AI_MODEL_REGISTRY

class MedicalAIVisionEngine:
    """
    Medical Docstring: محرك رؤية متعدد النطاقات (Multi-Domain ViT).
    الأهداف: الصدر، الدماغ، والأورام.
    يستخدم التخزين المؤقت التلقائي (Caching) عبر @st.cache_resource.
    """

    def __init__(self):
        """Initialize the medical AI vision engine and its cached session."""
        self.domain_registry = {
            "chest": {
                "model_id": AI_MODEL_REGISTRY["chest"],
                "modalities": {"CR", "DX", "XRAY"},
            },
            "brain": {
                "model_id": AI_MODEL_REGISTRY["brain"],
                "modalities": {"MR"},
            },
            "age": {
                "model_id": AI_MODEL_REGISTRY["age"],
                "modalities": {"CR", "DX", "XRAY"},
            },
        }
        self.confidence_threshold = 0.85
        self.processor = None
        self.model = None
        self.last_provenance = {}

    def _get_domain(self):
        """Return the matching HuggingFace model domain for a task, or None."""
        domain = st.session_state.get('ai_domain', 'brain')
        return domain if domain in self.domain_registry else 'brain'

    def _get_model_id(self):
        """Resolve the model identifier to load for the current setting."""
        domain = self._get_domain()
        return self.domain_registry[domain]["model_id"]

    def available_domains(self, modality: str) -> list[str]:
        """Return model domains declared compatible with a modality."""
        parts = [part.strip() for part in str(modality or "").upper().split("/")]
        normalized = parts[-1] if parts else "UNKNOWN"
        if normalized.startswith("DICOM "):
            normalized = normalized.replace("DICOM ", "", 1).strip()
        return [
            name for name, config in self.domain_registry.items()
            if normalized in config["modalities"]
        ]

    def _model_is_compatible(self, modality: str) -> bool:
        return self._get_domain() in self.available_domains(modality)

    def _ensure_loaded(self):
        """Load the model+processor once, triggering domain selection."""
        model_id = self._get_model_id()
        if getattr(self, '_loaded_model_id', None) != model_id or self.processor is None:
            self.processor, self.model, _ = _load_medical_model_cached(model_id)
            self._loaded_model_id = model_id if self.processor is not None else None
        return self.processor is not None

    def prepare_inputs(self, image_np: np.ndarray, modality: str) -> dict:
        """Prepare ViT input without treating resizing as image reconstruction."""
        if not self._ensure_loaded():
            raise RuntimeError("MODEL_UNAVAILABLE")
        image = np.asarray(image_np)
        if image.ndim not in (2, 3):
            raise ValueError("ViT input must be a 2D grayscale or RGB image.")
        source = Image.fromarray(image).convert("RGB")
        inputs = self.processor(images=source, return_tensors="pt")
        pixel_values = inputs.get("pixel_values")
        self.last_provenance = {
            "operation": "model_input_resize",
            "source_modality": str(modality or "UNKNOWN"),
            "source_shape": [int(v) for v in image.shape],
            "source_dtype": str(image.dtype),
            "source_representation": "rendered display image; not calibrated voxel data",
            "model_id": self._get_model_id(),
            "processor_class": type(self.processor).__name__,
            "model_input_shape": (
                [int(v) for v in pixel_values.shape]
                if pixel_values is not None else None
            ),
            "model_input_is_quantitative": False,
            "super_resolution": False,
            "warning": (
                "Resizing is for classification input only. It does not recover "
                "missing detail and must not replace source data."
            ),
        }
        return inputs

    def infer(
        self,
        image_np,
        hu_data=None,
        allow_hu_fallback: bool = False,
        modality: str = "UNKNOWN",
    ):
        """
        Medical Docstring: الاستدلال السريري مع التخزين المؤقت وفحص عتبة اليقين.
        image_np: uint8 display image (للنموذج ViT)
        hu_data: float32 HU values (للمصنف الفيزيائي الاحتياطي)
        """
        try:
            self.last_provenance = {}
            if str(modality).upper() != "UNKNOWN" and not self._model_is_compatible(modality):
                return (
                    "MODEL_INCOMPATIBLE",
                    0.0,
                    f"Model domain '{self._get_domain()}' is not validated for "
                    f"modality '{modality}'. No model input was generated.",
                )
            if not self._ensure_loaded():
                if not allow_hu_fallback:
                    return (
                        "MODEL_UNAVAILABLE",
                        0.0,
                        "No validated model is available for this modality.",
                    )
                return self._fallback(hu_data if hu_data is not None else image_np)

            inputs = self.prepare_inputs(image_np, modality)

            with torch.inference_mode():
                outputs = self.model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                conf, top_idx = torch.max(probs, dim=-1)
                conf_val = float(conf.item())

                if conf_val < self.confidence_threshold:
                    return "UNCERTAIN_DATA_ALERT", conf_val, "Low Confidence - Manual Review Required"

                label = self.model.config.id2label[top_idx.item()]
                return label, conf_val, (
                    f"Demo model ({self._get_domain()}) - resized classification "
                    "input only; research use, not clinical grade"
                )

        except Exception:
            if not allow_hu_fallback:
                return (
                    "INFERENCE_UNAVAILABLE",
                    0.0,
                    "Inference failed; no heuristic modality fallback was used.",
                )
            return self._fallback(hu_data if hu_data is not None else image_np)

    def _fallback(self, image_np):
        """Return a hand-rolled fallback prediction when the model is unavailable."""
        data = image_np.astype(np.float32)
        if data.size < 16:
            return "INSUFFICIENT ROI", 0.0, "Fallback: ROI too small for analysis"

        # --- 1. HU Statistics ---
        mean_hu = float(np.mean(data))
        std_hu = float(np.std(data))
        p10 = float(np.percentile(data, 10))
        p90 = float(np.percentile(data, 90))
        hu_range = p90 - p10

        # --- 2. GLCM Texture ---
        norm = np.clip((data - data.min()) / max(data.max() - data.min(), 1.0) * 255, 0, 255).astype(np.uint8)
        glcm = graycomatrix(norm, distances=[1], angles=[0], levels=256, symmetric=True)
        contrast = float(graycoprops(glcm, 'contrast')[0, 0])
        homogeneity = float(graycoprops(glcm, 'homogeneity')[0, 0])
        energy = float(graycoprops(glcm, 'energy')[0, 0])

        # --- 3. Histogram Features ---
        flat = data.flatten()
        hist, _ = np.histogram(flat, bins=64)
        hist_p = hist / max(hist.sum(), 1)
        entropy = -float(np.sum(hist_p * np.log2(hist_p + 1e-12)))

        # --- 4. Multi-Feature Decision Logic (APPEARANCE-ONLY categories) ---
        #
        # IMPORTANT: The labels below describe the APPARENT TISSUE TYPE based
        # on HU value and texture statistics. They are NOT medical diagnoses.
        # Identical HU ranges can correspond to many different pathologies or
        # normal variants; a real diagnosis requires a trained radiologist.
        if std_hu < 1.0 and energy > 0.99:
            if -5 <= mean_hu <= 5:
                return "BACKGROUND", 0.95, "Fallback: uniform near-zero region"
            elif mean_hu < -200:
                return "AIR/LUNG (uniform)", 0.95, f"Fallback: HU={mean_hu:.0f}"
            elif mean_hu < -20:
                return "FAT (uniform)", 0.95, f"Fallback: HU={mean_hu:.0f}"
            elif mean_hu < 150:
                return f"SOFT TISSUE (uniform, HU={mean_hu:.0f})", 0.90, "Fallback: uniform"
            elif mean_hu < 400:
                return "TRABECULAR BONE (uniform)", 0.90, f"Fallback: HU={mean_hu:.0f}, uniform"
            else:
                return "CORTICAL BONE (uniform)", 0.95, f"Fallback: HU={mean_hu:.0f}, uniform"

        if mean_hu < -400:
            if contrast < 10:
                return "AIR (uniform)", 0.92, f"Fallback: HU={mean_hu:.0f}, minimal texture"
            elif hu_range < 150:
                return "LUNG (low texture)", 0.85, f"Fallback: HU={mean_hu:.0f}, narrow range"
            else:
                return "LUNG PARENCHYMA", 0.85, f"Fallback: HU={mean_hu:.0f}, range={hu_range:.0f}"

        elif -200 <= mean_hu < -20:
            if energy > 0.3:
                return "FAT (homogeneous)", 0.88, f"Fallback: HU={mean_hu:.0f}, energy={energy:.2f}"
            elif std_hu > 30:
                return "FAT (heterogeneous)", 0.80, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"
            else:
                return "FAT", 0.85, f"Fallback: HU={mean_hu:.0f}, texture={contrast:.0f}"

        elif -20 <= mean_hu < 30:
            if energy > 0.5:
                return "FLUID-LIKE (homogeneous)", 0.90, f"Fallback: HU={mean_hu:.0f}, energy={energy:.2f}"
            elif homogeneity > 0.3:
                return "FLUID-LIKE", 0.85, f"Fallback: HU={mean_hu:.0f}, homo={homogeneity:.2f}"
            else:
                return "MIXED LOW-DENSITY", 0.80, f"Fallback: HU={mean_hu:.0f}, heterogeneous"

        elif 30 <= mean_hu < 80:
            if entropy > 5.2:
                return "SOFT TISSUE (heterogeneous)", 0.78, f"Fallback: HU={mean_hu:.0f}, entropy={entropy:.2f}"
            elif std_hu > 35:
                return "SOFT TISSUE (heterogeneous)", 0.80, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"
            elif mean_hu < 60 and std_hu > 20 and contrast > 250 and homogeneity < 0.15:
                return "MUSCLE-LIKE", 0.85, f"Fallback: HU={mean_hu:.0f}, contrast={contrast:.0f}"
            elif mean_hu >= 40 and std_hu < 22:
                return "PARENCHYMA-LIKE", 0.85, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"
            elif mean_hu < 40 and std_hu < 12:
                return "SOFT TISSUE (uniform)", 0.80, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"
            else:
                return "SOFT TISSUE", 0.80, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"

        elif 80 <= mean_hu < 150:
            if entropy > 5.2 or std_hu > 30:
                return "SOFT TISSUE (heterogeneous/enhanced)", 0.78, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"
            else:
                return "SOFT TISSUE (enhanced-like)", 0.85, f"Fallback: HU={mean_hu:.0f}, std={std_hu:.1f}"

        elif 150 <= mean_hu < 400:
            if energy > 0.5:
                return "TRABECULAR BONE", 0.88, f"Fallback: HU={mean_hu:.0f}, energy={energy:.2f}"
            elif entropy > 5.0:
                return "BONE (heterogeneous)", 0.80, f"Fallback: HU={mean_hu:.0f}, entropy={entropy:.2f}"
            else:
                return "CALCIFIED TISSUE", 0.85, f"Fallback: HU={mean_hu:.0f}, dense"

        elif mean_hu >= 400:
            if energy > 0.7:
                return "CORTICAL BONE", 0.95, f"Fallback: HU={mean_hu:.0f}, homogeneous"
            elif contrast > 800:
                return "METAL / BEAM-HARDENING ARTIFACT", 0.80, f"Fallback: HU={mean_hu:.0f}, extreme texture"
            else:
                return "DENSE BONE", 0.90, f"Fallback: HU={mean_hu:.0f}, dense"

        else:
            return f"TISSUE (HU={mean_hu:.0f})", 0.60, f"Fallback: std={std_hu:.1f}, entropy={entropy:.2f}"
