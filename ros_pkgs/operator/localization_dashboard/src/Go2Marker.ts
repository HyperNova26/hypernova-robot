// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
// Procedural Go2-style marker, not a calibrated robot model or joint telemetry.
export function createGo2Marker() {
  const root = new THREE.Group(),
    legs: THREE.Group[] = [];
  const shell = new THREE.MeshStandardMaterial({
    color: 0xc8d5df,
    roughness: 0.55,
  });
  const dark = new THREE.MeshStandardMaterial({
    color: 0x263848,
    roughness: 0.7,
  });
  function box(
    x: number,
    y: number,
    z: number,
    material: THREE.Material,
    parent: THREE.Group,
    px = 0,
    py = 0,
    pz = 0,
  ) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(x, y, z), material);
    mesh.position.set(px, py, pz);
    parent.add(mesh);
    return mesh;
  }
  box(0.62, 0.27, 0.2, shell, root, 0, 0, -0.1);
  box(0.12, 0.23, 0.13, dark, root, 0.34, 0, -0.1);
  const sensor = new THREE.Mesh(
    new THREE.CylinderGeometry(0.065, 0.065, 0.07, 16),
    new THREE.MeshStandardMaterial({ color: 0x60b6f5 }),
  );
  sensor.rotation.x = Math.PI / 2;
  root.add(sensor);
  for (const x of [-0.22, 0.22])
    for (const y of [-0.17, 0.17]) {
      const leg = new THREE.Group();
      leg.position.set(x, y, -0.16);
      box(0.065, 0.065, 0.19, dark, leg, 0, 0, -0.09);
      const knee = new THREE.Group();
      knee.position.z = -0.19;
      knee.rotation.y = -0.35;
      box(0.045, 0.045, 0.19, shell, knee, 0, 0, -0.09);
      leg.add(knee);
      root.add(leg);
      legs.push(leg);
    }
  return {
    root,
    animate(phase: number, moving: boolean) {
      legs.forEach((leg, i) => {
        leg.rotation.y = moving
          ? Math.sin(phase + (i === 0 || i === 3 ? 0 : Math.PI)) * 0.45
          : 0;
      });
    },
  };
}
