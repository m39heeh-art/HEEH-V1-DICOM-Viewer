import io
import json
import zipfile

from core.export_validation import validate_export_archive


def _zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_export_validation_accepts_manifest_and_correct_angle_schema():
    payload = json.dumps({
        "schema": "measurement-annotation",
        "measurements": [
            {"kind": "angle", "unit": "deg", "degrees": 73.2, "mm": None}
        ],
    }).encode()
    manifest = json.dumps({
        "files": [{
            "file": "image_measurements.json",
            "sha256": __import__("hashlib").sha256(payload).hexdigest(),
        }]
    }).encode()
    result = validate_export_archive(_zip({
        "image_measurements.json": payload,
        "export_manifest.json": manifest,
    }))
    assert result["ok"]
    assert not result["errors"]


def test_export_validation_rejects_paths_and_legacy_angle_units():
    payload = b'{"measurements":[{"kind":"angle","unit":"mm","mm":73.2}]}'
    result = validate_export_archive(_zip({
        "measurements.json": payload,
        "report.html": b"C:\\Users\\patient\\source.dcm",
        "../unsafe.txt": b"bad",
    }))
    codes = {item["code"] for item in result["errors"]}
    assert "UNSAFE_MEMBER" in codes
    assert "LOCAL_PATH_LEAK" in codes
    assert "ANGLE_UNIT_SEMANTICS" in codes


def test_export_validation_requires_manifest_and_lists_all_files():
    missing = validate_export_archive(_zip({"note.txt": b"export"}))
    assert any(item["code"] == "MISSING_MANIFEST" for item in missing["errors"])

    manifest = json.dumps({"files": []}).encode()
    unlisted = validate_export_archive(_zip({
        "note.txt": b"export",
        "export_manifest.json": manifest,
    }))
    assert any(item["code"] == "UNMANIFESTED_FILE" for item in unlisted["errors"])


def test_app_export_normalizes_legacy_angle_records():
    from app import ClinicalApp

    normalized = ClinicalApp._normalized_measurement({
        "kind": "angle",
        "unit": "mm",
        "mm": 73.2,
        "data": {"x1": 1, "y1": 1, "x2": 2, "y2": 1, "x3": 1, "y3": 2},
    })
    assert normalized["unit"] == "deg"
    assert normalized["degrees"] == 73.2
    assert "mm" not in normalized
    assert "millimeters" not in normalized


def test_html_export_never_prints_a_local_source_path():
    from app import ClinicalApp

    html = ClinicalApp._build_html_research_report({
        "file_id": r"C:\Users\patient\source.dcm",
        "image_index": 1,
        "modality": "CT",
        "dicom": {},
    })
    assert r"C:\Users\patient\source.dcm" not in html
    assert "HEEH-V1™ DICOM Viewer" in html
    assert "<title>HEEH-V1™ DICOM Viewer — Research Report</title>" in html
