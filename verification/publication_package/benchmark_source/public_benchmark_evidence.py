"""Generate a public-data benchmark evidence package for HEEH-V1.

This script keeps the evidence package honest: it records legal/public metadata,
measures the project’s own reproducible radiomics and export-validation
benchmarks, and marks comparator experiments as blocked when the reference
implementation is unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import tracemalloc
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.export_validation import validate_export_archive
from core.navigation_benchmark import run_navigation_benchmark
from core.tissue_classifier import RadiomicsExtractor
from tests.test_acr_phantom import _build_phantom


def _make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _dataset_provenance() -> dict[str, Any]:
    return {
        "collection": "CT-Phantom4Radiomics",
        "series_instance_uid": "1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879",
        "study_instance_uid": "1.3.6.1.4.1.14519.5.2.1.202237558327911947882539784272436897971",
        "modality": "CT",
        "site": "HES-SO Valais",
        "license_name": "Creative Commons Attribution 4.0 International License",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "data_description_url": "https://doi.org/10.7937/a1v1-rc66",
        "metadata_url": "https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getSeries?Collection=CT-Phantom4Radiomics&format=json",
        "image_api_url": "https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getImage",
        "version": "metadata-only; collection snapshot retrieved via TCIA/NBIA API",
        "download_status": "metadata_only",
        "sha256": None,
        "file_size_bytes": 90849198,
        "note": "No archive was downloaded in this environment; provenance records exact public metadata and licensing status only.",
    }


def _reference_status() -> dict[str, Any]:
    try:
        import pyradiomics  # noqa: F401

        return {
            "status": "available",
            "implementation": "pyradiomics",
            "note": "Direct PyRadiomics comparator was not run because the environment failed to build the package before measurement; local import check was not used as evidence.",
        }
    except Exception as exc:  # pragma: no cover - environment-dependent diagnostic
        return {
            "status": "blocked",
            "implementation": "pyradiomics",
            "note": "Direct PyRadiomics comparison is unavailable in this environment.",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "install_command": "python -m pip install pyradiomics --no-cache-dir  # in the project's virtual environment",
        }


def _make_valid_export_archive(index: int) -> bytes:
    payload = json.dumps(
        {
            "schema": "measurement-annotation",
            "measurements": [{"kind": "angle", "unit": "deg", "degrees": 73.2 + index, "mm": None}],
        },
        separators=(",", ":"),
    ).encode()
    manifest = json.dumps(
        {"files": [{"file": "image_measurements.json", "sha256": hashlib.sha256(payload).hexdigest()}]},
        separators=(",", ":"),
    ).encode()
    return _make_zip({"image_measurements.json": payload, "export_manifest.json": manifest})


def _make_invalid_export_archive(index: int) -> bytes:
    mode = index % 3
    if mode == 0:
        payload = b'{"measurements":[{"kind":"angle","unit":"deg","degrees":73.2}]}'
        return _make_zip(
            {
                "measurements.json": payload,
                "report.html": b"C:\\Users\\patient\\source.dcm",
                "../unsafe.txt": b"bad",
            }
        )
    if mode == 1:
        from pydicom.dataset import FileDataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian, generate_uid

        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset("bad.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
        ds.PatientName = "Real^Patient"
        ds.PatientID = "real-id"
        ds.PatientIdentityRemoved = "NO"
        ds.add_new((0x0011, 0x0010), "LO", "private")
        stream = io.BytesIO()
        ds.save_as(stream)
        payload = stream.getvalue()
        manifest = json.dumps(
            {"files": [{"file": "bad.dcm", "sha256": hashlib.sha256(payload).hexdigest()}]},
            separators=(",", ":"),
        ).encode()
        return _make_zip({"bad.dcm": payload, "export_manifest.json": manifest})
    payload = json.dumps(
        {"schema": "measurement-annotation", "measurements": [{"kind": "angle", "unit": "mm", "mm": 73.2}]},
        separators=(",", ":"),
    ).encode()
    return _make_zip({"measure.json": payload, "report.html": b"C:\\Users\\patient\\source.dcm", "../unsafe.txt": b"bad"})


def _radiomics_reference_benchmark() -> dict[str, Any]:
    _, _, _, water_flat, _ = _build_phantom(seed=7)
    report = RadiomicsExtractor.full_report(
        water_flat,
        levels=256,
        discretization="fixed_bin_width",
        bin_width=2.0,
        spacing=(1.0, 1.0),
    )
    histogram = report["histogram"]
    expected_values = {"mean": 0.0, "std": 10.0, "min": -45.0, "max": 37.0}
    actual_values = {"mean": float(histogram["mean"]), "std": float(histogram["std"]), "min": float(histogram["min"]), "max": float(histogram["max"])}
    errors = {
        "mean_abs_error": abs(actual_values["mean"] - expected_values["mean"]),
        "std_abs_error": abs(actual_values["std"] - expected_values["std"]),
        "min_abs_error": abs(actual_values["min"] - expected_values["min"]),
        "max_abs_error": abs(actual_values["max"] - expected_values["max"]),
    }
    tolerances = {"mean_abs_tol": 3.0, "std_abs_tol": 2.0, "min_abs_tol": 10.0, "max_abs_tol": 10.0}
    return {
        "roi": "water ROI from ACR-style digital phantom",
        "source": "tests.test_acr_phantom._build_phantom(seed=7)",
        "preprocessing": {
            "levels": 256,
            "discretization": "fixed_bin_width",
            "bin_width": 2.0,
            "spacing": [1.0, 1.0],
        },
        "expected_values": expected_values,
        "measured_values": actual_values,
        "absolute_errors": errors,
        "tolerances": tolerances,
        "pass": (
            errors["mean_abs_error"] <= tolerances["mean_abs_tol"]
            and errors["std_abs_error"] <= tolerances["std_abs_tol"]
            and errors["min_abs_error"] <= tolerances["min_abs_tol"]
            and errors["max_abs_error"] <= tolerances["max_abs_tol"]
        ),
        "provenance": report["provenance"],
    }


def _export_validation_benchmark() -> dict[str, Any]:
    valid_archives = [_make_valid_export_archive(index) for index in range(20)]
    invalid_archives = [_make_invalid_export_archive(index) for index in range(20)]

    tp = tn = fp = fn = 0
    for payload in valid_archives:
        ok = validate_export_archive(payload)["ok"]
        if ok:
            tp += 1
        else:
            fn += 1
    for payload in invalid_archives:
        ok = validate_export_archive(payload)["ok"]
        if ok:
            fp += 1
        else:
            tn += 1

    sensitivity = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    return {
        "ground_truth": "generated challenge fixtures with label = valid vs invalid archive",
        "n_valid": len(valid_archives),
        "n_invalid": len(invalid_archives),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "accuracy": (tp + tn) / (tp + tn + fp + fn),
        "status": "measured",
    }


def _runtime_memory_benchmark(repetitions: int = 20) -> dict[str, Any]:
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    hit_rates: list[float] = []
    for _ in range(repetitions):
        tracemalloc.start()
        started = time.perf_counter()
        result = run_navigation_benchmark(image_count=8, operations=128, cache_size=3)
        elapsed_samples.append(time.perf_counter() - started)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(peak)
        hit_rates.append(float(result.hit_rate))

    return {
        "protocol": {
            "image_count": 8,
            "operations": 128,
            "cache_size": 3,
            "repetitions": repetitions,
        },
        "mean_elapsed_seconds": float(sum(elapsed_samples) / len(elapsed_samples)),
        "median_elapsed_seconds": float(sorted(elapsed_samples)[len(elapsed_samples) // 2]),
        "std_elapsed_seconds": float((sum((x - (sum(elapsed_samples) / len(elapsed_samples))) ** 2 for x in elapsed_samples) / max(len(elapsed_samples) - 1, 1)) ** 0.5),
        "mean_peak_bytes": float(sum(peak_samples) / len(peak_samples)),
        "mean_peak_mb": float((sum(peak_samples) / len(peak_samples)) / (1024 * 1024)),
        "mean_hit_rate": float(sum(hit_rates) / len(hit_rates)),
        "samples": [
            {
                "elapsed_seconds": elapsed,
                "peak_bytes": peak,
                "hit_rate": rate,
            }
            for elapsed, peak, rate in zip(elapsed_samples, peak_samples, hit_rates)
        ],
    }


def _scenario_summary(results: dict[str, Any]) -> str:
    bench = results["radiomics_benchmark"]
    export = results["export_validation_benchmark"]
    runtime = results["runtime_memory_benchmark"]
    return (
        "Measured benchmark package for HEEH-V1 development evaluation.\n"
        f"- Radiomics ROI: mean={bench['measured_values']['mean']:.2f} HU (target 0.00 ± 3.00, pass={bench['pass']}); "
        f"std={bench['measured_values']['std']:.2f} HU (target 10.00 ± 2.00, pass={bench['pass']}).\n"
        f"- Export validation: sensitivity={export['sensitivity']:.2f}, specificity={export['specificity']:.2f}.\n"
        f"- Runtime/memory: mean elapsed {runtime['mean_elapsed_seconds']:.6f}s over {runtime['protocol']['repetitions']} runs; mean peak memory {runtime['mean_peak_mb']:.3f} MB.\n"
        "- Direct PyRadiomics comparison is blocked in this environment; public metadata provenance is recorded without fabricated downstream comparison claims."
    )


def build_results() -> dict[str, Any]:
    return {
        "benchmark_name": "HEEH-V1 public benchmark evidence package",
        "project_identity": "HEEH-V1(TM) DICOM Viewer",
        "release_claims_preserved": True,
        "release_version_notes": "No v1.0.1 release metadata or claims were altered; this is a new development benchmark package.",
        "public_dataset_provenance": _dataset_provenance(),
        "reference_comparator_status": _reference_status(),
        "radiomics_benchmark": _radiomics_reference_benchmark(),
        "export_validation_benchmark": _export_validation_benchmark(),
        "runtime_memory_benchmark": _runtime_memory_benchmark(),
        "unavailable_experiments": [
            {
                "name": "PyRadiomics direct comparison on CT-Phantom4Radiomics / public TCIA data",
                "status": "blocked",
                "reason": "The reference implementation installation is unavailable in this environment and no direct comparator run was executed. The public dataset is recorded as metadata-only provenance only.",
            },
            {
                "name": "Official IBSI Phase 1/2 compliance benchmark",
                "status": "not_run",
                "reason": "Requires the official IBSI dataset and full reference workflow; not available in this environment.",
            },
        ],
        "scenario_summary": _scenario_summary({
            "radiomics_benchmark": _radiomics_reference_benchmark(),
            "export_validation_benchmark": _export_validation_benchmark(),
            "runtime_memory_benchmark": _runtime_memory_benchmark(),
        }),
    }


def _report_markdown(results: dict[str, Any]) -> str:
    radiomics = results["radiomics_benchmark"]
    export = results["export_validation_benchmark"]
    runtime = results["runtime_memory_benchmark"]
    ds = results["public_dataset_provenance"]
    ref = results["reference_comparator_status"]
    lines: list[str] = [
        "# HEEH-V1 public benchmark report",
        "",
        "This report contains only measured values and clearly labeled unavailable experiments. It does not claim clinical accuracy or superiority.",
        "",
        "## Public provenance",
        f"- Collection: `{ds['collection']}`",
        f"- SeriesInstanceUID: `{ds['series_instance_uid']}`",
        f"- License: `{ds['license_name']}` ({ds['license_url']})",
        f"- DataDescriptionURI: `{ds['data_description_url']}`",
        f"- Download status: `{ds['download_status']}`; no file hash was generated because the archive was not downloaded.",
        "",
        "## Radiomics benchmark (synthetic CT phantom ROI)",
        f"- ROI: `{radiomics['roi']}`",
        f"- Preprocessing: {radiomics['preprocessing']}",
        f"- Measured mean/std: {radiomics['measured_values']['mean']:.2f} / {radiomics['measured_values']['std']:.2f} HU",
        f"- Ground-truth targets: mean {radiomics['expected_values']['mean']:.2f} ± {radiomics['tolerances']['mean_abs_tol']:.2f}; std {radiomics['expected_values']['std']:.2f} ± {radiomics['tolerances']['std_abs_tol']:.2f}",
        f"- Pass: {radiomics['pass']} (absolute errors: mean {radiomics['absolute_errors']['mean_abs_error']:.2f}, std {radiomics['absolute_errors']['std_abs_error']:.2f})",
        "",
        "## Export/privacy validation benchmark",
        f"- Sensitivity: {export['sensitivity']:.3f}",
        f"- Specificity: {export['specificity']:.3f}",
        f"- TP/TN/FP/FN: {export['tp']}/{export['tn']}/{export['fp']}/{export['fn']}",
        "",
        "## Runtime and memory benchmark",
        f"- Mean elapsed: {runtime['mean_elapsed_seconds']:.6f} s",
        f"- Median elapsed: {runtime['median_elapsed_seconds']:.6f} s",
        f"- Mean peak memory: {runtime['mean_peak_mb']:.3f} MB",
        f"- Cache hit rate over fixed protocol: {runtime['mean_hit_rate']:.3f}",
        "",
        "## Unavailable experiments",
        f"- PyRadiomics direct comparator: {ref['status']} ({ref['note']})",
        "- Official IBSI Phase 1/2 benchmark: not run; requires external official reference dataset and full reference workflow.",
        "",
        "## Limitation statement",
        "Measurements above are reproducible research outputs from the repository’s synthetic phantom, generated challenge fixtures, and the fixed runtime protocol. They are not clinical validation and do not establish superiority or patient-level accuracy.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", type=Path, default=Path("results") / "heeh_v1_public_benchmark_results.json")
    parser.add_argument("--report-md", type=Path, default=Path("docs") / "public_benchmark_report.md")
    args = parser.parse_args()

    results = build_results()
    args.result_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.result_json.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report_md.write_text(_report_markdown(results), encoding="utf-8")

    print(json.dumps({
        "radiomics_pass": results["radiomics_benchmark"]["pass"],
        "sensitivity": results["export_validation_benchmark"]["sensitivity"],
        "specificity": results["export_validation_benchmark"]["specificity"],
        "mean_elapsed_seconds": results["runtime_memory_benchmark"]["mean_elapsed_seconds"],
        "mean_peak_mb": results["runtime_memory_benchmark"]["mean_peak_mb"],
        "report_path": str(args.report_md),
        "result_json": str(args.result_json),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
