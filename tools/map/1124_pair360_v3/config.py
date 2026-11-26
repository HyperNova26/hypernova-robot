"""Paths, versions and shared parameters of the PAIR360 map pipeline (pair360_map frame: pc_v1 raw XYZ, m, Z-up).

Paths come from environment variables set by tools/map/1124_pair360_v3/build_pair360_v3.py:
HN_PAIR360_DATA (point clouds, reviewed S-004 ground, Go2 model; not in Git), HN_PAIR360_DECISIONS
(hand-made decisions, sim_scenes/pair360_v3/decisions), HN_PAIR360_ROAD (S-009 road mask PNG) and
HN_PAIR360_OUT (all results).
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get("HN_PAIR360_DATA", REPO/"data/pair360_v3"))
RAW = DATA/"raw"
REVIEWED = DATA/"reviewed"
DECISIONS = Path(os.environ.get("HN_PAIR360_DECISIONS", REPO/"sim_scenes/pair360_v3/decisions"))
ROAD_MASK = Path(os.environ.get("HN_PAIR360_ROAD", REPO/"sim_scenes/pair360_v3/nav2/road_s009.png"))
RESULTS = Path(os.environ.get("HN_PAIR360_OUT", REPO/"data/pair360_v3_results"))

# Inputs by version. pc_v1 defines the map frame; pc_v2 is the newer, more precise capture.
PC = {
    "pc_v1": RAW/"pc_v1_pair360_t1_parking_demo.ply",   # PAIR360 T1_parking_Seq0 demo crop (public dataset, ODbL)
    "pc_v2": RAW/"pc_v2_20261115.pcd",                  # team FAST-LIO capture, 2026-11-15
}
SOURCE_ID = {"pc_v1": 1, "pc_v2": 2}

# pc_v1 ground versions. ground v0 = CloudCompare CSF only (legacy/PAIR360_demo/20261102_csf_relief_r03_t015).
# ground v1 = v0 + human review polygons + continuous surface + local smoothing + under-canopy fill
# (S-004, 2026-11-02..09; called "v9" in the S-004 history).
GROUND_V1_SURFACE = REVIEWED/"pc_v1_ground_v1/ground_surface.npz"     # 0.1 m grid: height, permitted, observed_coarse
GROUND_V1_PARTITION = REVIEWED/"pc_v1_ground_v1_partition"            # raw rows within 0.15 m of the surface: ground.ply / non_ground.ply
GROUND_V1_DECISIONS = REPO/"tools/map/1109_pair360_v1/continuous_ground_20261109_v9.json"  # vehicle polygons, tree exclusions
GO2_XML = DATA/"models/unitree_go2/go2.xml"                      # MuJoCo Menagerie Go2
ROUTE = DECISIONS/"demo_route.json"                             # start, goal, via points
ROUTE_REVIEW = DECISIONS/"route_review.json"                   # demo-corridor objects removed by hand review
TERRAIN_EDITS = DECISIONS/"terrain_edits.json"                 # hand-reviewed curb lines and tree corrections

MAP_VERSION, MESH_VERSION = "map_v3", "mesh_v3"
MAP_DIR, MESH_DIR = RESULTS/MAP_VERSION, RESULTS/MESH_VERSION
WORK = MAP_DIR/"work"                                            # step-to-step intermediates

# Classes written to point clouds.
GROUND, OBSTACLE, VEHICLE, NOISE, TRANSIENT = 1, 2, 5, 6, 7
LABEL_NAMES = {GROUND: "ground", OBSTACLE: "obstacle", VEHICLE: "vehicle", NOISE: "noise", TRANSIENT: "transient"}

# Rainbow height colour of the FAST-LIO viewer.
RGB_Z_RANGE = (0.5, 9.0)

# One colour per class in the map_v3 point clouds, so map_v3.pcd shows exactly what the split files show.
CLASS_RGB = {"ground_pc_v1": (46, 204, 64),     # green
             "ground_pc_v2": (0, 116, 217),     # blue
             "obstacle": (255, 133, 27),        # orange
             "removed": (220, 20, 60),          # red: vehicles and transients taken out of the static map
             "pc_v1_not_in_pc_v2": (148, 0, 211)}  # purple: diagnostic only, not part of map_v3
GROUND_MESH_RGB = (150, 150, 150)

# CloudCompare command line, used by step 10 to pack the viewing bundle into two .bin files.
CLOUDCOMPARE = Path(os.environ.get("CLOUDCOMPARE", r"C:\Program Files\CloudCompare\CloudCompare.exe"))


def work(name):
    WORK.mkdir(parents=True, exist_ok=True)
    return WORK/name
