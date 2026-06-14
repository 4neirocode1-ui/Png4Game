import cv2
import numpy as np
import os
from pathlib import Path


def imread_unicode(path, flags=cv2.IMREAD_UNCHANGED):
    """Читает картинку, корректно работая с путями в кириллице/Unicode.

    cv2.imread на Windows открывает файл через узкую (ANSI) кодировку и
    возвращает None для путей с не-ASCII символами ('Артефакты.png' и т.п.).
    Обход: читаем байты файла через numpy (np.fromfile держит Unicode-пути)
    и декодируем уже из памяти. Возвращает None, если файл не прочитан/битый.
    """
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite_unicode(path, img):
    """Пишет картинку, корректно работая с путями в кириллице/Unicode.

    Симметрично imread_unicode: cv2.imwrite тоже спотыкается о не-ASCII пути.
    Кодируем в память по расширению файла и сбрасываем байты через tofile
    (держит Unicode-пути). Возвращает True/False как cv2.imwrite.
    """
    path = str(path)
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    buf.tofile(path)
    return True

# ==================== НАСТРОЙКИ ====================
INPUT_FILE = "input/1.png"
TARGET_SIZE = 256        # Сторона квадрата итоговой иконки, px (256 — стандарт для иконок;
                         # 512 — боевые спрайты, 1024 — портреты; см. asset_pipeline_brief).
OUTPUT_FORMAT = "webp"   # Что сохранять: "webp" (по умолч., в 2-4 раза легче PNG) | "png" | "both".
PADDING = 4              # Отступ от края холста (пропорц. размеру)
MIN_ICON_SIZE = 35       # Минимум пикселей по ширине и высоте
MIN_ICON_AREA = 500      # Минимум закрашенных пикселей в компоненте (отсекает мусорные штрихи)
MAX_ASPECT_RATIO = 3.0   # Длиннее этого по сторонам — кандидат в «подписи»; решает
                         # уже проверка площади (LONG_ITEM_MIN_FRACTION), а не сам порог.
LONG_ITEM_MIN_FRACTION = 0.30   # Длинный компонент (aspect>MAX_ASPECT_RATIO) оставляем
                         # как НАСТОЯЩИЙ ПРЕДМЕТ (молния/копьё/посох/лук/склянка), если
                         # его площадь ≥ этой доли от медианной иконки листа. Текстовая
                         # подпись мелкая (~5% медианы) — отсекается; длинный предмет
                         # весит 40–127% и проходит. Доля от медианы, а не абсолют, —
                         # листы разного масштаба (медиана от ~5k до ~170k px).
MERGE_RADIUS = 18        # Склейка кусков ОДНОЙ иконки: компоненты, между которыми
                         # зазор < 2×MERGE_RADIUS (≈36px), считаются одной иконкой.
                         # Снежинка = центр + отлетевшие лучи; оглушение = вихрь +
                         # звёзды; броня = осколки. Каждый кусок «подращиваем» на
                         # MERGE_RADIUS px и смотрим, кто слипся. Условие корректности:
                         # зазор МЕЖДУ иконками должен быть больше, чем ВНУТРИ иконки.
                         # На листах с иконками впритык (зазор < 36px) соседи сольются —
                         # такие листы либо генерить с бо́льшими промежутками, либо
                         # доводить вручную. 0 = выключить склейку (старое поведение).
MAX_HOLE_AREA = 8        # Замкнутые дыры МЕНЬШЕ стольких px → закрашиваются (пиксели
                         # антиалиасинга — 1-4px). Порог абсолютный, не процентный:
                         # шум не растёт с размером иконки. Стоит ровно под границей
                         # punch_internal_white (min_area=8), чтобы функции не конфликтовали:
                         # punch владеет белыми проёмами ≥8px, fill — спеклами <8px.
BG_TOLERANCE = 5         # Допуск flood fill — узкий, не «протекает» через тонкую обводку
ALPHA_FADE_LO = 200      # Граничный пиксель min(B,G,R) ≤ этого → α=255
ALPHA_FADE_HI = 250      # Граничный пиксель min(B,G,R) ≥ этого → α=0
DETECT_GRAY_HI = 230     # Любой пиксель темнее этого — часть иконки при детекции
# ====================================================


