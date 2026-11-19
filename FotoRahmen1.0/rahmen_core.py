"""
FotoRahmen – Bildverarbeitung (ohne Oberfläche).

Fügt Bildern einen einfachen oder doppelten Rahmen hinzu. Die Originaldateien
werden nur gelesen, niemals verändert: geschrieben wird ausschließlich in das
Ausgabe-Verzeichnis (zuerst in eine temporäre Datei, die erst nach
erfolgreichem Speichern umbenannt wird).
"""
from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

Image.MAX_IMAGE_PIXELS = None  # große Panoramen erlauben (lokales Werkzeug)

# --- optionale Bibliotheken ---------------------------------------------------
try:  # HEIC/HEIF (z. B. iPhone-Fotos)
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover
    HEIF_OK = False

try:  # 16-Bit-TIFF verlustfrei verarbeiten
    import numpy as np
    import tifffile

    TIFFFILE_OK = True
except Exception:  # pragma: no cover
    TIFFFILE_OK = False


# --- Formate ------------------------------------------------------------------
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

INPUT_EXTS = set(EXT_TO_FMT)

# Anzeige-Name -> Dateiendung (None = Format des Originals beibehalten)
OUTPUT_FORMATS = {
    "Wie Original": None,
    "JPEG (.jpg)": ".jpg",
    "PNG (.png)": ".png",
    "TIFF (.tif)": ".tif",
}

CONFLICT_NUMBER = "number"
CONFLICT_OVERWRITE = "overwrite"
CONFLICT_SKIP = "skip"


# --- Einstellungen ------------------------------------------------------------
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


@dataclass
class FrameSettings:
    double: bool = False          # True = innerer + äußerer Rahmen
    unit: str = "px"              # "px" oder "pct" (% der langen Bildkante)
    outer_width: float = 40.0
    outer_color: tuple = (255, 255, 255)
    inner_width: float = 4.0
    inner_color: tuple = (0, 0, 0)

    def _px(self, value: float, w: int, h: int) -> int:
        if value <= 0:
            return 0
        if self.unit == "pct":
            return max(1, round(max(w, h) * value / 100.0))
        return int(round(value))

    def layers(self, w: int, h: int) -> list[tuple[int, tuple]]:
        """Rahmenschichten (Breite in Pixel, Farbe) von innen nach außen."""
        result = []
        if self.double:
            result.append((self._px(self.inner_width, w, h), tuple(self.inner_color)))
        result.append((self._px(self.outer_width, w, h), tuple(self.outer_color)))
        return [(px, col) for px, col in result if px > 0]

    def total(self, w: int, h: int) -> int:
        return sum(px for px, _ in self.layers(w, h))


# --- Pillow-Hilfen ------------------------------------------------------------
def _lum(rgb) -> int:
    r, g, b = rgb[:3]
    return int(round(0.299 * r + 0.587 * g + 0.114 * b))


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
        return img.convert("I;16") if m != "I;16" else img
    return img


def add_frame(img: Image.Image, layers) -> Image.Image:
    for width, color in layers:
        if width <= 0:
            continue
        new = Image.new(img.mode, (img.width + 2 * width, img.height + 2 * width),
                        fill_for_mode(color, img.mode))
        new.paste(img, (width, width))
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
    """Für Bildschirm-Vorschau: RGB oder RGBA (8 Bit)."""
    img = normalize_mode(img)
    if img.mode in ("RGB", "RGBA"):
        return img
    if img.mode == "LA":
        return img.convert("RGBA")
    if img.mode.startswith("I") or img.mode == "F":
        return _to_8bit_gray(img).convert("RGB")
    return img.convert("RGB")


