"""
Tests for the HEEH-V1™ DICOM Viewer.

Scope: verify the scientific/mathematical correctness of the metric and
validation helpers. These are research/education tools and NOT a medical
device - the tests assert numerical correctness, not clinical validity.
"""

import numpy as np
import pytest
from types import SimpleNamespace

# Keep one canonical pytest entry point while retaining focused source modules.
# The imported tests are collected from this module when the test path is run.
from tests.test_a11y import *  # noqa: F401,F403
from tests.test_acr_phantom import *  # noqa: F401,F403
from tests.test_ct_calculator import *  # noqa: F401,F403
from tests.test_export_validation import *  # noqa: F401,F403
from tests.test_finetune import *  # noqa: F401,F403
from tests.test_i18n import *  # noqa: F401,F403
from tests.test_image_preservation import *  # noqa: F401,F403
from tests.test_logging_config import *  # noqa: F401,F403
from tests.test_modality_calculators import *  # noqa: F401,F403
from tests.test_security import *  # noqa: F401,F403
from tests.test_ui_helpers import *  # noqa: F401,F403

from core.constants import HU_MIN, HU_MAX, TISSUE_RANGES
from core.branding import PACKAGE_NAME, PRODUCT_NAME, PRODUCT_NAME_ASCII
from core.physiological_validator import PhysiologicalValidator
from engines.clinical_metrics import ClinicalMetrics


def test_protected_product_identity():
    """The public product identity must remain stable across releases."""
    assert PRODUCT_NAME == "HEEH-V1™ DICOM Viewer"
    assert PRODUCT_NAME_ASCII == "HEEH-V1(TM) DICOM Viewer"
    assert PACKAGE_NAME == "heeh-v1-dicom-viewer"


def test_enhanced_ct_is_registered_and_required_tags_are_enforced():
    from core.modality_detector import ModalityDetector, missing_required_tags
    from core.modality_registry import SOP_ENHANCED_CT_IMAGE_STORAGE
    from pydicom.dataset import Dataset

    dataset = Dataset()
    dataset.Modality = "CT"
    dataset.SOPClassUID = SOP_ENHANCED_CT_IMAGE_STORAGE
    detection = ModalityDetector().detect(dataset)

    assert detection.sop_class_match
    assert "Rows" in missing_required_tags(dataset, detection)
    assert not ModalityDetector().detect_supported(dataset)


def test_ct_zero_mean_cv_is_explicitly_undefined():
    from engines.modality_calculators.ct_calculator import CTCalculator

    noise = CTCalculator._noise(np.zeros((8, 8), dtype=float))

    assert noise["coefficient_of_variation"] is None


def test_dicom_ordering_prefers_physical_slice_position():
    from core.dicom_ordering import order_dicom_files
    from pydicom.dataset import Dataset

    items = ["slice-c", "slice-a", "slice-b"]
    headers = {
        "slice-c": Dataset(),
        "slice-a": Dataset(),
        "slice-b": Dataset(),
    }
    for name, z, instance in (
        ("slice-c", 2.0, 3),
        ("slice-a", 0.0, 1),
        ("slice-b", 1.0, 2),
    ):
        headers[name].StudyInstanceUID = "1.2.826.0.1.3680043.8.498.1"
        headers[name].SeriesInstanceUID = "1.2.826.0.1.3680043.8.498.2"
        headers[name].ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        headers[name].ImagePositionPatient = [0, 0, z]
        headers[name].InstanceNumber = instance

    ordered = order_dicom_files(items, header_reader=headers.get)

    assert ordered == ["slice-a", "slice-b", "slice-c"]


def test_radiomics_report_contains_reproducibility_parameters():
    from core.tissue_classifier import RadiomicsExtractor

    report = RadiomicsExtractor.full_report(
        np.arange(64, dtype=float).reshape(8, 8),
        levels=16,
        discretization="fixed_bin_width",
        bin_width=4.0,
        spacing=(0.5, 0.75),
    )

    assert report["provenance"]["levels"] == 16
    assert report["provenance"]["bin_width"] == 4.0
    assert report["provenance"]["spacing"] == [0.5, 0.75]
    assert report["provenance"]["profile"] == "CT_IBSI_SUBSET_V1"


def test_ct_radiomics_preprocessing_records_explicit_policy():
    from core.tissue_classifier import RadiomicsExtractor

    image, provenance = RadiomicsExtractor.preprocess_ct(
        np.zeros((4, 4, 4), dtype=float),
        spacing=(2.0, 2.0, 2.0),
        target_spacing=(1.0, 1.0, 1.0),
        resegment=(-1000.0, 1000.0),
    )

    assert image.shape == (512,)
    assert provenance["resampled"] is True
    assert provenance["target_spacing"] == [1.0, 1.0, 1.0]
    assert provenance["resegmentation"] == [-1000.0, 1000.0]


def test_navigation_benchmark_reports_cache_behavior():
    from core.navigation_benchmark import run_navigation_benchmark

    result = run_navigation_benchmark(image_count=3, operations=9, cache_size=3)

    assert result.operations == 9
    assert result.source_misses == 3
    assert result.source_hits == 6
    assert result.display_misses == 3
    assert result.display_hits == 6
    assert result.hit_rate == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Runtime consolidation and modality capability policy
