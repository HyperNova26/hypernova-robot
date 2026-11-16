// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from "vitest";
import {
  defaults,
  localizationStatus,
  localizationStates,
  csv,
  type Pose,
} from "../src/model";
import { Telemetry } from "../src/store";
import { FrameTransforms } from "../src/transforms";
const h = (t = 2) => ({
  stamp: { sec: t, nanosec: 0 },
  frame_id: defaults.frame,
});
const odom = (child = defaults.base) => ({
  header: h(),
  child_frame_id: child,
  pose: {
    pose: {
      position: { x: 10, y: 0, z: 0 },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
  },
});
describe("S-005 localization contract", () => {
  it("uses common topics and explicitly targets the LiDAR origin", () => {
    expect(defaults).toMatchObject({
      frame: "pair360_map",
      base: "mlx_lidar",
      lio: "/localization/odometry",
      status: "/localization/status",
      prior: "/localization/reference_map",
      scan: "/lidar/points",
      gt: "",
    });
    expect("camera" in defaults).toBe(false);
  });
  it.each(localizationStates.map((label, code) => ({ label, code })))(
    "preserves code $code as $label without inventing thresholds",
    ({ label, code }) => {
      expect(
        localizationStatus({ header: h(), status: code }, "status", 100),
      ).toMatchObject({ code, label, t: 2 });
    },
  );
  it("supports configured nested fields but never guesses missing or unknown codes", () => {
    expect(
      localizationStatus({ state: { value: 2 } }, "state.value", 10).label,
    ).toBe("DEGRADED");
    expect(localizationStatus({ state: 1 }, "status", 10).code).toBeUndefined();
    expect(
      localizationStatus({ status: "1" }, "status", 10).code,
    ).toBeUndefined();
    expect(localizationStatus({ status: 9 }, "status", 10).label).toBe(
      "UNKNOWN(9)",
    );
    expect(localizationStatus({ status: 1 }, "status", 10).t).toBeUndefined();
  });
  it("keeps received algorithm state separate from odometry reception and expiry", () => {
    vi.useFakeTimers();
    vi.setSystemTime(10000);
    const s = new Telemetry();
    s.ingest("status", { header: h(), status: 3 });
    s.ingest("lio", odom());
    expect(s.receiving).toBe(true);
    expect(s.current?.localization?.label).toBe("LOST");
    vi.advanceTimersByTime(1600);
    s.tick();
    expect(s.receiving).toBe(false);
    expect(s.localization?.label).toBe("LOST");
    vi.useRealTimers();
  });
  it("matches late status by measurement time and does not mutate frozen Logger rows", () => {
    const s = new Telemetry();
    s.ingest("lio", odom());
    const frozen = s.rows[0];
    s.ingest("status", { header: h(), status: 2 });
    expect(s.current?.localization?.label).toBe("DEGRADED");
    expect(frozen.localization).toBeUndefined();
    s.ingest("status", { header: h(9), status: 1 });
    expect(s.current?.localization?.label).toBe("DEGRADED");
    const output = csv(s.rows, s.events, s.statuses);
    expect(output).toContain('"localization_status"');
    expect(output).toContain('"DEGRADED"');
    expect(output).toContain("localization_payload_json");
  });
  it("never compares body GT with a LiDAR estimate without the extrinsic transform", () => {
    const s = new Telemetry();
    s.ingest("gt", odom("base_link"));
    s.ingest("lio", odom());
    expect(s.current?.error).toBeUndefined();
    expect(s.current?.reason).toBe("비교 기준점 불일치");
  });
});
describe("measurement-time point cloud transforms", () => {
  const frames = new FrameTransforms();
  const pose: Pose = {
    t: 2,
    frame: defaults.frame,
    child: defaults.base,
    p: { x: 10, y: 0, z: 0 },
    q: { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 },
  };
  it("transforms a raw LiDAR scan using the parent-child odometry relation", () => {
    frames.odometry(pose);
    const c = {
      t: 2,
      frame: defaults.base,
      points: new Float32Array([1, 0, 0]),
    };
    const out = frames.cloud(c, defaults.frame)!;
    expect([...out.points]).toEqual([10, 1, 0]);
    expect(out.frame).toBe(defaults.frame);
    expect(frames.cloud(c, defaults.frame)).toBe(out);
    expect(frames.cloud({ ...c, t: 3 }, defaults.frame)).toBeUndefined();
    expect(
      frames.cloud({ ...c, frame: "unknown" }, defaults.frame),
    ).toBeUndefined();
  });
  it("chains static sensor extrinsics with dynamic TF and supports inverse transforms", () => {
    const f = new FrameTransforms();
    f.ingest({
      transforms: [
        {
          header: h(),
          child_frame_id: defaults.base,
          transform: { translation: pose.p, rotation: pose.q },
        },
      ],
    });
    f.ingest(
      {
        transforms: [
          {
            header: { ...h(), frame_id: defaults.base },
            child_frame_id: "sensor",
            transform: {
              translation: { x: 1, y: 0, z: 0 },
              rotation: { x: 0, y: 0, z: 0, w: 1 },
            },
          },
        ],
      },
      true,
    );
    const cloud = f.cloud(
      { t: 2, frame: "sensor", points: new Float32Array([1, 0, 0]) },
      defaults.frame,
    )!;
    expect([...cloud.points]).toEqual([10, 2, 0]);
    expect([...f.cloud(cloud, "sensor")!.points]).toEqual([1, 0, 0]);
    f.clear(true);
    expect(f.lookup(defaults.base, "sensor", 99)).toBeDefined();
    expect(f.lookup(defaults.frame, defaults.base, 2)).toBeUndefined();
  });
  it("accepts a reference map sent once and keeps it as time advances", () => {
    const s = new Telemetry(),
      data = new Uint8Array(12);
    new DataView(data.buffer).setFloat32(0, 1, true);
    s.ingest("prior", {
      header: h(0),
      width: 1,
      height: 1,
      point_step: 12,
      row_step: 12,
      fields: ["x", "y", "z"].map((name, i) => ({
        name,
        offset: i * 4,
        datatype: 7,
      })),
      data,
      is_bigendian: false,
    });
    s.ingest("clock", { clock: { sec: 100 } });
    expect(s.prior?.frame).toBe(defaults.frame);
    expect(s.prior?.points[0]).toBe(1);
  });
});
