// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  DemoOperations,
  campusResumeError,
  commandBlock,
  demoMap,
  exampleMission,
  missionError,
  walkwayApproachError,
  type CampusMissionNetwork,
  type Mission,
  type OperationCommand,
} from "../src/operation";
import { walkwaySegment, type WalkwayPoint } from "../src/walkways";

function setup() {
  const operations = new DemoOperations(1000);
  let now = 1000;
  return {
    state: operations.getSnapshot,
    setCampusNetwork: operations.setCampusNetwork,
    request: (command: OperationCommand) => operations.request(command, now),
    advance(ms: number) {
      for (let remaining = ms; remaining > 0; remaining -= 100) {
        now += Math.min(100, remaining);
        operations.tick(now);
      }
    },
    jump(ms: number) {
      now += ms;
      operations.tick(now);
    },
  };
}

function shortMission(): Mission {
  return {
    ...exampleMission,
    routing: undefined,
    map: { ...exampleMission.map },
    waypoints: [{ id: "first", name: "입구", x: -7, y: -4, yaw: 90, dwell: 1 }],
  };
}

function walkwayMission(points: WalkwayPoint[]): Mission {
  return {
    ...shortMission(),
    routing: "walkway",
    waypoints: points.map((point, index) => ({
      ...point,
      id: `walk-${index}`,
      name: `보행로 ${index + 1}`,
      yaw: 0,
      dwell: 0,
    })),
  };
}

const campusMap = { id: "khu-osm", version: "2026-11-24", frame: "khu_map" };
const campusNetwork: CampusMissionNetwork = {
  identity: campusMap,
  containsRoute(points) {
    return points.every((point, index) => {
      const onRoute =
        (point.x >= 100 && point.x <= 104 && point.y === 200) ||
        (point.x === 104 && point.y >= 200 && point.y <= 203);
      const previous = points[index - 1];
      return (
        onRoute &&
        (!previous || previous.x === point.x || previous.y === point.y)
      );
    });
  },
};

function campusMission(): Mission {
  return {
    id: "osm-building-patrol",
    name: "전자정보대학관 인근 순찰",
    routing: "campus",
    map: { ...campusMap },
    waypoints: [
      { id: "g1", name: "시작점", x: 100, y: 200, yaw: 0, dwell: 0 },
      { id: "g2", name: "교차점", x: 104, y: 200, yaw: 90, dwell: 0 },
      { id: "g3", name: "도착점", x: 104, y: 203, yaw: 90, dwell: 0 },
    ],
  };
}

const forward = { type: "teleop", forward: 1, left: 0, turn: 0 } as const;
const strafe = (left: number): OperationCommand => ({
  type: "teleop",
  forward: 0,
  left,
  turn: 0,
});
const auto = { type: "mode", mode: "AUTO" } as const;
const takeover = { type: "mode", mode: "TELEOP" } as const;

