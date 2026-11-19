# -----------------------------------------------------------------------------
# FotoRahmen – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
# -----------------------------------------------------------------------------
"""Erzeugt die PDF-Dokumentation docs/FotoRahmen_Dokumentation.pdf.

Aufruf (aus dem Projektordner):
    python docs/werkzeuge/beispielbilder.py          # Beispielbilder (einmalig/bei Änderungen)
    python docs/werkzeuge/screenshots.py <Ordner>    # Screenshots (braucht Bildschirm/Xvfb)
    python docs/werkzeuge/dokumentation_pdf.py       # dieses Skript

Teil A ist das Benutzerhandbuch, Teil B die technische Dokumentation. Die
Funktionsreferenz in Teil B wird automatisch aus den Docstrings des
Quellcodes erzeugt – nach Code-Änderungen das Skript einfach erneut ausführen.
Benötigt: reportlab, Pillow; Schrift DejaVu Sans (sonst Helvetica).
"""
import ast
import datetime
import sys
from pathlib import Path

from PIL import Image
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image as RLImage, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app_info  # noqa: E402

DOCS = ROOT / "docs"
BILDER = DOCS / "bilder"
BEISPIELE = DOCS / "beispiele"
PDF = DOCS / "FotoRahmen_Dokumentation.pdf"
TMP = DOCS / ".pdf_tmp"

ORANGE = colors.HexColor("#f28a1e")
DARK = colors.HexColor("#1c1c1c")
PANEL = colors.HexColor("#2e2e2e")
GREY = colors.HexColor("#6b6b6b")
LIGHT = colors.HexColor("#f4f1ec")

# --- Schriften ----------------------------------------------------------------
FONT, FONT_B, FONT_M = "Helvetica", "Helvetica-Bold", "Courier"
_dejavu = Path("/usr/share/fonts/truetype/dejavu")
for base in (_dejavu, Path("C:/Windows/Fonts"), Path("/Library/Fonts")):
    try:
        pdfmetrics.registerFont(TTFont("DV", str(base / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DV-B", str(base / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("DV-M", str(base / "DejaVuSansMono.ttf")))
        pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV", boldItalic="DV-B")
        FONT, FONT_B, FONT_M = "DV", "DV-B", "DV-M"
        break
    except Exception:
        continue

# --- Stile ------------------------------------------------------------------------
S = {
    "body": ParagraphStyle("body", fontName=FONT, fontSize=9.6, leading=14, spaceAfter=5),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=8, leading=11, textColor=GREY),
    "caption": ParagraphStyle("caption", fontName=FONT, fontSize=8, leading=10.5, textColor=GREY,
                              alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
    "h1": ParagraphStyle("h1", fontName=FONT_B, fontSize=19, leading=24, textColor=DARK,
                         spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=FONT_B, fontSize=13, leading=17, textColor=ORANGE,
                         spaceBefore=12, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName=FONT_B, fontSize=10.5, leading=14, textColor=DARK,
                         spaceBefore=8, spaceAfter=3),
    "part": ParagraphStyle("part", fontName=FONT_B, fontSize=30, leading=36, textColor=colors.white),
    "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=9.6, leading=14, leftIndent=12,
                             bulletIndent=2, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.4, leading=11),
    "cellb": ParagraphStyle("cellb", fontName=FONT_B, fontSize=8.4, leading=11),
    "code": ParagraphStyle("code", fontName=FONT_M, fontSize=7.8, leading=10.2, textColor=DARK,
                           backColor=LIGHT, borderPadding=5, leftIndent=4, spaceBefore=4, spaceAfter=8),
    "toc1": ParagraphStyle("toc1", fontName=FONT_B, fontSize=10, leading=15, leftIndent=0),
    "toc2": ParagraphStyle("toc2", fontName=FONT, fontSize=9, leading=13, leftIndent=14),
}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


# =============================================================================
# Hilfen
# =============================================================================
def P(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="•") for t in items]


def H1(text):
    p = Paragraph(text, S["h1"])
    p._toc = (0, text)
    return p


def H2(text):
    p = Paragraph(text, S["h2"])
    p._toc = (1, text)
    return p


def table(rows, widths, header=True, font=None):
    data = [[P(c, "cellb" if (header and i == 0) else "cell") if isinstance(c, str) else c for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8d2c8")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#faf8f4")]),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ece6dc"))]
    t.setStyle(TableStyle(style))
    return t


def img(path, width, max_h=None, border=False):
    """Bild einbinden (verkleinert als JPEG/PNG gespeichert, damit die PDF klein bleibt)."""
    path = Path(path)
    im = Image.open(path)
    if im.mode in ("I;16", "I", "F"):
        im = im.convert("I").point(lambda v: v / 257).convert("L")
    w = width
    h = w * im.height / im.width
    if max_h and h > max_h:
        h = max_h
        w = h * im.width / im.height
    TMP.mkdir(exist_ok=True)
    out = TMP / (path.stem + ("_t.png" if im.mode in ("RGBA", "LA", "P") else "_t.jpg"))
    target = (int(w / mm * 9), int(h / mm * 9))            # ca. 230 dpi
    im = im.copy()
    im.thumbnail(target, Image.Resampling.LANCZOS)
    if out.suffix == ".jpg":
        im.convert("RGB").save(out, quality=86)
    else:
        im.save(out)
    r = RLImage(str(out), width=w, height=h)
    if border:
        t = Table([[r]], colWidths=[w + 2])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfc8bc")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return t
    return r


def tiff16_preview(path):
    """16-Bit-TIFF als 8-Bit-PNG für die PDF."""
    import tifffile
    import numpy as np
    a = tifffile.imread(path)
    a8 = (a.astype("float32") / 257).clip(0, 255).astype("uint8")
    TMP.mkdir(exist_ok=True)
    out = TMP / (Path(path).stem + "_8bit.png")
    Image.fromarray(np.ascontiguousarray(a8)).save(out)
    return out


