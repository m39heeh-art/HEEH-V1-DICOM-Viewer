"""
Core constants for the HEEH-V1™ DICOM Viewer.

NOTE: This software is a research/education tool. It is NOT a certified
medical device and must NOT be used for clinical diagnosis or treatment.

Physiological norms based on the standard CT Hounsfield Unit (HU) scale
(American College of Radiology - CT Accreditation Program; Kalender,
"Computed Tomography", 2nd ed.). The HU scale is defined by
water = 0 HU and air = -1000 HU.
"""

# Hounsfield Unit (HU) practical display range.
# Water = 0 HU, air = -1000 HU. CT scanners conventionally store HU in
# the 12-bit signed range [-1024, 3071]. Values outside this range are
# almost always artifacts (e.g. metal/beam-hardening or corrupted data).
HU_MIN: float = -1024.0
HU_MAX: float = 3071.0

# Pure-Gray Rendering Color
PURE_GRAY: str = "#808080"

# Research/education thresholds (NOT clinical acceptance criteria).
# These values are configurable defaults tuned for interactive research use;
# they are advisory UI gates, not validated clinical cutoffs.
PROBABILITY_THRESHOLD: float = 0.80
TISSUE_MIX_THRESHOLD: float = 0.82
CONFIDENCE_THRESHOLD: float = 0.85

# Statistical Thresholds
MIN_VOXELS_FOR_ANALYSIS: int = 100
STATISTICAL_POWER_THRESHOLD: int = 100
CI_CONFIDENCE_LEVEL: float = 0.95

# Research/education standards-conformance matrix identifiers.
# Each metric family implemented in this suite maps onto the international
# standards listed here; the full metric -> standard -> code -> test mapping is
# documented in docs/evaluation_updated_ar.md and mirrored inline in each
# module docstring. These are research references, NOT certification claims.
REFERENCE_STANDARDS: tuple = (
    "ACR CT Accreditation Program",
    "IEC 61223 series",
    "IEC 60601-2-44",
    "NEMA XR-25",
    "AAPM TG-116",
    "AAPM TG-150",
    "AAPM TG-233",
    "Kalender, Computed Tomography (2nd ed.)",
    "Rose criterion (CNR >= 5)",
)

# Structural Analysis Thresholds
HESSIAN_SIGMA_SCALES: tuple = (0.5, 1.5, 3.0)
HESSIAN_SIGMA_SINGLE: float = 1.2
PERCENTILE_CLIP: float = 99.5
L2_MAX_THRESHOLD: float = 15000.0
L2_MAX_BASE_ANALYSIS: float = 12000.0

# Tissue Classification Ranges (HU)
TISSUE_RANGES: dict = {
    "Air": (-1024, -950),
    "Lung": (-950, -500),
    "SoftTissueLow": (-500, -150),
    "Fat": (-150, -50),
    "Fluid": (-50, -10),
    "Water": (-10, 15),
    "SoftTissue": (15, 100),
    "DenseSoftTissue": (100, 200),
    "Bone": (200, 1500),
    "DenseBone": (1500, 3071),
}

# Display Presets (center, width)
DISPLAY_PRESETS: dict = {
    "lung": (-600, 1500),
    "bone": (400, 2000),
    "brain": (40, 80),
    "soft_tissue": (50, 400),
    "vascular_cta": (300, 700),
    "venography": (150, 500),
    "neurovascular": (100, 400),
    "temporal_bone": (700, 4000),
    "spine_bone": (350, 1800),
    "abdomen": (50, 400),
    "mediastinum": (40, 400),
    "mri_t1": (600, 1200),
    "mri_t2": (420, 840),
    "mri_flair": (450, 900),
    "pet_suv": (3, 8),
    "us": (50, 100),
}

# AI Model Registry (HuggingFace model IDs used for demonstration ONLY).
# These are publicly available research models. They are NOT FDA/CE
# certified and must NOT be used for clinical diagnosis.
AI_MODEL_REGISTRY: dict = {
    "chest": "lukas-blecher/vit-small-patch16-224-chest-xray-classification",
    "brain": "Ananthu-A/vit-brain-tumor-classification",
    "age": "nateraw/vit-age-classifier",
}

# Supported File Extensions
VALID_EXTENSIONS: tuple = ('.dcm', '.nii', '.nii.gz', '.nrrd', '.mha')

# Default Configuration
DEFAULT_TARGET_SIZE: tuple[int, int, int] = (128, 128, 128)
DEFAULT_MONAI_SPACING: tuple = (1.0, 1.0, 1.0)
DEFAULT_MAX_WORKERS: int = 8

# Display Dimensions
DISPLAY_W: int = 700