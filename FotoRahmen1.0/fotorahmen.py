"""
FotoRahmen – Rahmen um Fotos legen (Stapelverarbeitung mit Vorschau).

Start:  python fotorahmen.py
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

import rahmen_core as core

APP_NAME = "FotoRahmen"
VERSION = "1.0"

PREVIEW_BG = "#5a5a5a"   # neutrales Grau, damit weiße und schwarze Rahmen sichtbar sind

CONFLICT_LABELS = {
    "Nummer anhängen (_2, _3 …)": core.CONFLICT_NUMBER,
    "Überschreiben": core.CONFLICT_OVERWRITE,
    "Überspringen": core.CONFLICT_SKIP,
}

DEFAULTS = {
    "in_dir": "", "out_dir": "", "recursive": False,
    "double": False, "unit": "px",
    "outer_px": "60", "outer_pct": "3", "outer_color": "#ffffff",
    "inner_px": "6", "inner_pct": "0.3", "inner_color": "#000000",
    "format": "Wie Original", "quality": "95",
    "template": "{name}_rahmen",
    "conflict": "Nummer anhängen (_2, _3 …)",
    "geometry": "1280x820",
}


# --- Hilfsfunktionen ------------------------------------------------------------
def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel


def config_file() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME / "einstellungen.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_file().read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict):
    try:
        path = config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def open_folder(path: Path):
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def parse_number(text: str) -> float:
    return float(str(text).strip().replace(",", "."))


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


# --- Farbwahl -------------------------------------------------------------------
class ColorChoice(ttk.Frame):
    """Weiß / Schwarz / eigene Farbe mit Farbfeld zum Anklicken."""

    def __init__(self, master, value: str, on_change):
        super().__init__(master)
        self.on_change = on_change
        value = value.lower()
        self.custom = value if value not in ("#ffffff", "#000000") else "#b08d57"
        self.mode = tk.StringVar(value={"#ffffff": "white", "#000000": "black"}.get(value, "custom"))

        self.rb = [
            ttk.Radiobutton(self, text="Weiß", value="white", variable=self.mode, command=self._changed),
            ttk.Radiobutton(self, text="Schwarz", value="black", variable=self.mode, command=self._changed),
            ttk.Radiobutton(self, text="Farbe", value="custom", variable=self.mode, command=self._changed),
        ]
        for i, rb in enumerate(self.rb):
            rb.grid(row=0, column=i, sticky="w", padx=(0, 10))
        self.swatch = tk.Label(self, width=3, bg=self.custom, relief="solid", bd=1, cursor="hand2")
        self.swatch.grid(row=0, column=3, sticky="w", ipady=1)
        self.swatch.bind("<Button-1>", lambda e: self.pick())
        self.pick_btn = ttk.Button(self, text="Wählen…", command=self.pick, width=8)
        self.pick_btn.grid(row=0, column=4, sticky="w", padx=(6, 0))

    def pick(self):
        if str(self.pick_btn.cget("state")) == "disabled":
            return
        _, hx = colorchooser.askcolor(color=self.custom, title="Rahmenfarbe wählen", parent=self)
        if hx:
            self.custom = hx.lower()
            self.swatch.configure(bg=self.custom)
            self.mode.set("custom")
            self._changed()

    def _changed(self):
        self.on_change()

    def get(self) -> str:
        return {"white": "#ffffff", "black": "#000000"}.get(self.mode.get(), self.custom)

    def set_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for rb in self.rb:
            rb.configure(state=state)
        self.pick_btn.configure(state=state)
        self.swatch.configure(cursor="hand2" if enabled else "arrow")


# --- Hauptfenster ---------------------------------------------------------------
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.files: list[Path] = []
        self.overrides: dict[str, str] = {}
        self.status: dict[str, str] = {}
        self.jobs: list[core.Job] = []
        self.preview_cache: dict[str, tuple] = {}
        self.preview_path: Path | None = None
        self.preview_req = 0
        self.preview_photo = None
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel = threading.Event()
        self._after_ids: dict[str, str] = {}
        self._editor = None

        root.title(f"{APP_NAME} – Rahmen für Fotos")
        root.geometry(self.cfg.get("geometry", DEFAULTS["geometry"]))
        root.minsize(1020, 680)
        self._setup_style()
        self._set_icon()
        self._build_ui()
        self._apply_unit(initial=True)
        self._update_frame_state()
        self.rescan()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._poll_events)

    # ----- Aussehen -----
    def _setup_style(self):
        style = ttk.Style(self.root)
        names = style.theme_names()
        if sys.platform == "win32" and "vista" in names:
            style.theme_use("vista")
        elif sys.platform == "darwin" and "aqua" in names:
            style.theme_use("aqua")
        elif "clam" in names:
            style.theme_use("clam")

        base = 13 if sys.platform == "darwin" else 10
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(size=base)
            except tk.TclError:
                pass
        default = tkfont.nametofont("TkDefaultFont")
        self.font_bold = default.copy()
        self.font_bold.configure(weight="bold")
        self.font_title = default.copy()
        self.font_title.configure(size=base + 5, weight="bold")
        self.font_small = default.copy()
        self.font_small.configure(size=max(base - 1, 8))

        line = default.metrics("linespace")
        style.configure("Treeview", rowheight=line + 8)
        style.configure("Treeview.Heading", font=self.font_bold)
        style.configure("Section.TLabel", font=self.font_bold)
        style.configure("Title.TLabel", font=self.font_title)
        style.configure("Hint.TLabel", font=self.font_small, foreground="#666666")
        style.configure("Start.TButton", font=self.font_bold, padding=(18, 8))
        style.configure("TLabelframe.Label", font=self.font_bold)

    def _set_icon(self):
        try:
            icon = tk.PhotoImage(file=str(resource_path("assets/icon.png")))
            self.root.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            pass

    # ----- Aufbau -----
    def _build_ui(self):
        cfg = self.cfg
        outer = ttk.Frame(self.root, padding=(14, 10, 14, 12))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)

        # Kopfzeile
        head = ttk.Frame(outer)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(head, text="FotoRahmen", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="   Rahmen um Fotos legen – die Originale bleiben unverändert",
                  style="Hint.TLabel").pack(side="left", pady=(6, 0))

        # Ordner
        box = ttk.LabelFrame(outer, text="Ordner", padding=(10, 6))
        box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        box.columnconfigure(1, weight=1)
        self.var_in = tk.StringVar(value=cfg["in_dir"])
        self.var_out = tk.StringVar(value=cfg["out_dir"])
        self.var_rec = tk.BooleanVar(value=cfg["recursive"])
        ttk.Label(box, text="Eingabe-Ordner:").grid(row=0, column=0, sticky="w", pady=3)
        e_in = ttk.Entry(box, textvariable=self.var_in)
        e_in.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(box, text="Durchsuchen…", command=self.choose_in).grid(row=0, column=2)
        ttk.Label(box, text="Ausgabe-Ordner:").grid(row=1, column=0, sticky="w", pady=3)
        e_out = ttk.Entry(box, textvariable=self.var_out)
        e_out.grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(box, text="Durchsuchen…", command=self.choose_out).grid(row=1, column=2)
        row2 = ttk.Frame(box)
        row2.grid(row=2, column=1, sticky="ew", padx=8, pady=(2, 0))
        ttk.Checkbutton(row2, text="Unterordner einbeziehen (Ordnerstruktur wird übernommen)",
                        variable=self.var_rec, command=self.rescan).pack(side="left")
        self.lbl_count = ttk.Label(row2, text="", style="Hint.TLabel")
        self.lbl_count.pack(side="right")
        e_in.bind("<Return>", lambda e: self.rescan())
        e_in.bind("<FocusOut>", lambda e: self.rescan())
        self.var_out.trace_add("write", lambda *a: self._debounce("names", 300, self.refresh_names))

        # Linke Spalte: Einstellungen
        left = ttk.Frame(outer)
        left.grid(row=2, column=0, sticky="nsw", padx=(0, 12))
        self._build_frame_box(left)
        self._build_output_box(left)

        # Rechte Spalte: Vorschau + Liste
        right = ttk.Panedwindow(outer, orient="vertical")
        right.grid(row=2, column=1, sticky="nsew")

        pv = ttk.LabelFrame(right, text="Vorschau", padding=6)
        self.lbl_preview = ttk.Label(pv, text="", style="Hint.TLabel")
        self.lbl_preview.pack(side="bottom", fill="x", pady=(5, 0))
        self.canvas = tk.Canvas(pv, bg=PREVIEW_BG, highlightthickness=0, height=320)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._debounce("render", 60, self.render_preview))
        right.add(pv, weight=3)

        lst = ttk.LabelFrame(right, text="Bilder", padding=6)
        lst.columnconfigure(0, weight=1)
        lst.rowconfigure(0, weight=1)
        cols = ("datei", "ausgabe", "status")
        self.tree = ttk.Treeview(lst, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("datei", text="Originaldatei")
        self.tree.heading("ausgabe", text="Ausgabedatei  (Doppelklick = umbenennen)")
        self.tree.heading("status", text="Status")
        self.tree.column("datei", width=230, anchor="w")
        self.tree.column("ausgabe", width=300, anchor="w")
        self.tree.column("status", width=150, anchor="w", stretch=False)
        self.tree.tag_configure("renamed", foreground="#0b5cad")
        self.tree.tag_configure("ok", foreground="#1d7a2e")
        self.tree.tag_configure("err", foreground="#b3261e")
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select())
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<F2>", lambda e: self.edit_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())
        btns = ttk.Frame(lst)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Ausgabename ändern…", command=self.edit_selected).pack(side="left")
        ttk.Button(btns, text="Eigenen Namen zurücksetzen", command=self.reset_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="Alle zurücksetzen", command=self.reset_all).pack(side="left")
        ttk.Button(btns, text="Liste aktualisieren", command=self.rescan).pack(side="right")
        right.add(lst, weight=2)

        # Fußzeile
        foot = ttk.Frame(outer)
        foot.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        foot.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(foot, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.btn_cancel = ttk.Button(foot, text="Abbrechen", command=self.on_cancel, state="disabled")
        self.btn_cancel.grid(row=0, column=1, padx=(0, 8))
        self.btn_start = ttk.Button(foot, text="Rahmen erstellen", style="Start.TButton",
                                    command=self.start)
        self.btn_start.grid(row=0, column=2)
        self.lbl_status = ttk.Label(foot, text="Bereit.")
        self.lbl_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_frame_box(self, parent):
        cfg = self.cfg
        box = ttk.LabelFrame(parent, text="Rahmen", padding=(10, 6))
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)

        self.var_double = tk.BooleanVar(value=cfg["double"])
        self.var_unit = tk.StringVar(value=cfg["unit"])
        ttk.Label(box, text="Art:").grid(row=0, column=0, sticky="nw", pady=3)
        f = ttk.Frame(box)
        f.grid(row=0, column=1, sticky="w", pady=3)
        ttk.Radiobutton(f, text="Einfacher Rahmen", value=False, variable=self.var_double,
                        command=self._update_frame_state).pack(anchor="w")
        ttk.Radiobutton(f, text="Doppelter Rahmen (innen + außen)", value=True,
                        variable=self.var_double, command=self._update_frame_state).pack(anchor="w")

        ttk.Label(box, text="Breite in:").grid(row=1, column=0, sticky="nw", pady=3)
        f = ttk.Frame(box)
        f.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Radiobutton(f, text="Pixel", value="px", variable=self.var_unit,
                        command=self._apply_unit).pack(anchor="w")
        ttk.Radiobutton(f, text="% der langen Bildkante", value="pct", variable=self.var_unit,
                        command=self._apply_unit).pack(anchor="w")
        ttk.Label(box, text="Prozent: gleich wirkender Rahmen bei unterschiedlich großen Bildern",
                  style="Hint.TLabel", wraplength=330).grid(row=2, column=0, columnspan=2,
                                                            sticky="w", pady=(0, 4))

        ttk.Separator(box).grid(row=3, column=0, columnspan=2, sticky="ew", pady=6)

        self.lbl_outer = ttk.Label(box, text="Rahmen", style="Section.TLabel")
        self.lbl_outer.grid(row=4, column=0, columnspan=2, sticky="w")
        self.var_outer_w = tk.StringVar()
        self.sp_outer, self.lbl_outer_unit = self._width_row(box, 5, self.var_outer_w)
        ttk.Label(box, text="Farbe:").grid(row=6, column=0, sticky="w", pady=3)
        self.col_outer = ColorChoice(box, cfg["outer_color"], self.on_settings_changed)
        self.col_outer.grid(row=6, column=1, sticky="w", pady=3)

        ttk.Separator(box).grid(row=7, column=0, columnspan=2, sticky="ew", pady=6)

        self.lbl_inner = ttk.Label(box, text="Innerer Rahmen (direkt am Bild)", style="Section.TLabel")
        self.lbl_inner.grid(row=8, column=0, columnspan=2, sticky="w")
        self.var_inner_w = tk.StringVar()
        self.sp_inner, self.lbl_inner_unit = self._width_row(box, 9, self.var_inner_w)
        self.lbl_inner_col = ttk.Label(box, text="Farbe:")
        self.lbl_inner_col.grid(row=10, column=0, sticky="w", pady=3)
        self.col_inner = ColorChoice(box, cfg["inner_color"], self.on_settings_changed)
        self.col_inner.grid(row=10, column=1, sticky="w", pady=3)

    def _width_row(self, box, row, var):
        ttk.Label(box, text="Breite:").grid(row=row, column=0, sticky="w", pady=3)
        f = ttk.Frame(box)
        f.grid(row=row, column=1, sticky="w", pady=3)
        sp = ttk.Spinbox(f, textvariable=var, width=8, from_=0, to=10000, increment=1,
                         command=self.on_settings_changed)
        sp.pack(side="left")
        unit = ttk.Label(f, text="px")
        unit.pack(side="left", padx=(6, 0))
        var.trace_add("write", lambda *a: self.on_settings_changed())
        return sp, unit

    def _build_output_box(self, parent):
        cfg = self.cfg
        box = ttk.LabelFrame(parent, text="Ausgabe", padding=(10, 6))
        box.pack(fill="x", pady=(10, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Format:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_format = tk.StringVar(value=cfg["format"] if cfg["format"] in core.OUTPUT_FORMATS
                                       else "Wie Original")
        cb = ttk.Combobox(box, textvariable=self.var_format, values=list(core.OUTPUT_FORMATS),
                          state="readonly", width=24)
        cb.grid(row=0, column=1, sticky="w", pady=3)
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_settings_changed())

        ttk.Label(box, text="JPEG-Qualität:").grid(row=1, column=0, sticky="w", pady=3)
        f = ttk.Frame(box)
        f.grid(row=1, column=1, sticky="w", pady=3)
        self.var_quality = tk.StringVar(value=cfg["quality"])
        ttk.Spinbox(f, textvariable=self.var_quality, from_=50, to=100, increment=1,
                    width=6).pack(side="left")
        ttk.Label(f, text="(50–100, empfohlen 92–95)", style="Hint.TLabel").pack(side="left", padx=6)

        ttk.Label(box, text="Dateiname:").grid(row=2, column=0, sticky="w", pady=3)
        self.var_template = tk.StringVar(value=cfg["template"])
        ttk.Entry(box, textvariable=self.var_template, width=26).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(box, text="Platzhalter: {name} = Originalname, {nr} = 001, 002 …,\n"
                            "{datum} = heutiges Datum.  Einzelne Namen in der Liste änderbar.",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")
        self.var_template.trace_add("write", lambda *a: self._debounce("names", 250, self.refresh_names))

        ttk.Label(box, text="Datei existiert:").grid(row=4, column=0, sticky="w", pady=(6, 3))
        self.var_conflict = tk.StringVar(value=cfg["conflict"] if cfg["conflict"] in CONFLICT_LABELS
                                         else DEFAULTS["conflict"])
        cb2 = ttk.Combobox(box, textvariable=self.var_conflict, values=list(CONFLICT_LABELS),
                           state="readonly", width=28)
        cb2.grid(row=4, column=1, sticky="w", pady=(6, 3))
        cb2.bind("<<ComboboxSelected>>", lambda e: self.refresh_names())

    # ----- Einstellungen -----
    def _apply_unit(self, initial=False):
        unit = self.var_unit.get()
        if not initial:   # Werte der bisherigen Einheit merken
            prev = "pct" if unit == "px" else "px"
            self.cfg[f"outer_{prev}"] = self.var_outer_w.get()
            self.cfg[f"inner_{prev}"] = self.var_inner_w.get()
        if unit == "pct":
            for sp in (self.sp_outer, self.sp_inner):
                sp.configure(from_=0, to=50, increment=0.1, format="%.1f")
            label = "% der langen Kante"
        else:
            for sp in (self.sp_outer, self.sp_inner):
                sp.configure(from_=0, to=10000, increment=1, format="%.0f")
            label = "px"
        self.var_outer_w.set(self.cfg[f"outer_{unit}"])
        self.var_inner_w.set(self.cfg[f"inner_{unit}"])
        self.lbl_outer_unit.configure(text=label)
        self.lbl_inner_unit.configure(text=label)
        self.on_settings_changed()

    def _update_frame_state(self):
        double = self.var_double.get()
        self.lbl_outer.configure(text="Äußerer Rahmen" if double else "Rahmen")
        state = "normal" if double else "disabled"
        self.sp_inner.configure(state=state)
        self.col_inner.set_enabled(double)
        for w in (self.lbl_inner, self.lbl_inner_unit, self.lbl_inner_col):
            w.configure(foreground="" if double else "#9a9a9a")
        self.on_settings_changed()

    def get_settings(self) -> core.FrameSettings:
        def num(var, name):
            try:
                v = parse_number(var.get())
            except ValueError:
                raise ValueError(f"Bitte eine Zahl für die Breite des {name} eingeben.")
            if v < 0:
                raise ValueError(f"Die Breite des {name} darf nicht negativ sein.")
            return v
        return core.FrameSettings(
            double=self.var_double.get(),
            unit=self.var_unit.get(),
            outer_width=num(self.var_outer_w, "äußeren Rahmens" if self.var_double.get() else "Rahmens"),
            outer_color=core.hex_to_rgb(self.col_outer.get()),
            inner_width=num(self.var_inner_w, "inneren Rahmens") if self.var_double.get() else 0,
            inner_color=core.hex_to_rgb(self.col_inner.get()),
        )

    def on_settings_changed(self):
        if not hasattr(self, "canvas"):
            return
        self._debounce("render", 120, self.render_preview)

    def _debounce(self, key, ms, func):
        if key in self._after_ids:
            self.root.after_cancel(self._after_ids[key])
        self._after_ids[key] = self.root.after(ms, func)

    def collect_config(self) -> dict:
        unit = self.var_unit.get()
        cfg = dict(self.cfg)
        cfg.update({
            "in_dir": self.var_in.get(), "out_dir": self.var_out.get(),
            "recursive": self.var_rec.get(), "double": self.var_double.get(), "unit": unit,
            f"outer_{unit}": self.var_outer_w.get(), f"inner_{unit}": self.var_inner_w.get(),
            "outer_color": self.col_outer.get(), "inner_color": self.col_inner.get(),
            "format": self.var_format.get(), "quality": self.var_quality.get(),
            "template": self.var_template.get(), "conflict": self.var_conflict.get(),
            "geometry": self.root.geometry(),
        })
        return cfg

    # ----- Ordner & Liste -----
    def choose_in(self):
        d = filedialog.askdirectory(title="Eingabe-Ordner wählen", initialdir=self.var_in.get() or None)
        if d:
            self.var_in.set(d)
            if not self.var_out.get():
                self.var_out.set(str(Path(d) / "mit Rahmen"))
            self.rescan()

    def choose_out(self):
        d = filedialog.askdirectory(title="Ausgabe-Ordner wählen",
                                    initialdir=self.var_out.get() or self.var_in.get() or None)
        if d:
            self.var_out.set(d)
            self.rescan()

    def _out_dir(self) -> Path | None:
        t = self.var_out.get().strip()
        return Path(t) if t else None

    def rescan(self):
        if self.worker and self.worker.is_alive():
            return
        in_dir = Path(self.var_in.get().strip()) if self.var_in.get().strip() else None
        old = [str(f) for f in self.files]
        if in_dir and in_dir.is_dir():
            self.files = core.scan_images(in_dir, self.var_rec.get(), exclude=self._out_dir())
        else:
            self.files = []
        same = [str(f) for f in self.files] == old
        if not same:
            self.status.clear()
        n = len(self.files)
        if not in_dir:
            self.lbl_count.configure(text="Bitte einen Eingabe-Ordner wählen")
        elif not in_dir.is_dir():
            self.lbl_count.configure(text="Ordner nicht gefunden")
        else:
            self.lbl_count.configure(text=f"{n} Bild{'er' if n != 1 else ''} gefunden")
        self.refresh_names(keep_selection=same)

    def refresh_names(self, keep_selection=True):
        sel = self.tree.selection()
        sel_id = sel[0] if (sel and keep_selection) else None
        self.tree.delete(*self.tree.get_children())
        in_dir = Path(self.var_in.get().strip() or ".")
        out_dir = self._out_dir()
        if out_dir:
            self.jobs = core.plan_jobs(self.files, in_dir, out_dir, self.var_template.get(),
                                       self.overrides, self.var_format.get(),
                                       CONFLICT_LABELS[self.var_conflict.get()])
        else:
            self.jobs = [core.Job(f, Path("?") / f.name) for f in self.files]
        for i, job in enumerate(self.jobs):
            try:
                src_label = str(job.src.relative_to(in_dir))
                dst_label = str(job.dst.relative_to(out_dir)) if out_dir else "– Ausgabe-Ordner fehlt –"
            except ValueError:
                src_label, dst_label = job.src.name, job.dst.name
            st = self.status.get(str(job.src), "übersprungen (existiert)" if job.skip else "bereit")
            tags = []
            if str(job.src) in self.overrides:
                tags.append("renamed")
            if st.startswith("fertig"):
                tags = ["ok"]
            elif st.startswith("Fehler"):
                tags = ["err"]
            self.tree.insert("", "end", iid=str(i), values=(src_label, dst_label, st), tags=tags)
        if self.jobs:
            target = sel_id if sel_id and self.tree.exists(sel_id) else "0"
            self.tree.selection_set(target)
            self.tree.see(target)
        else:
            self.preview_path = None
            self.render_preview()

    def on_select(self):
        sel = self.tree.selection()
        if not sel:
            return
        job = self.jobs[int(sel[0])]
        if job.src != self.preview_path:
            self.preview_path = job.src
            self.load_preview(job.src)

    # ----- Umbenennen -----
    def on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.edit_selected()

    def edit_selected(self):
        if self.worker and self.worker.is_alive():
            return
        sel = self.tree.selection()
        if not sel or not self._out_dir():
            return
        iid = sel[0]
        job = self.jobs[int(iid)]
        self.tree.see(iid)
        self.root.update_idletasks()
        bbox = self.tree.bbox(iid, "ausgabe")
        if not bbox:
            return
        x, y, w, h = bbox
        if self._editor:
            self._editor.destroy()
        var = tk.StringVar(value=job.dst.stem)
        ent = ttk.Entry(self.tree, textvariable=var)
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()
        ent.select_range(0, "end")
        self._editor = ent

        done = {"flag": False}

        def commit(_=None):
            if done["flag"]:
                return
            done["flag"] = True
            name = core.sanitize_stem(var.get())
            ent.destroy()
            self._editor = None
            if name and name != job.dst.stem:
                self.overrides[str(job.src)] = name
                self.refresh_names()
            self.tree.focus_set()

        def cancel(_=None):
            if done["flag"]:
                return
            done["flag"] = True
            ent.destroy()
            self._editor = None
            self.tree.focus_set()

        ent.bind("<Return>", commit)
        ent.bind("<KP_Enter>", commit)
        ent.bind("<Escape>", cancel)
        ent.bind("<FocusOut>", commit)

    def reset_selected(self):
        sel = self.tree.selection()
        if sel:
            self.overrides.pop(str(self.jobs[int(sel[0])].src), None)
            self.refresh_names()

    def reset_all(self):
        self.overrides.clear()
        self.refresh_names()

    # ----- Vorschau -----
    def load_preview(self, path: Path):
        key = str(path)
        if key in self.preview_cache:
            self.render_preview()
            return
        self.preview_req += 1
        req = self.preview_req
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                text="Vorschau wird geladen …", fill="#e8e8e8",
                                font=self.font_bold)

        def work():
            try:
                thumb, size = core.load_preview(path)
                self.events.put(("preview", req, key, thumb, size, None))
            except Exception as exc:
                self.events.put(("preview", req, key, None, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def render_preview(self):
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 20 or ch < 20:
            return
        if not self.preview_path:
            self.canvas.create_text(cw // 2, ch // 2, fill="#e8e8e8", font=self.font_bold,
                                    text="Keine Bilder – bitte einen Eingabe-Ordner wählen")
            self.lbl_preview.configure(text="")
            return
        entry = self.preview_cache.get(str(self.preview_path))
        if not entry:
            return
        thumb, size, error = entry
        if error:
            self.canvas.create_text(cw // 2, ch // 2, fill="#ffb4ab", font=self.font_bold,
                                    text=f"Bild kann nicht gelesen werden:\n{error}", justify="center")
            self.lbl_preview.configure(text="")
            return
        try:
            settings = self.get_settings()
        except ValueError as exc:
            self.lbl_preview.configure(text=str(exc))
            return
        pad = 16
        img = core.render_preview(thumb, size, settings, cw - 2 * pad, ch - 2 * pad)
        self.preview_photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(cw // 2, ch // 2, image=self.preview_photo, anchor="center")
        w, h = size
        t = settings.total(w, h)
        self.lbl_preview.configure(
            text=f"{self.preview_path.name}:   {w} × {h} px   →   mit Rahmen {w + 2 * t} × {h + 2 * t} px"
                 f"   (Rahmen gesamt {t} px je Seite)")

    # ----- Verarbeitung -----
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        in_txt, out_txt = self.var_in.get().strip(), self.var_out.get().strip()
        if not in_txt or not Path(in_txt).is_dir():
            messagebox.showwarning(APP_NAME, "Bitte einen gültigen Eingabe-Ordner wählen.")
            return
        if not out_txt:
            messagebox.showwarning(APP_NAME, "Bitte einen Ausgabe-Ordner wählen.")
            return
        in_dir, out_dir = Path(in_txt).resolve(), Path(out_txt).resolve()
        if in_dir == out_dir:
            messagebox.showwarning(APP_NAME, "Eingabe- und Ausgabe-Ordner müssen verschieden sein,\n"
                                             "damit die Originale sicher unverändert bleiben.")
            return
        try:
            settings = self.get_settings()
            quality = int(parse_number(self.var_quality.get()))
            if not 1 <= quality <= 100:
                raise ValueError("Die JPEG-Qualität muss zwischen 1 und 100 liegen.")
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return
        if not settings.layers(1000, 1000):
            if not messagebox.askyesno(APP_NAME, "Die Rahmenbreite ist 0 – die Bilder würden nur "
                                                 "kopiert/umgewandelt. Trotzdem fortfahren?"):
                return
        self.rescan()
        if not self.jobs:
            messagebox.showinfo(APP_NAME, "Im Eingabe-Ordner wurden keine Bilder gefunden.")
            return
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Ausgabe-Ordner kann nicht angelegt werden:\n{exc}")
            return
        if CONFLICT_LABELS[self.var_conflict.get()] == core.CONFLICT_OVERWRITE:
            existing = sum(1 for j in self.jobs if j.dst.exists())
            if existing and not messagebox.askyesno(
                    APP_NAME, f"{existing} Datei(en) im Ausgabe-Ordner werden überschrieben.\nFortfahren?"):
                return

        save_config(self.collect_config())
        jobs = list(self.jobs)
        self.status.clear()
        self.cancel.clear()
        self._set_busy(True)
        self.progress.configure(maximum=len(jobs), value=0)
        self.lbl_status.configure(text=f"Starte Verarbeitung von {len(jobs)} Bildern …")

        def work():
            ok = err = skipped = 0
            for i, job in enumerate(jobs):
                if self.cancel.is_set():
                    break
                self.events.put(("progress", i, job.src.name, len(jobs)))
                if job.skip:
                    skipped += 1
                    self.events.put(("item", i, "übersprungen (existiert)"))
                    continue
                try:
                    w, h = core.process_file(job.src, job.dst, settings, quality)
                    ok += 1
                    self.events.put(("item", i, f"fertig  ✓  {w}×{h}"))
                except Exception as exc:
                    err += 1
                    self.events.put(("item", i, f"Fehler: {exc}"))
            self.events.put(("done", ok, err, skipped, self.cancel.is_set(), out_dir))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def on_cancel(self):
        self.cancel.set()
        self.lbl_status.configure(text="Wird nach dem aktuellen Bild abgebrochen …")

    def _set_busy(self, busy: bool):
        self.btn_start.configure(state="disabled" if busy else "normal")
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "preview":
                    _, req, key, thumb, size, error = ev
                    self.preview_cache[key] = (thumb, size, error)
                    if len(self.preview_cache) > 12:
                        self.preview_cache.pop(next(iter(self.preview_cache)))
                    if self.preview_path and str(self.preview_path) == key:
                        self.render_preview()
                elif kind == "progress":
                    _, i, name, total = ev
                    self.progress.configure(value=i)
                    self.lbl_status.configure(text=f"Bild {i + 1} von {total}: {name}")
                    if self.tree.exists(str(i)):
                        self.tree.set(str(i), "status", "in Arbeit …")
                        self.tree.see(str(i))
                elif kind == "item":
                    _, i, text = ev
                    self.progress.configure(value=i + 1)
                    self.status[str(self.jobs[i].src)] = text
                    if self.tree.exists(str(i)):
                        self.tree.set(str(i), "status", text)
                        tag = "ok" if text.startswith("fertig") else "err" if text.startswith("Fehler") else ""
                        self.tree.item(str(i), tags=(tag,) if tag else ())
                elif kind == "done":
                    self._finish(*ev[1:])
        except queue.Empty:
            pass
        self.root.after(80, self._poll_events)

    def _finish(self, ok, err, skipped, cancelled, out_dir):
        self._set_busy(False)
        parts = [f"{ok} Bild{'er' if ok != 1 else ''} mit Rahmen gespeichert"]
        if skipped:
            parts.append(f"{skipped} übersprungen")
        if err:
            parts.append(f"{err} Fehler")
        text = ", ".join(parts) + "."
        if cancelled:
            text = "Abgebrochen. " + text
        self.lbl_status.configure(text=text)
        if messagebox.askyesno(APP_NAME, text + "\n\nAusgabe-Ordner jetzt öffnen?"):
            open_folder(out_dir)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, "Die Verarbeitung läuft noch. Wirklich beenden?"):
                return
            self.cancel.set()
        save_config(self.collect_config())
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
