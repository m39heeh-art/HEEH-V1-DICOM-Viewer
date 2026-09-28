"""Optional model-backed anatomical segmentation adapters.

The adapters are deliberately opt-in. No heuristic mask is reported as an
anatomical organ label, and unavailable model runtimes fail explicitly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import requests


@dataclass(frozen=True)
class SegmentationStatus:
    backend: str
    available: bool
    detail: str


class AnatomicalSegmentation:
    """Run TotalSegmentator locally or a configured MONAI Label server."""

    def __init__(self, monai_label_url: str | None = None):
        self.monai_label_url = (
            monai_label_url or os.environ.get("MONAI_LABEL_URL", "")
        ).rstrip("/")

    @staticmethod
    def _totalsegmentator_command() -> str | None:
        return shutil.which("TotalSegmentator") or shutil.which("totalsegmentator")

    def statuses(self) -> list[SegmentationStatus]:
        total_cmd = self._totalsegmentator_command()
        return [
            SegmentationStatus(
                "TotalSegmentator",
                total_cmd is not None,
                f"Executable: {total_cmd}" if total_cmd else
                "Install TotalSegmentator and make its CLI available on PATH.",
            ),
            SegmentationStatus(
                "MONAI Label",
                bool(self.monai_label_url),
                f"Server: {self.monai_label_url}" if self.monai_label_url else
                "Set MONAI_LABEL_URL to a running MONAI Label server.",
            ),
        ]

    @staticmethod
    def _validate_volume(volume: np.ndarray) -> np.ndarray:
        array = np.asarray(volume)
        if array.ndim != 3:
            raise ValueError(
                "Anatomical segmentation requires a 3D volume, "
                f"received {array.ndim}D data."
            )
        if not np.isfinite(array).all():
            raise ValueError("Segmentation input contains non-finite voxels.")
        if min(array.shape) < 2:
            raise ValueError("Segmentation input contains an empty spatial axis.")
        return array.astype(np.float32, copy=False)

    @staticmethod
    def _load_masks(output_dir: Path) -> dict[str, np.ndarray]:
        masks: dict[str, np.ndarray] = {}
        for mask_path in sorted(output_dir.glob("*.nii*")):
            mask = np.asarray(nib.load(str(mask_path)).get_fdata())
            if mask.ndim != 3 or not np.isfinite(mask).all():
                raise ValueError(f"Invalid segmentation mask: {mask_path.name}")
            binary = (mask > 0).astype(np.uint8)
            if binary.any():
                masks[mask_path.stem.replace(".nii", "")] = binary
        if not masks:
            raise RuntimeError("The segmentation backend returned no non-empty masks.")
        return masks

    @staticmethod
    def _validate_masks(
        masks: dict[str, np.ndarray], shape: tuple[int, ...]
    ) -> dict[str, np.ndarray]:
        validated: dict[str, np.ndarray] = {}
        for name, mask in masks.items():
            array = np.asarray(mask)
            if array.shape != shape:
                raise ValueError(
                    f"Segmentation mask {name!r} has shape {array.shape}; "
                    f"expected {shape}."
                )
            if array.ndim != 3 or not np.isfinite(array).all():
                raise ValueError(f"Segmentation mask {name!r} is invalid.")
            binary = (array > 0).astype(np.uint8)
            if binary.any():
                validated[name] = binary
        if not validated:
            raise RuntimeError("The segmentation backend returned no valid masks.")
        return validated

    def segment_with_totalsegmentator(
        self,
        volume: np.ndarray,
        affine: np.ndarray | None = None,
        task: str = "total",
        timeout: int = 1800,
    ) -> dict[str, np.ndarray]:
        """Run the official TotalSegmentator CLI against a temporary NIfTI."""
        command = self._totalsegmentator_command()
        if not command:
            raise RuntimeError(
                "TotalSegmentator is unavailable. Install it and expose "
                "the TotalSegmentator CLI on PATH."
            )
        array = self._validate_volume(volume)
        affine_matrix = np.eye(4, dtype=np.float32) if affine is None else np.asarray(affine)
        if affine_matrix.shape != (4, 4):
            raise ValueError("Segmentation affine must be a 4x4 matrix.")
        with tempfile.TemporaryDirectory(prefix="neuro-seg-") as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.nii.gz"
            output_dir = root / "output"
            output_dir.mkdir()
            nib.save(nib.Nifti1Image(array, affine_matrix), str(input_path))
            try:
                completed = subprocess.run(
                    [command, "-i", str(input_path), "-o", str(output_dir), "--task", task],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"TotalSegmentator exceeded the {timeout}-second timeout."
                ) from exc
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()[-1000:]
                raise RuntimeError(
                    f"TotalSegmentator failed with exit code {completed.returncode}: {detail}"
                )
            return self._validate_masks(self._load_masks(output_dir), array.shape)

    def segment_with_monai_label(
        self,
        volume: np.ndarray,
        affine: np.ndarray | None = None,
        model: str = "segmentation",
        timeout: int = 1800,
    ) -> dict[str, np.ndarray]:
        """Call a configured MONAI Label server's standard ``/infer`` endpoint."""
        if not self.monai_label_url:
            raise RuntimeError(
                "MONAI Label is unavailable. Set MONAI_LABEL_URL to a running server."
            )
        array = self._validate_volume(volume)
        affine_matrix = np.eye(4, dtype=np.float32) if affine is None else np.asarray(affine)
        with tempfile.TemporaryDirectory(prefix="neuro-monai-label-") as temp_dir:
            input_path = Path(temp_dir) / "input.nii.gz"
            nib.save(nib.Nifti1Image(array, affine_matrix), str(input_path))
            with input_path.open("rb") as image_file:
                response = requests.post(
                    f"{self.monai_label_url}/infer",
                    params={"model": model},
                    files={"image": (input_path.name, image_file, "application/gzip")},
                    timeout=timeout,
                )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"MONAI Label inference failed ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            content_type = response.headers.get("content-type", "").lower()
            if "json" in content_type:
                payload: Any = response.json()
                if "result" not in payload:
                    raise RuntimeError("MONAI Label response did not contain a result.")
                result = payload["result"]
                if isinstance(result, dict):
                    masks = {
                        str(name): (np.asarray(mask) > 0).astype(np.uint8)
                        for name, mask in result.items()
                    }
                    return self._validate_masks(masks, array.shape)
                raise RuntimeError(
                    "MONAI Label JSON responses must contain a named result map."
                )
            result_path = Path(temp_dir) / "result.nii.gz"
            result_path.write_bytes(response.content)
            return self._validate_masks(self._load_masks(Path(temp_dir)), array.shape)
