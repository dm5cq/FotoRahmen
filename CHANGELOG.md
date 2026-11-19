# Änderungsprotokoll

## 2.0.0 – 2026-11-19 (GitHub)

- Quellcode (Desktop und iOS) ausgepackt im Repository `dm5cq/FotoRahmen`; alte Stände, ZIP- und EXE-Dateien entfernt (bleiben in der Git-Historie abrufbar).
- **Lizenz: GNU General Public License v3** (vorher MIT) – Kopfzeilen, Info-Dialog, README und PDF angepasst.

## iOS 2.0.0 – 2026-11-06

- **Neue App für iPhone und iPad** (SwiftUI, iOS/iPadOS 17+) mit dem Funktionsumfang von 2.0: Rahmen, Textzeile/Signatur, Copyright-Wasserzeichen und -Metadaten, Effekte, Größenbegrenzung, Formate, Dateinamen, Voreinstellungen, Vorschau, Stapelverarbeitung.
- Quellen: Fotos-Mediathek (mit Originaldateinamen), Ordner und Dateien aus der Dateien-App, Drag & Drop (iPad).
- Ziel automatisch „mit Rahmen“: Unterordner im gewählten Ordner, Album in Fotos bzw. App-Ordner in der Dateien-App; Originale bleiben unverändert.
- Gleiches dunkles Design (Capture One) und Logo Orange → Schwarz als App-Symbol; iPad mit Werkzeug-Tabs links und Vorschau rechts.
- Xcode-Projekt unter `ios/`, GitHub-Workflow mit Prüf-Build und unsignierter IPA; Anleitung inkl. Weitergabe an Freunde per TestFlight in `ios/README.md`.

## 2.0.0 – 2026-11-04

### Copyright-Schutz (neuer Tab SCHUTZ)
- **Transparentes Wasserzeichen im Bild:** Text mit Platzhaltern (`{jahr}`, `{datum}`, `{name}`), Deckkraft, Größe (in % der kurzen Bildkante), Farbe, optionale Kontrastkante. Positionen: vier Ecken, Mitte oder **diagonal über das ganze Bild wiederholt** (lässt sich nicht einfach wegschneiden).
- Funktioniert in allen Formaten, auch CMYK und **16-Bit-TIFF** (Bittiefe bleibt erhalten); bei EXIF-gedrehten Fotos steht das Wasserzeichen aufrecht.
- **Copyright in den Metadaten:** Urheber und Copyright werden geschrieben als EXIF (Artist, Copyright, XPAuthor), **XMP** (dc:creator, dc:rights, xmpRights:Marked), PNG-Textfelder bzw. TIFF-Tags – Unicode-sicher (©, Umlaute).
- Neue Voreinstellung „Copyright-Schutz Web“.

### Logo und Systemintegration
- **Neues Logo** mit Verlauf Orange → Schwarz (gerahmtes Foto mit Bergsilhouette), erzeugt per `make_icons.py` in allen Größen von 16 bis 1024 px.
- **Windows:** Logo in EXE, Explorer, **Task-Manager**, **Taskleiste** und **oben links in der Titelleiste** – im Hauptfenster und in allen Dialogen. Das Symbol wird direkt über die Windows-API (WM_SETICON) aus der `.ico` geladen, jeweils in der passenden Größe für die Bildschirm-Skalierung (16–48 px), damit es scharf ist und nicht die Tk-Feder erscheint. Eigene AppUserModelID, `.ico` mit 9 Größen.
- **macOS:** Logo im **Dock**, Finder und App-Umschalter (`.icns`); eigene **Menüleiste** mit „Über FotoRahmen“, Ablage (Ordner wählen ⌘O, Voreinstellung speichern, Rahmen erstellen ⌘↩), Fenster und Hilfe.
- Logo in der Werkzeugleiste der App.

### Bedienung
- **Ausgabe-Ordner automatisch:** Standardmäßig ist der Ausgabe-Ordner immer `Eingabe-Ordner/mit Rahmen` (Häkchen „Ausgabe automatisch in Unterordner „mit Rahmen““). Das Feld folgt jedem neuen Eingabe-Ordner und ist gesperrt; ein eigener Ordner über „Durchsuchen…“ schaltet die Automatik aus. Der Unterordner wird beim Einlesen (auch mit Unterordnern) nie erneut verarbeitet.

### Dokumentation
- **PDF-Dokumentation** `docs/FotoRahmen_Dokumentation.pdf` (Benutzerhandbuch mit Screenshots und Vorher/Nachher-Beispielen, technische Dokumentation mit automatisch erzeugter Code-Referenz).
- Alle Funktionen und Methoden haben jetzt Docstrings.
- Werkzeuge in `docs/werkzeuge/`: Beispielbilder, Screenshots per automatischem App-Lauf, PDF-Erzeugung.

### Sonstiges
- Code-Prüfung mit ruff und pyright ohne Befund.
- Selbsttest prüft Wasserzeichen und Metadaten (inkl. 16-Bit-TIFF).
- Build bindet den ganzen Ordner `assets` ein.

## 1.5.0 – 2026-11-03

### Neues Design
- **Dunkles Layout im Stil von Capture One:** dunkelgraue Paletten, weiße Schrift, orange Akzente (aktive Tabs, Abschnittstitel, Auswahl, Fortschritt, Start-Schaltfläche).
- Werkzeugleiste oben (Titel, Version, Voreinstellungen, Info), Paletten mit Kopfzeilen in Großbuchstaben (ORDNER, VORSCHAU, BILDER), Werkzeug-Tabs **RAHMEN · TEXT · EFFEKTE · AUSGABE**, Statusleiste unten.
- Eigene dunkle Dialoge statt der hellen Systemdialoge; dunkle Titelleiste unter Windows 10/11 und macOS.
- Das Theme „clam“ wird auf allen Systemen verwendet (die nativen Themes lassen sich nicht dunkel einfärben). Alle Farben zentral in `theme.py`.

