# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3.–4. November 2026
# Lizenz: GNU GPL v3 – siehe Datei LICENSE
# -----------------------------------------------------------------------------
"""Dunkles Erscheinungsbild im Stil von Capture One (Dark Mode).

Alle Farben stehen oben in ``C``. Wer das Aussehen ändern möchte, passt nur
diese Werte an – Styles und Dialoge übernehmen sie automatisch.

Inhalt
------
* ``C``               Farbpalette
* ``apply_theme()``   ttk-Styles (Theme „clam“, auf allen Systemen gleich)
* ``set_window_icon()`` Logo oben links in der Titelleiste (Windows, per WM_SETICON)
* ``dark_titlebar()`` dunkle Fenster-Titelleiste unter Windows 10/11 und macOS
* ``Dialog``          dunkle Meldungs-/Rückfragefenster (ersetzt tkinter.messagebox)
* ``info / warn / error / ask``  bequeme Aufrufe für ``Dialog``

Hinweis: Das Theme „clam“ wird bewusst auch unter Windows und macOS
verwendet, weil die nativen Themes („vista“, „aqua“) eigene Farben erzwingen
und sich nicht dunkel einfärben lassen.
"""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# =============================================================================
# Farbpalette
# =============================================================================
C = {
    "app":        "#1c1c1c",   # Fensterhintergrund / Zwischenräume
    "panel":      "#262626",   # Werkzeug-Paletten
    "bar":        "#2e2e2e",   # Werkzeugleiste, Kopfzeilen
    "input":      "#383838",   # Eingabefelder
    "button":     "#3a3a3a",   # normale Schaltflächen
    "button_hi":  "#4a4a4a",   # Schaltfläche unter dem Mauszeiger
    "border":     "#454545",   # feine Linien
    "viewer":     "#474747",   # Vorschau-Hintergrund (neutralgrau: Schwarz und Weiß sichtbar)
    "fg":         "#ececec",   # Text (weiß)
    "fg_dim":     "#9b9b9b",   # Nebentext, Kopfzeilen
    "fg_off":     "#626262",   # deaktivierter Text
    "accent":     "#f28a1e",   # Orange (Capture One)
    "accent_hi":  "#ffa244",   # Orange hell (Hover)
    "accent_dim": "#5c3a14",   # Orange gedämpft (Auswahl-Hintergrund)
    "on_accent":  "#1a1a1a",   # Text auf orangem Grund
    "ok":         "#7cc47f",
    "err":        "#ff6f61",
}


def _font(base: tkfont.Font, **kw) -> tkfont.Font:
    """Kopie einer Tk-Schrift mit geänderten Eigenschaften."""
    f = base.copy()
    f.configure(**kw)
    return f