# ---------------------------------------------------------------------------
def test_runtime_uses_shared_ai_engine_and_ui_compatibility_export():
    from app import MedicalAIVisionEngine as active_engine
    from ui.clinical_app import ClinicalApp as compatibility_app
    from utils.medical_ai_vision import MedicalAIVisionEngine as shared_engine

    assert active_engine is shared_engine
    from app import ClinicalApp
    assert compatibility_app is ClinicalApp


def test_feature_capabilities_are_conservative_and_centralized():
    from app import ClinicalApp
    from core.modality_registry import (
        get_available_features,
        get_feature_capabilities,
    )

    ct = get_feature_capabilities("CT")
    assert get_feature_capabilities("DICOM / CT") == ct
    mr = ClinicalApp._feature_capabilities("MR")
    unknown = get_feature_capabilities("UNKNOWN")

    assert ct["ct_windowing"] and ct["ct_tissue"]
    assert not mr["ct_windowing"] and not mr["ct_tissue"]
    assert mr["radiomics"] and mr["ai_inference"]
    assert not any(unknown.values())
    assert mr == ClinicalApp._feature_capabilities("MR")
    volume = get_feature_capabilities("VOLUME")
    assert volume["edge_detection"] and volume["volumetric"]
    assert not volume["ct_windowing"]
    assert "Native-intensity statistics" in get_available_features("MR")
    assert not any("SUV" in item for item in get_available_features("PT"))


def test_onnx_provider_selection_has_a_safe_cpu_fallback():
    from engines.onnx_inference import ONNXInferenceEngine

    engine = ONNXInferenceEngine()
    assert engine.providers
    assert engine.active_provider in engine.providers
    assert engine.active_provider in engine.available_providers()
    assert engine.cuda_enabled == (engine.active_provider == "CUDAExecutionProvider")


def test_non_dicom_volumes_get_a_safe_generic_image_type():
    from app import ClinicalApp

    assert ClinicalApp._parse_image_type(
        "VOLUME / NIFTI", np.zeros((8, 8, 4), dtype=np.float32)
    ) == ("VOLUME", False)


def test_volume_visualizer_handles_2d_4d_and_clamps_mpr():
    from core.volume_visualizer import VolumeVisualizer

    volume = np.arange(2 * 3 * 4 * 2, dtype=np.float32).reshape(2, 3, 4, 2)
    assert VolumeVisualizer.mip(volume, axis=9).shape == (3, 4)
    assert VolumeVisualizer.mpr(volume, axis=1, slice_idx=999).shape == (2, 4)
    assert VolumeVisualizer.mpr(np.ones((5, 6), dtype=np.float32)).shape == (5, 6)


def test_auto_reader_advances_and_stops_at_end():
    from app import ClinicalApp

    assert ClinicalApp._advance_auto_reader_index(0, 3) == (1, True)
    assert ClinicalApp._advance_auto_reader_index(2, 3) == (2, False)


def test_auto_reader_can_loop_to_first_image():
    from app import ClinicalApp

    assert ClinicalApp._advance_auto_reader_index(2, 3, loop=True) == (0, True)
    assert ClinicalApp._advance_auto_reader_index(0, 0, loop=True) == (0, False)
    assert ClinicalApp._parse_image_type(
        "VOLUME / NIFTI", np.zeros((8, 8, 3), dtype=np.float32)
    ) == ("VOLUME", False)


def test_ai_engine_does_not_apply_heuristic_fallback_without_permission(monkeypatch):
    from utils.medical_ai_vision import MedicalAIVisionEngine

    engine = MedicalAIVisionEngine()
    monkeypatch.setattr(engine, "_ensure_loaded", lambda: False)

    result = engine.infer(
        np.zeros((16, 16), dtype=np.uint8),
        hu_data=np.zeros((16, 16), dtype=np.float32),
    )
    assert result == (
        "MODEL_UNAVAILABLE",
        0.0,
        "No validated model is available for this modality.",
    )


def test_anatomical_segmentation_rejects_non_volumetric_inputs():
    from engines.anatomical_segmentation import AnatomicalSegmentation

    with pytest.raises(ValueError, match="requires a 3D volume"):
        AnatomicalSegmentation._validate_volume(np.zeros((16, 16), dtype=np.float32))


def test_anatomical_segmentation_validates_mask_shape():
    from engines.anatomical_segmentation import AnatomicalSegmentation

    with pytest.raises(ValueError, match="expected"):
        AnatomicalSegmentation._validate_masks(
            {"liver": np.ones((4, 4, 3), dtype=np.uint8)},
            (4, 4, 4),
        )


def test_anatomical_segmentation_status_is_explicit_without_backends(monkeypatch):
    from engines.anatomical_segmentation import AnatomicalSegmentation

    monkeypatch.setattr(
        AnatomicalSegmentation,
        "_totalsegmentator_command",
        staticmethod(lambda: None),
    )
    statuses = AnatomicalSegmentation(monai_label_url="").statuses()
    assert [status.available for status in statuses] == [False, False]


