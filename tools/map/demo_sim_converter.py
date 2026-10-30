#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
"""Convert all finite XYZ samples into matching Isaac USD and MuJoCo voxel scenes."""
import argparse
import ctypes
import datetime
import errno
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
ARGUMENTS = sys.argv[1:]
os.environ.setdefault("OMP_NUM_THREADS", "4")
CHUNK = 250_000
MAX_MESH_FACES = 1_000_000
SUPPORTED = {".ply", ".pcd", ".xyz", ".xyzn", ".xyzrgb", ".pts", ".bin"}


def progress(message):
    print(message, flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Input: PLY, PCD, XYZ, XYZN, XYZRGB, PTS, or native CloudCompare BIN.
Coordinates are metres, Z-up; local = (input - origin) * scale.
Every occupied voxel is retained without ground/car classification.
Outputs: <output-root>/MMDD_demo_whole/{terrain.usd,terrain.xml,scene.json}
Existing output paths are refused; simulator viewers are not launched.
Requires prepared numpy, open3d, usd-core; CloudCompare for BIN only.
For geometry limits, explicitly increase --voxel-size or crop the input.
""",
    )
    parser.add_argument("input", type=Path, help="Input point-cloud file")
    parser.add_argument("--voxel-size", type=float, default=0.5,
                        help="Occupied voxel edge length (default: 0.5 m)")
    parser.add_argument("--origin", type=float, nargs=3, default=[0.0, 0.0, 0.0],
                        help="Input origin to subtract (default: 0 0 0)")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="Positive coordinate scale (default: 1)")
    parser.add_argument("--date", default=datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m%d"),
                        help="Folder date MMDD (default: today in Asia/Seoul)")
    parser.add_argument("--output-root", type=Path, default=ROOT / "sim_scenes",
                        help="Parent folder (default: repository sim_scenes)")
    parser.add_argument("--max-geoms", type=int, default=100_000,
                        help="Maximum merged MuJoCo boxes (default: 100000)")
    parser.add_argument("--cloudcompare", help="CloudCompare executable for native BIN input")
    args = parser.parse_args(ARGUMENTS)
    if not math.isfinite(args.voxel_size) or args.voxel_size <= 0:
        parser.error("--voxel-size must be finite and positive")
    if not math.isfinite(args.scale) or args.scale <= 0:
        parser.error("--scale must be finite and positive")
    if not all(math.isfinite(value) for value in args.origin):
        parser.error("--origin must contain three finite numbers")
    if args.max_geoms < 1:
        parser.error("--max-geoms must be positive")
    try:
        if not re.fullmatch(r"[0-9]{4}", args.date):
            raise ValueError
        datetime.datetime.strptime("2000" + args.date, "%Y%m%d")
    except ValueError:
        parser.error("--date must be a valid MMDD date")
    return args


def convert_bin(source, workspace, requested_executable):
    executable = requested_executable or shutil.which("CloudCompare") or shutil.which("cloudcompare.CloudCompare")
    executable = shutil.which(executable) if executable else None
    if not executable:
        raise ValueError("Native BIN requires CloudCompare or cloudcompare.CloudCompare; use --cloudcompare EXEC or export PLY in its GUI.")
    # Snap and other dispatchers use the symlink name in argv[0].
    executable = os.path.abspath(executable)
    copied = workspace / "input.bin"
    shutil.copyfile(source, copied)
    converted = workspace / "converted.ply"
    command = [executable, "-SILENT", "-AUTO_SAVE", "OFF", "-O", str(copied),
               "-C_EXPORT_FMT", "PLY", "-PLY_EXPORT_FMT", "BINARY_LE", "-NO_TIMESTAMP",
               "-SAVE_CLOUDS", "FILE", str(converted)]
    log = workspace / "cloudcompare.log"
    progress("[1/5] Native BIN → PLY (temporary copy, CloudCompare timeout: 120 s)")
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=workspace,
                                    env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("CloudCompare timed out after 120 s; no scene was published.") from exc
    candidates = [path for path in workspace.iterdir()
                  if path.is_file() and path.suffix.lower() == ".ply"]
    if result.returncode != 0 or len(candidates) != 1 or candidates[0].stat().st_size == 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise ValueError(f"CloudCompare must export exactly one nonempty PLY (exit={result.returncode}, files={len(candidates)}).\n{tail}")
    return candidates[0], {
        "method": "CloudCompare native BIN, temporary input copy",
        "executable": str(executable), "converted_sha256": sha256(candidates[0]),
        "coordinate_policy": "CloudCompare PLY export coordinates; no extra global shift or leveling applied",
    }


def sorted_unique_cells(points, origin, scale, voxel):
    """Allocate sparse indices only, independent of the cloud's bounding volume."""
    count = len(points)
    cells = np.empty((count, 3), dtype=np.int64)  # z, y, x: x varies fastest.
    finite_count = 0
    input_min = np.full(3, np.inf)
    input_max = np.full(3, -np.inf)
    local_min = np.full(3, np.inf)
    local_max = np.full(3, -np.inf)
    for start in range(0, count, CHUNK):
        chunk = points[start:start + CHUNK]
        chunk = chunk[np.isfinite(chunk).all(axis=1)]
        if not len(chunk):
            continue
        input_min = np.minimum(input_min, chunk.min(axis=0))
        input_max = np.maximum(input_max, chunk.max(axis=0))
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            local = (chunk - origin) * scale
            indices = np.floor(local / voxel)
        if not np.isfinite(indices).all() or np.abs(indices).max() >= 2 ** 52:
            raise ValueError("Coordinates exceed safe voxel indexing; use a closer --origin or a larger --voxel-size.")
        local_min = np.minimum(local_min, local.min(axis=0))
        local_max = np.maximum(local_max, local.max(axis=0))
        cells[finite_count:finite_count + len(chunk)] = indices[:, ::-1]
        finite_count += len(chunk)
    if not finite_count:
        raise ValueError("Input is empty or has no finite XYZ records.")
    cells = cells[:finite_count]
    records = cells.view(CELL_DTYPE).reshape(-1)
    records.sort(kind="quicksort")  # In-place: no dense 3-D grid or Python set.
    keep = np.ones(finite_count, dtype=bool)
    for start in range(1, finite_count, CHUNK):
        end = min(start + CHUNK, finite_count)
        keep[start:end] = np.any(cells[start:end] != cells[start - 1:end - 1], axis=1)
    return cells[keep], finite_count, (input_min, input_max), (local_min, local_max)


def rectangle_runs(cells):
    """Merge exact col runs, then identical intervals on adjacent rows/planes.

    Input sorted [plane,row,col]; output [plane,row0,row1,col0,col1], exclusive ends.
    """
    if not len(cells):
        return np.empty((0, 5), dtype=np.int64)
    starts_mask = np.ones(len(cells), dtype=bool)
    for start in range(1, len(cells), CHUNK):
        end = min(start + CHUNK, len(cells))
        current, previous = cells[start:end], cells[start - 1:end - 1]
        starts_mask[start:end] = ((current[:, 0] != previous[:, 0]) |
                                  (current[:, 1] != previous[:, 1]) |
                                  (current[:, 2] != previous[:, 2] + 1))
    starts = np.flatnonzero(starts_mask)
    ends = np.r_[starts[1:] - 1, len(cells) - 1]
    runs = np.column_stack((cells[starts, :2], cells[starts, 2], cells[ends, 2] + 1))
    # Group identical col intervals within each plane, order rows increasingly.
    runs = runs[np.lexsort((runs[:, 1], runs[:, 3], runs[:, 2], runs[:, 0]))]
    starts_mask = np.ones(len(runs), dtype=bool)
    starts_mask[1:] = ((runs[1:, 0] != runs[:-1, 0]) |
                       (runs[1:, 2] != runs[:-1, 2]) |
                       (runs[1:, 3] != runs[:-1, 3]) |
                       (runs[1:, 1] != runs[:-1, 1] + 1))
    starts = np.flatnonzero(starts_mask)
    ends = np.r_[starts[1:] - 1, len(runs) - 1]
    return np.column_stack((runs[starts, 0], runs[starts, 1], runs[ends, 1] + 1,
                            runs[starts, 2], runs[starts, 3]))


def merge_boxes(cells):
    rectangles = rectangle_runs(cells)
    rectangles = rectangles[np.lexsort((rectangles[:, 0], rectangles[:, 4], rectangles[:, 3],
                                       rectangles[:, 2], rectangles[:, 1]))]
    starts_mask = np.ones(len(rectangles), dtype=bool)
    starts_mask[1:] = (np.any(rectangles[1:, 1:] != rectangles[:-1, 1:], axis=1) |
                       (rectangles[1:, 0] != rectangles[:-1, 0] + 1))
    starts = np.flatnonzero(starts_mask)
    ends = np.r_[starts[1:] - 1, len(rectangles) - 1]
    # x0,x1,y0,y1,z0,z1; exclusive integer upper bounds.
    boxes = np.column_stack((rectangles[starts, 3:5], rectangles[starts, 1:3],
                             rectangles[starts, 0], rectangles[ends, 0] + 1))
    volume = np.prod(boxes[:, 1::2] - boxes[:, ::2], axis=1).sum()
    if int(volume) != len(cells):
        raise ValueError("Internal error: merged boxes do not preserve occupied voxel volume.")
    return boxes


def boundary_rectangles(cells):
    """Find six exposed sides with sparse lookups, then merge coplanar faces."""
    lo, hi = cells.min(axis=0), cells.max(axis=0)
    dimensions = [int(hi[axis]) - int(lo[axis]) + 3 for axis in range(3)]
    key_capacity = math.prod(dimensions)
    keys = None
    if key_capacity < 2 ** 63:
        steps = [dimensions[1] * dimensions[2], dimensions[2], 1]
        keys = np.zeros(len(cells), dtype=np.int64)
        for axis in range(3):
            keys += (cells[:, axis] - lo[axis] + 1) * steps[axis]
    else:
        records = cells.view(CELL_DTYPE).reshape(-1)
    result = []
    face_count = 0
    for axis in range(3):
        for direction in (-1, 1):
            exposed = np.empty(len(cells), dtype=bool)
            for start in range(0, len(cells), CHUNK):
                end = min(start + CHUNK, len(cells))
                if keys is not None:
                    query = keys[start:end] + direction * steps[axis]
                    locations = np.searchsorted(keys, query)
                    present = locations < len(cells)
                    present[present] = keys[locations[present]] == query[present]
                else:
                    query = cells[start:end].copy()
                    query[:, axis] += direction
                    query = query.view(CELL_DTYPE).reshape(-1)
                    locations = np.searchsorted(records, query)
                    present = locations < len(cells)
                    present[present] = records[locations[present]] == query[present]
                exposed[start:end] = ~present
            order = [axis] + [other for other in range(3) if other != axis]
            faces = cells[exposed][:, order]
            if direction > 0:
                faces[:, 0] += 1
            if axis != 0 and len(faces):
                faces = faces[np.lexsort((faces[:, 2], faces[:, 1], faces[:, 0]))]
            rectangles = rectangle_runs(faces)
            face_count += len(rectangles)
            if face_count > MAX_MESH_FACES:
                raise ValueError(f"USD boundary exceeds {MAX_MESH_FACES:,} merged faces; increase --voxel-size or crop the input.")
            result.append((axis, direction, rectangles))
    return result, face_count


def mesh_arrays(groups, face_count, voxel):
    points = np.empty((face_count * 4, 3), dtype=np.float32)
    offset = 0
    for axis, direction, rectangles in groups:
        count = len(rectangles)
        if not count:
            continue
        p, r0, r1, c0, c1 = rectangles.T
        corners = np.empty((count, 4, 3), dtype=np.float64)
        if axis == 0:  # z plane, +Z winding
            corners[:, :, 0] = np.column_stack((c0, c1, c1, c0))
            corners[:, :, 1] = np.column_stack((r0, r0, r1, r1))
            corners[:, :, 2] = p[:, None]
        elif axis == 1:  # y plane, +Y winding
            corners[:, :, 0] = np.column_stack((c0, c0, c1, c1))
            corners[:, :, 1] = p[:, None]
            corners[:, :, 2] = np.column_stack((r0, r1, r1, r0))
        else:  # x plane, +X winding
            corners[:, :, 0] = p[:, None]
            corners[:, :, 1] = np.column_stack((c0, c1, c1, c0))
            corners[:, :, 2] = np.column_stack((r0, r0, r1, r1))
        if direction < 0:
            corners = corners[:, ::-1, :]
        points[offset:offset + count * 4] = (corners * voxel).reshape(-1, 3)
        offset += count * 4
    points, indices = np.unique(points, axis=0, return_inverse=True)
    return points, indices.astype(np.int32)


def write_mujoco(path, boxes, voxel):
    with path.open("w", encoding="utf-8") as stream:
        stream.write('<mujoco model="whole_pointcloud">\n  <compiler angle="radian"/>\n'
                     '  <option gravity="0 0 -9.81"/>\n  <worldbody>\n')
        for index, box in enumerate(boxes):
            lower = box[::2].astype(float) * voxel
            upper = box[1::2].astype(float) * voxel
            center = (lower + upper) / 2
            half_size = (upper - lower) / 2
            position = " ".join(format(value, ".17g") for value in center)
            size = " ".join(format(value, ".17g") for value in half_size)
            stream.write(f'    <geom name="voxel_box_{index}" type="box" pos="{position}" size="{size}" '
                         'contype="1" conaffinity="1" friction="0.8 0.01 0.001" rgba="0.55 0.6 0.65 1"/>\n')
        stream.write("  </worldbody>\n</mujoco>\n")


def write_usd(path, points, indices, face_count):
    from pxr import Usd, UsdGeom, UsdPhysics, Vt
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    mesh = UsdGeom.Mesh.Define(stage, "/Terrain")
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points))
    quads = indices.reshape(-1, 4)
    triangles = np.empty((face_count * 2, 3), dtype=np.int32)
    triangles[::2] = quads[:, [0, 1, 2]]
    triangles[1::2] = quads[:, [0, 2, 3]]
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(face_count * 2, 3, dtype=np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(triangles.ravel()))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
    mesh.CreateDoubleSidedAttr(False)
    mesh.CreateExtentAttr(Vt.Vec3fArray.FromNumpy(np.array([points.min(axis=0), points.max(axis=0)], dtype=np.float32)))
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr("none")
    stage.SetDefaultPrim(mesh.GetPrim())
    if not stage.GetRootLayer().Save():
        raise ValueError("USD layer could not be saved.")


