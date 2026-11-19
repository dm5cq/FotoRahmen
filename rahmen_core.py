# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3.–4. November 2026
# Lizenz: GNU GPL v3 – siehe Datei LICENSE
# -----------------------------------------------------------------------------
"""Bildverarbeitung von FotoRahmen (ohne Oberfläche, auch einzeln nutzbar).

Aufbau dieses Moduls
====================
1. Formate ............ welche Dateiendungen gelesen/geschrieben werden
2. FrameSettings ...... alle Rahmen-Einstellungen + Umrechnung in Pixel
3. Pillow-Hilfen ...... Farbwerte je Bildmodus, Rahmen anfügen, Modus-Umwandlung
4. 16-Bit-TIFF ........ verlustfreie Verarbeitung über numpy/tifffile
5. Vorschau ........... schnelles Laden + Rendern einer verkleinerten Vorschau
6. process_file() ..... eine Datei verarbeiten (Herzstück der Stapelverarbeitung)
7. Dateisuche/Namen ... Bilder finden, Ausgabenamen planen, Namenskonflikte lösen

Sicherheitsprinzip
==================
Originaldateien werden nur gelesen. Jede Ausgabe wird zuerst in eine
temporäre Datei im Zielordner geschrieben und erst nach erfolgreichem
Speichern per ``os.replace`` umbenannt. ``process_file`` verweigert außerdem,
wenn Quelle und Ziel derselbe Pfad wären.

Rahmen-Modell
=============
Ein Rahmen besteht aus Schichten (``Layer``) von innen nach außen. Jede
Schicht hat eine Breite in Pixeln (oben/links/rechts gleich) und eine Farbe.
Die äußerste Schicht kann unten zusätzlich verbreitert werden
(``bottom_extra``, „Galerie-Look“).
"""
from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from PIL import (Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps,
                 ImageSequence, PngImagePlugin, UnidentifiedImageError)

Image.MAX_IMAGE_PIXELS = None  # große Panoramen erlauben (lokales Werkzeug, keine fremden Uploads)

LANCZOS = Image.Resampling.LANCZOS

# --- optionale Bibliotheken ---------------------------------------------------
try:  # HEIC/HEIF (z. B. iPhone-Fotos)
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover - fehlt nur in Minimal-Installationen
    HEIF_OK = False

try:  # 16-Bit-TIFF verlustfrei verarbeiten
    import numpy as np
    import tifffile

    TIFFFILE_OK = True
except Exception:  # pragma: no cover
    TIFFFILE_OK = False


# =============================================================================
# 1. Formate
# =============================================================================
#: Dateiendung -> Pillow-Formatname. Alles hier wird gelesen und kann bei
#: „Wie Original“ auch wieder in diesem Format geschrieben werden.
EXT_TO_FMT = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".jfif": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF", ".tiff": "TIFF",
    ".gif": "GIF",
    ".bmp": "BMP",
    ".webp": "WEBP",
    ".jp2": "JPEG2000", ".j2k": "JPEG2000",
}
if HEIF_OK:
    EXT_TO_FMT.update({".heic": "HEIF", ".heif": "HEIF"})

INPUT_EXTS = frozenset(EXT_TO_FMT)

#: Anzeigename in der Oberfläche -> Dateiendung (None = Format des Originals).
OUTPUT_FORMATS = {
    "Wie Original": None,
    "JPEG (.jpg)": ".jpg",
    "PNG (.png)": ".png",
    "TIFF (.tif)": ".tif",
    "WebP (.webp)": ".webp",
}

#: Formate mit Transparenz – nur hier gibt es abgerundete Ecken und Schatten.
EFFECT_FORMATS = ("PNG", "WEBP")

#: Position der Textzeile
TEXT_POSITIONS = ("left", "center", "right")

#: Position des Wasserzeichens: unten rechts/links, oben rechts/links, Mitte,
#: diagonal über das ganze Bild wiederholt („tile“)
WM_POSITIONS = ("br", "bl", "tr", "tl", "c", "tile")

# Verhalten, wenn die Zieldatei schon existiert
CONFLICT_NUMBER = "number"        # _2, _3 … anhängen
CONFLICT_OVERWRITE = "overwrite"  # überschreiben
CONFLICT_SKIP = "skip"            # Datei überspringen

TMP_MARKER = ".fotorahmen-tmp"    # Kennzeichen temporärer Dateien


class ImageReadError(Exception):
    """Bild kann nicht gelesen werden (beschädigt, leer, unbekanntes Format)."""


