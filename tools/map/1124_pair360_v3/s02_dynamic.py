"""Step 2. Per cloud, before registration: ground, vehicles (one id per car), isolated noise. Rows are never moved.

pc_v1 ground comes from the reviewed pc_v1 ground v1 partition (S-004 "v9"); pc_v1 vehicles add the 32 reviewed polygons.
pc_v2 ground and vehicles come from the floor model and the car-size detector.

In : data/raw/pc_v*.{ply,pcd}, data/reviewed/pc_v1_ground_v1_partition/ground.ply,
     tools/map/1109_s004_ground/continuous_ground_20261109_v9.json
Out: work/02_<pc>_labels.npy (uint8 per source row: 1 ground, 2 obstacle, 5 vehicle, 6 noise),
     work/02_<pc>_hag.npy (float16 height above local floor), work/02_<pc>_vehicles.json,
     work/02_<pc>_vehicles.png (one thumbnail per vehicle for review)
"""
import numpy as np

from config import GROUND, GROUND_V1_DECISIONS, GROUND_V1_PARTITION, NOISE, OBSTACLE, PC, VEHICLE, work
from features import BODY_RETURNS, floor_model, isolated, polygon_instances, vehicle_instances
from pcio import load_json, read_xyzi, save_json


def ply_column(path, name):
    """One property of a binary little-endian PLY vertex element."""
    types = {"float": "<f4", "double": "<f8", "uint": "<u4", "int": "<i4", "uchar": "u1"}
    with open(path, "rb") as f:
        props, count = [], 0
        while True:
            line = f.readline().decode("ascii").strip()
            if line.startswith("element vertex"):
                count = int(line.split()[-1])
            if line.startswith("property "):
                _, typ, prop = line.split()
                props.append((prop, types[typ]))
            if line == "end_header":
                break
        offset = f.tell()
    return np.memmap(path, dtype=props, mode="r", offset=offset, shape=(count,))[name]


def review_sheet(xyz, hag, vehicles, path, window=4.5):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if not vehicles:
        return
    cols = 8
    rows = -(-len(vehicles)//cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols*2.2, rows*2.3), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, v in zip(axes.ravel(), vehicles):
        c = np.asarray(v["centre_xy"])
        m = np.all(np.abs(xyz[:, :2]-c) < window, axis=1)
        sel = np.flatnonzero(m)[::max(1, m.sum()//4000)]
        ax.scatter(xyz[sel, 0]-c[0], xyz[sel, 1]-c[1], c=hag[sel], s=.5, cmap="turbo", vmin=0, vmax=3)
        ax.set_title(f"#{v['id']} {v.get('length_m', '')}", fontsize=7)
        ax.set_aspect("equal")
    fig.savefig(path, dpi=80, bbox_inches="tight")
    plt.close(fig)


def main():
    decisions = load_json(GROUND_V1_DECISIONS)
    for key, path in PC.items():
        p = read_xyzi(path)
        xyz = np.asarray(p[:, :3], float)
        hag, smooth = floor_model(xyz)
        labels = np.full(len(xyz), OBSTACLE, np.uint8)
        if key == "pc_v1":
            ground = np.zeros(len(xyz), bool)
            ground[np.asarray(ply_column(GROUND_V1_PARTITION/"ground.ply", "original_index"))] = True
            car_id, vehicles = vehicle_instances(xyz, hag, ground, BODY_RETURNS[key])
            poly_id, reviewed = polygon_instances(xyz, hag, decisions["vehicles"], start_id=len(vehicles)+1)
            car_id = np.where(poly_id > 0, poly_id, car_id)
            vehicles += reviewed
        else:
            ground = (np.abs(hag) < .16) & smooth
            car_id, vehicles = vehicle_instances(xyz, hag, ground, BODY_RETURNS[key])
        labels[car_id > 0] = VEHICLE
        labels[isolated(xyz)] = NOISE
        labels[ground] = GROUND
        for v in vehicles:
            v["points"] = int((car_id == v["id"]).sum())
        np.save(work(f"02_{key}_labels.npy"), labels)
        np.save(work(f"02_{key}_hag.npy"), hag.astype(np.float16))
        save_json(work(f"02_{key}_vehicles.json"), vehicles)
        review_sheet(xyz, hag, vehicles, work(f"02_{key}_vehicles.png"))
        print(key, {n: int((labels == c).sum()) for n, c in (("ground", GROUND), ("obstacle", OBSTACLE),
                                                             ("vehicle", VEHICLE), ("noise", NOISE))},
              "vehicles", len(vehicles))


if __name__ == "__main__":
    main()