def _flatten(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    if img.mode in ("RGBA", "LA"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", img.size, background)
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img


def convert_for_format(img: Image.Image, fmt: str) -> Image.Image:
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
        if m in ("L", "LA", "RGB", "RGBA", "I;16"):
            return img
        return to_display(img)
    return img


# --- 16-Bit-TIFF (tifffile) ---------------------------------------------------
def is_highbit_tiff(path: Path) -> bool:
    if not TIFFFILE_OK or path.suffix.lower() not in (".tif", ".tiff"):
        return False
    try:
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            return np.dtype(page.dtype).itemsize > 1
    except Exception:
        return False


def _read_tiff_array(path: Path):
    """Liest Seite 1 eines TIFF als Array (Höhe, Breite[, Kanäle]) plus Infos."""
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
    if photometric == 2:            # RGB
        base = [c / 255 * maxv for c in rgb[:3]]
    elif photometric == 1:          # Graustufen, schwarz = 0
        base = [_lum(rgb) / 255 * maxv]
    elif photometric == 0:          # Graustufen, weiß = 0
        base = [(255 - _lum(rgb)) / 255 * maxv]
    elif photometric == 5:          # CMYK
        cmyk = Image.new("RGB", (1, 1), tuple(rgb[:3])).convert("CMYK").getpixel((0, 0))
        base = [v / 255 * maxv for v in cmyk]
    else:
        raise ValueError("Farbraum dieses TIFF wird nicht unterstützt")
    while len(base) < channels:     # Alpha/Zusatzkanäle: voll deckend
        base.append(maxv)
    return base[:channels]


def _pad_array(arr, layers, photometric):
    channels = 1 if arr.ndim == 2 else arr.shape[2]
    maxv = _max_value(arr.dtype)
    for width, color in layers:
        h, w = arr.shape[:2]
        new = np.empty((h + 2 * width, w + 2 * width) + arr.shape[2:], dtype=arr.dtype)
        val = _tiff_color(color, photometric, channels, maxv)
        new[...] = val[0] if arr.ndim == 2 else np.array(val, dtype=arr.dtype)
        new[width:width + h, width:width + w] = arr
        arr = new
    return arr


def _array_to_8bit_image(arr, photometric) -> Image.Image:
    maxv = _max_value(arr.dtype)
    a8 = np.clip(arr.astype(np.float32) / maxv * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if photometric == 0:
        a8 = 255 - a8
    if a8.ndim == 2:
        return Image.fromarray(a8, "L")
    ch = a8.shape[2]
    if photometric == 5 and ch >= 4:
        return Image.fromarray(np.ascontiguousarray(a8[:, :, :4]), "CMYK").convert("RGB")
    if ch == 1:
        return Image.fromarray(a8[:, :, 0], "L")
    if ch == 2:
        return Image.fromarray(np.ascontiguousarray(a8), "LA")
    if ch == 3:
        return Image.fromarray(np.ascontiguousarray(a8), "RGB")
    return Image.fromarray(np.ascontiguousarray(a8[:, :, :4]), "RGBA")


def _process_highbit_tiff(src: Path, tmp: Path, settings: FrameSettings):
    arr, info = _read_tiff_array(src)
    layers = settings.layers(arr.shape[1], arr.shape[0])
    arr = _pad_array(arr, layers, info["photometric"])
    phot = {0: "miniswhite", 1: "minisblack", 2: "rgb", 5: "separated"}[info["photometric"]]
    kwargs = dict(photometric=phot, planarconfig="contig", metadata=None,
                  compression="zlib")
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


# --- Laden für Vorschau ---------------------------------------------------------
def load_preview(path: Path, max_size: int = 1600):
    """Gibt (Vorschaubild RGB/RGBA, Originalgröße (B, H) nach Drehung) zurück."""
    path = Path(path)
    if is_highbit_tiff(path):
        arr, info = _read_tiff_array(path)
        h, w = arr.shape[:2]
        step = max(1, max(w, h) // max_size)
        img = _array_to_8bit_image(arr[::step, ::step], info["photometric"])
        img = _apply_orientation(img, info["orientation"])
        size = (h, w) if info["orientation"] in (5, 6, 7, 8) else (w, h)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        return to_display(img), size

    with Image.open(path) as im:
        orientation = 1
        try:
            orientation = int(im.getexif().get(0x0112, 1))
        except Exception:
            pass
        w, h = im.size
        size = (h, w) if orientation in (5, 6, 7, 8) else (w, h)
        if im.format == "JPEG":
            im.draft("RGB", (max_size, max_size))
        img = ImageOps.exif_transpose(im)
        img = to_display(img)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        img.load()
    return img, size


def _apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    method = {2: Image.FLIP_LEFT_RIGHT, 3: Image.ROTATE_180, 4: Image.FLIP_TOP_BOTTOM,
              5: Image.TRANSPOSE, 6: Image.ROTATE_270, 7: Image.TRANSVERSE,
              8: Image.ROTATE_90}.get(orientation)
    return img.transpose(method) if method is not None else img


def render_preview(thumb: Image.Image, orig_size, settings: FrameSettings,
                   box_w: int, box_h: int) -> Image.Image:
    """Vorschau mit Rahmen, passend in box_w × box_h skaliert.

    Die Rahmenbreiten werden aus der Originalgröße berechnet, damit die
    Vorschau exakt den Proportionen des späteren Ergebnisses entspricht.
    Sehr dünne Linien werden mindestens 1 Pixel breit gezeichnet.
    """
    ow, oh = orig_size
    layers = settings.layers(ow, oh)
    total = sum(px for px, _ in layers)
    scale = min(box_w / (ow + 2 * total), box_h / (oh + 2 * total))
    scale = max(scale, 1e-6)
    iw, ih = max(1, round(ow * scale)), max(1, round(oh * scale))
    img = thumb.resize((iw, ih), Image.LANCZOS) if (iw, ih) != thumb.size else thumb.copy()
    scaled = [(max(1, round(px * scale)), col) for px, col in layers]
    return add_frame(img, scaled)


# --- Verarbeitung einer Datei --------------------------------------------------
def _exif_bytes(img: Image.Image):
    try:
        exif = img.getexif()
        if not exif:
            return None
        if 0x0112 in exif:
            exif[0x0112] = 1
        return exif.tobytes()
    except Exception:
        return None


def process_file(src: Path, dst: Path, settings: FrameSettings, jpeg_quality: int = 95):
    """Rahmen um src legen und als dst speichern. Gibt die neue Größe zurück."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("Ziel wäre die Originaldatei – abgebrochen")
    fmt = EXT_TO_FMT.get(dst.suffix.lower())
    if fmt is None:
        raise ValueError(f"Ausgabeformat {dst.suffix} wird nicht unterstützt")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.stem}.fotorahmen-tmp{dst.suffix}")
    try:
        if fmt == "TIFF" and is_highbit_tiff(src):
            size = _process_highbit_tiff(src, tmp, settings)
        else:
            size = _process_with_pillow(src, tmp, fmt, settings, jpeg_quality)
        os.replace(tmp, dst)
        return size
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _open_8bit_from_highbit(src: Path) -> Image.Image:
    arr, info = _read_tiff_array(src)
    img = _array_to_8bit_image(arr, info["photometric"])
    return _apply_orientation(img, info["orientation"])


def _process_with_pillow(src: Path, tmp: Path, fmt: str, settings: FrameSettings,
                         quality: int):
    if is_highbit_tiff(src):          # 16-Bit-TIFF -> 8-Bit-Zielformat
        img = _open_8bit_from_highbit(src)
        with Image.open(src) as probe:
            info = dict(probe.info)
        info.pop("exif", None)
        return _save_single(img, tmp, fmt, settings, quality, info, None)

    with Image.open(src) as im:
        info = dict(im.info)
        n_frames = getattr(im, "n_frames", 1)
        if fmt == "GIF" and im.format == "GIF" and n_frames > 1:
            return _save_animated_gif(im, tmp, settings)
        im.seek(0)
        img = ImageOps.exif_transpose(im)
        exif = _exif_bytes(img)
        return _save_single(img, tmp, fmt, settings, quality, info, exif)


def _save_single(img, tmp, fmt, settings, quality, info, exif):
    img = normalize_mode(img)
    src_mode = img.mode
    out = add_frame(img, settings.layers(*img.size))
    out = convert_for_format(out, fmt)

    icc = info.get("icc_profile")
    if src_mode == "CMYK" and out.mode != "CMYK":
        icc = None                    # CMYK-Profil passt nicht mehr zu RGB
    dpi = info.get("dpi")

    meta = {}
    if icc:
        meta["icc_profile"] = icc
    if exif and fmt in ("JPEG", "PNG", "WEBP", "TIFF", "HEIF"):
        meta["exif"] = exif
    if dpi and fmt in ("JPEG", "PNG", "TIFF", "BMP"):
        meta["dpi"] = tuple(float(d) for d in dpi)

    opts = {}
    if fmt == "JPEG":
        opts = dict(quality=int(quality), subsampling=0 if quality >= 90 else 2,
                    optimize=True)
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
    elif fmt == "GIF":
        meta.pop("icc_profile", None)

    try:
        out.save(tmp, format=fmt, **opts, **meta)
    except Exception:
        out.save(tmp, format=fmt, **opts)   # zweiter Versuch ohne Metadaten
    return out.size


def _save_animated_gif(im, tmp, settings):
    frames, durations = [], []
    has_alpha = "transparency" in im.info
    layers = None
    for frame in ImageSequence.Iterator(im):
        durations.append(frame.info.get("duration", im.info.get("duration", 100)))
        f = frame.convert("RGBA" if has_alpha else "RGB")
        if layers is None:
            layers = settings.layers(*f.size)
        frames.append(add_frame(f, layers))
    frames[0].save(tmp, format="GIF", save_all=True, append_images=frames[1:],
                   duration=durations, loop=im.info.get("loop", 0), disposal=2)
    return frames[0].size


# --- Dateien finden & Ausgabenamen ---------------------------------------------
def _natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def scan_images(in_dir: Path, recursive: bool = False, exclude: Path | None = None):
    in_dir = Path(in_dir)
    if not in_dir.is_dir():
        return []
    exclude_r = exclude.resolve() if exclude else None
    it = in_dir.rglob("*") if recursive else in_dir.iterdir()
    files = []
    for p in it:
        try:
            if not p.is_file() or p.name.startswith("."):
                continue
            if p.suffix.lower() not in INPUT_EXTS:
                continue
            if exclude_r and (exclude_r == p.resolve().parent or
                              exclude_r in p.resolve().parents):
                continue
        except OSError:
            continue
        files.append(p)
    return sorted(files, key=_natural_key)


_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_stem(stem: str) -> str:
    stem = _ILLEGAL.sub("_", stem).strip().rstrip(".")
    return stem


def render_template(template: str, src: Path, number: int) -> str:
    today = datetime.date.today().isoformat()
    stem = (template or "{name}")
    stem = stem.replace("{name}", src.stem).replace("{nr}", f"{number:03d}")
    stem = stem.replace("{datum}", today)
    stem = sanitize_stem(stem)
    return stem or src.stem


def output_extension(src: Path, format_label: str) -> str:
    ext = OUTPUT_FORMATS.get(format_label)
    if ext:
        return ext
    return src.suffix if src.suffix.lower() in EXT_TO_FMT else ".png"


@dataclass
class Job:
    src: Path
    dst: Path
    skip: bool = False
    note: str = ""


def plan_jobs(files, in_dir: Path, out_dir: Path, template: str, overrides: dict,
              format_label: str, conflict: str) -> list[Job]:
    """Ermittelt für jede Datei den endgültigen Ausgabepfad."""
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    sources = {Path(f).resolve() for f in files}
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
            key = str(dst).casefold()
            clash_batch = key in used
            clash_src = dst.resolve() in sources
            clash_disk = dst.exists() and conflict == CONFLICT_NUMBER
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
