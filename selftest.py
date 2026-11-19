# -----------------------------------------------------------------------------
# FotoRahmen – Rahmen für Fotos
# Copyright (c) 2026 Stefan J. Kaiser
# Idee und Prompt: Stefan J. Kaiser
# Umsetzung: Claude Opus 5.5 (Anthropic), 3.–4. November 2026
# Lizenz: GNU GPL v3 – siehe Datei LICENSE
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

    # --- Neue Funktionen 1.5: Text, lange Kante begrenzen, Effekte, WebP-Ausgabe ---
    big = scene(3000, 2000)
    big.save(src.parent / "gross.jpg")
    tifffile.imwrite(src.parent / "gross16.tif", np.asarray(big).astype(np.uint16) * 257, photometric="rgb")
    fx = core.FrameSettings(unit="pct", outer_width=3, bottom_extra=5, text="© {jahr} {name}",
                            text_pos="right", max_edge=1024, corner_radius=2, shadow=1.5)
    for name in ("gross.jpg", "gross16.tif"):
        for ext in (".jpg", ".png", ".webp", ".tif"):
            dst = out / "neu" / f"{Path(name).stem}{ext}"
            try:
                size = core.process_file(src.parent / name, dst, fx, 90)
                exp = core.output_size(fx, 3000, 2000, core.EXT_TO_FMT[ext])
                assert size == exp, f"Größe {size} statt {exp}"
                assert max(size) <= 1024, "lange Kante nicht begrenzt"
                if ext in (".png", ".webp"):
                    with Image.open(dst) as im:
                        assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0, "keine Transparenz"
                print(f"OK     Neu            {name:12} -> {dst.name}  {size[0]}x{size[1]}")
            except Exception as exc:
                failures += 1
                print(f"FEHLER Neu            {name:12} -> {dst.name}: {exc!r}")
    # Text muss im unteren Rand dunkle Pixel erzeugen
    t = core.FrameSettings(outer_width=20, bottom_extra=60, text="TEST", text_color=(0, 0, 0))
    framed = core.compose(Image.new("RGB", (400, 300), (255, 255, 255)), t)
    band = framed.crop((0, framed.height - 70, framed.width, framed.height)).convert("L")
    if band.getextrema()[0] > 100:
        failures += 1
        print("FEHLER: Textzeile wurde nicht gezeichnet")

    # --- Neu in 2.0: Copyright-Schutz (Wasserzeichen + Metadaten) ---
    prot = core.FrameSettings(outer_width=10, wm_text="© {jahr} Test", wm_pos="tile", wm_opacity=50,
                              wm_size=6, meta_author="Max Müller", meta_copyright="© {jahr} Max Müller")
    plain = Image.new("RGB", (600, 400), (40, 90, 160))
    plain.save(src.parent / "schutz.png")
    for ext in (".jpg", ".png", ".tif", ".webp"):
        dst = out / "schutz" / f"schutz{ext}"
        try:
            core.process_file(src.parent / "schutz.png", dst, prot, 92)
            with Image.open(dst) as im:
                rgb = im.convert("RGB")
                diff = np.abs(np.asarray(rgb.crop((10, 10, 610, 410)), dtype=np.int16)
                              - np.array([40, 90, 160], dtype=np.int16)).sum(axis=2)
                changed = int((diff > 30).sum())
                assert changed > 500, "Wasserzeichen fehlt"
                xmp = im.info.get("xmp") or im.info.get("XML:com.adobe.xmp")
                if xmp is None and ext == ".tif":
                    xmp = tifffile.TiffFile(dst).pages[0].tags[700].value
                xmp = xmp.decode("utf-8") if isinstance(xmp, bytes) else xmp
                assert xmp and "Max Müller" in xmp and "©" in xmp, "XMP-Copyright fehlt"
            print(f"OK     Schutz         schutz.png   -> {dst.name}")
        except Exception as exc:
            failures += 1
            print(f"FEHLER Schutz         schutz.png   -> {dst.name}: {exc!r}")
    # 16-Bit-TIFF: Copyright-Tags
    dst = out / "schutz" / "g16_schutz.tif"
    core.process_file(src / "g16.tif", dst, prot, 92)
    tags = tifffile.TiffFile(dst).pages[0].tags
    if tags[33432].value != f"© {__import__('datetime').date.today().year} Max Müller":
        failures += 1
        print("FEHLER: Copyright-Tag im 16-Bit-TIFF fehlt/falsch:", tags[33432].value)

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
