"""Split module: VolumeVisualizer."""
from typing import Optional
import numpy as np

class VolumeVisualizer:
    """
    تصور ثلاثي الأبعاد للصور الحجمية (Volumetric Data).
    يدعم: MIP (Maximum Intensity Projection)، MPR (Multi-Planar Reconstruction).
    """

    @staticmethod
    def _ensure_3d(data: np.ndarray) -> np.ndarray:
        """Return a 3D numpy volume, reshaping 2D input to a slice volume."""
        volume = np.asarray(data)
        if volume.ndim == 2:
            volume = volume[np.newaxis, ...]
        elif volume.ndim > 3:
            # Keep the first spatial three dimensions and select the first
            # component from trailing time/channel dimensions.
            while volume.ndim > 3:
                volume = np.take(volume, 0, axis=-1)
        if volume.ndim != 3 or 0 in volume.shape:
            raise ValueError(f"Expected a non-empty 2D/3D volume, got {volume.shape}")
        return volume

    @staticmethod
    def mip(data: np.ndarray, axis: int = 0) -> np.ndarray:
        """Maximum Intensity Projection على محور معين."""
        vol = VolumeVisualizer._ensure_3d(data)
        axis = int(axis) % 3
        return np.max(vol, axis=axis)

    @staticmethod
    def minip(data: np.ndarray, axis: int = 0) -> np.ndarray:
        """Minimum Intensity Projection."""
        vol = VolumeVisualizer._ensure_3d(data)
        axis = int(axis) % 3
        return np.min(vol, axis=axis)

    @staticmethod
    def mpr(data: np.ndarray, axis: int = 0, slice_idx: int = None) -> np.ndarray:
        """Multi-Planar Reconstruction — شريحة على محور معين."""
        vol = VolumeVisualizer._ensure_3d(data)
        axis = int(axis) % 3
        if slice_idx is None:
            slice_idx = vol.shape[axis] // 2
        slice_idx = min(max(int(slice_idx), 0), vol.shape[axis] - 1)
        return np.take(vol, indices=slice_idx, axis=axis)

    @staticmethod
    def render_3d_plotly(data: np.ndarray, downsample: int = 4) -> Optional[object]:
        """عرض ثلاثي الأبعاد باستخدام Plotly (Isosurface)."""
        try:
            import plotly.graph_objects as go
            vol = np.asarray(VolumeVisualizer._ensure_3d(data), dtype=np.float32)
            step = max(1, int(downsample))
            vol_ds = vol[::step, ::step, ::step]
            finite = np.isfinite(vol_ds)
            if not finite.any():
                return None
            replacement = float(np.nanmedian(vol_ds[finite]))
            vol_ds = np.nan_to_num(
                vol_ds, nan=replacement, posinf=replacement, neginf=replacement
            )
            value_min = float(np.min(vol_ds))
            value_max = float(np.max(vol_ds))
            if value_min == value_max:
                vol_ds = vol_ds.copy()
                vol_ds.flat[0] = value_min + 1e-6
                value_max = float(np.max(vol_ds))
            threshold = float(np.percentile(vol_ds, 75))
            X, Y, Z = np.mgrid[:vol_ds.shape[0], :vol_ds.shape[1], :vol_ds.shape[2]]
            fig = go.Figure(data=go.Isosurface(
                x=X.flatten(), y=Y.flatten(), z=Z.flatten(),
                value=vol_ds.flatten(),
                isomin=threshold, isomax=value_max,
                caps=dict(x_show=False, y_show=False, z_show=False),
                surface_count=3,
            ))
            fig.update_layout(width=400, height=400, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor='#0A0A0A', scene_bgcolor='#0A0A0A')
            return fig
        except (ImportError, ValueError, TypeError):
            return None
