// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Focus, Map as MapIcon } from "lucide-react";
import { CampusRouteMap } from "./CampusRouteMap";
import { MapView } from "./MapView";
import { CampusMissionEditor } from "./MissionEditor";
import { AutoControls } from "./OperationControls";
import {
  commandBlock,
  missionError,
  type DemoOperations,
  type OperationCommand,
  type OperationState,
} from "./operation";
import { TeleopControls } from "./TeleopControls";
import type { ConsoleIncident } from "./IncidentsView";
import type { useCampusMissions } from "./useCampusMissions";

type Props = {
  demo: boolean;
  engine: DemoOperations;
  state: OperationState;
  campus: ReturnType<typeof useCampusMissions>;
  stale: boolean;
  settingsOpen: boolean;
  selectedIncidentId?: string;
  liveIncident?: ConsoleIncident["pose"];
  onSelectIncident: (id: string) => void;
  onCommand: (command: OperationCommand) => void;
};

export function OperationsWorkspace({
  demo,
  engine,
  state,
  campus,
  stale,
  settingsOpen,
  selectedIncidentId,
  liveIncident,
  onSelectIncident,
  onCommand,
}: Props) {
  const [mapFocus, setMapFocus] = useState(false);
  const [routePending, setRoutePending] = useState(false);
  const { site, draft } = campus;
  const auto = state.mode === "AUTO";
  const run = state.run?.mission.routing === "campus" ? state.run : undefined;
  const busy = run?.status === "running" || run?.status === "paused";
  const map = site?.network.identity;
  const sameMap = (other?: typeof map) =>
    !!map &&
    other?.id === map.id &&
    other.version === map.version &&
    other.frame === map.frame;
  const visibleDraft = sameMap(draft?.map) ? draft : undefined;
  const mapIncidents = state.incidents.filter((item) => sameMap(item.map));
  const modeBlocked = commandBlock(state, "TELEOP");
  const teleopBlocked = settingsOpen
    ? "연결 설정을 닫은 뒤 조작하세요."
    : !site || !state.campus
      ? "캠퍼스 지도를 불러온 뒤 조작할 수 있습니다."
      : modeBlocked;

  return (
    <div
      className={
        "ops-workspace" +
        (demo ? " ops-campus-workspace" : "") +
        (mapFocus ? " focus-map" : "")
      }
    >
      {demo && (
        <div className="ops-card ops-mode-card">
          <div
            className="ops-mode-switch"
            role="group"
            aria-label="운용 모드 선택"
          >
            <button
              aria-pressed={!auto}
              disabled={!!modeBlocked}
              onClick={() => {
                if (auto) onCommand({ type: "mode", mode: "TELEOP" });
              }}
            >
              {state.run?.status === "running" ? "TELEOP 개입" : "TELEOP"}
            </button>
            <button
              aria-pressed={auto}
              disabled={!!modeBlocked}
              onClick={() => {
                if (!auto) onCommand({ type: "mode", mode: "AUTO" });
              }}
            >
              AUTO
            </button>
          </div>
          <a
            className="ops-mobile-jump"
            href="#operation-controls"
            aria-label="운용 조작으로 이동"
          >
            조작 ↓
          </a>
        </div>
      )}
      <section
        className="ops-card ops-map"
        id="operation-map"
        tabIndex={-1}
        aria-label={demo ? "캠퍼스 지도" : "ROS 위치·센서 지도"}
      >
        <div className="ops-section-heading">
          <h3>
            <MapIcon size={17} aria-hidden="true" />{" "}
            {demo ? "캠퍼스 지도" : "ROS 위치·센서 지도"}
          </h3>
          <button
            aria-pressed={mapFocus}
            onClick={() => setMapFocus(!mapFocus)}
          >
            <Focus size={16} aria-hidden="true" />
            {mapFocus ? "기본 크기" : "지도 넓게 보기"}
          </button>
        </div>
        {demo ? (
          <>
            <CampusRouteMap
              data={site?.data}
              loadError={campus.loadError}
              editing={auto && !busy}
              draft={visibleDraft}
              run={run}
              position={state.campus?.pose}
              trail={state.campus?.trail}
              incidents={mapIncidents}
              selectedIncidentId={selectedIncidentId}
              onSelectIncident={onSelectIncident}
              onPendingRouteChange={setRoutePending}
              onApply={campus.applyRoute}
            />
            {campus.loadError && (
              <button onClick={campus.retry}>지도 다시 불러오기</button>
            )}
          </>
        ) : (
          <MapView
            incident={
              liveIncident && { ...liveIncident, z: liveIncident.z ?? 0 }
            }
          />
        )}
        {stale && (
          <p className="ops-help" role="status">
            수신이 지연되어 마지막 위치를 표시합니다.
          </p>
        )}
      </section>

      <section
        className="ops-card ops-control"
        id="operation-controls"
        tabIndex={-1}
        aria-label="운용 조작"
      >
        <div className="ops-section-heading">
          <h3>운용 조작</h3>
          {demo && (
            <div className="ops-row">
              <span>{state.battery}% 배터리</span>
              <a
                className="ops-mobile-jump"
                href="#operation-map"
                aria-label="캠퍼스 지도로 이동"
              >
                지도 ↑
              </a>
            </div>
          )}
        </div>
        {demo ? (
          <>
            {auto ? (
              <AutoControls
                state={state}
                draft={draft}
                editingRoute={routePending}
                campusNetwork={site?.network}
                onCommand={onCommand}
              >
                {draft && !busy && (
                  <CampusMissionEditor
                    draft={draft}
                    invalid={missionError(draft, undefined, site?.network)}
                    status={campus.status}
                    onName={(name) => campus.changeDraft({ ...draft, name })}
                    onSave={campus.saveDraft}
                  />
                )}
                {!draft && site?.example && !busy && !routePending && (
                  <button
                    onClick={() => campus.changeDraft(campus.exampleDraft())}
                  >
                    예제 임무 열기
                  </button>
                )}
                {!draft && campus.status && (
                  <p className="ops-help" role="status">
                    {campus.status}
                  </p>
                )}
              </AutoControls>
            ) : (
              <>
                <TeleopControls
                  state={state}
                  adapter={engine}
                  disabledReason={teleopBlocked}
                />
                {state.run?.status === "paused" && (
                  <p className="ops-help">
                    일시정지된 임무는 AUTO에서 재개할 수 있습니다.
                  </p>
                )}
              </>
            )}
          </>
        ) : (
          <p className="ops-help">
            ROS LIVE에서 위치와 센서 상태를 수신합니다. 운용 명령은 DEMO에서
            사용할 수 있습니다.
          </p>
        )}
      </section>
    </div>
  );
}
