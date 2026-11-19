// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity,
  ChevronRight,
  Settings2,
  Plug,
  FlaskConical,
  Download,
  Pause,
  Play,
  Radio,
  Terminal,
  X,
  Upload,
  Unplug,
  Circle,
  Square,
} from "lucide-react";
import { PCDLoader } from "three/addons/loaders/PCDLoader.js";
import { telemetry as s, demo } from "./store";
import { connect } from "./bridge";
import { BagRecorder } from "./recorder";
import {
  csv,
  mapLabel,
  mapReviewLabel,
  type Config,
  type Sample,
} from "./model";
import { MapView } from "./MapView";
import { LidarView } from "./LidarView";
const n = (v: number | undefined, d = 2) =>
  v === undefined || !Number.isFinite(v) ? "N/A" : v.toFixed(d);
function LocalizationState() {
  const status = s.localization;
  const age = status ? Date.now() - status.received : undefined;
  const stale = age !== undefined && age >= s.config.timeout;
  return (
    <div className="localization-state">
      <div className="localization-label">
        <span>위치추정 상태</span>
        <span>
          {stale ? "상태 수신 지연" : status ? "상태 수신 중" : "상태 미수신"}
        </span>
      </div>
      <div className="localization-value">
        <strong data-code={status?.code} className={stale ? "stale" : ""}>
          {status?.label ??
            (s.liveSession || s.demo ? "상태 메시지 없음" : "대기 중")}
        </strong>
        <small>
          {status?.code === undefined ? "—" : "CODE " + status.code}
        </small>
      </div>
      <div className="localization-detail">
        {status?.issue ??
          (status
            ? "측정 t=" +
              (status.t === undefined ? "미제공" : status.t.toFixed(3) + " s") +
              " · 수신 " +
              Math.round(age!) +
              " ms 전"
            : "/localization/status · 코드 0–5")}
      </div>
      {status?.issue && (
        <details>
          <summary>수신 메시지 확인</summary>
          <pre>
            {JSON.stringify(
              status.raw,
              (_, v) => (typeof v === "bigint" ? String(v) : v),
              2,
            )}
          </pre>
        </details>
      )}
    </div>
  );
}
function State() {
  const a = s.current;
  const age = s.lastReceived ? Date.now() - s.lastReceived : undefined;
  return (
    <section className="panel state-panel">
      <div className="panel-head compact">
        <h2>
          <Activity size={14} /> Robot State
        </h2>
        <span className={s.receiving ? "status good" : "status"}>
          <i />
          {s.receiving ? "Odometry 수신 중" : "Odometry 수신 없음"}
        </span>
      </div>
      <LocalizationState />
      <div className="state-body">
        <div className="state-label">
          POSITION{" "}
          <span>
            m · {a?.frame || s.config.frame} → {a?.child || s.config.base}
          </span>
        </div>
        <div className="triplet">
          {(["x", "y", "z"] as const).map((k) => (
            <div key={k}>
              <small>{k.toUpperCase()}</small>
              <strong>{n(a?.p[k])}</strong>
            </div>
          ))}
        </div>
        <div className="attitude">
          {(["x", "y", "z"] as const).map((k, i) => (
            <div key={k}>
              <small>{["ROLL", "PITCH", "YAW"][i]}</small>
              <b>
                {n(a?.rpy[k], 1)}
                <em>°</em>
              </b>
            </div>
          ))}
        </div>
        <div className="metrics">
          <div>
            <small>수평 속력</small>
            <b>
              {n(a?.speed)}
              <em>m/s</em>
            </b>
          </div>
          <div title={a?.reason || "동일 시각·기준 좌표의 3D 위치 차이"}>
            <small>GT 위치 오차</small>
            <b>
              {n(a?.error, 3)}
              <em>m</em>
            </b>
          </div>
          <div>
            <small>마지막 LIO 수신</small>
            <b>
              {age === undefined ? "N/A" : n(age, 0)}
              <em>ms</em>
            </b>
          </div>
        </div>
        <div className="state-foot">
          {a
            ? `속력: ${a.speedSource} · 측정 t=${n(a.t, 3)} s`
            : "Odometry 메시지를 기다리고 있습니다."}
        </div>
      </div>
    </section>
  );
}
// Close the active bag and hand it to the browser as a download. Safe to call when idle.
async function finishRecording() {
  const recorder = s.recorder;
  if (!recorder) return;
  s.recorder = undefined;
  s.notify();
  try {
    const blob = await recorder.finish();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `hyper-${new Date(recorder.started).toISOString().replace(/[:.]/g, "-")}.mcap`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    s.event(
      `bag 저장: ${recorder.messages.toLocaleString()}개 메시지, ${(blob.size / 1e6).toFixed(1)} MB`,
    );
  } catch (e) {
    s.error = "bag 저장 실패: " + String(e);
  }
  s.notify();
}
function Logger() {
  const [paused, setPaused] = useState(false);
  const frozen = useRef<Sample[]>([]);
  const rows = paused ? frozen.current : s.rows;
  const exportCsv = () => {
    const url = URL.createObjectURL(
      new Blob([csv(s.rows, s.events, s.statuses)], {
        type: "text/csv;charset=utf-8",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `hyper-${s.demo ? "ui-test" : "telemetry"}-${Date.now()}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };
  return (
    <section className="panel logger">
      <div className="panel-head compact">
        <h2>
          <Terminal size={14} /> Telemetry Logger{" "}
          <span className="chip">{s.rows.length.toLocaleString()} / 6,000</span>
        </h2>
        <div className="toolbar">
          <span className="subtle">
            {paused ? "화면 정지 · 수집 계속" : "최근 200행 · 자동 갱신"}
          </span>
          <button
            onClick={() => {
              if (!paused) frozen.current = [...s.rows];
              setPaused(!paused);
            }}
          >
            {paused ? <Play size={13} /> : <Pause size={13} />}{" "}
            {paused ? "재개" : "일시정지"}
          </button>
          <button
            className={s.recorder ? "recording" : ""}
            disabled={!s.recorder && !s.liveSession}
            title={
              s.liveSession
                ? "받은 ROS 메시지를 원본(CDR) 그대로 ROS 2 bag(MCAP)으로 기록합니다. 대시보드가 구독한 토픽만 들어갑니다."
                : "ROS 수신 중에만 기록할 수 있습니다"
            }
            onClick={() => {
              if (s.recorder) void finishRecording();
              else {
                s.recorder = new BagRecorder(undefined, () => {
                  s.event("bag 1 GB 도달: 자동 저장");
                  void finishRecording();
                });
                s.recorder.seed(s.latched.values());
                s.event("bag 기록 시작");
                s.notify();
              }
            }}
          >
            {s.recorder ? <Square size={13} /> : <Circle size={13} />}{" "}
            {s.recorder
              ? `기록 종료 · ${(s.recorder.bytes / 1e6).toFixed(1)} MB`
              : "bag 기록"}
          </button>
          <button onClick={exportCsv}>
            <Download size={13} /> CSV 저장
          </button>
        </div>
      </div>
      <div className="log-table">
        <table>
          <thead>
            <tr>
              {[
                "SIM TIME (s)",
                "X (m)",
                "Y (m)",
                "Z (m)",
                "ROLL (°)",
                "PITCH (°)",
                "YAW (°)",
                "SPEED (m/s)",
                "GT ERROR (m)",
                "위치추정 상태",
                "LIO 수신",
              ].map((x) => (
                <th key={x}>{x}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(-200)
              .reverse()
              .map((a) => (
                <tr key={a.t}>
                  <td>{n(a.t, 3)}</td>
                  <td>{n(a.p.x, 3)}</td>
                  <td>{n(a.p.y, 3)}</td>
                  <td>{n(a.p.z, 3)}</td>
                  <td>{n(a.rpy.x, 2)}</td>
                  <td>{n(a.rpy.y, 2)}</td>
                  <td>{n(a.rpy.z, 2)}</td>
                  <td>{n(a.speed, 3)}</td>
                  <td title={a.reason}>{n(a.error, 3)}</td>
                  <td>{a.localization?.label || "N/A"}</td>
                  <td>
                    <span className="table-status">● 수신 중</span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {!rows.length && (
          <div className="log-empty">
            수신한 위치 데이터가 여기에 기록됩니다.
          </div>
        )}
      </div>
      <div className="logger-foot">
        <span>
          <i className={s.receiving ? "live-dot" : "idle-dot"} />
          {s.events.at(-1)?.event || "세션 준비 완료"}
          {s.events.length > 0 && ` · t=${n(s.events.at(-1)!.t, 2)} s`}
        </span>
        <span>BUFFER 6,000 · CSV에 시각·좌표계·GT·수신 이벤트 보존</span>
      </div>
    </section>
  );
}
function Settings({
  close,
  onConnect,
}: {
  close: () => void;
  onConnect: () => void;
}) {
  const [c, set] = useState<Config>({ ...s.config });
  const fields: [keyof Config, string][] = [
    ["url", "Foxglove WebSocket"],
    ["frame", "표시 기준 frame"],
    ["base", "추정·비교 기준점 frame"],
    ["lio", "공통 Odometry 토픽"],
    ["gt", "GT Odometry 토픽 (선택, SIM 등)"],
    ["scan", "현재 PointCloud2 토픽"],
    ["status", "LocalizationStatus 토픽"],
    ["statusField", "상태 코드 필드 경로 (기본 status · 미확정)"],
    ["prior", "Reference Map PointCloud2 토픽"],
  ];
  return (
    <div className="modal-backdrop">
      <form
        className="settings"
        onSubmit={(e) => {
          e.preventDefault();
          s.config = c;
          s.reset();
          close();
          onConnect();
        }}
      >
        <div className="panel-head">
          <div>
            <span className="eyebrow">DATA CONNECTION</span>
            <h2>데이터 연결 설정</h2>
          </div>
          <button type="button" aria-label="닫기" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <p>
          S-005 명세의 공통 토픽과 좌표를 사용합니다. GT 토픽과 상태 코드
          필드명은 실제 메시지를 확인해 지정하세요.
        </p>
        <div className="settings-grid">
          {fields.map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={String(c[key])}
                onChange={(e) => set({ ...c, [key]: e.target.value })}
                required={["url", "frame", "base", "lio"].includes(key)}
                placeholder={
                  key === "gt"
                    ? "비우면 GT 없음 (REAL). MuJoCo SIM: /ground_truth/odom"
                    : undefined
                }
              />
            </label>
          ))}
          <label>
            GT 시각 허용 차이 (초)
            <input
              type="number"
              min="0"
              max="0.2"
              step="0.001"
              value={c.tolerance}
              onChange={(e) => set({ ...c, tolerance: Number(e.target.value) })}
            />
          </label>
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={c.twistValid}
            onChange={(e) => set({ ...c, twistValid: e.target.checked })}
          />{" "}
          주행 속력에 LIO twist 선속도 사용 (FAST-LIO2는 twist 패치 필요, 0이면
          위치 차분으로 대체)
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={c.mapVerified}
            onChange={(e) => set({ ...c, mapVerified: e.target.checked })}
          />{" "}
          지도 좌표와 표시 frame의 정합을 확인함
        </label>
        <p>
          GT도 mlx_lidar와 같은 기준점을 사용해야 합니다. 상태 코드 필드명은
          명세 캡처에 없어 기본 status를 사용하며, 다르면 위 경로를 변경하세요.
        </p>
        <button className="primary" type="submit">
          <Plug size={15} /> 적용하고 연결
        </button>
      </form>
    </div>
  );
}
export default function App() {
  useSyncExternalStore(s.subscribe, () => s.version);
  const [settings, setSettings] = useState(false),
    [session, setSession] = useState<"none" | "demo" | "live">("none");
  const stop = useRef<(() => void) | undefined>(undefined);
  const upload = useRef<HTMLInputElement>(null);
  const [mapShare, setMapShare] = useState(68),
    [logHeight, setLogHeight] = useState(140),
    [stateHeight, setStateHeight] = useState(244);
  // Remembers which source "수신 시작" resumes after "수신 중지".
  const lastSource = useRef<"demo" | "live">("live");
  const workspace = useRef<HTMLElement>(null),
    rail = useRef<HTMLElement>(null);
  // Top menus are <details>; close any open one when the pointer lands outside it.
  useEffect(() => {
    const close = (e: PointerEvent) => {
      document
        .querySelectorAll<HTMLDetailsElement>("details.top-menu[open]")
        .forEach((menu) => {
          if (!menu.contains(e.target as Node)) menu.open = false;
        });
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  const startResize = (
    axis: "map" | "log" | "state",
    event: React.PointerEvent<HTMLButtonElement>,
  ) => {
    event.preventDefault();
    const element = event.currentTarget;
    element.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => {
      const r = workspace.current!.getBoundingClientRect();
      if (axis === "state") {
        const box = rail.current!.getBoundingClientRect();
        setStateHeight(
          Math.max(170, Math.min(box.height - 150, e.clientY - box.top)),
        );
      } else if (axis === "map")
        setMapShare(
          Math.max(45, Math.min(76, ((e.clientX - r.left) / r.width) * 100)),
        );
      else
        setLogHeight(
          Math.max(100, Math.min(r.height * 0.45, r.bottom - e.clientY)),
        );
    };
    const finish = () => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", finish);
      element.removeEventListener("pointercancel", finish);
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", finish);
    element.addEventListener("pointercancel", finish);
  };
  const begin = (kind: "demo" | "live") => {
    void finishRecording(); // reconnecting ends the current bag rather than mixing sessions
    stop.current?.();
    s.reset();
    try {
      stop.current = kind === "demo" ? demo(s) : connect(s);
      lastSource.current = kind;
      setSession(kind);
    } catch (error) {
      stop.current = undefined;
      s.connection = "연결 실패";
      s.error = String(error);
      s.notify();
      setSession("none");
    }
  };
  const load = (
    buffer: ArrayBuffer,
    mapVersion: string,
    meta: { review?: string; reviewReason?: string } = {},
  ) => {
    try {
      const points = new PCDLoader().parse(buffer);
      const attr = points.geometry.getAttribute("position");
      const classes = points.geometry.getAttribute("label");
      const labels: number[] | undefined = classes ? [] : undefined;
      const stride = Math.max(1, Math.ceil(attr.count / 100000));
      const out: number[] = [];
      for (let i = 0; i < attr.count; i += stride) {
        const xyz = [attr.getX(i), attr.getY(i), attr.getZ(i)];
        if (xyz.every(Number.isFinite)) {
          out.push(...xyz);
          labels?.push(mapLabel(classes.getX(i)));
        }
      }
      s.localPrior = {
        t: 0,
        frame: "unverified",
        mapVersion,
        ...meta,
        points: new Float32Array(out),
        labels: labels && Uint8Array.from(labels),
      };
      points.geometry.dispose();
      points.material.dispose();
      s.notify();
    } catch (e) {
      s.error = "PCD 읽기 실패: " + String(e);
      s.notify();
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal, cache: "no-cache" as const };
    fetch("/reference-map.json", options)
      .then(async (response) => {
        // No local map is a valid setup (fresh checkout, or ROS-published map only).
        if (response.status === 404) return;
        if (!response.ok) throw Error("지도 목록을 열 수 없습니다.");
        const manifest = await response.json();
        if (
          typeof manifest.file !== "string" ||
          !/^[a-zA-Z0-9._-]+\.pcd$/.test(manifest.file)
        )
          throw Error("잘못된 지도 파일명");
        const map = await fetch("/" + manifest.file, options);
        if (!map.ok) throw Error(manifest.file);
        const bytes = await map.arrayBuffer();
        if (!controller.signal.aborted && !s.localPrior)
          load(bytes, String(manifest.version), {
            review:
              typeof manifest.review_status === "string"
                ? manifest.review_status
                : undefined,
            reviewReason:
              typeof manifest.review_reason === "string"
                ? manifest.review_reason
                : undefined,
          });
      })
      .catch((e) => {
        if (!controller.signal.aborted && !s.localPrior) {
          s.error = "로컬 지도 읽기 실패: " + String(e);
          s.notify();
        }
      });
    const timer = setInterval(() => s.tick(), 200);
    if (new URLSearchParams(location.search).get("demo") === "1") begin("demo");
    return () => {
      controller.abort();
      clearInterval(timer);
      stop.current?.();
    };
  }, []);
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-symbol">
            H<span />
          </div>
          <div>
            <h1>
              HYPER<span>NOVA</span>
            </h1>
            <small>ROBOTICS / LOCALIZATION CONSOLE</small>
          </div>
        </div>
        <div className="header-divider" />
        <span className="mode-badge">
          {s.demo ? "DEMO" : s.liveSession ? "LIVE" : "IDLE"}
        </span>
        <div className="breadcrumb">
          Workspace <ChevronRight size={13} />
          <strong>위치추정 대시보드</strong>
        </div>
        <div className="top-spacer" />
        <div className="sim-clock">
          <small>SIM TIME</small>
          <b>
            {n(s.clockAvailable ? s.simTime : undefined, 3)}
            <em>s</em>
          </b>
        </div>
        <div className={"connection " + (session === "demo" ? "demo" : "")}>
          <i />
          {s.connection}
        </div>
        <button
          title="연결 설정"
          aria-label="연결 설정"
          onClick={() => setSettings(true)}
        >
          <Settings2 size={17} />
        </button>
      </header>
      <div className="workspace-title">
        <div>
          <span className="eyebrow">
            PERCEPTION WORKSPACE <span>/ 01</span>
          </span>
          <h2>
            Localization Dashboard <span>3D</span>
          </h2>
        </div>
        <div className="workspace-actions">
          <label className="source-select">
            데이터 소스{" "}
            <select
              aria-label="데이터 소스"
              value={session === "demo" ? "demo" : "live"}
              onChange={(e) => {
                if (e.target.value === "demo") begin("demo");
                else {
                  stop.current?.();
                  stop.current = undefined;
                  s.reset();
                  s.connection = "미연결";
                  setSession("none");
                  setSettings(true);
                }
              }}
            >
              <option value="demo">가상 데이터 (브라우저 생성)</option>
              <option value="live">실제 데이터 (ROS 수신)</option>
            </select>
          </label>

          <input
            type="file"
            accept=".pcd"
            hidden
            ref={upload}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) f.arrayBuffer().then((bytes) => load(bytes, f.name));
            }}
          />
          <details className="top-menu">
            <summary>지도 관리</summary>
            <div>
              <p>
                기본 지도는 자동으로 읽습니다. 다른 PCD를 비교할 때 파일을
                선택하세요.
              </p>
              {s.localPrior && (
                <p>
                  현재 지도 {s.localPrior.mapVersion} ·{" "}
                  {mapReviewLabel(s.localPrior.review)}
                  {s.localPrior.reviewReason && (
                    <small> ({s.localPrior.reviewReason})</small>
                  )}
                </p>
              )}
              <button onClick={() => upload.current?.click()}>
                다른 지도 파일 선택 (.pcd)
              </button>
              <small>파일은 이 브라우저 안에서만 읽습니다.</small>
            </div>
          </details>
          {/* One toggle: stop while receiving, resume the last source when idle. */}
          {session === "none" ? (
            <button
              aria-label="수신 시작"
              title={
                lastSource.current === "demo"
                  ? "가상 데이터를 다시 시작합니다"
                  : `${s.config.url}에 다시 연결합니다`
              }
              onClick={() => begin(lastSource.current)}
            >
              <Plug size={14} /> 수신 시작
            </button>
          ) : (
            <button
              aria-label="수신 중지"
              title="데이터 수신을 멈추고 화면 기록을 비웁니다 (bag 기록 중이면 저장)"
              onClick={() => {
                void finishRecording();
                stop.current?.();
                stop.current = undefined;
                s.connection = "미연결";
                s.reset();
                setSession("none");
              }}
            >
              <Unplug size={14} /> 수신 중지
            </button>
          )}
          <button className="primary" onClick={() => setSettings(true)}>
            <Plug size={14} /> ROS 주소·토픽 설정
          </button>
        </div>
      </div>
      {s.error && (
        <div className="error-bar" role="alert">
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
      <main
        className="resizable-workspace"
        ref={workspace}
        style={
          {
            "--map-share": mapShare + "%",
            "--log-height": logHeight + "px",
            "--state-height": stateHeight + "px",
          } as React.CSSProperties
        }
      >
        <MapView />
        <button
          className="layout-divider-v"
          aria-label="지도와 상태 너비 조절"
          onPointerDown={(e) => startResize("map", e)}
        />
        <aside className="right-rail" ref={rail}>
          <State />
          <button
            className="layout-divider-r"
            aria-label="상태와 LiDAR 높이 조절"
            onPointerDown={(e) => startResize("state", e)}
          />
          <section className="panel sensor-panel">
            <div className="panel-head compact">
              <h2>
                <Radio size={14} /> LiDAR 3D View
              </h2>
              <span className="subtle">CURRENT SCAN · 16:9</span>
            </div>
            <LidarView />
            <div className="sensor-foot">
              <span>{s.config.scan || "토픽 미지정"}</span>
              <span>
                {s.cloud && !s.mapCloud
                  ? "지도 변환 없음 · 원본 좌표"
                  : "드래그 회전 · 휠 확대"}
              </span>
            </div>
          </section>
        </aside>
        <button
          className="layout-divider-h"
          aria-label="Logger 높이 조절"
          onPointerDown={(e) => startResize("log", e)}
        />
        <Logger />
      </main>
      <footer>
        <span>
          <span className="footer-mark">H</span> HYPERNOVA{" "}
          <span className="footer-separator">/</span> S-005 · S-006
        </span>
        <span>
          {s.demo
            ? "합성 데이터로 화면 기능을 시험하고 있습니다."
            : "ROS 2 · Foxglove Bridge · 수신 전용"}
          <span className="footer-separator">/</span> FRAME {s.config.frame} ·
          METERS
        </span>
      </footer>
      {settings && (
        <Settings
          close={() => setSettings(false)}
          onConnect={() => begin("live")}
        />
      )}
    </div>
  );
}
