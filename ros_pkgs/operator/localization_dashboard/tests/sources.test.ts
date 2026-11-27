// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Data source menu: a source only presets the bridge address and the GT topic.
import { describe, expect, it } from "vitest";
import { defaults, savedSettings, sources } from "../src/model";

const pick = (source: string, config: object = {}) =>
  savedSettings(JSON.stringify({ source, config })).config;

describe("data source presets", () => {
  it("handheld bag: local bridge, no GT", () => {
    expect(pick("bag", { url: "ws://10.0.0.5:8765", gt: "/x" })).toMatchObject({
      url: "ws://localhost:8765",
      gt: "",
    });
  });
  it("simulator: local bridge, simulator GT for the error columns", () => {
    expect(pick("sim")).toMatchObject({
      url: "ws://localhost:8765",
      gt: "/ground_truth/odom",
    });
  });
  it("robot: keeps the typed robot address, never uses GT", () => {
    expect(pick("robot", { url: "ws://192.168.0.20:8765", gt: "/x" })).toMatchObject({
      url: "ws://192.168.0.20:8765",
      gt: "",
    });
  });
  it("custom: keeps everything typed in settings", () => {
    expect(pick("custom", { url: "ws://h:1", gt: "/g", scan: "/s" })).toMatchObject({
      url: "ws://h:1",
      gt: "/g",
      scan: "/s",
    });
  });
  it("topics other than GT are the same for every preset", () => {
    for (const key of Object.keys(sources)) {
      const c = pick(key);
      expect(c.lio).toBe(defaults.lio);
      expect(c.scan).toBe(defaults.scan);
      expect(c.status).toBe(defaults.status);
    }
  });
  it("an unknown saved source falls back to the handheld bag", () => {
    expect(savedSettings('{"source":"mujoco"}').source).toBe("bag");
  });
});
