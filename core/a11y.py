"""Centralized accessibility helpers for the Streamlit app.

Pure, testable functions — no Streamlit imports at module level.
"""
from __future__ import annotations


_RTL_LANGS = frozenset({"ar", "he", "fa", "ur"})


def rtl_dir(lang: str) -> str:
    """Return ``'rtl'`` for RTL languages, else ``'ltr'``."""
    return "rtl" if lang in _RTL_LANGS else "ltr"


def lang_attr(lang: str) -> str:
    """Return an HTML attribute string ``lang="..." dir="..."``.

    Examples::

        lang_attr('ar')  # ' lang="ar" dir="rtl"'
        lang_attr('en')  # ' lang="en" dir="ltr"'
    """
    return f' lang="{lang}" dir="{rtl_dir(lang)}"'


def build_img_alt(caption: str, modality: str = "", extra: str = "") -> str:
    """Build an accessible alt string joining non-empty parts with `` — ``."""
    parts = [caption]
    if modality:
        parts.append(modality)
    if extra:
        parts.append(extra)
    return " — ".join(parts)


# ---------- WCAG contrast helpers ----------

def _srgb_to_linear(c: float) -> float:
    """Linearize a single sRGB channel value (0–1)."""
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse ``#RGB`` or ``#RRGGBB`` (case-insensitive) to (r, g, b) 0–255."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG 2.x relative luminance for linear sRGB."""
    lr = _srgb_to_linear(r / 255.0)
    lg = _srgb_to_linear(g / 255.0)
    lb = _srgb_to_linear(b / 255.0)
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb


def contrast_ratio(color1: str, color2: str) -> float:
    """Return WCAG contrast ratio between two hex colors, rounded to 2 decimals."""
    r1, g1, b1 = _hex_to_rgb(color1)
    r2, g2, b2 = _hex_to_rgb(color2)
    l1 = _relative_luminance(r1, g1, b1)
    l2 = _relative_luminance(r2, g2, b2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def passes_aa(ratio: float, normal_text: bool = True) -> bool:
    """Return True if *ratio* meets WCAG AA thresholds.

    Normal text requires ≥ 4.5; large text requires ≥ 3.0.
    """
    return ratio >= 4.5 if normal_text else ratio >= 3.0


def shortcuts_help() -> str:
    """Return a plain-text listing of keyboard shortcuts the app supports."""
    return (
        "Ctrl+L Switch language, "
        "Ctrl+O Open data path, "
        "Ctrl+1..4 toggle analysis sections"
    )
