# goodix-5201-linux

Linux support for the **Goodix `27c6:5201` fingerprint reader**, found in the
**ASUS ZenBook S UX391UA**. It is a [libfprint](https://fprint.freedesktop.org/)
driver, so the reader works with fprintd like any supported reader: enroll a
finger, then use it for `sudo`, polkit prompts, the lock screen and desktop
logins.

| | |
|---|---|
| Status | Working: enroll, verify and identify through fprintd |
| Tested on | ASUS ZenBook S UX391UA, Arch Linux / Omarchy, fprintd 1.94 |
| Upstream | Not in libfprint yet, see [docs/UPSTREAM.md](docs/UPSTREAM.md) |

Before this project, this reader had no Linux driver: Goodix never released one,
and libfprint listed it as unsupported.

## Do I have this reader?

```sh
lsusb | grep 27c6:5201
```

```
Bus 001 Device 004: ID 27c6:5201 Shenzhen Goodix Technology Co.,Ltd. Fingerprint Reader
```

If `lsusb` shows a different ID after `27c6:`, it is a different Goodix reader
and this driver will not pick it up. See
[libfprint's supported devices](https://fprint.freedesktop.org/supported-devices.html)
and [related devices](docs/PROTOCOL.md#9-related-devices).

Laptops known to have this reader:
- ASUS ZenBook S UX391UA

If you have it in another laptop, please open an issue so it can be added.

## Install

### Arch Linux, Omarchy

Build and install the package from this repository, together with fprintd:

```sh
git clone https://github.com/J0UH/goodix-5201-linux.git
cd goodix-5201-linux/packaging/arch
makepkg -si
sudo pacman -S --needed fprintd
```

It replaces the `libfprint` (or `libfprint-git`) package. An AUR package
(`libfprint-goodix-5201`) will follow once AUR account registration reopens.

**Omarchy:** then run the fingerprint setup from the Omarchy menu (*Setup →
Security → Fingerprint*) or with `omarchy-setup-security-fingerprint`. It enrolls
a finger and enables fingerprint login for `sudo`, polkit and the lock screen.
The package also counts as `libfprint-git`, so the setup does not replace it.

### Other distributions

Build libfprint from the [`libfprint`](https://github.com/J0UH/goodix-5201-linux/tree/libfprint)
branch. You need meson, ninja, a C/C++ compiler, and the development files for
glib2, gusb, gudev, pixman, openssl and OpenCV (4 or 5), plus
gobject-introspection for the typelib.

```sh
git clone -b libfprint https://github.com/J0UH/goodix-5201-linux.git libfprint
cd libfprint
meson setup build --prefix=/usr -Ddoc=false -Dgtk-examples=false
ninja -C build
sudo ninja -C build install
sudo systemctl restart fprintd
```

This overwrites your distribution's libfprint, and a system update of that
package will overwrite it back. Undo it with `sudo ninja -C build uninstall`
and reinstalling your distribution's libfprint package.

## Using it

**Enroll a finger.** This asks for the right index finger unless you pick another:

```sh
fprintd-enroll                          # right index finger
fprintd-enroll -f left-index-finger     # or any other finger
```

The reader is small (about 5 × 4 mm), so enrolling takes **16 presses**: one
check that the finger is not enrolled yet, then 15 samples. Press, hold about a
second, lift, and move the finger a little each time so more of it is covered.
A message like `enroll-retry-scan` or `enroll-swipe-too-short` means that press
was unusable, usually because the finger was lifted too fast. Just press again;
it does not count against you.

**Check it:**

```sh
fprintd-verify          # expect verify-match with the enrolled finger
fprintd-list "$USER"    # list enrolled fingers
fprintd-delete "$USER"  # delete them all
```

**Log in with it.** fprintd only checks fingers; PAM decides where fingerprints
are accepted. Omarchy's setup configures this for you. Elsewhere, see
[the Arch Wiki](https://wiki.archlinux.org/title/Fprint#Configuration)
(Ubuntu: `sudo pam-auth-update`, Fedora: `sudo authselect enable-feature with-fingerprint`).
Your password keeps working in every place.

## FAQ

**Why does the setup always use my right index finger?**
That is fprintd's default. Enroll more fingers with `fprintd-enroll -f <finger>`
(`left-index-finger`, `right-thumb`, …). A second finger is a good fallback.

**Verification sometimes fails.**
Enroll again with more varied positions, and see [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

**Will this break the reader on Windows?**
No. The driver only sends commands that change the reader's working memory.
Nothing is written to its flash, so the Windows driver keeps working.

**Why does it need OpenCV?**
libfprint's standard matcher needs more fingerprint detail than a 5 × 4 mm
sensor can see. This driver uses SIGFM, which matches SIFT keypoints with
OpenCV instead. See [MATCHING.md](docs/MATCHING.md).

**Does it work with the lid closed?**
With Omarchy, fingerprint login is skipped while the lid is closed, because the
reader is on the keyboard deck.

**Is it secure?**
Fingerprint login is a convenience, not strong security, and this reader is at
the weak end:
- It does *match-on-host*: the reader sends images to the computer, and
  libfprint compares them. The images are only obfuscated with a fixed key, not
  encrypted. Someone with root access or physical access to the USB bus could
  record or inject fingerprint images. This applies to most older readers
  supported by libfprint.
- Enrolled prints are stored in `/var/lib/fprint`, readable only by root.
- Matching accuracy was measured on one person (see
  [MATCHING.md](docs/MATCHING.md)): other fingers scored 0–3 against a pass mark
  of 40.

Keep a strong password. It always works as a fallback.

## How it works

The reader is a Goodix match-on-host sensor (108 × 88 pixels, 12 bit) behind a
USB bridge chip. It pretends to be a USB modem, so Linux binds `cdc_acm` to it,
which the driver detaches. The driver talks Goodix's "wrapless" message protocol
over two USB bulk endpoints. On each use it uploads the sensor configuration
(extracted from the Windows driver), takes an empty-sensor reference frame, and
polls frames until a finger appears. The frames are de-obfuscated (Goodix "GEA"
cipher, fixed key `0x12345678`), checked with a CRC, turned into an 8-bit image
and matched with SIGFM.

| Document | Content |
|---|---|
| [PROTOCOL.md](docs/PROTOCOL.md) | The full protocol specification |
| [REVERSE-ENGINEERING.md](docs/REVERSE-ENGINEERING.md) | How it was worked out, and how to repeat it for other Goodix sensors |
| [MATCHING.md](docs/MATCHING.md) | Why NBIS fails and SIGFM works, with measurements |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Debug logging and common problems |
| [UPSTREAM.md](docs/UPSTREAM.md) | Upstream status and what the libfprint branch contains |

## Repository layout

| Path | Content |
|---|---|
| [`libfprint` branch](https://github.com/J0UH/goodix-5201-linux/tree/libfprint) | Buildable libfprint: upstream + SIGFM (MR !530) + the driver |
| [`patches/`](patches) | The driver commits as patches, for review |
| [`packaging/arch/`](packaging/arch) | Arch Linux package (same as the AUR package) |
| [`tools/`](tools) | Python reference implementation and research tools |
| [`docs/`](docs) | Documentation |

## Help wanted

- **Other laptops with this reader.** Please report whether it works (open an
  issue with the laptop model and the output of
  [`tools/identify.py`](tools/README.md)).
- **Related Goodix readers** (`27c6:5301` and others): the
  [reverse-engineering notes](docs/REVERSE-ENGINEERING.md) explain how to check
  whether they speak the same protocol.
- **Upstream review** of the driver once it is submitted to libfprint.

Please never attach images of a finger you use to log in.

## Credits

- [goodix-fp-dump](https://github.com/goodix-fp-linux-dev/goodix-fp-dump) by the
  Goodix Fingerprint Linux Development group: the "wrapless" message format, the
  GEA cipher implementation and the configuration layout came from their work
  on related Goodix sensors.
- SIGFM by Matthieu Charette, Natasha England-Elbro and Timur Mangliev, and its
  libfprint integration ([MR !530](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/530))
  by Yassine Oudjana.
- The libfprint and fprintd developers.
- The driver was written by Jodi U. H.

## License

The driver and libfprint changes are licensed under the
[LGPL-2.1-or-later](LICENSE), like libfprint. The tools are LGPL-2.1-or-later as
well, except [`tools/gea.py`](tools/gea.py), which is MIT-licensed code from
goodix-fp-dump. The sensor configuration was extracted from the vendor's Windows
driver for interoperability.
