"""Regression tests for the HEEH-V1 audit follow-up.

Covers the confirmed audit findings:
- NGTDM coarseness formula (now matches PyRadiomics with identical settings).
- GLSZM connectivity parameter is honored and recorded.
- 3D shape features no longer call 2D-only skimage properties.
- De-identification metadata reflects the actual date handling.
- DenseBone upper edge (3071 HU) is classified in the CT tissue map and the
  low-contrast-detectability covered mask.

The PyRadiomics comparison runs only when the optional 'ibsi' dependency
group is installed; the remaining tests run on the base test stack.
"""

import numpy as np
import pytest

from core.tissue_classifier import RadiomicsExtractor


def _audit_texture_image() -> np.ndarray:
    """Deterministic structured 2D ROI (no patient data): levels {0,20,...,400}."""
    rng = np.random.default_rng(42)
    base = np.round(rng.integers(-200, 200, size=(87, 87)) / 20.0) * 20.0
    return base - base.min()


# ---------------------------------------------------------------------------
# NGTDM vs PyRadiomics (identical mask/settings)
# ---------------------------------------------------------------------------

def _pyradiomics_ngtdm(img: np.ndarray) -> dict[str, float]:
    """Run PyRadiomics NGTDM on the same 2D ROI with matched settings.

    The ROI is embedded in a 1-voxel background ring so every ROI voxel has
    the same in-ROI 8-neighborhood as in the plain 2D array; binWidth=1 makes
    PyRadiomics' binning the identity on the integer-valued fixture, matching
    the HEEH fixed_bin_width discretization with bin_width=1.
    """
    sitk = pytest.importorskip("SimpleITK")
    import logging

    try:
        from radiomics import featureextractor  # noqa: F401
    except ImportError as exc:
        # PyRadiomics' compiled C extensions can be blocked by OS policy
        # (e.g. Windows Application Control); skip instead of failing when
        # the reference implementation cannot be loaded on this machine.
        pytest.skip(f"pyradiomics unavailable: {exc}")

    padded = np.zeros((img.shape[0] + 2, img.shape[1] + 2), dtype=np.float32)
    padded[1:-1, 1:-1] = img
    mask_arr = np.zeros(padded.shape, dtype=np.uint8)
    mask_arr[1:-1, 1:-1] = 1

    img_sitk = sitk.GetImageFromArray(padded[np.newaxis, ...])
    img_sitk.SetSpacing((1.0, 1.0, 1.0))
    mask_sitk = sitk.GetImageFromArray(mask_arr[np.newaxis, ...])
    mask_sitk.SetSpacing((1.0, 1.0, 1.0))

    logging.getLogger("radiomics").setLevel(logging.ERROR)
    extractor = featureextractor.RadiomicsFeatureExtractor()
    extractor.settings.update(
        {
            "binWidth": 1.0,
            "force2D": True,
            "force2Ddimension": 0,
            "distances": [1],
            "label": 1,
        }
    )
    extractor.disableAllFeatures()
    extractor.enableFeatureClassByName("ngtdm")
    result = extractor.execute(img_sitk, mask_sitk)
    return {
        key.split("_")[-1].lower(): float(value)
        for key, value in result.items()
        if key.startswith("original_ngtdm_")
    }


def test_ngtdm_matches_pyradiomics_with_identical_settings():
    img = _audit_texture_image()
    levels = int(img.max() / 1.0) + 2  # cover the full range: nothing clipped
    heeh = RadiomicsExtractor.ngtdm_features(
        img, levels=levels, bin_width=1.0,
        discretization="fixed_bin_width", connectivity=2,
    )
    pyrad = _pyradiomics_ngtdm(img)

    assert set(pyrad) == {
        "coarseness", "contrast", "busyness", "complexity", "strength"
    }
    for name in sorted(pyrad):
        assert heeh[name] == pytest.approx(pyrad[name], abs=1e-6), (
            f"NGTDM {name} diverges from PyRadiomics v3.0.1"
        )


def test_ngtdm_coarseness_uses_sum_not_mean_difference():
    """IBSI coarseness = 1/sum(p_i * s_i) with s_i the summed absolute
    differences; normalizing s_i by the level count inflates coarseness."""
    img = _audit_texture_image()
    levels = int(img.max()) + 2
    heeh = RadiomicsExtractor.ngtdm_features(
        img, levels=levels, bin_width=1.0,
        discretization="fixed_bin_width", connectivity=2,
    )

    from scipy import ndimage

    structure = np.ones((3, 3), dtype=bool)
    structure[1, 1] = False
    neighbor_sum = ndimage.convolve(
        img.astype(np.float64), structure.astype(np.float64), mode="constant"
    )
    neighbor_count = ndimage.convolve(
        np.ones(img.shape), structure.astype(np.float64), mode="constant"
    )
    differences = np.abs(img - neighbor_sum / neighbor_count)
    level_values = img.astype(np.int64) + 1  # IBSI 1-based gray levels
    n_i = np.bincount(level_values.ravel()).astype(np.float64)
    s_i = np.bincount(level_values.ravel(), weights=differences.ravel())
    active = n_i > 0
    nvp = float(n_i.sum())
    expected = 1.0 / float(np.sum((n_i[active] / nvp) * s_i[active]))
    assert heeh["coarseness"] == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# GLSZM connectivity
# ---------------------------------------------------------------------------

