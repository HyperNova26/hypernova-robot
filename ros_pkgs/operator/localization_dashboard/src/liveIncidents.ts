// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import type { Telemetry } from "./store";

export type LiveIncident = {
  id: string;
  kind: "disconnect" | "timeout" | "degraded" | "lost";
  openedAt: number;
  lastAt: number;
  count: number;
  pose?: { x: number; y: number; z: number; yaw: number; frame: string };
  resolvedAt?: number;
  acknowledgedAt?: number;
  mutedAt?: number;
  closedAt?: number;
  history: { at: number; text: string }[];
};

export function updateLiveIncidents(
  previous: LiveIncident[],
  store: Telemetry,
  now: number,
) {
  const kinds: LiveIncident["kind"][] = [];
  if (store.transport === "closed") kinds.push("disconnect");
  if (store.transport === "open" && store.current && !store.receiving)
    kinds.push("timeout");
  const status = store.localization;
  if (
    store.transport === "open" &&
    status &&
    now - status.received < store.config.timeout
  ) {
    if (status.label === "DEGRADED") kinds.push("degraded");
    if (status.label === "LOST") kinds.push("lost");
    if (status.label === "INPUT_TIMEOUT" || status.label === "STALE_INPUT") {
      if (!kinds.includes("timeout")) kinds.push("timeout");
    }
  }
  let next = previous;
  const sample = store.current;
  const pose = sample && {
    ...sample.p,
    yaw: sample.rpy.z,
    frame: sample.frame,
  };

  for (const kind of kinds) {
    const active = next.find(
      (incident) => incident.kind === kind && !incident.resolvedAt,
    );
    if (active) continue;
    const related = [...next]
      .reverse()
      .find((incident) => incident.kind === kind && !incident.closedAt);
    if (related) {
      next = next.map((incident) =>
        incident === related
          ? {
              ...incident,
              lastAt: now,
              count: incident.count + 1,
              resolvedAt: undefined,
              history: [
                ...incident.history,
                { at: now, text: "같은 이상이 다시 관측됐습니다." },
              ],
            }
          : incident,
      );
      continue;
    }
    next = [
      ...next,
      {
        id: `ros-${store.epoch}-${kind}-${now}`,
        kind,
        openedAt: now,
        lastAt: now,
        count: 1,
        pose,
        history: [{ at: now, text: "ROS 수신 상태에서 이상을 관측했습니다." }],
      },
    ];
  }

  for (const incident of next) {
    if (incident.resolvedAt || kinds.includes(incident.kind)) continue;
    const recovered =
      store.transport === "open" &&
      (incident.kind === "disconnect" ||
        (incident.kind === "timeout" &&
          store.receiving &&
          (!status ||
            (status.label !== "INPUT_TIMEOUT" &&
              status.label !== "STALE_INPUT"))) ||
        (status?.label === "TRACKING" &&
          now - status.received < store.config.timeout));
    if (!recovered) continue;
    next = next.map((entry) =>
      entry === incident
        ? {
            ...entry,
            resolvedAt: now,
            history: [
              ...entry.history,
              { at: now, text: "수신 데이터에서 회복을 확인했습니다." },
            ],
          }
        : entry,
    );
  }
  return next;
}

export function respondToLiveIncident(
  incidents: LiveIncident[],
  id: string,
  action: "acknowledge" | "mute" | "close" | "note",
  text: string,
  now = Date.now(),
) {
  return incidents.map((incident) => {
    if (incident.id !== id || incident.closedAt) return incident;
    if (action === "acknowledge" && !incident.acknowledgedAt)
      return {
        ...incident,
        acknowledgedAt: now,
        history: [
          ...incident.history,
          { at: now, text: "운영자가 알람을 확인했습니다." },
        ],
      };
    if (action === "mute" && !incident.mutedAt)
      return {
        ...incident,
        mutedAt: now,
        history: [
          ...incident.history,
          { at: now, text: "운영자가 알림음을 껐습니다." },
        ],
      };
    if (action === "close" && incident.resolvedAt)
      return {
        ...incident,
        closedAt: now,
        history: [
          ...incident.history,
          { at: now, text: "운영자가 사건을 종료했습니다." },
        ],
      };
    if (action === "note" && text.trim())
      return {
        ...incident,
        history: [
          ...incident.history,
          { at: now, text: text.trim().slice(0, 500) },
        ],
      };
    return incident;
  });
}
