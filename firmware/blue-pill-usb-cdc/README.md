# PLASMA Blue Pill USB CDC firmware v0.1

Target: **STM32F103C8T6**, Cortex-M3, 64 KiB Flash, 20 KiB RAM. The clock
configuration assumes an 8 MHz HSE crystal and derives a 72 MHz system clock
and 48 MHz USB clock. PC13 drives the common active-low Blue Pill LED.

This Phase A source builds against ST's STM32CubeF1 HAL and USB Device CDC
middleware. It does not program a board. The USB descriptor uses provisional
experimental VID/PID `CAFE:4001`. PLASMA has no documented ownership or
authorization for this pair. It is **not an official PLASMA USB ID**. Obtain
an assigned or otherwise authorized VID/PID before distribution, formal
release, or physical acceptance. The common Blue Pill has a fixed D+ pull-up,
so boot now briefly sinks PA12 D+ with an open-drain GPIO for 30 ms after
HAL/clock setup and before `USBD_Init`. It preloads LOW, enables only the
PA12 output, then releases it to floating input before USB HAL takes over.
An unexpectedly enabled USB clock stops startup before touching D+. This is
reset-entry firmware, not a supported jump from an active USB bootloader.
There is no runtime disconnect retry, PA13/PA14 remap, or physical rework.

