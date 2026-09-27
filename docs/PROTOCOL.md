# Goodix 27c6:5201 protocol

This document describes the USB protocol of the Goodix fingerprint sensor with
USB ID `27c6:5201` as implemented by the `goodix5201` libfprint driver. Everything
here was observed on real hardware (an ASUS ZenBook S UX391UA). Statements that
are inferred rather than observed are marked as such.

Contents:

1. [Hardware](#1-hardware)
2. [USB interface](#2-usb-interface)
3. [Message framing](#3-message-framing)
4. [Commands](#4-commands)
5. [Sensor configuration](#5-sensor-configuration)
6. [Frames](#6-frames)
7. [Finger detection calibration (FDT)](#7-finger-detection-calibration-fdt)
8. [Sequences](#8-sequences)
9. [Related devices](#9-related-devices)

## 1. Hardware

| Property | Value |
|---|---|
| USB ID | `27c6:5201` |
| USB strings | manufacturer `HTMicroelectronics`, product `Goodix Fingerprint Device ` (trailing space), serial `HTK32` |
| Bridge | HT32 microcontroller running Goodix firmware (the serial `HTK32` is the same on every unit) |
| Firmware | `GF5288_HT_APP_20041` (reported as `GF3208_HT_APP_20041` once a configuration is uploaded) |
| Chip ID | `0x2202a0` |
| Sensor | 108 × 88 pixels, 12 bit, press type, roughly 5.4 × 4.4 mm (pixel pitch ~50 µm, inferred from a ridge period of ~9 px) |
| Matching | on the host: the sensor only delivers images |
| Encryption | none: this is *not* a TLS ("SEC") firmware; frame data is only obfuscated with a fixed key |

The Windows driver's `.inf` lists this device as `USB\Vid_27C6&Pid_5201&mi_00 ;GF3208`.

## 2. USB interface

The device enumerates as a CDC ACM modem, so Linux binds `cdc_acm` to it and
creates `/dev/ttyACM*`. The protocol does not use the serial line: it runs over
the bulk endpoints of the data interface, and no line coding or DTR/RTS is
needed.

```
Device: USB 2.0, full speed, class 0xEF/0x02/0x01 (interface association)
  Interface 0: CDC communication (class 2, subclass 2 ACM, protocol 1)
    EP 0x82 IN  interrupt, 64 bytes, interval 255   (unused)
  Interface 1: CDC data (class 10)
    EP 0x03 OUT bulk, 64 bytes                        (host -> device)
    EP 0x81 IN  bulk, 64 bytes                        (device -> host)
```

A driver has to detach `cdc_acm`. Detaching it from interface 0 releases both
interfaces. Because `cdc_acm` is re-attached whenever the driver releases the
device, other software (e.g. ModemManager probing new modems) may have written
to the device in the meantime, so stale input should be drained before the
first command.

## 3. Message framing

All messages, in both directions, use the same format (called "wrapless" in
[goodix-fp-dump](https://github.com/goodix-fp-linux-dev/goodix-fp-dump), as
opposed to the `0xa0` message-pack wrapper used by other Goodix firmware):

```
+--------+-----------------+----------------------+----------+
| cmd u8 | len u16 LE      | payload (len-1 bytes)| checksum |
+--------+-----------------+----------------------+----------+
```

- `len` is the payload length plus one (it counts the checksum byte).
- `checksum = (0xAA - sum of all preceding bytes) & 0xFF`. The value `0x88`
  means "no checksum" and is accepted when parsing device messages; host messages
  with `0x88` were ignored by the device in testing, so always send a real
  checksum.
- `cmd = category << 4 | command << 1`. Bit 0 is the continuation flag (below).

**Chunking.** Messages travel in 64-byte USB packets. The first packet starts
with the message. Each following packet starts with `cmd | 1` and carries the
next 63 message bytes. The host pads every packet to 64 bytes with zeros;
sending all packets as one bulk transfer (a multiple of 64 bytes) works too.
The device pads its packets too, so the message length has to be taken from
the header. The device occasionally sends zero-length packets in between, which
are ignored.

**Acknowledgement.** The device acknowledges every host message with a message
`cmd = 0xb0` whose payload is `[acknowledged cmd, flags]`. Bit 0 of `flags` was
always set. Bit 1 was set until a sensor configuration had been uploaded
(observed; its exact meaning is inferred).

**Replies.** Commands with a reply send, after the ACK, a message with the same
`cmd` byte as the request.

Example, firmware version query and its answer:

```
host   -> a8 03 00 00 00 ff
device <- b0 03 00 a8 03 4c                         ACK of 0xa8
device <- a8 15 00 47 46 35 32 38 38 5f 48 54 5f    "GF5288_HT_APP_20041\0"
          41 50 50 5f 32 30 30 34 31 00 f8
```

## 4. Commands

| cmd | Name | Request payload | Reply payload |
|---|---|---|---|
| `0x00` | ping | `00 00` | none (ACK only) |
| `0x20` | get frame | `01 00 8b 00 84 00 8c 00 88 00` | 14265 bytes, see [Frames](#6-frames) |
| `0x36` | finger detection, manual | 22 bytes, see [FDT](#7-finger-detection-calibration-fdt) | 28 bytes |
| `0x60` | sleep | `01 00` | none |
| `0x82` | read sensor register | `00`, address u16 LE, length u16 LE | register bytes |
| `0x90` | upload configuration | 256 bytes, see [configuration](#5-sensor-configuration) | u16 LE: `1` accepted, `0` rejected |
| `0xa2` | reset | `01 14` (reset the sensor, not the MCU; 20 ms) | none |
| `0xa6` | read OTP | `00 00` | 32 bytes of per-sensor calibration data |
| `0xa8` | firmware version | `00 00` | NUL-terminated ASCII string |
| `0xc4` | set driver state | `01 00` | none (the Windows driver sends it twice) |
| `0xe4` | production read | read type u32 LE | none on this firmware (see below) |

Notes:

- **Chip ID**: register `0x0000`, 4 bytes, reads `02 a0 00 22`, which is `0x2202a0`
  in Goodix's 32-bit byte order (two big-endian 16-bit halves, low half first:
  `b[0] << 8 | b[1] | b[2] << 24 | b[3] << 16`).
- **No TLS**: on TLS firmware, production read type `0xB003` returns the hash
  of the pre-shared key. This firmware acknowledges the request but never
  answers, which is consistent with it having no PSK/TLS support at all.
- **Firmware update** commands exist in related firmware (category `0xf`). They
  were never used and must not be needed: all commands above are volatile.
- The 4-byte frame request of the related 53x5 firmware (`op, hv, dac u16`) is
  acknowledged but produces no frame on this firmware.

## 5. Sensor configuration

The firmware needs a 256-byte sensor configuration in RAM before it produces
frames. The configuration stays in the MCU's RAM until the device loses power,
but a driver should upload it on every activation.

```
offset  size  content
0       1     type/version (0x08 for this sensor)
1       16    section table: 8 x (offset u8, size u8); each section starts
              where the previous one ends
17      ...   sections of 4-byte entries: tag u16 LE, value u16 LE
254     2     checksum u16 LE = 0x10000 - (0xA5A5 + sum of the 127 preceding
              u16 LE words), modulo 0x10000
```

The configuration used by the driver comes from the ASUS Windows driver
(`milanFusb.dll`, v1.0.20.1300, offset `0x2F140`). The checksum stored there is
not valid (the Windows driver presumably fills it in at runtime), so it is
recomputed. `tools/extract_config.py` finds all configurations in the DLL by
their section-table structure. There are five, all accepted by the firmware:

| Offset | Type | Result |
|---|---|---|
| `0x2F140` | `0x08` | **108 × 88 frames, used by the driver** |
| `0x2F240` | `0x28` | no finger detection, no frames |
| `0x2F340` | `0x38` | no finger detection, no frames |
| `0x2F440` | `0x18` | no finger detection, no frames |
| `0x2FD40` | `0x58` | 7680-byte frames (80 × 64): the GF3208 layout, but read from a 108-pixel-wide sensor, so the image is garbled |

Uploading the `0x08` configuration changes the name prefix the firmware reports
from `GF5288` to `GF3208`.

## 6. Frames

The reply to `0x20` is 14265 bytes:

```
offset  size   content
0       5      header, observed as 02 a0 00 22 00 (starts with the chip ID)
5       14256  pixel data, GEA-obfuscated (108 * 88 pixels * 1.5 bytes)
14261   4      CRC32/MPEG-2 of the 14256 obfuscated bytes, Goodix u32 order
```

**CRC.** CRC32/MPEG-2: polynomial `0x04C11DB7`, initial value `0xFFFFFFFF`, no
reflection, no final XOR, computed over the obfuscated pixel data.

**GEA obfuscation.** Goodix's "GEA" stream cipher XORs each little-endian 16-bit
word with a keystream generated from a 32-bit key by a shift-register
construction (see [`tools/gea.py`](../tools/gea.py) or `gdx_gea_decrypt()` in the
driver). On TLS firmware the key comes from the TLS session. Here it is
the constant **`0x12345678`**, loaded right before the call to the decryption
routine in `milanFusb.dll` (`mov ecx, 0x12345678`), and the Windows driver only
calls that routine when a per-device flag is set. Consistent with that, frames
produced with the `0x58` configuration arrived unobfuscated, while the `0x08`
configuration yields obfuscated frames.

**Pixels.** After de-obfuscation, every 6 bytes hold 4 pixels of 12 bits:

```
p0 = (c[0] & 0x0f) << 8 | c[1]
p1 =  c[3]         << 4 | c[0] >> 4
p2 = (c[5] & 0x0f) << 8 | c[2]
p3 =  c[4]         << 4 | c[5] >> 4
```

Pixels are stored row by row, 108 per row, 88 rows. An empty sensor reads around
2400 with a darker one-to-two pixel border and faint horizontal banding. Ridges in
contact with the sensor lower the value, so `background - frame` is large on
ridges.

## 7. Finger detection calibration (FDT)

The sensor has hardware finger detection ("FDT"). The driver only uses the
manual calibration command `0x36`, because the Windows driver sends it before
the first frame; frames are polled for finger detection instead of using FDT
events.

Request (22 bytes):
```
0d 01  8b 00 84 00 8c 00 88 00  80 96 80 91 80 92 80 85 80 8c 80 86
```

Reply (28 bytes), observed as:
```
80 00  0f 04  5f 01 98 01 88 01 70 01 63 01 9a 01 92 01 66 01 4c 01 7d 01 71 01 00 00
```
interpreted (following goodix-fp-dump's 53x5 driver) as IRQ status u16 LE,
touch flags u16 LE and 12 FDT channel values u16 LE.

Commands `0x32`/`0x34` (FDT "down"/"up" events) exist in related firmware and
could replace polling in the future.

## 8. Sequences

**Activation** (what the driver does each time fprintd starts an operation):

1. Detach `cdc_acm`, claim interfaces 0 and 1.
2. Drain stale input from EP `0x81` (read with a short timeout until nothing arrives).
3. `0x00` ping.
4. `0xa8` firmware version; refuse anything without `_HT_APP_`.
5. `0xa2` reset.
6. `0x90` upload configuration; must return `1`.
7. `0xc4` set driver state, twice.
8. `0x36` finger detection calibration.
9. `0x20` frame: the empty-sensor background.

**Capture.** Frames are requested in a loop (about 12 frames per second including
decoding). A finger is present when the mean absolute difference to the
background exceeds 50 (empty-sensor noise is ~3, a finger 200-400) and the frame
contains ridge structure. Pressure builds up over a few frames; the frame is
taken once the difference stops growing. A finger is gone when the difference
drops below 25.

**Deactivation.** `0x60` sleep, then release the interfaces (which re-attaches
`cdc_acm`).

## 9. Related devices

The USB strings `HTMicroelectronics` / `HTK32` are shared by other Goodix
sensors, which use the same bridge firmware family:

| USB ID | Notes |
|---|---|
| `27c6:5301` | GF3208, e.g. Dell Inspiron 15 7577. Same generation; untested with this driver |
| `27c6:5385`, `27c6:5395` | GF5288 with TLS ("SEC") firmware, supported by goodix-fp-dump after reflashing |
| `27c6:5503` | GF3208 behind a different MCU with TLS firmware |

If you own one of these, see [REVERSE-ENGINEERING.md](REVERSE-ENGINEERING.md)
for how the protocol details were found.
