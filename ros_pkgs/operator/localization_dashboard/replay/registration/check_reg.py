# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Check a registration: sensor height above mesh_v3 terrain along the trajectory, walkable/keepout hits. Read-only."""
import json, sys
from pathlib import Path
import numpy as np
from rosbags.rosbag2 import Reader
from rosbags.typesys import Stores, get_typestore

res, reg, npz, gj, nav = map(Path, sys.argv[1:6])
T = np.array(json.loads(reg.read_text())['matrix'])
types = get_typestore(Stores.ROS2_HUMBLE)
A, ts = [], []
with Reader(res) as r:
    for c, t, raw in r.messages():
        if c.topic == '/Odometry':
            m = types.deserialize_cdr(raw, c.msgtype); p = m.pose.pose.position
            A.append((p.x, p.y, p.z)); ts.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
A = np.array(A); ts = np.array(ts) - ts[0]
M = A @ T[:3, :3].T + T[:3, 3]
g = np.load(npz); meta = json.loads(gj.read_text())
H, known = g['height'], g['known']; ox, oy = meta['origin_xy']; step = meta['grid_m']
i = np.floor((M[:, 1] - oy) / step + 0.5).astype(int); j = np.floor((M[:, 0] - ox) / step + 0.5).astype(int)
ok = (i >= 0) & (i < H.shape[0]) & (j >= 0) & (j < H.shape[1])
gz = np.full(len(M), np.nan); gz[ok] = np.where(known[i[ok], j[ok]], H[i[ok], j[ok]], np.nan)
d = M[:, 2] - gz
v = ~np.isnan(d)
print(f'poses on terrain {v.mean()*100:.1f}%; sensor height above terrain median {np.nanmedian(d):.2f} m, p5 {np.nanpercentile(d,5):.2f}, p95 {np.nanpercentile(d,95):.2f}')
for k in np.linspace(0, len(M) - 1, 12).astype(int):
    print(f'  t={ts[k]:5.0f}s map ({M[k,0]:+6.1f},{M[k,1]:+6.1f},{M[k,2]:+5.2f}) terrain {gz[k]:+5.2f} height {d[k]:+5.2f}')


def pgm(path):
    with open(path, 'rb') as f:
        f.readline(); w, h = map(int, f.readline().split()); f.readline()
        return np.flipud(np.frombuffer(f.read(), np.uint8).reshape(h, w))
mp, ko = pgm(nav / 'map.pgm'), pgm(nav / 'keepout_mask.pgm')
ii = np.floor((M[:, 1] - 63.45) / 0.1).astype(int); jj = np.floor((M[:, 0] + 82.55) / 0.1).astype(int)
print(f'on map.pgm free {np.mean(mp[ii, jj] == 254)*100:.1f}%, no-go {np.mean(mp[ii, jj] == 0)*100:.1f}%, in keepout {np.mean(ko[ii, jj] == 0)*100:.1f}%')
np.savetxt(sys.argv[6], np.c_[ts, M], delimiter=',', header='t_s,x,y,z (pair360_map, sensor/IMU origin)', comments='', fmt='%.3f')
