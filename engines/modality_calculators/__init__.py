"""
Modality Calculators package.

Provides modality-specific quantitative metric calculators together with a
lightweight factory (:func:`get_calculator`) that maps a modality key / alias
to the concrete calculator subclass built for it.

Currently implemented:
    - CT    -> :class:`CTCalculator`
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.modality_registry import resolve_modality
from engines.modality_calculators.base_calculator import ModalityCalculator
from engines.modality_calculators.ct_calculator import CTCalculator
from engines.modality_calculators.generic_intensity_calculator import (
    GenericIntensityCalculator,
)
from core.modality_registry import get_supported_modalities

# Registry of concrete calculators keyed by canonical modality key.
_CALCULATOR_REGISTRY: Dict[str, type] = {
    "CT": CTCalculator,
}
_CALCULATOR_REGISTRY.update(
    {
        key: GenericIntensityCalculator
        for key in get_supported_modalities()
        if key != "CT"
    }
)


def get_calculator(
    modality: Optional[str] = None, **kwargs: Any
) -> ModalityCalculator:
    """
    Return an instance of the calculator built for the given modality.

    Args:
        modality: Modality key or alias (e.g. ``"CT"``, ``"ct"``).  When None,
            raises ValueError (the caller must select a modality).
        **kwargs: Extra constructor arguments passed to the calculator.

    Returns:
        An instantiated :class:`ModalityCalculator` subclass.

    Raises:
        ValueError: If the modality is unknown/unsupported or has no
            implemented calculator.
    """
    key = resolve_modality(modality or "")
    if key is None:
        raise ValueError(
            f"Unknown modality '{modality}'. Register it in "
            "core.modality_registry before use."
        )
    cls = _CALCULATOR_REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"Modality '{key}' is registered but has no implemented "
            f"calculator yet. Available: {sorted(_CALCULATOR_REGISTRY)}."
        )
    return cls(modality=key, **kwargs)


def available_calculators() -> Dict[str, str]:
    """Return a mapping of canonical modality key -> calculator class name."""
    return {key: cls.__name__ for key, cls in _CALCULATOR_REGISTRY.items()}


__all__ = [
    "ModalityCalculator",
    "CTCalculator",
    "GenericIntensityCalculator",
    "get_calculator",
    "available_calculators",
]
