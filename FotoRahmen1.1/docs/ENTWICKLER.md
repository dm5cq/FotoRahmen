# FotoRahmen – Entwicklerdokumentation

> © 2026 Stefan J. Kaiser · Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 3. November 2026 · Lizenz: MIT

Dieses Dokument beschreibt Aufbau, Abläufe und Code von FotoRahmen, damit später Änderungen sicher vorgenommen werden können.

**Inhalt:** [Überblick](#überblick) · [Projektstruktur](#projektstruktur) · [Architektur](#architektur) · [Code-Referenz rahmen_core](#code-referenz-rahmen_corepy) · [Code-Referenz Oberfläche](#code-referenz-fotorahmenpy) · [Datenflüsse](#datenflüsse) · [Typische Änderungen](#typische-änderungen-schritt-für-schritt) · [Testen](#testen) · [Bauen](#bauen) · [Neue Version veröffentlichen](#neue-version-veröffentlichen) · [Bekannte Grenzen](#bekannte-grenzen) · [Fehlersuche](#fehlersuche)

---

## Überblick

| | |
|---|---|
| Sprache | Python 3.12 (läuft ab 3.10) |
| Oberfläche | Tkinter/ttk (in Python enthalten, native Optik unter Windows und macOS) |
| Bildverarbeitung | Pillow; numpy + tifffile + imagecodecs für 16-Bit-TIFF; pillow-heif für HEIC |
| Verpackung | PyInstaller → Windows: eine `.exe` (`--onefile`), macOS: `.app`-Bundle |
| Automatischer Build | GitHub Actions (`.github/workflows/build.yml`) |
| Einstellungen | JSON: Windows `%APPDATA%\FotoRahmen\einstellungen.json`, macOS `~/Library/Application Support/FotoRahmen/einstellungen.json` |

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
├── app_info.py            Name, Version, Copyright – EINZIGE Stelle für Versionsnummer
├── selftest.py            automatischer Funktionstest aller Formate
├── make_version_info.py   erzeugt Windows-Versionsressource aus app_info.py
├── requirements.txt       Python-Abhängigkeiten
├── build_windows.bat      Build der EXE
├── build_macos.sh         Build der .app (+ ZIP)
├── assets/                Icons (png, ico, icns)
├── docs/                  diese Dokumentation, Screenshot
├── .github/workflows/     automatischer Build für Windows und macOS
├── README.md              Benutzer-Anleitung
├── CHANGELOG.md           Änderungsprotokoll
├── PROMPT.md              Prompt (Original + verbessert)
└── LICENSE                MIT-Lizenz
```

## Architektur

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

### Entscheidungsweg in `process_file()`

```
Quelle 16-Bit-TIFF?  ──ja──► Ziel TIFF? ──ja──► _process_highbit_tiff  (numpy, bleibt 16 Bit)
        │                        └─nein─► _process_with_pillow (16-Bit-Grau → PNG/JP2 bleibt 16 Bit, sonst 8 Bit)
        └─nein──► animiertes GIF→GIF / WebP→WebP? ──ja──► _save_animated
                         └─nein──► exif_transpose → _save_single
                                    (normalize_mode → add_frame → convert_for_format → speichern
                                     mit Metadaten; bei Fehler ohne EXIF, dann ohne alles)
```

## Code-Referenz `rahmen_core.py`

### Konstanten
| Name | Bedeutung |
|---|---|
| `EXT_TO_FMT` | Endung → Pillow-Format. **Neue Eingabeformate hier eintragen.** HEIC nur, wenn `pillow_heif` geladen werden konnte. |
| `INPUT_EXTS` | Menge aller lesbaren Endungen (aus `EXT_TO_FMT`). |
| `OUTPUT_FORMATS` | Anzeigename → Endung für die Auswahl „Format“. `None` = wie Original. |
| `CONFLICT_*` | `number` / `overwrite` / `skip` – Verhalten bei vorhandener Zieldatei. |
| `TMP_MARKER` | Kennung temporärer Dateien (`.<name>.fotorahmen-tmp.<ext>`). |
| `HEIF_OK`, `TIFFFILE_OK` | ob die optionalen Bibliotheken verfügbar sind. |

### Klassen
| Klasse | Beschreibung |
|---|---|
| `FrameSettings` | Alle Rahmen-Einstellungen. Felder: `double`, `unit` (`"px"`/`"pct"`), `outer_width`, `outer_color`, `inner_width`, `inner_color`, `bottom_extra`. Farben als `(r, g, b)` 0–255. |
| `FrameSettings.to_px(v, w, h)` | Wert → Pixel. Bei `pct`: Prozent der **langen** Kante, mindestens 1 px. |
| `FrameSettings.layers(w, h)` | Liste von `Layer` von innen nach außen; `bottom_extra` wird der äußersten Schicht unten addiert. Schichten mit Breite 0 entfallen. |
| `FrameSettings.framed_size(w, h)` | Endgröße inkl. Rahmen. |
| `Layer(width, bottom, color)` | Eine Schicht: Breite oben/links/rechts, Breite unten, Farbe. |
| `Job(src, dst, skip, note)` | Eine geplante Verarbeitung. |
| `ImageReadError` | Quelle beschädigt/leer/unbekannt – Text ist für Benutzer bestimmt. |

### Funktionen (öffentlich)
| Funktion | Aufgabe |
|---|---|
| `process_file(src, dst, settings, quality)` | **Herzstück.** Rahmen anlegen und speichern; Format aus Endung von `dst`. Gibt `(breite, höhe)` zurück. |
| `load_preview(path, max_size=1600)` | Verkleinertes RGB/RGBA-Bild + Originalgröße (nach EXIF-Drehung). JPEG wird per `draft()` schnell verkleinert dekodiert, 16-Bit-TIFF per Array-Ausdünnung. |
| `render_preview(thumb, orig_size, settings, box_w, box_h)` | Vorschau mit maßstabsgetreuem Rahmen; dünne Linien min. 1 px. |
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
`_read_tiff_array` (TIFF → Array + Metadaten; planare Daten werden umsortiert), `_pad_array` (Rahmen um Array), `_tiff_color` (Füllwert je Kanal/Farbinterpretation), `_array_to_8bit_image`, `_from_array` (Array → Pillow ohne veraltetes `mode`-Argument), `_apply_orientation` / `_apply_orientation_array` (EXIF-Orientierung 1–8), `_save_single`, `_save_animated`, `_exif_bytes` (EXIF mit Orientierung = 1, da die Pixel bereits gedreht sind), `_open` (Pillow öffnen mit Klartext-Fehlern).

**Wichtig zur Drehung:** Fotos mit EXIF-Orientierung werden vor dem Rahmen gedreht (`ImageOps.exif_transpose`), die Orientierung im Ergebnis wird auf 1 gesetzt. Bei 16-Bit-TIFF bleibt die Orientierung als Tag erhalten (Rahmen ist symmetrisch); nur wenn „Unten extra“ aktiv ist, werden die Pixel gedreht, damit der breite Rand im Anzeigebild unten liegt.

## Code-Referenz `fotorahmen.py`

| Teil | Beschreibung |
|---|---|
| `DEFAULTS` | Standardwerte aller Einstellungen. **Neue Einstellung → hier Schlüssel ergänzen** (nur bekannte Schlüssel werden geladen). |
| `config_file`, `load_config`, `save_config` | Einstellungen lesen/schreiben (Fehler werden still ignoriert). |
| `resource_path(rel)` | Pfad zu `assets/…` – funktioniert im Quellcode und in der gepackten App (`sys._MEIPASS`). |
| `enable_dpi_awareness()` | Windows: scharfe Schrift bei Skalierung. |
| `ColorChoice` | Weiß/Schwarz/Farbe-Auswahl. `get()` → `'#rrggbb'`, `set_enabled(bool)`. |
| `App.__init__` | Zustand, Skalierungsfaktor `self.ui`, Aufbau, Tastenkürzel, Start der Event-Schleife. |
| `App.px(v)` | Pixelmaß × Bildschirm-Skalierung (Windows/Linux; macOS skaliert selbst). |
| `App._build_*` | Aufbau der Bereiche Ordner, Rahmen, Ausgabe, Vorschau, Liste, Fußzeile. |
| `App._lock(*widgets)` | Widget als „während der Verarbeitung sperren“ registrieren. **Neue Bedienelemente immer über `_lock` anlegen.** |
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

## Datenflüsse

**Einstellung ändern:** Spinbox/Radiobutton → `on_settings_changed()` → nach 120 ms `render_preview()` → `get_settings()` → `core.render_preview()`.

**Namensvorlage ändern:** `var_template`-Trace → nach 250 ms `refresh_names()` → `core.plan_jobs()` → Liste.

**Start:** `start()` → `_validate_before_start()` → `rescan()` → Ausgabe-Ordner anlegen, Temp-Reste löschen → Einstellungen speichern → `_set_busy(True)` → Thread: je Job `core.process_file()` → Events → `_finish()`.

## Typische Änderungen Schritt für Schritt

### Neue Rahmen-Option (Beispiel „Abstand zwischen innerem und äußerem Rahmen“)
1. `rahmen_core.FrameSettings`: Feld ergänzen (z. B. `gap_width: float = 0`, `gap_color`).
2. `FrameSettings.layers()`: Schicht an passender Stelle einfügen. **Alle Ausgabewege nutzen `layers()`** (Pillow, 16-Bit-TIFF, animiert, Vorschau) – sonst ist nichts anzupassen.
3. `fotorahmen.DEFAULTS`: Schlüssel ergänzen (je Einheit: `gap_px`, `gap_pct`).
4. `App._build_frame_box`: Zeile mit `self._number_row(...)` anlegen (sperrt sich automatisch).
5. `App._apply_unit` und `App.collect_config`: Schlüssel mitführen.
6. `App.get_settings`: Wert übergeben.
7. `selftest.py`: erwartete Größe anpassen/erweitern, dann `python selftest.py`.

### Neues Eingabeformat
`EXT_TO_FMT` erweitern (Pillow muss es lesen können). Falls es ein eigenes Speicherformat braucht: `convert_for_format()` und ggf. `opts` in `_save_single()` ergänzen.

### Neues Ausgabeformat zur Auswahl
In `OUTPUT_FORMATS` eintragen (z. B. `"WebP (.webp)": ".webp"`). Die Endung muss in `EXT_TO_FMT` stehen.

### Neuer Platzhalter für Dateinamen
`render_template()` erweitern und den Hinweistext in `App._build_output_box` anpassen.

### Texte/Optik
Schriftgrößen und Farben: `App._setup_style()`. Vorschau-Hintergrund: `PREVIEW_BG`. Alle Texte stehen direkt im Code (Deutsch).

### Version/Copyright
Nur `app_info.py` ändern; Info-Dialog, Windows-Versionsressource und macOS-Info.plist übernehmen die Werte automatisch. Danach `CHANGELOG.md` ergänzen.

## Testen

```bash
python -m pip install -r requirements.txt
python selftest.py        # alle Formate × alle Ausgabeformate, Originale unverändert, Sonderfälle
python fotorahmen.py      # Oberfläche aus dem Quellcode starten
```

`selftest.py` erzeugt Testbilder (JPEG mit EXIF-Drehung, PNG, CMYK, WebP statisch + animiert, BMP, GIF animiert, 16-Bit-TIFF, 8-Bit-TIFF, HEIC falls verfügbar, beschädigte Datei), verarbeitet jedes in jedes Ausgabeformat, prüft Endgrößen, Lesbarkeit der Ergebnisse, CMYK-Schwarz, Dateinamen-Bereinigung und dass die Quelldateien byte-gleich bleiben. Exit-Code ≠ 0 bei Fehlern – der automatische Build bricht dann ab.

**Manuelle Prüfliste vor einer Veröffentlichung:** Ordner wählen · Einfach/Doppelt umschalten · px/% umschalten (Werte bleiben je Einheit erhalten) · Farbe wählen · Unten extra · Namen per Doppelklick ändern · Start/Abbrechen · Ausgabe-Ordner öffnen · Info-Dialog · App beenden und neu starten (Einstellungen da).

## Bauen

Voraussetzung: Python **3.12** von python.org (enthält Tk). PyInstaller kann **nicht** über Betriebssysteme hinweg bauen – die EXE entsteht nur unter Windows, die App nur unter macOS.

| Plattform | Befehl | Ergebnis |
|---|---|---|
| Windows | `build_windows.bat` | `dist\FotoRahmen.exe` (eine Datei, ca. 60–90 MB) |
| macOS | `./build_macos.sh` | `dist/FotoRahmen.app` + `dist/FotoRahmen-macOS.zip` |
| beide (automatisch) | Push nach GitHub | Artifacts im Actions-Lauf; bei Tag `v*` zusätzlich Release |

Wichtige PyInstaller-Optionen: `--windowed` (kein Konsolenfenster), `--onefile` (nur Windows), `--add-data assets/icon.png` (Fenster-Icon), `--collect-all pillow_heif` und `--collect-submodules imagecodecs` (dynamisch geladene Bibliotheken). Unter macOS setzt `build_macos.sh` danach in der Info.plist helles Erscheinungsbild, Version und Copyright und signiert die App ad-hoc neu (sonst startet sie auf Apple-Silicon-Macs nicht).

Der Workflow startet die fertige EXE/App zusätzlich 15 Sekunden lang als Rauchtest.

**Signieren (optional):** Für Starts ohne Sicherheitswarnung braucht es unter Windows ein Code-Signing-Zertifikat (`signtool`), unter macOS eine Apple Developer ID (`codesign --options runtime --sign "Developer ID Application: …"` + `notarytool`). Das ist kostenpflichtig und nicht eingerichtet.

## Neue Version veröffentlichen
1. `app_info.py`: `VERSION`, `RELEASE_DATE`.
2. `CHANGELOG.md`: Abschnitt ergänzen.
3. `python selftest.py`.
4. Commit, dann Tag: `git tag v1.2.0 && git push --tags` → GitHub baut und legt das Release mit EXE und Apps an.

## Bekannte Grenzen
- RAW-Formate werden nicht gelesen (bewusst; Export als TIFF empfohlen).
- Mehrseitige TIFFs: nur Seite 1.
- 16-Bit-RGB nach PNG wird 8 Bit (Pillow kann 16-Bit-RGB-PNG nicht schreiben); 16-Bit bleibt bei TIFF→TIFF erhalten.
- Bei 16-Bit-TIFF→TIFF werden ICC-Profil, Auflösung und Orientierung übernommen, sonstige EXIF/IPTC/XMP-Daten nicht.
- Sehr große Bilder brauchen viel Arbeitsspeicher (16-Bit-RGB mit 100 MP ≈ 600 MB je Kopie).
- Ohne Signatur zeigen Windows/macOS beim ersten Start eine Warnung.

## Fehlersuche
| Problem | Ursache / Lösung |
|---|---|
| macOS: „App ist beschädigt“ | Quarantäne-Attribut aus dem Download: `xattr -cr /Applications/FotoRahmen.app` |
| Windows: SmartScreen | „Weitere Informationen“ → „Trotzdem ausführen“ |
| HEIC fehlt in der Liste | `pillow-heif` nicht installiert/eingebunden (`--collect-all pillow_heif` beim Build) |
| 16-Bit-TIFF wird 8 Bit | `tifffile`/`imagecodecs` fehlen → Rückfall auf Pillow |
| Einstellungen zurücksetzen | Datei `einstellungen.json` (Pfad siehe Überblick) löschen |
| Start aus Quellcode: „No module named tkinter“ | Python von python.org verwenden (Homebrew-Python: `brew install python-tk`) |
