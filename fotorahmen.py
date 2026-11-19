# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3.–4. November 2026
# Lizenz: GNU GPL v3 – siehe Datei LICENSE
# -----------------------------------------------------------------------------
"""FotoRahmen – Oberfläche (Tkinter, dunkles Design im Stil von Capture One).

Start aus dem Quellcode:  ``python fotorahmen.py``

Aufbau des Fensters
===================
┌ Werkzeugleiste: Titel · Voreinstellungen (Auswahl/Speichern/Löschen) · Info ┐
├ ORDNER: Eingabe / Ausgabe / Unterordner  (Drag & Drop: Ordner oder Bilder) ┤
├ Tabs RAHMEN | TEXT | EFFEKTE | AUSGABE │ VORSCHAU                           ┤
│                                         │ BILDER (Liste, Umbenennen)         │
└ Statusleiste: Fortschritt · Status · Abbrechen · Rahmen erstellen          ┘

Code-Aufbau
===========
* ``ColorChoice``   Weiß / Schwarz / eigene Farbe
* ``App``           Hauptfenster

  - ``_build_*``        Aufbau der Bereiche
  - Zustand <-> Widgets: ``self.v`` (alle Tk-Variablen), ``state_from_widgets()``,
    ``apply_state()``  – genutzt von Einstellungsdatei und Voreinstellungen
  - ``get_settings``    Widgets -> ``rahmen_core.FrameSettings``
  - ``rescan`` / ``refresh_names``  Dateiliste und geplante Ausgabenamen
  - ``load_preview`` / ``render_preview``  Vorschau (Laden im Hintergrund-Thread)
  - ``start`` / ``_poll_events``  Stapelverarbeitung im Hintergrund-Thread

Threads: Hintergrund-Threads greifen nie auf Widgets zu, sondern legen
Nachrichten in ``self.events`` ab; ``_poll_events`` verarbeitet sie alle 80 ms.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, ttk

from PIL import Image, ImageTk

import app_info
import rahmen_core as core
import theme
from theme import C

try:  # Drag & Drop (optional – ohne Paket läuft die App ohne diese Funktion)
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_OK = True
except Exception:  # pragma: no cover
    DND_OK = False

APP_NAME = app_info.APP_NAME

CONFLICT_LABELS = {
    "Nummer anhängen (_2, _3 …)": core.CONFLICT_NUMBER,
    "Überschreiben": core.CONFLICT_OVERWRITE,
    "Überspringen": core.CONFLICT_SKIP,
}
TEXT_POS_LABELS = {"Links": "left", "Mitte": "center", "Rechts": "right"}
WM_POS_LABELS = {
    "Unten rechts": "br", "Unten links": "bl", "Oben rechts": "tr", "Oben links": "tl",
    "Mitte": "c", "Diagonal über das ganze Bild": "tile",
}
APP_USER_MODEL_ID = "StefanJKaiser.FotoRahmen"
AUTO_OUT_NAME = "mit Rahmen"   # Standard-Ausgabe: Unterordner im Eingabe-Ordner   # Windows: eigenes Taskleisten-Symbol

#: Standardwerte aller Einstellungen. Neue Einstellung -> hier ergänzen.
DEFAULTS = {
    "in_dir": "", "out_dir": "", "out_auto": True, "recursive": False,
    "double": False, "unit": "px",
    "outer_px": "60", "outer_pct": "3", "outer_color": "#ffffff",
    "inner_px": "6", "inner_pct": "0.3", "inner_color": "#000000",
    "bottom_px": "0", "bottom_pct": "0",
    "text": "", "text_size": "45", "text_pos": "center", "text_color": "#3c3c3c", "text_font": "",
    "corner_radius": "0", "shadow": "0",
    "wm_on": False, "wm_text": "© {jahr}", "wm_opacity": "35", "wm_size": "5", "wm_pos": "br",
    "wm_color": "#ffffff", "wm_outline": True,
    "meta_on": False, "meta_author": "", "meta_copyright": "© {jahr}",
    "format": "Wie Original", "quality": "95",
    "limit_on": False, "max_edge": "2048",
    "template": "{name}_rahmen",
    "conflict": "Nummer anhängen (_2, _3 …)",
    "preset": "",
    "size": "",
}

#: Diese Einstellungen gehören zu einer Voreinstellung (nicht Ordner/Namen).
PRESET_KEYS = [
    "double", "unit", "outer_px", "outer_pct", "outer_color", "inner_px", "inner_pct",
    "inner_color", "bottom_px", "bottom_pct", "text", "text_size", "text_pos", "text_color",
    "text_font", "corner_radius", "shadow", "format", "quality", "limit_on", "max_edge",
    "wm_on", "wm_text", "wm_opacity", "wm_size", "wm_pos", "wm_color", "wm_outline",
    "meta_on", "meta_author", "meta_copyright",
]

#: Mitgelieferte Voreinstellungen (werden beim ersten Start angelegt).
BUILTIN_PRESETS = {
    "Galerie – Linie + Weiß": {"double": True, "unit": "pct", "outer_pct": "4", "outer_color": "#ffffff",
                               "inner_pct": "0.2", "inner_color": "#000000", "bottom_pct": "2"},
    "Schwarzer Rand schmal": {"double": False, "unit": "pct", "outer_pct": "1.5",
                              "outer_color": "#000000", "bottom_pct": "0"},
    "Signatur unten": {"double": False, "unit": "pct", "outer_pct": "3", "outer_color": "#ffffff",
                       "bottom_pct": "5", "text": "© {jahr}", "text_size": "40",
                       "text_pos": "right", "text_color": "#3c3c3c"},
    "Social Media 2048 px": {"double": False, "unit": "pct", "outer_pct": "3", "outer_color": "#ffffff",
                             "bottom_pct": "0", "format": "JPEG (.jpg)", "quality": "92",
                             "limit_on": True, "max_edge": "2048"},
    "Copyright-Schutz Web": {"double": False, "unit": "pct", "outer_pct": "2", "outer_color": "#ffffff",
                             "bottom_pct": "0", "wm_on": True, "wm_text": "© {jahr}", "wm_pos": "tile",
                             "wm_opacity": "25", "wm_size": "4", "meta_on": True,
                             "format": "JPEG (.jpg)", "quality": "90", "limit_on": True, "max_edge": "2048"},
    "PNG mit Schatten": {"double": False, "unit": "pct", "outer_pct": "3", "outer_color": "#ffffff",
                         "bottom_pct": "0", "corner_radius": "2", "shadow": "1.5",
                         "format": "PNG (.png)"},
}


# =============================================================================
# Hilfsfunktionen
# =============================================================================
def resource_path(rel: str) -> Path:
    """Pfad zu mitgelieferten Dateien – auch in der gepackten EXE/App."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel


