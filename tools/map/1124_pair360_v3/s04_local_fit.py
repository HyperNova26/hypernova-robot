"""Step 4. Local correction after the rigid fit: per-tile x/y/z offsets that bend pc_v1 onto pc_v2.

pc_v2 is the more precise capture, so it stays rigid; pc_v1 (used only where pc_v2 has no data) is
moved so the two meet without steps. Each 20 m window (10 m stride) gets a translation-only
point-to-plane ICP; x/y are kept only where vertical surfaces constrain them. Offsets are smoothed,
held-out windows (20%) check the prediction, and the field fades to zero 30 m beyond the overlap.

In : data/raw/pc_v*.*, work/02_<pc>_labels.npy, work/03_register.json
Out: work/04_local_fit.npz (grid offsets), work/04_local_fit.json (tiles before/after, holdout),
     work/04_local_fit.png (evidence: offsets after the rigid fit vs after this correction)
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from config import GROUND, OBSTACLE, PC, work
from pcio import load_json, read_xyzi, save_json, transform

WINDOW, STRIDE, FADE_M = 20.0, 10.0, 30.0
MAX_SHIFT_M = 1.0   # a window needing more than this after the rigid fit is a failed fit, not a warp


def static_map(key):
    labels = np.load(work(f"02_{key}_labels.npy"))
    xyz = np.asarray(read_xyzi(PC[key])[:, :3], float)
    if key == "pc_v2":
        xyz = transform(xyz, load_json(work("03_register.json"))["pc_v2_to_map"])
    xyz = xyz[np.isin(labels, (GROUND, OBSTACLE))]
    cell = np.floor(xyz/.1).astype(np.int64)
    cell -= cell.min(axis=0)
    key_ = (cell[:, 0]*(cell[:, 1].max()+1)+cell[:, 1])*(cell[:, 2].max()+1)+cell[:, 2]
    return xyz[np.unique(key_, return_index=True)[1]]


def tile_offset(moving, fixed):
    """Translation that moves `moving` onto `fixed` (point-to-plane), its xy conditioning and residual."""
    tree = cKDTree(fixed)
    _, nb = tree.query(fixed, k=12, workers=-1)
    x = fixed[nb]-fixed[nb].mean(1, keepdims=True)
    w, v = np.linalg.eigh(x.transpose(0, 2, 1) @ x)
    nrm, flat = v[:, :, 0], w[:, 0] < .2*w[:, 1]
    t = np.zeros(3)
    A, r, used = np.eye(3), np.zeros(1), 0
    for lim in (1.0, .7, .5, .35, .25, .25, .25, .25):
        d, i = tree.query(moving+t, distance_upper_bound=lim, workers=-1)
        ok = np.isfinite(d)
        ok[ok] &= flat[i[ok]]
        i = i[ok]
        if len(i) < 500:
            return None
        n = nrm[i]
        r = ((moving[ok]+t-fixed[i])*n).sum(1)
        A = n.T @ n
        t -= np.linalg.solve(A+1e-6*np.eye(3), n.T @ r)
        used = len(i)
    return t, float(np.linalg.eigvalsh(A[:2, :2]).min()/used), float(np.median(np.abs(r))), used


def smooth_field(values, known, sigma=1.0):
    w = ndimage.gaussian_filter(known.astype(float), sigma)
    s = ndimage.gaussian_filter(np.where(known, values, 0), sigma)/np.maximum(w, 1e-6)
    idx = ndimage.distance_transform_edt(w < .05, return_distances=False, return_indices=True)
    return np.where(w >= .05, s, s[tuple(idx)])


def measure(v1, v2, grid=None):
    """Offset that moves pc_v1 onto pc_v2 in every 20 m window holding both clouds."""
    t1, t2 = cKDTree(v1[:, :2]), cKDTree(v2[:, :2])
    if grid is None:
        lo = np.floor(np.minimum(v1.min(0), v2.min(0))[:2]/STRIDE)*STRIDE
        hi = np.ceil(np.maximum(v1.max(0), v2.max(0))[:2]/STRIDE)*STRIDE
        grid = (np.arange(lo[0], hi[0]+STRIDE, STRIDE), np.arange(lo[1], hi[1]+STRIDE, STRIDE))
    gx, gy = grid
    off = np.full((len(gy), len(gx), 3), np.nan)
    xy_ok = np.zeros((len(gy), len(gx)), bool)
    tiles = []
    for r, cy in enumerate(gy):
        for c, cx in enumerate(gx):
            a = v1[t1.query_ball_point([cx, cy], WINDOW/2, p=np.inf)]
            b = v2[t2.query_ball_point([cx, cy], WINDOW/2, p=np.inf)]
            if len(a) < 3000 or len(b) < 3000:
                continue
            fit = tile_offset(a, b)
            if fit is None:
                continue
            t, cond, resid, used = fit
            if np.abs(t).max() > MAX_SHIFT_M:
                # ICP slid along a featureless surface; its z is no more reliable than its x/y.
                tiles.append({"centre_xy": [float(cx), float(cy)], "offset_m": np.round(t, 3).tolist(), "rejected": True})
                continue
            off[r, c], xy_ok[r, c] = t, cond > .04
            tiles.append({"centre_xy": [float(cx), float(cy)], "offset_m": np.round(t, 3).tolist(),
                          "xy_constrained": bool(cond > .04), "residual_m": round(resid, 3), "pairs": used})
    return grid, off, xy_ok, tiles


def offsets_at(field, lo, xyz):
    g = [(xyz[:, 1]-lo[1])/STRIDE, (xyz[:, 0]-lo[0])/STRIDE]
    return np.stack([ndimage.map_coordinates(field[..., k], g, order=1, mode="nearest") for k in range(3)], -1)


def stats(off, xy_ok):
    m = np.isfinite(off[..., 2])
    dz, dxy = np.abs(off[m][:, 2]), np.linalg.norm(off[m & xy_ok][:, :2], axis=1)
    return {"windows": int(m.sum()), "abs_dz_median_p95_max_m": np.round([np.median(dz), np.percentile(dz, 95), dz.max()], 3).tolist(),
            "dxy_median_p95_max_m": np.round([np.median(dxy), np.percentile(dxy, 95), dxy.max()], 3).tolist()}


def main():
    v1, v2 = static_map("pc_v1"), static_map("pc_v2")
    (gx, gy), off, xy_ok, tiles = measure(v1, v2)
    lo = np.array([gx[0], gy[0]])
    shape = off.shape[:2]
    measured = np.isfinite(off[..., 2])
    held = measured & (np.random.default_rng(1117).random(shape) < .2)
    pred = np.stack([smooth_field(off[..., k], (measured & ~held) & (xy_ok if k < 2 else True)) for k in range(3)], -1)
    err = np.linalg.norm((pred-off)[held], axis=1)
    field = np.stack([smooth_field(off[..., k], measured & (xy_ok if k < 2 else True)) for k in range(3)], -1)
    # Fade to zero away from the overlap so distant pc_v1 is not dragged by a boundary offset.
    dist = ndimage.distance_transform_edt(~measured)*STRIDE
    field *= np.clip(1-dist/FADE_M, 0, 1)[..., None]
    np.savez_compressed(work("04_local_fit.npz"), origin_xy=lo, step_m=STRIDE, offset_m=field.astype("f4"),
                        measured=measured, xy_constrained=xy_ok, applies_to="pc_v1")
    # Evidence: measure the same windows again after bending pc_v1.
    _, after, after_ok, after_tiles = measure(v1+offsets_at(field, lo, v1), v2, (gx, gy))
    report = {"applies_to": "pc_v1 (pc_v2 stays rigid)", "window_m": WINDOW, "stride_m": STRIDE, "fade_m": FADE_M,
              "before_correction": stats(off, xy_ok), "after_correction": stats(after, after_ok),
              "holdout_windows": int(held.sum()),
              "holdout_prediction_error_median_max_m": [float(np.median(err)), float(err.max())] if len(err) else None,
              "tiles_before": tiles, "tiles_after": after_tiles}
    save_json(work("04_local_fit.json"), report)
    plot(gx, gy, off, xy_ok, after, after_ok, report)
    print("before", report["before_correction"], "after", report["after_correction"],
          "holdout error median/max", report["holdout_prediction_error_median_max_m"])


def plot(gx, gy, off, xy_ok, after, after_ok, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    X, Y = np.meshgrid(gx, gy)
    fig, ax = plt.subplots(2, 3, figsize=(22, 13))
    for row, (o, ok, name) in enumerate(((off, xy_ok, "after rigid fit (step 3)"), (after, after_ok, "after local fit (step 4)"))):
        m = np.isfinite(o[..., 2])
        sc = ax[row, 0].scatter(X[m], Y[m], c=-o[m][:, 2], cmap="RdBu_r", vmin=-.5, vmax=.5, s=90, marker="s")
        plt.colorbar(sc, ax=ax[row, 0], label="pc_v1 - pc_v2 height (m)")
        mm = m & ok
        q = ax[row, 1].quiver(X[mm], Y[mm], -o[mm][:, 0], -o[mm][:, 1], np.linalg.norm(o[mm][:, :2], axis=1),
                              angles="xy", scale_units="xy", scale=.025, cmap="viridis", clim=(0, .5))
        plt.colorbar(q, ax=ax[row, 1], label="pc_v1 offset from pc_v2 (m)")
        for a, t in zip(ax[row, :2], ("vertical", "horizontal (arrows x40)")):
            a.set_aspect("equal")
            a.set_title(f"{t}, {name}")
        st = report["before_correction" if row == 0 else "after_correction"]
        ax[row, 2].hist(np.abs(o[m][:, 2]), bins=np.arange(0, .61, .025), alpha=.7, label="|dz|")
        ax[row, 2].hist(np.linalg.norm(o[mm][:, :2], axis=1), bins=np.arange(0, .61, .025), alpha=.7, label="|dxy|")
        ax[row, 2].legend()
        ax[row, 2].set_xlabel("m")
        ax[row, 2].set_title(f"{name}: |dz| median {st['abs_dz_median_p95_max_m'][0]:.3f} / max {st['abs_dz_median_p95_max_m'][2]:.2f} m,"
                             f" |dxy| median {st['dxy_median_p95_max_m'][0]:.3f} / max {st['dxy_median_p95_max_m'][2]:.2f} m", fontsize=9)
    fig.suptitle("pc_v1 vs pc_v2 per 20 m window (10 m stride), pair360_map")
    fig.savefig(work("04_local_fit.png"), dpi=65, bbox_inches="tight")
    plt.close(fig)


def apply(xyz):
    """Offset pc_v1 points (map frame) by the smoothed field."""
    f = np.load(work("04_local_fit.npz"))
    g = [(xyz[:, 1]-f["origin_xy"][1])/f["step_m"], (xyz[:, 0]-f["origin_xy"][0])/f["step_m"]]
    return xyz+np.stack([ndimage.map_coordinates(f["offset_m"][..., k], g, order=1, mode="nearest") for k in range(3)], -1)


if __name__ == "__main__":
    main()
