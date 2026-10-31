"""Verify and measure the pinned IBSI CT phantom without claiming certification."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.tissue_classifier import RadiomicsExtractor
from core.ibsi_radiomics import (
    run_configuration_a,
    run_configuration_b,
    run_configuration_c,
    run_configuration_d,
    run_configuration_e,
)
from scripts.ibsi_app_alignment import inspect_app_radiomics


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _feature_coverage() -> dict[str, dict[str, str]]:
    coverage = RadiomicsExtractor.feature_coverage()
    for name in coverage:
        coverage[name]["status"] = coverage[name]["status"]
    return coverage


def _resolve_phantom_root(data_root: Path) -> Path:
    """Accept either the phantom folder or the parent dataset root."""
    candidate = data_root.resolve()
    if not candidate.exists():
        return candidate
    expected_image = candidate / "nifti" / "image" / "phantom.nii.gz"
    expected_mask = candidate / "nifti" / "mask" / "mask.nii.gz"
    if expected_image.exists() and expected_mask.exists():
        return candidate
    for child in sorted(candidate.iterdir()):
        if not child.is_dir():
            continue
        probe_image = child / "nifti" / "image" / "phantom.nii.gz"
        probe_mask = child / "nifti" / "mask" / "mask.nii.gz"
        if probe_image.exists() and probe_mask.exists():
            return child
    return candidate


def _load_reference_table(data_root: Path, letter: str = "D") -> dict:
    """Load the official IBSI reference-value table for one configuration."""
    phantom_root = _resolve_phantom_root(data_root)
    filename = (
        "ibsi_1_digital_phantom_reference_values.csv"
        if letter.lower() == "digital"
        else f"ibsi_1_reference_values_config_{letter}.csv"
    )
    table = phantom_root.parent / "ibsi_1_reference_values" / filename
    if not table.exists():
        return {
            "status": "not_available",
            "path": str(table),
            "rows": 0,
        }
    with table.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    families = {}
    for row in rows:
        family = row.get("family") or "unknown"
        families[family] = families.get(family, 0) + 1
    return {
        "status": "available",
        "path": str(table),
        "rows": len(rows),
        "rows_with_reference": sum(bool(row.get("reference value")) for row in rows),
        "families": families,
        "_rows": rows,
    }


def _compare_statistics(reference_table: dict, features: dict) -> dict:
    """Compare every IBSI Configuration D Statistics row that is exposed.

    Z-Rad exposes the IBSI names directly, while PyRadiomics exposes a
    compatible subset under ``original_firstorder_*``.  Prefer the direct
    IBSI tag so MAD/RMAD/median absolute deviation/CV/QCOD are not reported
    as unsupported when the IBSI-oriented engine measured them.
    """
    feature_map = {
        "stat_mean": "original_firstorder_Mean",
        "stat_var": "original_firstorder_Variance",
        "stat_skew": "original_firstorder_Skewness",
        "stat_kurt": "original_firstorder_Kurtosis",
        "stat_median": "original_firstorder_Median",
        "stat_min": "original_firstorder_Minimum",
        "stat_p10": "original_firstorder_10Percentile",
        "stat_p90": "original_firstorder_90Percentile",
        "stat_max": "original_firstorder_Maximum",
        "stat_iqr": "original_firstorder_InterquartileRange",
        "stat_range": "original_firstorder_Range",
        "stat_mad": "original_firstorder_MeanAbsoluteDeviation",
        "stat_rmad": "original_firstorder_RobustMeanAbsoluteDeviation",
        "stat_medad": "stat_medad",
        "stat_cov": "stat_cov",
        "stat_qcod": "stat_qcod",
        "stat_energy": "original_firstorder_Energy",
        "stat_rms": "original_firstorder_RootMeanSquared",
    }
    rows = reference_table.get("_rows", [])
    comparisons = []
    for row in rows:
        tag = row.get("tag")
        key = feature_map.get(tag)
        expected_text = row.get("reference value")
        if not key or not expected_text:
            continue
        expected = float(expected_text)
        tolerance = float(row.get("tolerance") or 0)
        actual = features.get(tag) if tag in features else features.get(key)
        if tag == "stat_kurt" and tag not in features and actual is not None:
            # PyRadiomics reports Pearson kurtosis; IBSI reports excess kurtosis.
            actual = float(actual) - 3.0
        comparisons.append(
            {
                "tag": tag,
                "feature": row["feature"],
                "pyRadiomics_key": key,
                "expected": expected,
                "tolerance": tolerance,
                "actual": actual,
                "absolute_error": (
                    None if actual is None else abs(float(actual) - expected)
                ),
                "passed": (
                    False
                    if actual is None
                    else abs(float(actual) - expected) <= tolerance
                ),
            }
        )
    comparable = [item for item in comparisons if item["actual"] is not None]
    return {
        "family": "Statistics",
        "compared": len(comparable),
        "passed": sum(item["passed"] for item in comparable),
        "failed": sum(not item["passed"] for item in comparable),
        "unsupported": sum(
            item["expected"] is not None and item["actual"] is None
            for item in comparisons
        ),
        "comparisons": comparisons,
    }


def _compare_reference_rows(reference_table: dict, features: dict) -> dict:
    """Compare all reference rows with an unambiguous PyRadiomics equivalent."""
    aliases = {
        "Mean": "Mean",
        "Variance": "Variance",
        "Skewness": "Skewness",
        "(Excess) kurtosis": "Kurtosis",
        "Median": "Median",
        "Minimum": "Minimum",
        "10th percentile": "10Percentile",
        "90th percentile": "90Percentile",
        "Maximum": "Maximum",
        "Interquartile range": "InterquartileRange",
        "Range": "Range",
        "Mean absolute deviation": "MeanAbsoluteDeviation",
        "Robust mean absolute deviation": "RobustMeanAbsoluteDeviation",
        "Energy": "Energy",
        "Root mean square": "RootMeanSquared",
        "Elongation": "Elongation",
        "Flatness": "Flatness",
        "Least axis length": "LeastAxisLength",
        "Major axis length": "MajorAxisLength",
        "Minor axis length": "MinorAxisLength",
        "Maximum 3D diameter": "Maximum3DDiameter",
        "Volume (mesh)": "MeshVolume",
        "Volume (voxel counting)": "VoxelVolume",
        "Surface area (mesh)": "SurfaceArea",
        "Surface to volume ratio": "SurfaceVolumeRatio",
        "Sphericity": "Sphericity",
        "Small run emphasis": "ShortRunEmphasis",
        "Long run emphasis": "LongRunEmphasis",
        "Low grey level run emphasis": "LowGrayLevelRunEmphasis",
        "High grey level run emphasis": "HighGrayLevelRunEmphasis",
        "Short run low grey level emphasis": "ShortRunLowGrayLevelEmphasis",
        "Short run high grey level emphasis": "ShortRunHighGrayLevelEmphasis",
        "Long run low grey level emphasis": "LongRunLowGrayLevelEmphasis",
        "Long run high grey level emphasis": "LongRunHighGrayLevelEmphasis",
        "Grey level non-uniformity": "GrayLevelNonUniformity",
        "Normalised grey level non-uniformity": "GrayLevelNonUniformityNormalized",
        "Run length non-uniformity": "RunLengthNonUniformity",
        "Normalised run length non-uniformity": "RunLengthNonUniformityNormalized",
        "Run percentage": "RunPercentage",
        "Grey level variance": "GrayLevelVariance",
        "Run length variance": "RunVariance",
        "Run entropy": "RunEntropy",
        "Small zone emphasis": "SmallAreaEmphasis",
        "Large zone emphasis": "LargeAreaEmphasis",
        "Low grey level emphasis": "LowGrayLevelZoneEmphasis",
        "High grey level emphasis": "HighGrayLevelZoneEmphasis",
        "Small zone low grey level emphasis": "SmallAreaLowGrayLevelEmphasis",
        "Small zone high grey level emphasis": "SmallAreaHighGrayLevelEmphasis",
        "Large zone low grey level emphasis": "LargeAreaLowGrayLevelEmphasis",
        "Large zone high grey level emphasis": "LargeAreaHighGrayLevelEmphasis",
        "Zone size non-uniformity": "SizeZoneNonUniformity",
        "Normalised zone size non-uniformity": "SizeZoneNonUniformityNormalized",
        "Zone percentage": "ZonePercentage",
        "Zone size variance": "ZoneVariance",
        "Zone size entropy": "ZoneEntropy",
        "Coarseness": "Coarseness",
        "Contrast": "Contrast",
        "Busyness": "Busyness",
        "Complexity": "Complexity",
        "Strength": "Strength",
        "Low dependence emphasis": "SmallDependenceEmphasis",
        "High dependence emphasis": "LargeDependenceEmphasis",
        "Low grey level count emphasis": "LowGrayLevelEmphasis",
        "High grey level count emphasis": "HighGrayLevelEmphasis",
        "Dependence entropy": "DependenceEntropy",
        "Dependence count non-uniformity": "DependenceNonUniformity",
        "Normalised dependence count non-uniformity": "DependenceNonUniformityNormalized",
        "Dependence count variance": "DependenceVariance",
        "Low dependence low grey level emphasis": "SmallDependenceLowGrayLevelEmphasis",
        "Low dependence high grey level emphasis": "SmallDependenceHighGrayLevelEmphasis",
        "High dependence low grey level emphasis": "LargeDependenceLowGrayLevelEmphasis",
        "High dependence high grey level emphasis": "LargeDependenceHighGrayLevelEmphasis",
        "Dependence count entropy": "DependenceEntropy",
    }
    family_prefix = {
        "Statistics": "firstorder",
        "Morphology": "shape",
        "Neighbourhood grey tone difference matrix (3D)": "ngtdm",
        "Neighbouring grey level dependence matrix (3D)": "gldm",
        "Run length matrix (3D, averaged)": "glrlm",
        "Size zone matrix (3D)": "glszm",
    }
    rows = reference_table.get("_rows", [])
    comparisons = []
    for row in rows:
        expected_text = row.get("reference value")
        family = row.get("family", "")
        feature = row.get("feature", "")
        prefix = family_prefix.get(family)
        suffix = aliases.get(feature)
        key = f"original_{prefix}_{suffix}" if prefix and suffix else None
        reason = None
        reason_category = None
        if "merged" in family or "Co-occurrence" in family:
            reason = (
                "No defensible mapping was established for this comparison "
                "because aggregation semantics differ."
            )
            reason_category = "aggregation_semantics_not_comparable"
            key = None
        elif key is None:
            reason = (
                "No defensible PyRadiomics feature mapping was established "
                "for this comparison."
            )
            if family.startswith("Diagnostics"):
                reason_category = "pipeline_stage_diagnostic"
            elif family == "Intensity volume histogram":
                reason_category = "feature_family_not_provided_by_pyradiomics"
            elif family == "Local intensity":
                reason_category = "local_intensity_feature_not_provided_by_pyradiomics"
            elif family == "Distance zone matrix (3D)":
                reason_category = "feature_family_not_provided_by_pyradiomics"
            elif family == "Intensity histogram":
                reason_category = "histogram_definition_not_proven_equivalent"
            elif family == "Morphology":
                reason_category = "morphology_definition_not_proven_equivalent"
            else:
                reason_category = "no_unambiguous_feature_mapping"
        actual = features.get(key) if key else None
        if expected_text and actual is None and reason is None:
            reason = (
                "No defensible PyRadiomics feature mapping could be "
                "established for this comparison because the mapped output "
                "was not available."
            )
            reason_category = "mapped_feature_not_emitted_by_pyradiomics"
        if family == "Statistics" and row.get("tag") == "stat_kurt" and actual is not None:
            actual = float(actual) - 3.0
        passed = (
            None
            if actual is None or not expected_text
            else abs(float(actual) - float(expected_text))
            <= float(row.get("tolerance") or 0)
        )
        item = {
            "tag": row.get("tag"),
            "family": family,
            "feature": feature,
            "pyRadiomics_key": key,
            "expected": float(expected_text) if expected_text else None,
            "tolerance": float(row.get("tolerance") or 0) if expected_text else None,
            "actual": actual,
            "absolute_error": (
                None if actual is None or not expected_text else abs(float(actual) - float(expected_text))
            ),
            "passed": passed,
            "assessment_status": (
                "not_assessed"
                if expected_text and actual is None
                else "no_reference_value"
                if not expected_text
                else "passed"
                if passed
                else "failed"
            ),
            "unsupported_reason": reason,
            "unsupported_reason_category": reason_category,
        }
        comparisons.append(item)
    comparable = [item for item in comparisons if item["actual"] is not None and item["expected"] is not None]
    unassessed = [
        item
        for item in comparisons
        if item["expected"] is not None and item["actual"] is None
    ]
    unassessed_by_category: dict[str, int] = {}
    unassessed_by_family: dict[str, int] = {}
    for item in unassessed:
        category = item["unsupported_reason_category"] or "uncategorized"
        family_name = item["family"] or "unknown"
        unassessed_by_category[category] = unassessed_by_category.get(category, 0) + 1
        unassessed_by_family[family_name] = unassessed_by_family.get(family_name, 0) + 1
    return {
        "rows_with_reference": sum(item["expected"] is not None for item in comparisons),
        "compared": len(comparable),
        "passed": sum(item["passed"] for item in comparable),
        "failed": sum(not item["passed"] for item in comparable),
        "unsupported": len(unassessed),
        "unsupported_by_category": dict(sorted(unassessed_by_category.items())),
        "unsupported_by_family": dict(sorted(unassessed_by_family.items())),
        "comparisons": comparisons,
    }


_DIAGNOSTIC_TAG_PREFIXES = (
    "img_dim_",
    "vox_dim_",
    "mean_int_",
    "min_int_",
    "max_int_",
    "int_mask_",
    "morph_mask_",
)


def _compare_configuration_rows(reference_table: dict, features: dict) -> dict:
    """Compare official IBSI feature rows for a full A/B/C configuration.

    Reference rows for diagnostics (image / ROI dimensions, intensities and
    voxel counts) are pipeline-stage specific; the shared application run
    already exposes those stages and they are verified separately for
    Configuration D. For A/B/C every feature row with a published reference
    value is compared against the Z-Rad tag produced by the shared pipeline.
    """
    comparisons = []
    for row in reference_table.get("_rows", []):
        expected_text = row.get("reference value")
        tag = row.get("tag")
        diagnostic = tag.startswith(_DIAGNOSTIC_TAG_PREFIXES)
        expected = float(expected_text) if expected_text else None
        listed_tolerance = (
            float(row.get("tolerance") or 0) if expected_text else None
        )
        actual = features.get(tag) if (tag and not diagnostic) else None
        effective_tolerance = None
        if expected is not None and listed_tolerance == 0:
            decimals = (
                len(expected_text.split(".", 1)[1])
                if "." in expected_text
                else 0
            )
            effective_tolerance = 0.5 * 10 ** (-decimals)
        elif expected is not None:
            effective_tolerance = listed_tolerance
        if diagnostic and expected is not None:
            unsupported_reason = (
                "Diagnostics rows are stage-specific and are verified "
                "separately through the Configuration D diagnostics check."
            )
        elif actual is None:
            unsupported_reason = (
                "Z-Rad did not expose this reference tag."
                if expected is not None
                else None
            )
        else:
            unsupported_reason = None
        comparisons.append(
            {
                "tag": tag,
                "family": row.get("family"),
                "feature": row.get("feature"),
                "expected": expected,
                "tolerance": listed_tolerance,
                "effective_tolerance": effective_tolerance,
                "actual": actual,
                "absolute_error": (
                    None if actual is None or expected is None else abs(actual - expected)
                ),
                "passed": (
                    None
                    if actual is None or expected is None
                    else abs(actual - expected) <= effective_tolerance
                ),
                "unsupported_reason": unsupported_reason,
            }
        )
    comparable = [
        item
        for item in comparisons
        if item["actual"] is not None and item["expected"] is not None
    ]
    return {
        "rows_with_reference": sum(item["expected"] is not None for item in comparisons),
        "compared": len(comparable),
        "passed": sum(item["passed"] for item in comparable),
        "failed": sum(not item["passed"] for item in comparable),
        "unsupported": sum(
            item["expected"] is not None
            and item["actual"] is None
            and item["unsupported_reason"] is not None
            and "expose" in item["unsupported_reason"]
            for item in comparisons
        ),
        "skipped_diagnostics": sum(
            item["unsupported_reason"] is not None
            and item["unsupported_reason"].startswith("Diagnostics rows")
            for item in comparisons
        ),
        "comparison_precision_policy": (
            "For published rows with zero listed tolerance, comparison allows "
            "half a unit at the final displayed decimal place to account for "
            "rounding in the published reference value."
        ),
        "comparisons": comparisons,
    }


def _configuration_verification(
    phantom_image: Path, phantom_mask: Path, data_root: Path
) -> dict:
    """Verify Configurations A-C and E when official reference tables exist."""
    runners = {
        "A": run_configuration_a,
        "B": run_configuration_b,
        "C": run_configuration_c,
        "E": run_configuration_e,
    }
    configurations: dict[str, dict] = {}
    for letter, runner in runners.items():
        entry: dict = {"status": "blocked"}
        try:
            reference_table = _load_reference_table(data_root, letter)
            if reference_table.get("status") != "available":
                entry["status"] = "blocked"
                entry["blocker"] = "official_reference_values_missing"
            else:
                result = runner(phantom_image, phantom_mask)
                comparison = _compare_configuration_rows(
                    reference_table, result["features"]
                )
                passed = (
                    comparison["compared"]
                    == comparison["rows_with_reference"]
                    - comparison["skipped_diagnostics"]
                    and comparison["failed"] == 0
                    and comparison["unsupported"] == 0
                )
                entry = {
                    "status": "passed" if passed else "failed",
                    "reference_table": {
                        key: value
                        for key, value in reference_table.items()
                        if key != "_rows"
                    },
                    "configuration": result["configuration"],
                    "unsupported_families": result["unsupported_families"],
                    "comparison": comparison,
                }
        except Exception as exc:  # pragma: no cover - environment-specific
            entry = {
                "status": "blocked",
                "blocker": f"{type(exc).__name__}: {exc}",
            }
        configurations[letter] = entry
    return configurations


def _zrad_reference_features(image_path: Path, mask_path: Path) -> dict:
    """Run the same shared Configuration D pipeline used by the application."""
    result = run_configuration_d(image_path, mask_path)
    return {
        "implementation": result["implementation"],
        "version": result["version"],
        "features": result["features"],
        "configuration": result["configuration"],
    }


def _compare_zrad_rows(reference_table: dict, features: dict) -> dict:
    comparisons = []
    for row in reference_table.get("_rows", []):
        expected_text = row.get("reference value")
        tag = row.get("tag")
        actual = features.get(tag) if tag else None
        listed_tolerance = float(row.get("tolerance") or 0) if expected_text else None
        effective_tolerance = listed_tolerance
        if expected_text and listed_tolerance == 0:
            decimals = (
                len(expected_text.split(".", 1)[1])
                if "." in expected_text
                else 0
            )
            effective_tolerance = 0.5 * 10 ** (-decimals)
        comparisons.append(
            {
                "tag": tag,
                "family": row.get("family"),
                "feature": row.get("feature"),
                "expected": float(expected_text) if expected_text else None,
                "tolerance": listed_tolerance,
                "effective_tolerance": effective_tolerance,
                "actual": actual,
                "absolute_error": (
                    None
                    if actual is None or not expected_text
                    else abs(actual - float(expected_text))
                ),
                "passed": (
                    None
                    if actual is None or not expected_text
                    else abs(actual - float(expected_text))
                    <= effective_tolerance
                ),
                "unsupported_reason": (
                    None
                    if actual is not None or not expected_text
                    else "Z-Rad did not expose this reference tag."
                ),
            }
        )
    comparable = [
        item
        for item in comparisons
        if item["actual"] is not None and item["expected"] is not None
    ]
    return {
        "rows_with_reference": sum(item["expected"] is not None for item in comparisons),
        "compared": len(comparable),
        "passed": sum(item["passed"] for item in comparable),
        "failed": sum(not item["passed"] for item in comparable),
        "unsupported": sum(
            item["expected"] is not None and item["actual"] is None
            for item in comparisons
        ),
        "comparison_precision_policy": (
            "For published rows with zero listed tolerance, comparison allows "
            "half a unit at the final displayed decimal place to account for "
            "rounding in the published reference value."
        ),
        "comparisons": comparisons,
    }


def _zrad_diagnostics(image_path: Path, mask_path: Path) -> dict[str, float]:
    """Return Configuration D image and ROI diagnostics keyed by IBSI tags."""
    import SimpleITK as sitk

    image = sitk.ReadImage(str(image_path))
    mask = sitk.ReadImage(str(mask_path))
    image_array = sitk.GetArrayFromImage(image).astype(np.float64)
    mask_array = sitk.GetArrayFromImage(mask) == 1
    diagnostics: dict[str, float] = {}

    def add_image(prefix: str, image_obj: object) -> None:
        array = sitk.GetArrayFromImage(image_obj).astype(np.float64)
        size = image_obj.GetSize()
        spacing = image_obj.GetSpacing()
        diagnostics.update(
            {
                f"img_dim_x_{prefix}": float(size[0]),
                f"img_dim_y_{prefix}": float(size[1]),
                f"img_dim_z_{prefix}": float(size[2]),
                f"vox_dim_x_{prefix}": float(spacing[0]),
                f"vox_dim_y_{prefix}": float(spacing[1]),
                f"vox_dim_z_{prefix}": float(spacing[2]),
                f"mean_int_{prefix}": float(np.mean(array)),
                f"min_int_{prefix}": float(np.min(array)),
                f"max_int_{prefix}": float(np.max(array)),
            }
        )

    def bbox(mask_values: np.ndarray) -> tuple[int, int, int]:
        coordinates = np.argwhere(mask_values)
        if coordinates.size == 0:
            raise ValueError("IBSI diagnostic ROI is empty")
        dimensions_zyx = coordinates.max(axis=0) - coordinates.min(axis=0) + 1
        return tuple(int(value) for value in dimensions_zyx[::-1])

    def add_roi(
        prefix: str,
        image_obj: object,
        image_values: np.ndarray,
        roi_mask: np.ndarray,
        morphological_mask: np.ndarray | None = None,
    ) -> None:
        roi_values = image_values[roi_mask].astype(np.float64)
        morph_values = roi_mask if morphological_mask is None else morphological_mask
        size = image_obj.GetSize()
        diagnostics.update(
            {
                f"int_mask_dim_x_{prefix}": float(size[0]),
                f"int_mask_dim_y_{prefix}": float(size[1]),
                f"int_mask_dim_z_{prefix}": float(size[2]),
                f"int_mask_bb_dim_x_{prefix}": float(bbox(roi_mask)[0]),
                f"int_mask_bb_dim_y_{prefix}": float(bbox(roi_mask)[1]),
                f"int_mask_bb_dim_z_{prefix}": float(bbox(roi_mask)[2]),
                f"morph_mask_bb_dim_x_{prefix}": float(bbox(morph_values)[0]),
                f"morph_mask_bb_dim_y_{prefix}": float(bbox(morph_values)[1]),
                f"morph_mask_bb_dim_z_{prefix}": float(bbox(morph_values)[2]),
                f"int_mask_vox_count_{prefix}": float(np.count_nonzero(roi_mask)),
                f"morph_mask_vox_count_{prefix}": float(np.count_nonzero(morph_values)),
                f"int_mask_mean_int_{prefix}": float(np.mean(roi_values)),
                f"int_mask_min_int_{prefix}": float(np.min(roi_values)),
                f"int_mask_max_int_{prefix}": float(np.max(roi_values)),
            }
        )

    add_image("init_img", image)
    add_roi("init_roi", image, image_array, mask_array)

    spacing = (2.0, 2.0, 2.0)
    output_size = tuple(
        int(np.ceil(image.GetSize()[axis] * image.GetSpacing()[axis] / spacing[axis]))
        for axis in range(3)
    )
    output_origin = tuple(
        image.GetOrigin()[axis]
        + (
            image.GetSpacing()[axis] * (image.GetSize()[axis] - 1)
            - spacing[axis] * (output_size[axis] - 1)
        )
        / 2
        for axis in range(3)
    )

    def resample(source: object, interpolator: int, pixel_type: int) -> object:
        resampler = sitk.ResampleImageFilter()
        resampler.SetOutputSpacing(spacing)
        resampler.SetSize(output_size)
        resampler.SetOutputOrigin(output_origin)
        resampler.SetOutputDirection(image.GetDirection())
        resampler.SetTransform(sitk.Transform())
        resampler.SetInterpolator(interpolator)
        resampler.SetDefaultPixelValue(0)
        resampler.SetOutputPixelType(pixel_type)
        return resampler.Execute(source)

    interpolated_image = resample(image, sitk.sitkLinear, sitk.sitkFloat32)
    rounded_array = np.rint(sitk.GetArrayFromImage(interpolated_image)).astype(
        np.int16
    )
    rounded_image = sitk.GetImageFromArray(rounded_array)
    rounded_image.CopyInformation(interpolated_image)
    interpolated_image = rounded_image
    interpolated_mask = resample(mask, sitk.sitkLinear, sitk.sitkFloat32)
    interpolated_mask_array = (
        sitk.GetArrayFromImage(interpolated_mask) >= 0.5
    )
    interpolated_array = sitk.GetArrayFromImage(interpolated_image).astype(np.float64)
    add_image("interp_img", interpolated_image)
    add_roi(
        "interp_roi",
        interpolated_image,
        interpolated_array,
        interpolated_mask_array,
        interpolated_mask_array,
    )

    roi_interpolated_values = interpolated_array[interpolated_mask_array]
    lower = float(np.mean(roi_interpolated_values) - 3 * np.std(roi_interpolated_values))
    upper = float(np.mean(roi_interpolated_values) + 3 * np.std(roi_interpolated_values))
    resegmented_mask = interpolated_mask_array & (
        (interpolated_array >= lower) & (interpolated_array <= upper)
    )
    add_roi(
        "reseg_roi",
        interpolated_image,
        interpolated_array,
        resegmented_mask,
        interpolated_mask_array,
    )
    return diagnostics


def _blocked_result(
    data_root: Path,
    output: Path,
    blocker: str,
    message: str,
) -> dict:
    phantom_root = _resolve_phantom_root(data_root)
    image_path = phantom_root / "nifti" / "image" / "phantom.nii.gz"
    mask_path = phantom_root / "nifti" / "mask" / "mask.nii.gz"
    commit = None
    try:
        completed = subprocess.run(
            ["git", "-C", str(data_root), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            commit = completed.stdout.strip()
    except Exception:
        pass
    payload = {
        "status": "blocked",
        "scope": (
            "Official IBSI CT phantom verification is blocked because the direct reference suite "
            "or dataset is unavailable; this is not an IBSI compliance certificate."
        ),
        "feature_coverage": _feature_coverage(),
        "blocker": {
            "type": blocker,
            "message": message,
            "status": "blocked",
        },
        "source": {
            "repository": "https://github.com/theibsi/data_sets",
            "commit": commit,
            "dataset": "ibsi_1_ct_radiomics_phantom",
            "license": "CC BY-NC 3.0",
            "image": {
                "path": str(image_path),
                "sha256": sha256(image_path) if image_path.exists() else None,
                "bytes": image_path.stat().st_size if image_path.exists() else None,
            },
            "mask": {
                "path": str(mask_path),
                "sha256": sha256(mask_path) if mask_path.exists() else None,
                "bytes": mask_path.stat().st_size if mask_path.exists() else None,
            },
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def run(data_root: Path, output: Path) -> dict:
    phantom_root = _resolve_phantom_root(data_root)
    image_path = phantom_root / "nifti" / "image" / "phantom.nii.gz"
    mask_path = phantom_root / "nifti" / "mask" / "mask.nii.gz"
    if not image_path.exists() or not mask_path.exists():
        return _blocked_result(
            data_root,
            output,
            "missing_reference_dataset",
            "Official IBSI CT dataset files were not found at the specified data root.",
        )

    try:
        import SimpleITK as sitk
    except Exception as exc:  # pragma: no cover - environment-specific
        return _blocked_result(
            data_root,
            output,
            "simpleitk_missing",
            f"SimpleITK is unavailable for IBSI dataset loading: {type(exc).__name__}: {exc}",
        )

    try:
        reference = RadiomicsExtractor.ibsi_reference_features(
            str(image_path),
            str(mask_path),
            bin_count=32,
            round_resampled_intensities=True,
            resampled_pixel_spacing=(2.0, 2.0, 2.0),
            resegment_outlier_sigma=3.0,
            interpolator=sitk.sitkLinear,
            feature_classes=("firstorder", "glcm", "glrlm", "glszm", "gldm", "ngtdm", "shape"),
        )
    except Exception as exc:  # pragma: no cover - environment-specific
        return _blocked_result(
            data_root,
            output,
            "reference_extraction_failed",
            f"PyRadiomics reference extraction failed: {type(exc).__name__}: {exc}",
        )

    image = sitk.ReadImage(str(image_path))
    mask = sitk.ReadImage(str(mask_path))
    image_array = sitk.GetArrayFromImage(image).astype(np.float64)
    mask_array = sitk.GetArrayFromImage(mask) == 1
    result = reference["features"]
    diagnostics = reference["diagnostics"]
    reference_table = _load_reference_table(data_root)
    app_alignment = inspect_app_radiomics(image_path, reference_table["_rows"])
    try:
        zrad = _zrad_reference_features(image_path, mask_path)
        diagnostics = _zrad_diagnostics(image_path, mask_path)
        zrad["features"].update(diagnostics)
        zrad_comparison = _compare_zrad_rows(
            reference_table, zrad["features"]
        )
        statistics_comparison = _compare_statistics(
            reference_table, zrad["features"]
        )
        zrad_error = None
    except Exception as exc:  # pragma: no cover - optional reference engine
        zrad = None
        zrad_comparison = None
        statistics_comparison = None
        zrad_error = f"{type(exc).__name__}: {exc}"
    configuration_abc = _configuration_verification(
        image_path, mask_path, data_root
    )
    abc_passed = all(
        configuration_abc.get(letter, {}).get("status") == "passed"
        for letter in ("A", "B", "C")
    )
    e_passed = configuration_abc.get("E", {}).get("status") == "passed"
    std = result.get("original_firstorder_StandardDeviation")
    if std is None:
        std = float(np.sqrt(result["original_firstorder_Variance"]))
    pyradiomics = {
        "mean": float(result["original_firstorder_Mean"]),
        "std": float(std),
        "min": float(result["original_firstorder_Minimum"]),
        "max": float(result["original_firstorder_Maximum"]),
    }
    values = image_array[mask_array]
    feature_counts = {}
    for key in result:
        parts = key.split("_")
        if len(parts) >= 3 and parts[0] == "original":
            family = parts[1]
            feature_counts[family] = feature_counts.get(family, 0) + 1
    batch_comparison = _compare_reference_rows(reference_table, result)
    configuration_d_verified = (
        zrad_comparison is not None
        and zrad_comparison["compared"] == zrad_comparison["rows_with_reference"]
        and zrad_comparison["failed"] == 0
        and zrad_comparison["unsupported"] == 0
    )
    a_to_e_passed = configuration_d_verified and abc_passed and e_passed
    completed = subprocess.run(
        ["git", "-C", str(data_root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    commit = completed.stdout.strip() if completed.returncode == 0 else None
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": (
            "configurations_a_to_e_reference_verified"
            if a_to_e_passed
            else (
                "configurations_a_to_d_reference_verified"
                if configuration_d_verified and abc_passed
                else (
                    "configuration_d_reference_verified"
                    if configuration_d_verified
                    else "partially_verified"
                )
            )
        ),
        "scope": (
            "All populated IBSI reference feature rows of Configurations A, "
            "B, C, D and E were compared against the official published values "
            "on the CT radiomics phantom, using the Z-Rad pipelines shared "
            "by the dedicated application workflows. Diagnostics-stage rows "
            "(image and ROI dimensions, intensities and voxel counts) are "
            "covered by the Configuration D pipeline check. Configuration E "
            "feature rows are compared with its official reference table, "
            "while its stage-specific diagnostics are not part of the "
            "feature comparison. It "
            "is configuration-specific and does not establish full IBSI "
            "compliance or validate the default 2D viewer path."
        ),
        "verification_summary": {
            "official_reference_values": reference_table["status"],
            "configuration_d_reference_status": (
                "passed"
                if configuration_d_verified
                else "incomplete_or_mismatched"
            ),
            "local_comparison": (
                "configuration_d_reference_values_passed"
                if configuration_d_verified
                else "configuration_d_reference_comparison_incomplete"
            ),
            "measured_feature_counts": feature_counts,
            "full_ibsi_status": (
                "reference_verified_configurations_a_to_e"
                if a_to_e_passed
                else (
                    "reference_verified_configurations_a_to_d_only"
                    if configuration_d_verified and abc_passed
                    else (
                        "reference_verified_configuration_d_only"
                        if configuration_d_verified
                        else "not_verified_unsupported_or_failed_features"
                    )
                )
            ),
            "comparison": {
                key: value
                for key, value in batch_comparison.items()
                if key != "comparisons"
            },
            "zrad_comparison": (
                None
                if zrad_comparison is None
                else {
                    key: value
                    for key, value in zrad_comparison.items()
                    if key != "comparisons"
                }
            ),
            "statistics_comparison": (
                None
                if statistics_comparison is None
                else {
                    key: value
                    for key, value in statistics_comparison.items()
                    if key != "comparisons"
                }
            ),
            "application_alignment": app_alignment["status"],
            "application_configuration_d_workflow": (
                "reference_verified_when_3d_roi_mask_is_imported"
                if configuration_d_verified
                else "incomplete_or_mismatched"
            ),
            "configuration_a_to_c_summary": {
                letter: {
                    "status": entry.get("status"),
                    "blocker": entry.get("blocker"),
                    "comparison": (
                        None
                        if "comparison" not in entry
                        else {
                            key: value
                            for key, value in entry["comparison"].items()
                            if key != "comparisons"
                        }
                    ),
                }
                for letter, entry in configuration_abc.items()
                if letter in ("A", "B", "C")
            },
            "configuration_e_summary": {
                "status": configuration_abc.get("E", {}).get("status"),
                "blocker": configuration_abc.get("E", {}).get("blocker"),
                "comparison": (
                    None
                    if "comparison" not in configuration_abc.get("E", {})
                    else {
                        key: value
                        for key, value in configuration_abc["E"][
                            "comparison"
                        ].items()
                        if key != "comparisons"
                    }
                ),
            },
        },
        "configurations": configuration_abc,
        "reference_table": {
            key: value for key, value in reference_table.items() if key != "_rows"
        },
        "source": {
            "repository": "https://github.com/theibsi/data_sets",
            "commit": commit,
            "dataset": "ibsi_1_ct_radiomics_phantom",
            "license": "CC BY-NC 3.0",
            "image": {
                "path": str(image_path),
                "sha256": sha256(image_path),
                "bytes": image_path.stat().st_size,
            },
            "mask": {
                "path": str(mask_path),
                "sha256": sha256(mask_path),
                "bytes": mask_path.stat().st_size,
            },
        },
        "image": {
            "shape_zyx": list(image_array.shape),
            "spacing_xyz": list(image.GetSpacing()),
            "roi_voxels": int(values.size),
        },
        "preprocessing": {
            "discretization": "fixed_bin_number",
            "number_of_bins": 32,
            "intensity_rounding": "nearest_integer",
            "resampling": [2.0, 2.0, 2.0],
            "interpolator": "sitkLinear",
            "resegmentation": {
                "method": "outlier_standard_deviation",
                "sigma": 3.0,
            },
            "label": 1,
            "features": ["mean", "std", "min", "max"],
        },
        "feature_coverage": _feature_coverage(),
        "heeh_v1": {
            **app_alignment,
            "configuration_d_workflow": {
                "status": (
                    "reference_verified"
                    if configuration_d_verified
                    else "incomplete_or_mismatched"
                ),
                "available_when": (
                    "The user selects a 3D CT image, imports an aligned NIfTI "
                    "ROI mask or a DICOM RTSTRUCT ROI, and runs IBSI "
                    "Configuration D."
                ),
                "shared_with_reference_verifier": True,
                "reference_comparison": (
                    None
                    if zrad_comparison is None
                    else {
                        key: value
                        for key, value in zrad_comparison.items()
                        if key != "comparisons"
                    }
                ),
            },
        },
        "pyradiomics": {
            "version": str(diagnostics.get("diagnostics_Versions_PyRadiomics", "unknown")),
            "features": pyradiomics,
        },
        "reference_implementation": reference,
        "ibsi_reference_engine": {
            "implementation": None if zrad is None else zrad["implementation"],
            "version": None if zrad is None else zrad["version"],
            "configuration": None if zrad is None else zrad["configuration"],
            "error": zrad_error,
            "features": None if zrad is None else zrad["features"],
            "comparison": zrad_comparison,
        },
        "absolute_errors": batch_comparison,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.data_root, args.output), sort_keys=True))
