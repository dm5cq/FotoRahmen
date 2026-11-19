# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3. November 2026
# Lizenz: MIT – siehe Datei LICENSE
# -----------------------------------------------------------------------------
"""Kurzer Selbsttest der Bildverarbeitung (wird auch beim automatischen Build ausgeführt).

Aufruf:  python selftest.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw

import rahmen_core as core


def scene(w, h):
    im = Image.new("RGB", (w, h), (90, 140, 200))
    d = ImageDraw.Draw(im)
    d.polygon([(0, h), (w * 0.35, h * 0.4), (w * 0.6, h * 0.75), (w, h)], fill=(60, 110, 60))
    return im


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main():
    tmp = Path(tempfile.mkdtemp())
    src, out = tmp / "ein", tmp / "aus"
    src.mkdir()
    s = scene(400, 300)
    exif = Image.Exif()
    exif[0x0112] = 6
    s.save(src / "a.jpg", exif=exif.tobytes())
    s.save(src / "b.png")
    s.convert("CMYK").save(src / "c.jpg")
    s.save(src / "d.webp")
    s.save(src / "e.bmp")
    frames = [scene(120, 80), scene(120, 80).rotate(15)]
    frames[0].save(src / "f.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)
    tifffile.imwrite(src / "g16.tif", np.asarray(s).astype(np.uint16) * 257, photometric="rgb")
    s.save(src / "h.tif", compression="tiff_lzw")
    if core.HEIF_OK:
        s.save(src / "i.heic")
    s.save(src / "j.webp", save_all=True, append_images=[s.rotate(10)], duration=100)
    (src / "kaputt.jpg").write_bytes(b"kein Bild")
    before = {p.name: md5(p) for p in src.iterdir()}

    settings = core.FrameSettings(double=True, unit="px", outer_width=20,
                                  outer_color=(255, 255, 255), inner_width=3, inner_color=(0, 0, 0),
                                  bottom_extra=10)
    files = core.scan_images(src)
    failures = 0
    for label in core.OUTPUT_FORMATS:
        jobs = core.plan_jobs(files, src, out / label.split()[0], "{name}_rahmen", {}, label,
                              core.CONFLICT_NUMBER)
        for job in jobs:
            if job.src.name == "kaputt.jpg":
                try:
                    core.process_file(job.src, job.dst, settings, 92)
                    failures += 1
                    print("FEHLER: beschädigte Datei wurde nicht erkannt")
                except core.ImageReadError:
                    pass
                continue
            try:
                w, h = core.process_file(job.src, job.dst, settings, 92)
                ow, oh = core.load_preview(job.src)[1]
                assert (w, h) == (ow + 46, oh + 56), f"Größe {w}x{h} statt {ow + 46}x{oh + 56}"
                core.load_preview(job.dst)
                print(f"OK     {label:14} {job.src.name:8} -> {job.dst.name}  {w}x{h}")
            except Exception as exc:
                failures += 1
                print(f"FEHLER {label:14} {job.src.name:8}: {exc!r}")

    # CMYK: Schwarz muss reines K sein
    assert core.rgb_to_cmyk((0, 0, 0)) == (0, 0, 0, 255)
    assert core.rgb_to_cmyk((255, 255, 255)) == (0, 0, 0, 0)
    # Windows-reservierte Namen
    assert core.sanitize_stem("CON") == "CON_"
    assert core.sanitize_stem('a:b?') == "a_b_"

    after = {p.name: md5(p) for p in src.iterdir()}
    if before != after:
        failures += 1
        print("FEHLER: Originaldateien wurden verändert!")
    print("HEIC-Unterstützung:", "ja" if core.HEIF_OK else "nein")
    print("Ergebnis:", "alles in Ordnung" if not failures else f"{failures} Fehler")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
