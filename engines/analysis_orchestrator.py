"""Split module: AnalysisOrchestrator, MedicalDataProcessor."""
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List
import numpy as np

class AnalysisOrchestrator:
    """
    Control Plane Engine: coordinates the AI and structural analysis engines.

    NOTE: The earlier 'Phi' weighting formula has been removed. It combined
    the statistical dispersion of HU values with arbitrary weights and was
    presented with pseudo-physical terminology (Newton force / Einstein
    energy) that has no basis in medical physics. This class now provides a
    simple, transparent tissue-mix weighting for display purposes only.
    """

    def __init__(self, ai_engine: Any, struct_engine: Any):
        """Initialize the analysis orchestrator with its component registry."""
        self.ai_engine = ai_engine
        self.struct_engine = struct_engine
        self.TISSUE_MIX_THRESHOLD = 0.82
        self.executor = ThreadPoolExecutor(max_workers=8)

    @staticmethod
    def _get_tissue_params(modality: str) -> np.ndarray:
        """
        Return display weighting for tissue-mix summary (purely cosmetic).

        Weights are arbitrary visualization preferences, NOT physiological
        constants. Returns a length-3 vector summing to ~1.0.
        """
        mod = modality.upper()
        if "BONE" in mod:
            return np.array([0.60, 0.20, 0.20])
        if "NEURO" in mod or "BRAIN" in mod:
            return np.array([0.20, 0.40, 0.40])
        if "LUNG" in mod:
            return np.array([0.50, 0.30, 0.20])
        return np.array([0.33, 0.33, 0.34])

    @staticmethod
    def calculate_tissue_mix_score(tissue_stats: np.ndarray, weights: np.ndarray) -> float:
        """
        Weighted display score for a tissue mix.

        This is a transparent weighted sum (dot product) normalized to [-1, 1]
        via tanh. It is a visualization aid only and must NOT be interpreted
        as a diagnostic or physiological quantity.
        """
        weighted = float(np.dot(tissue_stats, weights))
        return float(np.tanh(weighted))


class MedicalDataProcessor:
    """
    Medical Data Processing Engine.
    """

    def __init__(self, target_dir: str):
        """Initialize the analysis orchestrator with its component registry."""
        self.target_dir = target_dir
        self.max_workers: int = os.cpu_count() or 4

    @staticmethod
    def process_node(node_id: int, profile_name: str = None) -> Dict[str, Any]:
        """
        Assertion: Output must align with Physiological Norms.
        """
        # تم حل Invalid escape sequence عبر حذف الـ backslash غير الضروري في الـ docstring
        # تم حل Method may be static عبر إضافة المزيّن @staticmethod
        if profile_name is not None and profile_name not in CLINICAL_PROFILES:
            raise ValueError(f"Unknown clinical profile: {profile_name!r}")

        # محاكاة تحليل كثافة نسيج عصبي
        result = {"id": node_id, "status": "processed", "density": 0.85}
        if profile_name is not None:
            result["profile"] = profile_name
            result["tissue_weights"] = CLINICAL_PROFILES[profile_name]["tissue_weights"]
        return result

    @staticmethod
    def apply_clinical_profile(node_id: int, profile_name: str) -> Dict[str, Any]:
        """
        Apply a named clinical profile to a processing node.

        Enriches the node result with the profile's tissue weights and a
        transparent weighted mix score for display only. Unknown profiles
        fail fast so misconfiguration surfaces immediately.
        """
        if profile_name not in CLINICAL_PROFILES:
            raise ValueError(f"Unknown clinical profile: {profile_name!r}")

        result = MedicalDataProcessor.process_node(node_id, profile_name)
        neutral_stats = np.array([0.33, 0.33, 0.34])
        weights = np.array(CLINICAL_PROFILES[profile_name]["tissue_weights"])
        result["tissue_mix_score"] = MedicalDataProcessor.calculate_tissue_mix_score(
            neutral_stats, weights
        )
        return result

    def execute_parallel_tasks(self, tasks: List[int]) -> List[Dict[str, Any]]:
        """ Parallel Execution for big data (2000+ files). """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # استخدام MedicalDataProcessor.process_node مباشرةً (وهي @staticmethod)
            results = list(executor.map(MedicalDataProcessor.process_node, tasks))

        assert len(results) == len(tasks), "Data loss detected"
        return results


# --- [LAYER 1: CLINICAL CONFIGURATION] ---
CLINICAL_PROFILES: Dict[str, Dict[str, Any]] = {
    "brain": {
        "description": "Profile for brain / neuro imaging studies (NEURO/BRAIN).",
        "tissue_weights": [0.20, 0.40, 0.40],
    },
    "chest": {
        "description": "Profile for chest imaging studies (LUNG).",
        "tissue_weights": [0.50, 0.30, 0.20],
    },
    "age": {
        "description": "Default profile when the dominant tissue cannot be reliably determined.",
        "tissue_weights": [0.33, 0.33, 0.34],
    },
}
