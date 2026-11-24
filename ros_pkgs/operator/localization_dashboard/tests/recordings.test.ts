// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  findRecord,
  RecordingLibrary,
  replayTelemetry,
  setRecordedDuration,
} from "../src/recordings";

afterEach(() => vi.useRealTimers());

describe("operation recording timelines", () => {
  it("seeks to a bundled video incident and never displays a future sample", () => {
    const library = new RecordingLibrary();
    const found = findRecord(library.getSnapshot(), {
      incidentId: "example-campus-inspection",
    });
    expect(found?.offsetMs).toBe(5000);
    const record = found!.record;
    const telemetry = replayTelemetry(record);
    expect(record.video).toMatchObject({
      status: "ready",
      offsetMs: 0,
      durationMs: 12000,
    });
    expect(telemetry.sampleAt(-1)).toBeUndefined();
    expect(telemetry.sampleAt(4999)?.incidents).toEqual([]);
    expect(telemetry.sampleAt(5000)?.incidents).toEqual(["데모 시설 이상"]);
    expect(telemetry.sampleAt(10000)?.phase).toBe("완료");
  });

  it("keeps session identity, record identity and ROS time independent", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    const library = new RecordingLibrary();
    const first = library.start({
      source: "ROS LIVE",
      sessionId: "example-ros-session",
      timeOrigin: Date.now(),
    });
    library.capture({ at: 1_000_010, rosTimeSeconds: 91.4 });
    library.capture({ at: 999_000, rosTimeSeconds: 1.1 });
    library.mark({
      at: 1_000_500,
      id: "signal-loss",
      title: "통신 끊김",
      incidentId: "incident-1234",
    });
    library.mark({
      at: 1_000_700,
      id: "signal-loss",
      title: "통신 끊김",
      incidentId: "incident-1234",
    });
    vi.setSystemTime(1_001_000);
    library.stop();
    const second = library.start({
      source: "ROS LIVE",
      sessionId: "example-ros-session",
      timeOrigin: Date.now(),
    });

    expect(first).not.toBe(second);
    expect(
      library.getSnapshot().filter((record) => record.active),
    ).toHaveLength(1);
    const result = findRecord(library.getSnapshot(), {
      sessionId: "example-ros-session",
      incidentId: "incident-1234",
    });
    expect(result?.record).toMatchObject({
      id: first,
      source: "ROS LIVE",
      timeOrigin: 1_000_000,
      durationMs: 1000,
      video: { status: "missing" },
    });
    expect(result?.offsetMs).toBe(500);
    expect(result?.record.events).toHaveLength(1);
    expect(replayTelemetry(result!.record).sampleAt(500)?.rosTimeSeconds).toBe(
      91.4,
    );
    expect(
      findRecord(library.getSnapshot(), {
        recordId: second,
        incidentId: "incident-1234",
      }),
    ).toBeUndefined();
    library.dispose();
  });

  it("preserves status transitions inside the telemetry sampling interval", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    const library = new RecordingLibrary();
    library.start({ source: "ROS LIVE", timeOrigin: Date.now() });
    library.capture({ at: 1_000_000, localization: "TRACKING" });
    library.capture({ at: 1_000_020, localization: "TRACKING" });
    library.capture({ at: 1_000_080, localization: "LOST" });
    library.capture({ at: 1_000_060, localization: "TRACKING" });
    const record = library.getSnapshot()[0];
    expect(record.samples).toHaveLength(2);
    expect(replayTelemetry(record).sampleAt(79)?.localization).toBe("TRACKING");
    expect(replayTelemetry(record).sampleAt(80)?.localization).toBe("LOST");
    library.dispose();
  });

  it("archives on source changes and caps the duration of an active recording", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    const library = new RecordingLibrary();
    const first = library.start({ source: "ROS LIVE", timeOrigin: Date.now() });
    expect(
      library.start({ source: "ROS LIVE", timeOrigin: Date.now() }),
    ).toBeUndefined();
    library.reset();
    expect(
      findRecord(library.getSnapshot(), { recordId: first })?.record,
    ).toMatchObject({
      active: false,
      stopReason: "운용 세션 변경",
    });
    const second = library.start({
      source: "ROS LIVE",
      timeOrigin: Date.now(),
    });
    vi.advanceTimersByTime(240_000);
    expect(
      findRecord(library.getSnapshot(), { recordId: second })?.record,
    ).toMatchObject({
      active: false,
      durationMs: 240_000,
      stopReason: "최대 기록 길이 4분 도달",
    });
    library.dispose();
  });
});

describe("recorded WebM duration", () => {
  const header = (info: number[]) => [
    0x1a,
    0x45,
    0xdf,
    0xa3,
    0x80, // EBML header
    0x18,
    0x53,
    0x80,
    0x67,
    0xff, // streaming Segment (unknown size)
    0x15,
    0x49,
    0xa9,
    0x66,
    0x80 | info.length,
    ...info,
  ];

  it("fills the zero-duration placeholder without moving other elements", async () => {
    const bytes = new Uint8Array(
      header([0x44, 0x89, 0x88, 0, 0, 0, 0, 0, 0, 0, 0]),
    );
    const clip = new Blob([bytes], { type: "video/webm;codecs=vp8" });
    const updated = await setRecordedDuration(clip, 2510);
    expect(updated.size).toBe(bytes.length);
    expect(new DataView(await updated.arrayBuffer()).getFloat64(18)).toBe(2510);
  });

  it("adds a duration to an unindexed segment with a custom timestamp scale", async () => {
    const bytes = new Uint8Array(
      header([0x2a, 0xd7, 0xb1, 0x83, 0x1e, 0x84, 0x80]),
    );
    const clip = new Blob([bytes], { type: "video/webm" });
    const updated = await setRecordedDuration(clip, 2400);
    expect(updated.size).toBe(bytes.length + 11);
    const view = new DataView(await updated.arrayBuffer());
    expect(view.getUint8(14)).toBe(0x80 | 18);
    expect(view.getFloat64(25)).toBe(1200);
  });
});
