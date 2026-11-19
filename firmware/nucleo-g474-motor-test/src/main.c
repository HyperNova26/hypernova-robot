/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/*
 * NUCLEO-G474RE bench firmware for up to three GO-M8010-6 on one RS-485 bus (IDs 0..2).
 * "check" and "run" port moter_test/go_chain.cpp; "read", "scan", "bench" and "stop" are bench helpers.
 * The console is the ST-LINK virtual COM port at 115200 8N1.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "board.h"
#include "console.h"
#include "go_m8010.h"
#include "motor_bus.h"

#define MAX_MOTORS 3
#define LOOP_PERIOD_MS 10u
#define TWO_PI 6.2831853f
#define RAD_TO_DEG 57.29578f
#define KD_FOC_OUT 1.6f /* output-side N*m*s/rad, as in go_chain.cpp */

typedef struct {
    float angle_deg; /* output shaft */
    float speed_rps; /* output shaft */
    float torque_nm; /* output shaft estimate */
    int8_t temp_c;
} feedback_t;

/* ---------------------------------------------------------------- motor helpers */

static bool exchange(uint8_t id, uint8_t mode, float rps, float kd_out, feedback_t *out, bool verbose)
{
    const float ratio = GO_M8010_GEAR_RATIO;
    const go_m8010_cmd_t cmd = {
        .id = id,
        .mode = mode,
        .dq = rps * TWO_PI * ratio,
        .kd = kd_out / (ratio * ratio),
    };
    go_m8010_fbk_t fb;
    const motor_bus_status_t status = motor_bus_exchange(&cmd, &fb, NULL);
    if (status != MOTOR_BUS_OK || fb.id != id) {
        if (verbose) {
            printf("ID %u: %s\n", id,
                   status == MOTOR_BUS_TX_STUCK ? "UART transmit stuck" : "missing or invalid feedback");
        }
        return false;
    }
    if (fb.merror || fb.mode != mode) {
        if (verbose) {
            printf("ID %u: error=%s mode=%u\n", id, go_m8010_error_name(fb.merror), fb.mode);
        }
        return false;
    }
    if (out) {
        out->angle_deg = fb.q / ratio * RAD_TO_DEG;
        out->speed_rps = fb.dq / ratio / TWO_PI;
        out->torque_nm = fb.tau * ratio;
        out->temp_c = fb.temp_c;
    }
    return true;
}

/* Mode 0, up to three tries. */
static bool brake_one(int id, bool verbose)
{
    for (int attempt = 0; attempt < 3; ++attempt) {
        if (exchange((uint8_t)id, GO_M8010_MODE_BRAKE, 0.0f, 0.0f, NULL, false)) {
            return true;
        }
    }
    if (verbose) {
        printf("ID %d: stop not confirmed - cut motor power if it is still moving\n", id);
    }
    return false;
}

static bool brake_all(int count, bool verbose)
{
    bool ok = true;
    for (int id = 0; id < count; ++id) {
        ok &= brake_one(id, verbose);
    }
    return ok;
}

/* Swallow the rest of the command line (e.g. LF after CR) so it does not count as a stop key. */
static void drain_input(void)
{
    HAL_Delay(20);
    while (console_getc() >= 0) {
    }
}

static bool stop_requested(void)
{
    if (board_button_pressed()) {
        printf("\nB1 pressed\n");
        return true;
    }
    if (console_getc() >= 0) {
        printf("\nkey pressed\n");
        return true;
    }
    return false;
}

static void wait_until(uint32_t tick_ms)
{
    while ((int32_t)(HAL_GetTick() - tick_ms) < 0) {
    }
}

/* ---------------------------------------------------------------- commands */

static bool cmd_check(int count)
{
    bool ok = true;
    for (int id = 0; id < count; ++id) {
        feedback_t fb;
        if (exchange((uint8_t)id, GO_M8010_MODE_BRAKE, 0.0f, 0.0f, &fb, true)) {
            printf("ID %d ready  angle=%.2f deg  T=%d C\n", id, (double)fb.angle_deg, fb.temp_c);
        } else {
            ok = false;
        }
    }
    return ok;
}

