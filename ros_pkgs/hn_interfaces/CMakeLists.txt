# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 HYPERNOVA contributors
cmake_minimum_required(VERSION 3.8)
project(hn_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/LocalizationStatus.msg"
  "msg/LocomotionStatus.msg"
  "srv/InjectFault.srv"
  DEPENDENCIES std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
