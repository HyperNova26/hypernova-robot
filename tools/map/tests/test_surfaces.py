# SPDX-License-Identifier: Apache-2.0
"""Cases the old cell-minimum and size-only segmentation cannot distinguish."""

import copy
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from pointcloud import build_heightfield, classify, read_yaml, split_ground
from test_pipeline import box

ROOT = Path(__file__).resolve().parents[3]


def parameters():
    return copy.deepcopy(read_yaml(ROOT/"sim_scenes/pair360_parking/frame.yaml")["processing"])


def sheet(xmin, xmax, ymin, ymax, spacing, slope=(0., 0.), height=0.):
    xx, yy = np.meshgrid(np.arange(xmin, xmax+spacing*.1, spacing),
                          np.arange(ymin, ymax+spacing*.1, spacing))
    return np.column_stack((xx.ravel(), yy.ravel(),
                            (xx*slope[0]+yy*slope[1]+height).ravel()))


def test_tilted_local_planes_keep_ground_despite_low_outliers():
    params = parameters()["ground"]
    terrain = sheet(-3, 4, -3, 3, .12, slope=(.25, .18))
    noise = np.array([[x, y, .25*x+.18*y-1.5] for x, y in [(-2, -2), (2, 2), (3, -1)]])
    points = np.vstack((terrain, noise))
    mask, _, _ = split_ground(points, params)
    assert mask[:len(terrain)].mean() > .98
    assert not mask[len(terrain):].any()


def test_minority_ground_beats_denser_parallel_roof():
    params = parameters()["ground"]
    terrain = sheet(-3, 5, -3, 3, .18, slope=(.08, .03))
    roof = sheet(1, 3.5, .4, 2.2, .07, slope=(.08, .03), height=1.6)
    details = {}
    mask, _, _ = split_ground(np.vstack((terrain, roof)), params, details)
    assert mask[:len(terrain)].mean() > .98
    assert mask[len(terrain):].mean() < .01
    assert details["report"]["patches_with_two_candidates"] > 0
    assert details["report"]["secondary_candidate_selected"] > 0


def test_roof_only_patch_does_not_invent_measured_ground():
    params = parameters()
    terrain = sheet(-3, 6, -3, 4, .12)
    terrain = terrain[~((terrain[:, 0] > 1) & (terrain[:, 0] < 4)
                        & (terrain[:, 1] > 0) & (terrain[:, 1] < 3))]
    roof = sheet(1.1, 3.9, .1, 2.9, .1, height=1.6)
    points = np.vstack((terrain, roof))
    mask, _, _ = split_ground(points, params["ground"])
    assert not mask[len(terrain):].any()
    _, measured, meta = build_heightfield(points[mask], points, params["heightfield"])
    i = int((1.5-meta["y0"])/meta["resolution"])
    j = int((2.5-meta["x0"])/meta["resolution"])
    assert not measured[i, j]
    with pytest.raises(ValueError, match="No reliable ground seed"):
        split_ground(sheet(-2, 2, -2, 2, .15, height=1.6), params["ground"])


def test_default_curb_stays_non_ground_and_rotated_car_needs_side_evidence():
    params = parameters()
    terrain = sheet(-3, 3, -3, 3, .1)
    curb = (np.abs(terrain[:, 0]) < 1) & (terrain[:, 1] > 1) & (terrain[:, 1] < 1.5)
    terrain[curb, 2] += .15
    mask, _, _ = split_ground(terrain, params["ground"])
    assert mask[curb].mean() < .1
    assert mask[~curb].mean() > .98
    rotation = Rotation.from_euler("z", 35, degrees=True).as_matrix()
    car = box((0, 0), 4.5, 2., 1.6) @ rotation.T
    floating_sheet = sheet(7, 11.5, -1, 1, .1, height=1.6)
    groups, records = classify(np.vstack((car, floating_sheet)), np.zeros((81, 161)),
                               {"x0": -4., "y0": -4., "resolution": .1}, params["classes"])
    assert len(groups["cars"]) > len(car)*.7
    assert not np.any(groups["cars"][:, 0] >= 7)
    assert any(row["class"] == "cars" and row["vertical_normal_fraction"] > .05 for row in records)
