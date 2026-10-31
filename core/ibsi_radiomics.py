"""IBSI 1 radiomics - Configurations A-E on a CT image + ROI mask.

The five reference workflows follow the official IBSI 1 configuration
tables (Reference data sets chapter, ibsi.readthedocs.io):

  A - 2D. No interpolation. Fixed-range resegmentation [-500, 400] HU.
      Texture and intensity-histogram discretisation: FBS 25 HU.
      Texture/local-intensity features are extracted in-plane (slice-wise).
  B - 2D. In-plane interpolation to 2 x 2 mm (bilinear, nearest-integer
      intensities; bilinear ROI mask at 0.5). Slice spacing is unchanged.
      Fixed-range resegmentation [-500, 400] HU. Texture/IH: FBN 32.
      Texture/local-intensity features are extracted in-plane.
  C - 3D. Interpolation to 2 x 2 x 2 mm (trilinear, nearest-integer
      intensities; trilinear ROI mask at 0.5). Fixed-range resegmentation
      [-1000, 400] HU. Texture/IH: FBS 25 HU; IVH: FBS 2.5 HU.
  D - 3D. Interpolation as in C, no fixed-range resegmentation, outlier
      resegmentation at mean +/- 3 SD. Texture/IH: FBN 32. IVH: direct.
  E - 3D. Cubic B-spline image interpolation, trilinear mask interpolation,
      fixed-range and 3-SD resegmentation. Texture/IH: FBN 32. IVH: FBN 1000.

Morphology, statistics, intensity-histogram and IVH families are extracted
volumetrically (3D, AVER and MERG aggregation) for every configuration.
Configuration D was present in the original release; A, B and C were
corrected to the official parameters after installing the pinned IBSI
reference data, and E implements the official B-spline workflow
(see verification/README_DATA.md and docs/ibsi_ct_subset.md).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import numpy as np

from core.ibsi_reporting import build_ibsi_ct_reporting_context


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_fingerprint(
    path: Path,
    *,
    source_files: list[Path] | None = None,
) -> dict[str, Any]:
    """Hash input file bytes or a directory snapshot without recording paths."""
    if source_files is None and path.is_file():
        files = [path]
        kind = "file"
    elif source_files is not None:
        files = source_files
        kind = "source_file_set"
    elif path.is_dir():
        files = sorted(item for item in path.rglob("*") if item.is_file())
        kind = "directory_content_set"
    else:
        raise FileNotFoundError(f"Analysis input does not exist: {path}")

    file_hashes: list[str] = []
    total_bytes = 0
    for candidate in files:
        if not candidate.is_file():
            raise FileNotFoundError(
                "An analysis input disappeared before provenance hashing."
            )
        file_hashes.append(_sha256_file(candidate))
        total_bytes += candidate.stat().st_size
    if not file_hashes:
        raise ValueError("Analysis input contains no files to fingerprint.")
    if len(file_hashes) == 1:
        return {
            "kind": "file",
            "sha256": file_hashes[0],
            "bytes": total_bytes,
            "files_hashed": 1,
        }
    aggregate = hashlib.sha256(
        "\n".join(sorted(file_hashes)).encode("ascii")
    ).hexdigest()
    return {
        "kind": kind,
        "sha256": aggregate,
        "bytes": total_bytes,
        "files_hashed": len(file_hashes),
    }


def _project_version() -> str:
    try:
        return importlib.metadata.version("heeh-v1-dicom-viewer")
    except importlib.metadata.PackageNotFoundError:
        project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
        if project_file.is_file():
            import tomllib

            return tomllib.loads(
                project_file.read_text(encoding="utf-8")
            ).get("project", {}).get("version", "unknown")
        return "unknown"


def _analysis_provenance(
    image_path: Path,
    mask_path: Path,
    result: dict[str, Any],
    *,
    image_source_files: list[Path],
) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    lock_path = project_root / "requirements.lock"
    package_versions: dict[str, str] = {}
    for package in ("numpy", "SimpleITK", "z-rad", "pydicom"):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = "unavailable"

    canonical_result = json.dumps(
        result, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return {
        "schema": "heeh-v1.analysis-provenance",
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "software": {
            "name": "HEEH-V1 DICOM Viewer",
            "version": _project_version(),
            "source_revision": (
                os.environ.get("HEEH_SOURCE_REVISION")
                or os.environ.get("GITHUB_SHA")
                or "unavailable"
            ),
            "dependency_lock_sha256": (
                _sha256_file(lock_path) if lock_path.is_file() else None
            ),
        },
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine_architecture": platform.machine(),
            "packages": package_versions,
        },
        "inputs": {
            "image": _input_fingerprint(
                image_path, source_files=image_source_files
            ),
            "mask": _input_fingerprint(mask_path),
            "paths_recorded": False,
        },
        "analysis_result_sha256": hashlib.sha256(canonical_result).hexdigest(),
        "privacy_note": (
            "Input fingerprints identify content and may enable linkage. They "
            "are not anonymization or protection against re-identification."
        ),
    }


def _load_reference_image(image_path: Path) -> tuple[Any, list[Path]]:
    from zrad.image import Image

    name = image_path.name.lower()
    if image_path.is_dir():
        dicom_directory = image_path
        selected_series_uid = None
    elif name.endswith((".nii", ".nii.gz")):
        return Image.from_nifti(image_path), [image_path]
    else:
        import pydicom
        import SimpleITK as sitk

        dataset = pydicom.dcmread(str(image_path), stop_before_pixels=True)
        modality = str(getattr(dataset, "Modality", "")).upper()
        if modality != "CT":
            raise ValueError("IBSI Configuration requires a CT image.")
        selected_series_uid = str(getattr(dataset, "SeriesInstanceUID", ""))
        if not selected_series_uid:
            raise ValueError("The selected DICOM image has no SeriesInstanceUID.")
        dicom_directory = image_path.parent

        series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(dicom_directory)) or []
        if selected_series_uid not in series_ids:
            raise ValueError("The selected CT series could not be found.")
        series_files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(
            str(dicom_directory), selected_series_uid
        )
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(series_files)
        return Image._from_sitk_image(reader.Execute()), [Path(f) for f in series_files]

    import SimpleITK as sitk
    import pydicom

    series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(dicom_directory)) or []
    ct_series = []
    for series_uid in series_ids:
        series_files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(
            str(dicom_directory), series_uid
        )
        if not series_files:
            continue
        dataset = pydicom.dcmread(series_files[0], stop_before_pixels=True)
        if str(getattr(dataset, "Modality", "")).upper() == "CT":
            ct_series.append((series_uid, series_files))
    if selected_series_uid is not None:
        ct_series = [item for item in ct_series if item[0] == selected_series_uid]
    if len(ct_series) != 1:
        raise ValueError(
            "Select a directory containing exactly one CT DICOM series, "
            "or choose a slice from the intended series."
        )
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(ct_series[0][1])
    return Image._from_sitk_image(reader.Execute()), [Path(f) for f in ct_series[0][1]]


def _load_mask(
    mask_path: Path,
    image: Any,
    roi_name: str | None,
) -> tuple[Any, str]:
    """Load a NIfTI or DICOM RTSTRUCT mask aligned to image."""
    from zrad.image import Image

    mask_name = mask_path.name.lower()
    if mask_name.endswith((".nii", ".nii.gz")):
        return Image.from_nifti_mask(mask_path, reference=image), "NIfTI"
    if not (roi_name and roi_name.strip()):
        raise ValueError("Enter the ROI name stored in the DICOM RTSTRUCT.")
    return (
        Image.from_dicom_mask(mask_path, roi_name.strip(), reference=image),
        "DICOM RTSTRUCT",
    )


IBSI1_FEATURE_FAMILY_COUNTS = {
    "morphology": 29,
    "local_intensity": 2,
    "intensity_statistics": 18,
    "intensity_histogram": 23,
    "ivh": 5,
    "glcm": 25,
    "glrlm": 16,
    "glszm": 16,
    "gldzm": 16,
    "ngtdm": 5,
    "ngldm": 17,
}

_ZRAD_FAMILIES = tuple(IBSI1_FEATURE_FAMILY_COUNTS)
_IBSI_FAMILY_PREFIXES = {
    "morphology": "morph",
    "local_intensity": "loc",
    "intensity_statistics": "stat",
    "intensity_histogram": "ih",
    "ivh": "ivh",
    "glcm": "cm",
    "glrlm": "rlm",
    "glszm": "szm",
    "gldzm": "dzm",
    "ngtdm": "ngt",
    "ngldm": "ngl",
}


_TEXTURE_FAMILIES = frozenset({"glcm", "glrlm"})
_ZONE_IN_PLANE_FAMILIES = frozenset(
    {"glszm", "gldzm", "ngtdm", "ngldm"}
)

_AGGREGATION_PLANS: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
for _family in _ZRAD_FAMILIES:
    if _family in _TEXTURE_FAMILIES:
        # IBSI publishes averaged and merged variants for both the
        # in-slice dimension and the 2.5D aggregation. Z-Rad's
        # SLICE_MERG merges direction matrices within a slice (the
        # IBSI "2D slice-merged" columns) while AVER averages features
        # per direction (the averaged columns). At 2.5D, DIR_MERG
        # averages the pooled direction matrices of every slice (the
        # IBSI "2.5D direction-merged" columns) and MERG pools across
        # directions and slices (the "2.5D merged" columns).
        _AGGREGATION_PLANS[(_family, "2D")] = (
            ("2D", "AVER"),
            ("2D", "SLICE_MERG"),
            ("2.5D", "DIR_MERG"),
            ("2.5D", "MERG"),
        )
        _AGGREGATION_PLANS[(_family, "3D")] = (("3D", "AVER"), ("3D", "MERG"))
    elif _family == "local_intensity":
        _AGGREGATION_PLANS[(_family, "2D")] = (("2D", "AVER"),)
        _AGGREGATION_PLANS[(_family, "3D")] = (("3D", "AVER"),)
    elif _family in _ZONE_IN_PLANE_FAMILIES:
        _AGGREGATION_PLANS[(_family, "2D")] = (("2D", "AVER"), ("2.5D", "AVER"))
        _AGGREGATION_PLANS[(_family, "3D")] = (("3D", "AVER"),)
    else:
        _AGGREGATION_PLANS[(_family, "2D")] = (("3D", "AVER"),)
        _AGGREGATION_PLANS[(_family, "3D")] = (("3D", "AVER"),)


def _extract_features(
    roi: Any,
    *,
    in_plane_aggr_dim: str = "3D",
) -> tuple[dict[str, float], dict[str, str]]:
    """Run Z-Rad feature extraction with AVER and MERG aggregation.

    Families are extracted one at a time. A degenerate ROI (for example a
    fully homogeneous or perfectly symmetric shape) can make one family
    mathematically undefined; that family is then recorded as unsupported
    instead of aborting the whole extraction, and the reason is reported in
    the result so it cannot be silently missing.

    ``in_plane_aggr_dim`` implements the IBSI 2D configurations (A and B):
    local-intensity and texture families are extracted on the in-slice
    plane instead of volumetrically, while morphology, statistics,
    intensity-histogram and IVH families remain volumetric.
    """
    from zrad.exceptions import DataStructureError
    from zrad.radiomics import Radiomics

    features: dict[str, float] = {}
    unsupported_families: dict[str, str] = {}
    for family in _ZRAD_FAMILIES:
        plan = _AGGREGATION_PLANS[(family, in_plane_aggr_dim)]
        family_features: dict[str, float] = {}
        for aggr_dim, aggr_method in plan:
            try:
                batch = Radiomics(
                    aggr_dim=aggr_dim,
                    aggr_method=aggr_method,
                ).extract_features(
                    roi_data=roi,
                    families=family,
                    include_metadata=False,
                )
            except DataStructureError as exc:
                unsupported_families[family] = f"{type(exc).__name__}: {exc}"
                break
            nonfinite_features = []
            for key, value in batch.items():
                numeric_value = float(value)
                if np.isfinite(numeric_value):
                    family_features[key] = numeric_value
                else:
                    nonfinite_features.append(key)
            if nonfinite_features:
                unsupported_families[family] = (
                    "The feature engine returned non-finite values for: "
                    + ", ".join(sorted(nonfinite_features))
                )
        if not family_features and family not in unsupported_families:
            unsupported_families[family] = (
                "The feature engine returned no finite feature values for this ROI."
            )
        features.update(family_features)
    if not features:
        raise ValueError(
            "No feature could be computed for this ROI; the ROI may be "
            "too small or fully degenerate."
        )
    return features, unsupported_families


def _feature_family_coverage(
    features: dict[str, float],
    unsupported_families: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Report output coverage against the IBSI 1 feature-family inventory."""
    coverage = {}
    for family, definition_count in IBSI1_FEATURE_FAMILY_COUNTS.items():
        prefix = f"{_IBSI_FAMILY_PREFIXES[family]}_"
        output_count = sum(name.startswith(prefix) for name in features)
        status = (
            "unsupported"
            if family in unsupported_families
            else "computed"
            if output_count
            else "missing"
        )
        coverage[family] = {
            "ibsi_feature_definitions": definition_count,
            "computed_output_values": output_count,
            "status": status,
            "reason": unsupported_families.get(family),
        }
    return coverage


