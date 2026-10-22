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
so firmware does not emulate USB detach. Physical unplug/replug and board-specific D+
pull-up behavior remain untested.

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
| `LED ON` / `LED OFF` | Same text | Set PC13 LED state |
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
and the `ID` reply. Normal continuous observation leaves the Host Port open.
An optional `--host-port-pause-seconds <seconds>` closes and reopens only the
host serial port, allowing a sequence gap across that deliberate interruption.
It does not disconnect USB power or prove a physical USB reconnect. **The
live probe is not run in Phase A.** Neither
these tests nor the static artifact check prove enumeration, real USB timing,
electrical behavior, disconnect/reconnect, LED operation, or physical CDC
transmission on a Blue Pill. Those outcomes are `NOT_RUN` in Phase A.
