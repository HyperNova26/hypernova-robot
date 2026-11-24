// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { connect } from "./bridge";
import { localizationStates, sample, type Pose } from "./model";
import { demoMap, type OperationState } from "./operation";
import type { Telemetry } from "./store";
import type { RecordingSample } from "./recordings";

export type CurrentSource = "DEMO" | "ROS LIVE";
export type TelemetrySource =
  | { kind: "DEMO"; publish: (state: OperationState) => void }
  | { kind: "ROS LIVE"; subscribe: (onBoundary: () => void) => () => void }
  | {
      kind: "REPLAY";
      sampleAt: (offsetMs: number) => RecordingSample | undefined;
    };

export function liveSource(
  store: Telemetry,
): Extract<TelemetrySource, { kind: "ROS LIVE" }> {
  return {
    kind: "ROS LIVE",
    subscribe: (onBoundary) => connect(store, onBoundary),
  };
}

export function demoSource(
  store: Telemetry,
): Extract<TelemetrySource, { kind: "DEMO" }> {
  let session = "",
    frame = "",
    lastPose = 0,
    lastScan = -Infinity;
  return {
    kind: "DEMO",
    publish(state) {
      const nextFrame = state.campus?.map.frame ?? demoMap.frame;
      if (session !== state.sessionId || frame !== nextFrame || !store.demo) {
        frame = nextFrame;
        session = state.sessionId;
        lastPose = 0;
        lastScan = -Infinity;
        store.reset();
        store.demo = true;
        store.syntheticFrame = { frame, child: "demo_robot" };
      }
      store.connection = state.connected
        ? "합성 데이터 수신"
        : "모의 연결 끊김";
      if (!state.connected || state.localization === "INPUT_TIMEOUT") {
        store.lastReceived = 0;
        store.tick();
        return;
      }
      if (state.lastReceived === lastPose) return;
      lastPose = state.lastReceived;
      const t = (state.lastReceived - state.timeOrigin) / 1000;
      const { x, y, yaw } = state.campus?.pose ?? state.pose;
      const radians = (yaw * Math.PI) / 180;
      const pose: Pose = {
        t,
        frame,
        child: "demo_robot",
        p: { x, y, z: 0 },
        q: { x: 0, y: 0, z: Math.sin(radians / 2), w: Math.cos(radians / 2) },
      };
      const code = localizationStates.findIndex(
        (label) => label === state.localization,
      );
      const localization = {
        code,
        label: state.localization,
        t,
        received: lastPose,
        field: "demo",
        raw: { code },
      };
      store.simTime = t;
      store.clockAvailable = true;
      store.lastReceived = lastPose;
      store.frames.odometry(pose);
      const row = sample(
        pose,
        store.lio.at(-1),
        undefined,
        {
          ...store.config,
          frame: pose.frame,
          base: pose.child,
        },
        lastPose,
      );
      row.speed = Math.hypot(state.observed.forward, state.observed.left);
      row.speedSource = "모의 위치 변화";
      row.localization = localization;
      if (store.localization?.code !== code)
        store.event("모의 위치추정 상태: " + state.localization);
      store.statuses.push(localization);
      store.lio.push(pose);
      store.rows.push(row);
      if (store.lio.length > 6000) store.lio.shift();
      if (store.rows.length > 6000) store.rows.shift();
      if (store.statuses.length > 1000) store.statuses.shift();
      if (t - lastScan >= 0.1) {
        lastScan = t;
        const points = new Float32Array(360 * 3);
        for (let i = 0; i < 360; i++) {
          const angle = (i * Math.PI) / 180;
          const distance = 2.6 + 0.35 * Math.sin(5 * angle);
          points.set(
            [x + distance * Math.cos(angle), y + distance * Math.sin(angle), 0],
            i * 3,
          );
        }
        store.clouds.push({ t, frame: pose.frame, points });
        if (store.clouds.length > 30) store.clouds.shift();
      }
      store.tick();
    },
  };
}
