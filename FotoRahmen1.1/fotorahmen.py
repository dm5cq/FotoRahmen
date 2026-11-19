# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3. November 2026
# Lizenz: MIT – siehe Datei LICENSE
# -----------------------------------------------------------------------------
"""FotoRahmen – Oberfläche (Tkinter).

Start aus dem Quellcode:  ``python fotorahmen.py``

Aufbau
======
* ``ColorChoice`` – Bedienelement Weiß / Schwarz / eigene Farbe
* ``App``         – Hauptfenster

  - ``_build_*``          Aufbau der Bereiche (Ordner, Rahmen, Ausgabe, Vorschau, Liste)
  - ``get_settings``      liest die Bedienelemente -> ``rahmen_core.FrameSettings``
  - ``rescan`` / ``refresh_names``  Dateiliste und geplante Ausgabenamen
  - ``load_preview`` / ``render_preview``  Vorschau (Laden im Hintergrund-Thread)
  - ``start`` / ``_poll_events``  Stapelverarbeitung im Hintergrund-Thread

Threads
=======
Bildladen und Verarbeitung laufen in Hintergrund-Threads. Diese greifen nie
direkt auf Tk-Widgets zu, sondern legen Nachrichten in ``self.events`` ab;
``_poll_events`` verarbeitet sie alle 80 ms im Haupt-Thread.
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

from PIL import ImageTk

import app_info
import rahmen_core as core

APP_NAME = app_info.APP_NAME
PREVIEW_BG = "#5a5a5a"   # neutrales Grau, damit weiße und schwarze Rahmen sichtbar sind

CONFLICT_LABELS = {
    "Nummer anhängen (_2, _3 …)": core.CONFLICT_NUMBER,
    "Überschreiben": core.CONFLICT_OVERWRITE,
    "Überspringen": core.CONFLICT_SKIP,
}

#: Standardwerte; werden durch die gespeicherten Einstellungen überschrieben.
DEFAULTS = {
    "in_dir": "", "out_dir": "", "recursive": False,
    "double": False, "unit": "px",
    "outer_px": "60", "outer_pct": "3", "outer_color": "#ffffff",
    "inner_px": "6", "inner_pct": "0.3", "inner_color": "#000000",
    "bottom_px": "0", "bottom_pct": "0",
    "format": "Wie Original", "quality": "95",
    "template": "{name}_rahmen",
    "conflict": "Nummer anhängen (_2, _3 …)",
    "size": "",
}


# =============================================================================
# Hilfsfunktionen
# =============================================================================
def resource_path(rel: str) -> Path:
    """Pfad zu mitgelieferten Dateien – auch in der gepackten EXE/App."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel


def config_file() -> Path:
    """Ort der Einstellungsdatei je Betriebssystem."""
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
        stored = json.loads(config_file().read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in stored.items() if k in DEFAULTS})
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
    """Ordner im Explorer/Finder öffnen."""
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
    """Zahl mit Komma oder Punkt einlesen ('0,5' -> 0.5)."""
    return float(str(text).strip().replace(",", "."))


def enable_dpi_awareness():
    """Windows: scharfe Darstellung bei Bildschirm-Skalierung 125 % / 150 % …"""
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