def test_monai_preprocessor_rejects_invalid_dimensions():
    from engines.monai_preprocessor import MONAIPreprocessor

    with pytest.raises(ValueError, match="2D or 3D"):
        MONAIPreprocessor().preprocess_volume(np.zeros((2, 2, 2, 2), dtype=np.float32))


def test_sitk_resampler_requires_matching_positive_spacing():
    from engines.sitk_registration import SimpleITKRegistration

    with pytest.raises(ValueError, match="one positive finite value"):
        SimpleITKRegistration.resample_to_isotropic(
            np.zeros((4, 4, 4), dtype=np.float32),
            spacing=(1.0, 1.0),
        )


def test_vit_model_registry_is_modality_conservative():
    from utils.medical_ai_vision import MedicalAIVisionEngine

    engine = MedicalAIVisionEngine()
    assert "brain" in engine.available_domains("MR")
    assert "chest" in engine.available_domains("DICOM / DX")
    assert engine.available_domains("CT") == []


def test_vit_preprocessing_records_non_quantitative_provenance(monkeypatch):
    from utils.medical_ai_vision import MedicalAIVisionEngine

    class FakeProcessor:
        def __call__(self, images, return_tensors):
            import torch
            return {"pixel_values": torch.zeros(1, 3, 224, 224)}

    engine = MedicalAIVisionEngine()
    engine.processor = FakeProcessor()
    engine.model = object()
    engine._loaded_model_id = engine._get_model_id()
    monkeypatch.setattr(engine, "_ensure_loaded", lambda: True)

    inputs = engine.prepare_inputs(np.zeros((32, 48), dtype=np.uint8), "MR")

    assert tuple(inputs["pixel_values"].shape) == (1, 3, 224, 224)
    assert engine.last_provenance["operation"] == "model_input_resize"
    assert engine.last_provenance["model_input_is_quantitative"] is False
    assert engine.last_provenance["super_resolution"] is False


# ---------------------------------------------------------------------------
# HU physiological range
# ---------------------------------------------------------------------------
def test_hu_range_constants():
    # Standard 12-bit CT storage range.
    """Test that hu range constants."""
    assert HU_MIN == -1024.0
    assert HU_MAX == 3071.0


def test_windowing_uses_symmetric_odd_width():
    """Odd CT window widths must preserve the requested center and width."""
    from app import ClinicalApp

    data = np.array([[-1.0, 1.25, 2.75, 3.5]], dtype=np.float32)
    rendered = ClinicalApp._apply_windowing(data, center=1.25, width=3.0)
    assert rendered.tolist() == [[0, 128, 255, 255]]


def test_tissue_ranges_inside_hu_range():
    # Every tissue window must sit within the valid CT HU display range.
    """Test that tissue ranges inside hu range."""
    for lo, hi in TISSUE_RANGES.values():
        assert lo >= HU_MIN
        assert hi <= HU_MAX
        assert lo < hi


# ---------------------------------------------------------------------------
# PhysiologicalValidator (HU validation)
# ---------------------------------------------------------------------------
def test_physiological_validator_accepts_valid_hu():
    """Test that physiological validator accepts valid hu."""
    data = np.array([[-1000, 0, 500, 1500, 3000]], dtype=np.float32)
    assert PhysiologicalValidator.validate_physiological_norms(data) is True


def test_physiological_validator_rejects_out_of_range():
    """Test that physiological validator rejects out of range."""
    data = np.array([[HU_MAX + 10]], dtype=np.float32)
    with pytest.raises(ValueError):
        PhysiologicalValidator.validate_physiological_norms(data)


def test_physiological_validator_rejects_nan():
    """Test that physiological validator rejects nan."""
    data = np.array([[0.0, np.nan, 100.0]], dtype=np.float32)
    with pytest.raises(ValueError):
        PhysiologicalValidator.validate_physiological_norms(data)


def test_physiological_validator_rejects_inf():
    """Test that physiological validator rejects inf."""
    data = np.array([[0.0, np.inf]], dtype=np.float32)
    with pytest.raises(ValueError):
        PhysiologicalValidator.validate_physiological_norms(data)


# ---------------------------------------------------------------------------
# ClinicalMetrics - known analytical results
# ---------------------------------------------------------------------------
def _make_pred_target():
    # Perfect overlap -> all metrics should be 1.0
    """Build a ground-truth binary mask and an identical prediction."""
    arr = np.zeros((10, 10), dtype=int)
    arr[2:5, 2:5] = 1
    return arr.copy(), arr.copy()


def test_perfect_overlap_all_metrics_one():
    """Test that perfect overlap all metrics one."""
    pred, target = _make_pred_target()
    assert ClinicalMetrics.dice_score(pred, target) == 1.0
    assert ClinicalMetrics.iou_score(pred, target) == 1.0
    assert ClinicalMetrics.sensitivity(pred, target) == 1.0
    assert ClinicalMetrics.specificity(pred, target) == 1.0
    assert ClinicalMetrics.precision(pred, target) == 1.0


