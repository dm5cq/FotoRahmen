# -----------------------------------------------------------------------------
# FotoRahmen – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
# -----------------------------------------------------------------------------
"""Erzeugt die Beispielfotos und die Vorher/Nachher-Beispiele für die Dokumentation.

Aufruf (aus dem Projektordner):  python docs/werkzeuge/beispielbilder.py

Ergebnis:
  docs/beispiele/eingabe/   vier künstlich erzeugte „Fotos“ (JPEG, JPEG hoch, 16-Bit-TIFF, PNG)
  docs/beispiele/ausgabe/   dieselben Bilder mit den Rahmen-Rezepten aus REZEPTE

Die Fotos werden rein rechnerisch erzeugt (keine fremden Bildrechte).
"""
import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import rahmen_core as core  # noqa: E402

OUT = ROOT / "docs" / "beispiele"
RNG = np.random.default_rng(7)


def ridge(width, base, amp, rough=0.55, seed=0):
    """Bergkamm per Mittelpunkt-Verschiebung (fraktal)."""
    rng = np.random.default_rng(seed)
    n = 1
    pts = np.array([0.0, 0.0])
    a = amp
    while n < width:
        mids = (pts[:-1] + pts[1:]) / 2 + rng.uniform(-a, a, len(pts) - 1)
        new = np.empty(len(pts) * 2 - 1)
        new[0::2], new[1::2] = pts, mids
        pts, n, a = new, len(new), a * rough
    return base + np.interp(np.linspace(0, len(pts) - 1, width), np.arange(len(pts)), pts)


def vgrad(h, w, stops):
    """Vertikaler Farbverlauf als float-Array (h, w, 3)."""
    ys = np.linspace(0, 1, h)
    out = np.zeros((h, 3))
    t = np.array([s[0] for s in stops])
    for c in range(3):
        out[:, c] = np.interp(ys, t, [s[1][c] for s in stops])
    return np.repeat(out[:, None, :], w, axis=1)


def grain(img, amount=4.0):
    return np.clip(img + RNG.normal(0, amount, img.shape), 0, 255)


