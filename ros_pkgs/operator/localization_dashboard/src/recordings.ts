// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
/// <reference types="vite/client" />
import { useEffect, useState, useSyncExternalStore } from "react";
import type { TelemetrySource } from "./sources";

export type RecordingSource = "DEMO" | "ROS LIVE";
export type RecordingPose = { x: number; y: number; yaw: number };
export type RecordingSample = {
  at: number;
  pose?: RecordingPose;
  coordinateFrame?: string;
  mode?: "TELEOP" | "AUTO";
  phase?: string;
  mission?: string;
  waypoint?: string;
  localization?: string;
  incidents?: string[];
  cameraAvailable?: boolean;
  rosTimeSeconds?: number;
};
export type RecordingEvent = {
  id: string;
  at: number;
  title: string;
  incidentId?: string;
};
type RecordingInput = {
  source: RecordingSource;
  timeOrigin: number;
  sessionId?: string;
  mission?: string;
  pose?: RecordingPose;
};
type RecordingVideo =
  | { status: "processing" }
  | { status: "missing"; reason: string }
  | { status: "error"; reason: string }
  | {
      status: "ready";
      url: string;
      offsetMs: number;
      durationMs: number;
      camera: "합성 시연 카메라";
    };
export type OperationRecording = {
  id: string;
  sessionId: string;
  timeOrigin: number;
  source: RecordingSource;
  mission?: string;
  missions: string[];
  durationMs: number;
  samples: RecordingSample[];
  events: RecordingEvent[];
  video: RecordingVideo;
  active: boolean;
  stopReason?: string;
  example?: boolean;
};
export type RecordSelection = {
  recordId?: string;
  sessionId?: string;
  incidentId?: string;
  at?: number;
};

const captureWidth = 480;
const captureHeight = 270;
const captureFps = 12;
const captureLimitMs = 4 * 60 * 1000;
const sampleIntervalMs = 200;
const recordLimit = 12;
const markerLimit = 200;
const syntheticCamera = "합성 시연 카메라" as const;

const demoEpoch = Date.UTC(2026, 10, 24, 0);
const demoSeconds = 12;
const demoIncident = "example-campus-inspection";

function sampleDemoPatrol(second: number): RecordingSample {
  const travel = Math.min(second, 10);
  return {
    at: demoEpoch + second * 1000,
    pose: { x: -3 + 0.7 * travel, y: -2 + 0.22 * travel, yaw: 0.3045 },
    mode: "AUTO",
    phase: second < 10 ? "실행" : "완료",
    mission: "캠퍼스 시설 순찰",
    waypoint: second < 5 ? "산책로" : "시설 점검 지점",
    localization: "TRACKING",
    incidents: second < 5 ? [] : ["데모 시설 이상"],
  };
}

const exampleRecording: OperationRecording = {
  id: "sample-patrol-video",
  sessionId: "sample-campus-patrol",
  timeOrigin: demoEpoch,
  source: "DEMO",
  mission: "캠퍼스 시설 순찰",
  missions: ["캠퍼스 시설 순찰"],
  durationMs: demoSeconds * 1000,
  active: false,
  example: true,
  samples: Array.from({ length: demoSeconds * 5 + 1 }, (_, i) =>
    sampleDemoPatrol(i / 5),
  ),
  events: [
    { id: "sample-start", at: demoEpoch, title: "예제 순찰 시작" },
    {
      id: "sample-incident",
      at: demoEpoch + 5000,
      title: "데모 시설 이상",
      incidentId: demoIncident,
    },
    { id: "sample-done", at: demoEpoch + 10000, title: "예제 순찰 완료" },
  ],
  video: {
    status: "ready",
    url: `${import.meta.env.BASE_URL}demo-patrol.webm`,
    offsetMs: 0,
    durationMs: demoSeconds * 1000,
    camera: syntheticCamera,
  },
};

export function replayTelemetry(
  record: OperationRecording,
): Extract<TelemetrySource, { kind: "REPLAY" }> {
  return {
    kind: "REPLAY",
    sampleAt(offsetMs) {
      // A future sample can contain a different mode, incident, or target.
      const at = record.timeOrigin + offsetMs;
      let left = 0;
      let right = record.samples.length;
      while (left < right) {
        const mid = Math.floor((left + right) / 2);
        if (record.samples[mid].at <= at) left = mid + 1;
        else right = mid;
      }
      return record.samples[left - 1];
    },
  };
}