def test_empty_both_returns_one_dice():
    """Test that empty both returns one dice."""
    empty = np.zeros((8, 8), dtype=int)
    # Both empty -> conventionally treated as perfect agreement (Dice=1).
    assert ClinicalMetrics.dice_score(empty, empty) == 1.0


def test_disjoint_masks_zero_overlap():
    """Test that disjoint masks zero overlap."""
    a = np.zeros((10, 10), dtype=int)
    b = np.zeros((10, 10), dtype=int)
    a[0:3, 0:3] = 1
    b[7:9, 7:9] = 1
    assert ClinicalMetrics.dice_score(a, b) == 0.0
    assert ClinicalMetrics.iou_score(a, b) == 0.0
    assert ClinicalMetrics.sensitivity(a, b) == 0.0
    assert ClinicalMetrics.precision(a, b) == 0.0


def test_metrics_reject_shape_mismatch():
    with pytest.raises(ValueError, match="shapes must match"):
        ClinicalMetrics.dice_score(np.zeros((2, 2)), np.zeros((3, 3)))


def test_metrics_accept_common_255_masks():
    pred = np.array([[0, 255], [0, 0]])
    target = np.array([[0, 1], [0, 0]])
    assert ClinicalMetrics.dice_score(pred, target) == 1.0


def test_quantitative_engine_rejects_outlier_voxel():
    from core.quantitative_engine import QuantitativeEngine

    roi = np.full((10, 10), 0.0, dtype=np.float32)
    roi[0, 0] = 10000.0
    result = QuantitativeEngine.execute(roi)
    assert "Physiological Range Violation" in result


def test_specificity_with_false_positives():
    """Test that specificity with false positives."""
    pred = np.zeros((5, 5), dtype=int)
    target = np.zeros((5, 5), dtype=int)
    pred[0, 0] = 1          # a false positive
    target[1, 1] = 1        # a false negative
    # TN = 25 - 1 - 1 = 23, FP = 1 -> specificity = 23/24
    assert abs(ClinicalMetrics.specificity(pred, target) - 23 / 24) < 1e-9


def test_hausdorff_identical_zero():
    """Test that hausdorff identical zero."""
    pred, target = _make_pred_target()
    assert ClinicalMetrics.hausdorff_distance(pred, target) == 0.0


def test_hausdorff_empty_returns_inf():
    """Test that hausdorff empty returns inf."""
    a = np.zeros((5, 5), dtype=int)
    b = np.zeros((5, 5), dtype=int)
    b[2, 2] = 1
    assert ClinicalMetrics.hausdorff_distance(a, b) == float('inf')


def test_report_keys_present():
    """Test that report keys present."""
    pred, target = _make_pred_target()
    rep = ClinicalMetrics.report(pred, target)
    for key in ("Dice", "IoU", "Sensitivity", "Specificity", "Precision",
                "Hausdorff_Distance", "Avg_Surface_Distance"):
        assert key in rep


# ---------------------------------------------------------------------------
# TissueClassifier (imported from app.py)
# ---------------------------------------------------------------------------
def test_tissue_classifier_percentages_sum():
    """Test that tissue classifier percentages sum."""
    from app import TissueClassifier
    rng = np.random.default_rng(0)
    data = rng.uniform(-1000, 1500, size=(200, 200)).astype(np.float32)
    result = TissueClassifier.classify(data)
    total = sum(v for k, v in result.items() if k not in ("OutsideRange",))
    # Assigned tissue + any Unclassified should be ~100%.
    assert 99.0 <= total <= 100.0


def test_tissue_classifier_pure_air():
    """Test that tissue classifier pure air."""
    from app import TissueClassifier
    data = np.full((50, 50), -1000, dtype=np.float32)
    result = TissueClassifier.classify(data)
    assert result["Air"] == 100.0


def test_tissue_classifier_pure_bone():
    """Test that tissue classifier pure bone."""
    from app import TissueClassifier
    data = np.full((50, 50), 1000, dtype=np.float32)
    result = TissueClassifier.classify(data)
    assert result["Bone"] == 100.0


# ---------------------------------------------------------------------------
# AnalysisOrchestrator.calculate_tissue_mix_score (display helper)
# ---------------------------------------------------------------------------
def test_tissue_mix_score_outputs_in_valid_range():
    """Test that tissue mix score outputs in valid range."""
    from app import AnalysisOrchestrator
    out = AnalysisOrchestrator.calculate_tissue_mix_score(
        np.array([0.5, 0.2, 0.3]), np.array([0.33, 0.33, 0.34])
    )
    # tanh -> always in (-1, 1)
    assert -1.0 < out < 1.0


# ---------------------------------------------------------------------------
# RadiomicsExtractor - degenerate (tiny) inputs
# ---------------------------------------------------------------------------
def test_histogram_features_single_voxel_finite():
    """Test that histogram features single voxel finite."""
    from app import RadiomicsExtractor
    h = RadiomicsExtractor.histogram_features(np.array([50.0]))
    assert h["mean"] == 50.0
    assert h["std"] == 0.0
    for v in h.values():
        assert np.isfinite(v)


