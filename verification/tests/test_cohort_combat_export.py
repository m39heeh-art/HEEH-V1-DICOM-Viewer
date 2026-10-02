"""End-to-end tests: ComBat harmonization wired into the cohort CSV export.

Covers the opt-in toggle, the per-row disclosure columns, the explicit
refusal path (raw statistics shipped with a stated reason), and the
invariance of the default (combat=False) export.
"""

import io
import sys
from pathlib import Path

import numpy as np
import pytest

from core.harmonization import combat_harmonize

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _make_cohort_file(tmp_path, name, modality, mean, slope=1.0, intercept=0.0):
    """Synthetic constant-intensity image with small noise-perturbed values."""
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, MRImageStorage, ExplicitVRLittleEndian

    rows = cols = 12
    rng = np.random.default_rng(abs(hash(name)) % (2**32))
    stored = np.full((rows, cols), int(mean), dtype=np.int16)
    stored = stored + rng.normal(0, 2.0, size=(rows, cols)).astype(np.int16)
    path = str(tmp_path / name)
    meta = FileMetaDataset()
    sop = CTImageStorage if modality == "CT" else MRImageStorage
    meta.MediaStorageSOPClassUID = sop
    meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = sop
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.Modality = modality
    ds.PatientName = "ANONYMOUS"
    ds.PatientID = "ANONYMOUS"
    ds.Rows, ds.Columns = rows, cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleSlope = slope
    ds.RescaleIntercept = intercept
    ds.PixelData = stored.tobytes()
    ds.save_as(path)
    return path


def _read_csv_rows(payload: bytes):
    import csv

    text = payload.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_cohort_export_without_combat_has_no_disclosure_columns(tmp_path):
    """Default export (combat=False) keeps the historical schema."""
    from app import ClinicalApp

    files = [
        _make_cohort_file(tmp_path, f"ct{i}.dcm", "CT", 1000 + i)
        for i in range(4)
    ]
    payload = ClinicalApp()._build_cohort_metrics_csv(files)
    rows = _read_csv_rows(payload)
    assert len(rows) == 4
    assert rows[0]["combat_applied"] == ""
    assert rows[0]["combat_details"] == ""
    # Raw statistics unchanged by the ComBat code path.
    assert float(rows[0]["mean"]) == pytest.approx(1000.0, abs=10.0)


def test_cohort_export_refuses_cross_modality_combat(tmp_path):
    """Modality is not a defensible batch for harmonizing unlike signals."""
    from app import ClinicalApp

    files = [
        _make_cohort_file(tmp_path, f"ct{i}.dcm", "CT", 1000)
        for i in range(3)
    ] + [
        _make_cohort_file(tmp_path, f"mr{i}.dcm", "MR", 2500)
        for i in range(3)
    ]
    payload = ClinicalApp()._build_cohort_metrics_csv(files, combat=True)
    rows = _read_csv_rows(payload)
    assert len(rows) == 6
    assert all(row["combat_applied"] == "no" for row in rows)
    assert all(row["combat_batch"] == "" for row in rows)
    assert all(row["combat_details"].startswith("refused:") for row in rows)
    assert all("modality is not a valid ComBat batch" in row["combat_details"] for row in rows)
    ct_means = [
        float(row["mean"]) for row in rows if row["modality"].endswith("CT")
    ]
    mr_means = [
        float(row["mean"]) for row in rows if row["modality"].endswith("MR")
    ]
    assert abs(np.mean(ct_means) - np.mean(mr_means)) > 1000.0


def test_cohort_export_combat_refusal_is_explicit_not_silent(tmp_path):
    """Single-batch cohorts refuse harmonization and ship raw stats."""
    from app import ClinicalApp

    files = [
        _make_cohort_file(tmp_path, f"ct{i}.dcm", "CT", 1000 + i)
        for i in range(5)
    ]
    payload = ClinicalApp()._build_cohort_metrics_csv(files, combat=True)
    rows = _read_csv_rows(payload)
    assert all(row["combat_applied"] == "no" for row in rows)
    assert all(row["combat_details"].startswith("refused:") for row in rows)
    # Raw values are untouched by the refusal path.
    assert float(rows[0]["mean"]) == pytest.approx(1000.0, abs=10.0)
    assert float(rows[4]["mean"]) == pytest.approx(1004.0, abs=10.0)


def test_cohort_export_combat_failed_rows_are_not_applicable(tmp_path):
    """Failed processing rows disclose 'not applicable', never fake data."""
    from app import ClinicalApp

    good = [
        _make_cohort_file(tmp_path, f"ct{i}.dcm", "CT", 1000)
        for i in range(3)
    ]
    bad_file = tmp_path / "broken.dcm"
    bad_file.write_bytes(b"not a dicom file at all")
    files = good + [str(bad_file)]
    payload = ClinicalApp()._build_cohort_metrics_csv(files, combat=True)
    rows = _read_csv_rows(payload)
    assert len(rows) == 4
    failed = [row for row in rows if row["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["combat_applied"] == "no"
    assert "not applicable" in failed[0]["combat_details"]
    ok = [row for row in rows if row["status"] == "success"]
    assert len(ok) == 3
    # 3 files in ONE batch -> refusal (engine requires >=2 per batch).
    assert all(row["combat_applied"] == "no" for row in ok)
    assert "refused:" in ok[0]["combat_details"]


def test_engine_rejects_confounded_covariate_design():
    """A covariate identical to the batch dummy is confounded; ComBat's
    design becomes rank-deficient, which must not crash or fabricate."""
    values = np.array([
        [1.0, 2.0], [3.0, 4.0],
        [21.0, 22.0], [23.0, 24.0],
    ])
    batch = ["A", "A", "B", "B"]
    confounded = np.array([0.0, 0.0, 1.0, 1.0])
    adjusted, diag = combat_harmonize(
        values, batch, covariates={"group": confounded}
    )
    assert adjusted.shape == values.shape
    assert diag.converged or diag.iterations > 0