# =============================================================================
# 2. Einstellungen
# =============================================================================
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """'#RRGGBB' oder '#RGB' -> (r, g, b) mit Werten 0–255."""
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        raise ValueError(f"Ungültige Farbe: #{value}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


class Layer(NamedTuple):
    """Eine Rahmenschicht: Breite (px) oben/links/rechts, Breite unten, Farbe."""
    width: int
    bottom: int
    color: tuple


@dataclass
class FrameSettings:
    """Alle Einstellungen eines Rahmens.

    Breiten sind je nach ``unit`` Pixel (``"px"``) oder Prozent der langen
    Bildkante (``"pct"``). Bei ``double=False`` wird nur der äußere Rahmen
    verwendet.
    """
    double: bool = False             # True = innerer + äußerer Rahmen
    unit: str = "px"                 # "px" oder "pct"
    outer_width: float = 40.0
    outer_color: tuple = (255, 255, 255)
    inner_width: float = 4.0
    inner_color: tuple = (0, 0, 0)
    bottom_extra: float = 0.0        # zusätzliche Breite unten (äußerer Rahmen)
    # Textzeile / Signatur im unteren Rand
    text: str = ""                   # Platzhalter: {name}, {datum}, {jahr}
    text_size: float = 45.0          # Schrifthöhe in % der unteren Randhöhe
    text_pos: str = "center"         # "left" / "center" / "right"
    text_color: tuple = (60, 60, 60)
    text_font: str = ""              # Pfad zu .ttf/.otf; leer = eingebaute Schrift
    # Ausgabegröße
    max_edge: int = 0                # lange Kante des Ergebnisses höchstens … px (0 = aus)
    # Effekte (nur PNG/WebP)
    corner_radius: float = 0.0       # Eckenradius in % der kurzen Kante des Ergebnisses
    shadow: float = 0.0              # Schattengröße in % der langen Kante (0 = aus)
    # Copyright-Schutz: transparentes Wasserzeichen im Bild
    wm_text: str = ""                # leer = kein Wasserzeichen; Platzhalter wie bei text
    wm_opacity: float = 35.0         # Deckkraft in %
    wm_size: float = 5.0             # Schrifthöhe in % der kurzen Bildkante
    wm_pos: str = "br"               # siehe WM_POSITIONS
    wm_color: tuple = (255, 255, 255)
    wm_outline: bool = True          # dezente Kontrastkante für bessere Lesbarkeit
    # Copyright-Schutz: Metadaten (EXIF „Artist“/„Copyright“, PNG-Textfelder, TIFF-Tags)
    meta_author: str = ""
    meta_copyright: str = ""

    def to_px(self, value: float, w: int, h: int) -> int:
        """Einstellungswert in Pixel für ein Bild der Größe w × h umrechnen."""
        if value <= 0:
            return 0
        if self.unit == "pct":
            return max(1, round(max(w, h) * value / 100.0))
        return int(round(value))

    def layers(self, w: int, h: int) -> list[Layer]:
        """Rahmenschichten von innen nach außen für ein Bild der Größe w × h."""
        result: list[Layer] = []
        if self.double:
            px = self.to_px(self.inner_width, w, h)
            result.append(Layer(px, px, tuple(self.inner_color)))
        px = self.to_px(self.outer_width, w, h)
        result.append(Layer(px, px, tuple(self.outer_color)))
        result = [layer for layer in result if layer.width > 0]
        extra = self.to_px(self.bottom_extra, w, h)
        if extra:
            if result:
                last = result[-1]
                result[-1] = Layer(last.width, last.bottom + extra, last.color)
            else:  # nur unterer Rand ohne seitlichen Rahmen
                result.append(Layer(0, extra, tuple(self.outer_color)))
        return result

    def framed_size(self, w: int, h: int) -> tuple[int, int]:
        """Größe des fertigen Bildes (Breite, Höhe) inklusive Rahmen."""
        layers = self.layers(w, h)
        return (w + sum(2 * l.width for l in layers),
                h + sum(l.width + l.bottom for l in layers))


# =============================================================================
# 3. Pillow-Hilfen
# =============================================================================
def _lum(rgb) -> int:
    """Helligkeit (0–255) einer RGB-Farbe nach ITU-R BT.601."""
    r, g, b = rgb[:3]
    return int(round(0.299 * r + 0.587 * g + 0.114 * b))


def rgb_to_cmyk(rgb) -> tuple[int, int, int, int]:
    """RGB -> CMYK (0–255) mit echtem Schwarzanteil.

    Pillows eingebaute Umrechnung erzeugt für Schwarz C=M=Y=100 %, K=0 – für
    den Druck ungeeignet. Hier wird Schwarz zu reinem K.
    """
    r, g, b = (c / 255.0 for c in rgb[:3])
    k = 1.0 - max(r, g, b)
    if k >= 1.0:
        return (0, 0, 0, 255)
    c = (1.0 - r - k) / (1.0 - k)
    m = (1.0 - g - k) / (1.0 - k)
    y = (1.0 - b - k) / (1.0 - k)
    return tuple(int(round(v * 255)) for v in (c, m, y, k))  # type: ignore[return-value]


def fill_for_mode(rgb, mode: str):
    """RGB-Farbe (0–255) in einen Füllwert für den Pillow-Bildmodus umrechnen."""
    r, g, b = rgb[:3]
    if mode == "RGB":
        return (r, g, b)
    if mode in ("RGBA", "RGBX"):
        return (r, g, b, 255)
    if mode == "L":
        return _lum(rgb)
    if mode == "LA":
        return (_lum(rgb), 255)
    if mode == "CMYK":
        return rgb_to_cmyk(rgb)
    if mode.startswith("I"):           # 16/32-Bit-Graustufen
        return _lum(rgb) * 257
    if mode == "F":
        return float(_lum(rgb)) / 255.0
    return Image.new("RGB", (1, 1), (r, g, b)).convert(mode).getpixel((0, 0))


def normalize_mode(img: Image.Image) -> Image.Image:
    """Exotische Modi in solche umwandeln, die sich sauber erweitern lassen."""
    m = img.mode
    if m == "1":
        return img.convert("L")
    if m == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if m == "PA":
        return img.convert("RGBA")
    if m in ("LAB", "HSV", "YCbCr"):
        return img.convert("RGB")
    if m in ("I;16B", "I;16L", "I;16N"):
        return img.convert("I;16")
    return img


def add_frame(img: Image.Image, layers) -> Image.Image:
    """Rahmenschichten (von innen nach außen) um ein Pillow-Bild legen."""
    for layer in layers:
        if layer.width <= 0 and layer.bottom <= 0:
            continue
        new = Image.new(img.mode,
                        (img.width + 2 * layer.width, img.height + layer.width + layer.bottom),
                        fill_for_mode(layer.color, img.mode))
        new.paste(img, (layer.width, layer.width))
        img = new
    return img


def _to_8bit_gray(img: Image.Image) -> Image.Image:
    """Beliebiges Graustufen-/16-Bit-/Float-Bild in 8-Bit-Graustufen („L“) umwandeln."""
    if img.mode.startswith("I"):
        img = img.convert("I") if img.mode != "I" else img
        return img.point(lambda v: v * (1 / 257.0)).convert("L")
    if img.mode == "F":
        return img.point(lambda v: v * 255.0).convert("L")
    return img.convert("L")


def to_display(img: Image.Image) -> Image.Image:
    """Für die Bildschirm-Vorschau: RGB oder RGBA mit 8 Bit."""
    img = normalize_mode(img)
    if img.mode in ("RGB", "RGBA"):
        return img
    if img.mode == "LA":
        return img.convert("RGBA")
    if img.mode.startswith("I") or img.mode == "F":
        return _to_8bit_gray(img).convert("RGB")
    return img.convert("RGB")


def _flatten(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """Transparenz auf weißen Hintergrund legen (für Formate ohne Alpha)."""
    if img.mode in ("RGBA", "LA"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", img.size, background)
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img


def convert_for_format(img: Image.Image, fmt: str) -> Image.Image:
    """Bildmodus so anpassen, dass ``fmt`` ihn speichern kann."""
    m = img.mode
    if fmt == "JPEG":
        img = _flatten(img)
        if img.mode.startswith("I") or img.mode == "F":
            return _to_8bit_gray(img)
        return img if img.mode in ("L", "RGB", "CMYK") else img.convert("RGB")
    if fmt == "PNG":
        if m == "CMYK":
            return img.convert("RGB")
        if m == "F":
            return _to_8bit_gray(img)
        return img
    if fmt == "TIFF":
        return img
    if fmt == "GIF":
        return img if m in ("RGB", "RGBA", "L", "P") else to_display(img)
    if fmt == "BMP":
        img = _flatten(img)
        if img.mode.startswith("I") or img.mode == "F":
            return _to_8bit_gray(img)
        return img if img.mode in ("RGB", "L") else img.convert("RGB")
    if fmt in ("WEBP", "HEIF"):
        return img if img.mode in ("RGB", "RGBA") else to_display(img)
    if fmt == "JPEG2000":
        return img if m in ("L", "LA", "RGB", "RGBA", "I;16") else to_display(img)
    return img


def _open(path: Path) -> Image.Image:
    """Bild mit Pillow öffnen; verständliche Fehlermeldung statt Pillow-Fehler."""
    try:
        if Path(path).stat().st_size == 0:
            raise ImageReadError("Datei ist leer")
        return Image.open(path)
    except ImageReadError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ImageReadError("Datei ist beschädigt oder kein unterstütztes Bild") from exc


# =============================================================================
# 3b. Text, Größe, Effekte – und der gemeinsame Ablauf compose()
# =============================================================================
def expand_text(text: str, ctx: dict | None) -> str:
    """Platzhalter {name}, {datum}, {jahr} in der Textzeile ersetzen."""
    if not text:
        return ""
    ctx = ctx or {}
    for key in ("name", "datum", "jahr"):
        text = text.replace("{" + key + "}", str(ctx.get(key, "")))
    return text


_FONT_CACHE: dict = {}


def load_font(path: str, size: int):
    """Schrift laden: eigene .ttf/.otf-Datei oder die in Pillow eingebaute Schrift."""
    size = max(1, int(size))
    key = (path or "", size)
    if key not in _FONT_CACHE:
        font = None
        if path:
            try:
                font = ImageFont.truetype(path, size)
            except Exception:
                font = None
        if font is None:
            try:
                font = ImageFont.load_default(size=size)
            except Exception:   # sehr alte Pillow-Version ohne skalierbare Standardschrift
                font = ImageFont.load_default()
        if len(_FONT_CACHE) > 32:
            _FONT_CACHE.clear()
        _FONT_CACHE[key] = font
    return _FONT_CACHE[key]


def scale_layers(layers, scale: float) -> list[Layer]:
    """Schichtbreiten skalieren; vorhandene Linien bleiben mindestens 1 px breit."""
    def sc(v):
        return max(1, round(v * scale)) if v > 0 else 0
    return [Layer(sc(l.width), sc(l.bottom), l.color) for l in layers]


def _text_mask(fw: int, fh: int, layers, settings: FrameSettings, text: str):
    """Maske (Graustufen) mit der Textzeile für den unteren Rand.

    Rückgabe ``(maske, y0)`` – die Maske ist so breit wie das gerahmte Bild
    und so hoch wie der untere Rand der äußersten Schicht; ``y0`` ist ihre
    obere Kante. ``None``, wenn kein Platz für Text ist.
    """
    if not layers or not text.strip():
        return None
    band_h = layers[-1].bottom
    if band_h < 3:
        return None
    font_px = round(band_h * max(1.0, min(settings.text_size, 100.0)) / 100.0)
    if font_px < 2:
        return None
    font = load_font(settings.text_font, font_px)
    side = sum(l.width for l in layers)        # Abstand Außenkante -> Bildkante
    margin = max(side, font_px // 2)
    mask = Image.new("L", (fw, band_h), 0)
    draw = ImageDraw.Draw(mask)
    pos = settings.text_pos if settings.text_pos in TEXT_POSITIONS else "center"
    x, anchor = {"left": (margin, "lm"), "right": (fw - margin, "rm"),
                 "center": (fw / 2, "mm")}[pos]
    try:
        draw.text((x, band_h / 2), text, fill=255, font=font, anchor=anchor)
    except (ValueError, TypeError):            # Bitmap-Schrift ohne Anker-Unterstützung
        draw.text((max(0, x - (fw / 4 if pos == "center" else 0)), band_h / 4), text,
                  fill=255, font=font)
    return mask, fh - band_h


def _draw_text(img: Image.Image, layers, settings: FrameSettings, text: str) -> Image.Image:
    """Textzeile in den unteren Rand eines gerahmten Bildes schreiben (beliebiger Bildmodus)."""
    tm = _text_mask(img.width, img.height, layers, settings, text)
    if tm is None:
        return img
    mask, y0 = tm
    mode = img.mode
    work = img.convert("I") if mode == "I;16" else img
    color = Image.new(work.mode, mask.size, fill_for_mode(settings.text_color, work.mode))
    work.paste(color, (0, y0), mask)
    return work.convert("I;16") if mode == "I;16" else work


def _contrast_color(rgb) -> tuple:
    """Schwarz oder Weiß – je nachdem, was sich von ``rgb`` besser abhebt."""
    return (0, 0, 0) if _lum(rgb) > 140 else (255, 255, 255)


def watermark_masks(w: int, h: int, settings: FrameSettings, text: str):
    """Masken (Graustufen, Größe w × h) für das Wasserzeichen.

    Rückgabe ``(füllung, kontur)``; der Grauwert ist bereits die Deckkraft.
    ``kontur`` ist ``None``, wenn keine Kontrastkante gewünscht ist.
    Bei ``wm_pos == "tile"`` wird der Text um 30° gedreht und versetzt über
    das ganze Bild wiederholt (Schutz gegen Wegschneiden).
    """
    import math
    short = min(w, h)
    font_px = max(6, round(short * max(0.5, min(settings.wm_size, 50.0)) / 100.0))
    font = load_font(settings.text_font, font_px)
    alpha = round(255 * max(1.0, min(settings.wm_opacity, 100.0)) / 100.0)
    # Kontrastkante erst ab lesbarer Schriftgröße (sonst wirkt kleiner Text grau)
    stroke_w = max(1, font_px // 16) if (settings.wm_outline and font_px >= 14) else 0

    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    x0, y0, x1, y1 = probe.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    tw, th = max(1, x1 - x0), max(1, y1 - y0)
    fill_t = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(fill_t).text((-x0, -y0), text, font=font, fill=alpha)
    stroke_t = None
    if stroke_w:
        stroke_t = Image.new("L", (tw, th), 0)
        a2 = round(alpha * 0.55)
        ImageDraw.Draw(stroke_t).text((-x0, -y0), text, font=font, fill=a2,
                                      stroke_width=stroke_w, stroke_fill=a2)

    fill_m = Image.new("L", (w, h), 0)
    stroke_m = Image.new("L", (w, h), 0) if stroke_t is not None else None
    pos = settings.wm_pos if settings.wm_pos in WM_POSITIONS else "br"

    if pos != "tile":
        margin = round(short * 0.03)
        x = {"bl": margin, "tl": margin, "br": w - tw - margin, "tr": w - tw - margin}.get(pos, (w - tw) // 2)
        y = {"tl": margin, "tr": margin, "bl": h - th - margin, "br": h - th - margin}.get(pos, (h - th) // 2)
        fill_m.paste(fill_t, (x, y))
        if stroke_m is not None:
            stroke_m.paste(stroke_t, (x, y))
        return fill_m, stroke_m

    angle = 30
    rf = fill_t.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    rs = stroke_t.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True) if stroke_t else None
    rad = math.radians(angle)
    du, dv = tw * 1.6 + font_px * 2, th * 4.0          # Abstände entlang/quer zur Schriftrichtung
    cx, cy = w / 2, h / 2
    reach = int(math.hypot(w, h) / min(du, dv)) + 2
    for j in range(-reach, reach + 1):
        for i in range(-reach, reach + 1):
            u = i * du + (du / 2 if j % 2 else 0)
            v = j * dv
            px = cx + u * math.cos(rad) + v * math.sin(rad)
            py = cy - u * math.sin(rad) + v * math.cos(rad)
            bx, by = int(px - rf.width / 2), int(py - rf.height / 2)
            if bx > w or by > h or bx + rf.width < 0 or by + rf.height < 0:
                continue
            for src, dst in ((rf, fill_m), (rs, stroke_m)):
                if src is None:
                    continue
                box = (bx, by, bx + src.width, by + src.height)
                dst.paste(ImageChops.lighter(dst.crop(box), src), (bx, by))
    return fill_m, stroke_m


def _apply_watermark(img: Image.Image, settings: FrameSettings, text: str) -> Image.Image:
    """Transparentes Wasserzeichen in ein Pillow-Bild (beliebiger Modus) setzen."""
    fill_m, stroke_m = watermark_masks(img.width, img.height, settings, text)
    mode = img.mode
    work = img.convert("I") if mode == "I;16" else img
    if stroke_m is not None:
        work.paste(Image.new(work.mode, work.size, fill_for_mode(_contrast_color(settings.wm_color), work.mode)),
                   (0, 0), stroke_m)
    work.paste(Image.new(work.mode, work.size, fill_for_mode(settings.wm_color, work.mode)), (0, 0), fill_m)
    return work.convert("I;16") if mode == "I;16" else work


def _apply_watermark_array(arr, settings: FrameSettings, text: str, photometric: int, extrasamples):
    """Wasserzeichen in ein numpy-Bild (16 Bit/Float) überblenden; Alphakanal bleibt."""
    fill_m, stroke_m = watermark_masks(arr.shape[1], arr.shape[0], settings, text)
    channels = 1 if arr.ndim == 2 else arr.shape[2]
    maxv = _max_value(arr.dtype)
    out = arr.astype(np.float32)
    color_ch = channels - len(extrasamples or ()) if arr.ndim == 3 else 1
    for mask, rgb in ((stroke_m, _contrast_color(settings.wm_color)), (fill_m, settings.wm_color)):
        if mask is None:
            continue
        m = np.asarray(mask, dtype=np.float32) / 255.0
        val = np.array(_tiff_color(rgb, photometric, channels, maxv), dtype=np.float32)
        if arr.ndim == 2:
            out = out * (1 - m) + val[0] * m
        else:
            mm = m[:, :, None]
            out[..., :color_ch] = out[..., :color_ch] * (1 - mm) + val[:color_ch] * mm
    if np.issubdtype(arr.dtype, np.integer):
        out = np.clip(np.rint(out), 0, maxv)
    return out.astype(arr.dtype)


def metadata_values(settings: FrameSettings, ctx: dict | None) -> tuple[str, str]:
    """(Urheber, Copyright) mit ersetzten Platzhaltern; leere Texte = nichts schreiben."""
    return (expand_text(settings.meta_author, ctx).strip(),
            expand_text(settings.meta_copyright, ctx).strip())


def _exif_with_copyright(exif_bytes, author: str, copyright_: str):
    """EXIF um Artist (0x013B) und Copyright (0x8298) ergänzen (UTF-8)."""
    if not (author or copyright_):
        return exif_bytes
    ex = Image.Exif()
    if exif_bytes:
        try:
            ex.load(exif_bytes)
        except Exception:
            ex = Image.Exif()
    if author:
        ex[0x013B] = author.encode("utf-8")                 # Artist
        ex[0x9C9D] = (author + "\0").encode("utf-16-le")   # XPAuthor (Windows-Explorer „Autoren“)
    if copyright_:
        ex[0x8298] = copyright_.encode("utf-8")             # Copyright
    return ex.tobytes()


def xmp_packet(author: str, copyright_: str) -> bytes:
    """XMP-Metadaten (UTF-8) mit dc:creator, dc:rights und xmpRights:Marked.

    XMP ist der Unicode-fähige Standard, den Lightroom, Capture One, Bridge und
    die meisten Bildverwaltungen für Urheber und Copyright auswerten.
    """
    from xml.sax.saxutils import escape
    parts = []
    if author:
        parts.append(f"<dc:creator><rdf:Seq><rdf:li>{escape(author)}</rdf:li></rdf:Seq></dc:creator>")
    if copyright_:
        parts.append('<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">'
                     f"{escape(copyright_)}</rdf:li></rdf:Alt></dc:rights>"
                     "<xmpRights:Marked>True</xmpRights:Marked>")
    return ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/">'
            + "".join(parts) +
            '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>').encode("utf-8")


def effects_active(settings: FrameSettings, fmt: str | None) -> bool:
    """True, wenn Ecken/Schatten für dieses Zielformat angewendet werden."""
    return fmt in EFFECT_FORMATS and (settings.corner_radius > 0 or settings.shadow > 0)


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    """Ecken abrunden (geglättet), Bild muss RGBA sein."""
    w, h = img.size
    radius = min(radius, w // 2, h // 2)
    if radius < 1:
        return img
    ss = 4                                         # Überabtastung für glatte Kanten
    circle = Image.new("L", (2 * radius * ss, 2 * radius * ss), 0)
    ImageDraw.Draw(circle).ellipse((0, 0, 2 * radius * ss - 1, 2 * radius * ss - 1), fill=255)
    circle = circle.resize((2 * radius, 2 * radius), LANCZOS)
    mask = Image.new("L", (w, h), 255)
    r = radius
    mask.paste(circle.crop((0, 0, r, r)), (0, 0))
    mask.paste(circle.crop((r, 0, 2 * r, r)), (w - r, 0))
    mask.paste(circle.crop((0, r, r, 2 * r)), (0, h - r))
    mask.paste(circle.crop((r, r, 2 * r, 2 * r)), (w - r, h - r))
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    return img


def _drop_shadow(img: Image.Image, size: int) -> Image.Image:
    """Weichen Schatten nach rechts unten hinzufügen (Bild wird größer)."""
    if size < 1:
        return img
    pad, off = 2 * size, max(1, size // 2)
    W, H = img.width + 2 * pad, img.height + 2 * pad
    alpha = Image.new("L", (W, H), 0)
    alpha.paste(img.getchannel("A"), (pad + off, pad + off))
    k = max(1, size // 8)                          # verkleinert weichzeichnen = schnell
    small = alpha.resize((max(1, W // k), max(1, H // k)), Image.Resampling.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(max(0.5, size * 0.5 / k)))
    alpha = small.resize((W, H), Image.Resampling.BILINEAR).point(lambda v: int(v * 0.55))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.putalpha(alpha)
    out.alpha_composite(img, (pad, pad))
    return out


def apply_effects(img: Image.Image, settings: FrameSettings) -> Image.Image:
    """Abgerundete Ecken und Schatten (Ergebnis RGBA, 8 Bit)."""
    img = to_display(img).convert("RGBA")
    if settings.corner_radius > 0:
        img = _round_corners(img, round(min(img.size) * min(settings.corner_radius, 50) / 100.0))
    if settings.shadow > 0:
        img = _drop_shadow(img, round(max(img.size) * min(settings.shadow, 25) / 100.0))
    return img


def limit_scale(settings: FrameSettings, w: int, h: int, fmt: str | None = None) -> float:
    """Verkleinerungsfaktor, damit die lange Kante ≤ ``max_edge`` wird (sonst 1.0)."""
    if not settings.max_edge:
        return 1.0
    fw, fh = settings.framed_size(w, h)
    return min(1.0, settings.max_edge / max(fw, fh))


def output_size(settings: FrameSettings, w: int, h: int, fmt: str | None = None) -> tuple[int, int]:
    """Voraussichtliche Größe der Ausgabedatei (Breite, Höhe)."""
    s = limit_scale(settings, w, h)
    layers = scale_layers(settings.layers(w, h), s)
    W = max(1, round(w * s)) + sum(2 * l.width for l in layers)
    H = max(1, round(h * s)) + sum(l.width + l.bottom for l in layers)
    if effects_active(settings, fmt) and settings.shadow > 0:
        pad = 4 * round(max(W, H) * min(settings.shadow, 25) / 100.0)
        W, H = W + pad, H + pad
    if settings.max_edge and max(W, H) > settings.max_edge:
        k = settings.max_edge / max(W, H)
        W, H = max(1, round(W * k)), max(1, round(H * k))
    return W, H


def compose(img: Image.Image, settings: FrameSettings, scale: float = 1.0,
            orig_size=None, fmt: str | None = None, ctx: dict | None = None) -> Image.Image:
    """Gemeinsamer Ablauf für Ausgabe und Vorschau.

    1. Bild auf ``orig_size × scale`` bringen (``orig_size`` = Maße, auf die
       sich die Einstellungen beziehen; ``img`` darf eine Verkleinerung sein)
    2. Wasserzeichen ins Bild (Copyright-Schutz), dann Rahmenschichten anfügen
    3. Textzeile in den unteren Rand schreiben
    4. Effekte (nur PNG/WebP)
    5. falls nötig auf ``max_edge`` nachkorrigieren (nur bei scale-Begrenzung)
    """
    ow, oh = orig_size or img.size
    layers = settings.layers(ow, oh)
    tw, th = max(1, round(ow * scale)), max(1, round(oh * scale))
    if img.size != (tw, th):
        if img.mode == "I;16":
            img = img.convert("I").resize((tw, th), LANCZOS).convert("I;16")
        else:
            img = img.resize((tw, th), LANCZOS)
    if scale != 1.0:
        layers = scale_layers(layers, scale)
    wm = expand_text(settings.wm_text, ctx)
    if wm.strip():
        img = _apply_watermark(img, settings, wm)
    img = add_frame(img, layers)
    text = expand_text(settings.text, ctx)
    if text.strip():
        img = _draw_text(img, layers, settings, text)
    if effects_active(settings, fmt):
        img = apply_effects(img, settings)
    if orig_size is None and settings.max_edge and max(img.size) > settings.max_edge:
        k = settings.max_edge / max(img.size)
        work = img.convert("I") if img.mode == "I;16" else img
        work = work.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), LANCZOS)
        img = work.convert("I;16") if img.mode == "I;16" else work
    return img


# =============================================================================
# 4. 16-Bit-TIFF (tifffile)
# =============================================================================
def is_highbit_tiff(path: Path) -> bool:
    """True, wenn ``path`` ein TIFF mit mehr als 8 Bit je Kanal ist
    und von tifffile gelesen werden kann."""
    if not TIFFFILE_OK or Path(path).suffix.lower() not in (".tif", ".tiff"):
        return False
    try:
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            if np.dtype(page.dtype).itemsize <= 1:
                return False
            # Prüfen, ob die Kompression dekodierbar ist (z. B. LZW braucht imagecodecs).
            # Fehlt der Decoder, wird stattdessen Pillow verwendet.
            compression = int(page.compression)
            if compression not in (1, 8, 32946, 32773):   # ohne / zlib / packbits
                try:
                    import imagecodecs  # noqa: F401
                except Exception:
                    return False
            return True
    except Exception:
        return False


def _read_tiff_array(path: Path):
    """Seite 1 eines TIFF als Array (Höhe, Breite[, Kanäle]) plus Metadaten."""
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        arr = page.asarray()
        axes = page.axes
        if axes == "SYX":
            arr = np.moveaxis(arr, 0, -1)
        elif axes not in ("YX", "YXS"):
            raise ValueError(f"TIFF-Aufbau '{axes}' wird nicht unterstützt")
        tags = page.tags
        info = {
            "photometric": int(page.photometric),
            "extrasamples": tuple(int(e) for e in (page.extrasamples or ())),
            "icc": tags[34675].value if 34675 in tags else None,
            "orientation": int(tags[274].value) if 274 in tags else 1,
            "xres": tags[282].value if 282 in tags else None,
            "yres": tags[283].value if 283 in tags else None,
            "resunit": int(tags[296].value) if 296 in tags else None,
        }
    return arr, info


def _max_value(dtype):
    """Größter Wert eines Datentyps (z. B. 65535 für uint16, 1.0 für Float)."""
    return np.iinfo(dtype).max if np.issubdtype(dtype, np.integer) else 1.0


def _tiff_color(rgb, photometric: int, channels: int, maxv):
    """Füllwert je Kanal für ein TIFF-Array mit gegebener Farbinterpretation."""
    if photometric == 2:            # RGB
        base = [c / 255 * maxv for c in rgb[:3]]
    elif photometric == 1:          # Graustufen, schwarz = 0
        base = [_lum(rgb) / 255 * maxv]
    elif photometric == 0:          # Graustufen, weiß = 0
        base = [(255 - _lum(rgb)) / 255 * maxv]
    elif photometric == 5:          # CMYK
        base = [v / 255 * maxv for v in rgb_to_cmyk(rgb)]
    else:
        raise ValueError("Farbraum dieses TIFF wird nicht unterstützt")
    while len(base) < channels:     # Alpha/Zusatzkanäle: voll deckend
        base.append(maxv)
    return base[:channels]


def _pad_array(arr, layers, photometric):
    """Rahmenschichten um ein numpy-Bildarray legen (Bittiefe bleibt erhalten)."""
    channels = 1 if arr.ndim == 2 else arr.shape[2]
    maxv = _max_value(arr.dtype)
    for layer in layers:
        h, w = arr.shape[:2]
        t, b = layer.width, layer.bottom
        new = np.empty((h + t + b, w + 2 * t) + arr.shape[2:], dtype=arr.dtype)
        val = _tiff_color(layer.color, photometric, channels, maxv)
        new[...] = val[0] if arr.ndim == 2 else np.array(val, dtype=arr.dtype)
        new[t:t + h, t:t + w] = arr
        arr = new
    return arr


def _from_array(a, mode: str) -> Image.Image:
    """numpy-Array -> Pillow-Bild (ohne das in Pillow 13 entfernte ``mode``-Argument)."""
    a = np.ascontiguousarray(a)
    return Image.frombytes(mode, (a.shape[1], a.shape[0]), a.tobytes())


def _array_to_8bit_image(arr, photometric) -> Image.Image:
    """numpy-Bild (16 Bit/Float, beliebige Farbinterpretation) in ein 8-Bit-Pillow-Bild umwandeln."""
    maxv = _max_value(arr.dtype)
    a8 = np.clip(arr.astype(np.float32) / maxv * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if photometric == 0:
        a8 = 255 - a8
    if a8.ndim == 2:
        return _from_array(a8, "L")
    ch = a8.shape[2]
    if photometric == 5 and ch >= 4:
        return _from_array(a8[:, :, :4], "CMYK").convert("RGB")
    if ch == 1:
        return _from_array(a8[:, :, 0], "L")
    if ch == 2:
        return _from_array(a8, "LA")
    if ch == 3:
        return _from_array(a8, "RGB")
    return _from_array(a8[:, :, :4], "RGBA")


def _apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    """EXIF/TIFF-Orientierung (1–8) auf ein Bild anwenden."""
    T = Image.Transpose
    method = {2: T.FLIP_LEFT_RIGHT, 3: T.ROTATE_180, 4: T.FLIP_TOP_BOTTOM,
              5: T.TRANSPOSE, 6: T.ROTATE_270, 7: T.TRANSVERSE, 8: T.ROTATE_90}.get(orientation)
    return img.transpose(method) if method is not None else img


def _resize_array(arr, new_w: int, new_h: int):
    """numpy-Bild (auch 16 Bit/Float) hochwertig verkleinern – Kanal für Kanal."""
    dtype = arr.dtype
    channels = [arr] if arr.ndim == 2 else [arr[:, :, i] for i in range(arr.shape[2])]
    out = []
    for ch in channels:
        ch32 = np.ascontiguousarray(ch, dtype=np.float32)
        im = Image.frombytes("F", (ch32.shape[1], ch32.shape[0]), ch32.tobytes())
        r = im.resize((new_w, new_h), LANCZOS)
        out.append(np.frombuffer(r.tobytes(), dtype=np.float32).reshape(new_h, new_w))
    res = out[0] if arr.ndim == 2 else np.stack(out, axis=-1)
    if np.issubdtype(dtype, np.integer):
        res = np.clip(np.rint(res), 0, np.iinfo(dtype).max)
    return res.astype(dtype)


def _apply_orientation_array(arr, orientation: int):
    """Orientierung auf ein numpy-Array (Y, X[, C]) anwenden."""
    ops = {
        2: lambda a: a[:, ::-1], 3: lambda a: a[::-1, ::-1], 4: lambda a: a[::-1, :],
        5: lambda a: np.swapaxes(a, 0, 1),
        6: lambda a: np.rot90(a, -1), 7: lambda a: np.rot90(np.swapaxes(a, 0, 1), 2),
        8: lambda a: np.rot90(a, 1),
    }
    return np.ascontiguousarray(ops.get(orientation, lambda a: a)(arr))


def _process_highbit_tiff(src: Path, tmp: Path, settings: FrameSettings, ctx: dict):
    """16-Bit-TIFF -> 16-Bit-TIFF, verlustfrei, mit ICC-Profil und Auflösung.

    Unterstützt Rahmen, „Unten extra“, Text und die Begrenzung der langen
    Kante. Effekte (Ecken/Schatten) gibt es nur für PNG/WebP.
    """
    arr, info = _read_tiff_array(src)
    text = expand_text(settings.text, ctx)
    rotate = info["orientation"] != 1 and (settings.bottom_extra > 0 or text.strip())
    if rotate:   # breiter Rand/Text muss im Anzeigebild unten liegen -> Pixel drehen
        arr = _apply_orientation_array(arr, info["orientation"])
        info["orientation"] = 1
    h, w = arr.shape[:2]
    if info["orientation"] in (5, 6, 7, 8):   # Maße beziehen sich auf das Anzeigebild
        w, h = h, w
    layers = settings.layers(w, h)
    scale = limit_scale(settings, w, h)
    if scale < 1.0:
        tw, th = max(1, round(arr.shape[1] * scale)), max(1, round(arr.shape[0] * scale))
        arr = _resize_array(arr, tw, th)
        layers = scale_layers(layers, scale)
    wm = expand_text(settings.wm_text, ctx)
    if wm.strip():
        if info["orientation"] != 1:   # Wasserzeichen muss im Anzeigebild aufrecht stehen
            arr = _apply_orientation_array(arr, info["orientation"])
            info["orientation"] = 1
        arr = _apply_watermark_array(arr, settings, wm, info["photometric"], info["extrasamples"])
    arr = _pad_array(arr, layers, info["photometric"])
    if text.strip() and layers:
        tm = _text_mask(arr.shape[1], arr.shape[0], layers, settings, text)
        if tm is not None:
            mask, y0 = tm
            m = np.asarray(mask, dtype=np.float32) / 255.0
            region = arr[y0:y0 + m.shape[0]].astype(np.float32)
            channels = 1 if arr.ndim == 2 else arr.shape[2]
            val = np.array(_tiff_color(settings.text_color, info["photometric"], channels,
                                       _max_value(arr.dtype)), dtype=np.float32)
            if arr.ndim == 3:
                m = m[:, :, None]
            else:
                val = val[0]
            blended = region * (1 - m) + val * m
            if np.issubdtype(arr.dtype, np.integer):
                blended = np.clip(np.rint(blended), 0, np.iinfo(arr.dtype).max)
            arr[y0:y0 + m.shape[0]] = blended.astype(arr.dtype)
    if settings.max_edge and max(arr.shape[:2]) > settings.max_edge:
        k = settings.max_edge / max(arr.shape[:2])
        arr = _resize_array(arr, max(1, round(arr.shape[1] * k)), max(1, round(arr.shape[0] * k)))

    phot = {0: "miniswhite", 1: "minisblack", 2: "rgb", 5: "separated"}[info["photometric"]]
    kwargs = dict(photometric=phot, planarconfig="contig", metadata=None, compression="zlib")
    if info["extrasamples"]:
        kwargs["extrasamples"] = info["extrasamples"]
    extratags = []
    if info["icc"] is not None:
        icc = bytes(info["icc"])
        extratags.append((34675, 7, len(icc), icc, True))
    if info["orientation"] != 1:
        extratags.append((274, 3, 1, info["orientation"], True))
    author, copyright_ = metadata_values(settings, ctx)
    if author:
        extratags.append((315, "s", 0, author.encode("utf-8"), True))       # Artist
    if copyright_:
        extratags.append((33432, "s", 0, copyright_.encode("utf-8"), True))  # Copyright
    if author or copyright_:
        xmp = xmp_packet(author, copyright_)
        extratags.append((700, 1, len(xmp), xmp, True))                         # XMP
    if extratags:
        kwargs["extratags"] = extratags
    if info["xres"] and info["yres"]:
        kwargs["resolution"] = (info["xres"], info["yres"])
        if info["resunit"]:
            kwargs["resolutionunit"] = info["resunit"]
    try:
        tifffile.imwrite(tmp, arr, predictor=True, **kwargs)
    except Exception:
        tifffile.imwrite(tmp, arr, **kwargs)
    return arr.shape[1], arr.shape[0]


# =============================================================================
# 5. Vorschau
# =============================================================================
def load_preview(path: Path, max_size: int = 1600):
    """Verkleinertes Vorschaubild laden.

    Rückgabe: ``(bild, (breite, höhe))`` – ``bild`` ist RGB/RGBA mit maximal
    ``max_size`` Pixeln Kantenlänge, die Größe ist die des Originals nach
    Berücksichtigung der Drehung (EXIF-Orientierung).
    """
    path = Path(path)
    if is_highbit_tiff(path):
        arr, info = _read_tiff_array(path)
        h, w = arr.shape[:2]
        step = max(1, max(w, h) // max_size)
        img = _array_to_8bit_image(arr[::step, ::step], info["photometric"])
        img = _apply_orientation(img, info["orientation"])
        size = (h, w) if info["orientation"] in (5, 6, 7, 8) else (w, h)
        img.thumbnail((max_size, max_size), LANCZOS)
        return to_display(img), size

    with _open(path) as im:
        try:
            orientation = int(im.getexif().get(0x0112, 1))
        except Exception:
            orientation = 1
        w, h = im.size
        size = (h, w) if orientation in (5, 6, 7, 8) else (w, h)
        if im.format == "JPEG":
            im.draft("RGB", (max_size, max_size))   # JPEG direkt verkleinert dekodieren
        try:
            img = ImageOps.exif_transpose(im)
            img = to_display(img)
            img.thumbnail((max_size, max_size), LANCZOS)
            img.load()
        except (OSError, SyntaxError) as exc:
            raise ImageReadError("Datei ist beschädigt oder unvollständig") from exc
    return img, size


def render_preview(thumb: Image.Image, orig_size, settings: FrameSettings,
                   box_w: int, box_h: int, fmt: str | None = None,
                   ctx: dict | None = None) -> Image.Image:
    """Vorschau des Ergebnisses, passend in ``box_w × box_h`` skaliert.

    Rahmen, Text und Effekte werden aus der Originalgröße berechnet, damit die
    Vorschau den Proportionen des Ergebnisses entspricht. ``fmt`` ist das
    Zielformat (Effekte nur bei PNG/WebP). Dünne Linien bleiben min. 1 px.
    """
    ow, oh = orig_size
    fw, fh = settings.framed_size(ow, oh)
    pad = 4 * max(fw, fh) * settings.shadow / 100.0 if effects_active(settings, fmt) else 0.0
    disp = max(min(box_w / (fw + pad), box_h / (fh + pad)), 1e-6)
    return compose(to_display(thumb), settings, scale=disp, orig_size=orig_size, fmt=fmt, ctx=ctx)


# =============================================================================
# 6. Verarbeitung einer Datei
# =============================================================================
def _exif_bytes(img: Image.Image):
    """EXIF-Daten als Bytes, Orientierung auf 1 („normal“) gesetzt."""
    try:
        exif = img.getexif()
        if not exif:
            return None
        if 0x0112 in exif:
            exif[0x0112] = 1
        return exif.tobytes()
    except Exception:
        return None


def make_context(src: Path) -> dict:
    """Werte für Platzhalter in der Textzeile."""
    today = datetime.date.today()
    return {"name": Path(src).stem, "datum": today.isoformat(), "jahr": str(today.year)}


def process_file(src: Path, dst: Path, settings: FrameSettings, quality: int = 95):
    """Rahmen um ``src`` legen und als ``dst`` speichern.

    Das Ausgabeformat ergibt sich aus der Endung von ``dst``. ``quality`` gilt
    für JPEG, WebP und HEIC. Rückgabe: Größe des Ergebnisses (Breite, Höhe).
    Löst ``ImageReadError`` aus, wenn die Quelle nicht lesbar ist.
    """
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("Ziel wäre die Originaldatei – abgebrochen")
    fmt = EXT_TO_FMT.get(dst.suffix.lower())
    if fmt is None:
        raise ValueError(f"Ausgabeformat {dst.suffix} wird nicht unterstützt")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.stem}{TMP_MARKER}{dst.suffix}")
    ctx = make_context(src)
    try:
        highbit = is_highbit_tiff(src)
        if fmt == "TIFF" and highbit:
            size = _process_highbit_tiff(src, tmp, settings, ctx)
        else:
            size = _process_with_pillow(src, tmp, fmt, settings, quality, highbit, ctx)
        os.replace(tmp, dst)
        return size
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _process_with_pillow(src: Path, tmp: Path, fmt: str, settings: FrameSettings,
                         quality: int, highbit: bool, ctx: dict):
    """Verarbeitung über Pillow (alle Formate außer 16-Bit-TIFF → TIFF); öffnet, dreht, rahmt, speichert."""
    if highbit:                       # 16-Bit-TIFF -> anderes Zielformat
        arr, tinfo = _read_tiff_array(src)
        if fmt in ("PNG", "JPEG2000") and arr.ndim == 2 and arr.dtype == np.uint16 \
                and tinfo["photometric"] == 1 and not effects_active(settings, fmt):
            img = _from_array(arr, "I;16")         # 16-Bit-Graustufen bleiben 16 Bit
        else:
            img = _array_to_8bit_image(arr, tinfo["photometric"])
        img = _apply_orientation(img, tinfo["orientation"])
        info = {"icc_profile": bytes(tinfo["icc"])} if tinfo["icc"] is not None else {}
        return _save_single(img, tmp, fmt, settings, quality, info, None, ctx)

    with _open(src) as im:
        info = dict(im.info)
        n_frames = getattr(im, "n_frames", 1)
        try:
            if n_frames > 1 and ((fmt == "GIF" and im.format == "GIF") or
                                 (fmt == "WEBP" and im.format == "WEBP")):
                return _save_animated(im, tmp, fmt, settings, quality, ctx)
            im.seek(0)
            img = ImageOps.exif_transpose(im)
        except (OSError, SyntaxError) as exc:
            raise ImageReadError("Datei ist beschädigt oder unvollständig") from exc
        exif = _exif_bytes(img)
        return _save_single(img, tmp, fmt, settings, quality, info, exif, ctx)


def _save_single(img, tmp, fmt, settings, quality, info, exif, ctx):
    """Einzelbild durch compose() führen, in das Zielformat wandeln und mit Metadaten speichern."""
    img = normalize_mode(img)
    src_mode = img.mode
    out = compose(img, settings, scale=limit_scale(settings, *img.size), fmt=fmt, ctx=ctx)
    out = convert_for_format(out, fmt)

    icc = info.get("icc_profile")
    if (src_mode == "CMYK") != (out.mode == "CMYK"):
        icc = None                    # Profil passt nicht mehr zum Farbraum
    dpi = info.get("dpi")

    author, copyright_ = metadata_values(settings, ctx)
    has_meta = bool(author or copyright_)
    xmp = xmp_packet(author, copyright_) if has_meta else None
    if fmt in ("JPEG", "PNG", "WEBP", "HEIF"):
        exif = _exif_with_copyright(exif, author, copyright_)

    meta = {}
    if icc and fmt != "GIF":
        meta["icc_profile"] = icc
    if exif and fmt in ("JPEG", "PNG", "WEBP", "TIFF", "HEIF"):
        if not (fmt == "JPEG" and len(exif) > 65000):   # JPEG-Grenze für EXIF
            meta["exif"] = exif
    if dpi and fmt in ("JPEG", "PNG", "TIFF", "BMP"):
        try:
            meta["dpi"] = tuple(float(d) for d in dpi)
        except (TypeError, ValueError):
            pass
    if has_meta:
        if fmt in ("JPEG", "WEBP", "HEIF"):
            meta["xmp"] = xmp
        elif fmt == "PNG":
            info_png = PngImagePlugin.PngInfo()
            if author:
                info_png.add_itxt("Author", author)
            if copyright_:
                info_png.add_itxt("Copyright", copyright_)
            info_png.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8"))
            meta["pnginfo"] = info_png
        elif fmt == "TIFF":
            from PIL import TiffImagePlugin
            ifd = TiffImagePlugin.ImageFileDirectory_v2()
            for tag, value in ((315, author), (33432, copyright_)):
                if value:
                    ifd[tag] = value.encode("utf-8")
                    ifd.tagtype[tag] = 2
            ifd[700] = xmp
            ifd.tagtype[700] = 1
            meta["tiffinfo"] = ifd

    opts = {}
    if fmt == "JPEG":
        opts = dict(quality=int(quality), subsampling=0 if quality >= 90 else 2, optimize=True)
    elif fmt == "PNG":
        opts = dict(compress_level=6)
    elif fmt == "TIFF":
        comp = info.get("compression")
        opts = dict(compression=comp if comp in (
            "raw", "tiff_lzw", "tiff_adobe_deflate", "packbits") else "tiff_lzw")
    elif fmt == "WEBP":
        opts = dict(quality=int(quality), method=4)
    elif fmt == "HEIF":
        opts = dict(quality=int(quality))

    # Speichern – bei Problemen mit Metadaten schrittweise ohne sie erneut versuchen
    attempts = [meta, {k: v for k, v in meta.items() if k not in ("exif", "xmp")},
                {k: v for k, v in meta.items() if k in ("icc_profile", "dpi")}, {}]
    last_exc = None
    for m in attempts:
        try:
            out.save(tmp, format=fmt, **opts, **m)
            return out.size
        except Exception as exc:   # noqa: BLE001 – nächster Versuch
            last_exc = exc
    raise last_exc  # type: ignore[misc]


def _save_animated(im, tmp, fmt, settings, quality, ctx):
    """Animiertes GIF/WebP Bild für Bild rahmen."""
    frames, durations = [], []
    has_alpha = ("transparency" in im.info or im.mode in ("RGBA", "LA", "PA")
                 or effects_active(settings, fmt))
    scale = None
    for frame in ImageSequence.Iterator(im):
        durations.append(frame.info.get("duration", im.info.get("duration", 100)))
        f = frame.convert("RGBA" if has_alpha else "RGB")
        if scale is None:
            scale = limit_scale(settings, *f.size)
        frames.append(compose(f, settings, scale=scale, fmt=fmt, ctx=ctx))
    kwargs = dict(save_all=True, append_images=frames[1:], duration=durations,
                  loop=im.info.get("loop", 0))
    if fmt == "GIF":
        kwargs["disposal"] = 2
    else:
        kwargs["quality"] = int(quality)
    frames[0].save(tmp, format=fmt, **kwargs)
    return frames[0].size


# =============================================================================
# 7. Dateien finden & Ausgabenamen
# =============================================================================
def _natural_key(p: Path):
    """Sortierschlüssel: 'Bild2' vor 'Bild10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def scan_images(in_dir: Path, recursive: bool = False, exclude: Path | None = None) -> list[Path]:
    """Alle unterstützten Bilder in ``in_dir`` finden (natürlich sortiert).

    Versteckte Dateien und temporäre Dateien werden ignoriert. Liegt der
    Ausgabe-Ordner (``exclude``) innerhalb des Eingabe-Ordners, wird er
    übersprungen, damit Ergebnisse nicht erneut verarbeitet werden.
    """
    in_dir = Path(in_dir)
    if not in_dir.is_dir():
        return []
    exclude_r = Path(exclude).resolve() if exclude else None
    it = in_dir.rglob("*") if recursive else in_dir.iterdir()
    files = []
    for p in it:
        try:
            if p.name.startswith(".") or not p.is_file():
                continue
            if p.suffix.lower() not in INPUT_EXTS:
                continue
            if exclude_r is not None:
                rp = p.resolve()
                if exclude_r == rp.parent or exclude_r in rp.parents:
                    continue
            if recursive and any(part.startswith(".") for part in p.relative_to(in_dir).parts):
                continue
        except (OSError, ValueError):
            continue
        files.append(p)
    return sorted(files, key=_natural_key)


def cleanup_temp_files(out_dir: Path) -> int:
    """Reste abgebrochener Läufe (temporäre Dateien) im Ausgabe-Ordner löschen."""
    count = 0
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return 0
    for p in out_dir.rglob(f".*{TMP_MARKER}*"):
        try:
            p.unlink()
            count += 1
        except OSError:
            pass
    return count


_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def sanitize_stem(stem: str) -> str:
    """Dateinamen (ohne Endung) für Windows und macOS gültig machen."""
    stem = _ILLEGAL.sub("_", stem).strip().rstrip(". ")
    if stem.upper() in _RESERVED:
        stem += "_"
    return stem[:200]


def render_template(template: str, src: Path, number: int) -> str:
    """Namensvorlage ausfüllen: {name}, {nr}, {datum}."""
    today = datetime.date.today().isoformat()
    stem = template or "{name}"
    stem = stem.replace("{name}", src.stem).replace("{nr}", f"{number:03d}")
    stem = stem.replace("{datum}", today)
    return sanitize_stem(stem) or sanitize_stem(src.stem) or "bild"


def output_extension(src: Path, format_label: str) -> str:
    """Dateiendung der Ausgabe (bei „Wie Original“ die der Quelle)."""
    ext = OUTPUT_FORMATS.get(format_label)
    if ext:
        return ext
    return src.suffix if src.suffix.lower() in EXT_TO_FMT else ".png"


@dataclass
class Job:
    """Eine geplante Verarbeitung: Quelle -> Ziel."""
    src: Path
    dst: Path
    skip: bool = False
    note: str = ""


def plan_jobs(files, in_dir: Path, out_dir: Path, template: str, overrides: dict,
              format_label: str, conflict: str) -> list[Job]:
    """Für jede Datei den endgültigen Ausgabepfad festlegen.

    * ``overrides``: {str(Quellpfad): eigener Name ohne Endung}
    * doppelte Namen innerhalb des Stapels erhalten immer _2, _3 …
    * ein Ziel darf nie eine der Quelldateien sein
    * ``conflict`` regelt den Umgang mit bereits vorhandenen Dateien
    """
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    sources = set()
    for f in files:
        try:
            sources.add(Path(f).resolve())
        except OSError:
            pass
    used: set[str] = set()
    jobs = []
    for i, src in enumerate(files, start=1):
        src = Path(src)
        try:
            rel_dir = src.parent.relative_to(in_dir)
        except ValueError:
            rel_dir = Path()
        stem = overrides.get(str(src)) or render_template(template, src, i)
        stem = sanitize_stem(stem) or src.stem
        ext = output_extension(src, format_label)
        folder = out_dir / rel_dir
        dst = folder / f"{stem}{ext}"
        n = 2
        while True:
            clash_batch = str(dst).casefold() in used
            clash_src = dst.resolve() in sources
            clash_disk = conflict == CONFLICT_NUMBER and dst.exists()
            if not (clash_batch or clash_src or clash_disk):
                break
            dst = folder / f"{stem}_{n}{ext}"
            n += 1
        used.add(str(dst).casefold())
        job = Job(src, dst)
        if conflict == CONFLICT_SKIP and dst.exists():
            job.skip, job.note = True, "existiert bereits"
        jobs.append(job)
    return jobs
