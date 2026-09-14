"""Regression tests for modality-safe non-CT measurements."""

import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.uid import ExplicitVRLittleEndian

from engines.modality_calculators import GenericIntensityCalculator, get_calculator


def test_non_ct_factory_returns_descriptive_calculator():
    calculator = get_calculator("MR")
    assert isinstance(calculator, GenericIntensityCalculator)
    result = calculator.calculate(np.arange(256, dtype=np.float32).reshape(16, 16))
    assert result["modality"] == "MR"
    assert result["intensity_units"] == "stored_signal"
    assert result["statistics"]["n_voxels"] == 256
    assert "not a calibrated clinical biomarker" in result["status"]


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
    dataset.PixelData = np.ones((16, 16), dtype=np.uint16).tobytes()
    with pytest.raises(ValueError, match="DoseGridScaling"):
        get_calculator("RTDOSE").calculate(dataset)
