"""Split module: ONNXInferenceEngine."""
import os
import numpy as np
import onnxruntime as ort

class ONNXInferenceEngine:
    """
    ONNX Runtime - محرك استدلال محسّن للنماذج العصبية.
    يتيح تشغيل نماذج ONNX على وحدات المعالجة المتاحة (CPU/GPU حسب المزود).
    """

    def __init__(self, model_path: str = None, providers: list = None):
        """Prepare the ONNX runtime session and provider list."""
        self.providers = providers or self._default_providers()
        self._session = None
        if model_path:
            self.load(model_path)

    @staticmethod
    def _default_providers() -> list:
        """Prefer CUDA only when the installed ONNX Runtime exposes it."""
        available = ort.get_available_providers()
        preferred = []
        if "CUDAExecutionProvider" in available:
            preferred.append("CUDAExecutionProvider")
        if "CPUExecutionProvider" in available:
            preferred.append("CPUExecutionProvider")
        return preferred or list(available)

    @staticmethod
    def available_providers() -> tuple[str, ...]:
        """Return providers exposed by the installed ONNX Runtime build."""
        return tuple(ort.get_available_providers())

    def load(self, model_path: str):
        """تحميل نموذج ONNX."""
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model not found: {model_path}")
        self._session = ort.InferenceSession(model_path, providers=self.providers)

    def infer(self, input_tensor: np.ndarray) -> np.ndarray:
        """استدلال باستخدام ONNX Runtime."""
        if self._session is None:
            raise RuntimeError("No ONNX model loaded. Call load() first.")
        input_name = self._session.get_inputs()[0].name
        output_name = self._session.get_outputs()[0].name
        return self._session.run([output_name], {input_name: input_tensor.astype(np.float32)})[0]

    def has_session(self) -> bool:
        """Return whether an ONNX model is currently loaded.

        Guards inference callers that must decide between the ONNX engine and
        a fallback path before invoking :meth:`infer`.
        """
        return self._session is not None

    @property
    def active_provider(self) -> str:
        """Return the provider used by the loaded session or the first default."""
        if self._session is not None:
            return self._session.get_providers()[0]
        return self.providers[0] if self.providers else "unknown"

    @property
    def cuda_enabled(self) -> bool:
        """Whether this engine can execute ONNX graphs through CUDA."""
        return self.active_provider == "CUDAExecutionProvider"
