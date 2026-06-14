"""
Окно мастерской иконок (Фаза 1).

Это «лицо» к тому же движку, что и консольное меню: вся обработка живёт в
utils.py / process_opencv.py / enhance.py, а здесь только интерфейс. Окно ничего
не дублирует и не ломает — launcher.py (консоль) остаётся запасным путём.

Фаза 1: слева список листов из input/ (с числом уже нарезанных иконок), справа
миниатюры нарезки, снизу выбор размера/формата + «Нарезать» и «Открыть папку».
Дальше (Фаза 2+): срез контуров, резкость, переключатель стадий, пакет «все листы».

Запуск: двойной клик по «Иконки-окно.bat» (ASCII-стартер, как и у консоли).
Зависимости: только стандартный tkinter + уже стоящий Pillow (превью webp/png).
"""
import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# Переиспользуем готовые хелперы консоли и движок — единый источник логики.
from launcher import (list_sources, load_settings, save_settings,
                      work_dir_for, OUTPUT_DIR, defringe_icons)
from utils import list_icon_files
from process_opencv import process
import enhance

THUMB = 100          # сторона миниатюры, px
COLS = 5             # миниатюр в ряду
SIZES = [256, 512, 1024]
FORMATS = ["webp", "png", "both"]
PRESETS = ["soft", "hard"]

# Подложки-превью под прозрачные иконки (файлы не меняют — только показ).
# Каждая ловит свой дефект: чёрная — белую бахрому, маджента — мусорные пиксели,
# шахматка — реальную прозрачность фона. (key, подпись, цвет RGB | None=шахматка)
BACKGROUNDS = [
    ("gray", "Серый", (220, 220, 220)),
    ("white", "Белый", (255, 255, 255)),
    ("black", "Чёрный", (0, 0, 0)),
    ("magenta", "Маджента", (255, 0, 255)),
    ("checker", "Шахматка", None),
]

# Стадии правой панели: код -> (подпись, подпапка результата в output/<лист>/).
# "source" — сам лист, у "enhanced" подпапка зависит от пресета (см. stage_folder).
STAGES = [
    ("source", "Исходник"),
    ("opencv", "Нарезка"),
    ("defringed", "Чистый край"),
    ("enhanced", "Резкость"),
]


