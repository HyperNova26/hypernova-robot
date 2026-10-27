# SPDX-License-Identifier: Apache-2.0
"""Small, metric synthetic smoke checks; no dataset or simulator GUI needed."""

import argparse
import copy
import shutil
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from pointcloud import (apply_transform, classify, level_cloud,
                  read_yaml, sample_height, save_cloud, write_yaml)
from exports import export_map2d, export_mujoco, mujoco_height, occupancy
from pair360_demo import execute

ROOT = Path(__file__).resolve().parents[3]


def box(center, length, width, height, base=0, step=0.08):
    x = np.linspace(center[0]-length/2, center[0]+length/2, int(length/step)+1)
    y = np.linspace(center[1]-width/2, center[1]+width/2, int(width/step)+1)
    z = np.linspace(base, base+height, int(height/step)+1)
    xx, yy = np.meshgrid(x, y)
    roof = np.column_stack((xx.ravel(), yy.ravel(), np.full(xx.size, base+height)))
    xx, zz = np.meshgrid(x, z)
    walls_y = [np.column_stack((xx.ravel(), np.full(xx.size, cy), zz.ravel())) for cy in (y[0], y[-1])]
    yy, zz = np.meshgrid(y, z)
    walls_x = [np.column_stack((np.full(yy.size, cx), yy.ravel(), zz.ravel())) for cx in (x[0], x[-1])]
    return np.concatenate([roof, *walls_y, *walls_x])


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    directory = tmp_path_factory.mktemp("terrain")
    raw = directory/"raw"
    raw.mkdir()
    cfg = read_yaml(ROOT/"sim_scenes/pair360_parking/frame.yaml")
    origin = np.array([12., 34., 2.])
    yaw = Rotation.from_euler("z", 25, degrees=True).as_matrix()
    t0 = np.eye(4)
    t0[:3, :3] = yaw
    t0[:3, 3] = -yaw @ origin
    cfg["T_demo_from_map_unleveled"] = t0.tolist()
    cfg["demo_frame"]["origin_in_map"] = origin.tolist()
    cfg["processing"]["ground"]["above_m"] = 0.18  # Preserve the 15 cm curb in the terrain.
    cfg["processing"]["isaac"]["random_samples"] = 1500
    xx, yy = np.meshgrid(np.arange(-10, 10.001, .1), np.arange(-8, 8.001, .1))
    zz = np.maximum(xx-3, 0)*.1  # Known 10% grade outside the leveling patch.
    curb = (np.abs(xx) <= 2) & (yy >= -6) & (yy <= -5.5)
    zz[curb] += .15
    ground = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    demo = np.concatenate((ground, box((-5, 3), 4.5, 2, 1.6), box((6, -3.5), 4, 4, 4, base=.3)))
    tilt = Rotation.from_euler("y", 2, degrees=True).as_matrix()
    unleveled = demo @ tilt.T
    points_map = apply_transform(unleveled, np.linalg.inv(t0))
    save_cloud(raw/"crop.ply", points_map)
    # Repeated in/out intervals and known orientation; world rotations are map poses.
    rows = []
    for k, x in enumerate([-30, -2, 0, 2, 30, 0, 1, 30]):
        pose_demo = np.eye(4)
        pose_demo[:3, 3] = [x, 0, 0]
        pose_map = np.linalg.inv(t0) @ np.block([[tilt, np.zeros((3, 1))], [np.zeros((1, 3)), np.ones((1, 1))]]) @ pose_demo
        rows.append([1700000000+k, *pose_map[:3].ravel()])
    np.savetxt(raw/"poses.txt", rows, fmt="%.10f")
    write_yaml(directory/"config.yaml", cfg)
    out = directory/"out"
    args = argparse.Namespace(config=directory/"config.yaml", input=raw/"crop.ply", poses=raw/"poses.txt",
                              out=str(out), cloudcompare=None, quick=False,
                              stages=["transform", "clean", "ground", "classify", "heightfield", "mujoco", "isaac", "map2d", "handoff", "check"])
    execute(args)
    return {"cfg": cfg, "out": out, "points_map": points_map, "origin": origin, "args": args}


