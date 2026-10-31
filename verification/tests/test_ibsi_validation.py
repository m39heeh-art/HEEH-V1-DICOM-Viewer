import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from scripts.ibsi_reference_verification import (
    _compare_configuration_rows,
    _compare_reference_rows,
    _compare_statistics,
    _compare_zrad_rows,
    run,
)
from scripts.ibsi_app_alignment import inspect_app_radiomics
from core.ibsi_radiomics import (
    IBSI1_FEATURE_FAMILY_COUNTS,
    run_configuration_a,
    run_configuration_b,
    run_configuration_c,
    run_configuration_d,
    run_configuration_e,
)
from core.tissue_classifier import RadiomicsExtractor
from scripts.ibsi_reference_verification import (
    _load_reference_table,
    _zrad_diagnostics,
)


def test_statistics_comparison_includes_robust_and_scale_metrics():
    rows = [
        {"tag": tag, "feature": tag, "reference value": "1", "tolerance": "0"}
        for tag in (
            "stat_p10",
            "stat_p90",
            "stat_mad",
            "stat_rmad",
            "stat_medad",
            "stat_cov",
            "stat_qcod",
            "stat_energy",
            "stat_rms",
        )
    ]
    features = {
        "original_firstorder_10Percentile": 1.0,
        "original_firstorder_90Percentile": 1.0,
        "original_firstorder_MeanAbsoluteDeviation": 1.0,
        "original_firstorder_RobustMeanAbsoluteDeviation": 1.0,
        "stat_medad": 1.0,
        "stat_cov": 1.0,
        "stat_qcod": 1.0,
        "original_firstorder_Energy": 1.0,
        "original_firstorder_RootMeanSquared": 1.0,
    }

    comparison = _compare_statistics({"_rows": rows}, features)

    assert comparison["compared"] == len(rows)
    assert comparison["passed"] == len(rows)
    assert comparison["unsupported"] == 0


def test_ibsi1_feature_inventory_covers_all_reference_manual_families():
    assert sum(IBSI1_FEATURE_FAMILY_COUNTS.values()) == 172
    assert set(IBSI1_FEATURE_FAMILY_COUNTS) == {
        "morphology",
        "local_intensity",
        "intensity_statistics",
        "intensity_histogram",
        "ivh",
        "glcm",
        "glrlm",
        "glszm",
        "gldzm",
        "ngtdm",
        "ngldm",
    }


def test_statistics_kurtosis_conversion_only_applies_to_pyradiomics_fallback():
    reference_table = {
        "_rows": [
            {
                "tag": "stat_kurt",
                "feature": "(Excess) kurtosis",
                "reference value": "4.35",
                "tolerance": "0.32",
            }
        ]
    }

    direct = _compare_statistics(reference_table, {"stat_kurt": 4.35})
    pyradiomics = _compare_statistics(
        reference_table, {"original_firstorder_Kurtosis": 7.35}
    )

    assert direct["passed"] == 1
    assert direct["comparisons"][0]["actual"] == 4.35
    assert pyradiomics["passed"] == 1
    assert pyradiomics["comparisons"][0]["actual"] == 4.35


def test_zero_tolerance_uses_reference_display_precision():
    reference_table = {
        "_rows": [
            {
                "tag": "integer_value",
                "family": "Diagnostics",
                "feature": "Rounded integer",
                "reference value": "18",
                "tolerance": "0",
            },
            {
                "tag": "decimal_value",
                "family": "Diagnostics",
                "feature": "Rounded decimal",
                "reference value": "18.5",
                "tolerance": "0",
            },
        ]
    }

    comparison = _compare_zrad_rows(
        reference_table,
        {"integer_value": 18.49, "decimal_value": 18.54},
    )

    assert comparison["passed"] == 2
    assert [row["effective_tolerance"] for row in comparison["comparisons"]] == [
        0.5,
        0.05,
    ]


def test_ibsi_reference_extraction_rejects_conflicting_discretization():
    with pytest.raises(ValueError, match="choose either"):
        RadiomicsExtractor.ibsi_reference_features(
            "unused-image.nii.gz",
            "unused-mask.nii.gz",
            bin_width=25.0,
            bin_count=32,
        )


