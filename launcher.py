"""
Меню запуска обработки иконок.

Вся русская консоль живёт ЗДЕСЬ (Python надёжно держит UTF-8 через reconfigure),
а .bat остаётся пустым ASCII-стартером — чтобы не воевать с кодировками cmd
(chcp/BOM/cp1251 — именно те «кракозябры», см. architecture.md §1).

В input/ можно класть НЕСКОЛЬКО листов со своими именами. При запуске выбираешь,
с каким работать; результаты идут в output/<имя_файла>/ (внутри opencv/, trimmed/
и т.д.). Размер и формат итоговых иконок настраиваются ([6]) и помнятся между
запусками (settings.json).

Запуск: двойной клик по «Иконки.bat».
"""
import os
import sys
import json
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
SETTINGS_FILE = ROOT / "settings.json"
IMAGE_EXT = {".png", ".webp", ".jpg", ".jpeg", ".bmp"}
DEFAULT_SETTINGS = {"size": 256, "format": "webp"}


# ---------- настройки (размер, формат) ----------

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            size = int(data.get("size", 256))
            fmt = data.get("format", "webp")
            if fmt in ("webp", "png", "both") and size >= 16:
                return {"size": size, "format": fmt}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(s):
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def edit_settings(s):
    print(f"\nТекущее: размер {s['size']}px, формат {s['format']}")
    print("\nРазмер итоговой иконки (квадрат):")
    print("  [1] 256 — иконки   [2] 512 — спрайты   [3] 1024 — портреты   [4] свой")
    c = input("Размер (Enter — оставить): ").strip()
    if c == "1":
        s["size"] = 256
    elif c == "2":
        s["size"] = 512
    elif c == "3":
        s["size"] = 1024
    elif c == "4":
        v = input("Сторона в пикселях: ").strip()
        if v.isdigit() and int(v) >= 16:
            s["size"] = int(v)

    print("\nФормат файлов:")
    print("  [1] webp — легче в 2-4 раза (по умолч.)   [2] png   [3] оба")
    c = input("Формат (Enter — оставить): ").strip()
    if c == "1":
        s["format"] = "webp"
    elif c == "2":
        s["format"] = "png"
    elif c == "3":
        s["format"] = "both"

    save_settings(s)
    print(f"\nСохранено: размер {s['size']}px, формат {s['format']}")


# ---------- выбор исходника ----------

def list_sources():
    """Картинки верхнего уровня input/ (подпапки вроде input/enhance/ пропускаем)."""
    if not INPUT_DIR.exists():
        return []
    return sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXT
    )


