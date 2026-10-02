"""Regression tests for the cohort color-vs-volume disambiguation bug.

Reviewer finding: a 3D medical volume whose last axis has 3 or 4 positions
was mistaken for an RGB image, mixing distinct slices into one luminance
value (e.g. mean 29.0 instead of the correct central-slice 0.0) and leaving
``selected_slice`` blank.
"""
import csv
import hashlib
import io

import nibabel as nib
import numpy as np
import pytest
from PIL import Image as PILImage

from app import ClinicalApp


@pytest.fixture()
def cohort_app():
    return ClinicalApp.__new__(ClinicalApp)


def _volume_rows(app, tmp_path, array):
    path = tmp_path / "volume.nii.gz"
    nib.save(nib.Nifti1Image(array, np.eye(4)), str(path))
    payload = app._build_cohort_metrics_csv([str(path)])
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def test_3slice_volume_is_not_mistaken_for_rgb(cohort_app, tmp_path):
    """(4,4,3) volume: hot last slice must not become RGB luminance (29.0)."""
    vol = np.zeros((4, 4, 3), dtype=np.float32)
    vol[:, :, 2] = 255.0
    row = _volume_rows(cohort_app, tmp_path, vol)[0]

    assert row["status"] == "success"
    # Correct volume behavior: central slice of the smallest axis (z, idx 1).
    assert float(row["mean"]) == 0.0
    # The collapse must be disclosed, not silently skipped (reviewer saw '').
    assert row["selected_slice"] == "1"
    assert row["slice_selection_rule"] == "central slice of smallest dimension"
    assert row["source_shape"] == "4x4x3"


def test_isotropic_4position_volume_collapses_as_volume(cohort_app, tmp_path):
    """(4,4,4): smallest-axis tie resolves to axis 0 -> slice mean 21.75.

    RGBA luminance conversion would have returned 0.0 here (alpha ignored),
    so this exact value proves the volume interpretation is applied.
    """
    vol = np.zeros((4, 4, 4), dtype=np.float32)
    vol[:, :, 3] = 87.0
    row = _volume_rows(cohort_app, tmp_path, vol)[0]

    assert row["status"] == "success"
    assert float(row["mean"]) == pytest.approx(87.0 * 4 / 16)
    assert row["selected_slice"] == "2"


def test_true_rgb_raster_still_gets_luminance(cohort_app, tmp_path):
    """A real (H,W,3) raster must still be luminance-converted, not sliced."""
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[..., 2] = 255  # blue image; luminance = 0.114 * 255 ~ 29.07
    path = tmp_path / "color.png"
    PILImage.fromarray(img, mode="RGB").save(str(path))
    payload = cohort_app._build_cohort_metrics_csv([str(path)])
    row = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))[0]

    assert row["status"] == "success"
    assert float(row["mean"]) == pytest.approx(0.114 * 255, abs=0.5)
    assert row["selected_slice"] == ""


def test_source_hash_is_sha256_of_file_contents_not_its_name(cohort_app, tmp_path):
    image_path = tmp_path / "original.nii.gz"
    copy_path = tmp_path / "renamed-copy.nii.gz"
    nib.save(
        nib.Nifti1Image(np.arange(64, dtype=np.float32).reshape(4, 4, 4), np.eye(4)),
        str(image_path),
    )
    copy_path.write_bytes(image_path.read_bytes())

    payload = cohort_app._build_cohort_metrics_csv(
        [str(image_path), str(copy_path)]
    )
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    expected_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()

    assert rows[0]["source_hash"] == expected_hash
    assert rows[1]["source_hash"] == expected_hash
    assert len(rows[0]["source_hash"]) == 64


def test_uploaded_source_hash_restores_stream_position():
    from io import BytesIO

    source = BytesIO(b"synthetic image bytes")
    source.seek(5)

    assert ClinicalApp._sha256_target(source) == hashlib.sha256(
        b"synthetic image bytes"
    ).hexdigest()
    assert source.tell() == 5
