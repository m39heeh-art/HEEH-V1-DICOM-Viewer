"""TCIA / folder dataset builder for local fine-tuning.

Research/education tool only. NOT a medical device.

Converts cached TCIA series (or a plain folder-per-class tree) into
RGB PIL images + integer labels, with a deterministic stratified split.

Folder layout (preferred for clean labels):
    data/train/<class_name>/*.dcm|*.nii|*.png|*.jpg

TCIA cache layout (reuses ClinicalApp cache):
    ~/.neuroproject_tcia/<SeriesUID>/... + metadata CSVs in
    ~/.neuroproject_tcia/metadata/*.csv

Label priority: --labels-csv (series_uid,label) > metadata column
(--label-column, default BodyPartExamined) > folder name.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

IMAGE_EXTS = (".dcm", ".dicom", ".nii", ".nii.gz", ".nrrd",
              ".mha", ".mhd", ".ima", ".img", ".png", ".jpg", ".jpeg")


def _is_image_name(name: str) -> bool:
    """Return whether a filename looks like a DICOM image."""
    n = name.lower()
    return any(n.endswith(e) for e in IMAGE_EXTS)


def load_labels_csv(path: str | Path) -> Dict[str, str]:
    """Parse series_uid,label CSV (header optional). Returns uid->label."""
    out: Dict[str, str] = {}
    with open(str(path), newline="", encoding="utf-8", errors="ignore") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        for row in reader:
            if not row or len(row) < 2:
                continue
            a, b = row[0].strip(), row[1].strip()
            if not a or not b:
                continue
            if a.lower() in ("series_uid", "seriesinstanceuid", "uid", "id",
                             "image", "path") and b.lower() == "label":
                continue  # header row
            out[a] = b
    return out


def _window_ct(hu: np.ndarray, center: float = 40.0,
               width: float = 400.0) -> np.ndarray:
    """Apply a CT window/level to a volume slice."""
    lo, hi = center - width / 2.0, center + width / 2.0
    return np.clip((hu - lo) / max(hi - lo, 1e-9) * 255.0, 0, 255).astype(np.uint8)


def _normalize_generic(arr: np.ndarray) -> np.ndarray:
    """Min-max normalize a non-CT slice to [0, 1]."""
    p1, p99 = float(np.percentile(arr, 1)), float(np.percentile(arr, 99))
    return np.clip((arr - p1) / max(p99 - p1, 1e-9) * 255.0, 0, 255).astype(np.uint8)


def slice_to_rgb(volume: np.ndarray, is_ct: bool = True) -> Image.Image:
    """Middle-slice extraction + windowing -> RGB PIL (224-ready)."""
    arr = np.asarray(volume, dtype=np.float32)
    while arr.ndim > 2:
        shape = arr.shape
        ax = int(np.argmin(shape))
        if shape[ax] < 1:
            raise ValueError("Volumetric axis is empty.")
        arr = np.take(arr, shape[ax] // 2, axis=ax)
    if arr.ndim != 2:
        raise ValueError(f"Cannot render {arr.ndim}D array as 2D slice.")
    gray = _window_ct(arr) if is_ct else _normalize_generic(arr)
    return Image.fromarray(gray, mode="L").convert("RGB")


def _read_dicom_slice(path: Path) -> Tuple[np.ndarray, bool]:
    """Read a single DICOM slice as a normalized float32 array."""
    import pydicom
    ds = pydicom.dcmread(str(path))
    px = ds.pixel_array.astype(np.float32)
    mod = str(getattr(ds, "Modality", "CT")).upper()
    if mod != "CT":
        if str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2")).upper() == "MONOCHROME1":
            px = px.max() - px
        return px, False
    slope = float(getattr(ds, "RescaleSlope", 1.0))
    inter = float(getattr(ds, "RescaleIntercept", 0.0))
    return px * slope + inter, True


def _read_volume_slice(path: Path) -> Tuple[np.ndarray, bool]:
    """Read a volumetric slice (NIfTI/NRRD/MHA) as float32."""
    try:
        import nibabel as nib
        img = nib.load(str(path))
        data = np.asarray(img.dataobj, dtype=np.float32)
        return data, True
    except Exception:
        import SimpleITK as sitk
        arr = sitk.GetArrayFromImage(sitk.ReadImage(str(path))).astype(np.float32)
        return arr, True


def image_file_to_rgb(path: Path) -> Image.Image:
    """Read any supported file -> RGB PIL. Raises on failure."""
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in (".png", ".jpg", ".jpeg"):
        return Image.open(str(path)).convert("RGB")
    if suffix in (".dcm", ".dicom", ".ima", ".img") or suffix == "":
        try:
            with open(str(path), "rb") as fh:
                head = fh.read(132)
            if len(head) >= 132 and head[128:132] == b"DICM":
                arr, is_ct = _read_dicom_slice(path)
                return slice_to_rgb(arr, is_ct)
        except Exception:
            pass
    if name.endswith(".nii.gz") or suffix in (".nii", ".nrrd", ".mha", ".mhd"):
        arr, is_ct = _read_volume_slice(path)
        return slice_to_rgb(arr, is_ct)
    # last resort: try DICOM reader (covers extension-less TCIA files)
    arr, is_ct = _read_dicom_slice(path)
    return slice_to_rgb(arr, is_ct)


def build_from_folder(root: str | Path, limit: int = 0) -> List[Dict]:
    """Folder-per-class tree -> items [{image, label, source}]."""
    root = Path(root)
    items: List[Dict] = []
    for cls_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(p for p in cls_dir.rglob("*")
                       if p.is_file() and _is_image_name(p.name))
        if limit:
            files = files[:limit]
        for fp in files:
            try:
                img = image_file_to_rgb(fp)
            except Exception:
                continue
            items.append({"image": img, "label": cls_dir.name,
                          "source": str(fp)})
    return items


def _scan_series_dirs(cache_root: Path) -> List[Path]:
    """Index series directories under the root data path."""
    return sorted(p for p in cache_root.iterdir()
                  if p.is_dir() and p.name != "metadata"
                  and any(f.is_file() and f.name != ".series.complete"
                          for f in p.rglob("*")))


def _metadata_label_lookup(cache_root: Path, column: str) -> Dict[str, str]:
    """Map a series dir to its metadata label, if present."""
    lookup: Dict[str, str] = {}
    meta_dir = cache_root / "metadata"
    if not meta_dir.is_dir():
        return lookup
    for csv_path in meta_dir.glob("*.csv"):
        try:
            with open(str(csv_path), newline="", encoding="utf-8",
                      errors="ignore") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames:
                    continue
                uid_col = next((c for c in reader.fieldnames
                                if "seriesinstanceuid" in c.lower().replace(" ", "")),
                               None)
                lab_col = next((c for c in reader.fieldnames
                                if c.lower().replace(" ", "") == column.lower().replace(" ", "")),
                               None)
                if not uid_col or not lab_col:
                    continue
                for row in reader:
                    uid, lab = (row.get(uid_col) or "").strip(), (row.get(lab_col) or "").strip()
                    if uid and lab:
                        lookup[uid] = lab
        except Exception:
            continue
    return lookup


def build_from_tcia_cache(cache_root: str | Path, label_column: str = "BodyPartExamined",
                           labels_csv: Optional[str | Path] = None,
                           limit_per_series: int = 4) -> List[Dict]:
    """TCIA cache dir -> items. Weak labels from metadata unless overridden."""
    cache_root = Path(cache_root)
    override = load_labels_csv(labels_csv) if labels_csv else {}
    meta_lookup = _metadata_label_lookup(cache_root, label_column)
    items: List[Dict] = []
    for series_dir in _scan_series_dirs(cache_root):
        uid = series_dir.name
        label = override.get(uid) or meta_lookup.get(uid)
        if not label:
            continue  # unlabeled series are skipped (never guessed)
        files = sorted(p for p in series_dir.rglob("*")
                       if p.is_file() and p.name not in (".series.complete", "series.zip.tmp")
                       and _is_image_name(str(p)))
        # even spread across the series (avoids near-duplicate slices)
        if len(files) > limit_per_series:
            idx = np.linspace(0, len(files) - 1, limit_per_series).astype(int)
            files = [files[i] for i in idx]
        for fp in files:
            try:
                img = image_file_to_rgb(fp)
            except Exception:
                continue
            items.append({"image": img, "label": str(label).strip() or "Unknown",
                          "source": str(fp), "series_uid": uid})
    return items


def encode_labels(items: List[Dict]) -> Tuple[List[Dict], Dict[str, int]]:
    """Encode string severity labels into integer classes."""
    classes = sorted({str(it["label"]) for it in items})
    mapping = {c: i for i, c in enumerate(classes)}
    for it in items:
        it["label_id"] = mapping[str(it["label"])]
    return items, mapping


def stratified_split(items: List[Dict], val_frac: float = 0.2,
                     seed: int = 42) -> Tuple[List[Dict], List[Dict]]:
    """Split items stratified by label, keeping series together when present.

    DICOM slices from one series are highly correlated. Keeping a series in
    one partition prevents slice-level leakage and gives more realistic
    validation results.
    """
    rng = random.Random(seed)
    by_cls: Dict[str, Dict[str, List[Dict]]] = {}
    for it in items:
        label = str(it["label"])
        group = str(it.get("series_uid") or it.get("group_id") or it.get("source"))
        by_cls.setdefault(label, {}).setdefault(group, []).append(it)
    train, val = [], []
    for groups in by_cls.values():
        group_items = list(groups.values())
        rng.shuffle(group_items)
        total = sum(len(group) for group in group_items)
        if len(group_items) < 2:
            train.extend(group_items[0] if group_items else [])
            continue
        target = max(1, int(round(total * val_frac)))
        val_count = 0
        split_at = 0
        for index, group in enumerate(group_items):
            if val_count >= target and split_at > 0:
                break
            val_count += len(group)
            split_at = index + 1
        val.extend(item for group in group_items[:split_at] for item in group)
        train.extend(item for group in group_items[split_at:] for item in group)
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def group_ids(items: List[Dict]) -> set[str]:
    """Return the independent groups represented by dataset items."""
    return {
        str(item.get("series_uid") or item.get("group_id") or item.get("source"))
        for item in items
    }


def validate_group_disjoint(train: List[Dict], val: List[Dict]) -> None:
    """Reject train/validation leakage when correlated images share a group."""
    overlap = group_ids(train) & group_ids(val)
    if overlap:
        preview = ", ".join(sorted(overlap)[:3])
        suffix = "..." if len(overlap) > 3 else ""
        raise ValueError(
            f"Train/validation group leakage detected for {len(overlap)} group(s): "
            f"{preview}{suffix}"
        )


def dataset_stats(items: List[Dict]) -> Dict:
    """Summarize per-class sample counts for the dataset."""
    counts: Dict[str, int] = {}
    groups = set()
    for it in items:
        counts[str(it["label"])] = counts.get(str(it["label"]), 0) + 1
        groups.add(str(it.get("series_uid") or it.get("group_id") or it.get("source")))
    return {"n": len(items), "groups": len(groups), "classes": sorted(counts), "counts": counts}


def dataset_manifest(items: List[Dict]) -> Dict:
    """Create a privacy-preserving, deterministic manifest for an experiment."""
    records = []
    for item in items:
        records.append({
            "group": str(item.get("series_uid") or item.get("group_id") or ""),
            "label": str(item.get("label") or ""),
            "source_name": Path(str(item.get("source") or "")).name,
        })
    records.sort(key=lambda value: (value["group"], value["label"], value["source_name"]))
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {
        "algorithm": "sha256",
        "record_count": len(records),
        "group_count": len({record["group"] for record in records}),
        "dataset_hash": hashlib.sha256(payload).hexdigest(),
        "records": records,
    }
