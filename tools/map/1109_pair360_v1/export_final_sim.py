# SPDX-License-Identifier: Apache-2.0
"""Export an accepted continuous ground as portable MuJoCo and Isaac scenes.

The input mesh is an explicitly supplied accepted surface.  MuJoCo mesh collision would turn a
terrain mesh into a convex hull, so collision is represented by a lossless
tiling of its regular 10 cm quad grid into MuJoCo hfields.  The original
triangle mesh remains a non-colliding visual asset.  The USD contains the
original triangle mesh and a static triangle-mesh collision API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import tempfile
from pathlib import Path

import mujoco
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, Vt


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as f:
        header = []
        while True:
            row = f.readline()
            if not row:
                raise ValueError("PLY header truncated")
            header.append(row.decode("ascii").strip())
            if header[-1] == "end_header":
                break
        nvert = next(int(row.split()[-1]) for row in header if row.startswith("element vertex "))
        nface = next(int(row.split()[-1]) for row in header if row.startswith("element face "))
        vertices = np.fromfile(f, "<f4", nvert * 3).reshape(nvert, 3)
        rows = np.fromfile(f, np.dtype([("n", "u1"), ("v", "<u4", (3,))]), nface)
    if not np.all(rows["n"] == 3):
        raise ValueError("only triangle meshes are supported")
    return vertices, rows["v"]


def read_ply_xyz(path: Path) -> np.ndarray:
    """Read binary-little-endian scalar PLY vertices, retaining XYZ only.

    The remainder handoff also has intensity and original_index.  Those are
    intentionally not copied into USD: this is a selectable visual context
    layer, not a semantic or collision asset.
    """
    type_map = {
        "char": "i1", "uchar": "u1", "short": "i2", "ushort": "u2",
        "int": "i4", "uint": "u4", "int64": "i8", "uint64": "u8",
        "float": "f4", "double": "f8",
    }
    with path.open("rb") as f:
        header = []
        while True:
            row = f.readline()
            if not row:
                raise ValueError("PLY header truncated")
            text = row.decode("ascii").strip(); header.append(text)
            if text == "end_header":
                break
        if header[0] != "ply" or "format binary_little_endian 1.0" not in header:
            raise ValueError("expected binary_little_endian PLY")
        nvert = next(int(r.split()[-1]) for r in header if r.startswith("element vertex "))
        begin = header.index(next(r for r in header if r.startswith("element vertex "))) + 1
        properties = []
        for r in header[begin:]:
            if r.startswith("element "):
                break
            if r.startswith("property list"):
                raise ValueError("list-valued vertex properties are unsupported")
            if r.startswith("property "):
                _, typ, name = r.split(); properties.append((name, "<" + type_map[typ]))
        names = {name for name, _ in properties}
        if not {"x", "y", "z"}.issubset(names):
            raise ValueError("PLY must contain x/y/z vertex properties")
        data = np.fromfile(f, np.dtype(properties), nvert)
    return np.column_stack((data["x"], data["y"], data["z"])).astype(np.float32)


def rectangles(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Exact cover by runs of equal X interval accumulated across Y rows.

    The mask represents *quads*, not vertices.  Each output tile therefore
    owns all its quads and later expands by one sample on every high edge.
    Adjacent tiles share their boundary samples without creating a collision
    seam.
    """
    active: dict[tuple[int, int], tuple[int, int]] = {}
    result = []
    for y, row in enumerate(mask):
        runs = []
        on = False
        for x, value in enumerate(row):
            if value and not on:
                start = x; on = True
            if on and (not value or x == len(row) - 1):
                runs.append((start, x if not value else x + 1)); on = False
        new = {}
        for interval in runs:
            new[interval] = (active.pop(interval)[0], y + 1) if interval in active else (y, y + 1)
        result.extend((x0, x1, y0, y1) for (x0, x1), (y0, y1) in active.items())
        active = new
    result.extend((x0, x1, y0, y1) for (x0, x1), (y0, y1) in active.items())
    # An interval of one quad expands to two hfield samples, which is valid.
    # Reject only a malformed zero-quad interval.
    if any(x1 - x0 < 1 or y1 - y0 < 1 for x0, x1, y0, y1 in result):
        raise ValueError("a hfield tile needs at least one quad in each direction")
    return result


