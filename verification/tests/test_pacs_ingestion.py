"""
PACS-ingestion / export round-trip conformance suite.

Boundary this suite closes: every DICOM object the toolkit emits must
survive an independent re-parse at the file-format level (the checks a PACS
or a viewer applies when a study is pushed to it) and must be re-ingested by
the toolkit's own loaders and parsers with no loss of information.

Scope (research/education tool, NOT a medical device): these tests assert
standards conformance and lossless round-trips, not clinical validity.

Emitted / re-read objects covered:
  - Comprehensive SR (SOP 1.2.840.10008.5.1.4.1.1.88.33, TID 1500 tree)
  - De-identified DICOM copies exported via core/dicom_privacy.py
  - Synthetic source CT images used as round-trip anchors
  - Measurement-annotated PNG composites (UCUM units in tEXt metadata)

File-format level: PS3.10 (preamble + DICM magic), PS3.7 file meta (Group
Length, MediaStorageSOP* <-> dataset SOP* agreement, declared vs. actually
used Transfer Syntax, VersionSpecificationMinor), C.12.1 identification.
"""

import io
import zipfile
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
    generate_uid,
)


# ---------------------------------------------------------------------------
# Synthetic source objects (no real patient data; deterministic pixel data)
# ---------------------------------------------------------------------------

def _make_source_ct(tmp_path, name="source.dcm", *, rows=16, cols=16,
                    slope=1.0, intercept=-1024, stored=None):
    """Write a minimal monochrome CT image the app's loader accepts."""
    path = str(tmp_path / name)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "CT"
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
    if stored is None:
        stored = np.full((rows, cols), 100, dtype=np.int16)
    ds.PixelData = stored.tobytes()
    ds.save_as(path)
    return path, str(meta.MediaStorageSOPInstanceUID)


def _measurement(kind, data, *, unit="mm", mm=None, px=None, degrees=None):
    item = {"kind": kind, "label": "t", "color": "#8ef0c8", "data": data,
            "unit": unit, "px": px, "mm": mm, "precision": 2, "profile": None}
    if degrees is not None:
        item["degrees"] = degrees
    return item


def _sr_bytes(measurements, *, source_sop_class=CTImageStorage,
              source_uid=None, pixel_spacing_mm=(0.5, 0.5),
              roi_center_px=(8.0, 8.0), roi_radius_px=4):
    from app import ClinicalApp

    return ClinicalApp._build_dicom_sr_report(
        measurements,
        source_sop_class_uid=str(source_sop_class),
        source_sop_instance_uid=source_uid or generate_uid(),
        pixel_spacing_mm=pixel_spacing_mm,
        roi_center_px=roi_center_px,
        roi_radius_px=roi_radius_px,
    )


def _annotated_png(measurement):
    from app import ClinicalApp

    return ClinicalApp._render_annotated_image_png(
        np.full((16, 16), 128, dtype=np.uint8), measurements=[measurement]
    )


class _NamedBytes(io.BytesIO):
    """BytesIO with a file name, mimicking a Streamlit uploaded file."""

    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def _with_session_state(monkeypatch):
    """Swap streamlit.session_state for a plain dict and return it."""
    import streamlit as st

    state: dict = {}
    monkeypatch.setattr(st, "session_state", state, raising=False)
    return state


# ---------------------------------------------------------------------------
# 1. File-format level conformance of emitted DICOM objects
# ---------------------------------------------------------------------------

