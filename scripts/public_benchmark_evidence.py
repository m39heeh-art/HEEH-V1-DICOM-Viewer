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
import platform
import subprocess
import sys
import time
import tracemalloc
import tomllib
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.export_validation import validate_export_archive
from core.navigation_benchmark import run_navigation_benchmark
from core.tissue_classifier import RadiomicsExtractor
from verification.tests.test_acr_phantom import _build_phantom


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
        "note": (
            "This synthetic/fixture benchmark records collection metadata only; "
            "it does not analyze collection-level image data. "
            "A separate study downloaded and evaluated one 172-slice series; "
            "the remainder of the collection was not evaluated."
        ),
    }


def _source_revision(root: Path) -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unavailable; Git revision metadata could not be read"
    tree_state = "modified working tree" if status else "clean working tree"
    return f"{commit} ({tree_state}; verify exact files with SHA256SUMS.txt)"


def _recorded_comparison_evidence(root: Path) -> dict[str, Any]:
    path = root / "verification" / "results" / "pyradiomics_comparison.json"
    if not path.is_file():
        return {
            "status": "not_recorded",
            "note": "No PyRadiomics comparison result is recorded in this checkout.",
        }
    result = json.loads(path.read_text(encoding="utf-8"))
    return {
        "status": result["status"],
        "artifact": path.relative_to(root).as_posix(),
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dataset": result["dataset"],
        "version": result["pyradiomics"]["version"],
        "roi_shape": result["roi_shape"],
        "roi_sha256": result["roi_sha256"],
        "absolute_errors": result["absolute_errors"],
        "tolerance": result["tolerance"],
        "all_within_tolerance": result["all_within_tolerance"],
        "execution_environment": result.get("execution_environment"),
        "scope": "Matched first-order comparison on a synthetic ROI only.",
    }


