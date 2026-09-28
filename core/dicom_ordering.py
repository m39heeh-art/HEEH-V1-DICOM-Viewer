"""Deterministic DICOM instance ordering for study/series navigation."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Iterable

import numpy as np
import pydicom


def _read_header(target: Any) -> pydicom.dataset.Dataset | None:
    """Read a DICOM header without decoding pixels, preserving file handles."""
    try:
        if hasattr(target, "seek"):
            target.seek(0)
            dataset = pydicom.dcmread(target, stop_before_pixels=True)
            target.seek(0)
            return dataset
        return pydicom.dcmread(
            str(getattr(target, "name", target)),
            stop_before_pixels=True,
            force=False,
        )
    except (
        OSError,
        ValueError,
        AttributeError,
        pydicom.errors.InvalidDicomError,
    ):
        return None


def _numbers(value: Any, length: int) -> tuple[float, ...] | None:
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if len(values) != length or not np.isfinite(values).all():
        return None
    return values


def _slice_projection(
    orientation: tuple[float, ...] | None,
    position: tuple[float, ...] | None,
) -> float | None:
    if orientation is None or position is None:
        return None
    row = np.asarray(orientation[:3], dtype=float)
    column = np.asarray(orientation[3:], dtype=float)
    normal = np.cross(row, column)
    norm = float(np.linalg.norm(normal))
    if norm <= 1e-12:
        return None
    normal /= norm
    # Orientation vectors can be sign-flipped by a sender. Canonicalizing the
    # normal makes ordering stable while retaining the physical slice axis.
    for component in normal:
        if abs(component) > 1e-12:
            if component < 0:
                normal *= -1.0
            break
    return float(np.dot(np.asarray(position, dtype=float), normal))


def order_dicom_files(
    files: Iterable[Any],
    *,
    header_reader: Callable[[Any], pydicom.dataset.Dataset | None] | None = None,
) -> list[Any]:
    """Order image instances by study/series and physical slice position.

    ``ImageOrientationPatient`` plus ``ImagePositionPatient`` is preferred.
    If either tag is absent or invalid, ``InstanceNumber`` and then the stable
    input order are used. Non-DICOM inputs retain their original relative
    order and are not mixed into DICOM study/series groups.
    """
    items = list(files or [])
    if len(items) < 2:
        return items
    read = header_reader or _read_header
    records: list[dict[str, Any]] = []
    for index, target in enumerate(items):
        dataset = read(target)
        if dataset is None:
            records.append(
                {"target": target, "index": index, "group": ("", ""), "dicom": False}
            )
            continue
        study = str(getattr(dataset, "StudyInstanceUID", "") or "")
        series = str(getattr(dataset, "SeriesInstanceUID", "") or "")
        orientation = _numbers(getattr(dataset, "ImageOrientationPatient", None), 6)
        position = _numbers(getattr(dataset, "ImagePositionPatient", None), 3)
        projection = _slice_projection(orientation, position)
        try:
            instance_number = float(getattr(dataset, "InstanceNumber", np.inf))
            if not np.isfinite(instance_number):
                instance_number = np.inf
        except (TypeError, ValueError):
            instance_number = np.inf
        records.append(
            {
                "target": target,
                "index": index,
                "group": (study, series),
                "dicom": True,
                "projection": projection,
                "position": position,
                "instance_number": instance_number,
                "name": str(getattr(target, "name", target)),
            }
        )

    groups: OrderedDict[tuple[str, str], list[dict[str, Any]]] = OrderedDict()
    for record in records:
        groups.setdefault(record["group"], []).append(record)

    ordered: list[Any] = []
    for group_records in groups.values():
        if not any(record["dicom"] for record in group_records):
            ordered.extend(record["target"] for record in group_records)
            continue

        def sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
            if record.get("projection") is not None:
                return (0, record["projection"], record["index"])
            if record.get("position") is not None:
                return (1, *record["position"], record["index"])
            return (
                2,
                record.get("instance_number", np.inf),
                record.get("name", ""),
                record["index"],
            )

        ordered.extend(record["target"] for record in sorted(group_records, key=sort_key))
    return ordered


__all__ = ["order_dicom_files"]
