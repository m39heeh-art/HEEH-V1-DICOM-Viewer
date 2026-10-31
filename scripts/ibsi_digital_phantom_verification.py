"""Compare IBSI 1 digital-phantom feature values with the official table."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ibsi_reference_verification import (
    _compare_configuration_rows,
    _load_reference_table,
)

_FAMILY_NAMES = {
    "Morphology": "morphology",
    "Local intensity": "local_intensity",
    "Statistics": "intensity_statistics",
    "Intensity histogram": "intensity_histogram",
    "Intensity volume histogram": "ivh",
    "Co-occurrence matrix": "glcm",
    "Run length matrix": "glrlm",
    "Size zone matrix": "glszm",
    "Distance zone matrix": "gldzm",
    "Neighbourhood grey tone difference matrix": "ngtdm",
    "Neighbouring grey level dependence matrix": "ngldm",
}
_NON_INVENTORY_DERIVED_OUTPUTS = {
    "ivh_diff_v10_v90",
    "ivh_diff_i10_i90",
}
_NOT_RECOMMENDED_FEATURES = {
    "morph_vol_dens_ombb": "ZH1A",
    "morph_area_dens_ombb": "IQYR",
    "morph_vol_dens_mvee": "SWZ1",
    "morph_area_dens_mvee": "BRI8",
    "ivh_auc": "9CMM",
}
_OFFICIAL_FEATURE_ID_SOURCE = (
    "https://ibsi.readthedocs.io/en/latest/03_Image_features.html"
)
_PERMANENT_IDS_BY_FAMILY = {
    "morphology": (
        "RNU0", "YEKZ", "C0JK", "2PR5", "SKGS", "BQWJ", "KRCK", "QCFX",
        "25C7", "KLMA", "L0JK", "TDIC", "P9VJ", "7J51", "Q3CK", "N17B",
        "PBX1", "R59B", "ZH1A", "IQYR", "6BDE", "RDD2", "SWZ1", "BRI8",
        "R3ER", "7T7F", "99N0", "N365", "NPT7",
    ),
    "local_intensity": ("VJGA", "0F91"),
    "intensity_statistics": (
        "Q4LE", "ECT3", "KE2A", "IPH6", "Y12H", "1GSF", "QG58", "8DWT",
        "84IY", "SALO", "2OJQ", "4FUA", "1128", "N72L", "7TET", "9S40",
        "N8CA", "5ZWQ",
    ),
    "intensity_histogram": (
        "X6K6", "CH89", "88K1", "C3I7", "WIFQ", "1PR8", "1PR8", "GPMT",
        "3NCY", "AMMC", "WR0O", "5Z3W", "D2ZX", "WRZB", "4RNL", "CWYJ",
        "SLWD", "TLU2", "BJ5W", "12CE", "8E6O", "VQB3", "RHQZ",
    ),
    "ivh": ("BC2M", "GBPN", "DDTU", "CNV2", "9CMM"),
    "glcm": (
        "GYBY", "60VM", "UR99", "TU9B", "TF7R", "D3YU", "NTRS", "ZGXS",
        "OEEB", "P6QZ", "8ZQL", "ACUI", "8S9J", "IB1Z", "NDRX", "WF0Z",
        "1QCO", "E8JP", "NI2N", "QWB0", "DG8W", "7NFM", "AE86", "R8DG",
        "JN9H",
    ),
    "glrlm": (
        "22OV", "W4KF", "V3SW", "G3QZ", "HTZT", "GD3A", "IVPO", "3KUM",
        "R5YN", "OVBL", "W92Y", "IC23", "9ZK5", "8CE5", "SXLW", "HJ9O",
    ),
    "glszm": (
        None, "48P8", "XMSY", "5GN9", "5RAI", "HW1V", "YH51", "J17V",
        "JNSA", "Y1RO", "4JP3", "VB3A", "P30P", "BYLV", "3NSA", "GU8N",
    ),
    "gldzm": (
        "0GBI", "MB4I", "S1RA", "K26C", "RUVG", "DKNJ", "A7WM", "KLTH",
        "VFT7", "7HP3", "V294", "IATH", "VIWW", "QK93", "7WT1", "GBDU",
    ),
    "ngtdm": ("QCDE", "65HE", "NQ30", "HDEZ", "1X9X"),
    "ngldm": (
        "SODN", "IMOQ", "TL9H", "OAE7", "EQ3F", "JA6D", "NBZI", "9QMG",
        "FP8K", "5SPA", "Z87G", "OKJI", "6XV8", "1PFV", "DNX2", "FCBV",
        "CAS9",
    ),
}
_OFFICIAL_3D_GLSZM_MATRIX = (
    (1, 50, 1),
    (3, 1, 1),
    (4, 2, 1),
    (4, 14, 1),
    (6, 7, 1),
)
_OFFICIAL_GLSZM_MATRIX_SOURCE = (
    "https://ibsi.readthedocs.io/en/latest/"
    "06_Digital_phantom_texture_matrices.html"
)


def _canonical_feature_tag(tag: str) -> str:
    tag = re.sub(r"_(?:2D|2_5D|3D)_(?:avg|comb)$", "", tag)
    return re.sub(r"_(?:2D|2_5D|3D)$", "", tag)


def _feature_inventory(
    reference_rows: list[dict[str, str]],
    computed_tags: set[str],
    comparison_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    from core.ibsi_radiomics import IBSI1_FEATURE_FAMILY_COUNTS

    entries: dict[tuple[str, str], dict[str, Any]] = {}
    comparisons_by_tag = {
        row["tag"]: row
        for row in comparison_rows
        if row.get("tag")
    }
    for row in reference_rows:
        source_family = row.get("family", "")
        family_label = source_family.split(" (", 1)[0]
        family = _FAMILY_NAMES.get(family_label)
        if family is None:
            continue
        source_tag = row.get("tag", "")
        tag = _canonical_feature_tag(source_tag)
        key = (family, tag)
        item = entries.setdefault(
            key,
            {
                "family": family,
                "feature_tag": tag,
                "feature_name": row.get("feature"),
                "inventory_definition": tag
                not in _NON_INVENTORY_DERIVED_OUTPUTS,
                "reference_rows": [],
            },
        )
        if row.get("reference value"):
            item["reference_rows"].append(source_tag)

    comparison_status: dict[str, list[bool]] = defaultdict(list)
    for tag, row in comparisons_by_tag.items():
        if row["expected"] is not None:
            comparison_status[_canonical_feature_tag(tag)].append(
                row["passed"] is True
            )

    for item in entries.values():
        canonical_tag = item["feature_tag"]
        output_tags = sorted(
            tag for tag in computed_tags
            if _canonical_feature_tag(tag) == canonical_tag
        )
        item["implementation_output_tags"] = output_tags
        item["implemented"] = bool(output_tags)
        item["reference_status"] = (
            "not_available"
            if not item["reference_rows"]
            else "failed"
            if False in comparison_status.get(canonical_tag, [])
            else "passed"
            if comparison_status.get(canonical_tag)
            else "not_compared"
        )
        item["recommendation_status"] = (
            "not_recommended_no_reference_value"
            if canonical_tag in _NOT_RECOMMENDED_FEATURES
            else "reference_supported"
        )
        item["ibsi_permanent_id"] = _NOT_RECOMMENDED_FEATURES.get(
            canonical_tag
        )
        item["reference_rows"] = sorted(set(item["reference_rows"]))
        if (item["recommendation_status"] != "reference_supported") != (
            item["reference_status"] == "not_available"
        ):
            raise ValueError(
                "IBSI no-reference feature set changed; review the official "
                f"feature manual before updating the inventory: {canonical_tag}"
            )

    for family, permanent_ids in _PERMANENT_IDS_BY_FAMILY.items():
        family_definitions = [
            item
            for item in entries.values()
            if item["family"] == family and item["inventory_definition"]
        ]
        if len(family_definitions) != len(permanent_ids):
            raise ValueError(
                f"IBSI permanent-ID inventory mismatch for {family}: "
                f"expected {len(permanent_ids)} definitions, "
                f"found {len(family_definitions)}."
            )
        for item, permanent_id in zip(family_definitions, permanent_ids):
            item["ibsi_permanent_id"] = permanent_id
            item["permanent_id_status"] = (
                "published" if permanent_id else "not_listed_in_official_manual"
            )

    permanent_id_to_tags: dict[str, list[str]] = defaultdict(list)
    for item in entries.values():
        if item["inventory_definition"] and item["ibsi_permanent_id"]:
            permanent_id_to_tags[item["ibsi_permanent_id"]].append(
                item["feature_tag"]
            )
    permanent_id_collisions = {
        permanent_id: sorted(tags)
        for permanent_id, tags in permanent_id_to_tags.items()
        if len(tags) > 1
    }
    definitions = [
        item for item in entries.values() if item["inventory_definition"]
    ]
    for item in definitions:
        if item["ibsi_permanent_id"] in permanent_id_collisions:
            item["permanent_id_status"] = "published_identifier_collision"
    family_summary = {}
    for family, expected_count in IBSI1_FEATURE_FAMILY_COUNTS.items():
        family_items = [
            item for item in definitions if item["family"] == family
        ]
        family_summary[family] = {
            "expected_definitions": expected_count,
            "mapped_definitions": len(family_items),
            "reference_supported_definitions": sum(
                item["recommendation_status"] == "reference_supported"
                for item in family_items
            ),
            "implemented_reference_supported_definitions": sum(
                item["recommendation_status"] == "reference_supported"
                and item["implemented"]
                for item in family_items
            ),
            "not_recommended_definitions": sum(
                item["recommendation_status"]
                == "not_recommended_no_reference_value"
                for item in family_items
            ),
            "missing_implementation_tags": [
                item["feature_tag"]
                for item in family_items
                if item["recommendation_status"] == "reference_supported"
                and not item["implemented"]
            ],
        }
        if len(family_items) != expected_count:
            raise ValueError(
                f"IBSI feature inventory mismatch for {family}: "
                f"expected {expected_count}, mapped {len(family_items)}."
            )
    return {
        "definitions": len(definitions),
        "implemented_definitions": sum(
            item["recommendation_status"] == "reference_supported"
            and item["implemented"]
            for item in definitions
        ),
        "reference_supported_definitions": sum(
            item["recommendation_status"] == "reference_supported"
            for item in definitions
        ),
        "implemented_reference_supported_definitions": sum(
            item["recommendation_status"] == "reference_supported"
            and item["implemented"]
            for item in definitions
        ),
        "unimplemented_recommended_definitions": sum(
            item["recommendation_status"] == "reference_supported"
            and not item["implemented"]
            for item in definitions
        ),
        "definitions_with_reference_values": sum(
            item["reference_status"] != "not_available"
            for item in definitions
        ),
        "definitions_without_reference_values": sum(
            item["reference_status"] == "not_available"
            for item in definitions
        ),
        "not_recommended_definitions": sum(
            item["recommendation_status"]
            == "not_recommended_no_reference_value"
            for item in definitions
        ),
        "permanent_id_source": _OFFICIAL_FEATURE_ID_SOURCE,
        "permanent_ids_published": sum(
            item["ibsi_permanent_id"] is not None for item in definitions
        ),
        "definitions_without_permanent_id": [
            item["feature_tag"]
            for item in definitions
            if item["ibsi_permanent_id"] is None
        ],
        "permanent_id_collisions": permanent_id_collisions,
        "derived_outputs_not_in_172_definition_inventory": sorted(
            _NON_INVENTORY_DERIVED_OUTPUTS
        ),
        "families": family_summary,
        "items": sorted(
            entries.values(),
            key=lambda item: (item["family"], item["feature_tag"]),
        ),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digital_phantom_features(image_path: Path, mask_path: Path) -> dict[str, float]:
    from zrad.image import Image
    from zrad.preprocessing import (
        IVHIntensityDiscretizer,
        IntensityMaskBuilder,
        RoiData,
        TextureDiscretizer,
    )
    from zrad.radiomics import Radiomics

    image = Image.from_nifti(image_path)
    mask = Image.from_nifti_mask(mask_path, reference=image)
    roi = IntensityMaskBuilder().apply(
        RoiData(image=image, morphological_mask=mask)
    )
    values = roi.intensity_mask.array[np.isfinite(roi.intensity_mask.array)]
    if values.size == 0:
        raise ValueError("The IBSI digital phantom ROI contains no valid voxels.")

    roi = RoiData(
        image=roi.image,
        morphological_mask=roi.morphological_mask,
        intensity_mask=roi.intensity_mask,
        intensity_range=(float(values.min()), float(values.max())),
    )
    roi = TextureDiscretizer(bin_size=1.0).apply(roi)
    roi = IVHIntensityDiscretizer(method="direct").apply(roi)

    requests = [
        ("morphology", "3D", "AVER"),
        ("local_intensity", "3D", "AVER"),
        ("intensity_statistics", "3D", "AVER"),
        ("intensity_histogram", "3D", "AVER"),
        ("ivh", "3D", "AVER"),
    ]
    for family in ("glcm", "glrlm"):
        requests.extend(
            (family, dimension, aggregation)
            for dimension, aggregation in (
                ("2D", "AVER"),
                ("2D", "SLICE_MERG"),
                ("2.5D", "DIR_MERG"),
                ("2.5D", "MERG"),
                ("3D", "AVER"),
                ("3D", "MERG"),
            )
        )
    for family in ("glszm", "gldzm", "ngtdm", "ngldm"):
        requests.extend(
            (family, dimension, "AVER")
            for dimension in ("2D", "2.5D", "3D")
        )

    features: dict[str, float] = {}
    for family, dimension, aggregation in requests:
        result = Radiomics(
            aggr_dim=dimension,
            aggr_method=aggregation,
        ).extract_features(
            roi_data=roi,
            families=family,
            include_metadata=False,
        )
        overlap = features.keys() & result.keys()
        if overlap:
            raise ValueError(
                f"Duplicate feature identifiers in digital phantom extraction: "
                f"{sorted(overlap)}"
            )
        features.update({key: float(value) for key, value in result.items()})
    return features


def _independent_glszm_check(
    image_path: Path,
    mask_path: Path,
    reference_value: float,
    zrad_value: float,
) -> dict[str, Any]:
    try:
        from radiomics import featureextractor
    except ImportError:
        return {
            "status": "not_available",
            "implementation": "PyRadiomics",
            "reason": "PyRadiomics is not installed.",
        }

    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=1,
        normalize=False,
        resampledPixelSpacing=None,
        correctMask=False,
        force2D=False,
    )
    extractor.disableAllFeatures()
    extractor.enableFeatureClassByName("glszm")
    result = extractor.execute(str(image_path), str(mask_path), label=1)
    feature_name = "original_glszm_LargeAreaHighGrayLevelEmphasis"
    actual = float(result[feature_name])
    return {
        "status": "corroborates_zrad_mismatch",
        "implementation": "PyRadiomics",
        "version": importlib.metadata.version("pyradiomics"),
        "feature": feature_name,
        "actual": actual,
        "official_reference": reference_value,
        "absolute_error": abs(actual - reference_value),
        "matches_zrad": abs(actual - zrad_value) <= 1e-12,
        "within_official_tolerance": abs(actual - reference_value) <= 0.5,
    }


def _official_glszm_matrix_check(
    implementation_value: float,
    feature_reference_value: float,
) -> dict[str, Any]:
    """Evaluate IBSI's published digital-phantom GLSZM table directly."""
    zone_count = sum(count for _, _, count in _OFFICIAL_3D_GLSZM_MATRIX)
    voxel_count = sum(
        zone_size * count
        for _, zone_size, count in _OFFICIAL_3D_GLSZM_MATRIX
    )
    matrix_feature_value = sum(
        gray_level**2 * zone_size**2 * count
        for gray_level, zone_size, count in _OFFICIAL_3D_GLSZM_MATRIX
    ) / zone_count
    return {
        "status": (
            "matrix_matches_implementation_but_conflicts_with_feature_reference"
            if np.isclose(matrix_feature_value, implementation_value)
            and not np.isclose(matrix_feature_value, feature_reference_value)
            else "matrix_check_inconclusive"
        ),
        "source": _OFFICIAL_GLSZM_MATRIX_SOURCE,
        "matrix_rows": [
            {"gray_level": gray_level, "zone_size": zone_size, "count": count}
            for gray_level, zone_size, count in _OFFICIAL_3D_GLSZM_MATRIX
        ],
        "formula": "sum(i^2 * s^2 * n) / sum(n)",
        "zone_count": zone_count,
        "voxel_count": voxel_count,
        "matrix_feature_value": matrix_feature_value,
        "implementation_value": implementation_value,
        "feature_reference_value": feature_reference_value,
        "matches_implementation": bool(
            np.isclose(matrix_feature_value, implementation_value)
        ),
        "matches_feature_reference": bool(
            np.isclose(matrix_feature_value, feature_reference_value)
        ),
    }


