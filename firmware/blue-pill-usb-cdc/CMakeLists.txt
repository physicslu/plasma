cmake_minimum_required(VERSION 3.20)
project(plasma_blue_pill_cdc VERSION 0.1 LANGUAGES C ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(NOT DEFINED STM32CUBE_F1_ROOT)
  message(FATAL_ERROR "Set STM32CUBE_F1_ROOT to STM32CubeF1 commit c7656f1fee178058be2f8ebfc8df9eaf91dc565e")
endif()
set(CUBE "${STM32CUBE_F1_ROOT}")
set(HAL "${CUBE}/Drivers/STM32F1xx_HAL_Driver")
set(CMSIS "${CUBE}/Drivers/CMSIS")
set(DEVICE "${CMSIS}/Device/ST/STM32F1xx")
set(USB "${CUBE}/Middlewares/ST/STM32_USB_Device_Library")
foreach(path "${HAL}/Inc/stm32f1xx_hal.h" "${DEVICE}/Include/stm32f1xx.h" "${USB}/Class/CDC/Inc/usbd_cdc.h")
  if(NOT EXISTS "${path}")
    message(FATAL_ERROR "Missing locked STM32CubeF1 component: ${path}")
  endif()
endforeach()
find_package(Git REQUIRED)
foreach(item "${CUBE}|c7656f1fee178058be2f8ebfc8df9eaf91dc565e" "${DEVICE}|c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22" "${HAL}|bd368aa335c529641d2e567574885e02deacc64a" "${USB}|e5a58ee2260204bfed632c7c56da0fdb41514a51")
  string(REPLACE "|" ";" pair "${item}")
  list(GET pair 0 repo)
  list(GET pair 1 expected)
  execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${repo}" rev-parse HEAD OUTPUT_VARIABLE actual OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE result)
  if(NOT result EQUAL 0 OR NOT actual STREQUAL expected)
    message(FATAL_ERROR "STM32CubeF1 dependency revision mismatch: ${repo}: ${actual}, expected ${expected}")
  endif()
endforeach()

add_executable(plasma-blue-pill-cdc.elf
  src/main.c src/app.c src/usbd_conf.c src/usbd_desc.c
  "${DEVICE}/Source/Templates/system_stm32f1xx.c"
  "${DEVICE}/Source/Templates/gcc/startup_stm32f103xb.s"
  "${HAL}/Src/stm32f1xx_hal.c"
  "${HAL}/Src/stm32f1xx_hal_rcc.c"
  "${HAL}/Src/stm32f1xx_hal_rcc_ex.c"
  "${HAL}/Src/stm32f1xx_hal_gpio.c"
  "${HAL}/Src/stm32f1xx_hal_cortex.c"
  "${HAL}/Src/stm32f1xx_hal_pcd.c"
  "${HAL}/Src/stm32f1xx_hal_pcd_ex.c"
  "${HAL}/Src/stm32f1xx_hal_flash.c"
  "${HAL}/Src/stm32f1xx_hal_flash_ex.c"
  "${HAL}/Src/stm32f1xx_ll_usb.c"
  "${USB}/Core/Src/usbd_core.c"
  "${USB}/Core/Src/usbd_ctlreq.c"
  "${USB}/Core/Src/usbd_ioreq.c"
  "${USB}/Class/CDC/Src/usbd_cdc.c")
target_include_directories(plasma-blue-pill-cdc.elf PRIVATE include "${HAL}/Inc" "${CMSIS}/Include" "${DEVICE}/Include" "${USB}/Core/Inc" "${USB}/Class/CDC/Inc")
target_compile_definitions(plasma-blue-pill-cdc.elf PRIVATE STM32F103xB USE_HAL_DRIVER)
target_compile_options(plasma-blue-pill-cdc.elf PRIVATE -mcpu=cortex-m3 -mthumb -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-unused-parameter -Os)
target_link_options(plasma-blue-pill-cdc.elf PRIVATE -mcpu=cortex-m3 -mthumb -nostartfiles -T${CMAKE_CURRENT_SOURCE_DIR}/stm32f103c8.ld -Wl,--gc-sections -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/plasma-blue-pill-cdc.map -Wl,--print-memory-usage
  "--specs=${ARM_GCC_ROOT}/usr/lib/arm-none-eabi/newlib/nano.specs"
  "--specs=${ARM_GCC_ROOT}/usr/lib/arm-none-eabi/newlib/nosys.specs"
  "-L${ARM_GCC_ROOT}/usr/lib/arm-none-eabi/newlib/thumb/v7-m/nofp")
add_custom_command(TARGET plasma-blue-pill-cdc.elf POST_BUILD
  COMMAND "${CMAKE_OBJCOPY}" -O ihex "$<TARGET_FILE:plasma-blue-pill-cdc.elf>" "${CMAKE_CURRENT_BINARY_DIR}/plasma-blue-pill-cdc.hex"
  COMMAND "${CMAKE_OBJCOPY}" -O binary "$<TARGET_FILE:plasma-blue-pill-cdc.elf>" "${CMAKE_CURRENT_BINARY_DIR}/plasma-blue-pill-cdc.bin"
  COMMAND "${CMAKE_SIZE}" "$<TARGET_FILE:plasma-blue-pill-cdc.elf>"
  VERBATIM)
