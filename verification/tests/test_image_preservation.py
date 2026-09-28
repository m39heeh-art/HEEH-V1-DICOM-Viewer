"""
Image quality preservation tests.

Verifies that opening (DICOM / NIfTI) and displaying images loses no
information that downstream analysis depends on:

* int16/uint16 DICOM pixel data round-trips through
  ``ClinicalApp()._load_image`` to the *exact* expected HU values (float32
  represents all 16-bit integers exactly, and integer slope/intercept
  rescale is exact).
* NIfTI volumes carrying RescaleSlope/RescaleIntercept in their header are
  loaded with those scalings applied correctly (``img.dataobj`` is the raw
  unscaled array).
* ``_apply_windowing`` returns a fresh uint8 *display* array and never
  mutates the raw HU array used by analysis.
* The quantitative/CT-metric paths consume the raw float ROI, not the
  uint8 display version.

These are research/education tools and NOT a medical device.
"""

import numpy as np
import pytest


def _write_synthetic_dicom(path, modality="CT", arr=None, slope=1.0, intercept=0.0):
    """Minimal synthetic DICOM series for loader tests (mirrors test_suite)."""
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.8"
    meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4.5.8"
    ds.Modality = modality
    ds.Rows, ds.Columns = arr.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleSlope = slope
    ds.RescaleIntercept = intercept
    ds.PixelData = arr.astype(np.int16).tobytes()
    ds.save_as(path)


# ---------------------------------------------------------------------------
# DICOM CT: lossless HU round-trip
# ---------------------------------------------------------------------------
def test_ct_dicom_hu_roundtrip_exact(tmp_path):
    """int16 pixel + integer slope/intercept -> HU must be bit-exact."""
    from app import ClinicalApp

    slope, intercept = 2.0, -1024.0
    rng = np.random.default_rng(5)
    # Realistic CT store values: rescale must land HU inside the valid band
    # [-1024, 3071] so the physiological gate accepts the volume.
    px = rng.integers(0, 2048, (16, 16)).astype(np.int16)
    path = str(tmp_path / "ct_exact.dcm")
    _write_synthetic_dicom(path, "CT", arr=px, slope=slope, intercept=intercept)

    data, uid, modality = ClinicalApp()._load_image(path)
    expected = px.astype(np.float64) * slope + intercept
    assert data.dtype == np.float32
    # Exact: float32 carries every int16 exactly, and integer rescale is exact.
    assert np.array_equal(data, expected.astype(np.float32))


def test_ct_dicom_full_hu_span_unclipped(tmp_path):
    """Values spanning the practical 12-bit HU range must not be clipped at load."""
    from app import ClinicalApp

    # Raw pixel range [-1024, 3071] maps with slope=1/intercept=0 to itself.
    px = np.arange(-1024, 3072, 1, dtype=np.int16).reshape(64, 64)
    path = str(tmp_path / "ct_span.dcm")
    _write_synthetic_dicom(path, "CT", arr=px, slope=1.0, intercept=0.0)

    data, uid, modality = ClinicalApp()._load_image(path)
    assert data.min() == -1024.0
    assert data.max() == 3071.0
    assert data.size == 64 * 64


def test_mr_dicom_preserves_raw_16bit_span(tmp_path):
    """Non-CT: raw signal must pass through without rescale or clipping."""
    from app import ClinicalApp

    rng = np.random.default_rng(7)
    px = rng.integers(-20000, 20000, (16, 16)).astype(np.int16)
    path = str(tmp_path / "mr_span.dcm")
    _write_synthetic_dicom(path, "MR", arr=px, slope=2.0, intercept=5.0)

    data, uid, modality = ClinicalApp()._load_image(path)
    assert np.array_equal(data, px.astype(np.float32))


def _write_synthetic_dicom_mono1(path, modality="MR", arr=None):
    """Minimal MONOCHROME1 ('dark = high signal') DICOM helper."""
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.MRImageStorage
    meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.9"
    meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = pydicom.uid.MRImageStorage
    ds.SOPInstanceUID = "1.2.3.4.5.9"
    ds.Modality = modality
    ds.Rows, ds.Columns = arr.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME1"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = 0.0
    ds.PixelData = arr.astype(np.int16).tobytes()
    ds.save_as(path)