def write_hfield(path: Path, values: np.ndarray) -> tuple[float, float]:
    zmin, zmax = float(values.min()), float(values.max())
    span = max(zmax - zmin, 1e-6)
    normal = ((values - zmin) / span).astype("<f4")
    with path.open("xb") as f:
        f.write(struct.pack("<ii", values.shape[0], values.shape[1]))
        f.write(normal.tobytes(order="C"))
    return zmin, span


def xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;")


def write_mujoco_viewer(root: Path) -> str:
    """Write a no-extra-dependency local viewer for a teammate's visual check."""
    path = root / "view_mujoco.py"
    path.write_text('''"""Open the PAIR360 ground-only MuJoCo scene (requires `pip install mujoco`)."""
from __future__ import annotations

import time
from pathlib import Path

import mujoco
import mujoco.viewer


scene = Path(__file__).with_name("scene.xml")
model = mujoco.MjModel.from_xml_path(str(scene))
data = mujoco.MjData(model)
mujoco.mj_forward(model, data)
with mujoco.viewer.launch_passive(model, data) as viewer:
    viewer.cam.lookat[:] = model.stat.center
    viewer.cam.distance = max(1.0, 2.0 * model.stat.extent)
    viewer.cam.elevation = -65.0
    viewer.cam.azimuth = 135.0
    while viewer.is_running():
        mujoco.mj_step(model, data)
        viewer.sync()
        time.sleep(model.opt.timestep)
''', encoding="utf-8")
    return str(path)


def export_mujoco(out: Path, surface: dict) -> dict:
    root = out / "mujoco"; assets = root / "hfields"
    root.mkdir(parents=True); assets.mkdir()
    x, y, height, mask = (surface[k] for k in ("x", "y", "height", "permitted"))
    quad = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, :-1] & mask[1:, 1:]
    tiles = rectangles(quad)
    asset_xml, geom_xml, records = [], [], []
    spacing_x, spacing_y = float(x[1] - x[0]), float(y[1] - y[0])
    for i, (x0, x1, y0, y1) in enumerate(tiles):
        values = height[y0:y1 + 1, x0:x1 + 1]
        name = f"tile_{i:03d}"; file = assets / f"{name}.bin"
        zmin, span = write_hfield(file, values)
        cx, cy = float((x[x0] + x[x1]) / 2), float((y[y0] + y[y1]) / 2)
        sx, sy = float((x1 - x0) * spacing_x / 2), float((y1 - y0) * spacing_y / 2)
        asset_xml.append(f'<hfield name="{name}" file="hfields/{name}.bin" size="{sx:.9g} {sy:.9g} {span:.9g} 0.1"/>')
        geom_xml.append(f'<geom name="{name}" type="hfield" hfield="{name}" pos="{cx:.9g} {cy:.9g} {zmin:.9g}" friction="1 0.005 0.0001" rgba="0.12 0.45 0.9 1"/>')
        records.append(dict(name=name, x_indices=[x0, x1], y_indices=[y0, y1], center_xy=[cx, cy], half_size_xy=[sx, sy], z_min=zmin, z_span=span, file=str(file.relative_to(out))))
    xml = "\n".join([
        '<mujoco model="PAIR360 continuous ground">',
        '  <compiler angle="radian" coordinate="local"/>',
        '  <option gravity="0 0 -9.81" timestep="0.002"/>',
        '  <asset>', *["    " + row for row in asset_xml],
        '  </asset>', '  <worldbody>',
        *["    " + row for row in geom_xml], '  </worldbody>', '</mujoco>', ''
    ])
    xml_path = root / "scene.xml"; xml_path.write_text(xml, encoding="utf-8")
    covered = np.zeros_like(quad, dtype=np.int16)
    for x0, x1, y0, y1 in tiles:
        covered[y0:y1, x0:x1] += 1
    if not np.array_equal(covered == 1, quad):
        raise RuntimeError("hfield tiles do not exactly cover mesh quads")
    return dict(scene=str(xml_path.relative_to(out)), tiles=records, expected_tiles=len(tiles),
                collision_quad_count=int(quad.sum()), exact_quad_cover=True,
                local_viewer=str(Path(write_mujoco_viewer(root)).relative_to(out)))


