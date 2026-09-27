#!/usr/bin/env python3
"""Evaluate candidate matchers on a dataset recorded with record_dataset.py.

A_* = enrolled finger, B_* = other finger. Genuine score: each A against the
best of the other A's (leave-one-out, like verify against an enrolled template
set). Impostor score: each B against the best of all A's.

    eval_matchers.py <dataset-dir>

Requires numpy and opencv-python-headless.
"""
import glob
import itertools
import math
import os
import sys

import cv2
import numpy as np

W, H, CROP = 108, 88, 2
DS = None  # set from the command line


def load(name):
    return np.fromfile(os.path.join(DS, name), dtype="<u2").reshape(H, W).astype(np.float64)


def preprocess(frame, bg, scale=1, local=0):
    d = (bg - frame)[CROP:H - CROP, CROP:W - CROP]
    if local:
        k = 2 * local + 1
        mean = cv2.blur(d, (k, k))
        sd = np.sqrt(np.maximum(cv2.blur(d * d, (k, k)) - mean * mean, 1e-6))
        img = np.clip(128 + (d - mean) / sd * 48, 0, 255)
    else:
        lo, hi = np.percentile(d, [1, 99])
        img = np.clip((d - lo) * 255 / max(hi - lo, 1), 0, 255)
    img = img.astype(np.uint8)
    if scale > 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
    return img


# ---- SIGFM (port of goodix-fp-linux-dev/libfprint sigfm.cpp) ------------------

def sigfm_extract(img):
    kp, desc = cv2.SIFT_create().detectAndCompute(img, None)
    return [k.pt for k in kp], desc


def sigfm_score(frame, enrolled, ratio=0.75, length_match=0.05, angle_match=0.05, min_match=5):
    kp1, d1 = frame
    kp2, d2 = enrolled
    if d1 is None or d2 is None or len(kp1) < 2 or len(kp2) < 2:
        return 0
    knn = cv2.BFMatcher().knnMatch(d1, d2, k=2)
    matches = set()
    nb = 0
    for pair in knn:
        if len(pair) < 2:
            continue
        m1, m2 = pair
        if m1.distance < ratio * m2.distance:
            p1 = tuple(int(v) for v in kp1[m1.queryIdx])
            p2 = tuple(int(v) for v in kp2[m1.trainIdx])
            matches.add((p1, p2))
            nb += 1
    if nb < min_match:
        return 0
    matches = list(matches)
    angles = []
    for (a1, a2), (b1, b2) in itertools.combinations(matches, 2):
        v1 = (a1[0] - b1[0], a1[1] - b1[1])
        v2 = (a2[0] - b2[0], a2[1] - b2[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 == 0 or l2 == 0:
            continue
        if 1 - min(l1, l2) / max(l1, l2) <= length_match:
            prod = l1 * l2
            c = math.pi / 2 + math.asin(max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / prod)))
            s = math.acos(max(-1, min(1, (v1[0] * v2[1] - v1[1] * v2[0]) / prod)))
            angles.append((c, s))
    if len(angles) < min_match:
        return 0
    count = 0
    for (c1, s1), (c2, s2) in itertools.combinations(angles, 2):
        if max(s1, s2) > 0 and max(c1, c2) > 0 and \
           1 - min(s1, s2) / max(s1, s2) <= angle_match and \
           1 - min(c1, c2) / max(c1, c2) <= angle_match:
            count += 1
    return count


# ---- Rotation-searched normalized cross-correlation ---------------------------

def ncc_features(img):
    return img.astype(np.float32)


def ncc_score(probe, tmpl, angles=range(-24, 25, 4), min_overlap=0.45):
    h, w = tmpl.shape
    best = 0.0
    for a in angles:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        rot = cv2.warpAffine(probe, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=-1)
        # central patch of the rotated probe, correlated over the template
        ph, pw = int(h * math.sqrt(min_overlap)), int(w * math.sqrt(min_overlap))
        y0, x0 = (h - ph) // 2, (w - pw) // 2
        patch = rot[y0:y0 + ph, x0:x0 + pw]
        if (patch < 0).any():
            continue
        r = cv2.matchTemplate(tmpl, patch, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(r.max()))
    return best


def evaluate(name, feats, score_fn, is_a):
    n = len(feats)
    gen, imp = [], []
    for i in range(n):
        best = max(score_fn(feats[i], feats[j]) for j in range(n) if j != i and is_a[j])
        (gen if is_a[i] else imp).append(best)
    gen.sort(reverse=True)
    imp.sort(reverse=True)
    imax = max(imp)
    acc = sum(g > imax for g in gen)
    fmt = (lambda v: f"{v:.2f}") if isinstance(gen[0], float) else str
    print(f"{name:42} genuine>max(impostor): {acc:2d}/{len(gen)}   "
          f"gen median {fmt(gen[len(gen) // 2])}  imp max {fmt(imax)}")
    print(f"{'':42} gen {[fmt(g) for g in gen]}")
    print(f"{'':42} imp {[fmt(g) for g in imp]}")
    sys.stdout.flush()


def main():
    global DS
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    DS = sys.argv[1]
    bg = load("background.raw")
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(DS, "[AB]_*.raw")))
    frames = [load(n) for n in names]
    is_a = [n.startswith("A") for n in names]
    print(f"{sum(is_a)} genuine (A) + {len(is_a) - sum(is_a)} impostor (B) presses\n")

    for scale in (1, 2, 3):
        for local in (0, 6):
            imgs = [preprocess(f, bg, scale, local) for f in frames]
            feats = [sigfm_extract(im) for im in imgs]
            nkp = np.mean([len(f[0]) for f in feats])
            evaluate(f"SIGFM scale={scale} local={local} (kp {nkp:.0f})", feats, sigfm_score, is_a)

    for local in (0, 6):
        imgs = [preprocess(f, bg, 1, local) for f in frames]
        evaluate(f"NCC rot±24 scale=1 local={local}", [ncc_features(i) for i in imgs], ncc_score, is_a)


if __name__ == "__main__":
    main()
