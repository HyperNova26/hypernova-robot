// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import {
  campusMissionNetwork,
  hallDemoRoute,
  loadCampusMap,
} from "../src/campusMission";
import {
  CampusRouter,
  projectCampus,
  type CampusMapData,
  type CampusPoint,
} from "../src/campusRouting";

const metresPerDegree = (6378137 * Math.PI) / 180;
const source = {
  url: "https://www.openstreetmap.org/",
  timestamp: "2026-11-24T00:00:00Z",
  attribution: "© OpenStreetMap contributors",
  license: "ODbL 1.0",
};
const point = (x: number, y: number): CampusPoint => ({ x, y });

function campus(
  points: CampusPoint[],
  ways: [CampusMapData["features"][number]["kind"], number[]][],
): CampusMapData {
  return {
    source,
    origin: { lat: 0, lon: 0 },
    nodes: Object.fromEntries(
      points.map(({ x, y }, id) => [
        id,
        [y / metresPerDegree, x / metresPerDegree],
      ]),
    ),
    features: ways.map(([kind, nodes], id) => ({ id, kind, nodes })),
  };
}

function expectRoute(
  result: ReturnType<CampusRouter["plan"]>,
  expected: CampusPoint[],
  length: number,
) {
  if ("error" in result) throw new Error(result.error);
  expect(result.points).toHaveLength(expected.length);
  for (const [i, { x, y }] of expected.entries()) {
    expect(result.points[i].x).toBeCloseTo(x);
    expect(result.points[i].y).toBeCloseTo(y);
  }
  expect(result.length).toBeCloseTo(length);
}

describe("campus XY metres", () => {
  it("uses the geographic origin with east and north axes", () => {
    const data = { ...campus([], []), origin: { lat: 37.24, lon: 127.08 } };
    expect(projectCampus(data, [37.24, 127.08])).toEqual(point(0, 0));
    const projected = projectCampus(data, [37.241, 127.081]);
    expect(projected.x).toBeCloseTo(88.6, 0);
    expect(projected.y).toBeCloseTo(111.32, 2);
  });
});

