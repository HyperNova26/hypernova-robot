// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Record the dashboard while a data source plays (S-015 video, 2026-11-27).
// Opens a separate Chrome window (own temporary profile) on the dashboard, presses 수신 시작,
// and pipes the page's own frames (Chrome DevTools screencast) into ffmpeg, so other windows
// covering it do not end up in the video. Nothing is sent anywhere; the page is read-only.
// The window opens full screen; frames are scaled into --width x --height (default 1920x1080).
//
//   node replay/record_demo.mjs --url http://127.0.0.1:5174 --out 영상/demo.mp4
//
// Layers named in --hide (default 기준 지도) are switched off first.
// Timeline: waits for the first odometry, shows "지도 전체" for --overview-s, switches to
// "로봇 따라가기", and when the bridge closes (bag finished) or --max-s passes, shows
// "지도 전체" again for --outro-s and stops. Needs Chrome and ffmpeg on PATH (or --chrome/--ffmpeg).
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { parseArgs } from "node:util";

const { values: a } = parseArgs({
  options: {
    url: { type: "string", default: "http://127.0.0.1:5174" },
    out: { type: "string", default: "demo.mp4" },
    source: { type: "string", default: "bag" },
    width: { type: "string", default: "1920" },
    height: { type: "string", default: "1080" },
    "overview-s": { type: "string", default: "6" },
    "outro-s": { type: "string", default: "8" },
    "max-s": { type: "string", default: "420" },
    "wait-s": { type: "string", default: "120" },
    port: { type: "string", default: "9333" },
    chrome: {
      type: "string",
      default: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    },
    ffmpeg: { type: "string", default: "ffmpeg" },
    capture: { type: "string", default: "screencast" },
    // Headless Chrome (GPU, no window on screen); --headless=false opens a full-screen window.
    headless: { type: "string", default: "true" },
    // Play the source this many times slower (e.g. bag --rate 0.333) and set the same value here:
    // the video is sped back up, so ~10 captured fps become ~30 at real speed.
    speedup: { type: "string", default: "1" },
    // Layers switched off for the video (comma list of the map's layer labels).
    hide: { type: "string", default: "기준 지도" },
  },
});
const W = +a.width,
  H = +a.height,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  log = (...m) => console.log(new Date().toISOString().slice(11, 19), ...m);

const profile = mkdtempSync(join(tmpdir(), "hn-record-"));
const chrome = spawn(
  a.chrome,
  [
    `--remote-debugging-port=${a.port}`,
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    // A visible window opens full screen at the display's own size (a forced 1920 px page on a
    // 125 % display is cropped); headless renders exactly --width x --height.
    ...(a.headless === "true"
      ? ["--headless=new", "--use-angle=d3d11", `--window-size=${W},${H}`]
      : ["--start-fullscreen"]),
    // Keep rendering at full rate when the window is covered or in the background.
    "--disable-features=CalculateNativeWinOcclusion",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    a.headless === "true" ? a.url : `--app=${a.url}`,
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
    // Chrome not listening yet
  }
}
if (!target) throw Error("Chrome DevTools에 연결하지 못했습니다");
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r, j) => ((ws.onopen = r), (ws.onerror = j)));
let id = 0;
const pending = new Map(),
  handlers = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) {
    const { r, j } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? j(Error(m.error.message)) : r(m.result);
  } else if (m.method) handlers.get(m.method)?.(m.params);
};
const send = (method, params = {}) =>
  new Promise((r, j) => {
    pending.set(++id, { r, j });
    ws.send(JSON.stringify({ id, method, params }));
  });
const page = async (expr) =>
  (
    await send("Runtime.evaluate", {
      expression: expr,
      awaitPromise: true,
      returnByValue: true,
    })
  ).result.value;

if (a.headless === "true")
  await send("Emulation.setDeviceMetricsOverride", {
    width: W,
    height: H,
    deviceScaleFactor: 1,
    mobile: false,
  });
await send("Page.reload");
for (let i = 0; !(await page(`!!document.querySelector("button.receive") && !!document.querySelector(".map-legend em")?.textContent.includes("점")`)); i++) {
  if (i > 120) throw Error("대시보드가 열리지 않습니다");
  await sleep(500);
}
// Pick the source, hide the error strip (the bridge closing at the end is expected), connect.
await page(`(() => {
  const st = document.createElement("style");
  st.textContent = ".error-bar{display:none!important}";
  document.head.append(st);
  const sel = document.querySelector(".source-select select");
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(sel, ${JSON.stringify(a.source)});
  sel.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
})()`);
await sleep(500);
await page(`(() => {
  const hide = ${JSON.stringify(a.hide.split(",").filter(Boolean))};
  for (const l of document.querySelectorAll(".layer-group label")) {
    const box = l.querySelector("input");
    if (hide.includes(l.textContent.trim()) && box.checked) box.click();
  }
  document.querySelector("button.receive").click();
})()`);
const view = (label) =>
  page(
    `[...document.querySelectorAll(".view-switch button")].find((b) => b.textContent === ${JSON.stringify(label)})?.click()`,
  );
