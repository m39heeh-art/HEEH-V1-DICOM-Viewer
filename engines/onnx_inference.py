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
        # Bind by the session's declared input metadata: validates name AND
        # shape so a mismatched tensor fails loudly instead of producing a
        # garbage output (research results must be traceable to the model
        # contract, per the ONNX Runtime input-spec conventions).
        model_input = self._session.get_inputs()[0]
        output_name = self._session.get_outputs()[0].name
        array = np.asarray(input_tensor)
        expected_shape = tuple(
            dim if isinstance(dim, int) and dim > 0 else None
            for dim in model_input.shape
        )
        if array.ndim != len(expected_shape):
            raise ValueError(
                "ONNX input rank mismatch: model expects "
                f"{len(expected_shape)}D, received {array.ndim}D."
            )
        for axis, (expected, actual) in enumerate(zip(expected_shape, array.shape)):
            if expected is not None and expected != actual:
                raise ValueError(
                    f"ONNX input shape mismatch on axis {axis}: model expects "
                    f"{expected}, received {actual}."
                )
        dtype = np.float32 if np.issubdtype(array.dtype, np.floating) else array.dtype
        return self._session.run([output_name], {model_input.name: array.astype(dtype)})[0]

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
