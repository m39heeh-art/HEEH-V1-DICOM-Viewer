"""Reproducibility controls for research exports.

:func:`apply_reproducibility` seeds all RNGs and asks NumPy/PyTorch to use
deterministic algorithms where possible; :func:`provenance` records the
library versions actually used, so the runtime environment is traceable from
the export manifest alone.

Honesty boundary: seeding plus ``warn_only=True`` determinism *reduces*
run-to-run variation on repeated inference with identical inputs; it does not
guarantee bit-identical results across hardware, thread counts, or library
versions. Manifest statements describe what was applied, not a guarantee.
"""
from __future__ import annotations

import platform
import random
import warnings
from importlib.metadata import PackageNotFoundError, version as _dist_version

_ENV_ID = "HEEH-V1 reproducibility v2"
_DEFAULT_SEED = 20260926
_state: dict | None = None

# Dependencies recorded in every manifest. (name -> distribution name)
_TRACKED = (
    ("numpy", "numpy"),
    ("pydicom", "pydicom"),
    ("SimpleITK", "SimpleITK"),
    ("nibabel", "nibabel"),
    ("scikit-image", "scikit-image"),
    ("streamlit", "streamlit"),
    ("torch", "torch"),
    ("pillow", "pillow"),
    ("pandas", "pandas"),
)


def apply_reproducibility(seed: int = _DEFAULT_SEED) -> dict:
    """Seed all RNGs and request deterministic algorithms.

    Runs once per process regardless of how many times it is called (Streamlit
    re-executes session code on every interaction), making the recorded state
    stable for the life of the process. Pass ``force=True`` via
    :func:`reset` only in tests.
    """
    global _state
    if _state is not None:
        return _state

    state: dict = {
        "seed": int(seed),
        "deterministic": {},
        "warnings": [],
    }

    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
        state["deterministic"]["numpy"] = True
    except Exception as exc:  # pragma: no cover - numpy always present here
        state["deterministic"]["numpy"] = False
        state["warnings"].append(f"numpy: {exc}")

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():  # pragma: no cover - depends on hardware
            torch.cuda.manual_seed_all(seed)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            torch.use_deterministic_algorithms(True, warn_only=True)
        state["deterministic"]["torch"] = True
        # Real warnings emitted by the deterministic-mode switch (e.g. ops
        # without deterministic implementations on this build) are recorded,
        # not fabricated.
        state["warnings"].extend(
            f"torch: {w.message}" for w in caught if issubclass(
                w.category, UserWarning
            )
        )
    except Exception as exc:
        state["deterministic"]["torch"] = False
        state["warnings"].append(f"torch: {exc}")

    state["environment"] = _ENV_ID
    _state = state
    return state


def reset() -> None:
    """Forget the cached state (test hook)."""
    global _state
    _state = None


def provenance() -> dict:
    """Return the dependency/runtime provenance recorded in exports."""
    deps: dict[str, str | None] = {"python": platform.python_version()}
    for name, dist in _TRACKED:
        try:
            deps[name] = _dist_version(dist)
        except PackageNotFoundError:
            deps[name] = None
    return {
        "environment": _ENV_ID,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "dependencies": deps,
    }


if __name__ == "__main__":  # pragma: no cover
    print(apply_reproducibility())
    print(provenance())
