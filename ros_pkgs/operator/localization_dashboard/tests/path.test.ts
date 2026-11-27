// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// S-012 global path: nav_msgs/Path (Nav2 planner_server /plan) shown on the map.
import { afterEach, describe, expect, it, vi } from "vitest";
import { parse } from "@foxglove/rosmsg";
import { MessageWriter } from "@foxglove/rosmsg2-serialization";
import { defaults, globalPath } from "../src/model";
import { Telemetry } from "../src/store";
import { connect } from "../src/bridge";
const schema = `std_msgs/Header header
geometry_msgs/PoseStamped[] poses
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
================================================================================
MSG: geometry_msgs/PoseStamped
std_msgs/Header header
geometry_msgs/Pose pose
================================================================================
MSG: geometry_msgs/Pose
geometry_msgs/Point position
geometry_msgs/Quaternion orientation
================================================================================
MSG: geometry_msgs/Point
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/Quaternion
float64 x
float64 y
float64 z
float64 w
`;
const header = (frame_id: string) => ({
  stamp: { sec: 12, nanosec: 0 },
  frame_id,
});
const plan = {
  header: header("pair360_map"),
  poses: [
    [-16.7, 123.4, -0.15],
    [-16.0, 140.0, 0.2],
    [21.9, 184.4, 5.96],
  ].map(([x, y, z]) => ({
    header: header("pair360_map"),
    pose: {
      position: { x, y, z },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
  })),
};
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
describe("S-012 global path", () => {
  it("defaults to the Nav2 planner topic", () => {
    expect(defaults.path).toBe("/plan");
  });
  it("keeps every pose position in the path's frame", () => {
    const p = globalPath(plan);
    expect(p.frame).toBe("pair360_map");
    expect(p.t).toBe(12);
    expect([...p.points]).toEqual(
      [-16.7, 123.4, -0.15, -16, 140, 0.2, 21.9, 184.4, 5.96].map(Math.fround),
    );
    expect(globalPath({ header: header("map"), poses: [] }).points).toHaveLength(0);
  });
  it("replaces the path on each message and clears it on reset", () => {
    const s = new Telemetry();
    s.ingest("path", plan);
    expect(s.plan?.points.length).toBe(9);
    s.ingest("path", { ...plan, poses: plan.poses.slice(0, 1) });
    expect(s.plan?.points.length).toBe(3);
    s.reset();
    expect(s.plan).toBeUndefined();
  });
  it("subscribes to nav_msgs/Path through the bridge and decodes the CDR", () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "WebSocket",
      class {
        sent: string[] = [];
        onmessage?: (e: any) => void;
        constructor() {
          (globalThis as any).__socket = this;
        }
        close() {}
        send(d: string) {
          this.sent.push(d);
        }
      },
    );
    const s = new Telemetry();
    const stop = connect(s);
    const socket = (globalThis as any).__socket;
    socket.onmessage?.({
      data: JSON.stringify({
        op: "advertise",
        channels: [
          {
            id: 5,
            topic: "/plan",
            encoding: "cdr",
            schemaEncoding: "ros2msg",
            schemaName: "nav_msgs/msg/Path",
            schema,
          },
        ],
      }),
    });
    expect(s.error).toBe("");
    const sub = JSON.parse(socket.sent[0]).subscriptions[0];
    const payload = new MessageWriter(parse(schema, { ros2: true })).writeMessage(
      plan,
    );
    const wire = new Uint8Array(13 + payload.length);
    wire[0] = 1;
    new DataView(wire.buffer).setUint32(1, sub.id, true);
    wire.set(payload, 13);
    socket.onmessage?.({ data: wire.buffer });
    expect(s.error).toBe("");
    expect(s.plan?.frame).toBe("pair360_map");
    expect(s.plan?.points[3 * 2 + 1]).toBeCloseTo(184.4);
    stop();
    delete (globalThis as any).__socket;
  });
});
