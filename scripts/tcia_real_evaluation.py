# -*- coding: utf-8 -*-
"""Reproducible evaluation on a REAL public TCIA CT series.

Uses the application's own code paths:
  - core.ibsi_radiomics._load_reference_image style loading
    (SimpleITK/GDCM series reader, identical helper in this module)
  - core.tissue_classifier.RadiomicsExtractor  (in-app radiomics engine)
  - core.dicom_privacy.deidentify_dataset      (in-app de-identification)
  - app.ClinicalApp export packaging           (in-app export path)
  - core.export_validation.validate_export_archive (in-app export gate)

Writes:
  verification/results/tcia_real_evaluation.json
  docs/tcia_real_evaluation_report.md

The real series is NOT committed: verification/data/ is git-ignored and the
artifacts record SHA-256 fingerprints of the exact downloaded bytes instead.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import platform
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.dicom_privacy import deidentify_dataset  # noqa: E402
from core.export_validation import validate_export_archive  # noqa: E402
from core.tissue_classifier import RadiomicsExtractor  # noqa: E402

SERIES_UID = "1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879"
STUDY_UID = "1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971"
ZIP_PATH = REPO / "verification/data/tcia_real_evaluation/series.zip"
DCM_DIR = REPO / "verification/data/tcia_real_evaluation/dcm"
OUT_JSON = REPO / "verification/results/tcia_real_evaluation.json"
OUT_MD = REPO / "docs/tcia_real_evaluation_report.md"

PROVENANCE = {
    "collection": "CT-Phantom4Radiomics",
    "series_instance_uid": SERIES_UID,
    "study_instance_uid": STUDY_UID,
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "data_doi": "https://doi.org/10.7937/a1v1-rc66",
    "download": "NBIA API v4 getImage (real archive download; 173 ZIP entries: LICENSE + 172 DICOM slices)",
    "privacy_note": (
        "Public research phantom collection derived from real patient data as "
        "described by the data submitter; the processed series is a "
        "task-based anthropomorphic phantom scan published for research use. "
        "No human-subject identifiable data are stored in this repository."
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate_sha256(paths: list[Path]) -> str:
    hashes = sorted(sha256_file(p) for p in paths)
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def load_series_hu() -> tuple[np.ndarray, tuple[float, float, float], list[Path]]:
    """Load the real series exactly like the app's Configuration D path."""
    import SimpleITK as sitk

    reader = sitk.ImageSeriesReader()
    series_ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(DCM_DIR))
    if SERIES_UID not in series_ids:
        raise RuntimeError("Downloaded series UID not found in extracted files")
    file_names = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(
        str(DCM_DIR), SERIES_UID
    )
    reader.SetFileNames(file_names)
    image = reader.Execute()
    volume = sitk.GetArrayFromImage(image).astype(np.float64)  # [z, y, x] HU
    spacing = tuple(float(v) for v in image.GetSpacing())  # (x, y, z) mm
    return volume, spacing, [Path(name) for name in file_names]


def centered_roi_mask(
    shape_yx: tuple[int, int], spacing_xy: tuple[float, float], radius_mm: float
) -> tuple[np.ndarray, dict]:
    rows, cols = shape_yx
    cy, cx = rows / 2.0 - 0.5, cols / 2.0 - 0.5
    ry = radius_mm / spacing_xy[1]
    rx = radius_mm / spacing_xy[0]
    yy, xx = np.mgrid[0:rows, 0:cols]
    mask = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0
    info = {
        "definition": "centered ellipsoid cylinder on the mid axial slice; radius given in mm",
        "center_row": float(cy),
        "center_col": float(cx),
        "radius_mm": radius_mm,
        "radius_pixels_row": float(ry),
        "radius_pixels_col": float(rx),
        "voxels": int(mask.sum()),
        "mask_sha256": hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
    }
    return mask, info


