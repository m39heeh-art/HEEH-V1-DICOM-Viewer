"""Ground-truth and refusal tests for the ComBat harmonization engine, and
convention locks for the kurtosis definition (IBSI = excess / Fisher).

ComBat ground truth: features are synthesized with KNOWN batch location and
scale effects plus KNOWN covariate effects, so the adjustment is scored
against analytic expectations instead of eyeballed.
"""

import csv
from pathlib import Path

import numpy as np
import pytest

from core.harmonization import combat_harmonize  # noqa: E402


def _synthetic_cohort(
    n_per_batch: int = 12,
    seed: int = 20260927,
    covariate: np.ndarray | None = None,
    covariate_effect: float = 0.0,
):
    """Two batches with KNOWN effects: +2.0 shift, x2.0 scale for batch B.

    A declared covariate effect is applied AFTER the batch transform so it
    is identical in both batches (a batch-dependent effect would not be a
    single preserved covariate and the ground truth would be ill-defined).
    """
    rng = np.random.default_rng(seed)
    n = 2 * n_per_batch
    values = rng.normal(100.0, 5.0, size=(n, 4))
    values[n_per_batch:, :] = values[n_per_batch:, :] * 2.0 + 2.0
    if covariate is not None:
        values = values + covariate_effect * np.asarray(covariate)[:, None]
    batch = ["A"] * n_per_batch + ["B"] * n_per_batch
    return values, batch


# ---------------------------------------------------------------------------
# Ground truth: known batch effects are removed, covariates are preserved
# ---------------------------------------------------------------------------

