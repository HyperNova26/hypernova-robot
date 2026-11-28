# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Fit a small roll/pitch correction about the start so the trajectory keeps a constant height above mesh_v3.
usage: tilt_fix.py REGISTRATION_JSON TRAJ_CSV(t,x,y,z=terrain+0.4,yaw,lio_z) OUT_JSON
"""
import json, math, sys
from pathlib import Path
import numpy as np

reg, traj, out = map(Path, sys.argv[1:4])
R = json.loads(reg.read_text())
T = np.array(R['matrix'])
a = np.loadtxt(traj, delimiter=',', skiprows=1)
x, y, ground, lz = a[:, 1], a[:, 2], a[:, 3] - 0.40, a[:, 5]
h = lz - ground
p0 = np.array([x[0], y[0], lz[0]])
A = np.c_[x - x[0], y - y[0], np.ones(len(x))]
coef, *_ = np.linalg.lstsq(A, h, rcond=None)
res = h - A @ coef
print(f'before: height above terrain mean {h.mean():.2f} std {h.std():.2f} m (p5 {np.percentile(h,5):.2f}, p95 {np.percentile(h,95):.2f})')
print(f'plane fit: dh/dx {coef[0]*100:.2f} cm/m, dh/dy {coef[1]*100:.2f} cm/m, offset {coef[2]:.2f} m; residual std {res.std():.2f} m p95|r| {np.percentile(abs(res),95):.2f}')
# rotation that removes the slope: z' = z - (ax*dx + ay*dy) -> small rotation about start
ax, ay = coef[0], coef[1]
n = np.array([-ax, -ay, 1.0]); n /= np.linalg.norm(n)   # current 'up' of the tilted trajectory plane
z = np.array([0, 0, 1.0])
v = np.cross(n, z); s = np.linalg.norm(v); c = n @ z
K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
Rc = np.eye(3) + K + K @ K * ((1 - c) / s ** 2) if s > 1e-12 else np.eye(3)
C = np.eye(4); C[:3, :3] = Rc; C[:3, 3] = p0 - Rc @ p0
T2 = C @ T
P = np.c_[x, y, lz] @ Rc.T + C[:3, 3]
h2 = P[:, 2] - ground  # ground under the slightly moved xy is nearly the same (shift < 0.1 m)
print(f'after: height above terrain mean {h2.mean():.2f} std {h2.std():.2f} m (p5 {np.percentile(h2,5):.2f}, p95 {np.percentile(h2,95):.2f}); correction {math.degrees(math.acos(c)):.2f} deg')
Rm = T2[:3, :3]
yaw = math.degrees(math.atan2(Rm[1, 0], Rm[0, 0])); pitch = math.degrees(-math.asin(max(-1, min(1, Rm[2, 0])))); roll = math.degrees(math.atan2(Rm[2, 1], Rm[2, 2]))
R.update({'matrix': T2.round(6).tolist(), 'translation_xyz': T2[:3, 3].round(4).tolist(), 'rpy_deg': [round(roll, 3), round(pitch, 3), round(yaw, 3)],
          'tilt_correction': {'deg': round(math.degrees(math.acos(c)), 3), 'dh_dx': round(ax, 5), 'dh_dy': round(ay, 5),
                              'why': 'constant sensor height above mesh_v3 along the loop; ICP pitch is weakly constrained (narrow vertical FoV)',
                              'height_above_terrain_m': {'before_std': round(h.std(), 3), 'after_std': round(h2.std(), 3), 'after_mean': round(h2.mean(), 3)}}})
out.write_text(json.dumps(R, indent=2))
print('rpy deg', R['rpy_deg'], 'xyz', R['translation_xyz'])