export function findRecord(
  records: readonly OperationRecording[],
  selection?: RecordSelection,
): { record: OperationRecording; offsetMs: number } | undefined {
  if (!selection) return undefined;
  const matches = records.filter(
    (record) =>
      (!selection.recordId || record.id === selection.recordId) &&
      (!selection.sessionId || record.sessionId === selection.sessionId),
  );
  if (selection.incidentId) {
    const markers = matches.flatMap((record) =>
      record.events.flatMap((event) =>
        event.incidentId === selection.incidentId
          ? [{ record, at: event.at }]
          : [],
      ),
    );
    const order = (at: number) =>
      selection.at === undefined ? at : Math.abs(at - selection.at);
    const hit = markers.sort((a, b) => order(a.at) - order(b.at))[0];
    return (
      hit && { record: hit.record, offsetMs: hit.at - hit.record.timeOrigin }
    );
  }
  const at = selection.at;
  const record =
    (at === undefined
      ? undefined
      : matches.find(
          (item) =>
            item.timeOrigin <= at && at <= item.timeOrigin + item.durationMs,
        )) ?? matches[0];
  if (!record) return undefined;
  const offsetMs = at === undefined ? 0 : at - record.timeOrigin;
  return {
    record,
    offsetMs: Math.max(0, Math.min(record.durationMs, offsetMs)),
  };
}

export function drawSyntheticCamera(
  canvas: HTMLCanvasElement,
  pose: RecordingPose | undefined,
  elapsedMs?: number,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const { width, height } = canvas;
  ctx.save();
  ctx.scale(width / captureWidth, height / captureHeight);
  ctx.fillStyle = "#192c3e";
  ctx.fillRect(0, 0, captureWidth, 113);
  ctx.fillStyle = "#263d40";
  ctx.fillRect(0, 113, captureWidth, captureHeight - 113);
  const project = (x: number, y: number) => {
    const dx = x - (pose?.x ?? 0);
    const dy = y - (pose?.y ?? 0);
    const yaw = pose?.yaw ?? 0;
    const depth = Math.cos(yaw) * dx + Math.sin(yaw) * dy;
    const side = -Math.sin(yaw) * dx + Math.cos(yaw) * dy;
    return { depth, side };
  };
  const screen = (depth: number, side: number) => ({
    x: captureWidth / 2 - (side * 170) / depth,
    y: 113 + 115 / depth,
  });
  const line = (x1: number, y1: number, x2: number, y2: number) => {
    let a = project(x1, y1);
    let b = project(x2, y2);
    const near = 0.65;
    if (a.depth < near && b.depth < near) return;
    if (a.depth > b.depth) [a, b] = [b, a];
    if (a.depth < near) {
      const factor = (near - a.depth) / (b.depth - a.depth);
      a = { depth: near, side: a.side + (b.side - a.side) * factor };
    }
    const from = screen(a.depth, a.side);
    const to = screen(b.depth, b.side);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
  };
  if (pose) {
    ctx.strokeStyle = "#4e696b";
    for (let i = -30; i <= 30; i += 2) {
      line(-30, i, 30, i);
      line(i, -30, i, 30);
    }
    for (const point of [
      { x: 5, y: 0, color: "#ffa859" },
      { x: 8, y: -5, color: "#68acc6" },
      { x: 12, y: 4, color: "#68acc6" },
      { x: 13, y: -7, color: "#68acc6" },
    ]) {
      const world = project(point.x, point.y);
      if (world.depth <= 0.65) continue;
      const { x, y } = screen(world.depth, world.side);
      const size = 44 / world.depth;
      ctx.fillStyle = point.color;
      ctx.fillRect(x - size / 2, y - size * 1.6, size, size * 1.6);
    }
    ctx.strokeStyle = "#bddee6";
    ctx.beginPath();
    ctx.moveTo(229, 130);
    ctx.lineTo(251, 130);
    ctx.moveTo(240, 119);
    ctx.lineTo(240, 141);
    ctx.stroke();
  }
  ctx.fillStyle = "#10202d";
  ctx.fillRect(0, 0, captureWidth, 29);
  ctx.fillRect(0, captureHeight - 29, captureWidth, 29);
  ctx.fillStyle = "#d9edf1";
  ctx.font = "12px monospace";
  ctx.fillText("HYPER  /  SYNTHETIC CAMERA", 13, 19);
  if (elapsedMs !== undefined) {
    ctx.textAlign = "right";
    ctx.fillText(`t + ${(elapsedMs / 1000).toFixed(1)} s`, 466, 19);
    ctx.textAlign = "left";
  }
  ctx.fillText(
    pose
      ? `X ${pose.x.toFixed(2)} m   Y ${pose.y.toFixed(2)} m   YAW ${((pose.yaw * 180) / Math.PI).toFixed(1)} deg`
      : "CAMERA INPUT UNAVAILABLE",
    13,
    captureHeight - 10,
  );
  ctx.restore();
}

