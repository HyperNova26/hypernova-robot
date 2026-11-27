"""Align the two downloaded XYZI maps to measured S-004. All lengths are metres."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
from scipy import ndimage, signal
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
BASE = ROOT.parent / "ground_seperation/sim_scenes/S004_ground_final/input/original.ply"
DOWNLOADS = Path.home() / "Downloads"


# Point clouds by version: pc_v1 S-004 raw (11-04), pc_v2 Downloads/map_preview.pcd (11-11),
# pc_v3 map_preview (1).pcd (11-15), moved to input/ and renamed on 11-16 with sha256 unchanged.
# output/frame.json and manifest.json (map_v1 dashboard contract) still use the old keys.
FRAME_KEY = {"pc_v1": "s004", "pc_v2": "old", "pc_v3": "new"}


def sources(downloads=DOWNLOADS):
    return {"pc_v1": BASE, "pc_v2": downloads / "map_preview.pcd", "pc_v3": ROOT / "input/pc_v3_20261115.pcd"}


def read_points(path):
    with path.open("rb") as f:
        lines = []
        for _ in range(64):
            line = f.readline(512).decode("ascii").strip()
            lines.append(line)
            if line in ("end_header", "DATA binary"):
                break
        else:
            raise ValueError(f"Unrecognized point header: {path}")
        if lines[-1] == "end_header":
            assert "format binary_little_endian 1.0" in lines
            assert [v for v in lines if v.startswith("property ")] == [
                "property float x", "property float y", "property float z", "property float scalar_intensity"]
            count = int(next(x for x in lines if x.startswith("element vertex ")).split()[-1])
        else:
            assert "FIELDS x y z intensity" in lines and "TYPE F F F F" in lines and "SIZE 4 4 4 4" in lines
            count = int(next(x for x in lines if x.startswith("POINTS ")).split()[-1])
        offset = f.tell()
    assert path.stat().st_size == offset + 16 * count
    return np.memmap(path, mode="r", offset=offset, dtype="<f4", shape=(count, 4))


def transform(points, matrix):
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def vox(points, size):
    # A real measurement represents each occupied voxel.
    cell = np.floor(points / size).astype(np.int64)
    cell -= cell.min(axis=0)
    key = (cell[:, 0] * (cell[:, 1].max()+1) + cell[:, 1]) * (cell[:, 2].max()+1) + cell[:, 2]
    return points[np.unique(key, return_index=True)[1]]


def train_mask(xyz):
    tile = np.floor(xyz[:, :2] / 10).astype(int)
    return (tile[:, 0] + 2 * tile[:, 1]) % 5 != 0


def raster(points, step):
    cells = np.floor(points[:, :2] / step).astype(int)
    origin = cells.min(axis=0)
    cells -= origin
    shape = tuple(cells.max(axis=0)+1)
    ids = cells[:, 0] * shape[1] + cells[:, 1]
    count = np.bincount(ids, minlength=np.prod(shape))
    top, bottom = np.full(len(count), -np.inf), np.full(len(count), np.inf)
    np.maximum.at(top, ids, points[:, 2])
    np.minimum.at(bottom, ids, points[:, 2])
    valid = count > 1
    relief = np.zeros(len(count), dtype=np.float32)
    relief[valid] = np.clip(top[valid]-bottom[valid], 0, 6)
    return relief.reshape(shape), origin


def yaw_rotation(degrees):
    return Rotation.from_euler("z", degrees, degrees=True).as_matrix()


def coarse(target, src, step=1.0):
    # Correlate high-frequency vertical relief over yaw and horizontal translation.
    def feature(r):
        return ndimage.gaussian_filter(r, .7) - ndimage.gaussian_filter(r, 3)
    fixed, base = raster(target, step)
    fixed = feature(fixed)
    candidates = []
    for deg in range(-180, 180, 2):
        rotated = src @ yaw_rotation(deg).T
        moving, origin = raster(rotated, step)
        moving = feature(moving)
        corr = signal.fftconvolve(fixed, moving[::-1, ::-1], mode="full")
        index = np.array(np.unravel_index(np.argmax(corr), corr.shape))
        shift = base - origin + index - np.array(moving.shape) + 1
        candidates.append((float(corr[tuple(index)] / np.linalg.norm(moving)), deg, (shift * step).tolist()))
    return sorted(candidates, reverse=True)


def estimate_height(target, moved):
    # Bin XY elevations independently; the modal height shift survives local occlusion.
    size = 1.0
    def low(points):
        cells = np.floor(points[:, :2]/size).astype(int)
        keys = (cells[:, 0]+10000)*30000 + cells[:, 1]+10000
        ids, inv = np.unique(keys, return_inverse=True)
        minima = np.full(len(ids), np.inf)
        np.minimum.at(minima, inv, points[:, 2])
        return ids, minima
    a, h = low(target)
    b, j = low(moved)
    _, i, k = np.intersect1d(a, b, return_indices=True)
    delta = h[i]-j[k]
    return float(np.median(delta))


def refine(src, target, matrix):
    for size, limit, steps in [(.9, 3.0, 28), (.45, 1.2, 22), (.24, .60, 20), (.14, .32, 16)]:
        fixed = vox(target, size)
        cloud = vox(src, size)
        if len(cloud) > 95000:
            cloud = cloud[np.random.default_rng(10).choice(len(cloud), 95000, replace=False)]
        tree = cKDTree(fixed)
        _, nb = tree.query(fixed, k=10, workers=3)
        normals = np.empty_like(fixed)
        planar = np.empty(len(fixed), dtype=bool)
        for start in range(0, len(fixed), 50000):
            section = slice(start, start+50000)
            x = fixed[nb[section]]
            x -= x.mean(axis=1, keepdims=True)
            w, v = np.linalg.eigh(x.transpose(0, 2, 1) @ x)
            normals[section] = v[:, :, 0]
            planar[section] = (w[:, 0] < .35 * w[:, 1])
        for _ in range(steps):
            moved = transform(cloud, matrix)
            dist, idx = tree.query(moved, workers=3)
            keep = (dist < limit) & planar[idx] & train_mask(moved)
            if keep.sum() < 100:
                raise ValueError("Insufficient plane correspondences")
            points, match, norm = moved[keep], fixed[idx[keep]], normals[idx[keep]]
            center = np.mean(points, axis=0)
            residual = np.einsum("ij,ij->i", norm, match-points)
            weight = np.minimum(1, (size*.45) / np.maximum(np.abs(residual), 1e-8))**.5
            design = np.column_stack((np.cross(points-center, norm), norm))
            pars = np.linalg.lstsq(design*weight[:, None], residual*weight, rcond=None)[0]
            rot = Rotation.from_rotvec(pars[:3]).as_matrix()
            update = np.eye(4)
            update[:3, :3], update[:3, 3] = rot, center - rot @ center + pars[3:]
            matrix = update @ matrix
            if np.linalg.norm(pars[:3]) < 1e-5 and np.linalg.norm(pars[3:]) < .00035:
                break
    return matrix


def evaluate(src, target, matrix):
    xyz = transform(vox(src, .22), matrix)
    xyz = xyz[~train_mask(xyz)]
    tree = cKDTree(target)
    distances, _ = tree.query(xyz, workers=3)
    tiles = np.floor(xyz[:, :2]/10).astype(int)
    rows = []
    for tile in np.unique(tiles, axis=0):
        mask = np.all(tiles == tile, axis=1)
        d = distances[mask]
        if len(d) >= 40:
            rows.append({"tile_xy":tile.tolist(),"points":len(d),"within_25cm":round(float(np.mean(d<=.25)),4),
                         "median_m":round(float(np.median(d)),3),"p95_m":round(float(np.quantile(d,.95)),3)})
    return rows


def overview(clouds, matrices, path):
    transformed = [transform(x[::max(1,len(x)//60000)], matrices[k]) for k,x in clouds.items()]
    low = np.min([p[:, :2].min(axis=0) for p in transformed], axis=0)
    high = np.max([p[:, :2].max(axis=0) for p in transformed], axis=0)
    scale = min(880/max(high[0]-low[0],1), 710/max(high[1]-low[1],1))
    canvas = Image.new("RGB",(940,790),"#101a20")
    draw = ImageDraw.Draw(canvas)
    for points,color in zip(transformed,("#76929a","#e4bb58","#5bd3cd")):
        xy = (points[:, :2]-low)*scale
        draw.point([(int(i)+32, 740-int(j)) for i,j in xy],fill=color)
    draw.text((14,12),"S004 grey   /   Nov 11 gold   /   Nov 15 cyan      |      top view, +Y up",fill="white")
    draw.line((32,765,32+int(20*scale),765), fill="white", width=2)
    draw.text((32+int(20*scale)+5,757),"20 m",fill="white")
    canvas.save(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--downloads", type=Path, default=DOWNLOADS)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inputs = sources(args.downloads)
    maps = {k:read_points(p) for k,p in inputs.items()}
    clouds = {k: np.ascontiguousarray(v[::4, :3]) for k,v in maps.items()}
    metrics = {}
    matrices = {"pc_v1": np.eye(4)}
    for k in ("pc_v2","pc_v3"):
        fixed = clouds["pc_v1"]
        train = fixed[train_mask(fixed)]
        fit_source = clouds[k]
        candidates = coarse(train[::3], fit_source[::2])
        print(k, "initial candidates", candidates[:5], flush=True)
        _, deg, xy = candidates[0]
        matrix = np.eye(4)
        matrix[:3, :3], matrix[:2, 3] = yaw_rotation(deg), xy
        matrix[2,3] = estimate_height(train, transform(fit_source, matrix))
        matrix = refine(fit_source, train, matrix)
        matrices[k] = matrix
        metrics[k] = {"initial_candidates":candidates[:5], "holdout_tiles":evaluate(fit_source, maps["pc_v1"][:, :3],matrix)}
        print(k, "matrix", matrix.tolist(), flush=True)
        (OUTPUT/f"registration_{k}.json").write_text(json.dumps({"transform":matrix.tolist(),**metrics[k]},indent=2))
    overview(clouds, matrices, OUTPUT/"registration-overview.png")
    record = {"frame":"pair360_map","basis":"local S-004 raw XYZ; metres, Z-up", "transform_direction":"p_map = R @ p_input + t",
              "M002_team_origin":"unconfirmed","source_to_map":{k:m.tolist() for k,m in matrices.items()},
              "source_sha256":{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in inputs.items()}}
    (OUTPUT/"frame.json").write_text(json.dumps(record,indent=2))


if __name__ == "__main__":
    main()
