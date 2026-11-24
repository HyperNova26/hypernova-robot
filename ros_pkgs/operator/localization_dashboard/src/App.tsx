// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AlertTriangle, Plug, Radio, Square, Unplug } from "lucide-react";
import {
  ConnectionSettings,
  Diagnostics,
  finishRecording,
  useLocalMap,
} from "./Diagnostics";
import {
  IncidentsView,
  demoIncident,
  incidentActive,
  rosIncident,
  useIncidentSound,
  type ConsoleIncident,
  type IncidentResponse,
} from "./IncidentsView";
import { MissionLibrary } from "./MissionEditor";
import {
  missionPhase,
  RecordControl,
  ScenarioPanel,
} from "./OperationControls";
import {
  DemoOperations,
  type Mission,
  type OperationCommand,
} from "./operation";
import { OperationsWorkspace } from "./OperationsWorkspace";
import { demoSample, rosSample, trackDemoRecording } from "./recordOperation";
import { findRecord, useRecordings, type RecordSelection } from "./recordings";
import { RecordsView } from "./RecordsView";
import {
  demoSource,
  liveSource,
  type CurrentSource,
  type TelemetrySource,
} from "./sources";
import { telemetry as s } from "./store";
import {
  respondToLiveIncident,
  updateLiveIncidents,
  type LiveIncident,
} from "./liveIncidents";
import { useCampusMissions } from "./useCampusMissions";
import "./operations.css";

type Screen = "operate" | "missions" | "incidents" | "records";
const nav: [Screen, string][] = [
  ["operate", "운용"],
  ["missions", "임무 관리"],
  ["incidents", "알람·이상 이력"],
  ["records", "기록 열람"],
];
const rosControls = "ROS LIVE 수신 전용 · 명령 연결 없음";
const incidentStorage = "hypernova.incident-history.v1";

function loadIncidentHistory(): ConsoleIncident[] {
  try {
    const entries: unknown = JSON.parse(
      localStorage.getItem(incidentStorage) ?? "[]",
    );
    return Array.isArray(entries)
      ? entries
          .filter(
            (item) =>
              item &&
              typeof item.id === "string" &&
              typeof item.openedAt === "number" &&
              (item.source === "DEMO" || item.source === "ROS LIVE") &&
              Array.isArray(item.history),
          )
          .map((incident) => ({ ...incident, archived: true }))
      : [];
  } catch {
    return [];
  }
}