def test_ibsi_reference_resegmentation_without_resampling_uses_source_spacing(
    tmp_path: Path,
):
    try:
        import radiomics  # noqa: F401
    except ImportError as exc:
        # PyRadiomics' compiled C extensions can be blocked by OS policy
        # (e.g. Windows Application Control); skip instead of failing when
        # the reference implementation cannot be loaded on this machine.
        pytest.skip(f"pyradiomics unavailable: {exc}")
    import SimpleITK as sitk

    image_path = tmp_path / "image.nii.gz"
    mask_path = tmp_path / "mask.nii.gz"
    image = sitk.GetImageFromArray(
        np.arange(64, dtype=np.float32).reshape(4, 4, 4)
    )
    image.SetSpacing((0.7, 0.8, 1.2))
    mask = sitk.GetImageFromArray(np.ones((4, 4, 4), dtype=np.uint8))
    mask.CopyInformation(image)
    sitk.WriteImage(image, str(image_path))
    sitk.WriteImage(mask, str(mask_path))

    result = RadiomicsExtractor.ibsi_reference_features(
        str(image_path),
        str(mask_path),
        resegment_range=(8.0, 55.0),
        feature_classes=("firstorder",),
    )

    np.testing.assert_allclose(
        result["configuration"]["spacing"], [0.7, 0.8, 1.2], rtol=1e-6
    )
    assert result["features"]


@pytest.mark.parametrize(
    "resampled_pixel_spacing",
    [None, (1.0, 1.0, 1.0)],
)
def test_intensity_resegmentation_preserves_original_shape_mask(
    tmp_path: Path,
    resampled_pixel_spacing: tuple[float, float, float] | None,
):
    pytest.importorskip("radiomics", exc_type=ImportError)
    import SimpleITK as sitk

    image_path = tmp_path / "image.nii.gz"
    mask_path = tmp_path / "mask.nii.gz"
    image_values = np.zeros((7, 7, 7), dtype=np.float32)
    image_values[3, 3, 3] = 100.0
    mask_values = np.zeros((7, 7, 7), dtype=np.uint8)
    mask_values[1:6, 1:6, 1:6] = 1

    image = sitk.GetImageFromArray(image_values)
    mask = sitk.GetImageFromArray(mask_values)
    mask.CopyInformation(image)
    sitk.WriteImage(image, str(image_path))
    sitk.WriteImage(mask, str(mask_path))

    result = RadiomicsExtractor.ibsi_reference_features(
        str(image_path),
        str(mask_path),
        resegment_outlier_sigma=1.0,
        resampled_pixel_spacing=resampled_pixel_spacing,
        feature_classes=("firstorder", "shape"),
    )

    features = result["features"]
    assert features["original_firstorder_Mean"] == 0.0
    assert features["original_shape_VoxelVolume"] == 125.0
    assert result["configuration"]["resegment_shape"] is False
    assert result["configuration"]["resegment_range"] is not None


def test_application_radiomics_is_reported_as_not_configuration_d_comparable(
    tmp_path: Path,
):
    image_path = tmp_path / "phantom.nii.gz"
    data = np.arange(8 * 8 * 2, dtype=np.float32).reshape(8, 8, 2)
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(image_path))
    rows = [
        {
            "tag": "stat_mean",
            "family": "Statistics",
            "feature": "Mean",
            "reference value": "30",
        }
    ]

    result = inspect_app_radiomics(image_path, rows)

    assert result["status"] == "not_configuration_d_compliant"
    assert result["application_processing"]["radiomics_input_dimensions"] == 2
    assert result["application_processing"]["segmentation_mask_passed"] is False
    assert result["reference_observations"]["status"] == "not_comparable"
    assert result["reference_observations"]["compared_as_pass_fail"] == 0
    assert result["reference_observations"]["observed_deltas"][0]["status"] == (
        "not_comparable"
    )


def test_dicom_rtstruct_requires_an_explicit_roi_name(tmp_path: Path):
    image_path = tmp_path / "image.nii.gz"
    image = np.arange(12 * 12 * 12, dtype=np.float32).reshape(12, 12, 12)
    nib.save(nib.Nifti1Image(image, np.eye(4)), str(image_path))

    with pytest.raises(ValueError, match="ROI name"):
        run_configuration_d(image_path, tmp_path / "mask.dcm")