def test_comprehensive_sr_file_format_conformance():
    """Emitted SR is a valid PS3.10 file with self-consistent file meta."""
    payload = _sr_bytes(
        [_measurement("distance", {"x1": 2.0, "y1": 3.0, "x2": 6.0, "y2": 3.0},
                      mm=2.0, px=4.0)]
    )
    assert payload, "SR builder returned empty bytes for a valid measurement"

    # PS3.10: 128-byte preamble + 'DICM' magic.
    assert len(payload) > 132
    assert payload[128:132] == b"DICM"

    ds = pydicom.dcmread(io.BytesIO(payload))  # strict: no force=True

    # PS3.7 / C.12.1 file meta: TS declared and actually used must agree.
    meta = ds.file_meta
    assert str(meta.TransferSyntaxUID) == str(ExplicitVRLittleEndian)
    assert meta.FileMetaInformationVersion == b"\x00\x01"
    assert int(meta.FileMetaInformationGroupLength) > 0
    # PS3.7 Group Length must cover exactly the file-meta elements present.
    # Byte-exact check: encode the meta group with pydicom's own file-meta
    # writer; the result includes the 12-byte (0002,0000) element itself,
    # which the stored Group Length value must exclude (PS3.7, group 0002).
    from pydicom.filewriter import write_file_meta_info

    meta_buffer = io.BytesIO()
    write_file_meta_info(meta_buffer, meta)
    assert int(meta.FileMetaInformationGroupLength) == (
        len(meta_buffer.getvalue()) - 12
    )

    # MediaStorageSOP* (file meta) must agree with the dataset SOP*.
    assert str(meta.MediaStorageSOPClassUID) == str(
        pydicom.uid.ComprehensiveSRStorage
    )
    assert str(meta.MediaStorageSOPInstanceUID) == str(ds.SOPInstanceUID)
    assert str(ds.SOPClassUID) == str(pydicom.uid.ComprehensiveSRStorage)
    assert ds.Modality == "SR"

    # The declared explicit-VR syntax is literally present in the stream.
    assert str(ExplicitVRLittleEndian).encode() in payload


def test_sr_meta_group_length_survives_rewriting():
    """pydicom's file-format writer must keep the meta group length exact."""
    payload = _sr_bytes(
        [_measurement("distance", {"x1": 1.0, "y1": 1.0, "x2": 4.0, "y2": 5.0},
                      mm=5.0, px=5.0)]
    )
    first = pydicom.dcmread(io.BytesIO(payload))
    buffer = io.BytesIO()
    first.save_as(buffer, enforce_file_format=True)
    second = pydicom.dcmread(io.BytesIO(buffer.getvalue()))
    assert second.file_meta.FileMetaInformationGroupLength == (
        first.file_meta.FileMetaInformationGroupLength
    )
    assert bytes(payload[128:132]) == bytes(buffer.getvalue()[128:132])


def test_deidentified_export_file_format_conformance(tmp_path):
    """A de-identified copy re-parses as a strict PS3.10 file, PHIs gone."""
    from core.dicom_privacy import deidentify_dataset

    src_path, _ = _make_source_ct(tmp_path)
    dataset = pydicom.dcmread(src_path)
    dataset.PatientName = "Real^Patient"
    dataset.PatientID = "real-id-42"
    dataset.PatientIdentityRemoved = "NO"

    buffer = io.BytesIO()
    deidentify_dataset(dataset).save_as(buffer)
    payload = buffer.getvalue()
    assert payload[128:132] == b"DICM"

    out = pydicom.dcmread(io.BytesIO(payload))  # strict parse
    assert out.PatientName == "ANONYMOUS"
    assert out.PatientID.startswith("NEURO_")
    assert out.PatientID != "real-id-42"
    # The partial helper removes the inherited marker instead of asserting YES
    # (attested removal is documented; it must not be fabricated).
    assert "PatientIdentityRemoved" not in out
    # File meta stays self-consistent after the UID remap walk.
    assert str(out.file_meta.TransferSyntaxUID) == str(ExplicitVRLittleEndian)
    assert str(out.file_meta.MediaStorageSOPClassUID) == str(out.SOPClassUID)
    assert str(out.file_meta.MediaStorageSOPInstanceUID) == (
        str(out.SOPInstanceUID)
    )
    # The source instance UID was remapped: no link back to the original.
    _, source_uid = _make_source_ct(tmp_path, name="probe.dcm")
    assert str(out.SOPInstanceUID) != source_uid


