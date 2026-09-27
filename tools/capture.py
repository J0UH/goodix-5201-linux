#!/usr/bin/env python3
"""Capture one fingerprint image.

Writes <prefix>.png (processed 8 bit image, as fed to the matcher),
<prefix>-4x.png (enlarged for viewing) and <prefix>.pgm (raw 12 bit frame).

Note: fingerprint images are biometric data. Do not publish images of a
finger you use to log in.
"""
import argparse

from goodix5201 import HEIGHT, WIDTH, Device, ridge_energy, to_8bit, wait_for_finger, write_png


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prefix", nargs="?", default="finger")
    args = ap.parse_args()

    with Device() as d:
        d.bring_up()
        print("Keep the sensor empty for a moment...")
        background = d.capture_frame()
        if ridge_energy(background) > 25:
            raise SystemExit("The sensor is not empty, lift your finger and try again")
        print("Place your finger on the sensor (30 s)")
        frame = wait_for_finger(d, background)
        d.sleep()
    if frame is None:
        raise SystemExit("No finger detected")

    gray, w, h = to_8bit(frame, background)
    write_png(f"{args.prefix}.png", gray, w, h)
    write_png(f"{args.prefix}-4x.png", gray, w, h, scale=4)
    with open(f"{args.prefix}.pgm", "wb") as f:
        f.write(f"P5 {WIDTH} {HEIGHT} 4095\n".encode())
        f.write(b"".join(v.to_bytes(2, "big") for v in frame))
    print(f"Saved {args.prefix}.png, {args.prefix}-4x.png and {args.prefix}.pgm")


if __name__ == "__main__":
    main()