await view("지도 전체");
log("수신 시작, 첫 Odometry 대기");
// Position and a LiDAR scan both on screen (the panels exist and are not N/A / empty).
const hasPose = () =>
  page(`(() => {
    const pos = document.querySelector(".position-xyz strong")?.textContent;
    const scan = document.querySelector(".viewport-label")?.textContent;
    return !!pos && !pos.includes("N/A") && !!scan && !scan.includes("NO POINT CLOUD");
  })()`);
// Map legend (LiDAR count) and the hidden error strip, for the log.
const status = () =>
  page(`[document.querySelector(".map-legend")?.textContent, document.querySelector(".error-bar")?.textContent ?? ""].join(" | ")`);
for (let t = 0; !(await hasPose()); t++) {
  if (t > +a["wait-s"] * 2) throw Error("Odometry가 들어오지 않습니다");
  // The bridge may not be up yet when the page first connects; retry until it is.
  await page(`[...document.querySelectorAll("button.receive")].find((b) => b.textContent.includes("다시 연결"))?.click()`);
  await sleep(500);
}

const out = resolve(a.out);
mkdirSync(dirname(out), { recursive: true });
// screencast (default): the page's own frames over DevTools; other windows never appear in it.
// About 10 fps on this PC, so record a slowed source with --speedup.
// desktop: Windows Desktop Duplication (ddagrab) at 30 fps. It records whatever is in front of the
// screen, including other windows the user opens, so use it only on an otherwise idle machine.
const vf = `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2`;
const input =
  a.capture === "desktop"
    ? ["-f", "lavfi", "-i", "ddagrab=output_idx=0:framerate=30,hwdownload,format=bgra"]
    : ["-f", "image2pipe", "-use_wallclock_as_timestamps", "1", "-c:v", "mjpeg", "-i", "-"];
const ff = spawn(
  a.ffmpeg,
  [
    "-y",
    ...input,
    "-vf", `setpts=PTS/${+a.speedup},fps=30,${vf}`,
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "23",
    "-pix_fmt", "yuv420p",
    // Fragmented MP4: the file stays playable even if the recording is cut off.
    "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
    out,
  ],
  { stdio: ["pipe", "ignore", "inherit"] },
);
let frames = 0,
  closing = false;
ff.stdin.on("error", () => {}); // ffmpeg may exit first on "q"
if (a.capture !== "desktop") {
  handlers.set("Page.screencastFrame", ({ data, sessionId }) => {
    if (closing) return; // frames still in flight after stopScreencast
    ff.stdin.write(Buffer.from(data, "base64"));
    frames++;
    send("Page.screencastFrameAck", { sessionId });
  });
  await send("Page.startScreencast", {
    format: "jpeg",
    quality: 80,
    maxWidth: W,
    maxHeight: H,
  });
}
const started = Date.now(),
  slow = +a.speedup; // overview/outro durations are in video seconds
log("녹화 시작", out);
await sleep(+a["overview-s"] * 1000 * slow);
await view("로봇 따라가기");
log("로봇 따라가기");
for (let i = 0; Date.now() - started < +a["max-s"] * 1000 * slow; i++) {
  await sleep(1000);
  if (i % 10 === 0) log(await status());
  const ended = await page(
    `document.querySelector(".connection")?.classList.contains("bad") || document.querySelector("button.receive")?.textContent.includes("다시 연결")`,
  );
  if (ended) break;
}
log("재생 끝, 전체 보기");
await view("지도 전체");
await sleep(+a["outro-s"] * 1000 * slow);
closing = true;
if (a.capture === "desktop") ff.stdin.write("q");
else await send("Page.stopScreencast");
ff.stdin.end();
await new Promise((r) => ff.on("close", r));
log(`녹화 끝: ${a.capture === "desktop" ? "30 fps 화면 캡처" : frames + " 프레임"}, ${((Date.now() - started) / 1000).toFixed(0)} s → ${out}`);
await send("Browser.close").catch(() => {});
ws.close();
chrome.kill();
