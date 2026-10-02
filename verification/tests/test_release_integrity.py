import hashlib
import subprocess
from pathlib import Path

from scripts.generate_sha256_manifest import build_manifest


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sha256_manifest_matches_repository_files():
    manifest = (_REPO_ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8")

    for line in manifest.splitlines():
        digest, separator, relative_path = line.partition(" *./")
        assert separator
        file_path = _REPO_ROOT / relative_path
        assert file_path.is_file()
        assert hashlib.sha256(file_path.read_bytes()).hexdigest() == digest

    git_root = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if git_root.returncode == 0:
        assert manifest == build_manifest(_REPO_ROOT)
    else:
        assert b"not a git repository" in git_root.stderr.lower()
