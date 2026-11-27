/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 HYPERNOVA contributors. */
/* HAL configuration for the NUCLEO-G474RE motor bench firmware. Only the modules in use are enabled. */
#ifndef STM32G4XX_HAL_CONF_H
#define STM32G4XX_HAL_CONF_H

#ifdef __cplusplus
extern "C" {
#endif

#define HAL_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED /* the UART handle references DMA types */
#define HAL_EXTI_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_IWDG_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_UART_MODULE_ENABLED

#define USE_HAL_EXTI_REGISTER_CALLBACKS 0U
#define USE_HAL_UART_REGISTER_CALLBACKS 0U

/* NUCLEO-G474RE (MB1367): 24 MHz crystal X3 on PF0/PF1. */
#define HSE_VALUE 24000000UL
#define HSE_STARTUP_TIMEOUT 100UL /* ms */
#define HSI_VALUE 16000000UL
#define HSI48_VALUE 48000000UL
#define LSI_VALUE 32000UL
#define LSE_VALUE 32768UL
#define LSE_STARTUP_TIMEOUT 5000UL /* ms */
#define EXTERNAL_CLOCK_VALUE 48000UL

#define VDD_VALUE 3300UL /* mV */
#define TICK_INT_PRIORITY 0x0FUL
#define USE_RTOS 0U
#define PREFETCH_ENABLE 1U
#define INSTRUCTION_CACHE_ENABLE 1U
#define DATA_CACHE_ENABLE 1U
#define USE_SPI_CRC 0U

#include "stm32g4xx_hal_rcc.h"
#include "stm32g4xx_hal_gpio.h"
#include "stm32g4xx_hal_dma.h"
#include "stm32g4xx_hal_cortex.h"
#include "stm32g4xx_hal_exti.h"
#include "stm32g4xx_hal_flash.h"
#include "stm32g4xx_hal_iwdg.h"
#include "stm32g4xx_hal_pwr.h"
#include "stm32g4xx_hal_uart.h"

#define assert_param(expr) ((void)0U)

#ifdef __cplusplus
}
#endif

#endif
