// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { telemetry as s } from "./store";
export function LidarView() {
  const host = useRef<HTMLDivElement>(null);
  const [failure, setFailure] = useState("");
  useEffect(() => {
    const el = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFailure("WebGL을 사용할 수 없습니다");
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0b1219");
    const camera = new THREE.PerspectiveCamera(48, 16 / 9, 0.05, 500);
    camera.up.set(0, 0, 1);
    camera.position.set(14, -17, 13);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.minDistance = 1;
    controls.maxDistance = 100;
    const grid = new THREE.GridHelper(40, 20, 0x344557, 0x1e2a36);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    const axes = new THREE.AxesHelper(3);
    scene.add(axes);
    const geometry = new THREE.BufferGeometry();
    const material = new THREE.PointsMaterial({
      color: 0xecc66d,
      size: 0.045,
      sizeAttenuation: true,
    });
    scene.add(new THREE.Points(geometry, material));
    let last: unknown;
    let id = 0;
    const resize = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      renderer.setSize(r.width, r.height);
      camera.aspect = r.width / r.height;
      camera.updateProjectionMatrix();
    });
    resize.observe(el);
    const render = () => {
      const cloud = s.lidarCloud;
      if (cloud !== last) {
        last = cloud;
        geometry.setAttribute(
          "position",
          new THREE.BufferAttribute(cloud?.points ?? new Float32Array(0), 3),
        );
        geometry.computeBoundingSphere();
      }
      controls.update();
      renderer.render(scene, camera);
      id = requestAnimationFrame(render);
    };
    render();
    return () => {
      cancelAnimationFrame(id);
      resize.disconnect();
      controls.dispose();
      geometry.dispose();
      material.dispose();
      grid.geometry.dispose();
      (grid.material as THREE.Material).dispose();
      axes.geometry.dispose();
      (axes.material as THREE.Material).dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, []);
  return (
    <div className="sensor-body">
      <div className="sensor-viewport">
        <div className="three-host" ref={host} />
        {(!s.lidarCloud || failure) && (
          <div className="sensor-empty">
            <span className="sensor-icon">⌘</span>
            <strong>{failure || "LiDAR 데이터 대기 중"}</strong>
            <small>현재 시각에 대응하는 PointCloud2 없음</small>
          </div>
        )}
        <span className="viewport-label">
          {s.lidarCloud
            ? (s.lidarCloud.points.length / 3).toLocaleString() +
              " pts · t=" +
              s.lidarCloud.t.toFixed(3) +
              " s"
            : "NO POINT CLOUD"}
        </span>
        <span className="axis-label">
          X <b>Y</b> <em>Z</em> · {s.lidarCloud?.frame || "—"}
        </span>
      </div>
    </div>
  );
}