# =============================================================================
# Farbwahl
# =============================================================================
class ColorChoice(ttk.Frame):
    """Weiß / Schwarz / eigene Farbe; das Farbfeld öffnet den Farbwähler."""

    def __init__(self, master, value: str, on_change):
        super().__init__(master)
        self.on_change = on_change
        value = value.lower()
        self.custom = value if value not in ("#ffffff", "#000000") else "#b08d57"
        self.mode = tk.StringVar(value={"#ffffff": "white", "#000000": "black"}.get(value, "custom"))
        self.enabled = True

        self.rb = [
            ttk.Radiobutton(self, text="Weiß", value="white", variable=self.mode, command=on_change),
            ttk.Radiobutton(self, text="Schwarz", value="black", variable=self.mode, command=on_change),
            ttk.Radiobutton(self, text="Farbe", value="custom", variable=self.mode, command=on_change),
        ]
        for i, rb in enumerate(self.rb):
            rb.grid(row=0, column=i, sticky="w", padx=(0, 10))
        self.swatch = tk.Label(self, width=3, bg=self.custom, relief="solid", bd=1, cursor="hand2")
        self.swatch.grid(row=0, column=3, sticky="w", ipady=1)
        self.swatch.bind("<Button-1>", lambda e: self.pick())
        self.pick_btn = ttk.Button(self, text="Wählen…", command=self.pick, width=8)
        self.pick_btn.grid(row=0, column=4, sticky="w", padx=(6, 0))

    def pick(self):
        if not self.enabled:
            return
        _, hx = colorchooser.askcolor(color=self.custom, title="Rahmenfarbe wählen", parent=self)
        if hx:
            self.custom = hx.lower()
            self.swatch.configure(bg=self.custom)
            self.mode.set("custom")
            self.on_change()

    def get(self) -> str:
        """Gewählte Farbe als '#rrggbb'."""
        return {"white": "#ffffff", "black": "#000000"}.get(self.mode.get(), self.custom)

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        for w in (*self.rb, self.pick_btn):
            w.state(["!disabled"] if enabled else ["disabled"])
        self.swatch.configure(cursor="hand2" if enabled else "arrow")


