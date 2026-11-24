// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { MapPin, Plus, Save } from "lucide-react";
import type { Mission } from "./operation";
import "./mission.css";

export function CampusMissionEditor({
  draft,
  invalid,
  status,
  onName,
  onSave,
}: {
  draft: Mission;
  invalid?: string;
  status: string;
  onName: (name: string) => void;
  onSave: () => void;
}) {
  return (
    <form
      className="mission-editor"
      aria-label="캠퍼스 임무 초안"
      data-teleop-ignore
      onSubmit={(event) => {
        event.preventDefault();
        if (!invalid) onSave();
      }}
    >
      <label className="mission-field">
        <span>임무 이름</span>
        <input
          value={draft.name}
          maxLength={70}
          onChange={(event) => onName(event.currentTarget.value)}
        />
      </label>
      <p className="mission-meta">
        {draft.waypoints.length}개 경유점 · OpenStreetMap
      </p>
      <button className="primary" type="submit" disabled={!!invalid}>
        <Save size={15} aria-hidden="true" /> 임무 저장
      </button>
      {status && (
        <p className="mission-meta" role="status">
          {status}
        </p>
      )}
    </form>
  );
}

export function MissionLibrary({
  missions,
  example,
  onExample,
  selectedMissionId,
  onOpen,
  onNew,
  persistenceIssue,
  editingDisabled = false,
}: {
  missions: readonly Mission[];
  example?: Mission;
  onExample: () => void;
  selectedMissionId?: string;
  onOpen: (mission: Mission) => void;
  onNew: () => void;
  persistenceIssue?: string;
  editingDisabled?: boolean;
}) {
  const current = missions.filter((mission) => mission.routing === "campus");
  const archive = missions.filter((mission) => mission.routing !== "campus");
  return (
    <section
      className="mission-library"
      aria-labelledby="mission-library-title"
      data-teleop-ignore
    >
      <header className="mission-library-heading">
        <div>
          <h2 id="mission-library-title">저장한 캠퍼스 순찰 임무</h2>
          <p className="mission-meta">경희대학교 국제캠퍼스 · OpenStreetMap</p>
        </div>
        <button
          type="button"
          className="primary"
          disabled={editingDisabled}
          onClick={onNew}
        >
          <Plus size={16} aria-hidden="true" /> 새 임무
        </button>
      </header>
      {editingDisabled && (
        <p className="mission-meta">
          DEMO 출처에서 임무를 작성하거나 열 수 있습니다.
        </p>
      )}
      {persistenceIssue && (
        <p className="mission-issue" role="status">
          {persistenceIssue}
        </p>
      )}
      {current.length === 0 ? (
        <p className="mission-empty">저장한 캠퍼스 임무가 없습니다.</p>
      ) : (
        <ul className="mission-list" aria-label="캠퍼스 순찰 임무">
          {current.map((mission) => (
            <li key={mission.id}>
              <div className="mission-list-description">
                <MapPin size={20} aria-hidden="true" />
                <div>
                  <h3>
                    {mission.name}
                    {selectedMissionId === mission.id && <span>현재 초안</span>}
                  </h3>
                  <p className="mission-meta">
                    {mission.waypoints.length}개 경유점 · 지도 버전{" "}
                    {mission.map.version}
                  </p>
                </div>
              </div>
              <button
                type="button"
                disabled={editingDisabled}
                onClick={() => onOpen(mission)}
                aria-label={`${mission.name} 임무 열기`}
              >
                임무 열기
              </button>
            </li>
          ))}
        </ul>
      )}
      {example && (
        <div className="ops-card ops-section-heading">
          <div>
            <h3>시연 예제</h3>
            <p className="mission-meta">{example.name}</p>
          </div>
          <button type="button" disabled={editingDisabled} onClick={onExample}>
            예제 임무 열기
          </button>
        </div>
      )}
      {archive.length > 0 && (
        <details className="mission-archive">
          <summary>이전 합성 임무 보관함 ({archive.length}개)</summary>
          <p className="mission-meta">
            열람용 보관함입니다. 캠퍼스에서 실행하려면 실제 지도에서 경로를
            작성하세요.
          </p>
          <ul className="mission-list" aria-label="보관한 합성 임무">
            {archive.map((mission) => (
              <li key={mission.id}>
                <div className="mission-list-description">
                  <div>
                    <h3>{mission.name.trim() || "이름 없는 임무"}</h3>
                    <p className="mission-meta">
                      {mission.waypoints.length}개 경유점 · {mission.map.frame}{" "}
                      · 지도 버전 {mission.map.version}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
