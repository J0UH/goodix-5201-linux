#!/usr/bin/env python3
"""Identify a Goodix 27c6:5201 sensor and check that it works (no finger needed).

Only volatile commands are sent; nothing is written to the sensor's flash.
"""
from goodix5201 import Device, ProtocolError, ridge_energy


def main():
    with Device() as d:
        firmware = d.firmware_version()
        print(f"firmware version : {firmware}")
        if "_HT_APP_" not in firmware:
            print("  -> not the non-TLS HT firmware this driver supports")
        print(f"chip id          : {d.chip_id():#x}")
        try:
            d.bring_up()
            print("configuration    : accepted")
            frame = d.capture_frame()
            ridge = ridge_energy(frame)
            state = "empty" if ridge < 25 else "finger present"
            print(f"frame            : OK, ridge energy {ridge:.1f} ({state})")
        finally:
            d.sleep()


if __name__ == "__main__":
    try:
        main()
    except ProtocolError as e:
        raise SystemExit(f"error: {e}")
