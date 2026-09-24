""" HEEH-V1™ DICOM Viewer -- research/education radiology analysis (NOT a medical device).

Shared analysis classes live once in core/ and engines/ (single source of
truth); this module owns the active Streamlit UI and hosts the image cache,
Multi-Domain ViT integration, ROI/MPR/3D viewers, and clinical dashboard.
"""
import csv
import atexit
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import io
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Optional
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import nibabel as nib
import numpy as np
import pydicom
import SimpleITK as sitk
import streamlit as st
import torch
import requests

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional for export-only workflows
    pd = None
import streamlit.components.v2 as components_v2
from PIL import Image, PngImagePlugin
from streamlit.errors import StreamlitAPIException
from streamlit_image_coordinates import streamlit_image_coordinates

from core.physiological_validator import PhysiologicalValidator as _PhysiologicalValidator
from core.constants import DISPLAY_PRESETS, DISPLAY_W, HU_MAX, HU_MIN
from core.branding import PRODUCT_NAME
from core.logging_config import audit_event, get_logger
from core.modality_detector import ModalityDetector, missing_required_tags
from core.dicom_ordering import order_dicom_files
from core.loaders import _load_volume_file_cached
from core.modality_registry import get_feature_capabilities
from core.standards import pseudonymous_identifier
from core.export_validation import validate_export_archive
from core.ui_helpers import (safe_diag_box, safe_section_heading,
                             safe_img_alt, safe_skip_link, safe_stat_card,
                             format_count_with_percent)
from core import i18n as _i18n
from engines.anatomical_segmentation import AnatomicalSegmentation
from engines.modality_calculators import (
    CTCalculator as _CTCalculator,
    get_calculator as _get_modality_calculator,
)
from engines.sitk_registration import SimpleITKRegistration
from core.tissue_classifier import (
    TissueClassifier, EdgeDetector, RadiomicsExtractor, XAIExplainer,
)
from core.volume_visualizer import VolumeVisualizer
from core.image_quality_metrics import (
    ImageQualityMetrics,
    LongitudinalAnalyzer,  # noqa: F401 - public compatibility export
    PerfusionAnalyzer,  # noqa: F401 - public compatibility export
)
from core.quantitative_engine import QuantitativeEngine
from core.structural_engine import StructuralEngine
from engines.onnx_inference import ONNXInferenceEngine
from engines.analysis_orchestrator import (
    AnalysisOrchestrator,  # noqa: F401 - public compatibility export
    MedicalDataProcessor,
)
from utils.medical_ai_vision import MedicalAIVisionEngine


_SESSION_TEMP_ROOTS: set[Path] = set()


def _register_session_temp_root(root: Path) -> None:
    """Track a session-owned temporary directory for process-exit cleanup."""
    _SESSION_TEMP_ROOTS.add(root.resolve())


def _cleanup_session_temp_roots() -> None:
    """Remove only temporary directories created by this application process."""
    for root in tuple(_SESSION_TEMP_ROOTS):
        if root.name.startswith(("heeh_upload_", "heeh_export_")):
            shutil.rmtree(root, ignore_errors=True)
        _SESSION_TEMP_ROOTS.discard(root)


atexit.register(_cleanup_session_temp_roots)


