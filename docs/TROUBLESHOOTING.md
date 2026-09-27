# Troubleshooting

## Quick checks

```sh
lsusb | grep 27c6:5201            # is this the sensor you have?
fprintd-list "$USER"              # is the device found, which fingers are enrolled?
journalctl -b -u fprintd          # fprintd's log
```

`fprintd-list` should print `Goodix Fingerprint Sensor 27c6:5201 (press)`. If it
says "No devices available", the installed libfprint does not contain the
driver: check `pacman -Qi libfprint-goodix-5201` (or how you installed it).

## Detailed logging

Detailed logging shows every finger detection decision and every match score:

```sh
sudo mkdir -p /etc/systemd/system/fprintd.service.d
printf '[Service]\nEnvironment=G_MESSAGES_DEBUG=all\n' | sudo tee /etc/systemd/system/fprintd.service.d/debug.conf
sudo systemctl daemon-reload && sudo systemctl stop fprintd
# reproduce the problem, then:
journalctl -b -u fprintd | grep -E "goodix5201|sigfm score|Finger|Captured|verify|enroll"
```

Remove it again afterwards (it is verbose):

```sh
sudo rm /etc/systemd/system/fprintd.service.d/debug.conf && sudo systemctl daemon-reload
```

Useful lines: `Finger on (score …, ridge …)`, `Captured image`, `sigfm score N/40`
(40 is the pass mark), `Sensor not empty at activation`, `Firmware version`.

## Common problems

**Enrollment shows `enroll-retry-scan` or `enroll-swipe-too-short`.**
That press was not usable, usually because the finger was lifted too early. Hold
it for about a second. Retries do not count against you.

**Verification says `verify-no-match` for the enrolled finger.**
- Enroll again and move the finger a little between the 15 presses (centre, tip,
  left, right, up, down). The sensor only sees a small part of the finger each time.
- Very dry or wet fingers give weaker images. Enroll a second finger as a
  fallback: `fprintd-enroll -f left-index-finger`.
- Look at the `sigfm score` lines in the detailed log. Genuine presses normally
  score in the hundreds or thousands.

**Nothing happens when touching the sensor.**
With detailed logging, look for `Sensor not empty at activation, waiting for the
finger to be lifted`. The driver needs one empty frame first, so lift the finger
and press again.

**fprintd logs `Data could not be parsed` / verification errors after an update.**
The stored print format changed between development builds. Delete and re-enroll:
`sudo fprintd-delete "$USER" && sudo fprintd-enroll "$USER"`.

**Omarchy: fingerprint is not offered when the laptop lid is closed.**
Intended: Omarchy skips the fingerprint prompt when the lid is shut, because the
sensor is on the keyboard deck.

**`Unsupported firmware …` in the log.**
Your sensor runs a different firmware than the one this driver was written for.
Please open an issue with the `Firmware version` line and your laptop model.

**Errors right after the device was plugged in or resumed.**
The device enumerates as a modem, and ModemManager may probe it through the
`ttyACM` port. The driver discards stale input before it starts, but if you
still see protocol errors, tell ModemManager to ignore the sensor:

```sh
echo 'ATTRS{idVendor}=="27c6", ATTRS{idProduct}=="5201", ENV{ID_MM_DEVICE_IGNORE}="1"' | sudo tee /etc/udev/rules.d/77-goodix-5201-mm-ignore.rules
sudo udevadm control --reload
```

## Recording a libfprint test case

libfprint's `tests/create-driver-test.py` needs the kernel's USB monitor, which
is not loaded by default. Without it the recorder silently skips the USB capture:

```sh
sudo modprobe usbmon
```

Record with the side of a finger, never the fingertip: the recording is
published with the driver and contains the complete image.

## Reporting a problem

Open an issue with:
- the laptop model and `lsusb -v -d 27c6:5201` output,
- `python3 tools/identify.py` output (see [tools/README.md](../tools/README.md)),
- the detailed fprintd log of the failing attempt.

Do not attach fingerprint images of a finger you use to log in.