// MediaRecorder uses streaming WebM headers. A missing or zero duration makes
// some players behave like a live feed after an operator seeks to a marker.
export async function setRecordedDuration(blob: Blob, durationMs: number) {
  if (!blob.type.includes("webm") || durationMs <= 0) return blob;
  const header = await blob.slice(0, 4096).arrayBuffer();
  const view = new Uint8Array(header);
  const widthAt = (at: number) => Math.clz32(view[at]) - 23;
  const elementAt = (at: number) => {
    const idWidth = widthAt(at);
    const sizeAt = at + idWidth;
    const sizeWidth = widthAt(sizeAt);
    const start = sizeAt + sizeWidth;
    if (idWidth > 4 || sizeWidth > 8 || start > view.length) return undefined;
    let id = 0;
    for (let i = at; i < sizeAt; i++) id = id * 256 + view[i];
    const marker = 1 << (8 - sizeWidth);
    let size = view[sizeAt] & (marker - 1);
    let unknown = size === marker - 1;
    for (let i = sizeAt + 1; i < start; i++) {
      size = size * 256 + view[i];
      unknown &&= view[i] === 255;
    }
    return { id, sizeAt, sizeWidth, size, start, end: start + size, unknown };
  };
  const ebml = elementAt(0);
  const segment = ebml && elementAt(ebml.end);
  if (ebml?.id !== 0x1a45dfa3 || segment?.id !== 0x18538067) return blob;
  let hasSeekHead = false;
  for (let at = segment.start; at < view.length;) {
    const info = elementAt(at);
    if (!info || info.unknown || info.end > view.length) return blob;
    if (info.id === 0x114d9b74) hasSeekHead = true;
    at = info.end;
    if (info.id !== 0x1549a966) continue;
    let scale = 1_000_000; // nanoseconds represented by one timestamp tick
    let duration: ReturnType<typeof elementAt>;
    for (let pos = info.start; pos < info.end;) {
      const field = elementAt(pos);
      if (!field || field.unknown || field.end > info.end) return blob;
      pos = field.end;
      if (field.id === 0x4489) duration = field;
      if (field.id === 0x2ad7b1) {
        scale = 0;
        for (let i = field.start; i < field.end; i++)
          scale = scale * 256 + view[i];
      }
    }
    if (!Number.isFinite(scale) || scale <= 0) return blob;
    const ticks = (durationMs * 1_000_000) / scale;
    const data = new DataView(header);
    if (duration?.size === 4) {
      if (data.getFloat32(duration.start) > 0) return blob;
      data.setFloat32(duration.start, ticks);
    } else if (duration?.size === 8) {
      if (data.getFloat64(duration.start) > 0) return blob;
      data.setFloat64(duration.start, ticks);
    } else {
      // Appending changes offsets. Only extend unindexed, streaming segments.
      const length = info.size + 11;
      if (
        duration ||
        !segment.unknown ||
        hasSeekHead ||
        length >= 2 ** (7 * info.sizeWidth) - 1
      )
        return blob;
      let value = length;
      for (let i = info.start - 1; i >= info.sizeAt; i--) {
        view[i] = value % 256;
        value = Math.floor(value / 256);
      }
      view[info.sizeAt] |= 1 << (8 - info.sizeWidth);
      const field = new Uint8Array(11);
      field.set([0x44, 0x89, 0x88]);
      new DataView(field.buffer).setFloat64(3, ticks);
      return new Blob([view.slice(0, info.end), field, blob.slice(info.end)], {
        type: blob.type,
      });
    }
    return new Blob([view.slice(0, info.end), blob.slice(info.end)], {
      type: blob.type,
    });
  }
  return blob;
}