def load_image(path=INPUT_FILE):
    img = imread_unicode(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Файл не найден: '{path}'")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

    # Photoshop при экспорте PNG оставляет RGB-данные под alpha=0 нетронутыми
    # (скрытые/стёртые слои с текстом всё ещё лежат в каналах R/G/B). Детектор
    # читает только RGB и принимает эти невидимые буквы за иконки. Заливаем
    # RGB белым там, где пиксель полностью прозрачен — детектор видит чистый фон.
    transparent = img[:, :, 3] == 0
    img[transparent, :3] = 255
    return img


def build_global_alpha(img, tolerance=BG_TOLERANCE,
                       edge_lo=ALPHA_FADE_LO, edge_hi=ALPHA_FADE_HI):
    """
    Глобальная альфа: жёсткий flood fill + feather на 1-px границе.

    1. Жёсткий flood fill (узкий tolerance) от краёв заливает только чисто
       белый фон. Тонкая обводка иконки служит барьером, и внутренности
       любых иконок (включая светлые) остаются непрозрачными.
    2. На 1-px-границе считаем α по яркости: чем светлее, тем прозрачнее.
       Это убирает белёсую бахрому от антиалиасинга исходника, не трогая
       светлые/металлические детали внутри иконок.
    """
    bgr = img[:, :, :3]
    h, w = bgr.shape[:2]

    ff_mask = np.zeros((h + 2, w + 2), np.uint8)
    temp = bgr.copy()
    diff = (tolerance, tolerance, tolerance)

    for x in range(w):
        for by in (0, h - 1):
            if ff_mask[by + 1, x + 1] == 0 and int(bgr[by, x].min()) > 240:
                cv2.floodFill(temp, ff_mask, (x, by), (0, 0, 0), diff, diff)
    for y in range(1, h - 1):
        for bx in (0, w - 1):
            if ff_mask[y + 1, bx + 1] == 0 and int(bgr[y, bx].min()) > 240:
                cv2.floodFill(temp, ff_mask, (bx, y), (0, 0, 0), diff, diff)

    bg = ff_mask[1:h + 1, 1:w + 1].astype(bool)
    fg = (~bg).astype(np.uint8) * 255

    # 2px-граница (erode kernel 3×3 дважды) — добивает остаток белой бахромы
    # антиалиасинга шире, чем 1-px вариант.
    fg_eroded = cv2.erode(fg, np.ones((3, 3), np.uint8), iterations=2)
    boundary = (fg > 0) & (fg_eroded == 0)

    min_channel = bgr.min(axis=2).astype(np.int16)
    span = max(1, edge_hi - edge_lo)
    alpha_soft = np.clip(255 * (edge_hi - min_channel) / span, 0, 255).astype(np.uint8)

    alpha = fg.copy()
    alpha[boundary] = np.minimum(alpha[boundary], alpha_soft[boundary])
    return alpha


def _group_by_proximity(labels, stats, valid_ids, radius=MERGE_RADIUS):
    """
    Склеивает компоненты-куски ОДНОЙ иконки в группы по близости.

    Иконку часто рисуют из несвязанных кусков: снежинка = центр + отлетевшие
    лучи, оглушение = вихрь + звёзды, броня = осколки. Связные компоненты дают
    по иконке-куску, а нужна целая. Решение: каждый кусок «подращиваем» на
    `radius` px (морфо-дилатация) — куски, между которыми зазор < 2×radius,
    слипаются; смотрим, что слиплось, и группируем исходные (НЕ раздутые)
    компоненты по разросшимся пятнам.

    Возвращает список (x, y, w, h, frozenset(label_ids)) — union-bbox группы и
    набор её компонент. radius<=0 → склейки нет (каждый кусок отдельной иконкой).
    """
    if not valid_ids:
        return []
    if radius <= 0:
        out = []
        for i in valid_ids:
            x, y, w, h, _ = stats[i]
            out.append((int(x), int(y), int(w), int(h), frozenset([i])))
        return out

    valid_mask = np.isin(labels, valid_ids).astype(np.uint8)
    k = 2 * radius + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    grown = cv2.dilate(valid_mask, kernel)
    _, glabels = cv2.connectedComponents(grown, connectivity=8)

    members = {}  # метка разросшейся группы -> список исходных компонент
    for i in valid_ids:
        ys, xs = np.where(labels == i)
        g = int(glabels[ys[0], xs[0]])
        members.setdefault(g, []).append(i)

    out = []
    for ids in members.values():
        x0 = min(stats[i][0] for i in ids)
        y0 = min(stats[i][1] for i in ids)
        x1 = max(stats[i][0] + stats[i][2] for i in ids)
        y1 = max(stats[i][1] + stats[i][3] for i in ids)
        out.append((int(x0), int(y0), int(x1 - x0), int(y1 - y0), frozenset(ids)))
    return out


def _select_valid_ids(num, stats, min_size, min_area, max_aspect,
                      long_frac=LONG_ITEM_MIN_FRACTION):
    """
    Отбирает метки компонент-иконок по размеру/площади/вытянутости.

    Длинные компоненты (aspect > max_aspect) — кандидаты в текстовые подписи,
    но настоящий длинный ПРЕДМЕТ (молния, копьё, посох, лук, склянка) тоже
    вытянут. Различаем по площади: подпись мелкая (~5% от обычной иконки),
    предмет крупный (40–127%). Длинный оставляем, если его площадь ≥
    long_frac × медианы «квадратных» иконок этого листа (масштаб у листов
    разный, поэтому доля, а не абсолют). Если квадратных иконок нет вовсе —
    эталона для «мелкого текста» нет, считаем все длинные предметами.
    """
    square, square_areas, longs = [], [], []
    for i in range(1, num):
        _x, _y, w, h, area = stats[i]
        if w < min_size or h < min_size:
            continue
        if area < min_area:
            continue
        if max(w / h, h / w) > max_aspect:
            longs.append((i, area))
        else:
            square.append(i)
            square_areas.append(area)

    valid = list(square)
    if longs:
        if square_areas:
            cutoff = long_frac * float(np.median(square_areas))
            valid += [i for i, area in longs if area >= cutoff]
        else:
            valid += [i for i, _ in longs]
    return valid


def find_icons_by_alpha(alpha, min_size=MIN_ICON_SIZE, min_area=MIN_ICON_AREA,
                        max_aspect=MAX_ASPECT_RATIO, merge_radius=MERGE_RADIUS):
    """
    Находит иконки как связные компоненты по альфа-каналу + склейка кусков.

    Между иконками — alpha=0 (полностью прозрачно), внутри иконки — alpha>0.
    Подходит для исходника с чистой альфой (фон уже стёрт в фотошопе).

    Фильтр по `min_area` отсекает остатки от ластика — несколько висящих
    пикселей могут дать bbox правильного размера, но fill-фактор у такого
    мусора ~3%, у настоящей иконки — 50%+. Уцелевшие компоненты группируются
    по близости (`_group_by_proximity`): отлетевшие куски одной иконки —
    в одну группу.

    Возвращает (groups, labels): groups — список (x, y, w, h, frozenset(ids))
    после склейки; labels — карта компонентов того же размера, что и картинка.
    """
    mask = (alpha > 0).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    valid = _select_valid_ids(num, stats, min_size, min_area, max_aspect)
    groups = _group_by_proximity(labels, stats, valid, merge_radius)
    groups.sort(key=lambda b: (b[1] // 90, b[0]))
    return groups, labels


def find_icons(img, min_size=MIN_ICON_SIZE, min_area=MIN_ICON_AREA,
               max_aspect=MAX_ASPECT_RATIO, gray_hi=DETECT_GRAY_HI,
               merge_radius=MERGE_RADIUS):
    """
    Находит иконки как связные компоненты по gray-threshold + склейка кусков.

    Любой пиксель темнее `gray_hi` — часть иконки. Это намеренно широкая
    маска: захватывает не только обводку, но и полупрозрачную бахрому
    антиалиасинга, поэтому обводка и цветные детали внутри иконки
    остаются связными даже если между ними светлые промежутки.

    Между иконкой и подписью идут чисто-белые строки (gray > gray_hi),
    поэтому подпись выделяется в отдельную компоненту и отбрасывается
    фильтром aspect_ratio (до склейки, чтобы подпись не прилипла к иконке).

    Возвращает (groups, labels): groups — список (x, y, w, h, frozenset(ids))
    после склейки; labels — карта компонентов того же размера, что и картинка.
    """
    gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, gray_hi, 255, cv2.THRESH_BINARY_INV)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    valid = _select_valid_ids(num, stats, min_size, min_area, max_aspect)
    # Построчно, слева направо. Шаг 90px — высота строки иконок на спрайтшите.
    groups = _group_by_proximity(labels, stats, valid, merge_radius)
    groups.sort(key=lambda b: (b[1] // 90, b[0]))
    return groups, labels


def punch_internal_white(roi_bgr, roi_a, min_area=8, white_thr=220):
    """
    Делает прозрачными белёсые области внутри иконки.

    Полость лука, дырка кольца, светлые промежутки в плетении пояса —
    все они окружены замкнутой обводкой, и глобальный flood fill до них
    не дотянулся. Признак внутренней «дыры»: пиксель почти белый
    (min(B,G,R) > white_thr) И отмечен как непрозрачный. Совсем мелкие
    пятна (одиночные блики на металле) пропускаем.

    Соседние иконки уже занулены до этой функции, поэтому проверка
    касания границы ROI не нужна — все белые-непрозрачные пиксели в ROI
    принадлежат именно этой иконке.
    """
    is_white = (roi_bgr.min(axis=2) > white_thr) & (roi_a > 100)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        is_white.astype(np.uint8), connectivity=4)

    result = roi_a.copy()
    for i in range(1, num):
        if stats[i][4] >= min_area:
            result[labels == i] = 0
    return result


def keep_main_component(alpha, small_ratio=0.25, text_aspect=2.5):
    """
    Удаляет в маске мусорные компоненты, оставляя саму иконку.

    Подпись часто склеена с иконкой тонким 1-2px мостиком (антиалиасинг
    или артефакт), поэтому связные компоненты считаем по «открытому»
    (morph open) варианту маски — мостик разрывается, и текст становится
    отдельной компонентой. Решение об удалении принимаем по этой
    эродированной разметке, а пиксели тушим в исходной альфе.

    Типы мусора, которые отлавливаем:
      - мелкие компоненты с area < `small_ratio` от главной;
      - текстовые подписи: широкие и низкие компоненты в нижней половине
        bbox (aspect ≥ text_aspect).
    """
    h = alpha.shape[0]
    mask = (alpha > 0).astype(np.uint8)
    # 2-проходный open разрывает соединения шире 1px, до 2-3px.
    eroded = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8),
                              iterations=2)
    if eroded.sum() == 0:
        return alpha

    num, labels, stats, _ = cv2.connectedComponentsWithStats(eroded, connectivity=8)
    if num <= 2:
        return alpha

    areas = [(i, stats[i][4]) for i in range(1, num)]
    main_idx, main_area = max(areas, key=lambda t: t[1])
    small_cutoff = max(40, int(main_area * small_ratio))

    # Растим главную компоненту обратно до исходных пикселей маски (учитываем
    # тонкие части — рукояти, цепочки, — которые open подрезал бы в чистом виде).
    keep = (labels == main_idx).astype(np.uint8)
    keep = cv2.dilate(keep, np.ones((3, 3), np.uint8)) & mask

    drop = np.zeros_like(mask)
    for i, _area in areas:
        if i == main_idx:
            continue
        x, y, bw, bh, area = stats[i]
        is_text = bw >= bh * text_aspect and y > h // 2
        if area < small_cutoff or is_text:
            drop |= (labels == i).astype(np.uint8)

    drop = cv2.dilate(drop, np.ones((3, 3), np.uint8)) & mask
    # Если пиксель попал и в keep, и в drop — оставляем (приоритет иконке)
    drop &= ~keep.astype(bool)

    result = alpha.copy()
    result[drop.astype(bool)] = 0
    return result


def fill_small_holes(alpha, max_area=MAX_HOLE_AREA):
    """
    Закрашивает только спеклы антиалиасинга — замкнутые прозрачные дырки в
    несколько пикселей внутри иконки.

    Большие проёмы (полость лука, внутренность кольца, петля стремени)
    остаются прозрачными — туда видно фон. Только субпиксельные «дырочки»
    от антиалиасинга (1-4px) делаются непрозрачными.

    Порог абсолютный (max_area), не процентный: шум антиалиасинга измеряется
    в единицах пикселей и не масштабируется с размером иконки. Раньше порог
    был 2% площади (~350px на 256-иконке) и заливал реальные проёмы — петля
    арбалета (238px) пропадала под белым.
    """
    h, w = alpha.shape[:2]
    inv = (alpha == 0).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)

    result = alpha.copy()
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        # Прозрачная компонента, доходящая до границы ROI = внешний фон, не трогаем
        if x == 0 or y == 0 or x + bw == w or y + bh == h:
            continue
        if area < max_area:
            result[labels == i] = 255
    return result


