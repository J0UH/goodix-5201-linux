# Matching: why NBIS fails and SIGFM works

The sensor produces clean images, but each one covers only about 5.4 × 4.4 mm of
a finger. This document records the measurements behind the driver's choice of
matcher, thresholds and enrollment stages.

**Scope of the data.** Everything below comes from one person: 15 presses of the
enrolled finger (right index) and 6 presses of a different finger, recorded in one
session with `tools/record_dataset.py`, plus live tests through fprintd. This is
enough to choose between approaches, not a formal false-accept/false-reject
evaluation. Please report your own numbers (see the README).

## NBIS / bozorth3 (libfprint's default)

libfprint's default matcher extracts minutiae (ridge endings and bifurcations)
with NIST's NBIS and compares them with bozorth3. That needs about ten minutiae
in common between two prints. On this sensor:

| Image variant | Minutiae per image | Result |
|---|---|---|
| As is (1× or 2× scaled, any contrast normalisation) | 1–2.5 | all scores 0 |
| Padded with grey | ~14 | impostors score *higher* than genuine (up to 51 vs a median of 34): the minutiae are artefacts where ridges hit the image edge |
| Padded by mirroring | ~10 | genuine and impostor overlap (median 5–9 vs up to 16) |
| Grey padding, edge artefacts removed | 2–3 | all scores 0 |

Once the edge artefacts are removed, **only 2–3 real minutiae remain per image**.
No amount of image processing fixes that, so bozorth3 cannot work here. (The
first working driver used NBIS: enrollment succeeded, but verification scored 0
against all ten enrolled samples.)

## SIGFM

[SIGFM](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/530)
matches SIFT keypoints instead. It uses Lowe's ratio test, then counts pairs of
keypoint matches that agree on the same rotation and scale. SIFT finds 80–125
keypoints per image on this sensor.

Leave-one-out on the recorded presses (each press matched against the best of the
other presses of the enrolled finger; impostor = the other finger against all
presses of the enrolled finger):

| Matcher | Same finger (15) | Other finger (6) |
|---|---|---|
| NBIS/bozorth3 | 0 | 0 |
| Rotation-searched normalised cross-correlation | 0.57 – 0.99 | up to 0.72 (overlaps) |
| SIGFM, goodix-fp-dump variant | 104 – 291017, median 17289 | at most 3 |
| **SIGFM, libfprint MR !530 (used)** | **132 – 87734** | **at most 3** |

With the threshold at libfprint's default of **40**, every same-finger press is
accepted and every other-finger press is rejected. The weakest genuine score is
still more than three times the threshold, and the strongest impostor score is
an order of magnitude below it.

Upscaling the image or normalising contrast locally did not help SIGFM. The
driver sends the image at its native resolution.

### Live results through fprintd

| Test | Score (threshold 40) | Result |
|---|---|---|
| `fprintd-verify`, enrolled finger | 334 | match |
| `sudo`, enrolled finger | 4853 | match, about 1.5 s after the prompt |
| `fprintd-verify`, a finger that was not enrolled | 0 against all 15 samples | no match |

## Enrollment stages

Each press covers only part of the finger, so verification succeeds if the
probe overlaps at least one enrolled sample well enough. The driver asks for 15
presses (the same as MR !530 uses for the elan driver). fprintd adds one scan
before enrollment to check the finger isn't already enrolled, so enrolling takes
16 presses. Move the finger a little between presses to cover more of it.

## Finger detection

Frames are polled and compared to an empty-sensor background frame:

| Measure | Empty sensor | Finger | Thresholds |
|---|---|---|---|
| Mean absolute difference to the background | ~3 (5–10 right after lifting) | 200–400 | on > 50, off < 25 |
| Ridge energy (band-pass magnitude, see `gdx_ridge_energy()`) | 14.7 – 15.0 | 69 – 99 | empty < 25, finger > 40 |

The difference measure alone is only as good as the background. If a finger rests
on the sensor while the driver starts (for example when verification begins right
after enrollment, or a `sudo` prompt appears while touching the sensor), the
background contains the finger and detection inverts. The ridge-energy measure
works on a single frame, so the driver only accepts a background without ridge
structure and waits for the finger to be lifted otherwise.
