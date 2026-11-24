// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Clock3, MapPin, VolumeX } from "lucide-react";
import {
  demoMap,
  incidentCatalog,
  type Incident,
  type IncidentKind,
} from "./operation";
import type { LiveIncident } from "./liveIncidents";
import type { CurrentSource } from "./sources";

export type ConsoleIncident = Omit<Incident, "pose" | "history"> & {
  source: CurrentSource;
  pose?: Incident["pose"] & { frame: string; z?: number };
  history: { at: number; text: string }[];
  archived?: boolean;
};

export type IncidentResponse =
  "acknowledge" | "mute" | "close" | "note" | "recover";
export const incidentActive = (incident: ConsoleIncident) =>
  !incident.resolvedAt && !incident.closedAt && !incident.archived;
const severity = { critical: "중요", warning: "주의", info: "정보" };
const dateTime = (at: number) => new Date(at).toLocaleString("ko-KR");
const incidentState = (incident: ConsoleIncident) =>
  incident.closedAt
    ? "종료"
    : incident.resolvedAt
      ? "원인 해소"
      : incident.archived
        ? "이전 세션"
        : incident.acknowledgedAt
          ? "확인됨"
          : "미확인";

export function demoIncident(incident: Incident): ConsoleIncident {
  return {
    ...incident,
    source: "DEMO",
    pose: { ...incident.pose, frame: incident.map?.frame ?? demoMap.frame },
  };
}

export function rosIncident(incident: LiveIncident): ConsoleIncident {
  const description: Record<LiveIncident["kind"], string> = {
    disconnect: "Foxglove Bridge 연결이 종료됐습니다.",
    timeout:
      "Odometry 수신이 지연됐거나 위치추정 상태가 입력 지연을 보고했습니다.",
    degraded: "ROS 위치추정 상태 메시지에서 DEGRADED를 받았습니다.",
    lost: "ROS 위치추정 상태 메시지에서 LOST를 받았습니다.",
  };
  return {
    ...incidentCatalog[incident.kind],
    ...incident,
    source: "ROS LIVE",
    description: description[incident.kind],
    impact: "수신 상태 및 마지막으로 표시된 위치를 확인할 수 있습니다.",
    action: "Bridge 연결, 토픽 수신 및 위치추정 상태를 확인하세요.",
  };
}

export function useIncidentSound(active: ConsoleIncident[]) {
  const sound = useRef<AudioContext | null>(null);
  const urgent = active.some(
    (incident) => incident.severity === "critical" && !incident.mutedAt,
  );
  useEffect(() => {
    const unlock = () => {
      if (!window.AudioContext) return;
      try {
        sound.current ??= new AudioContext();
        void sound.current.resume().catch(() => {});
      } catch {
        // Persistent visual alerts are available without browser audio.
      }
    };
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
      if (sound.current) void sound.current.close();
      sound.current = null;
    };
  }, []);
  useEffect(() => {
    if (!urgent) return;
    const play = () => {
      const context = sound.current;
      if (!context || context.state !== "running") return;
      const oscillator = context.createOscillator();
      const volume = context.createGain();
      oscillator.frequency.value = 610;
      volume.gain.setValueAtTime(0.035, context.currentTime);
      volume.gain.exponentialRampToValueAtTime(
        0.001,
        context.currentTime + 0.18,
      );
      oscillator.connect(volume).connect(context.destination);
      oscillator.start();
      oscillator.stop(context.currentTime + 0.18);
    };
    play();
    const timer = window.setInterval(play, 6000);
    return () => window.clearInterval(timer);
  }, [urgent]);
}

