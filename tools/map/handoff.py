# SPDX-License-Identifier: Apache-2.0
"""T1S0 crop traversal intervals and LiDAR ground truth poses."""

from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from pointcloud import apply_transform, write_yaml


def read_poses(path):
    rows = np.loadtxt(path, ndmin=2)
    if rows.shape[1] != 13 or not np.isfinite(rows).all():
        raise ValueError("Poses must contain finite t_sec + row-major 3x4 matrices")
    if len(rows) > 1 and np.any(np.diff(rows[:, 0]) <= 0):
        raise ValueError("Pose timestamps must strictly increase")
    rot = rows[:, 1:].reshape(-1, 3, 4)[:, :, :3]
    if not np.allclose(rot.transpose(0, 2, 1) @ rot, np.eye(3), atol=1e-3) or not np.allclose(np.linalg.det(rot), 1, atol=1e-3):
        raise ValueError("Pose file contains invalid rotations")
    return rows


def export_handoff(out, rows, resolved, cfg):
    out = Path(out)
    poses = rows[:, 1:].reshape(-1, 3, 4)
    xy = poses[:, :2, 3]
    lo, hi = np.asarray(resolved["bounds_map"])
    inside = np.all((xy >= lo[:2]) & (xy <= hi[:2]), axis=1)
    selected = np.flatnonzero(inside)
    groups = []
    gap = cfg["processing"]["handoff"]["max_pose_gap_s"]
    if len(selected):
        cuts = np.flatnonzero((np.diff(selected) > 1) | (np.diff(rows[selected, 0]) > gap)) + 1
        groups = np.split(selected, cuts)
    intervals = [{"start_unix_s": float(rows[g[0], 0]), "end_unix_s": float(rows[g[-1], 0]),
                  "pose_count": len(g)} for g in groups]
    t = np.asarray(resolved["T_demo_from_map"])
    xyz = apply_transform(poses[inside, :, 3], t)
    if len(selected):
        rotations = t[:3, :3] @ poses[inside, :, :3]
        quats = Rotation.from_matrix(rotations).as_quat()
        # Resolve q/-q sign ambiguity for continuous TUM trajectories.
        for i in range(1, len(quats)):
            if quats[i] @ quats[i-1] < 0:
                quats[i] *= -1
        tum = np.column_stack((rows[inside, 0], xyz, quats))
    else:
        tum = np.empty((0, 8))
    np.savetxt(out/"gt_poses_demo.tum", tum, fmt=["%.9f"]*8)
    report = {"source_frame": cfg["source"]["map_frame"], "pose_frame": "LiDAR (not robot base)",
              "selection": "inclusive source/map-frame XY AABB of the crop; not its convex hull",
              "bounds_map_xy": [lo[:2].tolist(), hi[:2].tolist()], "max_pose_gap_s": gap,
              "pose_count": len(selected), "intervals": intervals, "T3": "excluded: different frame"}
    write_yaml(out/"traversals.yaml", report)
    (out/"ATTRIBUTION.txt").write_text(
        "PAIR360 — Geunu Kim, Daeho Kim, Jaeyun Jang, Hyoseok Hwang, RA-L 2024.\n"
        "https://airlabkhu.github.io/PAIR-360-Dataset/\n"
        "https://doi.org/10.1109/LRA.2024.3460418\n"
        "Source database and shared derived terrain/map/pose outputs: ODbL 1.0.\n"
        "https://opendatacommons.org/licenses/odbl/1-0/\n"
        "Adaptations: crop, rigid transform/leveling, filtering, classes, rasterization, meshing and pose selection.\n")
    (out/"HANDOFF.md").write_text(
        "# PAIR360 SLAM 인계\n\n"
        "`frame_resolved.yaml`의 최종 변환은 T1S0 map → demo입니다. "
        "`gt_poses_demo.tum`은 LiDAR pose이며 로봇 base pose가 아닙니다. "
        "시각은 원본 Unix 초입니다. T3는 좌표계가 달라 제외합니다.\n\n"
        "`traversals.yaml`은 crop의 원본 map XY AABB 안에 들어온 연속 구간입니다. "
        "crop 모양의 다각형 포함 판정은 아닙니다. "
        "`heightfield.yaml`, `map2d.yaml`, `effective_config.yaml`, `manifest.yaml`, "
        "`smoke_report.yaml`을 함께 전달합니다.\n\n"
        "공개·공유 파생 데이터는 ODbL 1.0을 유지하고 `ATTRIBUTION.txt`를 포함합니다.\n")
    return report
