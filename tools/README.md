# Tools

Python tools used to reverse engineer the Goodix 27c6:5201 protocol. They talk
to the reader directly over USB, independently of libfprint. Use them to check a
reader, capture images for debugging, or study related Goodix sensors. For
logging in, use the libfprint driver.

Every command they send is volatile: nothing is written to the reader's flash.

## Setup

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# let your user access the reader (otherwise run the tools with sudo)
sudo install -m644 70-goodix-5201-dev.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

fprintd must not be using the reader at the same time (`sudo systemctl stop fprintd`).

## Tools

| Tool | What it does |
|---|---|
| `identify.py` | Firmware version, chip ID, configuration upload and one frame. No finger needed. Include its output in issues. |
| `capture.py [prefix]` | Waits for a finger and saves the image (`prefix.png`, a 4× `prefix-4x.png`, raw 12 bit `prefix.pgm`). |
| `record_dataset.py <dir>` | Records presses of two fingers for `eval_matchers.py`. |
| `eval_matchers.py <dir>` | Compares SIGFM and correlation matching on a recorded dataset (needs numpy and OpenCV). |
| `extract_config.py <milanFusb.dll>` | Finds the sensor configurations in the Goodix Windows driver. |
| `goodix5201.py` | The protocol implementation the others use. |
| `gea.py` | The Goodix GEA cipher (MIT, from goodix-fp-dump). |

Example:

```
$ ./identify.py
firmware version : GF3208_HT_APP_20041
chip id          : 0x2202a0
configuration    : accepted
frame            : OK, ridge energy 15.0 (empty)
```

Fingerprint images and datasets are biometric data. Keep images of fingers you
use to log in private.
