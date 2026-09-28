# Upstream status

The goal is for this driver to become part of
[libfprint](https://gitlab.freedesktop.org/libfprint/libfprint), so that
distributions ship it and this repository is no longer needed.

**Status:** not submitted yet. Submitting needs a gitlab.freedesktop.org account
with fork permission. Everything needed, including feedback for the MR !530
authors, is collected in
[issue #1](https://github.com/J0UH/goodix-5201-linux/issues/1): help is welcome.

## Dependencies

The driver needs SIGFM (see [MATCHING.md](MATCHING.md)), which is not in libfprint
yet. It is proposed in
[libfprint MR !530](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/530)
by Yassine Oudjana, based on the SIGFM work of Matthieu Charette, Natasha
England-Elbro and Timur Mangliev. The driver uses the API of that merge request
(`img_class->algorithm = FPI_DEVICE_ALGO_SIGFM`, `score_threshold`), so it can
only be merged together with or after it.

## What the `libfprint` branch contains

The [`libfprint`](https://github.com/J0UH/goodix-5201-linux/tree/libfprint) branch of this repository is:

1. upstream libfprint `6f9479c3` ("synaptics: Add new PID 0x10b"),
2. merged with MR !530 at `bed05d29`, with the conflicts resolved (upstream
   removed the image-device verify path the MR edits, turned print
   deserialisation into a `switch` and renamed `template` to `print_template`;
   the SIGFM deserialiser also got a type check so a malformed print file is
   rejected cleanly),
3. `sigfm: Accept OpenCV 5 and make doctest optional`: current distributions
   ship OpenCV 5 (`opencv5.pc`), and doctest is only needed for the SIGFM
   unit tests,
4. `secugen: Use score_threshold`: the secugen driver was added upstream after
   MR !530 renamed `bz3_threshold`,
5. `goodix5201: Add driver for Goodix 27c6:5201`,
6. `data: Update autosuspend hwdb for goodix5201`,
7. `tests: Add goodix5201 capture test` (a umockdev replay of one capture,
   recorded with the side of a finger).

Commits 3 and 4 are fixes for MR !530 itself, not part of the driver. Commits
5–7 are what the driver merge request contains. Commits 3–6 are also in
[`patches/`](../patches); the test recording is binary and only in the branch.

## Test results

`meson test` on the branch: 130 tests pass. `elan` and `elan-cobo` fail, and they
fail the same way on MR !530 by itself: the MR switches the elan driver to
SIGFM, but its reference capture images were not updated. It is a problem in
MR !530, not in this driver.

## Upstream's requirements for new drivers

libfprint's `HACKING.md` asks for a protocol specification (see
[PROTOCOL.md](PROTOCOL.md)) and, ideally, several devices for testing. Only one
device (in one laptop) has been tested so far, so reports from other owners are
very welcome.
