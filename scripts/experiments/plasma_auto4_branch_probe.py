#!/usr/bin/env python3
"""PLASMA AUTO-4 pre-merge CPU-only Path 2 candidate probe.

Intentional no imports beyond Python stdlib and no device, network or file I/O.
"""
def main() -> None:
    print("n,cube")
    for n in range(1, 9):
        print(f"{n},{n * n * n}")

if __name__ == "__main__":
    main()
