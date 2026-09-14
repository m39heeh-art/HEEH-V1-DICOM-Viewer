"""Analysis engines with lazy compatibility exports.

Heavy engines such as MONAI are loaded only when their public export is used.
This keeps importing a focused engine module fast while preserving the
historical ``engines.X`` API.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "ClinicalMetrics": ("engines.clinical_metrics", "ClinicalMetrics"),
    "MONAIPreprocessor": ("engines.monai_preprocessor", "MONAIPreprocessor"),
    "SimpleITKRegistration": ("engines.sitk_registration", "SimpleITKRegistration"),
    "ModalityCalculator": ("engines.modality_calculators", "ModalityCalculator"),
    "CTCalculator": ("engines.modality_calculators", "CTCalculator"),
    "get_calculator": ("engines.modality_calculators", "get_calculator"),
    "available_calculators": ("engines.modality_calculators", "available_calculators"),
}


def __getattr__(name: str):
    """Resolve an engine export on first use."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "ClinicalMetrics",
    "MONAIPreprocessor",
    "SimpleITKRegistration",
    "ModalityCalculator",
    "CTCalculator",
    "get_calculator",
    "available_calculators",
]