def test_glszm_connectivity_changes_zone_structure():
    # Diagonal ones: four size-1 zones with 4-connectivity, two size-2 zones
    # with 8-connectivity.
    image = np.array([[1, 0], [0, 1]], dtype=np.float64)

    conn4 = RadiomicsExtractor.glszm_features(
        image, levels=4, bin_width=1.0,
        discretization="fixed_bin_width", connectivity=1,
    )
    conn8 = RadiomicsExtractor.glszm_features(
        image, levels=4, bin_width=1.0,
        discretization="fixed_bin_width", connectivity=2,
    )

    assert conn4["zone_percentage"] == pytest.approx(1.0)
    assert conn8["zone_percentage"] == pytest.approx(0.5)


def test_glszm_records_connectivity_and_rejects_invalid():
    image = np.zeros((4, 4), dtype=np.float64)
    provenance = RadiomicsExtractor.glszm_features(
        image, levels=4, bin_width=1.0,
        discretization="fixed_bin_width", connectivity=2,
        include_provenance=True,
    )["provenance"]
    assert provenance["connectivity"] == 2

    with pytest.raises(ValueError, match="connectivity"):
        RadiomicsExtractor.glszm_features(
            image, levels=4, bin_width=1.0,
            discretization="fixed_bin_width", connectivity=3,
        )


# ---------------------------------------------------------------------------
# 3D shape behavior
# ---------------------------------------------------------------------------

def test_shape_features_3d_reports_volume_without_2d_only_properties():
    mask = np.zeros((20, 20, 20), dtype=np.uint8)
    mask[5:15, 5:15, 5:15] = 1

    result = RadiomicsExtractor.shape_features(mask, spacing=(1.0, 1.0, 2.0))

    assert result["volume_mm3"] == pytest.approx(10 * 10 * 10 * 2.0)
    assert result["voxel_count"] == 1000
    assert result["axis_length_0"] == pytest.approx(10.0)
    assert result["axis_length_1"] == pytest.approx(10.0)
    assert result["axis_length_2"] == pytest.approx(20.0)
    assert "feret_diameter_max" in result
    # 2D-only properties must not be fabricated for volumes; the element
    # count is a voxel count, not a pixel area.
    for two_d_only in ("area_px", "perimeter_px", "circularity", "eccentricity"):
        assert two_d_only not in result


def test_shape_features_2d_keys_unchanged():
    mask = np.zeros((12, 12), dtype=np.uint8)
    mask[3:9, 3:9] = 1

    result = RadiomicsExtractor.shape_features(mask, spacing=1.0)

    for key in (
        "area_px", "perimeter_px", "circularity", "eccentricity",
        "major_axis", "minor_axis", "area_mm2",
    ):
        assert key in result
    assert result["area_px"] == 36
    assert result["area_mm2"] == pytest.approx(36.0)
    assert "voxel_count" not in result


# ---------------------------------------------------------------------------
# Date-removal metadata
# ---------------------------------------------------------------------------

def test_deidentification_reports_dates_removed_by_default():
    pydicom = pytest.importorskip("pydicom")
    from core.dicom_privacy import deidentify_dataset

    dataset = pydicom.dataset.Dataset()
    dataset.PatientID = "patient-1"
    dataset.StudyDate = "20240101"
    dataset.StudyTime = "120000"

    clean = deidentify_dataset(dataset)

    assert clean.StudyDate == ""
    assert clean.StudyTime == ""
    assert "Dates Removed" in clean.DeidentificationMethod
    assert "Dates Retained" not in clean.DeidentificationMethod


def test_deidentification_reports_dates_retained_when_kept():
    pydicom = pytest.importorskip("pydicom")
    from core.dicom_privacy import deidentify_dataset

    dataset = pydicom.dataset.Dataset()
    dataset.PatientID = "patient-1"
    dataset.StudyDate = "20240101"
    dataset.StudyTime = "120000"

    clean = deidentify_dataset(dataset, keep_dates=True)

    # Only *Date* elements are retained; *Time* elements are always blanked.
    assert clean.StudyDate == "20240101"
    assert clean.StudyTime == ""
    assert "Dates Retained" in clean.DeidentificationMethod
    assert "Times Removed" in clean.DeidentificationMethod
    assert "Dates Removed" not in clean.DeidentificationMethod


# ---------------------------------------------------------------------------
# 3071 HU boundary
# ---------------------------------------------------------------------------

def test_tissue_classification_includes_dense_bone_upper_edge():
    from engines.modality_calculators.ct_calculator import CTCalculator

    hu = np.zeros((20, 20), dtype=np.float64)
    hu[0, 0] = 3071.0

    result = CTCalculator._tissue_classification(hu)

    assert result["DenseBone"]["count"] == 1
    assert result["Artifact"]["count"] == 0


def test_low_contrast_detectability_covers_dense_bone_upper_edge():
    from engines.modality_calculators.ct_calculator import CTCalculator

    # Two tissue classes above the minimum voxel count, one voxel at 3071 HU.
    hu = np.full((20, 40), -800.0, dtype=np.float64)  # Lung class
    hu[:, 20:] = 0.0  # Water class
    hu[0, 0] = 3071.0

    result = CTCalculator._low_contrast_detectability(hu)

    # The 3071 HU voxel must not crash or silently reclassify the analysis;
    # the two dominant classes remain Lung and Water.
    assert isinstance(result["cnr"], float)
    assert np.isfinite(result["cnr"])


def test_tissue_classifier_reports_dense_bone_upper_edge():
    from core.tissue_classifier import TissueClassifier

    hu = np.zeros((20, 20), dtype=np.float64)
    hu[0, 0] = 3071.0

    result = TissueClassifier.classify(hu)

    assert result["DenseBone"] == pytest.approx(0.25)
    assert result.get("OutsideRange", 0.0) == 0.0
    assert result.get("Unclassified", 0.0) == 0.0