def test_histogram_features_two_voxels_finite():
    """Test that histogram features two voxels finite."""
    from app import RadiomicsExtractor
    h = RadiomicsExtractor.histogram_features(np.array([50.0, 60.0]))
    assert h["std"] > 0
    assert h["variance"] > 0
    for v in h.values():
        assert np.isfinite(v)


def test_full_report_single_voxel_finite():
    """Test that full report single voxel finite."""
    from app import RadiomicsExtractor
    rep = RadiomicsExtractor.full_report(np.array([[50.0]]))
    assert "histogram" in rep
    for v in rep["histogram"].values():
        assert np.isfinite(v)


# ---------------------------------------------------------------------------
# ImageQualityMetrics - tiny / empty regions
# ---------------------------------------------------------------------------
def test_uniformity_tiny_rois():
    """Test that uniformity tiny rois."""
    from app import ImageQualityMetrics as IQM
    assert IQM.uniformity(np.ones((1, 1), np.float32)) == 0.0
    u = IQM.uniformity(np.arange(4, dtype=np.float32).reshape(2, 2))
    assert np.isfinite(u) and u > 0


def test_noise_estimate_any_shape_finite():
    """Test that noise estimate any shape finite."""
    from app import ImageQualityMetrics as IQM
    for shape in [(1, 10), (10, 1), (1, 1), (5, 5)]:
        n = IQM.noise_estimate(np.arange(np.prod(shape), dtype=np.float32).reshape(shape))
        for v in n.values():
            assert np.isfinite(v)


def test_snr_cnr_empty_or_tiny_regions():
    """Test that snr cnr empty or tiny regions."""
    from app import ImageQualityMetrics as IQM
    assert IQM.snr(np.array([]), np.array([1.0, 2.0])) == 0.0
    assert IQM.snr(np.array([1.0]), np.array([1.0])) == 0.0  # noise too small
    assert IQM.cnr(np.array([1.0]), np.array([1.0]), np.array([1.0])) == 0.0


# ---------------------------------------------------------------------------
# QuantitativeEngine - statistical power gate
# ---------------------------------------------------------------------------
def test_quantitative_engine_rejects_small_samples():
    """Test that quantitative engine rejects small samples."""
    from app import QuantitativeEngine
    out = QuantitativeEngine().execute(np.array([1.0, 2.0]))
    assert out.startswith("CANNOT_BE_CONFIRMED")


def test_quantitative_engine_normal_volume():
    """Test that quantitative engine normal volume."""
    from app import QuantitativeEngine
    rng = np.random.default_rng(0)
    out = QuantitativeEngine().execute(rng.normal(0, 100, (20, 20)).astype(np.float32))
    assert isinstance(out, dict)
    assert out["n_voxels"] == 400
    assert "CANNOT_BE_CONFIRMED" not in out["status"]


# ---------------------------------------------------------------------------
# StructuralEngine - output contract
# ---------------------------------------------------------------------------
def test_structural_engine_outputs_uint8():
    """Test that structural engine outputs uint8."""
    from app import StructuralEngine
    rng = np.random.default_rng(1)
    out = StructuralEngine().execute(rng.normal(0, 50, (32, 32)).astype(np.float32))
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255


# ---------------------------------------------------------------------------
# MedicalAIVisionEngine._fallback - degenerate ROI
# ---------------------------------------------------------------------------
def test_fallback_small_roi_returns_tuple():
    """Test that fallback small roi returns tuple."""
    from app import MedicalAIVisionEngine
    result = MedicalAIVisionEngine()._fallback(np.array([1.0]))
    assert result[0] == "INSUFFICIENT ROI"


# ---------------------------------------------------------------------------
# LongitudinalAnalyzer - shape contract
# ---------------------------------------------------------------------------
def test_longitudinal_shape_mismatch_raises():
    """Test that longitudinal shape mismatch raises."""
    from app import LongitudinalAnalyzer
    with pytest.raises(ValueError):
        LongitudinalAnalyzer.difference_map(np.zeros((3, 3)), np.zeros((4, 4)))


# ---------------------------------------------------------------------------
# ClinicalApp._apply_windowing - output contract
# ---------------------------------------------------------------------------
def test_windowing_outputs_uint8_clipped():
    """Test that windowing outputs uint8 clipped."""
    from app import ClinicalApp
    out = ClinicalApp._apply_windowing(
        np.array([[-1000.0, 0.0, 500.0]]), center=40, width=400
    )
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255


