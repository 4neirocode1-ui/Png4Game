# noinspection SpellCheckingInspection,GrazieInspection
"""Russian user-facing strings for enhance.py.

Kept separate so PyCharm's Grazie / spell-checker has nothing to analyse
in the main script (the Russian text here would otherwise generate ~200
typo warnings and chew CPU on every file open).
"""

CLI_DESC = "Постобработка иконок: усиление резкости через unsharp mask."

CLI_EPILOG = """\
Примеры запуска:
  python enhance.py                 # меню выбора метода
  python enhance.py --mode soft     # только soft
  python enhance.py --mode hard     # только hard
  python enhance.py --mode all      # все методы сразу
  python enhance.py --mode review   # интерактивный обзор

Источник иконок:
  input/enhance/   — если есть и не пуст, обрабатываем только её содержимое
                     (выборочная обработка: положил нужные иконки → запустил).
  output/opencv/   — иначе обрабатываем все иконки оттуда.

Результат раскладывается по подпапкам метода:
  output/enhanced/soft/icon_NNN.png
  output/enhanced/hard/icon_NNN.png
"""

CLI_MODE_HELP = "режим обработки; без флага запускается меню выбора"

HEADER = (
    "📂 Источник: {src} ({count} иконок)\n"
    "📁 Цель:     {dst}\n"
    "⚙  Режим:    {mode}"
)

MENU_TITLE = "\nВыбери метод обработки:"
MENU_ITEM = "  [{num}] {name}"
MENU_PROMPT = "> "
MENU_INVALID = "   ⚠  Не понял. Введи номер из списка или название режима."

REVIEW_PROMPT = """\

Иконка {name}: выберите, что сохранить.
Сделайте окно OpenCV активным и нажмите клавишу:
  [1] сохранить ТОЛЬКО оригинал  (папка orig)
  [2] сохранить ТОЛЬКО soft      (папка soft, мягкая резкость)
  [3] сохранить ТОЛЬКО hard      (папка hard, жёсткая резкость)
  [4] сохранить ОБА варианта soft и hard
  [5] сохранить ВСЕ три варианта (orig + soft + hard)
  [Пробел] пропустить иконку — ничего не сохранять
  [Q] / [Esc] выйти из обзора (остальные иконки оставить как есть)\
"""

UNKNOWN_KEY = "   ⚠  Неизвестная клавиша (код {key}). Нажмите 1-5, Пробел или Q."
REVIEW_QUIT = "👋 Выход из обзора по запросу пользователя."
NO_ICONS = (
    "❌ Не найдены иконки.\n"
    "   Положи нужные иконки в '{enhance}' для выборочной обработки\n"
    "   или сначала запусти run.py — иконки появятся в '{opencv}'."
)
NOT_RGBA = "  ⚠  {name}: ожидается RGBA — пропускаю."
SKIPPED = "  [{name}] пропущено"
SAVED = "  [{name}] → {preset}/icon_{name}.png"
SAVED_ALL = "  [{name}] → {presets}"
DONE = "\n✅ Сохранено файлов: {saved}, пропущено: {skipped}"