describe("DEMO TELEOP command application", () => {
  it("reports requested and observed motion separately and stops on release", () => {
    const sim = setup();
    expect(sim.state()).toMatchObject({
      mode: "TELEOP",
      connected: true,
    });
    expect(sim.state().run).toBeUndefined();
    expect(sim.request(forward)).toMatchObject({ ok: true });
    expect(sim.state().requested.forward).toBe(0.8);
    expect(sim.state().observed.forward).toBe(0);
    sim.advance(1000);
    expect(sim.state().pose.x).toBeCloseTo(-7.2);
    expect(sim.state().observed.forward).toBeCloseTo(0.8);
    sim.request({ type: "release" });
    sim.advance(1000);
    expect(sim.state().pose.x).toBeCloseTo(-7.2);
    expect(sim.state().requested.forward).toBe(0);
    expect(sim.state().observed.forward).toBe(0);
  });

  it("moves in the robot frame and bounds observed speed separately", () => {
    const sim = setup();
    sim.request({ type: "teleop", forward: 0, left: 0, turn: 1 });
    sim.advance(1000);
    expect(sim.state().pose.yaw).toBeCloseTo(90);
    sim.request(forward);
    sim.advance(30000);
    expect(sim.state().pose.y).toBeCloseTo(demoMap.bounds.maxY);
    expect(sim.state().pose.x).toBeCloseTo(-8);
    expect(sim.state().requested.forward).toBe(0.8);
    expect(sim.state().observed.forward).toBe(0);
  });

  it("drops manual input after a long browser suspension", () => {
    const sim = setup();
    sim.request(forward);
    sim.advance(100);
    const position = sim.state().pose;
    sim.jump(5000);
    sim.advance(100);
    expect(sim.state().pose).toEqual(position);
    expect(sim.state().requested.forward).toBe(0);
  });

  it("rejects expired input and requires a new hold after stop and mode changes", () => {
    const sim = setup();
    expect(sim.request({ ...forward, deadline: 999 })).toMatchObject({
      ok: false,
      code: "timeout",
    });
    expect(sim.state().requested.forward).toBe(0);
    sim.request(forward);
    sim.request({ type: "stop" });
    sim.advance(500);
    expect(sim.state().pose.x).toBe(-8);
    sim.request(forward);
    sim.request(auto);
    sim.request(takeover);
    sim.advance(500);
    expect(sim.state().pose.x).toBe(-8);
  });
});

describe("DEMO AUTO mission", () => {
  it.each(["id", "version", "frame"] as const)(
    "rejects a mismatched map %s",
    (field) => {
      const sim = setup();
      const mission = shortMission();
      mission.map[field] = "wrong";
      sim.request(auto);
      expect(sim.request({ type: "start", mission })).toMatchObject({
        ok: false,
        code: "invalid",
      });
      expect(sim.state().run).toBeUndefined();
    },
  );

  it("rejects invalid plane and waypoint parameters", () => {
    const mission = shortMission();
    mission.waypoints[0].x = demoMap.bounds.maxX + 0.1;
    expect(missionError(mission)).toContain("평면");
    mission.waypoints[0].x = 0;
    mission.waypoints[0].yaw = Number.NaN;
    expect(missionError(mission)).toContain("도착 방향");
    mission.waypoints[0].yaw = 90;
    mission.waypoints[0].dwell = -1;
    expect(missionError(mission)).toContain("대기 시간");
  });

  it("uses a frozen route snapshot and progresses through arrival, heading, dwell and completion", () => {
    const sim = setup();
    sim.request(auto);
    const mission = shortMission();
    expect(sim.request({ type: "start", mission })).toMatchObject({ ok: true });
    expect(sim.request({ type: "start", mission })).toMatchObject({
      ok: false,
      code: "duplicate",
    });
    mission.name = "편집 중";
    mission.waypoints[0].x = 5;
    sim.advance(1000);
    expect(sim.state().pose.x).toBeCloseTo(-7);
    expect(sim.state().pose.yaw).toBeGreaterThan(0);
    expect(sim.state().run?.reachedAt).toBeUndefined();
    sim.advance(1000);
    expect(sim.state().pose.yaw).toBeCloseTo(90);
    expect(sim.state().run?.reachedAt).toBeDefined();
    expect(sim.state().run?.targetIndex).toBe(0);
    sim.advance(700);
    expect(sim.state().run).toMatchObject({
      status: "completed",
      targetIndex: 1,
      mission: { name: exampleMission.name },
    });
  });

  it("pauses on TELEOP takeover and requires an explicit resume", () => {
    const sim = setup();
    sim.request(auto);
    sim.request({ type: "start", mission: shortMission() });
    sim.advance(200);
    expect(sim.request(forward)).toMatchObject({ ok: false, code: "blocked" });
    sim.request(takeover);
    expect(sim.state().run).toMatchObject({
      status: "paused",
      reason: "TELEOP 개입",
    });
    sim.request(forward);
    sim.advance(200);
    sim.request(auto);
    const position = sim.state().pose;
    sim.advance(2000);
    expect(sim.state().pose).toEqual(position);
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
    sim.advance(2700);
    expect(sim.state().run?.status).toBe("completed");
  });

  it("supports suspend, explicit resume, cancellation and a separate reset session", () => {
    const sim = setup();
    const originalId = sim.state().sessionId;
    sim.request(auto);
    sim.request({ type: "start", mission: shortMission() });
    sim.request({ type: "suspend" });
    expect(sim.state().run?.status).toBe("paused");
    sim.request({ type: "resume" });
    sim.request({ type: "cancel" });
    expect(sim.state().run?.status).toBe("cancelled");
    sim.advance(500);
    sim.request({ type: "reset" });
    expect(sim.state().sessionId).not.toBe(originalId);
    expect(sim.state().timeOrigin).toBe(1500);
    expect(sim.state()).toMatchObject({
      mode: "TELEOP",
      incidents: [],
    });
    expect(sim.state().run).toBeUndefined();
  });
});

