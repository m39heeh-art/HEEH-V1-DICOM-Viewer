import subprocess
from pathlib import Path

from scripts.generate_sha256_manifest import build_manifest, sha256_digest


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sha256_manifest_matches_repository_files():
    manifest = (_REPO_ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8")

    for line in manifest.splitlines():
        digest, separator, relative_path = line.partition(" *./")
        assert separator
        file_path = _REPO_ROOT / relative_path
        assert file_path.is_file()
        assert sha256_digest(file_path.read_bytes()) == digest

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


def test_sha256_digest_normalizes_text_line_endings_only():
    assert sha256_digest(b"first\r\nsecond\r\n") == sha256_digest(
        b"first\nsecond\n"
    )
    assert sha256_digest(b"\0first\r\nsecond") == sha256_digest(
        b"\0first\r\nsecond"
    )