/* go_chain.cpp drive(): 3 motors 0.1 rev/s for 3 s; 1-2 motors 0.5 rev/s (30 rpm) for 15 s. */
static bool drive(int count)
{
    const bool three = count == 3;
    const uint32_t duration_ms = three ? 3000u : 15000u;
    const float ramp_s = three ? 0.5f : 2.0f;
    const float target_rps = three ? 0.1f : 0.5f;
    feedback_t fb[MAX_MOTORS] = {0};
    float start_angle[MAX_MOTORS] = {0};
    float window_angle[MAX_MOTORS] = {0};
    uint32_t window_start = 0;
    uint32_t next_report = 0;
    bool first = true;
    const uint32_t start = HAL_GetTick();

    for (;;) {
        board_watchdog_kick();
        const uint32_t tick = HAL_GetTick();
        const uint32_t elapsed = tick - start;
        if (elapsed >= duration_ms) {
            return true;
        }
        if (stop_requested()) {
            return false;
        }
        const float t = (float)elapsed / 1000.0f;
        const float duration_s = (float)duration_ms / 1000.0f;
        const float speed = target_rps * fminf(1.0f, fminf(t / ramp_s, (duration_s - t) / ramp_s));
        for (int id = 0; id < count; ++id) {
            if (!exchange((uint8_t)id, GO_M8010_MODE_FOC, speed, KD_FOC_OUT, &fb[id], true)) {
                return false;
            }
            if (first) {
                window_angle[id] = start_angle[id] = fb[id].angle_deg;
            }
        }
        first = false;
        if (elapsed >= next_report) {
            printf("target=%.1f rpm", (double)(speed * 60.0f));
            for (int id = 0; id < count; ++id) {
                printf("  ID %d travel=%.1f deg torque_est=%.2f Nm T=%d C", id,
                       (double)(fb[id].angle_deg - start_angle[id]), (double)fb[id].torque_nm, fb[id].temp_c);
            }
            printf("\n");
            next_report = elapsed + 250u;
        }
        if (elapsed - window_start >= 1250u) {
            for (int id = 0; id < count; ++id) {
                if (fb[id].angle_deg - window_angle[id] < 1.0f) {
                    printf("ID %d: insufficient forward travel; stopping all motors\n", id);
                    return false;
                }
                window_angle[id] = fb[id].angle_deg;
            }
            window_start = elapsed;
        }
        wait_until(tick + LOOP_PERIOD_MS);
    }
}

static void cmd_run(int count)
{
    if (!cmd_check(count)) {
        printf("run aborted: not every motor answered the stop check\n");
        return;
    }
    drain_input();
    printf("run %d motor(s). B1 or any key stops.\n", count);
    board_led(true);
    const bool ok = drive(count);
    const bool stopped = brake_all(count, true);
    board_led(false);
    printf(ok && stopped ? "run finished\n" : "run FAILED\n");
}

/* Zero-torque FOC (kp = kd = tau = 0): turn the output shaft by hand and watch the reading. */
static void cmd_read(int id)
{
    drain_input();
    printf("ID %d zero torque, turn the shaft by hand. B1 or any key stops.\n", id);
    uint32_t next_print = HAL_GetTick();
    uint32_t misses = 0;
    for (;;) {
        board_watchdog_kick();
        const uint32_t tick = HAL_GetTick();
        if (stop_requested()) {
            break;
        }
        feedback_t fb;
        if (!exchange((uint8_t)id, GO_M8010_MODE_FOC, 0.0f, 0.0f, &fb, false)) {
            if (++misses >= 10) {
                printf("ID %d: 10 missed replies in a row\n", id);
                break;
            }
        } else {
            misses = 0;
            if ((int32_t)(tick - next_print) >= 0) {
                printf("angle=%9.2f deg  speed=%6.3f rev/s  torque=%6.2f Nm  T=%d C\n", (double)fb.angle_deg,
                       (double)fb.speed_rps, (double)fb.torque_nm, fb.temp_c);
                next_print = tick + 100u;
            }
        }
        wait_until(tick + LOOP_PERIOD_MS);
    }
    brake_one(id, true);
}

static void cmd_scan(void)
{
    int found = 0;
    for (int id = 0; id <= (int)GO_M8010_MAX_ID; ++id) {
        board_watchdog_kick();
        feedback_t fb;
        if (exchange((uint8_t)id, GO_M8010_MODE_BRAKE, 0.0f, 0.0f, &fb, false)) {
            printf("ID %2d  angle=%.2f deg  T=%d C\n", id, (double)fb.angle_deg, fb.temp_c);
            ++found;
        }
    }
    if (found) {
        printf("%d motor(s) answered\n", found);
    } else {
        printf("no motors answered: check motor power, A/B, GND and DE wiring\n");
    }
}

