/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
#include "motor_bus.h"

#include <string.h>

#include "board.h"

#define RX_ERROR_FLAGS (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE | USART_ISR_PE)
#define RX_ERROR_CLEAR (USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF | USART_ICR_PECF)
#define TX_LIMIT_US 200u /* 17 bytes take 42.5 us at 4 Mbps */
/* DE lead and lag around each frame, in sample times (1/8 bit = 31.25 ns at 4 Mbps). */
#define DE_ASSERT_SAMPLES 8u
#define DE_DEASSERT_SAMPLES 8u

static UART_HandleTypeDef huart4;
static motor_bus_stats_t stats;

bool motor_bus_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_UART4_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {.Mode = GPIO_MODE_AF_PP, .Speed = GPIO_SPEED_FREQ_HIGH};
    gpio.Pin = GPIO_PIN_10; /* UART4_TX -> transceiver DI */
    gpio.Pull = GPIO_NOPULL;
    gpio.Alternate = GPIO_AF5_UART4;
    HAL_GPIO_Init(GPIOC, &gpio);
    gpio.Pin = GPIO_PIN_11; /* UART4_RX <- transceiver RO, which floats while DE is high */
    gpio.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOC, &gpio);
    gpio.Pin = GPIO_PIN_15; /* UART4_DE; the carrier adds a 4.7 kohm pull-down */
    gpio.Pull = GPIO_NOPULL;
    gpio.Alternate = GPIO_AF8_UART4;
    HAL_GPIO_Init(GPIOA, &gpio);

    huart4.Instance = UART4;
    huart4.Init.BaudRate = MOTOR_BUS_BAUD;
    huart4.Init.WordLength = UART_WORDLENGTH_8B;
    huart4.Init.StopBits = UART_STOPBITS_1;
    huart4.Init.Parity = UART_PARITY_NONE;
    huart4.Init.Mode = UART_MODE_TX_RX;
    huart4.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart4.Init.OverSampling = UART_OVERSAMPLING_8; /* same as the main control board .ioc */
    huart4.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    huart4.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    huart4.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_RS485Ex_Init(&huart4, UART_DE_POLARITY_HIGH, DE_ASSERT_SAMPLES, DE_DEASSERT_SAMPLES) != HAL_OK ||
        HAL_UARTEx_SetTxFifoThreshold(&huart4, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK ||
        HAL_UARTEx_SetRxFifoThreshold(&huart4, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK ||
        HAL_UARTEx_EnableFifoMode(&huart4) != HAL_OK) {
        return false;
    }
    board_rs485_tx_allow(true);
    return true;
}

uint32_t motor_bus_actual_baud(void)
{
    /* OVER8: BRR[2:0] holds USARTDIV[3:1], so USARTDIV is always even. */
    const uint32_t brr = UART4->BRR;
    const uint32_t usartdiv = (brr & 0xFFF0u) | ((brr & 0x7u) << 1);
    return usartdiv ? (uint32_t)((2ull * HAL_RCC_GetPCLK1Freq() + usartdiv / 2) / usartdiv) : 0;
}

motor_bus_status_t motor_bus_exchange(const go_m8010_cmd_t *cmd, go_m8010_fbk_t *fbk, uint32_t *rtt_us)
{
    USART_TypeDef *const u = UART4;
    const uint32_t cycles_per_us = board_cycles_per_us();
    uint8_t tx[GO_M8010_TX_LEN];
    uint8_t buf[3 * GO_M8010_RX_LEN];
    uint32_t n = 0;
    uint32_t junk = 0;

    go_m8010_encode(cmd, tx);
    ++stats.sent;

    u->RQR = USART_RQR_RXFRQ;
    u->ICR = RX_ERROR_CLEAR | USART_ICR_TCCF;
    const uint32_t t0 = board_cycles();
    for (uint32_t i = 0; i < GO_M8010_TX_LEN;) {
        if (u->ISR & USART_ISR_TXE_TXFNF) {
            u->TDR = tx[i++];
        } else if (board_cycles() - t0 > TX_LIMIT_US * cycles_per_us) {
            return MOTOR_BUS_TX_STUCK;
        }
    }
    while (!(u->ISR & USART_ISR_TC)) {
        if (board_cycles() - t0 > TX_LIMIT_US * cycles_per_us) {
            return MOTOR_BUS_TX_STUCK;
        }
    }
    /* Discard anything heard while sending (an echo if the transceiver keeps its receiver on). */
    u->RQR = USART_RQR_RXFRQ;
    u->ICR = RX_ERROR_CLEAR;

    const uint32_t t_sent = board_cycles();
    for (;;) {
        const uint32_t isr = u->ISR;
        if (isr & RX_ERROR_FLAGS) {
            u->ICR = RX_ERROR_CLEAR;
            ++stats.rx_errors;
        }
        if (isr & USART_ISR_RXNE_RXFNE) {
            if (n == sizeof buf) {
                /* Keep the newest 15 bytes: they may still start a frame. */
                const uint32_t keep = GO_M8010_RX_LEN - 1;
                memmove(buf, &buf[n - keep], keep);
                junk += n - keep;
                n = keep;
            }
            buf[n++] = (uint8_t)u->RDR;
            if (n >= GO_M8010_RX_LEN && go_m8010_is_feedback(&buf[n - GO_M8010_RX_LEN])) {
                const uint32_t t_end = board_cycles();
                go_m8010_decode(&buf[n - GO_M8010_RX_LEN], fbk);
                stats.junk_bytes += junk + n - GO_M8010_RX_LEN;
                ++stats.ok;
                if (rtt_us) {
                    *rtt_us = (t_end - t0) / cycles_per_us;
                }
                return MOTOR_BUS_OK;
            }
        } else if (board_cycles() - t_sent > MOTOR_BUS_REPLY_TIMEOUT_US * cycles_per_us) {
            stats.junk_bytes += junk + n;
            ++stats.timeouts;
            return MOTOR_BUS_TIMEOUT;
        }
    }
}

void motor_bus_stats(motor_bus_stats_t *out) { *out = stats; }

void motor_bus_stats_reset(void) { memset(&stats, 0, sizeof stats); }