type CameraCapture = {
  media: MediaRecorder;
  stream: MediaStream;
  frames: number;
  offsetMs: number;
};
type ActiveRecording = {
  record: OperationRecording;
  camera?: CameraCapture;
  last?: RecordingSample;
  limitTimer: ReturnType<typeof setTimeout>;
};

export class RecordingLibrary {
  private recordings = [exampleRecording];
  private active?: ActiveRecording;
  private listeners = new Set<() => void>();
  private disposed = false;

  getSnapshot = () => this.recordings;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private update(record: OperationRecording) {
    const archived = this.recordings.filter((item) => item.id !== record.id);
    const current = this.recordings.findIndex((item) => item.id === record.id);
    if (current === -1) archived.unshift(record);
    else archived.splice(current, 0, record);
    // Keep the bundled sample and a bounded number of browser-session recordings.
    const released = archived
      .slice(recordLimit)
      .filter((item) => !item.example);
    released.forEach((item) => this.releaseVideo(item.video));
    this.recordings = archived.slice(0, recordLimit);
    if (!this.recordings.includes(exampleRecording)) {
      this.recordings.push(exampleRecording);
    }
    for (const listener of this.listeners) listener();
  }

  private releaseVideo(video: RecordingVideo) {
    if (video.status === "ready" && video.url.startsWith("blob:")) {
      URL.revokeObjectURL(video.url);
    }
  }

  start = ({
    source,
    timeOrigin,
    sessionId,
    mission,
    pose,
  }: RecordingInput) => {
    if (this.active || this.disposed || !Number.isFinite(timeOrigin)) return;
    const id = crypto.randomUUID();
    const record: OperationRecording = {
      id,
      sessionId: sessionId ?? id,
      source,
      timeOrigin,
      mission,
      missions: mission ? [mission] : [],
      durationMs: 0,
      samples: [],
      events: [],
      video:
        source === "DEMO"
          ? { status: "processing" }
          : { status: "missing", reason: "ROS 카메라 미연결" },
      active: true,
    };
    const draft: ActiveRecording = {
      record,
      last: pose ? { at: timeOrigin, pose } : undefined,
      limitTimer: setTimeout(
        () => this.stop("최대 기록 길이 4분 도달"),
        captureLimitMs,
      ),
    };
    this.active = draft;
    if (source === "DEMO") this.startCamera(draft);
    this.update(draft.record);
    return id;
  };

