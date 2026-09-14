"""
Modality Registry - Central authority for supported medical imaging modalities.

Each ModalitySpec defines:
  - DICOM identifiers (Modality tag, SOP Class UIDs)
  - Data characteristics (pixel representation, bits stored, intensity units)
  - Supported calculations and equations
  - Reference standards (IEC, ACR, NEMA, etc.)

This module is the single source of truth for which modalities the system
supports, and what validated calculations are available for each.

Reference: DICOM PS3.3 Table C.3-1 (Defined Terms for Modality).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ModalitySpec:
    """Immutable specification for a supported medical imaging modality."""

    name: str
    dicom_modality: str
    sop_classes: List[str]
    sub_type: Optional[str] = None
    supported: bool = True
    reject_display: bool = False

    rescale_required: bool = False
    hu_conversion: bool = False
    intensity_units: str = "raw"

    windowing_presets: List[str] = field(default_factory=list)
    required_dicom_tags: List[str] = field(default_factory=list)
    quantitative_metrics: List[str] = field(default_factory=list)
    reference_standards: List[str] = field(default_factory=list)

    def get_required_dicom_tags(self) -> List[str]:
        """Return the DICOM tags that must be present for a valid series.

        Used by the ingestion pipeline to reject incomplete studies before any
        pixel processing begins.
        """
        return list(self.required_dicom_tags)


# ---------------------------------------------------------------------------
# SOP Class UIDs (DICOM PS3.6 / IANA OID registry)
# ---------------------------------------------------------------------------
SOP_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
SOP_ENHANCED_CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2.1"
SOP_MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"
SOP_US_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.6.1"
SOP_PET_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.128"
SOP_XA_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.12.1"
SOP_CR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.1"
SOP_DX_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.1.1"

# Common DICOM transfer syntaxes. Decoding still depends on the installed
# pydicom pixel-data handler and is reported rather than assumed.
TRANSFER_SYNTAX_IMPLICIT_VR_LE = "1.2.840.10008.1.2"
TRANSFER_SYNTAX_EXPLICIT_VR_LE = "1.2.840.10008.1.2.1"
TRANSFER_SYNTAX_JPEG_LOSSLESS = "1.2.840.10008.1.2.4.70"
TRANSFER_SYNTAX_JPEG2000_LOSSLESS = "1.2.840.10008.1.2.4.90"
TRANSFER_SYNTAX_HTJ2K_LOSSLESS = "1.2.840.10008.1.2.4.201"
SOP_MG_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.1.2"
SOP_RT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.1"
SOP_RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"
SOP_RT_STRUCT_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
SOP_RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
SOP_NM_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.20"
SOP_US_MULTIFRAME = "1.2.840.10008.5.1.4.1.1.3.1"
SOP_ROI_STORAGE = "1.2.840.10008.5.1.4.1.1.481.8"
SOP_SPECT_STORAGE = "1.2.840.10008.5.1.4.1.1.20.1"

# Ophthalmic
SOP_OCT_FUNDUS = "1.2.840.10008.5.1.4.1.1.77.1.54"
SOP_OPTICAL_PHOTO = "1.2.840.10008.5.1.4.1.1.77.1.1"
SOP_OPHTHALMIC_TOMOGRAPHY_STORAGE = "1.2.840.10008.5.1.4.1.1.77.1.11"

# Slide Microscopy
SOP_SM_STORAGE = "1.2.840.10008.5.1.4.1.1.77.1.2"

# Radiofluoroscopy
SOP_RF_STORAGE = "1.2.840.10008.5.1.4.1.1.12.2"

# Intra-oral
SOP_IO_STORAGE = "1.2.840.10008.5.1.4.1.1.1.3"

# Intravascular
SOP_IVUS_STORAGE = "1.2.840.10008.5.1.4.1.1.12.4"
SOP_IVOCT_STORAGE = "1.2.840.10008.5.1.4.1.1.12.5"

# Bone densitometry
SOP_BDUS_STORAGE = "1.2.840.10008.5.1.4.1.1.6.2"

# Digital Breast Tomosynthesis
SOP_DBT_STORAGE = "1.2.840.10008.5.1.4.1.1.13.1.3"
SOP_BREAST_PROJ = "1.2.840.10008.5.1.4.1.1.13.1.5"

# Structural DICOM (NOT for display)
SOP_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.22"
SOP_SR_COMPREHENSIVE = "1.2.840.10008.5.1.4.1.1.88.33"
SOP_SR_KEY_OBJECT = "1.2.840.10008.5.1.4.1.1.88.59"
SOP_SR_BASIC_TEXT = "1.2.840.10008.5.1.4.1.1.88.11"
SOP_ENCAPS_PDF = "1.2.840.10008.5.1.4.1.1.104.1.1.2"
SOP_ENCAPS_CDA = "1.2.840.10008.5.1.4.1.1.104.1.1.3"
SOP_ENCAPS_STL = "1.2.840.10008.5.1.4.1.1.104.1.3"
SOP_HANGING_PROTOCOL = "1.2.840.10008.5.1.4.1.1.200.2"
SOP_PSEUDO_COLOR = "1.2.840.10008.5.1.4.1.1.77.1.6"
SOP_BLENDING_ROI = "1.2.840.10008.5.1.4.1.1.481.8"


# ---------------------------------------------------------------------------
# Modalities that are structural DICOM and must never be displayed
# ---------------------------------------------------------------------------
REJECT_DISPLAY_MODALITIES = frozenset({
    "RTPLAN", "RTSTRUCT", "RTRECORD",
    "HANGING_PROTOCOL",
    "BASIC_TEXT_SR", "ENHANCED_SR", "COMPREHENSIVE_SR",
    "KEY_OBJECT_SEL", "MEASUREMENT_REPORT",
    "ENCAPSULATED_PDF", "ENCAPSULATED_CDA",
    "PSEUDO_COLOR", "BLENDED_ROI",
})


# ---------------------------------------------------------------------------
# Primary modality registry
# ---------------------------------------------------------------------------
MODALITY_REGISTRY = {

    "CT": ModalitySpec(
        name="Computed Tomography",
        dicom_modality="CT",
        sop_classes=[SOP_CT_IMAGE_STORAGE, SOP_ENHANCED_CT_IMAGE_STORAGE],
        rescale_required=True,
        hu_conversion=True,
        intensity_units="HU",
        windowing_presets=[
            "lung", "bone", "brain", "soft_tissue", "vascular_cta",
            "venography", "neurovascular", "temporal_bone", "spine_bone",
            "abdomen", "mediastinum",
        ],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "RescaleSlope", "RescaleIntercept", "PhotometricInterpretation"],
        quantitative_metrics=[
            "HU_statistics", "noise", "uniformity", "SNR_CNR",
            "NPS", "MTF", "CTDIvol", "DLP", "exposure_index",
            "low_contrast_detectability", "tissue_classification",
        ],
        reference_standards=[
            "ACR_CT_Accreditation", "IEC_61223", "IEC_60601-2-44",
            "NEMA_XR-25", "AAPM_TG116", "AAPM_TG233",
        ],
    ),

    "MR": ModalitySpec(
        name="Magnetic Resonance",
        dicom_modality="MR",
        sop_classes=[SOP_MR_IMAGE_STORAGE],
        intensity_units="stored_signal",
        windowing_presets=["mri_t1", "mri_t2", "mri_flair"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "PhotometricInterpretation"],
        quantitative_metrics=[
            "SNR_NEMA", "CNR", "uniformity_integral",
            "ghosting_ratio", "geometric_accuracy", "slice_thickness",
            "T1_mapping", "T2_mapping", "ADC_mapping", "MRS",
            "diffusion_analysis", "perfusion_analysis",
        ],
        reference_standards=[
            "ACR_MRI_Accreditation", "IEC_60601-2-33",
            "NEMA_MS_1", "NEMA_MS_2",
        ],
    ),

    "PT": ModalitySpec(
        name="Positron Emission Tomography",
        dicom_modality="PT",
        sop_classes=[SOP_PET_IMAGE_STORAGE],
        intensity_units="stored_or_calibrated_activity",
        windowing_presets=["pet_suv"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "CorrectedImage", "DecayCorrection", "Units",
                            "PatientWeight"],
        quantitative_metrics=[
            "SUVbw", "SUVlbm", "SUVbsa", "SUVibw",
            "SUVmax", "SUVmean", "SUVpeak",
            "METABOLIC_VOLUME", "TLG",
            "kinetic_modeling", "recovery_correction",
        ],
        reference_standards=[
            "EANM_EANMFDG_QC_2015", "SNMMI", "PERCIST",
            "NEMA_NU_2_2018",
        ],
    ),

    "US": ModalitySpec(
        name="Ultrasound",
        dicom_modality="US",
        sop_classes=[SOP_US_IMAGE_STORAGE, SOP_US_MULTIFRAME],
        intensity_units="stored_signal",
        windowing_presets=["us"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated"],
        quantitative_metrics=[
            "axial_resolution", "lateral_resolution", "doppler_velocity",
            "elastography_strain", "shear_wave_speed",
            "contrast_perfusion", "frame_rate", "depth",
        ],
        reference_standards=[
            "AIUM", "IEC_60601-2-37", "WFUMB",
        ],
    ),

    "XA": ModalitySpec(
        name="X-Ray Angiography",
        dicom_modality="XA",
        sop_classes=[SOP_XA_IMAGE_STORAGE],
        intensity_units="raw",
        windowing_presets=["angio"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "XRayTubecurrent", "XRayTubeVoltage"],
        quantitative_metrics=[
            "vessel_diameter", "stenosis_percent", "TIMI_frame_count",
            "QCA_absolute", "QCA_relative", "frame_rate",
        ],
        reference_standards=["ACC_AHA", "SCAI", "EBC"],
    ),

    "CR": ModalitySpec(
        name="Computed Radiography",
        dicom_modality="CR",
        sop_classes=[SOP_CR_IMAGE_STORAGE],
        intensity_units="raw",
        windowing_presets=["chest", "bone", "abdomen"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "PhotometricInterpretation", "Exposure"],
        quantitative_metrics=[
            "exposure_index", "deviation_index",
            "contrast_resolution", "spatial_resolution",
        ],
        reference_standards=["IEC_62220-1", "AAPM_TG116"],
    ),

    "DX": ModalitySpec(
        name="Digital Radiography",
        dicom_modality="DX",
        sop_classes=[SOP_DX_IMAGE_STORAGE],
        intensity_units="raw",
        windowing_presets=["chest", "bone", "abdomen", "spine"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "PhotometricInterpretation", "Exposure",
                            "BodyPartExamined"],
        quantitative_metrics=[
            "exposure_index", "deviation_index", "DQE", "MTF",
            "contrast_resolution", "spatial_resolution",
        ],
        reference_standards=["IEC_62220-1", "IEC_62220-1-1"],
    ),

    "MG": ModalitySpec(
        name="Mammography",
        dicom_modality="MG",
        sop_classes=[SOP_MG_IMAGE_STORAGE, SOP_DBT_STORAGE, SOP_BREAST_PROJ],
        intensity_units="raw",
        windowing_presets=["mammo"],
        required_dicom_tags=["Modality", "Rows", "Columns", "BitsAllocated",
                            "PhotometricInterpretation", "CompressionForce",
                            "BreastImplantPresent"],
        quantitative_metrics=[
            "AGD", "glandular_dose", "contrast_detail",
            "BI-RADS_density", "exposure_index",
        ],
        reference_standards=[
            "MQSA", "ACR_Mammography", "IEC_60601-2-45",
            "EUREF", "ACR_BI-RADS_5th",
        ],
    ),

    "RTIMAGE": ModalitySpec(
        name="RT Image (Portal Imaging)",
        dicom_modality="RTIMAGE",
        sop_classes=[SOP_RT_IMAGE_STORAGE],
        intensity_units="raw",
        windowing_presets=["portal"],
        required_dicom_tags=["Modality", "Rows", "Columns"],
        quantitative_metrics=[
            "MU_verification", "field_alignment",
            "contrast_resolution", "spatial_resolution",
        ],
        reference_standards=["AAPM_TG142", "IEC_62220-1"],
    ),

    "RTDOSE": ModalitySpec(
        name="RT Dose",
        dicom_modality="RTDOSE",
        sop_classes=[SOP_RT_DOSE_STORAGE],
        intensity_units="GY",
        windowing_presets=["dose"],
        required_dicom_tags=["Modality", "Rows", "Columns",
                            "GridFrameOffsetVector", "DoseGridScaling",
                            "PixelRepresentation"],
        quantitative_metrics=[
            "DVH", "D95", "D2", "Dmean", "V95", "V20",
            "conformity_index", "homogeneity_index",
            "gradient_index",
        ],
        reference_standards=["ICRU_83", "AAPM_TG119", "ICRU_50"],
    ),

    "RTSTRUCT": ModalitySpec(
        name="RT Structure Set",
        dicom_modality="RTSTRUCT",
        sop_classes=[SOP_RT_STRUCT_STORAGE],
        reject_display=True,
        required_dicom_tags=["Modality"],
        quantitative_metrics=[],
        reference_standards=["DICOM_RT"],
    ),

    "RTPLAN": ModalitySpec(
        name="RT Plan",
        dicom_modality="RTPLAN",
        sop_classes=[SOP_RT_PLAN_STORAGE],
        reject_display=True,
        required_dicom_tags=["Modality"],
        quantitative_metrics=[],
        reference_standards=["DICOM_RT"],
    ),

    "NM": ModalitySpec(
        name="Nuclear Medicine",
        dicom_modality="NM",
        sop_classes=[SOP_NM_IMAGE_STORAGE, SOP_SPECT_STORAGE],
        intensity_units="counts",
        windowing_presets=["nm"],
        required_dicom_tags=["Modality", "Rows", "Columns",
                            "CollimatorType", "SliceThickness",
                            "ActualFrameDuration"],
        quantitative_metrics=[
            "counts", "uptake", "geometric_mean",
            "background_subtraction", "organ_uptake",
        ],
        reference_standards=["EANM", "SNMMI"],
    ),

    "OCT": ModalitySpec(
        name="Optical Coherence Tomography",
        dicom_modality="OCT",
        sop_classes=[SOP_OCT_FUNDUS, SOP_OPHTHALMIC_TOMOGRAPHY_STORAGE],
        intensity_units="raw",
        windowing_presets=["oct_retina", "oct_anterior"],
        required_dicom_tags=["Modality", "Rows", "Columns",
                            "Wavelengths"],

        quantitative_metrics=[
            "retinal_thickness", "RNFL_thickness",
            "cup_disc_ratio", "macular_thickness",
        ],
        reference_standards=["ISO_17309"],
    ),

    "OPTICAL": ModalitySpec(
        name="Ophthalmic Photography",
        dicom_modality="OPTICAL",
        sop_classes=[SOP_OPTICAL_PHOTO],
        intensity_units="raw",
        windowing_presets=["fundus"],
        required_dicom_tags=["Modality", "Rows", "Columns"],
        quantitative_metrics=[
            "cup_disc_ratio", "vessel_caliber",
            "nerve_fiber_layer",
        ],
        reference_standards=["ISO_10940"],
    ),

    "SM": ModalitySpec(
        name="Slide Microscopy",
        dicom_modality="SM",
        sop_classes=[SOP_SM_STORAGE],
        intensity_units="raw",
        windowing_presets=["h_e", "ihc"],
        required_dicom_tags=["Modality", "Rows", "Columns", "TotalPixelMatrixColumns"],
        quantitative_metrics=[
            "cell_count", "mitotic_count", "ki67_index",
            "nuclear_cytoplasmic_ratio",
        ],
        reference_standards=["DICOM_WSI", "CAP_ASCP"],
    ),

    "RF": ModalitySpec(
        name="Radiofluoroscopy",
        dicom_modality="RF",
        sop_classes=[SOP_RF_STORAGE],
        intensity_units="raw",
        windowing_presets=["fluoro"],
        required_dicom_tags=["Modality", "Rows", "Columns"],
        quantitative_metrics=[
            "frame_rate", "exposure", "spatial_resolution",
        ],
        reference_standards=["IEC_60601-2-43"],
    ),

    "IO": ModalitySpec(
        name="Intra-oral Radiography",
        dicom_modality="IO",
        sop_classes=[SOP_IO_STORAGE],
        intensity_units="raw",
        windowing_presets=["dental"],
        required_dicom_tags=["Modality", "Rows", "Columns"],
        quantitative_metrics=[
            "bone_level", "caries_detection",
            "periodontal_measures",
        ],
        reference_standards=["ISO_6874"],
    ),

    "BDUS": ModalitySpec(
        name="Bone Densitometry Ultrasound",
        dicom_modality="BDUS",
        sop_classes=[SOP_BDUS_STORAGE],
        intensity_units="raw",
        windowing_presets=[],
        required_dicom_tags=["Modality", "Rows", "Columns"],
        quantitative_metrics=[
            "BUA", "SOS", "QUS_index",
        ],
        reference_standards=["ISCD"],
    ),

    "IVUS": ModalitySpec(
        name="Intravascular Ultrasound",
        dicom_modality="IVUS",
        sop_classes=[SOP_IVUS_STORAGE],
        intensity_units="raw",
        windowing_presets=["ivus"],
        required_dicom_tags=["Modality", "Rows", "Columns",
                            "PullbackSpeed", "CenterFrequency"],
        quantitative_metrics=[
            "lumen_area", "eem_area", "plaque_burden",
            "remodeling_index", "stent_apposition", "MLA",
            "virtual_histology",
        ],
        reference_standards=["ACC_IVUS", "ESC_IVUS"],
    ),

    "IVOCT": ModalitySpec(
        name="Intravascular OCT",
        dicom_modality="IVOCT",
        sop_classes=[SOP_IVOCT_STORAGE],
        intensity_units="raw",
        windowing_presets=["ivoct"],
        required_dicom_tags=["Modality", "Rows", "Columns",
                            "PullbackSpeed", "Wavelength"],
        quantitative_metrics=[
            "lumen_area", "plaque_burden",
            "fibrous_cap_thickness", "macrophage_infiltration",
            "stent_apposition", "neointimal_area",
        ],
        reference_standards=["ICR_OCT", "ACC_OCT"],
    ),

    "SPECT": ModalitySpec(
        name="SPECT (Single Photon Emission CT)",
        dicom_modality="SPECT",
        sop_classes=[SOP_SPECT_STORAGE],
        intensity_units="counts",
        windowing_presets=["spect"],
        required_dicom_tags=["Modality", "Rows", "Columns",
                            "CollimatorType", "SliceThickness"],
        quantitative_metrics=[
            "counts", "SUV_equivalent", "defect_extent",
            "severity_score", "gated_SPECT", "phase_analysis",
        ],
        reference_standards=["EANM", "ASNC", "ACR_SPECT"],
    ),

    "OP": ModalitySpec(
        name="Ophthalmology Keratometry/Topography",
        dicom_modality="OP",
        sop_classes=[SOP_OPTICAL_PHOTO],
        sub_type="KER",
        intensity_units="raw",
        windowing_presets=["corneal_topo"],
        required_dicom_tags=["Modality", "Rows", "Columns"],
        quantitative_metrics=[
            "K1", "K2", "K_max", "K_min",
            "astigmatism", "corneal_thickness", "eccentricity",
            "topographic_cylinder", "axis",
        ],
        reference_standards=["ISO_17284"],
    ),
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_supported_modalities() -> List[str]:
    """Return sorted list of supported (non-rejected) modality keys."""
    return sorted(k for k, v in MODALITY_REGISTRY.items()
                  if v.supported and not v.reject_display)


def get_all_modalities() -> List[str]:
    """Return sorted list of all registered modality keys."""
    return sorted(MODALITY_REGISTRY.keys())


def get_rejected_modalities() -> List[str]:
    """Return sorted list of rejected (structural-only) modality keys."""
    return sorted(k for k, v in MODALITY_REGISTRY.items()
                  if v.reject_display)


def get_spec(modality: str) -> Optional[ModalitySpec]:
    """Look up a modality spec.  Returns None if not found."""
    return MODALITY_REGISTRY.get(modality.upper())


def is_supported(modality: str) -> bool:
    """Check if a modality is supported for display and analysis."""
    spec = get_spec(modality)
    if spec is None:
        return False
    return spec.supported and not spec.reject_display


def is_rejected(modality: str) -> bool:
    """Check if a modality is structural-only and must not be displayed."""
    spec = get_spec(modality)
    if spec is None:
        return False
    return spec.reject_display


_GENERIC_IMAGE_CAPABILITIES = frozenset({
    "edge_detection",
    "advanced_processing",
    "volumetric",
})
_QUALITY_MODALITIES = frozenset({"CT", "MR", "PT"})
_RADIOMICS_MODALITIES = frozenset({"CT", "MR"})
_AI_MODALITIES = frozenset({"CT", "MR", "PT"})
_CAPABILITY_KEYS = (
    "ct_windowing",
    "ct_tissue",
    "edge_detection",
    "quality",
    "radiomics",
    "ai_inference",
    "advanced_processing",
    "volumetric",
)


def get_feature_capabilities(modality: str) -> dict[str, bool]:
    """Return the conservative analysis capabilities for a modality.

    Capabilities are kept beside the modality registry so the active UI and
    execution paths cannot drift into separate modality policy tables.
    Unknown and mixed inputs intentionally expose no optional features.
    """
    raw_modality = str(modality or "").strip()
    if "/" in raw_modality:
        raw_modality = raw_modality.rsplit("/", 1)[-1].strip()
    key = resolve_modality(raw_modality)
    if key is None or not is_supported(key):
        # A non-DICOM volume can still be safely displayed and measured with
        # modality-neutral operations, but must not receive modality-specific
        # units or clinical equations.
        if raw_modality.upper() in {"VOLUME", "NIFTI", "NRRD", "MHA", "MHD"}:
            return {
                name: name in {"edge_detection", "advanced_processing", "volumetric"}
                for name in _CAPABILITY_KEYS
            }
        return {name: False for name in _CAPABILITY_KEYS}

    capabilities = {
        name: name in _GENERIC_IMAGE_CAPABILITIES
        for name in (
            "ct_windowing",
            "ct_tissue",
            "edge_detection",
            "quality",
            "radiomics",
            "ai_inference",
            "advanced_processing",
            "volumetric",
        )
    }
    capabilities["ct_windowing"] = key == "CT"
    capabilities["ct_tissue"] = key == "CT"
    capabilities["quality"] = key in _QUALITY_MODALITIES
    capabilities["radiomics"] = key in _RADIOMICS_MODALITIES
    capabilities["ai_inference"] = key in _AI_MODALITIES
    return capabilities


def get_available_features(modality: str) -> list[str]:
    """Return only calculations and tools implemented for ``modality``.

    Registry ``quantitative_metrics`` entries describe the scientific scope of
    a modality and may require future metadata-specific implementations. This
    function deliberately reports the smaller set that the application can
    execute today, preventing the UI from promising unimplemented equations.
    """
    caps = get_feature_capabilities(modality)
    features: list[str] = []
    if any(caps.values()):
        features.append("Native-intensity statistics")
    if caps["ct_windowing"]:
        features.append("CT Hounsfield-unit windowing")
    if caps["ct_tissue"]:
        features.extend([
            "CT tissue composition",
            "CT dose and exposure metrics (when DICOM metadata is present)",
        ])
    if caps["quality"]:
        features.append("Image-quality proxies: noise, uniformity, and SNR/CNR")
    if caps["radiomics"]:
        features.append("Radiomics-style histogram and texture features")
    if caps["edge_detection"]:
        features.append("Sobel, Canny, and gradient edge maps")
    if caps["volumetric"]:
        features.append("MIP/MPR/3D volume visualization")
    if caps["ai_inference"]:
        features.append("Demonstration AI inference (research only)")
    if caps["advanced_processing"]:
        features.append("MONAI preprocessing and SimpleITK registration")
    return features


def get_modality_aliases() -> dict:
    """Return a dict mapping common aliases to canonical modality keys."""
    return {
        "mr": "MR",
        "mri": "MR",
        "mri_t1": "MR",
        "mri_t2": "MR",
        "mri_flair": "MR",
        "pet": "PT",
        "pet_suv": "PT",
        "pt_suv": "PT",
        "ultrasound": "US",
        "echo": "US",
        "speckle": "US",
        "spect": "SPECT",
        "nm_planar": "NM",
        "scintigraphy": "NM",
        "dental": "IO",
        "oral": "IO",
        "fluoro": "RF",
        "cine": "XA",
        "angio": "XA",
        "microscopy": "SM",
        "pathology": "SM",
        "whole_slide": "SM",
        "retina": "OCT",
        "octa": "OCT",
        "fundus_photo": "OPTICAL",
        "topography": "OP",
        "keratometry": "OP",
        "ivus_bmode": "IVUS",
        "vhistology": "IVUS",
        "oct_ivl": "IVOCT",
        "bone_density": "BDUS",
        "qus": "BDUS",
    }


def resolve_modality(name: str) -> Optional[str]:
    """Resolve a modality name (case-insensitive) to its canonical key.

    Steps:
      1. Direct match in MODALITY_REGISTRY
      2. Alias lookup
      3. Partial prefix match (e.g. 'CT' in 'CT_HEAD')
    """
    if not name:
        return None
    key = name.strip().upper()
    if key in MODALITY_REGISTRY:
        return key
    aliases = get_modality_aliases()
    if key.lower() in aliases:
        return aliases[key.lower()]
    for reg_key in MODALITY_REGISTRY:
        if key.startswith(reg_key):
            return reg_key
    return None