# ---------------------------------------------------------------------------
# 2. Round-trip: exported SR -> the app's own parser -> measurement records
# ---------------------------------------------------------------------------

def test_distance_sr_round_trip_is_lossless(monkeypatch):
    """Export a ruler, re-parse with the app's own SR reader, compare."""
    from app import ClinicalApp

    state = _with_session_state(monkeypatch)
    rec = _measurement("distance", {"x1": 2.0, "y1": 3.0, "x2": 6.0, "y2": 7.0},
                       mm=5.656854249492381, px=5.656854249492381)
    payload = _sr_bytes([rec])
    dataset = pydicom.dcmread(io.BytesIO(payload))
    report = ClinicalApp._extract_sr_report(dataset)

    rows = [row for row in report["rows"] if row["kind"] == "distance"]
    assert len(rows) == 1
    row = rows[0]
    assert row["unit"] == "mm"
    assert float(row["value"]) == pytest.approx(5.656854249492381, rel=1e-9)
    assert row["points"] == [[(2.0, 3.0), (6.0, 7.0)]]

    # The re-import seam (the same code path the app calls) accepts it and
    # reproduces the original measurement record's geometry.
    imported = ClinicalApp._import_sr_measurements(rows)
    assert imported == 1
    assert state["measurements"][0]["kind"] == "distance"
    assert state["measurements"][0]["data"] == {
        "x1": 2.0, "y1": 3.0, "x2": 6.0, "y2": 7.0,
    }


def test_angle_sr_round_trip_is_lossless(monkeypatch):
    """Export a two-arm angle, re-parse it with the app's own SR reader."""
    from app import ClinicalApp

    state = _with_session_state(monkeypatch)
    rec = _measurement(
        "angle", {"x1": 4.0, "y1": 4.0, "x2": 8.0, "y2": 4.0,
                  "x3": 4.0, "y3": 8.0},
        degrees=90.0,
    )
    payload = _sr_bytes([rec])
    dataset = pydicom.dcmread(io.BytesIO(payload))
    report = ClinicalApp._extract_sr_report(dataset)

    rows = [row for row in report["rows"] if row["kind"] == "angle"]
    assert len(rows) == 1
    row = rows[0]
    assert float(row["value"]) == pytest.approx(90.0, rel=1e-9)
    # TID 320: one POLYLINE per arm; SR ingestion re-derives the vertex.
    assert row["points"] == [
        [(4.0, 4.0), (8.0, 4.0)], [(4.0, 4.0), (4.0, 8.0)],
    ]
    assert row["unit"] == "deg"

    imported = ClinicalApp._import_sr_measurements(rows)
    assert imported == 1
    item = state["measurements"][0]
    assert item["kind"] == "angle"
    # First point is the shared vertex in the app convention.
    assert item["data"] == {
        "x1": 4.0, "y1": 4.0, "x2": 8.0, "y2": 4.0, "x3": 4.0, "y3": 8.0,
    }


def test_roi_radius_sr_round_trip_with_calibration():
    """ROI radius exports as TID 300 NUM in mm when spacing is calibrated."""
    from app import ClinicalApp

    payload = _sr_bytes(
        [_measurement("distance", {"x1": 2.0, "y1": 2.0, "x2": 5.0, "y2": 2.0},
                      mm=3.0, px=3.0)],
        pixel_spacing_mm=(0.4, 0.4),
        roi_center_px=(8.0, 8.0),
        roi_radius_px=5,
    )
    dataset = pydicom.dcmread(io.BytesIO(payload))
    report = ClinicalApp._extract_sr_report(dataset)
    radius = [row for row in report["rows"] if row["kind"] == "radius"]
    assert len(radius) == 1
    assert radius[0]["unit"] == "mm"
    # 5 px * mean(0.4, 0.4) mm/px = 2.0 mm; GraphicData stays in px space.
    assert float(radius[0]["value"]) == pytest.approx(2.0, rel=1e-9)
    assert radius[0]["graphic_type"] == "CIRCLE"