def hu_calibration_probe(volume: np.ndarray) -> dict:
    """CT-number accuracy check on the real phantom's air regions.

    The phantom contains large tissue-equivalent inserts, so the whole-slice
    mean is NOT expected to be near air. Instead we measure the pixels that
    are actually air (HU <= -950), whose mean should sit near -1000 HU.
    """
    mid = volume[volume.shape[0] // 2]
    air = mid[mid <= -950]
    inserts = mid[(mid >= -150) & (mid <= 200)]
    return {
        "slice": "middle axial slice of the real series",
        "air_pixel_count": int(air.size),
        "air_mean_hu": float(air.mean()) if air.size else None,
        "air_std_hu": float(air.std()) if air.size else None,
        "air_reference_hu": -1000.0,
        "air_abs_deviation_hu": abs(float(air.mean()) - (-1000.0)) if air.size else None,
        "air_within_30hu_of_reference": (abs(float(air.mean()) - (-1000.0)) <= 30.0) if air.size else False,
        "soft_tissue_insert_voxels": int(inserts.size),
        "soft_tissue_insert_mean_hu": float(inserts.mean()) if inserts.size else None,
        "whole_slice_mean_hu": float(mid.mean()),
        "note": (
            "CT-number accuracy is assessed on the phantom's air regions "
            "(HU <= -950), which should reproduce -1000 HU within tolerance. "
            "The whole-slice mean is dominated by tissue-equivalent inserts "
            "and is recorded for completeness only."
        ),
    }


def firstorder_compare(slice_hu: np.ndarray, mask: np.ndarray, spacing_xy) -> dict:
    """App engine vs PyRadiomics v3.0.1 on the identical real-data ROI."""
    import SimpleITK as sitk
    from radiomics import featureextractor

    roi_hu = slice_hu[mask].astype(np.float64)
    report = RadiomicsExtractor.full_report(
        roi_hu,
        levels=256,
        discretization="fixed_bin_width",
        bin_width=25.0,
        spacing=(float(spacing_xy[0]), float(spacing_xy[1])),
    )
    hist = report["histogram"]
    app_values = {
        "mean": float(hist["mean"]),
        "std": float(hist["std"]),
        "min": float(hist["min"]),
        "max": float(hist["max"]),
    }

    roi_2d = slice_hu.astype(np.float64)
    image = sitk.GetImageFromArray(roi_2d)
    image.SetSpacing((float(spacing_xy[0]), float(spacing_xy[1])))
    mask_img = sitk.GetImageFromArray(mask.astype(np.uint8))
    mask_img.SetSpacing((float(spacing_xy[0]), float(spacing_xy[1])))
    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=25.0, label=1, voxelArrayShift=0.0
    )
    pyr = extractor.execute(image, mask_img)
    # PyRadiomics omits StandardDeviation from execute() output when Variance
    # is enabled (it is derivable: SD = sqrt(Variance)); this equivalence is
    # documented in firstorder.py (getStandardDeviationFeatureValue). We take
    # the square root explicitly so the comparison stays matched.
    pyr_values = {
        "mean": float(pyr["original_firstorder_Mean"]),
        "std": float(np.sqrt(float(pyr["original_firstorder_Variance"]))),
        "min": float(pyr["original_firstorder_Minimum"]),
        "max": float(pyr["original_firstorder_Maximum"]),
    }
    errors = {k: abs(app_values[k] - pyr_values[k]) for k in app_values}
    tolerance = 1e-6
    return {
        "roi": "centered 24 mm radius cylindrical ROI on the mid axial slice of the real TCIA series",
        "app_engine": "core.tissue_classifier.RadiomicsExtractor",
        "comparator": "PyRadiomics v3.0.1 (matched first-order; binWidth 25.0; voxelArrayShift 0.0; tolerance 1e-6)",
        "roi_voxels": int(mask.sum()),
        "app_values": app_values,
        "pyradiomics_values": pyr_values,
        "absolute_errors": errors,
        "tolerance": tolerance,
        "all_within_tolerance": all(v <= tolerance for v in errors.values()),
        "app_extras": {
            "entropy": hist.get("entropy"),
            "skewness": hist.get("skewness"),
            "kurtosis": hist.get("kurtosis"),
        },
    }