def test_application_configuration_d_pipeline_matches_official_phantom():
    verification_root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "ibsi_reference_data"
    )
    phantom_root = verification_root / "ibsi_1_ct_radiomics_phantom"
    image_path = phantom_root / "nifti" / "image" / "phantom.nii.gz"
    mask_path = phantom_root / "nifti" / "mask" / "mask.nii.gz"
    reference_path = (
        verification_root
        / "ibsi_1_reference_values"
        / "ibsi_1_reference_values_config_D.csv"
    )
    if not all(path.is_file() for path in (image_path, mask_path, reference_path)):
        pytest.skip("Optional licensed IBSI phantom/reference data are not installed")
    pytest.importorskip("zrad", reason="Optional Z-Rad reference engine is not installed")
    reference_table = _load_reference_table(phantom_root)

    result = run_configuration_d(image_path, mask_path)
    measured_features = result["features"]
    measured_features.update(_zrad_diagnostics(image_path, mask_path))
    comparison = _compare_zrad_rows(reference_table, measured_features)

    assert result["status"] == "configuration_d_pipeline_applied"
    assert result["configuration"]["texture_and_histogram_discretization"][
        "number_of_bins"
    ] == 32
    provenance = result["provenance"]
    assert provenance["schema"] == "heeh-v1.analysis-provenance"
    assert provenance["schema_version"] == 1
    assert provenance["inputs"]["image"]["sha256"] == (
        "909129fdf99d5f5fd17bc568b1834d31edce8663ea6746c6020720bfc1d7bbcb"
    )
    assert provenance["inputs"]["mask"]["sha256"] == (
        "0e9243e473b1255c60e6460df465d0b07b65436d6e0c691fe3d17bca0594ae78"
    )
    assert provenance["inputs"]["paths_recorded"] is False
    assert len(provenance["analysis_result_sha256"]) == 64
    assert provenance["software"]["dependency_lock_sha256"]
    assert provenance["environment"]["packages"]["z-rad"] == "26.9.0"
    assert str(image_path) not in json.dumps(provenance)
    assert str(mask_path) not in json.dumps(provenance)
    assert result["analysis"]["resampled_image_dimensions_xyz"] == [
        100,
        99,
        90,
    ]
    assert comparison["compared"] == 270
    assert comparison["passed"] == 270
    assert comparison["failed"] == 0
    assert comparison["unsupported"] == 0


def test_pyradiomics_morphology_matches_ibsi_reference_mask():
    pytest.importorskip("radiomics", exc_type=ImportError)
    import SimpleITK as sitk

    verification_root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "ibsi_reference_data"
    )
    phantom_root = verification_root / "ibsi_1_ct_radiomics_phantom"
    image_path = phantom_root / "nifti" / "image" / "phantom.nii.gz"
    mask_path = phantom_root / "nifti" / "mask" / "mask.nii.gz"
    reference_path = (
        verification_root
        / "ibsi_1_reference_values"
        / "ibsi_1_reference_values_config_D.csv"
    )
    if not all(path.is_file() for path in (image_path, mask_path, reference_path)):
        pytest.skip("Optional licensed IBSI phantom/reference data are not installed")

    reference_table = _load_reference_table(phantom_root)
    result = RadiomicsExtractor.ibsi_reference_features(
        str(image_path),
        str(mask_path),
        bin_count=32,
        round_resampled_intensities=True,
        resampled_pixel_spacing=(2.0, 2.0, 2.0),
        resegment_outlier_sigma=3.0,
        interpolator=sitk.sitkLinear,
        feature_classes=(
            "firstorder",
            "glcm",
            "glrlm",
            "glszm",
            "gldm",
            "ngtdm",
            "shape",
        ),
    )
    comparison = _compare_reference_rows(reference_table, result["features"])

    assert comparison["compared"] == 75
    assert comparison["passed"] == 75
    assert comparison["failed"] == 0
    assert comparison["unsupported"] == 195
    assert all(
        row["assessment_status"] == "not_assessed"
        and row["unsupported_reason_category"]
        for row in comparison["comparisons"]
        if row["expected"] is not None and row["actual"] is None
    )
    assert comparison["unsupported_by_category"]["aggregation_semantics_not_comparable"] > 0
    assert comparison["unsupported_by_category"]["pipeline_stage_diagnostic"] == 60
    assert sum(comparison["unsupported_by_category"].values()) == 195