def test_sr_references_the_source_image_instance():
    """TID 300/320 chain references the exact source SOP instance (C.18.4)."""
    from app import ClinicalApp

    source_uid = generate_uid()
    payload = _sr_bytes(
        [_measurement("distance", {"x1": 1.0, "y1": 1.0, "x2": 3.0, "y2": 2.0},
                      mm=2.23606797749979, px=2.23606797749979)],
        source_uid=source_uid,
    )
    dataset = pydicom.dcmread(io.BytesIO(payload))
    report = ClinicalApp._extract_sr_report(dataset)
    assert [ref["instance_uid"] for ref in report["source_images"]] == [
        source_uid
    ]
    assert report["source_images"][0]["class_uid"] == str(CTImageStorage)


# ---------------------------------------------------------------------------
# 3. Ingestion boundary: what the toolkit accepts and what it rejects
# ---------------------------------------------------------------------------

def test_exported_objects_reingest_through_the_app_loader(tmp_path):
    """An exported DICOM object re-ingests through the app's own loader."""
    from app import ClinicalApp

    source_path, source_uid = _make_source_ct(tmp_path)
    with open(source_path, "rb") as handle:
        source_bytes = handle.read()

    app = ClinicalApp()
    data, uid, modality = app._load_image(
        _NamedBytes(source_bytes, "source.dcm")
    )
    assert isinstance(data, np.ndarray)
    assert "DICOM" in modality and "CT" in modality
    assert uid == source_uid
    # CT rescale is applied on re-ingest (HU = stored * slope + intercept).
    assert float(data[0, 0]) == pytest.approx(100.0 + (-1024.0), abs=1e-6)


def test_annotated_png_reingests_as_measurement_composite():
    """The annotated-PNG export re-ingests through the composite path."""
    from app import ClinicalApp

    annotated = _annotated_png(
        _measurement("distance", {"x1": 1.0, "y1": 1.0, "x2": 5.0, "y2": 1.0},
                     mm=2.0, px=4.0)
    )
    assert annotated
    app = ClinicalApp()
    data, uid, modality = app._load_image(
        _NamedBytes(annotated, "annotated.png")
    )
    assert str(modality).startswith("MEASUREMENT_COMPOSITE")
    assert uid == "annotated.png"
    assert np.asarray(data).shape == (16, 16)


def test_ingestion_boundary_rejects_invalid_objects(tmp_path):
    """Missing TS, incomplete IOD, non-DICOM bytes, empty SR: all rejected."""
    from app import ClinicalApp

    # (a) No TransferSyntaxUID in file meta -> rejected before pixel decode.
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset("no_ts.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "CT"
    ds.Rows = ds.Columns = 4
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.PixelData = np.zeros((4, 4), dtype=np.int16).tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer)  # as-is: pydicom must not auto-fill the missing TS
    buffer.seek(0)
    outcome = ClinicalApp.process_dicom(ClinicalApp(), buffer)
    assert outcome[0].startswith("DATA_REJECTED")
    assert "TransferSyntaxUID" in outcome[0]

    # (b) Incomplete CT IOD (no rescale attributes) -> rejected by the
    #     required-tag gate; HU conversion must not run on guesses.
    meta2 = FileMetaDataset()
    meta2.MediaStorageSOPClassUID = CTImageStorage
    meta2.MediaStorageSOPInstanceUID = generate_uid()
    meta2.TransferSyntaxUID = ExplicitVRLittleEndian
    ds2 = FileDataset(
        "no_rescale.dcm", {}, file_meta=meta2, preamble=b"\0" * 128
    )
    ds2.SOPClassUID = CTImageStorage
    ds2.SOPInstanceUID = meta2.MediaStorageSOPInstanceUID
    ds2.Modality = "CT"
    ds2.Rows = ds2.Columns = 4
    ds2.SamplesPerPixel = 1
    ds2.PhotometricInterpretation = "MONOCHROME2"
    ds2.BitsAllocated = ds2.BitsStored = 16
    ds2.HighBit = 15
    ds2.PixelRepresentation = 1
    ds2.PixelData = np.zeros((4, 4), dtype=np.int16).tobytes()
    buffer2 = io.BytesIO()
    ds2.save_as(buffer2, enforce_file_format=True)
    buffer2.seek(0)
    outcome2 = ClinicalApp.process_dicom(ClinicalApp(), buffer2)
    assert outcome2[0].startswith("DATA_REJECTED")
    assert "RescaleSlope" in outcome2[0]

    # (c) Non-DICOM bytes are never mistaken for a DICOM object.
    app = ClinicalApp()
    data, uid, modality = app._load_image(io.BytesIO(b"not a dicom file"))
    assert isinstance(data, str) and data.startswith("LOAD_ERROR")
    assert uid is None

    # (d) SR builder emits nothing for measurements without usable values.
    assert _sr_bytes([{"kind": "distance", "data": {}}]) == b""


