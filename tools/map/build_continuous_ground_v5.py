# SPDX-License-Identifier: Apache-2.0
"""Build a car-free, continuous 10 cm ground mesh from the reviewed v1 grid.

This is deliberately a *simulation surface* exporter, not a semantic-label
writer.  The reviewed ground samples constrain height; empty road and parking
cells are filled by a Laplacian interpolation.  Decision polygons define the
walkable domain and tree/no-go holes.  Vehicle samples never constrain height.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path as Polygon
from scipy.ndimage import binary_closing, binary_dilation, distance_transform_edt

from review_cloud_io import load_xyzi_ply


BLUE = np.array([45, 135, 245], np.uint8)
BROWN = np.array([135, 92, 62], np.uint8)
ORANGE = np.array([240, 130, 45], np.uint8)
# The reviewed parking patch was selected by the team.  A decisions JSON can
# replace/extend it, but keeping it here makes missing tiny legacy holes not
# silently turn into walls in a simulation export.
DEFAULT_PARKING = [[-82.0, 64.0], [-16.0, 64.0], [-16.0, 212.0], [-82.0, 212.0]]


def export_view(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    """Write a display-only RGB PLY without importing the SMRF experiment."""
    dtype = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
                      ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')])
    header = ('ply\nformat binary_little_endian 1.0\n'
              'comment DISPLAY ONLY; source attributes in ../canonical\n'
              f'element vertex {len(points)}\nproperty float x\nproperty float y\n'
              'property float z\nproperty uchar red\nproperty uchar green\n'
              'property uchar blue\nend_header\n').encode('ascii')
    with path.open('xb') as stream:
        stream.write(header)
        for start in range(0, len(points), 250_000):
            part = points[start:start + 250_000]
            rgb = colors[start:start + 250_000]
            rows = np.empty(len(part), dtype=dtype)
            rows['x'], rows['y'], rows['z'] = part[:, :3].T
            rows['red'], rows['green'], rows['blue'] = rgb.T
            stream.write(rows.tobytes())


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _records(config: dict, *names: str) -> list[dict]:
    result: list[dict] = []
    for name in names:
        value = config.get(name, [])
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            raise ValueError(f"decisions.{name} must be a list")
        result.extend(value)
    return result


def _polygon_mask(xy: np.ndarray, records: list[dict] | list[list[float]]) -> np.ndarray:
    mask = np.zeros(len(xy), dtype=bool)
    for record in records:
        polygon = record.get("polygon_xy") if isinstance(record, dict) else record
        points = np.asarray(polygon, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
            raise ValueError("each decision polygon must be a finite Nx2 array (N >= 3)")
        mask |= Polygon(points).contains_points(xy, radius=1e-9)
    return mask


def apply_decisions(xy: np.ndarray, base_allowed: np.ndarray, decisions: dict, inherited_exclusion: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return permitted, excluded and vehicle masks; exclusion always wins."""
    if base_allowed.shape != (len(xy),):
        raise ValueError("base_allowed and xy do not align")
    reset = _records(decisions, "reset_parking", "reset_parking_polygon")
    # An absent reset still closes stale v1 cracks within the explicitly
    # reviewed parking envelope.  Tree islands remain holes through exclude.
    reset_mask = _polygon_mask(xy, reset) if reset else _polygon_mask(xy, [DEFAULT_PARKING])
    extend = _polygon_mask(xy, _records(decisions, "restore_road", "extend_ground", "allow", "extensions"))
    excluded = _polygon_mask(xy, _records(decisions, "exclude", "tree_exclusion", "vegetation_exclusion", "blocked"))
    if inherited_exclusion is not None:
        if inherited_exclusion.shape != excluded.shape:
            raise ValueError("inherited exclusion and xy do not align")
        # Manual vehicle-floor decisions override old geometric masks, while
        # explicitly reviewed tree polygons always remain excluded.
        override = _polygon_mask(xy, _records(decisions, "force_allow", "vehicle_floor_override"))
        excluded |= inherited_exclusion & ~override
    vehicles = _polygon_mask(xy, _records(decisions, "vehicles", "vehicle_polygons", "removed_vehicles"))
    allowed = (np.asarray(base_allowed, bool) | reset_mask | extend) & ~excluded
    return allowed, excluded, vehicles


