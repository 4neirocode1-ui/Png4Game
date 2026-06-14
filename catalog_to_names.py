"""
ГЕНЕРАТОР ШАБЛОНОВ ИМЁН ИЗ КАТАЛОГА — ПРОЕКТНЫЙ скрипт (Game-специфичный!).

Универсальный инструмент (rename.py) про этот файл НЕ знает: он живёт сбоку и
лишь готовит .names.txt-шаблоны, которые потом привязываются к конкретным листам
(в окне — кнопкой «Привязать», в консоли — копированием файла). Так всё знание о
Game (слуги, листы каталога) остаётся вне болванки конвейера.

Что делает: парсит User_files/Описание.txt. Каждый блок-лист каталога —
  SHEET N (предметы) / STATUS SHEET N (статусы) / COMBAT SHEET A|B (боевая
  панель) / PART 4 (характеристики) / PART 5 (навыки)
— даёт один шаблон с упорядоченным списком слугов, взятых из (скобок) в конце
строк предметов. Складывает шаблоны в input/_names_templates/.

Связь «какой лист = какой блок» НЕ автоматизируется здесь намеренно: имена
исходников произвольны и плодятся вариантами (Бижа / Бижа 2). Один человеческий
выбор «этот лист ← этот блок» делается при привязке шаблона — без перепечатки имён.

Слуги — единственный мост к предметам игры (см. Game/scripts/item_registry.gd и
icon_registry.gd). Перегенерация листа не трогает остальные: шаблоны по-листовые.
"""
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):      # консоль Windows по умолчанию cp1251 —
    if hasattr(_stream, "reconfigure"):        # держим UTF-8 (см. architecture.md §1)
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "User_files" / "Описание.txt"
OUT_DIR = ROOT / "input" / "_names_templates"
NAMES_SUFFIX = ".names.txt"

# Слуг = (буква-первой [a-z], дальше буквы/цифры/_). Требование «первая буква»
# отсекает служебные скобки каталога: (7 items) — пробел, (3) — цифра,
# (action points / ОД) — пробелы/кириллица. Совпадает только настоящий слуг.
SLUG_RE = re.compile(r"\(([a-z][a-z0-9_]*)\)")
NUM_RE = re.compile(r"^\d+\.")   # начало строки-предмета: «1.», «12.» …
# Начало блока-листа. Требуем форму «… — » (с тире-заголовком), чтобы проза вроде
# «PART 3 status rules apply» НЕ принималась за заголовок. PART [45] несут предметы
# прямо в себе; PART 1/2/3/6 — контейнеры, в список НЕ включены.
BLOCK_RE = re.compile(r"^(SHEET \d+|STATUS SHEET \d+|COMBAT SHEET [A-Z]|PART [4-9]) —")
# Линейка ===== между разделами. Закрывает блок ТОЛЬКО если в нём уже собраны
# имена: ====, идущая сразу ПОД заголовком PART, не должна закрыть пустой блок.
DIVIDER_RE = re.compile(r"^={6,}$")


def parse_blocks(text):
    """Список (title, [slugs]) по порядку в каталоге. Пустые блоки отбрасываются.

    Слуги собираются ПО ПРЕДМЕТАМ: предмет — нумерованная строка плюс её
    переносы. У предмета берётся ПОСЛЕДНИЙ слуг в скобках: настоящий стоит в
    конце описания, а в середине бывают перекрёстные ссылки на чужие слуги
    («…the skull (poison). (blunt)») — их хватать нельзя.
    """
    blocks = []
    cur_title, items = None, None   # items: список предметов, предмет — список строк

    def close():
        nonlocal cur_title, items
        if cur_title is not None and items:
            slugs = []
            for lines in items:
                found = SLUG_RE.findall(" ".join(lines))
                if found:
                    slugs.append(found[-1])
            if slugs:
                blocks.append((cur_title, slugs))
        cur_title, items = None, None

    for line in text.splitlines():
        s = line.strip()
        if BLOCK_RE.match(s):
            close()
            cur_title, items = s, []
            continue
        if DIVIDER_RE.match(s) and items:
            close()
            continue
        if items is not None:
            if NUM_RE.match(s):
                items.append([s])          # новый предмет
            elif items:
                items[-1].append(s)        # перенос описания текущего предмета
            # строки до первого номера (интро блока) пропускаем
    close()
    return blocks


def slugify(title):
    """Имя файла-шаблона из заголовка блока: 'SHEET 1 — MELEE WEAPONS (7)' → 'sheet-1-melee-weapons'."""
    head = title.split("(")[0].replace("—", "-")
    out = re.sub(r"[^a-z0-9]+", "-", head.lower()).strip("-")
    return out or "block"


def main():
    if not CATALOG.exists():
        print(f"Не найден каталог: {CATALOG}")
        return
    blocks = parse_blocks(CATALOG.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    used = {}
    for title, slugs in blocks:
        base = slugify(title)
        # Подстраховка от коллизии имён файлов (на случай похожих заголовков).
        n = used.get(base, 0)
        used[base] = n + 1
        fname = (base if n == 0 else f"{base}-{n + 1}") + NAMES_SUFFIX
        body = [f"# {title}",
                f"# {len(slugs)} имён — автоген из Описание.txt (catalog_to_names.py)",
                ""] + slugs + [""]
        (OUT_DIR / fname).write_text("\n".join(body), encoding="utf-8")
        print(f"  {fname:<48} {len(slugs):>3} имён")

    total = sum(len(s) for _t, s in blocks)
    print(f"\nГотово: {len(blocks)} шаблонов, {total} имён → {OUT_DIR}")


if __name__ == "__main__":
    main()
