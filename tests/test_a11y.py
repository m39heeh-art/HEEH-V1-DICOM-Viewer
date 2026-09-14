"""Unit tests for core.a11y accessibility helpers."""
import pytest

from core.a11y import (
    build_img_alt,
    contrast_ratio,
    lang_attr,
    passes_aa,
    rtl_dir,
    shortcuts_help,
)


# ---------- rtl_dir ----------

@pytest.mark.parametrize("lang", ["ar", "he", "fa", "ur"])
def test_rtl_dir_returns_rtl(lang):
    assert rtl_dir(lang) == "rtl"


@pytest.mark.parametrize("lang", ["en", "es", "fr", "de", "zh"])
def test_rtl_dir_returns_ltr(lang):
    assert rtl_dir(lang) == "ltr"


# ---------- lang_attr ----------

@pytest.mark.parametrize("lang,expected", [
    ("ar", ' lang="ar" dir="rtl"'),
    ("he", ' lang="he" dir="rtl"'),
    ("fa", ' lang="fa" dir="rtl"'),
    ("ur", ' lang="ur" dir="rtl"'),
    ("en", ' lang="en" dir="ltr"'),
    ("es", ' lang="es" dir="ltr"'),
])
def test_lang_attr(lang, expected):
    assert lang_attr(lang) == expected


# ---------- build_img_alt ----------

def test_build_img_alt_caption_only():
    assert build_img_alt("Brain scan") == "Brain scan"


def test_build_img_alt_with_modality():
    assert build_img_alt("Brain scan", modality="CT") == "Brain scan — CT"


def test_build_img_alt_with_extra():
    assert build_img_alt("Brain scan", extra="ROI") == "Brain scan — ROI"


def test_build_img_alt_all_parts():
    assert build_img_alt("Brain scan", modality="CT", extra="ROI") == "Brain scan — CT — ROI"


def test_build_img_alt_empty_modality_and_extra():
    assert build_img_alt("Caption", modality="", extra="") == "Caption"


def test_build_img_alt_omits_empty_middle():
    assert build_img_alt("Caption", modality="", extra="extra") == "Caption — extra"


# ---------- contrast_ratio ----------

def test_white_vs_black():
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)


def test_black_vs_white():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)


def test_dark_theme_text_passes():
    ratio = contrast_ratio("#E0E0E0", "#0B0D10")
    assert ratio >= 4.5
    assert passes_aa(ratio, normal_text=True)


def test_low_contrast_fails():
    ratio = contrast_ratio("#666666", "#0A0A0A")
    assert ratio < 4.5
    assert not passes_aa(ratio, normal_text=True)


def test_hex3_vs_hex6():
    assert contrast_ratio("#FFF", "#000") == pytest.approx(21.0)


def test_same_color_ratio():
    assert contrast_ratio("#808080", "#808080") == pytest.approx(1.0)


# ---------- passes_aa ----------

def test_passes_aa_normal_above():
    assert passes_aa(4.5, normal_text=True) is True


def test_passes_aa_normal_below():
    assert passes_aa(4.49, normal_text=True) is False


def test_passes_aa_large_above():
    assert passes_aa(3.0, normal_text=False) is True


def test_passes_aa_large_below():
    assert passes_aa(2.99, normal_text=False) is False


# ---------- shortcuts_help ----------

def test_shortcuts_help_returns_string():
    result = shortcuts_help()
    assert isinstance(result, str)
    assert "Ctrl+L" in result
    assert "Ctrl+O" in result
    assert "Ctrl+1..4" in result
