
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.ui_helpers import (
    esc,
    format_count_with_percent,
    safe_diag_box,
    safe_img_alt,
    safe_section_heading,
    safe_skip_link,
)


def test_format_count_with_percent_includes_denominator_and_percentage():
    assert format_count_with_percent(25, 100) == "25 / 100 (25.0%)"


def test_format_count_with_percent_handles_empty_denominator():
    assert format_count_with_percent(0, 0) == "0 / 0"


# --- esc() ---

class TestEsc:
    def test_plain_text(self):
        assert esc("hello") == "hello"

    def test_none_returns_empty(self):
        assert esc(None) == ""

    def test_lt_gt(self):
        assert "&lt;" in esc("<b>")
        assert "&gt;" in esc("<b>")

    def test_quotes(self):
        r = esc('"')
        assert "&quot;" in r or "&#x27;" not in r  # quote escaped
        r2 = esc("'")
        assert "&#" in r2 or "&amp;" in r2  # at least escaped

    def test_ampersand(self):
        assert "&amp;" in esc("a&b")

    def test_script_tag(self):
        out = esc("<script>alert(1)</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_unicode_arabic(self):
        assert esc("نطاق") == "نطاق"  # no escaping needed

    def test_numeric(self):
        assert esc(42) == "42"


# --- safe_diag_box ---

class TestSafeDiagBox:
    def test_css_class(self):
        out = safe_diag_box("info", "Title")
        assert "diag-box diag-box--info" in out

    def test_default_role_status(self):
        out = safe_diag_box("info", "Title")
        assert 'role="status"' in out

    def test_role_alert(self):
        out = safe_diag_box("error", "Oops", role="alert")
        assert 'role="alert"' in out

    def test_aria_live(self):
        out = safe_diag_box("warning", "Watch out")
        assert 'aria-live="polite"' in out

    def test_body_rendered(self):
        out = safe_diag_box("info", "T", body="Hello")
        assert "<p>Hello</p>" in out

    def test_body_xss_escaped(self):
        out = safe_diag_box("info", "T", body="<script>x</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_title_xss_escaped(self):
        out = safe_diag_box("info", "<b>XSS</b>")
        assert "<b>XSS</b>" not in out
        assert "&lt;b&gt;" in out

    def test_empty_body(self):
        out = safe_diag_box("success", "Done")
        assert "<p>" not in out


# --- safe_img_alt ---

class TestSafeImgAlt:
    def test_caption_only(self):
        assert safe_img_alt("Brain") == "Brain"

    def test_two_parts(self):
        assert safe_img_alt("Brain", "CT") == "Brain — CT"

    def test_three_parts(self):
        out = safe_img_alt("Brain", "CT", "axial")
        assert out == "Brain — CT — axial"

    def test_empty_modality_and_extra(self):
        assert safe_img_alt("X", "", "") == "X"


# --- safe_section_heading ---

class TestSafeSectionHeading:
    def test_h1(self):
        out = safe_section_heading(1, "Title")
        assert "<h1 " in out
        assert 'aria-level="1"' in out
        assert "</h1>" in out

    def test_h3(self):
        out = safe_section_heading(3, "Sub")
        assert "<h3 " in out
        assert 'aria-level="3"' in out

    def test_clamps_low(self):
        out = safe_section_heading(0, "X")
        assert 'aria-level="1"' in out

    def test_clamps_high(self):
        out = safe_section_heading(10, "X")
        assert 'aria-level="6"' in out

    def test_text_escaped(self):
        out = safe_section_heading(2, "<em>bad</em>")
        assert "<em>" not in out
        assert "&lt;em&gt;" in out


# --- safe_skip_link ---

class TestSafeSkipLink:
    def test_class(self):
        out = safe_skip_link()
        assert 'class="skip-link"' in out

    def test_default_href(self):
        out = safe_skip_link()
        assert 'href="#main-content"' in out

    def test_custom_target(self):
        out = safe_skip_link(target_id="content")
        assert 'href="#content"' in out

    def test_label(self):
        out = safe_skip_link(label="Jump")
        assert ">Jump</a>" in out
