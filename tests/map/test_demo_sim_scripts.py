# SPDX-License-Identifier: Apache-2.0
"""Synthetic CLI and collision checks; no real cloud, CloudCompare, or GUI required."""

import hashlib
import itertools
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
CONVERTER = ROOT / "tools/map/demo_sim_converter.sh"
DISASSEMBLER = ROOT / "tools/map/demo_sim_disassembler.sh"
DAY = "1030"


def run_script(script, *args, env=None, cwd=None):
    process_env = {
        **os.environ,
        "HN_MAP_PYTHON": sys.executable,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        **(env or {}),
    }
    command = [sys.executable, "-B"] if Path(script).suffix == ".py" else ["bash"]
    return subprocess.run(
        [*command, str(script), *map(str, args)],
        capture_output=True, text=True, timeout=120,
        cwd=cwd, env=process_env,
    )


def write_cloud(path, points):
    """Write tiny fixtures directly, independently of the converter's cloud reader."""
    rows = [" ".join(map(str, point)) for point in points]
    suffix = path.suffix.lower()
    if suffix == ".ply":
        text = (
            "ply\nformat ascii 1.0\n"
            f"element vertex {len(rows)}\n"
            "property double x\nproperty double y\nproperty double z\nend_header\n"
            + "\n".join(rows) + "\n"
        )
    elif suffix == ".pcd":
        text = (
            "# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\n"
            "TYPE F F F\nCOUNT 1 1 1\n"
            f"WIDTH {len(rows)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
            f"POINTS {len(rows)}\nDATA ascii\n" + "\n".join(rows) + "\n"
        )
    elif suffix == ".pts":
        text = f"{len(rows)}\n" + "\n".join(row + " 0 100 150 200" for row in rows) + "\n"
    elif suffix == ".xyzn":
        text = "\n".join(row + " 0 0 1" for row in rows) + "\n"
    elif suffix == ".xyzrgb":
        text = "\n".join(row + " 0.1 0.2 0.3" for row in rows) + "\n"
    else:
        text = "\n".join(rows) + "\n"
    path.write_text(text)
    return path


def write_binary_ply(path, points):
    """Encode NaN/Inf as IEEE-754 doubles, avoiding ASCII parser ambiguity."""
    array = np.asarray(points, dtype="<f8").reshape(-1, 3)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(array)}\n"
        "property double x\nproperty double y\nproperty double z\nend_header\n"
    )
    path.write_bytes(header.encode("ascii") + array.tobytes())
    return path