def checker_bg(path):
    """PNG mit Transparenz auf Karomuster legen, damit Schatten/Ecken sichtbar sind."""
    im = Image.open(path).convert("RGBA")
    tile = 24
    bg = Image.new("RGBA", im.size, (236, 236, 236, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(bg)
    for y in range(0, im.height, tile):
        for x in range(0, im.width, tile):
            if (x // tile + y // tile) % 2:
                d.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(214, 214, 214, 255))
    bg.alpha_composite(im)
    TMP.mkdir(exist_ok=True)
    out = TMP / (Path(path).stem + "_karo.jpg")
    bg.convert("RGB").save(out, quality=88)
    return out


# =============================================================================
# Seitenvorlagen
# =============================================================================
class Doc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=22 * mm, bottomMargin=18 * mm,
                         title=f"{app_info.APP_NAME} {app_info.VERSION} – Dokumentation",
                         author=app_info.AUTHOR, subject="Benutzerhandbuch und technische Dokumentation",
                         creator="FotoRahmen docs/werkzeuge/dokumentation_pdf.py")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        full = Frame(0, 0, PAGE_W, PAGE_H, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="titel", frames=[full], onPage=self.draw_title),
            PageTemplate(id="teil", frames=[Frame(MARGIN, 0, PAGE_W - 2 * MARGIN, PAGE_H * 0.62)],
                         onPage=self.draw_part),
            PageTemplate(id="normal", frames=[frame], onPage=self.draw_normal),
        ])

    def afterFlowable(self, flowable):
        toc = getattr(flowable, "_toc", None)
        if toc:
            level, text = toc
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            self.notify("TOCEntry", (level, text, self.page, key))

    # -- Titelseite
    def draw_title(self, c, doc):
        bg = TMP / "titel_bg.jpg"
        if not bg.exists():
            make_title_background(bg)
        c.drawImage(str(bg), 0, 0, PAGE_W, PAGE_H)
        logo = ROOT / "assets" / "icon.png"
        c.drawImage(str(logo), MARGIN, PAGE_H - 92 * mm, 52 * mm, 52 * mm, mask="auto")
        c.setFillColor(colors.white)
        c.setFont(FONT_B, 40)
        c.drawString(MARGIN, PAGE_H - 115 * mm, app_info.APP_NAME)
        c.setFillColor(ORANGE)
        c.setFont(FONT_B, 20)
        c.drawString(MARGIN, PAGE_H - 127 * mm, f"Version {app_info.VERSION}")
        c.setFillColor(colors.white)
        c.setFont(FONT, 14)
        c.drawString(MARGIN, PAGE_H - 142 * mm, "Rahmen und Copyright-Schutz für Fotos")
        c.drawString(MARGIN, PAGE_H - 149 * mm, "Stapelverarbeitung mit Vorschau · Windows und macOS")
        c.setFont(FONT_B, 12)
        c.setFillColor(ORANGE)
        c.drawString(MARGIN, PAGE_H - 170 * mm, "DOKUMENTATION")
        c.setFillColor(colors.white)
        c.setFont(FONT, 11)
        c.drawString(MARGIN, PAGE_H - 177 * mm, "Teil A  Benutzerhandbuch")
        c.drawString(MARGIN, PAGE_H - 183 * mm, "Teil B  Technische Dokumentation – Code, Änderungen, Bauen")
        c.setFont(FONT, 9)
        c.setFillColor(colors.HexColor("#d8d8d8"))
        y = 28 * mm
        for line in (app_info.COPYRIGHT, app_info.IDEA, app_info.IMPLEMENTATION,
                     f"Lizenz: {app_info.LICENSE_NAME} · Stand: {datetime.date.today():%d.%m.%Y}"):
            c.drawString(MARGIN, y, line)
            y -= 5 * mm

    # -- Trennseite für Teil A/B
    def draw_part(self, c, doc):
        c.setFillColor(DARK)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(ORANGE)
        c.rect(0, PAGE_H * 0.62, PAGE_W, 2.2 * mm, fill=1, stroke=0)
        c.drawImage(str(ROOT / "assets" / "icon.png"), PAGE_W - MARGIN - 30 * mm, PAGE_H - MARGIN - 30 * mm,
                    30 * mm, 30 * mm, mask="auto")

    # -- normale Seite
    def draw_normal(self, c, doc):
        c.saveState()
        c.setFillColor(DARK)
        c.rect(0, PAGE_H - 13 * mm, PAGE_W, 13 * mm, fill=1, stroke=0)
        c.setFillColor(ORANGE)
        c.rect(0, PAGE_H - 13.8 * mm, PAGE_W, 0.8 * mm, fill=1, stroke=0)
        c.drawImage(str(ROOT / "assets" / "logo_small.png"), MARGIN, PAGE_H - 11 * mm, 9 * mm, 9 * mm,
                    mask="auto")
        c.setFillColor(colors.white)
        c.setFont(FONT_B, 10)
        c.drawString(MARGIN + 12 * mm, PAGE_H - 8 * mm, app_info.APP_NAME)
        c.setFillColor(ORANGE)
        c.setFont(FONT_B, 9)
        c.drawString(MARGIN + 12 * mm + pdfmetrics.stringWidth(app_info.APP_NAME, FONT_B, 10) + 2 * mm,
                     PAGE_H - 8 * mm, app_info.VERSION)
        c.setFillColor(colors.HexColor("#bbbbbb"))
        c.setFont(FONT, 8)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 8 * mm, "Dokumentation")
        c.setFillColor(GREY)
        c.setFont(FONT, 7.5)
        c.drawString(MARGIN, 10 * mm, f"{app_info.COPYRIGHT} · Idee und Prompt: {app_info.AUTHOR} · "
                                      f"Umsetzung: Claude Opus 5.5 (Anthropic)")
        c.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Seite {doc.page}")
        c.restoreState()


def make_title_background(out):
    """Verlauf Orange -> Schwarz wie im Logo."""
    import numpy as np
    w, h = 620, 877
    yy, xx = np.mgrid[0:h, 0:w]
    t = np.clip((xx / w * 0.35 + (1 - yy / h) * 0.65), 0, 1)   # oben hell, unten dunkel
    t = t ** 1.6
    top = np.array([242, 138, 30], dtype=np.float32)
    mid = np.array([120, 50, 8], dtype=np.float32)
    bot = np.array([14, 14, 14], dtype=np.float32)
    a = np.where(t[..., None] > 0.5, mid + (top - mid) * ((t[..., None] - 0.5) * 2),
                 bot + (mid - bot) * (t[..., None] * 2))
    TMP.mkdir(exist_ok=True)
    Image.fromarray(a.astype("uint8")).save(out, quality=92)