describe("DEMO walkway route execution", () => {
  it("starts the built-in route as a walkway mission", () => {
    const sim = setup();
    expect(exampleMission.routing).toBe("walkway");
    expect(missionError(exampleMission)).toBeUndefined();
    sim.request(auto);
    expect(
      sim.request({ type: "start", mission: exampleMission }),
    ).toMatchObject({ ok: true });
  });

  it("requires every drawn waypoint and segment to remain on the centerline", () => {
    const sim = setup();
    sim.request(auto);
    const offCenter = walkwayMission([{ x: -7, y: -3.9 }]);
    expect(missionError(offCenter)).toContain("중심선");
    const diagonal = walkwayMission([
      { x: -7, y: -4 },
      { x: 0, y: -2 },
    ]);
    expect(missionError(diagonal)).toContain("구간");
    expect(sim.request({ type: "start", mission: diagonal })).toMatchObject({
      ok: false,
      code: "invalid",
    });
    diagonal.routing = undefined;
    expect(sim.request({ type: "start", mission: diagonal })).toMatchObject({
      ok: true,
    });
  });

  it("approaches a drawn route around the modeled corner without adding mission targets", () => {
    const sim = setup();
    const mission = walkwayMission([
      { x: 0, y: -2 },
      { x: 0, y: 0 },
    ]);
    sim.request(auto);
    expect(walkwayApproachError(sim.state().pose, mission)).toBeUndefined();
    expect(sim.request({ type: "start", mission })).toMatchObject({ ok: true });
    expect(sim.state().run?.approach).toEqual({
      from: { x: -8, y: -4 },
      points: [{ x: 0, y: -4 }],
      nextIndex: 0,
    });
    for (let i = 0; i < 120 && sim.state().run?.status === "running"; i++) {
      const before = sim.state().pose;
      sim.advance(100);
      expect(walkwaySegment(before, sim.state().pose)).toBe(true);
    }
    expect(sim.state().run).toMatchObject({
      status: "completed",
      targetIndex: 2,
    });
    expect(sim.state().run?.mission.waypoints).toEqual(mission.waypoints);
    expect(sim.state().pose).toMatchObject({ x: 0, y: 0 });
    const trail = sim.state().trail;
    expect(
      trail
        .slice(1)
        .every((point, index) => walkwaySegment(trail[index], point)),
    ).toBe(true);
  });

  it("blocks start when the robot is outside the walkway corridor", () => {
    const sim = setup();
    const mission = walkwayMission([{ x: -6, y: -4 }]);
    sim.request(strafe(1));
    sim.advance(1000);
    sim.request(auto);
    const reason = walkwayApproachError(sim.state().pose, mission);
    expect(reason).toContain("TELEOP");
    expect(sim.request({ type: "start", mission })).toMatchObject({
      ok: false,
      code: "blocked",
      reason,
    });
    expect(sim.state().run).toBeUndefined();
  });

  it("replans explicit resume from the corridor after TELEOP and preserves completed targets", () => {
    const sim = setup();
    const mission = walkwayMission([
      { x: -7, y: -4 },
      { x: 0, y: -4 },
      { x: 0, y: -2 },
    ]);
    sim.request(auto);
    sim.request({ type: "start", mission });
    sim.advance(1600);
    expect(sim.state().run?.targetIndex).toBe(1);
    sim.request(takeover);
    sim.request(strafe(1));
    sim.advance(750);
    sim.request(auto);
    const outside = sim.state().pose;
    expect(sim.request({ type: "resume" })).toMatchObject({
      ok: false,
      code: "blocked",
    });
    sim.advance(1000);
    expect(sim.state().pose).toEqual(outside);
    expect(sim.state().run).toMatchObject({ status: "paused", targetIndex: 1 });
    sim.request(takeover);
    sim.request(strafe(-1));
    sim.advance(400);
    sim.request(auto);
    expect(sim.state().run?.status).toBe("paused");
    const corridor = sim.state().pose;
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
    expect(sim.state().run?.approach?.points[0]).toEqual({
      x: corridor.x,
      y: -4,
    });
    sim.advance(200);
    expect(sim.state().pose.x).toBeCloseTo(corridor.x);
    expect(sim.state().pose.y).toBe(-4);
    expect(sim.state().run?.targetIndex).toBe(1);
    sim.advance(9000);
    expect(sim.state().run).toMatchObject({
      status: "completed",
      targetIndex: 3,
    });
  });
});