def test_pyradiomics_comparison_maps_supported_gldm_definitions():
    rows = [
        {
            "tag": "ngl_lde_3D",
            "family": "Neighbouring grey level dependence matrix (3D)",
            "feature": "Low dependence emphasis",
            "reference value": "0.5",
            "tolerance": "0.01",
        },
        {
            "tag": "ngl_dc_energy_3D",
            "family": "Neighbouring grey level dependence matrix (3D)",
            "feature": "Dependence count energy",
            "reference value": "0.25",
            "tolerance": "0.01",
        },
    ]

    comparison = _compare_reference_rows(
        {"_rows": rows},
        {"original_gldm_SmallDependenceEmphasis": 0.5},
    )

    assert comparison["compared"] == 1
    assert comparison["passed"] == 1
    assert comparison["unsupported"] == 1
    assert comparison["comparisons"][0]["assessment_status"] == "passed"
    assert comparison["comparisons"][1]["assessment_status"] == "not_assessed"
    assert comparison["comparisons"][1]["unsupported_reason_category"] == (
        "no_unambiguous_feature_mapping"
    )


def test_source_file_set_fingerprint_omits_paths_and_unrelated_files(tmp_path: Path):
    from core.ibsi_radiomics import _input_fingerprint

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    first = source_dir / "slice-one.dcm"
    second = source_dir / "slice-two.dcm"
    unrelated = source_dir / "unrelated.txt"
    first.write_bytes(b"slice-one")
    second.write_bytes(b"slice-two")
    unrelated.write_bytes(b"not part of the loaded series")

    selected = _input_fingerprint(
        source_dir,
        source_files=[first, second],
    )
    changed_unrelated = _input_fingerprint(
        source_dir,
        source_files=[first, second],
    )

    assert selected == changed_unrelated
    assert selected["kind"] == "source_file_set"
    assert selected["files_hashed"] == 2
    assert str(source_dir) not in json.dumps(selected)


def test_ibsi_reference_verification_reports_missing_reference_blocker(tmp_path: Path):
    missing_root = tmp_path / "missing_ibsi_data"
    output = tmp_path / "ibsi_verification.json"

    payload = run(missing_root, output)

    assert payload["status"] == "blocked"
    assert payload["blocker"]["type"] == "missing_reference_dataset"
    assert payload["feature_coverage"]["glrlm"]["status"] == "supported"
    assert output.exists()


def test_configuration_e_reference_verification_reports_missing_reference(tmp_path: Path):
    from scripts.ibsi_reference_verification import _configuration_verification

    result = _configuration_verification(
        tmp_path / "phantom.nii.gz",
        tmp_path / "mask.nii.gz",
        tmp_path / "ibsi_data",
    )

    assert result["E"]["status"] == "blocked"
    assert result["E"]["blocker"] == "official_reference_values_missing"


def test_configuration_e_matches_official_phantom_reference():
    if not _zrad_usable():
        pytest.skip("Z-Rad or a required DLL is unavailable on this machine")
    verification_root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "ibsi_reference_data"
    )
    phantom_root = verification_root / "ibsi_1_ct_radiomics_phantom"
    phantom = phantom_root / "nifti"
    image_path = phantom / "image" / "phantom.nii.gz"
    mask_path = phantom / "mask" / "mask.nii.gz"
    reference_path = (
        verification_root
        / "ibsi_1_reference_values"
        / "ibsi_1_reference_values_config_E.csv"
    )
    if not all(path.is_file() for path in (image_path, mask_path, reference_path)):
        pytest.skip("Optional licensed IBSI phantom/reference data are not installed")

    reference_table = _load_reference_table(phantom_root, "E")
    result = run_configuration_e(image_path, mask_path)
    comparison = _compare_configuration_rows(
        reference_table, result["features"]
    )

    assert comparison["rows_with_reference"] == 270
    assert comparison["compared"] == 210
    assert comparison["passed"] == 210
    assert comparison["failed"] == 0
    assert comparison["unsupported"] == 0
    assert comparison["skipped_diagnostics"] == 60