describe("campus walkway planning", () => {
  it("snaps to points on a segment and rejects an endpoint too far from a walkway", () => {
    const router = new CampusRouter(
      campus([point(0, 0), point(20, 20)], [["walkway", [0, 1]]]),
    );
    expectRoute(
      router.plan([point(2, 4), point(15, 13)]),
      [point(3, 3), point(14, 14)],
      11 * Math.SQRT2,
    );
    expect(router.plan([point(0, 18), point(15, 13)])).toHaveProperty("error");
  });

  it("excludes roads from both snaps and routing even when they join walkway nodes", () => {
    const router = new CampusRouter(
      campus(
        [point(0, 0), point(10, 0), point(30, 0), point(40, 0)],
        [
          ["walkway", [0, 1]],
          ["road", [1, 2]],
          ["walkway", [2, 3]],
        ],
      ),
    );
    expect(router.plan([point(20, 0), point(35, 0)])).toMatchObject({
      error: expect.stringContaining("시작점"),
    });
    expect(router.plan([point(5, 0), point(35, 0)])).toMatchObject({
      error: expect.stringContaining("이어지지"),
    });
  });

  it("keeps bends and uses a shorter connected walkway instead of a road or detour", () => {
    const router = new CampusRouter(
      campus(
        [
          point(-20, 0),
          point(-3, 0),
          point(-3, 10),
          point(20, 10),
          point(-20, 30),
          point(20, 30),
        ],
        [
          ["walkway", [0, 1, 2]],
          ["walkway", [2, 3]],
          ["walkway", [0, 4, 5, 3]],
          ["road", [0, 3]],
        ],
      ),
    );
    expectRoute(
      router.plan([point(-15, 2), point(13, 12)]),
      [point(-15, 0), point(-3, 0), point(-3, 10), point(13, 10)],
      38,
    );
  });

  it("does not connect geometric crossings when their OSM node IDs differ", () => {
    const points = [
      point(-20, 0),
      point(0, 0),
      point(20, 0),
      point(0, -20),
      point(0, 0),
      point(0, 20),
    ];
    const disconnected = new CampusRouter(
      campus(points, [
        ["walkway", [0, 1, 2]],
        ["walkway", [3, 4, 5]],
      ]),
    );
    expect(
      disconnected.plan([point(-15, 0), point(0, 0), point(0, 15)]),
    ).toMatchObject({ error: expect.stringContaining("이어지지") });
    const connected = new CampusRouter(
      campus(points, [
        ["walkway", [0, 1, 2]],
        ["walkway", [3, 1, 5]],
      ]),
    );
    expectRoute(
      connected.plan([point(-15, 0), point(0, 0), point(0, 15)]),
      [point(-15, 0), point(0, 0), point(0, 15)],
      30,
    );
  });

  it("bridges a short mid-drag excursion and rejects a long deviation", () => {
    const router = new CampusRouter(
      campus([point(0, 0), point(40, 0)], [["walkway", [0, 1]]]),
    );
    expectRoute(
      router.plan([point(2, 0), point(3, 11), point(4, 0), point(20, 0)]),
      [point(2, 0), point(20, 0)],
      18,
    );
    expect(
      router.plan([point(2, 0), point(3, 30), point(4, 0), point(20, 0)]),
    ).toMatchObject({ error: expect.stringContaining("멀어졌습니다") });
  });

  it("ignores brief drift across parallel walkways with distant connectors", () => {
    const router = new CampusRouter(
      campus(
        [point(0, 0), point(30, 0), point(30, 4), point(0, 4)],
        [["walkway", [0, 1, 2, 3, 0]]],
      ),
    );
    expectRoute(
      router.plan([
        point(8, 0),
        point(12, 0.3),
        point(12, 2.8),
        point(13, 1.8),
        point(20, 0),
      ]),
      [point(8, 0), point(20, 0)],
      12,
    );
  });

  it("retains a deliberate same-edge reversal and suppresses small cursor backtracks", () => {
    const router = new CampusRouter(
      campus([point(0, 0), point(40, 0)], [["walkway", [0, 1]]]),
    );
    expectRoute(
      router.plan([point(2, 0), point(15, 0), point(7, 0)]),
      [point(2, 0), point(15, 0), point(7, 0)],
      21,
    );
    expectRoute(
      router.plan([point(2, 0), point(15, 0), point(14, 0), point(20, 0)]),
      [point(2, 0), point(20, 0)],
      18,
    );
  });
});

