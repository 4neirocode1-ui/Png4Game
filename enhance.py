"""Sharpen cropped icons via unsharp mask.

Source priority:
  input/enhance/   (if exists and not empty)  →  output/opencv/  (fallback)

Writes: output/enhanced/<preset>/icon_NNN.png

Run `python enhance.py --help` for CLI options.
All Russian user-facing strings live in prompts.py (kept apart so
PyCharm's spell-checker has nothing to analyse here).
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

import prompts as P

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

OPENCV_DIR = Path("output/opencv")
ENHANCE_INPUT_DIR = Path("input/enhance")
OUTPUT_DIR = Path("output/enhanced")

# Add a new key here and it appears in the menu, in --mode choices,
# and gets its own output subfolder. Single source of truth.
PRESETS = {
    "soft": {"amount": 0.6, "radius": 1.0},
    "hard": {"amount": 1.2, "radius": 1.2},
}

REVIEW_KEYS = {
    ord("1"): {"orig"},
    ord("2"): {"soft"},
    ord("3"): {"hard"},
    ord("4"): {"soft", "hard"},
    ord("5"): {"orig", "soft", "hard"},
}


def unsharp(rgba, amount, radius):
    # Premultiplied alpha so transparent neighbours don't bleed grey into the icon edge.
    b, g, r, a = cv2.split(rgba)
    a_f = a.astype(np.float32) / 255.0
    pre = np.dstack([
        b.astype(np.float32) * a_f,
        g.astype(np.float32) * a_f,
        r.astype(np.float32) * a_f,
    ])
    blurred = cv2.GaussianBlur(pre, (0, 0), radius)
    sharp = pre * (1 + amount) - blurred * amount
    safe = np.where(a_f > 0.005, a_f, 1.0)
    bgr_final = np.clip(sharp / safe[..., None], 0, 255).astype(np.uint8)
    return np.dstack([bgr_final, a])


def laplacian_score(rgba):
    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def index_of(path):
    return path.stem.replace("icon_", "")


def resolve_source(opencv_dir=OPENCV_DIR):
    from utils import list_icon_files
    if ENHANCE_INPUT_DIR.exists():
        custom = list_icon_files(ENHANCE_INPUT_DIR)
        if custom:
            return ENHANCE_INPUT_DIR, custom
    opencv_dir = Path(opencv_dir)
    return opencv_dir, list_icon_files(opencv_dir)


def build_review_canvas(orig, soft, hard, name, scale=4):
    panels = []
    for img, label in [(orig, "orig"), (soft, "soft"), (hard, "hard")]:
        score = laplacian_score(img)
        bg_color = np.array([60, 60, 60], dtype=np.float32)
        bgr = img[:, :, :3].astype(np.float32)
        a = img[:, :, 3].astype(np.float32) / 255.0
        composite = (bgr * a[..., None] + bg_color * (1 - a[..., None])).astype(np.uint8)
        big = cv2.resize(composite, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_NEAREST)
        h, w = big.shape[:2]
        panel = np.full((h + 50, w, 3), 30, dtype=np.uint8)
        panel[:h] = big
        cv2.putText(panel, f"{label}  L={score:.0f}", (8, h + 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1, cv2.LINE_AA)
        panels.append(panel)
    canvas = np.hstack(panels)
    title_h = 32
    titled = np.full((canvas.shape[0] + title_h, canvas.shape[1], 3), 30, dtype=np.uint8)
    titled[title_h:] = canvas
    cv2.putText(titled, f"icon_{name}", (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 1, cv2.LINE_AA)
    return titled


def review_one(orig, soft, hard, name):
    canvas = build_review_canvas(orig, soft, hard, name)
    win = f"review icon_{name}"
    print(P.REVIEW_PROMPT.format(name=name))
    while True:
        cv2.imshow(win, canvas)
        key = cv2.waitKey(0) & 0xFF
        if key in REVIEW_KEYS:
            cv2.destroyWindow(win)
            return set(REVIEW_KEYS[key])
        if key == ord(" "):
            cv2.destroyWindow(win)
            return set()
        if key in (ord("q"), ord("Q"), 27):
            cv2.destroyWindow(win)
            return None
        print(P.UNKNOWN_KEY.format(key=key))


def save_variant(rgba, name, preset, output_dir=OUTPUT_DIR):
    target_dir = Path(output_dir) / preset
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"icon_{name}.png"
    cv2.imwrite(str(path), rgba)
    return path


def mode_choices():
    return list(PRESETS.keys()) + ["all", "review"]


def prompt_mode():
    options = mode_choices()
    print(P.MENU_TITLE)
    for i, opt in enumerate(options, 1):
        print(P.MENU_ITEM.format(num=i, name=opt))
    while True:
        choice = input(P.MENU_PROMPT).strip().lower()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
        elif choice in options:
            return choice
        print(P.MENU_INVALID)


def process(mode, opencv_dir=OPENCV_DIR, output_dir=OUTPUT_DIR):
    src_dir, paths = resolve_source(opencv_dir)

    if not paths:
        print(P.NO_ICONS.format(enhance=ENHANCE_INPUT_DIR, opencv=opencv_dir))
        return

    print(P.HEADER.format(src=src_dir, count=len(paths), dst=output_dir, mode=mode))

    saved = 0
    skipped = 0

    for path in paths:
        name = index_of(path)
        orig = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if orig is None or orig.ndim != 3 or orig.shape[2] != 4:
            print(P.NOT_RGBA.format(name=path.name))
            continue

        if mode == "review":
            variants = {
                "orig": orig,
                "soft": unsharp(orig, **PRESETS["soft"]),
                "hard": unsharp(orig, **PRESETS["hard"]),
            }
            choice = review_one(variants["orig"], variants["soft"], variants["hard"], name)
            if choice is None:
                print(P.REVIEW_QUIT)
                break
            if not choice:
                skipped += 1
                print(P.SKIPPED.format(name=name))
                continue
            for preset in sorted(choice):
                save_variant(variants[preset], name, preset, output_dir)
                saved += 1
                print(P.SAVED.format(name=name, preset=preset))
        elif mode == "all":
            for preset, params in PRESETS.items():
                save_variant(unsharp(orig, **params), name, preset, output_dir)
                saved += 1
            print(P.SAVED_ALL.format(name=name, presets=", ".join(PRESETS.keys())))
        else:
            save_variant(unsharp(orig, **PRESETS[mode]), name, mode, output_dir)
            saved += 1
            print(P.SAVED.format(name=name, preset=mode))

    cv2.destroyAllWindows()
    print(P.DONE.format(saved=saved, skipped=skipped))


def main():
    parser = argparse.ArgumentParser(
        description=P.CLI_DESC,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=P.CLI_EPILOG,
    )
    parser.add_argument("--mode", choices=mode_choices(),
                        default=None, help=P.CLI_MODE_HELP)
    args = parser.parse_args()
    mode = args.mode if args.mode else prompt_mode()
    process(mode)


if __name__ == "__main__":
    main()