def _recorded_ibsi_evidence(root: Path) -> dict[str, Any]:
    path = root / "verification" / "results" / "ibsi_configuration_d_verification.json"
    if not path.is_file():
        return {
            "status": "not_recorded",
            "note": "No successful Configuration D verification result is recorded.",
        }
    result = json.loads(path.read_text(encoding="utf-8"))
    summary = result["verification_summary"]
    return {
        "status": result["status"],
        "artifact": path.relative_to(root).as_posix(),
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": result["scope"],
        "reference_source": result["source"],
        "zrad_comparison": summary["zrad_comparison"],
        "application_alignment": summary["application_alignment"],
        "application_configuration_d_workflow": summary[
            "application_configuration_d_workflow"
        ],
        "pyradiomics_reference_comparison": summary["comparison"],
        "statistics_comparison": summary["statistics_comparison"],
        "full_ibsi_status": summary["full_ibsi_status"],
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
        "source": "verification.tests.test_acr_phantom._build_phantom(seed=7)",
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
        "ground_truth": "generated challenge fixtures labeled valid vs invalid archive",
        "estimate_scope": "Constructed fixtures only; not a real-world performance estimate.",
        "n_valid": len(valid_archives),
        "n_invalid": len(invalid_archives),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "accuracy": (tp + tn) / (tp + tn + fp + fn),
        "status": "generated_fixture_check",
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
        "measurement_scope": (
            "Synthetic navigation-cache workload only. Peak memory is Python "
            "allocation memory measured by tracemalloc; it excludes native "
            "library allocations, process RSS, image decoding, model inference, "
            "and end-to-end application workloads."
        ),
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
    comparator = results["external_radiomics_comparison"]
    return (
        "Measured benchmark package for HEEH-V1 development evaluation.\n"
        f"- Radiomics ROI: mean={bench['measured_values']['mean']:.2f} HU (target 0.00 ± 3.00, pass={bench['pass']}); "
        f"std={bench['measured_values']['std']:.2f} HU (target 10.00 ± 2.00, pass={bench['pass']}).\n"
        f"- Generated export fixtures: {export['tp']} valid and {export['tn']} invalid cases classified correctly.\n"
        f"- Runtime/memory: mean elapsed {runtime['mean_elapsed_seconds']:.6f}s over {runtime['protocol']['repetitions']} runs; mean peak memory {runtime['mean_peak_mb']:.3f} MB.\n"
        f"- PyRadiomics synthetic comparator: status={comparator['status']}, "
        f"all within tolerance={comparator.get('all_within_tolerance', False)}."
    )


def build_results() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    radiomics = _radiomics_reference_benchmark()
    export = _export_validation_benchmark()
    runtime = _runtime_memory_benchmark()
    comparator = _recorded_comparison_evidence(root)
    ibsi = _recorded_ibsi_evidence(root)
    return {
        "benchmark_name": "HEEH-V1 public benchmark evidence package",
        "project_identity": "HEEH-V1(TM) DICOM Viewer",
        "release_claims_preserved": True,
        "release_version_notes": (
            "The requested 1.0.2 version label is retained. This revised "
            "package includes post-tag fixes and evidence updates and is not "
            "byte-identical to the original tagged snapshot."
        ),
        "benchmark_environment": {
            "project_version": project["project"]["version"],
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine_architecture": platform.machine(),
            "processor": platform.processor() or "not reported by platform",
            "requirements_lock_sha256": hashlib.sha256(
                (root / "requirements.lock").read_bytes()
            ).hexdigest(),
            "benchmark_script_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "source_revision": _source_revision(root),
        },
        "public_dataset_provenance": _dataset_provenance(),
        "external_radiomics_comparison": comparator,
        "ibsi_configuration_d_verification": ibsi,
        "radiomics_benchmark": radiomics,
        "export_validation_benchmark": export,
        "runtime_memory_benchmark": runtime,
        "unavailable_experiments": [
            {
                "name": "Full IBSI Phase 1/2 compliance",
                "status": "not_run",
                "reason": "The recorded Configuration D verification is not a complete Phase 1/2 workflow or a full compliance certification.",
            },
            {
                "name": "Full-collection image-level analysis of CT-Phantom4Radiomics",
                "status": "not_run",
                "reason": (
                    "The synthetic/fixture benchmark records collection metadata "
                    "only and does not analyze image data. A separate real-data "
                    "study evaluated one 172-slice series; the rest of the "
                    "collection was not evaluated."
                ),
            },
        ],
        "scenario_summary": _scenario_summary({
            "radiomics_benchmark": radiomics,
            "export_validation_benchmark": export,
            "runtime_memory_benchmark": runtime,
            "external_radiomics_comparison": comparator,
        }),
    }


def _report_markdown(results: dict[str, Any]) -> str:
    radiomics = results["radiomics_benchmark"]
    export = results["export_validation_benchmark"]
    runtime = results["runtime_memory_benchmark"]
    ds = results["public_dataset_provenance"]
    comparator = results["external_radiomics_comparison"]
    ibsi = results["ibsi_configuration_d_verification"]
    environment = results["benchmark_environment"]
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
        f"- Synthetic/fixture benchmark provenance: `{ds['download_status']}` for the collection metadata; no collection-level images were analyzed in this benchmark.",
        "- Separate real-data study: one 172-slice series was downloaded and evaluated (ZIP SHA-256 `fe6d292dc6989ca85d8323781067a3781ddc21c62105403ee83af512725539ea`); the rest of the collection was not evaluated.",
        "",
        "## Execution environment",
        f"- Project version: `{environment['project_version']}`",
        f"- Python: `{environment['python_implementation']} {environment['python_version']}`",
        f"- Platform: `{environment['platform']}`",
        f"- Architecture: `{environment['machine_architecture']}`",
        f"- Processor: `{environment['processor']}`",
        f"- Dependency lock SHA-256: `{environment['requirements_lock_sha256']}`",
        f"- Benchmark script SHA-256: `{environment['benchmark_script_sha256']}`",
        f"- Source revision: `{environment['source_revision']}`",
        "",
        "## Radiomics benchmark (synthetic CT phantom ROI)",
        f"- ROI: `{radiomics['roi']}`",
        f"- Preprocessing: {radiomics['preprocessing']}",
        f"- Measured mean/std: {radiomics['measured_values']['mean']:.2f} / {radiomics['measured_values']['std']:.2f} HU",
        f"- Ground-truth targets: mean {radiomics['expected_values']['mean']:.2f} ± {radiomics['tolerances']['mean_abs_tol']:.2f}; std {radiomics['expected_values']['std']:.2f} ± {radiomics['tolerances']['std_abs_tol']:.2f}",
        f"- Pass: {radiomics['pass']} (absolute errors: mean {radiomics['absolute_errors']['mean_abs_error']:.2f}, std {radiomics['absolute_errors']['std_abs_error']:.2f})",
        "",
        "## Matched PyRadiomics comparison",
        f"- Status: `{comparator['status']}`",
        f"- Scope: {comparator.get('scope', comparator.get('note', 'No comparison recorded.'))}",
        f"- PyRadiomics version: `{comparator.get('version', 'not available')}`",
        f"- ROI shape/SHA-256: `{comparator.get('roi_shape', 'not available')}` / `{comparator.get('roi_sha256', 'not available')}`",
        f"- Absolute errors (mean/std/min/max): `{comparator.get('absolute_errors', 'not available')}`",
        f"- Within tolerance: `{comparator.get('all_within_tolerance', 'not established')}`",
        f"- Environment: `{comparator.get('execution_environment', {}).get('platform', 'not recorded')}`; Python `{comparator.get('execution_environment', {}).get('python_version', 'not recorded')}`",
        f"- Result artifact: `{comparator.get('artifact', 'not recorded')}` (SHA-256 `{comparator.get('artifact_sha256', 'not available')}`)",
        "",
        "## IBSI Configuration D reference verification",
        f"- Status: `{ibsi['status']}`",
        f"- Reference dataset: `{ibsi.get('reference_source', {}).get('dataset', 'not recorded')}` at `{ibsi.get('reference_source', {}).get('commit', 'commit unavailable')}`; license `{ibsi.get('reference_source', {}).get('license', 'not recorded')}`",
        f"- Configuration D Z-Rad comparison: `{ibsi.get('zrad_comparison', {}).get('compared', 'not available')}` compared; `{ibsi.get('zrad_comparison', {}).get('passed', 'not available')}` passed; `{ibsi.get('zrad_comparison', {}).get('failed', 'not available')}` failed; `{ibsi.get('zrad_comparison', {}).get('unsupported', 'not available')}` unsupported.",
        f"- PyRadiomics reference comparison (separate from Z-Rad): `{ibsi.get('pyradiomics_reference_comparison', {}).get('compared', 'not available')}` assessed; `{ibsi.get('pyradiomics_reference_comparison', {}).get('passed', 'not available')}` passed; `{ibsi.get('pyradiomics_reference_comparison', {}).get('failed', 'not available')}` failed; `{ibsi.get('pyradiomics_reference_comparison', {}).get('unsupported', 'not available')}` not assessed because no defensible feature mapping was established for this comparison.",
        f"- Z-Rad statistics rows: `{ibsi.get('statistics_comparison', {}).get('compared', 'not available')}` compared; `{ibsi.get('statistics_comparison', {}).get('passed', 'not available')}` passed; `{ibsi.get('statistics_comparison', {}).get('failed', 'not available')}` failed.",
        f"- Default viewer slice radiomics: `{ibsi.get('application_alignment', 'not available')}`. It uses a 2D unmasked slice, so no Configuration D pass/fail comparison is made for this path.",
        f"- Boundary: {ibsi.get('scope', ibsi.get('note', 'No verification recorded.'))}",
        f"- Result artifact: `{ibsi.get('artifact', 'not recorded')}` (SHA-256 `{ibsi.get('artifact_sha256', 'not available')}`)",
        "",
        "## Export/privacy validation benchmark",
        "- Fixture set: 20 valid and 20 invalid generated challenge archives.",
        f"- Interpretation: {export['estimate_scope']}",
        f"- Sensitivity: {export['sensitivity']:.3f}",
        f"- Specificity: {export['specificity']:.3f}",
        f"- TP/TN/FP/FN: {export['tp']}/{export['tn']}/{export['fp']}/{export['fn']}",
        "",
        "## Runtime and memory benchmark",
        f"- Mean elapsed: {runtime['mean_elapsed_seconds']:.6f} s",
        f"- Median elapsed: {runtime['median_elapsed_seconds']:.6f} s",
        f"- Mean Python allocation peak: {runtime['mean_peak_mb']:.3f} MB",
        f"- Cache hit rate over fixed protocol: {runtime['mean_hit_rate']:.3f}",
        f"- Scope: {runtime['measurement_scope']}",
        "",
        "## Unavailable experiments",
        "- Full IBSI Phase 1/2 compliance certification was not performed.",
        "- Full-collection image-level evaluation on CT-Phantom4Radiomics was not performed. A separate real-data study evaluates one 172-slice series.",
        "",
        "## Limitation statement",
        "Measurements above are limited to the stated synthetic ROI, official Configuration D reference table and Z-Rad pipeline, generated challenge fixtures, and synthetic navigation-cache workload. They are not clinical validation, do not establish global generalizability or superiority, and do not constitute full IBSI compliance.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", type=Path, default=Path("verification") / "results" / "heeh_v1_public_benchmark_results.json")
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
