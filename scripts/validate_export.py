"""Validate a HEEH-V1 export archive without modifying it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.export_validation import validate_export_archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        result = validate_export_archive(args.archive.read_bytes())
    except OSError as exc:
        print(json.dumps({
            "ok": False,
            "errors": [{"code": "READ_ERROR", "message": str(exc)}],
            "warnings": [],
        }, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
