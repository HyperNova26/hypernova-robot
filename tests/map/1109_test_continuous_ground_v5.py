"""Synthetic checks for the continuous car-free ground exporter."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "map" / "1109_pair360_v1"))
from build_continuous_ground_v5 import apply_decisions, build_mesh, canopy_floor_heights, fine_surface, harmonic_fill  # noqa: E402


def test_confirmed_tree_wins_over_legacy_vehicle_floor_override():
    xy = np.array([[.5, .5], [1.5, .5]])
    whole = {'polygon_xy': [[0, 0], [2, 0], [2, 1], [0, 1]]}
    tree = {'polygon_xy': [[0, 0], [1, 0], [1, 1], [0, 1]]}
    allowed, excluded, _ = apply_decisions(
        xy, np.ones(2, bool), {'force_allow': [whole], 'exclude': [tree]}, np.ones(2, bool))
    assert allowed.tolist() == [False, True]
    assert excluded.tolist() == [True, False]


def test_exclusion_is_a_real_hole_and_all_permitted_is_finite():
    yy, xx = np.indices((9, 9))
    xy = np.c_[xx.ravel() + .5, yy.ravel() + .5]
    base = np.ones(81, bool)
    decisions = {"exclude": [{"polygon_xy": [[3, 3], [6, 3], [6, 6], [3, 6]]}]}
    allowed, excluded, _ = apply_decisions(xy, base, decisions)
    observed = np.full((9, 9), np.nan); observed[1, 1] = 0.; observed[7, 7] = 2.
    height, distance, residual = harmonic_fill(observed, allowed.reshape(9, 9), iterations=1500)
    assert np.isfinite(height[allowed.reshape(9, 9)]).all()
    assert np.isnan(height[excluded.reshape(9, 9)]).all()
    assert np.isfinite(distance).all() and residual < .01
    x, y, fine, mask = fine_surface(height, allowed.reshape(9, 9), np.array([0., 0.]), 1., .5)
    vertices, faces = build_mesh(x, y, fine, mask)
    assert len(vertices) == mask.sum() and np.isfinite(vertices).all()
    assert len(faces) > 0 and np.all(faces < len(vertices))
    # no triangle can span the excluded centre: each face is inside a 2x2 mask quad
    centroids = vertices[faces].mean(axis=1)
    assert not np.any((centroids[:, 0] > 3) & (centroids[:, 0] < 6) &
                      (centroids[:, 1] > 3) & (centroids[:, 1] < 6))
    # Measured supports are Dirichlet constraints, not smoothed away.
    assert height[1, 1] == 0. and height[7, 7] == 2.


def test_extension_and_exclusion_precedence():
    xy = np.array([[.5, .5], [1.5, .5], [2.5, .5], [3.5, .5]])
    base = np.array([True, False, False, False])
    decisions = {"restore_road": [{"polygon_xy": [[1, 0], [4, 0], [4, 1], [1, 1]]}],
                 "exclude": [{"polygon_xy": [[2, 0], [3, 0], [3, 1], [2, 1]]}]}
    allowed, excluded, _ = apply_decisions(xy, base, decisions)
    assert allowed.tolist() == [True, True, False, True]
    assert excluded.tolist() == [False, False, True, False]


def test_vehicle_floor_override_can_reopen_an_inherited_tree_mask():
    xy = np.array([[.5, .5], [1.5, .5], [2.5, .5]])
    inherited = np.array([False, True, False])
    decisions = {"force_allow": [{"polygon_xy": [[1, 0], [2, 0], [2, 1], [1, 1]]}]}
    allowed, excluded, _ = apply_decisions(xy, np.ones(3, bool), decisions, inherited)
    assert allowed.tolist() == [True, True, True]
    assert excluded.tolist() == [False, False, False]


def test_canopy_floor_reopens_inherited_planting_but_never_extends_domain():
    xy = np.array([[.5, .5], [1.5, .5], [2.5, .5]])
    base = np.array([True, True, False])
    inherited = np.array([False, True, True])
    canopy = {"polygon_xy": [[1, 0], [3, 0], [3, 1], [1, 1]]}
    allowed, excluded, _ = apply_decisions(xy, base, {"canopy_floor": [canopy]}, inherited)
    assert allowed.tolist() == [True, True, False]
    assert excluded.tolist() == [False, False, False]
    # An explicit exclusion still wins over a canopy floor.
    allowed, excluded, _ = apply_decisions(xy, base, {"canopy_floor": [canopy], "exclude": [canopy]}, inherited)
    assert allowed.tolist() == [True, False, False]


def test_canopy_floor_height_uses_lowest_returns_not_the_crown():
    keys = np.array([0] * 8 + [1] * 5 + [2] * 2)
    z = np.array([1.40, 1.42, 1.45, 1.48, 1.50, 3.0, 4.0, 5.0,  # floor under a crown
                  2.80, 2.82, 2.85, 2.90, 6.0,                  # crown only: low band is canopy
                  1.0, 1.1])                                    # too few returns
    cells = np.array([True, True, True, False])
    height = canopy_floor_heights(keys, z, cells, percentile=5., band_m=.15, min_points=3)
    assert np.isclose(height[0], 1.465)
    assert np.isclose(height[1], 2.85)   # caller must reject it against the floor
    assert np.isnan(height[2]) and np.isnan(height[3])


def test_harmonic_neighbourhood_does_not_wrap_across_grid_edges():
    # Two isolated allowed cells on opposite rows cannot become neighbours via
    # np.roll; the unobserved one remains its nearest-seed initial value.
    allowed = np.zeros((4, 4), bool); allowed[0, 1] = True; allowed[-1, 1] = True
    observed = np.full((4, 4), np.nan); observed[0, 1] = 7.
    height, _, _ = harmonic_fill(observed, allowed, iterations=5)
    assert height[0, 1] == 7. and height[-1, 1] == 7.
