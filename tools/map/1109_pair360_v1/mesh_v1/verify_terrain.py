"""Check the released scene using MuJoCo rays, route clearance and Go2 foot contacts."""
import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy import ndimage

from load_go2 import SCENE_DIR, check_menagerie_stand


def ray(model, data, origin, direction, groups):
    hit = np.array([-1], dtype=np.int32)
    distance = mujoco.mj_ray(model, data, np.asarray(origin, dtype=float),
                             np.asarray(direction, dtype=float), groups, True, -1, hit)
    return distance, hit[0]


def check(scene, surface, go2=None):
    model = mujoco.MjModel.from_xml_path(str(scene/"scene.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    meta = json.loads((scene/"manifest.json").read_text(encoding="utf-8"))
    with surface.open("rb") as src:
        if meta["surface_sha256"] != hashlib.file_digest(src, "sha256").hexdigest():
            raise ValueError("Different surface used for generation and validation")
    terrain_only = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)
    solid_only = np.array([0, 0, 1, 0, 1, 0], dtype=np.uint8)
    direction = [0, 0, -1]
    ray_z = 40.0
    rng = np.random.default_rng(1601)
    with np.load(surface) as d:
        x, y, heights, valid = (d[k] for k in ["x", "y", "height", "permitted"])
        if "ground_refinement" in meta:
            with np.load(scene/"ground_adjustments.npz") as change:
                idx = change["flat_index"]
                r, c = np.unravel_index(idx, heights.shape)
                if d["observed_coarse"][r//5, c//5].any() or not valid[r, c].all():
                    raise ValueError("Ground refinement crossed a protected measured or excluded cell")
                heights.flat[idx] += change["delta_z_m"]
        quad = valid[1:, 1:] & valid[1:, :-1] & valid[:-1, 1:] & valid[:-1, :-1]
        ids = np.flatnonzero(quad)
        rows, cols = np.unravel_index(rng.choice(ids, min(1500, len(ids)), replace=False), quad.shape)
        errors, diagonal_errors = [], []
        for r, c in zip(rows, cols):
            u, v = .23, .71
            pos = (x[c]+u*(x[c+1]-x[c]), y[r]+v*(y[r+1]-y[r]), ray_z)
            distance, _ = ray(model, data, pos, direction, terrain_only)
            if distance < 0:
                raise RuntimeError(f"Missing surface at {pos}")
            expected = ((1-v)*heights[r, c] + u*heights[r+1, c+1] + (v-u)*heights[r+1, c])
            errors.append(abs((ray_z-distance)-expected))
            edge_pos = (x[c]+.0001, y[r]+.0001, ray_z)
            edge_distance, _ = ray(model, data, edge_pos, direction, terrain_only)
            edge_expected = .999*heights[r, c]+.001*heights[r+1, c+1]
            diagonal_errors.append(abs(ray_z-edge_distance-edge_expected))
        invalid = (~quad) & (ndimage.distance_transform_edt(~quad) >= 4)
        rows, cols = np.unravel_index(rng.choice(np.flatnonzero(invalid), 250, replace=False), quad.shape)
        hole_hits = sum(ray(model, data, (x[c]+.01, y[r]+.01, ray_z), direction, terrain_only)[0] >= 0
                        for r, c in zip(rows, cols))
    route = np.asarray(meta["route_xyz_m"])[:, :2]
    path = []
    for a, b in zip(route, route[1:]):
        samples = max(1, int(np.ceil(np.linalg.norm(b-a)/.1)))
        path.extend(a+(b-a)*t for t in np.linspace(0, 1, samples, endpoint=False))
    path.append(route[-1])
    probe_heights, blocked = [], []
    for i, center in enumerate(path):
        cross = []
        for offset in ([0, 0], [.24, .14], [.24, -.14], [-.24, .14], [-.24, -.14]):
            xy = center+offset
            dist, _ = ray(model, data, [*xy, ray_z], direction, terrain_only)
            if dist < 0:
                raise RuntimeError(f"Route leaves the floor at {xy}")
            floor = ray_z-dist
            cross.append(floor)
            # Upward and downward rays cover legs and torso up to 0.55 m.
            low = ray(model, data, [*xy, floor+.01], [0, 0, 1], solid_only)[0]
            high = ray(model, data, [*xy, floor+.55], direction, solid_only)[0]
            if (0 <= low <= .54) or (0 <= high <= .54):
                blocked.append(xy.tolist())
        probe_heights.append(cross[0])
    report = {"mujoco_version": mujoco.__version__, "scene_xml_sha256": hashlib.sha256((scene/"scene.xml").read_bytes()).hexdigest(),
              "reference_map_sha256": meta["reference_map_sha256"], "geom_count": model.ngeom, "hfields": model.nhfield,
              "v9_surface_rays": len(errors), "max_vertical_error_m": float(np.max(errors)),
              "hole_rays": len(rows), "hole_hits": int(hole_hits), "route_length_m": float(np.linalg.norm(np.diff(route, axis=0), axis=1).sum()),
              "route_floor_rays": 5*len(path), "max_center_step_per_10cm_m": float(np.abs(np.diff(probe_heights)).max()),
              "route_clearance_intersections": len(blocked), "blocked_probe_examples": blocked[:6]}
    report["diagonal_probe"] = {"rays": len(diagonal_errors), "above_2cm": int(np.sum(np.asarray(diagonal_errors)>.02)),
                                "max_error_m": float(max(diagonal_errors)), "xy_offset_from_vertex_m": [.0001, .0001]}
    report["context_sensor_checks"] = {}
    for cls, group in [("tree_solid", 2), ("tree_crown", 3), ("structure", 4)]:
        ids = np.flatnonzero(model.geom_group == group)
        if not len(ids):
            continue
        groups = np.zeros(6, dtype=np.uint8)
        groups[group] = 1
        tested = rng.choice(ids, min(32, len(ids)), replace=False)
        sensor_hits = 0
        for idx in tested:
            size_x = model.geom_size[idx, 0]
            pos = data.geom_xpos[idx]+[size_x+.02, 0, 0]
            if ray(model, data, pos, [-1, 0, 0], groups)[0] >= 0:
                sensor_hits += 1
        if sensor_hits != len(tested):
            raise RuntimeError(f"Invisible {cls} proxy in ray test")
        report["context_sensor_checks"][cls] = int(sensor_hits)
    if np.max(errors) > .015 or hole_hits or blocked:
        raise RuntimeError(f"Terrain check failed: {report}")
    probe = mujoco.MjSpec.from_file(str(scene/"scene.xml"))
    launch = np.array(meta["route_xyz_m"][0], dtype=float)
    launch[2] += .7
    ball = probe.worldbody.add_body(name="drop_test", pos=launch)
    ball.add_freejoint()
    ball.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[.08, 0, 0], mass=1.)
    pm = probe.compile()
    pd = mujoco.MjData(pm)
    touched = False
    for _ in range(round(1/pm.opt.timestep)):
        mujoco.mj_step(pm, pd)
        if pd.ncon:
            touched = True
    if not touched or abs(pd.qpos[2]-meta["route_xyz_m"][0][2]-.08) > .04:
        raise RuntimeError("Falling sphere failed to settle on the start tile")
    report["drop_test"] = {"radius_m": .08, "start_z_m": float(launch[2]), "end_z_m": float(pd.qpos[2]),
                           "contact": touched}
    if go2:
        report["go2_stand"] = check_menagerie_stand(go2, scene_dir=scene)
        report["go2_xml_sha256"] = hashlib.sha256(go2.read_bytes()).hexdigest()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=SCENE_DIR)
    parser.add_argument("--surface", type=Path, default=Path(__file__).resolve().parents[2] /
                        "ground_seperation/data/PAIR360_demo/20261109_canopy_floor_v9_smoothed/ground_surface.npz")
    parser.add_argument("--go2", type=Path)
    opts = parser.parse_args()
    report = check(opts.scene.resolve(), opts.surface, opts.go2)
    print(json.dumps(report, indent=2))
    (opts.scene/"verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