def test_ibsi_digital_phantom_records_every_reference_and_open_mismatch(
    tmp_path: Path,
):
    from scripts.ibsi_digital_phantom_verification import run as run_digital

    try:
        import radiomics  # noqa: F401
    except (ImportError, OSError) as exc:
        pytest.skip(f"PyRadiomics unavailable: {exc}")
    data_root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "ibsi_reference_data"
    )
    phantom_root = data_root / "ibsi_1_digital_phantom"
    reference_path = (
        data_root
        / "ibsi_1_reference_values"
        / "ibsi_1_digital_phantom_reference_values.csv"
    )
    if not all(
        path.is_file()
        for path in (
            phantom_root / "nifti" / "image" / "phantom.nii.gz",
            phantom_root / "nifti" / "mask" / "mask.nii.gz",
            reference_path,
        )
    ):
        pytest.skip("Optional licensed IBSI digital phantom/reference data are not installed")
    if not _zrad_usable():
        pytest.skip("Z-Rad or a required DLL is unavailable on this machine")

    output = tmp_path / "digital_phantom_verification.json"
    result = run_digital(data_root, output)
    comparison = result["comparison"]

    assert result["status"] == "reference_mismatch"
    assert result["reference_table"]["rows"] == 487
    assert result["reference_table"]["rows_with_reference"] == 482
    assert len(result["source"]["reference_csv_sha256"]) == 64
    assert comparison["rows_with_reference"] == 482
    assert comparison["compared"] == 482
    assert comparison["passed"] == 481
    assert comparison["failed"] == 1
    assert comparison["unsupported"] == 0
    assert result["mismatches"][0]["tag"] == "szm_lzhge_3D"
    assert result["mismatches"][0]["expected"] == 1490.0
    assert result["mismatches"][0]["actual"] == pytest.approx(1494.6)
    assert result["independent_check"]["status"] == (
        "corroborates_zrad_mismatch"
    )
    assert result["independent_check"]["matches_zrad"] is True
    assert result["independent_check"]["within_official_tolerance"] is False
    matrix_check = result["official_matrix_check"]
    assert matrix_check["status"] == (
        "matrix_matches_implementation_but_conflicts_with_feature_reference"
    )
    assert matrix_check["zone_count"] == 5
    assert matrix_check["voxel_count"] == 74
    assert matrix_check["matrix_feature_value"] == pytest.approx(1494.6)
    assert matrix_check["matches_implementation"] is True
    assert matrix_check["matches_feature_reference"] is False
    inventory = result["feature_inventory"]
    assert inventory["definitions"] == 172
    assert inventory["implemented_definitions"] == 167
    assert inventory["reference_supported_definitions"] == 167
    assert inventory["implemented_reference_supported_definitions"] == 167
    assert inventory["unimplemented_recommended_definitions"] == 0
    assert inventory["definitions_with_reference_values"] == 167
    assert inventory["definitions_without_reference_values"] == 5
    assert inventory["not_recommended_definitions"] == 5
    assert inventory["permanent_ids_published"] == 171
    assert inventory["permanent_id_source"].endswith("03_Image_features.html")
    assert inventory["definitions_without_permanent_id"] == ["szm_sze"]
    assert inventory["permanent_id_collisions"] == {
        "1PR8": ["ih_min", "ih_p10"]
    }
    assert len(inventory["items"]) == 174
    assert inventory["derived_outputs_not_in_172_definition_inventory"] == [
        "ivh_diff_i10_i90",
        "ivh_diff_v10_v90",
    ]
    assert {
        item["feature_tag"]
        for item in inventory["items"]
        if item["inventory_definition"]
        and item["recommendation_status"]
        == "not_recommended_no_reference_value"
    } == {
        "morph_vol_dens_ombb",
        "morph_area_dens_ombb",
        "morph_vol_dens_mvee",
        "morph_area_dens_mvee",
        "ivh_auc",
    }
    permanent_ids = {
        item["feature_tag"]: item["ibsi_permanent_id"]
        for item in inventory["items"]
        if item["inventory_definition"]
    }
    assert permanent_ids["szm_sze"] is None
    assert permanent_ids["stat_mean"] == "Q4LE"
    assert permanent_ids["cm_contrast"] == "ACUI"
    assert permanent_ids["ih_min"] == permanent_ids["ih_p10"] == "1PR8"
    assert permanent_ids["morph_vol_dens_ombb"] == "ZH1A"
    assert permanent_ids["morph_area_dens_ombb"] == "IQYR"
    assert permanent_ids["morph_vol_dens_mvee"] == "SWZ1"
    assert permanent_ids["morph_area_dens_mvee"] == "BRI8"
    assert permanent_ids["ivh_auc"] == "9CMM"
    permanent_id_statuses = {
        item["feature_tag"]: item["permanent_id_status"]
        for item in inventory["items"]
        if item["inventory_definition"]
    }
    assert permanent_id_statuses["szm_sze"] == "not_listed_in_official_manual"
    assert permanent_id_statuses["ih_min"] == "published_identifier_collision"
    assert permanent_id_statuses["ih_p10"] == "published_identifier_collision"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == (
        "reference_mismatch"
    )