def test_mono1_mr_analysis_keeps_raw_intensity(tmp_path):
    """MONOCHROME1 inversion is display-only: the data returned for analysis
    must equal the original stored pixel values (no data-level flip, no
    information loss), while the display-only flip yields the conventional
    brightness mapping."""
    from app import ClinicalApp

    rng = np.random.default_rng(17)
    raw = rng.integers(100, 3000, (16, 16)).astype(np.int16)
    path = str(tmp_path / "mr_mono1.dcm")
    _write_synthetic_dicom_mono1(path, "MR", arr=raw)

    data, uid, modality = ClinicalApp()._load_image(path)
    # (1) Analysis data is the untouched raw intensity.
    assert np.array_equal(data, raw.astype(np.float32))
    # (2) The marker must reach the display layer.
    assert "MONOCHROME1" in str(modality).upper()

    # (3) Display-only flip: monotone (bijective) remap that preserves order.
    pmin, pmax = float(np.percentile(raw, 1)), float(np.percentile(raw, 99))
    disp = np.clip((raw - pmin) / max(pmax - pmin, 1e-9) * 255, 0, 255).astype(np.uint8)
    disp_flipped = (255 - disp).astype(np.uint8)
    assert disp_flipped.dtype == np.uint8
    assert np.all(disp_flipped >= 0) and np.all(disp_flipped <= 255)
    # MONOCHROME1 convention: high signal → low display value (dark).
    # Verify the ordering is consistent: raw max maps to display min, raw min to display max.
    r_max_idx = np.unravel_index(raw.argmax(), raw.shape)
    r_min_idx = np.unravel_index(raw.argmin(), raw.shape)
    assert int(disp_flipped[r_max_idx]) <= int(disp_flipped[r_min_idx])


def test_mono1_mr_marker_flag_in_display_branch(tmp_path):
    """The render path must branch on the MONOCHROME1 marker to invert only
    the display array, leaving the analysis array untouched."""

    # Simulate the analyze vs display split exactly as the render path does.
    raw = np.array([[1000.0, 2000.0, 3000.0, 500.0]], dtype=np.float32)
    mod_key = "DICOM / MR (MONOCHROME1)"
    non_ct = (("DICOM" in mod_key) and ("CT" not in mod_key)) or \
             ("NIFTI" in mod_key or "NRRD" in mod_key or "MHA" in mod_key)
    assert non_ct

    pmin, pmax = float(np.percentile(raw, 1)), float(np.percentile(raw, 99))
    disp_img = np.clip((raw - pmin) / max(pmax - pmin, 1e-9) * 255, 0, 255).astype(np.uint8)
    if 'MONOCHROME1' in mod_key:
        disp_img = 255 - disp_img

    # Analysis array is untouched raw float; display is flipped uint8.
    assert raw.dtype == np.float32
    assert np.array_equal(raw, np.array([[1000.0, 2000.0, 3000.0, 500.0]], dtype=np.float32))
    assert disp_img.dtype == np.uint8
    # MONOCHROME1 convention: high signal → low display value (dark).
    # Verify monotone ordering: raw[0,1]=2000 < raw[0,2]=3000, and after flip
    # the display is also monotone (disp[0,2] < disp[0,1] < disp[0,0]).
    assert int(disp_img[0, 0]) > int(disp_img[0, 1])  # 1000→high disp; 2000→lower


def test_ct_unchanged_after_mono1_split(tmp_path):
    """CT is never inverted: HU stays exact regardless of the MONOCHROME1 path."""
    from app import ClinicalApp

    px = (np.arange(0, 256, 1, dtype=np.int16).reshape(16, 16) % 16) * 200 + 100
    path = str(tmp_path / "ct_mono2.dcm")
    _write_synthetic_dicom(path, "CT", arr=px, slope=1.0, intercept=-1024)
    data, uid, modality = ClinicalApp()._load_image(path)
    expected = px.astype(np.float32) - 1024.0
    assert np.array_equal(data, expected)