def export_usd(out: Path, vertices: np.ndarray, faces: np.ndarray) -> dict:
    root = out / "isaac"; root.mkdir(parents=True)
    # Binary USD avoids serialising millions of triangle indices as enormous
    # text while remaining a portable USD asset for Isaac.
    path = root / "ground_collision.usdc"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, "/World/PAIR360Ground")
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(vertices.astype(np.float32)))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(faces), 3, dtype=np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.astype(np.int32).reshape(-1)))
    mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr().Set(True)
    mesh.CreateDisplayColorAttr().Set([(0.12, 0.45, 0.9)])
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    collision = UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim())
    collision.CreateApproximationAttr().Set(UsdPhysics.Tokens.none)
    stage.SetDefaultPrim(world.GetPrim())
    stage.GetRootLayer().Save()
    # Reopen to prove the written USD has the expected topology and collision APIs.
    checked = Usd.Stage.Open(str(path)); prim = checked.GetPrimAtPath("/World/PAIR360Ground")
    checkmesh = UsdGeom.Mesh(prim)
    if len(checkmesh.GetPointsAttr().Get()) != len(vertices) or len(checkmesh.GetFaceVertexCountsAttr().Get()) != len(faces):
        raise RuntimeError("USD topology reload mismatch")
    if not prim.HasAPI(UsdPhysics.CollisionAPI) or not prim.HasAPI(UsdPhysics.MeshCollisionAPI):
        raise RuntimeError("USD collision APIs missing")
    return dict(file=str(path.relative_to(out)), vertices=len(vertices), triangles=len(faces),
                collision_approximation="none", raw_frame_identity=True)


def export_remainder_usd(out: Path, remainder_ply: Path) -> dict:
    """Write an optional, independently selectable Isaac-only context layer."""
    points = read_ply_xyz(remainder_ply)
    root = out / "isaac"; path = root / "remainder_points.usdc"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    cloud = UsdGeom.Points.Define(stage, "/World/SourceRemainder")
    cloud.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points))
    cloud.CreateWidthsAttr(Vt.FloatArray([0.035]))
    cloud.CreateDisplayColorAttr().Set([(0.43, 0.25, 0.14)])
    # No CollisionAPI is applied: the point cloud remains visual context only.
    stage.SetDefaultPrim(world.GetPrim()); stage.GetRootLayer().Save()
    checked = Usd.Stage.Open(str(path)); prim = checked.GetPrimAtPath("/World/SourceRemainder")
    if len(UsdGeom.Points(prim).GetPointsAttr().Get()) != len(points) or prim.HasAPI(UsdPhysics.CollisionAPI):
        raise RuntimeError("remainder USD reload or collision-scope mismatch")
    return dict(file=str(path.relative_to(out)), source=str(remainder_ply), points=len(points),
                collision=False, selectable_prim="/World/SourceRemainder", default_color="brown")


def export_isaac_scene(out: Path, remainder: dict | None) -> str:
    """Compose collision ground and optional visual context into one entry USD."""
    root = out / "isaac"; path = root / "scene.usda"
    layers = ["@ground_collision.usdc@"]
    if remainder is not None:
        layers.append("@remainder_points.usdc@")
    # Stage metadata is not inherited from sublayers.  Author it on this
    # launchable composition layer so Isaac sees the same raw metre Z-up frame.
    path.write_text("#usda 1.0\n(\n    defaultPrim = \"World\"\n    metersPerUnit = 1\n"
                    "    upAxis = \"Z\"\n    subLayers = [" + ", ".join(layers) + "]\n)\n", encoding="utf-8")
    checked = Usd.Stage.Open(str(path))
    if not checked.GetPrimAtPath("/World/PAIR360Ground").IsValid():
        raise RuntimeError("Isaac scene composition is missing ground")
    if remainder is not None and not checked.GetPrimAtPath("/World/SourceRemainder").IsValid():
        raise RuntimeError("Isaac scene composition is missing remainder")
    if (UsdGeom.GetStageUpAxis(checked) != UsdGeom.Tokens.z
            or UsdGeom.GetStageMetersPerUnit(checked) != 1.0
            or checked.GetDefaultPrim().GetPath().pathString != "/World"):
        raise RuntimeError("Isaac composition stage metadata mismatch")
    return str(path.relative_to(out))


