"""
Универсальный слой ИМЕНОВАНИЯ нарезанных иконок (project-agnostic).

Ядро конвейера выдаёт безликие icon_000, icon_001… Этот модуль НЕ знает ничего
про конкретный проект (ни «слугов», ни «листов Game»): он умеет ровно одно —
взять упорядоченный список имён из текстового файла-манифеста рядом с листом и
разложить нарезку под этими именами в отдельную папку <work>/named/.

Манифест: <input>/<имя листа>.names.txt — по одному имени в строке; пустые строки
и строки, начинающиеся с #, игнорируются. Нет манифеста → шаг просто не делается,
на выходе остаются обычные icon_NNN. Универсальность ядра цела.

Предохранитель: если число имён не совпало с числом иконок (сбой нарезки,
просочившийся текст, неполный лист) — НИЧЕГО не переименовываем, возвращаем отчёт
о расхождении. Имена привязаны к ПОЗИЦИИ (N-я иконка = N-е имя), поэтому показать
пару «иконка→имя» глазами — последняя проверка порядка (см. слабое место D-4 —
устойчивость сортировки строк).

Шаблоны имён (input/_names_templates/*.names.txt) — это просто заготовки списков,
которые можно ПРИВЯЗАТЬ к листу (скопировать в <лист>.names.txt). Откуда они
берутся — дело проекта (для Game их готовит catalog_to_names.py из Описание.txt);
сам слой именования знает лишь, что это папка с текстовыми списками имён.
"""
import re
import shutil
from pathlib import Path

NAMES_SUFFIX = ".names.txt"
TEMPLATES_DIRNAME = "_names_templates"
_INDEX_RE = re.compile(r"icon_(\d+)")


# ---------- манифест рядом с листом ----------

def names_path_for(sheet_path):
    """Путь манифеста рядом с листом: <stem>.names.txt."""
    sheet_path = Path(sheet_path)
    return sheet_path.with_name(sheet_path.stem + NAMES_SUFFIX)