def fit_to_canvas(rgba, target_size=TARGET_SIZE, padding=PADDING):
    """
    Вписывает BGRA-иконку по центру холста target_size × target_size.

    Ресайз через premultiplied alpha: BGR умножается на α перед усреднением
    INTER_AREA и делится после. Без этого края «выцветают» — INTER_AREA
    подмешивает в краевые пиксели цвет полностью прозрачных соседей
    (которые в обычном RGBA могут быть какими угодно).
    """
    h, w = rgba.shape[:2]
    inner = target_size - 2 * padding

    scale = inner / max(w, h)
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))

    b, g, r, a = cv2.split(rgba)
    a_f = a.astype(np.float32) / 255.0
    pre = cv2.merge([
        b.astype(np.float32) * a_f,
        g.astype(np.float32) * a_f,
        r.astype(np.float32) * a_f,
    ])

    pre_r = cv2.resize(pre, (nw, nh), interpolation=cv2.INTER_AREA)
    a_r = cv2.resize(a_f, (nw, nh), interpolation=cv2.INTER_AREA)

    safe_a = np.where(a_r > 0.005, a_r, 1.0)
    bgr_final = np.clip(pre_r / safe_a[..., None], 0, 255).astype(np.uint8)
    a_final = np.clip(a_r * 255, 0, 255).astype(np.uint8)
    resized = np.dstack([bgr_final, a_final])

    canvas = np.zeros((target_size, target_size, 4), dtype=np.uint8)
    off_x = (target_size - nw) // 2
    off_y = (target_size - nh) // 2
    canvas[off_y:off_y + nh, off_x:off_x + nw] = resized
    return canvas


