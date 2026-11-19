# Änderungsprotokoll

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
- Vollständige Code- und Entwicklerdokumentation (`docs/ENTWICKLER.md`), Lizenz (MIT), Prompt-Export (`PROMPT.md`).

## 1.0.0 – 2026-11-03
- Erste Version: einfacher/doppelter Rahmen, Farbwahl, Pixel/Prozent, Vorschau, Stapelverarbeitung, Umbenennen, JPEG/TIFF (8/16 Bit)/PNG/GIF/HEIC/WebP/BMP/JPEG 2000.
