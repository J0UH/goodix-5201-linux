#!/usr/bin/env python3
"""Find the sensor configuration blobs in the Goodix Windows driver.

Scans a binary (milanFusb.dll from the ASUS "Goodix Fingerprint driver and
utility" package) for 256 byte configurations. A configuration starts with a
version byte followed by a section table of (offset, size) pairs where each
section starts where the previous one ends; that chain is what is searched for.

    extract_config.py milanFusb.dll                 # list candidates
    extract_config.py milanFusb.dll --offset 0x2f140  # dump one (checksum fixed)

The 27c6:5201 driver uses the blob at 0x2F140 of milanFusb.dll v1.0.20.1300
(first byte 0x08). The other blobs are accepted by the firmware too, but only
this one produces full 108x88 frames.
"""
import argparse

from goodix5201 import fix_config_checksum


def candidates(data: bytes):
    for off in range(len(data) - 256):
        if data[off + 1] != 0x11:
            continue
        table = data[off + 1:off + 17]
        pairs = [(table[i], table[i + 1]) for i in range(0, 16, 2)]
        chain = 0
        for (base, size), (nxt, _) in zip(pairs, pairs[1:]):
            if size and base + size == nxt:
                chain += 1
            else:
                break
        if chain >= 4:
            yield off


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("binary")
    ap.add_argument("--offset", type=lambda v: int(v, 0))
    args = ap.parse_args()
    data = open(args.binary, "rb").read()

    if args.offset is None:
        for off in candidates(data):
            print(f"{off:#07x}: version {data[off]:#04x}, sections {data[off + 1:off + 17].hex(' ')}")
        return

    cfg = fix_config_checksum(data[args.offset:args.offset + 256])
    for i in range(0, 256, 32):
        print(cfg[i:i + 32].hex())


if __name__ == "__main__":
    main()
