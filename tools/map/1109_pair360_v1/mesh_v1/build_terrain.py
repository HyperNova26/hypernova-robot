"""Build PAIR360 MuJoCo height fields and measured obstacle proxies from project assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
MAP_TOOLS = PROJECT / "ground_seperation/tools/map"
sys.path.insert(0, str(MAP_TOOLS))
from export_final_sim import rectangles, write_hfield
from trees import filled_ground, segment, tree_geoms

SURFACE = PROJECT / "ground_seperation/data/PAIR360_demo/20261109_canopy_floor_v9_smoothed/ground_surface.npz"
REFERENCE = ROOT.parent / "output/reference_map.pcd"
GROUND = ROOT.parent / "output/map_v1_ground.pcd"
WAYPOINTS = [[-16, 170], [-16, 175], [-17, 179], [-18, 182], [-16, 185], [-12, 185], [-10, 185]]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def xyz_text(values):
    return " ".join(f"{v:.9g}" for v in values)


def read_reference(path):
    fields = {}
    with path.open("rb") as stream:
        for line in stream:
            key, _, value = line.decode("ascii").strip().partition(" ")
            fields[key] = value
            if key == "DATA":
                break
        offset = stream.tell()
    if (fields["FIELDS"].split(), fields["SIZE"].split(), fields["TYPE"].split(),
        fields["DATA"]) != (["x", "y", "z", "intensity", "label"], ["4"] * 5, ["F", "F", "F", "F", "U"], "binary"):
        raise ValueError(f"Unexpected PCD schema in {path}")
    dtype = [(name, "<u4" if name == "label" else "<f4") for name in fields["FIELDS"].split()]
    points = np.memmap(path, dtype=dtype, offset=offset, mode="r")
    if len(points) != int(fields["POINTS"]):
        raise ValueError("Reference map length and header differ")
    return points


def read_ground(path):
    """separate_ground.py output as the (x, y, z, label=1) view the builders use, plus source ids."""
    with path.open("rb") as stream:
        for line in stream:
            if line.startswith(b"FIELDS") and line.split()[1:] != [b"x", b"y", b"z", b"intensity", b"source"]:
                raise ValueError(f"Unexpected ground schema in {path}")
            if line.startswith(b"DATA"):
                break
        offset = stream.tell()
    raw = np.memmap(path, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4"), ("source", "<u4")],
                    offset=offset, mode="r")
    points = np.empty(len(raw), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("label", "<u4")])
    for name in "xyz":
        points[name] = raw[name]
    points["label"] = 1
    return points, np.asarray(raw["source"])


def heightfields(x, y, z, valid, asset, world, folder, name):
    mask = valid[1:, 1:] & valid[:-1, 1:] & valid[:-1, :-1] & valid[1:, :-1]
    coverage = np.zeros_like(mask, dtype=np.uint8)
    spans = rectangles(mask)
    (folder / "hfields").mkdir(exist_ok=True)
    for i, (left, right, bottom, top) in enumerate(spans):
        ident = f"pair360_{name}_{i:03d}"
        relative = f"hfields/{ident}.bin"
        destination = folder / relative
        # The reference writer uses exclusive creation.
        scratch = destination.with_suffix(f".{uuid4().hex}.tmp")
        minimum, span = write_hfield(scratch, z[bottom:top + 1, left:right + 1])
        scratch.replace(destination)
        size = [(x[right]-x[left])/2, (y[top]-y[bottom])/2, span, 0.1]
        pos = [(x[right]+x[left])/2, (y[top]+y[bottom])/2, minimum]
        ET.SubElement(asset, "hfield", name=ident, file=relative, size=xyz_text(size))
        ET.SubElement(world, "geom", name=ident, type="hfield", hfield=ident,
                      pos=xyz_text(pos), friction="1 0.005 0.0001", rgba="0.38 0.44 0.42 1", group="0")
        coverage[bottom:top, left:right] += 1
    if not np.array_equal(coverage, mask):
        raise ValueError("Incomplete height field coverage")
    return {"hfields": len(spans), "quads": int(mask.sum())}


def exterior_ground(cloud, surface, asset, world, folder):
    # Preserve all S-004 no-go polygons and its reviewed, interpolated surface.
    xlim, ylim = surface["x"][[0, -1]], surface["y"][[0, -1]]
    spacing = 0.5
    outside = ((cloud["x"] < xlim[0]-spacing) | (cloud["x"] > xlim[1]+spacing)
               | (cloud["y"] < ylim[0]-spacing) | (cloud["y"] > ylim[1]+spacing))
    p = cloud[(cloud["label"] == 1) & outside]
    if not len(p):
        return {"hfields": 0, "quads": 0, "points": 0}
    xy = np.column_stack((p["x"], p["y"]))
    bins = np.floor(xy / spacing).astype(np.int32)
    lo = bins.min(axis=0)
    bins -= lo
    nx, ny = bins.max(axis=0) + 1
    if int(nx)*int(ny) > 8_000_000:
        raise ValueError("Exterior ground extent exceeds expected site size")
    keys = bins[:, 1].astype(np.int64)*nx + bins[:, 0]
    order = np.argsort(keys, kind="stable")
    cells, starts, counts = np.unique(keys[order], return_index=True, return_counts=True)
    zpoints = p["z"][order]
    zmin, zmax = np.minimum.reduceat(zpoints, starts), np.maximum.reduceat(zpoints, starts)
    keep = (counts >= 3) & ((zmax-zmin) <= 0.16)
    z = np.full((ny, nx), np.nan)
    z.flat[cells[keep]] = np.add.reduceat(zpoints.astype(float), starts)[keep]/counts[keep]
    mask = np.isfinite(z)
    nearby_min = ndimage.minimum_filter(np.where(mask, z, np.inf), 3)
    nearby_max = ndimage.maximum_filter(np.where(mask, z, -np.inf), 3)
    mask &= (nearby_max - nearby_min <= 0.28)
    quads = mask[1:, 1:] & mask[1:, :-1] & mask[:-1, 1:] & mask[:-1, :-1]
    components, _ = ndimage.label(quads)
    large = np.bincount(components.ravel())[components] >= 4
    kept = quads & large
    supported = np.zeros_like(mask)
    for r, c in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        supported[r:r+kept.shape[0], c:c+kept.shape[1]] |= kept
    mask &= supported
    x = (lo[0]+np.arange(nx)+0.5)*spacing
    y = (lo[1]+np.arange(ny)+0.5)*spacing
    report = heightfields(x, y, z, mask, asset, world, folder, "measured")
    return {**report, "points": len(p), "spacing_m": spacing, "isolated_quads_excluded": int((quads & ~kept).sum())}


def refine_fill(points, source_ids, surface, folder):
    """Re-anchor inferred floor only where multiple subsequent returns agree."""
    p = points[(points["label"] == 1) & np.isin(source_ids, [1, 2])]
    x, y, base, permitted = [surface[k] for k in ("x", "y", "height", "permitted")]
    eligible = surface["coarse_allowed"] & ~surface["observed_coarse"]
    dx, dy = x[1]-x[0], y[1]-y[0]
    col = np.floor((p["x"]-x[0])/dx+.5).astype(int)
    row = np.floor((p["y"]-y[0])/dy+.5).astype(int)
    valid = (col >= 0) & (col < len(x)) & (row >= 0) & (row < len(y))
    q, r, c = p[valid], row[valid], col[valid]
    valid = permitted[r, c] & eligible[r//5, c//5]
    q, r, c = q[valid], r[valid], c[valid]
    residual = q["z"]-base[r, c]
    keys = (r//5)*eligible.shape[1]+c//5
    correction = np.zeros(eligible.shape)
    used = np.zeros_like(eligible)
    point_count = 0
    if len(keys):
        order = np.argsort(keys)
        bins, starts, counts = np.unique(keys[order], return_counts=True, return_index=True)
        values = residual[order]
        for key, start, count in zip(bins, starts, counts):
            if count < 4:
                continue
            group = values[start:start+count]
            low, med, high = np.percentile(group, [10, 50, 90])
            if high-low <= .09 and max(abs(low), abs(high)) <= .12:
                correction.flat[key] = med
                used.flat[key] = True
                point_count += count
    fine_mask = np.repeat(np.repeat(used, 5, axis=0), 5, axis=1) & permitted
    expanded = np.repeat(np.repeat(correction, 5, axis=0), 5, axis=1)
    # Wide smoothing and a 0.5 m fade keep cell-edge steps a Go2 foot can feel (<~2 cm/10 cm) out.
    weights = ndimage.gaussian_filter(fine_mask.astype(float), 3.0)
    smoothed = ndimage.gaussian_filter(expanded*fine_mask, 3.0)/np.maximum(weights, .001)
    fade = np.clip((ndimage.distance_transform_edt(fine_mask)-.5)/5, 0, 1)
    delta = np.where(fine_mask, smoothed*fade, 0).astype("f4")
    indices = np.flatnonzero(delta)
    np.savez_compressed(folder/"ground_adjustments.npz", flat_index=indices.astype("u4"), delta_z_m=delta.ravel()[indices])
    return base+delta, {"subsequent_measured_points": int(point_count), "accepted_50cm_cells": int(used.sum()),
                        "changed_10cm_vertices": len(indices), "max_abs_change_m": float(np.abs(delta).max())}


def context_geoms(points, world, route):
    # Only the corridor plus local laser range gets obstacle geometry.
    # Physics and sensor rays see the same boxes for low rigid obstacles.
    margin = 35.0
    lo, hi = route.min(axis=0)-margin, route.max(axis=0)+margin
    subset = points[(points["label"] >= 2) & (points["label"] <= 4)
                    & (points["x"] >= lo[0]) & (points["x"] <= hi[0])
                    & (points["y"] >= lo[1]) & (points["y"] <= hi[1])]
    summary = {"bounds_xy": [lo.tolist(), hi.tolist()], "classes": {}}
    for label, name, step, color in [(4, "structure", .45, ".43 .48 .52 1")]:
        p = subset[subset["label"] == label]
        if not len(p):
            summary["classes"][name] = {"points": 0, "boxes": 0}
            continue
        grid = np.floor(np.column_stack((p["x"], p["y"], p["z"]))/step).astype(np.int32)
        occupied, count = np.unique(grid, axis=0, return_counts=True)
        occupied = occupied[count >= 2]
        n = 0
        for layer in np.unique(occupied[:, 2]):
            xy = occupied[occupied[:, 2] == layer, :2]
            origin = xy.min(axis=0)
            xy = xy-origin
            mask = np.zeros(tuple((xy.max(axis=0)+1)[::-1]), dtype=bool)
            mask[xy[:, 1], xy[:, 0]] = True
            for left, right, bottom, top in rectangles(mask):
                center = ((origin[0]+(left+right)/2)*step, (origin[1]+(bottom+top)/2)*step, (layer+.5)*step)
                size = ((right-left)*step/2, (top-bottom)*step/2, step/2)
                ET.SubElement(world, "geom", name=f"pair360_{name}_{n}", type="box", pos=xyz_text(center),
                              size=xyz_text(size), rgba=color, group=str(label), **(
                                  {"contype": "0", "conaffinity": "0"} if label == 3 else {}))
                n += 1
        summary["classes"][name] = {"points": len(p), "occupied_voxels": len(occupied),
                                    "boxes": n, "voxel_width_m": step}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--ground-only", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "scene")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene = ET.Element("mujoco", model="PAIR360 walking environment")
    ET.SubElement(scene, "option", timestep="0.002", gravity="0 0 -9.81")
    ET.SubElement(scene, "statistic", center="-16 178 1.5", extent="17")
    asset, world = ET.SubElement(scene, "asset"), ET.SubElement(scene, "worldbody")
    route = np.array(WAYPOINTS, dtype=float)
    with np.load(SURFACE) as surf:
        report = {"frame": "pair360_map", "coordinates": "raw PAIR360 XYZ, metres, Z up",
                  "status": "simulation test candidate; automatic semantic classes await team review",
                  "surface_sha256": digest(SURFACE), "source": SURFACE.parent.name}
        heights = surf["height"]
        if not args.ground_only:
            points = read_reference(args.reference)
            report["reference_map_sha256"] = digest(args.reference)
            prov = args.reference.parent / "provenance.npz"
            with np.load(prov) as mapping:
                ids = mapping["source_id"]
                if len(ids) != len(points):
                    raise ValueError("Reference provenance length mismatch")
            report["provenance_sha256"] = digest(prov)
            ground, ground_ids = read_ground(GROUND)
            report["ground_map_sha256"] = digest(GROUND)
            heights, report["ground_refinement"] = refine_fill(ground, ground_ids, surf, out)
            report["exterior_ground"] = exterior_ground(ground, surf, asset, world, out)
            report["context"] = context_geoms(points, world, route)
            trees = segment(np.column_stack((points["x"], points["y"], points["z"])), np.asarray(points["label"]),
                            ids, filled_ground(surf), route)
            (out/"trees.json").write_text(json.dumps(trees, indent=1), encoding="utf-8")
            report["trees"] = {"area_xy": trees["area_xy"], "count": tree_geoms(trees["trees"], world),
                               "from_trunk_points": sum(t["trunk_evidence"] == "trunk_points" for t in trees["trees"]),
                               "solid": "trunk cylinder + root mound (contact and rays)",
                               "crown": "three ellipsoids, rays only"}
        else:
            report["reference_map_sha256"] = None
        report["reviewed_ground"] = heightfields(surf["x"], surf["y"], heights, surf["permitted"], asset, world, out, "ground")
        ix = np.abs(route[:, 0, None]-surf["x"]).argmin(axis=1)
        iy = np.abs(route[:, 1, None]-surf["y"]).argmin(axis=1)
        if not surf["permitted"][iy, ix].all():
            raise ValueError("Waypoint over missing ground")
        report["route_xyz_m"] = np.column_stack((route, heights[iy, ix])).tolist()
        report["spawn_yaw_deg"] = 90.0
    ET.indent(scene)
    ET.ElementTree(scene).write(out/"scene.xml", encoding="utf-8", xml_declaration=True)
    (out/"manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
