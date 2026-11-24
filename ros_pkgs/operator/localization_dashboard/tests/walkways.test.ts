// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  planWalkwayStroke,
  snapWalkway,
  walkwayRoute,
  walkwaySegment,
  type WalkwayPoint,
} from "../src/walkways";

const point = (x: number, y: number): WalkwayPoint => ({ x, y });

describe("demo walkway", () => {
  it("projects to the closest finite segment and caps its ends", () => {
    expect(snapWalkway(point(-12, -4))).toEqual({
      point: point(-11, -4),
      distance: 1,
    });
    expect(snapWalkway(point(0.25, 4))).toEqual({
      point: point(0, 4),
      distance: 0.25,
    });
    expect(snapWalkway(point(Infinity, 1))).toBeUndefined();
  });

  it("routes between centerlines through the actual junctions", () => {
    const start = point(-8, -4);
    const end = point(4, 1);
    expect(walkwaySegment(start, end)).toBe(false);
    expect(walkwayRoute(start, end)).toEqual([
      start,
      point(0, -4),
      point(0, 1),
      end,
    ]);
    expect(walkwayRoute(start, start)).toEqual([start]);
    expect(walkwayRoute(start, point(3, 2))).toBeUndefined();
    expect(walkwayRoute(point(0, 6), end)).toEqual([
      point(0, 6),
      point(0, 1),
      end,
    ]);
  });
});

describe("drawn walkway routes", () => {
  it("routes a drawn shortcut through the walkway junctions", () => {
    const start = point(-8, -4.5);
    const end = point(4, 1.5);
    const expected = {
      points: [point(-8, -4), point(0, -4), point(0, 1), point(4, 1)],
      length: 17,
    };
    expect(planWalkwayStroke([start, end])).toEqual(expected);
    expect(
      planWalkwayStroke([start, point(-4, -2), point(2, -0.15), end]),
    ).toEqual(expected);
  });

  it("simplifies forward samples and keeps a deliberate turn and return", () => {
    const start = point(-8, -4);
    expect(
      planWalkwayStroke([
        start,
        point(-7.5, -4.05),
        point(-7.61, -4.025),
        point(-5, -4.3),
        point(0, -4),
        point(0.16, -2),
        point(0, -4),
        start,
      ]),
    ).toEqual({
      points: [start, point(0, -4), point(0, -2), point(0, -4), start],
      length: 20,
    });
  });

  it("retains a reversal on one centerline", () => {
    expect(
      planWalkwayStroke([point(-8, -4), point(-6, -4), point(-7, -4)]),
    ).toEqual({
      points: [point(-8, -4), point(-6, -4), point(-7, -4)],
      length: 3,
    });
  });

  it("rejects unusable, off-lane, or excessive gestures", () => {
    const start = point(-8, -4);
    expect(planWalkwayStroke([start])).toHaveProperty("error");
    expect(planWalkwayStroke([start, point(-7.9, -4)])).toHaveProperty("error");
    expect(planWalkwayStroke([start, point(-6, -2)])).toHaveProperty("error");
    expect(
      planWalkwayStroke([start, point(NaN, -2), point(-6, -4)]),
    ).toHaveProperty("error");
    const loops = Array.from({ length: 51 }, (_, step) =>
      point(step % 2 === 0 ? -8 : -6, -4),
    );
    expect(planWalkwayStroke(loops.slice(0, 50))).toHaveProperty(
      "points.length",
      50,
    );
    expect(planWalkwayStroke(loops)).toHaveProperty("error");
  });
});
