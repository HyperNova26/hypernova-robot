# SPDX-License-Identifier: Apache-2.0
"""Synthetic exactness checks for review-cloud I/O."""

from pathlib import Path

import numpy as np
import pytest

from tools.map.review_cloud_io import load_xyzi_ply, subset_mask, write_review_ply


def _xyzi(rows):
    return np.asarray(rows, dtype="<f4")


def _read_header_and_records(path: Path):
    with path.open("rb") as stream:
        lines = []
        while True:
            line = stream.readline()
            lines.append(line.decode("ascii").strip())
            if line == b"end_header\n":
                break
        offset = stream.tell()
    properties = [line.split()[-1] for line in lines if line.startswith("property ")]
    formats = []
    for line in lines:
        if line.startswith("property "):
            kind = line.split()[1]
            formats.append({"float": "<f4", "uint": "<u4", "ulong": "<u8", "uchar": "u1"}[kind])
    count = int(next(line for line in lines if line.startswith("element vertex ")).split()[-1])
    return lines, np.memmap(path, mode="r", offset=offset, dtype=np.dtype(list(zip(properties, formats))), shape=(count,))


def test_subset_mask_exact_duplicates_and_stable_selection():
    duplicate = [1, 2, 3, 4]
    original = _xyzi([duplicate, [9, 8, 7, 6], duplicate, duplicate])
    mask = subset_mask(original, _xyzi([duplicate, duplicate]))
    assert mask.tolist() == [True, False, True, False]


def test_subset_mask_accepts_empty_and_partial_duplicate_subset():
    original = _xyzi([[1, 2, 3, 4], [9, 8, 7, 6], [1, 2, 3, 4]])
    assert subset_mask(original, _xyzi([]).reshape(0, 4)).tolist() == [False, False, False]
    assert subset_mask(original, _xyzi([[1, 2, 3, 4]])).tolist() == [True, False, False]


@pytest.mark.parametrize(
    "subset, message",
    [(_xyzi([[8, 8, 8, 8]]), "unknown row"), (_xyzi([[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]), "multiplicity"),],
)
def test_subset_mask_rejects_unknown_or_excess_multiplicity(subset, message):
    original = _xyzi([[1, 2, 3, 4], [1, 2, 3, 4], [9, 9, 9, 9]])
    with pytest.raises(ValueError, match=message):
        subset_mask(original, subset)


def test_writer_preserves_xyzi_bits_and_optional_schema(tmp_path):
    # Signed zero and a deliberately chosen NaN payload must round-trip as bits.
    raw = np.array(
        [[0x80000000, 0x7FC01234, 0x3F800000, 0x40400000], [0, 1, 2, 3]], dtype="<u4"
    ).view("<f4")
    target = tmp_path / "review.ply"
    write_review_ply(
        target, raw, np.array([7, 8], dtype=np.uint32), (1, 2, 3),
        review_class=4, baseline_ground=np.array([1, 0], dtype=np.uint8),
        provenance_fields={"review_score": np.array([.25, .75], dtype=np.float32)},
    )
    header, records = _read_header_and_records(target)
    assert "property uint original_index" in header
    assert "property uchar review_class" in header
    assert "property float review_score" in header
    written = np.column_stack([records[name] for name in ("x", "y", "z", "scalar_intensity")])
    assert np.array_equal(written.view("<u4"), raw.view("<u4"))
    assert records["original_index"].tolist() == [7, 8]
    assert records["red"].tolist() == [1, 1]
    assert records["review_score"].tolist() == pytest.approx([.25, .75])


def test_load_xyzi_ply_and_writer_refuses_overwrite(tmp_path):
    points = _xyzi([[1, 2, 3, 4]])
    source = tmp_path / "source.ply"
    write_review_ply(source, points, np.array([0], dtype=np.uint32), (5, 6, 7))
    # Review output contains extra fields, so the narrow source reader rejects it.
    with pytest.raises(ValueError, match="Expected vertex properties"):
        load_xyzi_ply(source)

    standard = tmp_path / "standard.ply"
    standard.write_bytes(
        b"ply\nformat binary_little_endian 1.0\nelement vertex 1\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"property float scalar_intensity\nend_header\n" + points.tobytes()
    )
    loaded = load_xyzi_ply(standard)
    assert np.array_equal(loaded.view("<u4"), points.view("<u4"))
    with pytest.raises(FileExistsError):
        write_review_ply(source, points, np.array([0], dtype=np.uint32), (5, 6, 7))
