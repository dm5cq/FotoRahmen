# -----------------------------------------------------------------------------
# FotoRahmen – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
# -----------------------------------------------------------------------------
"""Erzeugt das App-Logo (Verlauf Orange -> Schwarz) in allen benötigten Formaten.

Aufruf:  python make_icons.py

Ergebnis im Ordner assets/:
  icon.png        1024 px – Fenster-Icon, Quelle für alle anderen
  icon.ico        Windows: EXE, Taskleiste, Task-Manager, Titelleiste (16–256 px)
  icon.icns       macOS: Dock, Finder, App-Umschalter
  logo_small.png  64 px – Logo in der Werkzeugleiste der App

Motiv: abgerundetes Quadrat mit diagonalem Verlauf Orange -> Schwarz, darin ein
gerahmtes Foto (heller Passepartout-Rahmen, feine schwarze Linie) mit
Bergsilhouette und Sonne. Erkennbar auch in 16 px (Taskleiste).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ORANGE_HI = (255, 166, 64)
ORANGE = (242, 138, 30)
ORANGE_DARK = (176, 74, 8)
BLACK = (14, 14, 14)
MAT = (250, 244, 236)

S = 1024          # Endgröße
SS = 4            # Überabtastung für glatte Kanten
ASSETS = Path(__file__).resolve().parent / "assets"


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient(size, stops, angle_diag=True):
    """Diagonaler Verlauf (oben links -> unten rechts) über mehrere Farbstopps."""
    w, h = size
    small = Image.new("RGB", (256, 256))
    px = small.load()
    for y in range(256):
        for x in range(256):
            t = (x + y) / 510 if angle_diag else y / 255
            for i in range(len(stops) - 1):
                t0, c0 = stops[i]
                t1, c1 = stops[i + 1]
                if t <= t1:
                    px[x, y] = lerp(c0, c1, (t - t0) / max(t1 - t0, 1e-6))
                    break
            else:
                px[x, y] = stops[-1][1]
    return small.resize((w, h), Image.Resampling.BICUBIC)


def make_logo() -> Image.Image:
    n = S * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))

    # 1. Grundfläche: abgerundetes Quadrat, Verlauf Orange -> Schwarz
    margin = int(n * 0.045)
    radius = int(n * 0.22)
    base_mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(base_mask).rounded_rectangle((margin, margin, n - margin, n - margin), radius, fill=255)
    bg = gradient((n, n), [(0.0, ORANGE_HI), (0.28, ORANGE), (0.55, ORANGE_DARK), (0.82, BLACK), (1.0, BLACK)])
    img.paste(bg, (0, 0), base_mask)

    # 2. Schatten unter dem gerahmten Foto
    fx0, fy0, fx1, fy1 = int(n * 0.20), int(n * 0.22), int(n * 0.80), int(n * 0.76)
    sh = Image.new("L", (n, n), 0)
    off = int(n * 0.018)
    ImageDraw.Draw(sh).rectangle((fx0 + off, fy0 + off * 2, fx1 + off, fy1 + off * 2), fill=150)
    sh = sh.resize((n // 16, n // 16)).filter(ImageFilter.GaussianBlur(2.2)).resize((n, n))
    sh = Image.composite(sh, Image.new("L", (n, n), 0), base_mask)
    img.paste((0, 0, 0, 255), (0, 0), sh)

    d = ImageDraw.Draw(img)
    # 3. Heller Passepartout-Rahmen
    d.rectangle((fx0, fy0, fx1, fy1), fill=MAT + (255,))
    # 4. Feine schwarze Linie (innerer Rahmen)
    mat = int(n * 0.055)
    lx0, ly0, lx1, ly1 = fx0 + mat, fy0 + mat, fx1 - mat, fy1 - mat
    d.rectangle((lx0, ly0, lx1, ly1), fill=BLACK + (255,))
    line = max(SS * 3, int(n * 0.012))
    px0, py0, px1, py1 = lx0 + line, ly0 + line, lx1 - line, ly1 - line

    # 5. Foto: Himmel im Verlauf Orange -> Schwarz, Sonne, Bergsilhouette
    pw, ph = px1 - px0, py1 - py0
    sky = gradient((pw, ph), [(0.0, ORANGE_HI), (0.55, ORANGE), (1.0, ORANGE_DARK)], angle_diag=False)
    img.paste(sky, (px0, py0))
    sun_r = int(pw * 0.11)
    sx, sy = px0 + int(pw * 0.70), py0 + int(ph * 0.30)
    d.ellipse((sx - sun_r, sy - sun_r, sx + sun_r, sy + sun_r), fill=(255, 226, 170, 255))
    d.polygon([(px0, py1), (px0, py0 + int(ph * 0.72)), (px0 + int(pw * 0.33), py0 + int(ph * 0.38)),
               (px0 + int(pw * 0.55), py0 + int(ph * 0.66)), (px0 + int(pw * 0.72), py0 + int(ph * 0.48)),
               (px1, py0 + int(ph * 0.80)), (px1, py1)], fill=BLACK + (255,))

    # 6. Unterer Galerie-Rand mit angedeuteter Signatur
    sig_y = fy1 - int(mat * 0.48)
    d.rounded_rectangle((fx1 - mat - int(pw * 0.34), sig_y - int(n * 0.007),
                         fx1 - mat, sig_y + int(n * 0.007)), int(n * 0.007), fill=ORANGE + (255,))

    # 7. Glanzkante oben
    gloss = Image.new("L", (n, n), 0)
    ImageDraw.Draw(gloss).rounded_rectangle((margin, margin, n - margin, n - margin), radius,
                                            outline=90, width=int(n * 0.006))
    gloss = Image.composite(gloss, Image.new("L", (n, n), 0),
                            gradient((n, n), [(0, (255,) * 3), (0.5, (0,) * 3), (1, (0,) * 3)]).convert("L"))
    img.paste((255, 255, 255, 255), (0, 0), gloss)
    return img.resize((S, S), Image.Resampling.LANCZOS)


def make_ios_icon() -> Image.Image:
    """iOS-App-Symbol: randlos und deckend (iOS rundet die Ecken selbst ab)."""
    full = make_logo_square()
    return full.convert("RGB")


def make_logo_square() -> Image.Image:
    """Wie make_logo(), aber ohne transparenten Rand und ohne eigene Rundung."""
    n = S * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 255))
    bg = gradient((n, n), [(0.0, ORANGE_HI), (0.28, ORANGE), (0.55, ORANGE_DARK), (0.82, BLACK), (1.0, BLACK)])
    img.paste(bg, (0, 0))
    # gleiches Motiv wie make_logo(), 6 % größer, da der Rand entfällt
    logo = make_logo().resize((int(S * 1.06), int(S * 1.06)), Image.Resampling.LANCZOS)
    logo = logo.resize((int(n * 1.06), int(n * 1.06)), Image.Resampling.LANCZOS)
    off = (n - logo.width) // 2
    # nur das Motiv (heller Rahmen, Foto) übernehmen – Hintergrund kommt vom Verlauf
    mask = Image.new("L", logo.size, 0)
    ImageDraw.Draw(mask).rectangle((int(logo.width * 0.18), int(logo.height * 0.20),
                                     int(logo.width * 0.83), int(logo.height * 0.79)), fill=255)
    img.paste(logo, (off, off), Image.composite(logo.getchannel("A"), mask, mask))
    return img.resize((S, S), Image.Resampling.LANCZOS)


def make_small(logo: Image.Image, size: int) -> Image.Image:
    """Kleine Größen leicht nachschärfen, damit sie in der Taskleiste klar wirken."""
    small = logo.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=80, threshold=1))
    return small


def main():
    ASSETS.mkdir(exist_ok=True)
    logo = make_logo()
    logo.save(ASSETS / "icon.png")
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [make_small(logo, s) for s in sizes]
    frames[-1].save(ASSETS / "icon.ico", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    logo.save(ASSETS / "icon.icns")
    make_small(logo, 64).save(ASSETS / "logo_small.png")
    # iOS: App-Symbol (randlos, deckend) und Logo für die Oberfläche
    ios_assets = Path(__file__).resolve().parent / "ios" / "FotoRahmen" / "Assets.xcassets"
    if ios_assets.exists():
        make_ios_icon().save(ios_assets / "AppIcon.appiconset" / "AppIcon.png")
        logo.resize((256, 256), Image.Resampling.LANCZOS).save(ios_assets / "Logo.imageset" / "Logo.png")
    print("Icons erzeugt in", ASSETS)


if __name__ == "__main__":
    main()
