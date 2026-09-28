"""Resource limits for untrusted image, archive, and manifest inputs."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


MAX_UPLOAD_FILES = _env_int("HEEH_MAX_UPLOAD_FILES", 256)
MAX_UPLOAD_FILE_BYTES = _env_int("HEEH_MAX_UPLOAD_FILE_BYTES", 512 * 1024**2)
MAX_UPLOAD_TOTAL_BYTES = _env_int("HEEH_MAX_UPLOAD_TOTAL_BYTES", 2 * 1024**3)
MAX_ARCHIVE_MEMBERS = _env_int("HEEH_MAX_ARCHIVE_MEMBERS", 10_000)
MAX_ARCHIVE_MEMBER_BYTES = _env_int(
    "HEEH_MAX_ARCHIVE_MEMBER_BYTES", 512 * 1024**2
)
MAX_ARCHIVE_TOTAL_BYTES = _env_int("HEEH_MAX_ARCHIVE_TOTAL_BYTES", 10 * 1024**3)
MAX_MANIFEST_ROWS = _env_int("HEEH_MAX_MANIFEST_ROWS", 10_000)
MAX_MANIFEST_TOTAL_BYTES = _env_int(
    "HEEH_MAX_MANIFEST_TOTAL_BYTES", 2 * 1024**3
)
