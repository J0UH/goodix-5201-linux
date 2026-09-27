"""Userspace reference implementation of the Goodix 27c6:5201 protocol.

This is the Python prototype the libfprint driver was developed from. It is
meant for research and debugging, not for authentication: use the libfprint
driver (via fprintd) for that.

Requirements: pyusb (and read/write access to the USB device, see
70-goodix-5201-dev.rules). All commands used here are volatile: nothing is
written to the sensor's flash.

See docs/PROTOCOL.md for the protocol specification.

SPDX-License-Identifier: LGPL-2.1-or-later
"""
import struct
import time

import usb.core
import usb.util

from gea import gea_decrypt

VID, PID = 0x27C6, 0x5201
IFACE_COMM, IFACE_DATA = 0, 1
EP_OUT, EP_IN = 0x03, 0x81
CHUNK = 64

WIDTH, HEIGHT = 108, 88
PIXELS = WIDTH * HEIGHT
IMAGE_BYTES = PIXELS * 3 // 2
IMAGE_HEADER = 5
IMAGE_CRC = 4

GEA_KEY = 0x12345678

CMD_PING = 0x00
CMD_IMAGE = 0x20
CMD_FDT_MANUAL = 0x36
CMD_SLEEP = 0x60
CMD_READ_REGISTER = 0x82
CMD_CONFIG = 0x90
CMD_RESET = 0xA2
CMD_OTP = 0xA6
CMD_FIRMWARE = 0xA8
CMD_ACK = 0xB0
CMD_DRV_STATE = 0xC4

FDT_MANUAL = bytes.fromhex("0d018b0084008c0088008096809180928085808c8086")
IMAGE_REQUEST = bytes.fromhex("01008b0084008c008800")

# 256 byte sensor configuration, taken from the ASUS Windows driver
# (milanFusb.dll v1.0.20.1300, offset 0x2F140) with the checksum recomputed.
# tools/extract_config.py reproduces it from the DLL.
CONFIG = bytes.fromhex(
    "08115465248924ad1cc91ce504e904ed13ba000100ca00070084008081860080"
    "8c880080978a0080b08c0080868e00808c900080a0920080b394008084960080"
    "88980080a09a0080b85600082858004800700001007200785674003412260000"
    "12d000000020010204200010402200012024003200800001045c008000280200"
    "002a0200008200801520018204200010402200012024001400800001045c0000"
    "01280200002a020000820080152001080422001008800001005c008000280200"
    "002a02000082008015200108045c008000500001055200080054001001280200"
    "002a020000000000000000000000000000000000000000000000000000006b9f")


class ProtocolError(Exception):
    pass


# ---- message framing --------------------------------------------------------

def checksum(data: bytes) -> int:
    return (0xAA - sum(data)) & 0xFF


def encode_message(cmd: int, payload: bytes) -> bytes:
    """[cmd] [len u16 LE = payload + 1] [payload] [checksum], split in 64 byte
    chunks; continuation chunks start with cmd | 1; all chunks zero padded."""
    body = struct.pack("<BH", cmd, len(payload) + 1) + payload
    data = body + bytes([checksum(body)])
    chunks = [data[:CHUNK]]
    data = data[CHUNK:]
    while data:
        chunks.append(bytes([cmd | 1]) + data[:CHUNK - 1])
        data = data[CHUNK - 1:]
    return b"".join(c + b"\x00" * (CHUNK - len(c)) for c in chunks)


