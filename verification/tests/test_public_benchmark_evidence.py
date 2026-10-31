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
    external = results["external_radiomics_comparison"]
    comparator_path = _REPO_ROOT / "verification" / "results" / "pyradiomics_comparison.json"
    if comparator_path.is_file():
        assert external["status"] == "measured"
        assert external["all_within_tolerance"] is True
        assert external["execution_environment"]["python_version"]
    else:
        assert external["status"] == "not_recorded"
    assert results["ibsi_configuration_d_verification"]["zrad_comparison"][
        "compared"
    ] == 270
    assert results["ibsi_configuration_d_verification"][
        "pyradiomics_reference_comparison"
    ]["passed"] == 75
    assert results["ibsi_configuration_d_verification"][
        "pyradiomics_reference_comparison"
    ]["failed"] == 0
    assert results["ibsi_configuration_d_verification"][
        "pyradiomics_reference_comparison"
    ]["unsupported"] == 195
    assert sum(
        results["ibsi_configuration_d_verification"][
            "pyradiomics_reference_comparison"
        ]["unsupported_by_category"].values()
    ) == 195
    assert results["ibsi_configuration_d_verification"]["application_alignment"] == (
        "not_configuration_d_compliant"
    )
    assert results["ibsi_configuration_d_verification"][
        "configuration_e_reference_status"
    ]["status"] == "passed"
    assert results["ibsi_configuration_d_verification"][
        "configuration_e_reference_status"
    ]["comparison"]["compared"] == 210
    assert results["ibsi_configuration_d_verification"][
        "configuration_e_reference_status"
    ]["comparison"]["skipped_diagnostics"] == 60
    assert results["ibsi_configuration_d_verification"][
        "configuration_e_reference_status"
    ]["comparison"]["failed"] == 0
    digital = results["ibsi_digital_phantom_verification"]
    assert digital["status"] == "reference_mismatch"
    assert digital["comparison"]["compared"] == 482
    assert digital["comparison"]["passed"] == 481
    assert digital["comparison"]["failed"] == 1
    assert digital["mismatches"][0]["tag"] == "szm_lzhge_3D"
    assert digital["independent_check"]["matches_zrad"] is True
    assert digital["official_matrix_check"]["matrix_feature_value"] == pytest.approx(1494.6)
    assert digital["official_matrix_check"]["matches_implementation"] is True
    assert digital["official_matrix_check"]["matches_feature_reference"] is False
    assert digital["feature_inventory"]["definitions"] == 172
    assert digital["feature_inventory"]["implemented_definitions"] == 167
    assert digital["feature_inventory"]["unimplemented_recommended_definitions"] == 0
    assert len(digital["unimplemented_feature_tags"]) == 0
    assert len(digital["not_recommended_feature_tags"]) == 5
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
    assert "PyRadiomics reference comparison (separate from Z-Rad): `75` assessed" in report
    assert "`75` assessed; `75` passed; `0` failed; `195` not assessed." in report
    assert "aggregation_semantics_not_comparable" in report
    assert "neither passes nor failures" in report
    assert "Z-Rad statistics rows: `18` compared; `18` passed; `0` failed" in report
    assert (
        "Configuration E official-reference status: `passed`; blocker `none`."
    ) in report
    assert "## IBSI digital phantom" in report
    assert "`482` compared; `481` passed; `1` failed" in report
    assert "167` of `167` reference-supported definitions have implementation outputs" in report
    assert "The published matrix and feature formula yield 1494.6" in report
    assert "no Configuration D pass/fail comparison is made" in report
    assert "C:\\Users\\" not in report
