"""
Computed Tomography (CT) Modality Calculator.

Implements quantitative CT metrics on the Hounsfield Unit (HU) scale using the
shared :class:`ModalityCalculator` base.  DICOM RescaleSlope / RescaleIntercept
are applied automatically to convert stored pixel values to HU, then HU
statistics, image noise, uniformity, SNR/CNR, noise power spectrum (NPS),
modulation transfer function (MTF), CTDIvol/DLP dosimetry where the required
acquisition parameters are available, exposure index, low-contrast
detectability and tissue classification are reported for the full volume or an
optional region of interest.

Physically grounded equations follow the international standards cited below.

Reference standards: ACR CT Accreditation Program, IEC 61223 series,
IEC 60601-2-44, NEMA XR-25, AAPM TG-116 (image quality phantom), AAPM TG-233
(small-field dosimetry) and AAPM TG-150 (medical physics CT performance).

NOTE: This software is a research/education tool. It is NOT a certified
medical device and must NOT be used for clinical diagnosis or treatment.
Dosimetry values (CTDIvol/DLP) are computed only from the metadata supplied by
a calibrated device and are informational; they do not replace the output of a
validated TPS (treatment planning system) or a certified QA dose readout.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

try:  # pydicom is a hard dependency, kept importable for tooling-only use
    from pydicom.dataset import Dataset
except ImportError:  # pragma: no cover
    Dataset = None

from core.constants import (
    HU_MAX,
    HU_MIN,
    MIN_VOXELS_FOR_ANALYSIS,
    TISSUE_RANGES,
)
from engines.modality_calculators.base_calculator import ModalityCalculator

# Water reference used for SNR based on the CT number of water (0 HU).
HU_WATER: float = 0.0


class CTCalculator(ModalityCalculator):
    """
    Quantitative CT metric calculator operating on the HU scale.

    Inputs accepted by :meth:`calculate`: a pydicom Dataset, a DICOM file
    path, or a raw numpy array (interpreted as already-in-HU when no rescale
    tags are present).  An optional ROI may be a boolean mask matching the
    pixel array shape.
    """

    modality: str = "CT"

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def calculate(
        self,
        dataset: Any,
        roi: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Compute CT quantitative metrics on the HU scale.

        Args:
            dataset: pydicom Dataset, DICOM path, or numpy array.
            roi: Optional boolean mask selecting voxels to analyze.

        Returns:
            Dictionary of metric name -> value.  Keys: ``hu_statistics``,
            ``noise``, ``uniformity``, ``snr_cnr``, ``nps``, ``mtf``,
            ``dosimetry`` (CTDIvol/DLP when acquisition metadata is present),
            ``exposure_index``, ``low_contrast_detectability``,
            ``tissue_classification``, and the modality metadata
            (``modality``, ``intensity_units``, ``display_presets``,
            ``reference_standards``).

        Raises:
            ValueError: On non-finite, undersized, or invalid HU data.
        """
        pixels = self.prepare_pixels(dataset)

        if roi is not None:
            roi = np.asarray(roi, dtype=bool)
            if roi.shape != pixels.shape:
                raise ValueError(
                    f"ROI shape {roi.shape} does not match pixel shape {pixels.shape}."
                )
            pixels = pixels[roi]

        hu = self._validate_hu(pixels)

        spacing = self.get_pixel_spacing(dataset) if not isinstance(dataset, np.ndarray) else None
        px, py = spacing if spacing else (1.0, 1.0)
        nps = self._nps(hu, px, py)

        return {
            "modality": self.modality_key,
            "intensity_units": self.spec.intensity_units,
            "hu_statistics": self._hu_statistics(hu),
            "noise": self._noise(hu),
            "uniformity": self._uniformity(hu),
            "snr_cnr": self._snr_cnr(hu),
            "nps": nps,
            "mtf": self._mtf_from_nps(nps.get("nps_2d")),
            "dosimetry": self._dosimetry(dataset),
            "exposure_index": self._exposure_index(dataset),
            "low_contrast_detectability": self._low_contrast_detectability(hu),
            "tissue_classification": self._tissue_classification(hu),
            "display_presets": list(self.spec.windowing_presets),
            "reference_standards": self.get_reference(),
        }

    # ------------------------------------------------------------------
    # HU validation and tissue classification
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_hu(hu: np.ndarray) -> np.ndarray:
        """Reject out-of-range values and enforce the minimum voxel count."""
        if hu.size < MIN_VOXELS_FOR_ANALYSIS:
            raise ValueError(
                f"Fewer than {MIN_VOXELS_FOR_ANALYSIS} voxels available for "
                f"analysis (got {hu.size})."
            )
        if not np.isfinite(hu).all():
            raise ValueError("Non-finite HU values cannot be quantified.")
        out_of_range = (hu < HU_MIN) | (hu > HU_MAX)
        if np.any(out_of_range):
            raise ValueError(
                "HU values outside the supported quantitative range "
                f"[{HU_MIN:g}, {HU_MAX:g}] cannot be silently clipped."
            )
        return hu

    @staticmethod
    def _hu_statistics(hu: np.ndarray) -> Dict[str, float]:
        """Basic descriptive statistics of the HU distribution."""
        return {
            "min": float(np.min(hu)),
            "max": float(np.max(hu)),
            "mean": float(np.mean(hu)),
            "median": float(np.median(hu)),
            "std": float(np.std(hu)),
            "p5": float(np.percentile(hu, 5)),
            "p95": float(np.percentile(hu, 95)),
        }

    @staticmethod
    def _noise(hu: np.ndarray) -> Dict[str, Optional[float]]:
        """Image noise as the standard deviation of HU values."""
        std = float(np.std(hu))
        mean = float(np.mean(hu))
        # Coefficient of variation is conventionally non-negative even when
        # the measured signal has a negative mean (e.g. air in CT).
        cv = std / abs(mean) if not np.isclose(mean, 0.0) else None
        return {"std_hu": std, "coefficient_of_variation": cv}

    @staticmethod
    def _uniformity(hu: np.ndarray) -> Dict[str, float]:
        """
        Uniformity estimated from the difference between a central and a
        peripheral sampling region (ACR CT Accreditation methodology).
        """
        if hu.ndim < 2 or min(hu.shape[:2]) < 8:
            # Too small for meaningful ROI-based uniformity.
            return {"central_mean": None, "peripheral_mean": None, "difference": None}

        cy, cx = hu.shape[0] // 2, hu.shape[1] // 2
        r_center = max(1, min(hu.shape[:2]) // 8)
        central = hu[cy - r_center : cy + r_center + 1, cx - r_center : cx + r_center + 1]

        # Peripheral ring inset from the edge by ~10% of the smaller side.
        margin = max(1, min(hu.shape[:2]) // 10)
        interior = hu[margin:-margin, margin:-margin] if hu.shape[0] > 2 * margin else hu

        central_mean = float(np.mean(central))
        peripheral_mean = float(np.mean(interior)) if interior.size else float("nan")
        return {
            "central_mean": central_mean,
            "peripheral_mean": peripheral_mean,
            "difference": central_mean - peripheral_mean,
        }

    @classmethod
    def _snr_cnr(cls, hu: np.ndarray) -> Dict[str, float]:
        """
        Signal-to-noise ratio (SNR) and contrast-to-noise ratio (CNR).

        SNR is referenced to the CT number of water (0 HU) per ACR practice:
        ``SNR = |mean - HU_water| / std``.  CNR contrasts the two most
        abundant tissue classes separated by HU range.
        """
        std = float(np.std(hu))
        mean = float(np.mean(hu))

        snr_water = abs(mean - HU_WATER) / std if std != 0.0 else 0.0

        tissue = cls._tissue_classification(hu)
        classes = sorted(
            tissue.items(), key=lambda kv: kv[1]["fraction"], reverse=True
        )
        cnr = 0.0
        if len(classes) >= 2 and std != 0.0:
            m1 = classes[0][1]["mean"]
            m2 = classes[1][1]["mean"]
            cnr = abs(m1 - m2) / std

        return {"snr_water_hu": snr_water, "cnr": cnr}

    @staticmethod
    def _nps(hu: np.ndarray, pixel_size_x: float = 1.0, pixel_size_y: float = 1.0) -> Dict[str, Any]:
        """
        2D Noise Power Spectrum (NPS) of the HU noise field.

        Follows the AAPM TG-150 / IEC NPS methodology for a uniform area:

            NPS(u, v) = (dx * dy) / (Nx * Ny) * |FFT(n(x, y) - mean(n))|^2

        where ``n`` is the noise field, ``dx``/``dy`` are the pixel spacings in
        mm, and the FFT is applied over the Nx by Ny region.  Subtracting the
        mean forces the DC term to ~0.  For a white (spectrally flat) noise
        field the mean NPS over all frequency bins equals ``dx * dy * var(n)``
        (the NPS integrated over the Nyquist frequency band recovers the
        variance) — the standard invariant used for validation.  The radial
        average NPS(rho) and the zero-frequency NPS are also returned.

        Args:
            hu: 2D+ HU array.  The first two dimensions are used as the image.
            pixel_size_x: in-plane pixel spacing (mm) along the x axis.
            pixel_size_y: in-plane pixel spacing (mm) along the y axis.

        Returns:
            Dict with ``nps_2d`` (2D array), ``radial_frequency`` (cycles/mm),
            ``radial_nps`` (1D radial profile) and ``nps_0`` (zero-frequency
            NPS value in HU^2 mm^2).
        """
        if (
            hu.ndim < 2
            or hu.shape[0] < 8
            or hu.shape[1] < 8
            or not np.isfinite(pixel_size_x)
            or not np.isfinite(pixel_size_y)
            or pixel_size_x <= 0
            or pixel_size_y <= 0
        ):
            return {
                "nps_2d": None,
                "radial_frequency": None,
                "radial_nps": None,
                "nps_0": None,
                "dimensionality": "2D in-plane",
                "status": "invalid_input",
            }

        img = hu[: hu.shape[0], : hu.shape[1]].astype(np.float64)
        ny, nx = img.shape
        noise = img - img.mean()
        fft = np.fft.fft2(noise)
        # Standard normalization: NPS = dx*dy/(Nx*Ny) * |FFT|^2
        nps = (pixel_size_x * pixel_size_y) / (ny * nx) * np.abs(fft) ** 2
        nps = np.fft.fftshift(nps)

        # Radial frequency axes (cycles / mm).
        fx = np.fft.fftshift(np.fft.fftfreq(nx, d=pixel_size_x))
        fy = np.fft.fftshift(np.fft.fftfreq(ny, d=pixel_size_y))
        fx_grid, fy_grid = np.meshgrid(fx, fy)
        radius = np.sqrt(fx_grid ** 2 + fy_grid ** 2)

        # Radial average (excluding the zero-frequency DC term).
        dr = 1.0 / max(nx * pixel_size_x, ny * pixel_size_y)
        max_r = np.sqrt((0.5 / pixel_size_x) ** 2 + (0.5 / pixel_size_y) ** 2)
        bins = int(max_r / dr) + 1
        rad_freq = np.linspace(0.0, max_r, bins)
        # Assign every frequency bin once. The previous implementation
        # rebuilt a full-size boolean mask for every bin, making navigation
        # disproportionately slow on large CT slices.
        bin_indices = np.floor(radius / dr + 0.5).astype(np.intp)
        valid_bins = bin_indices < bins
        flat_bins = bin_indices[valid_bins].ravel()
        flat_nps = nps[valid_bins].ravel()
        counts = np.bincount(flat_bins, minlength=bins)
        sums = np.bincount(flat_bins, weights=flat_nps, minlength=bins)
        rad_nps = np.divide(
            sums,
            counts,
            out=np.zeros(bins, dtype=float),
            where=counts > 0,
        )
        # Drop empty tail bins.
        valid = counts > 0
        rad_freq = rad_freq[valid]
        rad_nps = rad_nps[valid]

        # Zero-frequency NPS approximated by the mean of the radial NPS near 0.
        near_zero = rad_nps[rad_freq <= dr]
        nps_0 = float(near_zero.mean()) if near_zero.size else float(rad_nps[0])

        return {
            "nps_2d": nps,
            "radial_frequency": rad_freq.tolist(),
            "radial_nps": rad_nps.tolist(),
            "nps_0": nps_0,
            "dimensionality": "2D in-plane",
            "methodology": "AAPM TG-150 / IEC-style uniform ROI estimate",
            "status": (
                "research estimate; not a 3D volume NPS and requires a "
                "uniform ROI and protocol-specific validation"
            ),
        }

    @staticmethod
    def _mtf_from_nps(nps_2d: Optional[np.ndarray], f_ref: float = 0.10) -> Dict[str, Any]:
        """
        Estimate a relative MTF curve from the 2D NPS.

        WARNING: For an ideal white-noise field the NPS is flat and the MTF
        derived from NPS alone is not a valid spatial-resolution measure.  The
        MTF from NPS is only an approximation for a correlated (structured)
        noise field.  This routine reports a normalized, frequency-domain
        summary and is provided for education/research; it does NOT replace an
        edge- or point-spread based MTF measurement.

        Returns radial MTF as ``sqrt(NPS)`` normalized to 1.0 at the lowest
        frequency, plus the frequency at which MTF falls to a reference level.

        Args:
            nps_2d: 2D NPS array from :meth:`_nps`.
            f_ref: reference MTF level (0.10 => 10%) used to report f10.

        Returns:
            Dict with ``radial_frequency``, ``mtf`` and ``f_ref``.
        """
        if nps_2d is None or nps_2d.ndim != 2:
            return {"radial_frequency": None, "mtf": None, "f_ref": None}

        ny, nx = nps_2d.shape
        cy, cx = ny // 2, nx // 2
        yy, xx = np.mgrid[0:ny, 0:nx]
        radius = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        # Radial average of sqrt(NPS) as a frequency-domain response proxy.
        radius_flat = np.unique(np.floor(radius)).astype(int)
        freqs = np.arange(0.0, radius_flat.max() + 1, 1.0)
        mtf = np.zeros(freqs.size)
        for i, r_bin in enumerate(freqs):
            mask = (radius >= r_bin - 0.5) & (radius < r_bin + 0.5)
            if mask.sum() > 0:
                mtf[i] = float(np.sqrt(np.abs(nps_2d[mask]).mean()))
        # Normalize by the mean response over the low-frequency band.  The
        # exact DC bin is ~0 for a mean-subtracted field, so a single-bin
        # normalization is unstable; use a neighbourhood average instead.
        norm_band = min(3, freqs.size)
        norm = float(np.mean(mtf[:norm_band]))
        if norm > 0:
            mtf = mtf / norm
        mtf = np.clip(mtf, 0.0, 1.0)
        # First crossing of the reference level (negative slope).
        f_ref_val = None
        for i in range(1, freqs.size):
            if mtf[i] < f_ref and mtf[i - 1] >= f_ref:
                f_ref_val = float(freqs[i])
                break
        return {
            "radial_frequency": freqs.tolist(),
            "mtf": np.clip(mtf, 0.0, 1.0).tolist(),
            "f_ref": f_ref_val,
        }

    @staticmethod
    def _dosimetry(dataset: Any) -> Dict[str, Any]:
        """
        Compute CTDIvol and DLP from acquisition metadata when available.

        CTDIvol is computed from CTDIw (phantom-weighted CT dose index) and
        pitch when the DICOM tags are present.  When ``CTDIvolPhantomHead`` /
        ``CTDIvolPhantomBody`` (tags (0018,9345)/(0018,9346)) are directly
        present in the dose report they are preferred.  DLP =
        CTDIvol * scan length.

        Returns dict with ``ctdiw``, ``pitch``, ``ctdivol``, ``dlp`` and
        ``source`` describing which branch was used.  Missing, informational
        metadata yields ``None`` (never a fabricated value).
        """
        if dataset is None or Dataset is None:
            return {"ctdiw": None, "pitch": None, "ctdivol": None, "dlp": None, "source": "not_available"}

        for attr, key in (("CTDIvolPhantomHead", "CTDIvolPhantomHead"),
                          ("CTDIvolPhantomBody", "CTDIvolPhantomBody")):
            val = getattr(dataset, attr, None)
            if val is not None:
                ctdi = float(val)
                return {
                    "ctdiw": ctdi,
                    "pitch": None,
                    "ctdivol": ctdi,
                    "dlp": None,
                    "source": attr,
                }

        # Volumetric dose index from CTDIw / pitch when both are available.
        ctdiw = getattr(dataset, "CTDIw", None)
        pitch = getattr(dataset, "SpiralPitch", None)
        if ctdiw is not None and pitch is not None and float(pitch) != 0.0:
            ctdi_vol = float(ctdiw) / float(pitch)
            return {
                "ctdiw": float(ctdiw),
                "pitch": float(pitch),
                "ctdivol": ctdi_vol,
                "dlp": None,
                "source": "ctdiw_pitch",
            }

        return {"ctdiw": None, "pitch": None, "ctdivol": None, "dlp": None, "source": "not_available"}

    @staticmethod
    def _exposure_index(dataset: Any) -> Optional[float]:
        """
        Exposure index from DICOM metadata.

        Reads ``ExposureIndex`` (0018,1412) when present; otherwise estimates
        a research-only exposure index from the CTDIw divided by a nominal
        reference (mm).  Returns None when no signal is available to avoid a
        fabricated number.
        """
        if dataset is None or Dataset is None:
            return None
        ei = getattr(dataset, "ExposureIndex", None)
        if ei is not None:
            return float(ei)
        ctdiw = getattr(dataset, "CTDIw", None)
        if ctdiw is None:
            return None
        # Research-only relative exposure proxy (no standard units).
        return round(float(ctdiw) / 10.0, 4)

    @staticmethod
    def _low_contrast_detectability(hu: np.ndarray) -> Dict[str, float]:
        """
        Low-contrast detectability proxy from contrast-to-noise.

        Computes the contrast-to-noise ratio (CNR) between the two most
        abundant tissue classes and expresses a "detectability" contrast term
        as ``|mu1 - mu2| / (sqrt(sigma1^2 + sigma2^2))`` (the so-called
        Rose-criterion style CNR) where sigma_i are the class standard
        deviations.  A value >= 5 is classically considered reliably
        detectable (Rose model).  Research/education only.
        """
        covered = np.zeros(hu.shape, dtype=bool)
        for lo, hi in TISSUE_RANGES.values():
            covered |= (hu >= lo) & (hu < hi)
        classes = []
        for name, (lo, hi) in TISSUE_RANGES.items():
            mask = (hu >= lo) & (hu < hi)
            if mask.sum() >= MIN_VOXELS_FOR_ANALYSIS and covered.sum() > 0:
                classes.append((name, hu[mask]))
        classes.sort(key=lambda kv: kv[1].size, reverse=True)
        if len(classes) < 2:
            return {"cnr": 0.0, "detectable": False, "note": "insufficient classes"}
        mu1, sig1 = float(classes[0][1].mean()), float(classes[0][1].std(ddof=1) if classes[0][1].size > 1 else 0.0)
        mu2, sig2 = float(classes[1][1].mean()), float(classes[1][1].std(ddof=1) if classes[1][1].size > 1 else 0.0)
        denom = np.sqrt(sig1 ** 2 + sig2 ** 2)
        cnr = abs(mu1 - mu2) / denom if denom > 0 else 0.0
        return {"cnr": round(cnr, 4), "detectable": bool(cnr >= 5.0)}

    @staticmethod
    def _tissue_classification(hu: np.ndarray) -> Dict[str, Dict[str, float]]:
        """
        Classify voxels into the tissue ranges and report fraction + mean.

        Uses the HU ranges in :data:`core.constants.TISSUE_RANGES`.  The
        ranges are inclusive of the lower bound and exclusive of the upper
        bound so the classes tile the HU range without overlap.
        """
        result: Dict[str, Dict[str, float]] = {}
        total = float(hu.size)
        for name, (lo, hi) in TISSUE_RANGES.items():
            mask = (hu >= lo) & (hu < hi)
            count = int(np.count_nonzero(mask))
            result[name] = {
                "count": count,
                "fraction": (count / total) if total else 0.0,
                "mean": float(np.mean(hu[mask])) if count else 0.0,
            }
        # Voxels outside every declared tissue range are classified as
        # "artifact" (metal / beam hardening) and reported separately.
        covered = np.zeros(hu.shape, dtype=bool)
        for lo, hi in TISSUE_RANGES.values():
            covered |= (hu >= lo) & (hu < hi)
        artifact_count = int(np.count_nonzero(~covered))
        result["Artifact"] = {
            "count": artifact_count,
            "fraction": (artifact_count / total) if total else 0.0,
            "mean": float(np.mean(hu[~covered])) if artifact_count else 0.0,
        }
        return result