def crc32_mpeg2(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def decode_u32(data: bytes) -> int:
    """Goodix stores 32 bit values as two big-endian 16 bit halves, low half first."""
    return data[0] * 0x100 + data[1] + data[2] * 0x1000000 + data[3] * 0x10000


def unpack_12bit(data: bytes) -> list[int]:
    """6 bytes -> 4 pixels of 12 bit."""
    px = []
    for i in range(0, len(data) - len(data) % 6, 6):
        c = data[i:i + 6]
        px += [((c[0] & 0xF) << 8) + c[1], (c[3] << 4) + (c[0] >> 4),
               ((c[5] & 0xF) << 8) + c[2], (c[4] << 4) + (c[5] >> 4)]
    return px


def decode_frame(payload: bytes) -> list[int]:
    """Image reply payload -> WIDTH * HEIGHT pixels (checks size and CRC)."""
    if len(payload) != IMAGE_HEADER + IMAGE_BYTES + IMAGE_CRC:
        raise ProtocolError(f"unexpected image size {len(payload)}")
    body = payload[IMAGE_HEADER:IMAGE_HEADER + IMAGE_BYTES]
    if crc32_mpeg2(body) != decode_u32(payload[-IMAGE_CRC:]):
        raise ProtocolError("image CRC mismatch")
    return unpack_12bit(gea_decrypt(GEA_KEY, body))


def fix_config_checksum(config: bytes) -> bytes:
    """Last u16 LE = 0x10000 - (0xA5A5 + sum of the preceding u16 LE words)."""
    cfg = bytearray(config)
    s = 0xA5A5
    for i in range(0, len(cfg) - 2, 2):
        s = (s + int.from_bytes(cfg[i:i + 2], "little")) & 0xFFFF
    cfg[-2:] = ((0x10000 - s) & 0xFFFF).to_bytes(2, "little")
    return bytes(cfg)


# ---- device -----------------------------------------------------------------

class Device:
    """Opens the sensor, detaching cdc_acm; reattaches it on close."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise ProtocolError("no 27c6:5201 sensor found")
        self.detached = []
        for iface in (IFACE_COMM, IFACE_DATA):
            # detaching cdc_acm from the comm interface also releases the data one
            if self.dev.is_kernel_driver_active(iface):
                self.dev.detach_kernel_driver(iface)
                self.detached.append(iface)
        usb.util.claim_interface(self.dev, IFACE_DATA)
        self.drain()

    def close(self):
        usb.util.release_interface(self.dev, IFACE_DATA)
        usb.util.dispose_resources(self.dev)
        for iface in self.detached:
            try:
                self.dev.attach_kernel_driver(iface)
            except usb.core.USBError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def drain(self):
        """Discard stale input."""
        while True:
            try:
                if not self.dev.read(EP_IN, CHUNK, 50):
                    return
            except usb.core.USBTimeoutError:
                return

    def _read_chunk(self, timeout: float) -> bytes:
        for _ in range(10):  # the device occasionally sends zero-length packets
            chunk = self.dev.read(EP_IN, CHUNK, int(timeout * 1000)).tobytes()
            if chunk:
                return chunk
        raise ProtocolError("too many empty reads")

    def recv(self, timeout: float = 1.0) -> tuple[int, bytes]:
        """Returns (command byte, payload) of the next message."""
        data = self._read_chunk(timeout)
        cmd = data[0]
        size = struct.unpack("<H", data[1:3])[0]
        while len(data) < size + 3:
            chunk = self._read_chunk(timeout)
            if chunk[0] != cmd | 1:
                raise ProtocolError(f"bad continuation chunk {chunk[0]:#04x}")
            data += chunk[1:]
        data = data[:size + 3]
        if len(data) < 4:
            raise ProtocolError("truncated message")
        if data[-1] not in (0x88, checksum(data[:-1])):
            raise ProtocolError(f"bad checksum in {data.hex(' ')}")
        if self.verbose:
            print(f"  << {cmd:#04x} {data[3:-1].hex(' ')}")
        return cmd, data[3:-1]

    def command(self, cmd: int, payload: bytes, reply: bool = False,
                timeout: float = 1.0) -> bytes | None:
        """Send a message, wait for its ACK and optionally for the reply."""
        if self.verbose:
            print(f"  >> {cmd:#04x} {payload.hex(' ')}")
        self.dev.write(EP_OUT, encode_message(cmd, payload), 1000)
        ack_cmd, ack = self.recv(1.0)
        if ack_cmd != CMD_ACK or not ack or ack[0] != cmd:
            raise ProtocolError(f"expected ACK for {cmd:#04x}, got {ack_cmd:#04x} {ack.hex()}")
        if not reply:
            return None
        rcmd, data = self.recv(timeout)
        if rcmd != cmd:
            raise ProtocolError(f"expected reply {cmd:#04x}, got {rcmd:#04x}")
        return data

    # ---- commands (all volatile) ----

    def ping(self):
        self.command(CMD_PING, b"\x00\x00")

    def firmware_version(self) -> str:
        return self.command(CMD_FIRMWARE, b"\x00\x00", reply=True).split(b"\x00")[0].decode()

    def read_otp(self) -> bytes:
        return self.command(CMD_OTP, b"\x00\x00", reply=True)

    def read_register(self, addr: int, size: int) -> bytes:
        return self.command(CMD_READ_REGISTER, b"\x00" + struct.pack("<HH", addr, size), reply=True)

    def chip_id(self) -> int:
        return decode_u32(self.read_register(0, 4))

    def reset_sensor(self):
        """Sensor reset (not the MCU), 20 ms."""
        self.command(CMD_RESET, bytes([0x01, 20]))

    def upload_config(self, config: bytes = CONFIG) -> bool:
        return self.command(CMD_CONFIG, config, reply=True)[0] == 1

    def bring_up(self) -> bytes:
        """Same sequence as the libfprint driver's activation; returns the
        finger detection (FDT) calibration reply."""
        self.ping()
        self.reset_sensor()
        if not self.upload_config():
            raise ProtocolError("sensor rejected the configuration")
        self.command(CMD_DRV_STATE, b"\x01\x00")
        self.command(CMD_DRV_STATE, b"\x01\x00")
        return self.command(CMD_FDT_MANUAL, FDT_MANUAL, reply=True)

    def capture_frame(self) -> list[int]:
        """One frame of WIDTH * HEIGHT 12 bit pixels."""
        return decode_frame(self.command(CMD_IMAGE, IMAGE_REQUEST, reply=True, timeout=3.0))

    def sleep(self):
        self.command(CMD_SLEEP, b"\x01\x00")


# ---- finger detection -------------------------------------------------------

def frame_score(frame: list[int], background: list[int]) -> float:
    """Mean absolute difference to the empty-sensor background (~3 empty, 200-400 finger)."""
    return sum(abs(a - b) for a, b in zip(frame, background)) / len(frame)


def ridge_energy(frame: list[int], crop: int = 4) -> float:
    """Band-pass (3x3 minus 11x11 box mean) magnitude after removing per-row
    offsets: ~15 for an empty sensor, 69-99 with a finger."""
    w, h = WIDTH - 2 * crop, HEIGHT - 2 * crop
    rows = []
    for y in range(h):
        row = frame[(y + crop) * WIDTH + crop:(y + crop) * WIDTH + crop + w]
        mean = sum(row) / w
        rows.append([v - mean for v in row])
    integral = [[0.0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        acc = 0.0
        for x in range(w):
            acc += rows[y][x]
            integral[y + 1][x + 1] = integral[y][x + 1] + acc

    def box(x, y, r):
        x0, x1, y0, y1 = max(0, x - r), min(w, x + r + 1), max(0, y - r), min(h, y + r + 1)
        s = integral[y1][x1] - integral[y0][x1] - integral[y1][x0] + integral[y0][x0]
        return s / ((x1 - x0) * (y1 - y0))

    return sum(abs(box(x, y, 1) - box(x, y, 5)) for y in range(h) for x in range(w)) / (w * h)


def wait_for_finger(dev: Device, background: list[int], on: float = 50.0,
                    timeout: float = 30.0) -> list[int] | None:
    """Poll until a finger is on the sensor; return the strongest settled frame."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        frame = dev.capture_frame()
        score = frame_score(frame, background)
        if score > on:
            best, best_score, last = frame, score, score
            for _ in range(5):
                frame = dev.capture_frame()
                score = frame_score(frame, background)
                if score > best_score:
                    best, best_score = frame, score
                if score < last * 1.03:
                    break
                last = score
            return best
    return None


# ---- image output -----------------------------------------------------------

def to_8bit(frame: list[int], background: list[int], crop: int = 2) -> tuple[bytes, int, int]:
    """Background-subtracted, cropped, 1..99 percentile stretched 8 bit image
    (the same processing as the libfprint driver)."""
    w, h = WIDTH - 2 * crop, HEIGHT - 2 * crop
    delta = [background[(y + crop) * WIDTH + x + crop] - frame[(y + crop) * WIDTH + x + crop]
             for y in range(h) for x in range(w)]
    s = sorted(delta)
    lo, hi = s[len(s) // 100], s[len(s) - 1 - len(s) // 100]
    hi = max(hi, lo + 1)
    return bytes(min(255, max(0, (d - lo) * 255 // (hi - lo))) for d in delta), w, h


def write_png(path: str, gray: bytes, width: int, height: int, scale: int = 1):
    """Write an 8 bit grayscale PNG (optionally scaled up for viewing)."""
    import zlib
    rows = b""
    for y in range(height * scale):
        line = gray[(y // scale) * width:(y // scale + 1) * width]
        rows += b"\x00" + bytes(v for v in line for _ in range(scale))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width * scale, height * scale, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