def remove_raised_islands(z: np.ndarray, allowed: np.ndarray, threshold_m: float = 1.0) -> np.ndarray:
    """Remove isolated one-metre-high cell medians, not continuous slopes."""
    padded = np.pad(z, 1, constant_values=np.nan)
    neighbours = [padded[dy:dy+z.shape[0], dx:dx+z.shape[1]]
                  for dy in range(3) for dx in range(3) if (dy, dx) != (1, 1)]
    stack = np.stack(neighbours)
    reference = np.nanmedian(stack, axis=0)
    bad = allowed & np.isfinite(z) & (np.isfinite(stack).sum(axis=0) >= 5) & (z > reference + threshold_m)
    result = z.copy(); result[bad] = np.nan
    return result


def coherent_tree_exclusion(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Close pinholes within inherited tree islands and retain a one-cell margin."""
    island = np.asarray(mask, bool).reshape(shape)
    island = binary_closing(island, structure=np.ones((3, 3), bool))
    return binary_dilation(island, structure=np.ones((3, 3), bool)).ravel()


def harmonic_fill(observed: np.ndarray, allowed: np.ndarray, *, iterations: int = 900, tolerance: float = 2e-4) -> tuple[np.ndarray, np.ndarray, float]:
    """Nearest-seed initialise then solve the 4-neighbour discrete Laplace equation.

    The updates only use neighbours in ``allowed``; therefore a tree exclusion
    is a real boundary and cannot be bridged by smoothing.  Components without
    a measured seed use the nearest global measured height only as a constant
    seed, which keeps the simulation surface finite while preserving provenance.
    """
    observed = np.asarray(observed, float)
    allowed = np.asarray(allowed, bool)
    if observed.shape != allowed.shape or observed.ndim != 2:
        raise ValueError("observed and allowed must be same 2-D shape")
    support = allowed & np.isfinite(observed)
    if not support.any():
        raise ValueError("no observed ground heights inside permitted domain")
    # EDT indices provide a deterministic nearest supported initial surface.
    _, nearest = distance_transform_edt(~support, return_indices=True)
    heights = observed[tuple(nearest)].copy()
    heights[~allowed] = np.nan
    inferred = allowed & ~support
    # Jacobi relaxation.  Fixed supports are never updated; excluded cells do
    # not participate in the numerator or denominator.
    residual = float("inf")
    for _ in range(iterations):
        total = np.zeros_like(heights, dtype=float)
        count = np.zeros_like(heights, dtype=np.int16)
        for axis, shift in ((0, -1), (0, 1), (1, -1), (1, 1)):
            src_h = np.roll(heights, shift, axis=axis)
            src_ok = np.roll(allowed, shift, axis=axis)
            # np.roll wraps; remove the artificial edge row/column.
            if axis == 0:
                src_ok[-1 if shift == -1 else 0, :] = False
            else:
                src_ok[:, -1 if shift == -1 else 0] = False
            total += np.where(src_ok, src_h, 0.0)
            count += src_ok
        candidate = np.divide(total, count, out=heights.copy(), where=count > 0)
        residual = float(np.nanmax(np.abs(candidate[inferred] - heights[inferred]))) if inferred.any() else 0.0
        heights[inferred & (count > 0)] = candidate[inferred & (count > 0)]
        if residual <= tolerance:
            break
    # Distance in coarse cells, not used to colour the final all-blue cloud.
    distance = distance_transform_edt(~support)
    heights[~allowed] = np.nan
    return heights, distance, residual


def fine_surface(coarse: np.ndarray, allowed: np.ndarray, origin: np.ndarray, coarse_m: float, fine_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Regular bilinear 10 cm samples, with domain inherited from coarse cells."""
    ratio = int(round(coarse_m / fine_m))
    if ratio < 1 or not np.isclose(ratio * fine_m, coarse_m):
        raise ValueError("fine cell size must divide the reviewed cell size")
    ny, nx = coarse.shape
    fy, fx = ny * ratio, nx * ratio
    yy, xx = np.indices((fy, fx), dtype=float)
    # Fine centres mapped onto the coarse-centre coordinate system.
    cy = (yy + 0.5) / ratio - 0.5
    cx = (xx + 0.5) / ratio - 0.5
    x0 = np.floor(cx).astype(int); y0 = np.floor(cy).astype(int)
    x1 = np.clip(x0 + 1, 0, nx - 1); y1 = np.clip(y0 + 1, 0, ny - 1)
    x0 = np.clip(x0, 0, nx - 1); y0 = np.clip(y0, 0, ny - 1)
    tx = np.clip(cx - x0, 0., 1.); ty = np.clip(cy - y0, 0., 1.)
    mask = np.repeat(np.repeat(allowed, ratio, axis=0), ratio, axis=1)
    # At an exclusion boundary, a fine sample may be inside an allowed coarse
    # cell while one bilinear neighbour is a hole.  Reuse the containing cell
    # for that unavailable neighbour: this preserves a finite boundary without
    # borrowing a height through the excluded region.
    base_y = np.minimum((yy // ratio).astype(int), ny - 1)
    base_x = np.minimum((xx // ratio).astype(int), nx - 1)
    base = coarse[base_y, base_x]
    v00 = np.where(np.isfinite(coarse[y0, x0]), coarse[y0, x0], base)
    v10 = np.where(np.isfinite(coarse[y0, x1]), coarse[y0, x1], base)
    v01 = np.where(np.isfinite(coarse[y1, x0]), coarse[y1, x0], base)
    v11 = np.where(np.isfinite(coarse[y1, x1]), coarse[y1, x1], base)
    height = ((1-tx)*(1-ty)*v00 + tx*(1-ty)*v10 +
              (1-tx)*ty*v01 + tx*ty*v11)
    height[~mask] = np.nan
    x = origin[0] + (np.arange(fx) + .5) * fine_m
    y = origin[1] + (np.arange(fy) + .5) * fine_m
    return x, y, height, mask


def build_mesh(x: np.ndarray, y: np.ndarray, height: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Create faces only where all four regular samples are permitted."""
    yy, xx = np.indices(mask.shape)
    vertex_id = np.full(mask.shape, -1, dtype=np.int64)
    vertex_id[mask] = np.arange(mask.sum(), dtype=np.int64)
    vertices = np.column_stack((x[xx[mask]], y[yy[mask]], height[mask])).astype("<f4")
    quad = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, :-1] & mask[1:, 1:]
    a, b, c, d = vertex_id[:-1, :-1][quad], vertex_id[:-1, 1:][quad], vertex_id[1:, :-1][quad], vertex_id[1:, 1:][quad]
    faces = np.empty((len(a) * 2, 3), dtype="<u4")
    faces[0::2] = np.column_stack((a, b, d)); faces[1::2] = np.column_stack((a, d, c))
    return vertices, faces


def _exclusive_write(destination: Path, header: bytes, payload_writer) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("xb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name); stream.write(header); payload_writer(stream)
            stream.flush(); os.fsync(stream.fileno())
        os.link(temp, destination)
    finally:
        if temp is not None:
            try: temp.unlink()
            except FileNotFoundError: pass


def write_mesh_ply(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    header = ("ply\nformat binary_little_endian 1.0\ncomment car-free continuous ground collision surface\n"
              f"element vertex {len(vertices)}\nproperty float x\nproperty float y\nproperty float z\n"
              f"element face {len(faces)}\nproperty list uchar uint vertex_indices\nend_header\n").encode("ascii")
    def payload(stream):
        for start in range(0, len(vertices), 1_000_000): stream.write(vertices[start:start+1_000_000].tobytes())
        rows = np.empty(len(faces), dtype=np.dtype([("n", "u1"), ("v", "<u4", (3,))])); rows["n"] = 3; rows["v"] = faces
        for start in range(0, len(rows), 1_000_000): stream.write(rows[start:start+1_000_000].tobytes())
    _exclusive_write(path, header, payload)


def _save_visuals(out: Path, x: np.ndarray, y: np.ndarray, height: np.ndarray, mask: np.ndarray, support_distance: np.ndarray) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    extent = [x[0], x[-1], y[0], y[-1]]
    axes[0].imshow(mask, origin="lower", extent=extent, cmap="Blues"); axes[0].set_title("permitted simulation domain")
    im = axes[1].imshow(height, origin="lower", extent=extent, cmap="terrain"); axes[1].set_title("height (m)"); fig.colorbar(im, ax=axes[1])
    im = axes[2].imshow(np.where(mask, support_distance, np.nan), origin="lower", extent=extent, cmap="magma"); axes[2].set_title("distance to measured support (m)"); fig.colorbar(im, ax=axes[2])
    for ax in axes: ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
    fig.savefig(out / "surface_overview.png", dpi=170); plt.close(fig)
    mid = height.shape[0] // 2
    fig, ax = plt.subplots(figsize=(12, 4)); ax.plot(x[mask[mid]], height[mid, mask[mid]], ".", ms=1, color="#2d87f5")
    ax.set(xlabel="X (m)", ylabel="Z (m)", title=f"cross-section at Y={y[mid]:.2f} m"); ax.grid(True, alpha=.25)
    fig.savefig(out / "surface_cross_section.png", dpi=170); plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, required=True, help="manual_ground_revision_v1 directory")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--decisions", type=Path, help="optional extension/tree/vehicle polygons JSON")
    ap.add_argument("--design", type=Path, help="optional car_free_design_v1/design_policy.npz")
    ap.add_argument("--fine-m", type=float, default=.10)
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists(): raise FileExistsError(f"output already exists: {out}")
    decision = json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions else {}
    # Baseline protocol files keep the actual polygon lists under this key;
    # a v5 decisions file may instead contain those lists at top level.
    if "manual_decisions" in decision:
        decision = decision["manual_decisions"]
    base = np.load(args.baseline / "classification.npz")
    protocol = json.loads((args.baseline / "protocol.json").read_text(encoding="utf-8"))
    cell_m = float(base["cell_m"]); shape = tuple(int(v) for v in base["shape"]); origin = np.asarray(base["origin"], float)
    xy = np.asarray(base["xy"], float); allowed0 = np.asarray(base["allowed"], bool)
    if len(xy) != np.prod(shape): raise ValueError("baseline grid shape mismatch")
    inherited_exclusion = np.zeros(len(xy), bool)
    design_path = args.design
    if design_path is None:
        candidate = args.baseline.parent / "20261104_car_free_design_v1" / "design_policy.npz"
        if candidate.is_file():
            design_path = candidate
    if design_path is not None:
        design = np.load(design_path)
        for name in ("planting_exclusion", "column_exclusion"):
            if name in design:
                inherited_exclusion |= np.asarray(design[name], bool)
    inherited_exclusion = coherent_tree_exclusion(inherited_exclusion, shape)
    allowed, excluded, vehicle_cells = apply_decisions(xy, allowed0, decision, inherited_exclusion)
    source = load_xyzi_ply(args.source)
    actual_hash = _sha(args.source)
    expected_hash = protocol.get("source_sha256")
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(f"source SHA-256 differs from reviewed baseline: {actual_hash}")
    point_type = np.asarray(base["point_type"], np.uint8)
    if len(point_type) != len(source): raise ValueError("baseline/source point count mismatch")
    keys_xy = np.floor((source[:, :2] - origin) / cell_m).astype(int)
    valid = ((keys_xy[:, 0] >= 0) & (keys_xy[:, 0] < shape[1]) & (keys_xy[:, 1] >= 0) & (keys_xy[:, 1] < shape[0]))
    keys = keys_xy[:, 1] * shape[1] + keys_xy[:, 0]
    manual_vehicle = np.asarray(base["manual_vehicle_body"], bool) if "manual_vehicle_body" in base else np.zeros(len(source), bool)
    measured = valid & (point_type == 1) & ~manual_vehicle & allowed[keys.clip(0, len(allowed)-1)] & ~vehicle_cells[keys.clip(0, len(allowed)-1)]
    # Robust median per 0.5 m cell.  Only classified observed ground enters.
    z = np.full(len(allowed), np.nan)
    order = np.argsort(keys[measured]); kk = keys[measured][order]; zz = np.asarray(source[measured, 2])[order]
    starts = np.r_[0, np.flatnonzero(kk[1:] != kk[:-1]) + 1] if len(kk) else np.empty(0, int)
    for start, stop in zip(starts, np.r_[starts[1:], len(kk)]): z[kk[start]] = np.median(zz[start:stop])
    z = remove_raised_islands(z.reshape(shape), allowed.reshape(shape)).ravel()
    coarse, distance_cells, residual = harmonic_fill(z.reshape(shape), allowed.reshape(shape))
    x, y, fine_h, fine_mask = fine_surface(coarse, allowed.reshape(shape), origin, cell_m, args.fine_m)
    vertices, faces = build_mesh(x, y, fine_h, fine_mask)
    if not np.isfinite(fine_h[fine_mask]).all() or not len(faces): raise RuntimeError("finite surface/mesh check failed")
    out.mkdir(parents=True)
    write_mesh_ply(out / "ground_surface_mesh.ply", vertices, faces)
    np.savez_compressed(out / "ground_surface.npz", x=x, y=y, height=fine_h.astype("<f4"), permitted=fine_mask,
                        observed_coarse=np.isfinite(z).reshape(shape), support_distance_m=(distance_cells * cell_m).astype("<f4"),
                        coarse_height=coarse.astype("<f4"), coarse_allowed=allowed.reshape(shape), coarse_excluded=excluded.reshape(shape))
    view = out / "cc_view"; view.mkdir()
    export_view(view / "01_ground_surface_blue.ply", vertices, np.broadcast_to(BLUE, (len(vertices), 3)))
    # Context is optional for collision but makes the CC review interpretable.
    context = valid & ~measured
    blocked = context & ~allowed[keys.clip(0, len(allowed)-1)]
    vehicles = context & (vehicle_cells[keys.clip(0, len(allowed)-1)] | (point_type == 3) | manual_vehicle)
    blocked &= ~vehicles
    export_view(view / "02_blocked_context_brown.ply", np.asarray(source[blocked]), np.broadcast_to(BROWN, (int(blocked.sum()), 3)))
    export_view(view / "03_removed_vehicles_orange.ply", np.asarray(source[vehicles]), np.broadcast_to(ORANGE, (int(vehicles.sum()), 3)))
    _save_visuals(out, x, y, fine_h, fine_mask, np.repeat(np.repeat(distance_cells * cell_m, int(round(cell_m/args.fine_m)), axis=0), int(round(cell_m/args.fine_m)), axis=1))
    manifest = {"status": "continuous-simulation-surface", "source": str(args.source), "source_sha256": actual_hash,
                "baseline": str(args.baseline), "decisions": str(args.decisions) if args.decisions else None,
                "decisions_sha256": _sha(args.decisions) if args.decisions else None,
                "frame": "raw PAIR360 XYZ metres; no rotation, scale or origin transform", "design_policy": str(design_path) if design_path else None,
                "fine_cell_m": args.fine_m, "coarse_cell_m": cell_m, "permitted_coarse_cells": int(allowed.sum()),
                "observed_coarse_cells": int((np.isfinite(z) & allowed).sum()), "filled_coarse_cells": int((allowed & ~np.isfinite(z)).sum()),
                "permitted_fine_vertices": int(len(vertices)), "triangles": int(len(faces)),
                "finite_permitted_coverage": float(np.isfinite(fine_h[fine_mask]).mean()), "harmonic_residual_m": residual,
                "excluded_coarse_cells": int(excluded.sum()), "vehicle_coarse_cells": int(vehicle_cells.sum()),
                "files": ["ground_surface_mesh.ply", "ground_surface.npz", "surface_overview.png", "surface_cross_section.png"],
                "limits": "Approximate car-free collision design.  Tree/exclusion polygons are holes; all other permitted gaps are interpolated from observed reviewed ground.  This is not semantic ground truth or a walking certification."}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
