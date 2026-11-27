# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
# ST CMSIS and HAL sources for STM32G4, downloaded at configure time as commit-pinned
# GitHub archives with SHA256 checks. Nothing from these repositories is copied into the tree.
#   cmsis-core           v5.9.0  Apache-2.0
#   cmsis-device-g4      v1.2.6  Apache-2.0
#   stm32g4xx-hal-driver v1.2.7  BSD-3-Clause
# To update: change the commit and hash together, then rebuild and rerun the bench checks.
include(FetchContent)

set(_st https://github.com/STMicroelectronics)
# SOURCE_SUBDIR points at a missing directory so FetchContent only downloads and never builds.
FetchContent_Declare(st_cmsis_core
    URL ${_st}/cmsis-core/archive/1a2f783395dd72778a98ebe7771f36ca1c30a35e.tar.gz
    URL_HASH SHA256=0dd7b9316c8ff157479d8a7ee21c2734f7ef543ffbd6bf680fdba631d2381853
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    SOURCE_SUBDIR download-only)
FetchContent_Declare(st_cmsis_device_g4
    URL ${_st}/cmsis-device-g4/archive/25664ddc3a7624ae9627ae8c4c672073dc5b2539.tar.gz
    URL_HASH SHA256=29f1c6a51740012cb6fec5c75ec175b1aac1f1a98adc2989eff4f5f5dbb4c6b5
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    SOURCE_SUBDIR download-only)
FetchContent_Declare(st_hal_g4
    URL ${_st}/stm32g4xx-hal-driver/archive/f5929f431f9effe45fbe18f5337e4753ced9ac92.tar.gz
    URL_HASH SHA256=08616f4ce3dcb3089386409b3a204c0e93ca560f5d5c180df0c1d3af729095e3
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    SOURCE_SUBDIR download-only)
FetchContent_MakeAvailable(st_cmsis_core st_cmsis_device_g4 st_hal_g4)

set(STM32G4_INCLUDE_DIRS
    ${st_cmsis_core_SOURCE_DIR}/Include
    ${st_cmsis_device_g4_SOURCE_DIR}/Include
    ${st_hal_g4_SOURCE_DIR}/Inc)
set(STM32G4_STARTUP ${st_cmsis_device_g4_SOURCE_DIR}/Source/Templates/gcc/startup_stm32g474xx.s)
set(STM32G4_VENDOR_SOURCES ${st_cmsis_device_g4_SOURCE_DIR}/Source/Templates/system_stm32g4xx.c)
foreach(_m hal hal_cortex hal_dma hal_dma_ex hal_exti hal_flash hal_flash_ex hal_flash_ramfunc hal_gpio
           hal_iwdg hal_pwr hal_pwr_ex hal_rcc hal_rcc_ex hal_uart hal_uart_ex)
    list(APPEND STM32G4_VENDOR_SOURCES ${st_hal_g4_SOURCE_DIR}/Src/stm32g4xx_${_m}.c)
endforeach()