def test_known_batch_effects_are_removed_to_a_common_target():
    values, batch = _synthetic_cohort()
    adjusted, diag = combat_harmonize(values, batch, feature_names=[
        "mean", "std", "entropy", "kurtosis",
    ])
    assert diag.converged, diag.summary()
    assert not diag.skipped_features
    # Location: batch means become indistinguishable (both -> grand mean).
    a_mean = adjusted[: len(batch) // 2, 0].mean()
    b_mean = adjusted[len(batch) // 2:, 0].mean()
    assert abs(a_mean - b_mean) < 0.25
    # Scale: batch standard deviations become indistinguishable.
    a_std = adjusted[: len(batch) // 2, 1].std(ddof=1)
    b_std = adjusted[len(batch) // 2:, 1].std(ddof=1)
    assert abs(a_std - b_std) / max(a_std, 1e-9) < 0.25
    # Reference mode: batch A values pass through (near-)unchanged.
    ref_adjusted, ref_diag = combat_harmonize(
        values, batch, reference_batch="A"
    )
    assert ref_diag.mode == "reference-batch"
    before = values[: len(batch) // 2, 0]
    after = ref_adjusted[: len(batch) // 2, 0]
    assert np.abs(after - before).mean() < 1e-6


def test_known_covariate_effects_are_preserved():
    """A covariate with a known effect must survive the adjustment.

    The covariate is deliberately interleaved across batches (present in
    BOTH batches) so its effect is estimable independently of the batch
    dummies; a covariate that perfectly coincides with the batch grouping
    is confounded and mathematically cannot be preserved.
    """
    n_per_batch = 14
    # Interleave: even indices -> group 1, odd indices -> group 0, with
    # both groups present inside each batch block.
    group = np.array(
        [(i % 2 == 1) * 1.0 for i in range(2 * n_per_batch)]
    )
    values, batch = _synthetic_cohort(
        n_per_batch=n_per_batch,
        covariate=group,
        covariate_effect=8.0,
    )
    adjusted, _diag = combat_harmonize(
        values, batch, covariates={"group": group}
    )
    # Ground-truth invariant: the preserved group gap in the output must
    # equal the least-squares estimate of the group coefficient on the same
    # data (ComBat preserves the ESTIMATED covariate effect; its sampling
    # noise is inherent to the data, not introduced by the adjustment).
    design = np.column_stack([
        np.asarray([1.0 if b == "A" else 0.0 for b in batch]),
        np.asarray([1.0 if b == "B" else 0.0 for b in batch]),
        group,
    ])
    beta = float(
        (np.linalg.pinv(design.T @ design) @ design.T @ values[:, 0])[2]
    )
    group0 = adjusted[group == 0.0, 0].mean()
    group1 = adjusted[group == 1.0, 0].mean()
    gap = float(group1 - group0)
    assert gap == pytest.approx(beta, abs=0.5)
    # And the estimate must be in the plausible range around the true 8.0.
    assert abs(gap - 8.0) < 6.0


def test_adjustment_is_deterministic():
    values, batch = _synthetic_cohort()
    first, first_diag = combat_harmonize(values, batch)
    second, second_diag = combat_harmonize(values, batch)
    assert np.array_equal(first, second)
    assert first_diag.summary() == second_diag.summary()


# ---------------------------------------------------------------------------
# Refusals: undefined cases fail loudly instead of fabricating output
# ---------------------------------------------------------------------------

def test_refuses_single_batch():
    values = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
    with pytest.raises(ValueError, match="at least two batches"):
        combat_harmonize(values, ["A"] * 4)


def test_refuses_undersized_batch():
    values = np.random.default_rng(0).normal(size=(5, 3))
    with pytest.raises(ValueError, match="at least two samples"):
        combat_harmonize(
            values, ["A", "A", "A", "A", "B"]
        )


def test_refuses_non_finite_values():
    values = np.array([[1.0, np.nan], [2.0, 3.0], [3.0, 4.0], [4.0, 5.0]])
    with pytest.raises(ValueError, match="non-finite"):
        combat_harmonize(values, ["A", "A", "B", "B"])


def test_refuses_unknown_reference_batch():
    values, batch = _synthetic_cohort()
    with pytest.raises(ValueError, match="not present"):
        combat_harmonize(values, batch, reference_batch="Z")


def test_feature_with_zero_within_batch_variance_is_skipped_and_disclosed():
    """A constant feature cannot be standardized; it must pass through
    unchanged with a disclosure, never silently zeroed or fabricated."""
    values, batch = _synthetic_cohort()
    values[:, 2] = 7.0  # constant feature
    adjusted, diag = combat_harmonize(
        values,
        batch,
        feature_names=["mean", "std", "entropy", "kurtosis"],
    )
    assert diag.skipped_features == ["entropy"]
    assert np.allclose(adjusted[:, 2], 7.0)


def test_diagnostics_summary_discloses_mode_and_sizes():
    values, batch = _synthetic_cohort(n_per_batch=5)
    _adjusted, diag = combat_harmonize(values, batch)
    text = diag.summary()
    assert "mode=pooled" in text
    assert "A:5" in text and "B:5" in text
    assert "converged=yes" in text


# ---------------------------------------------------------------------------
# Kurtosis convention locks: IBSI's reference convention IS excess (Fisher)
# ---------------------------------------------------------------------------

_REFERENCE_CSV = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "ibsi_reference_data"
    / "ibsi_1_reference_values"
    / "ibsi_1_reference_values_config_D.csv"
)


def _reference_kurtosis_rows():
    if not _REFERENCE_CSV.is_file():
        pytest.skip("Optional IBSI reference values are not installed")
    rows = []
    with open(_REFERENCE_CSV, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows.append(str(row.get("feature", "")))
    return rows


def test_ibsi_reference_labels_kurtosis_as_excess():
    """IBSI's own reference values define the compliant convention: the
    digital/CT phantom rows are labelled "(Excess) kurtosis"."""
    labels = _reference_kurtosis_rows()
    excess = [label for label in labels if "kurtosis" in label.lower()]
    assert excess, "no kurtosis rows found in the IBSI reference values"
    assert all("(excess)" in label.lower() for label in excess)


def test_kurtosis_uses_the_excess_fisher_formula_matching_ibsi():
    """scipy.stats.kurtosis(fisher=True) == excess == IBSI convention.

    The application's first-order feature extractor must keep using it:
    the shipped IBSI config-D comparison passes 270/270 against reference
    values labelled "(Excess) kurtosis" (see test_ibsi_validation.py).
    """
    from scipy import stats

    from core.tissue_classifier import RadiomicsExtractor

    rng = np.random.default_rng(7)
    sample = rng.normal(0.0, 1.0, size=20000)
    report = RadiomicsExtractor.full_report(sample)
    measured = report["histogram"]["kurtosis"]
    # The extractor's kurtosis must equal scipy's Fisher/excess kurtosis.
    assert measured == pytest.approx(
        float(stats.kurtosis(sample, fisher=True)), abs=5e-4
    )
    # And must NOT equal the non-Fisher (moment) formula.
    assert measured != pytest.approx(
        float(stats.kurtosis(sample, fisher=False)), abs=5e-4
    )
    # Fisher kurtosis is exactly moment kurtosis minus 3.
    assert float(stats.kurtosis(sample, fisher=True)) == pytest.approx(
        float(stats.kurtosis(sample, fisher=False)) - 3.0, abs=1e-9
    )


def test_disclosure_text_declares_the_excess_convention():
    """The UI/report disclosure must state the convention explicitly."""
    import app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "Fisher" in source
    assert "excess" in source.lower()