def bergsee(w=1800, h=1200):
    horizon = int(h * 0.62)
    img = vgrad(h, w, [(0, (30, 44, 98)), (0.28, (110, 74, 128)), (0.46, (236, 128, 64)),
                        (0.60, (255, 200, 112)), (1, (255, 200, 112))])
    yy, xx = np.mgrid[0:h, 0:w]
    sx, sy, sr = w * 0.64, h * 0.30, w * 0.03
    dist = np.hypot(xx - sx, yy - sy)
    img += (np.exp(-(dist / (sr * 5)) ** 2) * 70)[..., None] * np.array([1.0, 0.75, 0.35])
    img[dist < sr] = (255, 236, 190)
    for k, (base, amp, col) in enumerate([(0.44, 0.10, (110, 70, 112)), (0.51, 0.07, (70, 44, 82)),
                                           (0.575, 0.035, (34, 24, 44))]):
        r = ridge(w, h * base, h * amp, seed=k + 3)
        mask = (yy > r[None, :]) & (yy < horizon)
        img[mask] = img[mask] * 0.15 + np.array(col) * 0.85
    sky = img[:horizon][::-1]
    lake_h = h - horizon
    refl = sky[:lake_h] * 0.70 + np.array([12, 20, 38]) * 0.30
    ripple = np.sin(np.arange(lake_h)[:, None] * 0.9 + xx[:lake_h] * 0.02) * 5
    img[horizon:] = np.clip(refl + ripple[..., None], 0, 255)
    return Image.fromarray(grain(img).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


def wald(w=1200, h=1800):
    img = vgrad(h, w, [(0, (200, 214, 206)), (0.55, (150, 172, 150)), (1, (70, 86, 52))])
    pil = Image.fromarray(img.astype(np.uint8))
    d = ImageDraw.Draw(pil, "RGBA")
    rng = np.random.default_rng(11)
    for depth in range(4):                                   # von hinten nach vorn: dunkler, breiter
        tone = int(170 - depth * 45)
        alpha = 110 + depth * 45
        for _ in range(9 + depth * 2):
            x = rng.uniform(-50, w + 50)
            tw = rng.uniform(10, 26) * (1 + depth * 0.9)
            d.rectangle((x, 0, x + tw, h * (0.78 + depth * 0.06)),
                        fill=(tone - 40, tone - 20, tone - 50, alpha))
    d.polygon([(w * 0.42, h), (w * 0.5, h * 0.66), (w * 0.53, h * 0.66), (w * 0.72, h)],
              fill=(176, 150, 112, 230))
    pil = pil.filter(ImageFilter.GaussianBlur(1.2))
    fog = vgrad(h, w, [(0, (255, 255, 255)), (0.6, (255, 255, 255)), (1, (255, 255, 255))])
    a = np.linspace(0.45, 0.0, h)[:, None, None]
    out = np.asarray(pil, dtype=np.float32) * (1 - a) + fog * a
    return Image.fromarray(grain(out, 3).astype(np.uint8))


def kueste16(w=1500, h=1000):
    """Küste als 16-Bit-Array (für den verlustfreien TIFF-Weg)."""
    horizon = int(h * 0.45)
    shore = int(h * 0.72)
    img = vgrad(h, w, [(0, (80, 140, 210)), (0.44, (205, 228, 242)), (0.45, (36, 100, 140)),
                        (0.70, (64, 156, 172)), (0.72, (232, 214, 170)), (1, (205, 178, 128))])
    yy, xx = np.mgrid[0:h, 0:w]
    foam = (np.sin(yy * 0.45 + 2.5 * np.sin(xx * 0.008)) > 0.985) & (yy > horizon + 40) & (yy < shore)
    img[foam] = img[foam] * 0.35 + 255 * 0.65
    edge = (yy >= shore - 6) & (yy < shore + 4 + 6 * np.sin(xx * 0.02))
    img[edge] = img[edge] * 0.3 + 250 * 0.7
    rw = int(w * 0.36)
    top = ridge(rw, 0, h * 0.05, seed=21) + h * 0.30 + (np.arange(rw) / rw) ** 2.2 * h * 0.40
    rock = (xx < rw) & (yy > np.interp(xx, np.arange(rw), top)) & (yy < shore + 30)
    noise = np.asarray(Image.fromarray((RNG.random((h // 8, w // 8)) * 255).astype(np.uint8))
                       .resize((w, h), Image.Resampling.BICUBIC), dtype=np.float32) / 255
    shade = 0.70 + 0.30 * noise - 0.25 * (xx / rw)
    img[rock] = np.array([92, 80, 70]) * shade[rock][:, None]
    # kein Bildrauschen: 16-Bit-Rauschen ließe sich kaum komprimieren (Dateigröße)
    return (img / 255.0 * 65535).astype(np.uint16)


def stadt(w=1800, h=1100):
    img = vgrad(h, w, [(0, (8, 10, 30)), (0.6, (40, 30, 70)), (0.75, (120, 60, 70)), (1, (20, 14, 22))])
    pil = Image.fromarray(img.astype(np.uint8))
    d = ImageDraw.Draw(pil)
    rng = np.random.default_rng(5)
    x = 0
    while x < w:
        bw = int(rng.uniform(60, 160))
        bh = int(rng.uniform(h * 0.2, h * 0.62))
        top = h - bh
        d.rectangle((x, top, x + bw, h), fill=(18, 18, 28))
        for wy in range(top + 14, h - 10, 22):
            for wx in range(x + 10, x + bw - 12, 18):
                if rng.random() < 0.42:
                    c = (255, int(rng.uniform(180, 230)), int(rng.uniform(90, 150)))
                    d.rectangle((wx, wy, wx + 8, wy + 11), fill=c)
        x += bw + int(rng.uniform(2, 12))
    for _ in range(140):
        sx, sy = rng.uniform(0, w), rng.uniform(0, h * 0.4)
        d.point((sx, sy), fill=(230, 230, 255))
    return pil


#: Rezepte für die Beispiele: (Datei-Kürzel, Titel, Beschreibung, Einstellungen, Ausgabe-Endung)
REZEPTE = [
    ("einfach_weiss", "Einfacher weißer Rahmen",
     "Rahmen 3 % der langen Kante, Weiß.",
     core.FrameSettings(unit="pct", outer_width=3, outer_color=(255, 255, 255)), None),
    ("galerie", "Galerie-Look mit Signatur",
     "Doppelrahmen: innen 0,25 % Schwarz, außen 4 % Weiß, unten extra 4 %, Text rechts.",
     core.FrameSettings(double=True, unit="pct", outer_width=4, inner_width=0.25, bottom_extra=4,
                        text="© {jahr} Stefan J. Kaiser", text_pos="right", text_size=38,
                        text_color=(70, 70, 70)), None),
    ("schwarz_schmal", "Schmaler schwarzer Rahmen",
     "Rahmen 1,5 % Schwarz – betont helle Motive.",
     core.FrameSettings(unit="pct", outer_width=1.5, outer_color=(0, 0, 0)), None),
    ("copyright_diagonal", "Copyright-Schutz diagonal",
     "Wasserzeichen „© {jahr} Stefan J. Kaiser“, 28 % Deckkraft, diagonal; Rahmen 2 % Weiß; "
     "Urheber/Copyright in den Metadaten; JPEG, lange Kante 1600 px.",
     core.FrameSettings(unit="pct", outer_width=2, wm_text="© {jahr} Stefan J. Kaiser", wm_pos="tile",
                        wm_opacity=28, wm_size=3.5, meta_author="Stefan J. Kaiser",
                        meta_copyright="© {jahr} Stefan J. Kaiser", max_edge=1600), ".jpg"),
    ("schatten_png", "Web-Look mit Schatten (PNG)",
     "Rahmen 3 % Weiß, Ecken 2 %, Schatten 1,5 % – transparenter Hintergrund.",
     core.FrameSettings(unit="pct", outer_width=3, corner_radius=2, shadow=1.5), ".png"),
    ("farbe_copyright_ecke", "Farbiger Rahmen + Copyright in der Ecke",
     "Doppelrahmen: innen 0,4 % Orange, außen 3 % Anthrazit; Wasserzeichen unten rechts 60 %.",
     core.FrameSettings(double=True, unit="pct", outer_width=3, outer_color=(38, 38, 38),
                        inner_width=0.4, inner_color=(242, 138, 30),
                        wm_text="© {jahr} Stefan J. Kaiser", wm_pos="br", wm_opacity=60, wm_size=3), None),
]


def main():
    ein, aus = OUT / "eingabe", OUT / "ausgabe"
    ein.mkdir(parents=True, exist_ok=True)
    aus.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "Beispiel", "Kamera"
    bergsee().save(ein / "Bergsee_Abendrot.jpg", quality=92, exif=exif.tobytes(), dpi=(300, 300))
    wald().save(ein / "Waldweg_Hochformat.jpg", quality=92, dpi=(300, 300))
    tifffile.imwrite(ein / "Kueste_16bit.tif", kueste16(), photometric="rgb", compression="zlib", predictor=True,
                     resolution=(300, 300), resolutionunit=2)
    stadt().save(ein / "Stadt_Nacht.png")
    print("Eingabebilder:", sorted(p.name for p in ein.iterdir()))

    paare = {"einfach_weiss": "Bergsee_Abendrot.jpg", "galerie": "Waldweg_Hochformat.jpg",
             "schwarz_schmal": "Kueste_16bit.tif", "copyright_diagonal": "Bergsee_Abendrot.jpg",
             "schatten_png": "Stadt_Nacht.png", "farbe_copyright_ecke": "Stadt_Nacht.png"}
    for key, _title, _desc, settings, ext in REZEPTE:
        src = ein / paare[key]
        dst = aus / f"{key}{ext or src.suffix}"
        size = core.process_file(src, dst, settings, 92)
        print(f"  {src.name:24} -> {dst.name:28} {size[0]}×{size[1]}")


if __name__ == "__main__":
    main()