### Neue Funktionen
- **Voreinstellungen:** Rahmen, Text, Effekte und Ausgabe als benannte Voreinstellung speichern, laden und löschen. Fünf mitgelieferte Voreinstellungen (Galerie, Schwarzer Rand, Signatur, Social Media 2048 px, PNG mit Schatten).
- **Textzeile/Signatur** im unteren Rand: Text mit Platzhaltern `{name}`, `{datum}`, `{jahr}`, Größe (in % der Randhöhe), Position links/Mitte/rechts, Farbe, eingebaute oder eigene Schrift (.ttf/.otf). Funktioniert auch bei 16-Bit-TIFF.
- **Drag & Drop:** Ordner oder einzelne Bilder ins Fenster ziehen (Paket `tkinterdnd2`).
- **Ausgabegröße begrenzen:** lange Kante des fertigen Bildes (inkl. Rahmen) höchstens N px – nur verkleinern. Auch für 16-Bit-TIFF (hochwertige Skalierung ohne Verlust der Bittiefe).
- **Abgerundete Ecken und Schatten** für PNG und WebP (mit Transparenz).
- **WebP** als Ausgabeformat wählbar.
- Vorschau zeigt Text, Effekte und die tatsächliche Ausgabegröße.

### Technik
- Gemeinsamer Verarbeitungsablauf `compose()` für Ausgabe und Vorschau.
- Selbsttest um Text, Größenbegrenzung, Effekte und WebP erweitert.

## 1.1.0 – 2026-11-03

### Fehlerbehebungen
- **CMYK:** Schwarze Rahmen wurden als C/M/Y 100 % ohne K angelegt (Pillow-Standardumrechnung). Jetzt echtes Schwarz (K 100 %), gilt für CMYK-JPEG und 8/16-Bit-CMYK-TIFF.
- **Zukunftssicherheit:** Bildumwandlung nutzte ein Argument, das laut Pillow-Ankündigung ab Pillow 13 entfällt (`Image.fromarray(..., mode)`). Ersetzt durch `Image.frombytes`. Pillow-Version in `requirements.txt` auf die getestete Hauptversion begrenzt.
- **Windows-Dateinamen:** Reservierte Namen (`CON`, `PRN`, `AUX`, `NUL`, `COM1`…, `LPT1`…) erzeugten ungültige Dateien. Sie erhalten jetzt ein `_`; Namen werden auf 200 Zeichen begrenzt.
- **Während der Verarbeitung** konnten Änderungen an Ordner oder Namensvorlage die Liste neu aufbauen; Statusmeldungen landeten dann ggf. in der falschen Zeile. Alle Bedienelemente sind jetzt während des Laufs gesperrt, der Lauf nutzt eine feste Kopie der Aufgabenliste.
- **Hochauflösende Windows-Bildschirme** (125 %/150 %): Fenster, Spalten und Abstände waren zu klein. Maße werden jetzt mit der Bildschirm-Skalierung multipliziert.
- **Fensterposition** wurde mitgespeichert und konnte nach Monitorwechsel außerhalb des Bildschirms liegen. Es wird nur noch die Größe gespeichert.
- **Beschädigte oder leere Dateien** lieferten englische Pillow-Fehlertexte. Jetzt verständliche deutsche Meldung in der Liste und in der Vorschau.
- **16-Bit-TIFF mit LZW/JPEG-Kompression** ohne verfügbaren Decoder führten zu einem Fehler; jetzt Rückfall auf Pillow.
- **EXIF zu groß für JPEG** (> 64 KB): Speichern schlug fehl bzw. verlor auch das Farbprofil. Jetzt wird nur EXIF weggelassen, das Farbprofil bleibt.
- **Abgebrochene Läufe** konnten temporäre Dateien hinterlassen; diese werden beim nächsten Start im Ausgabe-Ordner entfernt.
- Gespeicherte Einstellungen mit unbekannten Schlüsseln werden ignoriert.

### Neu
- **Info-Dialog** mit Version, Copyright, Idee/Prompt, Umsetzung und Lizenz.
- **„Unten extra“**: zusätzlicher Rand unten am äußeren Rahmen (Galerie-/Passepartout-Look, Platz für Signatur).
- **Animierte WebP** werden Bild für Bild gerahmt (wie animierte GIFs).
- **16-Bit-Graustufen-TIFF → PNG** bleibt 16 Bit.
- Qualitätseinstellung gilt jetzt auch für WebP und HEIC (Beschriftung angepasst).
- Tastenkürzel **Strg+Enter** (macOS: **⌘+Enter**) startet die Verarbeitung.
- Windows-EXE enthält Versions- und Copyright-Angaben (Eigenschaften → Details); macOS-App ebenso (Info.plist).
- Automatischer Build mit **Starttest** der fertigen EXE/App.
- Erweiterter Selbsttest (beschädigte Datei, CMYK-Schwarz, reservierte Namen, unterer Rand, animiertes WebP).
- Vollständige Code- und Entwicklerdokumentation (`docs/ENTWICKLER.md`), Lizenz, Prompt-Export (`PROMPT.md`).

## 1.0.0 – 2026-11-03
- Erste Version: einfacher/doppelter Rahmen, Farbwahl, Pixel/Prozent, Vorschau, Stapelverarbeitung, Umbenennen, JPEG/TIFF (8/16 Bit)/PNG/GIF/HEIC/WebP/BMP/JPEG 2000.
