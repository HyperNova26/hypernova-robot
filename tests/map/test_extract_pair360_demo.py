# SPDX-License-Identifier: Apache-2.0
"""Synthetic checks for reproducible PAIR360 demo crop extraction."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/map/extract_pair360_demo.py"


def write_binary_pcd(path, points):
    records = np.asarray(points, dtype="<f4")
    header = (
        "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z intensity\n"
        "SIZE 4 4 4 4\nTYPE F F F F\nCOUNT 1 1 1 1\n"
        f"WIDTH {len(records)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {len(records)}\nDATA binary\n"
    )
    path.write_bytes(header.encode("ascii") + records.tobytes())


def run(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def read_binary_ply(path):
    with path.open("rb") as stream:
        header = []
        while True:
            line = stream.readline()
            header.append(line.decode("ascii").strip())
            if line == b"end_header\n":
                break
        data = np.fromfile(stream, dtype="<f4").reshape(-1, 4)
    return header, data


def test_extracts_inclusive_finite_crop_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source.pcd"
    output = tmp_path / "crop.ply"
    write_binary_pcd(source, [
        [0, 0, 0, 1],
        [1, 1, 1, 2],
        [2, 2, 2, 3],
        [3, 3, 3, 4],
        [np.nan, 1, 1, 5],
    ])

    result = run(source, "--output", output, "--min", 0, 0, 0,
                 "--max", 2, 2, 2, "--expected-count", 3)
    assert result.returncode == 0, result.stderr
    header, data = read_binary_ply(output)
    assert "format binary_little_endian 1.0" in header
    assert "element vertex 3" in header
    np.testing.assert_allclose(data[:, :3], [[0, 0, 0], [1, 1, 1], [2, 2, 2]])
    assert json.loads(output.with_suffix(".json").read_text())["selected_points"] == 3

    repeated = run(source, "--output", output, "--min", 0, 0, 0, "--max", 2, 2, 2)
    assert repeated.returncode == 2
    assert "Refusing existing" in repeated.stderr


def test_expected_count_mismatch_stops_before_writing(tmp_path):
    source = tmp_path / "source.pcd"
    output = tmp_path / "crop.ply"
    write_binary_pcd(source, [[0, 0, 0, 1]])

    result = run(source, "--output", output, "--min", 0, 0, 0,
                 "--max", 1, 1, 1, "--expected-count", 2)
    assert result.returncode == 2
    assert "Selected 1 points; expected 2" in result.stderr
    assert not output.exists()