class IconWorkshop:
    MAXZOOM = 16.0   # потолок увеличения в лупе

    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.sheet_paths = []      # пути листов в порядке списка слева
        self.thumb_refs = []       # держим ссылки на PhotoImage (иначе Tk их соберёт)
        # состояние лупы (режим одиночного изображения с зумом/панорамой)
        self.mode = "grid"         # "grid" — сетка миниатюр, "view" — лупа
        self.view_pil = None       # PIL-изображение в лупе (полное разрешение)
        self.view_item = None      # id картинки на канве
        self.view_from_grid = False  # лупу открыли из сетки (двойным кликом)?
        self.zoom = 1.0
        self.img_x = 0.0           # координата изображения в левом-верхнем углу канвы
        self.img_y = 0.0
        self._pan = None           # старт перетаскивания
        root.title("Иконки — мастерская")
        root.geometry("980x640")
        self._build()
        self.refresh_sheets()

    # ---------- построение окна ----------

    def _build(self):
        left = ttk.Frame(self.root, padding=6)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Листы (input/)").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=34, activestyle="dotbox",
                                  exportselection=False)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        right = ttk.Frame(self.root, padding=6)
        right.pack(side="left", fill="both", expand=True)

        self.title_var = tk.StringVar(value="Выбери лист слева")
        ttk.Label(right, textvariable=self.title_var,
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")

        self.bg_var = tk.StringVar(value="gray")   # текущая подложка-превью

        # переключатель «что показывать»: сам лист или его нарезку
        stbar = ttk.Frame(right)
        stbar.pack(anchor="w", pady=(2, 0))
        self.stage_var = tk.StringVar(value="opencv")
        for val, label in STAGES:
            ttk.Radiobutton(stbar, text=label, value=val,
                            variable=self.stage_var,
                            command=self.render).pack(side="left", padx=(0, 10))

        # выбор подложки-превью (контроль бахромы/мусора/прозрачности)
        bgbar = ttk.Frame(right)
        bgbar.pack(anchor="w", pady=(2, 0))
        ttk.Label(bgbar, text="Подложка:").pack(side="left", padx=(0, 6))
        for key, label, _c in BACKGROUNDS:
            ttk.Radiobutton(bgbar, text=label, value=key, variable=self.bg_var,
                            command=self.on_bg_change).pack(side="left", padx=(0, 8))

        # область миниатюр со скроллом
        mid = ttk.Frame(right)
        mid.pack(fill="both", expand=True, pady=6)
        self.canvas = tk.Canvas(mid, background=self.widget_bg(),
                                highlightthickness=0)
        vbar = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.grid_frame = tk.Frame(self.canvas, background=self.widget_bg())
        self.grid_window = self.canvas.create_window(
            (0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        # колесо: в сетке — прокрутка, с Ctrl в лупе — масштаб
        self.canvas.bind_all("<MouseWheel>", self.on_wheel)
        self.canvas.bind_all("<Control-MouseWheel>", self.on_ctrl_wheel)
        # ЛКМ-перетаскивание = панорама (рука) в лупе
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        # нижняя панель: ряд настроек + ряд действий
        opts = ttk.Frame(right)
        opts.pack(fill="x", pady=(4, 2))
        ttk.Label(opts, text="Размер:").pack(side="left")
        self.size_var = tk.StringVar(value=str(self.settings["size"]))
        size_cb = ttk.Combobox(opts, textvariable=self.size_var, width=6,
                               state="readonly", values=[str(s) for s in SIZES])
        size_cb.pack(side="left", padx=(2, 12))
        size_cb.bind("<<ComboboxSelected>>", self.on_settings_change)

        ttk.Label(opts, text="Формат:").pack(side="left")
        self.fmt_var = tk.StringVar(value=self.settings["format"])
        fmt_cb = ttk.Combobox(opts, textvariable=self.fmt_var, width=6,
                              state="readonly", values=FORMATS)
        fmt_cb.pack(side="left", padx=(2, 12))
        fmt_cb.bind("<<ComboboxSelected>>", self.on_settings_change)

        ttk.Label(opts, text="Резкость:").pack(side="left")
        self.preset_var = tk.StringVar(value=PRESETS[0])
        preset_cb = ttk.Combobox(opts, textvariable=self.preset_var, width=6,
                                 state="readonly", values=PRESETS)
        preset_cb.pack(side="left", padx=(2, 12))
        preset_cb.bind("<<ComboboxSelected>>", lambda e: self.render())

        self.all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="все листы",
                        variable=self.all_var).pack(side="left", padx=4)

        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=(0, 2))
        ttk.Button(bar, text="Нарезать", command=self.cut).pack(side="left", padx=3)
        ttk.Button(bar, text="Чистка края",
                   command=self.do_defringe).pack(side="left", padx=3)
        ttk.Button(bar, text="Резкость",
                   command=self.do_sharpen).pack(side="left", padx=3)
        ttk.Button(bar, text="Открыть папку",
                   command=self.open_folder).pack(side="left", padx=3)

        self.status = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.status, anchor="w",
                 fg="#555").place(relx=0, rely=1.0, anchor="sw")

    # ---------- данные ----------

    def selected_sheet(self):
        sel = self.listbox.curselection()
        return self.sheet_paths[sel[0]] if sel else None

    def refresh_sheets(self):
        """Перечитать input/ и обновить список с числом нарезанных иконок."""
        keep = self.listbox.curselection()
        self.listbox.delete(0, tk.END)
        self.sheet_paths = list_sources()
        for s in self.sheet_paths:
            n = len(list_icon_files(work_dir_for(s) / "opencv"))
            self.listbox.insert(tk.END, f"{s.name}   [{n if n else '-'}]")
        if keep:
            self.listbox.selection_set(keep)

    def on_select(self, _evt=None):
        self.render()

    def render(self):
        """Перерисовать правую область: «Исходник» — в лупе, прочие стадии — сеткой."""
        s = self.selected_sheet()
        if s is None:
            return
        if self.stage_var.get() == "source":
            self.open_view(Image.open(s).convert("RGBA"),
                           from_grid=False, title=f"{s.name} — исходник")
        else:
            self.show_grid(s)

    def stage_folder(self, sheet):
        """Папка-результат текущей стадии для листа (None для 'source')."""
        work = work_dir_for(sheet)
        st = self.stage_var.get()
        if st == "enhanced":
            return work / "enhanced" / self.preset_var.get()
        return work / st   # opencv / defringed

    def show_grid(self, sheet):
        """Сетка миниатюр текущей стадии. Двойной клик по иконке — открыть в лупе."""
        self.enter_grid_mode()
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.thumb_refs.clear()
        wbg = self.widget_bg()
        self.grid_frame.configure(background=wbg)

        label = dict(STAGES)[self.stage_var.get()]
        files = list_icon_files(self.stage_folder(sheet))
        self.title_var.set(f"{sheet.name} — {label.lower()} ({len(files)} иконок)")
        if not files:
            tk.Label(self.grid_frame, background=wbg,
                     text="Здесь пусто — сделай этот шаг кнопкой снизу.").grid(
                row=0, column=0, padx=10, pady=10)
        for i, f in enumerate(files):
            im = Image.open(f).convert("RGBA")
            im.thumbnail((THUMB, THUMB))
            img = self._composite(im)
            self.thumb_refs.append(img)
            cell = tk.Frame(self.grid_frame, background=wbg)
            cell.grid(row=i // COLS, column=i % COLS, padx=6, pady=6)
            lbl = tk.Label(cell, image=img, background=wbg, cursor="hand2")
            lbl.pack()
            lbl.bind("<Double-Button-1>",
                     lambda e, p=f, t=f"{sheet.name} — {f.name}":
                     self.open_view(Image.open(p).convert("RGBA"),
                                    from_grid=True, title=t))
            tk.Label(cell, text=f"{i:03d}", background=wbg, fg="#888").pack()
        # вернуть прокрутку сетки (после лупы scrollregion был обнулён)
        self.grid_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # ---------- лупа (зум + панорама одиночного изображения) ----------

    def enter_grid_mode(self):
        self.mode = "grid"
        if self.view_item is not None:
            self.canvas.delete(self.view_item)
            self.view_item = None
        self.view_pil = None
        self.canvas.itemconfigure(self.grid_window, state="normal")
        self.canvas.configure(cursor="")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def open_view(self, pil, from_grid, title):
        self.mode = "view"
        self.view_pil = pil
        self.view_from_grid = from_grid
        self.canvas.itemconfigure(self.grid_window, state="hidden")
        # лупа рисуется в координатах канвы от (0,0) — гасим прокрутку сетки
        self.canvas.configure(cursor="hand2", scrollregion=(0, 0, 0, 0))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.title_var.set(title)
        self.fit_view()
        self.render_view()
        hint = "Лупа: Ctrl+колёсико — масштаб, ЛКМ — двигать"
        if from_grid:
            hint += ", двойной клик — назад к сетке"
        self.status.set(hint)

    def canvas_size(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        return (w if w > 1 else 760), (h if h > 1 else 460)

    def fit_zoom(self):
        cw, ch = self.canvas_size()
        sw, sh = self.view_pil.size
        return min(cw / sw, ch / sh)

    def fit_view(self):
        cw, ch = self.canvas_size()
        sw, sh = self.view_pil.size
        self.zoom = self.fit_zoom()
        self.img_x = sw / 2 - (cw / self.zoom) / 2
        self.img_y = sh / 2 - (ch / self.zoom) / 2

    def render_view(self):
        if self.view_pil is None:
            return
        cw, ch = self.canvas_size()
        base = self._bg_tile((cw, ch))
        src = self.view_pil
        sw, sh = src.size
        z = self.zoom
        # видимый прямоугольник в координатах изображения
        ix0 = max(0, int(np.floor(self.img_x)))
        iy0 = max(0, int(np.floor(self.img_y)))
        ix1 = min(sw, int(np.ceil(self.img_x + cw / z)))
        iy1 = min(sh, int(np.ceil(self.img_y + ch / z)))
        if ix1 > ix0 and iy1 > iy0:
            crop = src.crop((ix0, iy0, ix1, iy1))
            dw = max(1, int(round((ix1 - ix0) * z)))
            dh = max(1, int(round((iy1 - iy0) * z)))
            # крупный зум — NEAREST (видны реальные пиксели/артефакты), мелкий — LANCZOS
            resample = Image.NEAREST if z >= 2 else Image.LANCZOS
            scaled = crop.resize((dw, dh), resample)
            dx = int(round((ix0 - self.img_x) * z))
            dy = int(round((iy0 - self.img_y) * z))
            base.alpha_composite(scaled, (dx, dy))
        img = ImageTk.PhotoImage(base.convert("RGB"))
        self.thumb_refs = [img]
        if self.view_item is None:
            self.view_item = self.canvas.create_image(0, 0, anchor="nw", image=img)
        else:
            self.canvas.itemconfigure(self.view_item, image=img)
            self.canvas.coords(self.view_item, 0, 0)

    def on_wheel(self, e):
        if self.mode == "grid":
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def on_ctrl_wheel(self, e):
        if self.mode != "view":
            return
        factor = 1.25 if e.delta > 0 else 1 / 1.25
        new = min(self.MAXZOOM, max(self.fit_zoom(), self.zoom * factor))
        # удержать точку под курсором на месте
        ix = self.img_x + e.x / self.zoom
        iy = self.img_y + e.y / self.zoom
        self.zoom = new
        self.img_x = ix - e.x / new
        self.img_y = iy - e.y / new
        self.render_view()

    def on_press(self, e):
        if self.mode == "view":
            self._pan = (e.x, e.y, self.img_x, self.img_y)
            self.canvas.configure(cursor="fleur")

    def on_drag(self, e):
        if self.mode == "view" and self._pan is not None:
            px, py, ox, oy = self._pan
            self.img_x = ox - (e.x - px) / self.zoom
            self.img_y = oy - (e.y - py) / self.zoom
            self.render_view()

    def on_release(self, _e):
        self._pan = None
        if self.mode == "view":
            self.canvas.configure(cursor="hand2")

    def on_canvas_double(self, _e):
        if self.mode == "view" and self.view_from_grid:
            self.show_grid(self.selected_sheet())

    def on_canvas_resize(self, _e):
        if self.mode == "view":
            self.render_view()

    # ---------- подложка-превью ----------

    def widget_bg(self):
        """Hex-цвет фона виджетов под текущую подложку (для шахматки — нейтральный)."""
        key = self.bg_var.get()
        if key == "checker":
            return "#b4b4b4"
        rgb = next(c for k, _l, c in BACKGROUNDS if k == key)
        return "#%02x%02x%02x" % rgb

    def _bg_tile(self, size):
        """RGBA-подложка размера size: сплошной цвет или шахматка."""
        if self.bg_var.get() == "checker":
            w, h = size
            cell = 8
            yy, xx = np.mgrid[0:h, 0:w]
            light = ((xx // cell + yy // cell) % 2).astype(bool)
            arr = np.where(light[..., None],
                           np.array([235, 235, 235], np.uint8),
                           np.array([170, 170, 170], np.uint8))
            return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
        rgb = next(c for k, _l, c in BACKGROUNDS if k == self.bg_var.get())
        return Image.new("RGBA", size, rgb + (255,))

    def _composite(self, im):
        """Положить RGBA-иконку на текущую подложку и вернуть PhotoImage."""
        base = self._bg_tile(im.size)
        base.alpha_composite(im)
        return ImageTk.PhotoImage(base.convert("RGB"))

    def on_bg_change(self):
        self.canvas.configure(background=self.widget_bg())
        if self.mode == "view":
            self.render_view()
        else:
            self.render()

    # ---------- действия ----------

    def on_settings_change(self, _evt=None):
        self.settings["size"] = int(self.size_var.get())
        self.settings["format"] = self.fmt_var.get()
        save_settings(self.settings)

    def _run(self, label, fn):
        """Применить действие fn(лист) к выбранному листу или ко всем (галочка).
        Один механизм для всех кнопок: прогон по очереди + прогресс в статусе.
        Окно на время обработки замирает — фоновый режим в Фазе 3."""
        if self.all_var.get():
            sheets = list(self.sheet_paths)
        else:
            s = self.selected_sheet()
            if s is None:
                self.status.set("Выбери лист слева (или включи «все листы»).")
                return
            sheets = [s]

        total = len(sheets)
        for i, sh in enumerate(sheets, 1):
            self.status.set(f"[{i}/{total}] {label}: «{sh.name}»… (окно замрёт)")
            self.root.update_idletasks()
            try:
                fn(sh)
            except Exception as e:
                self.status.set(f"Ошибка на «{sh.name}»: {e}")
                return
        self.refresh_sheets()
        self.render()
        self.status.set(f"Готово ({label}): листов — {total}" if total > 1
                        else f"Готово ({label}): {sheets[0].name}")

    def cut(self):
        self._run("нарезка", lambda sh: process(
            input_file=sh, output_dir=work_dir_for(sh) / "opencv",
            target_size=self.settings["size"], fmt=self.settings["format"]))

    def do_defringe(self):
        self._run("чистка края",
                  lambda sh: defringe_icons(work_dir_for(sh), self.settings))

    def do_sharpen(self):
        preset = self.preset_var.get()
        self._run(f"резкость:{preset}", lambda sh: enhance.process(
            preset, opencv_dir=work_dir_for(sh) / "opencv",
            output_dir=work_dir_for(sh) / "enhanced"))

    def open_folder(self):
        """Открыть папку текущей стадии выбранного листа (или корень output/)."""
        s = self.selected_sheet()
        if s is None or self.stage_var.get() == "source":
            target = OUTPUT_DIR
        else:
            target = self.stage_folder(s)
        if not target.exists():
            target = OUTPUT_DIR
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(target)


def main():
    root = tk.Tk()
    IconWorkshop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