# ---------------------------------------------------------------------------
# BaseAnalysis.execute - output shape + degenerate-input contract
# ---------------------------------------------------------------------------
def test_base_analysis_execute_shape_and_degenerate_contract():
    """Test BaseAnalysis.execute output shape and degenerate-input guard."""
    from core.base_analysis import BaseAnalysis

    class _BaseAnalysisHarness(BaseAnalysis):
        def execute(self, roi_hu, pixel_spacing=None):
            return super().execute(roi_hu, pixel_spacing)

    assert issubclass(_BaseAnalysisHarness, BaseAnalysis)
    assert BaseAnalysis.__module__ == "core.base_analysis"

    # deterministic structure-bearing ROI (nonzero second derivatives)
    yy, xx = np.meshgrid(np.linspace(-3, 3, 16), np.linspace(-3, 3, 16))
    roi = (xx ** 2.0) + (yy ** 2.0)

    out = _BaseAnalysisHarness().execute(roi, pixel_spacing=np.array([0.7, 0.7]))
    assert isinstance(out, np.ndarray)
    assert out.shape == roi.shape
    assert np.issubdtype(out.dtype, np.uint8)
    assert out.min() >= 0 and out.max() <= 255

    # constant ROI -> degenerate guard must return a clear alert string
    const_out = _BaseAnalysisHarness().execute(np.full((8, 8), 100.0))
    assert isinstance(const_out, str) and "UNCERTAIN_DATA_ALERT" in const_out


# ---------------------------------------------------------------------------
# DICOM modality handling (CT rescale vs. MR raw intensity)
# ---------------------------------------------------------------------------
def _write_synthetic_dicom(path, modality="CT", arr=None, slope=1.0, intercept=0.0):
    """Write a minimal synthetic DICOM series to temp for loader tests."""
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.6"
    meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4.5.6"
    ds.Modality = modality
    ds.Rows = 8
    ds.Columns = 8
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleSlope = slope
    ds.RescaleIntercept = intercept
    if arr is None:
        arr = np.full((8, 8), 100, dtype=np.int16)
    ds.PixelData = arr.tobytes()
    ds.save_as(path)


def test_load_ct_dicom_applies_hu_rescale(tmp_path):
    """Test that load ct dicom applies hu rescale."""
    from app import ClinicalApp
    path = str(tmp_path / "ct.dcm")
    _write_synthetic_dicom(path, "CT", slope=1.0, intercept=-1024)
    data, uid, modality = ClinicalApp()._load_image(path)
    assert isinstance(data, np.ndarray)
    assert np.issubdtype(data.dtype, np.floating)
    assert data.min() >= -1024 and data.max() <= 3071
    assert "CT" in modality


def test_load_mr_dicom_passes_raw_intensity(tmp_path):
    """Test that load mr dicom passes raw intensity."""
    from app import ClinicalApp
    path = str(tmp_path / "mr.dcm")
    _write_synthetic_dicom(path, "MR", slope=2.0, intercept=5.0)
    data, uid, modality = ClinicalApp()._load_image(path)
    assert np.all(data == 100.0)
    assert "MR" in modality