def part_page(title, subtitle):
    return [NextPageTemplate("teil"), PageBreak(),
            Spacer(1, 22 * mm),
            Paragraph(title, S["part"]),
            Spacer(1, 6),
            Paragraph(subtitle, ParagraphStyle("ps", fontName=FONT, fontSize=13, leading=18,
                                               textColor=colors.HexColor("#dddddd"))),
            NextPageTemplate("normal"), PageBreak()]


# =============================================================================
# Diagramme
# =============================================================================
def flow_diagram(steps, width=170 * mm, box_h=11 * mm, color=ORANGE):
    """Waagerechtes Ablaufdiagramm: Kästen mit Pfeilen."""
    n = len(steps)
    gap = 6 * mm
    bw = (width - gap * (n - 1)) / n
    d = Drawing(width, box_h + 8 * mm)
    y = 4 * mm
    for i, (title, sub) in enumerate(steps):
        x = i * (bw + gap)
        d.add(Rect(x, y, bw, box_h, rx=2.5, ry=2.5, fillColor=DARK if i % 2 == 0 else PANEL,
                   strokeColor=color, strokeWidth=0.8))
        d.add(String(x + bw / 2, y + box_h - 4.2 * mm, title, fontName=FONT_B, fontSize=7.4,
                     fillColor=colors.white, textAnchor="middle"))
        d.add(String(x + bw / 2, y + 2.2 * mm, sub, fontName=FONT, fontSize=6.2,
                     fillColor=colors.HexColor("#d0d0d0"), textAnchor="middle"))
        if i < n - 1:
            ax = x + bw + 1 * mm
            d.add(Line(ax, y + box_h / 2, ax + gap - 2.5 * mm, y + box_h / 2, strokeColor=color,
                       strokeWidth=1.2))
            d.add(Polygon([ax + gap - 2.5 * mm, y + box_h / 2 + 1.4 * mm, ax + gap - 1 * mm, y + box_h / 2,
                           ax + gap - 2.5 * mm, y + box_h / 2 - 1.4 * mm], fillColor=color, strokeColor=color))
    return d


def module_diagram(width=170 * mm):
    """Module und ihre Abhängigkeiten."""
    d = Drawing(width, 62 * mm)

    def box(x, y, w, h, title, lines, accent=False):
        d.add(Rect(x, y, w, h, rx=3, ry=3, fillColor=DARK if accent else PANEL,
                   strokeColor=ORANGE, strokeWidth=1 if accent else 0.6))
        d.add(String(x + 3 * mm, y + h - 5 * mm, title, fontName=FONT_B, fontSize=8.5,
                     fillColor=ORANGE if accent else colors.white))
        for i, line in enumerate(lines):
            d.add(String(x + 3 * mm, y + h - 9.5 * mm - i * 3.6 * mm, line, fontName=FONT, fontSize=6.6,
                         fillColor=colors.HexColor("#d6d6d6")))

    def arrow(x1, y1, x2, y2):
        d.add(Line(x1, y1, x2, y2, strokeColor=ORANGE, strokeWidth=1))
        d.add(Polygon([x2, y2, x2 - 1.2 * mm, y2 + 2 * mm, x2 + 1.2 * mm, y2 + 2 * mm],
                      fillColor=ORANGE, strokeColor=ORANGE))

    box(0, 36 * mm, 80 * mm, 25 * mm, "fotorahmen.py  (Oberfläche)",
        ["Fenster, Tabs, Liste, Vorschau, Dialogabläufe", "Voreinstellungen, Drag & Drop, Einstellungsdatei",
         "Hintergrund-Threads + Event-Queue"], accent=True)
    box(90 * mm, 36 * mm, 80 * mm, 25 * mm, "theme.py  (Design)",
        ["Farbpalette C, ttk-Styles (clam)", "dunkle Dialoge info/warn/ask/ask_string",
         "dunkle Titelleiste, Fenster-Logo (Windows)"])
    box(0, 2 * mm, 80 * mm, 27 * mm, "rahmen_core.py  (Bildverarbeitung)",
        ["FrameSettings, compose(), process_file()", "Rahmen, Text, Wasserzeichen, Effekte",
         "16-Bit-TIFF, Metadaten, Dateinamen, Suche"], accent=True)
    box(90 * mm, 2 * mm, 80 * mm, 27 * mm, "app_info.py · Hilfsskripte",
        ["Name, Version, Copyright (eine Stelle)", "selftest.py, make_icons.py,",
         "make_version_info.py, docs/werkzeuge/*"])
    arrow(40 * mm, 36 * mm, 40 * mm, 29.5 * mm)
    d.add(Line(80 * mm, 48 * mm, 89 * mm, 48 * mm, strokeColor=ORANGE, strokeWidth=1))
    d.add(Polygon([89.5 * mm, 48 * mm, 87.5 * mm, 49.2 * mm, 87.5 * mm, 46.8 * mm], fillColor=ORANGE,
                  strokeColor=ORANGE))
    return d


# =============================================================================
# Automatische Code-Referenz aus den Docstrings
# =============================================================================
def code_reference(module_file, title):
    src = (ROOT / module_file).read_text(encoding="utf-8")
    tree = ast.parse(src)
    rows = [["Name", "Art", "Zeile", "Beschreibung (aus dem Docstring)"]]

    def first_par(doc):
        if not doc:
            return "–"
        text = doc.strip().split("\n\n")[0].replace("\n", " ")
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("``", ""))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            kind = "Klasse" if isinstance(node, ast.ClassDef) else "Funktion"
            sig = node.name
            if isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                sig = f"{node.name}({', '.join(args)})"
            rows.append([f"<font name='{FONT_M}'>{sig}</font>", kind, str(node.lineno),
                         first_par(ast.get_docstring(node))])
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef) and not sub.name.startswith("__"):
                        doc = ast.get_docstring(sub)
                        if not doc and sub.name.startswith("_"):
                            continue
                        args = [a.arg for a in sub.args.args if a.arg != "self"]
                        rows.append([f"<font name='{FONT_M}'>  .{sub.name}({', '.join(args)})</font>",
                                     "Methode", str(sub.lineno), first_par(doc)])
    module_doc = first_par(ast.get_docstring(tree))
    lines = src.count("\n") + 1
    return [H2(title),
            P(f"<b>{module_file}</b> – {lines} Zeilen. {module_doc}"),
            table(rows, [54 * mm, 19 * mm, 14 * mm, 87 * mm])]