def _valid_roi_voxels(roi: Any) -> np.ndarray:
    """Return the finite (non-NaN) intensity values inside the ROI."""
    return roi.intensity_mask.array[~np.isnan(roi.intensity_mask.array)]


def _attach_ibsi_reporting_context(
    result: dict[str, Any],
    image: Any,
    image_source_files: list[Path],
) -> None:
    result["ibsi_reporting"] = build_ibsi_ct_reporting_context(
        configuration=result["configuration"],
        mask_source=result["mask_source"],
        roi_name=result["roi_name"],
        input_spacing_mm=image.spacing,
        image_source_files=image_source_files,
        feature_count=len(result["features"]),
        feature_family_coverage=result["feature_family_coverage"],
        application_version=_project_version(),
        radiomics_engine_version=result["version"],
    )


def run_configuration_a(
    image_path: str | Path,
    mask_path: str | Path,
    *,
    roi_name: str | None = None,
) -> dict[str, Any]:
    """Extract 2D IBSI Configuration A features (official parameters).

    Configuration A uses the original grid (no interpolation), fixed-range
    resegmentation [-500, 400] HU, fixed-bin-size 25 HU discretisation for
    texture and intensity-histogram features, and direct IVH (calibrated
    discrete intensities). In-plane (2D) extraction applies to the
    local-intensity and texture families; morphology, statistics, IH and
    IVH families are volumetric.
    """
    image_path = Path(image_path)
    mask_path = Path(mask_path)

    # Validate the mask source before importing Z-Rad (guard is DLL-free).
    _mask_name = mask_path.name.lower()
    if not _mask_name.endswith((".nii", ".nii.gz")) and not (
        roi_name and roi_name.strip()
    ):
        raise ValueError("Enter the ROI name stored in the DICOM RTSTRUCT.")

    from zrad.preprocessing import (
        IntensityMaskBuilder,
        IVHIntensityDiscretizer,
        Resegmenter,
        RoiData,
        TextureDiscretizer,
    )

    image, image_source_files = _load_reference_image(image_path)
    mask, mask_source = _load_mask(mask_path, image, roi_name)

    roi = RoiData(image=image, morphological_mask=mask)
    roi = IntensityMaskBuilder().apply(roi)
    roi = Resegmenter(intensity_range=(-500.0, 400.0)).apply(roi)
    roi = TextureDiscretizer(bin_size=25.0).apply(roi)
    roi = IVHIntensityDiscretizer(method="direct").apply(roi)

    features, unsupported_families = _extract_features(
        roi, in_plane_aggr_dim="2D"
    )
    valid_voxels = _valid_roi_voxels(roi)
    if valid_voxels.size == 0:
        raise ValueError(
            "The imported mask contains no valid ROI voxels after "
            "the IBSI Configuration A resegmentation range [-500, 400] HU."
        )
    morphological_voxels = int(np.count_nonzero(roi.morphological_mask.array))

    result: dict[str, Any] = {
        "status": "configuration_a_pipeline_applied",
        "implementation": "Z-Rad",
        "version": "26.9.0",
        "mask_source": mask_source,
        "roi_name": roi_name.strip() if roi_name else None,
        "configuration": {
            "ibsi_configuration": "A",
            "dimension": "2D",
            "resampling_mm": None,
            "interpolation": None,
            "resegmentation": {
                "method": "fixed_range",
                "range_lower_hu": -500.0,
                "range_upper_hu": 400.0,
                "outlier_filtering": False,
            },
            "texture_and_histogram_discretization": {
                "method": "fixed bin size",
                "bin_size_hu": 25.0,
            },
            "ivh_discretization": "direct",
            "texture_aggregation": ["AVER", "SLICE_MERG", "DIR_MERG", "MERG"],
        },
        "analysis": {
            "roi_voxels": int(valid_voxels.size),
            "morphological_voxels": morphological_voxels,
            "intensity_mean": float(np.mean(valid_voxels)),
            "intensity_min": float(np.min(valid_voxels)),
            "intensity_max": float(np.max(valid_voxels)),
        },
        "features": features,
        "unsupported_families": unsupported_families,
        "feature_family_coverage": _feature_family_coverage(
            features, unsupported_families
        ),
    }
    _attach_ibsi_reporting_context(result, image, image_source_files)
    result["provenance"] = _analysis_provenance(
        image_path,
        mask_path,
        {k: v for k, v in result.items() if k != "provenance"},
        image_source_files=image_source_files,
    )
    return result


