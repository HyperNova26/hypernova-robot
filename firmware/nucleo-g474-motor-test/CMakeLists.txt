# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
# NUCLEO-G474RE GO-M8010-6 bench firmware. Use the presets: cmake --preset nucleo && cmake --build --preset nucleo
cmake_minimum_required(VERSION 3.22)
project(nucleo_g474_motor_test LANGUAGES C ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)

set(HN_SYSCLK_MHZ 170 CACHE STRING "SYSCLK in MHz: 170 matches the main control board, 160 divides 4 Mbps exactly")
set_property(CACHE HN_SYSCLK_MHZ PROPERTY STRINGS 170 160)
if(NOT HN_SYSCLK_MHZ MATCHES "^(170|160)$")
    message(FATAL_ERROR "HN_SYSCLK_MHZ must be 170 or 160")
endif()

include(cmake/stm32cube-g4.cmake)

set(TARGET nucleo_g474_motor_test)
add_executable(${TARGET}
    src/main.c
    src/board.c
    src/console.c
    src/motor_bus.c
    src/go_m8010.c
    src/syscalls.c
    ${STM32G4_STARTUP}
    ${STM32G4_VENDOR_SOURCES})
set_target_properties(${TARGET} PROPERTIES SUFFIX .elf)
target_include_directories(${TARGET} PRIVATE include ${STM32G4_INCLUDE_DIRS})
target_compile_definitions(${TARGET} PRIVATE STM32G474xx USE_HAL_DRIVER HN_SYSCLK_MHZ=${HN_SYSCLK_MHZ})

set(MCU_FLAGS -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)
target_compile_options(${TARGET} PRIVATE
    ${MCU_FLAGS} -ffunction-sections -fdata-sections -fno-common
    $<$<COMPILE_LANGUAGE:C>:-Wall -Wextra -Wdouble-promotion -Wno-unused-parameter>)
# Vendor code is used as released; do not drown our warnings in theirs.
set_source_files_properties(${STM32G4_VENDOR_SOURCES} PROPERTIES COMPILE_OPTIONS "-w")

target_link_options(${TARGET} PRIVATE
    ${MCU_FLAGS}
    -T${CMAKE_CURRENT_SOURCE_DIR}/stm32g474re_flash.ld
    --specs=nano.specs -u _printf_float
    -Wl,--gc-sections -Wl,--print-memory-usage -Wl,--no-warn-rwx-segments
    -Wl,-Map=$<TARGET_FILE_DIR:${TARGET}>/${TARGET}.map)
target_link_libraries(${TARGET} PRIVATE m)
set_property(TARGET ${TARGET} APPEND PROPERTY LINK_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/stm32g474re_flash.ld)

add_custom_command(TARGET ${TARGET} POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:${TARGET}> $<TARGET_FILE_DIR:${TARGET}>/${TARGET}.bin
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${TARGET}>
    VERBATIM)

# cmake --build --preset nucleo --target flash  (ST-LINK on the Nucleo, STM32CubeProgrammer CLI)
find_program(STM32_PROGRAMMER_CLI STM32_Programmer_CLI)
if(STM32_PROGRAMMER_CLI)
    add_custom_target(flash
        COMMAND ${STM32_PROGRAMMER_CLI} -c port=SWD -w $<TARGET_FILE:${TARGET}> -v -rst
        DEPENDS ${TARGET}
        USES_TERMINAL
        VERBATIM)
endif()
