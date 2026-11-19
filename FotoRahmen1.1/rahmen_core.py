# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3. November 2026
# Lizenz: MIT – siehe Datei LICENSE
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

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

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
}

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


def _process_highbit_tiff(src: Path, tmp: Path, settings: FrameSettings):
    """16-Bit-TIFF -> 16-Bit-TIFF, verlustfrei, mit ICC-Profil und Auflösung."""
    arr, info = _read_tiff_array(src)
    h, w = arr.shape[:2]
    if info["orientation"] in (5, 6, 7, 8):   # Rahmen-Maße beziehen sich auf die Anzeige
        w, h = h, w
    layers = settings.layers(w, h)
    if info["orientation"] != 1 and any(l.bottom != l.width for l in layers):
        # Unterer Zusatzrand muss im Anzeigebild unten liegen -> Pixel drehen
        arr = np.asarray(_apply_orientation_array(arr, info["orientation"]))
        info["orientation"] = 1
    arr = _pad_array(arr, layers, info["photometric"])
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


def _apply_orientation_array(arr, orientation: int):
    """Orientierung auf ein numpy-Array (Y, X[, C]) anwenden."""
    ops = {
        2: lambda a: a[:, ::-1], 3: lambda a: a[::-1, ::-1], 4: lambda a: a[::-1, :],
        5: lambda a: np.swapaxes(a, 0, 1),
        6: lambda a: np.rot90(a, -1), 7: lambda a: np.rot90(np.swapaxes(a, 0, 1), 2),
        8: lambda a: np.rot90(a, 1),
    }
    return ops.get(orientation, lambda a: a)(arr)


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
                   box_w: int, box_h: int) -> Image.Image:
    """Vorschau mit Rahmen, passend in ``box_w × box_h`` skaliert.

    Die Rahmenbreiten werden aus der Originalgröße berechnet, damit die
    Vorschau den Proportionen des Ergebnisses entspricht. Sehr dünne Linien
    werden mindestens 1 Pixel breit gezeichnet, damit sie sichtbar bleiben.
    """
    ow, oh = orig_size
    fw, fh = settings.framed_size(ow, oh)
    scale = max(min(box_w / fw, box_h / fh), 1e-6)
    iw, ih = max(1, round(ow * scale)), max(1, round(oh * scale))
    img = thumb.resize((iw, ih), LANCZOS) if (iw, ih) != thumb.size else thumb.copy()

    def sc(v):
        return max(1, round(v * scale)) if v > 0 else 0

    scaled = [Layer(sc(l.width), sc(l.bottom), l.color) for l in settings.layers(ow, oh)]
    return add_frame(img, scaled)


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
    try:
        highbit = is_highbit_tiff(src)
        if fmt == "TIFF" and highbit:
            size = _process_highbit_tiff(src, tmp, settings)
        else:
            size = _process_with_pillow(src, tmp, fmt, settings, quality, highbit)
        os.replace(tmp, dst)
        return size
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _process_with_pillow(src: Path, tmp: Path, fmt: str, settings: FrameSettings,
                         quality: int, highbit: bool):
    if highbit:                       # 16-Bit-TIFF -> anderes Zielformat
        arr, tinfo = _read_tiff_array(src)
        if fmt in ("PNG", "JPEG2000") and arr.ndim == 2 and arr.dtype == np.uint16 \
                and tinfo["photometric"] == 1:
            img = _from_array(arr, "I;16")         # 16-Bit-Graustufen bleiben 16 Bit
        else:
            img = _array_to_8bit_image(arr, tinfo["photometric"])
        img = _apply_orientation(img, tinfo["orientation"])
        info = {"icc_profile": bytes(tinfo["icc"])} if tinfo["icc"] is not None else {}
        return _save_single(img, tmp, fmt, settings, quality, info, None)

    with _open(src) as im:
        info = dict(im.info)
        n_frames = getattr(im, "n_frames", 1)
        try:
            if n_frames > 1 and ((fmt == "GIF" and im.format == "GIF") or
                                 (fmt == "WEBP" and im.format == "WEBP")):
                return _save_animated(im, tmp, fmt, settings, quality)
            im.seek(0)
            img = ImageOps.exif_transpose(im)
        except (OSError, SyntaxError) as exc:
            raise ImageReadError("Datei ist beschädigt oder unvollständig") from exc
        exif = _exif_bytes(img)
        return _save_single(img, tmp, fmt, settings, quality, info, exif)


def _save_single(img, tmp, fmt, settings, quality, info, exif):
    img = normalize_mode(img)
    src_mode = img.mode
    out = add_frame(img, settings.layers(*img.size))
    out = convert_for_format(out, fmt)

    icc = info.get("icc_profile")
    if src_mode == "CMYK" and out.mode != "CMYK":
        icc = None                    # CMYK-Profil passt nicht zu RGB-Daten
    if src_mode != "CMYK" and out.mode == "CMYK":
        icc = None
    dpi = info.get("dpi")

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
    attempts = [meta, {k: v for k, v in meta.items() if k != "exif"}, {}]
    last_exc = None
    for m in attempts:
        try:
            out.save(tmp, format=fmt, **opts, **m)
            return out.size
        except Exception as exc:   # noqa: BLE001 – nächster Versuch
            last_exc = exc
    raise last_exc  # type: ignore[misc]


def _save_animated(im, tmp, fmt, settings, quality):
    """Animiertes GIF/WebP Bild für Bild rahmen."""
    frames, durations = [], []
    has_alpha = "transparency" in im.info or im.mode in ("RGBA", "LA", "PA")
    layers = None
    for frame in ImageSequence.Iterator(im):
        durations.append(frame.info.get("duration", im.info.get("duration", 100)))
        f = frame.convert("RGBA" if has_alpha else "RGB")
        if layers is None:
            layers = settings.layers(*f.size)
        frames.append(add_frame(f, layers))
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
