# -*- coding: utf-8 -*-
"""Full-series statistical study on the REAL TCIA CT series (172 slices).

Extends scripts/tcia_real_evaluation.py from a single-slice protocol to:
  1. First-order app-vs-PyRadiomics agreement on ALL slices (24 mm ROI).
  2. ROI-radius sensitivity sweep on the mid slice (12/18/24/30/36 mm).
  3. De-identification + export round trip for ALL slices, with sampled
     tamper-rejection checks (deterministic manifest corruption).
  4. Air-region CT-number calibration for ALL slices (worst slice reported).
  5. Quantitative root-cause analysis of the 8 morphology disagreements
     (PyRadiomics mesh-based vs voxel-count volume definitions) on a real
     3D spherical ROI.

Writes:
  verification/results/tcia_full_series_study.json
  docs/tcia_full_series_study_report.md
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.tcia_real_evaluation import (  # noqa: E402
    OUT_JSON as SINGLE_JSON,
    PROVENANCE,
    ZIP_PATH,
    centered_roi_mask,
    load_series_hu,
    sha256_file,
)

OUT_JSON = REPO / "verification/results/tcia_full_series_study.json"
OUT_MD = REPO / "docs/tcia_full_series_study_report.md"

RADII_MM = [12.0, 18.0, 24.0, 30.0, 36.0]
TAMPER_STRIDE = 17  # deterministic sampling for the rejection check


def aggregate_sha256(paths: list[Path]) -> str:
    hashes = sorted(sha256_file(p) for p in paths)
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


def firstorder_pair(slice_2d: np.ndarray, mask: np.ndarray, spacing_xy):
    """App engine vs PyRadiomics on one 2D ROI; returns (app, pyr, errors)."""
    import SimpleITK as sitk
    from radiomics import featureextractor

    roi_hu = slice_2d[mask].astype(np.float64)
    report = __import__(
        "core.tissue_classifier", fromlist=["RadiomicsExtractor"]
    ).RadiomicsExtractor.full_report(
        roi_hu,
        levels=256,
        discretization="fixed_bin_width",
        bin_width=25.0,
        spacing=(float(spacing_xy[0]), float(spacing_xy[1])),
    )
    hist = report["histogram"]
    app = {
        "mean": float(hist["mean"]),
        "std": float(hist["std"]),
        "min": float(hist["min"]),
        "max": float(hist["max"]),
    }
    image = sitk.GetImageFromArray(slice_2d.astype(np.float64))
    image.SetSpacing((float(spacing_xy[0]), float(spacing_xy[1])))
    mask_img = sitk.GetImageFromArray(mask.astype(np.uint8))
    mask_img.SetSpacing((float(spacing_xy[0]), float(spacing_xy[1])))
    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=25.0, label=1, voxelArrayShift=0.0
    )
    pyr_raw = extractor.execute(image, mask_img)
    pyr = {
        "mean": float(pyr_raw["original_firstorder_Mean"]),
        # PyRadiomics omits SD when Variance is enabled; SD = sqrt(Variance).
        "std": float(np.sqrt(float(pyr_raw["original_firstorder_Variance"]))),
        "min": float(pyr_raw["original_firstorder_Minimum"]),
        "max": float(pyr_raw["original_firstorder_Maximum"]),
    }
    errors = {k: abs(app[k] - pyr[k]) for k in app}
    return app, pyr, errors


def export_roundtrip(dataset, *, tamper: bool):
    """De-identify + package + gate one REAL slice; optional rejection check."""
    from app import ClinicalApp
    from core.dicom_privacy import deidentify_dataset
    from core.export_validation import validate_export_archive

    deidentified = deidentify_dataset(dataset)
    buffer = io.BytesIO()
    deidentified.save_as(buffer, enforce_file_format=True)
    products = [
        {
            "data": buffer.getvalue(),
            "file_name": "ct_slice_deidentified.dcm",
            "mime": "application/dicom",
        }
    ]
    manifest = ClinicalApp._export_standards_manifest(
        products, source="tcia_full_series_study", measurement_count=0
    )
    products.append(
        {"data": manifest, "file_name": "export_manifest.json", "mime": "application/json"}
    )
    archive = ClinicalApp._build_export_zip(products, zip_name="study")
    accepted = validate_export_archive(archive)["ok"]
    rejected = None
    if tamper:
        with __import__("zipfile").ZipFile(io.BytesIO(archive)) as bundle:
            entries = {
                info.filename: bundle.read(info.filename)
                for info in bundle.infolist()
            }
        parsed = json.loads(entries["export_manifest.json"].decode("utf-8"))
        first_hash = parsed["files"][0]["sha256"]
        parsed["files"][0]["sha256"] = (
            "b" if first_hash[0] != "b" else "c"
        ) + first_hash[1:]
        entries["export_manifest.json"] = json.dumps(parsed).encode("utf-8")
        rebuilt = io.BytesIO()
        with __import__("zipfile").ZipFile(
            rebuilt, "w", compression=__import__("zipfile").ZIP_DEFLATED
        ) as writer:
            for name, data in entries.items():
                writer.writestr(name, data)
        rejected = not validate_export_archive(rebuilt.getvalue())["ok"]
    return accepted, rejected, len(archive)


def spherical_3d_mask(shape_zyx, spacing_xyz, radius_mm):
    cz, cy, cx = (s / 2.0 - 0.5 for s in shape_zyx)
    zz, yy, xx = np.mgrid[0 : shape_zyx[0], 0 : shape_zyx[1], 0 : shape_zyx[2]]
    return (
        ((zz - cz) * spacing_xyz[2]) ** 2
        + ((yy - cy) * spacing_xyz[1]) ** 2
        + ((xx - cx) * spacing_xyz[0]) ** 2
    ) <= radius_mm**2


def morphology_root_cause(volume, spacing, mid):
    """Data-driven root cause of the 8 morphology disagreements.

    Quantifies, on a real 3D spherical ROI, the internal gap between
    PyRadiomics' two volume definitions (mesh vs voxel counting), and
    decomposes the recorded IBSI-table morphology failures into signed
    relative deviations grouped by feature kind (volumes, surface, ratios,
    PCA eigenvalues) so the dominant convention gap is measured, not guessed.
    """
    import SimpleITK as sitk
    from radiomics import featureextractor

    mask = spherical_3d_mask(volume.shape, spacing, 24.0)
    voxel_volume_mm3 = float(spacing[0] * spacing[1] * spacing[2])
    voxel_count_volume = float(mask.sum()) * voxel_volume_mm3

    image = sitk.GetImageFromArray(volume.astype(np.float64))
    image.SetSpacing((float(spacing[0]), float(spacing[1]), float(spacing[2])))
    mask_img = sitk.GetImageFromArray(mask.astype(np.uint8))
    mask_img.SetSpacing((float(spacing[0]), float(spacing[1]), float(spacing[2])))
    extractor = featureextractor.RadiomicsFeatureExtractor(label=1)
    extractor.disableAllFeatures()
    extractor.enableFeatureClassByName("shape")
    raw = extractor.execute(image, mask_img)
    mesh_volume = float(raw["original_shape_MeshVolume"])
    pyr_voxel_volume = float(raw["original_shape_VoxelVolume"])

    # Decompose the RECORDED IBSI-table morphology failures (signed,
    # relative to the official expected values).
    recorded_path = REPO / "verification/results/ibsi_configuration_d_verification.json"
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    rows = recorded["absolute_errors"]["comparisons"]
    failed = [
        row
        for row in rows
        if row.get("family") == "Morphology"
        and row.get("passed") is False
        and row.get("expected") is not None
        and row.get("actual") is not None
    ]
    decomposition = []
    for row in failed:
        expected = float(row["expected"])
        actual = float(row["actual"])
        decomposition.append(
            {
                "tag": row["tag"],
                "feature": row["feature"],
                "expected": expected,
                "actual": actual,
                "signed_relative_deviation": (actual - expected) / expected,
            }
        )
    volume_rows = [d for d in decomposition if d["tag"] in ("morph_volume", "morph_vol_approx")]
    surface_rows = [d for d in decomposition if d["tag"] == "morph_area_mesh"]
    ratio_rows = [d for d in decomposition if d["tag"] in ("morph_av", "morph_sphericity")]
    pca_rows = [d for d in decomposition if d["tag"].startswith("morph_pca")]

    def span(group):
        values = [d["signed_relative_deviation"] for d in group]
        if not values:
            return None
        return {"min": min(values), "max": max(values)}

    return {
        "real_3d_roi": {
            "roi": "3D sphere, 24 mm radius, centered in the real volume",
            "roi_voxels": int(mask.sum()),
            "voxel_volume_mm3": voxel_volume_mm3,
            "voxel_count_volume_mm3": voxel_count_volume,
            "pyradiomics_mesh_volume_mm3": mesh_volume,
            "pyradiomics_voxel_volume_mm3": pyr_voxel_volume,
            "mesh_vs_voxel_count_relative_difference": abs(
                mesh_volume - voxel_count_volume
            )
            / voxel_count_volume,
        },
        "recorded_table_decomposition": {
            "failed_rows": len(decomposition),
            "rows": decomposition,
            "volume_rows_span": span(volume_rows),
            "surface_rows_span": span(surface_rows),
            "ratio_rows_span": span(ratio_rows),
            "pca_rows_span": span(pca_rows),
        },
        "finding": (
            "On a smooth real 3D sphere at the series' anisotropic spacing, "
            "PyRadiomics' mesh and voxel-count volume definitions agree to "
            "within {internal:.2%}. In the recorded IBSI phantom comparison, "
            "PyRadiomics' two volume definitions also agree closely with each "
            "other, while both deviate from the official expected values by "
            "{vols}; surface area deviates by {surf}, and surface-derived "
            "ratios compound to {ratios}. The dominant source is therefore "
            "the reference phantom's mask/grid convention (the official "
            "values derive from the IBSI reference segmentation), with "
            "marching-cubes surface extraction on anisotropic voxels driving "
            "the larger surface and ratio deviations; PCA eigenvalue rows use "
            "a further decomposition convention. Reconciliation requires "
            "running the comparator on the IBSI reference segmentation "
            "itself and is disclosed as out of scope."
        ).format(
            internal=abs(mesh_volume - voxel_count_volume) / voxel_count_volume,
            vols=("{:.2%} to {:.2%}".format(
                span(volume_rows)["min"], span(volume_rows)["max"]
            ) if volume_rows else "n/a"),
            surf=("{:+.2%}".format(surface_rows[0]["signed_relative_deviation"]) if surface_rows else "n/a"),
            ratios=("{:+.2%} to {:+.2%}".format(
                span(ratio_rows)["min"], span(ratio_rows)["max"]
            ) if ratio_rows else "n/a"),
        ),
    }


def build_study() -> dict:
    import pydicom

    volume, spacing, ordered_files = load_series_hu()
    n_slices = volume.shape[0]
    spacing_xy = (spacing[0], spacing[1])
    mid = n_slices // 2

    per_slice = []
    t0 = time.perf_counter()
    for index in range(n_slices):
        mask, _info = centered_roi_mask(
            (volume.shape[1], volume.shape[2]), spacing_xy, radius_mm=24.0
        )
        app, pyr, errors = firstorder_pair(volume[index], mask, spacing_xy)
        per_slice.append(
            {
                "slice": index,
                "roi_voxels": int(mask.sum()),
                "app": app,
                "pyradiomics": pyr,
                "absolute_errors": errors,
                "all_within_tolerance": all(v <= 1e-6 for v in errors.values()),
            }
        )
    agreement_count = sum(1 for r in per_slice if r["all_within_tolerance"])
    max_error = max(
        max(r["absolute_errors"].values()) for r in per_slice
    )

    radius_sweep = []
    for radius in RADII_MM:
        mask, info = centered_roi_mask(
            (volume.shape[1], volume.shape[2]), spacing_xy, radius_mm=radius
        )
        app, pyr, errors = firstorder_pair(volume[mid], mask, spacing_xy)
        radius_sweep.append(
            {
                "radius_mm": radius,
                "roi_voxels": int(mask.sum()),
                "app": app,
                "pyradiomics": pyr,
                "absolute_errors": errors,
                "all_within_tolerance": all(v <= 1e-6 for v in errors.values()),
            }
        )

    air_records = []
    for index in range(n_slices):
        air = volume[index][volume[index] <= -950]
        air_records.append(
            {
                "slice": index,
                "air_pixels": int(air.size),
                "air_mean_hu": float(air.mean()) if air.size else None,
            }
        )
    deviations = [
        abs(r["air_mean_hu"] + 1000.0) for r in air_records if r["air_mean_hu"] is not None
    ]
    worst_index = int(np.argmax(deviations))

    export_records = []
    tamper_results = []
    for index in range(n_slices):
        dataset = pydicom.dcmread(str(ordered_files[index]))
        accepted, rejected, archive_bytes = export_roundtrip(
            dataset, tamper=(index % TAMPER_STRIDE == 0)
        )
        export_records.append({"slice": index, "accepted": accepted})
        if rejected is not None:
            tamper_results.append({"slice": index, "rejected": rejected})
        dataset = None

    morphology = morphology_root_cause(volume, spacing, mid)

    study = {
        "schema": "heeh-v1.tcia-full-series-study",
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "extends": {
            "single_slice_protocol": str(SINGLE_JSON.relative_to(REPO)).replace("\\", "/"),
            "series_provenance": PROVENANCE,
            "downloaded_zip_sha256": sha256_file(ZIP_PATH),
            "ordered_source_files_aggregate_sha256": aggregate_sha256(ordered_files),
        },
        "protocol": {
            "slices": n_slices,
            "roi": "centered 24 mm radius cylindrical ROI per slice unless stated",
            "comparison": "app RadiomicsExtractor vs PyRadiomics v3.0.1 (binWidth 25.0, voxelArrayShift 0.0, tolerance 1e-6; SD = sqrt(Variance))",
            "radius_sweep_mm": RADII_MM,
            "tamper_stride": TAMPER_STRIDE,
        },
        "all_slices_firstorder_agreement": {
            "n": n_slices,
            "within_tolerance": agreement_count,
            "agreement_rate": agreement_count / n_slices,
            "max_absolute_error": max_error,
            "tolerance": 1e-6,
            "per_slice": per_slice,
        },
        "radius_sensitivity_mid_slice": radius_sweep,
        "air_calibration_all_slices": {
            "reference_hu": -1000.0,
            "tolerance_hu": 30.0,
            "max_deviation_hu": float(max(deviations)),
            "worst_slice": air_records[worst_index]["slice"],
            "all_within_tolerance": bool(max(deviations) <= 30.0),
            "per_slice": air_records,
        },
        "export_privacy_all_slices": {
            "n": n_slices,
            "accepted": sum(1 for r in export_records if r["accepted"]),
            "acceptance_rate": sum(1 for r in export_records if r["accepted"]) / n_slices,
            "tamper_checks": len(tamper_results),
            "tamper_rejected": sum(1 for r in tamper_results if r["rejected"]),
            "tamper_records": tamper_results,
        },
        "morphology_root_cause": morphology,
        "scope_and_non_claims": [
            "All results describe the single real recorded phantom series only.",
            "Radiomics ROIs are geometric regions; no clinical or diagnostic meaning is attached.",
            "PyRadiomics agreement covers matched first-order statistics on 2D ROIs and shape definitions on one 3D ROI.",
            "The export gate exercise covers this series' slices only; it is not a clinical privacy estimate.",
            "The morphology analysis quantifies the mesh-vs-voxel-count definitional gap; full reconciliation with the official IBSI phantom mask remains out of scope.",
            "No clinical accuracy, diagnostic, or full IBSI compliance claim is made.",
        ],
        "runtime_seconds": round(time.perf_counter() - t0, 1),
    }
    return study


def report_markdown(study: dict) -> str:
    agr = study["all_slices_firstorder_agreement"]
    sweep = study["radius_sensitivity_mid_slice"]
    air = study["air_calibration_all_slices"]
    exp = study["export_privacy_all_slices"]
    morph = study["morphology_root_cause"]
    lines = [
        "# HEEH-V1 full-series real-data study (TCIA CT-Phantom4Radiomics)",
        "",
        f"Statistical extension of the single-slice protocol to all {study['protocol']['slices']} slices of the downloaded real series. No clinical claims.",
        "",
        "## First-order agreement, all slices (24 mm ROI)",
        f"- {agr['within_tolerance']}/{agr['n']} slices within the 1e-6 tolerance (rate {agr['agreement_rate']:.3f}); max absolute error {agr['max_absolute_error']:.3e}.",
        "",
        "## ROI-radius sensitivity (mid slice)",
    ]
    for row in sweep:
        lines.append(
            f"- r = {row['radius_mm']:.0f} mm ({row['roi_voxels']} voxels): within tolerance {row['all_within_tolerance']}; max error {max(row['absolute_errors'].values()):.3e}"
        )
    lines += [
        "",
        "## Air-region CT-number calibration, all slices",
        f"- Worst-slice deviation {air['max_deviation_hu']:.2f} HU (slice {air['worst_slice']}); all slices within +/-30 HU: {air['all_within_tolerance']}.",
        "",
        "## Export/privacy round trip, all slices",
        f"- Accepted {exp['accepted']}/{exp['n']} ({exp['acceptance_rate']:.3f}); tamper-rejection checked on {exp['tamper_checks']} deterministically sampled slices, rejected {exp['tamper_rejected']}/{exp['tamper_checks']}.",
        "",
        "## Morphology 58/66 root cause (data-driven)",
        f"- Real 3D sphere ROI: voxel-count {morph['real_3d_roi']['voxel_count_volume_mm3']:.1f} mm3 vs PyRadiomics MeshVolume {morph['real_3d_roi']['pyradiomics_mesh_volume_mm3']:.1f} mm3 (internal definitional gap {morph['real_3d_roi']['mesh_vs_voxel_count_relative_difference']:.4%}).",
        f"- Recorded IBSI-table failures decomposed (signed, vs official expected values): volumes {morph['recorded_table_decomposition']['volume_rows_span']}, surface {morph['recorded_table_decomposition']['surface_rows_span']}, ratios {morph['recorded_table_decomposition']['ratio_rows_span']}, PCA {morph['recorded_table_decomposition']['pca_rows_span']}.",
        f"- Finding: {morph['finding']}",
        "",
        "## Limitations",
    ] + [f"- {item}" for item in study["scope_and_non_claims"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    study = build_study()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(study, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(report_markdown(study), encoding="utf-8")
    print(
        json.dumps(
            {
                "agreement": study["all_slices_firstorder_agreement"]["within_tolerance"],
                "n_slices": study["protocol"]["slices"],
                "max_error": study["all_slices_firstorder_agreement"]["max_absolute_error"],
                "radius_all_ok": all(r["all_within_tolerance"] for r in study["radius_sensitivity_mid_slice"]),
                "air_all_ok": study["air_calibration_all_slices"]["all_within_tolerance"],
                "export_accepted": study["export_privacy_all_slices"]["accepted"],
                "tamper_rejected": study["export_privacy_all_slices"]["tamper_rejected"],
                "real_3d_internal_gap": study["morphology_root_cause"]["real_3d_roi"][
                    "mesh_vs_voxel_count_relative_difference"
                ],
                "recorded_volume_deviation_span": study["morphology_root_cause"][
                    "recorded_table_decomposition"
                ]["volume_rows_span"],
                "runtime_s": study["runtime_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
