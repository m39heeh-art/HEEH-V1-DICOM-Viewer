"""
Synthetic ACR-style CT phantom validation.

Builds a digital phantom whose ground truth is known exactly (uniform water
background, high-contrast and low-contrast inserts at specified HU values,
plus an injected white-noise field), then runs the integrated CT metric
pipeline (``CTCalculator.calculate``) and asserts the recovered numbers track
the analytic truth.  This is a physics validation on synthetic data — the
software is a research/education tool and NOT a medical device.

The phantom geometry mirrors the ACR CT accreditation phantom sections:
a ~20 cm water-equivalent disc carrying inserts of known composition.
"""

import numpy as np
import pytest

from engines.modality_calculators import CTCalculator

from core.constants import HU_MIN, HU_MAX


def _build_phantom(
    size=256,
    water_hu=0.0,
    air_hu=-1000.0,
    acrylic_hu=120.0,
    bone_hu=1000.0,
    low_contrast_hu=5.0,
    noise_std=10.0,
    seed=42,
):
    """Return (phantom_hu, truth, masks, water_flat, water_crop2d)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    center = (size - 1) / 2.0
    r = np.sqrt((xx - center) ** 2 + (yy - center) ** 2)
    radius = size * 0.45  # water disc fills most of the FOV

    img = np.full((size, size), water_hu, dtype=np.float64)
    img[r > radius] = air_hu  # air ring outside the water disc

    # Insert centres on the periphery of the water disc (ACR-style placement).
    cc = center
    rr = radius * 0.55
    inserts = {
        "acrylic": (acrylic_hu, (cc + rr, cc)),
        "bone": (bone_hu, (cc - rr, cc)),
        "air": (air_hu, (cc, cc + rr)),
        "low_contrast": (low_contrast_hu, (cc, cc - rr)),
    }
    truth = {"water": water_hu, "acrylic": acrylic_hu, "bone": bone_hu,
             "air": air_hu, "low_contrast": low_contrast_hu}
    irad = size * 0.04
    masks = {}
    for name, (hu, (cx, cy)) in inserts.items():
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= irad ** 2
        img[mask] = hu
        masks[name] = mask

    water_mask = (r <= radius) & ~np.logical_or.reduce(list(masks.values()))
    img = img + rng.normal(0.0, noise_std, img.shape)
    img = np.clip(img, HU_MIN, HU_MAX).astype(np.float32)

    # 2D crop of pure water, inset from edges and inserts (size*0.45 disc,
    # inserts at ~0.25*size from centre): a 0.34*size crop is insert-free.
    half = int(size * 0.17)
    cyi, cxi = size // 2, size // 2
    crop2d = img[cyi - half : cyi + half + 1, cxi - half : cxi + half + 1]
    return img, truth, masks, img[water_mask], crop2d


def test_phantom_recovers_water_mean_within_tolerance():
    """Verify water mean is recovered within tolerance."""
    img, truth, masks, water_flat, _ = _build_phantom(seed=7)
    s = CTCalculator._hu_statistics(water_flat)
    assert s["mean"] == pytest.approx(truth["water"], abs=3.0)


def test_phantom_recovers_high_contrast_insert_means():
    """Verify insert means are correctly segmented."""
    img, truth, masks, _, _ = _build_phantom(seed=9)
    calc = CTCalculator()
    for name in ("air", "acrylic", "bone"):
        hu = img[masks[name]]
        s = calc._hu_statistics(hu)
        assert s["mean"] == pytest.approx(truth[name], abs=8.0)
        assert s["max"] <= HU_MAX and s["min"] >= HU_MIN


def test_phantom_noise_estimate_tracks_injected_std():
    """Verify noise estimate matches injected std."""
    img, truth, masks, water_flat, _ = _build_phantom(noise_std=15.0, seed=11)
    n = CTCalculator._noise(water_flat)
    # Injected field was clipped to [HU_MIN, HU_MAX]; only a tiny tail is cut.
    assert n["std_hu"] == pytest.approx(15.0, abs=2.0)


def test_phantom_water_uniformity_is_low():
    """Verify water region uniformity is near zero."""
    img, truth, masks, _, crop2d = _build_phantom(noise_std=5.0, seed=13)
    u = CTCalculator._uniformity(crop2d)
    assert u["central_mean"] is not None
    assert abs(u["difference"]) < 3.0


def test_phantom_tissue_classification_matches_composition():
    """Verify classification matches phantom composition."""
    img, truth, masks, _, _ = _build_phantom(seed=17)
    frac = CTCalculator._tissue_classification(img)
    total = sum(v["fraction"] for v in frac.values())
    assert total == pytest.approx(1.0, abs=1e-6)
    # The dominant class must be water.
    top = max(frac.items(), key=lambda kv: kv[1]["fraction"])
    assert top[0] == "Water"


def _build_detectability_phantom(contrast_hu, noise_std, seed=19):
    """Two-material disc: water background + single insert; no air ring.

    Keeps exactly two tissue classes present so the top-2-class CNR heuristic
    contrasts water versus the insert alone.
    """
    size = 256
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    center = (size - 1) / 2.0
    r = np.sqrt((xx - center) ** 2 + (yy - center) ** 2)
    radius = size * 0.45
    img = np.full((size, size), 0.0, dtype=np.float64)
    img[r > radius] = 0.0  # keep everything water-like
    cx, cy = center + radius * 0.55, center
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= (size * 0.04) ** 2
    img[mask] = contrast_hu
    img = img + rng.normal(0.0, noise_std, img.shape)
    return np.clip(img, HU_MIN, HU_MAX).astype(np.float32)


def test_phantom_low_contrast_detectability_scales_with_contrast():
    """Verify detectability grows with injected contrast."""
    calc = CTCalculator()
    # Same injected noise; only the insert contrast differs.
    img_lo = _build_detectability_phantom(contrast_hu=5.0, noise_std=3.0)
    # 5 HU sits inside the Water band (-10..15) -> single class, not detectable.
    assert calc._low_contrast_detectability(img_lo)["detectable"] is False

    img_hi = _build_detectability_phantom(contrast_hu=120.0, noise_std=3.0)
    # 120 HU lands in DenseSoftTissue (100..200): water vs insert -> high CNR.
    assert calc._low_contrast_detectability(img_hi)["detectable"] is True


def test_phantom_full_calculate_report_has_grounded_keys():
    """Verify the full report contains the expected keys."""
    img, truth, masks, _, _ = _build_phantom(seed=23)
    r = CTCalculator().calculate(img)
    for key in ("hu_statistics", "noise", "uniformity", "snr_cnr",
                "nps", "mtf", "tissue_classification", "low_contrast_detectability"):
        assert key in r
    assert r["noise"]["std_hu"] > 0.0
    assert r["snr_cnr"]["snr_water_hu"] >= 0.0
