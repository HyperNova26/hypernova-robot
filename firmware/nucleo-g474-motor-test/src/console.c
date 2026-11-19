/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
#include "console.h"

#include <stdint.h>

#include "board.h"

#define TX_SIZE 2048u /* power of two */
#define RX_SIZE 128u  /* power of two */

static UART_HandleTypeDef hlpuart1;
static volatile uint8_t tx_buf[TX_SIZE];
static volatile uint32_t tx_head, tx_tail;
static volatile uint8_t rx_buf[RX_SIZE];
static volatile uint32_t rx_head, rx_tail;

void console_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_LPUART1_CLK_ENABLE();
    GPIO_InitTypeDef gpio = {
        .Pin = GPIO_PIN_2 | GPIO_PIN_3,
        .Mode = GPIO_MODE_AF_PP,
        .Pull = GPIO_PULLUP,
        .Speed = GPIO_SPEED_FREQ_LOW,
        .Alternate = GPIO_AF12_LPUART1,
    };
    HAL_GPIO_Init(GPIOA, &gpio);

    hlpuart1.Instance = LPUART1;
    hlpuart1.Init.BaudRate = CONSOLE_BAUD;
    hlpuart1.Init.WordLength = UART_WORDLENGTH_8B;
    hlpuart1.Init.StopBits = UART_STOPBITS_1;
    hlpuart1.Init.Parity = UART_PARITY_NONE;
    hlpuart1.Init.Mode = UART_MODE_TX_RX;
    hlpuart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    hlpuart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    hlpuart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&hlpuart1) != HAL_OK) {
        return; /* nothing to report through; the motor bus still works */
    }
    HAL_NVIC_SetPriority(LPUART1_IRQn, 8, 0);
    HAL_NVIC_EnableIRQ(LPUART1_IRQn);
    SET_BIT(LPUART1->CR1, USART_CR1_RXNEIE_RXFNEIE);
}

void console_write(const char *data, size_t len)
{
    for (size_t i = 0; i < len; ++i) {
        while (tx_head - tx_tail >= TX_SIZE) {
            /* ring full: the interrupt drains it */
        }
        tx_buf[tx_head % TX_SIZE] = (uint8_t)data[i];
        tx_head = tx_head + 1;
        const uint32_t primask = __get_PRIMASK();
        __disable_irq();
        SET_BIT(LPUART1->CR1, USART_CR1_TXEIE_TXFNFIE);
        __set_PRIMASK(primask);
    }
}

int console_getc(void)
{
    if (rx_head == rx_tail) {
        return -1;
    }
    const uint8_t c = rx_buf[rx_tail % RX_SIZE];
    rx_tail = rx_tail + 1;
    return c;
}

void console_flush(void)
{
    while (tx_head != tx_tail) {
    }
    while (!(LPUART1->ISR & USART_ISR_TC)) {
    }
}

void LPUART1_IRQHandler(void)
{
    const uint32_t isr = LPUART1->ISR;
    if (isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE | USART_ISR_PE)) {
        LPUART1->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF | USART_ICR_PECF;
    }
    if (isr & USART_ISR_RXNE_RXFNE) {
        const uint8_t c = (uint8_t)LPUART1->RDR;
        if (rx_head - rx_tail < RX_SIZE) {
            rx_buf[rx_head % RX_SIZE] = c;
            rx_head = rx_head + 1;
        }
    }
    if ((LPUART1->CR1 & USART_CR1_TXEIE_TXFNFIE) && (isr & USART_ISR_TXE_TXFNF)) {
        if (tx_head != tx_tail) {
            LPUART1->TDR = tx_buf[tx_tail % TX_SIZE];
            tx_tail = tx_tail + 1;
        } else {
            CLEAR_BIT(LPUART1->CR1, USART_CR1_TXEIE_TXFNFIE);
        }
    }
}