# =============================================================================
# Inhalt
# =============================================================================
def build():
    story = []
    story += [NextPageTemplate("normal"), PageBreak()]

    # --- Inhaltsverzeichnis
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    story += [Paragraph("Inhalt", S["h1"]), toc]

    # ================= TEIL A ==================
    story += part_page("Teil A<br/>Benutzerhandbuch", "Installation, Bedienung, Beispiele, Tipps")

    story += [H1("1  Überblick"),
              P(f"<b>{app_info.APP_NAME}</b> legt Fotos stapelweise einen Rahmen um und schützt sie auf Wunsch mit "
                "einem transparenten Copyright-Wasserzeichen sowie Urheber- und Copyright-Angaben in den "
                "Metadaten. Die Originale werden <b>nur gelesen und nie verändert</b> – alle Ergebnisse landen "
                "im Ausgabe-Ordner, standardmäßig im Unterordner <b>„mit Rahmen“</b> des Eingabe-Ordners."),
              P("Die Anwendung läuft eigenständig als einzelne <b>FotoRahmen.exe</b> unter Windows 10/11 und als "
                "<b>FotoRahmen.app</b> unter macOS (Apple Silicon und Intel). Eine Installation von Python "
                "o. Ä. ist nicht nötig."),
              img(BILDER / "01_hauptfenster_rahmen.png", 174 * mm, border=True),
              P("Abb. 1: Hauptfenster im dunklen Design (Stil Capture One) mit Tab RAHMEN und Vorschau.", "caption"),
              H2("Funktionen auf einen Blick")]
    story += [table([
        ["Bereich", "Funktionen"],
        ["Rahmen", "Einfach oder doppelt (innen + außen); Weiß, Schwarz oder freie Farbe; Breite in Pixel oder % "
                   "der langen Bildkante; „Unten extra“ für den Galerie-Look"],
        ["Text", "Textzeile/Signatur im unteren Rand; Platzhalter {name}, {datum}, {jahr}; Größe, Position, Farbe, "
                 "eigene Schrift (.ttf/.otf)"],
        ["Schutz", "Transparentes Copyright-Wasserzeichen (Ecke, Mitte oder diagonal über das ganze Bild); "
                   "Urheber und Copyright in EXIF, XMP, PNG- und TIFF-Feldern"],
        ["Effekte", "Abgerundete Ecken und weicher Schatten (PNG/WebP mit Transparenz)"],
        ["Ausgabe", "Wie Original, JPEG, PNG, TIFF, WebP; Qualität; lange Kante begrenzen; Dateinamen-Vorlagen und "
                    "Einzelumbenennung; Verhalten bei vorhandenen Dateien"],
        ["Bedienung", "Live-Vorschau, Voreinstellungen, Drag & Drop, Unterordner, Abbrechen, Tastenkürzel, "
                      "Einstellungen bleiben erhalten"],
        ["Formate", "JPEG, TIFF (8/16 Bit, CMYK), PNG (auch 16 Bit, Transparenz), GIF/WebP (auch animiert), "
                    "HEIC/HEIF, BMP, JPEG 2000"],
    ], [28 * mm, 146 * mm])]

    story += [H1("2  Installation und erster Start"),
              H2("Windows"),
              *bullets(["<b>FotoRahmen-Windows.exe</b> herunterladen und an einen beliebigen Ort legen "
                        "(z. B. Desktop). Keine Installation nötig.",
                        "Beim ersten Start meldet SmartScreen „Der Computer wurde durch Windows geschützt“: "
                        "<b>Weitere Informationen → Trotzdem ausführen</b> (die App ist nicht kostenpflichtig signiert).",
                        "Die EXE entpackt sich beim Start kurz im Hintergrund (einige Sekunden).",
                        "Logo: in Taskleiste, Task-Manager, Explorer und oben links in der Titelleiste."]),
              H2("macOS"),
              *bullets(["ZIP für <b>Apple Silicon</b> (M1–M4) oder <b>Intel</b> entpacken und FotoRahmen.app in den "
                        "Programme-Ordner ziehen.",
                        "Erster Start: <b>Rechtsklick → Öffnen → Öffnen</b>. Meldet macOS „beschädigt“ oder „kann nicht "
                        "überprüft werden“: Systemeinstellungen → Datenschutz &amp; Sicherheit → „Dennoch öffnen“, oder "
                        "im Terminal <font name='%s'>xattr -cr /Applications/FotoRahmen.app</font>." % FONT_M,
                        "Logo im Dock, eigene Menüleiste mit „Über FotoRahmen“, ⌘O (Ordner) und ⌘↩ (Start)."]),
              H2("Programme selbst bauen"),
              P("Siehe Teil B, Kapitel „Bauen und veröffentlichen“. Kurz: Python 3.12 installieren, dann "
                "<font name='%s'>build_windows.bat</font> bzw. <font name='%s'>./build_macos.sh</font> – oder den Ordner "
                "zu GitHub hochladen, dann baut GitHub Actions EXE und Apps automatisch." % (FONT_M, FONT_M))]

    story += [H1("3  Bedienung Schritt für Schritt"),
              H2("Schritt 1 – Ordner wählen"),
              *bullets(["<b>Eingabe-Ordner</b> über „Durchsuchen…“ wählen oder Ordner/Bilder ins Fenster ziehen.",
                        "Der <b>Ausgabe-Ordner wird automatisch</b> auf <i>Eingabe-Ordner/mit Rahmen</i> gesetzt "
                        "(Häkchen „Ausgabe automatisch in Unterordner „mit Rahmen““). Das Feld ist dann gesperrt und "
                        "folgt jedem neuen Eingabe-Ordner.",
                        "Eigenen Ausgabe-Ordner wählen: „Durchsuchen…“ neben dem Ausgabe-Ordner – die Automatik wird "
                        "dabei ausgeschaltet. Häkchen wieder setzen = zurück zur Automatik.",
                        "„Unterordner einbeziehen“: Bilder in Unterordnern werden mit verarbeitet, die Struktur wird im "
                        "Ausgabe-Ordner nachgebildet. Der Ordner „mit Rahmen“ selbst wird dabei nie erneut verarbeitet."]),
              H2("Schritt 2 – Voreinstellung wählen (optional)"),
              P("Oben in der Werkzeugleiste stehen fertige Voreinstellungen: <i>Galerie – Linie + Weiß, Schwarzer Rand "
                "schmal, Signatur unten, Social Media 2048 px, Copyright-Schutz Web, PNG mit Schatten</i>. Eigene "
                "Einstellungen speichern Sie mit <b>Speichern…</b> unter einem Namen; <b>Löschen</b> entfernt die "
                "gewählte Voreinstellung."),
              img(BILDER / "09_voreinstellung_speichern.png", 95 * mm, border=True),
              P("Abb. 2: Voreinstellung speichern.", "caption"),
              H2("Schritt 3 – Rahmen einstellen (Tab RAHMEN)"),
              table([["Einstellung", "Bedeutung"],
                     ["Art", "Einfacher Rahmen oder doppelter Rahmen (innerer Rahmen direkt am Bild + äußerer Rahmen)"],
                     ["Breite in", "Pixel oder % der langen Bildkante – Prozent wirkt bei verschieden großen Bildern gleich"],
                     ["Breite", "Breite des (äußeren) Rahmens"],
                     ["Unten extra", "Zusätzlicher Rand unten – Galerie-Look, Platz für Signatur/Textzeile"],
                     ["Farbe", "Weiß, Schwarz oder „Farbe…“ (öffnet den Farbwähler; Klick aufs Farbfeld ebenso)"],
                     ["Innerer Rahmen", "Nur beim Doppelrahmen: Breite und Farbe der Linie direkt am Bild"]],
                    [32 * mm, 142 * mm])]

    story += [PageBreak(), H2("Schritt 4 – Textzeile/Signatur (Tab TEXT)"),
              img(BILDER / "02_tab_text.png", 174 * mm, border=True),
              P("Abb. 3: Tab TEXT – die Signatur erscheint rechts im unteren Rand.", "caption"),
              *bullets(["Text mit Platzhaltern: <b>{name}</b> = Dateiname, <b>{datum}</b> = heutiges Datum, "
                        "<b>{jahr}</b> = Jahr.",
                        "<b>Größe</b> in % der unteren Randhöhe, <b>Position</b> links/Mitte/rechts (bündig mit der "
                        "Bildkante), <b>Farbe</b>.",
                        "Schrift: eingebaut oder eigene .ttf/.otf-Datei (z. B. aus C:\\Windows\\Fonts oder /Library/Fonts).",
                        "Wichtig: Der Text braucht einen unteren Rand – im Tab RAHMEN „Unten extra“ z. B. auf 4–5 % setzen."]),
              PageBreak(),
              H2("Schritt 5 – Copyright-Schutz (Tab SCHUTZ)"),
              img(BILDER / "03_tab_schutz.png", 174 * mm, border=True),
              P("Abb. 4: Tab SCHUTZ – Wasserzeichen diagonal über das ganze Bild, Copyright in den Metadaten.",
                "caption"),
              table([["Einstellung", "Bedeutung"],
                     ["Transparentes Copyright", "Schaltet das sichtbare Wasserzeichen ein"],
                     ["Text", "z. B. „© {jahr} Vorname Nachname“ – Platzhalter wie im Tab TEXT"],
                     ["Deckkraft", "Transparenz in % – 20–40 % wirkt dezent, 60 % deutlich"],
                     ["Größe", "Schrifthöhe in % der kurzen Bildkante"],
                     ["Position", "Unten rechts/links, oben rechts/links, Mitte oder <b>diagonal über das ganze Bild</b> "
                                  "(bester Schutz – lässt sich nicht einfach wegschneiden)"],
                     ["Farbe, Kontrastkante", "Farbe des Textes; die Kante (Schwarz/Weiß) macht ihn auf hellen und "
                                              "dunklen Bildstellen lesbar"],
                     ["Metadaten", "Urheber und Copyright werden als EXIF (Artist, Copyright), XMP (dc:creator, "
                                   "dc:rights) bzw. PNG-/TIFF-Felder gespeichert – sichtbar in Lightroom, Capture One und "
                                   "den Datei-Eigenschaften"]],
                    [36 * mm, 138 * mm])]

    story += [PageBreak(), H2("Schritt 6 – Effekte (Tab EFFEKTE)"),
              img(BILDER / "04_tab_effekte.png", 174 * mm, border=True),
              P("Abb. 5: Tab EFFEKTE – abgerundete Ecken und Schatten (nur bei PNG/WebP).", "caption"),
              P("Abgerundete Ecken (Radius in % der kurzen Kante) und ein weicher Schatten (Größe in % der langen Kante) "
                "brauchen Transparenz und werden daher nur bei Ausgabe als <b>PNG</b> oder <b>WebP</b> angewendet. Der "
                "Tab zeigt an, ob die Effekte für das gewählte Format aktiv sind."),
              PageBreak(),
              H2("Schritt 7 – Ausgabe (Tab AUSGABE)"),
              img(BILDER / "05_tab_ausgabe.png", 174 * mm, border=True),
              P("Abb. 6: Tab AUSGABE – Format, Qualität, Größenbegrenzung und Dateinamen.", "caption"),
              table([["Einstellung", "Bedeutung"],
                     ["Dateiformat", "Wie Original, JPEG, PNG, TIFF oder WebP"],
                     ["Qualität", "Für JPEG, WebP und HEIC (empfohlen 92–95)"],
                     ["Lange Kante begrenzen", "Fertiges Bild inkl. Rahmen höchstens N Pixel – nur verkleinern, nie "
                                               "vergrößern (z. B. 2048 px für Social Media)"],
                     ["Dateiname", "Vorlage mit {name}, {nr} (001, 002 …), {datum}; Standard „{name}_rahmen“"],
                     ["Datei existiert", "Nummer anhängen (_2, _3 …), überschreiben (mit Rückfrage) oder überspringen"]],
                    [36 * mm, 138 * mm]),
              H2("Schritt 8 – Namen prüfen und starten"),
              *bullets(["Die Liste BILDER zeigt jede Datei mit ihrem künftigen Namen. <b>Doppelklick</b> (oder F2) auf "
                        "„Ausgabedatei“ ändert einen Namen einzeln (Enter = übernehmen, Esc = abbrechen); eigene Namen "
                        "erscheinen orange.",
                        "<b>RAHMEN ERSTELLEN</b> (oder Strg+Enter / ⌘+Enter) startet die Stapelverarbeitung. Während "
                        "des Laufs sind alle Eingaben gesperrt; <b>Abbrechen</b> stoppt nach dem aktuellen Bild.",
                        "Am Ende kann der Ausgabe-Ordner direkt geöffnet werden."]),
              img(BILDER / "07_fertig.png", 174 * mm, border=True),
              P("Abb. 7: Nach dem Stapellauf – alle Bilder grün „fertig“ mit Endgröße; "
                "„Skyline bei Nacht.png“ wurde von Hand umbenannt.", "caption")]

    # --- Beispiele
    sys.path.insert(0, str(DOCS / "werkzeuge"))
    import beispielbilder as bb
    pairs = {"einfach_weiss": "Bergsee_Abendrot.jpg", "galerie": "Waldweg_Hochformat.jpg",
             "schwarz_schmal": "Kueste_16bit.tif", "copyright_diagonal": "Bergsee_Abendrot.jpg",
             "schatten_png": "Stadt_Nacht.png", "farbe_copyright_ecke": "Stadt_Nacht.png"}
    story += [PageBreak(), H1("4  Beispiele – vorher / nachher"),
              P("Alle Beispiele wurden mit FotoRahmen 2.0 aus denselben vier Ausgangsbildern erzeugt "
                "(<font name='%s'>docs/beispiele/</font>). Die Ausgangsbilder sind rechnerisch erzeugt; die "
                "Einstellungen stehen jeweils darunter." % FONT_M)]
    for key, title, desc, _settings, _ext in bb.REZEPTE:
        src = BEISPIELE / "eingabe" / pairs[key]
        dst = next((BEISPIELE / "ausgabe").glob(f"{key}.*"))
        src_img = tiff16_preview(src) if src.suffix == ".tif" else src
        dst_img = tiff16_preview(dst) if dst.suffix == ".tif" else (checker_bg(dst) if dst.suffix == ".png" and key == "schatten_png" else dst)
        portrait = Image.open(src_img).height > Image.open(src_img).width
        w = 60 * mm if portrait else 84 * mm
        mh = 92 * mm
        block = [H2(title),
                 Table([[img(src_img, w, mh), img(dst_img, w, mh)],
                        [P("Vorher: " + src.name, "caption"), P("Nachher: " + dst.name, "caption")]],
                       colWidths=[87 * mm, 87 * mm],
                       style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                         ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])),
                 P("<b>Einstellungen:</b> " + desc)]
        story.append(KeepTogether(block))

    story += [PageBreak(), H1("5  Formate, Qualität und Metadaten"),
              table([["Format", "Lesen / Schreiben", "Hinweise"],
                     ["JPEG", "✓ / ✓", "EXIF, ICC-Farbprofil, DPI bleiben; EXIF-Drehung wird berücksichtigt; CMYK bleibt "
                                       "CMYK (Schwarz = reines K)"],
                     ["TIFF", "✓ / ✓", "8 und 16 Bit; 16-Bit-TIFF bleibt verlustfrei 16 Bit – auch mit Text, Wasserzeichen "
                                       "und Größenbegrenzung; Graustufen, RGB, RGBA, CMYK; mehrseitig: Seite 1"],
                     ["PNG", "✓ / ✓", "Transparenz, 16-Bit-Graustufen; Effekte (Ecken/Schatten)"],
                     ["WebP", "✓ / ✓", "auch animiert; Effekte möglich"],
                     ["GIF", "✓ / ✓", "animierte GIFs werden Bild für Bild gerahmt"],
                     ["HEIC/HEIF", "✓ / ✓", "iPhone-Fotos"],
                     ["BMP, JPEG 2000", "✓ / ✓", "–"],
                     ["RAW (CR3, NEF …)", "– / –", "bitte vorher als TIFF oder JPEG exportieren"]],
                    [30 * mm, 26 * mm, 118 * mm]),
              H2("Was mit den Originalen passiert"),
              P("Nichts. Quelldateien werden ausschließlich gelesen. Jede Ausgabe wird zuerst als temporäre Datei im "
                "Ausgabe-Ordner geschrieben und erst nach erfolgreichem Speichern umbenannt. Eingabe- und Ausgabe-Ordner "
                "müssen verschieden sein, und ein Ziel darf nie eine Quelldatei sein."),
              H1("6  Tipps und Fehlersuche"),
              table([["Problem", "Lösung"],
                     ["Text erscheint nicht", "Unterer Rand zu schmal – „Unten extra“ erhöhen; Textgröße ist relativ zur Randhöhe"],
                     ["Ecken/Schatten fehlen", "Nur bei Ausgabe als PNG oder WebP (Hinweis im Tab EFFEKTE)"],
                     ["Wasserzeichen zu auffällig", "Deckkraft 20–30 %, Größe 3–4 %, Kontrastkante aus"],
                     ["Drag & Drop geht nicht", "In der Kopfzeile ORDNER fehlt der Hinweis „Ordner oder Bilder hierher "
                                                "ziehen“ – dann Ordner über „Durchsuchen…“ wählen"],
                     ["Windows: SmartScreen-Warnung", "„Weitere Informationen“ → „Trotzdem ausführen“"],
                     ["macOS: „App ist beschädigt“", "xattr -cr /Applications/FotoRahmen.app"],
                     ["Altes Symbol in der Taskleiste", "Windows-Symbol-Cache – ab- und wieder anmelden"],
                     ["Einstellungen zurücksetzen", "Datei einstellungen.json löschen: Windows %APPDATA%\\FotoRahmen, "
                                                    "macOS ~/Library/Application Support/FotoRahmen"]],
                    [44 * mm, 130 * mm])]

    # ================= TEIL B ==================
    story += part_page("Teil B<br/>Technische Dokumentation",
                       "Aufbau, Code-Referenz, Änderungen vornehmen, Testen, Bauen")

    story += [H1("7  Architektur"),
              P("FotoRahmen ist in Python 3.12 geschrieben. Die Oberfläche nutzt Tkinter/ttk (in Python enthalten), die "
                "Bildverarbeitung Pillow, für 16-Bit-TIFF zusätzlich numpy, tifffile und imagecodecs, für HEIC "
                "pillow-heif und für Drag &amp; Drop tkinterdnd2. PyInstaller verpackt alles zu einer EXE bzw. App."),
              H2("Module"),
              module_diagram(),
              Spacer(1, 4),
              P("<b>Grundsätze:</b> (1) Originale sind unantastbar. (2) Bildverarbeitung (rahmen_core) kennt keine "
                "Oberfläche und ist allein testbar. (3) Vorschau und Ausgabe nutzen denselben Ablauf <b>compose()</b> – "
                "die Vorschau zeigt immer das Ergebnis. (4) Die Oberfläche blockiert nie: Laden und Verarbeiten laufen "
                "in Threads, die nur über eine Event-Queue mit dem Fenster sprechen. (5) Version und Copyright stehen an "
                "genau einer Stelle (app_info.py)."),
              H2("Verarbeitungsablauf compose()"),
              flow_diagram([("Einlesen", "EXIF-Drehung"), ("Skalieren", "lange Kante"),
                            ("Wasserzeichen", "ins Bild"), ("Rahmen", "Schichten"), ("Textzeile", "unterer Rand"),
                            ("Effekte", "PNG/WebP"), ("Speichern", "+ Metadaten")]),
              P("16-Bit-TIFF → TIFF läuft über einen eigenen Weg mit numpy (<i>_process_highbit_tiff</i>), der dieselben "
                "Schritte ausführt, ohne die Bittiefe zu verringern. Animierte GIF/WebP werden Bild für Bild über "
                "compose() geführt.", "small"),
              H2("Oberfläche und Threads"),
              flow_diagram([("Bedienelemente", "Tk-Variablen self.v"), ("get_settings()", "-> FrameSettings"),
                            ("Thread", "process_file()"), ("Event-Queue", "progress / item"),
                            ("_poll_events()", "alle 80 ms")]),
              table([["Nachricht", "Inhalt"],
                     ["(\"preview\", key, bild, größe, fehler)", "Vorschau geladen"],
                     ["(\"progress\", i, name, gesamt)", "Bild i wird bearbeitet"],
                     ["(\"item\", i, text)", "Ergebnis für Bild i: „fertig …“, „Fehler: …“, „übersprungen …“"],
                     ["(\"done\", ok, fehler, übersprungen, abgebrochen, ordner)", "Lauf beendet"]],
                    [78 * mm, 96 * mm]),
              KeepTogether([H2("Projektstruktur"),
              Preformatted("""FotoRahmen/
├── fotorahmen.py          Oberfläche, Einstiegspunkt main()
├── rahmen_core.py         Bildverarbeitung, Dateisuche, Namensplanung
├── theme.py               Dunkles Design, Dialoge, Fenster-Logo
├── app_info.py            Name, Version, Copyright (einzige Stelle)
├── selftest.py            Automatischer Funktionstest
├── make_icons.py          Logo Orange→Schwarz als png/ico/icns
├── make_version_info.py   Windows-Versionsressource
├── build_windows.bat      Build der EXE
├── build_macos.sh         Build der .app
├── requirements.txt       Python-Abhängigkeiten
├── assets/                icon.png, icon.ico, icon.icns, logo_small.png
├── docs/                  ENTWICKLER.md, PDF, Bilder, Beispiele, werkzeuge/
└── .github/workflows/     Automatischer Build für Windows + macOS""", S["code"])])]

    story += [PageBreak(), H1("8  Code-Referenz"),
              P("Die folgenden Tabellen werden beim Erzeugen dieser PDF automatisch aus dem Quellcode gelesen "
                "(Funktionsname, Zeile, erster Absatz des Docstrings). Interne Methoden ohne Docstring sind "
                "ausgelassen.")]
    story += code_reference("rahmen_core.py", "8.1  rahmen_core.py – Bildverarbeitung")
    story += code_reference("fotorahmen.py", "8.2  fotorahmen.py – Oberfläche")
    story += code_reference("theme.py", "8.3  theme.py – Design und Dialoge")

    story += [H2("Wichtige Datenstrukturen"),
              table([["Struktur", "Felder / Bedeutung"],
                     ["FrameSettings", "Rahmen: double, unit (px/pct), outer_width, outer_color, inner_width, inner_color, "
                                       "bottom_extra · Text: text, text_size, text_pos, text_color, text_font · Ausgabe: "
                                       "max_edge · Effekte: corner_radius, shadow · Schutz: wm_text, wm_opacity, wm_size, "
                                       "wm_pos, wm_color, wm_outline, meta_author, meta_copyright"],
                     ["Layer", "width (oben/links/rechts), bottom (unten), color – eine Rahmenschicht"],
                     ["Job", "src, dst, skip, note – eine geplante Verarbeitung"],
                     ["DEFAULTS", "Standardwerte aller Einstellungen der Oberfläche (Schlüssel = Einstellungsdatei)"],
                     ["PRESET_KEYS", "Welche Einstellungen zu einer Voreinstellung gehören"],
                     ["theme.C", "Farbpalette des dunklen Designs (Orange-Akzent #f28a1e)"]],
                    [32 * mm, 142 * mm])]

    story += [PageBreak(), H1("9  Änderungen vornehmen"),
              H2("Neue Rahmen-Option (Beispiel: Abstand zwischen innerem und äußerem Rahmen)"),
              *bullets(["<b>rahmen_core.FrameSettings</b>: Feld ergänzen, z. B. <i>gap_width: float = 0</i>.",
                        "<b>FrameSettings.layers()</b>: Schicht einfügen – alle Ausgabewege (compose, 16-Bit-Weg, "
                        "Vorschau) nutzen layers(), sonst ist im Kern nichts zu tun.",
                        "<b>fotorahmen.DEFAULTS</b> (und ggf. <b>PRESET_KEYS</b>): Schlüssel <i>gap_px</i>, <i>gap_pct</i>.",
                        "<b>App._tab_frame</b>: <i>self._number_row(box, zeile, \"Abstand\", \"gap_w\")</i> – sperrt sich "
                        "während des Laufs automatisch und aktualisiert die Vorschau.",
                        "<b>App._apply_unit</b> und <b>App.state_from_widgets</b>: den Schlüssel wie outer/inner/bottom "
                        "mitführen; <b>App.get_settings</b>: Wert übergeben.",
                        "<b>selftest.py</b> erweitern und ausführen."]),
              H2("Weitere typische Änderungen"),
              table([["Aufgabe", "Wo"],
                     ["Neues Eingabeformat", "rahmen_core.EXT_TO_FMT (Pillow muss es lesen können)"],
                     ["Neues Ausgabeformat", "rahmen_core.OUTPUT_FORMATS; bei Transparenz auch EFFECT_FORMATS"],
                     ["Neuer Platzhalter", "render_template() (Dateinamen) bzw. make_context() + expand_text() (Text, "
                                           "Wasserzeichen); Hinweistexte in den Tabs anpassen"],
                     ["Neue Wasserzeichen-Position", "WM_POSITIONS + watermark_masks(); Anzeige in WM_POS_LABELS"],
                     ["Neue mitgelieferte Voreinstellung", "fotorahmen.BUILTIN_PRESETS (nur Schlüssel aus PRESET_KEYS)"],
                     ["Neuer Tab", "App._build_tools: (\"Titel\", self._tab_neu) ergänzen, Methode _tab_neu(box) schreiben"],
                     ["Farben/Design", "theme.C (z. B. C[\"accent\"]); Schriftgrößen in apply_theme()"],
                     ["Logo", "Farben/Motiv in make_icons.py, danach python make_icons.py und neu bauen"],
                     ["Standard-Ausgabeordner", "fotorahmen.AUTO_OUT_NAME (\"mit Rahmen\"), Automatik: _sync_auto_out()"],
                     ["Version/Copyright", "nur app_info.py (+ CHANGELOG.md); EXE-Details und Info.plist folgen automatisch"],
                     ["Dokumentation", "docs/ENTWICKLER.md; PDF neu erzeugen mit docs/werkzeuge/dokumentation_pdf.py"]],
                    [50 * mm, 124 * mm])]

    selftest_log = (DOCS / "bilder" / "selftest.txt")
    story += [H1("10  Testen"),
              P("<b>selftest.py</b> erzeugt Testbilder aller Formate, verarbeitet jedes in jedes Ausgabeformat und prüft "
                "Endgrößen, Lesbarkeit, unveränderte Originale (byte-gleich), beschädigte Dateien, CMYK-Schwarz, "
                "Dateinamen-Bereinigung, Text, Größenbegrenzung, Effekte, WebP, Wasserzeichen und Copyright-Metadaten "
                "(auch 16-Bit-TIFF). Der automatische Build bricht bei einem Fehler ab."),
              Preformatted("python -m pip install -r requirements.txt\npython selftest.py\npython fotorahmen.py",
                           S["code"])]
    if selftest_log.exists():
        lines = selftest_log.read_text(encoding="utf-8").splitlines()
        ok = sum(1 for line in lines if line.startswith("OK"))
        story += [P(f"<b>Letzter Testlauf:</b> {ok} Prüfungen „OK“ – {lines[-1] if lines else ''}"),
                  Preformatted("\n".join(lines[:12] + ["…"] + lines[-3:]), S["code"])]
    story += [P("<b>Manuelle Prüfliste vor einer Veröffentlichung:</b> Logo in Titelleiste/Taskleiste/Task-Manager bzw. "
                "Dock/Menüleiste · Ordnerwahl und Ausgabe-Automatik · Drag &amp; Drop · Voreinstellungen · Text mit "
                "eigener Schrift · Wasserzeichen in allen Positionen · Metadaten in Lightroom/Datei-Eigenschaften · "
                "Effekte bei PNG · Start/Abbrechen · Neustart (Einstellungen erhalten).")]

    story += [H1("11  Bauen und veröffentlichen"),
              table([["Plattform", "Befehl", "Ergebnis"],
                     ["Windows", "build_windows.bat", "dist\\FotoRahmen.exe – eine Datei, Logo, Versionsinfo"],
                     ["macOS", "./build_macos.sh", "dist/FotoRahmen.app + dist/FotoRahmen-macOS.zip"],
                     ["Beide (automatisch)", "Push nach GitHub", "GitHub Actions baut, testet und startet EXE und beide "
                                                                 "Mac-Apps; bei Tag v* entsteht ein Release"]],
                    [32 * mm, 40 * mm, 102 * mm]),
              P("PyInstaller kann nicht über Betriebssysteme hinweg bauen – die EXE entsteht nur unter Windows, die App nur "
                "unter macOS. Deshalb gibt es den GitHub-Workflow <font name='%s'>.github/workflows/build.yml</font>." % FONT_M),
              H2("Neue Version veröffentlichen"),
              *bullets(["app_info.py: VERSION und RELEASE_DATE anpassen; CHANGELOG.md ergänzen.",
                        "python selftest.py",
                        "Commit, dann Tag: <font name='%s'>git tag v2.1.0 &amp;&amp; git push --tags</font> – GitHub "
                        "erstellt das Release mit EXE und Apps." % FONT_M]),
              H2("Signieren (optional)"),
              P("Ohne kostenpflichtige Signatur warnen Windows und macOS beim ersten Start. Für Starts ohne Warnung: "
                "Windows-Code-Signing-Zertifikat (signtool) bzw. Apple Developer ID mit Notarisierung (notarytool)."),
              H1("12  Bekannte Grenzen"),
              *bullets(["RAW-Formate werden nicht gelesen; mehrseitige TIFFs: nur Seite 1.",
                        "16-Bit-RGB nach PNG wird 8 Bit (Pillow-Grenze); 16 Bit bleibt bei TIFF → TIFF.",
                        "Bei 16-Bit-TIFF → TIFF werden ICC-Profil, Auflösung, Orientierung und Copyright übernommen, "
                        "sonstige EXIF/IPTC-Daten nicht.",
                        "Ein sichtbares Wasserzeichen erschwert Missbrauch, verhindert ihn aber nicht vollständig; "
                        "Metadaten können von anderen Programmen entfernt werden.",
                        "Farbwähler und Ordnerauswahl sind Systemdialoge (folgen dem System-Erscheinungsbild)."]),
              H1("13  Copyright und Lizenz"),
              P(f"{app_info.COPYRIGHT}<br/>{app_info.IDEA}<br/>{app_info.IMPLEMENTATION}<br/>"
                f"Lizenz: {app_info.LICENSE_NAME} – der Quellcode ist öffentlich. Der vollständige Lizenztext steht in "
                "der Datei LICENSE, die Prompts in PROMPT.md, alle Änderungen in CHANGELOG.md.")]
    return story


def main():
    TMP.mkdir(exist_ok=True)
    doc = Doc(str(PDF))
    story = build()
    doc.multiBuild(story)
    for f in TMP.iterdir():
        f.unlink()
    TMP.rmdir()
    print("PDF erstellt:", PDF)


if __name__ == "__main__":
    main()