def publish_no_replace(staging, destination):
    """Atomic Linux directory publication, refusing even empty existing dirs."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise ValueError("Atomic no-overwrite publication requires Linux renameat2; no scene was published.")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(staging), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise ValueError(f"Output already exists; refusing overwrite: {destination}")
        raise OSError(error, os.strerror(error), str(destination))


def bounds_pair(pair):
    return {"min": pair[0].tolist(), "max": pair[1].tolist()}


def main():
    args = parse_args()
    source = args.input.expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in SUPPORTED:
        raise ValueError("Input must be a readable PLY/PCD/XYZ/XYZN/XYZRGB/PTS/native CloudCompare BIN file.")
    if source.stat().st_size == 0:
        raise ValueError("Input file is empty.")
    output_root = args.output_root.expanduser().resolve()
    destination = output_root / (args.date + "_demo_whole")
    if os.path.lexists(destination):
        raise ValueError(f"Output already exists; refusing overwrite: {destination}")
    # Fail before creating any scene directory if the prepared dependencies are absent.
    global np, CELL_DTYPE
    import numpy as np
    import open3d as o3d
    from pxr import Usd  # noqa: F401 - dependency check before expensive conversion
    CELL_DTYPE = np.dtype([("z", np.int64), ("y", np.int64), ("x", np.int64)])
    progress(f"Source / 입력: {source}\nOutput / 출력: {destination}")
    source_hash = sha256(source)
    generator_hash = sha256(SCRIPT)
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".whole-build-", dir=output_root) as temporary:
        workspace = Path(temporary)
        staging = workspace / "scene"
        staging.mkdir()
        conversion = {"method": "Open3D direct XYZ read"}
        readable = source
        if source.suffix.lower() == ".bin":
            readable, conversion = convert_bin(source, workspace, args.cloudcompare)
        else:
            progress("[1/5] Reading XYZ / XYZ 읽기 (all geometry)")
        cloud = o3d.io.read_point_cloud(str(readable), remove_nan_points=False,
                                       remove_infinite_points=False, print_progress=False)
        points = np.asarray(cloud.points)
        input_count = len(points)
        if not input_count:
            raise ValueError("Point cloud is unreadable, empty, or has no XYZ records.")
        progress(f"[2/5] Sparse voxelization / 복셀화: {input_count:,} records, {args.voxel_size:g} m")
        cells, finite_count, input_bounds, local_bounds = sorted_unique_cells(
            points, np.asarray(args.origin), args.scale, args.voxel_size)
        del points, cloud
        progress(f"[3/5] Exact cuboid merging / 상자 병합: {len(cells):,} occupied voxels")
        boxes = merge_boxes(cells)
        if len(boxes) > args.max_geoms:
            raise ValueError(f"{len(boxes):,} merged boxes exceed --max-geoms {args.max_geoms:,}; increase --voxel-size or explicitly crop the input.")
        geometry_min = cells.min(axis=0)[::-1].astype(float) * args.voxel_size
        geometry_max = (cells.max(axis=0)[::-1].astype(float) + 1) * args.voxel_size
        max_coordinate = float(np.max(np.abs([geometry_min, geometry_max])))
        with np.errstate(over="ignore", invalid="ignore"):
            spacing = float(np.spacing(np.float32(max_coordinate)))
        if not math.isfinite(spacing) or spacing > args.voxel_size:
            raise ValueError("USD float32 precision is too coarse for these coordinates; use --origin near the cloud or increase --voxel-size.")
        progress(f"[4/5] Exterior collision boundary / 외부 충돌면: {len(boxes):,} static boxes")
        groups, face_count = boundary_rectangles(cells)
        vertex_points, indices = mesh_arrays(groups, face_count, args.voxel_size)
        write_mujoco(staging / "terrain.xml", boxes, args.voxel_size)
        write_usd(staging / "terrain.usd", vertex_points, indices, face_count)
        if sha256(source) != source_hash:
            raise ValueError("Source changed during conversion; refusing to publish inconsistent provenance.")
        metadata = {
            "schema_version": 1, "status": "complete",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "folder_date_timezone": "Asia/Seoul", "folder_date_mmdd": args.date,
            "source": {"path": str(source), "sha256": source_hash,
                       "license": "Inherited from source; license is user supplied and not determined by this converter",
                       "conversion": conversion},
            "generator": {"script": str(SCRIPT.relative_to(ROOT)) if SCRIPT.is_relative_to(ROOT) else str(SCRIPT),
                          "sha256": generator_hash, "arguments": ARGUMENTS,
                          "python": sys.version.split()[0],
                          "versions": {name: importlib.metadata.version(name) for name in ("numpy", "open3d", "usd-core")}},
            "units": "m", "up_axis": "Z",
            "axes": {"x": "+X unchanged", "y": "+Y unchanged", "z": "+Z up"},
            "transform": {"formula": "local = (input - origin_input) * scale",
                          "origin_input": args.origin, "scale": args.scale,
                          "input_units_assumption": "m, Z-up before explicit scale"},
            "voxel_size_m": args.voxel_size,
            "voxel_convention": "floor(local/voxel_size); lower-inclusive, upper-exclusive cells; no semantic filtering",
            "bounds": {"input_finite": bounds_pair(input_bounds), "local_points": bounds_pair(local_bounds),
                       "voxel_geometry": bounds_pair((geometry_min, geometry_max))},
            "counts": {"input_points": input_count, "finite_points": finite_count,
                       "nonfinite_removed": input_count - finite_count,
                       "occupied_voxels": len(cells), "boxes": len(boxes),
                       "usd_vertices": len(vertex_points), "usd_faces": face_count * 2,
                       "usd_boundary_rectangles": face_count},
            "limits": {"max_geoms": args.max_geoms, "max_usd_boundary_faces": MAX_MESH_FACES},
            "files": {"isaac": "terrain.usd", "mujoco": "terrain.xml", "manifest": "scene.json"},
            "caveats": [
                "Every finite XYZ record contributes; no ground/car/outlier classification is performed.",
                "Occupied voxels approximate samples, not measured solid interiors or the exact original surface.",
                "Voxelization can thicken surfaces and close gaps smaller than the chosen voxel size.",
                "MuJoCo static boxes preserve occupied-cell union; USD uses its exposed boundary only, with float32 vertex precision.",
                "No simulator GUI, robot dynamics, or physical validation is implied by successful file generation.",
            ],
        }
        (staging / "scene.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        progress("[5/5] Publishing complete scene / 완료 장면 게시 (atomic, no overwrite)")
        publish_no_replace(staging, destination)
    progress(f"Complete / 완료: {destination}\n{finite_count:,} finite points → {len(cells):,} voxels → {len(boxes):,} static boxes; {face_count:,} exterior USD faces")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("ERROR: Interrupted; no incomplete final scene is published.", file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, ImportError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
