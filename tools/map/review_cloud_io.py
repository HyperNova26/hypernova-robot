# SPDX-License-Identifier: Apache-2.0
"""Exact XYZI review-cloud I/O.

This module deliberately has no classification policy.  It only connects a
subset produced by a classifier back to the rows of the source cloud and
writes reviewable binary PLY layers.

``load_xyzi_ply(path)`` accepts the PAIR360 review input contract: binary
little-endian PLY with one ``vertex`` element and exactly these vertex
properties, in order: ``float x, y, z, scalar_intensity``.  It returns a
read-only ``(N, 4)`` ``<f4`` memmap, so a full cloud need not be copied.

``subset_mask(original, subset)`` compares the *four IEEE-754 float32 bit
patterns*, rather than rounded numeric values.  It returns a boolean mask in
original-row order.  Repeated rows are selected in stable original-row order;
an unknown row or one requested more often than it occurs raises
``ValueError``.  The implementation uses sorted fixed-width row keys rather
than Python tuples/dictionaries, which keeps the working set bounded by a few
NumPy arrays and avoids per-point Python-object overhead.

``write_review_ply`` emits binary little-endian PLY with XYZ, intensity,
``original_index``, RGB, optional ``review_class``/``baseline_ground`` uchar
fields, and optional named float32 provenance fields.  The writer refuses an
existing destination without replacing it.  It writes a temporary sibling and
publishes it through an exclusive hard link, so readers never see a partial
destination file.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Mapping

import numpy as np


_XYZI_PROPERTIES = (
    "property float x",
    "property float y",
    "property float z",
    "property float scalar_intensity",
)
_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ROW_KEY_DTYPE = np.dtype([(name, "<u4") for name in ("x", "y", "z", "i")])


def load_xyzi_ply(path: str | os.PathLike[str]) -> np.memmap:
    """Return a read-only memmap of a standard four-float32 LE XYZI PLY.

    The intentionally narrow reader prevents a review layer from silently
    losing or reinterpreting an input property.  It does not read point data
    until the returned memmap is indexed.
    """
    source = Path(path)
    properties: list[str] = []
    vertex_count: int | None = None
    in_vertex = False
    with source.open("rb") as stream:
        if stream.readline().strip() != b"ply":
            raise ValueError(f"Not a PLY file: {source}")
        if stream.readline().strip() != b"format binary_little_endian 1.0":
            raise ValueError("Expected binary_little_endian PLY 1.0")
        while True:
            raw = stream.readline()
            if not raw:
                raise ValueError("Truncated PLY header")
            try:
                line = raw.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise ValueError("PLY header is not ASCII") from exc
            if line.startswith("element "):
                parts = line.split()
                in_vertex = len(parts) == 3 and parts[1] == "vertex"
                if in_vertex:
                    try:
                        vertex_count = int(parts[2])
                    except ValueError as exc:
                        raise ValueError("Invalid vertex count") from exc
                    if vertex_count < 0:
                        raise ValueError("Negative vertex count")
            elif line.startswith("property ") and in_vertex:
                properties.append(line)
            elif line == "end_header":
                offset = stream.tell()
                break

    if vertex_count is None:
        raise ValueError("PLY has no vertex element")
    if tuple(properties) != _XYZI_PROPERTIES:
        raise ValueError(
            "Expected vertex properties: " + ", ".join(_XYZI_PROPERTIES)
        )
    expected_size = offset + vertex_count * 16
    if source.stat().st_size != expected_size:
        raise ValueError(
            f"PLY payload size is {source.stat().st_size - offset}, expected {vertex_count * 16}"
        )
    return np.memmap(source, dtype="<f4", mode="r", offset=offset, shape=(vertex_count, 4))


def _xyzi_row_keys(points: np.ndarray, *, name: str) -> np.ndarray:
    array = np.asarray(points)
    if array.ndim != 2 or array.shape[1] != 4:
        raise ValueError(f"{name} must have shape (N, 4), got {array.shape}")
    if array.dtype != np.dtype("<f4"):
        raise ValueError(f"{name} must be float32; got {array.dtype}")
    if not array.flags.c_contiguous:
        raise ValueError(f"{name} must be C-contiguous to preserve exact row bytes")
    return array.view(_ROW_KEY_DTYPE).reshape(-1)


def subset_mask(original: np.ndarray, subset: np.ndarray) -> np.ndarray:
    """Map ``subset`` XYZI rows exactly and multiplicity-safely to ``original``.

    Duplicate subset rows take the earliest still-unselected equal original
    rows.  This selection is deterministic, although the returned boolean mask
    naturally does not expose which duplicate was paired with which duplicate.
    """
    original_keys = _xyzi_row_keys(original, name="original")
    subset_keys = _xyzi_row_keys(subset, name="subset")
    if len(subset_keys) > len(original_keys):
        raise ValueError("subset has more rows than original")
    mask = np.zeros(len(original_keys), dtype=bool)
    if not len(subset_keys):
        return mask
    if not len(original_keys):
        raise ValueError("subset contains rows but original is empty")

    # These are fixed-width primitive arrays (not Python tuple keys).  Keeping
    # the sorted values lets searchsorted validate exact bit-pattern groups.
    original_order = np.argsort(original_keys, kind="stable")
    sorted_original = original_keys[original_order]
    subset_order = np.argsort(subset_keys, kind="stable")
    sorted_subset = subset_keys[subset_order]
    starts = np.empty(len(sorted_subset), dtype=bool)
    starts[0] = True
    starts[1:] = sorted_subset[1:] != sorted_subset[:-1]
    group_starts = np.flatnonzero(starts)
    group_values = sorted_subset[group_starts]
    left = np.searchsorted(sorted_original, group_values, side="left")
    right = np.searchsorted(sorted_original, group_values, side="right")

    # A search hit alone does not prove multiplicity: each equal subset row
    # would otherwise find the same left boundary.  Check every run instead.
    group_ends = np.r_[group_starts[1:], len(sorted_subset)]
    requested = group_ends - group_starts
    available = right - left
    if np.any(requested > available):
        bad = int(np.flatnonzero(requested > available)[0])
        reason = "unknown row" if available[bad] == 0 else "row multiplicity exceeds original"
        raise ValueError(f"subset {reason} at sorted group {bad}")

    # A stable sort of original row keys makes duplicate selection earliest-row
    # first.  Assign each sorted subset run to the corresponding original run.
    run_offsets = np.arange(len(sorted_subset)) - np.repeat(group_starts, requested)
    selected_sorted_original = left.repeat(requested) + run_offsets
    mask[original_order[selected_sorted_original]] = True
    return mask


def _uchar_values(value: object, count: int, *, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim == 0:
        if not np.issubdtype(array.dtype, np.integer) or not 0 <= int(array) <= 255:
            raise ValueError(f"{name} scalar must be an integer in [0, 255]")
        return np.full(count, int(array), dtype=np.uint8)
    if array.shape != (count,) or not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"{name} must be an integer scalar or shape ({count},)")
    if np.any(array < 0) or np.any(array > 255):
        raise ValueError(f"{name} values must be in [0, 255]")
    return array.astype(np.uint8, copy=False)


def _rgb_values(rgb: object, count: int) -> np.ndarray:
    array = np.asarray(rgb)
    if array.shape == (3,):
        if not np.issubdtype(array.dtype, np.integer) or np.any(array < 0) or np.any(array > 255):
            raise ValueError("rgb tuple values must be integers in [0, 255]")
        return np.broadcast_to(array.astype(np.uint8), (count, 3))
    if array.shape != (count, 3) or not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"rgb must be a 3-tuple or integer array of shape ({count}, 3)")
    if np.any(array < 0) or np.any(array > 255):
        raise ValueError("rgb values must be in [0, 255]")
    return array.astype(np.uint8, copy=False)


def _provenance_values(
    provenance_fields: Mapping[str, object] | None, count: int
) -> dict[str, np.ndarray]:
    if provenance_fields is None:
        return {}
    result: dict[str, np.ndarray] = {}
    for field, value in provenance_fields.items():
        if field in {"x", "y", "z", "scalar_intensity", "original_index", "red", "green", "blue", "review_class", "baseline_ground"}:
            raise ValueError(f"provenance field conflicts with standard field: {field}")
        if not _FIELD_NAME.fullmatch(field):
            raise ValueError(f"invalid PLY property name: {field!r}")
        array = np.asarray(value)
        if array.ndim == 0:
            array = np.full(count, array, dtype=np.float32)
        elif array.shape != (count,):
            raise ValueError(f"provenance field {field!r} must be scalar or shape ({count},)")
        result[field] = np.asarray(array, dtype="<f4")
    return result


def write_review_ply(
    path: str | os.PathLike[str],
    points: np.ndarray,
    original_indices: np.ndarray,
    rgb: object,
    review_class: object | None = None,
    baseline_ground: object | None = None,
    provenance_fields: Mapping[str, object] | None = None,
) -> Path:
    """Write an exclusive, binary review PLY and return its path.

    ``original_indices`` is written as PLY ``uint`` when every value fits in
    uint32; otherwise it is written as ``ulong``.  ``provenance_fields`` maps
    safe property names to float32 scalars or one value per output row.
    """
    xyzi = np.asarray(points)
    _xyzi_row_keys(xyzi, name="points")
    count = len(xyzi)
    indices = np.asarray(original_indices)
    if indices.shape != (count,) or not np.issubdtype(indices.dtype, np.integer):
        raise ValueError(f"original_indices must be an integer array of shape ({count},)")
    if np.any(indices < 0):
        raise ValueError("original_indices cannot be negative")
    index_dtype = np.dtype("<u4") if not len(indices) or int(indices.max()) < 2**32 else np.dtype("<u8")
    index_property = "uint" if index_dtype.itemsize == 4 else "ulong"
    indices = indices.astype(index_dtype, copy=False)
    colors = _rgb_values(rgb, count)
    review = None if review_class is None else _uchar_values(review_class, count, name="review_class")
    baseline = None if baseline_ground is None else _uchar_values(baseline_ground, count, name="baseline_ground")
    provenance = _provenance_values(provenance_fields, count)

    fields: list[tuple[str, str]] = [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("scalar_intensity", "<f4"),
        ("original_index", index_dtype.str), ("red", "u1"), ("green", "u1"), ("blue", "u1"),
    ]
    ply_properties = [
        "property float x", "property float y", "property float z", "property float scalar_intensity",
        f"property {index_property} original_index", "property uchar red", "property uchar green", "property uchar blue",
    ]
    if review is not None:
        fields.append(("review_class", "u1")); ply_properties.append("property uchar review_class")
    if baseline is not None:
        fields.append(("baseline_ground", "u1")); ply_properties.append("property uchar baseline_ground")
    for field in provenance:
        fields.append((field, "<f4")); ply_properties.append(f"property float {field}")
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {count}\n" + "\n".join(ply_properties) + "\nend_header\n").encode("ascii")

    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing review PLY: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Output parent does not exist: {destination.parent}")
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="xb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as stream:
            temp_name = stream.name
            stream.write(header)
            dtype = np.dtype(fields)
            chunk_size = 1_000_000
            for start in range(0, count, chunk_size):
                stop = min(start + chunk_size, count)
                rows = np.empty(stop - start, dtype=dtype)
                rows["x"], rows["y"], rows["z"], rows["scalar_intensity"] = xyzi[start:stop].T
                rows["original_index"] = indices[start:stop]
                rows["red"], rows["green"], rows["blue"] = colors[start:stop].T
                if review is not None:
                    rows["review_class"] = review[start:stop]
                if baseline is not None:
                    rows["baseline_ground"] = baseline[start:stop]
                for field, values in provenance.items():
                    rows[field] = values[start:stop]
                stream.write(rows.tobytes())
            stream.flush()
            os.fsync(stream.fileno())
        # link() is exclusive: unlike replace(), it cannot overwrite another
        # writer's completed output.  Same-directory temp keeps it same-volume.
        os.link(temp_name, destination)
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return destination