def trim_edges(rgba, px=1, outer=True, inner=True):
    """
    Чистый срез края силуэта на px пикселей. НЕ эрозия всего объекта — трогаются
    только выбранные кромки, цвет (BGR) не меняется.

    outer=True — ВНЕШНИЙ контур (кромка у фона): убирает светлую кайму на тёмном UI.
    inner=True — ВНУТРЕННИЙ край (вокруг полостей): растит проём на px, снимая кайму
                 по его кромке — углы тетивы лука, петля арбалета, ободок кольца.

    Алгоритм: берём прозрачные области нужного типа (внешний фон — компоненты,
    касающиеся края картинки; полости — замкнутые внутри), раздуваем их на px
    внутрь силуэта и этому кольцу ставим α=0.
    """
    a = rgba[:, :, 3]
    h, w = a.shape[:2]
    fg = a > 0

    transp = (a == 0).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(transp, connectivity=4)
    cut = np.zeros((h, w), np.uint8)
    for i in range(1, num):
        x, y, bw, bh, _area = stats[i]
        touches = (x == 0 or y == 0 or x + bw == w or y + bh == h)
        if (touches and outer) or (not touches and inner):
            cut[labels == i] = 1

    grown = cv2.dilate(cut, np.ones((3, 3), np.uint8), iterations=px).astype(bool)
    ring = grown & fg

    out = rgba.copy()
    out[ring, 3] = 0
    return out


