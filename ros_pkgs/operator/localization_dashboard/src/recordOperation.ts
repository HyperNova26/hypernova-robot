// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { missionPhase } from "./OperationControls";
import { demoMap, type OperationPose, type OperationState } from "./operation";
import { useRecordings, type RecordingSample } from "./recordings";
import type { Telemetry } from "./store";

export const cameraPose = ({ x, y, yaw }: OperationPose) => ({
  x,
  y,
  yaw: (yaw * Math.PI) / 180,
});

export function demoSample(state: OperationState, at: number): RecordingSample {
  const run = state.run;
  const campus = state.campus;
  return {
    at,
    pose: cameraPose(campus?.pose ?? state.pose),
    coordinateFrame: campus?.map.frame ?? demoMap.frame,
    mode: state.mode,
    phase: missionPhase(run),
    mission: run?.mission.name,
    waypoint: run?.mission.waypoints[run.targetIndex]?.name,
    localization: state.localization,
    incidents: state.incidents
      .filter((incident) => !incident.resolvedAt && !incident.closedAt)
      .map((incident) => incident.title),
    cameraAvailable:
      !campus && state.connected && state.localization !== "INPUT_TIMEOUT",
  };
}

export function trackDemoRecording(
  library: Pick<ReturnType<typeof useRecordings>, "capture" | "mark">,
  state: OperationState,
  previous: OperationState,
  at: number,
) {
  const before = new Map(
    previous.incidents.map((incident) => [
      incident.id,
      incident.history.length,
    ]),
  );
  const newEvents = state.incidents.flatMap((incident) => {
    const count = before.get(incident.id) ?? 0;
    return incident.history.slice(count).map((entry, i) => ({
      id: `${incident.id}/${count + i}`,
      at: entry.at,
      incidentId: incident.id,
      title: `${incident.title} · ${entry.text}`,
    }));
  });
  const capture = demoSample(state, at);
  for (const event of newEvents) {
    library.capture({ ...capture, at: event.at }, true);
    library.mark(event);
  }
  library.capture(capture);
  const oldRun = previous.run;
  const run = state.run;
  if (
    run &&
    (oldRun?.status !== run.status || oldRun.targetIndex !== run.targetIndex)
  ) {
    library.mark({
      id: `mission/${run.mission.id}/${run.status}/${run.targetIndex}/${at}`,
      at,
      title:
        oldRun?.targetIndex !== run.targetIndex && run.status === "running"
          ? `${run.mission.name} · 현재 목표 ${run.targetIndex + 1}`
          : `${run.mission.name} · ${missionPhase(run)}`,
    });
  }
}

export function rosSample(
  store: Telemetry,
  now: number,
  incidents: string[],
): RecordingSample {
  const sample = store.current;
  return {
    at: now,
    pose:
      sample && cameraPose({ x: sample.p.x, y: sample.p.y, yaw: sample.rpy.z }),
    coordinateFrame: sample?.frame,
    localization: store.localization?.label,
    rosTimeSeconds: store.clockAvailable ? store.simTime : sample?.t,
    incidents,
    cameraAvailable: false,
  };
}
