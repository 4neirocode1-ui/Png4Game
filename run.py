"""
Точка входа. Проверяет структуру каталогов, наличие исходника, запускает обработку.
"""
import sys
from pathlib import Path

# Консоль cp1251 на Windows не тянет эмодзи из логов — переключаемся на UTF-8.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
EXPECTED_INPUT = INPUT_DIR / "1.png"


def ensure_structure():
    created = []
    for d in (INPUT_DIR, OUTPUT_DIR):
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d))
    if created:
        print(f"📁 Созданы папки: {', '.join(created)}")


def check_input() -> bool:
    if not EXPECTED_INPUT.exists():
        print(f"❌ Не найден исходник: '{EXPECTED_INPUT}'")
        print("   Положи спрайтшит в папку 'input' под именем '1.png'.")
        return False
    return True


def main():
    ensure_structure()
    if not check_input():
        sys.exit(1)

    from process_opencv import process
    process()


if __name__ == "__main__":
    main()
