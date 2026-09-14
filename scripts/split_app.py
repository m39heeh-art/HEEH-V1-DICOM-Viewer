"""Retired split-app maintenance command.

The runtime is now intentionally canonical in ``app.py``.  The former
generator could recreate stale duplicate implementations, so it is retained
only as a safe, explicit no-op for existing automation.
"""


def main() -> int:
    print(
        "split_app.py is retired: app.py is the canonical runtime and "
        "ui/clinical_app.py is a compatibility wrapper."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
