"""Goodix GEA stream cipher.

The keystream generator below is taken verbatim from goodix-fp-dump
(https://github.com/goodix-fp-linux-dev/goodix-fp-dump, wrapless.py,
commit cc43bb3b), only the key argument was changed to accept an int.
It is distributed under the following license:

    MIT License

    Copyright (c) 2022 Goodix Fingerprint Linux Development

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""
import struct


def gea_decrypt(key: int, encrypted_data: bytes) -> bytes:
    """XOR each little-endian 16 bit word with a keystream generated from key."""
    key &= 0xFFFFFFFF

    decrypted_data = b""
    for data_idx in range(0, len(encrypted_data), 2):
        uVar3 = (key >> 1 ^ key) & 0xFFFFFFFF
        uVar2 = (((((((
            (key >> 0xF & 0x2000 | key & 0x1000000) >> 1 | key & 0x20000) >> 2
                      | key & 0x1000) >> 3 | (key >> 7 ^ key) & 0x80000) >> 1 |
                    (key >> 0xF ^ key) & 0x4000) >> 2 | key & 0x2000) >> 2
                  | uVar3 & 0x40 | key & 0x20) >> 1 |
                 (key >> 9 ^ key << 8) & 0x800 | (key >> 0x14 ^ key * 2) & 4 |
                 (key * 8 ^ key >> 0x10) & 0x4000 |
                 (key >> 2 ^ key >> 0x10) & 0x80 |
                 (key << 6 ^ key >> 7) & 0x100 | (key & 0x100) << 7)
        uVar2 = uVar2 & 0xFFFFFFFF
        uVar1 = key & 0xFFFF
        key = ((key ^
                (uVar3 >> 0x14 ^ key) >> 10) << 0x1F | key >> 1) & 0xFFFFFFFF

        input_element = struct.unpack("<H",
                                      encrypted_data[data_idx:data_idx + 2])[0]
        stream_val = (
            (uVar2 >> 8) & 0xFFFF) + (uVar2 & 0xFF | uVar1 & 1) * 0x100
        decrypted_data += struct.pack("<H", input_element ^ stream_val)

    assert len(encrypted_data) == len(decrypted_data)
    return decrypted_data