# ---------------------------------------------------------------------------
# IBSI 1 Configuration A — unit / smoke tests (no phantom data required)
# ---------------------------------------------------------------------------

def _zrad_usable() -> bool:
    """Return True only when Z-Rad and its DLL dependencies can be loaded."""
    try:
        import zrad  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def test_configuration_a_status_and_schema_fields(tmp_path: Path):
    """Configuration A returns the expected status and schema fields."""
    if not _zrad_usable():
        pytest.skip("Z-Rad or a required DLL is unavailable on this machine")
    import SimpleITK as sitk

    image_path = tmp_path / "image.nii.gz"
    mask_path = tmp_path / "mask.nii.gz"
    image = sitk.GetImageFromArray(np.arange(64, dtype=np.float32).reshape(4, 4, 4))
    image.SetSpacing((1.0, 1.0, 1.0))
    mask = sitk.GetImageFromArray(np.ones((4, 4, 4), dtype=np.uint8))
    mask.CopyInformation(image)
    sitk.WriteImage(image, str(image_path))
    sitk.WriteImage(mask, str(mask_path))

    result = run_configuration_a(str(image_path), str(mask_path))

    assert result["status"] == "configuration_a_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "A"
    assert result["configuration"]["resampling_mm"] is None
    reseg = result["configuration"]["resegmentation"]
    assert reseg["method"] == "fixed_range"
    assert reseg["range_lower_hu"] == -500.0
    assert reseg["range_upper_hu"] == 400.0
    assert result["analysis"]["roi_voxels"] == 64
    provenance = result["provenance"]
    assert provenance["schema"] == "heeh-v1.analysis-provenance"
    assert provenance["inputs"]["paths_recorded"] is False


def test_configuration_a_dicom_rtstruct_requires_roi_name(tmp_path: Path):
    """Configuration A raises an error for a DICOM mask without an ROI name."""
    # This test exercises pure Python validation — no Z-Rad or DLL needed.
    image_path = tmp_path / "image.nii.gz"
    image = np.arange(12 * 12 * 12, dtype=np.float32).reshape(12, 12, 12)
    nib.save(nib.Nifti1Image(image, np.eye(4)), str(image_path))

    with pytest.raises(ValueError, match="ROI name"):
        run_configuration_a(image_path, tmp_path / "mask.dcm")


# ---------------------------------------------------------------------------
# IBSI 1 Configuration B — unit / smoke tests (no phantom data required)
# ---------------------------------------------------------------------------

def test_configuration_b_status_and_schema_fields(tmp_path: Path):
    """Configuration B returns the expected status and resampling fields."""
    if not _zrad_usable():
        pytest.skip("Z-Rad or a required DLL is unavailable on this machine")
    import SimpleITK as sitk

    image_path = tmp_path / "image.nii.gz"
    mask_path = tmp_path / "mask.nii.gz"
    image = sitk.GetImageFromArray(
        np.arange(8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8)
    )
    image.SetSpacing((1.0, 1.0, 1.0))
    mask = sitk.GetImageFromArray(np.ones((8, 8, 8), dtype=np.uint8))
    mask.CopyInformation(image)
    sitk.WriteImage(image, str(image_path))
    sitk.WriteImage(mask, str(mask_path))

    result = run_configuration_b(str(image_path), str(mask_path))

    assert result["status"] == "configuration_b_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "B"
    # Official Configuration B resamples in-plane only; the axial slice
    # spacing (1.0 mm in this synthetic image) is preserved.
    assert result["configuration"]["resampling_mm"] == [2.0, 2.0, 1.0]
    reseg = result["configuration"]["resegmentation"]
    assert reseg["method"] == "fixed_range"
    assert reseg["range_lower_hu"] == -500.0
    assert reseg["range_upper_hu"] == 400.0
    assert result["configuration"]["image_interpolation"] == "linear"
    assert result["analysis"]["resampled_roi_voxels"] > 0
    provenance = result["provenance"]
    assert provenance["schema"] == "heeh-v1.analysis-provenance"
    assert provenance["inputs"]["paths_recorded"] is False


def test_configuration_b_dicom_rtstruct_requires_roi_name(tmp_path: Path):
    """Configuration B raises an error for a DICOM mask without an ROI name."""
    # This test exercises pure Python validation — no Z-Rad or DLL needed.
    image_path = tmp_path / "image.nii.gz"
    image = np.arange(12 * 12 * 12, dtype=np.float32).reshape(12, 12, 12)
    nib.save(nib.Nifti1Image(image, np.eye(4)), str(image_path))

    with pytest.raises(ValueError, match="ROI name"):
        run_configuration_b(image_path, tmp_path / "mask.dcm")


