"""Step 3. Rigid registration of pc_v2 to pc_v1 on static returns (ground + obstacles, no vehicles or noise).

Coarse: 1 m relief rasters (max-min z), band-pass, yaw search every 2 deg with FFT cross-correlation;
z from the median of per-1 m-cell floor differences. Fine: multi-scale robust point-to-plane ICP on
80% of the 10 m tiles. The other 20% are scored, only where both clouds have returns.

In : data/raw/pc_v*.*, work/02_<pc>_labels.npy
Out: work/03_register.json (4x4 pc_v2 -> pair360_map, candidates, holdout tiles), work/03_register_overview.png
"""
import numpy as np
from scipy import ndimage, signal
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from config import GROUND, OBSTACLE, PC, work
from pcio import read_xyzi, save_json, sha256, transform


def vox(points, size):
    cell = np.floor(points/size).astype(np.int64)
    cell -= cell.min(axis=0)
    key = (cell[:, 0]*(cell[:, 1].max()+1)+cell[:, 1])*(cell[:, 2].max()+1)+cell[:, 2]
    return points[np.unique(key, return_index=True)[1]]


def train_mask(xyz):
    tile = np.floor(xyz[:, :2]/10).astype(int)
    return (tile[:, 0]+2*tile[:, 1]) % 5 != 0


def raster(points, step):
    cells = np.floor(points[:, :2]/step).astype(int)
    origin = cells.min(axis=0)
    cells -= origin
    shape = tuple(cells.max(axis=0)+1)
    ids = cells[:, 0]*shape[1]+cells[:, 1]
    count = np.bincount(ids, minlength=np.prod(shape))
    top, bottom = np.full(len(count), -np.inf), np.full(len(count), np.inf)
    np.maximum.at(top, ids, points[:, 2])
    np.minimum.at(bottom, ids, points[:, 2])
    valid = count > 1
    relief = np.zeros(len(count), np.float32)
    relief[valid] = np.clip(top[valid]-bottom[valid], 0, 6)
    return relief.reshape(shape), origin


def yaw_rotation(degrees):
    return Rotation.from_euler("z", degrees, degrees=True).as_matrix()


def coarse(target, src, step=1.0):
    def feature(r):
        return ndimage.gaussian_filter(r, .7)-ndimage.gaussian_filter(r, 3)
    fixed, base = raster(target, step)
    fixed = feature(fixed)
    candidates = []
    for deg in range(-180, 180, 2):
        moving, origin = raster(src @ yaw_rotation(deg).T, step)
        moving = feature(moving)
        corr = signal.fftconvolve(fixed, moving[::-1, ::-1], mode="full")
        index = np.array(np.unravel_index(np.argmax(corr), corr.shape))
        shift = base-origin+index-np.array(moving.shape)+1
        candidates.append((float(corr[tuple(index)]/np.linalg.norm(moving)), deg, (shift*step).tolist()))
    return sorted(candidates, reverse=True)


def estimate_height(target, moved, size=1.0):
    def low(points):
        cells = np.floor(points[:, :2]/size).astype(int)
        keys = (cells[:, 0]+10000)*30000+cells[:, 1]+10000
        ids, inv = np.unique(keys, return_inverse=True)
        minima = np.full(len(ids), np.inf)
        np.minimum.at(minima, inv, points[:, 2])
        return ids, minima
    a, h = low(target)
    b, j = low(moved)
    _, i, k = np.intersect1d(a, b, return_indices=True)
    return float(np.median(h[i]-j[k]))


def refine(src, target, matrix):
    for size, limit, steps in [(.9, 3.0, 28), (.45, 1.2, 22), (.24, .60, 20), (.14, .32, 16)]:
        fixed, cloud = vox(target, size), vox(src, size)
        if len(cloud) > 95000:
            cloud = cloud[np.random.default_rng(10).choice(len(cloud), 95000, replace=False)]
        tree = cKDTree(fixed)
        _, nb = tree.query(fixed, k=10, workers=-1)
        normals, planar = np.empty_like(fixed), np.empty(len(fixed), bool)
        for start in range(0, len(fixed), 50000):
            section = slice(start, start+50000)
            x = fixed[nb[section]]
            x -= x.mean(axis=1, keepdims=True)
            w, v = np.linalg.eigh(x.transpose(0, 2, 1) @ x)
            normals[section], planar[section] = v[:, :, 0], w[:, 0] < .35*w[:, 1]
        for _ in range(steps):
            moved = transform(cloud, matrix)
            dist, idx = tree.query(moved, workers=-1)
            keep = (dist < limit) & planar[idx] & train_mask(moved)
            if keep.sum() < 100:
                raise ValueError("Insufficient plane correspondences")
            points, match, norm = moved[keep], fixed[idx[keep]], normals[idx[keep]]
            center = points.mean(axis=0)
            residual = np.einsum("ij,ij->i", norm, match-points)
            weight = np.minimum(1, (size*.45)/np.maximum(np.abs(residual), 1e-8))**.5
            design = np.column_stack((np.cross(points-center, norm), norm))
            pars = np.linalg.lstsq(design*weight[:, None], residual*weight, rcond=None)[0]
            rot = Rotation.from_rotvec(pars[:3]).as_matrix()
            update = np.eye(4)
            update[:3, :3], update[:3, 3] = rot, center-rot @ center+pars[3:]
            matrix = update @ matrix
            if np.linalg.norm(pars[:3]) < 1e-5 and np.linalg.norm(pars[3:]) < .00035:
                break
    return matrix