/* Back-to-back mode-0 exchanges: reply rate and round-trip time per motor. Output stays off. */
static void cmd_bench(int count, int iterations)
{
    uint32_t ok[MAX_MOTORS] = {0}, rtt_min[MAX_MOTORS], rtt_max[MAX_MOTORS] = {0};
    uint64_t rtt_sum[MAX_MOTORS] = {0};
    for (int id = 0; id < MAX_MOTORS; ++id) {
        rtt_min[id] = UINT32_MAX;
    }
    drain_input();
    motor_bus_stats_reset();
    uint64_t elapsed_cycles = 0; /* accumulated per cycle so the 25 s DWT wrap does not matter */
    uint32_t last = board_cycles();
    int done = 0;
    for (; done < iterations; ++done) {
        if ((done & 15) == 0) { /* 16 cycles of 3 timeouts stay well under the 0.4 s watchdog minimum */
            board_watchdog_kick();
            if (stop_requested()) {
                break;
            }
        }
        for (int id = 0; id < count; ++id) {
            const go_m8010_cmd_t cmd = {.id = (uint8_t)id, .mode = GO_M8010_MODE_BRAKE};
            go_m8010_fbk_t fb;
            uint32_t rtt;
            if (motor_bus_exchange(&cmd, &fb, &rtt) == MOTOR_BUS_OK && fb.id == id && fb.merror == 0) {
                ++ok[id];
                rtt_sum[id] += rtt;
                rtt_min[id] = rtt < rtt_min[id] ? rtt : rtt_min[id];
                rtt_max[id] = rtt > rtt_max[id] ? rtt : rtt_max[id];
            }
        }
        const uint32_t now = board_cycles();
        elapsed_cycles += now - last;
        last = now;
    }
    const double elapsed_us = (double)elapsed_cycles / board_cycles_per_us();
    motor_bus_stats_t s;
    motor_bus_stats(&s);
    printf("bench: %d cycle(s) x %d motor(s) in %.0f ms, %.1f us per cycle\n", done, count, elapsed_us / 1000.0,
           done ? elapsed_us / done : 0.0);
    for (int id = 0; id < count; ++id) {
        if (ok[id]) {
            printf("  ID %d  ok %lu/%d  rtt min/avg/max %lu/%lu/%lu us\n", id, (unsigned long)ok[id], done,
                   (unsigned long)rtt_min[id], (unsigned long)(rtt_sum[id] / ok[id]), (unsigned long)rtt_max[id]);
        } else {
            printf("  ID %d  ok 0/%d\n", id, done);
        }
    }
    printf("  bus: sent %lu ok %lu timeouts %lu rx_errors %lu junk_bytes %lu\n", (unsigned long)s.sent,
           (unsigned long)s.ok, (unsigned long)s.timeouts, (unsigned long)s.rx_errors, (unsigned long)s.junk_bytes);
}

static void cmd_info(void)
{
    static const char *const reset_names[] = {"power-on or reset pin", "WATCHDOG", "software", "other"};
    const uint32_t baud = motor_bus_actual_baud();
    const float err = ((float)baud - (float)MOTOR_BUS_BAUD) * 100.0f / (float)MOTOR_BUS_BAUD;
    printf("NUCLEO-G474RE GO-M8010-6 bench, built " __DATE__ " " __TIME__ "\n");
    printf("SYSCLK %lu MHz from %s, reset cause: %s\n", (unsigned long)(SystemCoreClock / 1000000u),
           board_hse_ok() ? "HSE 24 MHz crystal" : "HSI16 (HSE failed to start)", reset_names[board_reset_cause()]);
    printf("RS-485 UART4 PC10/PC11, DE PA15, TX allow PB2: %lu bit/s (%+.2f %% from 4 Mbps), reply timeout %u us\n",
           (unsigned long)baud, (double)err, MOTOR_BUS_REPLY_TIMEOUT_US);
}