# ---------------------------------------------------------------------------
# IBSI 1 Configuration C — unit / smoke tests (no phantom data required)
# ---------------------------------------------------------------------------

def test_configuration_c_status_and_resegmentation_fields(tmp_path: Path):
    """Configuration C returns fixed-range resegmentation metadata."""
    if not _zrad_usable():
        pytest.skip("Z-Rad or a required DLL is unavailable on this machine")
    import SimpleITK as sitk

    image_path = tmp_path / "image.nii.gz"
    mask_path = tmp_path / "mask.nii.gz"
    # Intensities range 0..63; a range of [0, 63] keeps all voxels.
    image = sitk.GetImageFromArray(
        np.arange(8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8)
    )
    image.SetSpacing((1.0, 1.0, 1.0))
    mask = sitk.GetImageFromArray(np.ones((8, 8, 8), dtype=np.uint8))
    mask.CopyInformation(image)
    sitk.WriteImage(image, str(image_path))
    sitk.WriteImage(mask, str(mask_path))

    result = run_configuration_c(
        str(image_path), str(mask_path), range_lower=0.0, range_upper=100.0
    )

    assert result["status"] == "configuration_c_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "C"
    assert result["configuration"]["resampling_mm"] == [2.0, 2.0, 2.0]
    reseg = result["configuration"]["resegmentation"]
    assert reseg["method"] == "fixed_range"
    assert reseg["range_lower_hu"] == 0.0
    assert reseg["range_upper_hu"] == 100.0
    assert result["configuration"]["reference_configuration"] is False
    assert result["analysis"]["resampled_roi_voxels"] > 0
    provenance = result["provenance"]
    assert provenance["schema"] == "heeh-v1.analysis-provenance"
    assert provenance["inputs"]["paths_recorded"] is False


def test_configuration_c_rejects_invalid_range():
    """Configuration C raises ValueError for invalid intensity ranges."""
    with pytest.raises(ValueError, match="range_lower"):
        run_configuration_c(
            "unused.nii.gz", "unused.nii.gz", range_lower=500.0, range_upper=100.0
        )

    with pytest.raises(ValueError, match="finite"):
        run_configuration_c(
            "unused.nii.gz", "unused.nii.gz", range_lower=float("nan"), range_upper=100.0
        )


def test_configuration_c_dicom_rtstruct_requires_roi_name(tmp_path: Path):
    """Configuration C raises an error for a DICOM mask without an ROI name."""
    # This test exercises pure Python validation — no Z-Rad or DLL needed.
    image_path = tmp_path / "image.nii.gz"
    image = np.arange(12 * 12 * 12, dtype=np.float32).reshape(12, 12, 12)
    nib.save(nib.Nifti1Image(image, np.eye(4)), str(image_path))

    with pytest.raises(ValueError, match="ROI name"):
        run_configuration_c(image_path, tmp_path / "mask.dcm")


def test_configuration_e_status_and_official_processing_parameters(
    tmp_path: Path,
):
    if not _zrad_usable():
        pytest.skip("Z-Rad or a required DLL is unavailable on this machine")
    import SimpleITK as sitk

    image_path = tmp_path / "image.nii.gz"
    mask_path = tmp_path / "mask.nii.gz"
    image = sitk.GetImageFromArray(
        np.arange(8 * 8 * 8, dtype=np.float32).reshape(8, 8, 8)
    )
    image.SetSpacing((1.0, 1.0, 1.0))
    mask = sitk.GetImageFromArray(np.ones((8, 8, 8), dtype=np.uint8))
    mask.CopyInformation(image)
    sitk.WriteImage(image, str(image_path))
    sitk.WriteImage(mask, str(mask_path))

    result = run_configuration_e(image_path, mask_path)

    assert result["status"] == "configuration_e_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "E"
    assert result["configuration"]["resampling_mm"] == [2.0, 2.0, 2.0]
    assert "tricubic spline" in result["configuration"]["image_interpolation"]
    assert result["configuration"]["resegmentation"] == {
        "method": "fixed_range_and_outlier",
        "range_lower_hu": -1000.0,
        "range_upper_hu": 400.0,
        "outlier_sigma": 3.0,
    }
    assert result["configuration"]["texture_and_histogram_discretization"][
        "number_of_bins"
    ] == 32
    assert result["configuration"]["ivh_discretization"] == {
        "method": "fixed bin number",
        "number_of_bins": 1000,
    }
    assert result["analysis"]["resampled_roi_voxels"] > 0
    assert set(result["feature_family_coverage"]) == set(
        IBSI1_FEATURE_FAMILY_COUNTS
    )
    assert sum(
        family["ibsi_feature_definitions"]
        for family in result["feature_family_coverage"].values()
    ) == 172
    assert all(
        family["status"] in {"computed", "unsupported", "missing"}
        and family["computed_output_values"] >= 0
        for family in result["feature_family_coverage"].values()
    )
    assert result["provenance"]["inputs"]["paths_recorded"] is False