def evaluate(src, target, matrix):
    """Holdout tiles only, and only where pc_v1 also has returns within 1 m (overlap, not coverage gaps)."""
    xyz = transform(vox(src, .22), matrix)
    xyz = xyz[~train_mask(xyz)]
    d, _ = cKDTree(target).query(xyz, workers=-1)
    support = cKDTree(target[:, :2]).query(xyz[:, :2], workers=-1)[0] < 1.0
    xyz, d = xyz[support], d[support]
    tiles = np.floor(xyz[:, :2]/10).astype(int)
    rows = []
    for tile in np.unique(tiles, axis=0):
        dt = d[np.all(tiles == tile, axis=1)]
        if len(dt) >= 40:
            rows.append({"tile_xy": tile.tolist(), "points": len(dt), "within_25cm": round(float(np.mean(dt <= .25)), 4),
                         "median_m": round(float(np.median(dt)), 3), "p95_m": round(float(np.quantile(dt, .95)), 3)})
    return rows


def overview(target, moved, holdout, path):
    """Evidence: overlay of both clouds, and held-out 10 m tiles coloured by median distance to pc_v1."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(24, 8))
    ax[0].scatter(target[::40, 0], target[::40, 1], s=.2, c="grey", label="pc_v1")
    ax[0].scatter(moved[::10, 0], moved[::10, 1], s=.2, c="tab:cyan", label="pc_v2 registered")
    ax[0].legend(markerscale=20)
    ax[0].set_title("overlay after rigid fit")
    xy = np.array([np.array(t["tile_xy"])*10+5 for t in holdout])
    med = np.array([t["median_m"] for t in holdout])
    sc = ax[1].scatter(xy[:, 0], xy[:, 1], c=med, cmap="magma_r", vmin=0, vmax=.5, s=260, marker="s")
    for (x, y), m in zip(xy, med):
        ax[1].text(x, y, f"{m:.2f}", ha="center", va="center", fontsize=6, color="w" if m > .25 else "k")
    plt.colorbar(sc, ax=ax[1], label="median distance pc_v2 -> pc_v1 (m)")
    ax[1].set_title("held-out tiles (not used by ICP), overlap only")
    within = np.array([t["within_25cm"] for t in holdout])
    ax[2].hist(med, bins=np.arange(0, 1.01, .025))
    ax[2].set_xlabel("tile median distance (m)")
    ax[2].set_title(f"{len(med)} tiles: median {np.median(med):.3f} m, within 25 cm {np.median(within):.0%} (tile median)")
    for a in ax[:2]:
        a.set_aspect("equal")
    fig.savefig(path, dpi=65, bbox_inches="tight")
    plt.close(fig)


def static(key, stride):
    labels = np.load(work(f"02_{key}_labels.npy"))
    xyz = np.asarray(read_xyzi(PC[key])[:, :3], float)
    keep = np.isin(labels, (GROUND, OBSTACLE))
    return np.ascontiguousarray(xyz[keep][::stride])


def main():
    target, src = static("pc_v1", 4), static("pc_v2", 4)
    train = target[train_mask(target)]
    candidates = coarse(train[::3], src[::2])
    _, deg, xy = candidates[0]
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:2, 3] = yaw_rotation(deg), xy
    matrix[2, 3] = estimate_height(train, transform(src, matrix))
    matrix = refine(src, train, matrix)
    holdout = evaluate(src, target, matrix)
    pts = np.array([t["points"] for t in holdout])
    within = np.array([t["within_25cm"] for t in holdout])
    report = {"frame": "pair360_map", "basis": "pc_v1 raw XYZ, metres, Z up", "direction": "p_map = R @ p_pc_v2 + t",
              "pc_v2_to_map": matrix.tolist(), "pc_v1_to_map": np.eye(4).tolist(),
              "euler_zyx_deg": Rotation.from_matrix(matrix[:3, :3]).as_euler("zyx", degrees=True).round(3).tolist(),
              "sha256": {k: sha256(p) for k, p in PC.items()}, "coarse_candidates": candidates[:5],
              "holdout_overlap_tiles": holdout, "holdout_within_25cm": float((within*pts).sum()/pts.sum())}
    save_json(work("03_register.json"), report)
    overview(target, transform(src, matrix), holdout, work("03_register_overview.png"))
    print("yaw/pitch/roll", report["euler_zyx_deg"], "t", np.round(matrix[:3, 3], 2), "holdout within 25 cm",
          round(report["holdout_within_25cm"], 3))


if __name__ == "__main__":
    main()