def export_roundtrip(middle_slice_path: Path) -> dict:
    """De-identify the REAL slice and export it through the app's own path."""
    import pydicom
    from app import ClinicalApp

    dataset = pydicom.dcmread(str(middle_slice_path))
    deidentified = deidentify_dataset(dataset)
    buffer = io.BytesIO()
    deidentified.save_as(buffer, enforce_file_format=True)
    payload = buffer.getvalue()
    check = pydicom.dcmread(io.BytesIO(payload))
    markers = {
        "patient_name": str(check.PatientName),
        "patient_id": str(check.PatientID),
        "identity_removed": str(getattr(check, "PatientIdentityRemoved", "")),
    }
    products = [
        {
            "data": payload,
            "file_name": "ct_slice_deidentified.dcm",
            "mime": "application/dicom",
        }
    ]
    manifest = ClinicalApp._export_standards_manifest(
        products, source="tcia_real_evaluation", measurement_count=0
    )
    products.append(
        {"data": manifest, "file_name": "export_manifest.json", "mime": "application/json"}
    )
    archive = ClinicalApp._build_export_zip(products, zip_name="tcia_real")
    valid_ok = validate_export_archive(archive)["ok"]

    # Deterministic tamper: rewrite the archive with one corrupted manifest
    # hash (manifest JSON is modified BEFORE compression so the mutation is
    # exact), then require the gate to reject it.
    import zipfile as _zipfile

    with _zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        entries = {info.filename: bundle.read(info.filename) for info in bundle.infolist()}
    manifest = json.loads(entries["export_manifest.json"].decode("utf-8"))
    first_hash = manifest["files"][0]["sha256"]
    flipped = "b" if first_hash[0] != "b" else "c"
    manifest["files"][0]["sha256"] = flipped + first_hash[1:]
    entries["export_manifest.json"] = json.dumps(manifest).encode("utf-8")
    tamper_buffer = io.BytesIO()
    with _zipfile.ZipFile(tamper_buffer, "w", compression=_zipfile.ZIP_DEFLATED) as rebuilt:
        for name, data in entries.items():
            rebuilt.writestr(name, data)
    invalid_ok = validate_export_archive(tamper_buffer.getvalue())["ok"]

    tp = int(valid_ok and not invalid_ok)
    tn = int((not valid_ok) and invalid_ok)
    return {
        "source_slice": middle_slice_path.name,
        "deidentification_markers": markers,
        "archive_bytes": len(archive),
        "valid_archive_accepted": valid_ok,
        "tamper_method": "manifest sha256 value corrupted before re-compression, archive rebuilt",
        "tampered_manifest_rejected": not invalid_ok,
        "tp": tp,
        "tn": tn,
        "sensitivity": (tp / 1.0) if tp else 0.0,
        "specificity": (tn / 1.0) if tn else 0.0,
        "estimate_scope": (
            "One real de-identified CT slice exported through the application's "
            "own packaging path and validated by the application's own gate; "
            "not a clinical performance estimate."
        ),
    }


def build_results() -> dict:
    import SimpleITK as sitk

    project_file = REPO / "pyproject.toml"
    project_version = (
        tomllib.loads(project_file.read_text(encoding="utf-8"))
        .get("project", {})
        .get("version", "unknown")
        if project_file.is_file()
        else "unknown"
    )
    lock = REPO / "requirements.lock"
    dcm_files = sorted(DCM_DIR.glob("*.dcm"))

    volume, spacing, ordered_files = load_series_hu()
    mid = volume.shape[0] // 2
    spacing_xy = (spacing[0], spacing[1])
    slice_2d = volume[mid]
    mask, roi_info = centered_roi_mask(
        (volume.shape[1], volume.shape[2]), spacing_xy, radius_mm=24.0
    )

    calibration = hu_calibration_probe(volume)
    comparison = firstorder_compare(slice_2d, mask, spacing_xy)
    export = export_roundtrip(ordered_files[mid])

    results = {
        "schema": "heeh-v1.tcia-real-evaluation",
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "software": {
            "name": "HEEH-V1 DICOM Viewer",
            "version": project_version,
            "requirements_lock_sha256": sha256_file(lock) if lock.is_file() else None,
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "packages": {
                "numpy": np.__version__,
                "SimpleITK": sitk.__version__ if hasattr(sitk, "__version__") else package_version("SimpleITK"),
                "pyradiomics": package_version("pyradiomics"),
                "pydicom": package_version("pydicom"),
                "z-rad": package_version("z-rad"),
            },
        },
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine_architecture": platform.machine(),
        },
        "series_provenance": PROVENANCE,
        "input_fingerprints": {
            "downloaded_zip_sha256": sha256_file(ZIP_PATH),
            "zip_bytes": ZIP_PATH.stat().st_size,
            "dicom_file_count": len(dcm_files),
            "ordered_source_files_aggregate_sha256": aggregate_sha256(ordered_files),
            "paths_recorded": False,
        },
        "series_geometry": {
            "slices_loaded": int(volume.shape[0]),
            "rows": int(volume.shape[1]),
            "columns": int(volume.shape[2]),
            "spacing_mm_xyz": [spacing[0], spacing[1], spacing[2]],
            "hu_range_volume": [float(volume.min()), float(volume.max())],
        },
        "hu_calibration_probe": calibration,
        "real_roi_radiomics": {
            "definition": roi_info,
            "slice_index": mid,
            "preprocessing": {
                "levels": 256,
                "discretization": "fixed_bin_width",
                "bin_width": 25.0,
                "spacing_applied_to_extractor": [spacing_xy[0], spacing_xy[1]],
            },
            "measured_firstorder": comparison["app_values"],
            "extras": comparison["app_extras"],
            "pyradiomics_reference_comparison": {
                "comparator": comparison["comparator"],
                "values": comparison["pyradiomics_values"],
                "absolute_errors": comparison["absolute_errors"],
                "tolerance": comparison["tolerance"],
                "all_within_tolerance": comparison["all_within_tolerance"],
            },
        },
        "real_export_validation": export,
        "scope_and_non_claims": [
            "Single real public phantom series; results describe this series only.",
            "The radiomics ROI is a defined geometric region, not a clinical lesion; no diagnostic meaning is attached to its values.",
            "PyRadiomics agreement is matched first-order only, at one preprocessing setting.",
            "The export check exercises the real packaging path on one real de-identified slice; it does not estimate clinical privacy performance at scale.",
            "No clinical accuracy, diagnostic, or full IBSI compliance claim is made.",
        ],
    }
    return results


