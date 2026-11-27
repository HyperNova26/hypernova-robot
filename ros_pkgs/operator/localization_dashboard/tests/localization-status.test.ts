// SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
// SPDX-License-Identifier: Apache-2.0
// Provisional /localization/status as DiagnosticArray (adapters/localization_status.py).
import { describe, expect, it } from "vitest";
import { localizationFromDiagnostics } from "../src/model";
import { Telemetry } from "../src/store";

const diag = (values: Record<string, string>, level = 0) => ({
  header: { stamp: { sec: 1_795_000_000, nanosec: 0 } }, // wall time, ignored
  status: [
    {
      level: new Uint8Array([level]),
      name: "localization/state",
      message: values.state,
      hardware_id: "hn_v1_hyper",
      values: Object.entries(values).map(([key, value]) => ({ key, value })),
    },
  ],
});

describe("localization status (DiagnosticArray)", () => {
  it("reads code, reason, rate and uses sim_t as the time", () => {
    const s = localizationFromDiagnostics(
      diag({
        code: "1",
        state: "TRACKING",
        reason: "ok",
        sim_t: "1763190512.250",
        rate_hz: "10.0",
      }),
      5,
    );
    expect(s.label).toBe("TRACKING");
    expect(s.code).toBe(1);
    expect(s.reason).toBe("ok");
    expect(s.rate).toBe(10);
    expect(s.t).toBeCloseTo(1763190512.25);
    expect(s.issue).toBeUndefined();
  });
  it("flags a missing code instead of guessing", () => {
    const s = localizationFromDiagnostics(diag({ state: "TRACKING" }), 0);
    expect(s.code).toBeUndefined();
    expect(s.issue).toContain("code");
  });
  it("the store accepts both the diagnostic and the hn_interfaces draft", () => {
    const t = new Telemetry();
    t.ingest(
      "status",
      diag({ code: "5", state: "INPUT_TIMEOUT", reason: "no_odom" }, 2),
    );
    expect(t.localization?.label).toBe("INPUT_TIMEOUT");
    t.ingest("status", { header: { stamp: { sec: 3, nanosec: 0 } }, status: 1 });
    expect(t.localization?.label).toBe("TRACKING");
  });
});