export default function App() {
  const [engine] = useState(() => new DemoOperations());
  const state = useSyncExternalStore(engine.subscribe, engine.getSnapshot);
  const version = useSyncExternalStore(s.subscribe, () => s.version);
  const [source, setSource] = useState<CurrentSource>("DEMO");
  const currentSource = useRef<CurrentSource>("DEMO");
  const [screen, setScreen] = useState<Screen>("operate");
  const [settings, setSettings] = useState(false);
  const [selectedIncident, setSelectedIncident] = useState<string>();
  const [recordSelection, setRecordSelection] = useState<RecordSelection>();
  const campus = useCampusMissions(engine);
  const [feedback, setFeedback] = useState("");
  const [liveIncidents, setLiveIncidents] = useState<LiveIncident[]>([]);
  const liveIncidentRef = useRef<LiveIncident[]>([]);
  const [archive, setArchive] = useState(loadIncidentHistory);
  const rosEpoch = useRef(s.epoch);
  const stopLive = useRef<() => void>(undefined);
  const opsBar = useRef<HTMLElement>(null);
  const { records, active, start, capture, mark, stop } = useRecordings();
  const demo = source === "DEMO";
  const viewedSource: TelemetrySource["kind"] =
    screen === "records" ? "REPLAY" : source;
  useLocalMap();

  useEffect(() => {
    const bar = opsBar.current;
    if (!bar) return;
    const observer = new ResizeObserver(() => {
      document.documentElement.style.setProperty(
        "--ops-header-height",
        bar.offsetHeight + "px",
      );
    });
    observer.observe(bar);
    return () => observer.disconnect();
  }, []);

  const archiveIncidents = (incidents: ConsoleIncident[]) => {
    if (!incidents.length) return;
    setArchive((previous) => {
      const combined = new Map(
        previous.map((incident) => [incident.id, incident]),
      );
      for (const incident of incidents)
        combined.set(incident.id, {
          ...incident,
          archived: true,
          history: incident.history.slice(-20),
        });
      return [...combined.values()]
        .sort((a, b) => b.lastAt - a.lastAt)
        .slice(0, 80);
    });
  };
  useEffect(() => {
    const stored = new Map(archive.map((item) => [item.id, item]));
    const current =
      source === "DEMO"
        ? state.incidents.map(demoIncident)
        : liveIncidents.map(rosIncident);
    for (const incident of current)
      stored.set(incident.id, {
        ...incident,
        history: incident.history.slice(-20),
      });
    const latest = [...stored.values()]
      .sort((a, b) => b.lastAt - a.lastAt)
      .slice(0, 80);
    try {
      localStorage.setItem(incidentStorage, JSON.stringify(latest));
    } catch {
      /* Archived incidents remain available for this page session. */
    }
  }, [archive, source, state.incidents, liveIncidents]);

  useEffect(() => {
    const adapter = demoSource(s);
    let previous = engine.getSnapshot();
    const sample = () => {
      const current = engine.getSnapshot();
      if (currentSource.current === "DEMO" && current.campus) {
        const now = Date.now();
        if (current.sessionId === previous.sessionId)
          trackDemoRecording({ capture, mark }, current, previous, now);
        adapter.publish(current);
      }
      previous = current;
    };
    const unsubscribe = engine.subscribe(sample);
    const timer = window.setInterval(() => {
      if (currentSource.current === "DEMO") engine.tick();
    }, 50);
    const first = engine.getSnapshot();
    start({
      source: "DEMO",
      timeOrigin: first.timeOrigin,
      sessionId: first.sessionId,
    });
    sample();
    return () => {
      unsubscribe();
      window.clearInterval(timer);
      stopLive.current?.();
    };
  }, [engine, start, capture, mark]);

  useEffect(() => {
    if (source !== "ROS LIVE") return;
    if (rosEpoch.current !== s.epoch) {
      archiveIncidents(liveIncidentRef.current.map(rosIncident));
      liveIncidentRef.current = [];
      rosEpoch.current = s.epoch;
    }
    const now = Date.now();
    const previous = liveIncidentRef.current;
    const next = updateLiveIncidents(previous, s, now);
    if (next !== liveIncidents) setLiveIncidents(next);
    liveIncidentRef.current = next;
    if (s.current || next.length) {
      const open = next
        .filter((incident) => !incident.resolvedAt)
        .map((incident) => rosIncident(incident).title);
      capture(rosSample(s, now, open));
    }
    if (next !== previous) {
      for (const incident of next) {
        const old = previous.find((item) => item.id === incident.id);
        for (
          let index = old?.history.length ?? 0;
          index < incident.history.length;
          index++
        ) {
          const entry = incident.history[index];
          mark({
            id: `${incident.id}/${index}`,
            at: entry.at,
            incidentId: incident.id,
            title: entry.text,
          });
        }
      }
    }
  }, [source, version, capture, mark, liveIncidents]);

  const issue = (command: OperationCommand) => {
    if (currentSource.current !== "DEMO") return;
    const result = engine.request({ ...command, deadline: Date.now() + 500 });
    setFeedback(
      !result.ok
        ? result.reason
        : command.type === "stop"
          ? "모의 운용을 정지했습니다."
          : "",
    );
  };

  const changeScreen = (next: Screen) => {
    if (currentSource.current === "DEMO") engine.request({ type: "release" });
    setScreen(next);
    setFeedback("");
    if (next !== "records") setRecordSelection(undefined);
    if (next !== screen) window.scrollTo({ top: 0 });
  };

  function startCapture(snapshot = engine.getSnapshot()) {
    const now = Date.now();
    if (currentSource.current === "DEMO") {
      const sample = demoSample(snapshot, now);
      start({
        source: "DEMO",
        timeOrigin: now,
        sessionId: snapshot.sessionId,
        mission: snapshot.run?.mission.name,
      });
      if (snapshot.campus) capture(sample, true);
    } else {
      start({
        source: "ROS LIVE",
        timeOrigin: now,
        sessionId: `ros-${s.epoch}-${now}`,
      });
      if (s.current) capture(rosSample(s, now, []), true);
    }
  }

  function resetDemo() {
    archiveIncidents(engine.getSnapshot().incidents.map(demoIncident));
    stop("DEMO 세션 종료");
    issue({ type: "reset" });
    setSelectedIncident(undefined);
    startCapture();
  }

  function chooseSource(next: CurrentSource) {
    if (next === currentSource.current) return;
    if (next === "ROS LIVE") {
      engine.request({ type: "suspend" });
      archiveIncidents(engine.getSnapshot().incidents.map(demoIncident));
      stop("ROS LIVE 출처로 전환");
      currentSource.current = next;
      s.demo = false;
      s.connection = "미연결";
      s.reset();
      setSettings(true);
    } else {
      stop("DEMO 출처로 전환");
      void finishRecording();
      stopLive.current?.();
      stopLive.current = undefined;
      archiveIncidents(liveIncidentRef.current.map(rosIncident));
      liveIncidentRef.current = [];
      setLiveIncidents([]);
      currentSource.current = next;
      engine.request({ type: "reset" });
      startCapture();
      setSettings(false);
    }
    setSource(next);
    setSelectedIncident(undefined);
    setRecordSelection(undefined);
    setFeedback("");
  }

  function beginLive() {
    if (currentSource.current !== "ROS LIVE") chooseSource("ROS LIVE");
    setSettings(false);
    stop("ROS 연결 새 세션");
    void finishRecording();
    stopLive.current?.();
    stopLive.current = undefined;
    s.connection = "미연결";
    s.reset();
    try {
      stopLive.current = liveSource(s).subscribe(() => {
        stop("ROS 연결 종료 또는 시각 재설정");
        void finishRecording();
      });
    } catch (error) {
      s.transport = "closed";
      s.connection = "연결 실패";
      s.error = String(error);
      s.notify();
    }
  }

  function endLive() {
    stop("ROS 수신 중지");
    void finishRecording();
    stopLive.current?.();
    stopLive.current = undefined;
    s.connection = "수신 중지";
    s.transport = "idle";
    s.lastReceived = 0;
    s.tick();
  }

  const currentIncidents = demo
    ? state.incidents.map(demoIncident)
    : liveIncidents.map(rosIncident);
  const allIncidents = [
    ...currentIncidents,
    ...archive.filter(
      (record) => !currentIncidents.some((current) => current.id === record.id),
    ),
  ].sort((a, b) => b.lastAt - a.lastAt);
  const alerts = currentIncidents
    .filter(incidentActive)
    .sort((a, b) => b.lastAt - a.lastAt);
  const important =
    alerts.find((incident) => incident.severity === "critical") ?? alerts[0];
  useIncidentSound(alerts);
  const openIncident = (id: string) => {
    setSelectedIncident(id);
    changeScreen("incidents");
  };

  function incidentAction(
    incident: ConsoleIncident,
    action: IncidentResponse,
    text = "",
  ) {
    if (incident.archived || incident.source !== source) return;
    if (demo) {
      if (action === "recover") issue({ type: "recover", kind: incident.kind });
      else if (action === "note")
        issue({ type: "note", incidentId: incident.id, text });
      else issue({ type: action, incidentId: incident.id });
    } else if (action !== "recover") {
      const next = respondToLiveIncident(
        liveIncidentRef.current,
        incident.id,
        action,
        text,
      );
      for (const item of next) {
        const old = liveIncidentRef.current.find(
          (entry) => entry.id === item.id,
        );
        if (item === old || !old) continue;
        const entry = item.history.at(-1)!;
        mark({
          id: `${item.id}/${item.history.length - 1}`,
          at: entry.at,
          incidentId: item.id,
          title: entry.text,
        });
      }
      liveIncidentRef.current = next;
      setLiveIncidents(next);
    }
  }

  function openIncidentRecord(incident: ConsoleIncident) {
    const target = findRecord(records, { incidentId: incident.id });
    if (!target) return;
    if (target.record.active) {
      stop("사건 영상 처리");
      startCapture();
    }
    changeScreen("records");
    setRecordSelection({
      recordId: target.record.id,
      incidentId: incident.id,
      at: target.record.timeOrigin + target.offsetMs,
    });
  }

  function openMission(mission?: Mission) {
    if (!demo) return;
    if (state.run?.status === "running" || state.run?.status === "paused") {
      setFeedback(
        "현재 임무를 완료하거나 취소한 뒤 다른 임무를 열 수 있습니다.",
      );
      return;
    }
    const result = engine.request({ type: "mode", mode: "AUTO" });
    if (!result.ok) {
      setFeedback(result.reason);
      return;
    }
    campus.changeDraft(mission && structuredClone(mission));
    setSelectedIncident(undefined);
    changeScreen("operate");
  }

  function canShowIncident(incident: ConsoleIncident) {
    return (
      !incident.archived &&
      incident.source === source &&
      !!incident.pose &&
      (!demo || incident.pose.frame === campus.site?.network.identity.frame)
    );
  }

  const lastReceived = demo ? state.lastReceived : s.current?.received;
  const receivedAt =
    lastReceived === undefined ? undefined : new Date(lastReceived);
  const age =
    lastReceived === undefined
      ? undefined
      : Math.max(0, Date.now() - lastReceived);
  const stale = demo
    ? !state.connected || state.localization === "INPUT_TIMEOUT"
    : !!s.current && !s.receiving;
  const link = demo
    ? state.connected
      ? "모의 연결"
      : "모의 연결 끊김"
    : s.transport === "open"
      ? "Bridge 연결"
      : s.connection;
  const connected = !stale && (demo || s.transport === "open");
  const loc = demo
    ? state.localization
    : (s.localization?.label ?? "상태 미수신");
  const locStale = demo
    ? !state.connected
    : !!s.localization &&
      Date.now() - s.localization.received >= s.config.timeout;
  const mode = demo ? state.mode : undefined;
  const liveMarker = !demo
    ? currentIncidents.find((item) => item.id === selectedIncident)?.pose
    : undefined;
  return (
    <div className="ops-app">
      <header className="ops-header" ref={opsBar}>
        <div className="ops-header-top">
          <div className="ops-brand">
            <div className="brand-symbol" aria-hidden="true">
              H<span />
            </div>
            <div>
              <h1>HYPERNOVA</h1>
              <small>Hyper · 로봇 관제</small>
            </div>
          </div>
          <nav aria-label="관제 화면" className="ops-nav">
            {nav.map(([id, label]) => (
              <button
                key={id}
                aria-current={id === screen ? "page" : undefined}
                onClick={() => changeScreen(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="ops-header-actions">
            <label className="ops-source">
              <span>현재 출처</span>
              <select
                aria-label="현재 출처"
                value={source}
                onChange={(event) =>
                  chooseSource(event.currentTarget.value as CurrentSource)
                }
              >
                <option>DEMO</option>
                <option>ROS LIVE</option>
              </select>
            </label>
            <button
              className="ops-stop"
              disabled={!demo}
              onClick={() => issue({ type: "stop" })}
              title={!demo ? rosControls : "브라우저 모의 운용을 정지합니다."}
            >
              <Square size={16} aria-hidden="true" /> 운용 정지
            </button>
          </div>
        </div>
        <dl className="ops-status">
          <div>
            <dt>연결</dt>
            <dd className={stale ? "warning" : connected ? "connected" : ""}>
              {link}
            </dd>
          </div>
          <div>
            <dt>운용 모드</dt>
            <dd>{mode ?? "명령 미연결"}</dd>
          </div>
          <div>
            <dt>임무</dt>
            <dd>{demo ? missionPhase(state.run) : "미연결"}</dd>
          </div>
          <div>
            <dt>위치추정</dt>
            <dd className={locStale ? "warning" : ""}>
              {loc}
              {locStale ? " · 지연" : ""}
            </dd>
          </div>
          <div>
            <dt>마지막 수신</dt>
            <dd className={"ops-status-time" + (stale ? " warning" : "")}>
              {receivedAt && age !== undefined ? (
                <>
                  <time dateTime={receivedAt.toISOString()}>
                    {receivedAt.toLocaleTimeString("ko-KR", {
                      hourCycle: "h23",
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </time>
                  <span
                    className="ops-status-age"
                    title="마지막 Odometry 수신 이후 경과"
                  >
                    {(age / 1000).toFixed(1)}초{stale ? " 지연" : " 전"}
                  </span>
                </>
              ) : (
                "대기"
              )}
            </dd>
          </div>
          <div>
            <dt>활성 알람</dt>
            <dd>
              <button
                className="ops-status-link"
                onClick={() =>
                  important
                    ? openIncident(important.id)
                    : changeScreen("incidents")
                }
              >
                {alerts.length}건
              </button>
            </dd>
          </div>
          <div>
            <dt>기록</dt>
            <dd>
              {[active && "운용 기록 중", s.recorder && "MCAP 기록 중"]
                .filter(Boolean)
                .join(" · ") || "대기"}
            </dd>
          </div>
        </dl>
        {important && (
          <button
            className={"ops-alert-banner " + important.severity}
            onClick={() => openIncident(important.id)}
          >
            <AlertTriangle size={17} /> <strong>{important.title}</strong>
            <span>
              {important.acknowledgedAt ? "확인됨" : "미확인"} ·{" "}
              {important.count}회
            </span>
            <span className="ops-alert-link">알람 상세</span>
          </button>
        )}
      </header>
      <main className="ops-content" data-view-source={viewedSource}>
        {s.error && (
          <div className="ops-error" role="alert">
            {s.error}
            <button
              onClick={() => {
                s.error = "";
                s.notify();
              }}
            >
              닫기
            </button>
          </div>
        )}
        {feedback && (
          <div className="ops-feedback" role="status">
            {feedback}
            <button onClick={() => setFeedback("")}>닫기</button>
          </div>
        )}
        {screen === "operate" && (
          <>
            <div className="ops-view-heading">
              <div className="ops-site">
                <h2>{demo ? "경희대학교 국제캠퍼스" : "ROS LIVE 운용"}</h2>
                {demo && <p>전자정보대학관 및 인접 보행로</p>}
              </div>
              <div className="ops-row">
                {!demo && (
                  <>
                    <button onClick={() => setSettings(true)}>
                      <Plug size={16} /> ROS 주소·토픽 설정
                    </button>
                    {s.transport === "open" || s.transport === "connecting" ? (
                      <button onClick={endLive}>
                        <Unplug size={16} /> 수신 중지
                      </button>
                    ) : (
                      <button onClick={beginLive}>
                        <Radio size={16} /> 수신 시작
                      </button>
                    )}
                  </>
                )}
                <RecordControl
                  active={!!active}
                  onStart={() => startCapture()}
                  onStop={() => stop()}
                />
              </div>
            </div>
            <OperationsWorkspace
              key={source}
              demo={demo}
              engine={engine}
              state={state}
              campus={campus}
              stale={stale}
              settingsOpen={settings}
              selectedIncidentId={selectedIncident}
              liveIncident={liveMarker}
              onCommand={issue}
              onSelectIncident={openIncident}
            />
            <ScenarioPanel
              state={state}
              enabled={demo && !!state.campus}
              onCommand={issue}
              onReset={resetDemo}
            />
            <Diagnostics />
          </>
        )}
        {screen === "missions" && (
          <MissionLibrary
            missions={campus.library.value}
            example={campus.site?.example}
            onExample={() => openMission(campus.exampleDraft())}
            selectedMissionId={campus.draft?.id}
            onOpen={openMission}
            onNew={() => openMission()}
            editingDisabled={!demo}
            persistenceIssue={campus.library.error}
          />
        )}
        {screen === "incidents" && (
          <IncidentsView
            incidents={allIncidents}
            selectedId={selectedIncident}
            onSelect={setSelectedIncident}
            onResponse={incidentAction}
            onRecord={openIncidentRecord}
            canShowOnMap={canShowIncident}
            onMap={(incident) => {
              setSelectedIncident(incident.id);
              changeScreen("operate");
            }}
            hasRecord={(incident) =>
              !!findRecord(records, { incidentId: incident.id })
            }
          />
        )}
        {screen === "records" && (
          <RecordsView
            key={recordSelection?.recordId ?? "list"}
            records={records}
            selection={recordSelection}
            onReturn={() => changeScreen("operate")}
          />
        )}
      </main>
      {settings && (
        <ConnectionSettings
          close={() => setSettings(false)}
          onConnect={beginLive}
        />
      )}
    </div>
  );
}
