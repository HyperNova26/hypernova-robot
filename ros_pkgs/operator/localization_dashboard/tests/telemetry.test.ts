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
    ).toBe(0);
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
    expect(lines.map((x) => x.split(",").length)).toEqual([27, 27, 27]);
  });
});