def run_configuration_b(
    image_path: str | Path,
    mask_path: str | Path,
    *,
    roi_name: str | None = None,
) -> dict[str, Any]:
    """Extract 2D IBSI Configuration B features (official parameters).

    Configuration B interpolates in-plane only to 2 x 2 mm voxels (bilinear
    interpolation with nearest-integer intensities; bilinear ROI mask at a
    0.5 partial-volume threshold; slice spacing unchanged), applies
    fixed-range resegmentation [-500, 400] HU, and uses 32-bin FBN
    discretisation for texture and intensity-histogram features with direct
    IVH. In-plane extraction applies to the local-intensity and texture
    families; the remaining families are volumetric.
    """
    image_path = Path(image_path)
    mask_path = Path(mask_path)

    # Validate the mask source before importing Z-Rad (guard is DLL-free).
    _mask_name = mask_path.name.lower()
    if not _mask_name.endswith((".nii", ".nii.gz")) and not (
        roi_name and roi_name.strip()
    ):
        raise ValueError("Enter the ROI name stored in the DICOM RTSTRUCT.")

    from zrad.preprocessing import (
        ImageResampler,
        IntensityMaskBuilder,
        IVHIntensityDiscretizer,
        MaskResampler,
        Resegmenter,
        RoiData,
        TextureDiscretizer,
    )

    image, image_source_files = _load_reference_image(image_path)
    mask, mask_source = _load_mask(mask_path, image, roi_name)

    slice_spacing = float(image.spacing[2])
    in_plane_resolution = (2.0, 2.0, slice_spacing)

    roi = RoiData(image=image, morphological_mask=mask)
    roi = ImageResampler(
        in_plane_resolution,
        method="linear",
        intensity_rounding="nearest_integer",
    ).apply(roi)
    roi = MaskResampler(
        in_plane_resolution,
        method="linear",
        partial_volume_threshold=0.5,
    ).apply(roi)
    roi = IntensityMaskBuilder().apply(roi)
    roi = Resegmenter(intensity_range=(-500.0, 400.0)).apply(roi)
    roi = TextureDiscretizer(number_of_bins=32).apply(roi)
    roi = IVHIntensityDiscretizer(method="direct").apply(roi)

    features, unsupported_families = _extract_features(
        roi, in_plane_aggr_dim="2D"
    )
    valid_voxels = _valid_roi_voxels(roi)
    if valid_voxels.size == 0:
        raise ValueError(
            "The imported mask contains no valid ROI voxels after the "
            "IBSI Configuration B resampling and [-500, 400] HU resegmentation."
        )
    morphological_voxels = int(np.count_nonzero(roi.morphological_mask.array))

    result: dict[str, Any] = {
        "status": "configuration_b_pipeline_applied",
        "implementation": "Z-Rad",
        "version": "26.9.0",
        "mask_source": mask_source,
        "roi_name": roi_name.strip() if roi_name else None,
        "configuration": {
            "ibsi_configuration": "B",
            "dimension": "2D",
            "resampling_mm": [2.0, 2.0, slice_spacing],
            "interpolation": "bilinear (in-plane)",
            "image_interpolation": "linear",
            "resampled_intensity_rounding": "nearest_integer",
            "mask_interpolation": "linear",
            "mask_threshold": 0.5,
            "resegmentation": {
                "method": "fixed_range",
                "range_lower_hu": -500.0,
                "range_upper_hu": 400.0,
                "outlier_filtering": False,
            },
            "texture_and_histogram_discretization": {
                "method": "fixed bin number",
                "number_of_bins": 32,
            },
            "ivh_discretization": "direct",
            "texture_aggregation": ["AVER", "SLICE_MERG", "DIR_MERG", "MERG"],
        },
        "analysis": {
            "resampled_image_dimensions_xyz": [int(v) for v in roi.image.shape],
            "resampled_roi_voxels": int(valid_voxels.size),
            "morphological_voxels": morphological_voxels,
            "intensity_mean": float(np.mean(valid_voxels)),
            "intensity_min": float(np.min(valid_voxels)),
            "intensity_max": float(np.max(valid_voxels)),
        },
        "features": features,
        "unsupported_families": unsupported_families,
        "feature_family_coverage": _feature_family_coverage(
            features, unsupported_families
        ),
    }
    _attach_ibsi_reporting_context(result, image, image_source_files)
    result["provenance"] = _analysis_provenance(
        image_path,
        mask_path,
        {k: v for k, v in result.items() if k != "provenance"},
        image_source_files=image_source_files,
    )
    return result