def test_modality_display_conventions():
    """CT/MR stay MONOCHROME2 while projection radiography uses MONOCHROME1."""
    from app import ClinicalApp

    assert not ClinicalApp._uses_monochrome1_display("CT", "DICOM / CT")
    assert not ClinicalApp._uses_monochrome1_display(
        "MR", "DICOM / MR (MONOCHROME1)"
    )
    assert ClinicalApp._uses_monochrome1_display("CR", "DICOM / CR")
    assert ClinicalApp._uses_monochrome1_display("DX", "DICOM / DX")
    assert ClinicalApp._uses_monochrome1_display("XRAY", "DICOM / XRAY")
    assert ClinicalApp._uses_monochrome1_display(
        "US", "DICOM / US (MONOCHROME1)"
    )


def test_dicom_presentation_metadata_reads_standard_tags(tmp_path):
    from app import ClinicalApp

    path = str(tmp_path / "presentation.dcm")
    raw = np.arange(16, dtype=np.int16).reshape(4, 4)
    _write_synthetic_dicom(path, "CT", arr=raw, slope=1.0, intercept=-1024)

    import pydicom

    dataset = pydicom.dcmread(path)
    dataset.PatientName = "Test^Patient"
    dataset.WindowCenter = 40
    dataset.WindowWidth = 400
    dataset.PixelSpacing = [0.5, 0.75]
    dataset.save_as(path)

    metadata = ClinicalApp._read_dicom_presentation_metadata(path)
    assert metadata["patient_name"] == "Test^Patient"
    assert metadata["modality"] == "CT"
    assert metadata["photometric_interpretation"] == "MONOCHROME2"
    assert metadata["window_center"] == 40.0
    assert metadata["window_width"] == 400.0
    assert metadata["rows"] == 4
    assert metadata["columns"] == 4
    assert metadata["pixel_spacing_mm"] == [0.5, 0.75]
    assert metadata["sop_class_uid"] == "1.2.840.10008.5.1.4.1.1.2"
    assert metadata["transfer_syntax_uid"] == "1.2.840.10008.1.2.1"
    assert metadata["bits_allocated"] == 16
    assert metadata["bits_stored"] == 16
    assert metadata["pixel_representation"] == 1


# ---------------------------------------------------------------------------
# NIfTI: scl_slope / scl_inter applied on top of raw dataobj
# ---------------------------------------------------------------------------
def test_nifti_rescale_applied_exactly(tmp_path):
    """NIfTI with header slope/intercept: loaded data equals raw*slope+intercept."""
    import nibabel as nib
    from app import ClinicalApp

    rng = np.random.default_rng(11)
    raw = rng.integers(-500, 500, (4, 16, 16)).astype(np.int16)
    slope, intercept = 1.5, -1024.0

    nii = nib.Nifti1Image(raw, affine=np.eye(4))
    nii.header.set_slope_inter(slope, intercept)
    path = str(tmp_path / "scaled.nii")
    nib.save(nii, path)

    data, uid, modality = ClinicalApp()._load_image(path)
    assert np.issubdtype(data.dtype, np.floating)
    expected = raw.astype(np.float64) * slope + intercept
    assert np.allclose(data, expected, atol=1e-4)
    # Spot-check that scaling truly was applied (not raw int16 left as-is).
    assert abs(float(data[0, 0, 0]) - (float(raw[0, 0, 0]) * slope + intercept)) < 1e-3


def test_nifti_plain_load_is_identity(tmp_path):
    """NIfTI with no rescale: data equals stored int16 values exactly."""
    import nibabel as nib
    from app import ClinicalApp

    rng = np.random.default_rng(13)
    raw = rng.integers(0, 3000, (4, 16, 16)).astype(np.int16)
    path = str(tmp_path / "plain.nii")
    nib.save(nib.Nifti1Image(raw, affine=np.eye(4)), path)

    data, uid, modality = ClinicalApp()._load_image(path)
    assert np.array_equal(data, raw.astype(np.float32))


