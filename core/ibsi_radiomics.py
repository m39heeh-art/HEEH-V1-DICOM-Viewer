"""IBSI Configuration D radiomics for imported 3D image and ROI masks."""

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

    file_hashes = []
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


def _analysis_provenance(
    image_path: Path,
    mask_path: Path,
    result: dict[str, Any],
    *,
    image_source_files: list[Path],
) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    lock_path = project_root / "requirements.lock"
    project_version = "unknown"
    project_file = project_root / "pyproject.toml"
    if project_file.is_file():
        import tomllib

        project_version = tomllib.loads(
            project_file.read_text(encoding="utf-8")
        ).get("project", {}).get("version", "unknown")
    package_versions = {}
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
            "version": project_version,
            "source_revision": (
                os.environ.get("HEEH_SOURCE_REVISION")
                or os.environ.get("GITHUB_SHA")
                or "unavailable"
            ),
            "dependency_lock_sha256": (
                _sha256_file(lock_path)
                if lock_path.is_file()
                else None
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
            raise ValueError("IBSI Configuration D currently requires a CT image.")
        selected_series_uid = str(
            getattr(dataset, "SeriesInstanceUID", "")
        )
        if not selected_series_uid:
            raise ValueError("The selected DICOM image has no SeriesInstanceUID.")
        dicom_directory = image_path.parent

        series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(
            str(dicom_directory)
        ) or []
        if selected_series_uid not in series_ids:
            raise ValueError("The selected CT series could not be found.")
        series_files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(
            str(dicom_directory), selected_series_uid
        )
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(series_files)
        return Image._from_sitk_image(reader.Execute()), [
            Path(series_file) for series_file in series_files
        ]

    import SimpleITK as sitk
    import pydicom

    series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(
        str(dicom_directory)
    ) or []
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
        ct_series = [
            item for item in ct_series if item[0] == selected_series_uid
        ]
    if len(ct_series) != 1:
        raise ValueError(
            "Select a directory containing exactly one CT DICOM series, "
            "or choose a slice from the intended series."
        )
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(ct_series[0][1])
    return Image._from_sitk_image(reader.Execute()), [
        Path(series_file) for series_file in ct_series[0][1]
    ]


def run_configuration_d(
    image_path: str | Path,
    mask_path: str | Path,
    *,
    roi_name: str | None = None,
) -> dict[str, Any]:
    """Extract 3D IBSI Configuration D features using an imported ROI mask."""
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
    from zrad.radiomics import Radiomics

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

    features: dict[str, float] = {}
    for aggregation in ("AVER", "MERG"):
        result = Radiomics(
            aggr_dim="3D",
            aggr_method=aggregation,
        ).extract_features(
            roi_data=roi,
            families="all",
            include_metadata=False,
        )
        features.update(
            {
                key: float(value)
                for key, value in result.items()
                if np.isfinite(float(value))
            }
        )

    valid_voxels = roi.intensity_mask.array[
        ~np.isnan(roi.intensity_mask.array)
    ]
    if valid_voxels.size == 0:
        raise ValueError("The imported mask contains no valid ROI voxels.")

    result = {
        "status": "configuration_d_pipeline_applied",
        "implementation": "Z-Rad",
        "version": "26.9.0",
        "mask_source": mask_source,
        "roi_name": roi_name.strip() if roi_name else None,
        "configuration": {
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
            "texture_aggregation": ["AVER", "MERG"],
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
    }
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