def run_configuration_c(
    image_path: str | Path,
    mask_path: str | Path,
    *,
    roi_name: str | None = None,
    range_lower: float = -1000.0,
    range_upper: float = 400.0,
) -> dict[str, Any]:
    """Extract 3D IBSI Configuration C features (official parameters).

    Configuration C resamples to isotropic 2 mm voxels (trilinear with
    nearest-integer intensities; trilinear ROI mask at 0.5), applies
    fixed-range resegmentation [-1000, 400] HU by default, uses fixed-bin-
    size 25 HU discretisation for texture and intensity-histogram features,
    and fixed-bin-size 2.5 HU discretisation for the intensity-volume
    histogram.
    """
    image_path = Path(image_path)
    mask_path = Path(mask_path)

    if not np.isfinite([range_lower, range_upper]).all():
        raise ValueError("range_lower and range_upper must be finite numbers.")
    if range_lower >= range_upper:
        raise ValueError("range_lower must be strictly less than range_upper.")

    # Validate the mask source before importing Z-Rad (guard is DLL-free).
    _mask_name = mask_path.name.lower()
    if not _mask_name.endswith((".nii", ".nii.gz")) and not (
        roi_name and roi_name.strip()
    ):
        raise ValueError("Enter the ROI name stored in the DICOM RTSTRUCT.")

    from zrad.preprocessing import (
        ImageResampler,
        IntensityMaskBuilder,
        IVHIntensityDiscretizer,
        MaskResampler,
        Resegmenter,
        RoiData,
        TextureDiscretizer,
    )

    image, image_source_files = _load_reference_image(image_path)
    mask, mask_source = _load_mask(mask_path, image, roi_name)

    roi = RoiData(image=image, morphological_mask=mask)
    roi = ImageResampler(
        (2.0, 2.0, 2.0),
        method="linear",
        intensity_rounding="nearest_integer",
    ).apply(roi)
    roi = MaskResampler(
        (2.0, 2.0, 2.0),
        method="linear",
        partial_volume_threshold=0.5,
    ).apply(roi)
    roi = IntensityMaskBuilder().apply(roi)
    roi = Resegmenter(
        intensity_range=(range_lower, range_upper),
    ).apply(roi)
    roi = TextureDiscretizer(bin_size=25.0).apply(roi)
    roi = IVHIntensityDiscretizer(
        method="fixed_bin_size", bin_size=2.5
    ).apply(roi)

    features, unsupported_families = _extract_features(roi)
    valid_voxels = _valid_roi_voxels(roi)
    if valid_voxels.size == 0:
        raise ValueError(
            "The imported mask contains no valid ROI voxels after "
            f"range resegmentation [{range_lower}, {range_upper}] HU."
        )
    morphological_voxels = int(np.count_nonzero(roi.morphological_mask.array))

    result: dict[str, Any] = {
        "status": "configuration_c_pipeline_applied",
        "implementation": "Z-Rad",
        "version": "26.9.0",
        "mask_source": mask_source,
        "roi_name": roi_name.strip() if roi_name else None,
        "configuration": {
            "ibsi_configuration": "C",
            "dimension": "3D",
            "resampling_mm": [2.0, 2.0, 2.0],
            "image_interpolation": "linear",
            "resampled_intensity_rounding": "nearest_integer",
            "mask_interpolation": "linear",
            "mask_threshold": 0.5,
            "resegmentation": {
                "method": "fixed_range",
                "range_lower_hu": range_lower,
                "range_upper_hu": range_upper,
                "outlier_filtering": False,
            },
            "reference_configuration": (
                range_lower == -1000.0 and range_upper == 400.0
            ),
            "texture_and_histogram_discretization": {
                "method": "fixed bin size",
                "bin_size_hu": 25.0,
            },
            "ivh_discretization": {
                "method": "fixed bin size",
                "bin_size_hu": 2.5,
            },
            "texture_aggregation": ["AVER", "SLICE_MERG", "DIR_MERG", "MERG"],
        },
        "analysis": {
            "resampled_image_dimensions_xyz": [int(v) for v in roi.image.shape],
            "resampled_roi_voxels": int(valid_voxels.size),
            "morphological_voxels": morphological_voxels,
            "resegmented_intensity_mean": float(np.mean(valid_voxels)),
            "resegmented_intensity_min": float(np.min(valid_voxels)),
            "resegmented_intensity_max": float(np.max(valid_voxels)),
        },
        "features": features,
        "unsupported_families": unsupported_families,
        "feature_family_coverage": _feature_family_coverage(
            features, unsupported_families
        ),
    }
    _attach_ibsi_reporting_context(result, image, image_source_files)
    result["provenance"] = _analysis_provenance(
        image_path,
        mask_path,
        {k: v for k, v in result.items() if k != "provenance"},
        image_source_files=image_source_files,
    )
    return result