  private startCamera(draft: ActiveRecording) {
    let stream: MediaStream | undefined;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = captureWidth;
      canvas.height = captureHeight;
      if (
        typeof canvas.captureStream !== "function" ||
        typeof MediaRecorder === "undefined"
      ) {
        draft.record.video = {
          status: "missing",
          reason: "브라우저가 합성 영상 녹화를 지원하지 않습니다.",
        };
        return;
      }
      drawSyntheticCamera(canvas, draft.last?.pose, 0);
      stream = canvas.captureStream(captureFps);
      const type = ["video/webm;codecs=vp8", "video/webm", "video/mp4"].find(
        (mime) => MediaRecorder.isTypeSupported(mime),
      );
      const media = new MediaRecorder(stream, {
        ...(type ? { mimeType: type } : {}),
        videoBitsPerSecond: 250000,
      });
      const chunks: Blob[] = [];
      media.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      media.onerror = () => {
        this.finishCamera(draft, {
          status: "error",
          reason: "합성 영상 녹화 오류",
        });
      };
      media.onstop = async () => {
        const camera = draft.camera;
        if (!camera || this.disposed) return;
        if (!chunks.length) {
          this.finishCamera(draft, {
            status: "missing",
            reason: "저장된 영상 프레임 없음",
          });
          return;
        }
        const blob = new Blob(chunks, {
          type: media.mimeType || chunks[0].type,
        });
        const durationMs = Math.max(
          0,
          draft.record.durationMs - camera.offsetMs,
        );
        const playable = await setRecordedDuration(blob, durationMs).catch(
          () => blob,
        );
        this.finishCamera(draft, {
          status: "ready",
          url: URL.createObjectURL(playable),
          offsetMs: camera.offsetMs,
          durationMs,
          camera: syntheticCamera,
        });
      };
      const offsetMs = Math.max(0, Date.now() - draft.record.timeOrigin);
      media.start(1000);
      draft.camera = {
        media,
        stream,
        offsetMs,
        frames: window.setInterval(() => {
          const sample = draft.last;
          drawSyntheticCamera(
            canvas,
            sample?.cameraAvailable === false ? undefined : sample?.pose,
            Date.now() - draft.record.timeOrigin,
          );
        }, 1000 / captureFps),
      };
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      draft.record.video = {
        status: "error",
        reason: "합성 영상 녹화를 시작할 수 없습니다.",
      };
    }
  }

  private finishCamera(draft: ActiveRecording, video: RecordingVideo) {
    if (
      draft.record.video.status !== "processing" ||
      this.disposed ||
      !this.recordings.some((item) => item.id === draft.record.id)
    ) {
      this.releaseVideo(video);
      return;
    }
    const camera = draft.camera;
    if (camera) {
      window.clearInterval(camera.frames);
      camera.stream.getTracks().forEach((track) => track.stop());
    }
    draft.record = { ...draft.record, video };
    this.update(draft.record);
  }

  capture = (sample: RecordingSample, force = false) => {
    const draft = this.active;
    if (
      !draft ||
      !Number.isFinite(sample.at) ||
      sample.at < draft.record.timeOrigin
    )
      return;
    if (draft.last && sample.at < draft.last.at) return;
    draft.last = sample;
    const previous = draft.record.samples.at(-1);
    const changed =
      previous &&
      (previous.mode !== sample.mode ||
        previous.phase !== sample.phase ||
        previous.waypoint !== sample.waypoint ||
        previous.mission !== sample.mission ||
        previous.localization !== sample.localization ||
        previous.coordinateFrame !== sample.coordinateFrame ||
        previous.cameraAvailable !== sample.cameraAvailable ||
        (previous.incidents ?? []).join("\0") !==
          (sample.incidents ?? []).join("\0"));
    if (
      !force &&
      previous &&
      !changed &&
      sample.at - previous.at < sampleIntervalMs
    ) {
      return;
    }
    const missions = draft.record.missions;
    draft.record = {
      ...draft.record,
      durationMs: Math.max(
        draft.record.durationMs,
        sample.at - draft.record.timeOrigin,
      ),
      mission: sample.mission ?? draft.record.mission,
      missions:
        sample.mission && !missions.includes(sample.mission)
          ? [...missions, sample.mission]
          : missions,
      samples: [...draft.record.samples, sample],
    };
    this.update(draft.record);
  };

  mark = (event: RecordingEvent) => {
    const draft = this.active;
    if (
      !draft ||
      !Number.isFinite(event.at) ||
      event.at < draft.record.timeOrigin
    )
      return;
    if (draft.record.events.some((marker) => marker.id === event.id)) return;
    const events = [...draft.record.events, event].sort((a, b) => a.at - b.at);
    draft.record = {
      ...draft.record,
      durationMs: Math.max(
        draft.record.durationMs,
        event.at - draft.record.timeOrigin,
      ),
      events: events.slice(-markerLimit),
    };
    this.update(draft.record);
  };

  stop = (reason?: string) => {
    const draft = this.active;
    if (!draft) return;
    this.active = undefined;
    clearTimeout(draft.limitTimer);
    const { record, camera, last } = draft;
    const samples =
      last && record.samples.at(-1) !== last
        ? [...record.samples, last]
        : record.samples;
    draft.record = {
      ...record,
      samples,
      durationMs: Math.max(record.durationMs, Date.now() - record.timeOrigin),
      active: false,
      stopReason: reason,
    };
    this.update(draft.record);
    if (camera) {
      window.clearInterval(camera.frames);
      if (camera.media.state !== "inactive") camera.media.stop();
      camera.stream.getTracks().forEach((track) => track.stop());
    }
  };

  // Keep closed histories when the operator resets or switches source.
  reset = () => this.stop("운용 세션 변경");

  dispose = () => {
    this.stop();
    this.disposed = true;
    this.recordings.forEach((record) => this.releaseVideo(record.video));
    this.recordings = [exampleRecording];
  };
}

export function useRecordings() {
  const [library] = useState(() => new RecordingLibrary());
  const records = useSyncExternalStore(library.subscribe, library.getSnapshot);
  useEffect(() => library.dispose, [library]);
  return {
    records,
    active: records.find((record) => record.active),
    start: library.start,
    capture: library.capture,
    mark: library.mark,
    stop: library.stop,
    reset: library.reset,
  };
}