def test_series_round_trip_preserves_physical_order(tmp_path):
    """A physically ordered series re-orders identically after re-serialization."""
    from app import ClinicalApp
    from core.dicom_ordering import order_dicom_files

    paths = []
    study_uid, series_uid = generate_uid(), generate_uid()
    for index, z in enumerate((2.0, 0.0, 1.0)):
        path, _ = _make_source_ct(
            tmp_path, name=f"slice_{index}.dcm", rows=8, cols=8,
            stored=np.full((8, 8), 100 + index, dtype=np.int16),
        )
        dataset = pydicom.dcmread(path)
        # One physical series: all slices share the study/series UIDs.
        dataset.StudyInstanceUID = study_uid
        dataset.SeriesInstanceUID = series_uid
        dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        dataset.ImagePositionPatient = [0, 0, z]
        dataset.save_as(path)
        paths.append(path)

    before = order_dicom_files(paths)
    assert [paths.index(p) for p in before] == [1, 2, 0]  # z = 0, 1, 2

    # Re-serialize every object (an PACS-style rewrite) and re-order again.
    rewritten = []
    for path in before:
        dataset = pydicom.dcmread(path)
        out = str(path) + ".re.dcm"
        dataset.save_as(out, enforce_file_format=True)
        rewritten.append(out)
    after = order_dicom_files(rewritten)
    assert [p[:-7] for p in after] == before

    # Every re-serialized object still loads through the app's own loader.
    app = ClinicalApp()
    for path in rewritten:
        data, uid, modality = app._load_image(path)
        assert isinstance(data, np.ndarray)
        assert "DICOM" in modality
        assert uid != "unknown_uid"


def test_composite_annotation_metadata_round_trip():
    """PNG tEXt measurement payload survives re-read bit-for-bit."""
    from app import ClinicalApp

    rec = _measurement("distance", {"x1": 1.0, "y1": 2.0, "x2": 4.0, "y2": 6.0},
                       mm=5.0, px=5.0)
    annotated = _annotated_png(rec)
    metadata = ClinicalApp._read_measurement_composite_metadata(
        io.BytesIO(annotated)
    )
    assert metadata.get("measurement_composite") is True
    payload = metadata["measurement_payload"]
    assert payload["schema"] == "measurement-annotation"
    assert payload["ucum_units"] is True
    stored = payload["measurements"][0]
    assert stored["coords_px"] == [1.0, 2.0, 4.0, 6.0]
    assert stored["value"] == pytest.approx(5.0, rel=1e-9)
    assert stored["unit"] == "mm"


# ---------------------------------------------------------------------------
# 4. Package-level export validation (DICOM objects inside the export ZIP)
# ---------------------------------------------------------------------------

def _validated_archive(products):
    from app import ClinicalApp
    from core.export_validation import validate_export_archive

    manifest = ClinicalApp._export_standards_manifest(
        products, source="round-trip", measurement_count=len(products)
    )
    products = [*products, {
        "data": manifest, "file_name": "export_manifest.json",
        "mime": "application/json",
    }]
    archive = ClinicalApp._build_export_zip(products, zip_name="roundtrip")
    assert archive
    result = validate_export_archive(archive)
    assert result["ok"], result["errors"]
    return archive, result


