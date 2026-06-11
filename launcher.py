"""
Меню запуска обработки иконок.

Вся русская консоль живёт ЗДЕСЬ (Python надёжно держит UTF-8 через reconfigure),
а .bat остаётся пустым ASCII-стартером — чтобы не воевать с кодировками cmd
(chcp/BOM/cp1251 — именно те «кракозябры», см. architecture.md §1).

Запуск: двойной клик по «Иконки.bat».
"""
import os
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def cut_icons():
    """Нарезка иконок из input/1.png (тот же путь, что и run.py)."""
    import run
    run.ensure_structure()
    if not run.check_input():
        return
    from process_opencv import process
    process()


def sharpen():
    """Резкость (enhance): спрашивает режим и обрабатывает нарезанные иконки."""
    import enhance
    enhance.process(enhance.prompt_mode())


def open_output():
    out = ROOT / "output"
    if out.exists():
        os.startfile(out)
    else:
        print("Папки output ещё нет — сначала нарежь иконки [1].")


MENU = """
============================================
           ИКОНКИ — обработка листа
============================================

  Положи лист с иконками в  input\\1.png

  [1] Нарезать иконки из листа
  [2] Добавить резкость (enhance)
  [3] Открыть папку с результатом
  [0] Выход
"""


def main():
    while True:
        print(MENU)
        choice = input("Введи цифру и нажми Enter: ").strip()
        if choice == "1":
            cut_icons()
            input("\nГотово. Enter — вернуться в меню...")
        elif choice == "2":
            sharpen()
            input("\nEnter — вернуться в меню...")
        elif choice == "3":
            open_output()
        elif choice == "0":
            return
        else:
            print("Не понял. Введи 1, 2, 3 или 0.")


if __name__ == "__main__":
    main()
