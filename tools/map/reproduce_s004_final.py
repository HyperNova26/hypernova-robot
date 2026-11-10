# SPDX-License-Identifier: Apache-2.0
"""Rebuild the accepted S-004 ground mesh and simulator scenes from its review inputs."""
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
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    release = root / "sim_scenes/S004_ground_final"
    manifest = json.loads((release / "checksums.json").read_text(encoding="utf-8"))
    for name, expected in manifest["rebuild_inputs"].items():
        path = root / name
        if sha256(path) != expected:
            raise RuntimeError(f"missing or changed review input: {name}")

    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    source = release / "input/original.ply"
    baseline = release / "review"
    run(str(root / "tools/map/build_continuous_ground_v5.py"),
        "--source", str(source), "--baseline", str(baseline),
        "--decisions", str(root / "tools/map/continuous_ground_20261104_v7.json"),
        "--design", str(baseline / "design_policy.npz"), "--out", str(out / "v7"))
    run(str(root / "tools/map/smooth_local_ground_v8.py"),
        "--source", str(out / "v7/ground_surface.npz"), "--out", str(out / "v8"))
    result = out / "v8/ground_surface_mesh.ply"
    actual = sha256(result)
    if actual != manifest["final_mesh_sha256"]:
        raise RuntimeError(f"rebuild differs from accepted mesh: {actual}")
    run(str(root / "tools/map/export_s004_layers.py"),
        "--source", str(source), "--classification", str(baseline / "classification.npz"),
        "--surface", str(out / "v8/ground_surface.npz"),
        "--out", str(out / "pointcloud"))
    for name in ("ground.ply", "non_ground.ply"):
        actual_layer = sha256(out / "pointcloud" / name)
        if actual_layer != manifest["release_files"]["result/" + name]:
            raise RuntimeError(f"rebuilt point layer differs: {name} {actual_layer}")
    run(str(root / "tools/map/export_final_sim.py"),
        "--surface-dir", str(out / "v8"), "--out", str(out / "simulator"))
    print(json.dumps({"verified_mesh_sha256": actual,
                      "mesh": str(result), "pointcloud": str(out / "pointcloud"),
                      "simulator": str(out / "simulator")}, indent=2))


if __name__ == "__main__":
    main()
