from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from pxr import Usd, UsdGeom

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "map"))
from export_final_sim import export_isaac_scene, export_usd, rectangles


def test_rectangles_are_disjoint_and_cover_every_allowed_sample():
    mask = np.array([[1, 1, 0, 1, 1], [1, 1, 0, 1, 1],
                     [1, 1, 0, 1, 1], [1, 1, 0, 1, 1]], dtype=bool)
    cover = np.zeros(mask.shape, dtype=np.int16)
    for x0, x1, y0, y1 in rectangles(mask):
        cover[y0:y1, x0:x1] += 1
    assert np.array_equal(cover == 1, mask)


def test_composed_isaac_entry_layer_authors_frame_metadata(tmp_path: Path):
    """Sublayers do not supply the entry stage's axis/unit/default prim."""
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    faces = np.array([[0, 1, 2]], dtype=np.uint32)
    export_usd(tmp_path, vertices, faces)
    relative = export_isaac_scene(tmp_path, remainder=None)
    stage = Usd.Stage.Open(str(tmp_path / relative))
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    assert stage.GetDefaultPrim().GetPath().pathString == "/World"
    assert stage.GetPrimAtPath("/World/PAIR360Ground").IsValid()
