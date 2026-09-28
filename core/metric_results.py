"""Typed status-aware results for scientific metrics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class MetricStatus(str, Enum):
    """Whether a metric has a scientifically defined value."""

    DEFINED = "defined"
    UNDEFINED = "undefined"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class MetricResult(Generic[T]):
    """A metric value with an explicit status and optional explanation."""

    value: T | None
    status: MetricStatus
    reason: str | None = None

    @property
    def defined(self) -> bool:
        return self.status is MetricStatus.DEFINED

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "status": self.status.value,
            "reason": self.reason,
        }


def defined_metric(value: T) -> MetricResult[T]:
    return MetricResult(value=value, status=MetricStatus.DEFINED)


def undefined_metric(reason: str) -> MetricResult[T]:
    return MetricResult(value=None, status=MetricStatus.UNDEFINED, reason=reason)


def invalid_metric(reason: str) -> MetricResult[T]:
    return MetricResult(value=None, status=MetricStatus.INVALID, reason=reason)


__all__ = [
    "MetricResult",
    "MetricStatus",
    "defined_metric",
    "undefined_metric",
    "invalid_metric",
]