def run_configuration_d(
    image_path: str | Path,
    mask_path: str | Path,
    *,
    roi_name: str | None = None,
) -> dict[str, Any]:
    """Extract 3D IBSI Configuration D features using an imported ROI mask.

    Official parameters: 3D trilinear interpolation to 2 x 2 x 2 mm with
    nearest-integer intensities, ROI mask interpolated trilinearly at 0.5,
    outlier resegmentation at mean +/- 3 SD (no fixed range), 32-bin FBN
    texture and intensity-histogram discretisation, and direct IVH.
    """
    image_path = Path(image_path)
    mask_path = Path(mask_path)
    mask_name = mask_path.name.lower()
    if not mask_name.endswith((".nii", ".nii.gz")) and not (
        roi_name and roi_name.strip()
    ):
        raise ValueError("Enter the ROI name stored in the DICOM RTSTRUCT.")

    from zrad.image import Image
    from zrad.preprocessing import (
        ImageResampler,
        IntensityMaskBuilder,
        IVHIntensityDiscretizer,
        MaskResampler,
        Resegmenter,
        RoiData,
        TextureDiscretizer,
    )

    image, image_source_files = _load_reference_image(image_path)
    if mask_name.endswith((".nii", ".nii.gz")):
        mask = Image.from_nifti_mask(mask_path, reference=image)
        mask_source = "NIfTI"
    else:
        mask = Image.from_dicom_mask(
            mask_path,
            roi_name.strip(),
            reference=image,
        )
        mask_source = "DICOM RTSTRUCT"

    roi = RoiData(image=image, morphological_mask=mask)
    roi = ImageResampler(
        (2.0, 2.0, 2.0),
        method="linear",
        intensity_rounding="nearest_integer",
    ).apply(roi)
    roi = MaskResampler(
        (2.0, 2.0, 2.0),
        method="linear",
        partial_volume_threshold=0.5,
    ).apply(roi)
    roi = IntensityMaskBuilder().apply(roi)
    roi = Resegmenter(outlier_range=3.0).apply(roi)
    roi = TextureDiscretizer(number_of_bins=32).apply(roi)
    roi = IVHIntensityDiscretizer(method="direct").apply(roi)

    features, unsupported_families = _extract_features(roi)

    valid_voxels = roi.intensity_mask.array[
        ~np.isnan(roi.intensity_mask.array)
    ]
    if valid_voxels.size == 0:
        raise ValueError("The imported mask contains no valid ROI voxels.")

    result: dict[str, Any] = {
        "status": "configuration_d_pipeline_applied",
        "implementation": "Z-Rad",
        "version": "26.9.0",
        "mask_source": mask_source,
        "roi_name": roi_name.strip() if roi_name else None,
        "configuration": {
            "ibsi_configuration": "D",
            "dimension": "3D",
            "resampling_mm": [2.0, 2.0, 2.0],
            "image_interpolation": "linear",
            "resampled_intensity_rounding": "nearest_integer",
            "mask_interpolation": "linear",
            "mask_threshold": 0.5,
            "resegmentation": "outlier removal at mean +/- 3 SD",
            "texture_and_histogram_discretization": {
                "method": "fixed bin number",
                "number_of_bins": 32,
            },
            "ivh_discretization": "direct",
            "texture_aggregation": ["AVER", "SLICE_MERG", "DIR_MERG", "MERG"],
        },
        "analysis": {
            "resampled_image_dimensions_xyz": [
                int(value) for value in roi.image.shape
            ],
            "resampled_roi_voxels": int(valid_voxels.size),
            "resegmented_intensity_mean": float(np.mean(valid_voxels)),
            "resegmented_intensity_min": float(np.min(valid_voxels)),
            "resegmented_intensity_max": float(np.max(valid_voxels)),
        },
        "features": features,
        "unsupported_families": unsupported_families,
        "feature_family_coverage": _feature_family_coverage(
            features, unsupported_families
        ),
    }
    _attach_ibsi_reporting_context(result, image, image_source_files)
    result["provenance"] = _analysis_provenance(
        image_path,
        mask_path,
        {
            key: value
            for key, value in result.items()
            if key != "provenance"
        },
        image_source_files=image_source_files,
    )
    return result


