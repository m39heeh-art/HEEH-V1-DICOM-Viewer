"""Regression locks: "Fit to panel" removed from the Viewer mode selector.

The fit-to-panel render path (letterboxed element sizing + fitScale click
mapping) was removed; viewer modes are now 1:1 / 2x / 4x at native or
integer-magnified element scale, with the bitmap always at source 1:1.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_APP_SOURCE = (
    Path(__file__).resolve().parents[2] / "app.py"
).read_text(encoding="utf-8")


def test_viewer_mode_options_no_longer_offer_fit_to_panel():
    """The selectbox must not offer the removed mode."""
    match = re.search(
        r'view_mode = st\.selectbox\(\s*"Viewer mode",\s*\[(.*?)\]',
        _APP_SOURCE,
        re.S,
    )
    assert match, "Viewer mode selectbox not found in app.py"
    options = re.findall(r'"([^"]+)"', match.group(1))
    assert options == ["1:1 pixels", "2x magnification", "4x magnification"]


def test_fit_to_panel_code_path_is_gone():
    """No fit-to-panel sizing branch, fitScale mapping, or mode constant.

    The legacy "Fit to panel" literal may appear exactly once — inside the
    session-state migration guard that pops stale values from pre-removal
    sessions — and nowhere else (options, defaults, or render path).
    """
    occurrences = _APP_SOURCE.count("Fit to panel")
    guard_line = 'if st.session_state.get("viewer_mode") == "Fit to panel":'
    assert guard_line in _APP_SOURCE
    assert occurrences == 1, (
        '"Fit to panel" must appear only in the migration guard; '
        f"found {occurrences} occurrences"
    )
    assert "fitScale" not in _APP_SOURCE
    assert "viewer_view_mode\"] = \"fit\"" not in _APP_SOURCE


def test_legacy_fit_payload_is_mapped_to_native_in_viewer_js():
    """A session from an older build may still send view_mode='fit'; the
    viewer component must present 1:1 instead of a broken fit branch."""
    js_match = re.search(r'js="""(.*?)"""', _APP_SOURCE, re.S)
    assert js_match, "component JS not found in app.py"
    assert 'data.view_mode === "fit" ? "native"' in js_match.group(1)


def test_stale_widget_value_is_migrated_before_the_selectbox():
    """Guard pops a legacy 'Fit to panel' value so older Streamlit versions
    (and hot-reloaded sessions) cannot surface a dead option."""
    idx_guard = _APP_SOURCE.index('st.session_state.get("viewer_mode")')
    idx_widget = _APP_SOURCE.index('key="viewer_mode"')
    assert idx_guard < idx_widget


def test_default_session_state_uses_1to1_not_fit():
    """Source-selection reset must default to the new default mode."""
    assert 'st.session_state["viewer_mode"] = "1:1 pixels"' in _APP_SOURCE
    assert 'st.session_state["viewer_view_mode"] = "native"' in _APP_SOURCE
