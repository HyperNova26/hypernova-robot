// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  createCampusMission,
  createMission,
  loadCampusDraft,
  saveCampusDraft,
  createWaypoint,
  loadDraft,
  loadMissions,
  saveDraft,
  saveMissions,
} from "../src/missionStorage";
import { demoMap, exampleMission, missionError } from "../src/operation";

function memoryStorage() {
  const contents = new Map<string, string>();
  return {
    contents,
    getItem: (key: string) => contents.get(key) ?? null,
    setItem: (key: string, value: string) => {
      contents.set(key, value);
    },
  };
}

describe("mission storage", () => {
  it("restores the active unsaved draft independently from the mission library", () => {
    const storage = memoryStorage();
    const draft = createMission();
    expect(loadMissions(storage).value).toEqual([]);
    expect(loadDraft(storage).value).toEqual(exampleMission);

    draft.name = "";
    draft.waypoints.push(createWaypoint({ x: -3.25, y: 6.5 }, 0));
    expect(saveDraft(draft, storage)).toBeUndefined();
    expect(loadDraft(storage).value).toEqual(draft);
    expect(loadMissions(storage).value).toEqual([]);

    const saved = { ...draft, name: "시설 점검" };
    expect(saveMissions([exampleMission, saved], storage)).toBeUndefined();
    expect(loadMissions(storage).value).toEqual([exampleMission, saved]);
    expect(loadDraft(storage).value.name).toBe("");
  });

  it("preserves existing synthetic records without adding a default synthetic mission", () => {
    const storage = memoryStorage();
    const saved = { ...createMission(), name: "기존 점검 임무" };
    saveMissions([saved], storage);
    saveDraft(saved, storage);

    expect(loadMissions(storage).value).toEqual([saved]);
    expect(loadDraft(storage).value).toEqual(saved);
  });

  it("retains route validation when a corrected mission is saved and loaded", () => {
    const storage = memoryStorage();
    const route = createMission();
    route.routing = "walkway";
    route.waypoints = [
      createWaypoint({ x: -8, y: -4 }, 0),
      createWaypoint({ x: 0, y: -4 }, 1),
      createWaypoint({ x: 0, y: 1 }, 2),
    ];
    saveDraft(route, storage);
    saveMissions([route], storage);

    expect(loadDraft(storage).value).toEqual(route);
    expect(loadMissions(storage).value[0]).toEqual(route);
    expect(missionError(loadDraft(storage).value)).toBeUndefined();
  });

  it("stores campus missions with their map revision independently of the demo draft", () => {
    const storage = memoryStorage();
    const campus = createCampusMission(
      {
        id: "khu-global-campus-osm",
        version: "2026-11-24T05:00:32Z",
        frame: "khu_campus_osm_local",
      },
      [
        { x: -56, y: -6 },
        { x: -35, y: -2 },
      ],
    );
    const demo = createMission();
    saveDraft(demo, storage);
    saveCampusDraft(campus, storage);
    saveMissions([demo, campus], storage);

    expect(loadCampusDraft(storage).value).toEqual(campus);
    expect(loadDraft(storage).value).toEqual(demo);
    expect(loadMissions(storage).value).toContainEqual(campus);
    expect(campus.waypoints.every((point) => point.dwell === 0)).toBe(true);
    saveCampusDraft(undefined, storage);
    expect(loadCampusDraft(storage).value).toBeUndefined();
    expect(loadMissions(storage).value).toContainEqual(campus);
  });

  it("retains saved map metadata so a route from another frame is still rejected", () => {
    const storage = memoryStorage();
    const mission = {
      ...exampleMission,
      map: { ...exampleMission.map, frame: "another_map" },
    };
    saveMissions([mission], storage);
    const [restored] = loadMissions(storage).value;
    expect(restored.map).toEqual(mission.map);
    expect(missionError(restored, demoMap)).toBeTruthy();
  });

  it("falls back to the example and exposes unreadable storage", () => {
    const storage = memoryStorage();
    saveDraft(exampleMission, storage);
    const [key] = storage.contents.keys();
    storage.setItem(key, "{");
    expect(loadDraft(storage)).toEqual({
      value: exampleMission,
      error: expect.any(String),
    });
    expect(
      saveDraft(exampleMission, {
        setItem() {
          throw Error("quota");
        },
      }),
    ).toEqual(expect.any(String));
  });
});
