"""Single-cloud geometry used before registration: local floor height, car-sized clusters, isolated returns.

Ported from the S-004 classify.py (floor_model, bounded_clusters); vehicles are now returned as instances.
"""
import numpy as np
from matplotlib.path import Path as Polygon
from scipy import ndimage as ndi


def cell_quantile(ids, val, size, q):
    order = np.lexsort((val, ids))
    bins, start, n = np.unique(ids[order], return_index=True, return_counts=True)
    result = np.full(size, np.nan, np.float32)
    result[bins] = val[order[start+((n-1)*q).astype(int)]]
    return result


def floor_model(xyz, cell=0.6):
    """Height above a smoothed low envelope (hag) and whether the local floor is gentle (smooth)."""
    base = np.floor(xyz[:, :2].min(axis=0)/cell)*cell
    ij = np.floor((xyz[:, :2]-base)/cell).astype(np.int32)
    nx, ny = ij.max(axis=0)+1
    ids = ij[:, 1]*nx+ij[:, 0]
    floor = cell_quantile(ids, xyz[:, 2], nx*ny, .08).reshape(ny, nx)
    valid = np.isfinite(floor)
    floor = floor[tuple(ndi.distance_transform_edt(~valid, return_distances=False, return_indices=True))]
    floor = ndi.median_filter(floor, size=3)
    # Grey openings remove car roofs; poorly supported terraces stay out of the floor.
    for radius in (2, 5, 10, 18):
        opening = ndi.grey_opening(floor, size=2*radius+1)
        high = floor-opening > .16+.13*radius*cell
        if high.any() and (~high).any():
            nearest = ndi.distance_transform_edt(high, return_distances=False, return_indices=True)
            floor[high] = floor[tuple(nearest[:, high])]
    floor = ndi.gaussian_filter(floor, .8)
    gy, gx = np.gradient(floor, cell)
    smooth = np.hypot(gx, gy) < .38
    hag = xyz[:, 2]-ndi.map_coordinates(floor, [(xyz[:, 1]-base[1])/cell-.5, (xyz[:, 0]-base[0])/cell-.5],
                                         order=1, mode="nearest")
    return hag, smooth.ravel()[ids]


# Vehicle footprint limits (m). Single car: compact 1.6 x 3.6 to large van/SUV 2.0 x 5.3, with the
# 0.25 m grid and mirrors adding up to ~0.6 m. Parked rows come out as one long component: a row of
# cars nose-to-tail is car-width wide (split every 4.7 m), a row of cars side by side is car-length
# wide (split every 2.5 m, one stall), and two such rows parked back to back are split down the middle.
CAR_WIDTH, CAR_LENGTH = (1.15, 2.8), (2.8, 6.2)
INLINE_PITCH, STALL_PITCH, SIDE_ROW_WIDTH = 4.7, 2.5, (3.5, 6.2)   # two side-by-side rows back to back: up to 12.4
ROW_MAX_LENGTH = 60.0
MIN_FILL, MAX_HIGH_SHARE, MIN_PRESENCE = .36, .02, 12
MIN_BODY_COVER, RING_M, MIN_RING_GROUND = .30, 1.0, .40
BODY_RETURNS = {"pc_v1": 2, "pc_v2": 1}   # per 0.25 m cell; pc_v2 has half the density of pc_v1