export function IncidentsView({
  incidents,
  selectedId,
  onSelect,
  onResponse,
  onRecord,
  onMap,
  canShowOnMap,
  hasRecord,
}: {
  incidents: ConsoleIncident[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onResponse: (
    incident: ConsoleIncident,
    action: IncidentResponse,
    text?: string,
  ) => void;
  onRecord: (incident: ConsoleIncident) => void;
  onMap: (incident: ConsoleIncident) => void;
  canShowOnMap: (incident: ConsoleIncident) => boolean;
  hasRecord: (incident: ConsoleIncident) => boolean;
}) {
  const [filter, setFilter] = useState<"all" | "active" | "history">("all");
  const visible = incidents.filter(
    (incident) =>
      filter === "all" || incidentActive(incident) === (filter === "active"),
  );
  const selected =
    visible.find((incident) => incident.id === selectedId) ?? visible[0];
  return (
    <div className="ops-split">
      <section className="ops-card">
        <div className="ops-section-heading">
          <h2>알람·이상 이력</h2>
          <span>{incidents.length}건</span>
        </div>
        <label className="ops-filter">
          상태
          <select
            value={filter}
            onChange={(event) =>
              setFilter(event.currentTarget.value as typeof filter)
            }
          >
            <option value="all">전체</option>
            <option value="active">활성 알람</option>
            <option value="history">과거 이력</option>
          </select>
        </label>
        <div className="ops-item-list">
          {visible.map((incident) => (
            <button
              key={incident.id}
              className={incident === selected ? "active" : ""}
              aria-pressed={incident === selected}
              onClick={() => onSelect(incident.id)}
            >
              <AlertTriangle size={16} className={incident.severity} />
              <span>
                <strong>{incident.title}</strong>
                <small>
                  {incident.source} · {incidentState(incident)} ·{" "}
                  {incident.count}회
                </small>
              </span>
            </button>
          ))}
          {!visible.length && (
            <p className="ops-empty">표시할 알람이 없습니다.</p>
          )}
        </div>
      </section>
      {selected ? (
        <IncidentDetail
          key={selected.id}
          incident={selected}
          onResponse={onResponse}
          onRecord={onRecord}
          onMap={onMap}
          canShowOnMap={canShowOnMap(selected)}
          hasRecord={hasRecord(selected)}
        />
      ) : (
        <section className="ops-card ops-empty">
          알람이 발생하면 위치와 대응 기록을 여기에서 확인할 수 있습니다.
        </section>
      )}
    </div>
  );
}

function IncidentDetail({
  incident,
  onResponse,
  onRecord,
  onMap,
  canShowOnMap,
  hasRecord,
}: {
  incident: ConsoleIncident;
  onResponse: (
    incident: ConsoleIncident,
    action: IncidentResponse,
    text?: string,
  ) => void;
  onRecord: (incident: ConsoleIncident) => void;
  onMap: (incident: ConsoleIncident) => void;
  canShowOnMap: boolean;
  hasRecord: boolean;
}) {
  const [note, setNote] = useState("");
  const active = incidentActive(incident);
  const editable = !incident.closedAt && !incident.archived;
  const pose = incident.pose;
  return (
    <article className="ops-card ops-incident">
      <div className="ops-section-heading">
        <h2>
          <AlertTriangle size={19} /> {incident.title}
        </h2>
        <span className={"ops-tag " + incident.severity}>
          {severity[incident.severity]} · {incidentState(incident)}
        </span>
      </div>
      <p>{incident.description}</p>
      <dl className="ops-incident-details">
        <div>
          <dt>분류</dt>
          <dd>
            {incident.source === "DEMO" ? "모의" : "ROS 수신"} ·{" "}
            {incident.category === "field" ? "현장 이상" : "로봇·시스템"}
          </dd>
        </div>
        <div>
          <dt>최초 / 마지막 발생</dt>
          <dd>
            {dateTime(incident.openedAt)} / {dateTime(incident.lastAt)}
          </dd>
        </div>
        <div>
          <dt>위치</dt>
          <dd>
            {pose
              ? `X ${pose.x.toFixed(2)} · Y ${pose.y.toFixed(2)} m (${pose.frame})`
              : "수신 위치 없음"}
          </dd>
        </div>
        <div>
          <dt>임무 / waypoint</dt>
          <dd>
            {incident.missionName ?? "없음"} / {incident.waypointName ?? "없음"}
          </dd>
        </div>
        <div>
          <dt>운용 영향</dt>
          <dd>{incident.impact}</dd>
        </div>
        <div>
          <dt>다음 행동</dt>
          <dd>{incident.action}</dd>
        </div>
        <div>
          <dt>연결 자료</dt>
          <dd>
            {hasRecord
              ? "사건 시점에 연결된 자료를 기록 화면에서 확인할 수 있습니다."
              : "이 사건에 연결된 재생 자료가 없습니다."}
          </dd>
        </div>
      </dl>
      <div className="ops-row">
        <button
          disabled={!editable || !!incident.acknowledgedAt}
          onClick={() => onResponse(incident, "acknowledge")}
        >
          <Check size={16} /> 알람 확인
        </button>
        <button
          disabled={!editable || !!incident.mutedAt}
          onClick={() => onResponse(incident, "mute")}
        >
          <VolumeX size={16} /> 알림음 끄기
        </button>
        <button
          disabled={!active || incident.source !== "DEMO"}
          onClick={() => onResponse(incident, "recover")}
        >
          모의 원인 해소
        </button>
        <button
          disabled={!editable || !incident.resolvedAt}
          onClick={() => onResponse(incident, "close")}
        >
          사건 종료
        </button>
      </div>
      {active && (
        <p className="ops-help">
          {incident.source === "DEMO"
            ? "원인 해소 후 사건을 종료할 수 있습니다. 일시정지된 임무는 운용 화면에서 재개합니다."
            : "ROS 수신에서 회복이 확인되면 사건을 종료할 수 있습니다."}
        </p>
      )}
      <div className="ops-row">
        <button disabled={!canShowOnMap} onClick={() => onMap(incident)}>
          <MapPin size={16} /> 지도에서 보기
        </button>
        <button
          className="primary"
          disabled={!hasRecord}
          onClick={() => onRecord(incident)}
        >
          <Clock3 size={16} /> 사건 시점 기록 열기
        </button>
      </div>
      <h3>대응 이력</h3>
      <ol className="ops-history">
        {incident.history.map((entry, i) => (
          <li key={i}>
            <time dateTime={new Date(entry.at).toISOString()}>
              {dateTime(entry.at)}
            </time>{" "}
            {entry.text}
          </li>
        ))}
      </ol>
      {editable && (
        <form
          className="ops-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (note.trim()) {
              onResponse(incident, "note", note);
              setNote("");
            }
          }}
        >
          <label className="ops-note">
            대응 기록{" "}
            <input
              value={note}
              maxLength={280}
              onChange={(event) => setNote(event.currentTarget.value)}
              placeholder="확인하거나 조치한 내용"
            />
          </label>
          <button type="submit" disabled={!note.trim()}>
            기록 추가
          </button>
        </form>
      )}
    </article>
  );
}

export const scenarioGroups: { label: string; kinds: IncidentKind[] }[] = [
  { label: "전자정보대학관 보행로 순찰", kinds: ["field", "obstacle"] },
  { label: "위치추정·입력 복구", kinds: ["degraded", "lost", "timeout"] },
  { label: "통신·배터리 복구", kinds: ["disconnect", "battery"] },
];
