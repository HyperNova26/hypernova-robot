// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import {
  footPosition,
  jointAngles,
  legs,
  newGait,
  stepGait,
  bodyBob,
  type Leg,
  type LegGeometry,
  type Stand,
} from "./gait";
// Team URDF drawn with display copies of its visual meshes (adapters/prepare-robot.py).
// Joint motion is the display trot from gait.ts, not joint telemetry.
type Joint = {
  name: string;
  type: string;
  parent: string;
  child: string;
  xyz: number[];
  rpy: number[];
  axis: number[];
};
const nums = (s: string | null, fallback: number[]) =>
  s ? s.trim().split(/\s+/).map(Number) : fallback;
function originOf(el: Element | null) {
  const o = el?.querySelector(":scope > origin");
  return {
    xyz: nums(o?.getAttribute("xyz") ?? null, [0, 0, 0]),
    rpy: nums(o?.getAttribute("rpy") ?? null, [0, 0, 0]),
  };
}
// URDF rpy is fixed-axis X, Y, Z: R = Rz(yaw) Ry(pitch) Rx(roll).
function place(obj: THREE.Object3D, xyz: number[], rpy: number[]) {
  obj.position.set(xyz[0], xyz[1], xyz[2]);
  obj.rotation.set(rpy[0], rpy[1], rpy[2], "ZYX");
}
export function parseUrdf(text: string) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const robot = doc.querySelector("robot");
  if (!robot) throw Error("URDF robot 요소 없음");
  const joints: Joint[] = [...robot.querySelectorAll(":scope > joint")].map(
    (j) => ({
      name: j.getAttribute("name")!,
      type: j.getAttribute("type")!,
      parent: j.querySelector("parent")!.getAttribute("link")!,
      child: j.querySelector("child")!.getAttribute("link")!,
      ...originOf(j),
      axis: nums(
        j.querySelector("axis")?.getAttribute("xyz") ?? null,
        [1, 0, 0],
      ),
    }),
  );
  const visuals = [...robot.querySelectorAll(":scope > link")].map((l) => ({
    link: l.getAttribute("name")!,
    items: [...l.querySelectorAll(":scope > visual")].map((v) => {
      const mesh = v.querySelector("geometry > mesh"),
        box = v.querySelector("geometry > box");
      return {
        ...originOf(v),
        mesh: mesh?.getAttribute("filename") ?? undefined,
        scale: nums(mesh?.getAttribute("scale") ?? null, [1, 1, 1]),
        box: box ? nums(box.getAttribute("size"), [0.1, 0.1, 0.1]) : undefined,
      };
    }),
  }));
  return { joints, visuals };
}
// Leg lengths: thigh joint -> calf joint, calf joint -> foot frame (sagittal, z only in this URDF).
export function legGeometry(joints: Joint[]): LegGeometry {
  const z = (name: string) =>
    Math.abs(joints.find((j) => j.name === name)?.xyz[2] ?? NaN);
  const g = { thigh: z("FL_calf_joint"), calf: z("FL_foot_joint") };
  if (!(g.thigh > 0 && g.calf > 0))
    throw Error("다리 길이를 URDF에서 찾지 못함");
  return g;
}
// Isaac Lab init_state of policies/urdf_v1/robot.py (stand pose).
export const v1Stand: Record<Leg, Stand> = {
  FL: { hip: 0.1, thigh: 0.8, calf: -1.5 },
  FR: { hip: -0.1, thigh: 0.8, calf: -1.5 },
  RL: { hip: 0.1, thigh: 1.0, calf: -1.5 },
  RR: { hip: -0.1, thigh: 1.0, calf: -1.5 },
};
export async function loadRobot(base: string, signal?: AbortSignal) {
  const text = await (await fetch(base + "/robot.urdf", { signal })).text();
  const { joints, visuals } = parseUrdf(text);
  const geometry = legGeometry(joints);
  const loader = new STLLoader(),
    cache = new Map<string, Promise<THREE.BufferGeometry>>();
  const body = new THREE.MeshStandardMaterial({
      color: 0xd9e1e8,
      roughness: 0.45,
      metalness: 0.15,
    }),
    limb = new THREE.MeshStandardMaterial({
      color: 0x34495c,
      roughness: 0.6,
      metalness: 0.2,
    }),
    sensor = new THREE.MeshStandardMaterial({ color: 0x60b6f5 });
  const links = new Map<string, THREE.Group>();
  for (const v of visuals) {
    const group = new THREE.Group();
    group.name = v.link;
    links.set(v.link, group);
    for (const item of v.items) {
      let geom: THREE.BufferGeometry;
      if (item.mesh) {
        const file = item.mesh.split("/").pop()!;
        if (!cache.has(file))
          cache.set(
            file,
            fetch(base + "/meshes/" + file, { signal })
              .then((r) => r.arrayBuffer())
              .then((b) => loader.parse(b)),
          );
        geom = await cache.get(file)!;
      } else if (item.box) geom = new THREE.BoxGeometry(...item.box);
      else continue;
      const mesh = new THREE.Mesh(
        geom,
        v.link === "trunk" ? body : v.link.includes("lidar") ? sensor : limb,
      );
      place(mesh, item.xyz, item.rpy);
      mesh.scale.set(item.scale[0], item.scale[1], item.scale[2]);
      group.add(mesh);
    }
  }
  const motion = new Map<string, { group: THREE.Group; axis: THREE.Vector3 }>();
  for (const j of joints) {
    const parent = links.get(j.parent),
      child = links.get(j.child);
    if (!parent || !child) continue;
    const origin = new THREE.Group(),
      move = new THREE.Group();
    place(origin, j.xyz, j.rpy);
    origin.add(move);
    move.add(child);
    parent.add(origin);
    if (j.type === "revolute" || j.type === "continuous")
      motion.set(j.name, {
        group: move,
        axis: new THREE.Vector3(...j.axis).normalize(),
      });
  }
  const root = links.get("trunk");
  if (!root) throw Error("trunk 링크 없음");
  const lidarJoint = joints.find((j) => j.child === "front_lidar");
  const setJoints = (q: Record<string, number>) => {
    for (const [name, value] of Object.entries(q))
      motion
        .get(name)
        ?.group.quaternion.setFromAxisAngle(motion.get(name)!.axis, value);
  };
  // Trunk height over flat ground in the stand pose (foot frame at the sole).
  const foot = footPosition(geometry, v1Stand.FL.thigh, v1Stand.FL.calf);
  const standHeight =
    -foot.z -
    (joints.find((j) => j.name === "FL_hip_joint")?.xyz[2] ?? 0) +
    0.02;
  const gait = newGait();
  setJoints(jointAngles(gait, geometry, v1Stand));
  return {
    root,
    standHeight,
    // Horizontal trunk -> LiDAR offset (m); the pose we receive is the LiDAR's.
    lidarOffset: new THREE.Vector3(...(lidarJoint?.xyz ?? [0, 0, 0])),
    animate(dt: number, speed: number, yawRate: number) {
      stepGait(gait, dt, speed, yawRate);
      setJoints(jointAngles(gait, geometry, v1Stand));
      return bodyBob(gait);
    },
    legs,
  };
}
export type RobotModel = Awaited<ReturnType<typeof loadRobot>>;
