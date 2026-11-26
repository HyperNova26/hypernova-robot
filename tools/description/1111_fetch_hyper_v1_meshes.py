# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
"""Fetch the pinned hn_v1_hyper (HYPER v1) meshes into description/hn_v1_hyper/meshes; verify every SHA-256.

Standard library only. Meshes are STL (not Git LFS), downloaded from the commit in mesh_manifest.json.
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    model = Path(__file__).resolve().parents[2] / 'description/hn_v1_hyper'
    manifest = json.loads((model / 'mesh_manifest.json').read_text())
    repo = manifest['repository'].removeprefix('https://github.com/')
    base = f"https://raw.githubusercontent.com/{repo}/{manifest['revision']}/{manifest['source_dir']}/"
    target = model / 'meshes'
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f'Fetched {name}: {len(data)} bytes')


if __name__ == '__main__':
    main()
