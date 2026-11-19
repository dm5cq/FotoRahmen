# FotoRahmen – Entwicklerdokumentation

> © 2026 Stefan J. Kaiser · Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 3.–4. November 2026 · Lizenz: GNU GPL v3

Dieses Dokument beschreibt Aufbau, Abläufe und Code von FotoRahmen, damit später Änderungen sicher vorgenommen werden können.

**Inhalt:** [Überblick](#überblick) · [Projektstruktur](#projektstruktur) · [Architektur](#architektur) · [Design anpassen](#design-anpassen-themepy) · [Code-Referenz rahmen_core](#code-referenz-rahmen_corepy) · [Code-Referenz Oberfläche](#code-referenz-fotorahmenpy) · [Datenflüsse](#datenflüsse) · [Typische Änderungen](#typische-änderungen-schritt-für-schritt) · [Testen](#testen) · [Bauen](#bauen) · [Neue Version veröffentlichen](#neue-version-veröffentlichen) · [Bekannte Grenzen](#bekannte-grenzen) · [Fehlersuche](#fehlersuche)

---

## Überblick

| | |
|---|---|
| Sprache | Python 3.12 (läuft ab 3.10) |
| Oberfläche | Tkinter/ttk (in Python enthalten), dunkles Theme im Stil von Capture One (`theme.py`) |
| Bildverarbeitung | Pillow; numpy + tifffile + imagecodecs für 16-Bit-TIFF; pillow-heif für HEIC |
| Drag & Drop | tkinterdnd2 (optional – ohne das Paket startet die App ohne Drag & Drop) |
| Verpackung | PyInstaller → Windows: eine `.exe` (`--onefile`), macOS: `.app`-Bundle |
| Automatischer Build | GitHub Actions (`.github/workflows/build.yml`) |
| Einstellungen | JSON im Ordner Windows `%APPDATA%\FotoRahmen\`, macOS `~/Library/Application Support/FotoRahmen/`: `einstellungen.json` (letzter Zustand), `voreinstellungen.json` (benannte Voreinstellungen) |

**Grundsätze**
1. **Originale sind unantastbar.** Quelldateien werden nur gelesen. Ausgaben entstehen als temporäre Datei im Zielordner und werden erst nach erfolgreichem Schreiben umbenannt (`os.replace`). Ein Ziel darf nie eine Quelldatei sein; Eingabe- und Ausgabe-Ordner müssen verschieden sein.
2. **Kern und Oberfläche sind getrennt.** `rahmen_core.py` kennt kein Tkinter und kann allein (z. B. per Skript) genutzt und getestet werden.
3. **Qualität bleibt erhalten.** Bittiefe, Farbraum (inkl. CMYK), ICC-Profil, EXIF, DPI werden übernommen, soweit das Zielformat sie kann.
4. **Die Oberfläche blockiert nie.** Laden und Verarbeiten laufen in Threads; Tk-Widgets werden ausschließlich im Haupt-Thread angefasst.

## Projektstruktur

```
FotoRahmen/
├── fotorahmen.py          Oberfläche (Einstiegspunkt, main())
├── rahmen_core.py         Bildverarbeitung, Dateisuche, Namensplanung
├── theme.py               dunkles Design: Farben, ttk-Styles, dunkle Dialoge
├── app_info.py            Name, Version, Copyright – EINZIGE Stelle für Versionsnummer
├── selftest.py            automatischer Funktionstest aller Formate
├── make_version_info.py   erzeugt Windows-Versionsressource aus app_info.py
├── make_icons.py          erzeugt das Logo (Orange → Schwarz) als png/ico/icns
├── requirements.txt       Python-Abhängigkeiten
├── build_windows.bat      Build der EXE
├── build_macos.sh         Build der .app (+ ZIP)
├── assets/                Logo: icon.png (1024), icon.ico (Windows), icon.icns (macOS), logo_small.png
├── docs/                  diese Dokumentation, Screenshot
├── .github/workflows/     automatischer Build für Windows und macOS
├── README.md              Benutzer-Anleitung
├── CHANGELOG.md           Änderungsprotokoll
├── PROMPT.md              Prompt (Original + verbessert)
└── LICENSE                GNU GPL v3
```

## Architektur

**Fensteraufbau (2.0)**
```
┌ Werkzeugleiste: [Logo] FotoRahmen 2.0 · VOREINSTELLUNG [▼] Speichern… Löschen │ Info ┐
├ ORDNER  Eingabe / Ausgabe / Unterordner           (Drag & Drop-Ziel)      ┤
├ RAHMEN | TEXT | SCHUTZ | EFFEKTE | AUSGABE │ VORSCHAU       Größe alt → neu ┤
│ (Tabs, Abschnitte orange)           │ BILDER  Original | Ausgabe | Status  │
└ Statusleiste: Fortschritt · Status · Abbrechen · [RAHMEN ERSTELLEN]        ┘
```

```
┌──────────────────────────── fotorahmen.py (Haupt-Thread, Tk) ────────────────────────────┐
│  Bedienelemente ──get_settings()──► FrameSettings                                       │
│  Ordner ──rescan()──► core.scan_images() ──► files                                      │
│  files + Vorlage + overrides ──refresh_names()──► core.plan_jobs() ──► jobs ──► Liste   │
│  Auswahl ──load_preview()──► [Thread] core.load_preview() ─┐                            │
│  Start ──start()──► [Thread] core.process_file() je Job ───┤                            │
│                                                            ▼                            │
│                     self.events (Queue) ──_poll_events() alle 80 ms──► Liste/Vorschau   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### Gemeinsamer Ablauf `compose()` (Ausgabe **und** Vorschau)

```
Bild ──► auf Zielmaßstab bringen (lange Kante begrenzen / Vorschaugröße)
     ──► transparentes Wasserzeichen ins Bild (watermark_masks → _apply_watermark)
     ──► Rahmenschichten anfügen (layers, mitskaliert, dünne Linien ≥ 1 px)
     ──► Textzeile in den unteren Rand der äußersten Schicht (_text_mask)
     ──► Effekte: abgerundete Ecken, Schatten (nur PNG/WebP → RGBA)
     ──► Endkorrektur auf max_edge (nur Ausgabe)
```
Weil Vorschau und Ausgabe dieselbe Funktion nutzen, sieht die Vorschau immer wie das Ergebnis aus. `output_size()` berechnet die Endgröße vorab (Anzeige über der Vorschau; der Selbsttest prüft, dass sie exakt stimmt).

### Entscheidungsweg in `process_file()`

```
Quelle 16-Bit-TIFF?  ──ja──► Ziel TIFF? ──ja──► _process_highbit_tiff  (numpy, bleibt 16 Bit;
        │                        │                 Größe: _resize_array, Text: Maske überblenden)
        │                        └─nein─► _process_with_pillow (16-Bit-Grau → PNG/JP2 bleibt 16 Bit, sonst 8 Bit)
        └─nein──► animiertes GIF→GIF / WebP→WebP? ──ja──► _save_animated
                         └─nein──► exif_transpose → _save_single
                                    (normalize_mode → compose → convert_for_format → speichern
                                     mit Metadaten; bei Fehler ohne EXIF, dann ohne alles)
```

## Code-Referenz `rahmen_core.py`

### Konstanten
| Name | Bedeutung |
|---|---|
| `EXT_TO_FMT` | Endung → Pillow-Format. **Neue Eingabeformate hier eintragen.** HEIC nur, wenn `pillow_heif` geladen werden konnte. |
| `INPUT_EXTS` | Menge aller lesbaren Endungen (aus `EXT_TO_FMT`). |
| `OUTPUT_FORMATS` | Anzeigename → Endung für die Auswahl „Format“. `None` = wie Original. |
| `EFFECT_FORMATS` | Formate mit Transparenz, für die Ecken/Schatten gelten (`PNG`, `WEBP`). |
| `TEXT_POSITIONS` | `left`, `center`, `right`. |
| `WM_POSITIONS` | Wasserzeichen: `br`, `bl`, `tr`, `tl`, `c`, `tile` (diagonal wiederholt). |
| `CONFLICT_*` | `number` / `overwrite` / `skip` – Verhalten bei vorhandener Zieldatei. |
| `TMP_MARKER` | Kennung temporärer Dateien (`.<name>.fotorahmen-tmp.<ext>`). |
| `HEIF_OK`, `TIFFFILE_OK` | ob die optionalen Bibliotheken verfügbar sind. |

### Klassen
| Klasse | Beschreibung |
|---|---|
| `FrameSettings` | Alle Einstellungen. Rahmen: `double`, `unit` (`"px"`/`"pct"`), `outer_width`, `outer_color`, `inner_width`, `inner_color`, `bottom_extra`. Text: `text`, `text_size` (% der unteren Randhöhe), `text_pos`, `text_color`, `text_font` (Pfad oder leer). Ausgabe: `max_edge` (0 = aus). Effekte: `corner_radius` (% kurze Kante), `shadow` (% lange Kante). Schutz: `wm_text` (leer = aus), `wm_opacity` (%), `wm_size` (% kurze Kante), `wm_pos`, `wm_color`, `wm_outline`, `meta_author`, `meta_copyright` (leer = nicht schreiben). Farben als `(r, g, b)` 0–255. |
| `FrameSettings.to_px(v, w, h)` | Wert → Pixel. Bei `pct`: Prozent der **langen** Kante, mindestens 1 px. |
| `FrameSettings.layers(w, h)` | Liste von `Layer` von innen nach außen; `bottom_extra` wird der äußersten Schicht unten addiert. Schichten mit Breite 0 entfallen. |
| `FrameSettings.framed_size(w, h)` | Endgröße inkl. Rahmen. |
| `Layer(width, bottom, color)` | Eine Schicht: Breite oben/links/rechts, Breite unten, Farbe. |
| `Job(src, dst, skip, note)` | Eine geplante Verarbeitung. |
| `ImageReadError` | Quelle beschädigt/leer/unbekannt – Text ist für Benutzer bestimmt. |

### Funktionen (öffentlich)
| Funktion | Aufgabe |
|---|---|
| `compose(img, settings, scale, orig_size, fmt, ctx)` | **Gemeinsamer Ablauf** (siehe oben). `orig_size` = Maße, auf die sich die Einstellungen beziehen (bei der Vorschau ist `img` verkleinert); `ctx` = Platzhalterwerte. |
| `output_size(settings, w, h, fmt)` | Endgröße der Ausgabedatei. |
| `limit_scale(settings, w, h)` | Verkleinerungsfaktor für „lange Kante begrenzen“. |
| `apply_effects(img, settings)` | Ecken abrunden (geglättet) + Schatten → RGBA. |
| `effects_active(settings, fmt)` | Gelten Effekte für dieses Zielformat? |
| `watermark_masks(w, h, settings, text)` | Masken (Füllung, Kontur) für das Wasserzeichen; Grauwert = Deckkraft. Bei `tile` wird der um 30° gedrehte Text versetzt über das Bild verteilt (Kacheln werden mit `ImageChops.lighter` zusammengesetzt – schnell und speicherschonend). |
| `metadata_values`, `xmp_packet`, `_exif_with_copyright` | Urheber/Copyright: EXIF 0x013B/0x8298 (UTF-8), 0x9C9D XPAuthor (UTF-16), XMP-Paket. PNG: iTXt „Author“, „Copyright“, „XML:com.adobe.xmp“. TIFF: Tags 315, 33432, 700. |
| `expand_text(text, ctx)`, `make_context(src)` | Platzhalter `{name}`, `{datum}`, `{jahr}`. |
| `load_font(path, size)` | Eigene Schrift oder eingebaute Pillow-Schrift (mit Zwischenspeicher). |
| `scale_layers(layers, scale)` | Schichten skalieren, Linien ≥ 1 px. |
| `process_file(src, dst, settings, quality)` | **Herzstück.** Rahmen anlegen und speichern; Format aus Endung von `dst`. Gibt `(breite, höhe)` zurück. |
| `load_preview(path, max_size=1600)` | Verkleinertes RGB/RGBA-Bild + Originalgröße (nach EXIF-Drehung). JPEG wird per `draft()` schnell verkleinert dekodiert, 16-Bit-TIFF per Array-Ausdünnung. |
| `render_preview(thumb, orig_size, settings, box_w, box_h, fmt, ctx)` | Vorschau über `compose()`, passend in die Box skaliert. |
| `scan_images(in_dir, recursive, exclude)` | Bilder finden, natürlich sortiert; versteckte Dateien und der Ausgabe-Ordner werden ausgelassen. |
| `plan_jobs(files, in_dir, out_dir, template, overrides, format_label, conflict)` | Zielpfade festlegen, Duplikate im Stapel und Konflikte mit vorhandenen Dateien auflösen. |
| `render_template(template, src, number)` | `{name}`, `{nr}` (001…), `{datum}` (JJJJ-MM-TT) ersetzen. |
| `sanitize_stem(stem)` | Ungültige Zeichen → `_`, reservierte Windows-Namen → `NAME_`, max. 200 Zeichen. |
| `output_extension(src, format_label)` | Zielendung. |
| `cleanup_temp_files(out_dir)` | Reste abgebrochener Läufe löschen. |
| `rgb_to_cmyk(rgb)` | RGB → CMYK mit echtem Schwarzanteil. |
| `fill_for_mode(rgb, mode)` | Füllwert für beliebigen Pillow-Modus (RGB, RGBA, L, LA, CMYK, I;16, F …). |
| `add_frame(img, layers)` | Schichten um Pillow-Bild legen (Modus bleibt erhalten). |
| `normalize_mode(img)` | `1`, `P`, `PA`, `LAB`, `YCbCr`, `I;16B` … in gut verarbeitbare Modi wandeln. |
| `convert_for_format(img, fmt)` | Modus an Zielformat anpassen (z. B. Transparenz für JPEG auf Weiß legen). |
| `to_display(img)` | 8-Bit-RGB/RGBA für den Bildschirm. |
| `is_highbit_tiff(path)` | TIFF > 8 Bit und dekodierbar? |

### Interne Funktionen (Auswahl)
`_apply_watermark` / `_apply_watermark_array` (Pillow bzw. numpy/16 Bit, Alphakanal bleibt unverändert), `_contrast_color` (Kontur Schwarz oder Weiß), `_text_mask` (Textzeile als Graustufen-Maske für den unteren Rand), `_draw_text`, `_round_corners`, `_drop_shadow` (Weichzeichnen verkleinert = schnell), `_resize_array` (16-Bit/Float kanalweise über Pillow-Modus „F“ skalieren), `_read_tiff_array` (TIFF → Array + Metadaten; planare Daten werden umsortiert), `_pad_array` (Rahmen um Array), `_tiff_color` (Füllwert je Kanal/Farbinterpretation), `_array_to_8bit_image`, `_from_array` (Array → Pillow ohne veraltetes `mode`-Argument), `_apply_orientation` / `_apply_orientation_array` (EXIF-Orientierung 1–8), `_save_single`, `_save_animated`, `_exif_bytes` (EXIF mit Orientierung = 1, da die Pixel bereits gedreht sind), `_open` (Pillow öffnen mit Klartext-Fehlern).

**Wichtig zur Drehung:** Fotos mit EXIF-Orientierung werden vor dem Rahmen gedreht (`ImageOps.exif_transpose`), die Orientierung im Ergebnis wird auf 1 gesetzt. Bei 16-Bit-TIFF bleibt die Orientierung als Tag erhalten (Rahmen ist symmetrisch); nur wenn „Unten extra“ oder Text aktiv ist, werden die Pixel gedreht, damit Rand und Text im Anzeigebild unten und aufrecht liegen.

## Code-Referenz `fotorahmen.py`

| Teil | Beschreibung |
|---|---|
| `DEFAULTS` | Standardwerte aller Einstellungen. **Neue Einstellung → hier Schlüssel ergänzen** (nur bekannte Schlüssel werden geladen). |
| `PRESET_KEYS` | Welche Einstellungen zu einer Voreinstellung gehören. |
| `BUILTIN_PRESETS` | Mitgelieferte Voreinstellungen (werden angelegt, solange `voreinstellungen.json` fehlt). |
| `config_dir`, `load_config`, `load_presets`, `_write_json` | Einstellungen/Voreinstellungen lesen und schreiben (Fehler werden still ignoriert). |
| `create_root()` | Hauptfenster erzeugen – mit Drag & Drop (`TkinterDnD.Tk`), sonst `tk.Tk`. |
| `resource_path(rel)` | Pfad zu `assets/…` – funktioniert im Quellcode und in der gepackten App (`sys._MEIPASS`). |
| `enable_dpi_awareness()` | Windows: scharfe Schrift bei Skalierung. |
| `ColorChoice` | Weiß/Schwarz/Farbe…-Auswahl (Klick auf „Farbe…“ oder das Farbfeld öffnet den Farbwähler). `get()`/`set()` mit `'#rrggbb'`, `set_enabled(bool)`. |
| `App.v` | Dictionary aller Einstellungs-Variablen (Schlüssel wie `DEFAULTS`; Breiten der aktuellen Einheit als `outer_w`, `inner_w`, `bottom_w`). |
| `App.state_from_widgets` / `App.apply_state` | Zustand ↔ Widgets. Grundlage für Einstellungsdatei **und** Voreinstellungen. |
| `App.load_preset` / `save_preset` / `delete_preset` | Voreinstellungen; beim Laden werden erst alle `PRESET_KEYS` auf Standard gesetzt. |
| `AUTO_OUT_NAME`, `App._sync_auto_out`, `App._on_out_auto` | Ausgabe-Automatik: bei gesetztem Häkchen ist der Ausgabe-Ordner immer `Eingabe/„mit Rahmen“` (Feld schreibgeschützt); „Durchsuchen…“ beim Ausgabe-Ordner schaltet sie aus. |
| `App._setup_dnd` / `App._on_drop` | Drag & Drop: ein Ordner → Eingabe-Ordner; Bilder → `dropped_files` (Liste nur dieser Bilder). |
| `App._panel` / `App._section` | Palette mit Kopfzeile in Großbuchstaben / orange Abschnittstitel. |
| `App._tab_frame`, `_tab_text`, `_tab_protect`, `_tab_effects`, `_tab_output` | Inhalt der fünf Werkzeug-Tabs. Die Wasserzeichen-Position wird als Code (`br` …) gespeichert, die Combobox zeigt `WM_POS_LABELS`. |
| `App._set_icon` | Fenster-/Taskleisten-Logo: Windows `iconbitmap(icon.ico)` + `theme.set_window_icon` (Titelleiste oben links); macOS/Linux `iconphoto`. |
| `App._build_mac_menu` | macOS-Menüleiste (App-Menü „Über“, Ablage, Fenster, Hilfe; ⌘O, ⌘↩, ⌘Q). |
| `set_windows_app_id()` | Windows: eigene AppUserModelID → Taskleiste gruppiert unter dem FotoRahmen-Logo. |
| `App.__init__` | Zustand, Skalierungsfaktor `self.ui`, Aufbau, Tastenkürzel, Start der Event-Schleife. |
| `App.px(v)` | Pixelmaß × Bildschirm-Skalierung (Windows/Linux; macOS skaliert selbst). |
| `App._build_*` | Aufbau: Werkzeugleiste, Ordner, Tabs, Vorschau, Liste, Statusleiste. |
| `App._lock(widget)` | Widget als „während der Verarbeitung sperren“ registrieren. **Neue Bedienelemente immer über `_lock` anlegen.** |
| `App._number_row` | Zeile „Beschriftung: [Zahl] Einheit“, löst Vorschau-Aktualisierung aus. |
| `App._apply_unit` | Wechsel px ↔ %: Werte je Einheit getrennt gemerkt (`outer_px`, `outer_pct` …). |
| `App._update_frame_state` | Innerer Rahmen nur bei Doppelrahmen aktiv. |
| `App.get_settings` | Bedienelemente → `FrameSettings`; wirft `ValueError` mit Klartext. |
| `App.rescan` / `App.refresh_names` | Ordner einlesen / Zielnamen planen und Liste füllen. Während der Verarbeitung gesperrt. |
| `App.edit_selected` | Inline-Editor für den Ausgabenamen (Enter/Esc/Fokusverlust). Eigene Namen in `self.overrides`. |
| `App.load_preview` / `App.render_preview` | Laden im Thread mit Cache (12 Bilder), Zeichnen im Haupt-Thread. |
| `App._validate_before_start` / `App.start` | Prüfungen, dann Verarbeitung im Thread mit fester Job-Kopie `self.run_jobs`. |
| `App._poll_events` | Verarbeitet Nachrichten `preview`, `progress`, `item`, `done`. |
| `App._set_busy` | Sperrt/entsperrt alle registrierten Widgets. |

### Nachrichten der Event-Queue
| Nachricht | Inhalt |
|---|---|
| `("preview", key, thumb, size, error)` | Vorschau geladen (oder Fehlertext) |
| `("progress", i, name, total)` | Bild `i` wird bearbeitet |
| `("item", i, text)` | Ergebnis für Bild `i` („fertig …“, „Fehler: …“, „übersprungen …“) |
| `("done", ok, err, skipped, cancelled, out_dir)` | Lauf beendet |

## iOS-App (iPhone/iPad)

Der Ordner `ios/` enthält die SwiftUI-Version mit demselben Funktionsumfang. Aufbau, Entsprechungen zur Python-Version (`FrameSettings` ↔ `rahmen_core.FrameSettings`, `FrameRenderer.render` ↔ `compose()`, `Naming.plan` ↔ `plan_jobs()`, `Theme` ↔ `theme.C`), typische Änderungen, Installation und Weitergabe stehen in [ios/README.md](../ios/README.md). Bei Funktionsänderungen beide Versionen anpassen; `make_icons.py` erzeugt auch das iOS-App-Symbol.

## Logo und Symbole

- Quelle ist `make_icons.py` (reines Pillow, keine Grafikdateien nötig). Farben oben in der Datei (`ORANGE_HI`, `ORANGE`, `ORANGE_DARK`, `BLACK`), Aufruf `python make_icons.py` erzeugt alle Dateien in `assets/` neu.
- **Windows:** PyInstaller bettet `icon.ico` in die EXE ein → Explorer, Task-Manager, Taskleiste (gepinnt). Zur Laufzeit setzt `iconbitmap(default=…)` das Symbol für alle Fenster; zusätzlich lädt `theme.set_window_icon()` die passenden Größen aus der `.ico` per `LoadImageW` und setzt sie mit `WM_SETICON` (klein = Titelleiste oben links, groß = Alt+Tab/Taskleiste) – DPI-gerecht über `GetSystemMetricsForDpi`. Das geschieht beim Start, 300 ms nach dem Anzeigen und für jeden Dialog. `SetCurrentProcessExplicitAppUserModelID` sorgt dafür, dass Windows nicht das Python-Symbol zeigt.
- **macOS:** `icon.icns` wird zum Bundle-Symbol (Dock, Finder, ⌘-Tab). Der Name in der Menüleiste kommt aus `CFBundleName` („FotoRahmen“, von PyInstaller aus `--name`).
- Nach einer Logo-Änderung neu bauen; Windows zeigt ggf. noch das alte Symbol aus dem Symbol-Cache (Neuanmeldung hilft).

## Design anpassen (`theme.py`)

- **Farben:** nur das Dictionary `C` ändern – z. B. `C["accent"] = "#3d9cf5"` für Blau statt Orange. Alle Styles und Dialoge übernehmen den Wert.
- **Schriftgrößen:** `apply_theme()` → `base_size` (Windows/Linux 10 pt, macOS 13 pt).
- **Styles:** `TButton` (normal), `Accent.TButton` (orange Hauptaktion), `Tool.TButton` (flach in der Werkzeugleiste), `Header.TLabel` (Kopfzeilen), `Section.TLabel` (orange Abschnitte), `Hint.TLabel` (Nebentext).
- **Dialoge:** `theme.info/warn/error/ask/ask_string` statt `tkinter.messagebox` verwenden, damit alles dunkel bleibt. Der Farbwähler und die Ordnerauswahl sind Systemdialoge.
- Warum „clam“? Die nativen Themes („vista“, „aqua“) ignorieren Hintergrund- und Schriftfarben vieler Widgets.

## Datenflüsse

**Einstellung ändern:** Spinbox/Radiobutton → `on_settings_changed()` → nach 120 ms `render_preview()` → `get_settings()` → `core.render_preview()`.

**Namensvorlage ändern:** `var_template`-Trace → nach 250 ms `refresh_names()` → `core.plan_jobs()` → Liste.

**Start:** `start()` → `_validate_before_start()` → `rescan()` → Ausgabe-Ordner anlegen, Temp-Reste löschen → Einstellungen speichern → `_set_busy(True)` → Thread: je Job `core.process_file()` → Events → `_finish()`.

## Typische Änderungen Schritt für Schritt

### Neue Rahmen-Option (Beispiel „Abstand zwischen innerem und äußerem Rahmen“)
1. `rahmen_core.FrameSettings`: Feld ergänzen (z. B. `gap_width: float = 0`, `gap_color`).
2. `FrameSettings.layers()`: Schicht an passender Stelle einfügen. **Alle Ausgabewege nutzen `layers()`** (über `compose()` und den 16-Bit-Pfad) – sonst ist nichts anzupassen.
3. `fotorahmen.DEFAULTS` (und ggf. `PRESET_KEYS`): Schlüssel ergänzen (je Einheit: `gap_px`, `gap_pct`).
4. `App._tab_frame`: Zeile mit `self._number_row(box, zeile, "Abstand", "gap_w")` anlegen (sperrt sich automatisch, aktualisiert die Vorschau).
5. `App._apply_unit` und `App.state_from_widgets`: den neuen `…_w`-Schlüssel wie `outer`/`inner`/`bottom` mitführen.
6. `App.get_settings`: Wert übergeben.
7. `selftest.py` erweitern, dann `python selftest.py`.

### Neue Voreinstellung mitliefern
Eintrag in `BUILTIN_PRESETS` (nur Schlüssel aus `PRESET_KEYS`; nicht angegebene Werte = Standard). Wirkt nur, solange der Benutzer noch keine `voreinstellungen.json` hat.

### Neuer Werkzeug-Tab
In `App._build_tools` ein Paar `("Titel", self._tab_neu)` ergänzen und die Methode `_tab_neu(self, box)` schreiben (Abschnitte mit `self._section`, Zahlen mit `self._number_row`, Hinweise mit `self._hint`).

### Neues Eingabeformat
`EXT_TO_FMT` erweitern (Pillow muss es lesen können). Falls es ein eigenes Speicherformat braucht: `convert_for_format()` und ggf. `opts` in `_save_single()` ergänzen.

### Neues Ausgabeformat zur Auswahl
In `OUTPUT_FORMATS` eintragen (z. B. `"JPEG 2000 (.jp2)": ".jp2"`). Die Endung muss in `EXT_TO_FMT` stehen. Unterstützt das Format Transparenz, ggf. in `EFFECT_FORMATS` aufnehmen.

### Neuer Platzhalter für Dateinamen
`render_template()` erweitern und den Hinweistext in `App._build_output_box` anpassen.

### Texte/Optik
Siehe [Design anpassen](#design-anpassen-themepy). Vorschau-Hintergrund: `C["viewer"]`. Alle Texte stehen direkt im Code (Deutsch).

### Version/Copyright
Nur `app_info.py` ändern; Info-Dialog, Windows-Versionsressource und macOS-Info.plist übernehmen die Werte automatisch. Danach `CHANGELOG.md` ergänzen.

## Dokumentation erzeugen

Die PDF-Dokumentation (`docs/FotoRahmen_Dokumentation.pdf`) wird per Skript erzeugt:

```bash
python docs/werkzeuge/beispielbilder.py                 # Beispielfotos + Vorher/Nachher (docs/beispiele/)
python docs/werkzeuge/screenshots.py <Ordner mit Fotos> # startet die App, Stapellauf, Screenshots (docs/bilder/)
python selftest.py > docs/bilder/selftest.txt           # Testprotokoll für die PDF
python docs/werkzeuge/dokumentation_pdf.py              # PDF bauen (reportlab)
```

Die Code-Referenz in der PDF wird automatisch aus den Docstrings gelesen – nach Code-Änderungen das Skript einfach erneut ausführen. Unter Linux ohne Bildschirm: `xvfb-run -s "-screen 0 1400x900x24" python docs/werkzeuge/screenshots.py …`.

## Testen

```bash
python -m pip install -r requirements.txt
python selftest.py        # alle Formate × alle Ausgabeformate, Originale unverändert, Sonderfälle
python fotorahmen.py      # Oberfläche aus dem Quellcode starten
```

`selftest.py` prüft zusätzlich Text, „lange Kante begrenzen“ (Endgröße muss exakt `output_size()` entsprechen), Effekte (Transparenz in der Ecke) und WebP-Ausgabe, auch für 16-Bit-TIFF. Es erzeugt Testbilder (JPEG mit EXIF-Drehung, PNG, CMYK, WebP statisch + animiert, BMP, GIF animiert, 16-Bit-TIFF, 8-Bit-TIFF, HEIC falls verfügbar, beschädigte Datei), verarbeitet jedes in jedes Ausgabeformat, prüft Endgrößen, Lesbarkeit der Ergebnisse, CMYK-Schwarz, Dateinamen-Bereinigung und dass die Quelldateien byte-gleich bleiben. Exit-Code ≠ 0 bei Fehlern – der automatische Build bricht dann ab.

**Manuelle Prüfliste vor einer Veröffentlichung:** Logo in Taskleiste/Task-Manager (Windows) bzw. Dock/Menüleiste (macOS) · Wasserzeichen in allen Positionen · Metadaten in Lightroom/Datei-Eigenschaften prüfen · Ordner wählen · Ordner und einzelne Bilder per Drag & Drop · Voreinstellung laden/speichern/löschen · Text mit Platzhaltern und eigener Schrift · Effekte bei PNG · lange Kante begrenzen · Einfach/Doppelt umschalten · px/% umschalten (Werte bleiben je Einheit erhalten) · Farbe wählen · Unten extra · Namen per Doppelklick ändern · Start/Abbrechen · Ausgabe-Ordner öffnen · Info-Dialog · App beenden und neu starten (Einstellungen da).

## Bauen

Voraussetzung: Python **3.12** von python.org (enthält Tk). PyInstaller kann **nicht** über Betriebssysteme hinweg bauen – die EXE entsteht nur unter Windows, die App nur unter macOS.

| Plattform | Befehl | Ergebnis |
|---|---|---|
| Windows | `build_windows.bat` | `dist\FotoRahmen.exe` (eine Datei) |
| macOS | `./build_macos.sh` | `dist/FotoRahmen.app` + `dist/FotoRahmen-macOS.zip` |
| beide (automatisch) | Push nach GitHub | Artifacts im Actions-Lauf; bei Tag `v*` zusätzlich Release |

Wichtige PyInstaller-Optionen: `--windowed` (kein Konsolenfenster), `--onefile` (nur Windows), `--add-data assets` (Logo-Dateien für Fenster, Taskleiste und Werkzeugleiste), `--collect-all pillow_heif`, `--collect-submodules imagecodecs` und `--collect-all tkinterdnd2` (dynamisch geladene Bibliotheken bzw. die tkdnd-Erweiterung). Unter macOS setzt `build_macos.sh` danach in der Info.plist Erscheinungsbild, Version und Copyright und signiert die App ad-hoc neu (sonst startet sie auf Apple-Silicon-Macs nicht).

Der Workflow startet die fertige EXE/App zusätzlich 15 Sekunden lang als Rauchtest.

**Signieren (optional):** Für Starts ohne Sicherheitswarnung braucht es unter Windows ein Code-Signing-Zertifikat (`signtool`), unter macOS eine Apple Developer ID (`codesign --options runtime --sign "Developer ID Application: …"` + `notarytool`). Das ist kostenpflichtig und nicht eingerichtet.

## Neue Version veröffentlichen
1. `app_info.py`: `VERSION`, `RELEASE_DATE`.
2. `CHANGELOG.md`: Abschnitt ergänzen.
3. `python selftest.py`.
4. Auf GitHub unter Releases ein neues Release mit neuem Tag (z. B. `2.1.0`) veröffentlichen – GitHub baut und hängt EXE und Apps an. Nachträglich: Actions › FotoRahmen bauen › Run workflow mit dem Tag-Namen.

## Bekannte Grenzen
- RAW-Formate werden nicht gelesen (bewusst; Export als TIFF empfohlen).
- Mehrseitige TIFFs: nur Seite 1.
- 16-Bit-RGB nach PNG wird 8 Bit (Pillow kann 16-Bit-RGB-PNG nicht schreiben); 16-Bit bleibt bei TIFF→TIFF erhalten.
- Bei 16-Bit-TIFF→TIFF werden ICC-Profil, Auflösung und Orientierung übernommen, sonstige EXIF/IPTC/XMP-Daten nicht.
- Sehr große Bilder brauchen viel Arbeitsspeicher (16-Bit-RGB mit 100 MP ≈ 600 MB je Kopie).
- Ohne Signatur zeigen Windows/macOS beim ersten Start eine Warnung.
- Effekte (Ecken/Schatten) nur für PNG und WebP; animierte GIFs ohne Effekte.
- Ein sichtbares Wasserzeichen erschwert Missbrauch, verhindert ihn aber nicht vollständig; Metadaten können von anderen Programmen entfernt werden.
- Animierte GIF/WebP erhalten Wasserzeichen, aber keine Copyright-Metadaten.
- Beim Wasserzeichen wird die Schrift aus dem Tab TEXT verwendet (eingebaut oder eigene Datei).
- Text erscheint nur im unteren Rand der äußersten Rahmenschicht.
- Farbwähler und Ordnerauswahl sind Systemdialoge und folgen dem System-Erscheinungsbild.

## Fehlersuche
| Problem | Ursache / Lösung |
|---|---|
| macOS: „App ist beschädigt“ | Quarantäne-Attribut aus dem Download: `xattr -cr /Applications/FotoRahmen.app` |
| Windows: SmartScreen | „Weitere Informationen“ → „Trotzdem ausführen“ |
| HEIC fehlt in der Liste | `pillow-heif` nicht installiert/eingebunden (`--collect-all pillow_heif` beim Build) |
| 16-Bit-TIFF wird 8 Bit | `tifffile`/`imagecodecs` fehlen → Rückfall auf Pillow |
| Einstellungen zurücksetzen | Datei `einstellungen.json` (Pfad siehe Überblick) löschen |
| Drag & Drop fehlt (kein Hinweis in der Ordner-Kopfzeile) | `tkinterdnd2` nicht installiert bzw. beim Build nicht eingebunden (`--collect-all tkinterdnd2`) |
| Text erscheint nicht | Unterer Rand zu schmal – „Unten extra“ erhöhen; Textgröße ist relativ zur Randhöhe |
| Ecken/Schatten fehlen | Nur bei Ausgabe als PNG oder WebP (Hinweis im Tab EFFEKTE) |
| Start aus Quellcode: „No module named tkinter“ | Python von python.org verwenden (Homebrew-Python: `brew install python-tk`) |
