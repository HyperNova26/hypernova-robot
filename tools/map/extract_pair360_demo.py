#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recreate the recorded PAIR360 parking demo crop as binary PLY."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np


RECORDED_MIN = (-81.3052749633789, 64.42131042480469, -12.098955154418945)
RECORDED_MAX = (64.14539337158203, 223.58726501464844, 38.09461975097656)
MAX_HEADER_BYTES = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_binary_pcd(path: Path) -> tuple[np.memmap, dict[str, object]]:
    values: dict[str, list[str]] = {}
    with path.open("rb") as stream:
        while stream.tell() <= MAX_HEADER_BYTES:
            raw = stream.readline()
            if not raw:
                raise ValueError("PCD header ended before DATA")
            try:
                line = raw.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise ValueError("PCD header is not ASCII") from exc
            if not line or line.startswith("#"):
                continue
            key, *items = line.split()
            values[key.upper()] = items
            if key.upper() == "DATA":
                data_offset = stream.tell()
                break
        else:
            raise ValueError("PCD header exceeds 1 MiB")

    required = ("FIELDS", "SIZE", "TYPE", "COUNT", "WIDTH", "HEIGHT", "POINTS", "DATA")
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError(f"PCD header is missing: {', '.join(missing)}")
    fields = values["FIELDS"]
    sizes = [int(value) for value in values["SIZE"]]
    types = values["TYPE"]
    counts = [int(value) for value in values["COUNT"]]
    if not (len(fields) == len(sizes) == len(types) == len(counts)):
        raise ValueError("PCD FIELDS/SIZE/TYPE/COUNT lengths differ")
    if fields != ["x", "y", "z", "intensity"]:
        raise ValueError(f"Expected FIELDS x y z intensity, got: {' '.join(fields)}")
    if sizes != [4, 4, 4, 4] or types != ["F", "F", "F", "F"] or counts != [1, 1, 1, 1]:
        raise ValueError("Expected four scalar float32 PCD fields")
    if values["DATA"] != ["binary"]:
        raise ValueError("Expected DATA binary PCD")

    width = int(values["WIDTH"][0])
    height = int(values["HEIGHT"][0])
    points = int(values["POINTS"][0])
    if width * height != points:
        raise ValueError("PCD WIDTH * HEIGHT differs from POINTS")
    dtype = np.dtype([(field, "<f4") for field in fields])
    expected_size = data_offset + points * dtype.itemsize
    if path.stat().st_size != expected_size:
        raise ValueError(
            f"PCD byte size mismatch: expected {expected_size}, got {path.stat().st_size}"
        )
    cloud = np.memmap(path, mode="r", offset=data_offset, dtype=dtype, shape=(points,))
    metadata: dict[str, object] = {
        "fields": fields,
        "point_count": points,
        "data_offset": data_offset,
        "record_bytes": dtype.itemsize,
    }
    return cloud, metadata


def crop_mask(records: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    xyz = np.column_stack((records["x"], records["y"], records["z"]))
    return np.isfinite(xyz).all(axis=1) & (xyz >= lower).all(axis=1) & (xyz <= upper).all(axis=1)


def scan_crop(
    cloud: np.memmap, lower: np.ndarray, upper: np.ndarray, chunk_points: int
) -> tuple[int, np.ndarray, np.ndarray]:
    count = 0
    actual_min = np.full(3, np.inf)
    actual_max = np.full(3, -np.inf)
    for start in range(0, len(cloud), chunk_points):
        records = cloud[start : start + chunk_points]
        selected = records[crop_mask(records, lower, upper)]
        if not len(selected):
            continue
        xyz = np.column_stack((selected["x"], selected["y"], selected["z"]))
        count += len(selected)
        actual_min = np.minimum(actual_min, xyz.min(axis=0))
        actual_max = np.maximum(actual_max, xyz.max(axis=0))
    if not count:
        raise ValueError("Crop bounds selected no finite points")
    return count, actual_min, actual_max


def ply_header(count: int) -> bytes:
    return (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment source PAIR360 T1_parking_Seq0.pcd\n"
        f"element vertex {count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property float intensity\n"
        "end_header\n"
    ).encode("ascii")


def write_crop(cloud: np.memmap, output: Path, lower: np.ndarray, upper: np.ndarray,
               count: int, chunk_points: int) -> None:
    part = output.with_name(output.name + ".part")
    if output.exists() or part.exists():
        raise ValueError(f"Refusing existing output or partial file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with part.open("xb") as stream:
            stream.write(ply_header(count))
            for start in range(0, len(cloud), chunk_points):
                records = cloud[start : start + chunk_points]
                selected = records[crop_mask(records, lower, upper)]
                if len(selected):
                    stream.write(selected.tobytes())
                    written += len(selected)
        if written != count:
            raise RuntimeError(f"Crop changed between passes: counted {count}, wrote {written}")
        os.replace(part, output)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("input", type=Path, help="PAIR360 T1_parking_Seq0 binary PCD")
    result.add_argument("--output", type=Path, help="New binary little-endian PLY path")
    result.add_argument("--min", dest="lower", type=float, nargs=3, default=RECORDED_MIN,
                        metavar=("X", "Y", "Z"), help="Inclusive source-map lower XYZ")
    result.add_argument("--max", dest="upper", type=float, nargs=3, default=RECORDED_MAX,
                        metavar=("X", "Y", "Z"), help="Inclusive source-map upper XYZ")
    result.add_argument("--expected-count", type=int,
                        help="Stop before writing unless the selected count matches")
    result.add_argument("--chunk-points", type=int, default=1_000_000)
    result.add_argument("--scan-only", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        source = args.input.expanduser().resolve(strict=True)
        if args.chunk_points < 1:
            raise ValueError("--chunk-points must be positive")
        lower = np.asarray(args.lower, dtype=np.float64)
        upper = np.asarray(args.upper, dtype=np.float64)
        if not np.isfinite(lower).all() or not np.isfinite(upper).all() or np.any(lower > upper):
            raise ValueError("Crop bounds must be finite and min <= max")
        cloud, source_meta = read_binary_pcd(source)
        count, actual_min, actual_max = scan_crop(cloud, lower, upper, args.chunk_points)
        result = {
            "source": str(source),
            "source_points": len(cloud),
            "selected_points": count,
            "requested_bounds": {"min": lower.tolist(), "max": upper.tolist()},
            "selected_bounds": {"min": actual_min.tolist(), "max": actual_max.tolist()},
            "pcd": source_meta,
        }
        if args.expected_count is not None and count != args.expected_count:
            raise ValueError(f"Selected {count} points; expected {args.expected_count}")
        if args.scan_only:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.output is None:
            raise ValueError("--output is required unless --scan-only is used")
        output = args.output.expanduser().resolve()
        report = output.with_suffix(".json")
        if report.exists():
            raise ValueError(f"Refusing existing report: {report}")
        write_crop(cloud, output, lower, upper, count, args.chunk_points)
        result.update({
            "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
            "output": str(output),
            "format": "binary_little_endian PLY; float32 x y z intensity",
            "source_sha256": sha256(source),
            "output_sha256": sha256(output),
        })
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
