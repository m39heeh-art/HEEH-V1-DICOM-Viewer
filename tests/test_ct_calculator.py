"""
Numerical tests for the CT Modality Calculator.

Each metric is asserted against an analytically computed expectation so the
test verifies the *physics*, not just that keys exist. These are
research/education tools and NOT a medical device.
"""

import numpy as np
import pytest

from core.constants import HU_MIN, HU_MAX, TISSUE_RANGES
from engines.modality_calculators import CTCalculator, get_calculator, available_calculators


def _white_noise(n=64, mean=0.0, std=50.0, seed=0):
    """Test the  white noise path."""
    rng = np.random.default_rng(seed)
    return rng.normal(mean, std, (n, n)).astype(np.float32)


# ---------------------------------------------------------------------------
# Registry / factory
# ---------------------------------------------------------------------------
def test_factory_registers_ct():
    """Test that factory registers ct."""
    assert "CT" in available_calculators()
    assert available_calculators()["CT"] == "CTCalculator"


def test_get_calculator_resolves_case_aliases():
    """Test that get calculator resolves case aliases."""
    assert isinstance(get_calculator("CT"), CTCalculator)
    assert isinstance(get_calculator("ct"), CTCalculator)


def test_get_calculator_unknown_raises():
    """Test that get calculator unknown raises."""
    with pytest.raises(ValueError):
        get_calculator("UNKNOWN_MODALITY")


# ---------------------------------------------------------------------------
# HU validation
# ---------------------------------------------------------------------------
def test_validate_hu_rejects_out_of_range():
    """Quantitative CT analysis must not silently clip HU values."""
    hu = np.array([[1e6] * 20] * 20, dtype=np.float32)  # 400 voxels, all huge
    hu[10, 10] = -1e6
    with pytest.raises(ValueError, match="cannot be silently clipped"):
        CTCalculator._validate_hu(hu)


def test_validate_hu_rejects_too_small():
    """Test that validate hu rejects too small."""
    with pytest.raises(ValueError):
        CTCalculator._validate_hu(np.zeros((3, 3), dtype=np.float32))


# ---------------------------------------------------------------------------
# HU statistics and noise on a known distribution
# ---------------------------------------------------------------------------
def test_hu_statistics_known_gaussian():
    """Test that hu statistics known gaussian."""
    hu = _white_noise(mean=100.0, std=40.0, seed=2)
    s = CTCalculator._hu_statistics(hu)
    assert s["mean"] == pytest.approx(100.0, abs=2.0)
    assert s["std"] == pytest.approx(40.0, abs=2.0)
    assert s["median"] == pytest.approx(100.0, abs=2.0)


def test_noise_is_std_and_cv():
    """Test that noise is std and cv."""
    hu = _white_noise(std=25.0, seed=3)
    n = CTCalculator._noise(hu)
    assert n["std_hu"] == pytest.approx(25.0, abs=2.0)
    mean = float(np.mean(hu))
    # CV must equal std_hu/mean by definition (internal consistency).
    assert n["coefficient_of_variation"] == pytest.approx(n["std_hu"] / mean, rel=1e-9)


# ---------------------------------------------------------------------------
# SNR / CNR (water-referenced)
# ---------------------------------------------------------------------------
def test_snr_water_is_abs_mean_over_std():
    # Signal at +0 HU => SNR_w ~ 0; signal at 500 HU with std 50 => 10.
    """Test that snr water is abs mean over std."""
    hu = _white_noise(mean=500.0, std=50.0, seed=4)
    r = CTCalculator._snr_cnr(hu)
    assert r["snr_water_hu"] == pytest.approx(abs(500.0 - 0.0) / 50.0, rel=0.2)


# ---------------------------------------------------------------------------
# Uniformity (constant image -> ~0 difference)
# ---------------------------------------------------------------------------
def test_uniformity_constant_image_is_zero():
    """Test that uniformity constant image is zero."""
    hu = np.full((64, 64), 100.0, dtype=np.float32)
    u = CTCalculator._uniformity(hu)
    assert u["difference"] == pytest.approx(0.0, abs=1e-3)


# ---------------------------------------------------------------------------
# NPS invariants
# ---------------------------------------------------------------------------
def test_nps_white_noise_mean_equals_dxdy_var():
    """Test that nps white noise mean equals dxdy var."""
    hu = _white_noise(std=50.0, seed=5)
    dx = dy = 0.5
    r = CTCalculator._nps(hu, dx, dy)
    assert r["nps_2d"] is not None
    mean_nps = float(np.mean(r["nps_2d"]))
    var = float(hu.var())
    # mean(NPS) = dx*dy*var for a white (flat-spectrum) noise field.
    assert mean_nps == pytest.approx(dx * dy * var, rel=0.05)


def test_nps_uniform_field_is_zero():
    """Test that nps uniform field is zero."""
    hu = np.full((64, 64), 100.0, dtype=np.float32)
    r = CTCalculator._nps(hu, 1.0, 1.0)
    assert r["nps_0"] == pytest.approx(0.0, abs=1e-3)


def test_nps_radial_profile_matches_frequency_length():
    """Test that nps radial profile matches frequency length."""
    hu = _white_noise(seed=6)
    r = CTCalculator._nps(hu, 1.0, 1.0)
    assert len(r["radial_frequency"]) == len(r["radial_nps"])
    assert np.all(np.diff(r["radial_frequency"]) > 0)  # ascending frequency