def test_package_level_export_validation_of_dicom_sr():
    """A de-identified SR passes the toolkit's own archive gate."""
    payload = _sr_bytes(
        [_measurement("distance", {"x1": 1.0, "y1": 1.0, "x2": 2.0, "y2": 2.0},
                      mm=1.4142135623730951, px=1.4142135623730951)]
    )
    products = [{"data": payload, "file_name": "report.dcm",
                 "mime": "application/dicom"}]
    archive, _result = _validated_archive(products)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = set(bundle.namelist())
    assert {"report.dcm", "export_manifest.json"} <= names


def test_package_level_export_validation_of_mixed_exports(tmp_path):
    """DICOM + annotated PNG export together pass the archive gate."""
    source_path, _ = _make_source_ct(tmp_path)
    with open(source_path, "rb") as handle:
        source_bytes = handle.read()
    annotated = _annotated_png(
        _measurement("distance", {"x1": 1.0, "y1": 1.0, "x2": 5.0, "y2": 1.0},
                     mm=2.0, px=4.0)
    )
    products = [
        {"data": source_bytes, "file_name": "source.dcm",
         "mime": "application/dicom"},
        {"data": annotated, "file_name": "annotated.png", "mime": "image/png"},
    ]
    _validated_archive(products)


# ---------------------------------------------------------------------------
# 5. Declared dependencies must cover the API surface actually used
# ---------------------------------------------------------------------------

def test_declared_dependencies_match_runtime_api_surface():
    """requirements floors must admit the pydicom 3.x-only API surface in use."""
    from importlib import metadata

    floors = {}
    requirements_path = Path(__file__).resolve().parents[2] / "requirements.txt"
    with requirements_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = __import__("re").match(
                r"([A-Za-z0-9_.-]+)\s*>=\s*(\d+)\.(\d+)", line
            )
            if match:
                floors[match.group(1).lower()] = (
                    int(match.group(2)), int(match.group(3))
                )

    assert floors.get("pydicom") is not None
    assert floors["pydicom"] >= (3, 0), (
        "The export/ingest code path uses pydicom 3.x-only APIs "
        "(ds.save_as(enforce_file_format=True) and pydicom.filewriter."
        "write_file_meta_info replaced write_file_meta); the declared "
        "floor must be >=3.0."
    )
    installed = tuple(
        int(part) for part in metadata.version("pydicom").split(".")[:2]
    )
    assert installed >= floors["pydicom"]
    assert str(pydicom.__version__) >= "3.0"


def test_declared_floor_actually_supports_the_enforce_file_format_kwarg():
    """Behavioral proof: the kwarg distinguishing pydicom 3.x is required."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ImplicitVRLittleEndian
    ds = FileDataset("d.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "CT"
    buffer = io.BytesIO()
    # This kwarg does not exist on pydicom 2.x; a declared floor of 2.4
    # would let this call raise TypeError at runtime on fresh installs.
    ds.save_as(buffer, enforce_file_format=True)
    assert buffer.getvalue()[128:132] == b"DICM"


def test_pyproject_and_requirements_declare_the_same_dicom_floor():
    """requirements.txt and pyproject.toml must not disagree on pydicom."""
    import re as _re

    with (Path(__file__).resolve().parents[2] / "requirements.txt").open(
        "r", encoding="utf-8"
    ) as handle:
        req = [
            line.strip() for line in handle
            if line.strip().startswith("pydicom")
        ][0]
    with (Path(__file__).resolve().parents[2] / "pyproject.toml").open(
        "r", encoding="utf-8"
    ) as handle:
        text = handle.read()
    proj = _re.search(r'"(pydicom[^"]*)"', text).group(1)
    assert req == proj == "pydicom>=3.0"
