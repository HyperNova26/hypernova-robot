// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity,
  Crosshair,
  Settings2,
  Plug,
  Download,
  Pause,
  Play,
  Radio,
  Terminal,
  X,
  Square,
  Circle,
  Map as MapIcon,
} from "lucide-react";
import { PCDLoader } from "three/addons/loaders/PCDLoader.js";
import { telemetry as s } from "./store";
import { connect } from "./bridge";
import { BagRecorder } from "./recorder";
import {
  csv,
  mapLabel,
  mapReviewLabel,
  savedSettings,
  sources,
  type Config,
  type Sample,
  type Source,
} from "./model";
import { MapView } from "./MapView";
import { LidarView } from "./LidarView";
const n = (v: number | undefined, d = 2) =>
  v === undefined || !Number.isFinite(v) ? "N/A" : v.toFixed(d);
// Last data source and connection settings, per browser (a convenience, not shared state).
const storageKey = "hn-dashboard-connection";
function loadSettings() {
  try {
    return savedSettings(localStorage.getItem(storageKey));
  } catch {
    return savedSettings(null);
  }
}
function saveSettings(source: Source, config: Config) {
  try {
    localStorage.setItem(storageKey, JSON.stringify({ source, config }));
  } catch {
    // Private windows may refuse storage; the session still works with the values in memory.
  }
}
// Panel sizes: log width and position width in px, top-row and state shares in %.
type Layout = { log: number; top: number; position: number; state: number };
const layoutKey = "hn-dashboard-layout",
  layoutDefaults: Layout = { log: 400, top: 60, position: 290, state: 47 };