def select_source():
    """Возвращает выбранный файл-исходник или None, если в input/ ничего нет."""
    sources = list_sources()
    if not sources:
        print("В папке input/ нет картинок. Положи туда лист(ы) с иконками "
              "(.png/.webp) и запусти снова.")
        return None
    if len(sources) == 1:
        print(f"Исходник один: {sources[0].name} — беру его.")
        return sources[0]
    print("\nЧто в папке input/:")
    for i, s in enumerate(sources, 1):
        print(f"  [{i}] {s.name}")
    while True:
        choice = input("Выбери номер исходника: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(sources):
            return sources[int(choice) - 1]
        print("Не понял. Введи номер из списка.")


def work_dir_for(src):
    """Папка результатов для исходника: output/<имя_без_расширения>/."""
    return OUTPUT_DIR / src.stem


# ---------- действия ----------

def cut_icons(src, work, settings):
    """Нарезка иконок из выбранного исходника → <work>/opencv/."""
    from process_opencv import process
    process(input_file=src, output_dir=work / "opencv",
            target_size=settings["size"], fmt=settings["format"])


def _trim(work, fmt, outer, inner, dst_name, label):
    """Срез края у нарезанных иконок. Читает <work>/opencv/, пишет в <work>/<dst_name>/
    в текущем формате — оригинал не трогает, повтор не накапливает срез."""
    import cv2
    from utils import trim_edges, _save_webp, list_icon_files
    src = work / "opencv"
    files = list_icon_files(src)
    if not files:
        print(f"Нет нарезанных иконок в {src} — сначала нарежь лист [1].")
        return
    dst = work / dst_name
    dst.mkdir(parents=True, exist_ok=True)
    want_png = fmt in ("png", "both")
    want_webp = fmt in ("webp", "both")
    for f in files:
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None or img.ndim != 3 or img.shape[2] != 4:
            continue
        out = trim_edges(img, px=1, outer=outer, inner=inner)
        base = dst / f.stem
        if want_png:
            cv2.imwrite(str(base) + ".png", out)
        if want_webp:
            _save_webp(str(base) + ".webp", out)
    print(f"Готово: {len(files)} иконок ({label}, {fmt}) → {dst}")


def trim_outer(work, settings):
    """Срез ВНЕШНЕГО контура (безопасно, для всех иконок) → <work>/trimmed/."""
    _trim(work, settings["format"], outer=True, inner=False,
          dst_name="trimmed", label="внешний контур")


def trim_inner(work, settings):
    """Срез ВНУТРЕННИХ кромок полостей (для колец/петель; тончит тонкие линии)
    → <work>/trimmed_inner/."""
    _trim(work, settings["format"], outer=False, inner=True,
          dst_name="trimmed_inner", label="внутренние кромки")


def sharpen(work):
    """Резкость (enhance): спрашивает режим и обрабатывает нарезанные иконки."""
    import enhance
    enhance.process(enhance.prompt_mode(),
                    opencv_dir=work / "opencv",
                    output_dir=work / "enhanced")


def analyze_result(work):
    """Анализ результата: отчёт о проблемных местах (ничего не меняет)."""
    import analyze
    analyze.main(work / "opencv")


def open_work(work):
    if work.exists():
        os.startfile(work)
    else:
        print(f"Папки {work} ещё нет — сначала нарежь иконки [1].")


# ---------- меню ----------

def menu_text(src, work, settings):
    return f"""
============================================
           ИКОНКИ — обработка листа
============================================

  Исходник: {src.name}
  Результаты: output\\{work.name}\\
  Размер: {settings['size']}px   Формат: {settings['format']}

  [1] Нарезать иконки из листа
  [2] Срез внешнего контура 1px (безопасно, всем)
  [3] Срез внутренних кромок 1px (кольца/петли)
  [4] Добавить резкость (enhance)
  [5] Анализ результата (отчёт о проблемах)
  [6] Настройки (размер, формат)
  [7] Сменить исходник
  [8] Открыть папку с результатом
  [0] Выход
"""


def main():
    settings = load_settings()
    src = select_source()
    if src is None:
        input("\nEnter — выход...")
        return
    work = work_dir_for(src)

    while True:
        print(menu_text(src, work, settings))
        choice = input("Введи цифру и нажми Enter: ").strip()
        if choice == "1":
            cut_icons(src, work, settings)
            input("\nГотово. Enter — вернуться в меню...")
        elif choice == "2":
            trim_outer(work, settings)
            input("\nEnter — вернуться в меню...")
        elif choice == "3":
            trim_inner(work, settings)
            input("\nEnter — вернуться в меню...")
        elif choice == "4":
            sharpen(work)
            input("\nEnter — вернуться в меню...")
        elif choice == "5":
            analyze_result(work)
            input("\nEnter — вернуться в меню...")
        elif choice == "6":
            edit_settings(settings)
            input("\nEnter — вернуться в меню...")
        elif choice == "7":
            new_src = select_source()
            if new_src is not None:
                src = new_src
                work = work_dir_for(src)
        elif choice == "8":
            open_work(work)
        elif choice == "0":
            return
        else:
            print("Не понял. Введи цифру из меню (0–8).")


if __name__ == "__main__":
    main()
