"""HTML output helpers — safe rendering for Streamlit.

All HTML emitted by the UI flows through this module.  The helpers:
  1.  Escape user-supplied text to prevent XSS.
  2.  Wrap content in semantic, ARIA-attributed containers.
  3.  Return plain strings (safe for ``st.markdown``).

Usage::

    from core.ui_helpers import (safe_diag_box, safe_metric_label, safe_img_alt,
                                 safe_stat_card, safe_landmark,
                                 keyboard_hint, onboarding_step)
    st.markdown(safe_diag_box("info", "System ready."), unsafe_allow_html=True)
"""
from __future__ import annotations

import html as _html


def esc(text: object) -> str:
    """HTML-escape *text*.  Returns empty string for None."""
    if text is None:
        return ""
    return _html.escape(str(text))


def format_count_with_percent(count: int, total: int) -> str:
    """Format a count with its denominator and percentage.

    Percentages are only shown when the denominator is positive so an empty
    ROI cannot produce a misleading ``0.0%`` measurement.
    """
    count = int(count)
    total = int(total)
    if total <= 0:
        return f"{count:,} / 0"
    percentage = 100.0 * count / total
    return f"{count:,} / {total:,} ({percentage:.1f}%)"


# ---- Semantic HTML helpers ----

def safe_diag_box(kind: str, title: str, body: str = "",
                  role: str = "status") -> str:
    """Return a WCAG-safe diagnostic box with ARIA role.

    Parameters
    ----------
    kind : ``"info" | "success" | "warning" | "error"``
    title : short label displayed in bold
    body  : optional detail paragraph
    role  : ARIA role (default ``"status"``; use ``"alert"`` for errors)
    """
    cls = f"diag-box diag-box--{esc(kind)}"
    title_html = f"<strong>{esc(title)}</strong>"
    body_html = f"<p>{esc(body)}</p>" if body else ""
    return (f'<div class="{cls}" role="{esc(role)}" '
            f'aria-live="polite">{title_html}{body_html}</div>')


def safe_metric_block(label: str, value: str,
                      help_text: str = "",
                      delta: str = "") -> str:
    """Return an accessible metric block with ``aria-label``."""
    aria = f"{label}: {value}"
    if help_text:
        aria += f" ({help_text})"
    help_html = (f'<small style="color:var(--text-caption);display:block;'
                 f'margin-top:2px">{esc(help_text)}</small>') if help_text else ""
    delta_html = (f'<span style="color:var(--color-success);font-size:0.8em">'
                  f'{esc(delta)}</span>') if delta else ""
    return (
        f'<div role="group" aria-label="{esc(aria)}" '
        f'style="background:var(--bg-surface);border:1px solid var(--border-subtle);'
        f'border-radius:var(--radius-md);padding:12px 16px;margin-bottom:8px;">'
        f'<div style="color:var(--text-muted);font-size:0.85em;">{esc(label)}</div>'
        f'<div style="color:var(--text-primary);font-size:1.15em;font-weight:600;">'
        f'{esc(value)}{delta_html}</div>'
        f'{help_html}'
        f'</div>'
    )


def safe_img_alt(caption: str, modality: str = "",
                 extra: str = "") -> str:
    """Build an ARIA-friendly ``alt``/``title`` string for medical images.

    Example output::

        "CT Brain scan — axial slice. ROI: Brain tissue."
    """
    parts = [caption]
    if modality:
        parts.append(modality)
    if extra:
        parts.append(extra)
    return " — ".join(parts)


def safe_section_heading(level: int, text: str) -> str:
    """Return a semantic heading tag with proper ARIA level."""
    level = max(1, min(level, 6))
    tag = f"h{level}"
    return (f'<{tag} role="heading" aria-level="{level}" '
            f'style="color:var(--text-primary);margin:16px 0 8px;">'
            f'{esc(text)}</{tag}>')


def safe_skip_link(target_id: str = "main-content",
                   label: str = "Skip to main content") -> str:
    """Return the skip-navigation link (WCAG 2.4.1)."""
    return (f'<a href="#{esc(target_id)}" class="skip-link">'
            f'{esc(label)}</a>')


# ---- Additional accessible helpers ----

def safe_stat_card(label: str, value: str,
                   help_text: str = "") -> str:
    """Return an accessible stat/metric card (``role="group"``).

    Simpler than :func:`safe_metric_block` — displays a label, a value,
    and an optional help hint.  Uses theme CSS variables for styling.
    """
    aria = f"{label}: {value}"
    if help_text:
        aria += f" ({help_text})"
    help_html = (f'<div style="color:var(--text-muted);font-size:0.8em;'
                 f'margin-top:4px;">{esc(help_text)}</div>') if help_text else ""
    return (
        f'<div role="group" aria-label="{esc(aria)}" '
        f'style="background:var(--bg-surface);'
        f'border:1px solid var(--border-subtle);'
        f'border-radius:var(--radius-md);padding:12px 16px;">'
        f'<div style="color:var(--text-muted);font-size:0.85em;">'
        f'{esc(label)}</div>'
        f'<div style="color:var(--text-primary);font-size:1.1em;'
        f'font-weight:600;">{esc(value)}</div>'
        f'{help_html}'
        f'</div>'
    )


def safe_landmark(tag: str, role: str,
                  aria_label: str = "", inner: str = "") -> str:
    """Wrap *inner* (trusted markup) in a semantic landmark element.

    Parameters
    ----------
    tag       : HTML tag name, e.g. ``"section"`` or ``"main"``.
    role      : ARIA role, e.g. ``"region"``.
    aria_label: optional accessible label (escaped automatically).
    inner     : already-escaped HTML to embed as-is.
    """
    safe_tag = esc(tag)
    label_attr = (f' aria-label="{esc(aria_label)}"'
                  if aria_label else "")
    return f'<{safe_tag} role="{esc(role)}"{label_attr}>{inner}</{safe_tag}>'


def keyboard_hint(keys: list[str], description: str) -> str:
    """Return a small ``<kbd>`` shortcut hint for *description*.

    Example::

        keyboard_hint(["Ctrl", "L"], "lang")
        # → <span class="keyboard-hint">lang: <kbd>Ctrl</kbd>+<kbd>L</kbd></span>
    """
    kbd_parts = "+".join(f"<kbd>{esc(k)}</kbd>" for k in keys)
    return (f'<span class="keyboard-hint">'
            f'{esc(description)}: {kbd_parts}'
            f'</span>')


def onboarding_step(number: int, title: str, body: str) -> str:
    """Return a numbered onboarding step (``role="listitem"``).

    Includes a screen-reader-only step number for accessibility.
    """
    return (
        f'<div class="onboarding-step" role="listitem" '
        f'style="background:var(--bg-surface);'
        f'border:1px solid var(--border-subtle);'
        f'border-radius:var(--radius-md);padding:12px 16px;'
        f'margin-bottom:8px;">'
        f'<span class="sr-only">Step {esc(number)}:</span>'
        f'<strong style="color:var(--text-primary);">'
        f'{esc(title)}</strong>'
        f'<div style="color:var(--text-muted);margin-top:4px;">'
        f'{esc(body)}</div>'
        f'</div>'
    )
