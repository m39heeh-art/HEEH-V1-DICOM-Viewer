"""Inspect the radiomics path used by the application's image viewer."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from core.tissue_classifier import RadiomicsExtractor


_REFERENCE_ALIASES = {
    "stat_mean": "mean",
    "stat_var": "variance",
    "stat_skew": "skewness",
    "stat_kurt": "kurtosis",
    "stat_median": "median",
    "stat_min": "min",
    "stat_p10": "p10",
    "stat_p90": "p90",
    "stat_max": "max",
    "stat_iqr": "iqr",
    "stat_range": "range",
    "stat_mad": "mad",
    "stat_rmad": "rmad",
    "ih_mean": "mean",
    "ih_var": "variance",
    "ih_skew": "skewness",
    "ih_kurt": "kurtosis",
    "ih_median": "median",
    "ih_min": "min",
    "ih_p10": "p10",
    "ih_p90": "p90",
    "ih_max": "max",
    "ih_iqr": "iqr",
    "ih_range": "range",
    "ih_mad": "mad",
    "ih_rmad": "rmad",
    "ih_entropy": "entropy",
}

_CONFIGURATION_D_MISMATCHES = [
    "The viewer passes the selected 2D image slice to RadiomicsExtractor.full_report; it does not pass the 3D tumour ROI mask.",
    "The viewer does not resample the radiomics input to 2 x 2 x 2 mm or apply Configuration D's linear mask interpolation.",
    "The viewer does not apply Configuration D's 3-SD intensity re-segmentation.",
    "The viewer's current report uses fixed-bin-width 25 HU defaults rather than Configuration D's 32-bin discretisation.",
    "The viewer radiomics call does not pass image spacing, so the subset uses its default 1 mm spacing.",
]


def inspect_app_radiomics(
    image_path: Path,
    reference_rows: list[dict],
) -> dict:
    """Run the viewer's current radiomics call on its default phantom slice.

    The loader, first displayed slice selection, and ``full_report`` call mirror
    ``core.loaders._load_volume_file`` and ``ClinicalApp``. Reference
    deltas are reported as observations only because the viewer input is not
    Configuration D's resampled, re-segmented 3D ROI.
    """
    image = nib.load(str(image_path))
    volume = np.asarray(image.dataobj, dtype=np.float32)
    slope = float(getattr(image, "scl_slope", 1.0) or 1.0)
    intercept = float(getattr(image, "scl_inter", 0.0) or 0.0)
    if slope != 1.0 or intercept != 0.0:
        volume = volume * slope + intercept

    while volume.ndim > 3:
        axis = int(np.argmin(volume.shape))
        volume = np.take(volume, volume.shape[axis] // 2, axis=axis)

    source_dimensions = list(volume.shape)
    slice_axis = None
    slice_index = None
    if volume.ndim == 3:
        slice_axis = int(np.argmin(volume.shape))
        slice_index = 0
        radiomics_input = np.take(volume, slice_index, axis=slice_axis)
    else:
        radiomics_input = volume

    report = RadiomicsExtractor.full_report(radiomics_input)
    histogram = report["histogram"]
    observations = []
    for row in reference_rows:
        tag = row.get("tag")
        feature_key = _REFERENCE_ALIASES.get(tag)
        expected_text = row.get("reference value")
        actual = histogram.get(feature_key) if feature_key else None
        if not expected_text or actual is None:
            continue
        expected = float(expected_text)
        actual_value = float(actual)
        observations.append(
            {
                "tag": tag,
                "family": row.get("family"),
                "feature": row.get("feature"),
                "application_feature": feature_key,
                "reference_value": expected,
                "application_value": actual_value,
                "absolute_difference": abs(actual_value - expected),
                "status": "not_comparable",
                "reason": (
                    "Different image dimensionality, ROI, and preprocessing; "
                    "this numeric difference is not an IBSI pass/fail result."
                ),
            }
        )

    return {
        "status": "not_configuration_d_compliant",
        "verification_method": (
            "Reproduced the viewer's NIfTI loading, initial displayed-slice "
            "selection, and RadiomicsExtractor.full_report call."
        ),
        "input": str(image_path),
        "application_call": "RadiomicsExtractor.full_report(hu_data)",
        "application_processing": {
            "loaded_dimensions": source_dimensions,
            "radiomics_input_dimensions": int(radiomics_input.ndim),
            "selected_slice_axis": slice_axis,
            "selected_slice_index": slice_index,
            "segmentation_mask_passed": False,
            "resampling": None,
            "resegmentation": None,
            "discretization": {
                "method": "fixed_bin_width",
                "bin_width_hu": 25.0,
            },
            "spacing_mm": [1.0, 1.0],
        },
        "measured_output": report,
        "reference_observations": {
            "status": "not_comparable",
            "compared_as_pass_fail": 0,
            "observed_deltas": observations,
            "configuration_mismatches": _CONFIGURATION_D_MISMATCHES,
        },
    }
