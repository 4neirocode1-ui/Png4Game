"""
Анализатор итогового результата нарезки. НИЧЕГО НЕ МЕНЯЕТ — только смотрит и
печатает отчёт о проблемных местах, чтобы на его основе сделать авто-проход.

Что ищет в каждой иконке (output/opencv/icon_*.png):
  • Бахрома по ВНЕШНЕМУ краю — светлые пиксели на границе с фоном (на тёмном UI «светятся»).
  • Бахрома по ВНУТРЕННИМ краям — то же вокруг полостей (лук, петля, кольцо).
  • Чисто-белые пятна — крупные непрозрачные области у самого белого (возможна
    незакрытая «дыра-окно» или остаток фоновой заливки; мелкие — обычно блик стали).
  • Полости — число внутренних прозрачных областей (справочно).

Запуск: пункт меню [4] или `python analyze.py [папка]`.
"""
import sys
import json
from pathlib import Path

import cv2
import numpy as np

from utils import list_icon_files, imread_unicode

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

DEFAULT_DIR = "output/opencv"

# --- Пороги детекции ---
FRINGE_LIGHT = 210   # пиксель «светлый» (min(B,G,R) выше) — кандидат в бахрому
WHITE_PURE = 245     # пиксель «чисто-белый»
HOLE_MIN = 10        # внутренняя дыра меньше — спекл, не считаем полостью

# --- Пороги «поднять замечание» ---
# Внешний край НЕ флагуем: он чинится авто-срезом контура [2]. Число остаётся
# в отчёте (столбец + JSON) как топливо для авто-прохода, но тревоги не поднимает.
FLAG_INNER = 15      # светлых пикселей на внутреннем крае → чистить вручную (инструмента нет)
FLAG_WHITE = 25      # крупнейшее чисто-белое пятно → ПРОВЕРИТЬ глазами (код не отличит косяк от блика)


def _masks(rgba):
    """Раскладывает картинку на: объект, внешний фон, внутренние полости."""
    a = rgba[:, :, 3]
    h, w = a.shape
    fg = a > 0
    transp = (a == 0).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(transp, connectivity=4)
    ext = np.zeros((h, w), np.uint8)
    holes = np.zeros((h, w), np.uint8)
    hole_areas = []
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        touches = (x == 0 or y == 0 or x + bw == w or y + bh == h)
        if touches:
            ext[labels == i] = 1            # фон, связанный с краем картинки
        elif area >= HOLE_MIN:
            holes[labels == i] = 1          # замкнутая полость внутри объекта
            hole_areas.append(int(area))
    return fg, ext, holes, sorted(hole_areas, reverse=True)


def analyze_icon(rgba):
    fg, ext, holes, hole_areas = _masks(rgba)
    minc = rgba[:, :, :3].min(axis=2)
    k = np.ones((3, 3), np.uint8)

    # Край = пиксели объекта, примыкающие к фону / к полости.
    near_ext = cv2.dilate(ext, k).astype(bool) & fg
    near_hole = (cv2.dilate(holes, k).astype(bool) & fg) if holes.any() \
        else np.zeros_like(fg)

    light = minc > FRINGE_LIGHT
    outer_fringe = int((near_ext & light).sum())
    inner_fringe = int((near_hole & light).sum())

    # Чисто-белые непрозрачные пятна (крупнейшее — самое подозрительное).
    white = (fg & (minc > WHITE_PURE)).astype(np.uint8)
    wn, _wl, ws, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    white_max = max((int(ws[i][4]) for i in range(1, wn)), default=0)

    return {
        "outer_fringe": outer_fringe,
        "inner_fringe": inner_fringe,
        "white_total": int(white.sum()),
        "white_max_cluster": white_max,
        "cavities": hole_areas,
    }


def flags(m):
    """Только то, что НЕ чинится авто-срезом: внутренний край (вручную) и
    белые пятна (проверить глазами). Внешний край сюда не попадает."""
    f = []
    if m["inner_fringe"] >= FLAG_INNER:
        f.append("внутр.край (вручную)")
    if m["white_max_cluster"] >= FLAG_WHITE:
        f.append("белое пятно (проверь)")
    return f


def main(src=None):
    if src is None:
        src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_DIR)
    src = Path(src)
    files = [str(p) for p in list_icon_files(src)]
    if not files:
        print(f"Нет иконок в {src} — сначала нарежь лист [1].")
        return

    print(f"Анализ {len(files)} иконок в {src}\n")
    print(f"{'иконка':<11}{'край-снар(авто)':>16}{'край-внутр':>12}"
          f"{'белое':>7}{'полости':>9}  замечания")
    print("-" * 72)

    report = []
    flagged = 0
    for f in files:
        img = imread_unicode(f, cv2.IMREAD_UNCHANGED)
        if img is None or img.ndim != 3 or img.shape[2] != 4:
            continue
        m = analyze_icon(img)
        fl = flags(m)
        if fl:
            flagged += 1
        name = Path(f).stem
        mark = "  ⚠ " + ", ".join(fl) if fl else ""
        print(f"{name:<11}{m['outer_fringe']:>16}{m['inner_fringe']:>12}"
              f"{m['white_max_cluster']:>7}{len(m['cavities']):>9}{mark}")
        report.append({"icon": name, **m, "flags": fl})

    out = src.parent / "analyze_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("-" * 72)
    print(f"Итог: {flagged} иконок с замечаниями из {len(files)}.")
    print(f"Машиночитаемый отчёт: {out}")
    print("\nЧто значат столбцы:")
    print("  • край-снар(авто) — бахрома внешнего контура. Чинится АВТО срезом [2], не тревога.")
    print("  • край-внутр      — бахрома вокруг полостей. Инструмента пока нет → чистить вручную.")
    print("  • белое           — крупнейшее белое пятно. Код НЕ отличит косяк от блика → смотри глазами.")
    print("  • полости         — число внутренних проёмов (справочно).")


if __name__ == "__main__":
    main()
