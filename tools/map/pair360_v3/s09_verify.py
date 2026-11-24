"""Step 9. Check mesh_v3 in MuJoCo: the reference path is clear, the floor is continuous, Go2 stands.

Path probes every 0.1 m (centre + 4 corners of a 0.48 x 0.28 m footprint): the top surface must be the
ground (no no-go above it) and nothing solid within 0.54 m above the floor. Then the official
Menagerie Go2 stands 3 s at the start, and 2 s at every metre of the path facing along it.
Not a walking test: navigation and the team controller are checked separately.

In : results/mesh_v3/mujoco/*, data/models/unitree_go2/go2.xml
Out: results/mesh_v3/mujoco/verification.json
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from config import GO2_XML, MESH_DIR
from pcio import load_json, save_json, sha256

SIM = MESH_DIR/"mujoco"


def probe_path(model, data, route):
    import mujoco
    ground_only = np.array([1, 0, 0, 0, 0, 0], np.uint8)
    solid = np.array([0, 0, 1, 0, 1, 0], np.uint8)

    def ray(p, d, groups):
        return mujoco.mj_ray(model, data, np.asarray(p, float), np.asarray(d, float), groups, True, -1,
                             np.array([-1], np.int32))
    path = []
    for a, b in zip(route, route[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b-a)/.1)))
        path.extend(a+(b-a)*t for t in np.linspace(0, 1, n, endpoint=False))
    path.append(route[-1])
    blocked, floors, missing = [], [], 0
    for c in path:
        for off in ([0, 0], [.24, .14], [.24, -.14], [-.24, .14], [-.24, -.14]):
            xy = c+off
            # a ray exactly on a heightfield cell edge can slip to the field's base; a second ray 1 mm off settles it
            hits = [h for h in (ray([*xy, 60], [0, 0, -1], ground_only), ray([xy[0]+.001, xy[1]+.001, 60], [0, 0, -1], ground_only)) if h >= 0]
            d = min(hits) if hits else -1
            if d < 0:
                missing += 1
                continue
            fl = 60-d
            hit = ray([*xy, 60], [0, 0, -1], solid)
            low = ray([*xy, fl+.01], [0, 0, 1], solid)
            if (hit >= 0 and 60-hit > fl+.02) or 0 <= low <= .54:
                blocked.append(np.round(xy, 2).tolist())
            if off == [0, 0]:
                floors.append(fl)
    return {"route_probes": 5*len(path), "probes_without_floor": missing, "blocked_probes": len(blocked),
            "blocked_examples": blocked[:8], "max_center_step_per_10cm_m": float(np.abs(np.diff(floors)).max())}


def main():
    import mujoco
    from load_go2 import check_menagerie_stand
    manifest = load_json(SIM/"manifest.json")
    model = mujoco.MjModel.from_xml_path(str(SIM/"scene.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    report = {"mujoco_version": mujoco.__version__, "scene_xml_sha256": sha256(SIM/"scene.xml"),
              "geoms": model.ngeom, "hfields": model.nhfield,
              **probe_path(model, data, np.asarray(manifest["route_xyz_m"])[:, :2]),
              "go2_xml_sha256": sha256(GO2_XML), "go2_stand_at_start": check_menagerie_stand(GO2_XML, scene_dir=SIM)}
    out = subprocess.run([sys.executable, str(Path(__file__).with_name("route_stand_check.py")), str(GO2_XML), "--scene-dir", str(SIM)],
                         check=True, capture_output=True, text=True).stdout
    stations = json.loads(out)
    report["go2_stand_along_path"] = {k: v for k, v in stations.items() if k != "results"}
    report["go2_stand_failures"] = [r for r in stations["results"] if not r["pass"]]
    save_json(SIM/"verification.json", report)
    print({k: report[k] for k in ("blocked_probes", "probes_without_floor", "max_center_step_per_10cm_m")},
          report["go2_stand_along_path"])


if __name__ == "__main__":
    main()
