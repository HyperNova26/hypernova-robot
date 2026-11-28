# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Recalculate P2.3 DC and single-step input-network design bounds.

Run with Python 3. The component values and measurement conditions used here
are documented in power-validation.md. The RLC calculation covers the
passive input wiring prior to converter switching; it does not model the
firmware, closed-loop converters, contact bounce or nonlinear TVS dynamics.
"""
from math import sqrt


def check(label, actual, limit, *, minimum):
    passed = actual >= limit if minimum else actual <= limit
    print(f"{label:<60} {actual:9.5f}  {'>=' if minimum else '<='} {limit:.5f}")
    if not passed:
        raise ValueError(label)


def rs_threshold(shunt_reference, sense_reference, tolerance, bias_current):
    top = 576 * (1 + tolerance)
    bottom = 2_490 * (1 - tolerance)
    return shunt_reference + sense_reference * (1 + top / bottom) + bias_current * top


def main():
    # LT1634 0–70 °C plus shunt-current error; LTC2909 ADJ and leakage;
    # opposed worst-case resistor tolerance and temperature coefficients.
    low_trip = rs_threshold(2.49062 - 0.003, 0.4925, -0.0035, -15e-9)
    high_trip = rs_threshold(2.50937 + 0.003, 0.5075, 0.0035, 15e-9)
    print(f"U13 RS thresholds (V): {low_trip:.5f} .. {high_trip:.5f}")

    # An installed 47 uF capacitor must retain >=30 uF at the buck's VIN.
    # The specified cable loop includes the damping resistor's inductance.
    inductance = 1e-6
    capacitance = 30e-6
    damping_resistance_min = 0.630
    critical_resistance = 2 * sqrt(inductance / capacitance)
    damping_ratio = damping_resistance_min / critical_resistance
    check("RS input damping ratio, passive single plug-in", damping_ratio, 1.0, minimum=True)

    # Covers the initial, discharged EVM input; converter enable and its
    # incremental input impedance are assessed separately under load.
    check("Upper bound per R74 on initial 5.25 V inrush (A)",
          5.25 / damping_resistance_min, 8.34, minimum=False)
    # For this single fault step, R75 is in series with a conducting pass
    # FET independent of its gate response. This bounds source contribution;
    # local previously charged capacitances and ringing are separate.
    check("R75 source-current ceiling for 25.2 V step (A)",
          25.2 / 0.30, 84.0, minimum=False)
    # In the separate positive surge test 50.4 V is the open-circuit voltage
    # before a 27 ohm source resistor. The raw TVS D9 is upstream of R75.
    surge_current = 50.4 / 27
    check("50.4 V open-circuit fixture, short-circuit ceiling (A)",
          surge_current, 1.87, minimum=False)
    check("D9 energy ceiling, 25 C, 1 ms isolated pulse (J)",
          41.4 * surge_current * 0.001, 0.0775, minimum=False)

    # Lower bounds are applied at the specified measurement points in the
    # power budget, including return drops and the maximum simultaneous load.
    rs_vin_min = 3.90
    rs_vout_min = 3.25 * (1 - 0.015)
    rs_vout_max = 3.34 * (1 + 0.015)
    rs_current = rs_vout_max * 0.400 / (0.80 * rs_vin_min) + 0.002
    check("RS EVM input current at 400 mA output (A)",
          rs_current, 0.437, minimum=False)
    check("RS EVM input after 0.73 ohm and harness drops (V)",
          4.30 - rs_current * 0.73 - 0.05, rs_vin_min, minimum=True)
    check("RS EVM cold-start pin voltage (V)",
          rs_vin_min, 3.60, minimum=True)
    monitor_min = rs_vout_min - 0.024 - 0.010
    check("RS monitor at lowest EVM output (V)", monitor_min, high_trip, minimum=True)
    check("First TX enable, farthest transceiver supply (V)", low_trip - 0.040, 3.0, minimum=True)
    check("Settled supply at farthest transceiver (V)", monitor_min - 0.040, 3.0, minimum=True)
    check("Boost minimum output minus U6 dropout (V)",
          6.0 * 0.96 - 0.080 - 0.235, 5.173, minimum=True)
    check("CN7-6 at 380 mA including contacts, copper and U14 (V)",
          4.938 - 0.380 * (0.135 + 0.020 + 0.020) - 0.030,
          4.75, minimum=True)


if __name__ == "__main__":
    main()