def test_load_compressed_dicom_tcia_style(tmp_path):
    """TCIA images are often JPEG/JPEG2000-compressed DICOM; pixel_array
    must decode via the pylibjpeg stack instead of raising."""
    import io
    import pydicom
    from PIL import Image
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.encaps import encapsulate
    from app import ClinicalApp

    arr = np.linspace(0, 255, 64 * 64, dtype=np.uint8).reshape(64, 64)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=90)

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.7"
    meta.TransferSyntaxUID = pydicom.uid.JPEGBaseline8Bit
    ds = FileDataset("t", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4.5.7"
    ds.Modality = "CT"
    ds.Rows = 64
    ds.Columns = 64
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.RescaleSlope = "1.0"
    ds.RescaleIntercept = "0.0"
    ds.PixelData = encapsulate([buf.getvalue()])

    path = str(tmp_path / "tcia.IMA")
    ds.save_as(path)

    data, uid, modality = ClinicalApp()._load_image(path)
    assert isinstance(data, np.ndarray)
    assert data.shape == (64, 64)
    assert "CT" in modality


# ---------------------------------------------------------------------------
# TCIA .tcia manifest support
# ---------------------------------------------------------------------------
def test_parse_tcia_manifest():
    """Exercise the TCIA manifest parser round-trip."""
    from app import ClinicalApp
    manifest = (
        "downloadServerUrl=https://x/nbia-download/servlet/DownloadServlet\n"
        "includeAnnotation=true\n"
        "databasketId=manifest-test.tcia\n"
        "manifestVersion=3.0\n"
        "ListOfSeriesToDownload=\n"
        "1.3.6.1.4.1.14519.5.2.1.27391573362612334484148927657377202681\n"
        "1.3.6.1.4.1.14519.5.2.1.17769173823381730156093099454396349088\n"
    )
    uids = ClinicalApp()._parse_tcia_manifest(manifest)
    assert uids == [
        "1.3.6.1.4.1.14519.5.2.1.27391573362612334484148927657377202681",
        "1.3.6.1.4.1.14519.5.2.1.17769173823381730156093099454396349088",
    ]
    assert ClinicalApp()._parse_tcia_manifest("no numbers here") == []


def test_tcia_series_cache_hit_skips_download(tmp_path):
    """If the cache dir already contains a completed series (marked by
    .series.complete), _download_tcia_series must not touch the network and
    must return the cached paths."""
    from app import ClinicalApp
    dest = tmp_path / "cached_series"
    dest.mkdir()
    (dest / "1-1.dcm").write_bytes(b"DICM-cached")
    (dest / ".series.complete").write_text("ok", encoding="utf-8")
    files = ClinicalApp()._download_tcia_series(
        "1.3.6.1.4.1.14519.5.2.1.000000000000000000000000000000000000000",
        str(dest),
        progress_cb=None,
    )
    assert files == [str(dest / "1-1.dcm")]


def test_tcia_download_progress_is_always_numeric(tmp_path, monkeypatch):
    """TCIA responses are chunked (no Content-Length). The progress callback
    must never receive None — st.progress raises on None, which aborted real
    downloads. Simulate a chunked response with unknown size and verify the
    extracted files are returned and every callback value is a float."""
    import io
    import zipfile
    from pathlib import Path
    from unittest import mock
    from app import ClinicalApp

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("1-1.dcm", b"DICM")
        z.writestr("1-2.dcm", b"DICM")
    zip_bytes = buf.getvalue()

    class FakeResp:
        """Minimal requests.Response stand-in returning canned content."""
        headers = {}  # no Content-Length -> chunked, unknown size
        def __enter__(self):
            """Enter the fake-response context manager."""
            return self
        def __exit__(self, *a):
            """Exit the fake-response context manager."""
            return False
        def raise_for_status(self):
            """No-op success signal for the fake response."""
            pass
        def iter_content(self, chunk_size=1 << 20):
            """Yield the canned content in chunks."""
            for i in range(0, len(zip_bytes), 256):
                yield zip_bytes[i:i + 256]

    with mock.patch.object(
        ClinicalApp,
        "_TCIA_SESSION",
        SimpleNamespace(get=lambda *args, **kwargs: FakeResp()),
    ):
        calls = []
        dest = tmp_path / "series"
        files = ClinicalApp()._download_tcia_series(
            "1.3.6.1.4.1.14519.5.2.1.999999999999999999999999999999999999999",
            str(dest),
            expected_bytes=None,
            progress_cb=lambda frac, done, total: calls.append(frac),
        )
    assert sorted(Path(f).name for f in files) == ["1-1.dcm", "1-2.dcm"]
    assert calls, "progress callback was never invoked"
    assert all(isinstance(f, float) and 0.0 <= f <= 1.0 for f in calls)


def test_tcia_download_aggregates_raw_stream_reads(tmp_path, monkeypatch):
    """Use aggregated raw reads when NBIA sends many small wire chunks."""
    import io
    import zipfile
    from pathlib import Path
    from app import ClinicalApp

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("image.dcm", b"DICM")
    payload = buf.getvalue()

    class Raw:
        def __init__(self):
            self.read_sizes = []
            self.stream = io.BytesIO(payload)

        def read(self, size):
            self.read_sizes.append(size)
            return self.stream.read(min(size, 3)) if self.stream.tell() < len(payload) else b""

    class FakeResp:
        status_code = 200
        headers = {}

        def __init__(self):
            self.raw = Raw()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

    response = FakeResp()
    monkeypatch.setattr(
        ClinicalApp,
        "_TCIA_SESSION",
        SimpleNamespace(get=lambda *args, **kwargs: response),
    )
    files = ClinicalApp()._download_tcia_series("1.2.3", tmp_path / "series")

    assert [Path(path).name for path in files] == ["image.dcm"]
    assert response.raw.read_sizes
    assert max(response.raw.read_sizes) == 8 * 1024 * 1024


def test_tcia_download_uses_buffered_path_for_sized_series(tmp_path, monkeypatch):
    """Use requests' buffered transfer for bounded ordinary-sized archives."""
    import io
    import zipfile
    from pathlib import Path
    from app import ClinicalApp

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("image.dcm", b"DICM")
    payload = buf.getvalue()

    class FakeResp:
        headers = {}
        status_code = 200
        content = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

    calls = []
    response = FakeResp()
    monkeypatch.setattr(
        ClinicalApp,
        "_TCIA_SESSION",
        SimpleNamespace(
            get=lambda *args, **kwargs: calls.append(kwargs) or response
        ),
    )
    files = ClinicalApp()._download_tcia_series(
        "1.2.3", tmp_path / "series", expected_bytes=len(payload),
    )

    assert [Path(path).name for path in files] == ["image.dcm"]
    assert calls[0]["stream"] is False


def test_tcia_partial_cache_is_not_treated_as_complete(tmp_path, monkeypatch):
    """A stale partial download must be resumed/retried, not analyzed as data."""
    from pathlib import Path
    from app import ClinicalApp
    dest = tmp_path / "series"
    dest.mkdir()
    (dest / "series.zip.tmp").write_bytes(b"partial")

    class FakeResp:
        status_code = 200
        headers = {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size=1 << 20):
            import io
            import zipfile
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("image.dcm", b"DICM")
            yield buf.getvalue()

    with monkeypatch.context() as patch:
        patch.setattr(
            ClinicalApp,
            "_TCIA_SESSION",
            SimpleNamespace(get=lambda *args, **kwargs: FakeResp()),
        )
        files = ClinicalApp()._download_tcia_series(
            "1.2.3", str(dest), progress_cb=None
        )
    assert [Path(path).name for path in files] == ["image.dcm"]


def test_tcia_metadata_uses_get_and_writes_csv_cache(tmp_path, monkeypatch):
    """Metadata retrieval supports the current GET-based NBIA route."""
    from app import ClinicalApp

    calls = []

    class FakeResp:
        text = (
            "SeriesInstanceUID,Modality,ImageCount,FileSize\n"
            "1.2.3,CT,2,100\n"
        )

        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResp()

    monkeypatch.setattr(
        ClinicalApp,
        "_TCIA_SESSION",
        SimpleNamespace(get=fake_get),
    )
    path = ClinicalApp()._fetch_tcia_metadata(["1.2.3"], tmp_path)

    assert path.endswith(".csv")
    assert "SeriesInstanceUID" in open(path, encoding="utf-8").read()
    assert calls and calls[0][1]["params"]["SeriesInstanceUID"] == "1.2.3"


def test_tcia_v4_contract_uses_current_host_and_download_params():
    """Keep the upload flow aligned with the documented NBIA v4 contract."""
    from app import ClinicalApp

    app = ClinicalApp()
    assert "nbia.cancerimagingarchive.net" in app._TCIA_IMAGE_URL
    assert app._TCIA_IMAGE_URL.endswith("/v4/getImage")
    assert app._TCIA_META_URL.endswith("/v4/getSeries")
    assert app._is_allowed_manifest_url(
        "https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getImage"
    )


def test_tcia_metadata_accepts_json_records(tmp_path, monkeypatch):
    """Metadata retrieval accepts NBIA deployments returning JSON objects."""
    import csv
    from app import ClinicalApp

    class FakeResp:
        text = '{"data": [{"SeriesInstanceUID": "1.2.3", "Modality": "MR"}]}'

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"SeriesInstanceUID": "1.2.3", "Modality": "MR"},
                ]
            }

    monkeypatch.setattr(
        ClinicalApp,
        "_TCIA_SESSION",
        SimpleNamespace(get=lambda *args, **kwargs: FakeResp()),
    )
    path = ClinicalApp()._fetch_tcia_metadata(["1.2.3"], tmp_path)

    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    assert rows == [{"Modality": "MR", "SeriesInstanceUID": "1.2.3"}]


