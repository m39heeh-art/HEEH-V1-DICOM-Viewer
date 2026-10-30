# -*- coding: utf-8 -*-
"""Small-ROI robustness study for HEEH-V1's on-board first-order CT metrics.

Research use case documented in ``research_case/README.md``.

Research question (single, specific):
    On the public TCIA ``CT-Phantom4Radiomics`` series (CC BY 4.0), how do
    HEEH-V1's on-board first-order CT statistics and radiomics features within
    a centered circular ROI on the mid axial slice change as the ROI radius
    shrinks from 36 mm to 8 mm, and does the application's exact first-order
    agreement with PyRadiomics v3.0.1 (tolerance 1e-6) hold at every tested
    ROI size?

Method (all through the application's own code paths):
    - Series loading: SimpleITK GDCM series reader by SeriesInstanceUID,
      exactly like the app's IBSI Configuration D path
      (reused from ``scripts/tcia_real_evaluation.py``).
    - CT ROI statistics: ``engines.modality_calculators.ct_calculator.CTCalculator
      .calculate(slice, roi=mask)``
    - First-order radiomics: ``core.tissue_classifier.RadiomicsExtractor
      .full_report(ROI_voxels, ...)``, the documented ROI call used by the
      project's own real-data evaluation scripts.
    - Shape features: ``RadiomicsExtractor.shape_features(mask, spacing)``.
    - External comparator: PyRadiomics v3.0.1, matched first-order features
      (binWidth 25.0, voxelArrayShift 0.0, tolerance 1e-6), as recorded in
      ``docs/tcia_real_evaluation_report.md``.

Saves (paths relative to the repository root):
    - research_case/settings/extraction_settings.json   (exact engine settings)
    - research_case/inputs/data_provenance.json         (fingerprints + details)
    - research_case/results/small_roi_robustness.json   (full results)
    - research_case/results/small_roi_robustness_table.csv
    - research_case/figures/fig1..fig4 PNG visualizations
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from engines.modality_calculators.ct_calculator import CTCalculator  # noqa: E402
from core.tissue_classifier import RadiomicsExtractor  # noqa: E402

# Reuse the loading/ROI helpers recorded for the v1.0.2 real-data study so the
# input handling in this use case is byte-identical to a documented path.
import scripts.tcia_real_evaluation as prior_study  # noqa: E402

# --------------------------------------------------------------------------
# Study settings (a canonical copy is written to settings/)
# --------------------------------------------------------------------------
STUDY_TITLE = "Small-ROI robustness of on-board first-order CT metrics"
RADIUS_MM_LIST = [8.0, 12.0, 16.0, 20.0, 24.0, 28.0, 32.0, 36.0]
REFERENCE_RADIUS_MM = 36.0
LEVELS = 256
BIN_WIDTH_HU = 25.0
DISCRETIZATION = "fixed_bin_width"
PYRADIOMICS_TOLERANCE = 1e-6
STABILITY_CV_THRESHOLD = 0.10
FIRST_ORDER_KEYS = [
    "mean", "median", "min", "max", "energy", "std", "variance",
    "skewness", "kurtosis", "p10", "p25", "p50", "p75", "p90", "entropy",
]

OUT_DIR = REPO / "research_case"
SETTINGS_JSON = OUT_DIR / "settings" / "extraction_settings.json"
INPUTS_JSON = OUT_DIR / "inputs" / "data_provenance.json"
RESULTS_JSON = OUT_DIR / "results" / "small_roi_robustness.json"
RESULTS_CSV = OUT_DIR / "results" / "small_roi_robustness_table.csv"
FIG_DIR = OUT_DIR / "figures"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_version() -> str:
    import tomllib
    return (
        tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        .get("project", {})
        .get("version", "unknown")
    )


def package_version(name: str) -> str:
    import importlib.metadata
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def pyradiomics_firstorder(slice_2d, mask, spacing_xy):
    import SimpleITK as sitk
    from radiomics import featureextractor

    image = sitk.GetImageFromArray(slice_2d.astype(np.float64))
    image.SetSpacing((float(spacing_xy[0]), float(spacing_xy[1])))
    mask_img = sitk.GetImageFromArray(mask.astype(np.uint8))
    mask_img.SetSpacing((float(spacing_xy[0]), float(spacing_xy[1])))
    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=BIN_WIDTH_HU, label=1, voxelArrayShift=0.0
    )
    pyr = extractor.execute(image, mask_img)
    # StandardDeviation is derivable from Variance (documented case in
    # scripts/tcia_real_evaluation.py); builds the same matched set.
    return {
        "mean": float(pyr["original_firstorder_Mean"]),
        "std": float(np.sqrt(float(pyr["original_firstorder_Variance"]))),
        "min": float(pyr["original_firstorder_Minimum"]),
        "max": float(pyr["original_firstorder_Maximum"]),
    }


def coefficient_of_variation(values: list[float]) -> float:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(np.mean(arr))
    if abs(mean) < np.finfo(np.float64).eps:
        return float("nan")
    return float(np.std(arr) / abs(mean))


def jsonable(obj):
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    return obj


def main() -> None:
    np.random.seed(0)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    INPUTS_JSON.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1) Inputs: verify the cached public series and record fingerprint.
    # ------------------------------------------------------------------
    zip_path = prior_study.ZIP_PATH
    recorded_sha = (
        "579233ebf30ce41985ad6971f150bf6e56a94a3944af6ee123737896b7590f17"
    )
    zip_sha = sha256_file(zip_path)
    dcm_files = sorted(prior_study.DCM_DIR.glob("*.dcm"))
    print(
        f"[inputs] {len(dcm_files)} DICOM slices; zip sha256 {zip_sha} "
        f"(recorded {recorded_sha}; match={zip_sha == recorded_sha})"
    )

    volume, spacing, ordered_files = prior_study.load_series_hu()
    spacing_xy = (spacing[0], spacing[1])
    mid_index = volume.shape[0] // 2
    slice_2d = volume[mid_index]
    print(
        f"[inputs] loaded {volume.shape} HU volume, in-plane spacing "
        f"{spacing_xy[0]:.6f}/{spacing_xy[1]:.6f} mm; analysis slice index {mid_index}"
    )

    inputs = {
        "study": STUDY_TITLE,
        "dataset": prior_study.PROVENANCE,
        "cached_zip_path": str(zip_path.relative_to(REPO)),
        "cached_zip_sha256": zip_sha,
        "recorded_download_sha256": recorded_sha,
        "cached_zip_matches_recorded_download": zip_sha == recorded_sha,
        "dicom_file_count": len(dcm_files),
        "ordered_source_files_aggregate_sha256": prior_study.aggregate_sha256(
            ordered_files
        ),
        "paths_recorded": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    INPUTS_JSON.write_text(json.dumps(jsonable(inputs), indent=2), encoding="utf-8")

    settings = {
        "study": STUDY_TITLE,
        "research_question": (
            "How do HEEH-V1 on-board first-order CT statistics and radiomics "
            "features within a centered circular ROI on the mid axial slice "
            "change as the ROI radius shrinks from 36 mm to 8 mm, and does "
            "the application's exact first-order agreement with PyRadiomics "
            "v3.0.1 (tolerance 1e-6) hold at every tested ROI size?"
        ),
        "analysis_slice": {
            "selection_rule": "volume.shape[0] // 2 (mid axial slice)",
            "slice_index": mid_index,
        },
        "roi": {
            "type": "centered circular cylinder on one 2D axial slice",
            "center": "volume center pixel (row = n_rows/2 - 0.5, col = n_cols/2 - 0.5)",
            "radii_mm": RADIUS_MM_LIST,
            "physical_basis": "DICOM PixelSpacing (row, column spacing) via SimpleITK",
        },
        "preprocessing": {
            "levels": LEVELS,
            "discretization": DISCRETIZATION,
            "bin_width_hu": BIN_WIDTH_HU,
        },
        "stability_criterion": {
            "metric": "coefficient_of_variation_across_radii",
            "definition": "population std of the across-radius values / abs(mean) of those values",
            "threshold": STABILITY_CV_THRESHOLD,
            "interpretation": "feature is called radius-stable when CV <= threshold",
        },
        "comparator": {
            "name": "pyradiomics",
            "settings": {
                "binWidth": BIN_WIDTH_HU,
                "label": 1,
                "voxelArrayShift": 0.0,
            },
            "tolerance": PYRADIOMICS_TOLERANCE,
        },
        "engines": {
            "ct_calculator": (
                "engines.modality_calculators.ct_calculator.CTCalculator.calculate(slice, roi=mask)"
            ),
            "first_order": (
                "core.tissue_classifier.RadiomicsExtractor.full_report(ROI_voxels, "
                f"levels={LEVELS}, discretization='{DISCRETIZATION}', bin_width={BIN_WIDTH_HU})"
            ),
            "shape": (
                "core.tissue_classifier.RadiomicsExtractor.shape_features(mask, spacing=spacing_xyz)"
            ),
        },
        "software": {
            "application": "HEEH-V1(TM) DICOM Viewer",
            "application_version": project_version(),
            "python_version": platform.python_version(),
            "numpy": np.__version__,
            "simpleitk": package_version("SimpleITK"),
            "pyradiomics": package_version("pyradiomics"),
            "pydicom": package_version("pydicom"),
        },
        "boundary_notes": [
            "The in-app radiomics ROI call analyzes ROI voxel values; texture "
            "families (GLCM/GLRLM/GLSZM/GLDM/NGTDM) require a 2D finite image "
            "and are not part of this ROI sweep (feature_coverage boundary).",
            "PyRadiomics agreement is matched first-order only, same as the "
            "recorded project evaluations.",
            "The ROI is a defined geometric region, not a clinical lesion; no "
            "diagnostic meaning is attached to any measured value.",
        ],
    }
    SETTINGS_JSON.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # 2) Analysis: sweep the ROI radius through the app's own engines.
    # ------------------------------------------------------------------
    rows = []
    ct_engine = CTCalculator()

    for radius_mm in RADIUS_MM_LIST:
        mask, roi_info = prior_study.centered_roi_mask(
            (volume.shape[1], volume.shape[2]), spacing_xy, radius_mm=radius_mm
        )
        roi_voxels = slice_2d[mask].astype(np.float64)

        ct = ct_engine.calculate(slice_2d, roi=mask)
        report = RadiomicsExtractor.full_report(
            roi_voxels,
            levels=LEVELS,
            discretization=DISCRETIZATION,
            bin_width=BIN_WIDTH_HU,
            spacing=spacing_xy,
        )
        # Mask is (rows, cols); the engine requires one positive spacing per
        # mask dimension: (row spacing, column spacing).
        shape = RadiomicsExtractor.shape_features(
            mask, spacing=(spacing_xy[1], spacing_xy[0])
        )
        pyr = pyradiomics_firstorder(slice_2d, mask, spacing_xy)

        app_mean_std = {
            "mean": float(report["histogram"]["mean"]),
            "std": float(report["histogram"]["std"]),
            "min": float(report["histogram"]["min"]),
            "max": float(report["histogram"]["max"]),
        }
        errors = {k: abs(app_mean_std[k] - pyr[k]) for k in app_mean_std}
        agree = {k: bool(v <= PYRADIOMICS_TOLERANCE) for k, v in errors.items()}

        row = {
            "radius_mm": radius_mm,
            "roi_voxels": int(mask.sum()),
            "roi_diameter_mm": 2.0 * radius_mm,
            "hu_mean": ct["hu_statistics"]["mean"],
            "hu_median": ct["hu_statistics"]["median"],
            "hu_std": ct["hu_statistics"]["std"],
            "snr_water_ref": ct["snr_cnr"]["snr_water_hu"],
            "first_order": {k: float(report["histogram"][k]) for k in FIRST_ORDER_KEYS},
            "shape": jsonable(shape),
            "pyradiomics": pyr,
            "pyradiomics_abs_errors": errors,
            "pyradiomics_within_1e6": agree,
            "pyradiomics_max_abs_error": max(errors.values()),
        }
        rows.append(row)
        print(
            f"[sweep] r={radius_mm:5.1f} mm  voxels={row['roi_voxels']:6d}  "
            f"mean HU={row['hu_mean']:.4f}  std={row['hu_std']:.4f}  "
            f"pyradiomics max|err|={row['pyradiomics_max_abs_error']:.2e}  "
            f"agree={all(agree.values())}"
        )

    # ------------------------------------------------------------------
    # 3) Stability analysis relative to the largest ROI.
    # ------------------------------------------------------------------
    reference = next(r for r in rows if r["radius_mm"] == REFERENCE_RADIUS_MM)
    stability = {}
    for key in FIRST_ORDER_KEYS:
        values = [r["first_order"][key] for r in rows]
        ref = reference["first_order"][key]
        rel_dev = {
            r["radius_mm"]: abs(v - ref) / (abs(ref) if abs(ref) > 0 else 1.0)
            for r, v in zip(rows, values)
        }
        stability[key] = {
            "values_by_radius_mm": {
                r["radius_mm"]: v for r, v in zip(rows, values)
            },
            "cv_across_radii": coefficient_of_variation(values),
            "radius_stable_within_10pct_cv": bool(
                coefficient_of_variation(values) <= STABILITY_CV_THRESHOLD
            ),
            "value_at_36mm": ref,
            "relative_deviation_vs_36mm": rel_dev,
            "absolute_deviation_vs_36mm": {
                r["radius_mm"]: v - ref
                for r, v in zip(rows, values)
            },
        }
    hu_stats_summary = {}
    for key in ["hu_mean", "hu_std", "snr_water_ref"]:
        values = [r[key] for r in rows]
        ref = reference[key]
        hu_stats_summary[key] = {
            "values_by_radius_mm": {
                r["radius_mm"]: v for r, v in zip(rows, values)
            },
            "cv_across_radii": coefficient_of_variation(values),
            "relative_deviation_vs_36mm": {
                r["radius_mm"]: abs(v - ref) / (abs(ref) if abs(ref) > 0 else 1.0)
                for r, v in zip(rows, values)
            },
        }
    agreement = {
        "radii_tested": len(rows),
        "all_radii_within_1e6": all(
            all(r["pyradiomics_within_1e6"].values()) for r in rows
        ),
        "max_abs_error_over_all_radii": max(
            r["pyradiomics_max_abs_error"] for r in rows
        ),
    }

    results = {
        "schema": "heeh-v1.research-case.small-roi-robustness",
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "study": STUDY_TITLE,
        "research_question": settings["research_question"],
        "finding_summary": agreement,
        "stability": {
            "first_order": stability,
            "ct_stats": hu_stats_summary,
        },
        "per_radius_measurements": rows,
        "scope_and_non_claims": [
            "Single real public phantom series; results describe this series only.",
            "The radiomics ROI is a defined geometric region, not a clinical lesion.",
            "PyRadiomics agreement is matched first-order only, at one preprocessing setting.",
            "Stability classification is a study-defined descriptive criterion "
            "(CV <= 0.10 across the tested radii), not an externally validated "
            "robustness requirement.",
            "No clinical accuracy, diagnostic, or full IBSI compliance claim is made.",
        ],
    }
    RESULTS_JSON.write_text(json.dumps(jsonable(results), indent=2), encoding="utf-8")

    # CSV: one row per radius.
    import csv

    with RESULTS_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        header = ["radius_mm", "roi_voxels"] + [
            f"hu_{k}" for k in ("mean", "median", "std")
        ] + ["snr_water_ref"] + [f"firstorder_{k}" for k in FIRST_ORDER_KEYS] + [
            f"pyradiomics_{k}" for k in ("mean", "std", "min", "max")
        ] + ["pyradiomics_max_abs_error"]
        writer.writerow(header)
        for r in rows:
            writer.writerow(
                [r["radius_mm"], r["roi_voxels"]]
                + [r["hu_mean"], r["hu_median"], r["hu_std"], r["snr_water_ref"]]
                + [r["first_order"][k] for k in FIRST_ORDER_KEYS]
                + [r["pyradiomics"][k] for k in ("mean", "std", "min", "max")]
                + [r["pyradiomics_max_abs_error"]]
            )

    agreement_note = (
        "YES - all radii within tolerance"
        if agreement["all_radii_within_1e6"]
        else "NO - check pyradiomics_within_1e6 flags"
    )

    first_order_stability = stability

    print("[results]", RESULTS_JSON)
    print("[results]", RESULTS_CSV)
    print(f"[results] agreement: {agreement_note}")
    print("[results] radii-stable features (CV<=0.10):",
          [k for k, v in first_order_stability.items()
           if v["radius_stable_within_10pct_cv"]])

    # ------------------------------------------------------------------
    # 4) Visualizations.
    # ------------------------------------------------------------------
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    center = 40.0
    window = 400.0
    display = np.clip(
        (slice_2d - (center - window / 2.0)) / window, 0.0, 1.0
    )
    rows_px, cols_px = slice_2d.shape
    cy = rows_px / 2.0 - 0.5
    cx = cols_px / 2.0 - 0.5

    palette = plt.get_cmap("plasma")(np.linspace(0.05, 0.9, len(rows)))

    # Figure 1 — ROI circles on the windowed mid slice (zoom + context).
    fig, (ax_zoom, ax_full) = plt.subplots(
        1, 2, figsize=(11.0, 5.6), dpi=150, width_ratios=[1.35, 1.0]
    )
    crop = int(np.ceil(max(spacing_xy) * (REFERENCE_RADIUS_MM + 8.0) / spacing_xy[0]))
    lo_r = max(0, int(cy - crop))
    hi_r = min(rows_px, int(cy + crop))
    lo_c = max(0, int(cx - crop))
    hi_c = min(cols_px, int(cx + crop))
    ax_zoom.imshow(
        display[lo_r:hi_r, lo_c:hi_c], cmap="gray", vmin=0, vmax=1,
        extent=(lo_c, hi_c, hi_r, lo_r),
    )
    for row, color in zip(rows, palette):
        ry = row["radius_mm"] / spacing_xy[1]
        ax_zoom.add_patch(
            Circle((cx, cy), ry, fill=False, edgecolor=color, lw=1.1)
        )
    ax_zoom.set_title(
        f"Mid axial slice (#{mid_index}), window {center}/{window} HU\n"
        f"centered ROIs {RADIUS_MM_LIST[0]:.0f}-"
        f"{RADIUS_MM_LIST[-1]:.0f} mm (zoomed crop)"
    )
    ax_zoom.axis("off")
    ax_full.imshow(display, cmap="gray", vmin=0, vmax=1)
    for row, color in zip(rows, palette):
        ry = row["radius_mm"] / spacing_xy[1]
        ax_full.add_patch(
            Circle((cx, cy), ry, fill=False, edgecolor=color, lw=0.9)
        )
    ax_full.set_title("Full 512x512 slice with ROI positions")
    ax_full.axis("off")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_roi_overlay.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 2 — HU mean / noise vs radius.
    radii = [r["radius_mm"] for r in rows]
    means = [r["hu_mean"] for r in rows]
    stds = [r["hu_std"] for r in rows]
    snrs = [r["snr_water_ref"] for r in rows]
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.6), dpi=150)
    axes[0].errorbar(
        radii, means, yerr=stds, marker="o", color="#2563eb",
        ecolor="#93b4f5", capsize=3,
    )
    axes[0].set_title("ROI mean HU (± 1 std)")
    axes[1].plot(radii, stds, marker="s", color="#b45309")
    axes[1].set_title("ROI noise proxy (std, HU)")
    axes[2].plot(radii, snrs, marker="^", color="#15803d")
    axes[2].set_title("ROI |mean|/std (water-ref SNR proxy)")
    for item in axes:
        item.set_xlabel("ROI radius (mm)")
        item.grid(alpha=0.3)
    axes[0].set_ylabel("HU")
    fig.suptitle(
        "HEEH-V1 CTCalculator on the mid axial slice vs ROI radius"
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_hu_stats_vs_radius.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 3 — first-order stability: relative deviation vs 36 mm reference.
    # Relative deviation puts every feature on an identical 0-1 scale, so no
    # single feature's magnitude (e.g. energy, ~1e7 HU^2) hides the others.
    selected = ["mean", "std", "skewness", "kurtosis", "entropy", "energy"]
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=150)
    for key, color in zip(selected, palette[: len(selected)]):
        deviations = [
            first_order_stability[key]["relative_deviation_vs_36mm"][r]
            for r in radii
        ]
        ax.plot(radii, deviations, marker="o", label=key, color=color)
    ax.set_xlabel("ROI radius (mm)")
    ax.set_ylabel("relative deviation from the 36-mm ROI value")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title(
        "First-order feature drift as ROI shrinks (mid slice).\n"
        "CV across radii: "
        + ", ".join(
            f"{k} {first_order_stability[k]['cv_across_radii']:.2f}"
            for k in selected
        )
    )
    ax.legend(title="feature", fontsize=9)
    ax.grid(alpha=0.3, which="both")
    ax.set_xticks(radii)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_firstorder_stability.png", bbox_inches="tight")
    plt.close(fig)

    # Figure 4 — ROI intensity histograms at several radii.
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=150)
    edges = np.arange(
        np.floor(min(r["hu_mean"] - 4 * r["hu_std"] for r in rows)),
        np.ceil(max(r["hu_mean"] + 4 * r["hu_std"] for r in rows)) + BIN_WIDTH_HU,
        BIN_WIDTH_HU,
    )
    subset_radii = sorted(
        set([RADIUS_MM_LIST[0], RADIUS_MM_LIST[1], RADIUS_MM_LIST[3], REFERENCE_RADIUS_MM])
    )
    for radius, color in zip(subset_radii, palette[: len(subset_radii)]):
        roi_voxels = slice_2d[
            prior_study.centered_roi_mask(
                (volume.shape[1], volume.shape[2]), spacing_xy, radius_mm=radius
            )[0]
        ].astype(np.float64)
        ax.hist(
            roi_voxels, bins=edges, histtype="step", lw=1.6, color=color,
            label=f"r = {radius:.0f} mm",
        )
    ax.set_xlabel("HU")
    ax.set_ylabel("voxels")
    ax.set_title(
        f"ROI intensity histograms, {BIN_WIDTH_HU:.0f} HU bins "
        "(mid axial slice)"
    )
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_roi_histograms.png", bbox_inches="tight")
    plt.close(fig)

    print("[figures] " + ", ".join(sorted(p.name for p in FIG_DIR.glob("*.png"))))


if __name__ == "__main__":
    main()