def vehicle_instances(xyz, hag, ground, body_returns=2, cell=.25):
    """Car-sized footprints in the 0.5-1.75 m band, one id per vehicle (0 = none).

    Footprints come from the body band (>= body_returns at 1.0-1.75 m per 0.25 m cell); cells under
    anything higher than 2.45 m (tree crowns, roofs) are cut out first, so a car is not joined to the
    tree next to it. A vehicle (or each piece of a parked row) is 1.15-2.8 m wide and
    2.8-6.2 m long, at least 36% filled, has >= 12 returns at 1.0-1.75 m, its 1.0-1.75 m body covers
    >= 30% of the footprint (rules out poles, carts, scattered shrub returns) and >= 40% of a 1 m ring
    around it shows ground (a car stands on a road; hedges in planting or railings on slopes do not).
    Returns per-point ids and one record per vehicle with centre, size and heading.
    """
    base = xyz[:, :2].min(axis=0)
    ij = np.floor((xyz[:, :2]-base)/cell).astype(np.int32)
    nx, ny = ij.max(axis=0)+1
    ids = ij[:, 1]*nx+ij[:, 0]
    shape = (ny, nx)

    def counts(mask):
        return np.bincount(ids[mask], minlength=nx*ny).reshape(shape)
    high, presence, floor = counts(hag > 2.45), counts((hag > 1.0) & (hag < 1.75)), counts(ground) > 0
    canopy = ndi.binary_dilation(high > 0)
    # Footprints from the body band (>= body_returns at 1.0-1.75 m): lower down, mirrors and bumpers of
    # cars parked close together touch and merge whole lots into one component.
    band = (presence >= body_returns) & ~canopy
    comps, _ = ndi.label(band, structure=np.ones((3, 3), bool))
    reach = int(round(RING_M/cell))
    cell_id = np.zeros(shape, np.int32)
    found = []
    for k, sl in enumerate(ndi.find_objects(comps), 1):
        if sl is None:
            continue
        comp = comps[sl] == k
        rc = np.argwhere(comp)+[sl[0].start, sl[1].start]     # grid (row, col)
        if len(rc) < 3:
            continue
        xy = rc[:, ::-1]*cell
        centre = xy.mean(axis=0)
        _, axes = np.linalg.eigh(np.cov(xy, rowvar=False))
        proj = (xy-centre) @ axes
        ext = np.ptp(proj, axis=0)+cell
        long_axis = int(np.argmax(ext))
        length, width = ext[long_axis], ext[1-long_axis]
        if length > ROW_MAX_LENGTH:
            continue
        if CAR_WIDTH[0] <= width <= CAR_WIDTH[1]:          # one car, or cars nose to tail
            pieces = 1 if length <= CAR_LENGTH[1] else int(round(length/INLINE_PITCH))
            if length < CAR_LENGTH[0]:
                continue
            car_len, car_wid, turn, kind = length/pieces, width, 0.0, "nose-to-tail row"
        elif SIDE_ROW_WIDTH[0] <= width <= 2*SIDE_ROW_WIDTH[1] and length >= CAR_WIDTH[0]*2:   # cars side by side
            rows = 1 if width <= SIDE_ROW_WIDTH[1] else 2
            pieces = max(1, int(round(length/STALL_PITCH)))
            car_len, car_wid, turn, kind = width/rows, length/pieces, 90.0, f"side-by-side rows x{rows}"
        else:
            continue
        if not kind.startswith("side"):
            rows = 1
        if (len(rc)*cell**2/(width*length) <= MIN_FILL or high[sl][comp].sum() > max(2, MAX_HIGH_SHARE*len(rc))
                or presence[sl][comp].sum() < MIN_PRESENCE*pieces*rows
                or (presence[sl][comp] > 0).mean() < MIN_BODY_COVER):
            continue
        win = tuple(slice(max(0, d.start-reach), d.stop+reach) for d in sl)
        inside = comps[win] == k
        ring = ndi.binary_dilation(inside, iterations=reach) & ~inside
        if floor[win][ring].mean() < MIN_RING_GROUND:
            continue
        a = np.clip(((proj[:, long_axis]-proj[:, long_axis].min())/(length/pieces)).astype(int), 0, pieces-1)
        b = np.clip(((proj[:, 1-long_axis]-proj[:, 1-long_axis].min())/(width/rows)).astype(int), 0, rows-1)
        a = a*rows+b
        yaw = float(np.degrees(np.arctan2(axes[1, long_axis], axes[0, long_axis])))+turn
        for piece in range(pieces*rows):
            m = a == piece
            if m.sum() < .3*car_len*car_wid/cell**2:
                continue
            cell_id[rc[m, 0], rc[m, 1]] = len(found)+1
            found.append({"id": len(found)+1, "centre_xy": (base+xy[m].mean(axis=0)+cell/2).round(2).tolist(),
                          "yaw_deg": round(yaw, 1), "length_m": round(float(car_len), 2), "width_m": round(float(car_wid), 2),
                          "source": "detector" if pieces*rows == 1 else f"detector, {kind} of {pieces}"})
    # Grow each car by one cell (0.25 m) so its doors, mirrors and bumpers go with it.
    grown = ndi.grey_dilation(cell_id, size=3)
    cell_id = np.where(cell_id > 0, cell_id, grown)
    point_id = cell_id[ij[:, 1], ij[:, 0]]
    point_id[(hag <= .15) | (hag >= 2.5)] = 0
    return point_id, found


def polygon_instances(xyz, hag, polygons, start_id):
    """Reviewed vehicle polygons (pc_v1): returns 0.13-4.1 m above floor inside each polygon."""
    point_id = np.zeros(len(xyz), np.int32)
    found = []
    for k, item in enumerate(polygons):
        poly = np.asarray(item["polygon_xy"])
        box = np.flatnonzero(np.all((xyz[:, :2] >= poly.min(axis=0)) & (xyz[:, :2] <= poly.max(axis=0)), axis=1))
        inside = box[Polygon(poly).contains_points(xyz[box, :2], radius=1e-7)]
        if "z_bounds" in item:
            lo, hi = item["z_bounds"]
            inside = inside[(xyz[inside, 2] >= lo) & (xyz[inside, 2] <= hi)]
        inside = inside[(hag[inside] > .13) & (hag[inside] < 4.1)]
        point_id[inside] = start_id+k
        found.append({"id": start_id+k, "centre_xy": poly.mean(axis=0).round(2).tolist(), "points": int(len(inside)),
                      "polygon_xy": poly.round(2).tolist(), "source": f"reviewed polygon {item['id']}"})
    return point_id, found


def isolated(xyz, size=.26):
    """Returns alone in their voxel with no occupied neighbour voxel (26-neighbourhood)."""
    cell = np.floor(xyz/size).astype(np.int64)
    cell -= cell.min(axis=0)-1
    dims = cell.max(axis=0)+2
    key = (cell[:, 0]*dims[1]+cell[:, 1])*dims[2]+cell[:, 2]
    occupied, inverse, count = np.unique(key, return_inverse=True, return_counts=True)
    neighbours = np.zeros(len(occupied), np.int32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == dy == dz == 0:
                    continue
                probe = occupied+(dx*dims[1]+dy)*dims[2]+dz
                pos = np.clip(np.searchsorted(occupied, probe), 0, len(occupied)-1)
                neighbours += occupied[pos] == probe
    return ((count == 1) & (neighbours == 0))[inverse.ravel()]
