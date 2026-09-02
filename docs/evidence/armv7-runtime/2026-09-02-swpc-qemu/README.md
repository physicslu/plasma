# Plasma ARMv7 / QEMU Runtime Lab 測試報告

> 測試日期：2026-09-02
> Evidence Level：`swpc-qemu-armv7-userspace`

## 結論摘要

| 項目 | 結果 |
|---|---|
| Functional Result | **PASS** |
| Resource Result | **INVESTIGATE** |
| Overall Result | **INVESTIGATE** |
| Architecture | `armv7l` |
| Python | `3.12.14` |
| Runtime Size | `949,696 bytes` |
| Gateway-specific memory leak | **目前無證據支持** |
| Plasma Server memory leak | **目前無證據支持** |
| FD leak | **未觀察到** |
| Thread-count leak | **未觀察到** |
| QEMU ARMv7 + ThreadingHTTPServer request-correlated RSS growth | **已確認** |
| Native PYNQ-Z2 memory stability | **尚未驗證** |

最關鍵的 evidence：

- Gateway `/api/health/live` RSS growth：**27.432 KiB/request**
- 純 Python stdlib `ThreadingHTTPServer` control：**27.4384 KiB/request**
- Gateway / Control ratio：**0.999767**

兩者斜率幾乎一致，差異約 0.023%。目前 evidence 高度支持 QEMU ARMv7 userspace + `ThreadingHTTPServer` request lifecycle 的環境效應，而不是 Plasma Gateway application-specific memory leak。

## 測試環境

| 項目 | 值 |
|---|---|
| Host | SWPC |
| Execution Model | QEMU ARMv7 userspace |
| Architecture | `armv7l` |
| Python Version | `3.12.14` |
| Evidence Level | `swpc-qemu-armv7-userspace` |
| Gateway | Plasma packaged PPU Gateway |
| Server | Plasma packaged PPU Server |
| Control | Python stdlib `ThreadingHTTPServer` |
| Control imports Plasma | `false` |

## Readiness

```text
readiness_ms = 4678.246 ms
```

約 4.68 秒。此數值不可直接視為 PYNQ-Z2 native startup time。

## Gateway request-path results

| Path | Requests | Avg ms | P95 ms | P99 ms | Max ms | Gateway RSS Delta KiB | Server RSS Delta KiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| health/live | 1000 | 5.159 | 5.386 | 5.779 | 6.100 | **27,432** | 0 |
| health/ready | 1000 | 9.963 | 10.266 | 10.975 | 12.344 | **27,444** | 0 |
| PS Loopback | 1000 | 11.789 | 12.264 | 12.909 | 20.933 | **27,476** | 12 |

三條 application path 的 Gateway RSS growth 幾乎相同，且 thread / FD delta 都為 0。

## 30 秒後穩定狀態

Gateway：

```text
RSS     = 140,668 KiB
Threads = 2
FDs     = 4
```

Server：

```text
RSS     = 55,288 KiB
Threads = 2
FDs     = 7
```

RSS 沒有在 30 秒內下降，但 thread 與 FD 數量維持穩定。

## 純 Python ThreadingHTTPServer control

```text
implementation = python-stdlib-ThreadingHTTPServer
plasma_imported = false
```

Baseline：RSS 48,052 KiB / 2 threads / 4 FDs。

| Requests | RSS KiB | RSS Delta KiB | Threads | FDs |
|---:|---:|---:|---:|---:|
| 1,000 | 75,484 | **27,432** | 2 | 4 |
| 5,000 | 185,244 | **137,192** | 2 | 4 |
| 10,000 | 322,436 | **274,384** | 2 | 4 |

Final normalized growth：

```text
27.4384 KiB/request
```

成長從 1k → 5k → 10k 高度線性，沒有觀察到 plateau。

## Gateway vs Control

| 指標 | Gateway health/live | stdlib Control |
|---|---:|---:|
| RSS growth / request | **27.432 KiB** | **27.4384 KiB** |
| Threads delta | 0 | 0 |
| FD delta | 0 | 0 |

```text
gateway_to_control_ratio = 0.999767
```

目前最合理的工程判讀：

```text
QEMU ARMv7 userspace
+
Python ThreadingHTTPServer
+
per-request lifecycle
→ request-correlated RSS growth
```

而不是：

```text
Plasma Gateway business logic
→ application-specific memory leak
```

## Evidence boundary

本報告只代表：

```text
SWPC + QEMU ARMv7 userspace
```

不代表：

```text
PYNQ-Z2 native hardware
```

明確不宣告：PYNQ-Z2 hardware、systemd boot/reboot、PS-to-PL、Site I/O、target power、real IC programming、native Z2 memory stability。

## 下一步

QEMU 層的 memory isolation 已具備足夠 evidence。下一個高價值工作是：

```text
Layer 2 — PYNQ-Z2 Native Runtime / Resource Acceptance
```

在實體 Z2 測量 PYNQ idle、Server/Gateway idle、1000× health/live、1000× health/ready、1000× PS Loopback，以及 RSS/free RAM/swap/CPU/threads/FDs before、after 與 +30s。

判定原則：

```text
若 Z2 RSS stable / plateau
→ QEMU userspace artifact，可關閉此 memory concern

若 Z2 仍接近 27 KiB/request 線性成長
→ 重新開啟 Gateway runtime implementation investigation
```

## Final Engineering Assessment

```text
Functional correctness                  PASS
Gateway-specific memory leak            NOT SUPPORTED
Plasma Server memory leak               NOT SUPPORTED
FD leak                                 NOT OBSERVED
Thread-count leak                       NOT OBSERVED
QEMU ARMv7 ThreadingHTTPServer RSS grow CONFIRMED
Native Z2 memory stability              NOT YET TESTED
```
