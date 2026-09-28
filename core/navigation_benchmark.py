"""Small, PHI-free benchmark for cached viewer source/display operations."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Hashable

import numpy as np


@dataclass(frozen=True)
class NavigationBenchmarkResult:
    """Timing and cache counters for a deterministic navigation workload."""

    operations: int
    source_hits: int
    source_misses: int
    display_hits: int
    display_misses: int
    elapsed_seconds: float

    @property
    def hit_rate(self) -> float:
        total = self.source_hits + self.source_misses
        return float(self.source_hits / total) if total else 0.0


def run_navigation_benchmark(
    *,
    image_count: int = 8,
    operations: int = 32,
    cache_size: int = 3,
    source_loader: Callable[[int], np.ndarray] | None = None,
    display_renderer: Callable[[np.ndarray], np.ndarray] | None = None,
) -> NavigationBenchmarkResult:
    """Measure repeated source/display work using synthetic, non-PHI arrays."""
    if image_count < 1 or operations < 1 or cache_size < 1:
        raise ValueError("image_count, operations, and cache_size must be positive")
    source_loader = source_loader or (
        lambda index: np.full((32, 32), index, dtype=np.float32)
    )
    display_renderer = display_renderer or (
        lambda image: np.asarray(image, dtype=np.float32) / 255.0
    )
    source_cache: OrderedDict[Hashable, np.ndarray] = OrderedDict()
    display_cache: OrderedDict[Hashable, np.ndarray] = OrderedDict()
    source_hits = source_misses = display_hits = display_misses = 0
    started = perf_counter()
    for step in range(operations):
        index = step % image_count
        key = (index, "synthetic")
        source = source_cache.get(key)
        if source is None:
            source_misses += 1
            source = source_loader(index)
            source_cache[key] = source
        else:
            source_hits += 1
            source_cache.move_to_end(key)
        while len(source_cache) > cache_size:
            source_cache.popitem(last=False)
        rendered = display_cache.get(key)
        if rendered is None:
            display_misses += 1
            rendered = display_renderer(source)
            display_cache[key] = rendered
        else:
            display_hits += 1
            display_cache.move_to_end(key)
        while len(display_cache) > cache_size:
            display_cache.popitem(last=False)
    return NavigationBenchmarkResult(
        operations=operations,
        source_hits=source_hits,
        source_misses=source_misses,
        display_hits=display_hits,
        display_misses=display_misses,
        elapsed_seconds=perf_counter() - started,
    )


__all__ = ["NavigationBenchmarkResult", "run_navigation_benchmark"]