def _upstream_workbook_check(workbook_path: Path) -> dict[str, Any]:
    """Verify the pinned reference workbook against the currently published one.

    Opt-in (network) check: the official IBSI-1 submission table is fetched
    fresh once and its digest is compared with the pinned local copy. A match
    proves the recorded comparison used the workbook exactly as currently
    published upstream; a mismatch proves the source itself changed.
    """
    import tempfile
    import urllib.request
    from datetime import datetime, timezone

    url = "https://ibsi.radiomics.hevs.ch/assets/IBSI-1-submission-table.xlsx"
    result: dict[str, Any] = {
        "check": "pinned vs currently published official IBSI-1 submission workbook",
        "upstream_url": url,
        "checked_at_utc": None,
        "pinned_workbook_sha256": (
            _sha256(workbook_path) if workbook_path.is_file() else None
        ),
        "upstream_workbook_sha256": None,
        "identical_to_pinned": None,
        "status": "not_checked",
    }
    if result["pinned_workbook_sha256"] is None:
        result["status"] = "pinned_workbook_missing"
        return result
    try:
        tmp_path = Path(tempfile.gettempdir()) / "ibsi_submission_table.upstream_check.xlsx"
        urllib.request.urlretrieve(url, tmp_path)
    except Exception as exc:  # noqa: BLE001 - report soft failure, never crash the run
        result["status"] = "upstream_unreachable"
        result["reason"] = str(exc)
        return result
    result["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["upstream_workbook_sha256"] = _sha256(tmp_path)
    result["identical_to_pinned"] = bool(
        result["upstream_workbook_sha256"] == result["pinned_workbook_sha256"]
    )
    result["status"] = (
        "upstream_identical" if result["identical_to_pinned"] else "upstream_changed"
    )
    try:
        tmp_path.unlink()
    except OSError:  # noqa: BLE001 - temp cleanup is best-effort
        pass
    return result


def run(data_root: Path, output_path: Path, *, check_upstream: bool = False) -> dict:
    """Run the complete populated digital-phantom reference comparison."""
    phantom_root = data_root / "ibsi_1_digital_phantom"
    image_path = phantom_root / "nifti" / "image" / "phantom.nii.gz"
    mask_path = phantom_root / "nifti" / "mask" / "mask.nii.gz"
    if not image_path.is_file() or not mask_path.is_file():
        raise FileNotFoundError(
            "IBSI digital phantom image or mask is missing under "
            f"{phantom_root}."
        )

    reference_table = _load_reference_table(phantom_root, "digital")
    if reference_table.get("status") != "available":
        raise FileNotFoundError(
            "Official IBSI digital-phantom reference CSV is missing: "
            f"{reference_table['path']}"
        )
    features = _digital_phantom_features(image_path, mask_path)
    comparison = _compare_configuration_rows(reference_table, features)
    inventory = _feature_inventory(
        reference_table["_rows"],
        set(features),
        comparison["comparisons"],
    )
    mismatches = [
        row for row in comparison["comparisons"] if row["passed"] is False
    ]
    glszm_mismatch = next(
        (row for row in mismatches if row["tag"] == "szm_lzhge_3D"),
        None,
    )
    independent_check = (
        None
        if glszm_mismatch is None
        else _independent_glszm_check(
            image_path,
            mask_path,
            float(glszm_mismatch["expected"]),
            float(glszm_mismatch["actual"]),
        )
    )
    matrix_check = (
        None
        if glszm_mismatch is None
        else _official_glszm_matrix_check(
            float(glszm_mismatch["actual"]),
            float(glszm_mismatch["expected"]),
        )
    )
    reference_csv_path = Path(reference_table["path"])
    workbook_path = (
        Path(__file__).resolve().parents[1]
        / "cache_logs"
        / "ibsi_ref"
        / "IBSI-1-submission-table.xlsx"
    )
    status = (
        "passed"
        if comparison["failed"] == 0 and comparison["unsupported"] == 0
        else "reference_mismatch"
    )
    payload = {
        "schema": "heeh-v1.ibsi-digital-phantom-verification",
        "schema_version": 1,
        "status": status,
        "scope": (
            "All populated IBSI 1 digital-phantom reference rows were "
            "compared with the corresponding Z-Rad feature output. This is "
            "an implementation-to-reference comparison, not complete IBSI "
            "conformance or patient-data validation."
        ),
        "implementation": "Z-Rad",
        "configuration": {
            "image_interpolation": "none",
            "resegmentation": "none",
            "texture_discretization": {
                "method": "fixed bin size",
                "bin_size": 1.0,
                "anchor": "minimum intensity in the intensity mask",
            },
            "ivh_discretization": "direct",
            "label": 1,
            "aggregations": [
                "2D AVER",
                "2D SLICE_MERG",
                "2.5D DIR_MERG",
                "2.5D MERG",
                "3D AVER",
                "3D MERG",
            ],
        },
        "reference_table": {
            key: value
            for key, value in reference_table.items()
            if key != "_rows"
        },
        "comparison": {
            key: value
            for key, value in comparison.items()
            if key != "comparisons"
        },
        "feature_inventory": inventory,
        "mismatches": mismatches,
        "independent_check": independent_check,
        "official_matrix_check": matrix_check,
        "upstream_consistency_check": (
            _upstream_workbook_check(workbook_path) if check_upstream else None
        ),
        "source": {
            "image_sha256": _sha256(image_path),
            "mask_sha256": _sha256(mask_path),
            "phantom_license": "CC BY 4.0",
            "reference_workbook": (
                "https://ibsi.radiomics.hevs.ch/assets/"
                "IBSI-1-submission-table.xlsx"
            ),
            "reference_license": "CC BY 4.0",
            "feature_manual": (
                "https://ibsi.readthedocs.io/en/latest/"
                "03_Image_features.html"
            ),
            "digital_phantom_matrix_manual": _OFFICIAL_GLSZM_MATRIX_SOURCE,
            "no_reference_feature_guidance": (
                "IBSI states that features without reference values should "
                "not be used; the four OMBB/MVEE densities and IVH AUC "
                "are listed without reference values. Their permanent "
                "identifiers are ZH1A, IQYR, SWZ1, BRI8, and 9CMM."
            ),
            "reference_csv_sha256": _sha256(reference_csv_path),
            "reference_workbook_sha256": (
                _sha256(workbook_path) if workbook_path.is_file() else None
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("verification") / "data" / "ibsi_reference_data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("verification")
        / "results"
        / "ibsi_digital_phantom_verification.json",
    )
    parser.add_argument(
        "--check-upstream",
        action="store_true",
        help=(
            "Also fetch the currently published IBSI-1 submission workbook "
            "and record whether it is byte-identical to the pinned copy "
            "(requires network access)."
        ),
    )
    args = parser.parse_args()
    payload = run(args.data_root, args.output, check_upstream=args.check_upstream)
    print(json.dumps(
        {
            "status": payload["status"],
            **payload["comparison"],
            "output": str(args.output),
        },
        sort_keys=True,
    ))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