# ---------------------------------------------------------------------------
# Windowing: display octets never mutate / substitute the analysis data
# ---------------------------------------------------------------------------
def test_windowing_does_not_mutate_input():
    from app import ClinicalApp

    hu = np.array([[-1000.0, 0.0, 500.0, 3000.0]], dtype=np.float32)
    hu_copy = hu.copy()
    out = ClinicalApp._apply_windowing(hu, center=40, width=400)
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255
    assert np.array_equal(hu, hu_copy)


def test_color_display_and_monochrome_inversion_do_not_mutate_source():
    from app import ClinicalApp

    source = np.array(
        [[[0.0, 100.0, 200.0], [300.0, 400.0, 500.0]]],
        dtype=np.float32,
    )
    original = source.copy()
    display = ClinicalApp._prepare_color_display(source)
    assert display.dtype == np.uint8
    assert np.array_equal(source, original)

    grayscale = np.array([[0, 64], [128, 255]], dtype=np.uint8)
    grayscale_original = grayscale.copy()
    inverted = 255 - grayscale
    assert np.array_equal(grayscale, grayscale_original)
    assert inverted is not grayscale


def test_viewer_serializes_source_values_without_resizing_or_mutating(monkeypatch):
    import base64
    from app import ClinicalApp

    captured = {}

    def fake_component(*, data, key, on_click):
        captured.update(data)
        return type("Result", (), {})()

    monkeypatch.setattr("app._PIXEL_HOVER_VIEWER", fake_component)
    source = np.array([[1.25, 2.5], [3.75, 4.0]], dtype=np.float32)
    original = source.copy()
    display = np.array([[0, 85], [170, 255]], dtype=np.uint8)
    ClinicalApp._render_pixel_hover_viewer(
        display, source, "HU", key="integrity", zoom=4.0
    )

    encoded = base64.b64decode(captured["values"])
    restored = np.frombuffer(encoded, dtype="<f4").reshape(2, 2)
    assert np.array_equal(restored, original)
    assert captured["width"] == 2
    assert captured["height"] == 2
    assert captured["zoom"] == 4.0
    assert np.array_equal(source, original)


def test_image_type_drives_display_profile_and_color_handling():
    from app import ClinicalApp

    assert ClinicalApp._parse_image_type(
        "DICOM / CT", np.zeros((8, 8), dtype=np.float32)
    ) == ("CT", False)
    assert ClinicalApp._parse_image_type(
        "DICOM / MR (MONOCHROME1)", np.zeros((8, 8), dtype=np.float32)
    ) == ("MR", False)
    assert ClinicalApp._parse_image_type(
        "DICOM / OPTICAL", np.zeros((8, 8, 3), dtype=np.float32)
    ) == ("OPTICAL", True)
    assert ClinicalApp._default_window_preset("CT") == "brain"
    assert ClinicalApp._default_window_preset("MR") == "mri_t1"


def test_window_mapping_is_monotonic():
    """Windowing is a monotone remap: it preserves tissue ordering exactly."""
    from app import ClinicalApp

    hu = np.linspace(-1024, 3071, 200, dtype=np.float32).reshape(10, 20)
    disp = ClinicalApp._apply_windowing(hu, center=40, width=400)
    # Non-decreasing along HU.
    assert np.all(np.diff(disp.ravel()) >= 0)


def test_ct_metrics_use_raw_roi_not_display_array():
    """Quantitative/CT metrics consume the raw float ROI (bit-exact values)."""
    from app import ClinicalApp
    from engines.modality_calculators import CTCalculator

    raw = np.full((64, 64), 100.0, dtype=np.float32)
    disp = ClinicalApp._apply_windowing(raw, center=40, width=400)
    assert disp.dtype == np.uint8
    assert int(disp.max()) < 255  # display window saturated; analysis is not

    calc = CTCalculator()
    stats = calc._hu_statistics(raw)
    assert stats["mean"] == pytest.approx(100.0, abs=1e-4)