def load_names(names_path):
    """Список имён из манифеста (пустые строки и # — комментарии — пропускаем)."""
    names = []
    for raw in Path(names_path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


# ---------- нарезанные иконки ----------

def _icons_by_index(folder):
    """{индекс: [пути всех форматов]} для icon_NNN.* в папке, по возрастанию индекса."""
    folder = Path(folder)
    groups = {}
    if not folder.exists():
        return groups
    for p in sorted(folder.glob("icon_*")):
        if not p.is_file():
            continue
        m = _INDEX_RE.fullmatch(p.stem)
        if m:
            groups.setdefault(int(m.group(1)), []).append(p)
    return dict(sorted(groups.items()))


def delete_icon(folder, stem):
    """Удаляет все форматы одной нарезанной иконки (icon_NNN.png/.webp) из папки.

    Для ручной прополки шумной генерации: дубли предмета и лишние иконки. Имена
    вешаются по ПОРЯДКУ среди выживших (не по номеру файла), поэтому дырки в
    нумерации после удаления безопасны — порядок каталога у оставшихся цел.
    Возвращает список удалённых имён файлов.
    """
    folder = Path(folder)
    removed = []
    for p in folder.glob(stem + ".*"):
        if p.is_file():
            p.unlink()
            removed.append(p.name)
    return removed


def list_named_files(folder):
    """Картинки в named/ (произвольные имена), по одному файлу на имя — png в приоритете."""
    folder = Path(folder)
    if not folder.exists():
        return []
    by_stem = {}
    for p in sorted(folder.glob("*.png")) + sorted(folder.glob("*.webp")):
        by_stem.setdefault(p.stem, p)
    return [by_stem[s] for s in sorted(by_stem)]


def _duplicates(names):
    seen, dup = set(), []
    for n in names:
        if n in seen and n not in dup:
            dup.append(n)
        seen.add(n)
    return dup


def check(src_dir, names):
    """Сверяет число иконок и имён ДО записи. Возвращает (ok, message, pairs).

    pairs — список (index, путь_иконки, имя|None) для визуальной сверки пар:
    даже при совпадении числа порядок строк может «уехать» (D-4), и глаз ловит
    это по паре «миниатюра → имя».
    """
    groups = _icons_by_index(src_dir)
    indices = list(groups)
    n_icons, n_names = len(indices), len(names)

    pairs = []
    for pos, idx in enumerate(indices):
        nm = names[pos] if pos < n_names else None
        pairs.append((idx, groups[idx][0], nm))

    dup = _duplicates(names)
    if n_icons == 0:
        return False, "Нет нарезанных иконок — сначала нарежь лист.", pairs
    if n_names == 0:
        return False, "Манифест имён пуст.", pairs
    if dup:
        return False, f"Повторы имён в манифесте: {', '.join(dup)}.", pairs
    if n_icons != n_names:
        return False, (f"Не совпало: иконок {n_icons}, имён {n_names}. "
                       f"Имена НЕ применены — проверь лист/манифест."), pairs
    return True, f"OK: {n_icons} иконок ↔ {n_names} имён.", pairs


def _reset_dir(dst_dir):
    dst_dir = Path(dst_dir)
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    return dst_dir


def apply_names(src_dir, dst_dir, names):
    """ПОЗИЦИОННАЯ раскладка: N-я иконка → N-е имя (для ЧИСТОГО листа в порядке).

    При расхождении числа имён/иконок (или повторах) НЕ пишет ничего —
    предохранитель. named/ — полностью генерируемая папка, чистится целиком.
    Копируются ВСЕ форматы иконки (png и/или webp), имя берёт расширение файла.
    Для шумных листов (дубли/лишние/сбитый порядок) — apply_mapping по меткам.
    """
    ok, msg, _ = check(src_dir, names)
    if not ok:
        return False, msg

    dst_dir = _reset_dir(dst_dir)
    groups = _icons_by_index(src_dir)
    for name, (_idx, paths) in zip(names, groups.items()):
        for p in paths:
            shutil.copy2(p, dst_dir / (name + p.suffix))
    return True, f"Готово: {len(names)} иконок названо → {dst_dir}"


def apply_mapping(src_dir, dst_dir, mapping):
    """ЯВНАЯ раскладка по меткам, НЕЗАВИСИМО от порядка нарезки.

    mapping: {stem (icon_NNN): имя}. Иконки без имени просто не попадают в named/
    (выкинуты). Имя должно быть уникально — одно имя на одну иконку (UI этого
    добивается «переездом» имени). Возвращает (ok, message). Это рабочий путь для
    шумной генерации: дубли (выбрал лучший), лишние (без имени), сбитый порядок.
    """
    items = [(stem, name) for stem, name in mapping.items() if name]
    dup = _duplicates([n for _s, n in items])
    if not items:
        return False, "Ни одной иконке не задано имя."
    if dup:
        return False, f"Имя занято несколькими иконками: {', '.join(dup)}."

    src_dir = Path(src_dir)
    dst_dir = _reset_dir(dst_dir)
    written = 0
    for stem, name in items:
        files = [p for p in src_dir.glob(stem + ".*") if p.is_file()]
        if not files:
            continue
        for p in files:
            shutil.copy2(p, dst_dir / (name + p.suffix))
        written += 1
    return True, f"Готово: {written} иконок названо → {dst_dir}"


# ---------- шаблоны имён (заготовки списков) ----------

def templates_dir(input_dir):
    return Path(input_dir) / TEMPLATES_DIRNAME


def list_name_templates(input_dir):
    """Шаблоны .names.txt из input/_names_templates/ (отсортированы по имени)."""
    d = templates_dir(input_dir)
    if not d.exists():
        return []
    return sorted(d.glob("*" + NAMES_SUFFIX))


def template_label(template_path):
    """Читаемое имя шаблона для списка: без суффикса .names.txt."""
    name = Path(template_path).name
    return name[:-len(NAMES_SUFFIX)] if name.endswith(NAMES_SUFFIX) else name


def attach_template(template_path, sheet_path):
    """Копирует список имён шаблона в манифест рядом с листом. Возвращает путь манифеста."""
    dst = names_path_for(sheet_path)
    shutil.copy2(template_path, dst)
    return dst


# ---------- запуск как скрипт (один лист) ----------

if __name__ == "__main__":
    import sys
    from pathlib import Path as _P
    if len(sys.argv) < 2:
        print("Использование: python rename.py <путь к листу из input/> "
              "[папка-источник нарезки, по умолч. output/<лист>/opencv]")
        sys.exit(0)
    sheet = _P(sys.argv[1])
    work = _P("output") / sheet.stem
    src = _P(sys.argv[2]) if len(sys.argv) > 2 else work / "opencv"
    npath = names_path_for(sheet)
    if not npath.exists():
        print(f"Нет манифеста {npath} — положи рядом с листом .names.txt.")
        sys.exit(1)
    ok, message = apply_names(src, work / "named", load_names(npath))
    print(("✅ " if ok else "⚠ ") + message)
