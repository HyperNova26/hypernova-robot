// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from "vitest";
import {
  defaults,
  sample,
  pointCloud,
  rpy,
  csv,
  type Pose,
} from "../src/model";
import { Telemetry } from "../src/store";
const p = (t = 1, x = 0): Pose => ({
  t,
  frame: "pair360_map",
  child: "mlx_lidar",
  p: { x, y: 0, z: 0 },
  q: { x: 0, y: 0, z: 0, w: 1 },
  v: { x: 0, y: 0, z: 0 },
});
const msg = (t: number, x = 0) => ({
  header: {
    stamp: { sec: Math.floor(t), nanosec: Math.round((t % 1) * 1e9) },
    frame_id: "pair360_map",
  },
  child_frame_id: "mlx_lidar",
  pose: {
    pose: {
      position: { x, y: 0, z: 0 },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
  },
});
describe("coordinate, time and velocity contract", () => {
  it("computes 3D error only for matching time, parent and child", () => {
    const gt = { ...p(), p: { x: 3, y: 4, z: 12 } };
    expect(sample(p(), undefined, gt, defaults, 1).error).toBe(13);
    for (const invalid of [
      { ...gt, t: 2 },
      { ...gt, frame: "world" },
      { ...gt, child: "imu_link" },
    ])
      expect(
        sample(p(), undefined, invalid, defaults, 1).error,
      ).toBeUndefined();
    expect(
      sample(p(), undefined, undefined, { ...defaults, gt: "" }, 1).error,
    ).toBeUndefined();
  });
  it("uses the LIO twist in the child frame, rotated into the map", () => {
    // Yaw 90 deg: body +x is map +y. 1.5 m/s forward plus 2 m/s up must give 1.5 m/s horizontal.
    const yaw = Math.PI / 2;
    const moving: Pose = {
      ...p(1, 0),
      q: { x: 0, y: 0, z: Math.sin(yaw / 2), w: Math.cos(yaw / 2) },
      v: { x: 1.5, y: 0, z: 2 },
    };
    const s = sample(moving, p(0.5, 0), undefined, defaults, 1);
    expect(s.speed).toBeCloseTo(1.5);
    expect(s.speedSource).toBe("LIO twist 선속도");
    // Pitched body: forward velocity is partly vertical in the map.
    const pitch = Math.PI / 6;
    const climbing: Pose = {
      ...p(1, 0),
      q: { x: 0, y: -Math.sin(pitch / 2), z: 0, w: Math.cos(pitch / 2) },
      v: { x: 1, y: 0, z: 0 },
    };
    expect(
      sample(climbing, undefined, undefined, defaults, 1).speed,
    ).toBeCloseTo(Math.cos(pitch));
  });
  it("falls back to pose differences when twist is left at zero", () => {
    const s = sample(p(1, 2), p(0.5, 1), undefined, defaults, 1);
    expect(s.speed).toBe(2);
    expect(s.speedSource).toBe("pose 차분 (twist 미기재)");
    expect(
      sample(
        p(1, 2),
        p(0.5, 1),
        undefined,
        { ...defaults, twistValid: false },
        1,
      ).speedSource,
    ).toBe("pose 차분");
  });
  it("does not interpret unfilled twist as zero speed", () => {
    expect(sample(p(1, 2), p(0.5, 1), undefined, defaults, 1).speed).toBe(2);
    expect(
      sample(p(), undefined, undefined, defaults, 1).speed,
    ).toBeUndefined();
    expect(sample(p(), p(), undefined, defaults, 1).speed).toBeUndefined();
    expect(
      sample(
        p(1, 2),
        p(0.5, 1),
        undefined,
        { ...defaults, twistValid: true },
        1,
      ).speed,
    ).toBe(2); // all-zero twist = unfilled, so pose difference is used
  });
  it("converts quaternion to yaw degrees", () => {
    expect(rpy({ x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 }).z).toBeCloseTo(
      90,
    );
  });
});
describe("PointCloud2 binary decoding", () => {
  it.each([false, true])(
    "respects endian=%s, row padding, fields and NaNs",
    (big) => {
      const b = new Uint8Array(64);
      const v = new DataView(b.buffer);
      for (const [o, x, y, z] of [
        [0, 1, 2, 3],
        [32, 4, 5, 6],
      ]) {
        v.setFloat32(o + 4, x, !big);
        v.setFloat32(o + 8, y, !big);
        v.setFloat32(o + 12, z, !big);
      }
      const m = {
        header: { stamp: { sec: 1 }, frame_id: "lidar" },
        width: 1,
        height: 2,
        point_step: 16,
        row_step: 32,
        is_bigendian: big,
        fields: ["x", "y", "z"].map((name, i) => ({
          name,
          offset: 4 + i * 4,
          datatype: 7,
        })),
        data: b,
      };
      expect([...pointCloud(m).points]).toEqual([1, 2, 3, 4, 5, 6]);
      v.setFloat32(36, NaN, !big);
      expect([...pointCloud(m).points]).toEqual([1, 2, 3]);
      expect(() => pointCloud({ ...m, data: b.slice(0, 8) })).toThrow();
    },
  );
});
describe("collection and lifecycle", () => {
  it("matches delayed GT and preserves measurement timestamps", () => {
    const s = new Telemetry();
    s.ingest("lio", msg(2, 1));
    expect(s.current?.error).toBeUndefined();
    s.ingest("gt", msg(2, 1.1));
    expect(s.current?.error).toBeCloseTo(0.1);
    expect(s.current?.t).toBe(2);
  });
  it("records receive interruption and recovery using wall time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(10000);
    const s = new Telemetry();
    s.ingest("lio", msg(1));
    expect(s.receiving).toBe(true);
    vi.advanceTimersByTime(1600);
    s.tick();
    expect(s.receiving).toBe(false);
    expect(s.events.at(-1)?.event).toBe("수신 중단");
    s.ingest("lio", msg(2));
    expect(s.receiving).toBe(true);
    expect(s.events.at(-1)?.event).toBe("수신 재개");
    vi.useRealTimers();
  });
  it("resets the session on a backwards /clock jump", () => {
    const s = new Telemetry();
    s.ingest("clock", { clock: { sec: 20 } });
    s.ingest("lio", msg(20));
    s.ingest("clock", { clock: { sec: 1 } });
    expect(s.rows).toHaveLength(0);
    expect(s.events.at(-1)?.event).toBe("SIM 시각 재설정");
  });
  it("rejects out of order odometry and bounds history", () => {
    const s = new Telemetry();
    s.ingest("lio", msg(2));
    s.ingest("lio", msg(1));
    expect(s.rows).toHaveLength(1);
    for (let i = 3; i < 6010; i++) s.ingest("lio", msg(i));
    expect(s.rows).toHaveLength(6000);
    expect(s.lio).toHaveLength(6000);
  });
  it("CSV preserves GT, frame, missing values and events without fabricating zero", () => {
    const s = sample(p(), undefined, undefined, defaults, 123);
    const output = csv([s], [{ t: 2, event: "수신 중단" }]);
    expect(output).toContain('"gt_error_m"');
    expect(output).toContain('"gt_time_delta_s"');
    expect(output).toContain('"pair360_map","mlx_lidar"');
    expect(output).toContain('"event","2"');
    expect(output).not.toContain("undefined");
    const lines = output.trim().split("\r\n");
    // 27 localization columns + 13 G-006 locomotion columns
    expect(lines.map((x) => x.split(",").length)).toEqual([40, 40, 40]);
  });
});
