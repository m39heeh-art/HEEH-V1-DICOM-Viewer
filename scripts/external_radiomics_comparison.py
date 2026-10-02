"""Run a matched HEEH-V1/PyRadiomics first-order comparison.

The comparison uses the same deterministic synthetic CT phantom, 2-D ROI,
image spacing, and source intensities for both implementations. It is only
valid when PyRadiomics imports and completes extraction; otherwise the script
fails explicitly and writes no comparison result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.tissue_classifier import RadiomicsExtractor


def _build_roi(size: int = 256, seed: int = 7) -> np.ndarray:
    """Return the same insert-free water crop used by the local benchmark."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    center = (size - 1) / 2.0
    radius = size * 0.45
    image = np.full((size, size), 0.0, dtype=np.float64)
    image[np.sqrt((xx - center) ** 2 + (yy - center) ** 2) > radius] = -1000.0
    rr = radius * 0.55
    inserts = (
        (center + rr, center, 120.0),
        (center - rr, center, 1000.0),
        (center, center + rr, -1000.0),
        (center, center - rr, 5.0),
    )
    insert_mask = np.zeros_like(image, dtype=bool)
    for cx, cy, hu in inserts:
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= (size * 0.04) ** 2
        image[mask] = hu
        insert_mask |= mask
    water_mask = (
        np.sqrt((xx - center) ** 2 + (yy - center) ** 2) <= radius
    ) & ~insert_mask
    image += rng.normal(0.0, 10.0, image.shape)
    half = int(size * 0.17)
    middle = size // 2
    crop = image[
        middle - half : middle + half + 1,
        middle - half : middle + half + 1,
    ]
    assert crop.shape == (87, 87)
    assert np.isfinite(crop).all()
    assert water_mask.sum() > 0
    return crop.astype(np.float32)


def _heeh_features(roi: np.ndarray) -> dict[str, float]:
    roi = roi[1:-1, 1:-1]
    report = RadiomicsExtractor.full_report(
        roi,
        levels=256,
        discretization="fixed_bin_width",
        bin_width=2.0,
        spacing=(1.0, 1.0),
    )
    histogram = report["histogram"]
    return {
        "mean": float(histogram["mean"]),
        "std": float(histogram["std"]),
        "min": float(histogram["min"]),
        "max": float(histogram["max"]),
    }


def _pyradiomics_features(roi: np.ndarray) -> tuple[str, dict[str, float]]:
    try:
        import SimpleITK as sitk
        from radiomics import featureextractor
    except Exception as exc:
        raise RuntimeError(
            "PyRadiomics and SimpleITK must be installed in the active environment"
        ) from exc

    image = sitk.GetImageFromArray(roi.astype(np.float32))
    mask_array = np.zeros(roi.shape, dtype=np.uint8)
    mask_array[1:-1, 1:-1] = 1
    mask = sitk.GetImageFromArray(mask_array)
    image.SetSpacing((1.0, 1.0))
    mask.SetSpacing((1.0, 1.0))
    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=2.0,
        label=1,
    )
    extractor.disableAllFeatures()
    extractor.enableFeatureClassByName("firstorder")
    result = extractor.execute(image, mask, label=1)
    version = str(result.get("diagnostics_Versions_PyRadiomics", "unknown"))
    mapping = {
        "mean": "original_firstorder_Mean",
        "std": "original_firstorder_StandardDeviation",
        "min": "original_firstorder_Minimum",
        "max": "original_firstorder_Maximum",
    }
    if "original_firstorder_StandardDeviation" not in result:
        variance_key = "original_firstorder_Variance"
        if variance_key in result:
            result["original_firstorder_StandardDeviation"] = float(
                np.sqrt(result[variance_key])
            )
    missing = [key for key, name in mapping.items() if name not in result]
    if missing:
        available = sorted(key for key in result if "firstorder" in key)
        raise RuntimeError(
            f"PyRadiomics result missing first-order features: {missing}; "
            f"available={available}"
        )
    return version, {key: float(result[name]) for key, name in mapping.items()}


def run(output: Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    roi = _build_roi()
    heeh = _heeh_features(roi)
    version, pyradiomics = _pyradiomics_features(roi)
    absolute_errors = {
        key: abs(heeh[key] - pyradiomics[key]) for key in heeh
    }
    result: dict[str, object] = {
        "status": "measured",
        "dataset": "deterministic synthetic water ROI; no patient data",
        "execution_environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine_architecture": platform.machine(),
            "processor": platform.processor() or "not reported by platform",
            "requirements_lock_sha256": hashlib.sha256(
                (root / "requirements.lock").read_bytes()
            ).hexdigest(),
            "benchmark_script_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "source_revision": "unavailable; this workspace has no Git metadata",
        },
        "roi_shape": list(roi.shape),
        "roi_sha256": hashlib.sha256(roi.tobytes()).hexdigest(),
        "preprocessing": {
            "bin_width": 2.0,
            "spacing": [1.0, 1.0],
            "dimension": "2D",
            "mask_label": 1,
        },
        "heeh_v1": heeh,
        "pyradiomics": {"version": version, "features": pyradiomics},
        "absolute_errors": absolute_errors,
        "tolerance": 1e-6,
        "all_within_tolerance": all(
            error <= 1e-6 for error in absolute_errors.values()
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results") / "pyradiomics_comparison.json",
    )
    args = parser.parse_args()
    try:
        result = run(args.output)
    except Exception as exc:
        print(f"PyRadiomics comparison not measured: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