def convert(source, output_root, *options, env=None):
    result = run_script(
        CONVERTER, source, "--date", DAY, "--output-root", output_root,
        *options, env=env, cwd=source.parent,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output_root / f"{DAY}_demo_whole"


def read_geometry(directory):
    import mujoco
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    model = mujoco.MjModel.from_xml_path(str(directory / "terrain.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert model.nq == 0
    assert model.ngeom > 0
    assert np.all(model.geom_type == mujoco.mjtGeom.mjGEOM_BOX)
    assert np.all(model.geom_contype != 0)
    assert np.all(model.geom_conaffinity != 0)

    stage = Usd.Stage.Open(str(directory / "terrain.usd"))
    assert stage is not None
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1
    assert UsdGeom.GetStageUpAxis(stage) == "Z"
    meshes = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
    assert len(meshes) == 1
    prim = meshes[0]
    assert str(prim.GetPath()) == "/Terrain"
    assert prim.HasAPI(UsdPhysics.CollisionAPI)
    assert UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
    assert prim.HasAPI(UsdPhysics.MeshCollisionAPI)
    assert UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get() == "none"
    if prim.HasAPI(UsdPhysics.RigidBodyAPI):
        assert not UsdPhysics.RigidBodyAPI(prim).GetRigidBodyEnabledAttr().Get()
    mesh = UsdGeom.Mesh(prim)
    transform = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
    vertices = np.array([
        tuple(transform.Transform(Gf.Vec3d(*map(float, point))))
        for point in mesh.GetPointsAttr().Get()
    ])
    indices = list(mesh.GetFaceVertexIndicesAttr().Get())
    triangles = []
    offset = 0
    for count in mesh.GetFaceVertexCountsAttr().Get():
        face = indices[offset:offset + count]
        triangles.extend(vertices[[face[0], face[i], face[i + 1]]]
                         for i in range(1, count - 1))
        offset += count
    assert offset == len(indices)
    return model, data, vertices, np.array(triangles)


def mesh_contains(triangles, point):
    """Odd/even ray crossings, including paired internal faces of adjacent boxes."""
    direction = np.array([1.0, np.sqrt(2) / 7, np.sqrt(3) / 11])
    edge1 = triangles[:, 1] - triangles[:, 0]
    edge2 = triangles[:, 2] - triangles[:, 0]
    h = np.cross(direction, edge2)
    determinant = np.einsum("ij,ij->i", edge1, h)
    usable = np.abs(determinant) > 1e-10
    inverse = np.zeros_like(determinant)
    inverse[usable] = 1 / determinant[usable]
    relative = point - triangles[:, 0]
    u = inverse * np.einsum("ij,ij->i", relative, h)
    q = np.cross(relative, edge1)
    v = inverse * (q @ direction)
    distance = inverse * np.einsum("ij,ij->i", edge2, q)
    hits = usable & (u > 0) & (v > 0) & (u + v < 1) & (distance > 1e-10)
    return bool(np.count_nonzero(hits) % 2)


def assert_occupied_union(directory, cells, voxel_size=1.0):
    """Compare independent simulator occupancy to occupied and empty voxel centers."""
    model, data, vertices, triangles = read_geometry(directory)
    expected = set(cells)
    bounds = np.array(list(expected))
    lower = bounds.min(axis=0) * voxel_size
    upper = (bounds.max(axis=0) + 1) * voxel_size
    np.testing.assert_allclose(vertices.min(axis=0), lower, atol=1e-6)
    np.testing.assert_allclose(vertices.max(axis=0), upper, atol=1e-6)
    rotations = data.geom_xmat.reshape(-1, 3, 3)
    # Axis-aligned, voxel-aligned box limits make center occupancy an exact union
    # check, rather than a sparse sample that could miss partial-cell filling.
    np.testing.assert_allclose(np.abs(rotations), np.round(np.abs(rotations)), atol=1e-8)
    world_half_sizes = np.einsum("nij,nj->ni", np.abs(rotations), model.geom_size)
    for edges in [data.geom_xpos - world_half_sizes, data.geom_xpos + world_half_sizes]:
        np.testing.assert_allclose(edges / voxel_size, np.round(edges / voxel_size), atol=1e-6)
    np.testing.assert_allclose(vertices / voxel_size, np.round(vertices / voxel_size), atol=1e-5)
    np.testing.assert_allclose(
        np.sum(8 * np.prod(model.geom_size, axis=1)), len(cells) * voxel_size**3,
    )
    for cell in itertools.product(*[
        range(int(lo) - 1, int(hi) + 2)
        for lo, hi in zip(bounds.min(axis=0), bounds.max(axis=0))
    ]):
        # Noncentral samples avoid shared face diagonals during triangle ray tests.
        point = (np.array(cell) + [.37, .43, .61]) * voxel_size
        local = np.einsum(
            "ni,nij->nj", point - data.geom_xpos, rotations,
        )
        in_mujoco = bool(np.any(np.all(np.abs(local) < model.geom_size, axis=1)))
        assert in_mujoco == (cell in expected), ("MuJoCo", cell)
        assert mesh_contains(triangles, point) == (cell in expected), ("USD", cell)
    return model, data


@pytest.fixture(scope="module")
def whole_scene(tmp_path_factory):
    work = tmp_path_factory.mktemp("whole scene")
    cells = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 3), (-1, -1, -2)]
    source = write_cloud(work / "source cloud.ply", np.array(cells) + [.1, .2, .3])
    original = source.read_bytes()
    directory = convert(source, work / "output scenes", "--voxel-size", "1")
    assert source.read_bytes() == original
    return source, directory, cells, original


def test_exact_voxel_union_preserves_high_geometry_and_vertical_gap(whole_scene):
    import mujoco

    _, directory, cells, _ = whole_scene
    model, data = assert_occupied_union(directory, cells)
    assert model.ngeom < len(cells), "Adjacent occupied voxels should be merged"
    for z, expected in [(.4, 3.0), (1.4, -1.0), (2.4, -1.0), (3.4, 3.0)]:
        distance = mujoco.mj_ray(
            model, data, np.array([-3., .4, z]), np.array([1., 0., 0.]),
            None, 1, -1, np.array([-1], dtype=np.int32),
        )
        assert distance == pytest.approx(expected), z


def test_metadata_records_complete_geometry_and_source(whole_scene):
    source, directory, cells, original = whole_scene
    metadata = json.loads((directory / "scene.json").read_text())
    assert metadata["status"] == "complete"
    assert Path(metadata["source"]["path"]) == source.resolve()
    assert metadata["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    implementation = CONVERTER.with_suffix(".py")
    assert metadata["generator"]["script"] == str(implementation.relative_to(ROOT))
    assert metadata["generator"]["sha256"] == hashlib.sha256(implementation.read_bytes()).hexdigest()
    assert metadata["counts"]["finite_points"] == len(cells)
    assert metadata["counts"]["occupied_voxels"] == len(cells)
    assert metadata["counts"]["boxes"] < len(cells)
    assert metadata["transform"]["origin_input"] == [0, 0, 0]
    assert metadata["transform"]["scale"] == 1
    assert metadata["voxel_size_m"] == 1
    assert metadata["units"] == "m" and metadata["up_axis"] == "Z"
    assert metadata["files"]["isaac"] == "terrain.usd"
    assert metadata["files"]["mujoco"] == "terrain.xml"
    assert metadata["bounds"]["voxel_geometry"]["min"] == [-1, -1, -2]
    assert metadata["bounds"]["voxel_geometry"]["max"] == [2, 2, 4]


@pytest.mark.parametrize("suffix", ["ply", "pcd", "xyz", "xyzn", "xyzrgb", "pts"])
def test_supported_formats_and_default_transform(tmp_path, suffix):
    source = write_cloud(tmp_path / f"cloud.{suffix}", [[.05, .05, .05], [.55, .05, 1.05]])
    directory = convert(source, tmp_path / "results")
    metadata = json.loads((directory / "scene.json").read_text())
    assert metadata["voxel_size_m"] == .5
    assert metadata["counts"]["finite_points"] == 2
    assert_occupied_union(directory, [(0, 0, 0), (1, 0, 2)], .5)


def test_origin_and_scale_are_shared_by_both_simulators(tmp_path):
    source = write_cloud(tmp_path / "cloud.ply", [
        [10.25, 20.25, 30.25], [11.25, 20.25, 30.25], [10.25, 20.25, 33.25],
    ])
    directory = convert(
        source, tmp_path / "results", "--voxel-size", "1",
        "--origin", "10", "20", "30", "--scale", "2",
    )
    assert_occupied_union(directory, [(0, 0, 0), (2, 0, 0), (0, 0, 6)])
    metadata = json.loads((directory / "scene.json").read_text())
    assert metadata["transform"]["origin_input"] == [10, 20, 30]
    assert metadata["transform"]["scale"] == 2


def test_nonfinite_points_removed_without_filtering_finite_high_points(tmp_path):
    source = write_binary_ply(tmp_path / "cloud.ply", [
        [.1, .1, .1], [.2, .2, .2], [.1, .1, 9.1],
        [float("nan"), 0, 0], [0, float("inf"), 0],
    ])
    directory = convert(source, tmp_path / "results", "--voxel-size", "1")
    assert_occupied_union(directory, [(0, 0, 0), (0, 0, 9)])
    metadata = json.loads((directory / "scene.json").read_text())
    assert metadata["counts"]["input_points"] == 5
    assert metadata["counts"]["finite_points"] == 3
    assert metadata["counts"]["nonfinite_removed"] == 2


@pytest.mark.parametrize("options", [
    ("--voxel-size", "0"), ("--voxel-size", "nan"),
    ("--scale", "-1"), ("--origin", "0", "inf", "0"),
    ("--max-geoms", "0"), ("--unknown",), ("--voxel-size",),
])
def test_converter_rejects_invalid_options_without_final_output(tmp_path, options):
    source = write_cloud(tmp_path / "cloud.ply", [[0, 0, 0]])
    output = tmp_path / "results"
    result = run_script(CONVERTER, source, "--date", DAY, "--output-root", output, *options)
    assert result.returncode != 0
    assert not (output / f"{DAY}_demo_whole").exists()


@pytest.mark.parametrize("script,suffix", [(CONVERTER, "whole"), (DISASSEMBLER, "disassembled")])
@pytest.mark.parametrize("day", ["230", "0230", "0431", "1301", "abcd"])
def test_invalid_dates_do_not_publish_output(tmp_path, script, suffix, day):
    source = write_cloud(tmp_path / "cloud.ply", [[0, 0, 0]])
    output = tmp_path / "results"
    result = run_script(script, source, "--date", day, "--output-root", output)
    assert result.returncode != 0
    assert not (output / f"{day}_demo_{suffix}").exists()


@pytest.mark.parametrize("script,suffix", [(CONVERTER, "whole"), (DISASSEMBLER, "disassembled")])
def test_missing_input_is_rejected(tmp_path, script, suffix):
    output = tmp_path / "results"
    result = run_script(script, tmp_path / "missing.ply", "--date", DAY, "--output-root", output)
    assert result.returncode != 0
    assert not (output / f"{DAY}_demo_{suffix}").exists()


@pytest.mark.parametrize("script,suffix", [(CONVERTER, "whole"), (DISASSEMBLER, "disassembled")])
@pytest.mark.parametrize("populated", [False, True])
def test_existing_output_is_never_overwritten(tmp_path, script, suffix, populated):
    source = write_cloud(tmp_path / "cloud.ply", [[0, 0, 0]])
    output = tmp_path / "results"
    existing = output / f"{DAY}_demo_{suffix}"
    existing.mkdir(parents=True)
    if populated:
        (existing / "keep.txt").write_bytes(b"previous result must survive\n")
    before = {p.name: p.read_bytes() for p in existing.iterdir()}
    result = run_script(script, source, "--date", DAY, "--output-root", output)
    assert result.returncode != 0
    assert existing.is_dir()
    assert {p.name: p.read_bytes() for p in existing.iterdir()} == before


@pytest.mark.parametrize("kind", ["empty", "nonfinite", "geom_limit", "interpreter"])
def test_failed_conversion_does_not_leave_complete_scene(tmp_path, kind):
    points = {"empty": [], "nonfinite": [[float("nan"), 0, 0]]}.get(
        kind, [[0, 0, 0], [10, 0, 0]],
    )
    writer = write_binary_ply if kind == "nonfinite" else write_cloud
    source = writer(tmp_path / "cloud.ply", points)
    output = tmp_path / "results"
    options = ["--max-geoms", "1"] if kind == "geom_limit" else []
    env = {"HN_MAP_PYTHON": str(tmp_path / "missing-python")} if kind == "interpreter" else {}
    result = run_script(
        CONVERTER, source, "--date", DAY, "--output-root", output, *options, env=env,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert not (output / f"{DAY}_demo_whole").exists()


def fake_cloudcompare(tmp_path):
    """A controlled executable checks copy-only handoff, not native BIN parsing."""
    executable = tmp_path / "fake CloudCompare"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "source = next(pathlib.Path(a) for a in args if a.lower().endswith('.bin'))\n"
        "target = pathlib.Path(args[args.index('-SAVE_CLOUDS') + 2])\n"
        "assert args[args.index('-SAVE_CLOUDS') + 1] == 'FILE'\n"
        "pathlib.Path(os.environ['CC_LOG']).write_text(json.dumps({\n"
        "    'argv0': sys.argv[0], 'args': args, 'source': str(source), 'target': str(target),\n"
        "    'source_hex': source.read_bytes().hex()}))\n"
        "mode = os.environ['CC_MODE']\n"
        "if mode == 'error': sys.exit(37)\n"
        "if mode == 'empty': sys.exit(0)\n"
        "target.write_bytes(pathlib.Path(os.environ['CC_FIXTURE']).read_bytes())\n"
        "if mode == 'multiple':\n"
        "    target.with_name(target.stem + '_extra.ply').write_bytes(target.read_bytes())\n"
    )
    executable.chmod(0o755)
    return executable


@pytest.mark.parametrize("mode", ["success", "relative", "symlink", "error", "empty", "multiple"])
def test_bin_copy_only_handoff_and_cloudcompare_failures(tmp_path, mode):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "source map.bin"
    original = b"synthetic BIN sentinel; fake CloudCompare handles conversion\n"
    source.write_bytes(original)
    fixture = write_cloud(tmp_path / "export.ply", [[.1, .1, .1], [.1, .1, 3.1]])
    log = tmp_path / "cc.json"
    output = tmp_path / "results"
    executable = fake_cloudcompare(tmp_path)
    if mode == "symlink":
        alias = tmp_path / "CloudCompare-alias"
        alias.symlink_to(executable.name)
        executable = alias
    requested = "./" + executable.name if mode == "relative" else str(executable)
    result = run_script(
        CONVERTER, source, "--voxel-size", "1", "--date", DAY,
        "--output-root", output, "--cloudcompare", requested, cwd=tmp_path,
        env={"CC_LOG": str(log), "CC_FIXTURE": str(fixture), "CC_MODE": mode},
    )
    assert source.read_bytes() == original
    assert sorted(p.name for p in raw.iterdir()) == [source.name]
    handoff = json.loads(log.read_text())
    assert Path(handoff["source"]).resolve() != source.resolve()
    assert bytes.fromhex(handoff["source_hex"]) == original
    assert Path(handoff["target"]).parent.resolve() != raw.resolve()
    directory = output / f"{DAY}_demo_whole"
    if mode in {"success", "relative", "symlink"}:
        assert result.returncode == 0, result.stdout + result.stderr
        assert Path(handoff["argv0"]).name == executable.name
        assert_occupied_union(directory, [(0, 0, 0), (0, 0, 3)])
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert not directory.exists()


def test_disassembler_creates_only_empty_folder_with_stdlib_python(tmp_path):
    source = tmp_path / "cloud.bin"
    original = b"opaque input is valid for the unimplemented disassembler\n"
    source.write_bytes(original)
    stdlib_python = tmp_path / "stdlib-python"
    stdlib_python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -S "$@"\n')
    stdlib_python.chmod(0o755)
    output = tmp_path / "results"
    result = run_script(
        DISASSEMBLER, source, "--date", "0229", "--output-root", output,
        env={"HN_MAP_PYTHON": str(stdlib_python)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    directory = output / "0229_demo_disassembled"
    assert directory.is_dir() and list(directory.iterdir()) == []
    assert "not implemented" in (result.stdout + result.stderr).lower()
    assert source.read_bytes() == original


@pytest.mark.parametrize("script", [CONVERTER.with_suffix(".py"), DISASSEMBLER.with_suffix(".py")])
def test_python_help_needs_no_third_party_packages(tmp_path, script):
    result = subprocess.run(
        [sys.executable, "-B", "-S", str(script), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--output-root" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_python_converter_runs_directly_from_another_directory(tmp_path):
    source = write_cloud(tmp_path / "cloud.ply", [[.1, .1, .1], [.1, .1, 3.1]])
    output_root = tmp_path / "results"
    result = run_script(
        CONVERTER.with_suffix(".py"), source, "--voxel-size", "1", "--date", DAY,
        "--output-root", output_root, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert_occupied_union(output_root / f"{DAY}_demo_whole", [(0, 0, 0), (0, 0, 3)])


def test_python_disassembler_runs_directly_from_another_directory(tmp_path):
    source = tmp_path / "cloud.bin"
    source.write_bytes(b"synthetic")
    output_root = tmp_path / "results"
    result = run_script(
        DISASSEMBLER.with_suffix(".py"), source, "--date", DAY,
        "--output-root", output_root, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert list((output_root / f"{DAY}_demo_disassembled").iterdir()) == []


def test_default_date_is_asia_seoul_even_with_other_process_timezone(tmp_path):
    source = tmp_path / "cloud.bin"
    source.write_bytes(b"synthetic")
    output = tmp_path / "results"
    before = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m%d")
    result = run_script(
        DISASSEMBLER, source, "--output-root", output, env={"TZ": "Pacific/Honolulu"},
    )
    after = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m%d")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(output.iterdir())) == 1
    assert next(output.iterdir()).name in {f"{day}_demo_disassembled" for day in [before, after]}
