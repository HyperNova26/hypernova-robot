"""Classify measured source rows; no resampling, hole filling, or coordinate transform.

Run in the project checkout with numpy, scipy and matplotlib:
python classify.py --downloads <Downloads 폴더>
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from matplotlib.path import Path as Polygon

HERE = Path(__file__).resolve().parent
S004 = HERE.parents[1] / "ground_seperation"
ORIGINAL = S004 / "sim_scenes/S004_ground_final"
DATA = S004 / "data/PAIR360_demo"
V9 = DATA / "20261109_canopy_floor_v9_pointcloud"
NAMES = ["unknown", "ground", "trunk", "foliage", "structure", "vehicle", "noise"]
COLOR = np.array([[133,139,146], [82,158,205], [151,82,42], [47,155,89],
                  [167,120,201], [236,87,49], [245,191,35]], np.uint8)


def digest(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()


def read_cloud(path):
    types = {"float": "<f4", "uint": "<u4", "uchar": "u1"}
    props = []
    lines = []
    count = None
    with path.open("rb") as f:
        while True:
            raw = f.readline(1024)
            if not raw or len(lines) > 80:
                raise ValueError(path)
            line = raw.decode("ascii").strip()
            lines.append(line)
            if line.startswith("element vertex ") or line.startswith("POINTS "):
                count = int(line.split()[-1])
            if line.startswith("property "):
                _, typ, name = line.split()
                props.append((name, types[typ]))
            if line in ("end_header", "DATA binary"):
                break
        offset = f.tell()
    if lines[-1] == "DATA binary":
        if not all(k in lines for k in ["FIELDS x y z intensity", "SIZE 4 4 4 4", "TYPE F F F F", "COUNT 1 1 1 1"]):
            raise ValueError(f"Unexpected PCD layout in {path}")
        props = [(name, "<f4") for name in ("x","y","z","intensity")]
    elif "format binary_little_endian 1.0" not in lines:
        raise ValueError(path)
    dt = np.dtype(props)
    if offset + count * dt.itemsize != path.stat().st_size:
        raise ValueError(f"Source length differs from header {path}")
    rows = np.memmap(path, mode="r", offset=offset, dtype=dt, shape=(count,))
    return rows


def xyzi(rows):
    if rows.dtype.itemsize != 16:
        raise ValueError("Expected four raw floats")
    return rows.view("<f4").reshape(-1, 4)


def cell_quantile(ids, val, size, q):
    order = np.lexsort((val, ids))
    bins, start, n = np.unique(ids[order], return_index=True, return_counts=True)
    result = np.full(size, np.nan, np.float32)
    result[bins] = val[order[start + ((n - 1) * q).astype(int)]]
    return result


def floor_model(xyz):
    cell = 0.6
    base = np.floor(xyz[:,:2].min(axis=0)/cell) * cell
    ij = np.floor((xyz[:,:2] - base) / cell).astype(np.int32)
    nx, ny = ij.max(axis=0) + 1
    ids = ij[:,1]*nx + ij[:,0]
    floor = cell_quantile(ids, xyz[:,2], nx*ny, .08).reshape(ny,nx)
    valid = np.isfinite(floor)
    floor = floor[tuple(ndi.distance_transform_edt(~valid, return_distances=False, return_indices=True))]
    floor = ndi.median_filter(floor, size=3)
    # Grayscale openings suppress vehicle roofs; high terraces with poor support
    # remain unknown by requiring a gently varying surrounding elevation.
    for radius in (2, 5, 10, 18):
        opening = ndi.grey_opening(floor, size=2*radius+1)
        high = floor - opening > .16 + .13 * radius * cell
        if high.any() and (~high).any():
            nearest = ndi.distance_transform_edt(high, return_distances=False, return_indices=True)
            floor[high] = floor[tuple(nearest[:,high])]
    floor = ndi.gaussian_filter(floor,.8)
    gy,gx=np.gradient(floor,cell)
    smooth = np.hypot(gx, gy)<.38
    hag = xyz[:,2] - ndi.map_coordinates(floor,[(xyz[:,1]-base[1])/cell-.5,(xyz[:,0]-base[0])/cell-.5],order=1,mode="nearest")
    return hag, smooth.ravel()[ids]


def voxel_shape(xyz):
    width = .26
    origin = xyz.min(axis=0)
    ijk = np.floor((xyz-origin)/width).astype(np.int32)
    dims = ijk.max(axis=0).astype(np.int64)+1
    key = (ijk[:,0].astype(np.int64)*dims[1] + ijk[:,1])*dims[2]+ijk[:,2]
    _, first, inverse = np.unique(key,return_index=True,return_inverse=True)
    count = np.bincount(inverse)
    centers = np.column_stack([np.bincount(inverse,weights=xyz[:,i])/count for i in range(3)])
    tree=cKDTree(centers)
    planar=np.zeros(len(centers),bool)
    vertical=planar.copy()
    canopy=planar.copy()
    isolated=planar.copy()
    for i in range(0,len(centers),20000):
        part=slice(i,i+20000)
        d,ind=tree.query(centers[part], k=24,workers=2)
        offsets=centers[ind]
        offsets-=offsets.mean(axis=1,keepdims=True)
        cov=offsets.transpose(0,2,1)@offsets/24.
        val,vec=np.linalg.eigh(cov)
        val=np.maximum(val,0)
        ratio=val[:,0]/np.maximum(1e-9,val.sum(axis=1))
        flat=(ratio<.032)&(val[:,1]>0.20*val[:,2])&(d[:,-1]<1.25)
        planar[part]=flat&(np.abs(vec[:,2,0])>.87)
        vertical[part]=flat&(np.abs(vec[:,2,0])<.25)
        canopy[part]=(ratio>.062)&(val[:,1]>.22*val[:,2])&(d[:,-1]<1.8)
        # Isolated leaf tips in an otherwise supported cluster stay unknown.
        isolated[part]=(count[part]==1)&(d[:,1]>1.35)&(d[:,5]>2.1)
    return [m[inverse] for m in (planar,vertical,canopy,isolated)]


def bounded_clusters(xyz,hag,labels):
    """Label coherent low bodies and narrow, canopy-supported stems."""
    cell=.25
    base=xyz[:,:2].min(axis=0)
    ij=np.floor((xyz[:,:2]-base)/cell).astype(np.int32)
    nx,ny=ij.max(axis=0)+1
    ids=ij[:,1]*nx+ij[:,0]
    shape=(ny,nx)
    def counts(mask):
        return np.bincount(ids[mask],minlength=nx*ny).reshape(shape)
    # Connected footprints in the headlight/roof band. Use only isolated
    # components with car-sized oriented dimensions and no high return cluster.
    band=counts((hag>.5)&(hag<1.75))>0
    band=ndi.binary_closing(band,structure=np.ones((3,3),bool))
    comps,n=ndi.label(band,structure=np.ones((3,3),bool))
    vehicles=np.zeros(n+1,bool)
    trunks=np.zeros(n+1,bool)
    tree_top=counts((hag>3.1)&(hag<9)&(labels==3))
    high=counts(hag>2.45)
    presence=counts((hag>1.0)&(hag<1.75))
    tall=counts((hag>1.75)&(hag<3.05))
    for k,sl in enumerate(ndi.find_objects(comps),1):
        if sl is None: continue
        comp=comps[sl]==k
        cells=np.argwhere(comp)
        if not 3<=len(cells)<=280: continue
        pts=cells*cell
        vals,axes=np.linalg.eigh(np.cov(pts,rowvar=False))
        spread=np.ptp(pts@axes,axis=0)+cell
        width,length=np.sort(spread)
        occupancy=len(pts)*cell**2/(width*length)
        if (1.15<=width<=2.8 and 2.8<=length<=6.2 and .36<occupancy
                and high[sl][comp].sum()<=2 and presence[sl][comp].sum()>=12):
            vehicles[k]=True
        if width<=1.05 and length<=1.35 and tall[sl][comp].sum()>=5:
            cy,cx=np.mean(cells,axis=0).astype(int)+[sl[0].start,sl[1].start]
            canopy=tree_top[max(0,cy-6):cy+7,max(0,cx-6):cx+7].sum()
            trunks[k]=canopy>=15
    obj=comps.ravel()[ids]
    labels[vehicles[obj]&(hag>.20)&(hag<2.5)]=5
    labels[trunks[obj]&(hag>.25)&(hag<3.05)]=2


def polygon_indices(xyz, polygon):
    poly=np.asarray(polygon)
    mask=np.all((xyz[:,:2]>=poly.min(axis=0)) & (xyz[:,:2]<=poly.max(axis=0)),axis=1)
    ind=np.flatnonzero(mask)
    return ind[Polygon(poly).contains_points(xyz[ind,:2],radius=1e-7)]


def reviewed_pc_v1(source,xyz,labels,hag):
    protocol=json.loads((ORIGINAL/"review/protocol.json").read_text(encoding="utf-8"))
    if digest(source)!=protocol["source_sha256"]:
        raise ValueError("S-004 source checksum mismatch")
    # Each v9 row claims an original_index. Check the entire partition and
    # compare the exact stored XYZI bit patterns on both sides.
    seen=np.zeros(len(xyz),bool)
    ground=np.zeros(len(xyz),bool)
    src=xyzi(read_cloud(source))
    for part in ("ground","non_ground"):
        rows=read_cloud(V9/f"{part}.ply")
        for i in range(0,len(rows),250000):
            block=rows[i:i+250000]
            idx=block["original_index"]
            if (np.any(idx>=len(xyz)) or np.any(seen[idx]) or
                    len(np.unique(idx))!=len(idx)):
                raise AssertionError("Overlapping source index")
            for j,f in enumerate(("x","y","z","scalar_intensity")):
                if not np.array_equal(src[idx,j].view("<u4"),block[f].view("<u4")):
                    raise AssertionError(f"Source index mismatch {part} {i} {f}")
            seen[idx]=True
            if part=="ground": ground[idx]=True
    if not seen.all(): raise AssertionError("v9 partition incomplete")
    labels[labels==1]=0
    cfg=json.loads((S004/"tools/map/continuous_ground_20261109_v9.json").read_text(encoding="utf-8"))
    # Historical vehicle polygons span a footprint; limit them vertically.
    # Canopy, ground and noise are not vehicle bodies.
    for item in cfg["vehicles"]:
        ind=polygon_indices(xyz,item["polygon_xy"])
        if "z_bounds" in item:
            lo,hi=item["z_bounds"]
            mask=(xyz[ind,2]>=lo)&(xyz[ind,2]<=hi)
        else: mask=(hag[ind]>.22)&(hag[ind]<4.0)
        labels[ind[mask & (hag[ind]>.13) & (hag[ind]<4.1)]]=5
    canopy_records=cfg["tree_exclusion"] + [x for x in cfg["canopy_floor"] if "tree" in x["id"]]
    for item in canopy_records:
        ind=polygon_indices(xyz,item["polygon_xy"])
        # Preserve co-located cars and roofs; accept canopy only at height.
        labels[ind[(hag[ind]>3.0)&(labels[ind]!=4)&(labels[ind]!=6)]]=3
    # A reviewed trunk location identifies an object neighbourhood, not the
    # cylinder itself. Use the actual high-density near-ground column.
    for item in cfg["exclude"]:
        if not (item["id"].startswith("trunk_") or item["id"] in {"T09","T39","T130"}): continue
        ind=polygon_indices(xyz,item["polygon_xy"])
        body=ind[(hag[ind]>.65)&(hag[ind]<1.8)]
        if len(body)<10: continue
        center=np.median(xyz[body,:2],axis=0)
        radius=np.linalg.norm(xyz[body,:2]-center,axis=1)
        r=float(np.clip(np.quantile(radius,.65),.15,.48))
        within=np.linalg.norm(xyz[ind,:2]-center,axis=1)<=r
        labels[ind[within&(hag[ind]>.25)&(hag[ind]<3.2)]]=2
    labels[ground]=1
    return {"v9_all_source_indices_and_xyzi_verified":int(seen.sum()),"v9_observed_ground":int(ground.sum())}


def plots(key,xyz,labels,hag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig,axs=plt.subplots(1,2,figsize=(13,7),layout="constrained")
    cmap=COLOR/255.
    for ax,axes,title in zip(axs,[(0,1),(1,2)],["Plan view","Y-Z profile"]):
        for code in [0,1,4,3,2,5,6]:
            idx=np.flatnonzero(labels==code)
            idx=idx[::max(1,len(idx)//75000)]
            ax.scatter(xyz[idx,axes[0]],xyz[idx,axes[1]],s=.35,c=[cmap[code]],alpha=.8,linewidths=0)
        ax.set(aspect="equal", title=title,xlabel="XYZ"[axes[0]]+" (m)",ylabel="XYZ"[axes[1]]+" (m)")
    fig.legend(handles=[Line2D([],[],linestyle="none",marker="o",color=cmap[i],label=s) for i,s in enumerate(NAMES)],loc="lower center",ncol=7)
    fig.suptitle(key+" | measured points, native frame")
    fig.savefig(HERE/f"{key}_overview.png",dpi=125); plt.close(fig)
    # Pick a representative core of each retained/excluded class from dense
    # 8m tiles; XY and profile share the very same point rows.
    fig,axs=plt.subplots(2,4,figsize=(15,7),layout="constrained")
    examples={}
    for column,code in enumerate([1,2,3,5]):
        candidate=np.flatnonzero(labels==code)
        if not len(candidate): continue
        keys=np.floor(xyz[candidate,:2]/8).astype(int)
        cells,cnt=np.unique(keys,axis=0,return_counts=True)
        center=(cells[np.argmax(cnt)]+.5)*8
        inside=np.all(np.abs(xyz[:,:2]-center)<5,axis=1)
        ind=np.flatnonzero(inside)
        examples[NAMES[code]]={"center_xy":center.tolist(),"extent_m":[10,10],"source_points":len(ind)}
        for row,axes in enumerate([(0,1),(0,2)]):
            ax=axs[row,column]
            for c in [0,1,4,3,2,5,6]:
                sel=ind[labels[ind]==c]
                sel=sel[::max(1,len(sel)//7000)]
                ax.scatter(xyz[sel,axes[0]],xyz[sel,axes[1]],s=1,c=[cmap[c]],linewidths=0)
            ax.set(aspect="equal",title=NAMES[code]+" "+"XY"[row] if False else NAMES[code]+" "+["XY","XZ"][row],xlabel="X (m)",ylabel="XYZ"[axes[1]]+" (m)")
    fig.suptitle(key+" | class review tiles"); fig.savefig(HERE/f"{key}_sections.png",dpi=115);plt.close(fig)
    return examples


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--downloads",type=Path,required=True)
    ap.add_argument("--only",nargs="+", choices=["pc_v2","pc_v3","pc_v1"],default=["pc_v2","pc_v3","pc_v1"])
    args=ap.parse_args()
    paths={"pc_v2":args.downloads/"map_preview.pcd","pc_v3":HERE.parent/"input/pc_v3_20261115.pcd","pc_v1":ORIGINAL/"input/original.ply"}
    for key in args.only:
        path=paths[key]
        points=xyzi(read_cloud(path))
        xyz=points[:,:3]
        if not np.isfinite(points).all(): raise ValueError("Nonfinite input needs index-preserving mask")
        print(key,len(xyz),"terrain and morphology",flush=True)
        hag,smooth=floor_model(xyz)
        planar,vertical,canopy,isolated=voxel_shape(xyz)
        labels=np.zeros(len(xyz),np.uint8)
        labels[(np.abs(hag)<.16)&smooth&planar]=1
        labels[(hag>2.8)&canopy]=3
        # High walls/roofs only. Low vertical surfaces can equally be cars.
        labels[(hag>3.5)&(vertical|planar)]=4
        bounded_clusters(xyz,hag,labels)
        labels[isolated]=6
        audit=reviewed_pc_v1(path,xyz,labels,hag) if key=="pc_v1" else {}
        values=np.bincount(labels,minlength=len(NAMES))
        np.save(HERE/f"{key}_labels.npy",labels)
        print(key,dict(zip(NAMES,map(int,values))),flush=True)
        examples=plots(key,xyz,labels,hag)
        report={"source":path.name,"sha256":digest(path),"rows":len(xyz),"labels_dtype":"uint8","index":"same row offset in source, zero-based","class_counts":dict(zip(NAMES,map(int,values))),"class_codes":dict(enumerate(NAMES)),"tiles":examples,**audit}
        (HERE/f"{key}_audit.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    main()
