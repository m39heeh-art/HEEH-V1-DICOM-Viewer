"""IBSI CT reporting context for reproducible feature-extraction runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_DICOM_REPORT_TAGS = (
    "Modality",
    "Manufacturer",
    "ManufacturerModelName",
    "KVP",
    "XRayTubeCurrent",
    "Exposure",
    "ExposureInuAs",
    "SliceThickness",
    "SpacingBetweenSlices",
    "PixelSpacing",
    "ConvolutionKernel",
    "ReconstructionAlgorithm",
    "RescaleIntercept",
    "RescaleSlope",
    "ContrastBolusAgent",
    "ContrastBolusVolume",
)

_ITEM_LABELS = {
    "1": "Region of interest",
    "2a": "Patient preparation instructions",
    "2b": "Drugs administered before acquisition",
    "2c": "Patient comfort equipment",
    "3a": "Radioactive tracer",
    "3b": "Tracer administration method",
    "3c": "Injected tracer activity",
    "3d": "Tracer uptake time",
    "3e": "Competing substance control",
    "4a": "Contrast agent",
    "4b": "Contrast administration method",
    "4c": "Contrast quantity",
    "4d": "Contrast uptake time",
    "4e": "Competing substance control for contrast",
    "5": "Comorbidities affecting imaging",
    "6": "Acquisition protocol",
    "7": "Scanner type and vendor",
    "8": "Imaging modality",
    "9a": "Static or dynamic scan",
    "9b": "Dynamic acquisition time per frame",
    "9c": "Temporal modelling",
    "10": "Scanner calibration",
    "11": "Patient instructions during acquisition",
    "12": "Anatomical motion correction",
    "13": "Scan duration",
    "14": "CT tube voltage",
    "15": "CT tube current",
    "16": "PET time-of-flight",
    "17": "MRI RF coil",
    "18a": "MRI scanning sequence",
    "18b": "MRI sequence variant",
    "18c": "MRI scan options",
    "19": "MRI repetition time",
    "20": "MRI echo time",
    "21": "MRI echo train length",
    "22": "MRI inversion time",
    "23": "MRI flip angle",
    "24": "MRI acquisition type",
    "25": "MRI k-space traversal",
    "26": "MRI number of averages",
    "27": "MRI magnetic field strength",
    "28": "In-plane image resolution",
    "29": "Image slice thickness",
    "30": "Image slice spacing",
    "31a": "CT convolution kernel",
    "31b": "CT iterative reconstruction",
    "31c": "CT exposure in ROI slices",
    "32a": "PET reconstruction method",
    "32b": "PET reconstruction iterations",
    "32c": "PET reconstruction subsets",
    "33": "PET point-spread-function modelling",
    "34a": "PET attenuation correction",
    "34b": "Other PET image corrections",
    "35a": "MRI reconstruction method",
    "35b": "MRI reconstruction artifact suppression",
    "36": "DWI b-values",
    "37": "Multi-modality registration",
    "38": "PET SUV normalisation",
    "39": "DWI ADC computation",
    "40": "Other data conversion",
    "41": "Anti-aliasing during down-sampling",
    "42": "Noise suppression",
    "43": "PET post-reconstruction smoothing",
    "44": "MRI skull stripping",
    "45": "MRI non-uniformity correction",
    "46": "Intensity normalisation",
    "47": "Other post-acquisition processing",
    "48a": "Segmentation method",
    "48b": "Manual segmentation experts and consensus",
    "48c": "Semi-automatic or automatic segmentation",
    "48d": "Image used to define segmentation",
    "49": "Conversion of segmentation to voxel mask",
    "50a": "Image interpolation method",
    "50b": "Interpolation grid position",
    "50c": "Interpolation grid dimensions",
    "50d": "Interpolation extrapolation",
    "51": "Interpolated voxel dimensions",
    "52": "CT intensity rounding",
    "53": "ROI mask interpolation",
    "54": "Partially masked voxel threshold",
    "55": "Re-segmentation methods",
    "56a": "Intensity discretisation method",
    "56b": "Discretisation bins or bin size",
    "56c": "Lowest intensity in first fixed-size bin",
    "57": "Image filters",
    "58": "Image biomarker set",
    "59": "IBSI benchmark compliance statement",
    "60": "Feature robustness assessment",
    "61": "Software and version",
    "62": "Texture matrix aggregation",
    "63": "Texture distance weighting",
    "64": "GLCM symmetry",
    "65": "GLCM distance",
    "66": "GLSZM linkage distance",
    "67": "GLDZM linkage distance",
    "68": "GLDZM border-distance norm",
    "69": "NGTDM distance",
    "70": "NGLDM distance",
    "71": "NGLDM coarseness",
    "72": "Diagnostic or prognostic modelling",
    "73": "Comparison with known factors",
    "74": "Multicollinearity assessment",
    "75": "Radiomics model availability",
    "76": "Imaging data and metadata availability",
}

_NON_CT_ITEMS = {
    "3a", "3b", "3c", "3d", "3e", "16", "17", "18a", "18b", "18c",
    "19", "20", "21", "22", "23", "24", "25", "26", "27", "32a",
    "32b", "32c", "33", "34a", "34b", "35a", "35b", "36", "38", "39",
    "43", "44", "45",
}
_STUDY_LEVEL_ITEMS = {"2a", "2b", "2c", "5", "48b", "72", "73", "74", "75", "76"}


def _value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dicom_metadata(image_source_files: list[Path]) -> dict[str, Any]:
    dicom_files = [
        path for path in image_source_files
        if path.suffix.lower() not in {".nii", ".gz"}
    ]
    if not dicom_files:
        return {
            "status": "not_available",
            "reason": "The image source is not a DICOM file set.",
            "fields": {},
        }

    import pydicom

    values: dict[str, dict[str, Any]] = {keyword: {} for keyword in _DICOM_REPORT_TAGS}
    decoded: dict[str, dict[str, Any]] = {}
    for path in dicom_files:
        dataset = pydicom.dcmread(
            str(path),
            stop_before_pixels=True,
            specific_tags=_DICOM_REPORT_TAGS,
        )
        for keyword in _DICOM_REPORT_TAGS:
            raw = getattr(dataset, keyword, None)
            if raw is None:
                continue
            normalized = _value(raw)
            key = repr(normalized)
            values[keyword].setdefault(key, {"value": normalized, "files": 0})
            values[keyword][key]["files"] += 1
            decoded.setdefault(keyword, {})[key] = normalized

    fields = {
        keyword: {
            "values": [decoded[keyword][key] for key in sorted(decoded[keyword])],
            "source": "DICOM header allowlist",
            "value_counts_by_source_file": [
                {"value": values[keyword][key]["value"], "files": values[keyword][key]["files"]}
                for key in sorted(values[keyword])
            ],
        }
        for keyword in _DICOM_REPORT_TAGS
        if keyword in decoded
    }
    return {
        "status": "available",
        "source_files_inspected": len(dicom_files),
        "fields": fields,
        "privacy": (
            "Only an allowlist of acquisition, reconstruction, intensity "
            "calibration, and contrast-agent attributes is retained; patient "
            "identifiers and free-text protocol descriptions are excluded."
        ),
    }


def _record(
    label: str,
    value: Any = None,
    *,
    reason: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    if value is not None:
        return {
            "label": label,
            "status": status or "reported",
            "value": _value(value),
            **({"reason": reason} if reason else {}),
        }
    return {
        "label": label,
        "status": "not_recorded",
        "value": None,
        "reason": reason or "Not supplied by the image, mask, or analysis inputs.",
    }


def build_ibsi_ct_reporting_context(
    *,
    configuration: dict[str, Any],
    mask_source: str,
    roi_name: str | None,
    input_spacing_mm: tuple[float, ...] | list[float],
    image_source_files: list[Path],
    feature_count: int,
    feature_family_coverage: dict[str, dict[str, Any]],
    application_version: str,
    radiomics_engine_version: str,
) -> dict[str, Any]:
    """Build a privacy-conscious analysis record for relevant IBSI report items."""
    dicom = _dicom_metadata(image_source_files)
    dicom_fields = dicom["fields"]

    def dicom_values(keyword: str) -> Any:
        field = dicom_fields.get(keyword)
        if not field:
            return None
        values = field["values"]
        return values[0] if len(values) == 1 else values

    interpolation = configuration.get("image_interpolation") or configuration.get(
        "interpolation"
    )
    resampling = configuration.get("resampling_mm")
    resegmentation = configuration.get("resegmentation")
    discretization = configuration.get("texture_and_histogram_discretization")
    ivh_discretization = configuration.get("ivh_discretization")
    image_rounding = configuration.get("resampled_intensity_rounding")
    mask_interpolation = configuration.get("mask_interpolation")
    mask_threshold = configuration.get("mask_threshold")
    feature_count_value = int(feature_count)

    reported: dict[str, Any] = {
        "1": _record(
            _ITEM_LABELS["1"],
            {"roi_name": roi_name, "mask_source": mask_source},
            reason="The application records the imported ROI identifier and mask representation, not its clinical meaning.",
            status="partially_reported",
        ),
        "6": _record(_ITEM_LABELS["6"], reason="Acquisition protocol description is not captured."),
        "7": _record(
            _ITEM_LABELS["7"],
            {
                "manufacturer": dicom_values("Manufacturer"),
                "model": dicom_values("ManufacturerModelName"),
            }
            if dicom_values("Manufacturer") is not None
            or dicom_values("ManufacturerModelName") is not None
            else None,
        ),
        "8": _record(
            _ITEM_LABELS["8"],
            dicom_values("Modality"),
            reason="CT is the selected workflow, but modality is not verified when source data are NIfTI.",
            status="partially_reported",
        ),
        "9a": _record(_ITEM_LABELS["9a"], reason="Static/dynamic acquisition status is not captured."),
        "10": _record(_ITEM_LABELS["10"], reason="Scanner calibration history is not present in the analysis input."),
        "11": _record(_ITEM_LABELS["11"], reason="Patient acquisition instructions are not captured."),
        "12": _record(_ITEM_LABELS["12"], reason="Motion-correction methods are not captured."),
        "13": _record(_ITEM_LABELS["13"], reason="Scan duration is not captured."),
        "14": _record(_ITEM_LABELS["14"], dicom_values("KVP")),
        "15": _record(_ITEM_LABELS["15"], dicom_values("XRayTubeCurrent")),
        "4a": _record(_ITEM_LABELS["4a"], dicom_values("ContrastBolusAgent")),
        "4c": _record(_ITEM_LABELS["4c"], dicom_values("ContrastBolusVolume")),
        "28": _record(_ITEM_LABELS["28"], list(input_spacing_mm)),
        "29": _record(_ITEM_LABELS["29"], dicom_values("SliceThickness")),
        "30": _record(
            _ITEM_LABELS["30"],
            dicom_values("SpacingBetweenSlices") or list(input_spacing_mm)[2],
        ),
        "31a": _record(_ITEM_LABELS["31a"], dicom_values("ConvolutionKernel")),
        "31b": _record(_ITEM_LABELS["31b"], dicom_values("ReconstructionAlgorithm")),
        "31c": _record(
            _ITEM_LABELS["31c"],
            {
                "exposure_mAs": dicom_values("Exposure"),
                "exposure_uAs": dicom_values("ExposureInuAs"),
            }
            if dicom_values("Exposure") is not None
            or dicom_values("ExposureInuAs") is not None
            else None,
        ),
        "37": {
            "label": _ITEM_LABELS["37"],
            "status": "not_applicable",
            "value": None,
            "reason": "This workflow processes one CT image volume and one ROI mask; it performs no multimodality registration.",
        },
        "40": _record(
            _ITEM_LABELS["40"],
            {
                "dicom_rescale_slope": dicom_values("RescaleSlope"),
                "dicom_rescale_intercept": dicom_values("RescaleIntercept"),
            }
            if dicom_values("RescaleSlope") is not None
            or dicom_values("RescaleIntercept") is not None
            else None,
        ),
        "41": _record(
            _ITEM_LABELS["41"],
            "No separate anti-aliasing filter is applied by the configured Z-Rad resampler.",
        ),
        "42": _record(_ITEM_LABELS["42"], "No separate noise-suppression filter is applied."),
        "46": _record(_ITEM_LABELS["46"], "No cohort or within-image intensity normalisation is applied."),
        "47": _record(_ITEM_LABELS["47"], "No additional post-acquisition image processing is applied."),
        "48a": _record(
            _ITEM_LABELS["48a"],
            {
                "mask_representation": mask_source,
                "roi_name": roi_name,
                "segmentation_method": None,
            },
            reason="The analysis imports a pre-existing ROI mask; its annotation method is not supplied.",
            status="partially_reported",
        ),
        "48b": _record(_ITEM_LABELS["48b"], reason="Expert count, expertise, and consensus details are not supplied."),
        "48c": _record(_ITEM_LABELS["48c"], reason="Segmentation-generation algorithm settings are not supplied."),
        "48d": _record(_ITEM_LABELS["48d"], reason="The image used to define the original segmentation is not supplied."),
        "49": _record(
            _ITEM_LABELS["49"],
            "NIfTI voxel mask loaded directly."
            if mask_source == "NIfTI"
            else "DICOM RTSTRUCT contours rasterized by Z-Rad; exact boundary inclusion policy is not exposed.",
        ),
        "50a": _record(_ITEM_LABELS["50a"], interpolation or "No interpolation"),
        "50b": _record(
            _ITEM_LABELS["50b"],
            "Grid centers aligned; output origin is shifted to center the resampled grid."
            if resampling
            else "No interpolation grid; original grid retained.",
        ),
        "50c": _record(
            _ITEM_LABELS["50c"],
            "Each output axis dimension is ceil(input_dimension * input_spacing / target_spacing)."
            if resampling
            else "No interpolation grid; original dimensions retained.",
        ),
        "50d": _record(
            _ITEM_LABELS["50d"],
            "SimpleITK constant default pixel value 0 outside the source image."
            if resampling
            else "No extrapolation; interpolation is disabled.",
        ),
        "51": _record(_ITEM_LABELS["51"], resampling or list(input_spacing_mm)),
        "52": _record(_ITEM_LABELS["52"], image_rounding or "No interpolation; no post-interpolation rounding."),
        "53": _record(_ITEM_LABELS["53"], mask_interpolation or "No mask interpolation"),
        "54": _record(_ITEM_LABELS["54"], mask_threshold),
        "55": _record(_ITEM_LABELS["55"], resegmentation),
        "56a": _record(
            _ITEM_LABELS["56a"],
            {"texture_and_histogram": discretization, "ivh": ivh_discretization},
        ),
        "56b": _record(
            _ITEM_LABELS["56b"],
            {"texture_and_histogram": discretization, "ivh": ivh_discretization},
        ),
        "56c": _record(
            _ITEM_LABELS["56c"],
            resegmentation.get("range_lower_hu")
            if isinstance(resegmentation, dict)
            and discretization
            and discretization.get("method") == "fixed bin size"
            else None,
            reason="A fixed lower re-segmentation bound is required to report an FBS anchor.",
        ),
        "57": _record(_ITEM_LABELS["57"], "No spatial image filters are applied."),
        "58": _record(
            _ITEM_LABELS["58"],
            {
                "ibsi_feature_family_counts": {
                    family: details["ibsi_feature_definitions"]
                    for family, details in feature_family_coverage.items()
                },
                "computed_output_values": feature_count_value,
                "family_coverage": feature_family_coverage,
            },
        ),
        "59": {
            "label": _ITEM_LABELS["59"],
            "status": "not_claimed",
            "value": False,
            "reason": "This software does not claim complete IBSI benchmark compliance.",
        },
        "60": _record(_ITEM_LABELS["60"], reason="Feature robustness was not assessed in this single analysis run."),
        "61": _record(
            _ITEM_LABELS["61"],
            {
                "application": "HEEH-V1 DICOM Viewer",
                "application_version": application_version,
                "radiomics_engine": "Z-Rad",
                "radiomics_engine_version": radiomics_engine_version,
            },
        ),
        "62": _record(
            _ITEM_LABELS["62"],
            configuration.get("texture_aggregation"),
        ),
        "63": _record(_ITEM_LABELS["63"], "No distance weighting; unweighted neighbour/matrix counts."),
        "64": _record(_ITEM_LABELS["64"], "Symmetric GLCM (each directional matrix is summed with its transpose)."),
        "65": _record(_ITEM_LABELS["65"], "Chebyshev distance 1; 4 in-plane or 13 unique 3D directions."),
        "66": _record(_ITEM_LABELS["66"], "Chebyshev distance 1; 8-connected in 2D and 26-connected in 3D."),
        "67": _record(_ITEM_LABELS["67"], "Chebyshev distance 1; 8-connected in 2D and 26-connected in 3D."),
        "68": _record(_ITEM_LABELS["68"], "Manhattan (taxicab) distance to ROI boundary."),
        "69": _record(_ITEM_LABELS["69"], "Chebyshev distance 1; 8 in-plane or 26 3D neighbours."),
        "70": _record(_ITEM_LABELS["70"], "Chebyshev distance 1; 8 in-plane or 26 3D neighbours."),
        "71": _record(_ITEM_LABELS["71"], "0; dependence includes neighbours with equal discretised grey level."),
    }

    for item in _NON_CT_ITEMS:
        reported[item] = {
            "label": _ITEM_LABELS[item],
            "status": "not_applicable",
            "value": None,
            "reason": "This is a CT-only analysis workflow.",
        }
    for item in _STUDY_LEVEL_ITEMS:
        reported.setdefault(
            item,
            _record(
                _ITEM_LABELS[item],
                reason="This study-level information is not collected by a single-image analysis run.",
            ),
        )

    if not discretization or discretization.get("method") != "fixed bin size":
        reported["56c"] = {
            "label": _ITEM_LABELS["56c"],
            "status": "not_applicable",
            "value": None,
            "reason": "The selected texture and intensity-histogram discretisation is not fixed-bin-size.",
        }

    for item, label in _ITEM_LABELS.items():
        reported.setdefault(
            item,
            _record(
                label,
                reason="This study-level or modality-specific information is not supplied to this CT analysis.",
            ),
        )
    ordered_items = {
        item: reported[item] for item in _ITEM_LABELS
    }
    status_counts: dict[str, int] = {}
    for record in ordered_items.values():
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "schema": "heeh-v1.ibsi-1-reporting-context",
        "guideline": "IBSI 1 radiomics reporting guidance, items 1-76",
        "scope": "CT single-image-volume feature extraction; study-level information is not inferred.",
        "status": "incomplete",
        "compliance_claim": "not_claimed",
        "dicom_metadata": dicom,
        "items": ordered_items,
        "status_counts": status_counts,
    }
