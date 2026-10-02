from pathlib import Path

from scripts.generate_sha256_manifest import build_manifest


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sha256_manifest_matches_repository_files():
    manifest = (_REPO_ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8")

    assert manifest == build_manifest(_REPO_ROOT)