# =============================================================================
# Hauptfenster
# =============================================================================
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.files: list[Path] = []
        self.overrides: dict[str, str] = {}   # str(Quellpfad) -> eigener Ausgabename
        self.status: dict[str, str] = {}      # str(Quellpfad) -> Statustext
        self.jobs: list[core.Job] = []
        self.preview_cache: dict[str, tuple] = {}
        self.preview_path: Path | None = None
        self.preview_photo = None
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel = threading.Event()
        self.busy = False
        self._after_ids: dict[str, str] = {}
        self._editor = None
        self._lockable: list = []             # Widgets, die während der Verarbeitung gesperrt sind

        # Skalierung für hochauflösende Windows-/Linux-Bildschirme
        self.ui = 1.0
        if sys.platform != "darwin":
            try:
                self.ui = max(1.0, root.winfo_fpixels("1i") / 96.0)
            except tk.TclError:
                pass

        root.title(f"{APP_NAME} {app_info.VERSION} – Rahmen für Fotos")
        root.geometry(self.cfg.get("size") or f"{self.px(1280)}x{self.px(840)}")
        root.minsize(self.px(1040), self.px(700))
        self._setup_style()
        self._set_icon()
        self._build_ui()
        self._apply_unit(initial=True)
        self._update_frame_state()
        self.rescan()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Control-Return>", lambda e: self.start())
        root.bind_all("<Command-Return>" if sys.platform == "darwin" else "<Control-KP_Enter>",
                      lambda e: self.start())
        root.after(100, self._poll_events)

    def px(self, value: float) -> int:
        """Pixelmaß an die Bildschirm-Skalierung anpassen."""
        return int(round(value * self.ui))

    # ------------------------------------------------------------------ Aussehen
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
        style.configure("Treeview", rowheight=line + self.px(8))
        style.configure("Treeview.Heading", font=self.font_bold)
        style.configure("Section.TLabel", font=self.font_bold)
        style.configure("Title.TLabel", font=self.font_title)
        style.configure("Hint.TLabel", font=self.font_small, foreground="#5f5f5f")
        style.configure("Start.TButton", font=self.font_bold, padding=(self.px(18), self.px(8)))
        style.configure("TLabelframe.Label", font=self.font_bold)

    def _set_icon(self):
        try:
            icon = tk.PhotoImage(file=str(resource_path("assets/icon.png")))
            self.root.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            pass

    # ------------------------------------------------------------------ Aufbau
    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=(self.px(14), self.px(10), self.px(14), self.px(12)))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)

        head = ttk.Frame(outer)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, self.px(8)))
        ttk.Label(head, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="   Rahmen um Fotos legen – die Originale bleiben unverändert",
                  style="Hint.TLabel").pack(side="left", pady=(self.px(6), 0))
        ttk.Button(head, text="Info", command=self.show_about).pack(side="right")

        self._build_folder_box(outer)

        left = ttk.Frame(outer)
        left.grid(row=2, column=0, sticky="nsw", padx=(0, self.px(12)))
        self._build_frame_box(left)
        self._build_output_box(left)

        right = ttk.Panedwindow(outer, orient="vertical")
        right.grid(row=2, column=1, sticky="nsew")
        self._build_preview(right)
        self._build_list(right)
        self._build_footer(outer)

    def _lock(self, *widgets):
        self._lockable.extend(widgets)
        return widgets[0] if widgets else None

    def _build_folder_box(self, parent):
        cfg = self.cfg
        box = ttk.LabelFrame(parent, text="Ordner", padding=(self.px(10), self.px(6)))
        box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, self.px(10)))
        box.columnconfigure(1, weight=1)
        self.var_in = tk.StringVar(value=cfg["in_dir"])
        self.var_out = tk.StringVar(value=cfg["out_dir"])
        self.var_rec = tk.BooleanVar(value=bool(cfg["recursive"]))

        ttk.Label(box, text="Eingabe-Ordner:").grid(row=0, column=0, sticky="w", pady=3)
        e_in = self._lock(ttk.Entry(box, textvariable=self.var_in))
        e_in.grid(row=0, column=1, sticky="ew", padx=self.px(8))
        self._lock(ttk.Button(box, text="Durchsuchen…", command=self.choose_in)).grid(row=0, column=2)
        ttk.Label(box, text="Ausgabe-Ordner:").grid(row=1, column=0, sticky="w", pady=3)
        e_out = self._lock(ttk.Entry(box, textvariable=self.var_out))
        e_out.grid(row=1, column=1, sticky="ew", padx=self.px(8))
        self._lock(ttk.Button(box, text="Durchsuchen…", command=self.choose_out)).grid(row=1, column=2)

        row2 = ttk.Frame(box)
        row2.grid(row=2, column=1, sticky="ew", padx=self.px(8), pady=(2, 0))
        self._lock(ttk.Checkbutton(row2, text="Unterordner einbeziehen (Ordnerstruktur wird übernommen)",
                                   variable=self.var_rec, command=self.rescan)).pack(side="left")
        self.lbl_count = ttk.Label(row2, text="", style="Hint.TLabel")
        self.lbl_count.pack(side="right")

        e_in.bind("<Return>", lambda e: self.rescan())
        e_in.bind("<FocusOut>", lambda e: self.rescan())
        e_out.bind("<Return>", lambda e: self.rescan())
        self.var_out.trace_add("write", lambda *a: self._debounce("names", 300, self.refresh_names))

    def _build_frame_box(self, parent):
        cfg = self.cfg
        box = ttk.LabelFrame(parent, text="Rahmen", padding=(self.px(10), self.px(6)))
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)

        self.var_double = tk.BooleanVar(value=bool(cfg["double"]))
        self.var_unit = tk.StringVar(value=cfg["unit"] if cfg["unit"] in ("px", "pct") else "px")
        ttk.Label(box, text="Art:").grid(row=0, column=0, sticky="nw", pady=3)
        f = ttk.Frame(box)
        f.grid(row=0, column=1, sticky="w", pady=3)
        self._lock(ttk.Radiobutton(f, text="Einfacher Rahmen", value=False, variable=self.var_double,
                                   command=self._update_frame_state)).pack(anchor="w")
        self._lock(ttk.Radiobutton(f, text="Doppelter Rahmen (innen + außen)", value=True,
                                   variable=self.var_double,
                                   command=self._update_frame_state)).pack(anchor="w")

        ttk.Label(box, text="Breite in:").grid(row=1, column=0, sticky="nw", pady=3)
        f = ttk.Frame(box)
        f.grid(row=1, column=1, sticky="w", pady=3)
        self._lock(ttk.Radiobutton(f, text="Pixel", value="px", variable=self.var_unit,
                                   command=self._apply_unit)).pack(anchor="w")
        self._lock(ttk.Radiobutton(f, text="% der langen Bildkante", value="pct",
                                   variable=self.var_unit, command=self._apply_unit)).pack(anchor="w")
        ttk.Label(box, text="Prozent: gleich wirkender Rahmen bei unterschiedlich großen Bildern",
                  style="Hint.TLabel", wraplength=self.px(330)).grid(row=2, column=0, columnspan=2,
                                                                     sticky="w", pady=(0, 4))

        ttk.Separator(box).grid(row=3, column=0, columnspan=2, sticky="ew", pady=self.px(6))
        self.lbl_outer = ttk.Label(box, text="Rahmen", style="Section.TLabel")
        self.lbl_outer.grid(row=4, column=0, columnspan=2, sticky="w")
        self.var_outer_w = tk.StringVar()
        self.sp_outer, self.lbl_outer_unit = self._number_row(box, 5, "Breite:", self.var_outer_w)
        self.var_bottom = tk.StringVar()
        self.sp_bottom, self.lbl_bottom_unit = self._number_row(box, 6, "Unten extra:", self.var_bottom)
        ttk.Label(box, text="Farbe:").grid(row=7, column=0, sticky="w", pady=3)
        self.col_outer = ColorChoice(box, cfg["outer_color"], self.on_settings_changed)
        self.col_outer.grid(row=7, column=1, sticky="w", pady=3)

        ttk.Separator(box).grid(row=8, column=0, columnspan=2, sticky="ew", pady=self.px(6))
        self.lbl_inner = ttk.Label(box, text="Innerer Rahmen (direkt am Bild)", style="Section.TLabel")
        self.lbl_inner.grid(row=9, column=0, columnspan=2, sticky="w")
        self.var_inner_w = tk.StringVar()
        self.sp_inner, self.lbl_inner_unit = self._number_row(box, 10, "Breite:", self.var_inner_w)
        self.lbl_inner_col = ttk.Label(box, text="Farbe:")
        self.lbl_inner_col.grid(row=11, column=0, sticky="w", pady=3)
        self.col_inner = ColorChoice(box, cfg["inner_color"], self.on_settings_changed)
        self.col_inner.grid(row=11, column=1, sticky="w", pady=3)

    def _number_row(self, box, row, label, var):
        """Zeile 'Beschriftung: [Zahlenfeld] Einheit'."""
        ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", pady=3)
        f = ttk.Frame(box)
        f.grid(row=row, column=1, sticky="w", pady=3)
        sp = ttk.Spinbox(f, textvariable=var, width=8, from_=0, to=10000, increment=1,
                         command=self.on_settings_changed)
        sp.pack(side="left")
        self._lock(sp)
        unit = ttk.Label(f, text="px")
        unit.pack(side="left", padx=(self.px(6), 0))
        var.trace_add("write", lambda *a: self.on_settings_changed())
        return sp, unit

    def _build_output_box(self, parent):
        cfg = self.cfg
        box = ttk.LabelFrame(parent, text="Ausgabe", padding=(self.px(10), self.px(6)))
        box.pack(fill="x", pady=(self.px(10), 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Format:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_format = tk.StringVar(value=cfg["format"] if cfg["format"] in core.OUTPUT_FORMATS
                                       else "Wie Original")
        cb = self._lock(ttk.Combobox(box, textvariable=self.var_format, values=list(core.OUTPUT_FORMATS),
                                     state="readonly", width=24))
        cb.grid(row=0, column=1, sticky="w", pady=3)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_names())

        ttk.Label(box, text="Qualität:").grid(row=1, column=0, sticky="w", pady=3)
        f = ttk.Frame(box)
        f.grid(row=1, column=1, sticky="w", pady=3)
        self.var_quality = tk.StringVar(value=cfg["quality"])
        self._lock(ttk.Spinbox(f, textvariable=self.var_quality, from_=50, to=100, increment=1,
                               width=6)).pack(side="left")
        ttk.Label(f, text="JPEG/WebP/HEIC, 50–100 (empfohlen 92–95)",
                  style="Hint.TLabel").pack(side="left", padx=self.px(6))

        ttk.Label(box, text="Dateiname:").grid(row=2, column=0, sticky="w", pady=3)
        self.var_template = tk.StringVar(value=cfg["template"])
        self._lock(ttk.Entry(box, textvariable=self.var_template, width=26)).grid(
            row=2, column=1, sticky="ew", pady=3)
        ttk.Label(box, text="Platzhalter: {name} = Originalname, {nr} = 001, 002 …,\n"
                            "{datum} = heutiges Datum.  Einzelne Namen in der Liste änderbar.",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")
        self.var_template.trace_add("write", lambda *a: self._debounce("names", 250, self.refresh_names))

        ttk.Label(box, text="Datei existiert:").grid(row=4, column=0, sticky="w", pady=(self.px(6), 3))
        self.var_conflict = tk.StringVar(value=cfg["conflict"] if cfg["conflict"] in CONFLICT_LABELS
                                         else DEFAULTS["conflict"])
        cb2 = self._lock(ttk.Combobox(box, textvariable=self.var_conflict, values=list(CONFLICT_LABELS),
                                      state="readonly", width=28))
        cb2.grid(row=4, column=1, sticky="w", pady=(self.px(6), 3))
        cb2.bind("<<ComboboxSelected>>", lambda e: self.refresh_names())

    def _build_preview(self, paned):
        pv = ttk.LabelFrame(paned, text="Vorschau", padding=self.px(6))
        self.lbl_preview = ttk.Label(pv, text="", style="Hint.TLabel")
        self.lbl_preview.pack(side="bottom", fill="x", pady=(self.px(5), 0))
        self.canvas = tk.Canvas(pv, bg=PREVIEW_BG, highlightthickness=0, height=self.px(320))
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._debounce("render", 60, self.render_preview))
        paned.add(pv, weight=3)

    def _build_list(self, paned):
        lst = ttk.LabelFrame(paned, text="Bilder", padding=self.px(6))
        lst.columnconfigure(0, weight=1)
        lst.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(lst, columns=("datei", "ausgabe", "status"), show="headings",
                                 selectmode="browse")
        self.tree.heading("datei", text="Originaldatei")
        self.tree.heading("ausgabe", text="Ausgabedatei  (Doppelklick = umbenennen)")
        self.tree.heading("status", text="Status")
        self.tree.column("datei", width=self.px(230), anchor="w")
        self.tree.column("ausgabe", width=self.px(300), anchor="w")
        self.tree.column("status", width=self.px(170), anchor="w", stretch=False)
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
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(self.px(6), 0))
        self._lock(ttk.Button(btns, text="Ausgabename ändern…", command=self.edit_selected)).pack(side="left")
        self._lock(ttk.Button(btns, text="Eigenen Namen zurücksetzen",
                              command=self.reset_selected)).pack(side="left", padx=self.px(6))
        self._lock(ttk.Button(btns, text="Alle zurücksetzen", command=self.reset_all)).pack(side="left")
        self._lock(ttk.Button(btns, text="Liste aktualisieren", command=self.rescan)).pack(side="right")
        paned.add(lst, weight=2)

    def _build_footer(self, parent):
        foot = ttk.Frame(parent)
        foot.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(self.px(10), 0))
        foot.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(foot, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, self.px(12)))
        self.btn_cancel = ttk.Button(foot, text="Abbrechen", command=self.on_cancel, state="disabled")
        self.btn_cancel.grid(row=0, column=1, padx=(0, self.px(8)))
        self.btn_start = ttk.Button(foot, text="Rahmen erstellen", style="Start.TButton",
                                    command=self.start)
        self.btn_start.grid(row=0, column=2)
        self.lbl_status = ttk.Label(foot, text="Bereit.")
        self.lbl_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def show_about(self):
        messagebox.showinfo(f"Über {APP_NAME}", app_info.ABOUT_TEXT, parent=self.root)

    # ------------------------------------------------------------------ Einstellungen
    def _apply_unit(self, initial=False):
        """Einheit gewechselt: Werte je Einheit getrennt merken und Felder umstellen."""
        unit = self.var_unit.get()
        if not initial:
            prev = "pct" if unit == "px" else "px"
            self.cfg[f"outer_{prev}"] = self.var_outer_w.get()
            self.cfg[f"inner_{prev}"] = self.var_inner_w.get()
            self.cfg[f"bottom_{prev}"] = self.var_bottom.get()
        spins = (self.sp_outer, self.sp_inner, self.sp_bottom)
        if unit == "pct":
            for sp in spins:
                sp.configure(from_=0, to=50, increment=0.1, format="%.1f")
            label = "% der langen Kante"
        else:
            for sp in spins:
                sp.configure(from_=0, to=10000, increment=1, format="%.0f")
            label = "px"
        self.var_outer_w.set(self.cfg[f"outer_{unit}"])
        self.var_inner_w.set(self.cfg[f"inner_{unit}"])
        self.var_bottom.set(self.cfg[f"bottom_{unit}"])
        for lbl in (self.lbl_outer_unit, self.lbl_inner_unit, self.lbl_bottom_unit):
            lbl.configure(text=label)
        self.on_settings_changed()

    def _update_frame_state(self):
        """Felder des inneren Rahmens nur beim Doppelrahmen aktivieren."""
        double = self.var_double.get()
        self.lbl_outer.configure(text="Äußerer Rahmen" if double else "Rahmen")
        enabled = double and not self.busy
        self.sp_inner.state(["!disabled"] if enabled else ["disabled"])
        self.col_inner.set_enabled(enabled)
        for w in (self.lbl_inner, self.lbl_inner_unit, self.lbl_inner_col):
            w.configure(foreground="" if double else "#9a9a9a")
        self.on_settings_changed()

    def get_settings(self) -> core.FrameSettings:
        """Bedienelemente -> FrameSettings. Löst ValueError mit Klartext aus."""
        def num(var, name):
            try:
                v = parse_number(var.get())
            except ValueError:
                raise ValueError(f"Bitte eine Zahl bei „{name}“ eingeben.") from None
            if v < 0:
                raise ValueError(f"„{name}“ darf nicht negativ sein.")
            if self.var_unit.get() == "pct" and v > 100:
                raise ValueError(f"„{name}“: höchstens 100 %.")
            return v

        double = self.var_double.get()
        return core.FrameSettings(
            double=double,
            unit=self.var_unit.get(),
            outer_width=num(self.var_outer_w, "Breite äußerer Rahmen" if double else "Breite Rahmen"),
            outer_color=core.hex_to_rgb(self.col_outer.get()),
            inner_width=num(self.var_inner_w, "Breite innerer Rahmen") if double else 0,
            inner_color=core.hex_to_rgb(self.col_inner.get()),
            bottom_extra=num(self.var_bottom, "Unten extra"),
        )

    def on_settings_changed(self):
        if hasattr(self, "canvas"):
            self._debounce("render", 120, self.render_preview)

    def _debounce(self, key, ms, func):
        """``func`` erst ausführen, wenn ``ms`` lang keine weitere Änderung kam."""
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
            f"bottom_{unit}": self.var_bottom.get(),
            "outer_color": self.col_outer.get(), "inner_color": self.col_inner.get(),
            "format": self.var_format.get(), "quality": self.var_quality.get(),
            "template": self.var_template.get(), "conflict": self.var_conflict.get(),
            # nur die Größe merken – Position könnte auf einem anderen Bildschirm liegen
            "size": f"{self.root.winfo_width()}x{self.root.winfo_height()}",
        })
        return cfg

    # ------------------------------------------------------------------ Ordner & Liste
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
        """Eingabe-Ordner neu einlesen und Liste aktualisieren."""
        if self.busy:
            return
        txt = self.var_in.get().strip()
        in_dir = Path(txt) if txt else None
        old = [str(f) for f in self.files]
        if in_dir and in_dir.is_dir():
            self.files = core.scan_images(in_dir, self.var_rec.get(), exclude=self._out_dir())
        else:
            self.files = []
        same = [str(f) for f in self.files] == old
        if not same:
            self.status.clear()
            self.preview_cache.clear()
        n = len(self.files)
        if not in_dir:
            self.lbl_count.configure(text="Bitte einen Eingabe-Ordner wählen")
        elif not in_dir.is_dir():
            self.lbl_count.configure(text="Ordner nicht gefunden")
        else:
            self.lbl_count.configure(text=f"{n} Bild{'er' if n != 1 else ''} gefunden")
        self.refresh_names(keep_selection=same)

    def refresh_names(self, keep_selection=True):
        """Ausgabenamen neu planen und die Liste neu aufbauen."""
        if self.busy:
            return
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
            except ValueError:
                src_label = job.src.name
            if out_dir:
                try:
                    dst_label = str(job.dst.relative_to(out_dir))
                except ValueError:
                    dst_label = job.dst.name
            else:
                dst_label = "– Ausgabe-Ordner fehlt –"
            st = self.status.get(str(job.src), "übersprungen (existiert)" if job.skip else "bereit")
            tags = ["renamed"] if str(job.src) in self.overrides else []
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
        if not sel or int(sel[0]) >= len(self.jobs):
            return
        job = self.jobs[int(sel[0])]
        if job.src != self.preview_path:
            self.preview_path = job.src
            self.load_preview(job.src)

    # ------------------------------------------------------------------ Umbenennen
    def on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.edit_selected()

    def edit_selected(self):
        """Ausgabenamen der markierten Zeile direkt in der Liste bearbeiten."""
        if self.busy:
            return
        sel = self.tree.selection()
        if not sel:
            return
        if not self._out_dir():
            messagebox.showinfo(APP_NAME, "Bitte zuerst einen Ausgabe-Ordner wählen.", parent=self.root)
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

        def finish(save: bool):
            if done["flag"]:
                return
            done["flag"] = True
            name = core.sanitize_stem(var.get())
            ent.destroy()
            self._editor = None
            if save and name and name != job.dst.stem:
                self.overrides[str(job.src)] = name
                self.refresh_names()
            self.tree.focus_set()

        ent.bind("<Return>", lambda e: finish(True))
        ent.bind("<KP_Enter>", lambda e: finish(True))
        ent.bind("<Escape>", lambda e: finish(False))
        ent.bind("<FocusOut>", lambda e: finish(True))

    def reset_selected(self):
        sel = self.tree.selection()
        if sel:
            self.overrides.pop(str(self.jobs[int(sel[0])].src), None)
            self.refresh_names()

    def reset_all(self):
        self.overrides.clear()
        self.refresh_names()

    # ------------------------------------------------------------------ Vorschau
    def load_preview(self, path: Path):
        """Vorschaubild im Hintergrund laden (Ergebnis kommt über die Event-Queue)."""
        key = str(path)
        if key in self.preview_cache:
            self.render_preview()
            return
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                text="Vorschau wird geladen …", fill="#e8e8e8", font=self.font_bold)

        def work():
            try:
                thumb, size = core.load_preview(path)
                self.events.put(("preview", key, thumb, size, None))
            except Exception as exc:
                self.events.put(("preview", key, None, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def render_preview(self):
        """Vorschau mit den aktuellen Einstellungen neu zeichnen."""
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
            self.canvas.create_text(cw // 2, ch // 2, fill="#ffb4ab", font=self.font_bold,
                                    text=str(exc), justify="center")
            self.lbl_preview.configure(text=str(exc))
            return
        pad = self.px(16)
        img = core.render_preview(thumb, size, settings, cw - 2 * pad, ch - 2 * pad)
        self.preview_photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(cw // 2, ch // 2, image=self.preview_photo, anchor="center")
        w, h = size
        fw, fh = settings.framed_size(w, h)
        self.lbl_preview.configure(
            text=f"{self.preview_path.name}:   {w} × {h} px   →   mit Rahmen {fw} × {fh} px")

    # ------------------------------------------------------------------ Verarbeitung
    def _validate_before_start(self):
        """Eingaben prüfen. Rückgabe (in_dir, out_dir, settings, quality) oder None."""
        in_txt, out_txt = self.var_in.get().strip(), self.var_out.get().strip()
        if not in_txt or not Path(in_txt).is_dir():
            messagebox.showwarning(APP_NAME, "Bitte einen gültigen Eingabe-Ordner wählen.", parent=self.root)
            return None
        if not out_txt:
            messagebox.showwarning(APP_NAME, "Bitte einen Ausgabe-Ordner wählen.", parent=self.root)
            return None
        in_dir, out_dir = Path(in_txt).resolve(), Path(out_txt).resolve()
        if in_dir == out_dir:
            messagebox.showwarning(APP_NAME, "Eingabe- und Ausgabe-Ordner müssen verschieden sein,\n"
                                             "damit die Originale sicher unverändert bleiben.",
                                   parent=self.root)
            return None
        try:
            settings = self.get_settings()
            quality = int(parse_number(self.var_quality.get()))
            if not 1 <= quality <= 100:
                raise ValueError("Die Qualität muss zwischen 1 und 100 liegen.")
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc), parent=self.root)
            return None
        if not settings.layers(1000, 1000):
            if not messagebox.askyesno(APP_NAME, "Alle Rahmenbreiten sind 0 – die Bilder würden nur "
                                                 "kopiert bzw. umgewandelt. Trotzdem fortfahren?",
                                       parent=self.root):
                return None
        return in_dir, out_dir, settings, quality

    def start(self):
        """Stapelverarbeitung starten."""
        if self.busy:
            return
        checked = self._validate_before_start()
        if not checked:
            return
        _, out_dir, settings, quality = checked
        self.rescan()
        if not self.jobs:
            messagebox.showinfo(APP_NAME, "Im Eingabe-Ordner wurden keine Bilder gefunden.", parent=self.root)
            return
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            core.cleanup_temp_files(out_dir)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Ausgabe-Ordner kann nicht angelegt werden:\n{exc}",
                                 parent=self.root)
            return
        if CONFLICT_LABELS[self.var_conflict.get()] == core.CONFLICT_OVERWRITE:
            existing = sum(1 for j in self.jobs if j.dst.exists())
            if existing and not messagebox.askyesno(
                    APP_NAME, f"{existing} Datei(en) im Ausgabe-Ordner werden überschrieben.\nFortfahren?",
                    parent=self.root):
                return

        save_config(self.collect_config())
        jobs = list(self.jobs)          # feste Kopie – die Liste wird während des Laufs nicht neu geplant
        self.run_jobs = jobs
        for job in jobs:
            self.status.pop(str(job.src), None)
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
                except MemoryError:
                    err += 1
                    self.events.put(("item", i, "Fehler: zu wenig Arbeitsspeicher"))
                except Exception as exc:
                    err += 1
                    self.events.put(("item", i, f"Fehler: {exc}"))
            self.events.put(("done", ok, err, skipped, self.cancel.is_set(), out_dir))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def on_cancel(self):
        self.cancel.set()
        self.btn_cancel.state(["disabled"])
        self.lbl_status.configure(text="Wird nach dem aktuellen Bild abgebrochen …")

    def _set_busy(self, busy: bool):
        """Bedienelemente während der Verarbeitung sperren bzw. wieder freigeben."""
        self.busy = busy
        flag = ["disabled"] if busy else ["!disabled"]
        for w in self._lockable:
            try:
                w.state(flag)
            except (tk.TclError, AttributeError):
                pass
        self.col_outer.set_enabled(not busy)
        self.btn_start.state(flag)
        self.btn_cancel.state(["!disabled"] if busy else ["disabled"])
        self._update_frame_state()

    def _poll_events(self):
        """Nachrichten der Hintergrund-Threads im Haupt-Thread verarbeiten."""
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "preview":
                    _, key, thumb, size, error = ev
                    self.preview_cache[key] = (thumb, size, error)
                    while len(self.preview_cache) > 12:
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
                    self.status[str(self.run_jobs[i].src)] = text
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
            parts.append(f"{err} mit Fehler (siehe Liste)")
        text = ", ".join(parts) + "."
        if cancelled:
            text = "Abgebrochen. " + text
        self.lbl_status.configure(text=text)
        if messagebox.askyesno(APP_NAME, text + "\n\nAusgabe-Ordner jetzt öffnen?", parent=self.root):
            open_folder(out_dir)

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno(APP_NAME, "Die Verarbeitung läuft noch. Wirklich beenden?",
                                       parent=self.root):
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
