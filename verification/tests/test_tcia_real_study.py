"""Regression guard for the real-data TCIA evaluation evidence.

Two layers:
  1. The recorded full-series study artifact must keep its headline results
     (agreement, calibration, export gate, morphology decomposition).
  2. A live single-slice recomputation must still reproduce exact agreement,
     so the pipeline cannot silently drift from the recorded evidence.

Both layers skip cleanly when optional dependencies or the (git-ignored)
downloaded series are absent, so CI without the data still passes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STUDY_JSON = REPO / "verification/results/tcia_full_series_study.json"
SINGLE_JSON = REPO / "verification/results/tcia_real_evaluation.json"
SERIES_ZIP = REPO / "verification/data/tcia_real_evaluation/series.zip"
DCM_DIR = REPO / "verification/data/tcia_real_evaluation/dcm"


def _require_study_artifact() -> dict:
    if not STUDY_JSON.is_file():
        pytest.skip("Full-series study artifact has not been generated")
    return json.loads(STUDY_JSON.read_text(encoding="utf-8"))


def test_single_slice_evaluation_headline_is_stable():
    if not SINGLE_JSON.is_file():
        pytest.skip("Single-slice evaluation artifact has not been generated")
    results = json.loads(SINGLE_JSON.read_text(encoding="utf-8"))
    assert results["series_provenance"]["series_instance_uid"] == (
        "1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879"
    )
    calibration = results["hu_calibration_probe"]
    assert calibration["air_within_30hu_of_reference"] is True
    assert calibration["air_abs_deviation_hu"] < 10.0
    comparison = results["real_roi_radiomics"]["pyradiomics_reference_comparison"]
    assert comparison["all_within_tolerance"] is True
    assert max(comparison["absolute_errors"].values()) <= 1e-6
    export = results["real_export_validation"]
    assert export["valid_archive_accepted"] is True
    assert export["tampered_manifest_rejected"] is True


def test_full_series_study_headlines_are_stable():
    study = _require_study_artifact()
    agreement = study["all_slices_firstorder_agreement"]
    assert agreement["n"] == 172
    assert agreement["within_tolerance"] == agreement["n"]
    assert agreement["max_absolute_error"] <= 1e-6

    air = study["air_calibration_all_slices"]
    assert air["all_within_tolerance"] is True
    assert air["max_deviation_hu"] <= 30.0

    export = study["export_privacy_all_slices"]
    assert export["accepted"] == export["n"]
    assert export["tamper_checks"] > 0
    assert export["tamper_rejected"] == export["tamper_checks"]

    sweep = study["radius_sensitivity_mid_slice"]
    assert len(sweep) == 5
    assert all(row["all_within_tolerance"] for row in sweep)

    morphology = study["morphology_root_cause"]
    decomposition = morphology["recorded_table_decomposition"]
    assert decomposition["compared"] == 66
    assert decomposition["passed"] == 66
    assert decomposition["failed"] == 0
    assert decomposition["not_assessed"] == 204
    assert decomposition["failed_rows"] == 0
    assert "shape features now use the original ROI mask" in morphology["finding"]


def test_live_pipeline_still_reproduces_exact_agreement():
    pytest.importorskip("SimpleITK")
    pytest.importorskip("radiomics")
    if not SERIES_ZIP.is_file() or not DCM_DIR.is_dir():
        pytest.skip("Downloaded real series is not present in this environment")

    import sys

    sys.path.insert(0, str(REPO))
    from scripts.tcia_full_series_study import firstorder_pair
    from scripts.tcia_real_evaluation import centered_roi_mask, load_series_hu

    volume, spacing, _files = load_series_hu()
    probe = volume.shape[0] // 4  # deterministic slice different from the study's mid focus
    mask, _info = centered_roi_mask(
        (volume.shape[1], volume.shape[2]),
        (spacing[0], spacing[1]),
        radius_mm=24.0,
    )
    _app, _pyr, errors = firstorder_pair(
        volume[probe], mask, (spacing[0], spacing[1])
    )
    assert max(errors.values()) <= 1e-6
