"""
Нарезка листа на отдельные иконки 256×256. Сам определяет тип листа:

  • Лист с ПРОЗРАЧНЫМ фоном (RGBA, фон уже убран в редакторе) → режем по альфе.
    Твоя альфа уважается как есть: фон и почищенные внутренние области (полость
    лука и т.п.) остаются прозрачными, белого не появляется.

  • Сырой лист с НЕПРОЗРАЧНЫМ белым фоном → убираем белый заливкой от краёв и
    режем по силуэту (старый путь для листов прямо из Nano Banana).

Шаги (оба пути): детект иконок → чистка (чужие компоненты/подписи, мелкие дыры
от антиалиасинга) → центрирование на квадрате TARGET_SIZE.

punch_internal_white ОТКЛЮЧЁН (2026-06-11) — сверлил дыры в бликах стали;
замкнутые окна (петля арбалета, дырки колец) маскируются вручную. См. architecture.md.
"""
import time
import cv2
import numpy as np

from utils import (
    INPUT_FILE, TARGET_SIZE, PADDING, OUTPUT_FORMAT,
    load_image, build_global_alpha, find_icons, find_icons_by_alpha,
    keep_main_component, fill_small_holes,
    fit_to_canvas, save_icons, imread_unicode,
)

OUTPUT_DIR = "output/opencv"

# Доля полностью прозрачных пикселей, выше которой считаем фон убранным в альфу.
ALPHA_BG_MIN_FRACTION = 0.02


def _has_transparent_bg(src) -> bool:
    """Фон убран в прозрачность? — у листа есть альфа и заметная её доля == 0."""
    if src is None or src.ndim != 3 or src.shape[2] != 4:
        return False
    return float((src[:, :, 3] == 0).mean()) > ALPHA_BG_MIN_FRACTION


def _finalize_icon(roi_bgr, roi_a, target_size=TARGET_SIZE, prune=True):
    """Общий хвост: чистка альфы и центрирование на холсте target_size.

    prune=True (иконка из одного куска) — убираем приклеившийся мусор/подпись
    через keep_main_component. prune=False (склеенная многокусковая иконка:
    снежинка, оглушение) — НЕ трогаем: keep_main_component удалил бы как мусор
    отлетевшие лучи/звёзды, которые мы только что собрали в группу.
    """
    if prune:
        roi_a = keep_main_component(roi_a)
    roi_a = fill_small_holes(roi_a)
    b, g, r = cv2.split(roi_bgr)
    rgba = cv2.merge([b, g, r, roi_a])
    return fit_to_canvas(rgba, target_size, PADDING)


def _crop_group(roi_a, roi_labels, ids):
    """Оставляет в ROI только компоненты группы, чужие куски зануляет."""
    keep = np.isin(roi_labels, list(ids))
    roi_a = roi_a.copy()
    roi_a[~keep] = 0
    return roi_a


def _slice_by_alpha(src, target_size=TARGET_SIZE):
    """Путь для чистого RGBA: режем по исходной альфе, RGB не трогаем."""
    bgr = src[:, :, :3]
    alpha = src[:, :, 3]
    groups, labels = find_icons_by_alpha(alpha)
    print(f"🔍 Лист с прозрачным фоном — режем по альфе. Иконок: {len(groups)}")

    icons = []
    total = len(groups)
    for i, (x, y, w, h, ids) in enumerate(groups):
        roi_a = _crop_group(alpha[y:y + h, x:x + w], labels[y:y + h, x:x + w], ids)
        icons.append(_finalize_icon(bgr[y:y + h, x:x + w], roi_a, target_size,
                                    prune=len(ids) == 1))
        print(f"  [{i + 1:>2}/{total}] {w:>3}×{h:<3}px  pos=({x},{y})"
              f"{'  (склейка ' + str(len(ids)) + ')' if len(ids) > 1 else ''}")
    return icons


def _slice_by_color(input_file=INPUT_FILE, target_size=TARGET_SIZE):
    """Путь для сырого листа с белым фоном: заливка фона + детект по силуэту."""
    img = load_image(input_file)
    bgr = img[:, :, :3]

    alpha_full = build_global_alpha(img)
    groups, labels = find_icons(img)
    print(f"🔍 Лист с белым фоном — убираем фон и режем по силуэту. Иконок: {len(groups)}")

    icons = []
    total = len(groups)
    for i, (x, y, w, h, ids) in enumerate(groups):
        roi_a = _crop_group(alpha_full[y:y + h, x:x + w], labels[y:y + h, x:x + w], ids)
        icons.append(_finalize_icon(bgr[y:y + h, x:x + w], roi_a, target_size,
                                    prune=len(ids) == 1))
        print(f"  [{i + 1:>2}/{total}] {w:>3}×{h:<3}px  pos=({x},{y})"
              f"{'  (склейка ' + str(len(ids)) + ')' if len(ids) > 1 else ''}")
    return icons


def process(input_file=INPUT_FILE, output_dir=OUTPUT_DIR,
            target_size=TARGET_SIZE, fmt=OUTPUT_FORMAT):
    raw = imread_unicode(input_file, cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Файл не найден: '{input_file}'")

    t_start = time.time()
    icons = (_slice_by_alpha(raw, target_size) if _has_transparent_bg(raw)
             else _slice_by_color(input_file, target_size))
    save_icons(icons, str(output_dir), fmt)
    print(f"⏱  Всего: {time.time() - t_start:.2f}с")


if __name__ == "__main__":
    process()