def probe_mujoco(out: Path, surface: dict, expected_tiles: int) -> dict:
    xml = out / "mujoco" / "scene.xml"
    model = mujoco.MjModel.from_xml_path(str(xml)); data = mujoco.MjData(model)
    if model.nhfield != expected_tiles or model.ngeom != expected_tiles:
        raise RuntimeError("MuJoCo model count mismatch")
    x, y, height, mask = (surface[k] for k in ("x", "y", "height", "permitted"))
    quad = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, :-1] & mask[1:, 1:]
    candidates = np.argwhere(~quad)
    # Holes with allowed neighbours distinguish internal no-go from outside extent.
    internal_holes = np.array([(yy, xx) for yy, xx in candidates
                               if 0 < yy < quad.shape[0]-1 and 0 < xx < quad.shape[1]-1
                               and quad[yy-1:yy+2, xx-1:xx+2].any()])
    if not len(internal_holes):
        raise RuntimeError("no internal excluded quad available for hole validation")
    geom = np.array([-1], np.int32); ray = np.array([0.0, 0.0, -1.0])
    ztop = float(np.nanmax(height)) + 5.0
    mujoco.mj_forward(model, data)
    # Probe interior points against the source triangle interpolation.  This
    # checks hfield orientation and measures any diagonal convention error.
    errors = []
    # The representative middle sample of every permitted row run is robust
    # against tile boundaries and validates the compiled hfield orientation.
    sample = np.argwhere(quad)
    rng = np.random.default_rng(20261105)
    picks = sample[rng.choice(len(sample), size=min(401, len(sample)), replace=False)]
    offsets = ((0.23, 0.71), (0.71, 0.23), (0.37, 0.41))
    for yy, xx in picks:
      for u, v in offsets:
        px, py = x[xx] + u * (x[xx+1]-x[xx]), y[yy] + v * (y[yy+1]-y[yy])
        z00,z10,z01,z11 = height[yy,xx],height[yy,xx+1],height[yy+1,xx],height[yy+1,xx+1]
        expected = ((1-u)*z00 + (u-v)*z10 + v*z11) if u >= v else ((1-v)*z00 + u*z11 + (v-u)*z01)
        hit = mujoco.mj_ray(model, data, np.array([px, py, ztop]), ray, None, True, -1, geom)
        if hit < 0: raise RuntimeError("permitted quad did not collide")
        errors.append(abs((ztop-hit) - float(expected)))
    hole_picks = internal_holes[rng.choice(len(internal_holes), size=min(101, len(internal_holes)), replace=False)]
    hole_hits = []
    for hole_y, hole_x in hole_picks:
        hole_hits.append(mujoco.mj_ray(model, data, np.array([(x[hole_x]+x[hole_x+1])/2, (y[hole_y]+y[hole_y+1])/2, ztop]), ray, None, True, -1, None))
    # Test edges shared by distinct rectangular hfield tiles rather than all
    # grid edges.  An unshared tile boundary would produce a ray miss here
    # even if interior tests pass.
    seam_xy = []
    for x0, x1, y0, y1 in rectangles(quad):
        for yy in range(y0, y1):
            if x0 and quad[yy, x0 - 1] and quad[yy, x0]:
                seam_xy.append((x[x0], (y[yy] + y[yy + 1]) / 2))
            if x1 < quad.shape[1] and quad[yy, x1 - 1] and quad[yy, x1]:
                seam_xy.append((x[x1], (y[yy] + y[yy + 1]) / 2))
        for xx in range(x0, x1):
            if y0 and quad[y0 - 1, xx] and quad[y0, xx]:
                seam_xy.append(((x[xx] + x[xx + 1]) / 2, y[y0]))
            if y1 < quad.shape[0] and quad[y1 - 1, xx] and quad[y1, xx]:
                seam_xy.append(((x[xx] + x[xx + 1]) / 2, y[y1]))
    seam_xy = list(dict.fromkeys(seam_xy))
    if not seam_xy:
        raise RuntimeError("no shared hfield tile seam available for validation")
    seam_picks = [seam_xy[i] for i in rng.choice(len(seam_xy), size=min(101, len(seam_xy)), replace=False)]
    seam_hits = [mujoco.mj_ray(model, data, np.array([px, py, ztop]), ray, None, True, -1, None)
                 for px, py in seam_picks]
    if max(errors) > 1e-4 or any(hit >= 0 for hit in hole_hits) or any(hit < 0 for hit in seam_hits):
        raise RuntimeError(f"MuJoCo probe failed max_error={max(errors)} holes={max(hole_hits)} seams={min(seam_hits)}")
    return dict(model_compiled=True, hfields=int(model.nhfield), geoms=int(model.ngeom),
                interior_rays=len(picks)*len(offsets), maximum_raycast_error_m=max(errors),
                p95_raycast_error_m=float(np.percentile(errors, 95)),
                randomized_seed=20261105, hole_rays=len(hole_hits), maximum_hole_raycast_distance=float(max(hole_hits)),
                seam_rays=len(seam_hits), minimum_seam_raycast_distance=float(min(seam_hits)))


