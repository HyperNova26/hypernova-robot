// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  campusMissionNetwork,
  hallDemoRoute,
  loadCampusMap,
} from "./campusMission";
import type { CampusMapData, CampusPoint } from "./campusRouting";
import {
  createCampusMission,
  loadCampusDraft,
  loadMissions,
  saveCampusDraft,
  saveMissions,
} from "./missionStorage";
import {
  missionError,
  type CampusMissionNetwork,
  type DemoOperations,
  type Mission,
} from "./operation";

export function useCampusMissions(engine: DemoOperations) {
  const [site, setSite] = useState<{
    data: CampusMapData;
    network: CampusMissionNetwork;
    example?: Mission;
  }>();
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [library, setLibrary] = useState(loadMissions);
  const [draftStore] = useState(loadCampusDraft);
  const [draft, setDraft] = useState(draftStore.value);
  const [status, setStatus] = useState(draftStore.error ?? "");

  useEffect(() => {
    const controller = new AbortController();
    void loadCampusMap(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        const network = campusMissionNetwork(data);
        const sample = createCampusMission(
          network.identity,
          hallDemoRoute(data),
        );
        const example =
          network.demoStart && !missionError(sample, undefined, network)
            ? { ...sample, name: "전자정보대학관 북쪽 도로 예제" }
            : undefined;
        engine.setCampusNetwork(network);
        setSite({ data, network, example });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setLoadError(
            error instanceof Error
              ? error.message
              : "캠퍼스 지도를 불러오지 못했습니다.",
          );
      });
    return () => controller.abort();
  }, [attempt, engine]);

  function changeDraft(next?: Mission) {
    setDraft(next);
    setStatus(saveCampusDraft(next) ?? "");
  }

  function applyRoute(points: CampusPoint[]) {
    if (!site) return "캠퍼스 지도를 불러온 뒤 경로를 적용하세요.";
    const next = createCampusMission(site.network.identity, points);
    if (draft && !library.value.some((entry) => entry.id === draft.id)) {
      next.id = draft.id;
      next.name = draft.name.trim() || next.name;
    }
    const invalid = missionError(next, undefined, site.network);
    if (invalid) return invalid;
    changeDraft(next);
  }

  function saveDraft() {
    if (!draft) return;
    const invalid = missionError(draft, undefined, site?.network);
    if (invalid) {
      setStatus(invalid);
      return;
    }
    const exists = library.value.some((entry) => entry.id === draft.id);
    const copy = structuredClone(draft);
    const value = exists
      ? library.value.map((entry) => (entry.id === draft.id ? copy : entry))
      : [...library.value, copy];
    const error = saveMissions(value);
    setLibrary({ value, error });
    setStatus(error ?? "임무를 저장했습니다.");
  }

  return {
    site,
    loadError,
    retry: () => {
      setLoadError("");
      setAttempt((current) => current + 1);
    },
    exampleDraft: () => {
      if (!site?.example) return;
      const { map, waypoints, name } = site.example;
      return { ...createCampusMission(map, waypoints), name };
    },
    library,
    draft,
    status,
    changeDraft,
    applyRoute,
    saveDraft,
  };
}
