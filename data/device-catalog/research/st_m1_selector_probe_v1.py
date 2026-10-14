#!/usr/bin/env python3
from __future__ import annotations
import re
import urllib.request

URLS = [
    "https://www.st.com/en/microcontrollers-microprocessors/stm32f4-series/products.html",
    "https://www.st.com/en/microcontrollers-microprocessors/stm32h5-series/products.html",
]

for url in URLS:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Plasma-ST-M1-Probe/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        text = raw.decode("utf-8", errors="replace")
    print(f"URL={url}")
    print(f"STATUS=200 BYTES={len(raw)}")
    for needle in ("RAM Size", "Supply Voltage", "STM32F401CB", "STM32H503CB"):
        print(f"{needle}={needle in text}")
    for pat in (
        r"RAM Size.{0,180}",
        r"Supply Voltage.{0,180}",
        r"STM32F401CB.{0,500}",
        r"STM32H503CB.{0,500}",
    ):
        match = re.search(pat, text, re.I | re.S)
        if match:
            snippet = re.sub(r"\s+", " ", match.group(0))
            print("SNIPPET=" + snippet[:700])
    print("---")
