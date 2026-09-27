#!/usr/bin/env python3
"""Record raw frames for offline matcher evaluation (see eval_matchers.py).

Writes <dir>/background.raw and one frame per press: A_01.raw ... for the
finger you would enroll, B_01.raw ... for a different finger. Each file is
108 * 88 little-endian uint16 pixels (12 bit values).

Note: this is biometric data. Keep it private.
"""
import argparse
import os
import struct
import time

from goodix5201 import Device, frame_score, ridge_energy, wait_for_finger


def save(path, frame):
    with open(path, "wb") as f:
        f.write(struct.pack(f"<{len(frame)}H", *frame))


def session(d, background, out, prefix, count, name):
    print(f"\n=== {name}: {count} presses. Press, hold ~1 s, lift; vary the position a little ===")
    for i in range(1, count + 1):
        frame = wait_for_finger(d, background, timeout=120)
        if frame is None:
            raise SystemExit("timed out waiting for a finger")
        save(os.path.join(out, f"{prefix}_{i:02d}.raw"), frame)
        print(f"  {prefix} {i:2d}/{count} (signal {frame_score(frame, background):.0f}), lift your finger")
        while frame_score(d.capture_frame(), background) > 25:
            time.sleep(0.03)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--genuine", type=int, default=15, help="presses of the enrolled finger")
    ap.add_argument("--impostor", type=int, default=6, help="presses of a different finger")
    args = ap.parse_args()
    os.makedirs(args.dir, exist_ok=True)

    with Device() as d:
        d.bring_up()
        background = d.capture_frame()
        if ridge_energy(background) > 25:
            raise SystemExit("The sensor is not empty, lift your finger and try again")
        save(os.path.join(args.dir, "background.raw"), background)
        session(d, background, args.dir, "A", args.genuine, "Finger A (the one you would enroll)")
        input("\nSwitch to a DIFFERENT finger and press Enter...")
        session(d, background, args.dir, "B", args.impostor, "Finger B (a different finger)")
        d.sleep()
    print(f"\nSaved {args.genuine + args.impostor} frames in {args.dir}")


if __name__ == "__main__":
    main()