def test_transform_origin_and_tilt(synthetic):
    s = synthetic
    resolved = read_yaml(s["out"]/"frame_resolved.yaml")
    final = np.array(resolved["T_demo_from_map"])
    assert np.linalg.norm(apply_transform(s["origin"][None], final)) < .005
    assert resolved["tilt_deg"] == pytest.approx(2, abs=.2)
    assert abs(resolved["origin_ground_z_m"]) < .01


def test_ground_and_box_classes(synthetic):
    report = read_yaml(synthetic["out"]/"classes.yaml")
    assert report["counts"]["ground"] > 20000
    assert report["counts"]["cars"] > 500
    assert report["counts"]["other"] > 1000
    assert set(report["counts"]) == {"ground", "cars", "other"}
    assert not (synthetic["out"]/"buildings.ply").exists()
    assert not (synthetic["out"]/"buildings.npy").exists()
    assert sum(report["counts"].values()) == len(np.load(synthetic["out"]/"clean.npy"))


def test_heightfield_slope_curb_and_excluded_car(synthetic):
    out = synthetic["out"]
    hf = np.load(out/"heightfield.npy")
    meta = read_yaml(out/"heightfield.yaml")
    xy = np.array([[0, 0], [8, 6], [0, -5.8], [-5, 3], [6, -3.5]])
    actual = sample_height(hf, meta, xy)
    assert actual[:4] == pytest.approx([0, .5, .15, 0], abs=.02)
    assert actual[4] == pytest.approx(.3, abs=.02)  # Tall context remains other, above ground terrain.
    assert hf.dtype == np.float32
    assert np.load(out/"heightfield_measured.npy").dtype == bool


def test_mujoco_asymmetric_quadrants_and_flat(tmp_path):
    hf = np.zeros((25, 41), dtype=np.float32)
    hf[16:22, 27:36] = .7  # +x,+y on a non-square grid catches flips and transposes.
    meta = {"x0": -2., "y0": -1.2, "resolution": .1}
    params = {"walk_box": [-2, 2, -1.2, 1.2], "walk_box_status": "test", "base_m": .5}
    result = export_mujoco(tmp_path, hf, meta, params)
    assert result["bounds_xy"] == pytest.approx([-2, 2, -1.2, 1.2], abs=1e-10)
    assert result["shape"] == list(hf.shape)
    assert mujoco_height(tmp_path/"terrain.xml", [1.0, .6]) == pytest.approx(.7, abs=1e-5)
    assert mujoco_height(tmp_path/"terrain.xml", [-1.0, -.6]) == pytest.approx(0, abs=1e-5)
    export_mujoco(tmp_path, np.full(hf.shape, -.4, dtype=np.float32), meta, params)
    assert mujoco_height(tmp_path/"terrain.xml", [0, 0]) == pytest.approx(-.4, abs=1e-5)


def test_mesh_error_reduction_and_usd(synthetic):
    from pxr import Usd, UsdGeom, UsdPhysics

    out = synthetic["out"]
    report = read_yaml(out/"mesh_report.yaml")
    assert report["max_error_m"] <= .02
    assert report["triangles"] < report["raw_triangles"]*.5
    stage = Usd.Stage.Open(str(out/"terrain.usd"))
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    assert len(meshes) == 1
    assert meshes[0].HasAPI(UsdPhysics.CollisionAPI)
    assert meshes[0].HasAPI(UsdPhysics.MeshCollisionAPI)
    assert not meshes[0].HasAPI(UsdPhysics.RigidBodyAPI)
    assert UsdPhysics.MeshCollisionAPI(meshes[0]).GetApproximationAttr().Get() == "none"
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1
    assert UsdGeom.GetStageUpAxis(stage) == "Z"


