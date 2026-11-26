# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Register our FAST-LIO run (camera_init) to pc_v2 and to pair360_map (map_v3). Read-only on inputs.

usage: register.py RESULT_BAG PC_V2_PCD MAP_V3_MANIFEST MAP_V3_PCD OUT_JSON
Steps: accumulate /lidar/points (camera_init) -> voxel 0.4 m; coarse yaw search (with z flip, since our
camera_init is the z-down IMU frame) by trimmed nearest-neighbour score; point-to-point ICP refine;
compose with pc_v2_to_map. Independently check the composed result directly against map_v3.
"""
import json, math, sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from rosbags.rosbag2 import Reader
from rosbags.typesys import Stores, get_typestore

res, pcv2, man, mapv3, out = map(Path, sys.argv[1:6])
types = get_typestore(Stores.ROS2_HUMBLE)


def voxel(P, v):
    k = np.floor(P / v).astype(np.int64)
    _, idx = np.unique(k, axis=0, return_index=True)
    return P[idx]


def read_pcd_xyz(path):
    with open(path, 'rb') as f:
        head = {}
        while True:
            line = f.readline().decode('ascii').strip()
            key, *val = line.split()
            head[key] = val
            if key == 'DATA':
                break
        fields, sizes, types_, counts = head['FIELDS'], list(map(int, head['SIZE'])), head['TYPE'], list(map(int, head.get('COUNT', ['1'] * len(head['FIELDS']))))
        n = int(head['POINTS'][0])
        assert head['DATA'][0] == 'binary', head['DATA']
        dt = np.dtype([(f, {('F', 4): '<f4', ('F', 8): '<f8', ('U', 1): 'u1', ('U', 2): '<u2', ('U', 4): '<u4', ('I', 4): '<i4', ('I', 2): '<i2', ('I', 1): 'i1'}[(t, s)], (c,) if c > 1 else ())
                       for f, s, t, c in zip(fields, sizes, types_, counts)])
        a = np.frombuffer(f.read(n * dt.itemsize), dt, n)
    return np.stack([a['x'], a['y'], a['z']], 1).astype(float), a


# 1. our accumulated cloud and trajectory
dtype = None
clouds, traj = [], []
with Reader(res) as r:
    for c, t, raw in r.messages():
        m = types.deserialize_cdr(raw, c.msgtype)
        if c.topic == '/Odometry':
            p = m.pose.pose.position; traj.append((p.x, p.y, p.z))
        elif c.topic == '/lidar/points' and len(clouds) < 100000:
            off = {f.name: f.offset for f in m.fields}
            raw_b = m.data.tobytes()
            n = m.width * m.height
            arr = np.frombuffer(raw_b, np.uint8).reshape(n, m.point_step)
            xyz = np.stack([arr[:, off[k]:off[k] + 4].copy().view('<f4')[:, 0] for k in 'xyz'], 1)
            clouds.append(xyz[::2])
traj = np.array(traj)
S = voxel(np.concatenate(clouds).astype(float), 0.4)
print('our cloud', len(S), 'pts after 0.4 m voxel; frames', len(clouds))

T_v2_map = np.array(json.loads(man.read_text())['pc_v2_to_map'])
print('pc_v2_to_map\n', np.round(T_v2_map, 4))
V2, _ = read_pcd_xyz(pcv2)
D = voxel(V2, 0.3)
tree = cKDTree(D)
print('pc_v2', len(V2), '->', len(D))


def score(P, trim=2.0):
    d, _ = tree.query(P, distance_upper_bound=trim)
    d = np.where(np.isinf(d), trim, d)
    return d.mean(), (d < 0.3).mean()


def Rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def icp(P, R, t, iters=40, maxd=2.0):
    for it in range(iters):
        Q = P @ R.T + t
        d, i = tree.query(Q, distance_upper_bound=maxd)
        ok = np.isfinite(d)
        A, B = Q[ok], D[i[ok]]
        ca, cb = A.mean(0), B.mean(0)
        U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
        dR = Vt.T @ np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))]) @ U.T
        R, t = dR @ R, dR @ (t - cb) + cb if False else dR @ t + (cb - dR @ ca)
        maxd = max(0.5, maxd * 0.85)
    return R, t


sub = S[np.random.default_rng(0).choice(len(S), min(20000, len(S)), replace=False)]
best = None
if len(sys.argv) > 6:  # known coarse answer from the first run: same origin as pc_v2, z flipped
    R0 = np.diag([1., -1, -1]); best = (*score(sub @ R0.T), 'Rx(pi)', 0, np.zeros(3), R0)
for flip_name, F in ([] if best else [('Rx(pi)', np.diag([1., -1, -1])), ('identity', np.eye(3))]):
    for yaw in np.arange(0, 360, 3):
        R = Rz(math.radians(yaw)) @ F
        # translation: try origin at pc_v2 origin and a coarse grid around it
        for tx in np.arange(-30, 31, 10):
            for ty in np.arange(-30, 31, 10):
                t = np.array([tx, ty, 0.0])
                m, frac = score(sub @ R.T + t)
                if best is None or m < best[0]:
                    best = (m, frac, flip_name, yaw, t, R)
print(f'coarse best: {best[2]} yaw {best[3]} t {best[4]} mean nn {best[0]:.2f} m inliers(<0.3m) {best[1]*100:.1f}%')
R, t = icp(sub, best[5], best[4])
m, frac = score(S @ R.T + t, trim=1.0)
print(f'ICP: mean nn {m:.3f} m (trim 1 m), inliers(<0.3 m) {frac*100:.1f}%')
T_ours_v2 = np.eye(4); T_ours_v2[:3, :3] = R; T_ours_v2[:3, 3] = t
T_ours_map = T_v2_map @ T_ours_v2
Rm, tm = T_ours_map[:3, :3], T_ours_map[:3, 3]
yaw = math.degrees(math.atan2(Rm[1, 0], Rm[0, 0]))
pitch = math.degrees(-math.asin(max(-1, min(1, Rm[2, 0]))))
roll = math.degrees(math.atan2(Rm[2, 1], Rm[2, 2]))
print('camera_init origin (recording start, IMU) in pair360_map:', np.round(tm, 3), f'rpy deg ({roll:.2f}, {pitch:.2f}, {yaw:.2f})')

# independent check against map_v3
M3, a3 = read_pcd_xyz(mapv3)
keep = np.isin(a3['label'], [1, 2]) if 'label' in a3.dtype.names else np.ones(len(M3), bool)
tree = cKDTree(voxel(M3[keep], 0.3))
D = tree.data
m3, frac3 = score(S @ Rm.T + tm, trim=1.0)
print(f'check vs map_v3 static: mean nn {m3:.3f} m, inliers(<0.3 m) {frac3*100:.1f}%')
Tm = traj @ Rm.T + tm
print('trajectory in map: start', np.round(Tm[0], 2), 'x range', np.round([Tm[:, 0].min(), Tm[:, 0].max()], 1), 'y range', np.round([Tm[:, 1].min(), Tm[:, 1].max()], 1), 'z range', np.round([Tm[:, 2].min(), Tm[:, 2].max()], 1))
out.write_text(json.dumps({
    'transform': 'pair360_map <- camera_init (FAST-LIO run with sensor-capture/ros/fast_lio_mlx.yaml, 11-15 recording)',
    'matrix': T_ours_map.round(6).tolist(),
    'translation_xyz': tm.round(4).tolist(), 'rpy_deg': [round(roll, 3), round(pitch, 3), round(yaw, 3)],
    'via': 'ICP to pc_v2 (voxel 0.3 m), composed with map_v3 manifest pc_v2_to_map',
    'fit_pc_v2': {'mean_nn_m_trim1': round(m, 4), 'inlier_lt_0.3m': round(frac, 4)},
    'fit_map_v3_static': {'mean_nn_m_trim1': round(m3, 4), 'inlier_lt_0.3m': round(frac3, 4)},
    'trajectory_start_map': Tm[0].round(3).tolist(),
}, indent=2))
print('wrote', out)
