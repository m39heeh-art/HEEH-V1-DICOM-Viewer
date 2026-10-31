"""Regression tests for modality-safe non-CT measurements."""

import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.uid import ExplicitVRLittleEndian

from engines.modality_calculators import (
    CTCalculator,
    GenericIntensityCalculator,
    get_calculator,
)


def test_non_ct_factory_returns_descriptive_calculator():
    calculator = get_calculator("MR")
    assert isinstance(calculator, GenericIntensityCalculator)
    result = calculator.calculate(np.arange(256, dtype=np.float32).reshape(16, 16))
    assert result["modality"] == "MR"
    assert result["intensity_units"] == "stored_signal"
    assert result["statistics"]["n_voxels"] == 256
    assert "not a calibrated clinical biomarker" in result["status"]


def test_ct_nps_is_unavailable_without_physical_pixel_spacing():
    dataset = Dataset()
    dataset.Modality = "CT"
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 1
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.RescaleSlope = 1
    dataset.RescaleIntercept = 0
    dataset.PixelData = np.zeros((16, 16), dtype=np.int16).tobytes()
    dataset.file_meta = Dataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    nps = CTCalculator().calculate(dataset)["nps"]

    assert nps["status"] == "unavailable"
    assert "frequency_units" not in nps
    assert nps["nps_2d"] is None
    assert "PixelSpacing" in nps["reason"]


@pytest.mark.parametrize("spacing", [[0.5], [0.5, 0.0], [0.5, float("nan")]])
def test_dicom_pixel_spacing_rejects_malformed_or_nonpositive_values(spacing):
    dataset = Dataset()
    dataset.PixelSpacing = spacing

    with pytest.raises(ValueError, match="PixelSpacing"):
        CTCalculator.get_pixel_spacing(dataset)


def test_ct_nps_is_unavailable_for_region_smaller_than_minimum():
    dataset = Dataset()
    dataset.Modality = "CT"
    dataset.PixelSpacing = [0.5, 0.75]
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 1
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.RescaleSlope = 1
    dataset.RescaleIntercept = 0
    dataset.PixelData = np.zeros((16, 16), dtype=np.int16).tobytes()
    dataset.file_meta = Dataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    roi = np.zeros((16, 16), dtype=bool)
    roi[:10, :11] = True
    nps = CTCalculator().calculate(dataset, roi=roi)["nps"]

    assert nps["status"] == "unavailable"
    assert "at least 8 by 8" in nps["reason"]


def test_rt_dose_requires_grid_scaling():
    dataset = Dataset()
    dataset.file_meta = Dataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.DoseUnits = "GY"
    dataset.PixelData = np.ones((16, 16), dtype=np.uint16).tobytes()
    with pytest.raises(ValueError, match="DoseGridScaling"):
        get_calculator("RTDOSE").calculate(dataset)


@pytest.mark.parametrize(
    ("dose_units", "expected_units"),
    [("GY", "Gy"), ("RELATIVE", "relative_dose")],
)
def test_rt_dose_reports_dicom_units_without_relabeling(dose_units, expected_units):
    dataset = Dataset()
    dataset.file_meta = Dataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.Modality = "RTDOSE"
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.PixelData = np.full((16, 16), 100, dtype=np.uint16).tobytes()
    dataset.DoseGridScaling = 0.01
    dataset.DoseUnits = dose_units
    dataset.DoseType = "PHYSICAL"

    result = get_calculator("RTDOSE").calculate(dataset)

    assert result["intensity_units"] == expected_units
    assert result["statistics"]["mean"] == pytest.approx(1.0)
    assert result["dose_type"] == "PHYSICAL"


def test_rt_dose_rejects_missing_or_unsupported_units():
    dataset = Dataset()
    dataset.DoseUnits = "CODED"
    dataset.DoseGridScaling = 0.01
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.file_meta = Dataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.PixelData = np.ones((16, 16), dtype=np.uint16).tobytes()

    with pytest.raises(ValueError, match="DoseUnits GY or RELATIVE"):
        get_calculator("RTDOSE").calculate(dataset)


def test_real_world_mapping_is_reported_as_not_applied():
    dataset = Dataset()
    dataset.Modality = "MR"
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.PixelData = np.full((16, 16), 7, dtype=np.uint16).tobytes()
    dataset.file_meta = Dataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    mapping = Dataset()
    mapping.RealWorldValueSlope = 2.0
    mapping.RealWorldValueIntercept = 1.0
    dataset.RealWorldValueMappingSequence = [mapping]

    result = get_calculator("MR").calculate(dataset)

    assert result["statistics"]["mean"] == pytest.approx(7.0)
    assert "not applied" in result["calibration"]
