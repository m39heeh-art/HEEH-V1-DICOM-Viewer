"""ComBat feature harmonization for multi-scanner / multi-site cohorts.

Implements the empirical-Bayes location-and-scale ComBat adjustment of
Johnson, Li & Dasarathy (2007), "Adjusting batch effects in microarray
expression data using empirical Bayes methods" (Biostatistics), following
the neuroCombat / sva formulation used in neuroimaging: per feature, the
data are modeled as batch intercept + preserved covariate effects, the
residuals are standardized by the pooled residual variance, batch location
(gamma) and scale (delta) effects are estimated on the standardized scale,
and the location/scale estimates are shrunk toward their empirical-Bayes
priors so small batches are stabilized rather than over-fitted. Every batch
is then adjusted to a common target:

- pooled mode (default): common location (grand mean) and common scale
  (pooled residual variance) for every batch;
- reference-batch mode: common location (reference-batch mean) and the
  reference batch's scale, so reference-site values pass through unchanged.

Purpose in this toolkit: cohort metric exports pool files acquired across
different scanners, sequences, or sessions ("batches"). ComBat removes the
batch location/scale component while preserving declared biological
covariates, so pooled cohort features are comparable without per-site
manual rescaling.

What this is NOT: it is not a clinical recalibration, not a substitute for
phantom-based site calibration, and not certified for diagnostic use. The
adjustment is disclosed in every export that applies it.

Guarantees and refusals (fail loudly rather than fabricate):
- At least two batches with at least two samples each are required.
- All input values must be finite.
- A feature with (near-)zero residual variance cannot be standardized and
  is skipped with disclosure instead of adjusted.
- Runs are deterministic; identical inputs give identical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["combat_harmonize", "ComBatDiagnostics"]

_VARIANCE_FLOOR = 1e-12
_CONVERGENCE_TOLERANCE = 1e-8
_MAX_ITERATIONS = 200


@dataclass
class ComBatDiagnostics:
    """Per-run diagnostics so every adjustment is auditable and disclosable."""

    feature_names: list[str]
    batch_labels: list[str]
    batch_sizes: dict[str, int]
    gamma_hat: dict[str, np.ndarray]
    gamma_star: dict[str, np.ndarray]
    delta_hat: dict[str, np.ndarray]
    delta_star: dict[str, np.ndarray]
    grand_mean: np.ndarray
    pooled_variance: np.ndarray
    skipped_features: list[str] = field(default_factory=list)
    iterations: int = 0
    converged: bool = False
    mode: str = "pooled"
    reference_batch: str | None = None

    def summary(self) -> str:
        """One-line disclosure for export rows and provenance records."""
        parts = [
            f"empirical-bayes ComBat (Johnson 2007); mode={self.mode}",
            f"batches={len(self.batch_sizes)}",
            "sizes=" + ",".join(
                f"{name}:{size}" for name, size in sorted(self.batch_sizes.items())
            ),
            f"iterations={self.iterations}",
            "converged=" + ("yes" if self.converged else "no"),
        ]
        if self.skipped_features:
            parts.append(
                "skipped_features=" + ",".join(self.skipped_features)
            )
        if self.reference_batch is not None:
            parts.append(f"reference={self.reference_batch}")
        return "; ".join(parts)


def _design_matrix(
    batch: list[str],
    covariates: dict[str, np.ndarray] | None,
) -> np.ndarray:
    """Build [batch dummies | covariate columns]; batch dummies act as the
    implicit intercept (one column per batch, no separate constant term)."""
    batches = sorted(set(batch))
    n = len(batch)
    columns = [
        np.asarray([1.0 if label == b else 0.0 for label in batch])
        for b in batches
    ]
    for name, values in (covariates or {}).items():
        array = np.asarray(values, dtype=float)
        if array.shape != (n,):
            raise ValueError(
                f"covariate '{name}' has shape {array.shape}; expected ({n},)"
            )
        if not np.isfinite(array).all():
            raise ValueError(f"covariate '{name}' contains non-finite values")
        unique = np.unique(array)
        if unique.size <= 2 and set(unique.tolist()) <= {0.0, 1.0}:
            columns.append(array)
        elif np.array_equal(unique, np.arange(unique.size, dtype=float)):
            # Categorical: one-hot against the first (sorted) level.
            for level in unique[1:]:
                columns.append((array == level).astype(float))
        else:
            columns.append(array - array.mean())
    return np.column_stack(columns)


def _aprior(delta_hat: np.ndarray) -> float:
    """Method-of-moments inverse-gamma shape (sva/neuroCombat convention)."""
    mean = float(np.mean(delta_hat))
    var = float(np.var(delta_hat, ddof=1)) if delta_hat.size > 1 else 0.0
    if var <= 0.0:
        return mean
    return (2.0 * var + mean * mean) / var


def _bprior(delta_hat: np.ndarray) -> float:
    """Method-of-moments inverse-gamma scale (sva/neuroCombat convention)."""
    mean = float(np.mean(delta_hat))
    var = float(np.var(delta_hat, ddof=1)) if delta_hat.size > 1 else 0.0
    if var <= 0.0:
        return mean
    return (mean * var + mean**3) / var


def combat_harmonize(
    features,
    batch,
    *,
    covariates: dict[str, np.ndarray] | None = None,
    reference_batch: str | None = None,
    feature_names: list[str] | None = None,
) -> tuple[np.ndarray, ComBatDiagnostics]:
    """Return (adjusted_features, diagnostics).

    Parameters
    ----------
    features:
        ``(n_samples, n_features)`` array of feature values.
    batch:
        Length-``n_samples`` sequence of batch labels (e.g. scanner,
        modality, acquisition session). Every batch must contain >= 2
        samples and at least two distinct batches must be present.
    covariates:
        Optional mapping of preserved (biological) covariates to length-``n``
        arrays. Numeric covariates are centered; binary/categorical ones are
        (one-hot) encoded. Their effects are estimated jointly with the
        batch effects and *preserved* in the adjusted output.
    reference_batch:
        When given, all batches are shifted to the reference batch's mean and
        rescaled to the reference batch's variance (reference-batch mode), so
        the reference site's values pass through (near-)unchanged. Otherwise
        the pooled grand mean and pooled residual variance are the targets.
    feature_names:
        Optional names for diagnostics/disclosure.
    """
    values = np.asarray(features, dtype=float)
    if values.ndim != 2:
        raise ValueError("features must be a 2D array (n_samples, n_features)")
    n_samples, n_features = values.shape
    if n_samples == 0 or n_features == 0:
        raise ValueError("features must contain at least one sample and feature")
    if not np.isfinite(values).all():
        raise ValueError(
            "features contain non-finite values; ComBat refuses to "
            "harmonize undefined measurements"
        )
    labels = [str(label) for label in batch]
    if len(labels) != n_samples:
        raise ValueError(
            f"batch has {len(labels)} labels; expected {n_samples}"
        )
    batch_sizes: dict[str, int] = {}
    for label in labels:
        batch_sizes[label] = batch_sizes.get(label, 0) + 1
    if len(batch_sizes) < 2:
        raise ValueError(
            "ComBat requires at least two batches; a single batch has no "
            "batch effect to remove"
        )
    if any(size < 2 for size in batch_sizes.values()):
        raise ValueError(
            "every batch must contain at least two samples; "
            + ", ".join(
                f"{name}:{size}" for name, size in sorted(batch_sizes.items())
            )
        )
    batches = sorted(batch_sizes)
    if reference_batch is not None and reference_batch not in batch_sizes:
        raise ValueError(
            f"reference batch '{reference_batch}' not present in batch labels"
        )

    names = list(feature_names or [f"f{j}" for j in range(n_features)])
    if len(names) != n_features:
        raise ValueError("feature_names length does not match n_features")

    design = _design_matrix(labels, covariates)
    n_batch_columns = len(batches)

    # Least-squares fit of [batch dummies | covariates] per feature. Because
    # the batch dummies one-hot the batches, the residual is the pooled
    # within-batch, covariate-adjusted deviation.
    coefficients = np.linalg.pinv(design.T @ design) @ design.T @ values
    additive = design @ coefficients
    residual = values - additive

    # Pooled residual variance per feature (the ComBat standardization
    # denominator, sva/neuroCombat ``var_pooled``).
    pooled_variance = np.mean(residual * residual, axis=0)
    constant_feature = pooled_variance < _VARIANCE_FLOOR
    keep = np.flatnonzero(~constant_feature)
    skipped = [names[int(column)] for column in np.flatnonzero(constant_feature)]
    kept_residual = residual[:, keep]
    pooled_variance = pooled_variance[keep]
    kept_coefficients = coefficients[:, keep]
    if keep.size:
        grand_mean_raw = kept_coefficients[:n_batch_columns, :]
    else:
        grand_mean_raw = np.zeros((n_batch_columns, 0))
    if reference_batch is None:
        weights = np.array(
            [batch_sizes[name] / n_samples for name in batches]
        )
        grand_mean = weights @ grand_mean_raw
        mode = "pooled"
        ref_row = -1
    else:
        ref_row = batches.index(reference_batch)
        grand_mean = grand_mean_raw[ref_row, :].copy()
        mode = "reference-batch"

    # Standardize the residuals to unit pooled variance.
    z = kept_residual / np.sqrt(pooled_variance)
    gamma_hat = np.zeros((len(batches), keep.size))
    delta_hat = np.zeros_like(gamma_hat)
    masks = {
        name: np.asarray([label == name for label in labels])
        for name in batches
    }
    for row, name in enumerate(batches):
        gamma_hat[row, :] = np.mean(z[masks[name], :], axis=0)
        delta_hat[row, :] = np.var(z[masks[name], :], axis=0, ddof=1)

    degenerate = np.any(delta_hat < _VARIANCE_FLOOR, axis=0)
    if np.any(degenerate):
        for column in np.flatnonzero(degenerate):
            skipped.append(names[int(keep[column])])
        keep2 = np.flatnonzero(~degenerate)
        z = z[:, keep2]
        gamma_hat = gamma_hat[:, keep2]
        delta_hat = delta_hat[:, keep2]
        pooled_variance = pooled_variance[keep2]
        grand_mean = grand_mean[keep2]
        keep = keep[keep2]

    # Empirical-Bayes shrinkage of the batch location/scale estimates.
    gamma_star = gamma_hat.copy()
    delta_star = delta_hat.copy()
    gamma_bar = np.mean(gamma_hat, axis=0)
    t2 = np.var(gamma_hat, axis=0, ddof=1)
    t2 = np.maximum(t2, _VARIANCE_FLOOR)
    n_per_batch = np.array(
        [batch_sizes[name] for name in batches], dtype=float
    )
    iterations = 0
    converged = False
    for iteration in range(_MAX_ITERATIONS):
        iterations = iteration + 1
        gamma_new = (
            n_per_batch[:, None] * (gamma_star / delta_star)
            + gamma_bar / t2
        ) / (n_per_batch[:, None] / delta_star + 1.0 / t2)
        delta_new = np.empty_like(delta_star)
        for row, name in enumerate(batches):
            block = z[masks[name], :] - gamma_new[row, :]
            a_prior = _aprior(delta_hat[row, :])
            b_prior = _bprior(delta_hat[row, :])
            delta_new[row, :] = (
                a_prior + 0.5 * np.sum(block * block, axis=0)
            ) / (b_prior + n_per_batch[row] / 2.0 - 1.0)
        shift = max(
            float(np.max(np.abs(gamma_new - gamma_star))),
            float(np.max(np.abs(delta_new - delta_star))),
        )
        gamma_star, delta_star = gamma_new, delta_new
        if shift < _CONVERGENCE_TOLERANCE:
            converged = True
            break

    # Adjust every batch to the common location and scale target:
    #   pooled mode    -> target variance = pooled residual variance
    #   reference mode -> target variance = reference batch's variance
    # In standardized units the target variance is 1 (pooled) or
    # delta_star[reference]; multiplying back by sqrt(pooled_variance)
    # returns to data units.
    target_variance_units = (
        np.ones_like(delta_star)
        if reference_batch is None
        else np.broadcast_to(
            delta_star[ref_row, :], delta_star.shape
        ).copy()
    )
    scale_multiplier = np.sqrt(target_variance_units / delta_star)
    # Preserved-covariate contribution (neuroCombat adds X @ beta back into
    # the output so covariate effects survive the adjustment). With no
    # covariates this is an (n, 0) @ (0, k) product and evaluates to zeros.
    # Sliced with the FINAL keep mask so it stays column-aligned with z
    # after both skip passes (constant residual + zero within-batch scale).
    covariate_fit = (
        design[:, n_batch_columns:] @ coefficients[n_batch_columns:, :][:, keep]
    )
    adjusted = np.empty_like(z)
    for row, name in enumerate(batches):
        adjusted[masks[name], :] = (
            (z[masks[name], :] - gamma_star[row, :])
            * scale_multiplier[row, :]
            * np.sqrt(pooled_variance)
            + grand_mean
            + covariate_fit[masks[name], :]
        )

    # Re-insert skipped features unchanged (disclosed, never fabricated).
    if skipped:
        result = np.empty_like(values)
        for source_column, target_column in enumerate(keep):
            result[:, target_column] = adjusted[:, source_column]
        for column in np.flatnonzero(constant_feature):
            result[:, column] = values[:, column]
        adjusted = result

    diagnostics = ComBatDiagnostics(
        feature_names=names,
        batch_labels=labels,
        batch_sizes=batch_sizes,
        gamma_hat={
            name: gamma_hat[row, :] for row, name in enumerate(batches)
        },
        gamma_star={
            name: gamma_star[row, :] for row, name in enumerate(batches)
        },
        delta_hat={
            name: delta_hat[row, :] for row, name in enumerate(batches)
        },
        delta_star={
            name: delta_star[row, :] for row, name in enumerate(batches)
        },
        grand_mean=grand_mean,
        pooled_variance=pooled_variance,
        skipped_features=skipped,
        iterations=iterations,
        converged=converged,
        mode=mode,
        reference_batch=reference_batch,
    )
    return adjusted, diagnostics