def save_icons(icons, output_dir, fmt=OUTPUT_FORMAT):
    """Сохраняет иконки в выбранном формате: webp | png | both."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    want_png = fmt in ("png", "both")
    want_webp = fmt in ("webp", "both")
    for i, icon in enumerate(icons):
        base = os.path.join(output_dir, f"icon_{i:03d}")
        if want_png:
            imwrite_unicode(base + ".png", icon)
        if want_webp:
            _save_webp(base + ".webp", icon)
    print(f"✅ Сохранено {len(icons)} иконок ({fmt}) → '{output_dir}'")


def list_icon_files(folder):
    """Иконки icon_* в папке (png и/или webp), по одной на индекс — png в приоритете.
    Нужно, чтобы trim/analyze/enhance работали независимо от выбранного формата."""
    folder = Path(folder)
    by_stem = {}
    for p in sorted(folder.glob("icon_*.png")) + sorted(folder.glob("icon_*.webp")):
        by_stem.setdefault(p.stem, p)   # png встречается первым → выигрывает
    return [by_stem[s] for s in sorted(by_stem)]


def _save_webp(path, bgra_icon, quality=90):
    """Сохраняет BGRA-иконку в WebP с прозрачностью через Pillow.

    OpenCV в части сборок теряет альфу при записи WebP, поэтому пишем через
    Pillow — он надёжно держит прозрачность. Pillow обязателен для конвейера
    (отдельной зависимостью, ставится в .venv).
    """
    from PIL import Image as PILImage
    rgba = cv2.cvtColor(bgra_icon, cv2.COLOR_BGRA2RGBA)
    PILImage.fromarray(rgba).save(path, "WEBP", quality=quality, method=6)
