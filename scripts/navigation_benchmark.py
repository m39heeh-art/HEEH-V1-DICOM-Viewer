"""Run the PHI-free cached navigation benchmark from a terminal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.navigation_benchmark import run_navigation_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=int, default=8)
    parser.add_argument("--operations", type=int, default=128)
    parser.add_argument("--cache-size", type=int, default=3)
    args = parser.parse_args()
    result = run_navigation_benchmark(
        image_count=args.images,
        operations=args.operations,
        cache_size=args.cache_size,
    )
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
