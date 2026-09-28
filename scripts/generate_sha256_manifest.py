"""Generate or verify the repository snapshot SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_PATH = Path("SHA256SUMS.txt")


def build_manifest(root: Path = _REPOSITORY_ROOT) -> str:
    """Hash versioned and non-ignored additions using repository checkout bytes."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = {
        path.decode("utf-8") for path in result.stdout.split(b"\0") if path
    }
    paths.discard(_MANIFEST_PATH.as_posix())

    entries = []
    for relative_path in sorted(paths):
        file_path = root / relative_path
        if not file_path.is_file():
            raise FileNotFoundError(f"Cannot checksum missing repository file: {relative_path}")
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        entries.append(f"{digest} *./{relative_path}")
    return "\n".join(entries) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify SHA256SUMS.txt without changing it",
    )
    args = parser.parse_args()

    manifest_path = _REPOSITORY_ROOT / _MANIFEST_PATH
    expected = build_manifest()
    if args.check:
        actual = manifest_path.read_text(encoding="utf-8")
        if actual != expected:
            parser.error("SHA256SUMS.txt is stale; run this script without --check")
        print("SHA256SUMS.txt is current.")
        return 0

    manifest_path.write_text(expected, encoding="utf-8")
    print(f"Updated {_MANIFEST_PATH} with {len(expected.splitlines())} file hashes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
