# -----------------------------------------------------------------------------
# FotoRahmen – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
# -----------------------------------------------------------------------------
"""Startet FotoRahmen automatisch, führt einen Stapellauf aus und erstellt Screenshots.

Aufruf:  python docs/werkzeuge/screenshots.py <Demo-Ordner mit Fotos>

Unter Linux ohne Bildschirm z. B. mit „xvfb-run -s '-screen 0 1400x900x24'“.
Screenshots landen in docs/bilder/, das Protokoll des Laufs in docs/bilder/lauf.txt.
Die Einstellungen werden in einem temporären Ordner gespeichert (die echten
Einstellungen des Benutzers bleiben unberührt).
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["APPDATA"] = os.environ["XDG_CONFIG_HOME"]

from PIL import ImageGrab  # noqa: E402

import fotorahmen as fr  # noqa: E402
import theme  # noqa: E402

OUT = ROOT / "docs" / "bilder"
OUT.mkdir(parents=True, exist_ok=True)
DEMO = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "beispiele" / "eingabe")
LOG = []

root = fr.create_root()
app = fr.App(root)
root.geometry("1320x860+0+0")


def shot(name, widget=None):
    root.update()
    w = widget or root
    x, y = w.winfo_rootx(), w.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height()),
                   xdisplay=os.environ.get("DISPLAY")).save(OUT / name)
    LOG.append(f"Screenshot: {name}")


def select(filename):
    for i, job in enumerate(app.jobs):
        if job.src.name == filename:
            app.tree.selection_set(str(i))
            app.tree.see(str(i))


steps = []


def step(delay):
    def deco(fn):
        steps.append((delay, fn))
        return fn
    return deco


@step(600)
def s_start():
    app.v["in_dir"].set(str(DEMO))
    app._on_in_dir_edited()
    LOG.append(f"Eingabe-Ordner: {DEMO}")
    LOG.append(f"Ausgabe-Ordner (automatisch): {app.v['out_dir'].get()}")
    LOG.append(f"Gefundene Bilder: {len(app.files)}")
    select("Bergsee_Abendrot.jpg")


@step(1500)
def s_rahmen():
    app.v["preset"].set("Galerie – Linie + Weiß")
    app.load_preset()
    app.notebook.select(0)
    select("Bergsee_Abendrot.jpg")


@step(1400)
def s_rahmen_shot():
    shot("01_hauptfenster_rahmen.png")
    app.v["text"].set("© {jahr} Stefan J. Kaiser")
    app.v["text_pos"].set("right")
    app.v["bottom_w"].set("4")
    app.notebook.select(1)
    select("Waldweg_Hochformat.jpg")


@step(1500)
def s_text_shot():
    shot("02_tab_text.png")
    app.v["preset"].set("Copyright-Schutz Web")
    app.load_preset()
    app.v["wm_text"].set("© {jahr} Stefan J. Kaiser")
    app.v["meta_author"].set("Stefan J. Kaiser")
    app.v["meta_copyright"].set("© {jahr} Stefan J. Kaiser")
    app.notebook.select(2)
    select("Bergsee_Abendrot.jpg")


@step(1500)
def s_schutz_shot():
    shot("03_tab_schutz.png")
    app.v["preset"].set("PNG mit Schatten")
    app.load_preset()
    app.notebook.select(3)
    select("Stadt_Nacht.png")


@step(1500)
def s_effekte_shot():
    shot("04_tab_effekte.png")
    app.v["preset"].set("Signatur unten")
    app.load_preset()
    app.v["text"].set("© {jahr} Stefan J. Kaiser")
    app.v["wm_on"].set(True)
    app.v["wm_text"].set("© {jahr} Stefan J. Kaiser")
    app.v["wm_pos"].set("br")
    app.var_wm_pos_label.set("Unten rechts")
    app.v["wm_opacity"].set("45")
    app.v["meta_on"].set(True)
    app.v["meta_author"].set("Stefan J. Kaiser")
    app.v["meta_copyright"].set("© {jahr} Stefan J. Kaiser")
    app.v["limit_on"].set(True)
    app.v["max_edge"].set("2048")
    app.notebook.select(4)
    select("Kueste_16bit.tif")


@step(1500)
def s_ausgabe_shot():
    shot("05_tab_ausgabe.png")
    for job in app.jobs:                          # einen Namen per Hand ändern
        if job.src.name == "Stadt_Nacht.png":
            app.overrides[str(job.src)] = "Skyline bei Nacht"
    app.refresh_names()
    app.start()
    LOG.append("Stapellauf gestartet")


@step(400)
def s_running():
    shot("06_verarbeitung_laeuft.png")


@step(6000)
def s_done():
    shot("07_fertig.png")
    LOG.append("Status: " + app.lbl_status.cget("text"))
    for job in app.run_jobs:
        LOG.append(f"  {job.src.name:26} -> {job.dst.name:32} {app.status.get(str(job.src), '')}")
    dlg = theme.Dialog(root, f"Über {fr.APP_NAME}", fr.app_info.ABOUT_TEXT)
    root.after(500, lambda: (shot("08_info_dialog.png", dlg), dlg._close(None)))


@step(1200)
def s_dialog():
    dlg = theme.InputDialog(root, "Voreinstellung speichern",
                            "Name der Voreinstellung (Rahmen, Text, Effekte und Ausgabeformat):", "Mein Stil")
    root.after(500, lambda: (shot("09_voreinstellung_speichern.png", dlg), dlg._close(None)))


@step(1200)
def s_end():
    (OUT / "lauf.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print("\n".join(LOG))
    root.destroy()


# Rückfragen automatisch beantworten (Lauf ohne Benutzer)
theme.ask = lambda *a, **k: False


def run_steps(i=0):
    if i < len(steps):
        delay, fn = steps[i]
        root.after(delay, lambda: (fn(), run_steps(i + 1)))


run_steps()
root.mainloop()
