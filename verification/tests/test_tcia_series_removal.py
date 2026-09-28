"""Regression locks: TCIA "Series to download" add/remove/re-add cycle.

Defect under test: a download group that was added and then de-selected kept
rendering in the interface (the caller treated the flow's empty return as a
transient empty read and resurrected the stale active-input snapshot), and
re-adding the same group duplicated its files (the download loop extended
the file list once per selected label with no UID dedup).

The fix introduces an explicit deselection marker (``_tcia_removal_requested``),
an explicit-removal path in the caller (mirroring the uploader's on_change
removal handling), UID-level de-duplication of the selection, and a
resolved-path de-duplication of the returned file list.
"""

import csv
import io
import sys
import tempfile
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from app import ClinicalApp  # noqa: E402


class _FakeEl:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


_ROWS = [{
    "SeriesInstanceUID": "1.2.3.4",
    "Modality": "CT",
    "SeriesDescription": "Test series",
    "ImageCount": "2",
    "FileSize": "1024",
}]
_LABEL = "[CT] Test series | 2 imgs | 1 KB | 1.2.3.4"


class _State(dict):
    """dict with attribute access, mimicking Streamlit's SessionStateProxy
    (app code uses both st.session_state["key"] and st.session_state.key)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture()
def flow_env(monkeypatch):
    """Redirect st.session_state + UI calls and stub the network layer."""
    state = _State({
        "_uploads_present": True,
        "_active_input_files": ["/cached/A/file1.dcm", "/cached/A/file2.dcm"],
        "_active_input_fingerprint": "FP_A",
        "tcia_download_details": {},
    })

    def fake_fetch(self, series_uids, cache_dir):
        path = Path(tempfile.mkdtemp()) / "meta.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(_ROWS[0].keys())
            )
            writer.writeheader()
            writer.writerows(_ROWS)
        return str(path)

    def fake_download(self, uid, dest_dir, expected_bytes=None,
                      progress_cb=None):
        target = Path(dest_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "file1.dcm").write_bytes(b"x")
        (target / "file2.dcm").write_bytes(b"y")
        (target / ".series.complete").write_bytes(b"")
        return [str(target / "file1.dcm"), str(target / "file2.dcm")]

    monkeypatch.setattr(
        ClinicalApp, "_fetch_tcia_metadata", fake_fetch
    )
    monkeypatch.setattr(
        ClinicalApp, "_download_tcia_series", fake_download
    )

    saved = {
        name: getattr(st, name)
        for name in vars(st)
        if not name.startswith("__")
    }
    st.session_state = state
    app = ClinicalApp()
    manifest = io.BytesIO(b"1.2.3.4\n")
    manifest.name = "study.tcia"
    cache_root = Path(tempfile.mkdtemp())
    try:
        yield types.SimpleNamespace(
            state=state,
            app=app,
            manifest=manifest,
            cache_root=cache_root,
        )
    finally:
        for name, value in saved.items():
            setattr(st, name, value)


def _install_ui(selection, submit):
    shim = types.ModuleType("streamlit_tcia_shim")
    for name in ("sidebar", "error", "info", "warning", "success", "caption",
                 "markdown", "write", "toast", "subheader", "progress",
                 "form", "expander"):
        setattr(shim, name, _FakeEl())
    shim.selectbox = lambda *args, **kwargs: "A"

    def multiselect(label, options, default=None, **kwargs):
        if label == "Modality filter":
            return list(options)
        return selection

    shim.multiselect = multiselect
    shim.form_submit_button = lambda *args, **kwargs: submit
    for name, value in vars(shim).items():
        if not name.startswith("__"):
            setattr(st, name, value)


def test_add_downloads_and_returns_files(flow_env):
    env = flow_env
    _install_ui([_LABEL], True)
    files = env.app._run_tcia_manifest_flow(env.manifest, env.cache_root)
    assert len(files) == 2
    assert len(set(files)) == len(files)


def test_deselection_returns_empty_and_marks_removal(flow_env):
    env = flow_env
    _install_ui([], True)
    files = env.app._run_tcia_manifest_flow(env.manifest, env.cache_root)
    assert files == []
    assert env.state.get("_tcia_removal_requested") is True


def test_waiting_state_does_not_mark_removal(flow_env):
    """Selecting nothing without submitting is a waiting state, not a
    removal; the caller must keep the active snapshot in that case."""
    env = flow_env
    _install_ui([], False)
    files = env.app._run_tcia_manifest_flow(env.manifest, env.cache_root)
    assert files == []
    assert "_tcia_removal_requested" not in env.state


def test_duplicate_labels_collapse_to_one_download(flow_env):
    """Sparse metadata can map several labels to the SAME series; selecting
    them together must download once and never duplicate images."""
    env = flow_env

    def fake_fetch_dup(self, series_uids, cache_dir):
        path = Path(tempfile.mkdtemp()) / "meta.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(_ROWS[0].keys())
            )
            writer.writeheader()
            writer.writerows(_ROWS * 2)  # same UID row twice
        return str(path)

    import app as app_module

    app_module.ClinicalApp._fetch_tcia_metadata = fake_fetch_dup
    _install_ui([_LABEL, _LABEL + " "], True)
    files = env.app._run_tcia_manifest_flow(env.manifest, env.cache_root)
    assert len(files) == 2
    assert len(set(files)) == len(files)


def test_caller_removal_path_clears_the_active_snapshot(flow_env):
    """The caller-side branch (mirrored from run()): an empty return plus
    the deselection marker must clear the active-input snapshot and set the
    explicit-removal flag, so the interface no longer renders the group."""
    env = flow_env
    _install_ui([], True)
    files = env.app._run_tcia_manifest_flow(env.manifest, env.cache_root)
    assert files == []
    if not files and env.state.pop("_tcia_removal_requested", None):
        env.state["_uploads_present"] = False
        ClinicalApp._discard_persisted_uploads()
    assert env.state.get("_uploads_present") is False
    assert env.state.get("_active_input_files") is None
    assert env.state.get("_active_input_fingerprint") is None