def test_configuration_e_dicom_rtstruct_requires_roi_name(tmp_path: Path):
    image_path = tmp_path / "image.nii.gz"
    image = np.arange(12 * 12 * 12, dtype=np.float32).reshape(12, 12, 12)
    nib.save(nib.Nifti1Image(image, np.eye(4)), str(image_path))

    with pytest.raises(ValueError, match="ROI name"):
        run_configuration_e(image_path, tmp_path / "mask.dcm")


# ---------------------------------------------------------------------------
# IBSI 1 — Phantom cross-validation tests for A, B, C (skips if data absent)
# ---------------------------------------------------------------------------

def _get_phantom_paths():
    verification_root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "ibsi_reference_data"
    )
    phantom_root = verification_root / "ibsi_1_ct_radiomics_phantom"
    image_path = phantom_root / "nifti" / "image" / "phantom.nii.gz"
    mask_path = phantom_root / "nifti" / "mask" / "mask.nii.gz"
    return image_path, mask_path


def test_configuration_a_pipeline_runs_on_official_phantom():
    """Configuration A pipeline executes without error on the IBSI CT phantom."""
    image_path, mask_path = _get_phantom_paths()
    if not all(p.is_file() for p in (image_path, mask_path)):
        pytest.skip("Optional licensed IBSI phantom data are not installed")
    pytest.importorskip("zrad", reason="Optional Z-Rad engine is not installed")

    result = run_configuration_a(image_path, mask_path)

    assert result["status"] == "configuration_a_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "A"
    assert result["analysis"]["roi_voxels"] > 0
    assert result["features"]
    assert result["provenance"]["inputs"]["paths_recorded"] is False


def test_configuration_b_pipeline_runs_on_official_phantom():
    """Configuration B pipeline executes without error on the IBSI CT phantom."""
    image_path, mask_path = _get_phantom_paths()
    if not all(p.is_file() for p in (image_path, mask_path)):
        pytest.skip("Optional licensed IBSI phantom data are not installed")
    pytest.importorskip("zrad", reason="Optional Z-Rad engine is not installed")

    result = run_configuration_b(image_path, mask_path)

    assert result["status"] == "configuration_b_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "B"
    reseg = result["configuration"]["resegmentation"]
    assert reseg["method"] == "fixed_range"
    assert reseg["range_lower_hu"] == -500.0
    assert reseg["range_upper_hu"] == 400.0
    assert result["analysis"]["resampled_roi_voxels"] > 0
    assert result["features"]
    assert result["provenance"]["inputs"]["paths_recorded"] is False


def test_configuration_c_pipeline_runs_on_official_phantom():
    """Configuration C pipeline executes without error on the IBSI CT phantom."""
    image_path, mask_path = _get_phantom_paths()
    if not all(p.is_file() for p in (image_path, mask_path)):
        pytest.skip("Optional licensed IBSI phantom data are not installed")
    pytest.importorskip("zrad", reason="Optional Z-Rad engine is not installed")

    # IBSI 1 phantom HU range: typically -500..400 HU keeps the solid phantom.
    result = run_configuration_c(
        image_path, mask_path, range_lower=-500.0, range_upper=400.0
    )

    assert result["status"] == "configuration_c_pipeline_applied"
    assert result["configuration"]["ibsi_configuration"] == "C"
    reseg = result["configuration"]["resegmentation"]
    assert reseg["method"] == "fixed_range"
    assert result["analysis"]["resampled_roi_voxels"] > 0
    assert result["features"]
    assert result["provenance"]["inputs"]["paths_recorded"] is False
