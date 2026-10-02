import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from scripts.ibsi_reference_verification import (
    _compare_reference_rows,
    _compare_statistics,
    _compare_zrad_rows,
    run,
)
from scripts.ibsi_app_alignment import inspect_app_radiomics
from core.ibsi_radiomics import run_configuration_d
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
    pytest.importorskip("radiomics")
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
    pytest.importorskip("radiomics")
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

    assert comparison["compared"] == 66
    assert comparison["passed"] == 66
    assert comparison["failed"] == 0
    assert comparison["unsupported"] == 204
    assert all(
        "No defensible" in row["unsupported_reason"]
        for row in comparison["comparisons"]
        if row["expected"] is not None and row["actual"] is None
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
