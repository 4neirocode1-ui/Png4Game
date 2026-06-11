"""
Вырезает иконки из спрайтшита с помощью нейросети rembg.

Установка зависимостей (один раз):
    pip install rembg[gpu] onnxruntime-gpu pillow
  или без GPU:
    pip install rembg onnxruntime pillow

Доступные модели (MODEL ниже):
    u2net              — универсальная, хорошее качество
    isnet-general-use  — лучше для детализированных объектов, медленнее
    u2netp             — облегчённая, быстрее, чуть хуже качеством
"""
import time
import cv2
import numpy as np
from PIL import Image

from utils import (
    INPUT_FILE, TARGET_SIZE, PADDING,
    load_image, find_icon_bboxes, fit_to_canvas, save_icons,
)

OUTPUT_DIR = "output/rembg"
MODEL = "isnet-general-use"

# Порог бинаризации rembg-альфы.
# 128 = убираем полупрозрачный белый ореол на краях, сохраняем чёткие объекты.
ALPHA_THRESHOLD = 128


def _bgr_to_pil(bgr):
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _fill_enclosed_holes(alpha):
    """
    Восстанавливает замкнутые прозрачные области внутри объекта.

    rembg иногда удаляет внутренние детали (центр медальона, декор щита,
    пятна лапы), если они светлые и похожи на фон.

    Алгоритм: flood fill от всех краёв по прозрачным пикселям (alpha == 0).
    Прозрачные пиксели, до которых нельзя добраться снаружи — внутри объекта,
    их нужно сделать непрозрачными.

    Настоящие дырки (отверстие кольца, промежуток лука) остаются прозрачными:
    flood fill добирается до них снаружи через пространство вокруг объекта.
    """
    h, w = alpha.shape[:2]

    # Карта прозрачных пикселей: 255 = прозрачно, 0 = объект
    transparent_map = np.where(alpha == 0, np.uint8(255), np.uint8(0))
    fill_mask = np.zeros((h + 2, w + 2), np.uint8)
    temp = transparent_map.copy()

    # Flood fill только по прозрачным пикселям (loDiff=upDiff=0 — строго по 255)
    for x in range(w):
        for border_y in [0, h - 1]:
            if temp[border_y, x] == 255 and fill_mask[border_y + 1, x + 1] == 0:
                cv2.floodFill(temp, fill_mask, (x, border_y), 128, 0, 0)
    for y in range(1, h - 1):
        for border_x in [0, w - 1]:
            if temp[y, border_x] == 255 and fill_mask[y + 1, border_x + 1] == 0:
                cv2.floodFill(temp, fill_mask, (border_x, y), 128, 0, 0)

    # Прозрачные, до которых не добраться снаружи = внутренние дыры → непрозрачные
    reached = fill_mask[1:h + 1, 1:w + 1] > 0
    result = alpha.copy()
    result[(~reached) & (alpha == 0)] = 255
    return result


def remove_bg_rembg(roi_bgra, session):
    """
    1. rembg даёт альфа-маску (без использования его RGB — они могут быть обнулены).
    2. Жёсткий порог по альфе убирает полупрозрачный белый ореол.
    3. Заливаем замкнутые дыры внутри объекта.
    4. Итоговый цвет берём из оригинального изображения.
    """
    from rembg import remove

    roi_bgr = roi_bgra[:, :, :3]

    # Только альфа от rembg; его RGB не используем
    rembg_out = np.array(remove(_bgr_to_pil(roi_bgr), session=session))
    rembg_alpha = rembg_out[:, :, 3]

    # Жёсткий порог: убирает белый ореол, оставляет чёткие объекты
    _, alpha = cv2.threshold(rembg_alpha, ALPHA_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Восстанавливаем внутренние детали (работаем только с альфой, не с BGR)
    alpha = _fill_enclosed_holes(alpha)

    # Оригинальные цвета — никаких чёрных артефактов
    b, g, r = cv2.split(roi_bgr)
    return cv2.merge([b, g, r, alpha])


def process():
    try:
        from rembg import new_session
    except ImportError:
        print("❌ rembg не установлен. Выполни: pip install rembg onnxruntime pillow")
        return

    img = load_image(INPUT_FILE)
    bboxes = find_icon_bboxes(img)
    print(f"🔍 Найдено иконок: {len(bboxes)}")

    print(f"⏳ Загрузка модели '{MODEL}'... (первый раз скачивает ~170 МБ)")
    session = new_session(MODEL)
    print("✅ Модель загружена")

    icons = []
    total = len(bboxes)
    t_start = time.time()

    for i, (x, y, w, h) in enumerate(bboxes):
        t0 = time.time()
        roi = img[y:y + h, x:x + w]
        rgba = remove_bg_rembg(roi, session)
        icon = fit_to_canvas(rgba, TARGET_SIZE, PADDING)
        icons.append(icon)

        elapsed = time.time() - t_start
        per_icon = elapsed / (i + 1)
        remaining = per_icon * (total - i - 1)
        print(
            f"  [{i + 1:>2}/{total}] {w:>3}×{h:<3}  "
            f"иконка: {time.time() - t0:.1f}с  "
            f"осталось: ~{remaining:.0f}с"
        )

    save_icons(icons, OUTPUT_DIR)
    print(f"⏱  Всего: {time.time() - t_start:.1f}с")


if __name__ == "__main__":
    process()