def test_nav2_origin_curb_threshold_unknown_and_row_order(tmp_path):
    # Read the actual default so this detects configuration regressions.
    # A 15 cm non-ground curb must be occupied above an elevated surface.
    hf = np.full((21, 31), 2.0, dtype=np.float32)
    measured = np.ones(hf.shape, dtype=bool)
    measured[0:3, 0:3] = False
    meta = {"x0": -1., "y0": -1., "resolution": .1}
    points = np.array([[1., .5, 2.15], [-.5, -.5, 2.5], [0, 0, 4.], [1.5, -.5, 2.05]])
    params = copy.deepcopy(read_yaml(ROOT/"sim_scenes/pair360_parking/frame.yaml")["processing"]["map2d"])
    export_map2d(tmp_path, hf, measured, meta, points, params)
    image = occupancy(hf, measured, meta, points, params)
    assert image[5, 20] == 0  # +y near the top of the PGM.
    assert image[15, 5] == 0
    assert image[20, 0] == 205
    assert image[10, 15] == 254  # >1 m relative height excluded.
    assert image[15, 25] == 254  # 5 cm remains below the default cutoff.
    nav = read_yaml(tmp_path/"map2d.yaml")
    assert nav["origin"] == [meta["x0"], meta["y0"], 0]
    assert nav["resolution"] == meta["resolution"]
    assert (tmp_path/"map2d.pgm").read_bytes().endswith(image.tobytes())
    stricter = dict(params, min_height_m=.2)
    assert occupancy(hf, measured, meta, points, stricter)[5, 20] == 254


def test_handoff_times_and_pose_orientation(synthetic):
    out = synthetic["out"]
    report = read_yaml(out/"traversals.yaml")
    assert [i["pose_count"] for i in report["intervals"]] == [3, 2]
    assert report["intervals"][0]["start_unix_s"] == 1700000001
    tum = np.loadtxt(out/"gt_poses_demo.tum")
    assert tum.shape == (5, 8)
    assert tum[:, 1] == pytest.approx([-2, 0, 2, 0, 1], abs=.005)
    assert Rotation.from_quat(tum[:, 4:]).magnitude() == pytest.approx(np.zeros(5), abs=.005)


def test_individual_stage_and_stale_config_guard(synthetic):
    args = copy.copy(synthetic["args"])
    args.stages = ["map2d"]
    args.input = args.poses = None
    execute(args)
    manifest = read_yaml(synthetic["out"]/"manifest.yaml")
    assert "map2d" in manifest["stages"]
    assert "check" not in manifest["stages"]
    args.quick = True
    with pytest.raises(ValueError, match="differs"):
        execute(args)


def test_shifted_crop_stops_before_output(synthetic):
    with pytest.raises(ValueError, match="global shift"):
        level_cloud(synthetic["points_map"] + [10000, 10000, 0], synthetic["cfg"])


def test_singleton_cluster_remains_finite_other():
    cfg = read_yaml(ROOT/"sim_scenes/pair360_parking/frame.yaml")
    params = copy.deepcopy(cfg["processing"]["classes"])
    params["object_min_points"] = 1
    surface = np.zeros((3, 3))
    groups, records = classify(np.array([[.5, .5, .8]]), surface,
                               {"x0": 0., "y0": 0., "resolution": 1.}, params)
    assert len(groups["other"]) == 1
    assert np.isfinite([records[0]["length_m"], records[0]["width_m"], records[0]["height_m"]]).all()


