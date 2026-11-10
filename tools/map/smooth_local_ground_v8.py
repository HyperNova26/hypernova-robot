# SPDX-License-Identifier: Apache-2.0
"""Repair isolated raised parking-surface bumps without changing its footprint."""
from pathlib import Path
import argparse
import json
import numpy as np
from scipy.ndimage import median_filter, distance_transform_edt, label, binary_dilation
from build_continuous_ground_v5 import fine_surface, build_mesh, write_mesh_ply, harmonic_fill

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root / 'data/PAIR360_demo/20261104_continuous_ground_v7/ground_surface.npz')
parser.add_argument('--out', type=Path, default=root / 'data/PAIR360_demo/20261105_local_smoothing_v8')
args = parser.parse_args()
source = args.source.resolve()
out = args.out.resolve()
if out.exists():
    raise FileExistsError(out)
s = np.load(source)
h = s['coarse_height'].astype(float)
allowed = s['coarse_allowed']
observed = s['observed_coarse'].copy()
x0, y0 = float(s['x'][0]-.05), float(s['y'][0]-.05)
cx = x0 + (np.arange(h.shape[1])+.5)*.5
cy = y0 + (np.arange(h.shape[0])+.5)*.5
xx, yy = np.meshgrid(cx, cy)
parking = (xx >= -82) & (xx <= -16) & (yy >= 64) & (yy <= 140)
finite = allowed & np.isfinite(h)
nearest = distance_transform_edt(~finite, return_distances=False, return_indices=True)
reference = median_filter(h[tuple(nearest)], size=7, mode='nearest')
residual = h - reference
seeds = finite & parking & (residual > .15)
components, count = label(seeds)
selected = np.zeros_like(seeds)
records = []
for i in range(1, count+1):
    component = components == i
    size = int(component.sum())
    peak = float(np.max(residual[component]))
    if size >= 2 and peak > .25:
        selected |= component
        yidx,xidx = np.where(component)
        records.append(dict(cells=size, peak_above_local_m=peak, center_xy_m=[float(cx[round(xidx.mean())]),float(cy[round(yidx.mean())])]))
if not records:
    raise RuntimeError('No isolated raised parking components detected')
repair = binary_dilation(selected, iterations=2) & finite & parking
anchors = h.copy(); anchors[repair] = np.nan
corrected,_,resid = harmonic_fill(anchors, allowed, iterations=600, tolerance=1e-5)
delta = corrected-h
if np.any(~np.isfinite(corrected[allowed])) or np.max(delta[repair]) > .05 or np.min(delta[repair]) < -1.0:
    raise RuntimeError('Local repair left invalid heights or exceeded conservative bounds')
newobs = observed & ~repair
distance = distance_transform_edt(~newobs)*.5
x,y,fine,mask = fine_surface(corrected, allowed, np.array([x0,y0]), .5, .1)
if not np.array_equal(mask,s['permitted']) or not np.allclose(x,s['x']) or not np.allclose(y,s['y']):
    raise RuntimeError('Footprint/frame changed')
unchanged = np.repeat(np.repeat(~binary_dilation(repair,structure=np.ones((3,3),bool)),5,axis=0),5,axis=1) & mask
outside_max = float(np.max(np.abs(fine[unchanged]-s['height'][unchanged])))
if outside_max > 1e-4:
    dy, dx = np.unravel_index(np.nanargmax(np.where(unchanged,np.abs(fine-s['height']),np.nan)),fine.shape)
    coarse_dy,coarse_dx = np.unravel_index(np.nanargmax(np.where(~repair,np.abs(delta),np.nan)),h.shape)
    raise RuntimeError(f'Height changed outside local area: {outside_max} at fine XY {x[dx]},{y[dy]}; coarse outside max {delta[coarse_dy,coarse_dx]} at XY {cx[coarse_dx]},{cy[coarse_dy]}')
vertices,faces = build_mesh(x,y,fine,mask)
out.mkdir(parents=True)
write_mesh_ply(out/'ground_surface_mesh.ply',vertices,faces)
np.savez_compressed(out/'ground_surface.npz',x=x,y=y,height=fine.astype('<f4'),permitted=mask,
    observed_coarse=newobs,support_distance_m=distance.astype('<f4'),
    coarse_height=corrected.astype('<f4'),coarse_allowed=allowed,coarse_excluded=s['coarse_excluded'])
report=dict(source=str(source),status='local_parking_bump_repair_candidate',
    method='positive isolated coarse-height components over local 3.5 m median; two-cell neighbourhood harmonic fill',
    parking_search_xy_m=[-82,-16,64,140],component_threshold_m=.15,selected_components=records,
    selected_core_cells=int(selected.sum()),repaired_coarse_cells=int(repair.sum()),
    changed_vertex_count=int(np.count_nonzero(np.abs(fine-s['height'])>1e-5)),
    maximum_height_lowering_m=float(-np.min(delta[repair])),maximum_height_raising_m=float(np.max(delta[repair])),
    maximum_change_outside_local_area_m=outside_max,
    footprint_unchanged=True,vertices=len(vertices),triangles=len(faces),harmonic_residual_m=resid,
    limits='Image does not provide an XY picked point; targets are spatial/height candidates and need visual review in the viewer.')
(out/'repair_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
