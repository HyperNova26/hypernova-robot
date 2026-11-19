# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors.
# Host-side codec test. Configure this directory on its own with the host compiler:
#   cmake -S test -B build/host-test && cmake --build build/host-test && ctest --test-dir build/host-test
cmake_minimum_required(VERSION 3.22)
project(go_m8010_host_test C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_executable(test_go_m8010 test_go_m8010.c ../src/go_m8010.c)
target_include_directories(test_go_m8010 PRIVATE ../include)
target_compile_options(test_go_m8010 PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
target_link_libraries(test_go_m8010 PRIVATE m)

enable_testing()
add_test(NAME go_m8010_codec COMMAND test_go_m8010)