describe("DEMO OSM campus mission execution", () => {
  it("requires the matching geographic network, finite coordinates and a valid connected route", () => {
    const sim = setup();
    const mission = campusMission();
    sim.request(auto);
    expect(missionError(mission)).toContain("지도를 불러오세요");
    expect(sim.request({ type: "start", mission })).toMatchObject({
      ok: false,
    });
    sim.setCampusNetwork(campusNetwork);
    expect(missionError(mission, demoMap, campusNetwork)).toBeUndefined();
    for (const field of ["id", "version", "frame"] as const) {
      expect(
        missionError(
          { ...mission, map: { ...mission.map, [field]: "other" } },
          demoMap,
          campusNetwork,
        ),
      ).toContain("일치");
    }
    expect(
      missionError(
        { ...mission, waypoints: mission.waypoints.slice(0, 1) },
        demoMap,
        campusNetwork,
      ),
    ).toContain("2개");
    const invalidCoordinate = campusMission();
    invalidCoordinate.waypoints[1].x = NaN;
    expect(missionError(invalidCoordinate, demoMap, campusNetwork)).toContain(
      "지도 좌표",
    );
    const diagonal = {
      ...mission,
      waypoints: [mission.waypoints[0], mission.waypoints[2]],
    };
    expect(missionError(diagonal, demoMap, campusNetwork)).toContain(
      "연결된 보행로",
    );
    expect(sim.request({ type: "start", mission: diagonal })).toMatchObject({
      ok: false,
      code: "invalid",
    });
    expect(sim.state().campus).toBeUndefined();
  });

  it("starts from the first OSM waypoint and keeps pause, takeover and trail in their own coordinates", () => {
    const sim = setup();
    const syntheticPose = sim.state().pose;
    const syntheticTrail = sim.state().trail;
    sim.setCampusNetwork(campusNetwork);
    sim.request(auto);
    const mission = campusMission();
    expect(sim.request({ type: "start", mission })).toMatchObject({ ok: true });
    expect(sim.state().campus).toEqual({
      map: campusMap,
      pose: { x: 100, y: 200, yaw: 0 },
      trail: [{ x: 100, y: 200, yaw: 0 }],
    });
    sim.advance(1000);
    expect(sim.state().run).toMatchObject({
      status: "running",
      targetIndex: 1,
    });
    const campusPose = sim.state().campus?.pose;
    expect(campusPose?.x).toBeGreaterThan(100);
    expect(sim.state().pose).toBe(syntheticPose);
    expect(sim.state().trail).toBe(syntheticTrail);
    expect(sim.state().observed.forward).toBe(0);
    sim.request(takeover);
    sim.request(forward);
    sim.advance(500);
    expect(sim.state().pose.x).toBeGreaterThan(syntheticPose.x);
    expect(sim.state().campus?.pose).toBe(campusPose);
    sim.request(auto);
    sim.advance(500);
    expect(sim.state().campus?.pose).toBe(campusPose);
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
    sim.advance(7500);
    expect(sim.state().run).toMatchObject({
      status: "completed",
      targetIndex: 3,
    });
    expect(sim.state().campus?.pose).toEqual({ x: 104, y: 203, yaw: 90 });
    expect(campusNetwork.containsRoute(sim.state().campus!.trail)).toBe(true);
    expect(sim.request({ type: "start", mission })).toMatchObject({ ok: true });
    expect(sim.state().campus?.trail).toHaveLength(1);
  });

  it("pauses when the campus map revision changes and resumes only when it matches again", () => {
    const sim = setup();
    sim.setCampusNetwork(campusNetwork);
    sim.request(auto);
    sim.request({ type: "start", mission: campusMission() });
    sim.advance(500);
    const pose = sim.state().campus?.pose;
    sim.setCampusNetwork({
      ...campusNetwork,
      identity: { ...campusMap, version: "new" },
    });
    expect(sim.state().run).toMatchObject({
      status: "paused",
      reason: expect.stringContaining("일치"),
    });
    expect(sim.request({ type: "resume" })).toMatchObject({
      ok: false,
      code: "blocked",
    });
    sim.advance(500);
    expect(sim.state().campus?.pose).toBe(pose);
    sim.setCampusNetwork(campusNetwork);
    expect(sim.state().run?.status).toBe("paused");
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
    expect(sim.request({ type: "cancel" })).toMatchObject({ ok: true });
    expect(sim.state().run?.status).toBe("cancelled");
  });

  it("tags incidents with their campus pose and map and keeps recovery explicit", () => {
    const sim = setup();
    sim.request({ type: "inject", kind: "field" });
    const synthetic = sim.state().incidents[0];
    expect(synthetic.map).toBeUndefined();
    sim.setCampusNetwork(campusNetwork);
    sim.request(auto);
    sim.request({ type: "start", mission: campusMission() });
    sim.advance(500);
    const pose = sim.state().campus?.pose;
    sim.request({ type: "inject", kind: "field" });
    expect(sim.state().incidents[0]).toMatchObject({
      kind: "field",
      map: campusMap,
      pose,
    });
    expect(sim.state().incidents[0].id).not.toBe(synthetic.id);
    sim.request({ type: "inject", kind: "obstacle" });
    expect(sim.state().incidents[0]).toMatchObject({
      kind: "obstacle",
      map: campusMap,
      pose,
      waypointId: "g2",
    });
    expect(sim.state().run?.status).toBe("paused");
    sim.request({ type: "recover", kind: "obstacle" });
    expect(sim.state().run?.status).toBe("paused");
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
  });
});