def test_nps_too_small_returns_none():
    """Test that nps too small returns none."""
    r = CTCalculator._nps(np.zeros((4, 4), np.float32), 1.0, 1.0)
    assert r["nps_2d"] is None


# ---------------------------------------------------------------------------
# MTF from NPS
# ---------------------------------------------------------------------------
def test_mtf_normalized_to_one_at_low_frequency():
    """Test that mtf normalized to one at low frequency."""
    hu = _white_noise(seed=7)
    r = CTCalculator._nps(hu, 1.0, 1.0)
    m = CTCalculator._mtf_from_nps(r["nps_2d"])
    assert m["mtf"] is not None
    # The curve is normalized by the low-frequency band => peak ~1.0.
    assert m["mtf"][0] <= 1.0
    assert max(m["mtf"]) == pytest.approx(1.0, abs=0.05)
    assert all(0.0 <= v <= 1.0 for v in m["mtf"])


def test_mtf_none_when_nps_none():
    """Test that mtf none when nps none."""
    assert CTCalculator._mtf_from_nps(None)["mtf"] is None


# ---------------------------------------------------------------------------
# Dosimetry (CTDIvol / DLP) from metadata
# ---------------------------------------------------------------------------
def test_dosimetry_from_ctdiw_pitch():
    """Test that dosimetry from ctdiw pitch."""
    ds = type("D", (), {})()
    ds.CTDIw = 20.0
    ds.SpiralPitch = 1.5
    d = CTCalculator._dosimetry(ds)
    assert d["ctdivol"] == pytest.approx(20.0 / 1.5, rel=1e-9)
    assert d["source"] == "ctdiw_pitch"


def test_dosimetry_prefers_ctdivol_phantom_tag():
    """Test that dosimetry prefers ctdivol phantom tag."""
    ds = type("D", (), {})()
    ds.CTDIvolPhantomBody = 12.5
    d = CTCalculator._dosimetry(ds)
    assert d["ctdivol"] == pytest.approx(12.5, rel=1e-9)
    assert d["source"] == "CTDIvolPhantomBody"


def test_dosimetry_not_available_for_missing_meta():
    """Test that dosimetry not available for missing meta."""
    assert CTCalculator._dosimetry(None)["ctdivol"] is None


# ---------------------------------------------------------------------------
# Exposure index
# ---------------------------------------------------------------------------
def test_exposure_index_reads_tag():
    """Test that exposure index reads tag."""
    ds = type("D", (), {})()
    ds.ExposureIndex = 320.0
    assert CTCalculator._exposure_index(ds) == pytest.approx(320.0)


def test_exposure_index_none_without_meta():
    """Test that exposure index none without meta."""
    assert CTCalculator._exposure_index(None) is None


# ---------------------------------------------------------------------------
# Low contrast detectability
# ---------------------------------------------------------------------------
def test_low_contrast_two_tissue_phases():
    # Bone (~800 HU) against water (~0 HU) with small noise -> strong CNR.
    """Test that low contrast two tissue phases."""
    rng = np.random.default_rng(8)
    bone = rng.normal(800, 10, (64, 64)).astype(np.float32)
    water = rng.normal(0, 10, (64, 64)).astype(np.float32)
    hu = np.concatenate([bone, water], axis=1)
    r = CTCalculator._low_contrast_detectability(hu)
    assert r["cnr"] > 10.0
    assert r["detectable"] is True


# ---------------------------------------------------------------------------
# Full calculate() return contract
# ---------------------------------------------------------------------------
def test_calculate_returns_all_keys():
    """Test that calculate returns all keys."""
    hu = _white_noise(seed=9)
    out = CTCalculator().calculate(hu)
    expected = {
        "modality", "intensity_units", "hu_statistics", "noise", "uniformity",
        "snr_cnr", "nps", "mtf", "dosimetry", "exposure_index",
        "low_contrast_detectability", "tissue_classification",
        "display_presets", "reference_standards",
    }
    assert set(out.keys()) == expected
    assert out["modality"] == "CT"
    assert out["intensity_units"] == "HU"


def test_calculate_roi_mask():
    """Test that calculate roi mask."""
    hu = _white_noise(seed=10)
    roi = np.zeros_like(hu, dtype=bool)
    roi[10:30, 10:30] = True
    out = CTCalculator().calculate(hu, roi=roi)
    assert abs(out["hu_statistics"]["mean"] - float(np.mean(hu[roi]))) < 1e-3


def test_calculate_roi_shape_mismatch_raises():
    """Test that calculate roi shape mismatch raises."""
    hu = _white_noise(n=32, seed=11)
    with pytest.raises(ValueError):
        CTCalculator().calculate(hu, roi=np.ones((16, 16), dtype=bool))


# ---------------------------------------------------------------------------
# Tissue classification is exhaustive (fractions sum to 1)
# ---------------------------------------------------------------------------
def test_tissue_classification_fractions_sum_to_unity():
    """Test that tissue classification fractions sum to unity."""
    rng = np.random.default_rng(12)
    hu = rng.integers(HU_MIN, HU_MAX, (64, 64)).astype(np.float32)
    t = CTCalculator._tissue_classification(hu)
    total_frac = sum(v["fraction"] for v in t.values())
    assert total_frac == pytest.approx(1.0, abs=1e-6)
    # Every declared tissue range plus the Artifact class is present.
    assert set(TISSUE_RANGES.keys()).issubset(t.keys())
    assert "Artifact" in t
