import numpy as np

from core.tissue_classifier import RadiomicsExtractor


def test_ibsi_texture_feature_classes_are_finite_and_supported():
    image = np.array(
        [
            [0.0, 0.0, 1.0, 1.0],
            [0.0, 1.0, 1.0, 2.0],
            [1.0, 2.0, 2.0, 2.0],
            [2.0, 2.0, 3.0, 3.0],
        ],
        dtype=np.float64,
    )
    report = RadiomicsExtractor.full_report(
        image,
        levels=8,
        bin_width=1.0,
        discretization="fixed_bin_width",
        include_provenance=True,
    )

    assert report["feature_coverage"]["glrlm"]["status"] == "supported"
    assert report["feature_coverage"]["glszm"]["status"] == "supported"
    assert report["feature_coverage"]["gldm"]["status"] == "supported"
    assert report["feature_coverage"]["ngtdm"]["status"] == "supported"
    for name in ("glcm", "glrlm", "glszm", "gldm", "ngtdm"):
        values = report[name]
        assert values
        for key, value in values.items():
            if key == "provenance":
                continue
            assert np.isfinite(value), f"non-finite result in {name}.{key}: {value!r}"


def test_glrlm_glszm_gldm_ngtdm_return_expected_keys():
    image = np.array(
        [
            [0, 0, 1, 1],
            [0, 1, 1, 2],
            [1, 2, 2, 2],
            [2, 2, 3, 3],
        ],
        dtype=np.float64,
    )
    glrlm = RadiomicsExtractor.glrlm_features(
        image,
        levels=8,
        bin_width=1.0,
        discretization="fixed_bin_width",
    )
    glszm = RadiomicsExtractor.glszm_features(
        image,
        levels=8,
        bin_width=1.0,
        discretization="fixed_bin_width",
    )
    gldm = RadiomicsExtractor.gldm_features(
        image,
        levels=8,
        bin_width=1.0,
        discretization="fixed_bin_width",
    )
    ngtdm = RadiomicsExtractor.ngtdm_features(
        image,
        levels=8,
        bin_width=1.0,
        discretization="fixed_bin_width",
    )

    assert set(glrlm) >= {"short_run_emphasis", "long_run_emphasis", "gray_level_non_uniformity", "run_length_non_uniformity"}
    assert set(glszm) >= {"small_zone_emphasis", "large_zone_emphasis", "gray_level_non_uniformity", "zone_size_non_uniformity"}
    assert set(gldm) >= {"small_dependence_emphasis", "large_dependence_emphasis", "gray_level_non_uniformity", "dependence_non_uniformity"}
    assert set(ngtdm) >= {"coarseness", "contrast", "busyness", "complexity", "strength"}


def test_gldm_counts_local_gray_level_dependence_not_connected_zone_size():
    image = np.array(
        [
            [0, 0, 0],
            [0, 1, 0],
            [0, 0, 0],
        ],
        dtype=np.float64,
    )

    glszm = RadiomicsExtractor.glszm_features(
        image, levels=4, bin_width=1.0, discretization="fixed_bin_width"
    )
    gldm = RadiomicsExtractor.gldm_features(
        image, levels=4, bin_width=1.0, discretization="fixed_bin_width"
    )

    assert gldm["small_dependence_emphasis"] != glszm["small_zone_emphasis"]
    assert gldm["dependence_percentage"] == 1.0


def test_gldm_alpha_and_connectivity_are_explicit():
    image = np.array([[0, 1], [1, 0]], dtype=np.float64)

    four_neighbor = RadiomicsExtractor.gldm_features(
        image,
        levels=4,
        bin_width=1.0,
        discretization="fixed_bin_width",
        include_provenance=True,
        connectivity=1,
        alpha=0,
    )
    eight_neighbor = RadiomicsExtractor.gldm_features(
        image,
        levels=4,
        bin_width=1.0,
        discretization="fixed_bin_width",
        connectivity=2,
        alpha=1,
    )

    assert four_neighbor["provenance"]["connectivity"] == 1
    assert four_neighbor["provenance"]["alpha"] == 0
    assert four_neighbor["small_dependence_emphasis"] != (
        eight_neighbor["small_dependence_emphasis"]
    )


def test_ngtdm_handles_large_2d_inputs_without_per_pixel_python_loops():
    image = np.tile(np.arange(128, dtype=np.float64), (128, 1))

    result = RadiomicsExtractor.ngtdm_features(
        image,
        levels=128,
        bin_width=1.0,
        discretization="fixed_bin_width",
    )

    assert all(np.isfinite(value) for value in result.values())


def test_radiomics_excludes_invalid_pixels_and_disables_spatial_features():
    image = np.array(
        [[0.0, 10.0], [20.0, np.nan]],
        dtype=np.float64,
    )

    report = RadiomicsExtractor.full_report(
        image,
        levels=16,
        bin_width=5.0,
        discretization="fixed_bin_width",
    )

    assert report["histogram"]["mean"] == 10.0
    assert report["histogram"]["min"] == 0.0
    assert report["histogram"]["max"] == 20.0
    assert "glcm" not in report
    assert report["masking"] == {
        "status": (
            "first_order_only; spatial_features_not_computed_because_"
            "validity_mask_is_not_supported"
        ),
        "excluded_pixel_count": 1,
        "included_pixel_count": 3,
    }
