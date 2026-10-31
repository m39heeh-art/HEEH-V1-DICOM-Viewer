"""Build the local ibsi_reference_data layout from official IBSI sources.

Downloads (once) the official IBSI-1 reference-values workbook and converts
its per-configuration sheets and digital-phantom sheet into the CSV tables expected by
``verification/tests/test_ibsi_validation.py`` and
``scripts/ibsi_reference_verification.py``. Phantom NIfTI data must already
exist under ``verification/data/ibsi_validation/`` (see
``verification/README_DATA.md``).

The workbook is published by the IBSI consortium (CC BY 4.0) at
https://ibsi.radiomics.hevs.ch/assets/IBSI-1-submission-table.xlsx
and contains one sheet per processing configuration with the exact columns
the comparison code reads: ``family``, ``feature``, ``reference value``,
``tolerance`` and ``tag``.

Rows without a published reference value are excluded because comparison
consumers treat an empty ``reference value`` as "not assessed". The reference
row count is 270 for Configuration D and 482 for the digital phantom.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REF_ROOT = REPO_ROOT / "verification" / "data" / "ibsi_reference_data"
CLONE_ROOT = REPO_ROOT / "verification" / "data" / "ibsi_validation"
WORKBOOK_URL = "https://ibsi.radiomics.hevs.ch/assets/IBSI-1-submission-table.xlsx"
WORKBOOK_URL_FALLBACK = "https://raw.githubusercontent.com/theibsi/ibsi1_submissions/master/IBSI-1-submission-table.xlsx?download=1"
XLSX_PATH = REPO_ROOT / "cache_logs" / "ibsi_ref" / "IBSI-1-submission-table.xlsx"

CONFIGS = {
    "config A": "A",
    "config B": "B",
    "config C": "C",
    "config D": "D",
    "config E": "E",
}
DIGITAL_PHANTOM_SHEET = "digital phantom"
DIGITAL_PHANTOM_REFERENCE_FILE = "ibsi_1_digital_phantom_reference_values.csv"


def _ensure_workbook() -> Path:
    if XLSX_PATH.is_file() and XLSX_PATH.stat().st_size > 100_000:
        return XLSX_PATH
    XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    for url in (WORKBOOK_URL, WORKBOOK_URL_FALLBACK):
        try:
            urllib.request.urlretrieve(url, XLSX_PATH)
            if XLSX_PATH.stat().st_size > 100_000:
                return XLSX_PATH
        except Exception as exc:  # noqa: BLE001 - report and try next source
            print(f"download failed from {url}: {exc}", file=sys.stderr)
    raise SystemExit(
        "Could not download the IBSI-1 reference-values workbook; place it at "
        f"{XLSX_PATH} (CC BY 4.0, https://theibsi.github.io/ibsi1/)"
    )


def _sheet_to_csv(
    sheet: str,
    csv_path: Path,
    *,
    include_unreferenced: bool = False,
) -> tuple[int, int]:
    import openpyxl

    workbook = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    rows = list(workbook[sheet].iter_rows(values_only=True))
    header = [str(column) for column in rows[0]]
    column_index = {name: position for position, name in enumerate(header)}
    written = 0
    skipped = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["family", "feature", "consensus", "reference value", "tolerance", "tag"])
        for row in rows[1:]:
            family = row[column_index["family"]]
            tag = row[column_index["tag"]]
            if not tag:
                continue
            value = row[column_index["reference value"]]
            tolerance = row[column_index["tolerance"]]
            consensus = row[column_index["consensus"]] or ""
            has_reference = value is not None and not (
                isinstance(value, str) and not value.strip()
            )
            if not has_reference and not include_unreferenced:
                skipped += 1
                continue
            writer.writerow(
                [
                    str(family),
                    str(row[column_index["feature"]]),
                    str(consensus),
                    ("%.12g" % float(value)) if has_reference else "",
                    ("%.12g" % float(tolerance)) if tolerance is not None else "0",
                    str(tag),
                ]
            )
            written += 1
    return written, skipped


def _clone_phantoms() -> None:
    if not (CLONE_ROOT / ".git").exists():
        raise SystemExit(
            "verification/data/ibsi_validation is not a git checkout; see "
            "verification/README_DATA.md step 1 (pin 6da96021)."
        )
    revision = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=CLONE_ROOT,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
    )
    if revision != "6da96021bc91faf4c0cb7fd7fa56a4225d2064a8":
        raise SystemExit(f"Unexpected ibsi_validation revision: {revision}")
    for phantom in (
        "ibsi_1_ct_radiomics_phantom",
        "ibsi_1_digital_phantom",
    ):
        target = REF_ROOT / phantom
        nifti_target = target / "nifti"
        (nifti_target / "image").mkdir(parents=True, exist_ok=True)
        (nifti_target / "mask").mkdir(parents=True, exist_ok=True)
        for kind in ("image", "mask"):
            source = CLONE_ROOT / phantom / "nifti" / kind / "phantom.nii.gz" if kind == "image" else CLONE_ROOT / phantom / "nifti" / kind / "mask.nii.gz"
            if not source.exists():
                subprocess.run(
                    ["git", "checkout", "-f", "HEAD", "--", phantom],
                    cwd=CLONE_ROOT,
                    check=True,
                    capture_output=True,
                )
            shutil.copy2(source, nifti_target / kind / source.name)
        for metadata in ("LICENSE.md", "README.md"):
            shutil.copy2(CLONE_ROOT / phantom / metadata, target / metadata)


def main() -> int:
    _ensure_workbook()
    REF_ROOT.mkdir(parents=True, exist_ok=True)
    _clone_phantoms()
    reference_dir = REF_ROOT / "ibsi_1_reference_values"
    reference_dir.mkdir(parents=True, exist_ok=True)
    for sheet, letter in CONFIGS.items():
        name = f"ibsi_1_reference_values_config_{letter}.csv"
        written, skipped = _sheet_to_csv(sheet, reference_dir / name)
        print(f"{name}: {written} reference rows ({skipped} rows without values skipped)")
    written, skipped = _sheet_to_csv(
        DIGITAL_PHANTOM_SHEET,
        reference_dir / DIGITAL_PHANTOM_REFERENCE_FILE,
        include_unreferenced=True,
    )
    print(
        f"{DIGITAL_PHANTOM_REFERENCE_FILE}: {written} reference rows "
        f"({skipped} rows without values skipped)"
    )
    (reference_dir / "SOURCE.md").write_text(
        "# Source of these reference tables\n\n"
        "Generated from the official IBSI-1 reference-values workbook "
        "(CC BY 4.0): https://ibsi.radiomics.hevs.ch/assets/IBSI-1-submission-table.xlsx\n"
        f"Saved locally at {XLSX_PATH.relative_to(REPO_ROOT)}; regenerate with "
        "`python scripts/build_ibsi_reference_tables.py`.\n"
        "Phantom NIfTI data come from github.com/theibsi/data_sets at pinned "
        "revision 6da96021bc91faf4c0cb7fd7fa56a4225d2064a8 (see LICENSE.md in each phantom folder).\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