describe("persisted campus route validation", () => {
  it("accepts planned paths across shared nodes including rounded and simplified spans", () => {
    const router = new CampusRouter(
      campus(
        [point(0, 0), point(8, 0), point(15, 0), point(15, 12)],
        [
          ["walkway", [0, 1]],
          ["walkway", [1, 2, 3]],
        ],
      ),
    );
    const route = router.plan([point(3, 0), point(15, 0), point(15, 9)]);
    if ("error" in route) throw new Error(route.error);
    expect(route.points).toHaveLength(3);
    expect(router.containsRoute(route.points)).toBe(true);
    expect(
      router.containsRoute([
        point(3.0009, 0.0008),
        point(15.0006, 0),
        point(15, 9.0005),
      ]),
    ).toBe(true);
    expect(router.containsRoute([...route.points].reverse())).toBe(true);
    expect(router.containsRoute([point(3, 0), point(15, 9)])).toBe(false);
    expect(router.containsRoute([point(3, 0.02), point(15, 0.02)])).toBe(false);
  });

  it("validates transitions using shared OSM nodes, not coincident intersections", () => {
    const points = [
      point(-12, 0),
      point(0, 0),
      point(12, 0),
      point(0, -9),
      point(0, 0),
      point(0, 9),
    ];
    const disconnected = new CampusRouter(
      campus(points, [
        ["walkway", [0, 1, 2]],
        ["walkway", [3, 4, 5]],
      ]),
    );
    const corner = [point(-7, 0), point(0, 0), point(0, 7)];
    expect(disconnected.containsRoute(corner)).toBe(false);
    expect(disconnected.containsRoute([point(-7, 0), point(7, 0)])).toBe(true);
    const connected = new CampusRouter(
      campus(points, [
        ["walkway", [0, 1, 2]],
        ["walkway", [3, 1, 5]],
      ]),
    );
    expect(connected.containsRoute(corner)).toBe(true);
  });

  it("does not bridge collinear geometry with duplicate nodes or roads", () => {
    const router = new CampusRouter(
      campus(
        [
          point(0, 0),
          point(10, 0),
          point(10, 0),
          point(20, 0),
          point(28, 0),
          point(38, 0),
        ],
        [
          ["walkway", [0, 1]],
          ["walkway", [2, 3]],
          ["road", [3, 4]],
          ["walkway", [4, 5]],
        ],
      ),
    );
    expect(router.containsRoute([point(2, 0), point(18, 0)])).toBe(false);
    expect(
      router.containsRoute([point(2, 0), point(10, 0), point(18, 0)]),
    ).toBe(false);
    expect(
      router.containsRoute([point(12, 0), point(20, 0), point(30, 0)]),
    ).toBe(false);
    expect(router.containsRoute([])).toBe(false);
    expect(router.containsRoute([point(2, NaN)])).toBe(false);
  });
});

describe("mapped campus motion boundary", () => {
  it("blocks crossing a concave exterior pocket even when both ends and the midpoint are inside", () => {
    const data = campus([point(1, 1), point(2, 1)], [["walkway", [0, 1]]]);
    data.campusOutline = [
      [0, 0],
      [10, 0],
      [10, 10],
      [7, 10],
      [7, 4],
      [6, 4],
      [6, 10],
      [0, 10],
      [0, 0],
    ].map(([x, y]) => [y / metresPerDegree, x / metresPerDegree]);
    const allows = campusMissionNetwork(data).allowsDemoMotion!;
    expect(allows(point(1, 8), point(5, 8))).toBe(true);
    expect(allows(point(1, 8), point(9, 8))).toBe(false);
    expect(allows(point(9, 8), point(1, 8))).toBe(false);
    expect(allows(point(1, 4), point(9, 4))).toBe(true);
    expect(allows(point(0, 1), point(0, 9))).toBe(true);
    expect(allows(point(1, 8), point(-1, 8))).toBe(false);
    expect(allows(point(6.5, 8), point(6.5, 8))).toBe(false);
    expect(allows(point(2, 8), point(2, 8))).toBe(true);
  });

  it("leaves earlier snapshots without an outline usable for route validation", () => {
    const data = campus([point(0, 0), point(2, 0)], [["walkway", [0, 1]]]);
    const network = campusMissionNetwork(data);
    expect(network.demoStart).toBeUndefined();
    expect(network.allowsDemoMotion).toBeUndefined();
    expect(network.containsRoute([point(0, 0), point(2, 0)])).toBe(true);
  });
});

