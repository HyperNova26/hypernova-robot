/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
#include "board.h"

#if HN_SYSCLK_MHZ == 170
#define PLL_N 85u /* 4 MHz * 85 / 2 = 170 MHz, same as the main control board */
#elif HN_SYSCLK_MHZ == 160
#define PLL_N 80u /* 4 MHz * 80 / 2 = 160 MHz, divides 4 Mbps exactly */
#else
#error "HN_SYSCLK_MHZ must be 170 or 160"
#endif

#define LED_PORT GPIOA
#define LED_PIN GPIO_PIN_5 /* LD2 */
#define BUTTON_PORT GPIOC
#define BUTTON_PIN GPIO_PIN_13 /* B1 */
#define TX_ALLOW_PORT GPIOB
#define TX_ALLOW_PIN GPIO_PIN_2

static bool hse_ok;
static board_reset_t reset_cause;
static GPIO_PinState button_idle;
static IWDG_HandleTypeDef hiwdg;

static void fatal_blink(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitTypeDef gpio = {.Pin = LED_PIN, .Mode = GPIO_MODE_OUTPUT_PP, .Speed = GPIO_SPEED_FREQ_LOW};
    HAL_GPIO_Init(LED_PORT, &gpio);
    for (;;) {
        HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
        for (volatile uint32_t i = 0; i < 400000u; ++i) {
        }
    }
}

void HAL_MspInit(void)
{
    __HAL_RCC_SYSCFG_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();
    /* Release the UCPD dead-battery pull-downs on PB4/PB6 as the CubeMX board default does. */
    HAL_PWREx_DisableUCPDDeadBattery();
}

static bool clock_config(uint32_t source)
{
    RCC_OscInitTypeDef osc = {0};
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLN = PLL_N;
    osc.PLL.PLLP = RCC_PLLP_DIV2;
    osc.PLL.PLLQ = RCC_PLLQ_DIV2;
    osc.PLL.PLLR = RCC_PLLR_DIV2;
    if (source == RCC_PLLSOURCE_HSE) {
        osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
        osc.HSEState = RCC_HSE_ON;
        osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
        osc.PLL.PLLM = RCC_PLLM_DIV6; /* 24 MHz / 6 = 4 MHz */
    } else {
        osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
        osc.HSIState = RCC_HSI_ON;
        osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
        osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
        osc.PLL.PLLM = RCC_PLLM_DIV4; /* 16 MHz / 4 = 4 MHz */
    }
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
        return false;
    }
    RCC_ClkInitTypeDef clk = {
        .ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2,
        .SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK,
        .AHBCLKDivider = RCC_SYSCLK_DIV1,
        .APB1CLKDivider = RCC_HCLK_DIV1,
        .APB2CLKDivider = RCC_HCLK_DIV1,
    };
    return HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_4) == HAL_OK;
}

static void read_reset_cause(void)
{
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST)) {
        reset_cause = BOARD_RESET_WATCHDOG;
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST)) {
        reset_cause = BOARD_RESET_SOFTWARE;
    } else if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST) || __HAL_RCC_GET_FLAG(RCC_FLAG_BORRST)) {
        reset_cause = BOARD_RESET_POWER_OR_PIN;
    } else {
        reset_cause = BOARD_RESET_OTHER;
    }
    __HAL_RCC_CLEAR_RESET_FLAGS();
}

static void gpio_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(TX_ALLOW_PORT, TX_ALLOW_PIN, GPIO_PIN_RESET);
    GPIO_InitTypeDef out = {.Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL, .Speed = GPIO_SPEED_FREQ_LOW};
    out.Pin = LED_PIN;
    HAL_GPIO_Init(LED_PORT, &out);
    out.Pin = TX_ALLOW_PIN;
    HAL_GPIO_Init(TX_ALLOW_PORT, &out);

    /* B1 has its own resistor on the board; learn the released level instead of assuming one. */
    GPIO_InitTypeDef in = {.Pin = BUTTON_PIN, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_NOPULL};
    HAL_GPIO_Init(BUTTON_PORT, &in);
    HAL_Delay(2);
    button_idle = HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN);
}

void board_init(void)
{
    read_reset_cause();
    HAL_Init();
    HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST); /* required above 150 MHz */
    hse_ok = clock_config(RCC_PLLSOURCE_HSE);
    if (!hse_ok && !clock_config(RCC_PLLSOURCE_HSI)) {
        fatal_blink();
    }

    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    gpio_init();
}

bool board_hse_ok(void) { return hse_ok; }

board_reset_t board_reset_cause(void) { return reset_cause; }

void board_led(bool on) { HAL_GPIO_WritePin(LED_PORT, LED_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET); }

void board_led_toggle(void) { HAL_GPIO_TogglePin(LED_PORT, LED_PIN); }

bool board_button_pressed(void) { return HAL_GPIO_ReadPin(BUTTON_PORT, BUTTON_PIN) != button_idle; }

void board_rs485_tx_allow(bool allow)
{
    HAL_GPIO_WritePin(TX_ALLOW_PORT, TX_ALLOW_PIN, allow ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void board_watchdog_start(void)
{
    __HAL_DBGMCU_FREEZE_IWDG();
    hiwdg.Instance = IWDG;
    hiwdg.Init.Prescaler = IWDG_PRESCALER_32; /* LSI 32 kHz / 32 = 1 kHz */
    hiwdg.Init.Reload = 500;                  /* about 0.5 s; LSI tolerance makes it 0.4 to 0.6 s */
    hiwdg.Init.Window = IWDG_WINDOW_DISABLE;
    if (HAL_IWDG_Init(&hiwdg) != HAL_OK) {
        fatal_blink();
    }
}

void board_watchdog_kick(void)
{
    if (hiwdg.Instance != NULL) {
        HAL_IWDG_Refresh(&hiwdg);
    }
}

void SysTick_Handler(void) { HAL_IncTick(); }

/* Faults fall through to the startup file's Default_Handler loop; the IWDG then resets the MCU
   and the boot sequence sends brake commands again. */
