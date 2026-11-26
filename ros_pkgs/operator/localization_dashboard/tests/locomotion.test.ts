// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from "vitest";
import { parse } from "@foxglove/rosmsg";
import { MessageWriter } from "@foxglove/rosmsg2-serialization";
import {
  csv,
  defaults,
  locomotionStates,
  locomotionStatus,
} from "../src/model";
import { Telemetry } from "../src/store";
import { connect } from "../src/bridge";
// hn_interfaces/msg/LocomotionStatus as foxglove_bridge advertises it (ros2msg with dependencies).
const schema = `std_msgs/Header header
uint8 CODE_INITIALIZING = 0
uint8 CODE_STANDING = 1
uint8 CODE_WALKING = 2
uint8 CODE_TILTING = 3
uint8 CODE_SLIPPING = 4
uint8 CODE_FALLEN = 5
uint8 CODE_STALE_INPUT = 6
uint8 SEVERITY_OK = 0
uint8 SEVERITY_WARN = 1
uint8 SEVERITY_ERROR = 2
uint8 SEVERITY_STALE = 3
uint8 code
string state
uint8 severity
string reason
float32 since_s
string robot_id
float64 sim_time_s
float32 tilt_deg
float32 roll_deg
float32 pitch_deg
float32 speed_mps
float32 height_m
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
`;
const report = (over: Record<string, unknown> = {}) => ({
  header: { stamp: { sec: 1_763_600_000, nanosec: 0 }, frame_id: "" },
  code: 2,
  state: "WALKING",
  severity: 0,
  reason: "moving",
  since_s: 1.5,
  robot_id: "hn_v1_hyper",
  sim_time_s: 2,
  tilt_deg: 3,
  roll_deg: 1,
  pitch_deg: -2,
  speed_mps: 0.6,
  height_m: NaN,
  ...over,
});
const odom = (t: number) => ({
  header: { stamp: { sec: t, nanosec: 0 }, frame_id: defaults.frame },
  child_frame_id: defaults.base,
  pose: {
    pose: {
      position: { x: 0, y: 0, z: 0 },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
  },
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
describe("G-006 locomotion status", () => {
  it("subscribes to the agreed topic by default", () => {
    expect(defaults.locomotion).toBe("/locomotion/status");
  });
  it.each(locomotionStates.map((label, code) => ({ label, code })))(
    "names code $code as $label",
    ({ label, code }) => {
      expect(
        locomotionStatus(report({ code, state: label }), 0),
      ).toMatchObject({ code, label, issue: undefined });
    },
  );
  it("prefers SIM time, keeps NaN as unknown and flags inconsistent payloads", () => {
    const g = locomotionStatus(report(), 10);
    expect(g).toMatchObject({
      t: 2,
      timeSource: "sim_time_s",
      severityLabel: "OK",
      speed: 0.6,
      height: undefined,
    });
    const real = locomotionStatus(report({ sim_time_s: NaN }), 10);
    expect(real.timeSource).toBe("header.stamp");
    expect(real.t).toBe(1_763_600_000);
    expect(locomotionStatus(report({ code: 9 }), 0).label).toBe("UNKNOWN(9)");
    expect(locomotionStatus(report({ state: "FALLEN" }), 0).issue).toContain(
      "FALLEN",
    );
    expect(locomotionStatus({}, 0).label).toBe("필드 확인 필요");
  });
  it("pairs Logger rows with the latest report at or before their time", () => {
    const s = new Telemetry();
    s.ingest("locomotion", report({ sim_time_s: 1.8 }));
    s.ingest("lio", odom(2));
    expect(s.current?.locomotion?.label).toBe("WALKING");
    s.ingest("lio", odom(3));
    expect(s.current?.locomotion).toBeUndefined();
    s.ingest(
      "locomotion",
      report({ code: 5, state: "FALLEN", severity: 2, sim_time_s: 2.9 }),
    );
    expect(s.current?.locomotion?.label).toBe("FALLEN");
    expect(s.rows[0].locomotion?.label).toBe("WALKING");
    expect(s.events.at(-1)?.event).toBe("보행 상태: FALLEN (moving)");
    const out = csv(s.rows, s.events, s.statuses, s.gait);
    expect(out).toContain('"locomotion_status"');
    expect(out).toContain('"sim_time_s"');
  });
  it("never pairs wall-clock stamps with SIM-time odometry", () => {
    const s = new Telemetry();
    s.ingest("locomotion", report({ sim_time_s: NaN }));
    s.ingest("lio", odom(2));
    expect(s.locomotion?.label).toBe("WALKING");
    expect(s.current?.locomotion).toBeUndefined();
  });
  it("decodes the advertised CDR message through the bridge and keeps it latched", () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "WebSocket",
      class {
        static latest: any;
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
            id: 3,
            topic: "/locomotion/status",
            encoding: "cdr",
            schemaEncoding: "ros2msg",
            schemaName: "hn_interfaces/msg/LocomotionStatus",
            schema,
          },
        ],
      }),
    });
    expect(s.error).toBe("");
    const sub = JSON.parse(socket.sent[0]).subscriptions[0];
    const payload = new MessageWriter(
      parse(schema, { ros2: true }),
    ).writeMessage(report({ code: 3, state: "TILTING", severity: 1 }));
    const wire = new Uint8Array(13 + payload.length);
    wire[0] = 1;
    new DataView(wire.buffer).setUint32(1, sub.id, true);
    wire.set(payload, 13);
    socket.onmessage?.({ data: wire.buffer });
    expect(s.locomotion).toMatchObject({
      label: "TILTING",
      severityLabel: "WARN",
      robotId: "hn_v1_hyper",
      t: 2,
    });
    expect(s.latched.has("/locomotion/status")).toBe(true);
    stop();
    delete (globalThis as any).__socket;
  });
});