describe("single-campus DEMO operation", () => {
  const configuredNetwork: CampusMissionNetwork = {
    ...campusNetwork,
    demoStart: { x: 100, y: 200, yaw: 0 },
    allowsDemoMotion: (_from, to) =>
      to.x >= 100 && to.x <= 104 && to.y >= 200 && to.y <= 203,
  };

  it("registers, moves and resets the TELEOP robot in the campus map frame", () => {
    const sim = setup();
    const syntheticPose = sim.state().pose;
    sim.request(forward);
    sim.setCampusNetwork(configuredNetwork);
    expect(sim.state().requested.forward).toBe(0);
    expect(sim.state().campus).toEqual({
      map: campusMap,
      pose: configuredNetwork.demoStart,
      trail: [configuredNetwork.demoStart],
    });
    sim.request(forward);
    sim.advance(500);
    const moved = sim.state().campus;
    expect(moved?.pose.x).toBeCloseTo(100.4);
    expect(moved?.trail.length).toBeGreaterThan(1);
    expect(sim.state().pose).toBe(syntheticPose);
    expect(sim.state().observed.forward).toBeCloseTo(0.8);
    sim.setCampusNetwork(configuredNetwork);
    expect(sim.state().campus).toBe(moved);
    sim.request({ type: "release" });
    sim.advance(1000);
    expect(sim.state().campus).toBe(moved);
    expect(sim.state().observed.forward).toBe(0);
    sim.request({ type: "inject", kind: "field" });
    expect(sim.state().incidents[0]).toMatchObject({
      map: campusMap,
      pose: moved?.pose,
    });
    expect(sim.state().incidents[0].missionId).toBeUndefined();
    sim.request({ type: "reset" });
    expect(sim.state().campus).toMatchObject({
      map: campusMap,
      pose: configuredNetwork.demoStart,
      trail: [configuredNetwork.demoStart],
    });
  });

  it("reports no observed translation when a TELEOP step crosses the campus limit", () => {
    const sim = setup();
    sim.setCampusNetwork({
      ...configuredNetwork,
      allowsDemoMotion: (from, to) => from.x <= 100.3 && to.x <= 100.3,
    });
    sim.request(forward);
    sim.advance(300);
    const pose = sim.state().campus?.pose;
    expect(pose?.x).toBeCloseTo(100.24);
    sim.advance(300);
    expect(sim.state().campus?.pose).toEqual(pose);
    expect(sim.state().requested.forward).toBe(0.8);
    expect(sim.state().observed.forward).toBe(0);
    sim.request({ type: "teleop", forward: 1, left: 0, turn: 1 });
    sim.advance(100);
    expect(sim.state().campus?.pose).toEqual({ ...pose, yaw: 9 });
    expect(sim.state().observed).toMatchObject({
      forward: 0,
      left: 0,
      turn: 90,
    });
  });

  it("runs only campus AUTO in a registered campus map and observes campus motion", () => {
    const sim = setup();
    sim.setCampusNetwork(configuredNetwork);
    sim.request(auto);
    expect(
      sim.request({ type: "start", mission: shortMission() }),
    ).toMatchObject({ ok: false, code: "invalid" });
    sim.request({ type: "start", mission: campusMission() });
    sim.advance(500);
    expect(sim.state().observed.forward).toBeCloseTo(1.5);
    sim.request({ type: "stop" });
    expect(sim.state().observed.forward).toBe(0);
    expect(sim.state().run?.resumePose).toEqual(sim.state().campus?.pose);
  });

  it("rejects resume after off-walkway TELEOP movement and resumes over a validated connector", () => {
    const sim = setup();
    sim.setCampusNetwork(configuredNetwork);
    sim.request(auto);
    sim.request({ type: "start", mission: campusMission() });
    sim.advance(1000);
    const paused = sim.state().campus!.pose;
    sim.request(takeover);
    expect(sim.state().run?.resumePose).toEqual(paused);
    sim.request(strafe(1));
    sim.advance(400);
    sim.request(auto);
    const offWalkway = sim.state().campus!.pose;
    const reason = campusResumeError(sim.state(), configuredNetwork);
    expect(reason).toContain("이어진 보행로");
    expect(sim.request({ type: "resume" })).toMatchObject({
      ok: false,
      code: "blocked",
      reason,
    });
    sim.advance(500);
    expect(sim.state().campus?.pose).toBe(offWalkway);
    expect(sim.state().run?.status).toBe("paused");
    sim.request(takeover);
    sim.request(strafe(-1));
    sim.advance(400);
    sim.request(forward);
    sim.advance(500);
    sim.request(auto);
    const beforeResume = sim.state().campus!.pose;
    expect(beforeResume.x).toBeGreaterThan(paused.x);
    expect(campusResumeError(sim.state(), configuredNetwork)).toBeUndefined();
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
    expect(sim.state().run?.approach?.points[0]).toEqual(paused);
    sim.advance(100);
    expect(sim.state().campus!.pose.x).toBeLessThan(beforeResume.x);
    expect(sim.state().campus!.pose.x).toBeGreaterThan(paused.x);
    sim.advance(9000);
    expect(sim.state().run).toMatchObject({
      status: "completed",
      targetIndex: 3,
    });
  });
});