[ST AN4879](https://www.st.com/content/st_com/en/technical-documents/an4879-introduction-to-usb-hardware-and-pcb-guidelines-using-stm32-mcus-stmicroelectronics_asset/chunk-001-topic-an4879-usb-on-stm32-products.html)
documents the F103 external 1.5 kΩ D+ pull-up. The pinned F1 HAL's
`USB_DevConnect`/`USB_DevDisconnect` do nothing for this USB FS peripheral.
[STM32duino's upstream implementation](https://github.com/stm32duino/Arduino_Core_STM32/blob/main/libraries/USBDevice/src/usbd_if.c)
describes a brief startup D+ low pulse followed by floating input for fixed
pull-ups, and warns that it is a workaround rather than a standards-compliant
switched pull-up; it also warns against attempting it with F103 USB active.
Here open-drain avoids driving D+ HIGH. With the expected 1.5 kΩ to 3.3 V,
static sink current is approximately 2.2 mA. Board wiring/pull-up value and
host behavior still require physical verification; this does not repair a
wrong resistor, cable, host driver, or arbitrary CDC stall.

MCU RESET restarts the stack but does not remove the fixed pull-up by itself.
Host serial close/open (which may toggle DTR) does not reset the MCU or remove
USB power; firmware does not gate transmission on DTR. Physical USB unplug
removes the bus connection and may remove power. These are separate tests.
The owner's prior Mac test reported 121 heartbeats plus ID over 60 seconds
on the preceding diagnostic firmware; it does not validate this new pulse.
RESET recovery and physical unplug/replug on this candidate remain NOT_RUN.
A controlled pull-up or physical unplug is an alternative, but hardware
rework is outside this patch. Failure rollback is the previous diagnostic
firmware via the owner's existing authorized flashing route; no automatic
flash or hardware operation is performed here. A missing HAL tick can stall
the boot delay; the output is released on MCU reset. Runtime LED/USB service
has no added blocking delay.

## Independent PC13 diagnostics

PC13 is initialized active-low ON before HAL, HSE/PLL and USB initialization.
After initialization the main loop toggles it every 500 ms in AUTO mode,
including while USB is unconfigured, suspended or transmitting. The unsigned
elapsed-tick timer handles 32-bit wrap and catches up missed periods without
blocking USB service. This timer is separate from the CDC heartbeat.
`LED ON` and `LED OFF` take persistent manual precedence, including across USB
reset/reconnect; `LED AUTO` restarts ON with a new 500 ms LED deadline. Reboot
also restores AUTO. Terminal errors override all modes with repeating double
flashes and a long dark gap. The fault pattern uses a volatile busy loop,
no SysTick or interrupts; its speed depends on the clock at failure and is
not a calibrated timing measurement. Early boot ON is a marker, not proof
that clock setup or USB completed. A stalled HAL tick or unexpected CPU fault
is not diagnosed by this main-loop heartbeat.

## Wire behavior

After USB reaches `CONFIGURED`, a heartbeat is due 500 ms later, without a
host command. Format: `HB version=0.1 seq=<n> uptime_ms=<HAL_GetTick()>\r\n`.
Sequence starts at 1, advances only when the CDC transmit API accepts a frame,
and remains increasing across reconnect. The next due time is 500 ms after an
accepted heartbeat. CDC BUSY defers a frame without blocking or duplicating
the sequence. The transmit buffer is static and is reused only when the CDC
class `TxState` becomes idle. USB reset/disconnect invalidates queued replies
and restarts the heartbeat delay on the next configuration. Under sustained
traffic, actual output intervals can be longer than 500 ms.

ASCII commands are newline-delimited, with optional carriage return. Replies
use CRLF. The RX interrupt copies data into a bounded ring; the main loop parses
it independently of TX availability. Supported commands:

| Command | Reply | Meaning |
| --- | --- | --- |
| `ID` | `ID PLASMA_BLUE_PILL_CDC/0.1` | Firmware identity |
| `PING` | `PONG` | Transport response |
| `LED ON` / `LED OFF` | Same text | Latch manual LED state until AUTO or reboot |
| `LED AUTO` | Same text | Resume autonomous blink, starting ON |
| `UPTIME` | `UPTIME <ms>` | HAL tick, wraps at 32 bits |
| `COUNT` | `COUNT <n>` | Complete command lines received since boot |
| `RX_DROPS` | `RX_DROPS <n>` | RX ring bytes, overlong line bytes, or replies dropped since boot |

An unknown nonempty command replies `ERR UNKNOWN_COMMAND`; an overlong line
replies `ERR LINE_TOO_LONG`. The reply queue has seven usable slots. A full
queue increments `RX_DROPS` and discards the new reply. The CDC line-coding
control request stores and returns the host's 7-byte setting; it does not
change the USB data path.

## Reproducible Phase A build on SWPC

The following package versions were used without changing the system install:
Ubuntu Jammy `gcc-arm-none-eabi` `15:10.3-2021.07-4`, `binutils-arm-none-eabi`
`2.38-3ubuntu1+15build1`, `libnewlib-dev` and `libnewlib-arm-none-eabi`
`3.3.0-1.3`; CMake 3.22.1 and Ninja 1.10.1. These packages are extracted to
`/tmp/plasma-arm-toolchain`. A system-installed Ubuntu toolchain can be used
with `ARM_GCC_ROOT=/`.

STM32CubeF1 and its three used submodules are pinned by full Git commits in
`CMakeLists.txt`. Fetch from the official STMicroelectronics repositories:

```bash
git clone https://github.com/STMicroelectronics/STM32CubeF1.git /tmp/plasma-stm32cubef1
git -C /tmp/plasma-stm32cubef1 checkout c7656f1fee178058be2f8ebfc8df9eaf91dc565e
git -C /tmp/plasma-stm32cubef1 submodule update --init Drivers/CMSIS/Device/ST/STM32F1xx Drivers/STM32F1xx_HAL_Driver Middlewares/ST/STM32_USB_Device_Library
cd /tmp
apt download gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-dev libnewlib-arm-none-eabi
for package in /tmp/*arm-none-eabi*.deb /tmp/libnewlib-dev*.deb; do dpkg-deb -x "$package" /tmp/plasma-arm-toolchain; done
```

From the repository root:

```bash
cmake -S firmware/blue-pill-usb-cdc -B /tmp/plasma-blue-pill-build -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/firmware/blue-pill-usb-cdc/cmake/arm-none-eabi.cmake" \
  -DARM_GCC_ROOT=/tmp/plasma-arm-toolchain \
  -DSTM32CUBE_F1_ROOT=/tmp/plasma-stm32cubef1
cmake --build /tmp/plasma-blue-pill-build -v
python3 firmware/blue-pill-usb-cdc/host/check_artifacts.py \
  /tmp/plasma-blue-pill-build /tmp/plasma-arm-toolchain/usr/bin
```

The build emits `.elf`, `.hex`, `.bin`, and `.map` under the build directory.
The static checker uses `arm-none-eabi-size`, `readelf`, and `objdump` to assert
Flash/RAM bounds, vector stack pointer, Reset/SysTick/USB handler addresses,
and firmware strings in the binary image.

## Host-only tests

```bash
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -Ifirmware/blue-pill-usb-cdc/include \
  firmware/blue-pill-usb-cdc/src/app.c \
  firmware/blue-pill-usb-cdc/tests/test_app.c \
  -o /tmp/plasma-blue-pill-app-test
/tmp/plasma-blue-pill-app-test
python3 -m unittest discover -s firmware/blue-pill-usb-cdc/host -p 'test_*.py' -v
```

`host/cdc_probe.py` is a future serial-port test using pyserial. It prints each
heartbeat immediately and checks exact consecutive sequence/interval/uptime
and the exact `ID PLASMA_BLUE_PILL_CDC/0.1` reply. Default duration is 60s.
It allows 3s for the first heartbeat, rejects silence exceeding 1.5s (including
a silent tail), and requires at least `max(3, floor(0.9 * active_seconds / 0.5))`
frames. Active seconds exclude the 3s startup allowance. Thus a normal 60s
run requires at least 102 frames as well as interval/sequence checks.
A late arriving frame cannot erase an excessive gap. The live probe refuses Python `-O` before importing pyserial,
since these diagnostic checks use assertions. Normal continuous observation leaves the Host Port open.
An optional `--host-port-pause-seconds <seconds>` closes and reopens only the
host serial port, allowing a sequence gap across that deliberate interruption.
Only actual close/open time plus a bounded 1.5s reacquisition allowance is
excluded from coverage. Reopening must leave more than 2.5s of observation;
recovery must arrive within 1.5s, and the requested pause must actually occur.
The exception does not exempt later silence or subsequent sequence gaps.
It does not disconnect USB power or prove a physical USB reconnect. **The
live probe is not run in Phase A.** Neither
these tests nor the static artifact check prove enumeration, real USB timing,
electrical behavior, disconnect/reconnect, LED operation, or physical CDC
transmission on a Blue Pill. Those outcomes are `NOT_RUN` in Phase A.