# =============================================================================
# Styles
# =============================================================================
def apply_theme(root: tk.Tk, ui: float = 1.0) -> dict:
    """Dunkles Theme auf alle ttk-Widgets anwenden.

    ``ui`` ist der Skalierungsfaktor für Abstände (hochauflösende Bildschirme).
    Rückgabe: Dictionary mit Schriften (``normal``, ``bold``, ``small``,
    ``title``, ``header``).
    """
    def px(v):
        return int(round(v * ui))

    root.configure(bg=C["app"])
    style = ttk.Style(root)
    style.theme_use("clam")

    base_size = 13 if sys.platform == "darwin" else 10
    family = None
    if sys.platform == "win32":
        family = "Segoe UI"
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            f = tkfont.nametofont(name)
            f.configure(size=base_size)
            if family:
                f.configure(family=family)
        except tk.TclError:
            pass
    normal = tkfont.nametofont("TkDefaultFont")
    fonts = {
        "normal": normal,
        "bold": _font(normal, weight="bold"),
        "small": _font(normal, size=max(base_size - 1, 8)),
        "title": _font(normal, size=base_size + 5, weight="bold"),
        "header": _font(normal, size=max(base_size - 1, 8), weight="bold"),
    }

    flat = dict(bordercolor=C["border"], lightcolor=C["border"], darkcolor=C["border"])

    style.configure(".", background=C["panel"], foreground=C["fg"], fieldbackground=C["input"],
                    troughcolor=C["input"], selectbackground=C["accent"],
                    selectforeground=C["on_accent"], insertcolor=C["fg"], font=normal,
                    focuscolor=C["accent"], **flat)
    style.map(".", foreground=[("disabled", C["fg_off"])])

    # Flächen & Texte
    style.configure("TFrame", background=C["panel"])
    style.configure("App.TFrame", background=C["app"])
    style.configure("Bar.TFrame", background=C["bar"])
    style.configure("TLabel", background=C["panel"], foreground=C["fg"])
    style.configure("Bar.TLabel", background=C["bar"], foreground=C["fg"])
    style.configure("Title.TLabel", background=C["bar"], foreground=C["fg"], font=fonts["title"])
    style.configure("Version.TLabel", background=C["bar"], foreground=C["accent"], font=fonts["bold"])
    style.configure("BarHint.TLabel", background=C["bar"], foreground=C["fg_dim"], font=fonts["small"])
    style.configure("Hint.TLabel", background=C["panel"], foreground=C["fg_dim"], font=fonts["small"])
    style.configure("Header.TLabel", background=C["bar"], foreground=C["fg_dim"], font=fonts["header"])
    style.configure("Section.TLabel", background=C["panel"], foreground=C["accent"], font=fonts["header"])
    style.configure("Status.TLabel", background=C["bar"], foreground=C["fg_dim"])
    style.configure("TSeparator", background=C["border"])

    # Schaltflächen
    style.configure("TButton", background=C["button"], foreground=C["fg"], padding=(px(10), px(4)),
                    relief="flat", borderwidth=1, focusthickness=0, **flat)
    style.map("TButton",
              background=[("disabled", C["panel"]), ("pressed", C["border"]), ("active", C["button_hi"])],
              foreground=[("disabled", C["fg_off"])],
              bordercolor=[("focus", C["accent"])])
    style.configure("Accent.TButton", background=C["accent"], foreground=C["on_accent"],
                    font=fonts["bold"], padding=(px(20), px(8)), bordercolor=C["accent"],
                    lightcolor=C["accent"], darkcolor=C["accent"])
    style.map("Accent.TButton",
              background=[("disabled", C["accent_dim"]), ("pressed", C["accent"]),
                          ("active", C["accent_hi"])],
              foreground=[("disabled", C["fg_off"])],
              lightcolor=[("active", C["accent_hi"])], darkcolor=[("active", C["accent_hi"])],
              bordercolor=[("active", C["accent_hi"]), ("disabled", C["accent_dim"])])
    style.configure("Tool.TButton", background=C["bar"], foreground=C["fg"], padding=(px(10), px(5)),
                    bordercolor=C["bar"], lightcolor=C["bar"], darkcolor=C["bar"])
    style.map("Tool.TButton", background=[("active", C["button_hi"])],
              foreground=[("active", C["accent"]), ("disabled", C["fg_off"])])

    # Auswahl-Elemente
    for w in ("TRadiobutton", "TCheckbutton"):
        style.configure(w, background=C["panel"], foreground=C["fg"], indicatorbackground=C["input"],
                        indicatorforeground=C["accent"], upperbordercolor=C["border"],
                        lowerbordercolor=C["border"], focusthickness=0, padding=(0, px(1)))
        style.map(w,
                  background=[("active", C["panel"])],
                  foreground=[("disabled", C["fg_off"]), ("selected", C["fg"])],
                  indicatorbackground=[("disabled", C["panel"]), ("selected", C["input"])],
                  indicatorforeground=[("disabled", C["fg_off"]), ("selected", C["accent"])])
    style.configure("Bar.TCheckbutton", background=C["bar"])
    style.map("Bar.TCheckbutton", background=[("active", C["bar"])])

    # Eingabefelder
    field = dict(fieldbackground=C["input"], foreground=C["fg"], insertcolor=C["fg"],
                 selectbackground=C["accent"], selectforeground=C["on_accent"], padding=px(3), **flat)
    style.configure("TEntry", **field)
    style.configure("TSpinbox", arrowcolor=C["fg_dim"], background=C["button"], arrowsize=px(11), **field)
    style.configure("TCombobox", arrowcolor=C["fg_dim"], background=C["button"], arrowsize=px(12), **field)
    for w in ("TEntry", "TSpinbox"):
        style.map(w, fieldbackground=[("disabled", C["panel"]), ("readonly", C["panel"])],
                  foreground=[("disabled", C["fg_off"]), ("readonly", C["fg_dim"])],
                  bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])])
    style.map("TSpinbox", arrowcolor=[("active", C["accent"]), ("disabled", C["fg_off"])],
              background=[("active", C["button_hi"])])
    style.map("TCombobox",
              fieldbackground=[("readonly", C["input"]), ("disabled", C["panel"])],
              foreground=[("disabled", C["fg_off"]), ("readonly", C["fg"])],
              background=[("active", C["button_hi"]), ("readonly", C["button"])],
              arrowcolor=[("active", C["accent"]), ("disabled", C["fg_off"])],
              selectbackground=[("readonly", C["input"])], selectforeground=[("readonly", C["fg"])],
              bordercolor=[("focus", C["accent"])])
    # Aufklappliste der Combobox (klassisches Tk-Widget)
    root.option_add("*TCombobox*Listbox.background", C["input"])
    root.option_add("*TCombobox*Listbox.foreground", C["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["on_accent"])
    root.option_add("*TCombobox*Listbox.font", normal)

    # Registerkarten (wie die Werkzeug-Tabs in Capture One)
    style.configure("TNotebook", background=C["panel"], borderwidth=0, tabmargins=(0, 0, 0, 0),
                    bordercolor=C["panel"], lightcolor=C["panel"], darkcolor=C["panel"])
    style.configure("TNotebook.Tab", background=C["bar"], foreground=C["fg_dim"], font=fonts["header"],
                    padding=(px(12), px(8)), borderwidth=0, bordercolor=C["bar"],
                    lightcolor=C["bar"], darkcolor=C["bar"], focuscolor=C["bar"])
    style.map("TNotebook.Tab",
              background=[("selected", C["panel"]), ("active", C["button"])],
              foreground=[("selected", C["accent"]), ("active", C["fg"])],
              lightcolor=[("selected", C["panel"])], bordercolor=[("selected", C["panel"])],
              expand=[("selected", (0, 0, 0, 0))])

    # Liste
    style.configure("Treeview", background=C["panel"], fieldbackground=C["panel"], foreground=C["fg"],
                    borderwidth=0, rowheight=normal.metrics("linespace") + px(8),
                    bordercolor=C["panel"], lightcolor=C["panel"], darkcolor=C["panel"])
    style.map("Treeview", background=[("selected", C["accent_dim"])],
              foreground=[("selected", C["fg"])])
    style.configure("Treeview.Heading", background=C["bar"], foreground=C["fg_dim"], font=fonts["header"],
                    relief="flat", padding=(px(6), px(5)), bordercolor=C["border"],
                    lightcolor=C["bar"], darkcolor=C["bar"])
    style.map("Treeview.Heading", background=[("active", C["button"])],
              foreground=[("active", C["fg"])])

    # Bildlauf, Fortschritt, Trenner
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=C["button"], troughcolor=C["panel"],
                        arrowcolor=C["fg_dim"], bordercolor=C["panel"], lightcolor=C["button"],
                        darkcolor=C["button"], gripcount=0, arrowsize=px(12))
        style.map(f"{orient}.TScrollbar", background=[("active", C["button_hi"])],
                  arrowcolor=[("active", C["accent"])])
    style.configure("Horizontal.TProgressbar", background=C["accent"], troughcolor=C["input"],
                    bordercolor=C["bar"], lightcolor=C["accent"], darkcolor=C["accent"],
                    thickness=px(6))
    style.configure("TPanedwindow", background=C["app"])
    style.configure("Sash", sashthickness=px(6), gripcount=0, background=C["app"],
                    bordercolor=C["app"], lightcolor=C["app"], darkcolor=C["app"])
    return fonts


_ICON_PATH: str | None = None   # Pfad zu icon.ico (wird von der App gesetzt)
_ICON_HANDLES: list = []        # Windows-Icon-Handles am Leben halten


def set_window_icon(window: tk.Misc, ico_path: str | None = None):
    """Windows: Logo oben links in der Titelleiste und in der Taskleiste setzen.

    Tk zeigt sonst unter Umständen die Tk-Feder oder ein unscharf skaliertes
    Bild. Hier wird das Symbol direkt über die Windows-API (WM_SETICON) aus der
    .ico-Datei geladen – jeweils in der Größe, die Windows für die aktuelle
    Bildschirm-Skalierung verlangt (16/20/24 px klein, 32/40/48 px groß).
    Auf anderen Systemen passiert nichts.
    """
    global _ICON_PATH
    if ico_path:
        _ICON_PATH = ico_path
    if sys.platform != "win32" or not _ICON_PATH:
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetParent.restype = wintypes.HWND
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

        window.update_idletasks()
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        try:   # Symbolgrößen passend zur DPI des Fensters (Windows 10 1607+)
            dpi = user32.GetDpiForWindow(hwnd)
            small = user32.GetSystemMetricsForDpi(49, dpi)   # SM_CXSMICON
            big = user32.GetSystemMetricsForDpi(11, dpi)     # SM_CXICON
        except Exception:
            small, big = user32.GetSystemMetrics(49), user32.GetSystemMetrics(11)
        IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x80
        for which, size in ((0, small), (1, big)):           # ICON_SMALL, ICON_BIG
            handle = user32.LoadImageW(None, _ICON_PATH, IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if handle:
                _ICON_HANDLES.append(handle)
                user32.SendMessageW(hwnd, WM_SETICON, which, handle)
    except Exception:
        pass


def dark_titlebar(window: tk.Misc):
    """Dunkle Titelleiste: Windows 10 (ab 20H1) / 11 und macOS (Tk ≥ 8.6.10)."""
    try:
        window.update_idletasks()
        if sys.platform == "win32":
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (neu, alt)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        elif sys.platform == "darwin":
            window.tk.call("::tk::unsupported::MacWindowStyle", "appearance", window, "darkaqua")
    except Exception:
        pass


# =============================================================================
# Dunkle Dialoge
# =============================================================================
class Dialog(tk.Toplevel):
    """Modales Meldungsfenster im dunklen Stil.

    ``buttons``: Liste von (Beschriftung, Rückgabewert, hervorgehoben?).
    Enter wählt die hervorgehobene Schaltfläche, Esc die letzte.
    """

    ICONS = {"info": ("i", "accent"), "warn": ("!", "accent"), "error": ("✕", "err"),
             "ask": ("?", "accent")}

    def __init__(self, parent, title: str, text: str, kind: str = "info", buttons=None):
        super().__init__(parent)
        self.result = None
        buttons = buttons or [("OK", True, True)]
        self.title(title)
        self.configure(bg=C["panel"])
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())

        body = ttk.Frame(self, padding=(22, 20, 22, 12))
        body.pack(fill="both", expand=True)
        sym, color = self.ICONS.get(kind, self.ICONS["info"])
        icon = tk.Label(body, text=sym, bg=C[color], fg=C["on_accent"], width=2,
                        font=tkfont.Font(size=16, weight="bold"))
        icon.grid(row=0, column=0, sticky="n", padx=(0, 16), ipady=2)
        ttk.Label(body, text=text, justify="left", wraplength=420).grid(row=0, column=1, sticky="w")

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 10))
        bar.pack(fill="x")
        default = None
        for label, value, primary in reversed(buttons):
            b = ttk.Button(bar, text=label, style="Accent.TButton" if primary else "TButton",
                           command=lambda v=value: self._close(v))
            if primary:
                b.configure(padding=(16, 5))
                default = value
            b.pack(side="right", padx=(8, 0))
        cancel = buttons[-1][1]
        self.bind("<Return>", lambda e: self._close(default if default is not None else cancel))
        self.bind("<KP_Enter>", lambda e: self._close(default if default is not None else cancel))
        self.bind("<Escape>", lambda e: self._close(cancel))
        self.protocol("WM_DELETE_WINDOW", lambda: self._close(cancel))

        self.update_idletasks()
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dark_titlebar(self)
        set_window_icon(self)
        self.grab_set()
        self.focus_set()

    def _close(self, value):
        """Dialog mit Rückgabewert schließen."""
        self.result = value
        self.grab_release()
        self.destroy()

    def show(self):
        """Dialog anzeigen und auf die Antwort warten."""
        self.wait_window()
        return self.result


