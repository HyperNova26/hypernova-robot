// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Display-only trot: joint angles come from foot targets, not from joint telemetry or a policy.
export type Leg = "FL" | "FR" | "RL" | "RR";
export const legs: Leg[] = ["FL", "FR", "RL", "RR"];
// Diagonal pairs move together (trot).
const offset: Record<Leg, number> = { FL: 0, RR: 0, FR: 0.5, RL: 0.5 };
export type LegGeometry = { thigh: number; calf: number };
export type Stand = { hip: number; thigh: number; calf: number };
export type GaitOptions = {
  stride: number; // m the body travels while one foot is on the ground
  lift: number; // m swing foot clearance
  duty: number; // stance share of a cycle
};
export const gaitDefaults: GaitOptions = {
  stride: 0.22,
  lift: 0.07,
  duty: 0.55,
};
// Rotation about +y by q maps (0,0,-l) to (-l sin q, 0, -l cos q).
export function footPosition(g: LegGeometry, thigh: number, calf: number) {
  return {
    x: -g.thigh * Math.sin(thigh) - g.calf * Math.sin(thigh + calf),
    z: -g.thigh * Math.cos(thigh) - g.calf * Math.cos(thigh + calf),
  };
}
// Sagittal two-link IK with the knee bent backwards (negative calf, as in the URDF limits).
export function legIK(g: LegGeometry, x: number, z: number) {
  const reach = g.thigh + g.calf - 1e-4,
    d = Math.min(
      Math.max(Math.hypot(x, z), Math.abs(g.thigh - g.calf) + 1e-4),
      reach,
    );
  const cosKnee =
    (d * d - g.thigh * g.thigh - g.calf * g.calf) / (2 * g.thigh * g.calf);
  const calf = -Math.acos(Math.min(1, Math.max(-1, cosKnee)));
  const angle = (vx: number, vz: number) => Math.atan2(-vx, -vz);
  const local = footPosition(g, 0, calf);
  return { thigh: angle(x, z) - angle(local.x, local.z), calf };
}
// Foot target relative to its stand position for a leg phase in [0, 1).
export function footOffset(phase: number, amount: number, o: GaitOptions) {
  const half = o.stride / 2;
  if (phase < o.duty) {
    const s = phase / o.duty;
    return { x: amount * (half - s * o.stride), z: 0 };
  }
  const s = (phase - o.duty) / (1 - o.duty),
    blend = (1 - Math.cos(Math.PI * s)) / 2;
  return {
    x: amount * (-half + blend * o.stride),
    z: amount * o.lift * Math.sin(Math.PI * s),
  };
}
export type GaitState = { phase: number; amount: number };
export function newGait(): GaitState {
  return { phase: 0, amount: 0 };
}
// Phase follows travelled distance so stance feet stay planted; turning in place also steps.
export function stepGait(
  state: GaitState,
  dt: number,
  speed: number,
  yawRate: number,
  o = gaitDefaults,
) {
  const travel = Math.abs(speed) + Math.abs(yawRate) * 0.25,
    target = Math.min(1, travel / 0.12);
  state.amount += (target - state.amount) * Math.min(1, dt * 6);
  if (state.amount > 0.02)
    state.phase = (state.phase + (travel * dt) / (o.stride / o.duty)) % 1;
  return state;
}
export function jointAngles(
  state: GaitState,
  g: LegGeometry,
  stand: Record<Leg, Stand>,
  o = gaitDefaults,
) {
  const out: Record<string, number> = {};
  for (const leg of legs) {
    const s = stand[leg],
      base = footPosition(g, s.thigh, s.calf),
      d = footOffset((state.phase + offset[leg]) % 1, state.amount, o),
      q = legIK(g, base.x + d.x, base.z + d.z);
    out[leg + "_hip_joint"] = s.hip;
    out[leg + "_thigh_joint"] = q.thigh;
    out[leg + "_calf_joint"] = q.calf;
  }
  return out;
}
// Small trunk bob at twice the step frequency while moving.
export function bodyBob(state: GaitState) {
  return -0.012 * state.amount * Math.abs(Math.sin(2 * Math.PI * state.phase));
}