def config_dir() -> Path:
    """Ordner für Einstellungen und Voreinstellungen je Betriebssystem."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def _read_json(name: str) -> dict:
    """JSON-Datei aus dem Einstellungsordner lesen (bei Fehlern leeres Dictionary)."""
    try:
        data = json.loads((config_dir() / name).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(name: str, data: dict):
    """JSON-Datei in den Einstellungsordner schreiben (Fehler werden ignoriert)."""
    try:
        path = config_dir() / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_config() -> dict:
    """Gespeicherte Einstellungen laden; unbekannte Schlüssel werden verworfen."""
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in _read_json("einstellungen.json").items() if k in DEFAULTS})
    return cfg


def load_presets() -> dict:
    """Voreinstellungen laden – beim ersten Start die mitgelieferten BUILTIN_PRESETS."""
    path = config_dir() / "voreinstellungen.json"
    if not path.exists():
        return {k: dict(v) for k, v in BUILTIN_PRESETS.items()}
    return {name: {k: v for k, v in p.items() if k in PRESET_KEYS}
            for name, p in _read_json("voreinstellungen.json").items() if isinstance(p, dict)}


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


def parse_number(text) -> float:
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
        self.mode = tk.StringVar()
        self.custom = "#b08d57"
        self.enabled = True
        self.rb = [
            ttk.Radiobutton(self, text="Weiß", value="white", variable=self.mode, command=on_change),
            ttk.Radiobutton(self, text="Schwarz", value="black", variable=self.mode, command=on_change),
            ttk.Radiobutton(self, text="Farbe…", value="custom", variable=self.mode, command=self.pick),
        ]
        for i, rb in enumerate(self.rb):
            rb.grid(row=0, column=i, sticky="w", padx=(0, 10))
        self.swatch = tk.Label(self, width=3, bg=self.custom, bd=0, highlightthickness=1,
                               highlightbackground=C["border"], cursor="hand2")
        self.swatch.grid(row=0, column=3, sticky="w", ipady=2)
        self.swatch.bind("<Button-1>", lambda e: self.pick())
        self.set(value)

    def pick(self):
        """Farbwähler öffnen und die gewählte Farbe als „eigene Farbe“ übernehmen."""
        if not self.enabled:
            return
        _, hx = colorchooser.askcolor(color=self.custom, title="Farbe wählen", parent=self)
        if not hx:
            self.on_change()          # Radiobutton „Farbe…“ wurde ggf. schon umgeschaltet
        else:
            self.custom = hx.lower()
            self.swatch.configure(bg=self.custom)
            self.mode.set("custom")
            self.on_change()

    def set(self, value: str):
        """Farbe setzen (#ffffff = Weiß, #000000 = Schwarz, sonst eigene Farbe)."""
        value = (value or "#ffffff").lower()
        if value == "#ffffff":
            self.mode.set("white")
        elif value == "#000000":
            self.mode.set("black")
        else:
            self.custom = value
            self.mode.set("custom")
        self.swatch.configure(bg=self.custom)

    def get(self) -> str:
        """Gewählte Farbe als '#rrggbb'."""
        return {"white": "#ffffff", "black": "#000000"}.get(self.mode.get(), self.custom)

    def set_enabled(self, enabled: bool):
        """Auswahl aktivieren oder sperren (z. B. während der Verarbeitung)."""
        self.enabled = enabled
        for w in self.rb:
            w.state(["!disabled"] if enabled else ["disabled"])
        self.swatch.configure(cursor="hand2" if enabled else "arrow")


# =============================================================================
# Hauptfenster
# =============================================================================
class App:
    """Hauptfenster von FotoRahmen: baut die Oberfläche, verwaltet Zustand, Vorschau und Stapelverarbeitung."""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.presets = load_presets()
        self.files: list[Path] = []
        self.dropped_files: list[Path] | None = None   # per Drag & Drop gewählte Einzelbilder
        self.dropped_base = ""
        self.overrides: dict[str, str] = {}   # str(Quellpfad) -> eigener Ausgabename
        self.status: dict[str, str] = {}      # str(Quellpfad) -> Statustext
        self.jobs: list[core.Job] = []
        self.run_jobs: list[core.Job] = []
        self.preview_cache: dict[str, tuple] = {}
        self.preview_path: Path | None = None
        self.preview_photo = None
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel = threading.Event()
        self.busy = False
        self._loading_state = False
        self._after_ids: dict[str, str] = {}
        self._editor = None
        self._lockable: list = []             # Widgets, die während der Verarbeitung gesperrt sind
        self.v: dict[str, tk.Variable] = {}   # alle Einstellungs-Variablen (Schlüssel wie DEFAULTS)

        self.ui = 1.0                         # Skalierung für hochauflösende Windows/Linux-Bildschirme
        if sys.platform != "darwin":
            try:
                self.ui = max(1.0, root.winfo_fpixels("1i") / 96.0)
            except tk.TclError:
                pass

        root.title(f"{APP_NAME} {app_info.VERSION}")
        root.geometry(self.cfg.get("size") or f"{self.px(1320)}x{self.px(860)}")
        root.minsize(self.px(1100), self.px(720))
        self.fonts = theme.apply_theme(root, self.ui)
        self._set_icon()
        self._build_ui()
        self.apply_state(self.cfg)
        self.rescan()
        self._setup_dnd()
        if sys.platform == "darwin":
            self._build_mac_menu()
        theme.dark_titlebar(root)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Control-Return>", lambda e: self.start())
        if sys.platform == "darwin":
            root.bind_all("<Command-Return>", lambda e: self.start())
        root.after(100, self._poll_events)

    def px(self, value: float) -> int:
        """Pixelmaß an die Bildschirm-Skalierung anpassen."""
        return int(round(value * self.ui))

    def _set_icon(self):
        """Logo oben links in der Titelleiste, in der Taskleiste (Windows) bzw. im Dock
        (macOS beim Start aus dem Quellcode).

        Windows: .ico mit allen Größen über ``iconbitmap`` (gilt auch für alle
        weiteren Fenster) und zusätzlich direkt per Windows-API
        (``theme.set_window_icon``) – scharf in jeder Bildschirm-Skalierung.
        In der fertigen EXE/App kommt das Symbol im Task-Manager, Explorer,
        Finder und Dock aus icon.ico bzw. icon.icns (beim Bauen eingebettet).
        """
        try:
            if sys.platform == "win32":
                ico = str(resource_path("assets/icon.ico"))
                self.root.iconbitmap(default=ico)
                theme.set_window_icon(self.root, ico)
                # nach dem Anzeigen des Fensters noch einmal setzen (Tk setzt beim Mappen ggf. zurück)
                self.root.after(300, lambda: theme.set_window_icon(self.root))
            else:
                src = Image.open(resource_path("assets/icon.png"))
                icon = ImageTk.PhotoImage(src.resize((256, 256), Image.Resampling.LANCZOS))
                small = ImageTk.PhotoImage(src.resize((32, 32), Image.Resampling.LANCZOS))
                self.root.iconphoto(True, icon, small)
                self._icons = (icon, small)
        except Exception:
            pass

    def _build_mac_menu(self):
        """macOS: Menüleiste mit App-Menü („Über FotoRahmen“), Ablage und Fenster."""
        menubar = tk.Menu(self.root)
        app_menu = tk.Menu(menubar, name="apple", tearoff=False)
        app_menu.add_command(label=f"Über {APP_NAME}", command=self.show_about)
        app_menu.add_separator()
        menubar.add_cascade(menu=app_menu)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Eingabe-Ordner wählen…", accelerator="Command-O", command=self.choose_in)
        file_menu.add_command(label="Ausgabe-Ordner wählen…", command=self.choose_out)
        file_menu.add_separator()
        file_menu.add_command(label="Voreinstellung speichern…", command=self.save_preset)
        file_menu.add_separator()
        file_menu.add_command(label="Rahmen erstellen", accelerator="Command-Return", command=self.start)
        menubar.add_cascade(menu=file_menu, label="Ablage")
        window_menu = tk.Menu(menubar, name="window", tearoff=False)
        menubar.add_cascade(menu=window_menu, label="Fenster")
        help_menu = tk.Menu(menubar, name="help", tearoff=False)
        help_menu.add_command(label=f"{APP_NAME} – Info", command=self.show_about)
        menubar.add_cascade(menu=help_menu, label="Hilfe")
        self.root.configure(menu=menubar)
        self.root.bind_all("<Command-o>", lambda e: self.choose_in())
        try:
            self.root.createcommand("tk::mac::ShowPreferences", lambda: self.notebook.select(0))
            self.root.createcommand("::tk::mac::Quit", self.on_close)
            self.root.createcommand("tkAboutDialog", self.show_about)
        except tk.TclError:
            pass

    # ================================================================== Aufbau
    def _var(self, key, kind=tk.StringVar):
        """Tk-Variable anlegen und unter ``key`` in ``self.v`` registrieren."""
        var = kind()
        self.v[key] = var
        return var

    def _lock(self, widget):
        """Widget registrieren: wird während der Verarbeitung gesperrt."""
        self._lockable.append(widget)
        return widget

    def _build_ui(self):
        """Gesamtes Fenster aufbauen: Werkzeugleiste, Ordner, Tabs, Vorschau, Liste, Statusleiste."""
        self._build_toolbar()
        main = ttk.Frame(self.root, style="App.TFrame", padding=(self.px(8), self.px(8), self.px(8), 0))
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
        self._build_folder_panel(main)
        self._build_tools(main)
        right = ttk.Panedwindow(main, orient="vertical")
        right.grid(row=1, column=1, sticky="nsew")
        self._build_preview(right)
        self._build_list(right)
        self._build_statusbar()

    def _panel(self, parent, title: str):
        """Palette im Capture-One-Stil: Kopfzeile in Großbuchstaben + Inhalt.
        Rückgabe (äußerer Rahmen, Kopfzeile, Inhalt)."""
        outer = ttk.Frame(parent)
        head = ttk.Frame(outer, style="Bar.TFrame", padding=(self.px(10), self.px(5)))
        head.pack(fill="x")
        ttk.Label(head, text=title.upper(), style="Header.TLabel").pack(side="left")
        body = ttk.Frame(outer, padding=(self.px(12), self.px(8)))
        body.pack(fill="both", expand=True)
        return outer, head, body

    def _section(self, parent, row, text):
        """Abschnittsüberschrift (orange) innerhalb eines Tabs."""
        lbl = ttk.Label(parent, text=text.upper(), style="Section.TLabel")
        lbl.grid(row=row, column=0, columnspan=2, sticky="w", pady=(self.px(10), self.px(4)))
        return lbl

    def _build_toolbar(self):
        """Werkzeugleiste oben: Logo, Titel, Version, Voreinstellungen, Info."""
        bar = ttk.Frame(self.root, style="Bar.TFrame", padding=(self.px(14), self.px(8)))
        bar.pack(fill="x")
        try:
            logo = Image.open(resource_path("assets/logo_small.png")).convert("RGBA")
            size = self.px(30) if sys.platform != "darwin" else 30
            self._logo = ImageTk.PhotoImage(logo.resize((size, size), Image.Resampling.LANCZOS))
            tk.Label(bar, image=self._logo, bg=C["bar"], bd=0).pack(side="left", padx=(0, self.px(10)))
        except Exception:
            pass
        ttk.Label(bar, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(bar, text=f" {app_info.VERSION}", style="Version.TLabel").pack(side="left", pady=(self.px(4), 0))
        ttk.Label(bar, text="    Rahmen für Fotos – Originale bleiben unverändert",
                  style="BarHint.TLabel").pack(side="left", pady=(self.px(5), 0))

        ttk.Button(bar, text="Info", style="Tool.TButton", command=self.show_about).pack(side="right")
        ttk.Separator(bar, orient="vertical").pack(side="right", fill="y", padx=self.px(10))
        self._lock(ttk.Button(bar, text="Löschen", style="Tool.TButton",
                              command=self.delete_preset)).pack(side="right")
        self._lock(ttk.Button(bar, text="Speichern…", style="Tool.TButton",
                              command=self.save_preset)).pack(side="right")
        self.cb_preset = self._lock(ttk.Combobox(bar, state="readonly", width=26,
                                                 textvariable=self._var("preset")))
        self.cb_preset.pack(side="right", padx=(self.px(6), self.px(4)))
        self.cb_preset.bind("<<ComboboxSelected>>", lambda e: self.load_preset())
        ttk.Label(bar, text="VOREINSTELLUNG", style="Header.TLabel").pack(side="right")
        self._update_preset_list()

    def _build_folder_panel(self, parent):
        """Palette ORDNER: Eingabe-/Ausgabe-Ordner, Ausgabe-Automatik, Unterordner, Anzahl."""
        outer, head, body = self._panel(parent, "Ordner")
        outer.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, self.px(8)))
        self.lbl_dnd = ttk.Label(head, text="", style="Header.TLabel")
        self.lbl_dnd.pack(side="right")
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Eingabe-Ordner").grid(row=0, column=0, sticky="w", pady=3)
        e_in = self._lock(ttk.Entry(body, textvariable=self._var("in_dir")))
        e_in.grid(row=0, column=1, sticky="ew", padx=self.px(10))
        self._lock(ttk.Button(body, text="Durchsuchen…", command=self.choose_in)).grid(row=0, column=2)
        ttk.Label(body, text="Ausgabe-Ordner").grid(row=1, column=0, sticky="w", pady=3)
        e_out = self._lock(ttk.Entry(body, textvariable=self._var("out_dir")))
        e_out.grid(row=1, column=1, sticky="ew", padx=self.px(10))
        self.e_out = e_out
        self._lock(ttk.Button(body, text="Durchsuchen…", command=self.choose_out)).grid(row=1, column=2)
        row = ttk.Frame(body)
        row.grid(row=2, column=1, columnspan=2, sticky="ew", padx=self.px(10), pady=(self.px(2), 0))
        self._lock(ttk.Checkbutton(row, text=f"Ausgabe automatisch in Unterordner „{AUTO_OUT_NAME}“",
                                   variable=self._var("out_auto", tk.BooleanVar),
                                   command=self._on_out_auto)).pack(side="left")
        self._lock(ttk.Checkbutton(row, text="Unterordner einbeziehen (Struktur wird übernommen)",
                                   variable=self._var("recursive", tk.BooleanVar),
                                   command=self.rescan)).pack(side="left", padx=(self.px(18), 0))
        self.lbl_count = ttk.Label(row, text="", style="Hint.TLabel")
        self.lbl_count.pack(side="right")
        self.v["in_dir"].trace_add("write", lambda *a: self._sync_auto_out())
        e_in.bind("<Return>", lambda e: self._on_in_dir_edited())
        e_in.bind("<FocusOut>", lambda e: self._on_in_dir_edited())
        e_out.bind("<Return>", lambda e: self.rescan())
        self.v["out_dir"].trace_add("write", lambda *a: self._debounce("names", 300, self.refresh_names))
        self._drop_widgets = [outer, body]

    def _build_tools(self, parent):
        """Linke Spalte: Registerkarten wie die Werkzeug-Tabs in Capture One."""
        frame = ttk.Frame(parent, width=self.px(440))
        frame.grid(row=1, column=0, sticky="nsw", padx=(0, self.px(8)))
        frame.grid_propagate(False)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        nb = ttk.Notebook(frame)
        nb.grid(row=0, column=0, sticky="nsew")
        self.notebook = nb
        for title, builder in (("Rahmen", self._tab_frame), ("Text", self._tab_text),
                               ("Schutz", self._tab_protect), ("Effekte", self._tab_effects),
                               ("Ausgabe", self._tab_output)):
            tab = ttk.Frame(nb, padding=(self.px(14), self.px(4), self.px(14), self.px(10)))
            tab.columnconfigure(1, weight=1)
            builder(tab)
            nb.add(tab, text=title.upper())

    def _number_row(self, box, row, label, key, unit_text="px", lo=0, hi=10000, inc=1.0, fmt="%.0f"):
        """Zeile 'Beschriftung  [Zahl] Einheit'; Änderungen aktualisieren die Vorschau."""
        ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", pady=3)
        f = ttk.Frame(box)
        f.grid(row=row, column=1, sticky="w", pady=3)
        var = self._var(key)
        sp = self._lock(ttk.Spinbox(f, textvariable=var, width=8, from_=lo, to=hi, increment=inc,
                                    format=fmt, command=self.on_settings_changed))
        sp.pack(side="left")
        unit = ttk.Label(f, text=unit_text, style="Hint.TLabel")
        unit.pack(side="left", padx=(self.px(8), 0))
        var.trace_add("write", lambda *a: self.on_settings_changed())
        return sp, unit

    def _hint(self, box, row, text):
        """Grauen Hinweistext über die volle Breite eines Tabs einfügen."""
        ttk.Label(box, text=text, style="Hint.TLabel", wraplength=self.px(370), justify="left").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(self.px(2), self.px(4)))

    def _tab_frame(self, box):
        """Tab RAHMEN: Art, Einheit, äußerer Rahmen (Breite, unten extra, Farbe), innerer Rahmen."""
        self._section(box, 0, "Art")
        f = ttk.Frame(box)
        f.grid(row=1, column=0, columnspan=2, sticky="w")
        dv = self._var("double", tk.BooleanVar)
        self._lock(ttk.Radiobutton(f, text="Einfacher Rahmen", value=False, variable=dv,
                                   command=self._update_frame_state)).pack(anchor="w")
        self._lock(ttk.Radiobutton(f, text="Doppelter Rahmen (innen + außen)", value=True, variable=dv,
                                   command=self._update_frame_state)).pack(anchor="w")
        self._section(box, 2, "Breite in")
        f = ttk.Frame(box)
        f.grid(row=3, column=0, columnspan=2, sticky="w")
        uv = self._var("unit")
        self._lock(ttk.Radiobutton(f, text="Pixel", value="px", variable=uv,
                                   command=self._apply_unit)).pack(anchor="w")
        self._lock(ttk.Radiobutton(f, text="% der langen Bildkante", value="pct", variable=uv,
                                   command=self._apply_unit)).pack(anchor="w")
        self._hint(box, 4, "Prozent: gleich wirkender Rahmen bei unterschiedlich großen Bildern.")

        self.lbl_outer = self._section(box, 5, "Rahmen")
        self.sp_outer, self.lbl_outer_unit = self._number_row(box, 6, "Breite", "outer_w")
        self.sp_bottom, self.lbl_bottom_unit = self._number_row(box, 7, "Unten extra", "bottom_w")
        ttk.Label(box, text="Farbe").grid(row=8, column=0, sticky="w", pady=3)
        self.col_outer = ColorChoice(box, "#ffffff", self.on_settings_changed)
        self.col_outer.grid(row=8, column=1, sticky="w", pady=3)

        self.lbl_inner = self._section(box, 9, "Innerer Rahmen (direkt am Bild)")
        self.sp_inner, self.lbl_inner_unit = self._number_row(box, 10, "Breite", "inner_w")
        self.lbl_inner_col = ttk.Label(box, text="Farbe")
        self.lbl_inner_col.grid(row=11, column=0, sticky="w", pady=3)
        self.col_inner = ColorChoice(box, "#000000", self.on_settings_changed)
        self.col_inner.grid(row=11, column=1, sticky="w", pady=3)

    def _tab_text(self, box):
        """Tab TEXT: Textzeile/Signatur mit Größe, Position, Farbe und Schrift."""
        self._section(box, 0, "Textzeile / Signatur")
        ttk.Label(box, text="Text").grid(row=1, column=0, sticky="w", pady=3)
        tv = self._var("text")
        self._lock(ttk.Entry(box, textvariable=tv)).grid(row=1, column=1, sticky="ew", pady=3)
        tv.trace_add("write", lambda *a: self.on_settings_changed())
        self._hint(box, 2, "Platzhalter: {name} = Dateiname, {datum} = heute, {jahr} = Jahr.\n"
                           "Der Text steht im unteren Rand – dafür im Tab RAHMEN „Unten extra“ "
                           "vergrößern (z. B. 5 %).")
        self._number_row(box, 3, "Größe", "text_size", "% der unteren Randhöhe", 5, 100, 5)
        ttk.Label(box, text="Position").grid(row=4, column=0, sticky="w", pady=3)
        f = ttk.Frame(box)
        f.grid(row=4, column=1, sticky="w", pady=3)
        pv = self._var("text_pos")
        for label, value in TEXT_POS_LABELS.items():
            self._lock(ttk.Radiobutton(f, text=label, value=value, variable=pv,
                                       command=self.on_settings_changed)).pack(side="left", padx=(0, 10))
        ttk.Label(box, text="Farbe").grid(row=5, column=0, sticky="w", pady=3)
        self.col_text = ColorChoice(box, "#3c3c3c", self.on_settings_changed)
        self.col_text.grid(row=5, column=1, sticky="w", pady=3)

        self._section(box, 6, "Schrift")
        f = ttk.Frame(box)
        f.grid(row=7, column=0, columnspan=2, sticky="ew")
        self._var("text_font")
        self.lbl_font = ttk.Label(f, text="Eingebaut", width=22)
        self.lbl_font.pack(side="left")
        self._lock(ttk.Button(f, text="Schriftdatei…", command=self.choose_font)).pack(side="left")
        self._lock(ttk.Button(f, text="Standard", command=lambda: self._set_font(""))).pack(
            side="left", padx=(self.px(6), 0))
        self._hint(box, 8, "Eigene Schrift: .ttf- oder .otf-Datei, z. B. aus C:\\Windows\\Fonts "
                           "oder /Library/Fonts.")

    def _tab_protect(self, box):
        """Tab SCHUTZ: transparentes Wasserzeichen und Copyright in den Metadaten."""
        self._section(box, 0, "Sichtbares Wasserzeichen")
        self._lock(ttk.Checkbutton(box, text="Transparentes Copyright ins Bild setzen",
                                   variable=self._var("wm_on", tk.BooleanVar),
                                   command=self.on_settings_changed)).grid(row=1, column=0, columnspan=2,
                                                                           sticky="w", pady=3)
        ttk.Label(box, text="Text").grid(row=2, column=0, sticky="w", pady=3)
        tv = self._var("wm_text")
        self._lock(ttk.Entry(box, textvariable=tv)).grid(row=2, column=1, sticky="ew", pady=3)
        tv.trace_add("write", lambda *a: self.on_settings_changed())
        self._hint(box, 3, "Platzhalter: {jahr}, {datum}, {name}. Beispiel: © {jahr} Vorname Nachname")
        self._number_row(box, 4, "Deckkraft", "wm_opacity", "% (20–40 = dezent)", 5, 100, 5)
        self._number_row(box, 5, "Größe", "wm_size", "% der kurzen Bildkante", 1, 30, 0.5, "%.1f")
        ttk.Label(box, text="Position").grid(row=6, column=0, sticky="w", pady=3)
        self.var_wm_pos_label = tk.StringVar()
        cb = self._lock(ttk.Combobox(box, textvariable=self.var_wm_pos_label, values=list(WM_POS_LABELS),
                                     state="readonly", width=28))
        cb.grid(row=6, column=1, sticky="w", pady=3)
        cb.bind("<<ComboboxSelected>>", lambda e: (
            self.v["wm_pos"].set(WM_POS_LABELS[self.var_wm_pos_label.get()]), self.on_settings_changed()))
        self._var("wm_pos")
        ttk.Label(box, text="Farbe").grid(row=7, column=0, sticky="w", pady=3)
        self.col_wm = ColorChoice(box, "#ffffff", self.on_settings_changed)
        self.col_wm.grid(row=7, column=1, sticky="w", pady=3)
        self._lock(ttk.Checkbutton(box, text="Kontrastkante (auf hellen und dunklen Stellen lesbar)",
                                   variable=self._var("wm_outline", tk.BooleanVar),
                                   command=self.on_settings_changed)).grid(row=8, column=0, columnspan=2,
                                                                           sticky="w", pady=3)
        self._hint(box, 9, "„Diagonal über das ganze Bild“ schützt am besten – das Wasserzeichen lässt sich "
                           "nicht einfach wegschneiden.")

        self._section(box, 10, "Copyright in den Metadaten")
        self._lock(ttk.Checkbutton(box, text="Urheber und Copyright in die Datei schreiben",
                                   variable=self._var("meta_on", tk.BooleanVar))).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(box, text="Urheber").grid(row=12, column=0, sticky="w", pady=3)
        self._lock(ttk.Entry(box, textvariable=self._var("meta_author"))).grid(row=12, column=1, sticky="ew", pady=3)
        ttk.Label(box, text="Copyright").grid(row=13, column=0, sticky="w", pady=3)
        self._lock(ttk.Entry(box, textvariable=self._var("meta_copyright"))).grid(row=13, column=1, sticky="ew", pady=3)
        self._hint(box, 14, "Wird als EXIF (Artist/Copyright), XMP (dc:creator/dc:rights) bzw. PNG-/TIFF-"
                            "Felder gespeichert – sichtbar z. B. in Lightroom, Capture One und in den "
                            "Datei-Eigenschaften.")

    def _tab_effects(self, box):
        """Tab EFFEKTE: abgerundete Ecken und Schatten (nur PNG/WebP)."""
        self._section(box, 0, "Abgerundete Ecken")
        self._number_row(box, 1, "Radius", "corner_radius", "% der kurzen Kante", 0, 50, 0.5, "%.1f")
        self._section(box, 2, "Schatten")
        self._number_row(box, 3, "Größe", "shadow", "% der langen Kante (0 = aus)", 0, 25, 0.5, "%.1f")
        self._hint(box, 4, "Effekte brauchen Transparenz und werden nur bei Ausgabe als PNG oder WebP "
                           "angewendet (Tab AUSGABE). Bei JPEG, TIFF usw. werden sie ignoriert.")
        self.lbl_fx_state = ttk.Label(box, text="", style="Section.TLabel", wraplength=self.px(370))
        self.lbl_fx_state.grid(row=5, column=0, columnspan=2, sticky="w", pady=(self.px(6), 0))

    def _tab_output(self, box):
        """Tab AUSGABE: Format, Qualität, lange Kante begrenzen, Dateiname, Verhalten bei vorhandenen Dateien."""
        self._section(box, 0, "Format")
        ttk.Label(box, text="Dateiformat").grid(row=1, column=0, sticky="w", pady=3)
        cb = self._lock(ttk.Combobox(box, textvariable=self._var("format"), values=list(core.OUTPUT_FORMATS),
                                     state="readonly", width=22))
        cb.grid(row=1, column=1, sticky="w", pady=3)
        cb.bind("<<ComboboxSelected>>", lambda e: (self.refresh_names(), self.on_settings_changed()))
        self._number_row(box, 2, "Qualität", "quality", "JPEG / WebP / HEIC (92–95 empfohlen)", 50, 100, 1)

        self._section(box, 3, "Größe")
        f = ttk.Frame(box)
        f.grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        self._lock(ttk.Checkbutton(f, text="Lange Kante begrenzen auf", variable=self._var("limit_on", tk.BooleanVar),
                                   command=self.on_settings_changed)).pack(side="left")
        me = self._var("max_edge")
        self._lock(ttk.Spinbox(f, textvariable=me, width=7, from_=100, to=20000, increment=64,
                               format="%.0f", command=self.on_settings_changed)).pack(side="left", padx=(self.px(8), 0))
        ttk.Label(f, text="px", style="Hint.TLabel").pack(side="left", padx=(self.px(6), 0))
        me.trace_add("write", lambda *a: self.on_settings_changed())
        self._hint(box, 5, "Gilt für das fertige Bild inklusive Rahmen – nur verkleinern, nie vergrößern "
                           "(z. B. 2048 px für Social Media).")

        self._section(box, 6, "Dateiname")
        tv = self._var("template")
        self._lock(ttk.Entry(box, textvariable=tv)).grid(row=7, column=0, columnspan=2, sticky="ew", pady=3)
        tv.trace_add("write", lambda *a: self._debounce("names", 250, self.refresh_names))
        self._hint(box, 8, "Platzhalter: {name} = Originalname, {nr} = 001, 002 …, {datum} = heute. "
                           "Einzelne Namen per Doppelklick in der Liste ändern.")
        ttk.Label(box, text="Datei existiert").grid(row=9, column=0, sticky="w", pady=3)
        cb2 = self._lock(ttk.Combobox(box, textvariable=self._var("conflict"), values=list(CONFLICT_LABELS),
                                      state="readonly", width=26))
        cb2.grid(row=9, column=1, sticky="w", pady=3)
        cb2.bind("<<ComboboxSelected>>", lambda e: self.refresh_names())

    def _build_preview(self, paned):
        """Palette VORSCHAU: Zeichenfläche und Größenangabe alt → neu."""
        outer, head, body = self._panel(paned, "Vorschau")
        body.configure(padding=0)
        self.lbl_preview = ttk.Label(head, text="", style="Header.TLabel")
        self.lbl_preview.pack(side="right")
        self.canvas = tk.Canvas(body, bg=C["viewer"], highlightthickness=0, height=self.px(330))
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._debounce("render", 60, self.render_preview))
        paned.add(outer, weight=3)
        self._drop_widgets.append(self.canvas)

    def _build_list(self, paned):
        """Palette BILDER: Liste Original | Ausgabedatei | Status mit Umbenennen-Schaltflächen."""
        outer, head, body = self._panel(paned, "Bilder")
        body.configure(padding=(0, 0, 0, self.px(6)))
        self.lbl_list = ttk.Label(head, text="Doppelklick auf „Ausgabedatei“ = umbenennen",
                                  style="Header.TLabel")
        self.lbl_list.pack(side="right")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(body, columns=("datei", "ausgabe", "status"), show="headings",
                                 selectmode="browse")
        self.tree.heading("datei", text="ORIGINALDATEI", anchor="w")
        self.tree.heading("ausgabe", text="AUSGABEDATEI", anchor="w")
        self.tree.heading("status", text="STATUS", anchor="w")
        self.tree.column("datei", width=self.px(230), anchor="w")
        self.tree.column("ausgabe", width=self.px(300), anchor="w")
        self.tree.column("status", width=self.px(180), anchor="w", stretch=False)
        self.tree.tag_configure("renamed", foreground=C["accent"])
        self.tree.tag_configure("ok", foreground=C["ok"])
        self.tree.tag_configure("err", foreground=C["err"])
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select())
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<F2>", lambda e: self.edit_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())

        btns = ttk.Frame(body, padding=(self.px(8), self.px(6), self.px(8), 0))
        btns.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._lock(ttk.Button(btns, text="Ausgabename ändern…", command=self.edit_selected)).pack(side="left")
        self._lock(ttk.Button(btns, text="Eigenen Namen zurücksetzen",
                              command=self.reset_selected)).pack(side="left", padx=self.px(6))
        self._lock(ttk.Button(btns, text="Alle zurücksetzen", command=self.reset_all)).pack(side="left")
        self._lock(ttk.Button(btns, text="Liste aktualisieren", command=self.rescan)).pack(side="right")
        paned.add(outer, weight=2)
        self._drop_widgets.append(self.tree)

    def _build_statusbar(self):
        """Statusleiste unten: Fortschritt, Statustext, Abbrechen, RAHMEN ERSTELLEN."""
        bar = ttk.Frame(self.root, style="Bar.TFrame", padding=(self.px(14), self.px(9)))
        bar.pack(fill="x", side="bottom")
        bar.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bar, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, self.px(14)))
        self.btn_cancel = ttk.Button(bar, text="Abbrechen", command=self.on_cancel)
        self.btn_cancel.state(["disabled"])
        self.btn_cancel.grid(row=0, column=1, padx=(0, self.px(8)))
        self.btn_start = ttk.Button(bar, text="RAHMEN ERSTELLEN", style="Accent.TButton", command=self.start)
        self.btn_start.grid(row=0, column=2, rowspan=2)
        self.lbl_status = ttk.Label(bar, text="Bereit.", style="Status.TLabel")
        self.lbl_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(self.px(4), 0))
        # Statusleiste vor dem Hauptbereich einordnen (unten fixiert)
        bar.pack_configure(before=self.root.pack_slaves()[1])

    def show_about(self):
        """Info-Dialog mit Version, Copyright, Idee/Prompt, Umsetzung und Lizenz anzeigen."""
        extra = "\n\nDrag & Drop: verfügbar" if DND_OK else ""
        theme.info(self.root, f"Über {APP_NAME}", app_info.ABOUT_TEXT + extra)

    # ================================================================== Zustand
    def state_from_widgets(self) -> dict:
        """Aktuellen Zustand aller Einstellungen als Dictionary (Schlüssel wie DEFAULTS)."""
        unit = self.v["unit"].get()
        st = dict(self.cfg)
        for key, var in self.v.items():
            if key in DEFAULTS:
                st[key] = var.get()
        st[f"outer_{unit}"] = self.v["outer_w"].get()
        st[f"inner_{unit}"] = self.v["inner_w"].get()
        st[f"bottom_{unit}"] = self.v["bottom_w"].get()
        st["outer_color"] = self.col_outer.get()
        st["inner_color"] = self.col_inner.get()
        st["text_color"] = self.col_text.get()
        st["wm_color"] = self.col_wm.get()
        return st

    def apply_state(self, st: dict):
        """Einstellungen (aus Datei oder Voreinstellung) in die Widgets übernehmen."""
        self._loading_state = True
        try:
            self.cfg.update(st)
            for key, var in self.v.items():
                if key in st and key in DEFAULTS:
                    val = st[key]
                    if isinstance(var, tk.BooleanVar):
                        var.set(bool(val))
                    else:
                        var.set(str(val))
            if self.v["unit"].get() not in ("px", "pct"):
                self.v["unit"].set("px")
            if self.v["format"].get() not in core.OUTPUT_FORMATS:
                self.v["format"].set("Wie Original")
            if self.v["conflict"].get() not in CONFLICT_LABELS:
                self.v["conflict"].set(DEFAULTS["conflict"])
            if self.v["text_pos"].get() not in core.TEXT_POSITIONS:
                self.v["text_pos"].set("center")
            if self.v["wm_pos"].get() not in core.WM_POSITIONS:
                self.v["wm_pos"].set("br")
            code_to_label = {v: k for k, v in WM_POS_LABELS.items()}
            self.var_wm_pos_label.set(code_to_label[self.v["wm_pos"].get()])
            self.col_wm.set(self.cfg["wm_color"])
            self.col_outer.set(self.cfg["outer_color"])
            self.col_inner.set(self.cfg["inner_color"])
            self.col_text.set(self.cfg["text_color"])
            self._set_font(self.cfg.get("text_font", ""), refresh=False)
            self._apply_unit(initial=True)
        finally:
            self._loading_state = False
        self._update_frame_state()
        self._on_out_auto()
        self.refresh_names()

    def _apply_unit(self, initial=False):
        """Einheit gewechselt: Werte je Einheit getrennt merken und Felder umstellen."""
        unit = self.v["unit"].get()
        if not initial:
            prev = "pct" if unit == "px" else "px"
            for k in ("outer", "inner", "bottom"):
                self.cfg[f"{k}_{prev}"] = self.v[f"{k}_w"].get()
        spins = (self.sp_outer, self.sp_inner, self.sp_bottom)
        if unit == "pct":
            for sp in spins:
                sp.configure(from_=0, to=50, increment=0.1, format="%.1f")
            label = "% der langen Kante"
        else:
            for sp in spins:
                sp.configure(from_=0, to=10000, increment=1, format="%.0f")
            label = "px"
        for k in ("outer", "inner", "bottom"):
            self.v[f"{k}_w"].set(self.cfg[f"{k}_{unit}"])
        for lbl in (self.lbl_outer_unit, self.lbl_inner_unit, self.lbl_bottom_unit):
            lbl.configure(text=label)
        self.on_settings_changed()

    def _update_frame_state(self):
        """Felder des inneren Rahmens nur beim Doppelrahmen aktivieren."""
        double = self.v["double"].get()
        self.lbl_outer.configure(text="ÄUSSERER RAHMEN" if double else "RAHMEN")
        enabled = double and not self.busy
        self.sp_inner.state(["!disabled"] if enabled else ["disabled"])
        self.col_inner.set_enabled(enabled)
        for w in (self.lbl_inner_unit, self.lbl_inner_col):
            w.configure(foreground="" if double else C["fg_off"])
        self.lbl_inner.configure(foreground="" if double else C["fg_off"])
        self.on_settings_changed()

    def choose_font(self):
        """Eigene Schriftdatei (.ttf/.otf/.ttc) für Textzeile und Wasserzeichen wählen."""
        path = filedialog.askopenfilename(title="Schriftdatei wählen", parent=self.root,
                                          filetypes=[("Schriften", "*.ttf *.otf *.ttc"), ("Alle Dateien", "*")])
        if path:
            self._set_font(path)

    def _set_font(self, path: str, refresh=True):
        """Schriftdatei setzen (leer = eingebaute Schrift) und die Anzeige aktualisieren."""
        self.v["text_font"].set(path or "")
        self.lbl_font.configure(text=Path(path).name if path else "Eingebaut")
        if refresh:
            self.on_settings_changed()

    def get_settings(self) -> core.FrameSettings:
        """Widgets -> FrameSettings. Löst ValueError mit Klartext aus."""
        pct = self.v["unit"].get() == "pct"

        def num(key, name, maxv=None, unit_rel=True):
            try:
                val = parse_number(self.v[key].get())
            except ValueError:
                raise ValueError(f"Bitte eine Zahl bei „{name}“ eingeben.") from None
            if val < 0:
                raise ValueError(f"„{name}“ darf nicht negativ sein.")
            limit = maxv if maxv is not None else (100 if (pct and unit_rel) else None)
            if limit is not None and val > limit:
                raise ValueError(f"„{name}“: höchstens {limit:g}.")
            return val

        double = self.v["double"].get()
        max_edge = 0
        if self.v["limit_on"].get():
            max_edge = int(num("max_edge", "Lange Kante begrenzen", 100000, False))
            if max_edge < 16:
                raise ValueError("„Lange Kante begrenzen“: mindestens 16 px.")
        return core.FrameSettings(
            double=double,
            unit=self.v["unit"].get(),
            outer_width=num("outer_w", "Breite äußerer Rahmen" if double else "Breite Rahmen"),
            outer_color=core.hex_to_rgb(self.col_outer.get()),
            inner_width=num("inner_w", "Breite innerer Rahmen") if double else 0,
            inner_color=core.hex_to_rgb(self.col_inner.get()),
            bottom_extra=num("bottom_w", "Unten extra"),
            text=self.v["text"].get(),
            text_size=num("text_size", "Textgröße", 100, False),
            text_pos=self.v["text_pos"].get(),
            text_color=core.hex_to_rgb(self.col_text.get()),
            text_font=self.v["text_font"].get(),
            max_edge=max_edge,
            corner_radius=num("corner_radius", "Eckenradius", 50, False),
            shadow=num("shadow", "Schatten", 25, False),
            wm_text=self.v["wm_text"].get() if self.v["wm_on"].get() else "",
            wm_opacity=num("wm_opacity", "Deckkraft Wasserzeichen", 100, False),
            wm_size=num("wm_size", "Größe Wasserzeichen", 50, False),
            wm_pos=self.v["wm_pos"].get(),
            wm_color=core.hex_to_rgb(self.col_wm.get()),
            wm_outline=bool(self.v["wm_outline"].get()),
            meta_author=self.v["meta_author"].get() if self.v["meta_on"].get() else "",
            meta_copyright=self.v["meta_copyright"].get() if self.v["meta_on"].get() else "",
        )

    def on_settings_changed(self):
        """Nach jeder Änderung die Vorschau verzögert (120 ms) neu zeichnen."""
        if hasattr(self, "canvas") and not self._loading_state:
            self._debounce("render", 120, self.render_preview)

    def _debounce(self, key, ms, func):
        """``func`` erst ausführen, wenn ``ms`` lang keine weitere Änderung kam."""
        if key in self._after_ids:
            self.root.after_cancel(self._after_ids[key])
        self._after_ids[key] = self.root.after(ms, func)

    def collect_config(self) -> dict:
        """Aktuellen Zustand für einstellungen.json zusammenstellen (nur bekannte Schlüssel)."""
        cfg = self.state_from_widgets()
        # nur die Größe merken – die Position könnte auf einem anderen Bildschirm liegen
        cfg["size"] = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        return {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}

    # ================================================================== Voreinstellungen
    def _update_preset_list(self):
        """Auswahlliste der Voreinstellungen alphabetisch neu füllen."""
        self.cb_preset.configure(values=sorted(self.presets, key=str.lower))

    def load_preset(self):
        """Gewählte Voreinstellung laden (erst alle PRESET_KEYS auf Standard, dann die Werte der Voreinstellung)."""
        name = self.v["preset"].get()
        if name in self.presets:
            # Erst alle Voreinstellungs-Werte auf Standard, dann die Voreinstellung darüber –
            # so bleiben keine Werte der vorher gewählten Voreinstellung hängen.
            st = {k: DEFAULTS[k] for k in PRESET_KEYS}
            st.update(self.presets[name])
            st["preset"] = name
            self.apply_state(st)
            self.lbl_status.configure(text=f"Voreinstellung „{name}“ geladen.")

    def save_preset(self):
        """Aktuelle Einstellungen unter einem Namen als Voreinstellung speichern (mit Rückfrage beim Überschreiben)."""
        name = theme.ask_string(self.root, "Voreinstellung speichern",
                                "Name der Voreinstellung (Rahmen, Text, Effekte und Ausgabeformat):",
                                self.v["preset"].get())
        if not name:
            return
        name = name.strip()[:60]
        if name in self.presets and not theme.ask(self.root, APP_NAME,
                                                  f"„{name}“ existiert bereits. Überschreiben?"):
            return
        try:
            self.get_settings()
        except ValueError as exc:
            theme.warn(self.root, APP_NAME, str(exc))
            return
        st = self.state_from_widgets()
        self.presets[name] = {k: st[k] for k in PRESET_KEYS}
        _write_json("voreinstellungen.json", self.presets)
        self._update_preset_list()
        self.v["preset"].set(name)
        self.lbl_status.configure(text=f"Voreinstellung „{name}“ gespeichert.")

    def delete_preset(self):
        """Gewählte Voreinstellung nach Rückfrage löschen."""
        name = self.v["preset"].get()
        if name not in self.presets:
            theme.info(self.root, APP_NAME, "Bitte zuerst oben eine Voreinstellung auswählen.")
            return
        if theme.ask(self.root, APP_NAME, f"Voreinstellung „{name}“ löschen?"):
            del self.presets[name]
            _write_json("voreinstellungen.json", self.presets)
            self._update_preset_list()
            self.v["preset"].set("")

    # ================================================================== Drag & Drop
    def _setup_dnd(self):
        """Drag & Drop auf Fenster, Ordner-Palette, Vorschau und Liste einrichten (falls tkinterdnd2 vorhanden)."""
        if not DND_OK:
            return
        ok = False
        for w in [self.root, *self._drop_widgets]:
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                ok = True
            except Exception:
                pass
        if ok:
            self.lbl_dnd.configure(text="ORDNER ODER BILDER HIERHER ZIEHEN")

    def _on_drop(self, event):
        """Abgelegte Dateien verarbeiten: ein Ordner wird Eingabe-Ordner, einzelne Bilder bilden die Liste."""
        if self.busy:
            return
        paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        dirs = [p for p in paths if p.is_dir()]
        if len(dirs) == 1 and len(paths) == 1:
            self.dropped_files = None
            self.v["in_dir"].set(str(dirs[0]))
        else:
            images = [p for p in paths if p.is_file() and p.suffix.lower() in core.INPUT_EXTS]
            if not images:
                theme.warn(self.root, APP_NAME, "Keine unterstützten Bilder in der Auswahl.")
                return
            base = Path(os.path.commonpath([str(p.parent) for p in images]))
            self.dropped_files = images
            self.dropped_base = str(base)
            self.v["in_dir"].set(str(base))
        self._sync_auto_out()
        self.rescan()
        return getattr(event, "action", None)

    # ================================================================== Ordner & Liste
    def choose_in(self):
        """Eingabe-Ordner wählen; bei aktiver Automatik folgt der Ausgabe-Ordner."""
        d = filedialog.askdirectory(title="Eingabe-Ordner wählen", parent=self.root,
                                    initialdir=self.v["in_dir"].get() or None)
        if d:
            self.dropped_files = None
            self.v["in_dir"].set(d)      # Ausgabe folgt automatisch (siehe _sync_auto_out)
            self.rescan()

    def choose_out(self):
        """Eigenen Ausgabe-Ordner wählen – schaltet die Ausgabe-Automatik aus."""
        d = filedialog.askdirectory(title="Ausgabe-Ordner wählen", parent=self.root,
                                    initialdir=self.v["out_dir"].get() or self.v["in_dir"].get() or None)
        if d:
            self.v["out_auto"].set(False)   # eigener Ordner gewählt -> Automatik aus
            self._on_out_auto()
            self.v["out_dir"].set(d)
            self.rescan()

    def _sync_auto_out(self):
        """Bei aktiver Automatik: Ausgabe-Ordner = Eingabe-Ordner/„mit Rahmen“."""
        if not self.v["out_auto"].get():
            return
        txt = self.v["in_dir"].get().strip()
        new = str(Path(txt) / AUTO_OUT_NAME) if txt else ""
        if self.v["out_dir"].get() != new:
            self.v["out_dir"].set(new)

    def _on_out_auto_state_only(self):
        """Ausgabe-Feld je nach Automatik schreibgeschützt anzeigen."""
        self.e_out.state(["readonly"] if self.v["out_auto"].get() else ["!readonly"])

    def _on_out_auto(self):
        """Automatik umgeschaltet: Feld sperren/freigeben und Pfad ggf. setzen."""
        auto = bool(self.v["out_auto"].get())
        if not self.busy:
            self.e_out.state(["readonly"] if auto else ["!readonly"])
        if auto:
            self._sync_auto_out()
            self.rescan()

    def _on_in_dir_edited(self):
        """Eingabe-Ordner wurde von Hand geändert: Drag-&-Drop-Auswahl ggf. verwerfen, neu einlesen."""
        if self.dropped_files is not None and self.v["in_dir"].get().strip() != self.dropped_base:
            self.dropped_files = None
        self.rescan()

    def _out_dir(self) -> Path | None:
        """Ausgabe-Ordner als Path (oder None, wenn leer)."""
        t = self.v["out_dir"].get().strip()
        return Path(t) if t else None

    def rescan(self):
        """Eingabe-Ordner (bzw. per Drag & Drop gewählte Bilder) neu einlesen."""
        if self.busy:
            return
        txt = self.v["in_dir"].get().strip()
        in_dir = Path(txt) if txt else None
        old = [str(f) for f in self.files]
        if self.dropped_files is not None:
            self.files = [f for f in self.dropped_files if f.is_file()]
        elif in_dir and in_dir.is_dir():
            self.files = core.scan_images(in_dir, self.v["recursive"].get(), exclude=self._out_dir())
        else:
            self.files = []
        same = [str(f) for f in self.files] == old
        if not same:
            self.status.clear()
            self.preview_cache.clear()
        n = len(self.files)
        if self.dropped_files is not None:
            self.lbl_count.configure(text=f"{n} Bild{'er' if n != 1 else ''} per Drag & Drop")
        elif not in_dir:
            self.lbl_count.configure(text="Bitte einen Eingabe-Ordner wählen")
        elif not in_dir.is_dir():
            self.lbl_count.configure(text="Ordner nicht gefunden")
        else:
            self.lbl_count.configure(text=f"{n} Bild{'er' if n != 1 else ''} gefunden")
        self.refresh_names(keep_selection=same)

    def refresh_names(self, keep_selection=True):
        """Ausgabenamen neu planen und die Liste neu aufbauen."""
        if self.busy or not hasattr(self, "tree"):
            return
        sel = self.tree.selection()
        sel_id = sel[0] if (sel and keep_selection) else None
        self.tree.delete(*self.tree.get_children())
        in_dir = Path(self.v["in_dir"].get().strip() or ".")
        out_dir = self._out_dir()
        if out_dir:
            self.jobs = core.plan_jobs(self.files, in_dir, out_dir, self.v["template"].get(),
                                       self.overrides, self.v["format"].get(),
                                       CONFLICT_LABELS.get(self.v["conflict"].get(), core.CONFLICT_NUMBER))
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
        """Zeile in der Liste gewählt: Vorschau dieses Bildes laden."""
        sel = self.tree.selection()
        if not sel or int(sel[0]) >= len(self.jobs):
            return
        job = self.jobs[int(sel[0])]
        if job.src != self.preview_path:
            self.preview_path = job.src
            self.load_preview(job.src)

    # ================================================================== Umbenennen
    def on_double_click(self, event):
        """Doppelklick auf eine Zeile: Ausgabenamen bearbeiten."""
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
            theme.info(self.root, APP_NAME, "Bitte zuerst einen Ausgabe-Ordner wählen.")
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
        """Eigenen Ausgabenamen der markierten Zeile entfernen (wieder Vorlage)."""
        sel = self.tree.selection()
        if sel:
            self.overrides.pop(str(self.jobs[int(sel[0])].src), None)
            self.refresh_names()

    def reset_all(self):
        """Alle eigenen Ausgabenamen entfernen."""
        self.overrides.clear()
        self.refresh_names()

    # ================================================================== Vorschau
    def load_preview(self, path: Path):
        """Vorschaubild im Hintergrund laden (Ergebnis kommt über die Event-Queue)."""
        key = str(path)
        if key in self.preview_cache:
            self.render_preview()
            return
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                text="Vorschau wird geladen …", fill=C["fg_dim"], font=self.fonts["bold"])

        def work():
            try:
                thumb, size = core.load_preview(path)
                self.events.put(("preview", key, thumb, size, None))
            except Exception as exc:
                self.events.put(("preview", key, None, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _preview_format(self, src: Path) -> str | None:
        """Zielformat des Vorschaubildes (z. B. "PNG") – entscheidet über Effekte."""
        return core.EXT_TO_FMT.get(core.output_extension(src, self.v["format"].get()).lower())

    def _canvas_message(self, text, color):
        """Meldungstext mittig in der Vorschau anzeigen."""
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.create_text(cw // 2, ch // 2, fill=color, font=self.fonts["bold"], text=text,
                                justify="center", width=max(100, cw - 40))

    def render_preview(self):
        """Vorschau mit den aktuellen Einstellungen neu zeichnen."""
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 20 or ch < 20:
            return
        self._update_fx_state()
        if not self.preview_path:
            self._canvas_message("Keine Bilder – Eingabe-Ordner wählen"
                                 + (" oder Ordner/Bilder hierher ziehen" if DND_OK else ""), C["fg_dim"])
            self.lbl_preview.configure(text="")
            return
        entry = self.preview_cache.get(str(self.preview_path))
        if not entry:
            return
        thumb, size, error = entry
        if error:
            self._canvas_message(f"Bild kann nicht gelesen werden:\n{error}", C["err"])
            self.lbl_preview.configure(text="")
            return
        try:
            settings = self.get_settings()
        except ValueError as exc:
            self._canvas_message(str(exc), C["err"])
            self.lbl_preview.configure(text="")
            return
        fmt = self._preview_format(self.preview_path)
        pad = self.px(18)
        img = core.render_preview(thumb, size, settings, cw - 2 * pad, ch - 2 * pad, fmt,
                                  core.make_context(self.preview_path))
        self.preview_photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(cw // 2, ch // 2, image=self.preview_photo, anchor="center")
        w, h = size
        ow, oh = core.output_size(settings, w, h, fmt)
        self.lbl_preview.configure(text=f"{self.preview_path.name}   {w} × {h}  →  {ow} × {oh} PX")

    def _update_fx_state(self):
        """Hinweis im Tab EFFEKTE, ob Effekte für das gewählte Format greifen."""
        try:
            on = parse_number(self.v["corner_radius"].get()) > 0 or parse_number(self.v["shadow"].get()) > 0
        except ValueError:
            on = False
        label = self.v["format"].get()
        if not on:
            text = ""
        elif label in ("PNG (.png)", "WebP (.webp)"):
            text = "✓ Effekte aktiv"
        elif label == "Wie Original":
            text = "Effekte nur für PNG/WebP-Originale aktiv"
        else:
            text = "Effekte inaktiv – Ausgabe als PNG oder WebP wählen"
        self.lbl_fx_state.configure(text=text)

    # ================================================================== Verarbeitung
    def _validate_before_start(self):
        """Eingaben prüfen. Rückgabe (out_dir, settings, quality) oder None."""
        in_txt, out_txt = self.v["in_dir"].get().strip(), self.v["out_dir"].get().strip()
        if not in_txt or not Path(in_txt).is_dir():
            theme.warn(self.root, APP_NAME, "Bitte einen gültigen Eingabe-Ordner wählen.")
            return None
        if not out_txt:
            theme.warn(self.root, APP_NAME, "Bitte einen Ausgabe-Ordner wählen.")
            return None
        in_dir, out_dir = Path(in_txt).resolve(), Path(out_txt).resolve()
        if in_dir == out_dir:
            theme.warn(self.root, APP_NAME, "Eingabe- und Ausgabe-Ordner müssen verschieden sein,\n"
                                            "damit die Originale sicher unverändert bleiben.")
            return None
        try:
            settings = self.get_settings()
            quality = int(parse_number(self.v["quality"].get()))
            if not 1 <= quality <= 100:
                raise ValueError("Die Qualität muss zwischen 1 und 100 liegen.")
        except ValueError as exc:
            theme.warn(self.root, APP_NAME, str(exc))
            return None
        if not settings.layers(1000, 1000) and not settings.max_edge \
                and not (settings.corner_radius or settings.shadow) \
                and not settings.wm_text.strip() and not (settings.meta_author or settings.meta_copyright):
            if not theme.ask(self.root, APP_NAME, "Alle Rahmenbreiten sind 0 – die Bilder würden nur "
                                                  "kopiert bzw. umgewandelt. Trotzdem fortfahren?"):
                return None
        return out_dir, settings, quality

    def start(self):
        """Stapelverarbeitung starten."""
        if self.busy:
            return
        checked = self._validate_before_start()
        if not checked:
            return
        out_dir, settings, quality = checked
        self.rescan()
        if not self.jobs:
            theme.info(self.root, APP_NAME, "Es wurden keine Bilder gefunden.")
            return
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            core.cleanup_temp_files(out_dir)
        except OSError as exc:
            theme.error(self.root, APP_NAME, f"Ausgabe-Ordner kann nicht angelegt werden:\n{exc}")
            return
        if CONFLICT_LABELS[self.v["conflict"].get()] == core.CONFLICT_OVERWRITE:
            existing = sum(1 for j in self.jobs if j.dst.exists())
            if existing and not theme.ask(self.root, APP_NAME,
                                          f"{existing} Datei(en) im Ausgabe-Ordner werden überschrieben.\n"
                                          "Fortfahren?"):
                return

        _write_json("einstellungen.json", self.collect_config())
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
        """Verarbeitung nach dem aktuellen Bild abbrechen."""
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
        for cc in (self.col_outer, self.col_text, self.col_wm):
            cc.set_enabled(not busy)
        self.btn_start.state(flag)
        self.btn_cancel.state(["!disabled"] if busy else ["disabled"])
        self._update_frame_state()
        if not busy:
            self._on_out_auto_state_only()

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
        """Lauf beendet: Bedienung freigeben, Zusammenfassung anzeigen, Ausgabe-Ordner öffnen anbieten."""
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
        if theme.ask(self.root, APP_NAME, text + "\n\nAusgabe-Ordner jetzt öffnen?",
                     yes="Ordner öffnen", no="Schließen"):
            open_folder(out_dir)

    def on_close(self):
        """Fenster schließen: ggf. Rückfrage bei laufender Verarbeitung, Einstellungen speichern."""
        if self.busy:
            if not theme.ask(self.root, APP_NAME, "Die Verarbeitung läuft noch. Wirklich beenden?"):
                return
            self.cancel.set()
        _write_json("einstellungen.json", self.collect_config())
        self.root.destroy()


def create_root() -> tk.Tk:
    """Hauptfenster erzeugen – mit Drag & Drop, falls verfügbar."""
    global DND_OK
    if DND_OK:
        try:
            return TkinterDnD.Tk()
        except Exception:
            DND_OK = False
    return tk.Tk()


def set_windows_app_id():
    """Windows: eigene App-ID, damit die Taskleiste das FotoRahmen-Logo zeigt
    (und nicht das Python-Symbol, wenn aus dem Quellcode gestartet)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def main():
    """Programmstart: Windows-App-ID und DPI setzen, Fenster erzeugen, Ereignisschleife starten."""
    set_windows_app_id()
    enable_dpi_awareness()
    root = create_root()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