def info(parent, title, text):
    """Dunkle Info-Meldung anzeigen."""
    Dialog(parent, title, text, "info").show()


def warn(parent, title, text):
    """Dunkle Warnung anzeigen."""
    Dialog(parent, title, text, "warn").show()


def error(parent, title, text):
    """Dunkle Fehlermeldung anzeigen."""
    Dialog(parent, title, text, "error").show()


def ask(parent, title, text, yes="Ja", no="Nein") -> bool:
    """Dunkle Ja/Nein-Rückfrage; True bei „Ja“."""
    return bool(Dialog(parent, title, text, "ask", [(yes, True, True), (no, False, False)]).show())


class InputDialog(Dialog):
    """Dunkles Eingabefenster für einen kurzen Text (z. B. Name einer Voreinstellung)."""

    def __init__(self, parent, title: str, prompt: str, initial: str = ""):
        self.var = tk.StringVar(value=initial)
        super().__init__(parent, title, prompt, "ask",
                         [("Speichern", "ok", True), ("Abbrechen", None, False)])
        body = self.winfo_children()[0]
        entry = ttk.Entry(body, textvariable=self.var, width=40)
        entry.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        entry.focus_set()
        entry.select_range(0, "end")

    def show(self):
        """Dialog anzeigen und auf die Antwort warten."""
        result = super().show()
        return self.var.get().strip() if result == "ok" else None


def ask_string(parent, title, prompt, initial="") -> str | None:
    """Dunkles Eingabefenster; gibt den Text oder None (Abbrechen) zurück."""
    return InputDialog(parent, title, prompt, initial).show()