function loadLayout(): Layout {
  try {
    const saved = JSON.parse(localStorage.getItem(layoutKey) ?? "{}") ?? {};
    const out = { ...layoutDefaults };
    for (const k of Object.keys(out) as (keyof Layout)[])
      if (Number.isFinite(saved[k])) out[k] = saved[k];
    return out;
  } catch {
    return { ...layoutDefaults };
  }
}
const clamp = (v: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(hi, v));
// Drag handle between two panels; double-click restores the default sizes.
function Divider({
  axis,
  label,
  move,
  done,
  reset,
}: {
  axis: "x" | "y";
  label: string;
  move: (e: PointerEvent) => void;
  done: () => void;
  reset: () => void;
}) {
  return (
    <button
      className={"divider " + axis}
      aria-label={label}
      title={label + " · 두 번 누르면 기본 크기"}
      onDoubleClick={reset}
      onPointerDown={(event) => {
        event.preventDefault();
        const el = event.currentTarget;
        el.setPointerCapture(event.pointerId);
        const finish = () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerup", finish);
          el.removeEventListener("pointercancel", finish);
          done();
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", finish);
        el.addEventListener("pointercancel", finish);
      }}
    />
  );
}
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
          {status?.label ?? (s.liveSession ? "상태 메시지 없음" : "대기 중")}
        </strong>
        <small>
          {status?.code === undefined ? "—" : "CODE " + status.code}
        </small>
      </div>
      <div className="localization-detail">
        {status?.issue ??
          (status
            ? (status.reason ? status.reason + " · " : "") +
              (status.rate !== undefined
                ? status.rate.toFixed(1) + " Hz · "
                : "") +
              "측정 t=" +
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
// G-006 /locomotion/status. Colour follows severity (OK/WARN/ERROR/STALE), not the code.
function LocomotionState() {
  const g = s.locomotion;
  const age = g ? Date.now() - g.received : undefined;
  const stale = age !== undefined && age >= s.config.timeout;
  return (
    <div className="localization-state">
      <div className="localization-label">
        <span>보행 상태 (G-006)</span>
        <span>
          {stale ? "상태 수신 지연" : g ? "상태 수신 중" : "상태 미수신"}
        </span>
      </div>
      <div className="localization-value">
        <strong
          data-severity={g?.severity}
          className={stale ? "stale" : ""}
          title={g?.reason}
        >
          {g
            ? g.label + (g.reason ? ` · ${g.reason}` : "")
            : s.liveSession
              ? "상태 메시지 없음"
              : "대기 중"}
        </strong>
        <small>{g ? `${g.severityLabel} · CODE ${g.code ?? "—"}` : "—"}</small>
      </div>
      <div className="localization-detail">
        {g?.issue ??
          (g
            ? `기울기 ${n(g.tilt, 1)}° · R ${n(g.roll, 1)}° P ${n(g.pitch, 1)}° · ${n(g.speed)} m/s · 높이 ${n(g.height)} m · ${g.timeSource} ${g.t === undefined ? "미제공" : n(g.t, 2) + " s"}`
            : s.config.locomotion + " · 코드 0–6")}
      </div>
      {g?.issue && (
        <details>
          <summary>수신 메시지 확인</summary>
          <pre>
            {JSON.stringify(
              g.raw,
              (_, v) => (typeof v === "bigint" ? String(v) : v),
              2,
            )}
          </pre>
        </details>
      )}
    </div>
  );
}
function StatePanel() {
  return (
    <section className="panel state-panel">
      <div className="panel-head compact">
        <h2>
          <Activity size={14} /> 상태
        </h2>
        <span className={s.receiving ? "status good" : "status"}>
          <i />
          {s.receiving ? "Odometry 수신 중" : "Odometry 수신 없음"}
        </span>
      </div>
      <LocalizationState />
      <LocomotionState />
    </section>
  );
}
function PositionPanel() {
  const a = s.current;
  const age = s.lastReceived ? Date.now() - s.lastReceived : undefined;
  return (
    <section className="panel position-panel">
      <div className="panel-head compact">
        <h2>
          <Crosshair size={14} /> 위치
        </h2>
        <span className="subtle" title="표시 기준 frame → 추정 기준점 frame">
          {a?.frame || s.config.frame} → {a?.child || s.config.base}
        </span>
      </div>
      <div className="position-body">
        <div className="position-xyz">
          {(["x", "y", "z"] as const).map((k) => (
            <div key={k}>
              <small>{k.toUpperCase()}</small>
              <strong>{n(a?.p[k])}</strong>
              <em>m</em>
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
          <div title={a ? `속력: ${a.speedSource}` : undefined}>
            <small>수평 속력</small>
            <b>
              {n(a?.speed)}
              <em>m/s</em>
            </b>
          </div>
          {s.config.gt && (
            <div title={a?.reason || "동일 시각·기준 좌표의 3D 위치 차이"}>
              <small>GT 위치 오차</small>
              <b>
                {n(a?.error, 3)}
                <em>m</em>
              </b>
            </div>
          )}
          <div>
            <small>마지막 수신</small>
            <b>
              {age === undefined ? "N/A" : n(age, 0)}
              <em>ms 전</em>
            </b>
          </div>
        </div>
        <div className="state-foot">
          {a
            ? `측정 t=${n(s.shown(a.t), 3)} s`
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
// Narrow log column: the latest 100 rows, main numbers only; every field (status, GT time, ...) is in the CSV.
function Logger() {
  const [paused, setPaused] = useState(false);
  const frozen = useRef<Sample[]>([]);
  const rows = paused ? frozen.current : s.rows;
  const gt = !!s.config.gt;
  const exportCsv = () => {
    const url = URL.createObjectURL(
      new Blob([csv(s.rows, s.events, s.statuses, s.gait)], {
        type: "text/csv;charset=utf-8",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `hyper-telemetry-${Date.now()}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };
  return (
    <section className="panel logger">
      <div className="panel-head compact">
        <h2>
          <Terminal size={14} /> 로그{" "}
          <span className="chip">{s.rows.length.toLocaleString()} / 6,000</span>
        </h2>
        <span className="subtle">
          {paused ? "화면 정지 · 수집 계속" : "최근 100행"}
        </span>
      </div>
      <div className="toolbar">
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
          disabled={!s.recorder && s.link !== "open"}
          title={
            s.link === "open"
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
        <button onClick={exportCsv} title="시각·좌표계·GT·상태·수신 이벤트 전체">
          <Download size={13} /> CSV
        </button>
      </div>
      <div className="log-table">
        <table>
          <thead>
            <tr>
              {["t (s)", "X", "Y", "Z", "YAW°", "m/s", ...(gt ? ["GT 오차"] : [])].map(
                (x) => (
                  <th key={x}>{x}</th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(-100)
              .reverse()
              .map((a) => (
                <tr
                  key={a.t}
                  title={`위치추정 ${a.localization?.label || "N/A"} · 보행 ${a.locomotion?.label || "N/A"}`}
                >
                  <td title={`stamp ${a.t.toFixed(3)} s`}>{n(s.shown(a.t), 2)}</td>
                  <td>{n(a.p.x, 2)}</td>
                  <td>{n(a.p.y, 2)}</td>
                  <td>{n(a.p.z, 2)}</td>
                  <td>{n(a.rpy.z, 1)}</td>
                  <td>{n(a.speed, 2)}</td>
                  {gt && <td title={a.reason}>{n(a.error, 3)}</td>}
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
        <i className={s.receiving ? "live-dot" : "idle-dot"} />
        <span>
          {s.events.at(-1)?.event || "세션 준비 완료"}
          {s.events.length > 0 && ` · t=${n(s.shown(s.events.at(-1)!.t), 2)} s`}
        </span>
      </div>
    </section>
  );
}
function Settings({
  initial,
  close,
  apply,
}: {
  initial: Config;
  close: () => void;
  apply: (config: Config) => void;
}) {
  const [c, set] = useState<Config>({ ...initial });
  const fields: [keyof Config, string][] = [
    ["url", "Foxglove WebSocket 주소"],
    ["frame", "표시 기준 frame"],
    ["base", "추정·비교 기준점 frame"],
    ["lio", "공통 Odometry 토픽"],
    ["gt", "GT Odometry 토픽 (선택, SIM 등)"],
    ["scan", "현재 PointCloud2 토픽"],
    ["status", "LocalizationStatus 토픽"],
    ["statusField", "상태 코드 필드 경로 (기본 status · 미확정)"],
    ["locomotion", "보행 상태 토픽 (G-006 LocomotionStatus)"],
    ["prior", "Reference Map PointCloud2 토픽"],
    ["path", "글로벌 경로 Path 토픽 (S-012, Nav2 기본 /plan)"],
  ];
  return (
    <div className="modal-backdrop">
      <form
        className="settings"
        onSubmit={(e) => {
          e.preventDefault();
          apply(c);
        }}
      >
        <div className="panel-head">
          <div>
            <span className="eyebrow">DATA CONNECTION</span>
            <h2>연결 설정</h2>
          </div>
          <button type="button" aria-label="닫기" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <p>
          주소나 토픽을 바꾸면 데이터 소스가 "직접 지정"으로 바뀝니다. S-005
          명세의 공통 토픽과 좌표가 기본값입니다.
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
          주행 속력에 LIO twist 선속도 사용 (0이면 위치 차분으로 대체)
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={c.mapVerified}
            onChange={(e) => set({ ...c, mapVerified: e.target.checked })}
          />{" "}
          지도 좌표와 표시 frame의 정합을 확인함 (로컬 PCD 지도를 ROS 좌표에
          겹쳐 표시)
        </label>
        <button className="primary" type="submit">
          <Plug size={15} /> 적용하고 연결
        </button>
      </form>
    </div>
  );
}
export default function App() {
  useSyncExternalStore(s.subscribe, () => s.version);
  const [settings, setSettings] = useState(false);
  const [source, setSource] = useState<Source>(() => {
    const saved = loadSettings();
    s.config = saved.config;
    return saved.source;
  });
  const stop = useRef<(() => void) | undefined>(undefined);
  const [layout, setLayout] = useState<Layout>(loadLayout);
  const layoutNow = useRef(layout);
  layoutNow.current = layout;
  const mainBox = useRef<HTMLElement>(null),
    leftBox = useRef<HTMLDivElement>(null),
    topBox = useRef<HTMLDivElement>(null),
    bottomBox = useRef<HTMLDivElement>(null);
  const resize =
    (
      box: React.RefObject<HTMLElement | null>,
      size: (r: DOMRect, e: PointerEvent) => Partial<Layout>,
    ) =>
    (e: PointerEvent) => {
      const r = box.current?.getBoundingClientRect();
      if (r) setLayout((l) => ({ ...l, ...size(r, e) }));
    };
  const saveLayout = () => {
    try {
      localStorage.setItem(layoutKey, JSON.stringify(layoutNow.current));
    } catch {
      // Sizes still apply for this page.
    }
  };
  const resetLayout = () => {
    setLayout({ ...layoutDefaults });
    try {
      localStorage.removeItem(layoutKey);
    } catch {
      // nothing saved
    }
  };
  const upload = useRef<HTMLInputElement>(null);
  const begin = () => {
    void finishRecording(); // reconnecting ends the current bag rather than mixing sessions
    stop.current?.();
    s.reset();
    try {
      stop.current = connect(s);
    } catch (error) {
      stop.current = undefined;
      s.connection = "연결 실패";
      s.error = String(error);
      s.notify();
    }
  };
  const end = () => {
    void finishRecording();
    stop.current?.();
    stop.current = undefined;
    s.connection = "미연결";
    s.reset();
  };
  const choose = (next: Source, config: Config) => {
    s.config = { ...config, ...sources[next].config };
    setSource(next);
    saveSettings(next, s.config);
    if (stop.current) begin();
    else s.notify();
  };
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
    return () => {
      controller.abort();
      clearInterval(timer);
      stop.current?.();
    };
  }, []);
  const live = !!stop.current;
  const tone = !live
    ? "idle"
    : s.receiving
      ? "good"
      : s.link === "failed" || s.link === "closed"
        ? "bad"
        : "wait";
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-symbol">
            H<span />
          </div>
          <h1>
            HYPER<span>NOVA</span>
          </h1>
          <strong className="app-title">위치추정 대시보드</strong>
        </div>
        <div className="top-spacer" />
        <label className="source-select" title={sources[source].start}>
          <span>데이터 소스</span>
          <select
            aria-label="데이터 소스"
            value={source}
            onChange={(e) => {
              const next = e.target.value as Source;
              choose(next, s.config);
              if (next === "custom") setSettings(true);
            }}
          >
            {(Object.keys(sources) as Source[]).map((key) => (
              <option key={key} value={key}>
                {sources[key].label}
              </option>
            ))}
          </select>
        </label>
        {/* One toggle: stop while a session is open (even a failed one), start otherwise. */}
        {live && s.link !== "failed" && s.link !== "closed" ? (
          <button
            className="receive stop"
            aria-label="수신 중지"
            title="데이터 수신을 멈추고 화면 기록을 비웁니다 (bag 기록 중이면 저장)"
            onClick={end}
          >
            <Square size={14} /> 수신 중지
          </button>
        ) : (
          <button
            className="receive"
            aria-label="수신 시작"
            title={`${s.config.url}에 연결합니다${sources[source].start ? ` · 먼저 ${sources[source].start}` : ""}`}
            onClick={begin}
          >
            <Play size={15} /> {live ? "다시 연결" : "수신 시작"}
          </button>
        )}
        <div
          className={"connection " + tone}
          title={`${s.config.url} · 수신 전용 (브라우저는 ROS 메시지를 보내지 않음)`}
        >
          <i />
          <span>{s.connection}</span>
          <b>
            {s.t0 !== undefined && s.t0 > 1e8 ? "경과" : "SIM"}{" "}
            {n(s.clockAvailable ? s.shown(s.simTime) : undefined, 1)}
            <em>s</em>
          </b>
        </div>
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
          <summary title="지도 관리">
            <MapIcon size={15} />
          </summary>
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
        <button
          className="icon"
          title="연결 설정 (주소·토픽)"
          aria-label="연결 설정"
          onClick={() => setSettings(true)}
        >
          <Settings2 size={16} />
        </button>
      </header>
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
        className="dash"
        ref={mainBox}
        style={
          {
            "--log-w": layout.log + "px",
            "--top-h": layout.top + "%",
            "--pos-w": layout.position + "px",
            "--state-w": layout.state + "%",
          } as React.CSSProperties
        }
      >
        <div className="dash-left" ref={leftBox}>
          <div className="dash-top" ref={topBox}>
            <MapView />
            <Divider
              axis="x"
              label="지도와 위치 패널 너비 조절"
              move={resize(topBox, (r, e) => ({
                position: clamp(r.right - e.clientX, 200, r.width * 0.5),
              }))}
              done={saveLayout}
              reset={resetLayout}
            />
            <PositionPanel />
          </div>
          <Divider
            axis="y"
            label="위아래 패널 높이 조절"
            move={resize(leftBox, (r, e) => ({
              top: clamp(((e.clientY - r.top) / r.height) * 100, 30, 80),
            }))}
            done={saveLayout}
            reset={resetLayout}
          />
          <div className="dash-bottom" ref={bottomBox}>
            <StatePanel />
            <Divider
              axis="x"
              label="상태와 LiDAR 패널 너비 조절"
              move={resize(bottomBox, (r, e) => ({
                state: clamp(((e.clientX - r.left) / r.width) * 100, 20, 80),
              }))}
              done={saveLayout}
              reset={resetLayout}
            />
            <section className="panel sensor-panel">
              <div className="panel-head compact">
                <h2>
                  <Radio size={14} /> LiDAR 현재 스캔
                </h2>
                <span className="subtle">
                  {s.config.scan || "토픽 미지정"} · 드래그 회전 · 휠 확대
                </span>
              </div>
              <LidarView />
            </section>
          </div>
        </div>
        <Divider
          axis="x"
          label="로그 너비 조절"
          move={resize(mainBox, (r, e) => ({
            log: clamp(r.right - e.clientX - 14, 260, r.width * 0.5),
          }))}
          done={saveLayout}
          reset={resetLayout}
        />
        <Logger />
      </main>
      {settings && (
        <Settings
          initial={s.config}
          close={() => setSettings(false)}
          apply={(config) => {
            const preset = sources[source].config as Partial<Config>;
            const same = (Object.keys(preset) as (keyof Config)[]).every(
              (k) => config[k] === preset[k],
            );
            setSettings(false);
            choose(same ? source : "custom", config);
            if (!stop.current) begin();
          }}
        />
      )}
    </div>
  );
}
