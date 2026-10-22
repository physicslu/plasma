# Blue Pill USB CDC firmware v0.1 — Gate 1 / Phase A evidence

Executor: Codex Path 3 on `SWPC`, local isolated worktree from `origin/main`
`b8ad41a35`. Reviewed build source commit:
`ceda5b1894fda77effa280a39cf8557225685cd3`.

## Tool and dependency identity

| Component | Actual version or source revision |
| --- | --- |
| arm-none-eabi-gcc | Ubuntu package `15:10.3-2021.07-4`; GCC 10.3.1 |
| GNU binutils (`ld`, `size`, `readelf`, `objdump`) | Ubuntu package `2.38-3ubuntu1+15build1`; 2.38 |
| newlib | Ubuntu packages `libnewlib-dev` and `libnewlib-arm-none-eabi` `3.3.0-1.3` |
| CMake / Ninja | 3.22.1 / 1.10.1 |
| Host GCC / Python | 11.4.0 / 3.10.12 |
| STM32CubeF1 | `c7656f1fee178058be2f8ebfc8df9eaf91dc565e` |
| CMSIS device F1 | `c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22` |
| STM32F1 HAL | `bd368aa335c529641d2e567574885e02deacc64a` |
| USB Device Middleware | `e5a58ee2260204bfed632c7c56da0fdb41514a51` |

The ARM packages were extracted under `/tmp/plasma-arm-toolchain`; the ST
sources were checked out under `/tmp/plasma-stm32cubef1`. The system package
database, installed toolchain, services, and physical devices were not changed.
The firmware [README](../../../firmware/blue-pill-usb-cdc/README.md) gives
reproduction commands and the pinned-source contract.

## Actual Phase A results

| Check | Expected | Observed | Result |
| --- | --- | --- | --- |
| CMake + Ninja cross-build | ELF, HEX, BIN, MAP; exit 0 | Exit 0; all four emitted; [full log](build.log) | PASS |
| `arm-none-eabi-size` | Image fits 64 KiB Flash / 20 KiB RAM | Flash 18,328 B (27.97%); RAM 5,936 B (28.98%), including 2 KiB reserved stack | PASS |
| `readelf` / `objdump` static check | ARM ELF, Flash/RAM segments, valid vector pointers, firmware strings | SP `0x20005000`; Reset `0x0800094D`; SysTick `0x0800037D`; USB IRQ `0x08000381`; [inspection](inspection.log) | PASS |
| Host C app tests with UBSan | Commands, 500 ms schedule, BUSY, reconnect, RX overflow, concurrent parser | Exit 0, `app host tests PASS` | PASS |
| Host Python CDC monitor unit tests | Sequence, interval, ID, interruption parsing | 4 tests, exit 0; [host log](host-tests.log) | PASS |
| Real USB enumeration, unsolicited output, timing, physical disconnect/reconnect, LED | Measured on Blue Pill | No hardware operation in Phase A | NOT_RUN |
| ST-LINK, Flash, Reset, Z2/PL, other hardware | No operation in Phase A | No operation | NOT_RUN |

The build and static checker used the commands in the firmware README, with
`/tmp/plasma-blue-pill-phase-a-final` as the build directory. The C host
test used `gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined
-fno-omit-frame-pointer` and returned 0. The Python command was
`python3 -m unittest discover -s firmware/blue-pill-usb-cdc/host -p
'test_*.py' -v` and returned 0. `host/cdc_probe.py` was **not run against a
port**. [SHA256SUMS](SHA256SUMS) records the exact ELF, HEX, BIN, and MAP files
in [artifacts](artifacts/).

Phase A stops at code review. The provisional USB VID/PID and physical USB
behavior require review and later separately authorized physical acceptance.
