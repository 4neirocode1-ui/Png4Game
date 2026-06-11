"""
ПОЛНЫЙ АВТОМАТ: берёт СЫРОЙ лист с белым фоном (и даже с подписями), сам
убирает фон в прозрачность, отбрасывает подписи, нарезает иконки и приводит
к единому размеру.

Лист кладётся в input/1.png прямо из браузера / Nano Banana — фотошоп-подготовка
больше не нужна.

Шаги:
  1. build_global_alpha — сплошной белый фон → прозрачность (с мягким краем).
  2. find_icons       — детект силуэтов; подписи отсекаются по форме (aspect).
  3. на каждую иконку — чистка: чужие компоненты, прилипшие подписи,
                        внутренние белёсые просветы (лук/кольцо), мелкие дыры.
  4. fit_to_canvas    — центрирование на квадрате TARGET_SIZE.
"""
import time
import cv2

from utils import (
    INPUT_FILE, TARGET_SIZE, PADDING,
    load_image, build_global_alpha, find_icons,
    keep_main_component, punch_internal_white, fill_small_holes,
    fit_to_canvas, save_icons,
)

OUTPUT_DIR = "output/opencv"


def process():
    img = load_image(INPUT_FILE)
    bgr = img[:, :, :3]

    t_start = time.time()

    # 1. Глобальная альфа: убираем сплошной белый фон.
    alpha_full = build_global_alpha(img)

    # 2. Детект иконок по тёмному силуэту; подписи отсекаются по форме.
    bboxes, labels = find_icons(img)
    print(f"🔍 Найдено иконок: {len(bboxes)}")

    icons = []
    total = len(bboxes)
    for i, (x, y, w, h, label_id) in enumerate(bboxes):
        roi_bgr = bgr[y:y + h, x:x + w]
        roi_a = alpha_full[y:y + h, x:x + w].copy()

        # Зануляем чужие компоненты, попавшие в bbox этой иконки.
        roi_labels = labels[y:y + h, x:x + w]
        roi_a[(roi_labels != 0) & (roi_labels != label_id)] = 0

        # Чистка: прилипшие подписи/мусор → внутренние белёсые просветы
        # (полость лука, дырка кольца) → мелкие дыры от антиалиасинга.
        roi_a = keep_main_component(roi_a)
        roi_a = punch_internal_white(roi_bgr, roi_a)
        roi_a = fill_small_holes(roi_a)

        b, g, r = cv2.split(roi_bgr)
        rgba = cv2.merge([b, g, r, roi_a])
        icons.append(fit_to_canvas(rgba, TARGET_SIZE, PADDING))
        print(f"  [{i + 1:>2}/{total}] {w:>3}×{h:<3}px  pos=({x},{y})")

    save_icons(icons, OUTPUT_DIR)
    print(f"⏱  Всего: {time.time() - t_start:.2f}с")


if __name__ == "__main__":
    process()
