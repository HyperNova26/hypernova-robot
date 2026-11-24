// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  RotateCcw,
  RotateCw,
} from "lucide-react";
import {
  teleopSpeedRange,
  type CommandAdapter,
  type OperationState,
} from "./operation";

const moves = [
  {
    code: "ArrowUp",
    key: "↑",
    label: "전진",
    axis: "forward",
    value: 1,
    icon: ArrowUp,
  },
  {
    code: "ArrowDown",
    key: "↓",
    label: "후진",
    axis: "forward",
    value: -1,
    icon: ArrowDown,
  },
  {
    code: "ArrowLeft",
    key: "←",
    label: "왼쪽 이동",
    axis: "left",
    value: 1,
    icon: ArrowLeft,
  },
  {
    code: "ArrowRight",
    key: "→",
    label: "오른쪽 이동",
    axis: "left",
    value: -1,
    icon: ArrowRight,
  },
  {
    code: "KeyZ",
    key: "Z",
    label: "왼쪽 회전",
    axis: "turn",
    value: 1,
    icon: RotateCcw,
  },
  {
    code: "KeyX",
    key: "X",
    label: "오른쪽 회전",
    axis: "turn",
    value: -1,
    icon: RotateCw,
  },
] as const;
type Move = (typeof moves)[number];
const ignoresTeleop = (target: EventTarget | null) =>
  target instanceof Element &&
  !target.closest(".ops-teleop-buttons") &&
  Boolean(
    target.closest(
      "input,textarea,select,button,a,[contenteditable]:not([contenteditable=false]),[data-teleop-ignore]",
    ),
  );

export function TeleopControls({
  state,
  adapter,
  disabledReason,
}: {
  state: OperationState;
  adapter: CommandAdapter;
  disabledReason?: string;
}) {
  const inputs = useRef(new Map<string, Move>());
  const [pressed, setPressed] = useState<string[]>([]);
  const [failure, setFailure] = useState("");
  const send = useCallback(() => {
    const movement = { forward: 0, left: 0, turn: 0 };
    for (const { axis, value } of inputs.current.values())
      movement[axis] += value;
    const result = inputs.current.size
      ? adapter.request({
          type: "teleop",
          forward: Math.sign(movement.forward),
          left: Math.sign(movement.left),
          turn: Math.sign(movement.turn),
        })
      : adapter.request({ type: "release" });
    if (!result.ok) inputs.current.clear();
    setFailure(result.ok || result.code === "duplicate" ? "" : result.reason);
    setPressed([...inputs.current.values()].map((move) => move.code));
  }, [adapter]);
  const release = useCallback(() => {
    if (inputs.current.size) {
      inputs.current.clear();
      send();
    }
  }, [send]);
  const change = (id: string, move?: Move) => {
    if (move) inputs.current.set(id, move);
    else if (!inputs.current.delete(id)) return;
    send();
  };
  useEffect(() => {
    if (disabledReason) {
      release();
      setPressed([]);
      return;
    }
    const down = (event: KeyboardEvent) => {
      const move = moves.find(({ code }) => code === event.code);
      if (
        !move ||
        event.repeat ||
        event.isComposing ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        ignoresTeleop(event.target)
      )
        return;
      event.preventDefault();
      inputs.current.set("key:" + move.code, move);
      send();
    };
    const up = (event: KeyboardEvent) => {
      if (inputs.current.delete("key:" + event.code)) {
        event.preventDefault();
        send();
      }
    };
    const hidden = () => {
      if (document.hidden) release();
    };
    const focus = (event: FocusEvent) => {
      if (ignoresTeleop(event.target)) release();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", release);
    document.addEventListener("visibilitychange", hidden);
    document.addEventListener("focusin", focus);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", release);
      document.removeEventListener("visibilitychange", hidden);
      document.removeEventListener("focusin", focus);
      if (inputs.current.size) {
        inputs.current.clear();
        adapter.request({ type: "release" });
      }
    };
  }, [adapter, disabledReason, release, send]);

  const row = (move: Move) => {
    const Icon = move.icon;
    return (
      <button
        type="button"
        key={move.code}
        aria-label={move.label}
        className={pressed.includes(move.code) ? "active" : ""}
        disabled={!!disabledReason}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          change("pointer:" + event.pointerId, move);
        }}
        onPointerUp={(event) => change("pointer:" + event.pointerId)}
        onPointerCancel={(event) => change("pointer:" + event.pointerId)}
        onLostPointerCapture={(event) => change("pointer:" + event.pointerId)}
        onContextMenu={(event) => event.preventDefault()}
        onKeyDown={(event) => {
          if (event.code !== "Space" && event.code !== "Enter") return;
          event.preventDefault();
          if (!event.repeat) change("button:" + event.code, move);
        }}
        onKeyUp={(event) => change("button:" + event.code)}
        onBlur={() => release()}
      >
        <Icon size={17} aria-hidden="true" />
        <span>{move.label}</span>
        <kbd>{move.key}</kbd>
      </button>
    );
  };
  return (
    <>
      <p className="ops-help">
        방향키로 이동하고 Z / X로 회전합니다. 누르고 있는 동안에만 움직입니다.
      </p>
      <div className="ops-teleop-buttons">{moves.map(row)}</div>
      <label className="ops-range">
        <span>
          데모 속도 설정 <b>{state.teleopSpeed.toFixed(1)} m/s</b>
        </span>
        <input
          type="range"
          min={teleopSpeedRange.min}
          max={teleopSpeedRange.max}
          step="0.1"
          value={state.teleopSpeed}
          disabled={!!disabledReason}
          onChange={(event) => {
            const result = adapter.request({
              type: "speed",
              speed: Number(event.currentTarget.value),
            });
            setFailure(result.ok ? "" : result.reason);
          }}
        />
      </label>
      <dl className="ops-measurements">
        <div>
          <dt>명령 속도</dt>
          <dd>
            {Math.hypot(state.requested.forward, state.requested.left).toFixed(
              2,
            )}{" "}
            m/s
            <br />
            {state.requested.turn.toFixed(0)} °/s
          </dd>
        </div>
        <div>
          <dt>관측 속도</dt>
          <dd>
            {Math.hypot(state.observed.forward, state.observed.left).toFixed(2)}{" "}
            m/s
            <br />
            {state.observed.turn.toFixed(0)} °/s
          </dd>
        </div>
      </dl>
      {(disabledReason || failure) && (
        <p className="ops-help" role="status">
          {disabledReason || failure}
        </p>
      )}
    </>
  );
}
