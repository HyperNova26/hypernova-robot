"""Package the tested MuJoCo scene and Go2 loader without external source files."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def package(root, scene):
    report = json.loads((scene/"verification.json").read_text(encoding="utf-8"))
    manifest = json.loads((scene/"manifest.json").read_text(encoding="utf-8"))
    if report["scene_xml_sha256"] != hashlib.sha256((scene/"scene.xml").read_bytes()).hexdigest():
        raise ValueError("Scene changed since the last MuJoCo validation")
    if not manifest["reference_map_sha256"] or report["reference_map_sha256"] != manifest["reference_map_sha256"]:
        raise ValueError("Scene was not verified against the released map candidate")
    if not report.get("go2_stand") or report["route_clearance_intersections"]:
        raise ValueError("Route and official Go2 must be checked before packaging")
    paths = ["README.html", "load_go2.py", "scene/manifest.json", "scene/scene.xml", "scene/verification.json", "scene/trees.json"]
    if "ground_refinement" in manifest:
        paths += ["scene/ground_adjustments.npz"]
    paths += ["scene/"+a.attrib["file"] for a in ET.parse(scene/"scene.xml").findall("./asset/hfield")]
    archive = root/"PAIR360-Go2-MuJoCo_mesh_v1b.zip"
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        stage = Path(tmp)/archive.name
        with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as bundle:
            for name in paths:
                source = scene/name[6:] if name.startswith("scene/") else root/name
                bundle.write(source, f"PAIR360-Go2/{name}")
        with zipfile.ZipFile(stage) as bundle:
            if len(bundle.namelist()) != len(set(paths)) or bundle.testzip():
                raise ValueError("ZIP file entries failed validation")
        stage.replace(archive)
    print(archive.name, archive.stat().st_size, hashlib.sha256(archive.read_bytes()).hexdigest())


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=root/"scene")
    parser.add_argument("--build-with-go2", type=Path, help="Rebuild from the map candidate and test this Menagerie model")
    args = parser.parse_args()
    if args.build_with_go2:
        with tempfile.TemporaryDirectory(prefix="pair360-handoff-") as tmp:
            stage = Path(tmp)
            subprocess.run([sys.executable, "-B", str(root/"build_terrain.py"), "--out", tmp], check=True)
            subprocess.run([sys.executable, "-B", str(root/"verify_terrain.py"), "--scene", tmp,
                            "--go2", str(args.build_with_go2.resolve())], check=True)
            package(root, stage)
    else:
        package(root, args.scene.resolve())


if __name__ == "__main__":
    main()
