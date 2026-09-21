"""Offline validation helpers for HEEH-V1 export archives.

These checks are intentionally conservative.  They verify package integrity
and the project's export contract, but they do not claim regulatory or PACS
conformance.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath

from core.resource_limits import (
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_ARCHIVE_MEMBERS,
    MAX_ARCHIVE_TOTAL_BYTES,
)

_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|患者|病人)/)", re.IGNORECASE
)
_PRIVATE_PATH_MARKERS = (".neuroproject_tcia", "\\users\\", "/users/")
_TEXT_SUFFIXES = {".csv", ".html", ".json", ".txt", ".xml"}


def _is_safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def _payload(data: bytes | bytearray | memoryview | str) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    return data.encode("utf-8")


def validate_export_archive(
    archive_bytes: bytes, *, scan_nested_archives: bool = True
) -> dict:
    """Validate ZIP safety, manifest hashes, privacy markers, and units.

    The result is JSON-serializable and contains ``ok``, ``errors``, and
    ``warnings`` keys so it can be used by a CLI, tests, or the UI.
    """
    result = {
        "ok": False,
        "errors": [],
        "warnings": [],
        "files_checked": 0,
        "manifest_checked": False,
    }

    def error(code: str, message: str) -> None:
        result["errors"].append({"code": code, "message": message})

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except (OSError, zipfile.BadZipFile) as exc:
        error("INVALID_ZIP", f"Archive could not be opened: {exc}")
        return result

    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        error(
            "TOO_MANY_MEMBERS",
            f"Archive contains {len(members)} members; maximum is "
            f"{MAX_ARCHIVE_MEMBERS}.",
        )
        return result
    contents: dict[str, bytes] = {}
    total_size = 0
    for member in members:
        if not _is_safe_member(member.filename):
            error("UNSAFE_MEMBER", member.filename)
            continue
        if member.is_dir():
            continue
        if member.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            error("MEMBER_TOO_LARGE", member.filename)
            continue
        total_size += member.file_size
        if total_size > MAX_ARCHIVE_TOTAL_BYTES:
            error("ARCHIVE_TOO_LARGE", "Total uncompressed archive size exceeded.")
            break
        try:
            contents[member.filename] = archive.read(member)
            result["files_checked"] += 1
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            error("UNREADABLE_MEMBER", f"{member.filename}: {exc}")

    manifest_names = [
        name for name in contents if name.lower().endswith("export_manifest.json")
    ]
    if not manifest_names:
        error("MISSING_MANIFEST", "Archive does not contain export_manifest.json")
    for manifest_name in manifest_names:
        try:
            manifest = json.loads(contents[manifest_name].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            error("INVALID_MANIFEST", f"{manifest_name}: {exc}")
            continue
        result["manifest_checked"] = True
        manifest_files = set()
        for entry in manifest.get("files", []):
            name = str(entry.get("file") or "")
            manifest_files.add(name)
            if name not in contents:
                error("MISSING_MANIFEST_FILE", name)
                continue
            expected = str(entry.get("sha256") or "")
            actual = hashlib.sha256(contents[name]).hexdigest()
            if expected != actual:
                error("MANIFEST_HASH_MISMATCH", name)
        manifest_only = {
            name for name in contents
            if name != manifest_name
            and not name.lower().endswith("export_manifest.json")
        }
        for name in sorted(manifest_only - manifest_files):
            error("UNMANIFESTED_FILE", name)

    for name, data in contents.items():
        suffix = PurePosixPath(name).suffix.lower()
        if suffix == ".dcm":
            try:
                import pydicom
                from pydicom.errors import InvalidDicomError

                dataset = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
                if str(getattr(dataset, "Modality", "")) == "SR":
                    if not getattr(dataset, "ContentSequence", None):
                        error("EMPTY_DICOM_SR", name)
            except (ImportError, InvalidDicomError, OSError, ValueError, TypeError) as exc:
                error("INVALID_DICOM", f"{name}: {type(exc).__name__}")
            continue
        if suffix not in _TEXT_SUFFIXES:
            continue
        text = data.decode("utf-8", errors="replace")
        if _LOCAL_PATH_RE.search(text) or any(
            marker in text.lower() for marker in _PRIVATE_PATH_MARKERS
        ):
            error("LOCAL_PATH_LEAK", name)
        if name.lower().endswith("measurements.json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                error("INVALID_MEASUREMENT_JSON", f"{name}: {exc}")
                continue
            for index, item in enumerate(payload.get("measurements", [])):
                kind = str(item.get("kind") or "").lower()
                unit = str(item.get("unit") or "").lower()
                if kind == "angle":
                    if unit != "deg" or item.get("mm") is not None:
                        error(
                            "ANGLE_UNIT_SEMANTICS",
                            f"{name}: measurement {index + 1} must use deg and no mm",
                        )
                elif kind == "distance" and unit == "deg":
                    error(
                        "DISTANCE_UNIT_SEMANTICS",
                        f"{name}: measurement {index + 1} cannot use deg",
                    )
        if name.lower().endswith(".csv") and "millimeters" in text.splitlines()[0].lower():
            error("AMBIGUOUS_CSV_SCHEMA", f"{name}: use physical_distance_mm instead")
        if name.lower().endswith("cohort_metrics.csv"):
            header = {field.strip() for field in text.splitlines()[0].split(",")}
            required = {"status", "error_code", "error_message", "source_hash"}
            missing = sorted(required - header)
            if missing:
                error("INCOMPLETE_COHORT_SCHEMA", f"{name}: missing {missing}")

    if scan_nested_archives:
        for name, data in contents.items():
            if name.lower().endswith(".zip"):
                nested = validate_export_archive(data, scan_nested_archives=False)
                result["errors"].extend(nested["errors"])
                result["warnings"].extend(nested["warnings"])

    result["ok"] = not result["errors"]
    return result