def run_configuration_e(
    image_path: str | Path,
    mask_path: str | Path,
    *,
    roi_name: str | None = None,
) -> dict[str, Any]:
    """Extract IBSI Configuration E features from a CT image and ROI mask.

    Configuration E uses cubic B-spline image interpolation and trilinear
    mask interpolation on a 2 mm isotropic grid, nearest-integer image
    rounding, fixed-range and 3-SD outlier resegmentation, 32-bin FBN texture
    and histogram discretisation, and 1000-bin FBN IVH discretisation.
    """
    image_path = Path(image_path)
    mask_path = Path(mask_path)
    mask_name = mask_path.name.lower()
    if not mask_name.endswith((".nii", ".nii.gz")) and not (
        roi_name and roi_name.strip()
    ):
        raise ValueError("Enter the ROI name stored in the DICOM RTSTRUCT.")

    from zrad.image import Image
    from zrad.preprocessing import (
        ImageResampler,
        IntensityMaskBuilder,
        IVHIntensityDiscretizer,
        MaskResampler,
        Resegmenter,
        RoiData,
        TextureDiscretizer,
    )

    image, image_source_files = _load_reference_image(image_path)
    if mask_name.endswith((".nii", ".nii.gz")):
        mask = Image.from_nifti_mask(mask_path, reference=image)
        mask_source = "NIfTI"
    else:
        mask = Image.from_dicom_mask(
            mask_path,
            roi_name.strip(),
            reference=image,
        )
        mask_source = "DICOM RTSTRUCT"

    target_spacing = (2.0, 2.0, 2.0)
    roi = RoiData(image=image, morphological_mask=mask)
    roi = ImageResampler(
        target_spacing,
        method="bspline",
        intensity_rounding="nearest_integer",
    ).apply(roi)
    roi = MaskResampler(
        target_spacing,
        method="linear",
        partial_volume_threshold=0.5,
    ).apply(roi)
    roi = IntensityMaskBuilder().apply(roi)
    roi = Resegmenter(
        intensity_range=(-1000.0, 400.0),
        outlier_range=3.0,
    ).apply(roi)
    roi = TextureDiscretizer(number_of_bins=32).apply(roi)
    roi = IVHIntensityDiscretizer(
        method="fixed_bin_number",
        number_of_bins=1000,
    ).apply(roi)

    features, unsupported_families = _extract_features(roi)
    valid_voxels = roi.intensity_mask.array[
        ~np.isnan(roi.intensity_mask.array)
    ]
    if valid_voxels.size == 0:
        raise ValueError(
            "The imported mask contains no valid ROI voxels after "
            "IBSI Configuration E resegmentation."
        )

    result: dict[str, Any] = {
        "status": "configuration_e_pipeline_applied",
        "implementation": "Z-Rad",
        "version": "26.9.0",
        "mask_source": mask_source,
        "roi_name": roi_name.strip() if roi_name else None,
        "configuration": {
            "ibsi_configuration": "E",
            "dimension": "3D",
            "resampling_mm": [2.0, 2.0, 2.0],
            "image_interpolation": "tricubic spline (cubic B-spline)",
            "resampled_intensity_rounding": "nearest_integer",
            "mask_interpolation": "trilinear",
            "mask_threshold": 0.5,
            "resegmentation": {
                "method": "fixed_range_and_outlier",
                "range_lower_hu": -1000.0,
                "range_upper_hu": 400.0,
                "outlier_sigma": 3.0,
            },
            "texture_and_histogram_discretization": {
                "method": "fixed bin number",
                "number_of_bins": 32,
            },
            "ivh_discretization": {
                "method": "fixed bin number",
                "number_of_bins": 1000,
            },
            "texture_aggregation": ["AVER", "SLICE_MERG", "DIR_MERG", "MERG"],
        },
        "analysis": {
            "resampled_image_dimensions_xyz": [
                int(value) for value in roi.image.shape
            ],
            "resampled_roi_voxels": int(valid_voxels.size),
            "resegmented_intensity_mean": float(np.mean(valid_voxels)),
            "resegmented_intensity_min": float(np.min(valid_voxels)),
            "resegmented_intensity_max": float(np.max(valid_voxels)),
        },
        "features": features,
        "unsupported_families": unsupported_families,
        "feature_family_coverage": _feature_family_coverage(
            features, unsupported_families
        ),
    }
    _attach_ibsi_reporting_context(result, image, image_source_files)
    result["provenance"] = _analysis_provenance(
        image_path,
        mask_path,
        {
            key: value
            for key, value in result.items()
            if key != "provenance"
        },
        image_source_files=image_source_files,
    )
    return result