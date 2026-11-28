// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Measure the dashboard's frame rate and WebGL renderer in a Chrome window (2026-11-27, for the
// S-015 recording). Connects to the selected data source, waits --wait-s, counts frames for 5 s.
//   node replay/probe_fps.mjs [--headless] [--url http://127.0.0.1:5174]
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";

const { values: a } = parseArgs({
  options: {
    url: { type: "string", default: "http://127.0.0.1:5174" },
    headless: { type: "boolean", default: false },
    "wait-s": { type: "string", default: "20" },
    port: { type: "string", default: "9334" },
    chrome: { type: "string", default: "C:/Program Files/Google/Chrome/Application/chrome.exe" },
  },
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn(
  a.chrome,
  [
    `--remote-debugging-port=${a.port}`,
    `--user-data-dir=${mkdtempSync(join(tmpdir(), "hn-probe-"))}`,
    "--no-first-run",
    "--window-size=1920,1080",
    "--disable-features=CalculateNativeWinOcclusion",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    ...(a.headless ? ["--headless=new", "--enable-gpu", "--use-angle=d3d11"] : []),
    a.headless ? a.url : `--app=${a.url}`,
  ],
  { stdio: "ignore" },
);
let target;
for (let i = 0; i < 60 && !target; i++) {
  await sleep(500);
  try {
    const list = await (await fetch(`http://127.0.0.1:${a.port}/json/list`)).json();
    target = list.find((t) => t.type === "page" && t.url.startsWith(a.url));
  } catch {
    // not up yet
  }
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0;
const pending = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  pending.get(m.id)?.(m.result);
};
const page = (expression) =>
  new Promise((r) => {
    pending.set(++id, (res) => r(res?.result?.value));
    ws.send(JSON.stringify({ id, method: "Runtime.evaluate", params: { expression, awaitPromise: true, returnByValue: true } }));
  });
await sleep(4000);
await page(`document.querySelector("button.receive")?.click()`);
await sleep(+a["wait-s"] * 1000);
console.log(
  JSON.stringify(
    await page(`(async () => {
      const gl = document.createElement("canvas").getContext("webgl2");
      const info = gl?.getExtension("WEBGL_debug_renderer_info");
      const t0 = performance.now(); let n = 0;
      await new Promise((r) => { const f = () => { n++; performance.now() - t0 < 5000 ? requestAnimationFrame(f) : r(); }; requestAnimationFrame(f); });
      return { fps: n / 5, renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : "?", size: innerWidth + "x" + innerHeight,
        dpr: devicePixelRatio, pos: document.querySelector(".position-xyz")?.textContent, legend: document.querySelector(".map-legend")?.textContent };
    })()`),
  ),
);
ws.close();
chrome.kill();
process.exit(0);
