"""Evidence for step 2: every vehicle drawn as a box on its original cloud, in pair360_map (after step 3).

In : data/raw/pc_v*, work/02_<pc>_vehicles.json, work/02_<pc>_labels.npy, work/03_register.json
Out: results/map_v3/evidence/vehicles_<pc>_overview.png (whole cloud, numbered boxes),
     results/map_v3/evidence/vehicles_<pc>_closeups.png (top + side view of each box, removed rows red)
"""
import numpy as np

from config import MAP_DIR, PC, VEHICLE, work
from pcio import load_json, read_xyzi, transform

OUT = MAP_DIR/"evidence"


def outline(v, matrix):
    """Box or reviewed polygon of a vehicle in the map frame."""
    if "polygon_xy" in v:
        poly = np.asarray(v["polygon_xy"], float)
    else:
        yaw = np.radians(v["yaw_deg"])
        u, w = np.array([np.cos(yaw), np.sin(yaw)]), np.array([-np.sin(yaw), np.cos(yaw)])
        c, hl, hw = np.asarray(v["centre_xy"]), v["length_m"]/2, v["width_m"]/2
        poly = np.array([c+hl*u+hw*w, c-hl*u+hw*w, c-hl*u-hw*w, c+hl*u-hw*w])
    poly = transform(np.column_stack([poly, np.zeros(len(poly))]), matrix)[:, :2]
    return np.vstack([poly, poly[:1]])


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    OUT.mkdir(parents=True, exist_ok=True)
    reg = load_json(work("03_register.json"))
    for key in PC:
        matrix = np.array(reg["pc_v2_to_map" if key == "pc_v2" else "pc_v1_to_map"])
        xyz = transform(np.asarray(read_xyzi(PC[key])[:, :3], float), matrix)
        labels = np.load(work(f"02_{key}_labels.npy"))
        vehicles = load_json(work(f"02_{key}_vehicles.json"))
        fig, ax = plt.subplots(figsize=(16, 16))
        s = np.random.default_rng(0).choice(len(xyz), min(len(xyz), 1500000), replace=False)
        o = s[np.argsort(xyz[s, 2])]
        ax.scatter(xyz[o, 0], xyz[o, 1], c=xyz[o, 2], s=.05, cmap="turbo", vmin=.5, vmax=9)
        for v in vehicles:
            box = outline(v, matrix)
            colour = "magenta" if "polygon" in v["source"] else "white"
            ax.plot(box[:, 0], box[:, 1], "-", color=colour, lw=1.2)
            ax.text(box[:, 0].max(), box[:, 1].max(), str(v["id"]), color=colour, fontsize=7)
        ax.set_aspect("equal")
        ax.set_facecolor("black")
        ax.set_title(f"{key}: {len(vehicles)} vehicles (white = detector, magenta = reviewed polygon), colour = z")
        fig.savefig(OUT/f"vehicles_{key}_overview.png", dpi=70, bbox_inches="tight")
        plt.close(fig)
        if not vehicles:
            continue
        cols = 6
        rows = -(-len(vehicles)//cols)
        fig, axes = plt.subplots(rows*2, cols, figsize=(cols*2.6, rows*4.4), squeeze=False)
        for ax in axes.ravel():
            ax.axis("off")
        for i, v in enumerate(vehicles):
            box = outline(v, matrix)
            c = box[:-1].mean(axis=0)
            m = np.all(np.abs(xyz[:, :2]-c) < 5, axis=1)
            sel = np.flatnonzero(m)[::max(1, m.sum()//6000)]
            gone = labels[sel] == VEHICLE
            top, side = axes[2*(i//cols), i % cols], axes[2*(i//cols)+1, i % cols]
            top.scatter(xyz[sel, 0]-c[0], xyz[sel, 1]-c[1], c=np.where(gone, "red", "grey"), s=.4)
            top.plot(box[:, 0]-c[0], box[:, 1]-c[1], "b-", lw=1)
            top.set_title(f"#{v['id']} {v.get('length_m', '')}x{v.get('width_m', '')}", fontsize=7)
            side.scatter(xyz[sel, 0]-c[0], xyz[sel, 2], c=np.where(gone, "red", "grey"), s=.4)
            for a in (top, side):
                a.axis("on")
                a.tick_params(labelsize=5)
            top.set_aspect("equal")
            side.set_aspect("equal")
        fig.savefig(OUT/f"vehicles_{key}_closeups.png", dpi=70, bbox_inches="tight")
        plt.close(fig)
        print(key, len(vehicles), "vehicles drawn")


if __name__ == "__main__":
    main()
