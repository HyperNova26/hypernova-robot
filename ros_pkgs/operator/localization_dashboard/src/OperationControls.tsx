// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from "react";
import { Circle, Pause, Play, Square } from "lucide-react";
import { scenarioGroups } from "./IncidentsView";
import {
  campusResumeError,
  commandBlock,
  incidentCatalog,
  missionError,
  type CampusMissionNetwork,
  type Mission,
  type MissionRun,
  type OperationCommand,
  type OperationState,
} from "./operation";

export const missionPhase = (run?: MissionRun) =>
  run
    ? {
        running: "실행",
        paused: "일시정지",
        completed: "완료",
        cancelled: "취소",
        failed: "실패",
      }[run.status]
    : "대기";

export function AutoControls({
  state,
  draft,
  editingRoute,
  campusNetwork,
  onCommand,
  children,
}: {
  state: OperationState;
  draft?: Mission;
  editingRoute: boolean;
  campusNetwork?: CampusMissionNetwork;
  onCommand: (command: OperationCommand) => void;
  children: ReactNode;
}) {
  const run = state.run?.mission.routing === "campus" ? state.run : undefined;
  const busy = run?.status === "running" || run?.status === "paused";
  const blocked = commandBlock(state, "AUTO");
  const invalid = !state.campus
    ? "캠퍼스 지도와 로봇 시작 위치를 확인하는 중입니다."
    : editingRoute
      ? "지도에서 보정 경로를 적용하거나 그리기를 종료하세요."
      : draft
        ? missionError(draft, undefined, campusNetwork)
        : "경로를 그리거나 예제 임무를 열어 시작하세요.";
  const resumeBlocked = campusResumeError(state, campusNetwork);
  const target = busy ? run?.mission.waypoints[run.targetIndex] : undefined;
  return (
    <>
      <div className="ops-compact-heading">
        <div>
          <span>실행 대상</span>
          <strong>
            {busy ? run?.mission.name : draft?.name || "선택된 초안 없음"}
          </strong>
        </div>
        <b>{missionPhase(run)}</b>
      </div>
      {target && (
        <p className="ops-help">
          현재 목표 {(run?.targetIndex ?? 0) + 1}. {target.name}
          {run?.reachedAt !== undefined &&
            ` · 대기 ${run.dwellElapsed.toFixed(1)} / ${target.dwell}초`}
        </p>
      )}
      {run?.approach && busy && (
        <p className="ops-help">
          보행로를 따라 일시정지 지점으로 복귀 중입니다.
        </p>
      )}
      {!!run?.reason && <p className="ops-help">{run.reason}</p>}
      <div className="ops-row ops-auto-actions">
        {busy ? (
          <>
            {run?.status === "running" ? (
              <button onClick={() => onCommand({ type: "pause" })}>
                <Pause size={16} /> 일시정지
              </button>
            ) : (
              <button
                className="primary"
                disabled={!!(blocked || resumeBlocked)}
                onClick={() => onCommand({ type: "resume" })}
              >
                <Play size={16} /> 임무 재개
              </button>
            )}
            <button onClick={() => onCommand({ type: "cancel" })}>
              <Square size={15} /> 임무 취소
            </button>
          </>
        ) : (
          <button
            className="primary"
            disabled={!!(invalid || blocked)}
            onClick={() => {
              if (draft) onCommand({ type: "start", mission: draft });
            }}
          >
            <Play size={16} /> 임무 시작
          </button>
        )}
      </div>
      {(blocked || resumeBlocked || (!busy && invalid)) && (
        <p className="ops-help" role="status">
          {blocked || resumeBlocked || (!busy && invalid)}
        </p>
      )}
      {run && busy && (
        <details>
          <summary>
            경유점 {run.targetIndex} / {run.mission.waypoints.length} 완료
          </summary>
          <ol className="ops-auto-progress" aria-label="경유점 진행 상세">
            {run.mission.waypoints.map((point, i) => (
              <li
                key={point.id}
                aria-current={i === run.targetIndex ? "step" : undefined}
              >
                <span>{point.name}</span>
                <small>
                  {i < run.targetIndex
                    ? "완료"
                    : i === run.targetIndex
                      ? "현재 목표"
                      : "예정"}
                </small>
              </li>
            ))}
          </ol>
        </details>
      )}
      {children}
    </>
  );
}

export function ScenarioPanel({
  state,
  enabled,
  onCommand,
  onReset,
}: {
  state: OperationState;
  enabled: boolean;
  onCommand: (command: OperationCommand) => void;
  onReset: () => void;
}) {
  const [choice, setChoice] = useState(0);
  const scenario = scenarioGroups[choice];
  return (
    <details className="ops-disclosure ops-scenario">
      <summary>진행자용 시나리오</summary>
      <div className="ops-scenario-content">
        <label className="ops-filter">
          시나리오
          <select
            value={choice}
            disabled={!enabled}
            onChange={(event) => setChoice(Number(event.currentTarget.value))}
          >
            {scenarioGroups.map((group, i) => (
              <option key={group.label} value={i}>
                {group.label}
              </option>
            ))}
          </select>
        </label>
        <p className="ops-help">
          {enabled
            ? "시연에 맞춰 이상을 발생시키거나 원인을 해소합니다."
            : "DEMO 출처에서 시나리오를 사용할 수 있습니다."}
        </p>
        <div className="ops-scenario-events">
          {scenario.kinds.map((kind) => {
            const active = state.incidents.some(
              (item) =>
                item.kind === kind && !item.resolvedAt && !item.closedAt,
            );
            return (
              <div key={kind}>
                <strong>{incidentCatalog[kind].title}</strong>
                <div className="ops-row">
                  <button
                    disabled={!enabled}
                    onClick={() => onCommand({ type: "inject", kind })}
                  >
                    {active ? "다시 발생" : "이상 발생"}
                  </button>
                  <button
                    disabled={!enabled || !active}
                    onClick={() => onCommand({ type: "recover", kind })}
                  >
                    원인 해소
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <button disabled={!enabled} onClick={onReset}>
          시연 초기화
        </button>
      </div>
    </details>
  );
}

export function RecordControl({
  active,
  onStart,
  onStop,
}: {
  active: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  return active ? (
    <button className="ops-recording" onClick={onStop}>
      <Square size={15} /> 운용 기록 종료
    </button>
  ) : (
    <button onClick={onStart}>
      <Circle size={15} /> 운용 기록 시작
    </button>
  );
}
