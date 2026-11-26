# SPDX-License-Identifier: Apache-2.0
"""Rebuild the accepted S-004 ground (v8 release, or v9 = pc_v1 ground v1) from its review inputs and check the hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(*parts: str) -> None:
    print("running:", " ".join(parts), flush=True)
    subprocess.run([sys.executable, *parts], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--ground", choices=["v8", "v9"], default="v8",
                        help="v8: accepted S-004 release with simulator scenes (default); "
                             "v9: pc_v1 ground v1, the input of PAIR360 maps v1 and v3 (mesh and point layers only)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    tools = root / "tools/map/1109_s004_ground"
    release = root / "sim_scenes/S004_ground_final"
    manifest = json.loads((release / "checksums.json").read_text(encoding="utf-8"))
    inputs = dict(manifest["rebuild_inputs"])
    if args.ground == "v9":
        inputs.update(manifest["ground_v9"]["decisions"])
    for name, expected in inputs.items():
        path = root / name
        if sha256(path) != expected:
            raise RuntimeError(f"missing or changed review input: {name}")

    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    source = release / "input/original.ply"
    baseline = release / "review"
    decisions = tools / ("continuous_ground_20261104_v7.json" if args.ground == "v8" else "continuous_ground_20261109_v9.json")
    surface = out / ("v7" if args.ground == "v8" else "v9_surface")
    run(str(tools / "build_continuous_ground_v5.py"),
        "--source", str(source), "--baseline", str(baseline), "--decisions", str(decisions),
        "--design", str(baseline / "design_policy.npz"), "--out", str(surface))
    run(str(tools / "smooth_local_ground_v8.py"),
        "--source", str(surface / "ground_surface.npz"), "--out", str(out / args.ground))
    result = out / args.ground / "ground_surface_mesh.ply"
    actual = sha256(result)
    expected_mesh = manifest["final_mesh_sha256"] if args.ground == "v8" else manifest["ground_v9"]["mesh_sha256"]
    if actual != expected_mesh:
        raise RuntimeError(f"rebuild differs from accepted mesh: {actual}")
    run(str(tools / "export_s004_layers.py"),
        "--source", str(source), "--classification", str(baseline / "classification.npz"),
        "--surface", str(out / args.ground / "ground_surface.npz"),
        "--out", str(out / "pointcloud"))
    for name in ("ground.ply", "non_ground.ply"):
        actual_layer = sha256(out / "pointcloud" / name)
        expected_layer = (manifest["release_files"]["result/" + name] if args.ground == "v8"
                          else manifest["ground_v9"]["pointcloud"][name])
        if actual_layer != expected_layer:
            raise RuntimeError(f"rebuilt point layer differs: {name} {actual_layer}")
    report = {"ground": args.ground, "verified_mesh_sha256": actual,
              "mesh": str(result), "pointcloud": str(out / "pointcloud")}
    if args.ground == "v8":
        run(str(tools / "export_final_sim.py"),
            "--surface-dir", str(out / "v8"), "--out", str(out / "simulator"))
        report["simulator"] = str(out / "simulator")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
