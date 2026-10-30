# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""Fetch only the pinned Go2 mesh dependency; verify every SHA-256."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--convert', action='store_true', help='Convert DAE to STL using installed trimesh and pycollada')
    args = parser.parse_args()
    model = Path(__file__).resolve().parents[2] / 'description/hypernova_go2'
    manifest = json.loads((model / 'mesh_manifest.json').read_text())
    target = model / 'meshes'
    target.mkdir(exist_ok=True)
    base = ('https://raw.githubusercontent.com/unitreerobotics/unitree_ros/'
            + manifest['revision'] + '/robots/go2_description/dae/')
    for name, expected in manifest['assets'].items():
        path = target / name
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f'Existing mesh differs; refusing to overwrite: {path}')
            print(f'OK {name}')
            continue
        with urlopen(base + name, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'SHA-256 mismatch: {name}')
        path.write_bytes(data)
        print(f'Fetched {name}: {len(data)} bytes')
    if args.convert:
        import trimesh

        for name in manifest['assets']:
            source = target / name
            # Bake scene-node transforms; preserve SI geometry without decimation.
            mesh = trimesh.load(source, force='scene').to_geometry()
            output = source.with_suffix('.stl')
            data = mesh.export(file_type='stl')
            expected = manifest.get('converted_assets', {}).get(output.name)
            if expected and hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f'Converted mesh differs from recorded tool versions: {output.name}')
            if output.exists() and output.read_bytes() != data:
                raise RuntimeError(f'Existing converted mesh differs: {output}')
            output.write_bytes(data)
            print(f'Converted {output.name}: {len(mesh.faces)} triangles')


if __name__ == '__main__':
    main()