def report_markdown(results: dict) -> str:
    geo = results["series_geometry"]
    cal = results["hu_calibration_probe"]
    roi = results["real_roi_radiomics"]
    cmp_ = roi["pyradiomics_reference_comparison"]
    exp = results["real_export_validation"]
    lines = [
        "# HEEH-V1 real-data evaluation (TCIA CT-Phantom4Radiomics)",
        "",
        "This report contains only measured values on a downloaded real public series. It does not claim clinical accuracy or full IBSI compliance.",
        "",
        "## Series provenance",
        f"- Collection: `{results['series_provenance']['collection']}` (real archive downloaded via NBIA; CC BY 4.0; {results['series_provenance']['data_doi']})",
        f"- SeriesInstanceUID: `{results['series_provenance']['series_instance_uid']}`",
        f"- Downloaded ZIP SHA-256: `{results['input_fingerprints']['downloaded_zip_sha256']}` ({results['input_fingerprints']['zip_bytes']:,} bytes)",
        f"- DICOM slices: {results['input_fingerprints']['dicom_file_count']} (aggregate SHA-256 `{results['input_fingerprints']['ordered_source_files_aggregate_sha256'][:16]}...`)",
        "",
        "## Geometry and HU calibration",
        f"- Volume: {geo['slices_loaded']} slices, {geo['rows']}x{geo['columns']}, spacing {geo['spacing_mm_xyz']} mm",
        f"- HU range (volume): {geo['hu_range_volume'][0]:.1f} .. {geo['hu_range_volume'][1]:.1f}",
        f"- Mid-slice air-region mean HU: {cal['air_mean_hu']:.3f} over {cal['air_pixel_count']} air pixels (reference -1000 HU; |deviation| = {cal['air_abs_deviation_hu']:.3f}, within ±30 HU: {cal['air_within_30hu_of_reference']}); soft-tissue insert mean {cal['soft_tissue_insert_mean_hu']:.1f} HU",
        "",
        "## Real-data ROI radiomics (mid axial slice, centered 24 mm radius ROI)",
        f"- ROI voxels: {roi['definition']['voxels']}",
        f"- App engine measured: mean {roi['measured_firstorder']['mean']:.6f} HU, std {roi['measured_firstorder']['std']:.6f} HU, min {roi['measured_firstorder']['min']:.3f} HU, max {roi['measured_firstorder']['max']:.3f} HU",
        f"- PyRadiomics v3.0.1 matched first-order absolute errors: mean {cmp_['absolute_errors']['mean']:.9f}, std {cmp_['absolute_errors']['std']:.9f}, min {cmp_['absolute_errors']['min']:.9f}, max {cmp_['absolute_errors']['max']:.9f} (tolerance {cmp_['tolerance']})",
        f"- All within tolerance: {cmp_['all_within_tolerance']}",
        "",
        "## Real-data export/privacy round trip",
        f"- De-identification markers: PatientName={exp['deidentification_markers']['patient_name']}, PatientID={exp['deidentification_markers']['patient_id']}, PatientIdentityRemoved={exp['deidentification_markers']['identity_removed']}",
        f"- Valid archive accepted by the export gate: {exp['valid_archive_accepted']}",
        f"- Tampered-manifest archive rejected: {exp['tampered_manifest_rejected']}",
        f"- Scope: {exp['estimate_scope']}",
        "",
        "## Limitations",
    ] + [f"- {item}" for item in results["scope_and_non_claims"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    results = build_results()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    OUT_MD.write_text(report_markdown(results), encoding="utf-8")
    print(
        json.dumps(
            {
                "hu_mean_deviation_from_air": results["hu_calibration_probe"]["air_abs_deviation_hu"],
                "pyradiomics_all_within_tolerance": results["real_roi_radiomics"][
                    "pyradiomics_reference_comparison"
                ]["all_within_tolerance"],
                "valid_archive_accepted": results["real_export_validation"][
                    "valid_archive_accepted"
                ],
                "tampered_manifest_rejected": results["real_export_validation"][
                    "tampered_manifest_rejected"
                ],
                "result_json": str(OUT_JSON),
                "report_md": str(OUT_MD),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