describe("bundled KHU campus snapshot", () => {
  const data = JSON.parse(
    readFileSync(new URL("../public/khu-osm.json", import.meta.url), "utf8"),
  ) as CampusMapData;
  const router = new CampusRouter(data);
  const position = (id: string) => projectCampus(data, data.nodes[id]);

  it("preserves the original pedestrian spur by the hall", () => {
    const roadside = position("4230762568");
    const front = position("4230762570");
    expectRoute(router.plan([roadside, front]), [roadside, front], 21.838);
    expect(router.containsRoute([roadside, front])).toBe(true);
  });

  it("connects the west and east approaches via registered campus access roads", () => {
    const nodes = [
      "4230762570",
      "4230762568",
      "5596604867",
      "4230762567",
      "4230762563",
      "1762480901",
      "1762481725",
      "1762481729",
      "1762481723",
      "3335634553",
    ];
    const stroke = nodes.map(position);
    const route = router.plan(stroke);
    if ("error" in route) throw new Error(route.error);
    expect(route.length).toBeCloseTo(457.2, 0);
    expect(router.containsRoute(route.points)).toBe(true);
    const [start, east] = [stroke[0], stroke.at(-1)!];
    expect(router.containsRoute([start, east])).toBe(false);
  });

  it("registers nearby parking lanes and leaves distant road segments and stairs outside routing", () => {
    const lot = [position("5596604566"), position("5596604565")];
    const distant = [position("3335634480"), position("3335634474")];
    expect(router.containsRoute(lot)).toBe(true);
    expect(router.containsRoute(distant)).toBe(false);
    expect(data.features.some(({ id }) => id === 1370636323)).toBe(false);
  });

  it("does not enter a side branch on a smooth drag between plaza walkways", () => {
    const first = position("11356882031");
    const last = position("11357697664");
    const stroke = Array.from({ length: 16 }, (_, i) => ({
      x: first.x + ((last.x - first.x) * i) / 15,
      y: first.y + ((last.y - first.y) * i) / 15,
    }));
    expect(router.plan(stroke)).toHaveProperty(
      "length",
      expect.closeTo(38.6, 0),
    );
  });

  it("routes turns across multiple shared nodes at the Plaza of Contemplation", () => {
    const route = router.plan(
      [
        "11356882031",
        "14391581582",
        "5596604641",
        "5596604653",
        "11357697664",
      ].map(position),
    );
    expect(route).toHaveProperty("length", expect.closeTo(38.6, 0));
    if ("error" in route) throw new Error(route.error);
    expect(route.points.length).toBeGreaterThan(2);
    const network = campusMissionNetwork(data, router);
    expect(network.identity).toEqual({
      id: "khu-global-campus-osm",
      frame: "khu_campus_osm_local",
      version: data.source.timestamp,
    });
    expect(network.containsRoute(route.points)).toBe(true);
  });

  it("spawns opposite the hall's north facade facing the road to the plaza", () => {
    const network = campusMissionNetwork(data, router);
    const spawn = network.demoStart!;
    const [start, forward] = hallDemoRoute(data);
    const westBend = position("1762481725");
    const facadeWest = position("4681081847");
    const facadeEast = position("4681081858");
    expect(spawn.x).toBeCloseTo((facadeWest.x + facadeEast.x) / 2);
    expect(spawn.y).toBeGreaterThan(Math.max(facadeWest.y, facadeEast.y));
    expect(spawn.x).toBeCloseTo(start.x);
    expect(spawn.y).toBeCloseTo(start.y);
    expect(spawn.yaw).toBeCloseTo(
      (Math.atan2(westBend.y - spawn.y, westBend.x - spawn.x) * 180) / Math.PI,
    );
    expect(forward.x).toBeLessThan(start.x);
    expect(network.containsRoute([start, forward, westBend])).toBe(true);
    expect(network.allowsDemoMotion?.(start, forward)).toBe(true);
    expect(network.allowsDemoMotion?.(start, point(10000, 10000))).toBe(false);
  });

  it("loads the shared snapshot and rejects invalid graph or outline metadata", async () => {
    const requests = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(data)))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...data, nodes: {} })),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...data,
            campusOutline: data.campusOutline?.slice(0, -1),
          }),
        ),
      );
    vi.stubGlobal("fetch", requests);
    try {
      const controller = new AbortController();
      await expect(loadCampusMap(controller.signal)).resolves.toEqual(data);
      expect(requests).toHaveBeenCalledWith(
        expect.stringMatching(/khu-osm\.json$/),
        {
          signal: controller.signal,
        },
      );
      await expect(loadCampusMap()).rejects.toThrow(
        "등록된 보행로 데이터가 없습니다.",
      );
      await expect(loadCampusMap()).rejects.toThrow(
        "등록된 보행로 데이터가 없습니다.",
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