# ---------------------------------------------------------------------------
# Volumetric loading (_load_image): nibabel + SimpleITK fallback
# ---------------------------------------------------------------------------
def _make_volume(shape=(10, 12, 8)):
    """Return a small deterministic numpy volume for loader tests."""
    rng = np.random.default_rng(0)
    return rng.normal(0, 100, shape).astype(np.float32)


def test_load_nifti_local(tmp_path):
    """Test that load nifti local."""
    import nibabel as nib
    from app import ClinicalApp
    vol = _make_volume()
    path = str(tmp_path / "vol.nii")
    nib.save(nib.Nifti1Image(vol, np.eye(4)), path)
    data, uid, modality = ClinicalApp()._load_image(path)
    assert isinstance(data, np.ndarray)
    assert data.shape == vol.shape
    assert np.allclose(data, vol)
    assert "Volume" in modality


def test_load_nifti_upload_resets_file_position(tmp_path):
    """Uploaded volumes must load even when the upload cursor is at EOF."""
    import io
    import nibabel as nib
    from app import ClinicalApp

    vol = _make_volume()
    path = tmp_path / "vol.nii"
    nib.save(nib.Nifti1Image(vol, np.eye(4)), str(path))
    upload = io.BytesIO(path.read_bytes())
    upload.name = "vol.nii"
    upload.seek(0, io.SEEK_END)

    data, _uid, modality = ClinicalApp()._load_image(upload)

    assert isinstance(data, np.ndarray)
    assert data.shape == vol.shape
    assert "Volume" in modality


def test_load_nrrd_via_sitk_fallback(tmp_path):
    """Test that load nrrd via sitk fallback."""
    import SimpleITK as sitk
    from app import ClinicalApp
    vol = _make_volume()
    path = str(tmp_path / "vol.nrrd")
    sitk.WriteImage(sitk.GetImageFromArray(vol.astype(np.float32)), path)
    data, uid, modality = ClinicalApp()._load_image(path)
    assert isinstance(data, np.ndarray)
    assert data.ndim == 3
    assert np.allclose(data, vol)


def test_load_mha_via_sitk_fallback(tmp_path):
    """Test that load mha via sitk fallback."""
    import SimpleITK as sitk
    from app import ClinicalApp
    vol = _make_volume()
    path = str(tmp_path / "vol.mha")
    sitk.WriteImage(sitk.GetImageFromArray(vol.astype(np.float32)), path)
    data, uid, modality = ClinicalApp()._load_image(path)
    assert isinstance(data, np.ndarray)
    assert data.ndim == 3
    assert np.allclose(data, vol)


def test_load_missing_file_returns_error_string():
    """Test that load missing file returns error string."""
    from app import ClinicalApp
    data, uid, modality = ClinicalApp()._load_image("C:/does/not/exist.dcm")
    assert isinstance(data, str)
    assert data.startswith(("LOAD_ERROR", "CRITICAL"))