def ball_contact_check(out: Path, surface: dict) -> dict:
    """Compile a disposable probe model and verify a falling sphere contacts ground.

    The probe body exists only in the validation XML; it is never shipped in
    `scene.xml`.  The selected quad has the lowest four-corner height range,
    avoiding a deliberately steep curb or edge for this basic collision check.
    """
    x, y, height, mask = (surface[k] for k in ("x", "y", "height", "permitted"))
    quad = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, :-1] & mask[1:, 1:]
    yy, xx = min(np.argwhere(quad), key=lambda p: float(np.ptp(height[p[0]:p[0]+2, p[1]:p[1]+2])))
    u = v = 0.5
    z00,z10,z01,z11 = height[yy,xx],height[yy,xx+1],height[yy+1,xx],height[yy+1,xx+1]
    floor_z = float((1-u)*z00 + (u-v)*z10 + v*z11)
    px, py = float((x[xx]+x[xx+1])/2), float((y[yy]+y[yy+1])/2)
    scene = out / "mujoco" / "scene.xml"; temporary = out / "mujoco" / "_collision_probe.xml"
    probe_body = ('    <body name="validation_ball" pos="0 0 0">\n'
                  '      <freejoint name="validation_ball_free"/>\n'
                  '      <geom name="validation_ball_geom" type="sphere" size="0.15" density="1000"/>\n'
                  '    </body>\n')
    temporary.write_text(scene.read_text(encoding="utf-8").replace("  </worldbody>", probe_body + "  </worldbody>"), encoding="utf-8")
    try:
        model = mujoco.MjModel.from_xml_path(str(temporary)); data = mujoco.MjData(model)
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "validation_ball")
        qadr = model.jnt_qposadr[model.body_jntadr[body]]
        data.qpos[qadr:qadr+7] = [px, py, floor_z + 1.0, 1.0, 0.0, 0.0, 0.0]
        contacted = False
        for step in range(1500):
            mujoco.mj_step(model, data)
            if data.ncon:
                contacted = True
                break
        z_final = float(data.qpos[qadr+2])
        if not contacted or not (floor_z + 0.12 <= z_final <= floor_z + 0.25):
            raise RuntimeError(f"ball collision failed contact={contacted} z={z_final} floor={floor_z}")
        return dict(contacted=True, steps_to_contact=step + 1, probe_xy=[px, py],
                    expected_floor_z=floor_z, final_ball_center_z=z_final, ball_radius_m=0.15)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surface-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--remainder-ply", type=Path, help="optional display-only source-complement PLY")
    args = ap.parse_args(); out = args.out.resolve()
    if out.exists(): raise FileExistsError(f"refusing to overwrite: {out}")
    surface_dir = args.surface_dir.resolve(); surface = np.load(surface_dir / "ground_surface.npz")
    mesh_source = surface_dir / "ground_surface_mesh.ply"; vertices, faces = read_mesh(mesh_source)
    if int(surface["permitted"].sum()) != len(vertices) or len(faces) == 0:
        raise ValueError("surface NPZ/mesh invariant mismatch")
    out.mkdir(parents=True)
    print("stage=mujoco_hfields", flush=True)
    mj = export_mujoco(out, surface)
    print("stage=isaac_ground_usdc", flush=True)
    usd = export_usd(out, vertices, faces)
    print("stage=mujoco_rays", flush=True)
    probe = probe_mujoco(out, surface, mj["expected_tiles"])
    print("stage=mujoco_ball_contact", flush=True)
    contact = ball_contact_check(out, surface)
    print("stage=isaac_remainder", flush=True)
    remainder = export_remainder_usd(out, args.remainder_ply.resolve()) if args.remainder_ply else None
    print("stage=isaac_compose", flush=True)
    usd["scene"] = export_isaac_scene(out, remainder)
    manifest = dict(status="simulator_package_verified", source_surface=str(surface_dir), source_mesh_sha256=sha(mesh_source),
                    coordinate_frame="raw PAIR360 XYZ metres; identity pose; M-002 transform is intentionally not invented",
                    mujoco=mj, isaac=usd, mujoco_probe=probe, mujoco_ball_contact=contact,
                    optional_remainder_context=remainder,
                    physics_scope="Static ground collision only. Remaining point cloud is display-only and is packaged separately.",
                    geometry_policy="USD uses exact accepted triangle mesh with MeshCollisionAPI approximation=none. MuJoCo tiles the accepted regular-grid permitted quads into static hfields; excluded holes have no hfield collision.")
    (out / "simulator_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