describe("DEMO incident and recovery transitions", () => {
  it("records grouped alarm occurrences and keeps confirmation, mute, recovery and closure independent", () => {
    const sim = setup();
    sim.request(auto);
    sim.request({ type: "start", mission: shortMission() });
    sim.request({ type: "inject", kind: "lost" });
    const incident = sim.state().incidents[0];
    expect(incident).toMatchObject({
      openedAt: 1000,
      count: 1,
      severity: "critical",
      waypointId: "first",
    });
    sim.advance(200);
    sim.request({ type: "inject", kind: "lost" });
    sim.request({ type: "acknowledge", incidentId: incident.id });
    sim.request({ type: "mute", incidentId: incident.id });
    sim.request({
      type: "note",
      incidentId: incident.id,
      text: " 위치 로그 확인 ",
    });
    expect(sim.state().incidents).toHaveLength(1);
    expect(sim.state().incidents[0]).toMatchObject({
      count: 2,
      lastAt: 1200,
      acknowledgedAt: 1200,
      mutedAt: 1200,
    });
    expect(
      sim.request({ type: "close", incidentId: incident.id }),
    ).toMatchObject({ ok: false });
    expect(sim.request({ type: "resume" })).toMatchObject({
      ok: false,
      code: "blocked",
    });
    sim.request({ type: "recover", kind: "lost" });
    expect(sim.state()).toMatchObject({
      localization: "TRACKING",
      run: { status: "paused" },
    });
    expect(
      sim.request({ type: "close", incidentId: incident.id }),
    ).toMatchObject({ ok: true });
    expect(sim.state().incidents[0].history.map(({ type }) => type)).toEqual([
      "opened",
      "repeated",
      "acknowledged",
      "muted",
      "note",
      "resolved",
      "closed",
    ]);
    expect(sim.request({ type: "resume" })).toMatchObject({ ok: true });
  });

  it("keeps connection and localization independent and preserves last received data when stale", () => {
    const sim = setup();
    sim.request(forward);
    sim.advance(200);
    sim.request({ type: "inject", kind: "disconnect" });
    sim.advance(2000);
    expect(sim.state()).toMatchObject({
      connected: false,
      lastReceived: 1200,
      localization: "TRACKING",
    });
    expect(sim.request(forward)).toMatchObject({ ok: false, code: "blocked" });
    expect(sim.request(auto)).toMatchObject({ ok: false, code: "blocked" });
    sim.request({ type: "inject", kind: "timeout" });
    sim.request({ type: "recover", kind: "disconnect" });
    expect(sim.state()).toMatchObject({
      connected: true,
      lastReceived: 1200,
      localization: "INPUT_TIMEOUT",
    });
    sim.advance(200);
    sim.request({ type: "recover", kind: "timeout" });
    expect(sim.state()).toMatchObject({
      connected: true,
      lastReceived: 3400,
      localization: "TRACKING",
      requested: { forward: 0 },
    });
  });

  it("continues for degraded and field events, pauses for obstacle, and fails for low battery", () => {
    const sim = setup();
    sim.request(auto);
    sim.request({ type: "start", mission: shortMission() });
    sim.request({ type: "inject", kind: "degraded" });
    sim.request({ type: "inject", kind: "field" });
    expect(sim.state()).toMatchObject({
      localization: "DEGRADED",
      run: { status: "running" },
    });
    sim.request({ type: "inject", kind: "obstacle" });
    expect(sim.state().run?.status).toBe("paused");
    expect(commandBlock(sim.state(), "AUTO")).toContain("장애물");
    expect(commandBlock(sim.state(), "TELEOP")).toBeUndefined();
    sim.request(takeover);
    sim.request({ type: "inject", kind: "battery" });
    expect(sim.state()).toMatchObject({
      battery: 8,
      run: { status: "failed" },
    });
    sim.request({ type: "recover", kind: "battery" });
    expect(sim.state()).toMatchObject({
      battery: 96,
      run: { status: "failed" },
    });
  });
});
