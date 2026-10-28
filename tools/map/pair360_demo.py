#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible PAIR360 crop → terrain/map/SLAM handoff pipeline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# Keep Open3D's short CPU jobs from oversubscribing large workstations.
os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np

from pointcloud import (build_heightfield, classify, clean_cloud, effective_config, level_cloud,
                  load_cloud, read_yaml, sample_height, save_cloud, split_ground, write_yaml)
from exports import export_isaac, export_map2d, export_mujoco, mujoco_height
from handoff import export_handoff, read_poses

STAGES = ("transform", "clean", "ground", "classify", "heightfield", "mujoco", "isaac", "map2d", "handoff", "check")
DEPS = {"transform": [], "clean": ["transform"], "ground": ["clean"], "classify": ["ground"],
        "heightfield": ["classify"], "mujoco": ["heightfield"], "isaac": ["heightfield"],
        "map2d": ["heightfield"], "handoff": ["transform"],
        "check": ["mujoco", "isaac", "map2d", "handoff"]}
OUTPUTS = {
    "transform": ["transformed.npy", "frame_resolved.yaml", "poses_map.npy", "input_provenance.yaml"],
    "clean": ["clean.npy"], "ground": ["ground.npy", "non_ground.npy", "ground_surface.npy", "ground_surface.yaml", "ground.ply",
                                      "ground_patches.npz", "ground_report.yaml"],
    "classify": ["cars.npy", "other.npy", "cars.ply", "other.ply", "classes.yaml"],
    "heightfield": ["heightfield.npy", "heightfield_measured.npy", "heightfield.yaml"],
    "mujoco": ["terrain.hfield", "terrain.xml", "mujoco.yaml"],
    "isaac": ["terrain.obj", "terrain.usd", "mesh_report.yaml"], "map2d": ["map2d.pgm", "map2d.yaml", "map2d_report.yaml"],
    "handoff": ["traversals.yaml", "gt_poses_demo.tum", "ATTRIBUTION.txt", "HANDOFF.md"],
    "check": ["smoke_report.yaml", "slam_handoff.zip"],
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_crop(source, out, cloudcompare=None):
    source = Path(source).resolve(strict=True)
    if source.suffix.lower() not in (".bin", ".ply", ".pcd"):
        raise ValueError("Input must be a crop PLY/PCD or CloudCompare native BIN")
    if source.suffix.lower() == ".bin":
        for suffix in (".ply", ".pcd"):
            if source.with_suffix(suffix).is_file():
                source = source.with_suffix(suffix)
                break
    provenance = {"input_name": source.name, "input_sha256": sha256(source), "conversion": "not_needed"}
    if source.suffix.lower() != ".bin":
        return source, provenance
    conversion_path = out/"conversion.yaml"
    if conversion_path.exists():
        old = read_yaml(conversion_path)
        converted = out/old["converted_name"]
        if old["input_sha256"] == provenance["input_sha256"] and converted.is_file() and sha256(converted) == old["converted_sha256"]:
            return converted, old
        raise ValueError("Existing BIN conversion differs; use a fresh output directory")
    executable = cloudcompare or shutil.which("CloudCompare") or shutil.which("cloudcompare.CloudCompare")
    if not executable:
        raise ValueError("CloudCompare unavailable. Re-save the crop in the GUI as binary PLY and pass --input crop.ply")
    copied = out/"crop_input.bin"
    shutil.copyfile(source, copied)
    before = set(out.glob("*.ply"))
    command = [executable, "-SILENT", "-AUTO_SAVE", "OFF", "-O", str(copied),
               "-C_EXPORT_FMT", "PLY", "-PLY_EXPORT_FMT", "BINARY_LE", "-NO_TIMESTAMP", "-SAVE_CLOUDS"]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    try:
        with (out/"cloudcompare.log").open("w") as log:
            result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        candidates = sorted(set(out.glob("*.ply"))-before)
        if result.returncode or len(candidates) != 1 or candidates[0].stat().st_size == 0:
            raise ValueError(f"exit={result.returncode}, exported clouds={len(candidates)}")
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        raise ValueError("CloudCompare conversion failed; see cloudcompare.log. Stop and re-save the crop in the GUI as binary PLY") from exc
    converted = candidates[0]
    provenance.update({"conversion": "CloudCompare_offscreen_copy_only", "converted_name": converted.name,
                       "converted_sha256": sha256(converted), "command": [Path(command[0]).name, *[Path(x).name if x == str(copied) else x for x in command[1:]]]})
    write_yaml(conversion_path, provenance)
    return converted, provenance


def check_outputs(out, cfg):
    from pxr import Usd, UsdGeom, UsdPhysics

    resolved = read_yaml(out/"frame_resolved.yaml")
    meta = read_yaml(out/"heightfield.yaml")
    mesh = read_yaml(out/"mesh_report.yaml")
    hf = np.load(out/"heightfield.npy", mmap_mode="r")
    measured = np.load(out/"heightfield_measured.npy", mmap_mode="r")
    if not resolved["origin_inside_crop"] or abs(resolved["origin_ground_z_m"]) > cfg["processing"]["leveling"]["origin_z_tolerance_m"]:
        raise ValueError("Origin/crop ground sanity check failed")
    if mesh["max_error_m"] > cfg["processing"]["isaac"]["max_error_m"]:
        raise ValueError("Mesh metric error exceeds limit")
    hit = mujoco_height(out/"terrain.xml", [0., 0.])
    if abs(hit) > cfg["processing"]["leveling"]["origin_z_tolerance_m"]:
        raise ValueError(f"MuJoCo origin ray hit z={hit:.4f} m; expected approximately zero")
    if abs(hit-float(sample_height(hf, meta, np.array([[0., 0.]]))[0])) > 0.02:
        raise ValueError("MuJoCo/heightfield origin elevations disagree")
    stage = Usd.Stage.Open(str(out/"terrain.usd"))
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    if len(meshes) != 1 or not meshes[0].HasAPI(UsdPhysics.CollisionAPI) or not meshes[0].HasAPI(UsdPhysics.MeshCollisionAPI):
        raise ValueError("USD must have exactly one collision Mesh prim")
    if UsdPhysics.MeshCollisionAPI(meshes[0]).GetApproximationAttr().Get() != "none":
        raise ValueError("USD mesh collision approximation must be none")
    if UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != "Z":
        raise ValueError("USD units/up-axis mismatch")
    nav = read_yaml(out/"map2d.yaml")
    if nav["resolution"] != meta["resolution"] or nav["origin"] != [meta["x0"], meta["y0"], 0.0]:
        raise ValueError("Nav2 origin/resolution mismatch")
    i = int(np.floor(-meta["y0"]/meta["resolution"]))
    j = int(np.floor(-meta["x0"]/meta["resolution"]))
    if not (0 <= i < hf.shape[0] and 0 <= j < hf.shape[1] and measured[i, j]):
        raise ValueError("No measured ground at origin heightfield cell; interpolation could conceal an offset")
    traversal = read_yaml(out/"traversals.yaml")
    if not traversal["intervals"]:
        raise ValueError("No traversal intervals found; check T1S0 pose file/crop frame")
    report = {"status": "pass", "origin_inside_crop": True,
              "origin_ground_z_m": resolved["origin_ground_z_m"], "leveling_tilt_deg": resolved["tilt_deg"],
              "class_counts": read_yaml(out/"classes.yaml")["counts"],
              "heightfield": meta, "mujoco_origin_hit_z_m": hit,
              "mesh": mesh, "traversals": traversal, "warnings": resolved["warnings"],
              "versions": {p: importlib.metadata.version(p) for p in ("numpy", "scipy", "open3d", "mujoco", "usd-core")}}
    write_yaml(out/"smoke_report.yaml", report)
    with zipfile.ZipFile(out/"slam_handoff.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("frame_resolved.yaml", "effective_config.yaml", "input_provenance.yaml", "manifest.yaml",
                     "heightfield.yaml", "map2d.yaml", "map2d.pgm", "traversals.yaml", "gt_poses_demo.tum",
                     "ATTRIBUTION.txt", "HANDOFF.md", "smoke_report.yaml"):
            archive.write(out/name, arcname=name)
    return report


def run_stage(name, args, cfg, out):
    p = cfg["processing"]
    load = lambda filename: np.load(out/filename)
    save = lambda filename, values: np.save(out/filename, values)
    if name == "transform":
        if not args.input or not args.poses:
            raise ValueError("transform requires --input and --poses")
        source, provenance = prepare_crop(args.input, out, args.cloudcompare)
        points = load_cloud(source)
        if not len(points):
            raise ValueError("Empty crop")
        points, resolved = level_cloud(points, cfg)
        poses = read_poses(args.poses)
        provenance.update({"poses_name": Path(args.poses).name, "poses_sha256": sha256(args.poses), "finite_points": len(points)})
        save("transformed.npy", points)
        save("poses_map.npy", poses)
        resolved.update({"source": cfg["source"], "demo_frame": cfg["demo_frame"],
                         "gps_anchor": cfg["gps_anchor"], "robot_start": cfg["robot_start"], "quick": args.quick})
        write_yaml(out/"frame_resolved.yaml", resolved)
        write_yaml(out/"input_provenance.yaml", provenance)
        for warning in resolved["warnings"]:
            print(f"WARNING: {warning}: {resolved['tilt_deg']:.3f} deg", flush=True)
    elif name == "clean":
        save("clean.npy", clean_cloud(load("transformed.npy"), p["clean"]))
    elif name == "ground":
        points = load("clean.npy")
        diagnostics = {}
        mask, surface, meta = split_ground(points, p["ground"], diagnostics)
        save("ground.npy", points[mask])
        save("non_ground.npy", points[~mask])
        save("ground_surface.npy", surface)
        save_cloud(out/"ground.ply", points[mask])
        write_yaml(out/"ground_surface.yaml", meta)
        np.savez_compressed(out/"ground_patches.npz", **diagnostics["patches"])
        write_yaml(out/"ground_report.yaml", diagnostics["report"])
    elif name == "classify":
        groups, clusters = classify(load("non_ground.npy"), load("ground_surface.npy"), read_yaml(out/"ground_surface.yaml"), p["classes"])
        for key, points in groups.items():
            save(f"{key}.npy", points)
            save_cloud(out/f"{key}.ply", points)
        counts = {"ground": len(load("ground.npy")), **{k: len(v) for k, v in groups.items()}}
        write_yaml(out/"classes.yaml", {"method": "normal_surface_proposals_and_geometry", "counts": counts, "clusters": clusters})
    elif name == "heightfield":
        hf, measured, meta = build_heightfield(load("ground.npy"), load("clean.npy"), p["heightfield"])
        save("heightfield.npy", hf)
        save("heightfield_measured.npy", measured)
        write_yaml(out/"heightfield.yaml", meta)
    elif name in ("mujoco", "isaac", "map2d"):
        hf, meta = np.load(out/"heightfield.npy", mmap_mode="r"), read_yaml(out/"heightfield.yaml")
        if name == "mujoco":
            export_mujoco(out, hf, meta, p["mujoco"])
        elif name == "isaac":
            export_isaac(out, hf, meta, p["isaac"], p["seed"])
        else:
            report = export_map2d(out, hf, load("heightfield_measured.npy"), meta, load("non_ground.npy"), p["map2d"])
            write_yaml(out/"map2d_report.yaml", report)
    elif name == "handoff":
        export_handoff(out, load("poses_map.npy"), read_yaml(out/"frame_resolved.yaml"), cfg)
    elif name == "check":
        check_outputs(out, cfg)


def reuse_heightfield(source, out, cfg, quick, code_hash):
    """Explicitly import verified upstream artifacts into a fresh output.

    The original manifest/code hash remains in provenance; imported results
    are never represented as having been recomputed by the current code.
    """
    source = Path(source).expanduser().resolve(strict=True)
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError("Reused heightfield source and new --out must be separate directories")
    if any(out.iterdir()):
        raise ValueError("--reuse-heightfield-from requires an empty/new --out")
    original = read_yaml(source/"manifest.yaml")
    original_cfg = read_yaml(source/"effective_config.yaml")
    original_fingerprint = hashlib.sha256(json.dumps({"config": original_cfg, "quick": original["quick"]}, sort_keys=True).encode()).hexdigest()
    if original["config_sha256"] != original_fingerprint:
        raise ValueError("Reused output effective config does not match its manifest")
    if original["quick"] != quick:
        raise ValueError("Reused output quick mode differs; pass the matching --quick flag")

    def upstream_config(value):
        result = copy.deepcopy(value)
        for section in ("mujoco", "isaac", "map2d", "handoff"):
            result["processing"].pop(section, None)
        return result

    if upstream_config(original_cfg) != upstream_config(cfg):
        raise ValueError("Reused output config differs before heightfield; regenerate upstream stages")
    upstream = STAGES[:STAGES.index("mujoco")]
    # Check everything before copying, including every prerequisite's files.
    for name in upstream:
        record = original["stages"].get(name)
        if record is None or set(record["files"]) != set(OUTPUTS[name]):
            raise ValueError(f"Reused output lacks a complete {name} stage")
        for filename, digest in record["files"].items():
            if not (source/filename).is_file() or sha256(source/filename) != digest:
                raise ValueError(f"Reused output has missing/modified {filename}")
    provenance = {"source_output_name": source.name, "source_manifest_sha256": sha256(source/"manifest.yaml"),
                  "source_config_sha256": original["config_sha256"], "source_code_sha256": original["code_sha256"],
                  "current_code_sha256": code_hash,
                  "selection": "explicit import through heightfield; all artifact hashes verified; no upstream recomputation"}
    records = {}
    for name in upstream:
        print(f"[reuse] verified/copying {name}", flush=True)
        for filename in OUTPUTS[name]:
            # Copies must be independent: later stage reruns may overwrite them.
            shutil.copyfile(source/filename, out/filename)
            if sha256(out/filename) != original["stages"][name]["files"][filename]:
                raise ValueError(f"Reused {filename} changed while being copied")
        records[name] = {**original["stages"][name], "reused": True,
                         "source_code_sha256": original["code_sha256"]}
    write_yaml(out/"reused_heightfield.yaml", provenance)
    write_yaml(out/"reused_source_config.yaml", original_cfg)
    return records, provenance


def execute(args):
    cfg = effective_config(read_yaml(args.config), args.quick)
    if args.out:
        out = Path(args.out).expanduser().resolve()
    else:
        out = (Path(__file__).resolve().parents[2]/cfg["output"]["directory"]).resolve()
        if args.quick:
            out /= "quick"
    # Reject output paths in or containing either raw input directory.
    for source in (args.input, args.poses):
        if source:
            parent = Path(source).expanduser().resolve(strict=True).parent
            if out.is_relative_to(parent) or parent.is_relative_to(out):
                raise ValueError("Output must be separate from raw input/pose directories")
    out.mkdir(parents=True, exist_ok=True)
    reuse = getattr(args, "reuse_heightfield_from", None)
    if reuse and (args.input or args.poses):
        raise ValueError("--reuse-heightfield-from cannot be combined with raw --input/--poses")
    if args.stages is None:
        args.stages = list(STAGES[STAGES.index("mujoco"):] if reuse else STAGES)
    if reuse and any(name in args.stages for name in STAGES[:STAGES.index("mujoco")]):
        raise ValueError("Reusing a heightfield only supports mujoco/isaac/map2d/handoff/check stages")
    fingerprint = hashlib.sha256(json.dumps({"config": cfg, "quick": args.quick}, sort_keys=True).encode()).hexdigest()
    code_hash = hashlib.sha256("".join(sha256(Path(__file__).with_name(f)) for f in (
        "pair360_demo.py", "pointcloud.py", "ground.py", "objects.py", "surfaces.py",
        "exports.py", "mesh_tiling.py", "handoff.py")).encode()).hexdigest()
    manifest_path = out/"manifest.yaml"
    manifest = read_yaml(manifest_path) if manifest_path.exists() else {"config_sha256": fingerprint, "code_sha256": code_hash, "quick": args.quick, "stages": {}}
    if reuse:
        records, provenance = reuse_heightfield(reuse, out, cfg, args.quick, code_hash)
        manifest["stages"] = records
        manifest["reused_heightfield"] = provenance
        write_yaml(manifest_path, manifest)
    if manifest["config_sha256"] != fingerprint or manifest["code_sha256"] != code_hash:
        raise ValueError("Output config/code differs. Use a fresh --out directory to avoid mixing artifacts")
    write_yaml(out/"effective_config.yaml", cfg)
    for name in STAGES:
        if name not in args.stages:
            continue
        # Validate dependency hashes recursively: transitive prerequisites matter.
        def validate(dependency):
            if dependency not in manifest["stages"]:
                raise ValueError(f"Missing prerequisite stage {dependency} for {name}")
            for ancestor in DEPS[dependency]:
                validate(ancestor)
            for file, digest in manifest["stages"][dependency]["files"].items():
                if not (out/file).is_file() or sha256(out/file) != digest:
                    raise ValueError(f"Missing/modified prerequisite {file}; rerun {dependency}")
        for dep in DEPS[name]:
            validate(dep)
        # Invalidate this stage and all descendants before any output is changed.
        invalid = {name}
        for candidate in STAGES:
            if any(d in invalid for d in DEPS[candidate]):
                invalid.add(candidate)
        for candidate in invalid:
            manifest["stages"].pop(candidate, None)
        write_yaml(manifest_path, manifest)
        started = time.monotonic()
        print(f"[{name}] starting", flush=True)
        try:
            run_stage(name, args, cfg, out)
        except Exception as exc:
            write_yaml(out/"failure.yaml", {"stage": name, "error": str(exc)})
            raise
        manifest["stages"][name] = {"seconds": round(time.monotonic()-started, 3),
                                    "files": {f: sha256(out/f) for f in OUTPUTS[name]}}
        write_yaml(manifest_path, manifest)
        print(f"[{name}] done ({manifest['stages'][name]['seconds']:.2f}s)", flush=True)
    (out/"failure.yaml").unlink(missing_ok=True)
    print(f"Outputs: {out}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_input = Path(__file__).resolve().parents[2]/"sim_scenes/pair360_parking/T1_parking_Seq0_demo.bin"
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path,
                        help=f"Crop only; never the full source map (default for transform: {default_input})")
    parser.add_argument("--poses", type=Path, help="T1S0 LiDAR poses, 13 columns")
    parser.add_argument("--out", help="Override output.directory in config; default quick runs use its quick/ subdirectory")
    parser.add_argument("--stages", nargs="+", choices=STAGES)
    parser.add_argument("--reuse-heightfield-from", type=Path,
                        help="Verify/copy completed upstream stages from an existing output into a fresh --out")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--cloudcompare", help="CloudCompare executable (including snap launcher)")
    args = parser.parse_args()
    if args.input is None and not args.reuse_heightfield_from and (args.stages is None or "transform" in args.stages):
        args.input = default_input
    try:
        execute(args)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