def test_tiled_mesh_has_conforming_seams_and_bounded_qem(monkeypatch):
    import exports
    from mesh_tiling import boundary_edges

    cfg = read_yaml(ROOT/"sim_scenes/pair360_parking/frame.yaml")
    params = dict(cfg["processing"]["isaac"], tile_cells=32, random_samples=256, max_attempts=3)
    meta = {"x0": -1.3, "y0": -.7, "resolution": .05}
    ii, jj = np.indices((65, 81))
    hf = (.03*np.sin(jj*.2)*np.cos(ii*.1) + jj*.005 + .15*((ii >= 32) & (jj >= 20))).astype(np.float32)
    original_grid_mesh = exports.grid_mesh
    seen = []

    def bounded_grid_mesh(tile, tile_meta):
        assert max(tile.shape) <= 33  # No full-grid mesh may reach QEM.
        seen.append(tile.shape)
        return original_grid_mesh(tile, tile_meta)

    monkeypatch.setattr(exports, "grid_mesh", bounded_grid_mesh)
    mesh, report = exports.decimate(hf, meta, params, 360)
    assert len(seen) == report["tile_count"] == 6
    assert report["max_tile_raw_triangles"] <= 2*32*32
    assert report["triangles"] < report["raw_triangles"]
    assert report["max_error_m"] <= .02
    vertices = np.asarray(mesh.vertices)
    boundary = boundary_edges(np.asarray(mesh.triangles))
    for edge in boundary:
        xy = vertices[edge, :2]
        # Every unmatched edge must lie on the outer rectangle, never a seam.
        assert (np.allclose(xy[:, 0], meta["x0"]) or np.allclose(xy[:, 0], meta["x0"]+80*.05)
                or np.allclose(xy[:, 1], meta["y0"]) or np.allclose(xy[:, 1], meta["y0"]+64*.05))
    for column in (32, 64):
        for row in range(hf.shape[0]):
            expected = [meta["x0"]+column*.05, meta["y0"]+row*.05, hf[row, column]]
            assert np.any(np.all(np.isclose(vertices, expected, atol=1e-9, rtol=0), axis=1))
    # Independently check the welded mesh, including rays across tile seams.
    assert exports.mesh_error(mesh, hf, meta, params, 361)["max_error_m"] <= .02


def test_reuse_heightfield_preserves_provenance_and_checks_inputs(synthetic, tmp_path):
    from pair360_demo import sha256

    source = tmp_path/"legacy"
    shutil.copytree(synthetic["out"], source)
    manifest = read_yaml(source/"manifest.yaml")
    manifest["code_sha256"] = "legacy-code-version"
    write_yaml(source/"manifest.yaml", manifest)
    cfg = copy.deepcopy(synthetic["cfg"])
    cfg["processing"]["isaac"]["tile_cells"] = 32  # Export-only change is allowed.
    config_path = tmp_path/"revised.yaml"
    write_yaml(config_path, cfg)
    args = copy.copy(synthetic["args"])
    args.config = config_path
    args.input = args.poses = None
    args.reuse_heightfield_from = source
    args.out = str(tmp_path/"resumed")
    args.stages = ["mujoco", "map2d", "handoff"]
    execute(args)
    resumed = read_yaml(Path(args.out)/"manifest.yaml")
    assert resumed["reused_heightfield"]["source_code_sha256"] == "legacy-code-version"
    assert resumed["stages"]["heightfield"]["reused"]
    assert sha256(Path(args.out)/"heightfield.npy") == sha256(source/"heightfield.npy")
    assert (Path(args.out)/"heightfield.npy").stat().st_ino != (source/"heightfield.npy").stat().st_ino
    assert (Path(args.out)/"map2d.pgm").exists()
    original_above = cfg["processing"]["ground"]["above_m"]
    cfg["processing"]["ground"]["above_m"] = original_above+.01
    write_yaml(config_path, cfg)
    args.out = str(tmp_path/"incompatible")
    with pytest.raises(ValueError, match="differs before heightfield"):
        execute(args)
    cfg["processing"]["ground"]["above_m"] = original_above
    write_yaml(config_path, cfg)
    (source/"heightfield.npy").write_bytes(b"tampered")
    args.out = str(tmp_path/"corrupt")
    with pytest.raises(ValueError, match="missing/modified heightfield.npy"):
        execute(args)
