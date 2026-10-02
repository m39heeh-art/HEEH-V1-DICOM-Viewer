from pathlib import Path

import pytest

from scripts.public_benchmark_evidence import _report_markdown, build_results


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_EVIDENCE = (
    _REPO_ROOT
    / "verification"
    / "results"
    / "ibsi_configuration_d_verification.json"
)


def test_public_benchmark_results_are_measured_and_explicitly_blocked():
    if not _REQUIRED_EVIDENCE.is_file():
        pytest.skip("Optional recorded IBSI benchmark evidence is not included")
    results = build_results()

    assert results["public_dataset_provenance"]["collection"] == "CT-Phantom4Radiomics"
    assert results["radiomics_benchmark"]["pass"] is True
    assert results["export_validation_benchmark"]["sensitivity"] == 1.0
    assert results["export_validation_benchmark"]["specificity"] == 1.0
    assert results["runtime_memory_benchmark"]["protocol"]["image_count"] == 8
    assert results["runtime_memory_benchmark"]["measurement_scope"].startswith(
        "Synthetic navigation-cache workload only."
    )
    source_revision = results["benchmark_environment"]["source_revision"]
    assert (
        source_revision.startswith("unavailable;")
        or len(source_revision.split(" ", 1)[0]) == 40
    )
    assert "metadata only" in results["public_dataset_provenance"]["note"]
    assert any(
        item["name"].startswith("Full-collection image-level")
        for item in results["unavailable_experiments"]
    )
    assert results["external_radiomics_comparison"]["status"] == "measured"
    assert results["external_radiomics_comparison"]["all_within_tolerance"] is True
    assert results["external_radiomics_comparison"]["execution_environment"][
        "python_version"
    ]
    assert results["ibsi_configuration_d_verification"]["zrad_comparison"][
        "compared"
    ] == 270
    assert results["ibsi_configuration_d_verification"][
        "pyradiomics_reference_comparison"
    ]["passed"] == 66
    assert results["ibsi_configuration_d_verification"][
        "pyradiomics_reference_comparison"
    ]["failed"] == 0
    assert results["ibsi_configuration_d_verification"][
        "pyradiomics_reference_comparison"
    ]["unsupported"] == 204
    assert results["ibsi_configuration_d_verification"]["application_alignment"] == (
        "not_configuration_d_compliant"
    )
    assert (
        results["ibsi_configuration_d_verification"]["statistics_comparison"][
            "passed"
        ]
        == 18
    )
    assert any(
        item["name"].startswith("Full IBSI")
        for item in results["unavailable_experiments"]
    )

    path = Path("verification") / "results" / "heeh_v1_public_benchmark_results.json"
    assert path.exists() is False or path.is_file()


def test_public_benchmark_report_is_generated_from_results():
    if not _REQUIRED_EVIDENCE.is_file():
        pytest.skip("Optional recorded IBSI benchmark evidence is not included")
    results = build_results()
    report = _report_markdown(results)

    assert "HEEH-V1 public benchmark report" in report
    assert "Constructed fixtures only" in report
    assert "Python allocation peak" in report
    assert results["benchmark_environment"]["requirements_lock_sha256"] in report
    assert "configuration-specific" in report
    assert "PyRadiomics reference comparison (separate from Z-Rad): `66` assessed" in report
    assert (
        "66` assessed; `66` passed; `0` failed; `204` not assessed because "
        "no defensible feature mapping was established for this comparison."
    ) in report
    assert "Z-Rad statistics rows: `18` compared; `18` passed; `0` failed" in report
    assert "no Configuration D pass/fail comparison is made" in report
    assert "C:\\Users\\" not in report