def _positive_timeout_from_env(name: str, default: float) -> float:
    """Read a positive HTTP timeout from the environment."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value

logger = get_logger("app")

# Per-measurement color palette (projected on the dark viewer so the
# annotation always stays readable). Colors are assigned in order and
# repeat only when more than eight measurements exist on one image.
_MEASURE_COLORS = (
    "#8ef0c8",  # mint
    "#ffd166",  # amber
    "#7fd3ff",  # sky
    "#ff9eb2",  # rose
    "#c7a2ff",  # violet
    "#9dffa0",  # spring green
    "#ffe08a",  # pale gold
    "#a6e3ff",  # ice blue
)

_PIXEL_HOVER_VIEWER = components_v2.component(
    "neuro_pixel_hover_viewer",
    html="""
    <div class="neuro-pixel-viewer">
      <div class="neuro-pixel-readout" aria-live="polite">Move over an image pixel</div>
      <div class="neuro-pixel-stage">
        <canvas class="neuro-pixel-canvas"></canvas>
      </div>
    </div>
    """,
    css="""
    .neuro-pixel-viewer {
      width: 100%; color: #d9dee8; font: 13px sans-serif; position: relative;
      margin: 0; padding: 0; line-height: 1;
    }
    .neuro-pixel-stage {
      width: 100%; max-height: min(70vh, 720px); overflow: auto;
      background: #050608; border: 1px solid #2a2e35; border-radius: 5px;
      scrollbar-color: #4a5060 #11151c;
      margin: 0; padding: 0;
    }
    .neuro-pixel-readout {
      position: absolute; top: 10px; right: 10px; z-index: 2;
      min-height: 28px; padding: 6px 10px;
      border: 1px solid #343b47; border-radius: 5px; background: #11151c;
      font-variant-numeric: tabular-nums;
    }
    .neuro-pixel-canvas {
      display: block; width: 100%; height: auto; max-width: 100%;
      object-fit: contain; background: #050608; cursor: crosshair;
      margin: 0; padding: 0;
    }
    """,
    js="""
    export default function(component) {
      const { data, parentElement, setTriggerValue } = component;
      const canvas = parentElement.querySelector(".neuro-pixel-canvas");
      const stage = parentElement.querySelector(".neuro-pixel-stage");
      const readout = parentElement.querySelector(".neuro-pixel-readout");
      if (!canvas || !stage || !readout || !data) return;
      const ctx = canvas.getContext("2d", { alpha: false });
      const image = new Image();
      const valueBytes = Uint8Array.from(atob(data.values), ch => ch.charCodeAt(0));
      const view = new DataView(valueBytes.buffer);
      const unit = data.unit || "native intensity";
      const width = Number(data.width);
      const height = Number(data.height);
      // Stable per-image token used to distinguish "navigated to another
      // image/slice" from "re-render of the same image". Zooming, panning,
      // placing measurement endpoints and adding rulers must NOT touch the
      // displayed coordinate system; only an actual image change recalibrates
      // (recenters) the viewport, so the user's zoom/pan survives interaction.
      const imageSig = String(data.image_sig || "");

      const centerStage = () => {
        stage.scrollLeft = Math.max(0, (stage.scrollWidth - stage.clientWidth) / 2);
        stage.scrollTop = Math.max(0, (stage.scrollHeight - stage.clientHeight) / 2);
      };

      // ---- Research measuring mode ---------------------------------------
      // Click coordinates are source-pixel indices (see pixelAt), so the
      // Python side converts them to physical units using DICOM PixelSpacing.
      // Drawn lines are overlays only; the pixel buffer is never modified.
      const measureMode = String(data.measure_mode || "off");
      const measureLines = Array.isArray(data.measure_lines) ? data.measure_lines : [];
      const spacing = Array.isArray(data.pixel_spacing_mm)
        && data.pixel_spacing_mm.length >= 2
        ? [Number(data.pixel_spacing_mm[0]), Number(data.pixel_spacing_mm[1])]
        : null;
      let pendingStart = null;   // distance mode: first vertex
      let pendingPoints = [];    // angle mode: collected vertices

      const strokeW = () => Math.max(1, Math.round(Math.max(width, height) / 700));

      const drawFrame = () => {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(image, 0, 0, width, height);
        if (measureLines.length === 0) return;
        const lw = strokeW();
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.textBaseline = "bottom";
        measureLines.forEach((line) => {
          const color = line.color || "#8ef0c8";
          // Keep strictly to the user's clicked points: only finite
          // coordinates are vertices. Distance measurements carry x3/y3
          // = null, and an unguarded null would otherwise pull the ruler
          // toward the (0,0) corner on every redraw (e.g. slice refresh).
          const coords = [line.x1, line.y1, line.x2, line.y2, line.x3, line.y3];
          const vertices = [];
          for (let i = 0; i + 1 < coords.length; i += 2) {
            const x = coords[i];
            const y = coords[i + 1];
            if (x === undefined || x === null || Number.isNaN(x)) continue;
            if (y === undefined || y === null || Number.isNaN(y)) continue;
            vertices.push([Number(x), Number(y)]);
          }
          if (vertices.length < 2) return; // partial measurement: nothing to draw
          // Ruler segment(s) drawn in the measurement's own color.
          ctx.strokeStyle = color;
          ctx.lineWidth = lw;
          ctx.beginPath();
          ctx.moveTo(vertices[0][0] + 0.5, vertices[0][1] + 0.5);
          for (let i = 1; i < vertices.length; i += 1) {
            ctx.lineTo(vertices[i][0] + 0.5, vertices[i][1] + 0.5);
          }
          ctx.stroke();
          // Endpoint cross markers keep the exact source pixels visible so a
          // measured value can always be traced back to its endpoints.
          ctx.fillStyle = color;
          ctx.strokeStyle = "rgba(5,6,8,0.9)";
          ctx.lineWidth = 1;
          vertices.forEach((v) => {
            const cx = v[0] + 0.5;
            const cy = v[1] + 0.5;
            const r = Math.max(2, lw + 1);
            ctx.fillRect(cx - r, cy - 1, r * 2, 2);
            ctx.fillRect(cx - 1, cy - r, 2, r * 2);
          });
          // Measurement values are drawn once in the edge legend below, so
          // rulers may cross freely without ever hiding each other's number.
        });

        // Compact legend pinned to the top-right edge of the image. One row per
        // ruler in measurement order, colored to match the ruler it belongs
        // to. Rows flow top-to-bottom and, when the panel would exceed the
        // canvas height, into extra columns from right to left so every value
        // stays readable no matter how closely the rulers crowd or cross.
        const truncate = (text, maxW) => {
          if (ctx.measureText(text).width <= maxW) return text;
          let t = text;
          while (t.length > 1 && ctx.measureText(`${t}…`).width > maxW) {
            t = t.slice(0, -1);
          }
          return `${t}…`;
        };
        const padX = 10;
        const padY = 9;
        const rowGap = 5;
        const colGap = 12;
        const baseFont = Math.max(11, Math.round(width / 95));
        const minFont = 9;
        const rowsTotal = measureLines.length;
        const colRowsFor = (f) =>
          Math.max(1, Math.floor((height - 16 - padY * 2) / (f + rowGap)));
        const oneColFits = (rows) => colRowsFor(minFont) >= rows
          || colRowsFor(baseFont) >= rows;
        let legendFont = oneColFits(rowsTotal) ? baseFont : minFont;
        const colRows = colRowsFor(legendFont);
        const nCols = Math.max(1, Math.ceil(rowsTotal / colRows));
        const widthBudget = Math.max(
          86,
          Math.floor((width - 16 - padX * 2 - colGap * (nCols - 1)) / nCols),
        );
        const maxTextW = Math.min(
          Math.max(130, Math.round(width * 0.55)) - padX * 2,
          widthBudget,
        );
        ctx.save();
        ctx.font = `600 ${legendFont}px sans-serif`;
        const rows = [];
        let widest = 0;
        measureLines.forEach((line, i) => {
          const color = line.color || "#8ef0c8";
          const text = truncate(line.label, maxTextW);
          rows.push({ text, color });
          widest = Math.max(widest, ctx.measureText(text).width);
        });
        const colW = Math.max(widest, 40);
        const panelW = Math.min(
          colW * nCols + colGap * (nCols - 1) + padX * 2,
          width - 16,
        );
        const panelLeft = width - panelW - 8;
        const panelTop = 8;
        const panelHTotal = Math.min(colRows, rowsTotal)
          * (legendFont + rowGap) + padY * 2;
        ctx.fillStyle = "rgba(17,21,28,0.85)";
        ctx.strokeStyle = "rgba(180,190,205,0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (typeof ctx.roundRect === "function") {
          ctx.roundRect(panelLeft, panelTop, panelW, panelHTotal, 6);
        } else {
          ctx.rect(panelLeft, panelTop, panelW, panelHTotal);
        }
        ctx.fill();
        ctx.stroke();
        ctx.lineJoin = "round";
        ctx.textAlign = "right";
        ctx.textBaseline = "bottom";
        const xRight = (col) =>
          panelLeft + panelW - padX - col * (colW + colGap);
        rows.forEach((row, i) => {
          const col = Math.floor(i / colRows);
          const r = i % colRows;
          const y = panelTop + padY + legendFont + r * (legendFont + rowGap);
          ctx.lineWidth = Math.max(3, lw + 2);
          ctx.strokeStyle = "rgba(5,6,8,0.9)";
          ctx.strokeText(row.text, xRight(col), y);
          ctx.fillStyle = row.color;
          ctx.fillText(row.text, xRight(col), y);
        });
        ctx.restore();
      };

      const drawPreview = (hoverPixel) => {
        drawFrame();
        if (measureMode === "off" || !hoverPixel) return;
        ctx.save();
        // A small pixel-centered reticle is more precise than an I-beam
        // cursor, especially when the image is zoomed or scrolled.
        const reticle = Math.max(3, strokeW() + 2);
        ctx.strokeStyle = "rgba(255,255,255,0.9)";
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.strokeRect(
          hoverPixel.x + 0.5 - reticle,
          hoverPixel.y + 0.5 - reticle,
          reticle * 2,
          reticle * 2,
        );
        ctx.beginPath();
        ctx.moveTo(hoverPixel.x + 0.5 - reticle - 3, hoverPixel.y + 0.5);
        ctx.lineTo(hoverPixel.x + 0.5 + reticle + 3, hoverPixel.y + 0.5);
        ctx.moveTo(hoverPixel.x + 0.5, hoverPixel.y + 0.5 - reticle - 3);
        ctx.lineTo(hoverPixel.x + 0.5, hoverPixel.y + 0.5 + reticle + 3);
        ctx.stroke();
        ctx.lineWidth = strokeW();
        ctx.strokeStyle = "rgba(142,240,200,0.45)";
        ctx.setLineDash([6, 6]);
        if (measureMode === "line" && pendingStart) {
          ctx.beginPath();
          ctx.moveTo(pendingStart.x + 0.5, pendingStart.y + 0.5);
          ctx.lineTo(hoverPixel.x + 0.5, hoverPixel.y + 0.5);
          ctx.stroke();
        } else if (measureMode === "angle" && pendingPoints.length >= 1) {
          if (pendingPoints.length === 1) {
            ctx.beginPath();
            ctx.moveTo(pendingPoints[0].x + 0.5, pendingPoints[0].y + 0.5);
            ctx.lineTo(hoverPixel.x + 0.5, hoverPixel.y + 0.5);
            ctx.stroke();
          } else {
            // The first click is the vertex. Keep the completed arm fixed
            // and preview only the second arm from that same vertex.
            ctx.beginPath();
            ctx.moveTo(pendingPoints[0].x + 0.5, pendingPoints[0].y + 0.5);
            ctx.lineTo(pendingPoints[1].x + 0.5, pendingPoints[1].y + 0.5);
            ctx.lineTo(hoverPixel.x + 0.5, hoverPixel.y + 0.5);
            ctx.stroke();
          }
        }
        ctx.restore();
      };

      const render = () => {
        // Decode the replacement before resizing the visible canvas. This
        // keeps the previous frame visible during navigation.
        image.decode().then(() => {
          canvas.width = width;
          canvas.height = height;
          ctx.imageSmoothingEnabled = false;
          drawFrame();
          if (firstRenderForImage) requestAnimationFrame(centerStage);
        }).catch(() => {
          image.onload = () => {
            canvas.width = width;
            canvas.height = height;
            ctx.imageSmoothingEnabled = false;
            drawFrame();
            if (firstRenderForImage) requestAnimationFrame(centerStage);
          };
        });
      };
      image.onload = render;
      image.src = data.image;

      const pixelAt = (event) => {
        const rect = canvas.getBoundingClientRect();
        // During a layout pass or slice refresh the canvas can report a
        // zero-size box; do not fabricate a corner click from it.
        if (!rect.width || !rect.height) return null;
        const x = Math.max(0, Math.min(width - 1,
          Math.floor((event.clientX - rect.left) * width / rect.width)));
        const y = Math.max(0, Math.min(height - 1,
          Math.floor((event.clientY - rect.top) * height / rect.height)));
        const value = view.getFloat32((y * width + x) * 4, true);
        return { x, y, value };
      };
      const zoom = Math.max(0.25, Number(data.zoom) || 1);
      const viewMode = data.view_mode || "fit";
      if (viewMode === "native" || zoom > 1) {
        canvas.style.width = `${Math.round(width * zoom)}px`;
        canvas.style.maxWidth = "none";
        canvas.style.maxHeight = "none";
      } else {
        canvas.style.width = "100%";
        canvas.style.maxWidth = "100%";
        canvas.style.maxHeight = "620px";
      }
      const firstRenderForImage = stage.dataset.imageSig !== imageSig;
      if (firstRenderForImage) {
        stage.dataset.imageSig = imageSig;
        requestAnimationFrame(centerStage);
      }
      canvas.style.imageRendering = (viewMode === "native" || zoom > 1)
        ? "pixelated" : "auto";

      const measuring = measureMode !== "off";
      canvas.style.cursor = measuring ? "crosshair" : "default";
      canvas.onmousemove = (event) => {
        const pixel = pixelAt(event);
        if (!pixel) return;
        if (measuring) {
          const pointNumber = measureMode === "line"
            ? (pendingStart ? "P2" : "P1")
            : `P${Math.min(pendingPoints.length + 1, 3)}`;
          let physical = "";
          if (spacing && spacing[0] > 0 && spacing[1] > 0) {
            physical = ` · ${((pixel.x + 0.5) * spacing[1]).toFixed(2)}, `
              + `${((pixel.y + 0.5) * spacing[0]).toFixed(2)} mm`;
          }
          readout.textContent = `Measure ${pointNumber} · pixel center `
            + `(${pixel.x}, ${pixel.y})${physical}`;
        } else {
          readout.textContent = `${unit}: ${pixel.value.toFixed(2)} · Pixel: `
            + `(${pixel.x}, ${pixel.y})`;
        }
        if (measuring) drawPreview(pixel);
      };
      canvas.onmouseleave = () => {
        readout.textContent = "Move over an image pixel";
        drawFrame();
      };
      canvas.onclick = (event) => {
        const pixel = pixelAt(event);
        if (!pixel) return;
        if (measureMode === "line") {
          if (!pendingStart) {
            pendingStart = pixel;
            drawPreview(pixel);
          } else {
            setTriggerValue("measure_line", {
              x1: pendingStart.x, y1: pendingStart.y,
              x2: pixel.x, y2: pixel.y,
            });
            pendingStart = null;
            drawFrame();
          }
          return;
        }
        if (measureMode === "angle") {
          pendingPoints.push(pixel);
          if (pendingPoints.length === 3) {
            const [p1, p2, p3] = pendingPoints;
            setTriggerValue("measure_angle", {
              x1: p1.x, y1: p1.y,
              x2: p2.x, y2: p2.y,
              x3: p3.x, y3: p3.y,
            });
            pendingPoints = [];
            drawFrame();
          } else {
            drawPreview(pixel);
          }
          return;
        }
        setTriggerValue("click", pixel);
      };
      canvas.ondblclick = (event) => {
        const pixel = pixelAt(event);
        if (!pixel) return;
        setTriggerValue("open", pixel);
      };
    }
    """,
)


def _translate(key: str, lang: str) -> str:
    """Return a localized UI string from the i18n module."""
    translations = getattr(_i18n, key, None)
    if not isinstance(translations, dict):
        raise KeyError(f"Unknown translation key: {key}")
    return translations.get(lang, translations["en"])


# Module-level alias used by the physiological validation path.
_validate_physiological_norms = _PhysiologicalValidator.validate_physiological_norms

# Configure the page before any widgets are created so the shell, sidebar, and
# browser metadata are consistent across every rerun.
st.set_page_config(
    page_title=PRODUCT_NAME,
    page_icon=str(Path(__file__).resolve().parent / "assets" / "heeh-v1-logo.jpg"),
    layout="wide",
    initial_sidebar_state="expanded",
)








# --- User interface (Pure-Gray UI) ---


def _safe_fragment_rerun() -> None:
    """Rerun the enclosing fragment when possible, else fall back to a full-app
    rerun. During a fragment rerun ``st.rerun(scope="fragment")`` halts
    execution through ``RerunException``, a ``BaseException`` that bypasses
    the ``except Exception`` guard, so the fragment-scoped path is never
    swallowed. The fallback only fires in contexts such as headless test
    harnesses that replay the full script."""
    try:
        st.rerun(scope="fragment")
    except Exception:
        st.rerun()


@st.fragment(run_every="1s")
def _run_auto_reader_tick(total: int) -> None:
    """Advance detected exported-image sets without rendering controls."""
    if not st.session_state.get("auto_reader_enabled", False):
        return
    now = time.monotonic()
    interval = max(
        1.0, float(st.session_state.get("auto_reader_interval", 3))
    )
    last_tick = float(
        st.session_state.get("auto_reader_last_tick", now)
    )
    if now - last_tick < interval:
        return
    current = int(st.session_state.get("viewer_index", 0))
    next_index, keep_running = ClinicalApp._advance_auto_reader_index(
        current,
        total,
        loop=bool(st.session_state.get("auto_reader_loop", False)),
    )
    st.session_state.auto_reader_last_tick = now
    st.session_state.viewer_index = next_index
    st.session_state.viewer_index_slider = next_index + 1
    st.session_state.coords = None
    if not keep_running:
        st.session_state.auto_reader_enabled = False
    _safe_fragment_rerun()


@st.cache_data(show_spinner=False, max_entries=32)
def _discover_input_files_cached(
    directory: str, extensions: tuple[str, ...], mtime_ns: int, entry_count: int
) -> list[str]:
    """Discover supported files once per stable directory state."""
    del mtime_ns, entry_count
    root = Path(directory)
    try:
        return sorted(
            str(path)
            for path in root.rglob("*")
            if path.is_file()
            and any(path.name.lower().endswith(ext) for ext in extensions)
        )
    except OSError:
        return []


def _measure_label_html(name: str) -> str:
    """Render a user-supplied measurement label safely for st.markdown.

    The label is written into an ``unsafe_allow_html=True`` string, so both
    HTML and the CommonMark metacharacters are neutralized before display.
    """
    escaped = html.escape(str(name))
    for char in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|", ">", "~"):
        escaped = escaped.replace(char, "\\" + char)
    return escaped


class ClinicalApp:
    @staticmethod
    def _advance_auto_reader_index(
        current_index: int,
        total: int,
        *,
        loop: bool = False,
    ) -> tuple[int, bool]:
        """Return the next image index and whether automatic reading continues."""
        if total <= 0:
            return 0, False
        current = min(max(int(current_index), 0), total - 1)
        if current < total - 1:
            return current + 1, True
        if loop and total > 1:
            return 0, True
        return current, False
    """
    Orchestrator for medical image processing and biophysical analysis.
    Preserves raw calibrated values for analysis and uses Pure-Gray rendering.
    """

    def __init__(self):
        """Initialize engines, apply the design system, and set up session."""

        # --- 1. Engine initialization with friendly + logged errors ---
        # The single grouped catch below is intentional (doc-only note):
        #   * StreamlitAPIException - init happens inside a Streamlit rerun, so any
        #     widget/API failure must abort here before further UI calls are made.
        #   * ImportError          - optional heavy engines (MONAI, ONNX Runtime,
        #     SimpleITK) may be absent on end-user machines; missing deps must fail
        #     gracefully instead of crashing the page.
        #   * RuntimeError         - engine constructors may raise for missing
        #     models/assets or invalid config. All three share the same localized,
        #     logged error path via ``_i18n.ERR_ENGINE_INIT`` + ``safe_diag_box``.
        # NOTE: keep the except tuple a plain literal so it stays one grouped
        # catch clause (visible to linters and static analyzers).
        try:
            self.quant_engine = QuantitativeEngine()
            self.struct_engine = StructuralEngine()
            self.ai_engine = MedicalAIVisionEngine()
            self.processor = MedicalDataProcessor(target_dir="analysis_cache")
            # MONAI is optional and expensive to import.  Keep it out of the
            # normal startup path; the advanced-analysis branch loads it on
            # first use.
            self.monai_preprocessor = None
            self.anatomical_segmentation = AnatomicalSegmentation()
            self.sitk_registration = SimpleITKRegistration()
            self.onnx_engine = ONNXInferenceEngine()
        except (StreamlitAPIException, ImportError, RuntimeError) as e:
            logger.error("engine init failed", exc_info=e)
            lang = st.session_state.get("app_lang", "en")
            msg = _i18n.ERR_ENGINE_INIT[lang]
            st.markdown(safe_diag_box("error", msg, str(e), role="alert"),
                        unsafe_allow_html=True)
            return

        # --- 2. Language + layout (RTL ready) ---
        self._setup_lang()
        self._inject_css()
        self._inject_skip_link()

        # --- 3. Session state management ---
        if 'coords' not in st.session_state:
            st.session_state.coords = None
        if 'current_file' not in st.session_state:
            st.session_state.current_file = None
        if 'analysis_history' not in st.session_state:
            st.session_state.analysis_history = []
        if 'onboarding_seen' not in st.session_state:
            st.session_state.onboarding_seen = False

    @staticmethod
    def _load_model_metrics() -> list[dict]:
        """Return fine-tuned model metrics discovered under models/finetuned."""
        metrics: list[dict] = []
        models_root = Path(__file__).resolve().parent / "models"
        if not models_root.exists():
            return metrics
        def _metric(value, default=0.0):
            try:
                return float(value) if value is not None else default
            except (TypeError, ValueError):
                return default
        for metrics_path in sorted(models_root.rglob("metrics.json"), key=str):
            try:
                payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            summary = {
                "path": str(metrics_path),
                "model_id": payload.get("model_id", metrics_path.parent.name),
                "device": payload.get("device", "unknown"),
                "accuracy": _metric(payload.get("accuracy", payload.get("best_val_acc", 0.0))),
                "macro_f1": _metric(payload.get("macro_f1", 0.0)),
                "roc_auc": _metric(payload.get("roc_auc"), default=None),
                "epochs": int(payload.get("epochs_run", 0)),
                "best_val_acc": _metric(payload.get("best_val_acc", payload.get("accuracy", 0.0))),
            }
            if summary["accuracy"] or summary["macro_f1"] or summary["roc_auc"]:
                metrics.append(summary)
        return metrics

    @staticmethod
    def _flatten_radiomics_report(report: dict) -> list[dict]:
        """Flatten nested radiomics dicts into a tabular structure for CSV export."""
        rows: list[dict] = []
        for group, values in report.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    if isinstance(value, dict):
                        for inner_key, inner_value in value.items():
                            rows.append({"group": group, "feature": f"{key}.{inner_key}", "value": inner_value})
                    elif isinstance(value, (int, float, str, bool)):
                        rows.append({"group": group, "feature": str(key), "value": value})
            elif isinstance(values, (int, float, str, bool)):
                rows.append({"group": "summary", "feature": str(group), "value": values})
        return rows

    @staticmethod
    def _radiomics_export_csv(report: dict, *, prefix: str = "radiomics") -> bytes:
        """Create a CSV export for the radiomics report."""
        rows = ClinicalApp._flatten_radiomics_report(report)
        if pd is not None:
            df = pd.DataFrame(rows)
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            return csv_buffer.getvalue().encode("utf-8-sig")
        # Lightweight fallback when pandas is unavailable.
        headers = ["group", "feature", "value"]
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get("group", ""), row.get("feature", ""), row.get("value", "")])
        return out.getvalue().encode("utf-8-sig")

    @staticmethod
    def _radiomics_export_excel(report: dict, *, prefix: str = "radiomics") -> bytes:
        """Create a real XLSX export when pandas and openpyxl are available."""
        rows = ClinicalApp._flatten_radiomics_report(report)
        if not rows:
            return b""
        if pd is None:
            return b""
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine="openpyxl") as writer:  # type: ignore[union-attr]
                df.to_excel(writer, index=False, sheet_name="radiomics")
        except (ImportError, ValueError):
            return b""
        return output.getvalue()

    @staticmethod
    def _missing_export_dependencies() -> list[str]:
        """Report which optional `export` dependencies are missing."""
        from importlib.util import find_spec

        missing = []
        if pd is None or find_spec("pandas") is None:
            missing.append("pandas")
        if find_spec("openpyxl") is None:
            missing.append("openpyxl")
        return missing

    @staticmethod
    def _build_export_zip(products: list[dict], *, zip_name: str = "export") -> bytes:
        """Bundle every ready export product into a single in-memory ZIP archive."""
        ready = [p for p in products if p.get("data") is not None]
        if not ready:
            return b""
        buffer = io.BytesIO()
        base_counter: dict[str, int] = {}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for product in ready:
                base_name = product["file_name"] or zip_name
                count = base_counter.get(base_name, 0)
                base_counter[base_name] = count + 1
                if count:
                    stem, ext = os.path.splitext(base_name)
                    member_name = f"{stem}_{count}{ext}"
                else:
                    member_name = base_name
                archive.writestr(member_name, product["data"])
        archive_bytes = buffer.getvalue()
        validation = validate_export_archive(archive_bytes)
        if not validation["ok"]:
            details = "; ".join(
                f"{item['code']}: {item['message']}"
                for item in validation["errors"][:5]
            )
            raise ValueError(f"Export archive failed validation: {details}")
        return archive_bytes

    @staticmethod
    def _export_standards_manifest(
        products: list[dict], *, source: str, measurement_count: int = 0
    ) -> bytes:
        """Create a machine-readable provenance and conformance manifest."""
        def _payload_bytes(value) -> bytes:
            if isinstance(value, bytes):
                return value
            if isinstance(value, bytearray):
                return bytes(value)
            if isinstance(value, memoryview):
                return value.tobytes()
            if isinstance(value, str):
                return value.encode("utf-8")
            raise TypeError(
                f"Unsupported export payload type: {type(value).__name__}"
            )

        files = []
        for product in products:
            data = product.get("data")
            if data is None:
                continue
            payload = _payload_bytes(data)
            files.append({
                "file": product.get("file_name", ""),
                "media_type": product.get("mime", "application/octet-stream"),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        manifest = {
            "schema": "heeh-v1.export-manifest",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "software": {
                "name": "HEEH-V1 DICOM Research Toolkit",
                "project": "heeh-v1-dicom-viewer",
                "purpose": "research and education",
                "clinical_certification": False,
            },
            "source": str(source),
            "measurement_count": int(measurement_count),
            "encoding": {
                "text": "UTF-8",
                "csv": "RFC 4180-compatible UTF-8 with BOM",
                "json": "RFC 8259-compatible JSON",
                "archive": "ZIP",
            },
            "interoperability": {
                "dicom": [
                    "DICOM PS3.5/PS3.10",
                    "DICOM SR TID 1500/1501/300/320 where generated",
                    "UCUM units for numeric measurements",
                ],
                "png": ["PNG with embedded measurement JSON metadata"],
                "spreadsheet": ["Office Open XML XLSX"],
                "web": ["HTML5 self-contained research report"],
            },
            "privacy": {
                "deidentified_dicom": True,
                "burned_in_annotations": "not automatically removed",
                "pixel_privacy_review": "required before external release",
                "source_identifiers": "export filenames and manifest source labels are pseudonymous",
                "nested_sequences": "curated PHI fields and private tags only; external review required",
                "dates": "dates are removed by default; no validated date-shift protocol is applied",
                "archive_security": "ZIP is not encrypted or access-controlled",
            },
            "validation_required": [
                "Run scripts/validate_export.py before external transfer",
                "Independent DICOM and DICOM SR validator",
                "Target PACS/viewer interoperability test",
                "Burned-in annotation inspection or pixel-redaction protocol",
                "Deployment privacy, security, retention, and access-control review",
            ],
            "conformance_boundary": (
                "This manifest documents implemented export conventions. It is "
                "not a HIPAA/GDPR certification, DICOM conformance statement, "
                "IHE certification, or medical-device approval."
            ),
            "files": files,
        }
        return json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _open_export_archive(target) -> tuple[list[str], dict[str, dict]]:
        """Safely extract exported images and restore measurement metadata.

        Annotated measurement composites are preferred over their matching
        DICOM fallback so reopening uses the same rendered presentation that
        was used when the measurement was created.
        """
        archive_bytes = ClinicalApp._read_target_bytes(target)
        root = Path(tempfile.mkdtemp(prefix="heeh_export_"))
        _register_session_temp_root(root)
        st.session_state.setdefault("_export_archive_roots", []).append(str(root))
        dicom_images: list[str] = []
        composite_images: list[str] = []
        other_images: list[str] = []
        json_by_prefix: dict[str, dict] = {}
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member.is_dir() or member_path.is_absolute() or ".." in member_path.parts:
                    continue
                destination = root / member_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
                if destination.suffix.lower() == ".json":
                    try:
                        payload = json.loads(destination.read_text(encoding="utf-8"))
                        if (
                            isinstance(payload, dict)
                            and payload.get("schema") == "measurement-annotation"
                        ):
                            key = destination.stem.replace(
                                "_measurements", ""
                            ).lower()
                            json_by_prefix[key] = {
                                "measurements": list(
                                    payload.get("measurements") or []
                                ),
                                "display_mode": payload.get("display_mode"),
                                "window_preset": payload.get("window_preset"),
                                "window_center": payload.get("window_center"),
                                "window_width": payload.get("window_width"),
                            }
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        logger.warning("Ignoring invalid measurement JSON: %s", member.filename)
                elif destination.suffix.lower() in (".dcm", ".dicom"):
                    if not destination.name.endswith("_measurements_sr.dcm"):
                        dicom_images.append(str(destination))
                elif destination.suffix.lower() in (
                    ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"
                ):
                    if destination.suffix.lower() == ".png" and (
                        ClinicalApp._read_measurement_composite_metadata(
                            str(destination)
                        )
                    ):
                        composite_images.append(str(destination))
                    else:
                        other_images.append(str(destination))

        # Keep one displayable entry per exported image. The composite is the
        # editable presentation; a DICOM fallback remains available when no
        # composite was included in the archive.
        # DICOM is the authoritative editable source. The PNG composite is
        # retained only as a fallback when the archive lacks DICOM pixels.
        images = list(dicom_images)
        if not images:
            images = list(composite_images)
        images.extend(other_images)
        return images, json_by_prefix

    @staticmethod
    def _cleanup_export_archives() -> None:
        """Remove archive extraction directories owned by this Streamlit session."""
        roots = st.session_state.pop("_export_archive_roots", [])
        for root_name in roots:
            root = Path(str(root_name))
            if root.name.startswith("heeh_export_") and root.parent == Path(
                tempfile.gettempdir()
            ):
                shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _persist_uploaded_files(uploaded_files) -> list[str]:
        """Materialize completed uploads so reruns do not depend on upload handles."""
        uploads = list(uploaded_files or [])
        signature = tuple(
            (
                str(getattr(item, "name", "upload")),
                int(getattr(item, "size", 0) or 0),
            )
            for item in uploads
        )
        if (
            signature
            and st.session_state.get("_uploaded_input_signature") == signature
            and st.session_state.get("_uploaded_input_paths")
        ):
            paths = st.session_state["_uploaded_input_paths"]
            if all(Path(path).is_file() for path in paths):
                return list(paths)

        old_root = st.session_state.pop("_uploaded_input_root", None)
        if old_root:
            root = Path(str(old_root))
            if root.name.startswith("heeh_upload_"):
                shutil.rmtree(root, ignore_errors=True)
                _SESSION_TEMP_ROOTS.discard(root.resolve())

        root = Path(tempfile.mkdtemp(prefix="heeh_upload_"))
        _register_session_temp_root(root)
        paths = []
        for index, uploaded in enumerate(uploads):
            name = Path(str(getattr(uploaded, "name", f"upload_{index}"))).name
            suffix = "".join(Path(name).suffixes)
            if not suffix:
                suffix = ".bin"
            destination = root / f"{index:06d}{suffix.lower()}"
            data = ClinicalApp._read_target_bytes(uploaded)
            destination.write_bytes(data)
            paths.append(str(destination))

        st.session_state["_uploaded_input_root"] = str(root)
        st.session_state["_uploaded_input_signature"] = signature
        st.session_state["_uploaded_input_paths"] = paths
        return paths

    @staticmethod
    def _reopened_measurement_keys(file_id: str) -> tuple[str, ...]:
        """Return filename-independent aliases for exported image records."""
        stem = Path(str(file_id)).stem.lower()
        aliases = [stem]
        for suffix in ("_anonymized", "_annotated", "_image", "_dcm"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                aliases.append(stem)
        return tuple(dict.fromkeys(aliases))

    @staticmethod
    def _safe_export_stem(file_id: str, index: int | None = None) -> str:
        """Return a non-identifying, stable export stem for a source item."""
        digest = pseudonymous_identifier(Path(str(file_id)).name)
        suffix = f"_image_{int(index) + 1:04d}" if index is not None else ""
        return f"heeh_{digest}{suffix}"

    @staticmethod
    def _normalized_measurement(item: dict | None) -> dict:
        """Return a backwards-compatible, export-safe measurement record.

        Older sessions stored angle values in the legacy ``mm`` field.  That
        field is deliberately removed from exported angle records so clients
        cannot mistake an angular value for a physical length.
        """
        normalized = dict(item or {})
        kind = str(normalized.get("kind") or "").lower()
        if kind == "angle":
            degrees = normalized.get("degrees")
            if degrees is None:
                degrees = normalized.get("value")
            if degrees is None:
                degrees = normalized.get("mm")
            try:
                degrees = None if degrees is None else float(degrees)
            except (TypeError, ValueError):
                degrees = None
            normalized["degrees"] = degrees
            normalized["value"] = degrees
            normalized["unit"] = "deg"
            normalized.pop("mm", None)
            normalized.pop("millimeters", None)
        return normalized

    @classmethod
    def _measurement_export_row(
        cls,
        item: dict,
        number: int,
        *,
        file_name: str = "",
        slice_number: int | None = None,
    ) -> dict:
        """Build one explicit measurement row shared by CSV/XLSX exports."""
        normalized = cls._normalized_measurement(item)
        kind = str(normalized.get("kind") or "")
        unit = "deg" if kind == "angle" else str(normalized.get("unit") or "mm")
        physical_mm = normalized.get("mm") if kind == "distance" else None
        if kind == "angle":
            value = normalized.get("degrees")
        elif unit == "mm":
            value = physical_mm
        elif unit == "cm":
            value = None if physical_mm is None else physical_mm / 10.0
        else:
            value = normalized.get("px")
        row = {
            "file": file_name,
            "slice": "" if slice_number is None else slice_number,
            "measurement": number,
            "label": normalized.get("label") or "",
            "kind": kind,
            "value": value,
            "unit": unit,
            "pixels": normalized.get("px"),
            "physical_distance_mm": physical_mm,
            "angle_degrees": normalized.get("degrees")
            if kind == "angle"
            else None,
            "calibration": normalized.get("calib_source") or "",
            "pixel_spacing_mm": json.dumps(
                normalized.get("pixel_spacing_mm") or []
            ),
        }
        return row

    def _build_measured_images_batch_export(
        self, files_list: list, *, files_fpr: str
    ) -> bytes:
        """Package every measured image and all applicable export products."""
        store = st.session_state.get("_measurement_store", {})
        records = []
        for key, value in store.items():
            if not str(key).startswith(f"{files_fpr}:"):
                continue
            if isinstance(value, dict):
                record = dict(value)
            elif isinstance(value, list):
                # Compatibility with sessions created before the record schema.
                record = {
                    "file_id": str(key),
                    "file_index": -1,
                    "slice_index": 0,
                    "measurements": value,
                }
            else:
                continue
            if record.get("measurements"):
                records.append(record)
        if not records:
            return b""

        products: list[dict] = []
        aggregate_rows: list[dict] = []
        aggregate_json: list[dict] = []
        status_rows: list[dict] = []
        for record in records:
            index = int(record.get("file_index", -1))
            if not 0 <= index < len(files_list):
                status_rows.append({
                    "file": self._safe_export_stem(str(record.get("file_id") or "image")),
                    "status": "failed",
                    "error_code": "SOURCE_INDEX_UNAVAILABLE",
                    "error_message": "The saved measurement source is no longer available.",
                })
                continue
            target = files_list[index]
            file_id = str(record.get("file_id") or getattr(target, "name", target))
            slice_index = int(record.get("slice_index", 0))
            safe_name = self._safe_export_stem(file_id, index)
            measurements = [
                self._normalized_measurement(item)
                for item in list(record.get("measurements") or [])
            ]
            try:
                data, uid, modality = self._load_image(target)
                if isinstance(data, str) or data is None or data.size == 0:
                    status_rows.append({
                        "file": safe_name,
                        "status": "failed",
                        "error_code": "EMPTY_OR_REJECTED_DATA",
                        "error_message": "No pixel data was available.",
                    })
                    continue
                volume = np.asarray(data)
                raw_color = (
                    volume.ndim == 3
                    and volume.shape[-1] in (3, 4)
                    and not str(modality or "").upper().startswith("VOLUME")
                )
                if volume.ndim > 3 and not raw_color:
                    while volume.ndim > 3:
                        axis = int(np.argmin(volume.shape))
                        volume = np.take(volume, volume.shape[axis] // 2, axis=axis)
                if volume.ndim == 3 and not raw_color:
                    axis = int(np.argmin(volume.shape))
                    slice_index = min(max(slice_index, 0), volume.shape[axis] - 1)
                    image = np.take(volume, slice_index, axis=axis)
                else:
                    image = volume
                metadata = self._read_dicom_presentation_metadata(target)
                modality_key, is_color = self._parse_image_type(
                    str(modality or "").upper(), image
                )
                if is_color:
                    display = self._prepare_color_display(image)
                elif modality_key == "CT":
                    preset = self._default_window_preset(modality_key)
                    center, width = DISPLAY_PRESETS.get(preset, (40, 400))
                    display = self._apply_windowing(
                        image, center=center, width=width, preset=preset
                    )
                else:
                    finite = image[np.isfinite(image)]
                    lo, hi = np.percentile(finite, [1, 99])
                    display = np.clip(
                        (image - lo) * 255.0 / max(hi - lo, 1e-9), 0, 255
                    ).astype(np.uint8)
                prefix = f"measured/{safe_name}_slice_{slice_index + 1}"
                annotated = self._render_annotated_image_png(
                    display,
                    measurements=measurements,
                    source_label=safe_name,
                    pixel_spacing_mm=metadata.get("pixel_spacing_mm"),
                )
                if annotated:
                    products.append({
                        "data": annotated,
                        "file_name": f"{prefix}_annotated.png",
                    })
                measurement_payload = {
                    "schema": "measurement-annotation",
                    "version": 1,
                    "source": safe_name,
                    "slice_index": slice_index,
                    "modality": modality_key,
                    "pixel_spacing_mm": metadata.get("pixel_spacing_mm") or [],
                    "measurements": measurements,
                    "display_mode": "measurement_composite",
                    "window_preset": st.session_state.get(
                        "window_preset", self._default_window_preset(modality_key)
                    ),
                    "window_center": float(
                        st.session_state.get("w_center", 40)
                    ),
                    "window_width": float(
                        st.session_state.get("w_width", 400)
                    ),
                }
                aggregate_json.append(measurement_payload)
                products.append({
                    "data": json.dumps(
                        measurement_payload, indent=2, default=str
                    ).encode("utf-8"),
                    "file_name": f"{prefix}_measurements.json",
                })
                for number, item in enumerate(measurements, 1):
                    aggregate_rows.append(
                        self._measurement_export_row(
                            item,
                            number,
                            file_name=safe_name,
                            slice_number=slice_index + 1,
                        )
                    )
                anon = self._deidentified_dicom_bytes(target)
                if anon:
                    products.append({
                        "data": anon,
                        "file_name": f"{prefix}_anonymized.dcm",
                    })
                    try:
                        source = pydicom.dcmread(
                            io.BytesIO(anon), stop_before_pixels=True
                        )
                        sr = self._build_dicom_sr_report(
                            measurements,
                            source_sop_class_uid=str(source.SOPClassUID),
                            source_sop_instance_uid=str(source.SOPInstanceUID),
                            pixel_spacing_mm=metadata.get("pixel_spacing_mm"),
                        )
                        if sr:
                            products.append({
                                "data": sr,
                                "file_name": f"{prefix}_measurements_sr.dcm",
                            })
                    except (AttributeError, KeyError, TypeError, ValueError):
                        logger.warning("Could not create batch SR for %s", file_id)
                report = {
                    "file_id": safe_name,
                    "modality": modality_key,
                    "slice_index": slice_index,
                    "measurements": measurements,
                    "dicom": metadata,
                }
                products.append({
                    "data": self._build_html_research_report(report),
                    "file_name": f"{prefix}_research_report.html",
                })
                status_rows.append({
                    "file": safe_name,
                    "status": "success",
                    "error_code": "",
                    "error_message": "",
                })
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                logger.warning("Batch measurement export skipped %s: %s", file_id, exc)
                status_rows.append({
                    "file": safe_name,
                    "status": "failed",
                    "error_code": "PROCESSING_ERROR",
                    "error_message": str(exc)[:240],
                })

        if aggregate_rows:
            output = io.StringIO()
            writer = csv.DictWriter(
                output, fieldnames=list(aggregate_rows[0]), extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(aggregate_rows)
            products.append({
                "data": output.getvalue().encode("utf-8-sig"),
                "file_name": "measurements_all.csv",
            })
            if pd is not None:
                try:
                    workbook_report = {
                        "measurements": {
                            str(index): row
                            for index, row in enumerate(aggregate_rows)
                        }
                    }
                    products.append({
                        "data": self._radiomics_export_excel(
                            workbook_report, prefix="measurements_all"
                        ),
                        "file_name": "measurements_all.xlsx",
                    })
                except (ImportError, ValueError, TypeError):
                    logger.warning("Batch measurement XLSX export unavailable")
        if status_rows:
            status_output = io.StringIO()
            status_writer = csv.DictWriter(
                status_output,
                fieldnames=["file", "status", "error_code", "error_message"],
            )
            status_writer.writeheader()
            status_writer.writerows(status_rows)
            products.append({
                "data": status_output.getvalue().encode("utf-8-sig"),
                "file_name": "measured_images_status.csv",
            })
        products.append({
            "data": json.dumps(
                aggregate_json, indent=2, default=str
            ).encode("utf-8"),
            "file_name": "measurements_manifest.json",
        })
        products.append({
            "data": self._export_standards_manifest(
                products,
                source="measured-images-batch",
                measurement_count=len(aggregate_rows),
            ),
            "file_name": "export_manifest.json",
            "mime": "application/json",
        })
        return self._build_export_zip(
            products, zip_name="measured_images_batch"
        )

    @staticmethod
    def _render_annotated_image_png(
        display_image: np.ndarray,
        *,
        measurements: list | None = None,
        roi_center_px: tuple | None = None,
        roi_radius_px: int | None = None,
        source_label: str | None = None,
        pixel_spacing_mm: tuple | None = None,
    ) -> bytes:
        """Render the BASE display image with measurement rulers and the ROI.

        Measurement coordinates are source-pixel indices (the hover viewer
        reports them at natural resolution; zoom/pan never alters that space),
        so rulers are drawn directly on the native image. Only pixels of the
        overlay are added; the underlying base image is never modified. The
        output keeps the display image's own format and colors: grayscale
        bases stay grayscale (expanded to RGB only so rulers render in their
        true color) and RGB/RGBA color sources are never down-mixed to gray.

        Standards alignment: measurements and calibration are also embedded
        as PNG tEXt metadata, following the DICOM measurement-reporting model
        (DICOM PS3.3/PS3.16): every ruler records its source-pixel vertices,
        its numeric value with a UCUM-registered unit code (``mm``/``deg``)
        and the physical calibration used, so the file stays spatially and
        metrologically traceable without altering the rendered pixels.
        """
        from PIL import Image, ImageDraw, ImageFont

        image = np.asarray(display_image, dtype=np.uint8)
        if image.ndim < 2 or image.size == 0:
            return b""
        if image.ndim == 2:
            pil_img = Image.fromarray(image, mode="L").convert("RGB")
        elif image.ndim == 3 and image.shape[2] in (3, 4):
            pil_img = Image.fromarray(image[..., :3], mode="RGB")
        else:
            return b""
        draw = ImageDraw.Draw(pil_img)
        width, height = pil_img.size

        line_width = max(1, round(max(width, height) / 700))
        try:
            font = ImageFont.load_default(size=max(11, round(width / 95)))
        except TypeError:  # pragma: no cover - older Pillow has no size arg
            font = ImageFont.load_default()

        def _clamped(x: float, y: float):
            return (
                max(0, min(round(x), width - 1)),
                max(0, min(round(y), height - 1)),
            )

        def _draw_label(text: str, x: float, y: float, fill: str) -> None:
            tx, ty = _clamped(x, y)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    draw.text((tx + dx, ty + dy), text, fill="#050608", font=font)
            draw.text((tx + 1, ty + 1), text, fill=fill, font=font)

        legend_items: list = []
        for item in measurements or []:
            kind = item.get("kind", "distance")
            data = item.get("data", {})
            if not ClinicalApp._measurement_coords_valid(kind, data):
                continue
            color = str(item.get("color") or "#8ef0c8")
            legend_items.append((ClinicalApp._measurement_display(item), color))
            if kind == "angle":
                vertices = [
                    _clamped(float(data["x1"]), float(data["y1"])),
                    _clamped(float(data["x2"]), float(data["y2"])),
                    _clamped(float(data["x3"]), float(data["y3"])),
                ]
            else:
                vertices = [
                    _clamped(float(data["x1"]), float(data["y1"])),
                    _clamped(float(data["x2"]), float(data["y2"])),
                ]
            # Straight ruler segments, exactly as the viewer draws them. PIL rounds
            # fractional coordinates itself, so integer pixel coordinates give
            # each segment as a solid, unbroken ruler on the source grid.
            if kind == "angle":
                segments = [[vertices[0], vertices[1]], [vertices[0], vertices[2]]]
            else:
                segments = [[vertices[0], vertices[1]]]
            for segment in segments:
                draw.line(segment, fill=color, width=line_width)
            # Endpoint cross markers keep the exact source pixels visible.
            for vx, vy in vertices:
                r = max(2, line_width + 1)
                hx1, hy1 = _clamped(vx - r, vy - 1)
                hx2, hy2 = _clamped(vx + r - 1, vy)
                vx1, vy1 = _clamped(vx - 1, vy - r)
                vx2, vy2 = _clamped(vx, vy + r - 1)
                draw.rectangle(
                    [min(hx1, hx2), min(hy1, hy2), max(hx1, hx2), max(hy1, hy2)],
                    fill=color,
                )
                draw.rectangle(
                    [min(vx1, vx2), min(vy1, vy2), max(vx1, vx2), max(vy1, vy2)],
                    fill=color,
                )

        if roi_center_px is not None and roi_radius_px:
            cx, cy = _clamped(*roi_center_px)
            radius = max(1, int(roi_radius_px))
            rx1, ry1 = _clamped(cx - radius, cy - radius)
            rx2, ry2 = _clamped(cx + radius, cy + radius)
            draw.ellipse((rx1, ry1, rx2, ry2), outline="#6db1ff", width=max(1, line_width - 1))
            _draw_label("ROI", cx + radius + 4, cy - radius, fill="#6db1ff")

        # Compact value legend pinned to the top-right edge of the image,
        # replicating the on-screen canvas overlay so the numbers sit exactly
        # as they do in the calculation display (one row per ruler in
        # measurement order; extra columns grow right-to-left when crowded).
        if legend_items:
            pad_x, pad_y = 10, 9
            row_gap, col_gap = 5, 12
            base_font_size = max(11, round(width / 95))
            min_font_size = 9
            rows_total = len(legend_items)

            def _col_rows_hold(font_size: int) -> int:
                return max(1, (height - 16 - pad_y * 2) // (font_size + row_gap))

            one_col_fits = (
                _col_rows_hold(min_font_size) >= rows_total
                or _col_rows_hold(base_font_size) >= rows_total
            )
            legend_font_size = base_font_size if one_col_fits else min_font_size
            legend_font = ImageFont.load_default(size=legend_font_size)
            col_rows = _col_rows_hold(legend_font_size)
            n_cols = max(1, (rows_total + col_rows - 1) // col_rows)
            width_budget = max(
                86,
                (width - 16 - pad_x * 2 - col_gap * (n_cols - 1)) // n_cols,
            )
            max_text_w = max(
                8,
                min(max(130, round(width * 0.55)) - pad_x * 2, width_budget),
            )

            dots = "…" if legend_font.getmask("…").getbbox() is not None else "..."

            def _truncate(text: str, max_w: int) -> str:
                if legend_font.getlength(text) <= max_w:
                    return text
                clipped = text
                while (
                    len(clipped) > 1
                    and legend_font.getlength(clipped + dots) > max_w
                ):
                    clipped = clipped[:-1]
                return clipped + dots

            rows = []
            widest = 0
            for text, color in legend_items:
                short = _truncate(text, max_text_w)
                rows.append((short, color))
                widest = max(widest, legend_font.getlength(short))
            col_w = max(widest, 40)
            panel_w = max(
                1,
                min(
                    col_w * n_cols + col_gap * (n_cols - 1) + pad_x * 2,
                    max(width - 16, 1),
                ),
            )
            panel_left = max(0, width - panel_w - 8)
            panel_top = 8
            panel_h = min(col_rows, rows_total) * (
                legend_font_size + row_gap
            ) + pad_y * 2

            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rounded_rectangle(
                (panel_left, panel_top, panel_left + panel_w, panel_top + panel_h),
                radius=6,
                fill=(17, 21, 28, round(0.85 * 255)),
                outline=(180, 190, 205, round(0.35 * 255)),
                width=1,
            )
            pil_img = Image.alpha_composite(pil_img.convert("RGBA"), overlay)
            draw = ImageDraw.Draw(pil_img)
            stroke_w = max(3, line_width + 2)

            for index, (text, color) in enumerate(rows):
                col = index // col_rows
                row_in = index % col_rows
                x_right = panel_left + panel_w - pad_x - col * (col_w + col_gap)
                y = (
                    panel_top
                    + pad_y
                    + legend_font_size
                    + row_in * (legend_font_size + row_gap)
                )
                draw.text(
                    (x_right, y),
                    text,
                    font=legend_font,
                    fill=color,
                    anchor="rs",
                    stroke_width=stroke_w,
                    stroke_fill=(5, 6, 8, 255),
                )

        metadata_measures = []
        try:
            for item in list(measurements or []):
                kind = item.get("kind")
                data = item.get("data") or {}
                if not ClinicalApp._measurement_coords_valid(kind, data):
                    continue
                keys = ["x1", "y1", "x2", "y2"]
                if kind == "angle":
                    keys += ["x3", "y3"]
                entry = {
                    "kind": kind,
                    "label": str(item.get("label") or ""),
                    "coords_px": [data.get(key) for key in keys],
                }
                if kind == "angle":
                    normalized = ClinicalApp._normalized_measurement(item)
                    entry["value"] = normalized.get("degrees")
                    entry["unit"] = "deg"  # UCUM angle degree
                else:
                    unit = str(item.get("unit") or "mm")
                    if unit == "cm" and item.get("mm") is not None:
                        entry["value"] = item.get("mm") / 10.0
                        entry["unit"] = "cm"  # UCUM
                    elif unit == "px":
                        entry["value"] = item.get("px")
                        entry["unit"] = "px"  # UCUM
                    else:
                        entry["value"] = item.get("mm")
                        entry["unit"] = "mm"  # UCUM
                if item.get("mm_per_px") is not None:
                    entry["mm_per_px"] = item["mm_per_px"]
                if item.get("calib_source"):
                    entry["calib_source"] = item["calib_source"]
                metadata_measures.append(entry)
        except Exception:
            metadata_measures = []
        payload = {
            "schema": "measurement-annotation",
            "version": 1,
            "producer": "HEEH-V1 DICOM Research Toolkit",
            "ucum_units": True,
            "sample_space": "native_pixels",
            "source": str(source_label or ""),
            "pixel_spacing_mm": [float(v) for v in pixel_spacing_mm[:2]]
            if pixel_spacing_mm
            else [],
            "measurements": metadata_measures,
        }
        if roi_center_px is not None and roi_radius_px is not None:
            payload["roi"] = {
                "center_px": [roi_center_px[0], roi_center_px[1]],
                "radius_px": int(roi_radius_px),
            }

        buffer = io.BytesIO()
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("Software", "HEEH-V1 DICOM Research Toolkit")
        png_info.add_text("Measurement-Data", json.dumps(payload))
        pil_img.convert("RGB").save(buffer, format="PNG", pnginfo=png_info)
        return buffer.getvalue()

    @staticmethod
    def _build_dicom_sr_report(
        measurements: list | None,
        *,
        source_sop_class_uid: str,
        source_sop_instance_uid: str,
        pixel_spacing_mm: tuple | None = None,
        roi_center_px: tuple | None = None,
        roi_radius_px: int | None = None,
    ) -> bytes:
        """Build a DICOM Comprehensive SR for clinical measurement reporting.

        Follows DICOM PS3.16 TID 1500 (Measurement Report) → TID 1001/1002
        (device Observer Context) and TID 1501 (Measurement and Qualitative
        Evaluation Group) → TID 300 (Measurement) → TID 320 (Spatial
        Coordinates) with SCOORD content items that are SELECTED FROM the
        source IMAGE (PS3.3 C.18.4-1 Image Reference Macro, C.17.3.2 SCOORD).

        Returns bytes of a valid DICOM file (Explicit VR Little Endian),
        or empty bytes if no valid measurements are provided.
        """
        from datetime import datetime

        from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
        from pydicom.sequence import Sequence as DSequence
        from pydicom.uid import (
            ExplicitVRLittleEndian,
            generate_uid,
        )

        valid = [
            m
            for m in (measurements or [])
            if ClinicalApp._measurement_coords_valid(
                m.get("kind"), m.get("data")
            )
            and m.get("mm") is not None
        ]
        if not valid:
            return b""

        def _code(val: str, scheme: str, meaning: str) -> Dataset:
            c = Dataset()
            c.CodeValue = val
            c.CodingSchemeDesignator = scheme
            c.CodeMeaning = meaning
            return c

        def _content_item(
            value_type: str,
            rel: str | None,
            concept_name_ds: Dataset,
            *,
            text_val: str | None = None,
            code_seq: Dataset | None = None,
            uid_val: str | None = None,
            num_val: str | None = None,
            graphic_type: str | None = None,
            graphic_data: list | None = None,
            children: list | None = None,
        ) -> Dataset:
            item = Dataset()
            item.ValueType = value_type
            if rel is not None:
                item.RelationshipType = rel
            item.ConceptNameCodeSequence = DSequence([concept_name_ds])
            if text_val is not None:
                item.TextValue = text_val
            if code_seq is not None:
                item.ConceptCodeSequence = DSequence([code_seq])
            if uid_val is not None:
                item.UID = uid_val
            if num_val is not None:
                item.NumericValue = num_val
            if graphic_type is not None:
                item.GraphicType = graphic_type
            if graphic_data is not None:
                item.GraphicData = [float(v) for v in graphic_data]
            if children:
                item.ContentSequence = DSequence(children)
            return item

        def _ucum_code(unit: str) -> Dataset:
            u = unit.lower()
            if u == "cm":
                return _code("cm", "UCUM", "centimeter")
            if u == "px":
                return _code("px", "UCUM", "pixel")
            return _code("mm", "UCUM", "millimeter")

        def _ds(value) -> str:
            text = format(float(value), ".15g")
            if len(text) <= 16:
                return text
            return format(float(value), ".9e")

        def _image_item(purpose_ds: Dataset) -> Dataset:
            """IMAGE content item with the Image Reference Macro (C.18.4)."""
            img = Dataset()
            img.ValueType = "IMAGE"
            img.RelationshipType = "SELECTED FROM"
            img.ReferencedSOPClassUID = source_sop_class_uid
            img.ReferencedSOPInstanceUID = source_sop_instance_uid
            img.ConceptNameCodeSequence = DSequence([purpose_ds])
            img.PurposeOfReferenceCodeSequence = DSequence([purpose_ds])
            return img

        def _scoord_item(
            concept_ds: Dataset,
            graphic_type: str,
            graphic_data: list,
            purpose_ds: Dataset,
        ) -> Dataset:
            """SCOORD content item SELECTED FROM the referenced IMAGE (TID 320)."""
            sc = Dataset()
            sc.ValueType = "SCOORD"
            sc.RelationshipType = "INFERRED FROM"
            sc.ConceptNameCodeSequence = DSequence([concept_ds])
            sc.GraphicType = graphic_type
            sc.GraphicData = [float(v) for v in graphic_data]
            sc.ContentSequence = DSequence([_image_item(purpose_ds)])
            return sc

        def _num_item(
            concept_ds: Dataset,
            value: float,
            unit_ds: Dataset,
            *,
            scoords: list | None = None,
        ) -> Dataset:
            """NUM content item per TID 300 with MeasuredValueSequence."""
            num = Dataset()
            num.ValueType = "NUM"
            num.RelationshipType = "CONTAINS"
            num.ConceptNameCodeSequence = DSequence([concept_ds])
            m = Dataset()
            m.NumericValue = _ds(value)
            m.MeasurementUnitsCodeSequence = DSequence([unit_ds])
            num.MeasuredValueSequence = DSequence([m])
            if scoords:
                num.ContentSequence = DSequence(scoords)
            return num

        sop_uid = generate_uid()
        now = datetime.now()
        sop_class_uid = pydicom.uid.ComprehensiveSRStorage
        study_uid = generate_uid()
        series_uid = generate_uid()

        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = sop_class_uid
        file_meta.MediaStorageSOPInstanceUID = sop_uid
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        buf = io.BytesIO()
        ds = FileDataset(buf, {}, file_meta=file_meta, preamble=b"\x00" * 128)

        ds.PatientName = "ANONYMOUS"
        ds.PatientID = "ANONYMOUS"
        ds.PatientIdentityRemoved = "YES"
        ds.DeidentificationMethod = "Basic Application Confidentiality Profile; UID Remapping"
        ds.SpecificCharacterSet = "ISO_IR 100"
        ds.Modality = "SR"
        ds.Manufacturer = "HEEH-V1 DICOM Research Toolkit"
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.SeriesNumber = 1
        ds.InstanceNumber = 1
        ds.CompletionFlag = "COMPLETE"
        ds.VerificationFlag = "UNVERIFIED"
        ds.ContentDate = now.strftime("%Y%m%d")
        ds.ContentTime = now.strftime("%H%M%S")
        ds.InstanceCreationDate = now.strftime("%Y%m%d")
        ds.InstanceCreationTime = now.strftime("%H%M%S")
        ds.SOPClassUID = sop_class_uid
        ds.SOPInstanceUID = sop_uid
        ds.ContinuityOfContent = "SEPARATE"
        template = Dataset()
        template.MappingResource = "DCMR"
        template.TemplateIdentifier = "1500"
        ds.ContentTemplateSequence = DSequence([template])

        device_uid_val = generate_uid()
        device_uid_item = _content_item(
            "UIDREF", "HAS OBS CONTEXT",
            _code("121012", "DCM", "Device Observer UID"),
            uid_val=device_uid_val,
        )
        device_name_item = _content_item(
            "TEXT", "HAS OBS CONTEXT",
            _code("121013", "DCM", "Device Observer Name"),
            text_val="HEEH-V1 DICOM Research Toolkit",
        )
        observer_type_item = _content_item(
            "CODE", "HAS OBS CONTEXT",
            _code("121005", "DCM", "Observer Type"),
            code_seq=_code("121007", "DCM", "Device"),
        )

        group_children: list[Dataset] = []
        for m in valid:
            kind = m["kind"]
            data = m.get("data") or {}
            x1 = float(data.get("x1", 0))
            y1 = float(data.get("y1", 0))
            x2 = float(data.get("x2", 0))
            y2 = float(data.get("y2", 0))

            if kind == "angle":
                normalized = ClinicalApp._normalized_measurement(m)
                angle_ds = _code("121207", "DCM", "Angle")
                x3 = float(data.get("x3", 0))
                y3 = float(data.get("y3", 0))
                group_children.append(
                    _num_item(
                        angle_ds,
                        float(normalized.get("degrees") or 0),
                        _code("deg", "UCUM", "degree"),
                        scoords=[
                            _scoord_item(
                                angle_ds, "POLYLINE",
                                [x1, y1, x2, y2], angle_ds,
                            ),
                            _scoord_item(
                                angle_ds, "POLYLINE",
                                [x1, y1, x3, y3], angle_ds,
                            ),
                        ],
                    )
                )
            else:
                unit = str(m.get("unit") or "mm").lower()
                if unit == "cm":
                    value = float(m.get("mm", 0)) / 10.0
                elif unit == "px":
                    value = float(m.get("px", 0))
                else:
                    value = float(m.get("mm", 0))
                distance_ds = _code("121206", "DCM", "Distance")
                group_children.append(
                    _num_item(
                        distance_ds,
                        value,
                        _ucum_code(unit),
                        scoords=[
                            _scoord_item(
                                distance_ds, "POLYLINE",
                                [x1, y1, x2, y2], distance_ds,
                            ),
                        ],
                    )
                )

        if roi_center_px is not None and roi_radius_px is not None:
            cx, cy = float(roi_center_px[0]), float(roi_center_px[1])
            cr = float(roi_radius_px)
            radius_ds = _code("121204", "DCM", "Radius")
            if pixel_spacing_mm:
                spacing = (
                    float(pixel_spacing_mm[0]) + float(pixel_spacing_mm[1])
                ) / 2.0
                radius_value = cr * spacing
                radius_unit = _code("mm", "UCUM", "millimeter")
            else:
                radius_value = cr
                radius_unit = _code("px", "UCUM", "pixel")
            group_children.append(
                _num_item(
                    radius_ds,
                    radius_value,
                    radius_unit,
                    scoords=[
                        _scoord_item(
                            radius_ds, "CIRCLE",
                            [cx, cy, cx + cr, cy], radius_ds,
                        ),
                    ],
                )
            )

        tracking_id = _content_item(
            "TEXT", "HAS OBS CONTEXT",
            _code("112039", "DCM", "Tracking Identifier"),
            text_val=f"Measurement Group {now.strftime('%Y%m%d%H%M%S')}",
        )
        tracking_uid = _content_item(
            "UIDREF", "HAS OBS CONTEXT",
            _code("112040", "DCM", "Tracking Unique Identifier"),
            uid_val=generate_uid(),
        )
        meas_group = _content_item(
            "CONTAINER", "CONTAINS",
            _code("125007", "DCM", "Measurement Group"),
            children=[tracking_id, tracking_uid, *group_children],
        )
        meas_group.ContinuityOfContent = "SEPARATE"

        img_meas = _content_item(
            "CONTAINER", "CONTAINS",
            _code("126010", "DCM", "Imaging Measurements"),
            children=[meas_group],
        )
        img_meas.ContinuityOfContent = "SEPARATE"

        root_container = _content_item(
            "CONTAINER", None,
            _code("126000", "DCM", "Measurement Report"),
            children=[
                observer_type_item,
                device_uid_item,
                device_name_item,
                img_meas,
            ],
        )
        root_container.ContinuityOfContent = "SEPARATE"
        ds.ContentSequence = DSequence([root_container])
        ds.save_as(buf, enforce_file_format=True, little_endian=True, implicit_vr=False)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # DICOM SR ingestion (view and re-import of exported reports).
    # ------------------------------------------------------------------
    SR_SOP_CLASS_PREFIX = "1.2.840.10008.5.1.4.1.1.88"

    @staticmethod
    def _read_target_bytes(target) -> bytes:
        """Read an uploaded or local file target as bytes, restoring seek."""
        if hasattr(target, "seek"):
            target.seek(0)
            data = target.read()
            try:
                target.seek(0)
            except Exception:
                pass
            return data
        with open(str(target), "rb") as fh:
            return fh.read()

    @staticmethod
    def _is_dicom_sr_metadata(metadata) -> bool:
        """True when DICOM presentation metadata belongs to an SR object."""
        if not isinstance(metadata, dict):
            return False
        modality = str(metadata.get("modality") or "").upper()
        sop_class = str(metadata.get("sop_class_uid") or "")
        return modality == "SR" or sop_class.startswith(
            ClinicalApp.SR_SOP_CLASS_PREFIX
        )

    @staticmethod
    def _sr_concept_code(item) -> tuple:
        """Return (CodeValue, CodeMeaning, Scheme) of a content item."""
        cncs = item.get("ConceptNameCodeSequence")
        if not cncs:
            return (None, None, None)
        code = cncs[0]
        return (
            str(code.CodeValue),
            str(code.CodeMeaning or ""),
            str(code.CodingSchemeDesignator or ""),
        )

    @staticmethod
    def _sr_kind_for(code_value: str | None, graphic_type: str, points: list) -> str:
        """Infer measurement kind from the DCM concept code or SCOORD shape."""
        if code_value == "121204":
            return "radius"
        if code_value == "121206":
            return "distance"
        if code_value == "121207":
            return "angle"
        if graphic_type == "CIRCLE":
            return "radius"
        if len(points) >= 2:
            return "angle"
        if points and len(points[0]) >= 2:
            return "distance"
        return "unknown"

    @staticmethod
    def _sr_num_to_row(node, mv, scords) -> dict | None:
        """Convert one NUM content item into a plain measurement row."""
        try:
            raw = mv.get("NumericValue")
            if isinstance(raw, (list, tuple)):
                raw = raw[0]
            num = float(raw)
        except (TypeError, ValueError):
            return None
        unit = ""
        units_seq = mv.get("MeasurementUnitsCodeSequence")
        if units_seq:
            unit = str(getattr(units_seq[0], "CodeValue", "") or "")
        concept = ClinicalApp._sr_concept_code(node)
        points: list = []
        graphic_type = None
        for sc in scords:
            graphic_type = str(sc.get("GraphicType") or "POINT")
            gd = list(sc.get("GraphicData") or [])
            pairs = []
            for i in range(0, len(gd) - 1, 2):
                try:
                    pairs.append((float(gd[i]), float(gd[i + 1])))
                except (TypeError, ValueError):
                    pairs = []
                    break
            if pairs:
                points.append(pairs)
        kind = ClinicalApp._sr_kind_for(concept[0], graphic_type, points)
        return {
            "kind": kind,
            "concept": concept[0],
            "meaning": concept[1],
            "scheme": concept[2],
            "value": num,
            "unit": unit,
            "graphic_type": graphic_type,
            "points": points,
        }

    @staticmethod
    def _extract_sr_report(dataset) -> dict:
        """Walk an SR content tree into {rows, source_images}.

        Measurement NUM items are paired with their SCOORD coordinates
        (TID 301 -> TID 320) and the referenced source IMAGE instances,
        matching the TID 1500 layout this app exports.
        """
        rows: list[dict] = []
        source_images: list[dict] = []
        seen_images: set[str] = set()

        def _walk(node) -> None:
            value_type = node.get("ValueType")
            content_seq = node.get("ContentSequence") or []
            if value_type == "NUM":
                mvs = node.get("MeasuredValueSequence")
                scords = [
                    child
                    for child in content_seq
                    if child.get("ValueType") == "SCOORD"
                    and child.get("GraphicData") is not None
                ]
                if mvs:
                    row = ClinicalApp._sr_num_to_row(node, mvs[0], scords)
                    if row:
                        rows.append(row)
            if value_type == "IMAGE":
                ref_seq = node.get("ReferencedSOPSequence")
                if ref_seq:
                    refs = list(ref_seq)
                else:
                    refs = [node]
                for ref in refs:
                    uid = str(getattr(ref, "ReferencedSOPInstanceUID", "") or "")
                    if uid and uid not in seen_images:
                        seen_images.add(uid)
                        source_images.append({
                            "instance_uid": uid,
                            "class_uid": str(
                                getattr(ref, "ReferencedSOPClassUID", "") or ""
                            ),
                        })
            for child in content_seq:
                _walk(child)

        _walk(dataset)
        return {"rows": rows, "source_images": source_images}

    @staticmethod
    def _import_sr_measurements(rows: list) -> int:
        """Re-create line/angle measurements in the active image analysis."""
        items = st.session_state.setdefault("measurements", [])
        imported = 0
        for row in rows:
            kind = row["kind"]
            if kind == "distance":
                pts = row["points"][0] if row["points"] else []
                if len(pts) < 2:
                    continue
                (x1, y1), (x2, y2) = pts[0], pts[1]
                pixel_len = float(np.hypot(x2 - x1, y2 - y1))
                if pixel_len <= 0:
                    continue
                unit = (row["unit"] or "mm").lower()
                if unit == "px":
                    px = row["value"]
                    mm = row["value"]
                    mm_per_px = None
                else:
                    if unit == "cm":
                        mm = row["value"] * 10.0
                    else:
                        mm = row["value"]
                    px = pixel_len
                    mm_per_px = mm / pixel_len
                data = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
            elif kind == "angle":
                segs = row["points"]
                if len(segs) < 2:
                    continue
                a, b = segs[0], segs[1]
                if len(a) < 2 or len(b) < 2:
                    continue
                a0, a1 = tuple(a[0]), tuple(a[1])
                b0, b1 = tuple(b[0]), tuple(b[1])
                shared = next((p for p in (a0, a1) if p in (b0, b1)), None)
                if shared is None:
                    continue
                arms = [p for p in (a0, a1, b0, b1) if p != shared]
                if len(arms) != 2:
                    continue
                # App convention: the first point is the shared vertex.
                data = {
                    "x1": shared[0], "y1": shared[1],
                    "x2": arms[0][0], "y2": arms[0][1],
                    "x3": arms[1][0], "y3": arms[1][1],
                }
                px = None
                mm = row["value"]
                unit = (row["unit"] or "deg").lower() or "deg"
                mm_per_px = None
            else:
                continue
            if not ClinicalApp._measurement_coords_valid(kind, data):
                continue
            color = _MEASURE_COLORS[len(items) % len(_MEASURE_COLORS)]
            items.append({
                "kind": kind,
                "label": "",
                "color": color,
                "data": {key: float(value) for key, value in data.items()},
                "px": px,
                "mm": mm,
                "mm_per_px": mm_per_px,
                "calib_source": "imported SR",
                "unit": unit,
                "precision": 2,
                "profile": None,
            })
            imported += 1
        st.session_state["measurements"] = items[-50:]
        return imported

    def _render_dicom_sr_viewer(
        self,
        target,
        metadata: dict,
        lang: str,
        *,
        file_id=None,
        idx: int = 0,
        total: int = 1,
        files_list=None,
        files_fpr: str = "",
    ) -> None:
        """Render a DICOM SR (no-pixel) object as a structured report.

        SR objects carry no pixel data, but the standard workspace chrome
        (navigation slider and series browser) stays available so the report
        does not dead-end the viewer.
        """
        st.subheader(_i18n.SR_REPORT_TITLE[lang])
        st.caption(_i18n.SR_REPORT_HINT[lang])

        nav_col, pos_col = st.columns([6, 4])
        with nav_col:
            if st.button(
                "Previous", key="sr_viewer_previous",
                disabled=idx <= 0, width="stretch",
            ):
                st.session_state.viewer_index = idx - 1
                st.session_state.sr_viewer_index_slider = idx
                st.session_state.coords = None
                _safe_fragment_rerun()
            if st.button(
                "Next", key="sr_viewer_next",
                disabled=idx >= total - 1, width="stretch",
            ):
                st.session_state.viewer_index = idx + 1
                st.session_state.sr_viewer_index_slider = idx + 2
                st.session_state.coords = None
                _safe_fragment_rerun()
        with pos_col:
            st.caption(f"Image {idx + 1} of {total}")

        num_files = len(files_list) if files_list else total
        if num_files > 1:

            def _select_viewer_image() -> None:
                selected_value = st.session_state.get(
                    "sr_viewer_index_slider",
                    st.session_state.get("viewer_index", 0) + 1,
                )
                try:
                    selected_index = int(selected_value) - 1
                except (TypeError, ValueError):
                    selected_index = int(st.session_state.get("viewer_index", 0))
                st.session_state.viewer_index = min(
                    max(selected_index, 0),
                    num_files - 1,
                )
                st.session_state.coords = None

            st.slider(
                "Image index",
                min_value=1,
                max_value=num_files,
                value=idx + 1,
                step=1,
                format="Image %d",
                key="sr_viewer_index_slider",
                on_change=_select_viewer_image,
            )

        try:
            blob = ClinicalApp._read_target_bytes(target)
            dataset = pydicom.dcmread(io.BytesIO(blob))
        except Exception as exc:
            logger.error("SR parse failed: %s", exc)
            st.error(f"{_i18n.SR_PARSE_FAILED[lang]} ({type(exc).__name__})")
            return

        report = ClinicalApp._extract_sr_report(dataset)

        def _esc(value) -> str:
            return html.escape(str(value))

        details = {
            "Patient": metadata.get("patient_name") or "—",
            "Patient ID": metadata.get("patient_id") or "—",
            "Study": (
                metadata.get("study_description")
                or metadata.get("study_instance_uid")
                or "—"
            ),
            "Series": (
                metadata.get("series_description")
                or metadata.get("series_instance_uid")
                or "—"
            ),
            "SOP class": (
                metadata.get("sop_class_name")
                or metadata.get("sop_class_uid")
                or "—"
            ),
            "Transfer syntax": (
                metadata.get("transfer_syntax_name")
                or metadata.get("transfer_syntax_uid")
                or "—"
            ),
        }
        st.markdown(f"**{_i18n.SR_HEADER_DETAILS[lang]}**")
        for key, value in details.items():
            st.markdown(f"- **{_esc(key)}:** {_esc(value)}")
        if report["source_images"]:
            refs = ", ".join(
                r["instance_uid"] for r in report["source_images"][:5]
            )
            more = "…" if len(report["source_images"]) > 5 else ""
            st.markdown(
                f"**{_i18n.SR_REFERENCED_IMAGES[lang]}:** "
                f"`{_esc(refs)}{_esc(more)}`"
            )

        rows = report["rows"]
        if rows:
            table = []
            for row in rows:
                coords = []
                for poly in row["points"]:
                    coords.append(
                        ", ".join(f"({x:g}, {y:g})" for x, y in poly)
                    )
                value_text = "n/a" if row["value"] is None else f"{row['value']:g}"
                table.append({
                    "Type": row["kind"].title(),
                    "Measurement": row["meaning"] or (row["concept"] or "—"),
                    "Value": value_text,
                    "Unit": row["unit"] or "—",
                    "Pixel coordinates": " ; ".join(coords) if coords else "—",
                })
            st.subheader(_i18n.SR_MEASUREMENTS_TABLE[lang])
            st.table(table)

            audit_event(
                logger,
                "sr_report_viewed",
                image_ref=pseudonymous_identifier(file_id),
                n_measurements=len(rows),
            )

            button_key = "sr_import_" + re.sub(
                r"[^A-Za-z0-9_]", "_", str(file_id)
            )
            if st.button(_i18n.SR_IMPORT_BUTTON[lang], key=button_key, width="stretch"):
                imported = ClinicalApp._import_sr_measurements(rows)
                message = _i18n.SR_IMPORT_NOTICE[lang].format(n=imported)
                if any(row["kind"] == "radius" for row in rows):
                    message += " " + _i18n.SR_IMPORT_SKIPPED_RADIUS[lang]
                st.success(message)
        else:
            st.info(_i18n.SR_NO_MEASUREMENTS[lang])

        self._render_sr_series_browser(files_list, files_fpr, idx, num_files)

        self._render_sr_export(rows, report, file_id, lang)

    def _render_sr_series_browser(
        self, files_list, files_fpr: str, idx: int, num_files: int
    ) -> None:
        """Series/study browser for the SR view (needs no pixel data)."""
        if not files_list or num_files <= 1:
            return
        with st.expander("Series browser & comparison", expanded=False):
            series_groups = st.session_state.get("_series_groups")
            if (
                series_groups is None
                or st.session_state.get("_series_groups_sig") != files_fpr
            ):
                series_groups = self._build_series_index(files_list)
                st.session_state["_series_groups"] = series_groups
                st.session_state["_series_groups_sig"] = files_fpr
            series_by_first = {}
            for group in series_groups:
                if group["indices"]:
                    series_by_first[group["indices"][0]] = group

            def _pick_series() -> None:
                first_index = int(st.session_state.get("sr_series_select", idx))
                st.session_state.viewer_index = min(first_index, num_files - 1)
                st.session_state.sr_viewer_index_slider = first_index + 1
                st.session_state.coords = None

            if series_by_first and len(series_groups) > 1:
                st.selectbox(
                    "Series / study",
                    options=sorted(series_by_first.keys()),
                    format_func=lambda i: f"{i + 1}. "
                    f"{self._series_label(series_by_first[i], files_list)}",
                    key="sr_series_select",
                    on_change=_pick_series,
                )
            else:
                st.caption("A single series was detected for this input set.")

    def _render_sr_export(
        self, rows: list, report: dict, file_id, lang: str
    ) -> None:
        """CSV/JSON download of the extracted SR report data."""
        _fallback = {
            "SR_EXPORT_HEADING": "Export report data",
            "SR_EXPORT_HINT": (
                "Download the extracted measurements as CSV or a full JSON "
                "snapshot of the structured report."
            ),
            "SR_EXPORT_CSV": "Download CSV",
            "SR_EXPORT_JSON": "Download JSON",
        }

        def _text(key: str) -> str:
            value = getattr(_i18n, key, None)
            if isinstance(value, dict):
                return value.get(lang) or value.get("en") or _fallback[key]
            return _fallback[key]

        st.divider()
        st.markdown(f"**{_text('SR_EXPORT_HEADING')}**")
        st.caption(_text("SR_EXPORT_HINT"))
        csv_lines = ["type,meaning,value,unit,coordinates"]
        for row in rows:
            value = (
                ""
                if row.get("value") is None
                else f"{row['value']:g}"
            )
            coords = "; ".join(
                " ".join(f"{x:g},{y:g}" for x, y in poly)
                for poly in row.get("points") or []
            )
            fields = [
                str(row.get("kind") or ""),
                str(row.get("meaning") or row.get("concept") or ""),
                value,
                str(row.get("unit") or ""),
                coords,
            ]
            csv_lines.append(
                ",".join('"' + field.replace('"', '""') + '"' for field in fields)
            )
        csv_bytes = "\n".join(csv_lines).encode("utf-8")
        json_bytes = json.dumps(
            {
                "file": str(file_id),
                "rows": rows,
                "source_images": report.get("source_images", []),
            },
            indent=2,
            default=str,
        ).encode("utf-8")
        export_key = "sr_export_" + re.sub(r"[^A-Za-z0-9_]", "_", str(file_id))
        row_cols = st.columns(2)
        with row_cols[0]:
            st.download_button(
                _text("SR_EXPORT_CSV"),
                data=csv_bytes,
                file_name=f"{export_key}.csv",
                mime="text/csv",
                key=f"{export_key}_csv",
            )
        with row_cols[1]:
            st.download_button(
                _text("SR_EXPORT_JSON"),
                data=json_bytes,
                file_name=f"{export_key}.json",
                mime="application/json",
                key=f"{export_key}_json",
            )

    def _render_scientific_overview(self) -> None:
        """Show model performance and GPU status for research users."""
        metrics = self._load_model_metrics()
        if not metrics:
            return
        latest = metrics[-1]
        st.subheader("Scientific model performance")
        gpu_status = "CUDA available" if torch.cuda.is_available() else "CPU only"
        st.caption(f"Compute backend: {gpu_status} · Latest model: {latest['model_id']}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Accuracy", f"{latest['accuracy']:.3f}")
        col2.metric("Macro F1", f"{latest['macro_f1']:.3f}")
        auc_text = (
            f"{latest['roc_auc']:.3f}"
            if latest["roc_auc"] is not None
            else "N/A"
        )
        col3.metric("ROC AUC", auc_text)
        if pd is not None:
            st.dataframe(pd.DataFrame(metrics), width="stretch")

    def _setup_lang(self) -> str:
        """App UI is English-only (scientific/medical terminology)."""
        st.session_state.app_lang = "en"
        # html{lang=en} drives correct screen-reader pronunciation.
        st.markdown(
            '<html lang="en" dir="ltr"></html>',
            unsafe_allow_html=True,
        )
        return "en"

    def _inject_css(self) -> None:
        """Load the design system CSS from core/theme.css."""
        css_path = Path(__file__).resolve().parent / "core" / "theme.css"
        try:
            css = css_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("could not read theme.css: %s", e)
            css = ""
        if css:
            st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    def _inject_skip_link(self) -> None:
        """Insert the skip-to-content link (WCAG 2.4.1)."""
        st.markdown(
            safe_skip_link(label="Skip to main content"),
            unsafe_allow_html=True,
        )

    def _render_onboarding(self) -> None:
        """Collapsible first-run tutorial shown once per session."""
        if st.session_state.get("onboarding_seen"):
            return
        docs = (
            "1. **Choose a source** in the control panel above the workspace.\n"
            "2. Click the image to analyze an ROI.\n"
            "3. Toggle analysis tools on the left (tissue, edges, quality, \u2026).\n"
            "4. Use the **Windowing Preset** to adjust the CT display."
        )
        with st.expander(
            "\U0001F4D6 Quick guide",
            expanded=not st.session_state.get("onboarding_seen"),
        ):
            st.markdown(docs)
        st.session_state.onboarding_seen = True

    # 5. Caching layer (assertion readiness)
    @st.cache_data(
        show_spinner="Analyzing medical image data...",
        max_entries=16,
    )
    def process_dicom(_self, input_data):
        """
        DICOM Acquisition Pipeline.

        CT series: convert stored pixels to Hounsfield Units (HU) using the
        standard HU = pixel * RescaleSlope + RescaleIntercept formula, then
        validate the CT HU range and reject NaN/Inf.

        Non-CT series (e.g. MR, US, PET): stored values are signal intensity,
        not Hounsfield units, so raw values are passed through unchanged and
        no CT range check is applied.

        Returns: (data_or_error, uid_or_none, modality_or_none).
        """
        try:
            ds = pydicom.dcmread(input_data)

            transfer_syntax = str(
                getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "")
                or ""
            ).strip()
            if not transfer_syntax:
                return (
                    "DATA_REJECTED: DICOM TransferSyntaxUID is missing; "
                    "the pixel encoding cannot be validated.",
                    None,
                    "DICOM",
                )
            if not hasattr(ds, 'pixel_array'):
                raise ValueError("Missing pixel data in DICOM.")

            try:
                pixel_array = ds.pixel_array.astype(np.float32)
            except (AttributeError, ImportError, OSError, RuntimeError, ValueError) as exc:
                return (
                    f"LOAD_ERROR: Unable to decode TransferSyntaxUID "
                    f"{transfer_syntax}: {exc}",
                    None,
                    "DICOM",
                )
            detection = ModalityDetector().detect(ds)
            if detection.rejected:
                return (
                    f"UNSUPPORTED_OBJECT: {detection.reason}",
                    None,
                    detection.raw_modality or "DICOM",
                )
            missing_tags = missing_required_tags(ds, detection)
            if missing_tags:
                return (
                    "DATA_REJECTED: DICOM object is missing required "
                    f"metadata for {detection.detected_modality or 'the detected modality'}: "
                    + ", ".join(missing_tags),
                    None,
                    detection.raw_modality or "DICOM",
                )
            modality = detection.detected_modality or "UNKNOWN"
            uid = str(getattr(ds, 'SOPInstanceUID', 'unknown_uid'))

            if modality != 'CT':
                # Non-CT modalities: raw signal intensity, not HU.
                # MONOCHROME1 means "dark = high signal" (common for MR/US);
                # it is a *display-only* convention. Analysis must consume the
                # original stored intensity, so the raw array is returned here
                # unchanged and the inversion is applied by the render path
                # (display codepath) instead. The marker is carried in the
                # modality string for the display layer.
                if not np.isfinite(pixel_array).all():
                    return "DATA_REJECTED: Non-finite (NaN/Inf) pixel values detected.", None, modality
                if str(getattr(ds, 'PhotometricInterpretation', 'MONOCHROME2')).upper() == 'MONOCHROME1':
                    modality = f"{modality} (MONOCHROME1)"
                return pixel_array, uid, modality

            # Standard CT HU conversion: HU = pixel * slope + intercept
            slope = float(getattr(ds, 'RescaleSlope', 1.0))
            intercept = float(getattr(ds, 'RescaleIntercept', 0.0))
            hu = (pixel_array * slope) + intercept

            # Validate every voxel. A median-only check can hide corrupted
            # outliers that would contaminate quantitative measurements.
            if not np.isfinite(hu).all():
                return (
                    "DATA_REJECTED: Non-finite (NaN/Inf) pixel values detected.",
                    None,
                    modality,
                )
            if np.any((hu < HU_MIN) | (hu > HU_MAX)):
                return (
                    f"INTEGRITY_HALT: CT HU values must be within "
                    f"[{HU_MIN:g}, {HU_MAX:g}].",
                    None,
                    modality,
                )

            # Return the matrix after verifying its integrity
            return hu, uid, modality

        except Exception as e:
            # Stability guard layer
            return f"CRITICAL_BALANCE_FAILURE: {e!s}", None, None

    def _load_image(self, target):
        """
        Medical Image Acquisition Dispatcher.
        Supports DICOM (.dcm) via the PhysiologicalValidator pipeline and volumetric formats
        (.nii/.nii.gz/.nrrd/.mha) via nibabel. Returns (array_or_error, uid, modality).
        """
        try:
            path = getattr(target, 'name', str(target))
            is_upload = hasattr(target, 'read')
            lower_path = str(path).lower()
            if lower_path.endswith('.nii.gz'):
                suffix = '.nii.gz'
            else:
                suffix = Path(lower_path).suffix

            if suffix in ('.dcm', '.dicom'):
                data, uid, modality = self.process_dicom(target)
                mod = f"DICOM / {modality}" if modality else "DICOM"
                return data, uid, mod

            # TCIA often ships DICOM files with non-standard extensions
            # (.IMA, .img) or no extension at all. Sniff the DICOM magic
            # ('DICM' at byte 128) before trying volumetric readers.
            if suffix.lower() in ('.ima', '.img', '.mha', '.mhd') or suffix == '':
                raw = None
                try:
                    if is_upload:
                        target.seek(0)
                        raw = target.read(132)
                    else:
                        with open(path, 'rb') as _f:
                            raw = _f.read(132)
                    if len(raw) >= 132 and raw[128:132] == b'DICM':
                        if is_upload:
                            target.seek(0)
                        data, uid, modality = self.process_dicom(target)
                        mod = f"DICOM / {modality}" if modality else "DICOM"
                        return data, uid, mod
                except Exception:
                    pass
                finally:
                    if is_upload and raw is not None:
                        try:
                            target.seek(0)
                        except Exception:
                            pass

            # Common 2D raster images are accepted as generic research images.
            # They never receive modality-specific clinical units.
            raster_suffixes = (".png", ".jpg", ".jpeg", ".bmp", ".tif",
                               ".tiff", ".webp")
            if suffix.lower() in raster_suffixes:
                if is_upload:
                    raw_raster = self._read_target_bytes(target)
                    with Image.open(io.BytesIO(raw_raster)) as image:
                        composite_metadata = (
                            self._read_measurement_composite_metadata(target)
                            if suffix.lower() == ".png"
                            else {}
                        )
                        converted = image.convert(
                            "L"
                            if composite_metadata
                            else (
                                "RGB"
                                if image.mode in ("RGB", "RGBA", "P", "LA")
                                else "L"
                            )
                        )
                        data = np.asarray(converted)
                else:
                    with Image.open(path) as image:
                        composite_metadata = (
                            self._read_measurement_composite_metadata(path)
                            if suffix.lower() == ".png"
                            else {}
                        )
                        converted = image.convert(
                            "L"
                            if composite_metadata
                            else (
                                "RGB"
                                if image.mode in ("RGB", "RGBA", "P", "LA")
                                else "L"
                            )
                        )
                        data = np.asarray(converted)
                if suffix.lower() == ".png":
                    if composite_metadata:
                        return data, path, "MEASUREMENT_COMPOSITE"
                return data, path, "RASTER / UNKNOWN"

            # Volumetric formats: try nibabel first (NIfTI/ANALYZE/MINC/GIFTI),
            # then fall back to SimpleITK for NRRD and MetaImage (.mha/.mhd),
            # which nibabel cannot read.
            load_path = str(path)
            tmp_path = None
            if is_upload:
                import tempfile as _tf
                tmp = _tf.NamedTemporaryFile(delete=False, suffix=suffix)
                target.seek(0)
                tmp.write(target.read())
                tmp.close()
                tmp_path = tmp.name
                load_path = tmp_path

            try:
                if is_upload:
                    try:
                        img = nib.load(load_path)
                        data = np.asarray(img.dataobj, dtype=np.float32)
                        slope = float(getattr(img, 'scl_slope', 1.0) or 1.0)
                        intercept = float(getattr(img, 'scl_inter', 0.0) or 0.0)
                        if slope != 1.0 or intercept != 0.0:
                            data = data * slope + intercept
                    except Exception:
                        sitk_img = sitk.ReadImage(load_path)
                        data = sitk.GetArrayFromImage(sitk_img).astype(np.float32)
                else:
                    mtime = 0.0
                    try:
                        mtime = float(os.path.getmtime(load_path))
                    except OSError:
                        pass
                    data = _load_volume_file_cached(load_path, mtime)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
            if data.size == 0:
                return "LOAD_ERROR: Image contains no voxel data.", path, "Volume"
            try:
                # A non-DICOM volume does not provide enough metadata here to
                # infer CT reliably. Validate finiteness without applying CT
                # HU limits to MR, PET, or other non-CT volumes.
                _validate_physiological_norms(data, None)
            except ValueError as exc:
                return f"LOAD_ERROR: {exc}", path, "Volume (NIfTI / NRRD / MHA)"
            return data, path, "Volume / UNKNOWN"
        except Exception as e:
            return f"LOAD_ERROR: {e!s}", None, None

    @staticmethod
    def _read_dicom_presentation_metadata(target) -> dict:
        """Read validated DICOM presentation tags without loading pixel data."""
        path = getattr(target, "name", str(target))
        suffix = Path(str(path).lower()).suffix
        if suffix == ".png":
            composite = ClinicalApp._read_measurement_composite_metadata(target)
            if composite:
                return composite
        dataset = None
        try:
            if hasattr(target, "seek"):
                target.seek(0)
                dataset = pydicom.dcmread(target, stop_before_pixels=True)
                target.seek(0)
            else:
                dataset = pydicom.dcmread(
                    str(path), stop_before_pixels=True, force=True
                )
        except (
            OSError,
            ValueError,
            pydicom.errors.InvalidDicomError,
            AttributeError,
        ):
            return {}

        def _number(tag_name: str):
            value = getattr(dataset, tag_name, None)
            if value is None:
                return None
            try:
                if isinstance(value, (list, tuple)):
                    return [float(item) for item in value]
                return float(value)
            except (TypeError, ValueError):
                return None

        rows = getattr(dataset, "Rows", None)
        columns = getattr(dataset, "Columns", None)
        pixel_spacing = getattr(dataset, "PixelSpacing", None)
        try:
            pixel_spacing = [float(item) for item in pixel_spacing] \
                if pixel_spacing is not None else None
        except (TypeError, ValueError):
            pixel_spacing = None
        transfer_syntax = getattr(
            getattr(dataset, "file_meta", None),
            "TransferSyntaxUID",
            None,
        )
        transfer_syntax_uid = str(transfer_syntax or "")
        metadata = {
            "patient_name": str(getattr(dataset, "PatientName", "") or ""),
            "modality": str(getattr(dataset, "Modality", "") or "").upper(),
            "photometric_interpretation": str(
                getattr(dataset, "PhotometricInterpretation", "") or ""
            ).upper(),
            "window_center": _number("WindowCenter"),
            "window_width": _number("WindowWidth"),
            "rows": int(rows) if rows is not None else None,
            "columns": int(columns) if columns is not None else None,
            "pixel_spacing_mm": pixel_spacing,
            "sop_class_uid": str(getattr(dataset, "SOPClassUID", "") or ""),
            "sop_class_name": (
                str(getattr(dataset, "SOPClassUID", "").name)
                if getattr(dataset, "SOPClassUID", None) is not None
                else ""
            ),
            "transfer_syntax_uid": transfer_syntax_uid,
            "transfer_syntax_name": (
                str(transfer_syntax.name) if transfer_syntax is not None else ""
            ),
            "bits_allocated": int(getattr(dataset, "BitsAllocated", 0) or 0),
            "bits_stored": int(getattr(dataset, "BitsStored", 0) or 0),
            "pixel_representation": int(
                getattr(dataset, "PixelRepresentation", 0) or 0
            ),
            "study_instance_uid": str(getattr(dataset, "StudyInstanceUID", "") or ""),
            "series_instance_uid": str(getattr(dataset, "SeriesInstanceUID", "") or ""),
            "series_description": str(getattr(dataset, "SeriesDescription", "") or ""),
            "study_description": str(getattr(dataset, "StudyDescription", "") or ""),
            "patient_id": str(getattr(dataset, "PatientID", "") or ""),
            "instance_number": _number("InstanceNumber"),
            "slice_thickness_mm": _number("SliceThickness"),
        }
        if metadata["rows"] is not None and metadata["rows"] <= 0:
            metadata["rows"] = None
        if metadata["columns"] is not None and metadata["columns"] <= 0:
            metadata["columns"] = None
        return metadata

    @staticmethod
    def _read_measurement_composite_metadata(target) -> dict:
        """Read measurement metadata embedded in an annotated PNG."""
        try:
            raw = (
                ClinicalApp._read_target_bytes(target)
                if hasattr(target, "read")
                else None
            )
            source = io.BytesIO(raw) if raw is not None else str(target)
            with Image.open(source) as image:
                info = dict(image.info)
                width, height = image.size
            raw = info.get("Measurement-Data")
            if not raw:
                return {}
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get(
                "schema"
            ) != "measurement-annotation":
                return {}
            measurements = payload.get("measurements")
            if not isinstance(measurements, list):
                return {}
            return {
                "modality": "MEASUREMENT_COMPOSITE",
                "photometric_interpretation": "MONOCHROME2",
                "rows": int(height),
                "columns": int(width),
                "pixel_spacing_mm": payload.get("pixel_spacing_mm") or None,
                "measurement_composite": True,
                "measurement_payload": payload,
                "measurements": measurements,
                "source_label": payload.get("source", ""),
                "display_mode": payload.get("display_mode") or "measurement_composite",
                "window_preset": payload.get("window_preset"),
                "window_center": payload.get("window_center"),
                "window_width": payload.get("window_width"),
            }
        except (
            OSError,
            ValueError,
            TypeError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return {}

    # ------------------------------------------------------------------
    # Measurement, series, export, and reporting helpers (research toolkit).
    # ------------------------------------------------------------------
    @staticmethod
    def _measure_distance(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        pixel_spacing_mm: list | None = None,
    ) -> tuple[float, float | None]:
        """Distance between two source pixels.

        Returns (pixel distance, millimeters). Millimeters are only reported
        when isotropic PixelSpacing is available; the computation is anchored
        to source-pixel indices and is therefore independent of the CSS zoom
        used to render the canvas.
        """
        px = float(np.hypot(x2 - x1, y2 - y1))
        mm = None
        if (
            pixel_spacing_mm
            and len(pixel_spacing_mm) >= 2
            and all(v > 0 for v in pixel_spacing_mm[:2])
        ):
            mm = float(
                np.hypot(
                    # DICOM PixelSpacing is row (y), column (x).
                    (x2 - x1) * pixel_spacing_mm[1],
                    (y2 - y1) * pixel_spacing_mm[0],
                )
            )
        return px, mm

    @staticmethod
    def _measure_angle(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        pixel_spacing_mm: list | None = None,
    ) -> float:
        """Angle in degrees at the first point between arms to points 2 and 3.

        PixelSpacing is applied per axis so the angle is evaluated in physical
        (mm) space when spacing metadata is present, otherwise in pixel space.
        """
        sx = (
            pixel_spacing_mm[1]
            if pixel_spacing_mm and len(pixel_spacing_mm) >= 2
            else 1.0
        )
        sy = (
            pixel_spacing_mm[0]
            if pixel_spacing_mm and len(pixel_spacing_mm) >= 2
            else 1.0
        )
        # The canvas collects vertex, arm point, arm point.
        v1x = (x2 - x1) * sx
        v1y = (y2 - y1) * sy
        v2x = (x3 - x1) * sx
        v2y = (y3 - y1) * sy
        n1 = float(np.hypot(v1x, v1y))
        n2 = float(np.hypot(v2x, v2y))
        if n1 <= 0 or n2 <= 0:
            return 0.0
        cos_value = float(np.clip((v1x * v2x + v1y * v2y) / (n1 * n2), -1.0, 1.0))
        return float(np.degrees(np.arccos(cos_value)))

    @staticmethod
    def _measure_line_profile(
        values: np.ndarray,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> dict | None:
        """First-order intensity statistics along the rasterized segment.

        The segment is sampled with a Bresenham walk over nearest source
        pixels, so the profile never depends on CSS zoom or on-screen scale.
        Returns None for degenerate or fully out-of-bounds segments.
        """
        arr = np.asarray(values)
        if arr.ndim < 2:
            return None
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h < 1 or w < 1:
            return None
        x0 = min(max(round(x1), 0), w - 1)
        y0 = min(max(round(y1), 0), h - 1)
        x1i = min(max(round(x2), 0), w - 1)
        y1i = min(max(round(y2), 0), h - 1)
        dx = abs(x1i - x0)
        dy = -abs(y1i - y0)
        sx = 1 if x0 < x1i else -1
        sy = 1 if y0 < y1i else -1
        err = dx + dy
        samples: list[float] = []
        x, y = x0, y0
        guard = 0
        while guard < (h + w + 4):
            if 0 <= x < w and 0 <= y < h:
                samples.append(float(arr[y, x]))
            if x == x1i and y == y1i:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
            guard += 1
        if not samples:
            return None
        sample_arr = np.asarray(samples, dtype=np.float64)
        return {
            "count": int(sample_arr.size),
            "mean": float(sample_arr.mean()),
            "min": float(sample_arr.min()),
            "max": float(sample_arr.max()),
            "std": float(sample_arr.std()),
        }

    @staticmethod
    def _effective_pixel_spacing_mm(dicom_spacing_mm) -> tuple[list | None, str]:
        """Return (spacing, source) honoring a manual mm/pixel override.

        Auto calibration reads the DICOM PixelSpacing (NEMA PS3.3,
        C.7.6.2.1.1). A manual override replaces it for every measurement and
        must be validated against a certified phantom before any quantitative
        interpretation (see AAPM practice guidance).
        """
        if st.session_state.get("viewer_measure_manual", False):
            raw = st.session_state.get("viewer_measure_factor")
            try:
                factor = float(raw) if raw not in (None, 0, "") else 0.0
            except (TypeError, ValueError):
                factor = 0.0
            if factor > 0:
                return [factor, factor], "manual"
        return list(dicom_spacing_mm) if dicom_spacing_mm else None, "dicom"

    @staticmethod
    def _measurement_display(item: dict) -> str:
        """Short display string for a stored measurement item.

        The value is rendered in the unit snapshotted when the measurement
        was created (mm/cm/px), so the sidebar and the HTML report stay stable
        even after the display unit or precision settings change later.
        """
        kind = item.get("kind")
        try:
            precision = int(item.get("precision", 2))
        except (TypeError, ValueError):
            precision = 2
        if kind == "angle":
            normalized = ClinicalApp._normalized_measurement(item)
            degrees = normalized.get("degrees")
            return (
                "n/a deg"
                if degrees is None
                else f"{float(degrees):.{precision}f} deg"
            )
        px = item.get("px")
        mm = item.get("mm")
        unit = item.get("unit") or "mm"
        if unit == "px":
            if px is None:
                return "n/a px"
            return f"{float(px):.{precision}f} px"
        if mm is None:
            if px is None:
                return "n/a"
            return f"{float(px):.{precision}f} px (no spacing)"
        if unit == "cm":
            return f"{float(mm) / 10.0:.{precision}f} cm"
        return f"{float(mm):.{precision}f} mm"

    @staticmethod
    def _files_fingerprint(files_list: list) -> str:
        """Stable short hash of input identity and local file changes."""
        digest = hashlib.md5()
        for item in files_list or []:
            name = str(getattr(item, "name", str(item)))
            parts = [name]
            upload_size = getattr(item, "size", None)
            if upload_size is not None:
                try:
                    parts.append(str(int(upload_size)))
                except (TypeError, ValueError):
                    pass
            else:
                try:
                    path = Path(name)
                    stat = path.stat()
                    parts.extend([str(stat.st_size), str(stat.st_mtime_ns)])
                except OSError:
                    pass
            digest.update("|".join(parts).encode("utf-8", "replace"))
        return digest.hexdigest()[:12]

    def _series_label(self, group: dict, files_list: list, explicit_index=None) -> str:
        """Human label for a series group column ('series · modality · file')."""
        index = explicit_index
        if index is None and group.get("indices"):
            index = group["indices"][0]
        base = ""
        if index is not None and 0 <= int(index) < len(files_list or []):
            item = files_list[int(index)]
            base = Path(str(getattr(item, "name", str(item)))).name
        parts = [
            group.get("description") or "Series",
            group.get("modality") or "",
            base,
        ]
        return " · ".join(part for part in parts if part)

    def _build_series_index(self, files_list: list, *, limit: int = 250) -> list[dict]:
        """Group DICOM inputs by (StudyInstanceUID, SeriesInstanceUID).

        Headers are read without pixel decoding (``stop_before_pixels``), so
        this is cheap even for large cohorts. Group order follows first
        appearance in *files_list*; non-DICOM inputs fall into one logical
        group keyed by an empty UID pair.
        """
        grouped: dict[tuple[str, str], dict] = {}
        order: list[tuple[str, str]] = []
        for index, target in enumerate(list(files_list or [])[:limit]):
            meta = self._read_dicom_presentation_metadata(target)
            study = meta.get("study_instance_uid") or ""
            series = meta.get("series_instance_uid") or ""
            key = (study, series)
            if key not in grouped:
                grouped[key] = {
                    "study_uid": study,
                    "series_uid": series,
                    "description": meta.get("series_description") or "",
                    "patient_label": meta.get("patient_id") or "",
                    "modality": meta.get("modality") or "",
                    "indices": [],
                }
                order.append(key)
            grouped[key]["indices"].append(index)
        groups = [grouped[key] for key in order]
        for group in groups:
            group["count"] = len(group["indices"])
        return groups

    @staticmethod
    def _deidentified_dicom_bytes(target) -> bytes | None:
        """Serialize an anonymized copy of a DICOM input, or None on failure."""
        try:
            from io import BytesIO

            if hasattr(target, "seek"):
                target.seek(0)
                dataset = pydicom.dcmread(target)
                target.seek(0)
            else:
                dataset = pydicom.dcmread(str(target))
            from core.dicom_privacy import deidentify_dataset

            output = BytesIO()
            deidentify_dataset(dataset).save_as(output)
            return output.getvalue()
        except Exception:
            return None

    @staticmethod
    def _measurement_coords_valid(kind: str, data: dict | None) -> bool:
        """Return True only when the measurement has real clicked points.

        Endpoints may legitimately sit at pixel (0, 0); the guard rejects
        missing, null, non-numeric or NaN coordinates so a machine never
        fabricates a corner-anchored line from an empty value.
        """
        if not isinstance(data, dict):
            return False
        keys = ["x1", "y1", "x2", "y2"]
        if kind == "angle":
            keys += ["x3", "y3"]
        for key in keys:
            value = data.get(key)
            if value is None or isinstance(value, bool):
                return False
            try:
                if not np.isfinite(float(value)):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _stored_measurements(value) -> list:
        """Read both the current record schema and legacy list values."""
        if isinstance(value, dict):
            value = value.get("measurements", [])
        return list(value) if isinstance(value, list) else []

    @staticmethod
    def _add_measurement(
        kind: str,
        data: dict,
        pixel_spacing_mm,
        source_values: np.ndarray | None = None,
        label: str = "",
    ) -> None:
        """Append a line or angle measurement to the per-image session list.

        Each item snapshots its effective calibration source (DICOM or manual
        override), the display unit and precision, an automatic color and the
        optional user label. Distances also store the first-order intensity
        profile along the ruled segment so measurements stay stable in the
        sidebar and in the HTML report independently of later UI changes.
        """
        items = st.session_state.setdefault("measurements", [])
        color = _MEASURE_COLORS[len(items) % len(_MEASURE_COLORS)]
        unit = str(st.session_state.get("viewer_measure_unit") or "mm")
        try:
            precision = int(st.session_state.get("viewer_measure_precision", "2"))
        except (TypeError, ValueError):
            precision = 2
        spacing, calib_source = ClinicalApp._effective_pixel_spacing_mm(
            pixel_spacing_mm
        )
        mm_per_px = None
        if spacing and len(spacing) >= 2 and all(float(v) > 0 for v in spacing[:2]):
            # Retained for compatibility; anisotropic calibration is stored
            # separately so the UI never implies a single scale when there
            # are distinct row and column spacings.
            mm_per_px = float(np.mean([spacing[0], spacing[1]]))
        if not ClinicalApp._measurement_coords_valid(kind, data):
            return
        px = None
        mm = None
        if kind == "distance":
            px, mm = ClinicalApp._measure_distance(
                data["x1"], data["y1"], data["x2"], data["y2"], spacing
            )
        elif kind == "angle":
            degrees = ClinicalApp._measure_angle(
                data["x1"],
                data["y1"],
                data["x2"],
                data["y2"],
                data["x3"],
                data["y3"],
                spacing,
            )
        else:
            return
        profile = None
        if kind == "distance" and source_values is not None:
            profile = ClinicalApp._measure_line_profile(
                source_values,
                data["x1"],
                data["y1"],
                data["x2"],
                data["y2"],
            )
        item = {
            "kind": kind,
            "label": str(label or "").strip()[:60],
            "color": color,
            "data": dict(data),
            "px": px,
            "mm": mm if kind == "distance" else None,
            "degrees": degrees if kind == "angle" else None,
            "mm_per_px": mm_per_px,
            "pixel_spacing_mm": list(spacing[:2]) if spacing and len(spacing) >= 2 else None,
            "calib_source": calib_source,
            "unit": "deg" if kind == "angle" else unit,
            "precision": precision,
            "profile": profile,
        }
        items.append(item)
        st.session_state["measurements"] = items[-50:]
        active_key = st.session_state.get("_measure_sig")
        if active_key:
            st.session_state.setdefault("_measurement_store", {})[active_key] = {
                "file_id": st.session_state.get("current_file", active_key),
                "file_index": int(st.session_state.get("viewer_index", 0)),
                "slice_index": int(st.session_state.get("viewer_slice_index", 0)),
                "measurements": list(st.session_state["measurements"]),
            }

    def _build_cohort_metrics_csv(self, files_list: list, *, limit: int = 30) -> bytes | None:
        """Merge per-file first-order radiomics/statistics into a single CSV."""
        fieldnames = [
            "file",
            "source_hash",
            "status",
            "error_code",
            "error_message",
            "modality",
            "mean",
            "std",
            "entropy",
            "skewness",
            "kurtosis",
            "p10",
            "p90",
            "n_voxels",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        empty_row = {key: "" for key in fieldnames}
        for item in list(files_list or [])[:limit]:
            name = str(getattr(item, "name", str(item)))
            safe_name = self._safe_export_stem(name)
            row = dict(empty_row)
            row["file"] = safe_name
            row["source_hash"] = pseudonymous_identifier(name)
            try:
                data, _uid, modality = self._load_image(item)
                if isinstance(data, str) or data is None or data.size == 0:
                    row["status"] = "failed"
                    row["error_code"] = "EMPTY_OR_REJECTED_DATA"
                    row["error_message"] = (
                        str(data)[:240] if isinstance(data, str)
                        else "No pixel data was available."
                    )
                    writer.writerow(row)
                    continue
                array = np.asarray(data)
                if array.ndim > 3:
                    while array.ndim > 3:
                        axis = int(np.argmin(array.shape))
                        array = np.take(array, array.shape[axis] // 2, axis=axis)
                if array.ndim == 3 and array.shape[-1] not in (3, 4):
                    axis = int(np.argmin(array.shape))
                    array = np.take(array, array.shape[axis] // 2, axis=axis)
                if array.ndim == 3 and array.shape[-1] in (3, 4):
                    array = np.asarray(
                        Image.fromarray(array.astype(np.uint8)).convert("L")
                    ).astype(np.float32)
                if array.ndim == 2 and array.size == 0:
                    row["status"] = "failed"
                    row["error_code"] = "EMPTY_ARRAY"
                    row["error_message"] = "The decoded image array is empty."
                    writer.writerow(row)
                    continue
                array = np.asarray(array).reshape(-1).astype(np.float64)
                finite = array[np.isfinite(array)]
                if finite.size == 0:
                    row["status"] = "failed"
                    row["error_code"] = "NO_FINITE_PIXELS"
                    row["error_message"] = "No finite pixel values were available."
                    writer.writerow(row)
                    continue
                row.update(
                    {
                        "file": safe_name,
                        "status": "success",
                        "modality": str(modality or ""),
                        "mean": f"{float(np.mean(finite)):.4f}",
                        "std": f"{float(np.std(finite)):.4f}",
                        "n_voxels": f"{int(finite.size)}",
                    }
                )
                hist = RadiomicsExtractor.full_report(finite).get("histogram", {})
                for key in ("entropy", "skewness", "kurtosis", "p10", "p90"):
                    if hist.get(key) is not None:
                        row[key] = f"{float(hist[key]):.4f}"
            except Exception as exc:
                logger.warning("cohort metrics failed for %s: %s", name, exc)
                row["status"] = "failed"
                row["error_code"] = "PROCESSING_ERROR"
                row["error_message"] = str(exc)[:240]
            writer.writerow(row)
        return output.getvalue().encode("utf-8-sig")

    def _render_comparison_pair(
        self,
        current_disp: np.ndarray,
        compare_target,
        *,
        compare_id: str,
        slice_index: int,
        w_center: float,
        w_width: float,
        is_ct: bool,
        analysis_modality: str,
    ) -> None:
        """Render the active image next to the same frame of another file.

        Both frames use the same slice index and the same display window so
        the comparison is fair; intensities are never re-quantized to 8 bits.
        """
        st.caption(
            f"Same slice index {slice_index + 1}, same display window "
            f"(center {w_center}, width {w_width})."
        )
        lang = st.session_state.get("app_lang", "en")
        compare_disp = None
        compare_caption = compare_id
        try:
            other_data, _, other_modality = self._load_image(compare_target)
            if isinstance(other_data, str) or other_data is None or other_data.size == 0:
                compare_caption = f"{compare_id} (could not be decoded)"
            else:
                array = np.asarray(other_data)
                if array.ndim > 3:
                    while array.ndim > 3:
                        axis = int(np.argmin(array.shape))
                        array = np.take(array, array.shape[axis] // 2, axis=axis)
                if array.ndim == 3 and array.shape[-1] in (3, 4):
                    compare_disp = self._prepare_color_display(array)
                else:
                    if array.ndim == 3:
                        slice_axis = int(np.argmin(array.shape))
                        array = np.take(
                            array,
                            min(slice_index, array.shape[slice_axis] - 1),
                            axis=slice_axis,
                        )
                    array = np.asarray(array)
                    if array.ndim == 2:
                        if is_ct:
                            compare_disp = self._apply_windowing(
                                array, center=w_center, width=w_width
                            )
                        else:
                            pmin, pmax = float(np.percentile(array, 1)), float(
                                np.percentile(array, 99)
                            )
                            compare_disp = np.clip(
                                (array - pmin) / max(pmax - pmin, 1e-9) * 255,
                                0,
                                255,
                            ).astype(np.uint8)
                    compare_caption = f"{compare_id} · {other_modality or 'image'}"
        except Exception as exc:
            logger.warning("comparison failed for %s: %s", compare_id, exc)
            compare_caption = f"{compare_id} (error)"

        left_col, right_col = st.columns(2, gap="small")
        left_col.image(
            current_disp,
            caption=safe_img_alt(_i18n.CAP_VIEWER[lang], modality=analysis_modality),
            width="stretch",
            output_format="PNG",
        )
        if compare_disp is not None:
            right_col.image(
                compare_disp,
                caption=compare_caption,
                width="stretch",
                output_format="PNG",
            )
        else:
            right_col.caption(compare_caption)

    @staticmethod
    def _build_html_research_report(data: dict) -> str:
        """Serialize a self-contained research report (print-friendly HTML)."""
        from datetime import datetime

        lang = st.session_state.get("app_lang", "en")
        safe_file_id = ClinicalApp._safe_export_stem(
            str(data.get("file_id") or "image"),
            int(data.get("image_index", 1) or 1) - 1,
        )

        def _text(value):
            return html.escape(str(value)) if value is not None else "Not available"

        def _safe(value):
            return str(value) if value is not None else ""

        dicom = data.get("dicom") or {}
        rows: list[str] = []
        rows.append(
            '<div class="report-head">'
            '<div class="report-brand">HEEH-V1™ DICOM Viewer</div>'
            '<h1>HEEH-V1™ DICOM Viewer — Research Report</h1>'
            '<p class="report-tag">Generated for research and education. '
            "This is not a medical device output and has no clinical validity.</p>"
            "</div>"
        )
        rows.append(
            "<h2>Study and series</h2>"
            f"<p><b>Modality:</b> {_text(data.get('modality'))} &nbsp; "
            f"<b>DICOM series:</b> {_text(dicom.get('series_description'))} &nbsp; "
            f"<b>Series UID:</b> {_text(dicom.get('series_instance_uid'))}</p>"
            f"<p><b>Matrix:</b> "
            f"{_safe(dicom.get('rows'))} x {_safe(dicom.get('columns'))} &nbsp; "
            f"<b>Spacing:</b> {_text(', '.join(str(v) for v in dicom.get('pixel_spacing_mm') or []) or 'n/a')} mm &nbsp; "
            f"<b>Window (C/W):</b> {_text(data.get('w_center'))} / {_text(data.get('w_width'))} &nbsp; "
            f"<b>SOP:</b> {_text(dicom.get('sop_class_name'))} &nbsp; "
            f"<b>Transfer:</b> {_text(dicom.get('transfer_syntax_name'))}</p>"
            f"<p><b>Image:</b> file {data.get('image_index', '?')} of "
            f"{data.get('num_files', '?')} · slice {data.get('slice_index', 0) + 1} "
            f"of {data.get('slice_count', '?')}</p>"
        )
        measurements = data.get("measurements") or []
        if measurements:
            lines = []
            for i, item in enumerate(measurements):
                kind_word = "Distance" if item.get("kind") == "distance" else "Angle"
                name = _text(item.get("label")) or f"{kind_word} {i + 1}"
                value_text = _text(ClinicalApp._measurement_display(item))
                color = _safe(item.get("color")) or "#8ef0c8"
                if item.get("calib_source") == "manual":
                    calib_extra = " (manual calibration override)"
                elif item.get("mm_per_px") is None:
                    calib_extra = " (no PixelSpacing; pixel values)"
                else:
                    calib_extra = ""
                lines.append(
                    f"<li><span style='color:{color}'><b>{_text(name)}</b></span>: "
                    f"{kind_word} = {value_text}{calib_extra}</li>"
                )
                profile = item.get("profile")
                if profile:
                    lines.append(
                        f"<li style='margin-left:1.25em' class='report-note'>"
                        f"Line intensity profile: mean {profile['mean']:.2f}, "
                        f"min {profile['min']:.2f}, max {profile['max']:.2f}, "
                        f"SD {profile['std']:.2f} ({profile.get('count', '?')} samples)"
                        f"</li>"
                    )
            rows.append(
                "<h2>Measurements</h2>"
                f"<ul>{''.join(lines)}</ul>"
                "<p class=\"report-note\">Geometric calibration uses the DICOM "
                "PixelSpacing (NEMA PS3.3, C.7.6.2.1.1); a manual mm/pixel factor "
                "overrides it per measurement and must be validated against a "
                "certified phantom before quantitative interpretation. Values are "
                "research descriptors, not clinical findings.</p>"
            )
        roi = data.get("roi") or {}
        if roi:
            ci = roi.get("ci")
            ci_text = (
                f"[{ci[0]:.1f}, {ci[1]:.1f}]" if isinstance(ci, (list, tuple)) else "n/a"
            )
            rows.append(
                "<h2>ROI analysis</h2>"
                f"<p><b>ROI radius:</b> {_safe(roi.get('radius_px'))} px &nbsp; "
                f"<b>Voxels:</b> {_safe(roi.get('n_voxels'))} &nbsp; "
                f"<b>Mean HU:</b> {_safe(roi.get('mean'))} &nbsp; "
                f"<b>SD:</b> {_safe(roi.get('std'))} &nbsp; "
                f"<b>95% CI:</b> {ci_text} "
                f"({_text(roi.get('ci_method') or 'Student t interval')})</p>"
                "<p class=\"report-note\">The interval is a descriptive "
                "voxel-level calculation under an independence assumption; it "
                "must not be interpreted as a patient-level confidence interval.</p>"
            )
        ai = data.get("ai") or {}
        if ai.get("label"):
            rows.append(
                "<h2>AI inference (ViT demonstration)</h2>"
                f"<p><b>Label:</b> {_text(ai.get('label'))} &nbsp; "
                f"<b>Score:</b> {_safe(ai.get('confidence'))} &nbsp; "
                f"<p>{_text(ai.get('message'))}</p>"
            )
        quality = data.get("quality") or {}
        if quality:
            quality_html = " ".join(
                f"<b>{_text(key)}:</b> {_text(value)}" for key, value in quality.items()
            )
            rows.append(f"<h2>Quality metrics</h2><p>{quality_html}</p>")
        radiomics = data.get("radiomics") or {}
        if radiomics:
            radio_html = " ".join(
                f"<b>{_text(key)}:</b> {_text(value)}"
                for key, value in radiomics.items()
            )
            rows.append(
                "<h2>Radiomics (first-order)</h2>"
                f"<p>{radio_html}</p>"
                "<p class=\"report-note\">The report records the declared "
                "discretization and provenance when available. Resampling, "
                "resegmentation, and feature-specific IBSI validation remain "
                "study-specific requirements. These selected features must not "
                "be described as fully IBSI-compliant without benchmark "
                "validation.</p>"
            )
        native = data.get("native_stats") or {}
        if native:
            native_html = " ".join(
                f"<b>{_text(key)}:</b> {_text(value)}" for key, value in native.items()
            )
            rows.append(f"<h2>Native-intensity statistics</h2><p>{native_html}</p>")
        rows.append(
            '<div class="report-foot">'
            "<p><b>Product:</b> HEEH-V1™ DICOM Viewer · "
            "Research/education edition</p>"
            f"<p>Configuration: window preset <b>{_text(data.get('window_preset'))}</b>, "
            f"center {_text(data.get('w_center'))}, width {_text(data.get('w_width'))}, "
            f"viewer zoom {_safe(data.get('zoom'))}, measure mode "
            f"{_text(data.get('measure_mode'))} (unit "
            f"{_safe(data.get('measure_unit'))}, "
            f"{_safe(data.get('measure_precision'))} decimals).</p>"
            f"<p>Input fingerprint: <code>{_text(safe_file_id)}</code> · "
            f"Locale: {_safe(lang)} · Generated: {datetime.now().isoformat(timespec='minutes')}.</p>"
            "<p class=\"report-note\">All metrics are descriptive research "
            "measurements. The radiologist/physician remains responsible for "
            "final interpretation.</p>"
            "</div>"
        )
        content = "\n".join(rows)
        return (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>HEEH-V1™ DICOM Viewer — Research Report</title>"
            "<meta name=\"application-name\" content=\"HEEH-V1™ DICOM Viewer\">"
            "<meta name=\"description\" content=\"Research report generated by HEEH-V1™ DICOM Viewer\">"
            "<style>"
            "body{font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;color:#1a202c;"
            "max-width:840px;margin:2rem auto;padding:0 1rem}"
            "h1{font-size:1.5rem;margin:0 0 .25rem}h2{font-size:1.05rem;"
            "margin:1.25rem 0 .35rem;border-bottom:1px solid #e2e8f0;padding-bottom:.25rem}"
            ".report-head{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
            "padding:.9rem 1rem;margin-bottom:1.25rem}"
            ".report-brand{font-weight:700;letter-spacing:.02em;color:#334155;"
            "font-size:.9rem;margin-bottom:.25rem}"
            ".report-tag{color:#64748b;margin:0}.report-note{color:#64748b;font-size:.85rem}"
            ".report-foot{margin-top:1.5rem;border-top:1px solid #e2e8f0;padding-top:.75rem;"
            "color:#475569;font-size:.85rem}li{margin:.15rem 0}code{background:#f1f5f9;"
            "padding:1px 4px;border-radius:3px}"
            "@media print{body{margin:0;max-width:none}.report-head{break-inside:avoid}}"
            "</style></head><body>" + content + "</body></html>"
        )

    # ------------------------------------------------------------------
    # TCIA .tcia manifest support (on-demand, single-series downloads).
    # ------------------------------------------------------------------
    # NBIA v4 production moved to nbia.cancerimagingarchive.net.  The v4
    # contract uses GET /getSeries for series summaries and does not accept
    # the legacy includeAnnotation parameter on /getImage.
    _TCIA_IMAGE_URL = "https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getImage"
    _TCIA_META_URL = "https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getSeries"
    _TCIA_HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "HEEH-V1-DICOM-Viewer/1.0",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    _TCIA_META_HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "HEEH-V1-DICOM-Viewer/1.0",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    _IMAGE_EXTENSIONS = ('.dcm', '.dicom', '.nii', '.nii.gz', '.nrrd', '.mha',
                         '.mhd', '.ima', '.img')
    _TCIA_CONNECT_TIMEOUT = _positive_timeout_from_env(
        "HEEH_TCIA_CONNECT_TIMEOUT", 15.0
    )
    _TCIA_METADATA_READ_TIMEOUT = _positive_timeout_from_env(
        "HEEH_TCIA_METADATA_READ_TIMEOUT", 60.0
    )
    _TCIA_DOWNLOAD_READ_TIMEOUT = _positive_timeout_from_env(
        "HEEH_TCIA_DOWNLOAD_READ_TIMEOUT", 180.0
    )
    _TCIA_SESSION = None

    @classmethod
    def _get_tcia_session(cls):
        """Get or create a persistent requests.Session with connection pooling."""
        if cls._TCIA_SESSION is None:
            cls._TCIA_SESSION = __import__('requests').Session()
            retry_strategy = Retry(
                total=0,
                connect=0,
                read=0,
                redirect=0,
                status_forcelist=[],
            )
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=6,
                pool_maxsize=6,
                pool_block=False,
            )
            cls._TCIA_SESSION.mount("http://", adapter)
            cls._TCIA_SESSION.mount("https://", adapter)
        return cls._TCIA_SESSION

    @staticmethod
    def _cleanup_stale_partial_downloads(cache_dir: Path, age_days: int = 7):
        """Remove partial archives older than age_days to free space."""
        cutoff = time.time() - (age_days * 86400)
        cleaned = 0
        for partial in cache_dir.glob("*.zip.part"):
            try:
                if partial.stat().st_mtime < cutoff:
                    partial.unlink()
                    cleaned += 1
                    get_logger("app").info(f"Cleaned stale partial: {partial.name}")
            except OSError:
                pass
        return cleaned

    @classmethod
    def _check_archive_ready(cls, url: str, params: dict, headers: dict,
                             timeout: int = 15) -> bool:
        """Use HEAD to detect if TCIA archive is ready (server-side preparation done)."""
        try:
            session = cls._get_tcia_session()
            resp = session.head(url, params=params, headers=headers, timeout=timeout, allow_redirects=True)
            return resp.status_code in (200, 206, 416)
        except Exception:
            return False

    def _is_image_file(self, path):
        """Filter out non-image files (e.g. LICENSE) from extracted TCIA zips:
        keep files with a known imaging extension or DICOM magic bytes."""
        name = Path(path).name.lower()
        if any(name.endswith(ext) for ext in self._IMAGE_EXTENSIONS):
            return True
        try:
            with open(path, "rb") as f:
                f.seek(128)
                return f.read(4) == b"DICM"
        except OSError:
            return False

    @staticmethod
    def _is_allowed_manifest_url(url: str) -> bool:
        """Allow only the trusted TCIA API host for remote manifest inputs."""
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in {
                "nbia.cancerimagingarchive.net",
                "services.cancerimagingarchive.net",
            }
            and not parsed.username
            and not parsed.password
            and parsed.port is None
        )

    def _tcia_files_to_analyze(self, files):
        """Return the list of downloaded TCIA files for analysis."""
        return [str(p) for p in files if self._is_image_file(p)]

    def _parse_tcia_manifest(self, raw_text):
        """Parse an NBIA .tcia manifest into a list of SeriesInstanceUIDs."""
        uids = [line.strip() for line in raw_text.splitlines()
                if re.fullmatch(r"[0-9.]+", line.strip())]
        return uids

    def _parse_manifest_file(self, manifest_target, ext=None):
        """Parse any supported manifest into an offline preview dict.

        .tcia manifests reuse _parse_tcia_manifest; other formats are parsed
        as CSV-like (tab/comma/semicolon/pipe separated) with # comment
        skipping. No downloads, authentication, or remote calls are made.
        """
        try:
            name = getattr(manifest_target, "name", manifest_target)
            file_name = Path(name).name
            ext = ext or Path(file_name).suffix.lower()
            if file_name.lower().endswith(".nii.gz"):
                ext = ".nii.gz"
            if hasattr(manifest_target, "read"):
                manifest_target.seek(0)
                raw_text = manifest_target.read().decode("utf-8", errors="ignore")
            else:
                target = Path(manifest_target)
                if not target.exists():
                    return {"error": f"File not found: {target.name}",
                            "file_name": file_name, "format": ext}
                raw_text = target.read_text(encoding="utf-8", errors="ignore")
            if ext == ".tcia":
                uids = self._parse_tcia_manifest(raw_text)
                return {"format": "tcia", "file_name": file_name,
                        "series_uids": uids, "row_count": len(uids),
                        "id_column": "SeriesInstanceUID", "url_column": None,
                        "comments": [], "header": [], "rows": []}
            return self._parse_csv_like(raw_text, file_name, ext)
        except Exception as exc:
            return {"error": str(exc),
                    "file_name": getattr(manifest_target, "name", "manifest"),
                    "format": ext}

    def _parse_csv_like(self, raw_text, file_name, ext=None):
        """Parse a CSV-like manifest (tab/comma/semicolon/pipe) offline."""
        lines = raw_text.splitlines()
        comments = [line.strip() for line in lines
                    if line.strip() and line.strip().startswith("#")]
        body_lines = [line.strip() for line in lines
                      if line.strip() and not line.strip().startswith("#")]
        result = {"format": ext or "csv", "file_name": file_name,
                  "comments": comments, "header": [], "rows": [],
                  "id_column": None, "url_column": None, "row_count": 0}
        if not body_lines:
            return result
        header_line = body_lines[0]
        delimiter = None
        best_count = -1
        for candidate in ("\t", ",", ";", "|"):
            count = header_line.count(candidate)
            if count > best_count:
                best_count = count
                delimiter = candidate
        if best_count <= 0:
            header = [token for token in re.split(r"\s+", header_line) if token]
            def splitter(text):
                return [token for token in re.split(r"\s+", text) if token]
        else:
            header = [token.strip() for token in header_line.split(delimiter)]
            def splitter(text):
                return [token.strip() for token in text.split(delimiter)]
        id_column = None
        url_column = None
        url_keywords = ("url", "link", "download", "http")
        for col in header:
            low = col.lower()
            if any(keyword in low for keyword in url_keywords):
                if url_column is None:
                    url_column = col
                continue
            if id_column is not None:
                continue
            tokens = [t for t in re.split(r"[^a-z0-9]+", low) if t]
            if tokens and tokens[-1].endswith("id"):
                id_column = col
        seen = set()
        rows = []
        for text in body_lines[1:]:
            fields = splitter(text)
            if len(fields) < len(header):
                fields = fields + [""] * (len(header) - len(fields))
            elif len(fields) > len(header):
                fields = fields[:len(header)]
            key = tuple(fields)
            if key in seen:
                continue
            seen.add(key)
            rows.append(dict(zip(header, fields, strict=True)))
        if url_column is None:
            for col in header:
                if "path" not in col.lower():
                    continue
                values = [row[col] for row in rows if row.get(col)]
                if any(value.startswith(("http://", "https://")) for value in values) or any(
                    re.search(r"patient\d", value, re.IGNORECASE) for value in values
                ):
                    url_column = col
                    break
        if id_column is None and url_column is not None:
            id_column = url_column
        result["header"] = header
        result["rows"] = rows
        result["id_column"] = id_column
        result["url_column"] = url_column
        result["row_count"] = len(rows)
        return result

    def _render_manifest_preview(self, parsed):
        """Render an offline manifest preview for a parsed manifest dict."""
        st.markdown("## Manifest Preview")
        if parsed.get("error"):
            logger.warning("manifest parse error: %s", parsed["error"])
            st.error(f"Could not parse manifest: {parsed['error']}")
            return
        fname = parsed.get("file_name", "manifest")
        fmt = parsed.get("format", "?")
        row_count = parsed.get("row_count", 0)
        id_col = parsed.get("id_column") or "-"
        url_col = parsed.get("url_column") or "-"
        st.caption(f"**{fname}**  `{fmt}`  {row_count} rows  "
                   f"ID column: {id_col}  URL column: {url_col}")
        comments = parsed.get("comments") or []
        if comments:
            with st.expander(f"Comments / header notes ({len(comments)})"):
                st.code("\n".join(comments), language=None)
        rows = parsed.get("rows") or []
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info("No data rows found in this manifest.")
        st.info("Offline preview only - no download performed. "
                "TCIA `.tcia` manifests are the only formats that download "
                "via the NBIA API.")

    def _fetch_tcia_metadata(self, series_uids, cache_dir):
        """Fetch series metadata (CSV) from the TCIA v4 API, cached on disk."""
        import requests
        from io import StringIO

        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.md5(",".join(series_uids).encode("utf-8")).hexdigest()
        cache_path = cache_dir / f"{key}.csv"
        if cache_path.exists():
            try:
                with cache_path.open(newline="", encoding="utf-8") as handle:
                    cached = csv.DictReader(handle)
                    if cached.fieldnames and any(row for row in cached):
                        return str(cache_path)
            except (OSError, csv.Error):
                logger.warning("Ignoring invalid TCIA metadata cache: %s", cache_path)
        headers = {
            **self._TCIA_META_HEADERS,
            "Accept": "text/csv, application/json;q=0.9, */*;q=0.1",
        }
        # NBIA deployments differ: current v4 accepts GET with
        # SeriesInstanceUID, while older installations expose the v2 route.
        # Query each UID independently so one malformed UID cannot invalidate
        # the complete manifest.
        endpoints = [
            self._TCIA_META_URL,
            self._TCIA_META_URL.replace("/v4/", "/v2/"),
            "https://services.cancerimagingarchive.net/nbia-api/services/v2/getSeries",
        ]
        session = self._get_tcia_session()

        def _fetch_one(uid):
            local_errors = []
            fetched = False
            response_text = None
            for endpoint in endpoints:
                try:
                    resp = session.get(
                        endpoint,
                        params={"SeriesInstanceUID": uid, "format": "csv"},
                        headers=headers,
                        timeout=(
                            self._TCIA_CONNECT_TIMEOUT,
                            self._TCIA_METADATA_READ_TIMEOUT,
                        ),
                    )
                    resp.raise_for_status()
                    text = resp.text.lstrip()
                    if text and not text.startswith(("<", "{", "[")):
                        response_text = resp.text
                        fetched = True
                        break
                    if text.startswith(("{", "[")):
                        payload = resp.json()
                        if isinstance(payload, dict):
                            for key_name in ("data", "results", "items", "records"):
                                candidate = payload.get(key_name)
                                if isinstance(candidate, list):
                                    payload = candidate
                                    break
                            else:
                                payload = [payload]
                        if isinstance(payload, list) and payload and all(
                            isinstance(row, dict) for row in payload
                        ):
                            fieldnames = sorted({key for row in payload for key in row})
                            output = StringIO()
                            writer = csv.DictWriter(output, fieldnames=fieldnames)
                            writer.writeheader()
                            writer.writerows(payload)
                            response_text = output.getvalue()
                            fetched = True
                            break
                except (OSError, ValueError, requests.RequestException) as exc:
                    local_errors.append(f"{uid}: {exc}")
            if not fetched:
                logger.warning("TCIA metadata unavailable for %s", uid)
            return uid, response_text, local_errors

        responses = []
        errors = []
        # Metadata requests are independent. Parallelize the small header/API
        # calls, while keeping downloads explicitly user-triggered below.
        worker_count = min(6, max(1, len(series_uids)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_fetch_one, uid) for uid in series_uids]
            for future in as_completed(futures):
                _uid, response_text, local_errors = future.result()
                if response_text:
                    responses.append(response_text)
                errors.extend(local_errors)

        if not responses:
            detail = "; ".join(errors[-3:])[:500]
            raise RuntimeError(
                "TCIA metadata API returned no usable records"
                + (f": {detail}" if detail else "")
            )

        # Merge CSV responses while preserving one header row.
        rows = []
        fieldnames = []
        for text in responses:
            reader = csv.DictReader(StringIO(text))
            if reader.fieldnames:
                for field in reader.fieldnames:
                    if field not in fieldnames:
                        fieldnames.append(field)
                rows.extend(dict(row) for row in reader)
        if not rows or not fieldnames:
            raise RuntimeError("TCIA metadata API returned no tabular records")
        with cache_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return str(cache_path)

    @staticmethod
    def _extract_tcia_archive(
        archive,
        dest,
        preexisting_files,
        *,
        max_members,
        max_extracted_bytes,
        max_member_bytes,
    ):
        """Safely extract a validated TCIA archive into its series directory."""
        base = dest.resolve()
        members = archive.infolist()
        if len(members) > max_members:
            raise ValueError("Archive contains too many files.")
        total_uncompressed = sum(member.file_size for member in members)
        if total_uncompressed > max_extracted_bytes:
            raise ValueError("Archive expands beyond the safety limit.")
        extracted_bytes = 0
        for member in members:
            if member.is_dir():
                continue
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == 0o120000:
                raise ValueError("Archive contains an unsafe symbolic link.")
            name = member.filename.replace("\\", "/")
            if ".." in name.split("/"):
                raise ValueError("Archive contains a parent traversal path.")
            if member.file_size > max_member_bytes:
                raise ValueError("Archive member exceeds the safety limit.")
            out_path = (base / name).resolve()
            if not out_path.is_relative_to(base):
                raise ValueError("Archive contains an unsafe output path.")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, open(str(out_path), "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_bytes += member.file_size
            if extracted_bytes > max_extracted_bytes:
                raise ValueError("Archive expands beyond the safety limit.")

    def _download_tcia_series(self, series_uid, dest_dir, expected_bytes=None,
                              progress_cb=None):
        """Download a single TCIA series ZIP (v4 getImage) and extract it into
        dest_dir. Returns the list of extracted file paths. Cached on disk.

        progress_cb(frac, done_bytes, total_bytes) is called with a numeric
        fraction in [0, 1] (never None) so Streamlit's st.progress never
        receives an invalid value.
        """
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        complete_marker = dest / ".series.complete"
        existing = [p for p in dest.rglob("*") if p.is_file()
                    and p.name != "series.zip.tmp"
                    and p.name != ".series.complete"]
        preexisting_files = {p.resolve() for p in existing}
        # A stale/partial extraction (e.g. an interrupted unzip) must never be
        # mistaken for a complete series, otherwise the cache is poisoned
        # forever. Only a successful extraction writes the .complete marker.
        if existing and complete_marker.exists():
            return [str(p) for p in existing]

        # Clean stale partial archives to free cache space
        self._cleanup_stale_partial_downloads(dest, age_days=7)

        tmp_zip = dest / "series.zip.tmp"
        last_err = None
        max_archive_bytes = 2 * 1024**3
        max_extracted_bytes = 10 * 1024**3
        max_member_bytes = 512 * 1024**2
        max_members = 10000
        read_size = 8 * 1024 * 1024
        buffered_download_limit = 512 * 1024**2
        connect_timeout = self._TCIA_CONNECT_TIMEOUT
        read_timeout = self._TCIA_DOWNLOAD_READ_TIMEOUT
        session = self._get_tcia_session()
        
        # Retry loop: the user's connection is flaky; a dropped stream must
        # not abort the whole download permanently. The partial ZIP is kept
        # and resumed with a byte range after a transport failure.
        for attempt in range(1, 6):
            download_completed = False
            try:
                resume_at = tmp_zip.stat().st_size if tmp_zip.exists() else 0
                request_headers = dict(self._TCIA_HEADERS)
                if resume_at:
                    request_headers["Range"] = f"bytes={resume_at}-"
                use_buffered_download = (
                    resume_at == 0
                    and expected_bytes is not None
                    and 0 < expected_bytes <= buffered_download_limit
                )
                resp = session.get(
                    self._TCIA_IMAGE_URL,
                    params={
                        "SeriesInstanceUID": series_uid,
                    },
                    headers={**request_headers, "Accept": "application/zip, application/octet-stream"},
                    timeout=(connect_timeout, read_timeout),
                    stream=not use_buffered_download,
                )
                with resp:
                    resp.raise_for_status()
                    if use_buffered_download and hasattr(resp, "content"):
                        payload = resp.content
                        if len(payload) > max_archive_bytes:
                            raise ValueError(
                                "Downloaded archive exceeds the safety limit."
                            )
                        with open(str(tmp_zip), "wb") as fh:
                            fh.write(payload)
                        if progress_cb is not None:
                            progress_cb(1.0, len(payload), len(payload))
                        download_completed = True
                    else:
                        resumed = resume_at > 0 and resp.status_code == 206
                        if resume_at and resp.status_code == 416:
                            content_range = resp.headers.get("Content-Range", "")
                            if content_range.startswith("bytes */"):
                                total_size = int(content_range.split("/", 1)[1])
                                if resume_at == total_size:
                                    download_completed = True
                                    resumed = True
                                    total = total_size
                                    done = resume_at
                                else:
                                    raise requests.RequestException(
                                        "TCIA rejected the requested resume range."
                                    )
                            else:
                                raise requests.RequestException(
                                    "TCIA returned an invalid range response."
                                )
                        if not download_completed and resume_at and not resumed:
                            # Some proxies silently strip Range. Never append a
                            # full response to a partial ZIP.
                            resume_at = 0
                            tmp_zip.unlink(missing_ok=True)
                        total = resp.headers.get("Content-Length")
                        total = int(total) + resume_at if total and resumed else (
                            int(total) if total else (expected_bytes or 0)
                        )
                        done = resume_at
                        if not download_completed:
                            with open(str(tmp_zip), "ab" if resumed else "wb") as fh:
                                # NBIA may use HTTP chunked transfer with very small
                                # wire chunks. Reading from urllib3's raw stream
                                # aggregates them and avoids thousands of Python/UI
                                # iterations for a single series.
                                if hasattr(resp, "raw") and hasattr(resp.raw, "read"):
                                    def _chunks(response=resp):
                                        while True:
                                            chunk = response.raw.read(read_size)
                                            if not chunk:
                                                break
                                            yield chunk
                                else:
                                    def _chunks(response=resp):
                                        yield from response.iter_content(chunk_size=read_size)
                                for chunk in _chunks():
                                    if not chunk:
                                        continue
                                    fh.write(chunk)
                                    done += len(chunk)
                                    if progress_cb is not None:
                                        if total:
                                            frac = min(done / total, 1.0)
                                        else:
                                            # No size known at all: assume ~512 MB as a
                                            # coarse ceiling just to keep the bar moving.
                                            frac = min(done / (512 * 2 ** 20), 1.0)
                                        progress_cb(frac, done, total)
                                    if done > max_archive_bytes:
                                        raise ValueError("Downloaded archive exceeds the safety limit.")
                        download_completed = True
                with zipfile.ZipFile(str(tmp_zip)) as zf:
                    self._extract_tcia_archive(
                        zf,
                        dest,
                        preexisting_files,
                        max_members=max_members,
                        max_extracted_bytes=max_extracted_bytes,
                        max_member_bytes=max_member_bytes,
                    )
                complete_marker.write_text("ok", encoding="utf-8")
                try:
                    tmp_zip.unlink(missing_ok=True)
                except OSError:
                    pass
                last_err = None
                break
            except Exception as e:
                last_err = e
                for extracted in dest.rglob("*"):
                    if (
                        extracted.is_file()
                        and extracted.name not in {"series.zip.tmp", ".series.complete"}
                        and extracted.resolve() not in preexisting_files
                    ):
                        try:
                            extracted.unlink()
                        except OSError:
                            pass
                # Preserve an incomplete archive after a transport failure so
                # the next attempt can request the remaining bytes. Corrupt
                # completed archives and safety-limit failures must restart
                # from a clean file.
                if download_completed or not isinstance(
                    e, (OSError, requests.RequestException, TimeoutError)
                ):
                    try:
                        tmp_zip.unlink(missing_ok=True)
                    except OSError:
                        pass
                if attempt < 5:
                    time.sleep(3 * attempt)
        if last_err is not None:
            raise last_err
        return [str(p) for p in dest.rglob("*")
                if p.is_file() and p.name != ".series.complete" and p.name != "series.zip.tmp"]

    def _run_tcia_manifest_flow(self, manifest_target, cache_root):
        """
        Render the TCIA manifest UI: list series from metadata, let the user
        pick ONE series, download it on demand and return the extracted file
        paths (or [] while waiting for a selection).
        """

        raw_text = None
        if hasattr(manifest_target, 'read'):
            manifest_target.seek(0)
            raw_text = manifest_target.read().decode('utf-8', errors='ignore')
        else:
            raw_text = Path(manifest_target).read_text(encoding='utf-8', errors='ignore')

        series_uids = self._parse_tcia_manifest(raw_text)
        if not series_uids:
            logger.error("TCIA manifest contains no series UIDs")
            st.error("❌ The .tcia manifest contains no series UIDs.")
            return []

        st.markdown("## 📦 TCIA Collection Manifest")
        st.caption(
            f"Found **{len(series_uids)}** series. Select one or more to "
            "download and analyze (cached locally; cache hits are skipped)."
        )

        # Modality filter + series picker (metadata is cached after first fetch).
        try:
            meta_csv = self._fetch_tcia_metadata(series_uids, cache_root / "metadata")
            with open(meta_csv, encoding="utf-8", errors="ignore") as handle:
                rows = list(csv.DictReader(handle))
        except Exception as e:
            logger.warning("TCIA metadata fetch failed: %s", str(e)[:200])
            st.error(f"❌ Failed to fetch TCIA metadata: {str(e)[:200]}")
            return []

        def _fmt_size(s):
            """Format a byte count as a human-readable size string."""
            try:
                b = int(float(s))
            except (TypeError, ValueError):
                return "?"
            if b >= 1024 ** 3:
                return f"{b / 1024 ** 3:.1f} GB"
            if b >= 1024 ** 2:
                return f"{b / 1024 ** 2:.0f} MB"
            return f"{b / 1024:.0f} KB"

        def _label(row):
            """Return a printable label for a UI identifier."""
            mod = row.get("Modality", "?")
            desc = (row.get("SeriesDescription") or "").strip() or "?"
            nimg = row.get("ImageCount", "?")
            size = _fmt_size(row.get("FileSize", "0"))
            extras = []
            proto = (row.get("ProtocolName") or "").strip()
            if proto:
                extras.append(proto)
            date = (row.get("StudyDate") or "").strip()
            if date:
                extras.append(date)
            snum = (row.get("SeriesNumber") or "").strip()
            if snum:
                extras.append(f"#{snum}")
            body = (row.get("BodyPartExamined") or "").strip()
            if body:
                extras.append(body)
            suffix = f" | {' / '.join(extras)}" if extras else ""
            return (f"[{mod}] {desc} | {nimg} imgs | {size}{suffix} | "
                    f"{row.get('SeriesInstanceUID', '')[:24]}")

        modalities = sorted({r.get("Modality", "?") for r in rows})
        if modalities:
            sel_mod = st.multiselect("Modality filter", modalities, default=modalities[:1])
            rows = [r for r in rows if r.get("Modality", "?") in sel_mod]

        if not rows:
            st.info("No series match the selected filter.")
            return []

        def _fsize(row):
            """Return the size of a file, handling missing paths."""
            try:
                return int(float(row.get("FileSize", "0") or 0))
            except (TypeError, ValueError):
                return 0

        # Smallest series first: on slow connections a huge default pick
        # (e.g. a 500 MB CT) would otherwise look like the app is broken.
        rows = sorted(rows, key=_fsize)

        labels = [_label(r) for r in rows]
        # Map each label back to its row (labels may repeat if metadata is sparse).
        label_to_rows = {}
        for r in rows:
            label_to_rows.setdefault(_label(r), []).append(r)

        # Keep selection changes inside a form. Without a form, every click in
        # the multiselect triggers a full Streamlit rerun and can make the
        # metadata/download path appear to restart before submission.
        with st.form("tcia_selection_form", clear_on_submit=False, border=False):
                 sel_labels = st.multiselect(
                     "Series to download",
                     labels,
                     default=[],
                     help="You may select more than one series. Each is downloaded and "
                     "analyzed on its own; a series that fails is skipped without "
                     "cancelling the others.",
                 )
                 start_download = st.form_submit_button(
                     "Download selected series",
                     type="primary",
                     help="Start downloading only after the series selection is complete.",
                 )
        if not sel_labels:
                 st.info("Select one or more series, then start the download.")
                 return []

        if not start_download:
                 st.caption("Selection is ready. Submit the form to start downloading.")
                 return []

        def _row_for(label):
            """Build a display row from raw file metadata."""
            opts = label_to_rows.get(label, [])
            return opts[0] if opts else None

        previous_details = st.session_state.get("tcia_download_details", {})
        visible_details = [
            (label, previous_details.get((_row_for(label) or {}).get("SeriesInstanceUID")))
            for label in sel_labels
        ]
        visible_details = [
            (label, detail) for label, detail in visible_details if detail
        ]
        if visible_details:
            with st.expander("Previous download details", expanded=True):
                for label, detail in visible_details:
                    if detail["status"] == "cached":
                        st.write(
                            f"**{label}** — already cached: "
                            f"{detail['files']:,} files, "
                            f"{detail['bytes'] / 2**20:.1f} MB."
                        )
                    else:
                        st.write(
                            f"**{label}** — {detail['files']:,} files, "
                            f"{detail['bytes'] / 2**20:.1f} MB in "
                            f"{detail['elapsed']:.1f}s "
                            f"({detail['rate'] / 2**20:.2f} MB/s)."
                        )

        import time as _time

        all_files = []
        failed = []
        download_details = st.session_state.setdefault(
            "tcia_download_details", {}
        )
        for label in sel_labels:
            sel_row = _row_for(label)
            if sel_row is None:
                continue
            sel_uid = sel_row["SeriesInstanceUID"]

            title = (f"[{sel_row.get('Modality', '?')}] "
                     f"{(sel_row.get('SeriesDescription') or '').strip() or sel_uid[:12]}")
            st.subheader(f"⬇️ {title}", divider="gray")

            dest_dir = cache_root / sel_uid
            already = (
                [p for p in dest_dir.rglob("*") if p.is_file()
                 and p.name not in {"series.zip.tmp", ".series.complete"}]
                if dest_dir.exists() and (dest_dir / ".series.complete").exists()
                else []
            )
            if already:
                cached_bytes = sum(
                    path.stat().st_size for path in already if path.exists()
                )
                detail = {
                    "status": "cached",
                    "files": len(already),
                    "bytes": cached_bytes,
                    "elapsed": 0.0,
                    "rate": 0.0,
                }
                download_details[sel_uid] = detail
                st.info(
                    f"**Already cached** — {len(already):,} files, "
                    f"{cached_bytes / 2**20:.1f} MB. No download was needed."
                )
                all_files.extend(self._tcia_files_to_analyze(already))
                continue

            expected_bytes = _fsize(sel_row)
            size_mb = expected_bytes / 2 ** 20
            if expected_bytes:
                if size_mb > 100:
                    st.warning(
                        f"This series is **~{size_mb:.0f} MB**. On your current "
                        f"connection this can take a long time (30+ minutes). "
                        f"Consider picking a smaller series for a quick test."
                    )
                else:
                    st.caption(f"Fetching ~{size_mb:.0f} MB from TCIA — usually "
                               f"a few minutes on a normal connection.")

            prog = st.progress(0.0, text="Connecting to TCIA...")
            _t0 = _time.time()
            _last_ui_update = [0.0]
            _downloaded_bytes = [0]

            def _cb(frac, done, total, _prog=prog, _t0=_t0):
                """Render a collapsible UI callback for a checkbox row."""
                _downloaded_bytes[0] = max(_downloaded_bytes[0], done)
                el = _time.time() - _t0
                # Avoid forcing a Streamlit frontend update for every network
                # chunk; the downloader still tracks every byte internally.
                if el - _last_ui_update[0] < 0.25 and frac < 0.999:
                    return
                _last_ui_update[0] = el
                rate = done / el if el > 0 else 0.0
                mb_done = done / 2 ** 20
                txt = f"Downloaded {mb_done:.0f} MB"
                if total:
                    txt += f" / {total / 2 ** 20:.0f} MB"
                if rate > 0:
                    txt += f" @ {rate / 2 ** 20:.2f} MB/s"
                    if total and done < total:
                        eta_s = (total - done) / rate
                        txt += f" | ETA ~{eta_s / 60:.1f} min"
                _prog.progress(min(frac, 0.99), text=txt)

            try:
                files = self._download_tcia_series(
                    sel_uid, str(dest_dir),
                    expected_bytes=expected_bytes, progress_cb=_cb,
                )
            except Exception as e:
                logger.warning("TCIA download failed for %s: %s",
                               sel_uid, str(e)[:200])
                st.error(f"❌ Download failed for {sel_uid}: {str(e)[:200]}")
                failed.append(sel_uid)
                continue

            if not files:
                st.warning(f"Series {sel_uid} ZIP contained no files to analyze.")
                failed.append(sel_uid)
                continue
            elapsed = max(_time.time() - _t0, 0.0)
            downloaded_bytes = _downloaded_bytes[0]
            if not downloaded_bytes:
                downloaded_bytes = sum(
                    path.stat().st_size for path in files
                    if Path(path).exists()
                )
            rate = downloaded_bytes / elapsed if elapsed > 0 else 0.0
            detail = {
                "status": "downloaded",
                "files": len(files),
                "bytes": downloaded_bytes,
                "elapsed": elapsed,
                "rate": rate,
            }
            download_details[sel_uid] = detail
            prog.progress(
                1.0,
                text=(
                    f"Download complete — {downloaded_bytes / 2**20:.1f} MB "
                    f"in {elapsed:.1f}s"
                ),
            )
            st.success(
                f"**Download complete** — {len(files):,} files, "
                f"{downloaded_bytes / 2**20:.1f} MB in {elapsed:.1f}s "
                f"({rate / 2**20:.2f} MB/s). Cached locally."
            )
            all_files.extend(self._tcia_files_to_analyze(files))

        if not all_files:
            if failed:
                logger.error("%d of %d selected series failed; nothing to analyze",
                             len(failed), len(sel_labels))
                st.error(f"❌ {len(failed)} of {len(sel_labels)} selected series "
                         f"failed and nothing was available to analyze.")
            return []
        if failed:
            st.warning(f"⚠️ {len(failed)} of {len(sel_labels)} selected series "
                       f"failed; continuing with the ones that succeeded.")
        st.toast(
            f"Ready to analyze {len(all_files)} files from {len(sel_labels)} selected series.",
            icon="✅",
        )
        return all_files

    def run(self):
        """
        Main Streamlit UI for HEEH-V1™ DICOM Viewer (research tool).
        """
        lang = st.session_state.get("app_lang", "en")

        header_logo = Path(__file__).resolve().parent / "assets" / "heeh-v1-logo.jpg"
        header_left, header_right = st.columns([1, 8], vertical_alignment="center")
        with header_left:
            if header_logo.is_file():
                st.image(str(header_logo), width=88)
        with header_right:
            st.title(PRODUCT_NAME)
        st.caption("Research and education workspace")

        # --- Floating sidebar: input and analysis configuration ---
        def _I(key: str) -> str:
            return _translate(key, lang)
        control_panel = st.sidebar
        with control_panel.expander(_i18n.SECTION_INPUT[lang], expanded=True):
            st.subheader(_I("SIDEBAR_TITLE"))
            # One input surface handles both new studies and exported packages.
            # Exported content is detected after selection and its measurements
            # and presentation settings are restored automatically.
            input_workflow = "Initial input"
            mode_label = _I("SOURCE_MODE")
            if "input_mode_selector" not in st.session_state:
                st.session_state["input_mode_selector"] = st.session_state.get(
                    "input_mode", "Local Directory"
                )
            mode = st.radio(
                mode_label,
                ["Local Directory", "Direct Upload"],
                key="input_mode_selector",
            )
            st.session_state.input_mode = mode

            valid_extensions = (
                ".zip", ".dcm", ".dicom", ".png", ".jpg", ".jpeg",
                ".bmp", ".tif", ".tiff", ".webp", ".nii", ".nii.gz",
                ".nrrd", ".mha", ".mhd", ".ima", ".img",
            )
            manifest_exts = (".tcia", ".tsv", ".csv", ".txt")
            st.caption(
                "Select a study, folder, or exported ZIP/image. Exported "
                "measurements and presentation settings are restored "
                "automatically when detected."
            )
            files_list = []
            workflow_changed = (
                st.session_state.get("_active_input_workflow") != "Unified input"
            )
            st.session_state["_active_input_workflow"] = "Unified input"
            if workflow_changed:
                self._cleanup_export_archives()
                st.session_state.pop("_reopened_measurements", None)
                st.session_state.pop("_restored_display_target", None)
                st.session_state.auto_reader_enabled = False
                st.session_state.pop("_measurement_store", None)
                st.session_state.pop("_measure_sig", None)
                st.session_state.pop("measurements", None)
                st.session_state.pop("viewer_index", None)
                st.session_state.pop("viewer_slice_index", None)
                st.session_state.pop("window_preset_selector", None)
                st.session_state.pop("ct_window_center", None)
                st.session_state.pop("ct_window_width", None)
                st.session_state.pop("_last_window_preset", None)
                st.session_state["viewer_mode"] = "Fit to panel"
                st.session_state["viewer_zoom"] = 1.0
                st.session_state["viewer_view_mode"] = "fit"

            if mode == "Local Directory":
                path = st.text_input(
                    _I("DATA_PATH_LABEL"),
                    placeholder=_I("DATA_PATH_PLACEHOLDER"),
                    key="input_path_initial",
                )
                if path:
                    path_obj = Path(path)
                    if path_obj.exists() and path_obj.is_dir():
                        try:
                            stat = path_obj.stat()
                            entry_count = sum(1 for _ in path_obj.iterdir())
                        except OSError:
                            stat = None
                            entry_count = -1
                        if stat is not None:
                            files_list = _discover_input_files_cached(
                                str(path_obj),
                                tuple(valid_extensions),
                                stat.st_mtime_ns,
                                entry_count,
                            )
                    elif (
                        path_obj.exists()
                        and path_obj.is_file()
                        and (
                            str(path_obj).lower().endswith(valid_extensions)
                            or str(path_obj).lower().endswith(manifest_exts)
                        )
                    ):
                        files_list = [str(path_obj)]
                    else:
                        st.error(_I("ERR_INVALID_DIR"))
            else:
                uploaded_files = st.file_uploader(
                    _I("UPLOAD_LABEL"),
                    type=None,
                    accept_multiple_files=True,
                    key="initial_file_uploader",
                )
                # Streamlit may briefly return an empty list while a rerun is
                # triggered by downstream processing. Keep the last completed
                # upload available so starting analysis cannot make the input
                # disappear from the active viewer.
                if uploaded_files:
                    files_list = self._persist_uploaded_files(uploaded_files)
                else:
                    files_list = st.session_state.get(
                        "_uploaded_input_paths", []
                    )

        # Reopen consolidated measurement exports by extracting their
        # de-identified DICOM members and restoring the matching JSON records.
        st.session_state.pop("_reopened_measurements", None)
        detected_reopened_input = False
        archive_candidates = [
            f for f in (files_list or [])
            if str(getattr(f, "name", f)).lower().endswith(".zip")
        ]
        if archive_candidates:
            self._cleanup_export_archives()
            reopened_files: list[str] = []
            reopened_measurements: dict[str, dict] = {}
            for archive_target in archive_candidates:
                try:
                    extracted, measurements_by_prefix = self._open_export_archive(
                        archive_target
                    )
                    reopened_files.extend(extracted)
                    reopened_measurements.update(measurements_by_prefix)
                except (OSError, ValueError, zipfile.BadZipFile) as exc:
                    logger.warning("Could not open export archive: %s", exc)
                    st.error(f"Could not open export archive: {exc}")
            if reopened_files:
                files_list = reopened_files
                st.session_state["_reopened_measurements"] = reopened_measurements
                detected_reopened_input = True
                st.info(
                    f"Reopened {len(reopened_files)} editable image(s) "
                    "from the export archive. The original source background, "
                    "display settings, and saved measurement overlays are "
                    "restored when available."
                )

        if not detected_reopened_input:
            for target in files_list or []:
                target_name = str(getattr(target, "name", target)).lower()
                if target_name.endswith(".png"):
                    try:
                        if self._read_measurement_composite_metadata(target):
                            detected_reopened_input = True
                            break
                    except (OSError, ValueError, TypeError):
                        continue
        input_workflow = (
            "Reopen exported / measured files"
            if detected_reopened_input
            else "Initial input"
        )
        previous_detected_workflow = st.session_state.get(
            "_detected_input_workflow"
        )
        if previous_detected_workflow != input_workflow:
            st.session_state.pop("_restored_display_target", None)
            st.session_state.auto_reader_enabled = False
            if input_workflow == "Initial input":
                self._cleanup_export_archives()
                st.session_state.pop("_reopened_measurements", None)
                st.session_state.pop("_measurement_store", None)
                st.session_state.pop("_measure_sig", None)
                st.session_state.pop("measurements", None)
            else:
                # Reopened exports must be populated from their embedded
                # records, not from measurements belonging to a prior study.
                st.session_state.pop("_measurement_store", None)
                st.session_state.pop("_measure_sig", None)
                st.session_state.pop("measurements", None)
        st.session_state["_detected_input_workflow"] = input_workflow
        st.session_state["input_workflow"] = input_workflow

        # --- Manifest routing: .tcia download flow vs offline parse/preview ---
        tcia_candidates = [
            f for f in (files_list or [])
            if str(getattr(f, 'name', f)).lower().endswith(('.tcia',))
        ]
        if tcia_candidates:
            cache_root = Path.home() / ".neuroproject_tcia"
            files_list = self._run_tcia_manifest_flow(tcia_candidates[0], cache_root)

        manifest_candidates = [
            f for f in (files_list or [])
            if str(getattr(f, 'name', f)).lower().endswith(('.tsv', '.csv', '.txt'))
        ]
        if manifest_candidates and not tcia_candidates:
            # --- direct download with immediate analysis like .tcia (no tabular view) ---
            import requests

            manifest_cache_root = Path.home() / ".neuroproject_manifest"
            manifest_cache_root.mkdir(parents=True, exist_ok=True)
            files_list = []

            for manifest_target in manifest_candidates:
                manifest_name = str(getattr(manifest_target, 'name', manifest_target))
                parsed = self._parse_manifest_file(
                    manifest_target,
                    ext=Path(manifest_name).suffix
                )
                if parsed.get("error"):
                    logger.warning("manifest parse error for %s: %s",
                                   parsed.get("file_name", "?"),
                                   parsed["error"])
                    st.error(f"Failed to parse manifest `{parsed.get('file_name', '?')}`: "
                             f"{parsed['error']}")
                    continue

                url_col = parsed.get("url_column")
                rows = parsed.get("rows") or []
                if not url_col:
                    logger.warning("manifest %s has no URL column",
                                   parsed.get("file_name", "?"))
                    st.error(
                        f"Manifest `{parsed.get('file_name', '?')}` has no download "
                        "URL column. Direct image download requires valid manifest URLs."
                    )
                    continue
                if not rows:
                    st.warning(f"Manifest `{parsed.get('file_name', '?')}` contains "
                               "no rows to analyze.")
                    continue

                manifest_files = []
                failed_urls = 0
                total = len(rows)
                progress = st.progress(
                    0.0,
                    text=f"Downloading images from `{parsed.get('file_name', '?')}` ...")

                for row_index, row in enumerate(rows):
                    url = str(row.get(url_col) or "").strip()
                    if not url:
                        continue

                    if url.startswith(("http://", "https://")):
                        dest = None
                        try:
                            if not self._is_allowed_manifest_url(url):
                                raise ValueError(
                                    "Remote manifest URLs must use the trusted "
                                    "TCIA HTTPS host."
                                )
                            name_part = url.split("?", 1)[0].rstrip("/")
                            candidate_name = Path(name_part).name or f"image_{row_index}"
                            if not candidate_name or "." not in candidate_name:
                                candidate_name = f"image_{row_index}.dcm"
                            dest = manifest_cache_root / Path(candidate_name).name
                            if not dest.exists():
                                with requests.get(
                                    url,
                                    headers=self._TCIA_HEADERS,
                                    timeout=(30, 300),
                                    stream=True,
                                ) as resp:
                                    resp.raise_for_status()
                                    content_length = int(
                                        resp.headers.get("Content-Length", "0") or 0
                                    )
                                    max_bytes = 512 * 1024**2
                                    if content_length > max_bytes:
                                        raise ValueError(
                                            "Remote image exceeds the safety limit."
                                        )
                                    downloaded = 0
                                    with open(str(dest), "wb") as out:
                                        for chunk in resp.iter_content(
                                            chunk_size=1 << 20
                                        ):
                                            if not chunk:
                                                continue
                                            downloaded += len(chunk)
                                            if downloaded > max_bytes:
                                                raise ValueError(
                                                    "Remote image exceeds the safety limit."
                                                )
                                            out.write(chunk)
                            if dest.exists() and dest.is_file() and dest.stat().st_size:
                                with open(str(dest), "rb") as fh:
                                    head = fh.read(256)
                                stripped = head.lstrip()[:5].lower()
                                if not head or stripped == b"<html" or stripped == b"<!doc":
                                    dest.unlink(missing_ok=True)
                                    failed_urls += 1
                                    continue
                            if self._is_image_file(str(dest)):
                                manifest_files.append(str(dest))
                            else:
                                failed_urls += 1
                        except Exception:
                            if dest is not None and dest.exists():
                                dest.unlink(missing_ok=True)
                            failed_urls += 1
                    elif Path(url).is_file():
                        if self._is_image_file(Path(url)):
                            manifest_files.append(str(Path(url)))
                        else:
                            failed_urls += 1
                    else:
                        failed_urls += 1

                    progress.progress(
                        (row_index + 1) / total,
                        text=f"Downloading images from `{parsed.get('file_name', '?')}` ..."
                    )

                progress.empty()
                if manifest_files:
                    st.toast(
                        f"Downloaded {len(manifest_files)} images from "
                        f"`{parsed.get('file_name', '?')}` (cached locally).",
                        icon="✅",
                    )
                elif failed_urls:
                    logger.warning("manifest %s: all %d URLs failed to download",
                                   parsed.get("file_name", "?"), failed_urls)
                    st.error(
                        f"Manifest `{parsed.get('file_name', '?')}`: all "
                        f"{failed_urls} URLs failed to download. Verify that the "
                        "manifest contains valid image URLs or access keys."
                    )
                files_list.extend(manifest_files)

        # Keep the completed study separate from the current widget result.
        # Sidebar widgets cause full Streamlit reruns and may transiently
        # produce an empty input value even though the user has not selected a
        # new study. The active snapshot is the authoritative viewer source
        # until a genuinely different non-empty input is supplied.
        if files_list:
            candidate_fingerprint = self._files_fingerprint(files_list)
            active_fingerprint = st.session_state.get(
                "_active_input_fingerprint"
            )
            active_files = st.session_state.get("_active_input_files", [])
            if (
                active_fingerprint != candidate_fingerprint
                or len(active_files) != len(files_list)
                or not all(Path(path).exists() for path in active_files)
            ):
                st.session_state["_active_input_files"] = list(files_list)
                st.session_state["_active_input_fingerprint"] = (
                    candidate_fingerprint
                )
            else:
                files_list = list(active_files)
        else:
            files_list = list(
                st.session_state.get("_active_input_files", [])
            )

        # --- 2. The assertion layer ---
        if not files_list:
            st.markdown(
                safe_diag_box(
                    "warning",
                    "⚠️ " + _i18n.DISCLAIMER_TITLE["en"],
                    _i18n.DISCLAIMER_TEXT["en"],
                    role="note",
                ),
                unsafe_allow_html=True,
            )
            st.info("🔄 System Ready. Waiting for data input to begin analysis.")
            st.stop()

        # Use physical slice position when DICOM provides orientation and
        # position tags; filename order is not reliable for a study. Cache
        # this header-heavy pass for the active input set: Streamlit reruns
        # frequently during navigation, but the input list usually does not
        # change.
        input_fingerprint = self._files_fingerprint(files_list)
        ordered_cache = st.session_state.setdefault(
            "_ordered_input_cache", OrderedDict()
        )
        if not isinstance(ordered_cache, OrderedDict):
            ordered_cache = OrderedDict(ordered_cache)
            st.session_state["_ordered_input_cache"] = ordered_cache
        cached_order = ordered_cache.get(input_fingerprint)
        if cached_order is None or len(cached_order) != len(files_list):
            files_list = order_dicom_files(files_list)
            ordered_cache[input_fingerprint] = files_list
        else:
            files_list = cached_order
            ordered_cache.move_to_end(input_fingerprint)
        while len(ordered_cache) > 2:
            ordered_cache.popitem(last=False)
        st.session_state["_active_files_fingerprint"] = self._files_fingerprint(
            files_list
        )

        # Navigation is rendered beside the image inside the fragment below, so
        # changing images does not rebuild the sidebar or the full application.
        num_files = len(files_list)
        if num_files == 0:
            logger.error("no valid data files found")
            st.error(_i18n.ERR_NO_VALID_FILES[lang])
            st.stop()

        detected_modality = self._detect_input_modality(files_list)
        feature_caps = self._feature_capabilities(detected_modality)
        active_input_index = min(
            max(int(st.session_state.get("viewer_index", 0)), 0),
            num_files - 1,
        )
        active_input = files_list[active_input_index]
        active_presentation = self._read_dicom_presentation_metadata(active_input)
        reopened_payload = next(
            (
                st.session_state.get("_reopened_measurements", {}).get(key)
                for key in self._reopened_measurement_keys(
                    str(getattr(active_input, "name", active_input))
                )
                if key in st.session_state.get("_reopened_measurements", {})
            ),
            None,
        )
        if active_presentation.get("measurement_composite"):
            payload = active_presentation.get("measurement_payload") or {}
        elif isinstance(reopened_payload, dict):
            payload = reopened_payload
        else:
            payload = {}
        if payload:
            restore_key = (
                f"{self._files_fingerprint(files_list)}:"
                f"{getattr(active_input, 'name', active_input)}"
            )
            if st.session_state.get("_restored_display_target") != restore_key:
                preset = str(payload.get("window_preset") or "custom")
                if preset not in {
                    "custom", "lung", "bone", "brain", "soft_tissue",
                    "vascular_cta", "venography", "neurovascular",
                    "temporal_bone", "spine_bone", "abdomen", "mediastinum",
                }:
                    preset = "custom"
                st.session_state.window_preset_selector = preset
                try:
                    st.session_state.ct_window_center = int(
                        round(float(payload.get("window_center", 40)))
                    )
                    st.session_state.ct_window_width = max(
                        1, int(round(float(payload.get("window_width", 400))))
                    )
                except (TypeError, ValueError):
                    st.session_state.ct_window_center = 40
                    st.session_state.ct_window_width = 400
                st.session_state._restored_display_target = restore_key
        st.markdown(
            '<div class="workspace-status" role="status">'
            '<span class="workspace-status__label">Workspace</span>'
            f'<span class="workspace-status__item"><b>{detected_modality}</b> input</span>'
            f'<span class="workspace-status__item">{num_files} image'
            f'{"s" if num_files != 1 else ""} available</span>'
            '<span class="workspace-status__item">Research mode</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        with control_panel.expander("Research compute", expanded=False):
            gpu_state = "CUDA available" if torch.cuda.is_available() else "CPU only"
            st.caption(f"GPU / accelerator: {gpu_state}")
            if torch.cuda.is_available():
                st.caption(f"Device count: {torch.cuda.device_count()} · current: {torch.cuda.get_device_name(0)}")
            onnx_provider = self.onnx_engine.active_provider
            onnx_state = (
                "CUDA"
                if self.onnx_engine.cuda_enabled
                else onnx_provider
            )
            st.caption(
                f"ONNX Runtime: {onnx_state} "
                f"(available: {', '.join(self.onnx_engine.available_providers()) or 'none'})"
            )

        # --- Floating sidebar: AI and advanced tools ---
        with control_panel.expander(_i18n.SECTION_AI_TOOLS[lang], expanded=False):
            if feature_caps["advanced_processing"]:
                enable_monai = st.checkbox(
                    _i18n.FEATURE_MONAI[lang], value=False
                )
                enable_sitk = st.checkbox(
                    _i18n.FEATURE_SITK[lang], value=False
                )
            else:
                enable_monai = False
                enable_sitk = False
            if feature_caps["ai_inference"]:
                compatible_domains = self._available_ai_domains(
                    detected_modality
                )
                if not compatible_domains:
                    st.caption(
                        "No registered ViT model is validated for this modality. "
                        "AI inference remains disabled."
                    )
                    ai_domain = "brain"
                else:
                    current_domain = st.session_state.get("ai_domain")
                    domain_index = (
                        compatible_domains.index(current_domain)
                        if current_domain in compatible_domains else 0
                    )
                    ai_domain = st.selectbox(
                        _i18n.AI_DOMAIN_LABEL[lang],
                        compatible_domains,
                        index=domain_index,
                    )
            else:
                ai_domain = "brain"
        st.session_state.enable_monai = enable_monai
        st.session_state.enable_sitk = enable_sitk
        st.session_state.ai_domain = ai_domain

        # --- Floating sidebar: display settings ---
        with control_panel.expander(_i18n.SECTION_SETTINGS[lang], expanded=False):
            view_mode = st.selectbox(
                "Viewer mode",
                ["Fit to panel", "1:1 pixels", "2x magnification", "4x magnification"],
                index=0,
                key="viewer_mode",
                help="Changes presentation only; source pixels and measurements remain unchanged.",
            )
            st.session_state.viewer_zoom = {
                "Fit to panel": 1.0,
                "1:1 pixels": 1.0,
                "2x magnification": 2.0,
                "4x magnification": 4.0,
            }[view_mode]
            st.session_state.viewer_view_mode = (
                "native" if view_mode == "1:1 pixels" else "fit"
            )
            ct_presets = {
                "lung": (-600, 1500),
                "bone": (400, 2000),
                "brain": (40, 80),
                "soft_tissue": (50, 400),
                "vascular_cta": (300, 700),
                "venography": (150, 500),
                "neurovascular": (100, 400),
                "temporal_bone": (700, 4000),
                "spine_bone": (350, 1800),
                "abdomen": (50, 400),
                "mediastinum": (40, 400),
            }
            window_preset = st.selectbox(
                _i18n.WINDOW_PRESET_LABEL[lang],
                (
                    ["custom", *ct_presets]
                    if feature_caps["ct_windowing"]
                    else ["automatic"]
                ),
                index=0,
                key="window_preset_selector",
            )
            default_center, default_width = (
                ct_presets.get(window_preset, (40, 400))
            )
            if (
                feature_caps["ct_windowing"]
                and st.session_state.get("_last_window_preset") != window_preset
            ):
                st.session_state.ct_window_center = default_center
                st.session_state.ct_window_width = default_width
                st.session_state._last_window_preset = window_preset
            if feature_caps["ct_windowing"]:
                w_center = st.slider(
                    "Window Center (HU)", -1024, 3071,
                    key="ct_window_center",
                )
                w_width = st.slider(
                    "Window Width (HU)", 1, 4095,
                    key="ct_window_width",
                )
                st.caption(
                    f"Effective display window: center {w_center} HU, "
                    f"width {w_width} HU."
                )
                st.caption(
                    "Windowing changes visualization only. It does not create "
                    "vessel, nerve, or tissue segmentation."
                )
                if window_preset in {
                    "vascular_cta", "venography", "neurovascular"
                }:
                    st.caption(
                        "Vessel visibility depends on contrast timing, "
                        "opacification, and reconstruction parameters."
                    )
                elif window_preset in {"temporal_bone", "spine_bone"}:
                    st.caption(
                        "Routine CT does not directly visualize peripheral nerves."
                    )
            else:
                w_center, w_width = 40, 400
                st.caption(
                    "Automatic native-intensity display is used for this "
                    "modality; CT window presets are hidden."
                )
        st.session_state.window_preset = window_preset
        st.session_state.w_center = w_center
        st.session_state.w_width = w_width

        # --- Floating sidebar: analysis suite ---
        with control_panel.expander(_i18n.SECTION_ANALYSIS[lang], expanded=True):
            if not feature_caps["ct_tissue"]:
                st.caption(
                    f"Detected modality: {detected_modality}. "
                    "Only compatible research features are shown."
                )
            if feature_caps["ct_tissue"]:
                enable_tissue = st.checkbox(
                    _i18n.FEATURE_TISSUE[lang], value=True
                )
                enable_tissue_map = st.checkbox(
                    _i18n.FEATURE_TMAP[lang], value=False
                )
            else:
                enable_tissue = False
                enable_tissue_map = False
            if feature_caps["edge_detection"]:
                enable_edges = st.selectbox(
                    _i18n.FEATURE_EDGES[lang],
                    ["Off", "Sobel", "Canny", "Gradient Mag"],
                    index=0,
                )
            else:
                enable_edges = "Off"
            if feature_caps["quality"]:
                enable_quality = st.checkbox(
                    _i18n.FEATURE_QUALITY[lang],
                    value=False,
                    help="Disabled by default to keep image navigation responsive.",
                )
            else:
                enable_quality = False
            if feature_caps["radiomics"]:
                enable_radiomics = st.checkbox(
                    _i18n.FEATURE_RADIOMICS[lang],
                    value=False,
                    help="Enable when needed; radiomics is computed on demand.",
                )
            else:
                enable_radiomics = False
            if feature_caps["ai_inference"]:
                enable_attention = st.checkbox(
                    _i18n.FEATURE_XAI[lang], value=False
                )
            else:
                enable_attention = False
            if feature_caps["volumetric"]:
                visualization_mode = st.selectbox(
                    _i18n.FEATURE_VIZ[lang],
                    ["Off", "MIP", "MPR", "3D Plotly"],
                    index=0,
                )
            else:
                visualization_mode = "Off"
        st.session_state.enable_tissue = (
            enable_tissue if feature_caps["ct_tissue"] else False
        )
        st.session_state.enable_edges = (
            enable_edges if feature_caps["edge_detection"] else "Off"
        )
        st.session_state.enable_quality = (
            enable_quality if feature_caps["quality"] else False
        )
        st.session_state.enable_radiomics = (
            enable_radiomics if feature_caps["radiomics"] else False
        )
        st.session_state.enable_attention = (
            enable_attention if feature_caps["ai_inference"] else False
        )
        st.session_state.enable_tissue_map = (
            enable_tissue_map if feature_caps["ct_tissue"] else False
        )
        st.session_state.visualization_mode = (
            visualization_mode if feature_caps["volumetric"] else "Off"
        )

        self._render_scientific_overview()

        # --- 4. Immediate processing and navigation (zero-latency slice navigation) ---
        # Slice browsing and image clicks happen within a single fragment:
        # Changing the slice index redraws the viewer alone without restarting the page.
        if st.session_state.get("auto_reader_enabled", False):
            _run_auto_reader_tick(num_files)
        self._render_slice_viewer(files_list, num_files)


    @st.fragment
    def _render_slice_viewer(self, files_list: list, num_files: int) -> None:
        """
        Fragment-isolated image viewer. Navigation stays beside the image and
        only this fragment reruns when the selected image changes.
        """
        files_signature = tuple(
            getattr(item, "name", str(item)) for item in files_list
        )
        if st.session_state.get("viewer_files_signature") != files_signature:
            st.session_state.viewer_files_signature = files_signature
            st.session_state.viewer_index = 0
            reopen_workflow = st.session_state.get("input_workflow") == (
                "Reopen exported / measured files"
            )
            st.session_state.auto_reader_enabled = reopen_workflow and num_files > 1
            st.session_state.auto_reader_loop = False
            st.session_state.auto_reader_interval = max(
                1, int(st.session_state.get("auto_reader_interval", 3))
            )
            st.session_state.auto_reader_last_tick = time.monotonic()
            st.session_state.pop("viewer_index_slider", None)
            st.session_state.pop("sr_viewer_index_slider", None)

        idx = min(
            max(int(st.session_state.get("viewer_index", 0)), 0),
            num_files - 1,
        )
        target = files_list[idx]

        lang = st.session_state.get("app_lang", "en")

        # Pin the file identity to keep the session stable (session stability)
        file_id = getattr(target, 'name', str(target))

        # Clear coordinates when the slice changes to preserve source-data integrity.
        if st.session_state.get('current_file') != file_id:
            st.session_state.coords = None
            st.session_state.current_file = file_id
            st.session_state.viewer_slice_index = 0
            st.session_state.pop("viewer_slice_slider", None)

        # Measurements and comparisons belong to one displayed image only.
        # Clear them when either the uploaded set or the active file/slice
        # changes so a stale ruler is never plotted on unrelated data.
        files_fpr = st.session_state.get("_active_files_fingerprint")
        if not files_fpr:
            files_fpr = self._files_fingerprint(files_list)
        if st.session_state.get("_files_fpr") != files_fpr:
            st.session_state["_files_fpr"] = files_fpr
            st.session_state["_viewer_source_cache"] = {}
            st.session_state["_viewer_display_cache"] = {}
            st.session_state["_pixel_viewer_payload_cache"] = {}
            st.session_state["_viewer_derived_cache"] = {}
            st.session_state["_quality_cache"] = {}
            st.session_state["_radiomics_cache"] = {}
            st.session_state["compare_index"] = None
            st.session_state.pop("_series_groups", None)
            st.session_state.pop("_series_groups_sig", None)
            st.session_state.pop("series_select", None)
            st.session_state.pop("sr_series_select", None)
            st.session_state.pop("compare_select", None)
        image_signature = f"{files_fpr}:{file_id}:{idx}"
        if st.session_state.get("_measure_sig") != image_signature:
            st.session_state["_measure_sig"] = image_signature
            st.session_state.setdefault("_measurement_store", {})
            st.session_state.pop("compare_select", None)

        # --- 4. Processing (data acquisition & transformation) ---
        # Keep source acquisition in a session cache. Browsing, measurement
        # edits, and display controls rerun the fragment but do not need to
        # decode the same DICOM or volume repeatedly.
        source_cache = st.session_state.setdefault(
            "_viewer_source_cache", OrderedDict()
        )
        if not isinstance(source_cache, OrderedDict):
            source_cache = OrderedDict(source_cache)
            st.session_state["_viewer_source_cache"] = source_cache
        source_cache_key = (files_fpr, file_id, idx)
        cached_source = source_cache.get(source_cache_key)
        if cached_source is None:
            dicom_metadata = self._read_dicom_presentation_metadata(target)
            loaded_source = self._load_image(target)
            source_cache[source_cache_key] = (
                dicom_metadata,
                loaded_source,
            )
        else:
            dicom_metadata, loaded_source = cached_source
            source_cache.move_to_end(source_cache_key)
        # Keep a wider hot set so stepping through nearby images does not
        # repeatedly decode the same source when the user changes direction.
        while len(source_cache) > 8:
            source_cache.popitem(last=False)

        # Invoke the protocol that verifies the physiological range
        is_measurement_composite = bool(
            dicom_metadata.get("measurement_composite")
        )

        # DICOM SR objects carry no pixel data; route them to the structured
        # report viewer instead of the image acquisition pipeline.
        if ClinicalApp._is_dicom_sr_metadata(dicom_metadata):
            self._render_dicom_sr_viewer(
                target, dicom_metadata, lang,
                file_id=file_id, idx=idx, total=num_files,
                files_list=files_list, files_fpr=files_fpr,
            )
            return

        hu_data, _uid, modality = loaded_source

        if isinstance(hu_data, str):
            logger.error("_load_image returned error string: %s", hu_data[:300])
            st.error(_i18n.ERR_ACQUISITION[lang])
            return

        if hu_data is None or hu_data.size == 0:
            logger.error("_load_image returned empty voxel data")
            st.error(_i18n.ERR_EMPTY_VOXEL_DATA[lang])
            return
        original_image_data = np.asarray(hu_data)
        audit_event(
            logger,
            "image_viewed",
            image_ref=pseudonymous_identifier(file_id),
            modality=str(modality or "unknown"),
        )

        # Ensure a 2D dimension for interactive analysis (fold volumetric series to the mid-slice).
        # The slice axis is the smallest dimension under NIfTI (z) and SITK (z on axis 0)
        # conventions, so we choose argmin rather than argmax, guarding every empty axis.
        if hu_data.ndim < 2:
            logger.error("image degenerate (%dD)", hu_data.ndim)
            st.error(_i18n.ERR_ACQUISITION[lang])
            return
        raw_is_color = (
            not str(modality or "").upper().startswith("VOLUME")
            and hu_data.ndim == 3
            and hu_data.shape[-1] in (3, 4)
        )
        volume_data = hu_data
        slice_axis = None
        slice_count = 1
        slice_index = 0
        if hu_data.ndim > 3 and not raw_is_color:
            # Reduce non-spatial dimensions conservatively before exposing the
            # spatial sequence. The smallest remaining axis is the safest
            # deterministic fallback for time/echo/sequence dimensions.
            while hu_data.ndim > 3:
                shape = hu_data.shape
                reduction_axis = int(np.argmin(shape))
                if shape[reduction_axis] < 1:
                    logger.error("sequence axis is empty (zero-length)")
                    st.error(_i18n.ERR_EMPTY_VOXEL_DATA[lang])
                    return
                hu_data = np.take(hu_data, shape[reduction_axis] // 2, axis=reduction_axis)
            volume_data = hu_data
        if hu_data.ndim == 3 and not raw_is_color:
            slice_axis = int(np.argmin(hu_data.shape))
            slice_count = int(hu_data.shape[slice_axis])
            slice_signature = (file_id, tuple(int(v) for v in hu_data.shape), slice_axis)
            if st.session_state.get("viewer_slice_signature") != slice_signature:
                st.session_state.viewer_slice_signature = slice_signature
                st.session_state.viewer_slice_index = 0
                st.session_state.pop("viewer_slice_slider", None)
            slice_index = min(
                max(int(st.session_state.get("viewer_slice_index", 0)), 0),
                slice_count - 1,
            )
            hu_data = np.take(hu_data, slice_index, axis=slice_axis)
        elif not raw_is_color:
            st.session_state.pop("viewer_slice_signature", None)
            st.session_state.viewer_slice_index = 0
        image_signature = f"{files_fpr}:{file_id}:{idx}:{slice_index}"
        st.session_state["_measure_sig"] = image_signature
        measurement_store = st.session_state.setdefault("_measurement_store", {})
        reopened = st.session_state.get("_reopened_measurements", {})
        reopened_record = next(
            (
                reopened[key]
                for key in self._reopened_measurement_keys(str(file_id))
                if key in reopened
            ),
            None,
        )
        if isinstance(reopened_record, dict):
            reopened_measurements = reopened_record.get("measurements") or []
        else:
            reopened_measurements = reopened_record or []
        if image_signature not in measurement_store and reopened_measurements:
            measurement_store[image_signature] = {
                "file_id": file_id,
                "file_index": idx,
                "slice_index": slice_index,
                "measurements": list(reopened_measurements),
            }
        if (
            image_signature not in measurement_store
            and is_measurement_composite
            and dicom_metadata.get("measurements")
        ):
            measurement_store[image_signature] = {
                "file_id": file_id,
                "file_index": idx,
                "slice_index": slice_index,
                "measurements": list(dicom_metadata["measurements"]),
            }
        st.session_state["measurements"] = list(
            self._stored_measurements(measurement_store.get(image_signature, []))
        )
        if is_measurement_composite:
            st.info(
                "Measurement composite opened: native dimensions and saved "
                "measurement method restored. Existing measurements can be "
                "deleted or supplemented with new measurements."
            )
        if hu_data.ndim != 2 and not raw_is_color:
            st.warning(
                f"Multi-frame / volumetric data detected ({hu_data.ndim}D). "
                f"Displaying the middle slice for interactive analysis."
            )

        # Informational rendering: apply the grayscale vision protocol (Pure-Gray).
        # HU-windowed greyscaling is intended for CT only; MR/US/PET signal
        # intensity is not in Hounsfield units, so percentiles [1,99] are printed automatically.
        mod_key = str(modality or "").upper()
        analysis_modality, is_color = self._parse_image_type(mod_key, hu_data)
        is_ct = analysis_modality == "CT"
        non_ct = not is_ct
        self._render_anatomical_segmentation(
            volume_data,
            file_id,
            is_ct=is_ct,
            raw_is_color=raw_is_color,
        )
        actual_caps = self._feature_capabilities(analysis_modality)
        actual_caps["ai_inference"] = (
            actual_caps["ai_inference"]
            and bool(self._available_ai_domains(analysis_modality))
        )
        actual_caps["edge_detection"] = (
            actual_caps["edge_detection"] and not is_color
        )
        for feature_name, capability in actual_caps.items():
            if not capability:
                if feature_name == "ct_tissue":
                    st.session_state.enable_tissue = False
                    st.session_state.enable_tissue_map = False
                elif feature_name == "edge_detection":
                    st.session_state.enable_edges = "Off"
                elif feature_name == "quality":
                    st.session_state.enable_quality = False
                elif feature_name == "radiomics":
                    st.session_state.enable_radiomics = False
                elif feature_name == "ai_inference":
                    st.session_state.enable_attention = False
                elif feature_name == "volumetric":
                    st.session_state.visualization_mode = "Off"
        st.markdown(
            '<div class="image-meta-strip">'
            f'<span class="image-meta-strip__label">Image type</span>'
            f'<span>{analysis_modality}</span>'
            f'<span class="image-meta-strip__divider">·</span>'
            f'<span class="image-meta-strip__label">Units</span>'
            f'<span>{"HU" if is_ct else "native signal"}</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if dicom_metadata:
            tag_window = dicom_metadata["window_center"]
            tag_width = dicom_metadata["window_width"]
            window_text = "not supplied"
            if tag_window is not None and tag_width is not None:
                if isinstance(tag_window, list):
                    tag_window = tag_window[0]
                if isinstance(tag_width, list):
                    tag_width = tag_width[0]
                window_text = f"{tag_window:g} / {tag_width:g}"
            spacing = dicom_metadata.get("pixel_spacing_mm")
            spacing_text = (
                f"{spacing[0]:g} x {spacing[1]:g} mm"
                if spacing and len(spacing) >= 2
                else "not supplied"
            )
            st.markdown(
                '<div class="dicom-meta" aria-label="DICOM metadata">'
                '<span>'
                '<b>DICOM</b> · '
                f"{dicom_metadata.get('photometric_interpretation') or 'unspecified'} · "
                f"matrix {dicom_metadata.get('rows') or '?'} x "
                f"{dicom_metadata.get('columns') or '?'} · "
                f"window {window_text}"
                '</span>'
                '<span>'
                f"<b>SOP Class</b> {dicom_metadata.get('sop_class_name') or 'unknown'} · "
                f"transfer {dicom_metadata.get('transfer_syntax_name') or 'unknown'} · "
                f"spacing {spacing_text}"
                '</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            # De-identification is an export operation and is intentionally
            # deferred so browsing never serializes the active DICOM.
            anon_bytes = None
        native_stats = None
        if actual_caps["edge_detection"] or analysis_modality == "VOLUME":
            native_stats = {
                "Minimum": float(np.min(hu_data)),
                "Maximum": float(np.max(hu_data)),
                "Mean": float(np.mean(hu_data)),
                "Standard deviation": float(np.std(hu_data)),
            }
        window_preset = st.session_state.get(
            "window_preset",
            self._default_window_preset(analysis_modality),
        )
        if window_preset == "automatic":
            window_preset = self._default_window_preset(analysis_modality)
        w_center = st.session_state.get('w_center', 40)
        w_width = st.session_state.get('w_width', 400)
        mono1 = self._uses_monochrome1_display(analysis_modality, mod_key)
        display_key = (
            image_signature,
            str(window_preset),
            float(w_center),
            float(w_width),
            bool(is_measurement_composite),
            bool(is_color),
            bool(mono1),
        )
        display_cache = st.session_state.setdefault(
            "_viewer_display_cache", OrderedDict()
        )
        if not isinstance(display_cache, OrderedDict):
            display_cache = OrderedDict(display_cache)
            st.session_state["_viewer_display_cache"] = display_cache
        disp_img = display_cache.get(display_key)
        if disp_img is None:
            if is_measurement_composite:
                # Composite PNG pixels are already in the original measurement
                # presentation. Do not percentile-scale or window them again.
                disp_img = np.asarray(hu_data, dtype=np.uint8)
            elif is_color:
                disp_img = self._prepare_color_display(hu_data)
            elif non_ct:
                pmin, pmax = float(np.percentile(hu_data, 1)), float(
                    np.percentile(hu_data, 99)
                )
                disp_img = np.clip(
                    (hu_data - pmin) / max(pmax - pmin, 1e-9) * 255,
                    0,
                    255,
                ).astype(np.uint8)
            else:
                disp_img = self._apply_windowing(
                    hu_data, center=w_center, width=w_width
                )
            # Keep physical values untouched and apply modality-specific
            # presentation only to the rendered 8-bit image.
            if mono1:
                disp_img = 255 - disp_img
            display_cache[display_key] = disp_img
        else:
            display_cache.move_to_end(display_key)
        while len(display_cache) > 24:
            display_cache.popitem(last=False)

        # --- Edge detection ---
        # Edges are computed from the ORIGINAL source (display-independent
        # rendition), so changing the window/zoom never changes the detected
        # structure; the windowed array is used only for the visual overlay.
        edge_method = st.session_state.get('enable_edges', 'Off')
        edge_norm = None
        if edge_method != 'Off' and actual_caps["edge_detection"]:
            edge_map = None
            try:
                edge_source = ClinicalApp._model_ready_image_from_source(hu_data)
            except (ValueError, TypeError):
                edge_source = None
            if edge_source is not None:
                if edge_method == 'Sobel':
                    edge_map = EdgeDetector.sobel(edge_source)
                elif edge_method == 'Canny':
                    edge_map = EdgeDetector.canny(edge_source, sigma=1.0, low_threshold=0.05, high_threshold=0.15)
                elif edge_method == 'Gradient Mag':
                    edge_map = EdgeDetector.gradient_magnitude(edge_source)
                if edge_map is not None:
                    edge_norm = np.clip(edge_map / max(edge_map.max(), 1e-9) * 255, 0, 255).astype(np.uint8)

        # --- Bone/Muscle/Fat Map ---
        tissue_map_viz = None
        tissue_map_percentages = None
        if (
            st.session_state.get('enable_tissue_map')
            and actual_caps["ct_tissue"]
        ):
            tissue_map = np.zeros_like(hu_data, dtype=np.uint8)
            tissue_map[(hu_data >= -200) & (hu_data < -20)] = 1    # Fat
            tissue_map[(hu_data >= 30) & (hu_data < 80)] = 2       # Muscle
            tissue_map[hu_data >= 200] = 3                          # Bone
            tissue_map_viz = np.zeros_like(hu_data, dtype=np.uint8)
            tissue_map_viz[tissue_map == 1] = 64    # Fat: dark gray
            tissue_map_viz[tissue_map == 2] = 160   # Muscle: medium gray
            tissue_map_viz[tissue_map == 3] = 230   # Bone: light gray
            if tissue_map_viz.max() > 0:
                p_fat = float(np.sum(tissue_map == 1)) / max(hu_data.size, 1) * 100
                p_muscle = float(np.sum(tissue_map == 2)) / max(hu_data.size, 1) * 100
                p_bone = float(np.sum(tissue_map == 3)) / max(hu_data.size, 1) * 100
                tissue_map_percentages = (p_fat, p_muscle, p_bone)

        # --- Target ROI & Structural Connectome (L6) ---
        # ROI crop semantics match render_deep_analysis; computed here so the
        # visualizations can live in the Series browser section below.
        roi_disp_viz = None
        l6_map_viz = None
        if st.session_state.get("coords") and not is_color:
            _coords = st.session_state.coords
            if isinstance(_coords, dict) and "x" in _coords and "y" in _coords:
                _h_dim, _w_dim = hu_data.shape
                _scale = st.session_state.get("coord_scale", 1.0)
                _cx = round(_coords["x"] * _scale)
                _cy = round(_coords["y"] * _scale)
                _radius = 64
                _y1, _y2 = np.clip([_cy - _radius, _cy + _radius], 0, _h_dim).astype(int)
                _x1, _x2 = np.clip([_cx - _radius, _cx + _radius], 0, _w_dim).astype(int)
                _roi_hu_viz = hu_data[_y1:_y2, _x1:_x2]
                if _roi_hu_viz.size > 0:
                    roi_disp_viz = disp_img[_y1:_y2, _x1:_x2]
                    _l6_viz = self.struct_engine.execute(_roi_hu_viz)
                    if isinstance(_l6_viz, np.ndarray):
                        l6_map_viz = _l6_viz

        # --- Image quality ---
        quality_report = None
        if st.session_state.get('enable_quality') and actual_caps["quality"]:
            quality_cache = st.session_state.setdefault(
                "_quality_cache", OrderedDict()
            )
            if not isinstance(quality_cache, OrderedDict):
                quality_cache = OrderedDict(quality_cache)
                st.session_state["_quality_cache"] = quality_cache
            quality_key = (image_signature, is_ct)
            quality_report = quality_cache.get(quality_key)
            if quality_report is None:
                noise = ImageQualityMetrics.noise_estimate(hu_data)
                unit_label = "HU" if is_ct else "native intensity"
                uniformity = ImageQualityMetrics.uniformity(hu_data)
                # SNR using a quarter of the image as signal and a corner as noise
                h, w = hu_data.shape
                center_roi = hu_data[h//4:3*h//4, w//4:3*w//4]
                corner = hu_data[:h//8, :w//8]
                snr_val = ImageQualityMetrics.snr(center_roi, corner)
                quality_report = {
                    "Noise (H)": f"{noise['noise_horizontal']:.2f} {unit_label}",
                    "Noise (V)": f"{noise['noise_vertical']:.2f} {unit_label}",
                    "Uniformity CV%": f"{uniformity:.2f}%",
                    "SNR": f"{snr_val:.2f}",
                }
                quality_cache[quality_key] = quality_report
            else:
                quality_cache.move_to_end(quality_key)
            while len(quality_cache) > 32:
                quality_cache.popitem(last=False)

        # --- Radiomics ---
        radiomics_report = None
        radiomics_export_data = {}
        if (
            st.session_state.get('enable_radiomics')
            and actual_caps["radiomics"]
        ):
            radiomics_cache = st.session_state.setdefault(
                "_radiomics_cache", OrderedDict()
            )
            if not isinstance(radiomics_cache, OrderedDict):
                radiomics_cache = OrderedDict(radiomics_cache)
                st.session_state["_radiomics_cache"] = radiomics_cache
            rad_report = radiomics_cache.get(image_signature)
            if rad_report is None:
                rad_report = RadiomicsExtractor.full_report(hu_data)
                radiomics_cache[image_signature] = rad_report
            else:
                radiomics_cache.move_to_end(image_signature)
            while len(radiomics_cache) > 16:
                radiomics_cache.popitem(last=False)
            radiomics_export_data = rad_report
            if "histogram" in rad_report:
                hf = rad_report["histogram"]
                radiomics_report = {
                    "Skewness": f"{hf.get('skewness', 0):.3f}",
                    "Kurtosis": f"{hf.get('kurtosis', 0):.3f}",
                    "Entropy": f"{hf.get('entropy', 0):.3f}",
                    "P10/P90": f"{hf.get('p10', 0):.0f}/{hf.get('p90', 0):.0f}",
                }

        # --- 3D Visualization ---
        visualization_mode = st.session_state.get('visualization_mode', 'Off')
        volume_preview = None
        if (
            visualization_mode != 'Off'
            and actual_caps["volumetric"]
            and hu_data.ndim >= 2
        ):
            if visualization_mode == 'MIP':
                mip_img = VolumeVisualizer.mip(volume_data, axis=0)
                volume_preview = (
                    self._apply_windowing(
                        mip_img,
                        preset=window_preset,
                    )
                    if not non_ct else
                    np.clip(
                        (mip_img - mip_img.min())
                        / max(mip_img.max() - mip_img.min(), 1e-9)
                        * 255,
                        0,
                        255,
                    ).astype(np.uint8)
                )
                if 'MONOCHROME1' in mod_key:
                    volume_preview = 255 - volume_preview
            elif visualization_mode == 'MPR':
                mpr_img = VolumeVisualizer.mpr(volume_data, axis=0)
                volume_preview = (
                    self._apply_windowing(
                        mpr_img,
                        preset=window_preset,
                    )
                    if not non_ct else
                    np.clip(
                        (mpr_img - mpr_img.min())
                        / max(mpr_img.max() - mpr_img.min(), 1e-9)
                        * 255,
                        0,
                        255,
                    ).astype(np.uint8)
                )
                if 'MONOCHROME1' in mod_key:
                    volume_preview = 255 - volume_preview
            elif visualization_mode == '3D Plotly':
                volume_preview = VolumeVisualizer.render_3d_plotly(volume_data)

        # Whole-image CT quantitative metrics for the Analysis results section.
        # Computed from the full selected image (same basis as native_stats),
        # independently of the ROI-based deep analysis.
        derived_cache = st.session_state.setdefault(
            "_viewer_derived_cache", OrderedDict()
        )
        if not isinstance(derived_cache, OrderedDict):
            derived_cache = OrderedDict(derived_cache)
            st.session_state["_viewer_derived_cache"] = derived_cache
        derived = derived_cache.get(image_signature)
        if derived is None:
            ct_metrics_report = None
            ct_tissue_pct = None
            if is_ct and not is_color:
                try:
                    ct_metrics_report = _CTCalculator().calculate(hu_data)
                except (ValueError, TypeError, RuntimeError):
                    ct_metrics_report = None
                try:
                    ct_tissue_pct = TissueClassifier.classify(hu_data)
                except (TypeError, RuntimeError):
                    ct_tissue_pct = None
            derived = (ct_metrics_report, ct_tissue_pct)
            derived_cache[image_signature] = derived
        else:
            derived_cache.move_to_end(image_signature)
        while len(derived_cache) > 16:
            derived_cache.popitem(last=False)
        ct_metrics_report, ct_tissue_pct = derived

        # Split the display matrix (visual matrix)
        st.markdown('<div id="main-content" tabindex="-1"></div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="viewer-context" role="status">'
            f'<span class="viewer-context__label">Selected image</span>'
            f'<span>Image {idx + 1} of {num_files}</span>'
            f'<span>{analysis_modality} · {"HU" if is_ct else "native intensity"}</span>'
            '<span class="viewer-context__hint">Click the image to inspect an ROI</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([4.2, 1.1], gap="medium", vertical_alignment="top")
        with col1:
            with st.container(border=True):
                st.markdown(
                    '<div class="viewer-title">Primary image viewer</div>',
                    unsafe_allow_html=True,
                )
                img_pil = Image.fromarray(disp_img).convert("L")
                if not is_color:
                    measure_mode = str(
                        st.session_state.get("viewer_measure_mode", "Off")
                    )
                    hover_result = self._render_pixel_hover_viewer(
                        disp_img,
                        hu_data,
                        "HU" if is_ct else "Native intensity",
                        key="pixel_viewer_main",
                        zoom=float(st.session_state.get("viewer_zoom", 1.0)),
                        view_mode=str(st.session_state.get("viewer_view_mode", "fit")),
                        measure_lines=st.session_state.get("measurements", []),
                        measure_mode=(
                            "line"
                            if measure_mode == "Distance (mm)"
                            else "angle" if measure_mode == "Angle (deg)" else "off"
                        ),
                        pixel_spacing_mm=dicom_metadata.get("pixel_spacing_mm"),
                        image_sig=(
                            f"{image_signature}:{slice_index}:"
                            f"{window_preset}:{w_center}:{w_width}:"
                            f"{int(is_measurement_composite)}:"
                            f"{int(self._uses_monochrome1_display(analysis_modality, mod_key))}"
                        ),
                    )
                    spacing = dicom_metadata.get("pixel_spacing_mm")
                    measure_line = getattr(hover_result, "measure_line", None)
                    if measure_line and measure_mode != "Off":
                        _next_label = str(
                            st.session_state.get("viewer_measure_label", "") or ""
                        ).strip()
                        ClinicalApp._add_measurement(
                            "distance",
                            measure_line,
                            spacing,
                            source_values=hu_data,
                            label=_next_label,
                        )
                        _safe_fragment_rerun()
                    measure_angle = getattr(hover_result, "measure_angle", None)
                    if measure_angle and measure_mode != "Off":
                        _next_label = str(
                            st.session_state.get("viewer_measure_label", "") or ""
                        ).strip()
                        ClinicalApp._add_measurement(
                            "angle",
                            measure_angle,
                            spacing,
                            source_values=hu_data,
                            label=_next_label,
                        )
                        _safe_fragment_rerun()
                    coords = getattr(hover_result, "click", None)
                    if coords:
                        st.session_state.coord_scale = 1.0
                        st.session_state.coords = coords
                        # The component reports source-pixel indices mapped back
                        # from whatever on-screen scale is active, so a click does
                        # not need to change the zoom. Forcing a 2x view here
                        # would silently override the zoom the user selected in
                        # Settings and re-render at a different scale, which
                        # looks like an unexpected data/quality change even
                        # though measurements are taken from the original array.
                        # Rerun only so the ROI panel picks up the new pixel.
                        _safe_fragment_rerun()
                    open_coords = getattr(hover_result, "open", None)
                    if open_coords:
                        st.session_state.coord_scale = 1.0
                        st.session_state.coords = open_coords
                        _safe_fragment_rerun()
                else:
                    coords = streamlit_image_coordinates(
                        img_pil,
                        width=min(
                            max(
                                DISPLAY_W,
                                int(DISPLAY_W * st.session_state.get(
                                    "viewer_zoom", 1.0
                                )),
                            ),
                            2800,
                        ),
                        key="coord_viewer_main",
                    )
                    if coords:
                        st.session_state.coord_scale = img_pil.width / DISPLAY_W
                        st.session_state.coords = coords
        with col2:
            with st.container(border=True):
                st.subheader("Navigation")
                st.caption(f"Image {idx + 1} of {num_files}")
                if slice_count > 1:
                    st.caption(
                        f"Sequence position: slice {slice_index + 1} of {slice_count}"
                    )

                    def _select_viewer_slice() -> None:
                        st.session_state.viewer_slice_index = int(
                            st.session_state.viewer_slice_slider
                        ) - 1

                    if "viewer_slice_slider" not in st.session_state:
                        st.session_state.viewer_slice_slider = slice_index + 1
                    st.slider(
                        "Sequence position",
                        min_value=1,
                        max_value=slice_count,
                        step=1,
                        format="Slice %d",
                        key="viewer_slice_slider",
                        on_change=_select_viewer_slice,
                    )
                if st.button(
                    "Previous",
                    key="viewer_previous",
                    disabled=idx == 0,
                    width="stretch",
                ):
                    st.session_state.viewer_index = idx - 1
                    st.session_state.viewer_index_slider = idx
                    st.session_state.coords = None
                    _safe_fragment_rerun()
                if st.button(
                    "Next",
                    key="viewer_next",
                    disabled=idx >= num_files - 1,
                    width="stretch",
                ):
                    st.session_state.viewer_index = idx + 1
                    st.session_state.viewer_index_slider = idx + 2
                    st.session_state.coords = None
                    _safe_fragment_rerun()
                if num_files > 1:
                    def _select_viewer_image() -> None:
                        selected_value = st.session_state.get(
                            "viewer_index_slider",
                            st.session_state.get("viewer_index", 0) + 1,
                        )
                        try:
                            selected_index = int(selected_value) - 1
                        except (TypeError, ValueError):
                            selected_index = int(st.session_state.get("viewer_index", 0))
                        st.session_state.viewer_index = min(
                            max(selected_index, 0),
                            num_files - 1,
                        )
                        st.session_state.coords = None

                    if "viewer_index_slider" not in st.session_state:
                        st.session_state.viewer_index_slider = idx + 1
                    st.slider(
                        "Image index",
                        min_value=1,
                        max_value=num_files,
                        step=1,
                        format="Image %d",
                        key="viewer_index_slider",
                        on_change=_select_viewer_image,
                    )

            if not is_color:
                with st.container(border=True):
                    st.subheader("Measurements")
                    st.selectbox(
                        "Mode",
                        ["Off", "Distance (mm)", "Angle (deg)"],
                        key="viewer_measure_mode",
                        help=(
                            "Distance: click two points on the image. Angle: "
                            "click three points (vertex first). Every measurement "
                            "stays on the image and in the list underneath, so "
                            "several distances and angles can be drawn at once."
                        ),
                    )
                    effective_spacing, effective_source = (
                        self._effective_pixel_spacing_mm(spacing)
                    )
                    if effective_spacing and len(effective_spacing) >= 2:
                        st.caption(
                            f"Calibration: {float(effective_spacing[0]):.4g} "
                            f"mm/row × {float(effective_spacing[1]):.4g} "
                            f"mm/column ({effective_source})"
                        )
                    else:
                        st.warning(
                            "No DICOM PixelSpacing is available. Distances will "
                            "remain in pixels until calibration is supplied."
                        )
                    unit_col, precision_col = st.columns(2)
                    with unit_col:
                        if measure_mode == "Angle (deg)":
                            st.caption("Unit")
                            st.markdown("**degrees (deg)**")
                            st.session_state["viewer_measure_unit"] = "deg"
                        else:
                            st.selectbox(
                                "Unit",
                                ["mm", "cm", "px"],
                                key="viewer_measure_unit",
                                help=(
                                    "Display unit for the value drawn on the image "
                                    "and listed below. mm/cm use the effective "
                                    "calibration (DICOM or manual); px uses the "
                                    "raw pixel length."
                                ),
                            )
                    with precision_col:
                        st.selectbox(
                            "Decimals",
                            ["0", "1", "2", "3"],
                            index=2,
                            key="viewer_measure_precision",
                            help="Number of decimal places for measurement values.",
                        )
                    st.text_input(
                        "Label for next measurement",
                        key="viewer_measure_label",
                        value="",
                        placeholder="e.g. AFP diameter, pituitary width",
                    )
                    with st.expander("Calibration accuracy"):
                        st.caption(
                            "Auto calibration reads the DICOM PixelSpacing "
                            "(NEMA PS3.3, C.7.6.2.1.1) and applies it per image "
                            "axis, so angles and lengths are evaluated in physical "
                            "mm space."
                        )
                        st.toggle(
                            "Manual calibration (mm/pixel)",
                            key="viewer_measure_manual",
                            value=False,
                            help=(
                                "Override DICOM calibration with your own factor "
                                "for this session. It is applied to every new "
                                "measurement."
                            ),
                        )
                        if st.session_state.get("viewer_measure_manual", False):
                            default_factor = 1.0
                            if spacing and len(spacing) >= 2:
                                try:
                                    default_factor = float(spacing[0])
                                except (TypeError, ValueError):
                                    default_factor = 1.0
                            st.number_input(
                                "mm per pixel",
                                value=st.session_state.get(
                                    "viewer_measure_factor", default_factor
                                ),
                                min_value=1e-4,
                                step=0.01,
                                format="%.4f",
                                key="viewer_measure_factor",
                            )
                            st.caption(
                                "Validate the factor against a certified phantom "
                                "before any quantitative interpretation "
                                "(AAPM practice guidance)."
                            )
                    measurements = st.session_state.get("measurements", [])
                    if measurements:
                        for i, item in enumerate(measurements):
                            row = st.columns([5.2, 1.0])
                            kind_word = (
                                "Dist" if item.get("kind") == "distance" else "Angle"
                            )
                            name = item.get("label") or f"{kind_word} #{i + 1}"
                            value_text = ClinicalApp._measurement_display(item)
                            if item.get("calib_source") == "manual":
                                calib_note = " [manual calib]"
                            elif item.get("mm_per_px") is None:
                                calib_note = " [no spacing]"
                            else:
                                item_spacing = item.get("pixel_spacing_mm")
                                if item_spacing and len(item_spacing) >= 2:
                                    calib_note = (
                                        f" [{float(item_spacing[0]):.4g}×"
                                        f"{float(item_spacing[1]):.4g} mm/px]"
                                    )
                                else:
                                    calib_note = ""
                            with row[1]:
                                if st.button(
                                    "Delete", key=f"viewer_measure_del_{i}"
                                ):
                                    current = st.session_state.get("measurements", [])
                                    if i < len(current):
                                        del current[i]
                                        st.session_state["measurements"] = current
                                        active_key = st.session_state.get("_measure_sig")
                                        if active_key:
                                            previous = st.session_state.setdefault(
                                                "_measurement_store", {}
                                            ).get(active_key, {})
                                            if not isinstance(previous, dict):
                                                previous = {}
                                            previous.update({
                                                "file_id": st.session_state.get(
                                                    "current_file", active_key
                                                ),
                                                "file_index": int(
                                                    st.session_state.get(
                                                        "viewer_index", 0
                                                    )
                                                ),
                                                "slice_index": int(
                                                    st.session_state.get(
                                                        "viewer_slice_index", 0
                                                    )
                                                ),
                                                "measurements": list(current),
                                            })
                                            st.session_state["_measurement_store"][
                                                active_key
                                            ] = previous
                                    _safe_fragment_rerun()
                            with row[0]:
                                st.markdown(
                                    f'<span style="color:{item.get("color", "#8ef0c8")}">'
                                    f"■</span> <b>{_measure_label_html(name)}</b> — "
                                    f"{value_text}{calib_note}",
                                    unsafe_allow_html=True,
                                )
                            profile = item.get("profile")
                            if profile:
                                st.caption(
                                    f"Line intensity: mean {profile['mean']:.2f}, "
                                    f"min {profile['min']:.2f}, "
                                    f"max {profile['max']:.2f}, "
                                    f"SD {profile['std']:.2f} "
                                    f"({profile.get('count', '?')} samples)"
                                )
                        action_col, clear_col = st.columns(2)
                        with action_col:
                            if st.button(
                                "Undo last",
                                key="viewer_measure_undo",
                                help="Remove the most recently created measurement.",
                            ):
                                st.session_state["measurements"] = measurements[:-1]
                                active_key = st.session_state.get("_measure_sig")
                                if active_key:
                                    previous = st.session_state.setdefault(
                                        "_measurement_store", {}
                                    ).get(active_key, {})
                                    if not isinstance(previous, dict):
                                        previous = {}
                                    previous["measurements"] = list(
                                        st.session_state["measurements"]
                                    )
                                    st.session_state["_measurement_store"][
                                        active_key
                                    ] = previous
                                _safe_fragment_rerun()
                        with clear_col:
                            clear_requested = st.button(
                                "Clear all", key="viewer_measure_clear"
                            )
                        if clear_requested:
                            st.session_state["measurements"] = []
                            active_key = st.session_state.get("_measure_sig")
                            if active_key:
                                previous = st.session_state.setdefault(
                                    "_measurement_store", {}
                                ).get(active_key, {})
                                if not isinstance(previous, dict):
                                    previous = {}
                                previous["measurements"] = []
                                st.session_state["_measurement_store"][active_key] = (
                                    previous
                                )
                            _safe_fragment_rerun()
                    else:
                        st.caption("No measurements yet in this image.")

        # --- Series / study browser + side-by-side comparison + cohort CSV ---
        with st.expander(
            "Series browser, comparison & visualizations", expanded=False
        ):
            series_groups = st.session_state.get("_series_groups")
            if (
                series_groups is None
                or st.session_state.get("_series_groups_sig") != files_fpr
            ):
                series_groups = self._build_series_index(files_list)
                st.session_state["_series_groups"] = series_groups
                st.session_state["_series_groups_sig"] = files_fpr
            series_by_first = {}
            for group in series_groups:
                if group["indices"]:
                    series_by_first[group["indices"][0]] = group

            def _pick_series() -> None:
                first_index = int(st.session_state.get("series_select", idx))
                st.session_state.viewer_index = min(first_index, num_files - 1)
                st.session_state.viewer_index_slider = first_index + 1
                st.session_state.coords = None

            if series_by_first and len(series_groups) > 1:
                st.selectbox(
                    "Series / study",
                    options=sorted(series_by_first.keys()),
                    format_func=lambda i: f"{i + 1}. {self._series_label(series_by_first[i], files_list)}",
                    key="series_select",
                    on_change=_pick_series,
                )
            else:
                st.caption("A single series was detected for this input set.")

            def _pick_compare() -> None:
                option = st.session_state.get("compare_select", "None")
                try:
                    selected = None if option == "None" else int(option)
                except (TypeError, ValueError):
                    selected = None
                st.session_state["compare_index"] = selected
                st.session_state.coords = None

            compare_options = ["None"] + [str(i) for i in range(num_files) if i != idx]
            if compare_options:
                st.selectbox(
                    "Compare side-by-side",
                    options=compare_options,
                    format_func=lambda o: (
                        "None"
                        if o == "None"
                        else f"{int(o) + 1}. {self._series_label({}, files_list, o)}"
                    ),
                    key="compare_select",
                    on_change=_pick_compare,
                )
            compare_index = st.session_state.get("compare_index")
            if compare_index is not None and 0 <= compare_index < num_files:
                with st.container(border=True):
                    self._render_comparison_pair(
                        disp_img,
                        files_list[compare_index],
                        compare_id=files_signature[compare_index],
                        slice_index=slice_index,
                        w_center=w_center,
                        w_width=w_width,
                        is_ct=is_ct,
                        analysis_modality=analysis_modality,
                    )
            elif compare_index is not None:
                st.session_state.pop("compare_index", None)

            if edge_norm is not None or tissue_map_viz is not None:
                st.markdown("**Edge Detection & Tissue Composition Map**")
                _edge_col, _tissue_col = st.columns(2)
                with _edge_col:
                    if edge_norm is not None:
                        st.caption(f"{edge_method} edge map")
                        st.image(
                            edge_norm,
                            caption=safe_img_alt(
                                _i18n.CAP_EDGE_DETECTION[lang],
                                modality=edge_method,
                            ),
                            width="stretch",
                            output_format="PNG",
                        )
                    else:
                        st.caption("Edge detection is not enabled for this image.")
                with _tissue_col:
                    if tissue_map_viz is not None:
                        st.caption(
                            "Research visualization based on CT-number thresholds; "
                            "not a validated tissue segmentation or clinical finding."
                        )
                        st.image(
                            tissue_map_viz,
                            caption=safe_img_alt(
                                _i18n.CAP_BONE_MUSCLE_FAT[lang],
                                modality="CT intensity classification",
                            ),
                            width="stretch",
                            output_format="PNG",
                        )
                        if tissue_map_percentages is not None:
                            p_fat, p_muscle, p_bone = tissue_map_percentages
                            st.caption(
                                f"Fat {p_fat:.1f}% · Muscle {p_muscle:.1f}% · "
                                f"Bone {p_bone:.1f}%"
                            )
                    else:
                        st.caption("Tissue composition map is not available for this image.")

            if roi_disp_viz is not None or l6_map_viz is not None:
                st.markdown("**Target ROI (Pure-Gray) & Structural Connectome**")
                _roi_col, _connectome_col = st.columns(2)
                with _roi_col:
                    if roi_disp_viz is not None:
                        st.caption(
                            "Cropped region around the selected coordinate "
                            "(Pure-Gray display protocol)."
                        )
                        st.image(
                            roi_disp_viz,
                            caption=safe_img_alt(
                                _i18n.CAP_TARGET_ROI[lang],
                                modality="Pure-Gray",
                            ),
                            width="stretch",
                            output_format="PNG",
                        )
                    else:
                        st.caption("Target ROI is not available for this image.")
                with _connectome_col:
                    if l6_map_viz is not None:
                        st.caption(
                            "Structural-balance mapping; research visualization, "
                            "not a validated graph-theoretic connectome."
                        )
                        st.image(
                            l6_map_viz,
                            caption=safe_img_alt(
                                _i18n.CAP_STRUCTURAL_CONNECTOME[lang],
                                modality="structural connectome",
                            ),
                            width="stretch",
                            output_format="PNG",
                        )
                    else:
                        st.caption(
                            "Structural connectome is not available for this image."
                        )

        if (native_stats or quality_report or radiomics_report
                or volume_preview is not None or ct_metrics_report is not None
                or ct_tissue_pct is not None):
            st.markdown(
                '<div class="analysis-results-heading">'
                '<span class="analysis-results-heading__eyebrow">Review workspace</span>'
                '<span class="analysis-results-heading__title">Analysis results</span>'
                '<span class="analysis-results-heading__hint">Derived from the selected image</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                _ct_tab_index = None
                if is_ct and not is_color:
                    result_tabs = st.tabs(
                        ["Intensity", "Quality", "Radiomics", "Volume", "CT Metrics"]
                    )
                    _ct_tab_index = 4
                else:
                    result_tabs = st.tabs(["Intensity", "Quality", "Radiomics", "Volume"])
                with result_tabs[0]:
                    if native_stats:
                        metric_cols = st.columns(4)
                        native_items = list(native_stats.items())[:4]
                        for column, (label, value) in zip(
                            metric_cols[: len(native_items)],
                            native_items,
                            strict=True,
                        ):
                            column.metric(label, f"{value:.3f}")
                    else:
                        st.caption("Native-intensity statistics are not enabled for this image type.")
                with result_tabs[1]:
                    if quality_report:
                        quality_cols = st.columns(2)
                        quality_items = list(quality_report.items())[:2]
                        for column, (label, value) in zip(
                            quality_cols[: len(quality_items)],
                            quality_items,
                            strict=True,
                        ):
                            column.metric(label, value)
                    else:
                        st.caption("Enable image quality analysis in the sidebar to view results.")
                with result_tabs[2]:
                    if radiomics_report:
                        radio_cols = st.columns(2)
                        radio_items = list(radiomics_report.items())[:2]
                        for column, (label, value) in zip(
                            radio_cols[: len(radio_items)],
                            radio_items,
                            strict=True,
                        ):
                            column.metric(label, value)
                        st.caption(
                            "First-order/histogram features are computed on raw "
                            "source voxels without resampling or fixed-bit "
                            "quantization, so they are **not IBSI-compliant**. "
                            "Document acquisition/reconstruction parameters if "
                            "these values are shared."
                        )
                    else:
                        st.caption("Enable radiomics in the sidebar to view results.")
                with result_tabs[3]:
                    if volume_preview is not None:
                        if visualization_mode == "3D Plotly":
                            st.plotly_chart(volume_preview, width="stretch")
                        else:
                            st.image(volume_preview, width="stretch")
                    else:
                        st.warning(
                            "The selected volumetric visualization could not be "
                            "rendered. Check that the volume is non-empty and "
                            "Plotly is installed for 3D Plotly mode."
                        )
                if _ct_tab_index is not None:
                    with result_tabs[_ct_tab_index]:
                        # --- Whole-image CT tissue composition ---
                        st.markdown(safe_section_heading(
                            3, _i18n.CAP_TISSUE_COMPOSITION[lang]),
                            unsafe_allow_html=True)
                        if ct_tissue_pct:
                            tissue_cols = st.columns(4)
                            items = list(ct_tissue_pct.items())[:4]
                            for column, (tissue, pct) in zip(
                                tissue_cols[: len(items)],
                                items,
                                strict=True,
                            ):
                                column.metric(tissue, f"{pct:.1f}%")
                            if len(items) > 4:
                                _extra = "; ".join(
                                    f"{t}: {p:.1f}%" for t, p in items[4:]
                                )
                                st.caption(_extra)
                        else:
                            st.caption("Tissue classification could not be computed for this image.")

                        # --- Whole-image quantitative density (L4) ---
                        st.markdown(safe_section_heading(
                            4, _i18n.SECTION_QUANTITATIVE_DENSITY[lang]),
                            unsafe_allow_html=True)
                        _density_res = self.quant_engine.execute(hu_data)
                        if isinstance(_density_res, dict):
                            density_cols = st.columns(3)
                            density_cols[0].metric(
                                _i18n.LABEL_MEAN_HU[lang],
                                f"{_density_res['mean']:.2f} HU",
                                help="Mean CT number in Hounsfield units (HU).",
                            )
                            density_cols[1].metric(
                                "95% CI (naive)",
                                f"[{_density_res['ci'][0]:.1f}, "
                                f"{_density_res['ci'][1]:.1f}] HU",
                                help="95% confidence interval under the naive "
                                "voxel-independence assumption.",
                            )
                            density_cols[2].metric(
                                _i18n.LABEL_SAMPLE_SIZE[lang],
                                f"{_density_res['n_voxels']:,}",
                            )
                        elif is_ct:
                            st.warning(
                                "Sigma Low: whole-image quantitative metrics "
                                "cannot be confirmed for this CT image."
                            )

                        # --- Whole-image CT quantitative metrics (IEC/ACR/AAPM) ---
                        st.markdown(safe_section_heading(
                            4, _i18n.SECTION_CT_QUANTITATIVE_METRICS[lang]),
                            unsafe_allow_html=True)
                        st.markdown(safe_diag_box(
                            "info",
                            "[RESEARCH/EDUCATION - NOT CLINICAL]",
                            role="note",
                        ), unsafe_allow_html=True)
                        if ct_metrics_report:
                            _h = ct_metrics_report["hu_statistics"]
                            _n = ct_metrics_report["noise"]
                            _sc = ct_metrics_report["snr_cnr"]
                            _t = ct_metrics_report["tissue_classification"]
                            _lcd = ct_metrics_report["low_contrast_detectability"]
                            m1, m2, m3 = st.columns(3)
                            m1.metric(_i18n.LABEL_MEAN_HU[lang], f"{_h['mean']:.1f}",
                                      help="Mean CT number in Hounsfield units (HU).")
                            m2.metric(_i18n.LABEL_STD_NOISE[lang], f"{_n['std_hu']:.1f} HU",
                                      help="Standard deviation of CT numbers; research measure.")
                            m3.metric(_i18n.LABEL_SNR[lang], f"{_sc['snr_water_hu']:.2f}",
                                      help="Research proxy: absolute mean CT number relative to water (0 HU), divided by the SD.")
                            st.caption(
                                f"{_i18n.LABEL_SAMPLE_SIZE[lang]}: {hu_data.size:,} voxels"
                            )
                            m4, m5, m6 = st.columns(3)
                            m4.metric(_i18n.LABEL_CNR[lang], f"{_sc['cnr']:.2f}",
                                      help="Research proxy using the two most prevalent HU tissue classes.")
                            m5.metric("NPS at 0 frequency", (
                                f"{ct_metrics_report['nps']['nps_0']:.2f} HU²·mm²"
                                if ct_metrics_report['nps']['nps_0'] is not None
                                else "Not available"
                            ), help="Noise power spectrum summary; requires spatially sampled 2D data.")
                            m6.metric(_i18n.LABEL_LOW_CONTRAST_CNR[lang], f"{_lcd['cnr']:.2f}",
                                      help="Rose-style research proxy; not a validated clinical detectability result.")
                            st.caption(
                                f"Low-contrast proxy: {'above' if _lcd['detectable'] else 'below'} "
                                "the illustrative Rose threshold of CNR 5.0; research use only."
                            )
                            _dos = ct_metrics_report.get("dosimetry")
                            if _dos and _dos.get("ctdivol") is not None:
                                st.caption(
                                    f"Dose metadata: CTDIvol = {_dos['ctdivol']:.2f} mGy"
                                )
                            _dom = sorted(
                                _t.items(),
                                key=lambda kv: kv[1]["fraction"],
                                reverse=True,
                            )[:3]
                            _dom_txt = ", ".join(
                                f"{k}: {v['fraction'] * 100:.1f}%"
                                for k, v in _dom
                            )
                            st.caption(
                                f"{_i18n.LABEL_DOMINANT_TISSUE[lang]}: {_dom_txt}"
                            )
                        else:
                            st.caption(
                                "CT quantitative metrics could not be computed "
                                "for this image (values may be outside the "
                                "supported HU range)."
                            )

        # --- 4. Deep dimensions (L3-L6 deep analysis) ---
        if st.session_state.coords and not is_color:
            self.render_deep_analysis(
                hu_data,
                disp_img,
                st.session_state.coords,
                st.container(),
                file_id,
                is_ct=is_ct,
                modality_key=analysis_modality,
                original_image_data=original_image_data,
            )
        elif is_color:
            st.caption(
                "Color image detected. Pixel-wise grayscale/CT ROI metrics are "
                "disabled unless a modality-specific color analysis is selected."
            )

        # --- Consolidated export surface ---
        # All export types live behind a single button and dialog: the user
        # can download one format or all formats from one window, keeping the
        # main interface free of scattered export controls. Payloads are
        # built lazily inside the dialog and cached per image/file set.
        report_dicom = {
            key: dicom_metadata.get(key)
            for key in (
                "rows", "columns", "pixel_spacing_mm", "sop_class_name",
                "transfer_syntax_name", "series_description",
                "series_instance_uid", "slice_thickness_mm",
            )
        }
        report_data = {
            "file_id": file_id,
            "modality": analysis_modality,
            "image_index": idx + 1,
            "num_files": num_files,
            "slice_index": slice_index,
            "slice_count": slice_count,
            "dicom": report_dicom,
            "window_preset": window_preset,
            "w_center": float(w_center),
            "w_width": float(w_width),
            "zoom": float(st.session_state.get("viewer_zoom", 1.0)),
            "measure_mode": str(st.session_state.get("viewer_measure_mode", "Off")),
            "measurements": list(st.session_state.get("measurements", [])),
            "measure_unit": str(st.session_state.get("viewer_measure_unit") or "mm"),
            "measure_precision": int(
                st.session_state.get("viewer_measure_precision", "2")
            ),
            "roi": st.session_state.get("roi_report_block"),
            "ai": st.session_state.get("last_ai_result"),
            "quality": quality_report if isinstance(quality_report, dict) else None,
            "radiomics": radiomics_report if isinstance(radiomics_report, dict) else None,
            "native_stats": native_stats if isinstance(native_stats, dict) else None,
        }
        _export_coords = st.session_state.get("coords")
        _export_roi_block = st.session_state.get("roi_report_block")
        _export_roi_center_px = None
        _export_roi_radius_px = None
        if isinstance(_export_coords, dict) and _export_roi_block:
            _coord_scale = float(st.session_state.get("coord_scale", 1.0))
            _export_roi_center_px = (
                float(_export_coords.get("x")) * _coord_scale,
                float(_export_coords.get("y")) * _coord_scale,
            )
            _export_roi_radius_px = int(
                (isinstance(_export_roi_block.get("radius_px"), int)
                 and _export_roi_block["radius_px"])
                or 64
            )
        if st.sidebar.button(
            "Export",
            key="viewer_export_all",
            type="primary",
            icon=":material/download:",
            help=(
                "Open a single export dialog with every available format "
                "(de-identified DICOM, cohort metrics CSV, radiomics CSV/Excel, "
                "HTML research report) and download one format or all of them."
            ),
        ):
            anon_bytes = self._deidentified_dicom_bytes(target)
            self._export_dialog(
                file_id=file_id,
                files_list=files_list,
                anon_bytes=anon_bytes,
                radiomics_data=radiomics_export_data,
                report_data=report_data,
                display_image=disp_img,
                measurements=list(st.session_state.get("measurements", [])),
                roi_center_px=_export_roi_center_px,
                roi_radius_px=_export_roi_radius_px,
                pixel_spacing_mm=dicom_metadata.get("pixel_spacing_mm"),
            )

    @st.dialog("Export", width="large")
    def _export_dialog(
        self,
        *,
        file_id: str,
        files_list: list,
        anon_bytes: bytes | None,
        radiomics_data: dict,
        report_data: dict,
        display_image: np.ndarray | None = None,
        measurements: list | None = None,
        roi_center_px: tuple | None = None,
        roi_radius_px: int | None = None,
        pixel_spacing_mm: tuple | None = None,
    ) -> None:
        """Single dialog exposing every export format for the active image.

        The user selects one format or all formats and downloads them from
        this window. Payloads are produced lazily and cached per file set so
        repeated exports avoid recomputation. The dialog is an accessible,
        keyboard-friendly modal (focus trapped, Esc closes); every control
        carries descriptive help text.
        """
        safe_name = self._safe_export_stem(
            file_id, int(report_data.get("image_index", 1)) - 1
        )
        sr_source = None
        if anon_bytes:
            try:
                src = pydicom.dcmread(
                    io.BytesIO(anon_bytes), stop_before_pixels=True
                )
                sr_source = (
                    str(src.SOPClassUID),
                    str(src.SOPInstanceUID),
                )
            except (OSError, EOFError, ValueError, TypeError, AttributeError):
                sr_source = None
        cohort_key = ("cohort", self._files_fingerprint(files_list))
        if st.session_state.get("_cohort_sig") != cohort_key:
            st.session_state.pop("_cohort_csv", None)
        cohort_value = st.session_state.get("_cohort_csv")
        entries = [
            {
                "slug": "dicom",
                "category": "DICOM and interoperability",
                "label": "Anonymized DICOM",
                "desc": (
                    "De-identified image copy (.dcm): PHI tags are blanked and "
                    "the PatientID is pseudonymized (DICOM PS3.10 file). Verify "
                    "that burned-in annotations are handled per study protocol."
                ),
                "available": bool(anon_bytes),
            },
            {
                "slug": "cohort",
                "category": "Analysis",
                "label": "Cohort metrics CSV",
                "desc": (
                    "Per-file image statistics in RFC 4180 CSV: one numeric row "
                    "per input file. Failed inputs remain visible with an explicit "
                    "status and error code."
                ),
                "available": bool(files_list),
            },
            {
                "slug": "radiomics",
                "category": "Analysis",
                "label": "Radiomics CSV / Excel",
                "desc": (
                    "First-order/histogram features as RFC 4180 CSV or a real "
                    "XLSX workbook. Not IBSI-compliant - see disclaimer."
                ),
                "available": bool(radiomics_data),
            },
            {
                "slug": "annotated",
                "category": "Measurements",
                "label": "Original image + measurements (PNG)",
                "desc": (
                    "PNG rendering of the base (windowed) image with every "
                    "distance/angle ruler and the active ROI drawn on top, at "
                    "native pixel resolution. Overlays only - the base image "
                    "pixels are never altered."
                ),
                "available": bool(
                    display_image is not None
                    and (measurements or roi_center_px is not None)
                ),
            },
            {
                "slug": "sr",
                "category": "Measurements",
                "label": "Measurement report (DICOM SR)",
                "desc": (
                    "Structured Measurement Report (DICOM SR) encoding every "
                    "distance/angle ruler and the ROI circle with UCUM units, "
                    "following DICOM PS3.16 TID 1500/1501/300/320: measurements "
                    "are NUM content items whose SCOORD coordinates reference "
                    "the anonymized source image."
                ),
                "available": bool(
                    (measurements or (roi_center_px is not None and roi_radius_px))
                    and sr_source
                ),
            },
            {
                "slug": "report",
                "category": "Analysis",
                "label": "Research report (HTML)",
                "desc": (
                    "Self-contained, print-friendly HTML summary of the display, "
                    "measurement, ROI, quality, and radiomics data for this image."
                ),
                "available": bool(report_data),
            },
            {
                "slug": "measured_batch",
                "category": "Package and provenance",
                "label": "All measured images (ZIP)",
                "desc": (
                    "Package all measured images saved in this session into one "
                    "ZIP containing applicable annotated PNG, JSON, CSV, Excel, "
                    "HTML, de-identified DICOM, and DICOM SR products."
                ),
                "available": any(
                    str(key).startswith(f"{self._files_fingerprint(files_list)}:")
                    and self._stored_measurements(value)
                    for key, value in st.session_state.get(
                        "_measurement_store", {}
                    ).items()
                ),
            },
        ]
        available = [entry for entry in entries if entry["available"]]
        st.caption(
            "Select one format or all formats, then click its Download button. "
            "Export filenames are pseudonymous by default; source pixels and "
            "privacy limitations are described in the manifest."
        )
        grid_cols = st.columns(2)
        selection = {}
        rendered_categories = set()
        for index, entry in enumerate(available):
            if entry["category"] not in rendered_categories:
                st.markdown(f"**{entry['category']}**")
                rendered_categories.add(entry["category"])
            col = grid_cols[index % 2]
            selection[entry["slug"]] = col.checkbox(
                entry["label"],
                value=True,
                help=entry["desc"],
                key=f"export_select_{entry['slug']}",
            )
        if not available:
            st.info("No export formats are available for the current image.")
            return

        if selection.get("cohort") and cohort_value is None:
            with st.spinner("Computing cohort statistics across files..."):
                cohort_value = self._build_cohort_metrics_csv(files_list)
            st.session_state["_cohort_csv"] = cohort_value
            st.session_state["_cohort_sig"] = cohort_key

        products = []
        if selection.get("dicom") and anon_bytes:
            products.append(
                {
                    "label": "Anonymized DICOM",
                    "data": anon_bytes,
                    "file_name": f"{safe_name}_anonymized.dcm",
                    "mime": "application/dicom",
                    "help": "De-identified DICOM PS3.10 file.",
                }
            )
        if selection.get("cohort") and cohort_value:
            products.append(
                {
                    "label": "Cohort metrics CSV",
                    "data": cohort_value,
                    "file_name": f"{safe_name}_cohort_metrics.csv",
                    "mime": "text/csv",
                    "help": "RFC 4180 UTF-8 CSV; one row per input file.",
                }
            )
        if selection.get("radiomics") and radiomics_data:
            products.append(
                {
                    "label": "Radiomics CSV",
                    "data": self._radiomics_export_csv(
                        radiomics_data, prefix=safe_name
                    ),
                    "file_name": f"{safe_name}_radiomics.csv",
                    "mime": "text/csv",
                    "help": "First-order/histogram features as CSV.",
                }
            )
            excel_bytes = self._radiomics_export_excel(
                radiomics_data, prefix=safe_name
            )
            if excel_bytes:
                products.append(
                    {
                        "label": "Radiomics Excel",
                        "data": excel_bytes,
                        "file_name": f"{safe_name}_radiomics.xlsx",
                        "mime": (
                            "application/vnd.openxmlformats-"
                            "officedocument.spreadsheetml.sheet"
                        ),
                        "help": "Real XLSX workbook (openpyxl).",
                    }
                )
            else:
                missing_deps = self._missing_export_dependencies()
                products.append(
                    {
                        "label": "Radiomics Excel (unavailable)",
                        "data": None,
                        "file_name": "",
                        "mime": "",
                        "help": (
                            "Excel export requires the optional `export` "
                            "dependencies (pandas + openpyxl). Missing: "
                            + (", ".join(missing_deps) if missing_deps else "unknown")
                            + "."
                        ),
                    }
                )
        if selection.get("report") and report_data:
            products.append(
                {
                    "label": "Research report (HTML)",
                    "data": self._build_html_research_report(report_data),
                    "file_name": f"{safe_name}_research_report.html",
                    "mime": "text/html",
                    "help": "Self-contained, print-friendly report.",
                }
            )
        if selection.get("measured_batch"):
            with st.spinner("Preparing measured-image batch..."):
                batch_bytes = self._build_measured_images_batch_export(
                    files_list,
                    files_fpr=self._files_fingerprint(files_list),
                )
            if batch_bytes:
                products.append(
                    {
                        "label": "All measured images (ZIP)",
                        "data": batch_bytes,
                        "file_name": "measured_images_batch.zip",
                        "mime": "application/zip",
                        "help": "ZIP package containing all measured-image exports.",
                    }
                )
        if selection.get("annotated") and display_image is not None:
            annotated_bytes = self._render_annotated_image_png(
                display_image,
                measurements=measurements,
                roi_center_px=roi_center_px,
                roi_radius_px=roi_radius_px,
                source_label=safe_name,
                pixel_spacing_mm=pixel_spacing_mm,
            )
            if annotated_bytes:
                products.append(
                    {
                        "label": "Original image + measurements (PNG)",
                        "data": annotated_bytes,
                        "file_name": f"{safe_name}_annotated.png",
                        "mime": "image/png",
                        "help": "Base image with rulers and ROI at native pixels.",
                    }
                )
        if (
            selection.get("sr")
            and sr_source
            and (measurements or (roi_center_px is not None and roi_radius_px))
        ):
            sr_bytes = self._build_dicom_sr_report(
                measurements,
                source_sop_class_uid=sr_source[0],
                source_sop_instance_uid=sr_source[1],
                pixel_spacing_mm=pixel_spacing_mm,
                roi_center_px=roi_center_px,
                roi_radius_px=roi_radius_px,
            )
            if sr_bytes:
                products.append(
                    {
                        "label": "Measurement report (DICOM SR)",
                        "data": sr_bytes,
                        "file_name": f"{safe_name}_measurements_sr.dcm",
                        "mime": "application/dicom",
                        "help": "DICOM PS3.16 TID 1500 structured measurement report.",
                    }
                )
        if measurements:
                measurement_rows = [
                    self._measurement_export_row(item, number)
                    for number, item in enumerate(measurements, 1)
                ]
                measurement_csv = io.StringIO()
                writer = csv.DictWriter(
                    measurement_csv,
                    fieldnames=list(measurement_rows[0]),
                    extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(measurement_rows)
                measurement_json = {
                    "schema": "measurement-annotation",
                    "version": 1,
                    "source": safe_name,
                    "pixel_spacing_mm": list(pixel_spacing_mm or []),
                    "measurements": [
                        self._normalized_measurement(item)
                        for item in measurements
                    ],
                }
                products.extend(
                    [
                        {
                            "label": "Measurement data CSV",
                            "data": measurement_csv.getvalue().encode("utf-8-sig"),
                            "file_name": f"{safe_name}_measurements.csv",
                            "mime": "text/csv",
                            "help": "UTF-8 CSV measurement table with calibration provenance.",
                        },
                        {
                            "label": "Measurement data JSON",
                            "data": json.dumps(
                                measurement_json, indent=2, default=str
                            ).encode("utf-8"),
                            "file_name": f"{safe_name}_measurements.json",
                            "mime": "application/json",
                            "help": "Machine-readable measurement coordinates and calibration.",
                        },
                    ]
                )

        products.append(
                {
                    "label": "Export provenance manifest",
                    "data": self._export_standards_manifest(
                        products,
                        source=safe_name,
                        measurement_count=len(measurements or []),
                    ),
                    "file_name": f"{safe_name}_export_manifest.json",
                    "mime": "application/json",
                    "help": "Machine-readable provenance, hashes, privacy, and standards boundary.",
                }
        )

        if any(product["data"] is not None for product in products):
            st.divider()
            st.markdown("**Download**")
            row_cols = st.columns(2)
            for index, product in enumerate(products):
                col = row_cols[index % 2]
                if product["data"] is None:
                    col.caption(f"{product['label']} - {product['help']}")
                else:
                    col.download_button(
                        product["label"],
                        data=product["data"],
                        file_name=product["file_name"],
                        mime=product["mime"],
                        help=product["help"],
                        key=f"export_dl_{index}",
                    )
            zip_bytes = self._build_export_zip(products, zip_name=safe_name)
            if zip_bytes:
                st.caption(
                    "Tip: use **Download all** to get every selected format in "
                    "one archive named after the source image."
                )
                st.download_button(
                    "Download all (ZIP)",
                    data=zip_bytes,
                    file_name=f"{safe_name}_export.zip",
                    mime="application/zip",
                    help=(
                        "Single .zip archive containing all available export "
                        "formats, named after the source image."
                    ),
                    key="export_dl_all",
                )
        else:
            st.caption("No formats are selected for download.")
        st.caption("Research/educational exports only - not a medical device.")

    @staticmethod
    def _detect_input_modality(files_list: list) -> str:
        """Detect modality metadata before exposing modality-specific tools."""
        detected = set()
        saw_volume = False
        for target in files_list[:8]:
            path = getattr(target, "name", str(target))
            lower_path = str(path).lower()
            if not (
                lower_path.endswith((".dcm", ".dicom", ".ima", ".img"))
                or not Path(lower_path).suffix
            ):
                if lower_path.endswith((".nii", ".nii.gz", ".nrrd", ".mha", ".mhd")):
                    saw_volume = True
                continue
            try:
                if hasattr(target, "seek"):
                    target.seek(0)
                    dataset = pydicom.dcmread(target, stop_before_pixels=True)
                    target.seek(0)
                else:
                    dataset = pydicom.dcmread(
                        str(path), stop_before_pixels=True, force=True
                    )
                result = ModalityDetector().detect(dataset)
                if result.modality:
                    detected.add(result.modality)
            except (OSError, ValueError, pydicom.errors.InvalidDicomError):
                continue
        if len(detected) == 1:
            if saw_volume:
                return "MIXED"
            return next(iter(detected))
        if len(detected) > 1:
            return "MIXED"
        if saw_volume:
            return "VOLUME"
        return "UNKNOWN"

    @staticmethod
    def _feature_capabilities(modality: str) -> dict[str, bool]:
        """Return the registry-owned UI and calculation capabilities."""
        return get_feature_capabilities(modality)

    def _available_ai_domains(self, modality: str) -> list[str]:
        """Resolve compatible ViT domains across current and stale sessions."""
        resolver = getattr(self.ai_engine, "available_domains", None)
        if callable(resolver):
            return list(resolver(modality))
        normalized = str(modality or "").upper().split("/")[-1].strip()
        if normalized.startswith("DICOM "):
            normalized = normalized[6:].strip()
        fallback_modalities = {
            "chest": {"CR", "DX", "XRAY"},
            "brain": {"MR"},
            "age": {"CR", "DX", "XRAY"},
        }
        return [
            domain for domain, modalities in fallback_modalities.items()
            if normalized in modalities
        ]

    @staticmethod
    def _parse_image_type(modality: str, data: np.ndarray) -> tuple[str, bool]:
        """Resolve a canonical image type and whether pixels are RGB."""
        text = modality.upper()
        if text.startswith("DICOM /"):
            name = text.split("/", 1)[1].strip().split()[0]
        elif text.startswith("VOLUME /"):
            name = "VOLUME"
        else:
            name = text.split()[0] if text else "UNKNOWN"
        is_color = (
            name != "VOLUME"
            and data.ndim == 3
            and data.shape[-1] in (3, 4)
        )
        return name, is_color

    @staticmethod
    def _uses_monochrome1_display(
        modality: str,
        modality_metadata: str = "",
    ) -> bool:
        """Return whether the modality should use film-like MONOCHROME1."""
        modality_key = str(modality or "").upper()
        if modality_key in {"CT", "MR"}:
            return False
        if modality_key in {"CR", "DX", "XR", "X_RAY", "XRAY"}:
            return True
        return "MONOCHROME1" in str(modality_metadata or "").upper()

    @staticmethod
    def _default_window_preset(modality: str) -> str:
        """Select a display preset appropriate to the detected modality."""
        return {
            "CT": "brain",
            "MR": "mri_t1",
            "PT": "pet_suv",
            "US": "us",
            "SPECT": "spect",
            "NM": "nm",
            "MG": "mammo",
            "CR": "chest",
            "DX": "chest",
        }.get(modality, "custom")

    @staticmethod
    def _prepare_color_display(data: np.ndarray) -> np.ndarray:
        """Render RGB/RGBA DICOM pixels without collapsing a color axis."""
        channels = data[..., :3].astype(np.float32)
        output = np.empty(channels.shape, dtype=np.uint8)
        for channel in range(3):
            values = channels[..., channel]
            lo, hi = np.percentile(values, [1, 99])
            if hi <= lo:
                output[..., channel] = np.clip(values, 0, 255).astype(np.uint8)
            else:
                output[..., channel] = np.clip(
                    (values - lo) * 255.0 / (hi - lo), 0, 255
                ).astype(np.uint8)
        return output

    @staticmethod
    def _render_pixel_hover_viewer(
        display_image: np.ndarray,
        source_values: np.ndarray,
        unit: str,
        key: str,
        zoom: float = 1.0,
        view_mode: str = "fit",
        measure_lines: list | None = None,
        measure_mode: str = "off",
        pixel_spacing_mm: list | tuple | None = None,
        image_sig: str = "",
    ):
        """Render a local hover readout while preserving source pixel values."""
        payload_cache = st.session_state.setdefault(
            "_pixel_viewer_payload_cache", OrderedDict()
        )
        if not isinstance(payload_cache, OrderedDict):
            payload_cache = OrderedDict(payload_cache)
            st.session_state["_pixel_viewer_payload_cache"] = payload_cache
        payload = payload_cache.get(str(image_sig))
        if payload is None:
            display = Image.fromarray(display_image.astype(np.uint8), mode="L")
            encoded_image = io.BytesIO()
            display.save(
                encoded_image,
                format="PNG",
                optimize=False,
                compress_level=1,
            )
            values = np.ascontiguousarray(source_values, dtype="<f4")
            payload = {
                "image": base64.b64encode(
                    encoded_image.getvalue()
                ).decode("ascii"),
                "values": base64.b64encode(values.tobytes()).decode("ascii"),
                "width": int(values.shape[1]),
                "height": int(values.shape[0]),
            }
            payload_cache[str(image_sig)] = payload
        else:
            payload_cache.move_to_end(str(image_sig))
        while len(payload_cache) > 32:
            payload_cache.popitem(last=False)
        result = _PIXEL_HOVER_VIEWER(
            data={
                "image": "data:image/png;base64," + payload["image"],
                "values": payload["values"],
                "width": payload["width"],
                "height": payload["height"],
                "unit": unit,
                "zoom": max(0.25, min(float(zoom), 4.0)),
                "view_mode": view_mode,
                "pixel_spacing_mm": list(pixel_spacing_mm or []),
                "image_sig": str(image_sig),
                "measure_mode": measure_mode if measure_mode in ("line", "angle") else "off",
                "measure_lines": [
                    {
                        "x1": int(item["data"]["x1"]),
                        "y1": int(item["data"]["y1"]),
                        "x2": int(item["data"]["x2"]),
                        "y2": int(item["data"]["y2"]),
                        "x3": int(item["data"]["x3"])
                        if item.get("kind") == "angle" and "x3" in item["data"] else None,
                        "y3": int(item["data"]["y3"])
                        if item.get("kind") == "angle" and "y3" in item["data"] else None,
                        "kind": item.get("kind", "distance"),
                        "label": ClinicalApp._measurement_display(item),
                        "color": item.get("color", "#8ef0c8"),
                    }
                    for item in (measure_lines or [])
                    if ClinicalApp._measurement_coords_valid(
                        item.get("kind", "distance"), item.get("data", {})
                    )
                ],
            },
            key=key,
            on_click=lambda: None,
        )
        return result

    @staticmethod
    def _model_ready_image_from_source(source: np.ndarray) -> np.ndarray:
        """Render ORIGINAL source voxels to the uint8 input the ViT consumes.

        Normalization is computed from the calibrated source values themselves,
        so AI input is fully decoupled from on-screen display settings: window
        center/width, percentile stretch and zoom never reach the model. The
        display array changes when the user re-windows the image; the model
        input below does not, keeping inference stable and traceable to source.
        """
        data = np.asarray(source)
        if data.ndim != 2 or data.size == 0:
            raise ValueError(
                "model input requires a non-empty 2D grayscale slice"
            )
        flat = data.reshape(-1)
        if not np.isfinite(flat).any():
            raise ValueError("model input requires finite source voxels")
        finite = np.asarray(flat[np.isfinite(flat)], dtype=np.float64)
        lo, hi = float(np.percentile(finite, 1.0)), float(np.percentile(finite, 99.0))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo, hi = float(finite.min()), float(finite.max())
        if hi <= lo:
            hi = lo + 1.0  # degenerate constant ROI: legal single-level map
        scale = 255.0 / float(hi - lo)
        normalized = np.clip(
            (data.astype(np.float32) - float(lo)) * scale,
            0.0,
            255.0,
        )
        return normalized.astype(np.uint8)

    @staticmethod
    def _apply_windowing(hu: np.ndarray, center: int = 40, width: int = 400, preset: Optional[str] = None) -> np.ndarray:
        """
        CT Windowing (V2.2): nuclear fusion of speed and precision.
        Architecture: Static Method for SIMD-Optimized Throughput.
        
        Presets (from core.constants.DISPLAY_PRESETS):
            "lung":        center=-600,  width=1500
            "bone":        center=400,   width=2000
            "brain":       center=40,    width=80
            "soft_tissue": center=50,   width=400
            "vascular_cta": center=300, width=700
            "venography": center=150,  width=500
            "neurovascular": center=100, width=400
            "temporal_bone": center=700, width=4000
            "spine_bone": center=350, width=1800
            "abdomen":     center=50,   width=400
            "mediastinum": center=40,   width=400
            "mri_t1":      center=600,   width=1200
            "mri_t2":      center=420,   width=840
            "mri_flair":   center=450,   width=900
            "pet_suv":     center=3,     width=8
            "us":          center=50,    width=100
            "custom":      uses provided center/width
        """
        if preset and preset in DISPLAY_PRESETS:
            center, width = DISPLAY_PRESETS[preset]
        try:
            # --- 1. Physiological boundaries ---
            # Use true division so odd and floating-point widths remain
            # symmetric around the requested window center.
            half_width = float(width) / 2.0
            w_min = center - half_width
            w_max = center + half_width

            # --- 2. Vectorized clipping ---
            # Use hu.copy() so the original matrix is never altered (data integrity)
            windowed = np.clip(hu, w_min, w_max)

            # --- 3. Calibrated energy conversion (optimized normalization) ---
            # Replace division with multiplication by the reciprocal to cut CPU cycles
            lut_factor = 255.0 / max(width, 1.0)

            # Final operation: (x - min) * factor
            # Executed in a vectorized pattern to exploit the AVX/SIMD units of your CPU
            normalized = (windowed - w_min) * lut_factor

            # --- 4. Integer casting ---
            # Assertion Layer: final uint8 conversion to guarantee grayscale display compatibility
            return np.round(normalized).astype(np.uint8)

        except (ValueError, TypeError, MemoryError) as e:
            # Target matrix and memory errors specifically (specific clinical guard)
            # Report the failure instead of silently returning zeros that could
            # lead to a wrong interpretation
            raise RuntimeError(f"WINDOWING_MATRIX_FAILURE: {e!s}") from e

    @staticmethod
    def _heuristic_segment(roi_hu: np.ndarray) -> np.ndarray:
        """
        Deterministic intensity-based region mask (no trained model required).
        Isolates the largest coherent region within the 5th-95th percentile band.
        """
        from skimage import measure
        lo, hi = np.percentile(roi_hu, [5, 95])
        mask = ((roi_hu >= lo) & (roi_hu <= hi)).astype(np.uint8)
        labels = measure.label(mask)
        if labels.max() == 0:
            return mask
        sizes = np.bincount(labels.ravel())
        biggest = int(np.argmax(sizes[1:]) + 1)
        return (labels == biggest).astype(np.uint8) * 255

    def _render_anatomical_segmentation(
        self,
        volume_data: np.ndarray,
        file_id: str,
        *,
        is_ct: bool,
        raw_is_color: bool,
    ) -> None:
        """Render optional model-backed 3D anatomical segmentation controls."""
        if volume_data.ndim != 3 or raw_is_color:
            return
        statuses = self.anatomical_segmentation.statuses()
        with st.expander("Anatomical segmentation", expanded=False):
            st.caption(
                "Model-backed 3D segmentation only. The result is a research "
                "mask and is not a diagnosis."
            )
            backend = st.selectbox(
                "Backend",
                [status.backend for status in statuses],
                key="anatomical_segmentation_backend",
            )
            selected = next(status for status in statuses if status.backend == backend)
            if not selected.available:
                st.info(selected.detail)
                return
            if backend == "TotalSegmentator" and not is_ct:
                st.info("TotalSegmentator requires a 3D CT volume.")
                return
            if st.button(
                f"Run {backend}",
                key="run_anatomical_segmentation",
                type="primary",
            ):
                try:
                    if backend == "TotalSegmentator":
                        masks = self.anatomical_segmentation.segment_with_totalsegmentator(
                            volume_data
                        )
                    else:
                        masks = self.anatomical_segmentation.segment_with_monai_label(
                            volume_data
                        )
                    st.session_state.anatomical_masks = masks
                    st.session_state.anatomical_masks_file = file_id
                    st.success(
                        f"{backend} returned {len(masks)} non-empty anatomical masks."
                    )
                except (OSError, RuntimeError, ValueError, requests.RequestException) as exc:
                    logger.exception("anatomical segmentation failed")
                    st.error(f"{backend} segmentation failed: {exc}")

            masks = st.session_state.get("anatomical_masks")
            if (
                masks
                and st.session_state.get("anatomical_masks_file") == file_id
            ):
                label = st.selectbox(
                    "Mask",
                    sorted(masks),
                    key="anatomical_segmentation_label",
                )
                mask = np.asarray(masks[label])
                if mask.shape != volume_data.shape:
                    st.error(
                        "The returned mask shape does not match the source volume; "
                        "it was not displayed."
                    )
                    return
                slice_axis = int(np.argmin(volume_data.shape))
                slice_index = min(
                    int(st.session_state.get("viewer_slice_index", 0)),
                    mask.shape[slice_axis] - 1,
                )
                mask_slice = np.take(mask, slice_index, axis=slice_axis)
                st.image(
                    (mask_slice > 0).astype(np.uint8) * 255,
                    caption=f"{label} mask · slice {slice_index + 1}",
                    clamp=True,
                    width="stretch",
                )

    def render_deep_analysis(
        self,
        hu_data: np.ndarray,
        disp_img: np.ndarray,
        coords: dict,
        info_col,
        file_id: str,
        is_ct: bool = True,
        modality_key: str = "CT",
        original_image_data: np.ndarray | None = None,
    ) -> Optional[np.ndarray]:
        """
        Deep ROI Analysis Pipeline (L3-L6).
        """
        lang = st.session_state.get("app_lang", "en")
        capabilities = self._feature_capabilities(modality_key)
        ai_enabled = capabilities["ai_inference"]
        advanced_enabled = capabilities["advanced_processing"]
        try:
            source_data = (
                np.asarray(original_image_data)
                if original_image_data is not None
                else np.asarray(hu_data)
            )
            if source_data.ndim not in (2, 3):
                raise ValueError(
                    "Advanced AI requires the original image to be 2D or 3D; "
                    f"received {source_data.ndim}D data."
                )
            if source_data.size == 0 or not np.isfinite(source_data).all():
                raise ValueError(
                    "Advanced AI requires a non-empty original image with finite values."
                )
            if source_data.ndim == 3 and min(source_data.shape) < 2:
                raise ValueError(
                    "Advanced AI requires at least two voxels along every 3D axis."
                )
            if not isinstance(coords, dict) or 'x' not in coords or 'y' not in coords:
                logger.warning("render_deep_analysis: invalid coordinates %r",
                               type(coords).__name__)
                st.error(_i18n.ERR_INVALID_COORDS[lang])
                return None
            # --- 1. Extract ROI around the clicked coordinates ---
            h_dim, w_dim = hu_data.shape
            # Map displayed coordinates back to original image pixels.
            scale = st.session_state.get('coord_scale', 1.0)
            center_x = round(coords['x'] * scale)
            center_y = round(coords['y'] * scale)
            radius = 64

            y1, y2 = np.clip([center_y - radius, center_y + radius], 0, h_dim).astype(int)
            x1, x2 = np.clip([center_x - radius, center_x + radius], 0, w_dim).astype(int)

            roi_hu = hu_data[y1:y2, x1:x2]
            roi_disp = disp_img[y1:y2, x1:x2]

            if roi_hu.size == 0:
                return None

            # --- 2. CT HU range validation (data-integrity check) ---
            if is_ct and (
                not np.isfinite(roi_hu).all()
                or np.any((roi_hu < HU_MIN) | (roi_hu > HU_MAX))
            ):
                logger.error("ROI contains invalid CT HU values")
                st.error(_i18n.ERR_ROI_OUT_OF_RANGE[lang])
                return None

            # AI input is derived from the ORIGINAL calibrated source voxels
            # (roi_hu), never from the windowed/display array (roi_disp). The
            # on-screen window/zoom may change freely without ever altering the
            # model's input, matching how MONAI and SimpleITK consume source_data.
            model_input = ClinicalApp._model_ready_image_from_source(roi_hu)

            with info_col:
                st.caption(f"**Fingerprint:** `{file_id}`")

                # --- L4: quantitative density (moved to Review workspace -> Analysis results) ---
                # ROI stats are still captured here for the export payload only;
                # the on-screen display now lives on the whole image in the
                # Analysis results "CT Metrics" tab.
                stats_res = self.quant_engine.execute(roi_hu) if is_ct else None

                if isinstance(stats_res, dict):
                    st.session_state["roi_report_block"] = {
                        "radius_px": radius,
                        "n_voxels": int(roi_hu.size),
                        "mean": float(stats_res.get("mean", float("nan"))),
                        "std": float(stats_res.get("std", float("nan"))),
                        "ci": (
                            [float(v) for v in stats_res["ci"]]
                            if isinstance(stats_res.get("ci"), (list, tuple))
                            else [None, None]
                        ),
                    }

                if not is_ct:
                    try:
                        generic_out = _get_modality_calculator(modality_key).calculate(
                            roi_hu
                        )
                        generic_stats = generic_out["statistics"]
                        st.markdown(
                            safe_section_heading(
                                3,
                                f"{generic_out['modality']} native-intensity "
                                "measurements",
                            ),
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            safe_diag_box(
                                "info",
                                "[RESEARCH/EDUCATION - NOT CLINICAL]",
                                (
                                    f"Units: {generic_out['intensity_units']}; "
                                    f"basis: {generic_out['calibration']}. "
                                    "These are descriptive measurements, not "
                                    "validated biomarkers."
                                ),
                                role="note",
                            ),
                            unsafe_allow_html=True,
                        )
                        g1, g2, g3 = st.columns(3)
                        g1.metric(
                            "Mean Native Intensity",
                            f"{generic_stats['mean']:.3f} "
                            f"{generic_out['intensity_units']}",
                        )
                        g2.metric(
                            "Native-Intensity SD",
                            f"{generic_stats['std']:.3f} "
                            f"{generic_out['intensity_units']}",
                        )
                        g3.metric("Sample size", f"{generic_stats['n_voxels']:,}")
                    except (ValueError, TypeError) as exc:
                        st.warning(f"Native-intensity metrics unavailable: {exc}")

                st.divider()

                if ai_enabled:
                    # --- L3: inference measurement (ViT dimension) ---
                    st.markdown(safe_section_heading(
                        3, f"L3: AI Vision Transformer "
                           f"[{self.ai_engine._get_domain().upper()}]"),
                        unsafe_allow_html=True)
                    inf_label, inf_conf, inf_msg = self.ai_engine.infer(
                        model_input,
                        hu_data=roi_hu if is_ct else None,
                        allow_hu_fallback=is_ct,
                        modality=modality_key,
                    )
                    provenance = self.ai_engine.last_provenance
                    if provenance:
                        st.caption(
                            "ViT input: original calibrated source ROI, "
                            "normalized display-independently "
                            f"{provenance['source_shape']} -> "
                            f"{provenance['model_input_shape'][-2:]} "
                            "(no display window/percentile affects the model; "
                            "quantitative analysis uses the original ROI)."
                        )

                    is_fallback = inf_msg.startswith("Fallback:")
                    inf_label_esc = html.escape(str(inf_label))
                    inf_msg_esc = html.escape(str(inf_msg))
                    # Align the UI gate with the engine threshold (0.85): infer()
                    # already returns "UNCERTAIN_DATA_ALERT" for conf < 0.85, so a
                    # separate 0.80 gate below would have rendered that alert as a
                    # normal high-confidence output.
                    is_uncertain = (inf_label == "UNCERTAIN_DATA_ALERT"
                                    or inf_conf < self.ai_engine.confidence_threshold)

                    st.session_state["last_ai_result"] = {
                        "label": str(inf_label),
                        "confidence": f"{inf_conf:.4f}",
                        "message": str(inf_msg),
                    }

                    if is_fallback:
                        st.markdown(safe_diag_box(
                            "warning",
                            inf_label_esc,
                            f"{inf_msg_esc}<br>Heuristic score: {inf_conf:.4f}",
                            role="status",
                        ), unsafe_allow_html=True)
                    elif is_uncertain:
                        st.markdown(safe_diag_box(
                            "error",
                            _i18n.LOW_CONFIDENCE_MANUAL_REVIEW[lang],
                            f"{inf_msg_esc} (confidence below "
                            f"{self.ai_engine.confidence_threshold:.0%})",
                            role="alert",
                        ), unsafe_allow_html=True)
                    else:
                        st.markdown(safe_stat_card(
                            "[INFERENCE DIMENSION]",
                            inf_label_esc.upper(),
                            f"Heuristic score: {inf_conf:.4f}",
                        ), unsafe_allow_html=True)

                else:
                    st.info("AI inference is unavailable for this modality.")
                    st.session_state["last_ai_result"] = None

            # --- MONAI / SimpleITK: advanced analysis (when enabled) ---
            if advanced_enabled and (st.session_state.get('enable_monai') or st.session_state.get('enable_sitk')):
                st.divider()
                st.subheader("Advanced AI: MONAI + SimpleITK")
                adv_cols = st.columns(3)

                if (
                    advanced_enabled
                    and st.session_state.get('enable_monai')
                    and source_data.size >= 4096
                ):
                    with adv_cols[0]:
                        try:
                            if self.monai_preprocessor is None:
                                from engines.monai_preprocessor import MONAIPreprocessor
                                self.monai_preprocessor = MONAIPreprocessor()
                            processed = self.monai_preprocessor.preprocess_volume(
                                source_data
                            )
                            st.metric(
                                "MONAI Resampled",
                                f"{processed.shape}",
                                help=(
                                    "Preprocessed from the original image; "
                                    f"source dimensions: {source_data.shape}"
                                ),
                            )
                            st.caption(
                                "Input: original image · "
                                f"{source_data.ndim}D · "
                                f"{source_data.size:,} voxels. "
                                "The selected ROI is not used as the model input."
                            )
                        except (RuntimeError, ValueError, TypeError) as e:
                            st.error(f"MONAI input validation failed: {e}")

                if st.session_state.get('enable_sitk'):
                    with adv_cols[1]:
                        try:
                            isotropic = self.sitk_registration.resample_to_isotropic(
                                source_data,
                                spacing=(1.0,) * source_data.ndim,
                            )
                            st.metric(
                                "SimpleITK Isotropic",
                                f"{isotropic.shape}",
                                help=(
                                    "Resampled from the original image; "
                                    f"source dimensions: {source_data.shape}"
                                ),
                            )
                        except (RuntimeError, ValueError, TypeError) as e:
                            st.error(f"SimpleITK input validation failed: {e}")

                    with adv_cols[2]:
                        try:
                            # No ground truth exists for a single clicked ROI, so
                            # "Sensitivity/Specificity" (two thresholds of the same
                            # mask) were meaningless ~1.0/1.0 placeholders. Replace
                            # with transparent composition statistics.
                            roi_pos = int(np.sum(roi_hu > 0))
                            roi_med = float(np.median(roi_hu))
                            roi_high = int(np.sum(roi_hu > roi_med))
                            st.metric("Voxels > 0 HU",
                                      format_count_with_percent(roi_pos, roi_hu.size),
                                      help="Composition count only; not a tissue diagnosis.")
                            st.metric("Voxels > Median",
                                      format_count_with_percent(roi_high, roi_hu.size),
                                      help="Composition count only; not a tissue diagnosis.")
                        except Exception as e:
                            st.caption(f"Metrics: {str(e)[:50]}")

            # --- Model attention visualization ---
            if ai_enabled and st.session_state.get('enable_attention'):
                st.divider()
                st.subheader("Model Attention Visualization (XAI)")
                if self.ai_engine.processor is None or self.ai_engine.model is None:
                    st.caption(
                        "Attention visualization unavailable: the demonstration "
                        "model is not loaded."
                    )
                else:
                    try:
                        inputs = self.ai_engine.prepare_inputs(
                            model_input, modality_key
                        )
                        attn_map = XAIExplainer.compute_attention_map(self.ai_engine.model, inputs['pixel_values'])
                        overlay = XAIExplainer.overlay_heatmap(roi_disp, attn_map)
                        st.image(overlay,
                                 caption=_i18n.CAP_ATTENTION_OVERLAY[lang]
                                 if lang in _i18n.CAP_ATTENTION_OVERLAY
                                 else "Attention Overlay (ViT; exploratory, not lesion localization)",
                                 width="stretch")
                        st.caption(
                            "Attention visualization is a model-behavior aid only. "
                            "It is not a validated explanation, segmentation, or "
                            "lesion-localization result."
                        )
                    except Exception as e:
                        st.caption(f"XAI: {str(e)[:60]}")

            # --- Region Segmentation (Heuristic, deterministic) ---
            if st.session_state.get('enable_monai') and roi_hu.size >= 4096:
                st.divider()
                st.subheader("Region Segmentation")
                try:
                    seg = ClinicalApp._heuristic_segment(roi_hu)
                    st.image(seg,
                             caption=_i18n.CAP_SEGMENTATION_MASK[lang]
                             if lang in _i18n.CAP_SEGMENTATION_MASK
                             else "Segmentation Mask (intensity-based)",
                             width="stretch", clamp=True)
                except Exception as e:
                    st.caption(f"Segmentation: {str(e)[:60]}")

            return roi_hu

        except Exception:
            logger.exception("render_deep_analysis failed")
            st.error(_i18n.ERR_ANALYSIS_FAILED[lang])
            return None


if __name__ == "__main__":
    ClinicalApp().run()
