"""Step 10. CloudCompare bundle: two files, one for point clouds and one for meshes, each with named children.

map_v3_pointclouds.bin (open it once; tick children on and off in the DB tree)
  ground_pc_v1 (green), ground_pc_v2 (blue), obstacle (orange), removed_movable (red): together = map_v3.pcd
  pc_v1_not_in_pc_v2 (purple): pc_v1 rows left out by the pc_v2-priority rule with no pc_v2 return within
      0.5 m; diagnostic only, not part of map_v3
  input_pc_v1, input_pc_v2: the two captures in the map frame, step-2 labels, turbo height colour
mesh_v3_meshes.bin
  ground_mesh (grey), obstacle_mesh (no-go blocks), trees_mesh, demo_route (red ribbon, start/goal discs)

The .bin files are written by the CloudCompare command line (config.CLOUDCOMPARE, -SAVE_* ALL_AT_ONCE).
Every point keeps its fields (intensity, label, source) as scalar fields. CloudCompare's PCD reader switches
the scalar-field display on, which hides the class colours (each cloud showed a scalar-field colour ramp
instead), so show_rgb() turns that one display flag off in the saved file; the scalar fields stay selectable.

In : frames.map_xyzi, work/02_<pc>_labels.npy, results/map_v3/*.pcd, results/mesh_v3/*.ply
Out: results/cc_view_map_v3/{map_v3_pointclouds.bin, mesh_v3_meshes.bin, contents.json}
"""
import mmap
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from config import (CLASS_RGB, CLOUDCOMPARE, MAP_DIR, MAP_VERSION, MESH_DIR, MESH_VERSION, RESULTS, SOURCE_ID,
                    work)
from frames import map_xyzi
from pcio import read_labelled, save_json, sha256, write_pcd

OUT = RESULTS/f"cc_view_{MAP_VERSION}"


def cloudcompare(*args):
    if not CLOUDCOMPARE.exists():
        raise SystemExit(f"CloudCompare not found at {CLOUDCOMPARE}; set the CLOUDCOMPARE environment variable")
    subprocess.run([str(CLOUDCOMPARE), "-SILENT", "-AUTO_SAVE", "OFF", *map(str, args)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def show_rgb(path, names):
    """Turn off 'scalar field shown' for the named clouds of a CloudCompare .bin (format CCB2, CloudCompare 2.13).

    Each entity is written as: class id, unique id, name (uint32 byte length + UTF-16-BE), flags (4 bytes),
    metadata count (4 bytes), then the display booleans visible, locked, colours, normals, scalar field, ...
    The layout is checked byte for byte before the single flag is changed; anything else stops the step."""
    expected = bytes([1, 0, 1, 0, 1, 0, 0, 0])
    with open(path, "r+b") as stream, mmap.mmap(stream.fileno(), 0) as data:
        if data[:4] != b"CCB2":
            raise SystemExit(f"{path} is not a CloudCompare CCB2 file")
        for name in names:
            label = name.encode("utf-16-be")
            at = data.find(struct.pack(">I", len(label))+label)
            flags = at+4+len(label)+8
            if at < 0 or data[flags-4:flags] != bytes(4) or data[flags:flags+8] != expected:
                raise SystemExit(f"Unexpected CloudCompare layout for '{name}' in {path}; display flags not changed")
            data[flags+4] = 0
        data.flush()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():   # earlier layouts (01..08 single files) are replaced by the two bundles
        if old.is_file():
            old.unlink()
    with tempfile.TemporaryDirectory(dir=RESULTS) as tmp:
        tmp = Path(tmp)
        clouds = []
        g = read_labelled(MAP_DIR/f"{MAP_VERSION}_ground.pcd")
        for key in ("pc_v1", "pc_v2"):
            part = g[np.asarray(g["source"]) == SOURCE_ID[key]]
            path = tmp/f"ground_{key}.pcd"
            write_pcd(path, part["xyzi"], part["label"], part["source"], np.tile(np.array(CLASS_RGB[f"ground_{key}"], np.uint8), (len(part["label"]), 1)))
            clouds.append((path, len(part["label"])))
        for src, name in ((MAP_DIR/f"{MAP_VERSION}_obstacle.pcd", "obstacle"),
                          (MAP_DIR/f"{MAP_VERSION}_removed_dynamic.pcd", "removed_movable"),
                          (MAP_DIR/"pc_v1_not_in_pc_v2.pcd", "pc_v1_not_in_pc_v2")):
            shutil.copyfile(src, tmp/f"{name}.pcd")
            clouds.append((tmp/f"{name}.pcd", len(read_labelled(src)["label"])))
        for key in ("pc_v1", "pc_v2"):
            p = map_xyzi(key)
            path = tmp/f"input_{key}.pcd"
            write_pcd(path, p, np.load(work(f"02_{key}_labels.npy")).astype(np.uint32), np.full(len(p), SOURCE_ID[key], np.uint32))
            clouds.append((path, len(p)))
        open_args = [a for path, _ in clouds for a in ("-O", path)]
        cloudcompare(*open_args, "-C_EXPORT_FMT", "BIN", "-SAVE_CLOUDS", "ALL_AT_ONCE", "FILE", OUT/"map_v3_pointclouds.bin")
        show_rgb(OUT/"map_v3_pointclouds.bin", [path.stem for path, _ in clouds])
        meshes = []
        for name, src in (("ground_mesh", f"{MESH_VERSION}_ground.ply"), ("obstacle_mesh", f"{MESH_VERSION}_obstacle.ply"),
                          ("trees_mesh", f"{MESH_VERSION}_trees.ply"),
                          ("demo_route", f"{MESH_VERSION}_route.ply")):
            cloudcompare("-O", MESH_DIR/src, "-RENAME_ENTITIES", name, "-M_EXPORT_FMT", "BIN", "-SAVE_MESHES", "FILE", tmp/f"{name}.bin")
            meshes.append((tmp/f"{name}.bin", src))
        cloudcompare(*[a for path, _ in meshes for a in ("-O", path)], "-M_EXPORT_FMT", "BIN",
                     "-SAVE_MESHES", "ALL_AT_ONCE", "FILE", OUT/"mesh_v3_meshes.bin")
    contents = {"map_v3_pointclouds.bin": {"children": {path.stem: n for path, n in clouds},
                                           "note": "ground_pc_v1 + ground_pc_v2 + obstacle + removed_movable = map_v3.pcd; "
                                                   "pc_v1_not_in_pc_v2 is diagnostic; input_* are the captures in the map frame"},
                "mesh_v3_meshes.bin": {"children": {path.stem: src for path, src in meshes}}}
    for name in contents:
        contents[name]["bytes"] = (OUT/name).stat().st_size
        contents[name]["sha256"] = sha256(OUT/name)
    save_json(OUT/"contents.json", contents)
    print(OUT, {k: v["bytes"] for k, v in contents.items()})


if __name__ == "__main__":
    main()
