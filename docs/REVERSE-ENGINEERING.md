# How the protocol was reverse engineered

This is how the 27c6:5201 protocol was worked out in about a day, without
flashing firmware and without a Windows installation. The steps should carry
over to related Goodix sensors (see [PROTOCOL.md § Related devices](PROTOCOL.md#9-related-devices)).
Every command used is volatile: nothing is written to the sensor's flash, and
the Windows driver keeps working.

Tools used: Python with `pyusb` (see [`tools/`](../tools)), `objdump`, and the
vendor's Windows driver package.

## 1. Identify the hardware

```sh
lsusb -v -d 27c6:5201
```

The descriptors show a CDC ACM "modem" (Linux binds `cdc_acm`) with the strings
`HTMicroelectronics` / `Goodix Fingerprint Device` / `HTK32`. Searching for those
strings finds the same identity on Goodix sensors that the
[goodix-fp-dump](https://github.com/goodix-fp-linux-dev/goodix-fp-dump) project
already studied (e.g. 27c6:5395). That suggested a known protocol family behind a
known USB bridge.

goodix-fp-dump's `protocol.py` talks to exactly this kind of interface: the
bulk endpoints of the CDC data interface.

## 2. Find the framing: ask for the firmware version

Every goodix-fp-dump driver starts with the same two harmless commands: a no-op
and "firmware version" (`0xa8`). Wrapped in the `0xa0` message-pack header that
most of those drivers use, the device did not answer. Sent without that wrapper
(goodix-fp-dump's "wrapless" framing, used by the 53x5 family) it did:

```
host   -> a8 03 00 00 00 ff
device <- b0 03 00 a8 03 4c                    ACK
device <- a8 15 00 "GF5288_HT_APP_20041\0" f8  reply
```

`tools/identify.py` does this.

The firmware name was the key clue:
- `GF5288` is the sensor goodix-fp-dump drives in the 53x5 family.
- `HT` is this USB bridge.
- There is **no `SEC`**. The 53x5 firmware is `GF5288_HTSEC_APP_…`, and "SEC"
  means TLS with a pre-shared key, which is the hard part of every other Goodix
  driver. A production read of the PSK hash (`0xe4`, type `0xB003`) was
  acknowledged but never answered, which confirmed the firmware has no TLS.

Further read-only commands gave the chip ID (`0x2202a0`, register 0) and the
32-byte OTP calibration block.

## 3. Get frames: the configuration

A frame request was acknowledged but produced nothing, and the 53x5 sensor
configuration was rejected. The device needs its own 256-byte configuration, and
the Windows driver must contain it.

ASUS publishes the driver ("Goodix Fingerprint driver and utility", e.g.
`Fingerprint_Goodix_Win10_64_VER10201300.zip`). Its `.inf` names this device
(`USB\Vid_27C6&Pid_5201 ;GF3208`), and `milanFusb.dll` contains the protocol
code ("Milan" is Goodix's codename for this generation).

Configurations start with a type byte and a table of eight `(offset, size)`
section pairs, where each section starts where the previous one ends. Scanning
the DLL for that chain finds five blobs:

```sh
tools/extract_config.py milanFusb.dll
```

The firmware accepted all five, so acceptance did not identify the right one.
Frames did:

- The `0x58` configuration (almost identical to goodix-fp-dump's known GF3208
  configuration) gave 7680-byte frames, i.e. 80 × 64 pixels. They showed
  diagonal streaks: an autocorrelation of the pixel data peaked at a lag of
  **108**, not 80. The sensor rows are 108 pixels wide and the frame was
  being cut short.
- The `0x08` configuration gave **14265** bytes = 5 + 108 × 88 × 1.5 + 4: full
  108 × 88 frames plus a header and a checksum.

## 4. The obfuscation

The 108 × 88 frames were uniform noise across the whole 12-bit range. A badly
configured sensor gives flat or saturated values, not that, so this looked like
encryption. Three observations narrowed it down:

1. **The trailer is a CRC32/MPEG-2 over the ciphertext**, the same layout the 53x5
   family uses after its TLS layer, where the payload is "GEA" encrypted with a
   key derived from the TLS session.
2. **The keystream is fixed.** XORing two empty-sensor frames left a third of the
   bytes zero (byte entropy dropped from 8.0 to 4.5). A per-session key would
   not do that. So: GEA with a constant key.
3. **The key is in the DLL.** GEA's keystream step uses distinctive masks
   (`0x1000000`, `0x20000`, `0x80000`). Searching the disassembly for them finds
   the keystream function, which is called from a decryption loop, whose only
   caller loads the key right before the call:

   ```sh
   objdump -d -M intel milanFusb.dll > milanFusb.asm
   grep -n "0x1000000" milanFusb.asm          # the keystream step
   # follow "call <that function>" to the decrypt loop, then its caller:
   #   mov ecx, 0x12345678
   #   call <gea_decrypt>
   ```

With key `0x12345678`, the frame turned into a clean image of an empty sensor,
and the next capture showed a fingerprint.

## 5. From prototype to driver

`tools/goodix5201.py` is the resulting reference implementation, and
`tools/capture.py` takes a fingerprint image with it. The libfprint driver
follows the same sequence (see [PROTOCOL.md § Sequences](PROTOCOL.md#8-sequences)).

Two more things only showed up when matching was attempted. See
[MATCHING.md](MATCHING.md):

- libfprint's standard matcher (NBIS) cannot work with a sensor this small,
  so the driver uses SIGFM.
- Finger detection needs an empty-sensor background frame. A finger resting on
  the sensor when the driver starts has to be detected, which is what the
  "ridge energy" measure is for.

## Adapting this to another sensor

1. `lsusb -v` and the USB strings: is it the same bridge (`HTMicroelectronics`, `HTK32`)?
2. Firmware version via `0xa8`, wrapless or `0xa0`-packed: which family, `SEC` or not?
3. Without `SEC`: extract the configurations from your vendor's driver and try
   them. The frame size tells you which one fits.
4. If frames look like noise: check the CRC, XOR two empty frames, and look for
   the GEA key in the DLL as above.
5. With `SEC`: you need goodix-fp-dump's TLS work, and possibly a firmware
   reflash. That is a different and riskier path.

Please report results for other devices, even failures. See the README.