static void cmd_help(void)
{
    printf("commands (motors use IDs 0..n-1 on one bus):\n"
           "  check [n]          mode 0 to IDs 0..n-1 and show replies (n = 1..3, default 3)\n"
           "  run [n]            go_chain run: n=3 0.1 rev/s 3 s; n=1,2 0.5 rev/s 15 s, stall check 1 deg/1.25 s\n"
           "  read <id>          zero-torque feedback at 10 Hz, turn by hand\n"
           "  scan               mode 0 to IDs 0..14, list replies\n"
           "  bench [n] [count]  back-to-back mode 0, reply rate and round trip (default 3 1000)\n"
           "  stop               mode 0 to IDs 0..2\n"
           "  info               clock, baud error, reset cause\n"
           "B1 or any key stops run, read and bench. Keep the motor power switch within reach.\n");
}

/* ---------------------------------------------------------------- console */

static bool parse_int(const char *s, int lo, int hi, int fallback, int *out)
{
    if (s == NULL) {
        *out = fallback;
        return true;
    }
    char *end;
    const long v = strtol(s, &end, 10);
    if (*end != '\0' || v < lo || v > hi) {
        printf("expected a number %d..%d, got '%s'\n", lo, hi, s);
        return false;
    }
    *out = (int)v;
    return true;
}

static void handle_line(char *line)
{
    const char *cmd = strtok(line, " \t");
    const char *a1 = strtok(NULL, " \t");
    const char *a2 = strtok(NULL, " \t");
    int n, m;
    if (cmd == NULL) {
        return;
    } else if (!strcmp(cmd, "check")) {
        if (parse_int(a1, 1, MAX_MOTORS, MAX_MOTORS, &n)) {
            printf(cmd_check(n) ? "check ok\n" : "check FAILED\n");
        }
    } else if (!strcmp(cmd, "run")) {
        if (parse_int(a1, 1, MAX_MOTORS, MAX_MOTORS, &n)) {
            cmd_run(n);
        }
    } else if (!strcmp(cmd, "read")) {
        if (a1 == NULL) {
            printf("usage: read <id>\n");
        } else if (parse_int(a1, 0, GO_M8010_MAX_ID, 0, &n)) {
            cmd_read(n);
        }
    } else if (!strcmp(cmd, "scan")) {
        cmd_scan();
    } else if (!strcmp(cmd, "bench")) {
        if (parse_int(a1, 1, MAX_MOTORS, MAX_MOTORS, &n) && parse_int(a2, 1, 1000000, 1000, &m)) {
            cmd_bench(n, m);
        }
    } else if (!strcmp(cmd, "stop")) {
        printf(brake_all(MAX_MOTORS, true) ? "all stopped\n" : "stop incomplete\n");
    } else if (!strcmp(cmd, "info")) {
        cmd_info();
    } else if (!strcmp(cmd, "help") || !strcmp(cmd, "?")) {
        cmd_help();
    } else {
        printf("unknown command '%s', try help\n", cmd);
    }
}

int main(void)
{
    board_init();
    console_init();
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("\n");

    const bool bus_ok = motor_bus_init();
    cmd_info();
    if (!bus_ok) {
        printf("UART4 init FAILED; motor commands will not work\n");
    }
    /* A reset may have interrupted a run: stop IDs 0..2 before doing anything else. */
    printf("boot stop: ");
    for (int id = 0; id < MAX_MOTORS; ++id) {
        const bool ok = exchange((uint8_t)id, GO_M8010_MODE_BRAKE, 0.0f, 0.0f, NULL, false);
        printf("ID %d %s  ", id, ok ? "ok" : "no reply");
    }
    printf("\ntype help for commands\n> ");

    board_watchdog_start();
    char line[64];
    size_t len = 0;
    uint32_t next_blink = HAL_GetTick();
    for (;;) {
        board_watchdog_kick();
        if ((int32_t)(HAL_GetTick() - next_blink) >= 0) {
            board_led_toggle();
            next_blink += 500u;
        }
        const int c = console_getc();
        if (c < 0) {
            continue;
        }
        if (c == '\r' || c == '\n') {
            if (len > 0) {
                printf("\n");
                line[len] = '\0';
                len = 0;
                handle_line(line);
                printf("> ");
            } else if (c == '\r') {
                printf("\n> ");
            }
        } else if (c == 0x7F || c == 0x08) {
            if (len > 0) {
                --len;
                printf("\b \b");
            }
        } else if (c >= 0x20 && c < 0x7F && len < sizeof line - 1) {
            line[len++] = (char)c;
            putchar(c);
        }
    }
}
