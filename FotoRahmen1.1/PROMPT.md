# Prompt – FotoRahmen

> © 2026 Stefan J. Kaiser · Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 3. November 2026

Diese Datei enthält die ursprünglichen Prompts (unverändert) und einen überarbeiteten Prompt, der alle Anforderungen der Version 1.1 vollständig beschreibt. Mit dem verbesserten Prompt lässt sich die Anwendung reproduzierbar neu erstellen oder erweitern.

---

## 1. Ursprünglicher Prompt (Version 1.0)

> Ich benötige eine Windows und MacOS App welche eigenständig lauffähig ist. Nur eine EXE unter Windows oder App in MacOS. Die Anwendung soll für Bilder einen Rahmen ergänzen. Es sollen alle Bildformate wie JPG, TIFF, GIF, PNG untersütz werden die bei Fotografen verwendung finden. Die Rahmen sollen entweder ein einfacher schwarzer oder weisser Rahmen sein. Die Breite soll einzustellen sein. Es soll auch die möglichkeit geben z.B. einen kleineren inneren und grösseren äusseren Rahmen um die Bilder zu erstellen. In einer weiteren Option soll ggf. auch die Farbe der Rahmen angegeben werden können,. Es soll ein Input Verzeichnis geben - und ein Ausgabe Verzeichnis. die Bilddateien im Input Verzeichnis werden dabei nicht verändert. Nur im Ausgabeverzeichnis wird der Rahmen um das Bild ergänzt. Es werden in der Stapelverarbeitung alle Bilder nacheinander Bearbeite und im Ausgabeverzeichnis ausgegeben. Der Ausgabenahme kann dabei vor start der Bearbeitung umbenannt werden. Die App soll eine Einfache aber klare gut lesbare Oberfläche haben. Vorschaufunktion der Bilder mit ergänztem Rahmen.

## 2. Folge-Prompt (Version 1.1)

> Validiere und prüfe die Apps auf Fehler - berichtige diese, erstelle eine saubere Programm und Code Dokumentation um auch nachträglich änderungen vornehmen zu können. Ergänze bitte den Copyright Hinweis, Idee und Promt Stefan J. Kaiser, Umsetzung durch Claude Modell und Umsetzungsdatum. Der Code ist öffentlich. Exportiere zusätzlich noch den Promt - ergänze ggf. Verbesserungen und erstelle eine neue Version - erstelle bitte auch die fertigen Programme - also für windows die EXE und MacOS die App damit die sofort lauffähig sind!

---

## 3. Verbesserter Prompt (vollständige Spezifikation für Version 1.1)

```text
Erstelle die Desktop-Anwendung „FotoRahmen“ für Windows und macOS.

ZIEL
Fotografen sollen allen Bildern eines Ordners in einem Durchgang einen Rahmen
hinzufügen können – mit Vorschau, ohne die Originale zu verändern.

AUSLIEFERUNG
- Windows: eine einzige, ohne Installation lauffähige FotoRahmen.exe (64 Bit).
- macOS: FotoRahmen.app für Apple Silicon und für Intel (je als ZIP).
- Öffentlicher Quellcode (Python 3.12, Tkinter/ttk, Pillow) unter MIT-Lizenz.
- Automatischer Build über GitHub Actions inkl. Selbsttest und Starttest;
  bei Git-Tag v* ein Release mit allen Programmen.
- Programme ohne kostenpflichtige Signatur: Anleitung für den ersten Start
  (SmartScreen bzw. Gatekeeper) in die README.

BILDFORMATE (Lesen)
JPEG, TIFF (8 und 16 Bit, Graustufen/RGB/RGBA/CMYK, auch planar und
komprimiert), PNG (inkl. Transparenz und 16 Bit), GIF und WebP (auch animiert –
jedes Einzelbild rahmen), HEIC/HEIF, BMP, JPEG 2000.
RAW wird nicht unterstützt (Hinweis in der Doku).

QUALITÄT
- Bittiefe, Farbraum (CMYK bleibt CMYK, Schwarz = reines K 100 %),
  ICC-Farbprofil, EXIF und DPI übernehmen, soweit das Zielformat es erlaubt.
- 16-Bit-TIFF → TIFF verlustfrei in 16 Bit.
- EXIF-Orientierung berücksichtigen (Hochformatfotos richtig herum rahmen).
- Ausgabeformat wählbar: wie Original, JPEG, PNG, TIFF; Qualität 50–100
  für JPEG/WebP/HEIC.

RAHMEN
- Einfacher Rahmen oder doppelter Rahmen (innerer, direkt am Bild + äußerer).
- Farbe je Rahmen: Weiß, Schwarz oder frei wählbar (Farbwähler).
- Breite in Pixel oder in % der langen Bildkante; Werte je Einheit getrennt merken.
- Option „Unten extra“: zusätzlicher Rand unten am äußeren Rahmen (Galerie-Look).

ORDNER & STAPELVERARBEITUNG
- Eingabe- und Ausgabe-Ordner wählbar; beide müssen verschieden sein.
- Originale werden nie verändert: nur lesen, Ausgabe zuerst als temporäre
  Datei, dann umbenennen; Ziel darf nie eine Quelldatei sein.
- Optional Unterordner einbeziehen (Struktur im Ausgabe-Ordner nachbilden;
  liegt der Ausgabe-Ordner im Eingabe-Ordner, wird er ausgelassen).
- Verarbeitung im Hintergrund mit Fortschritt, Status je Datei und Abbrechen.
- Beschädigte/leere Dateien: verständliche Fehlermeldung, Lauf geht weiter.

DATEINAMEN
- Vorlage mit Platzhaltern {name}, {nr} (001, 002 …), {datum} (JJJJ-MM-TT),
  Standard „{name}_rahmen“.
- Vor dem Start jede Ausgabedatei einzeln umbenennbar (Doppelklick/F2 in der
  Liste, Enter/Esc), eigene Namen hervorheben, zurücksetzbar.
- Ungültige Zeichen und reservierte Windows-Namen (CON, PRN, AUX, NUL,
  COM1–9, LPT1–9) bereinigen.
- Wenn die Datei existiert: Nummer anhängen (Standard) / überschreiben
  (mit Rückfrage) / überspringen. Doppelte Namen im Stapel immer nummerieren.

OBERFLÄCHE
- Einfach, klar, gut lesbar, Deutsch; native Optik; scharf bei
  Windows-Skalierung 125–200 %; unter macOS helles Erscheinungsbild.
- Links Einstellungen (Rahmen, Ausgabe), rechts große Vorschau und Dateiliste
  (Original | Ausgabedatei | Status).
- Live-Vorschau des gewählten Bildes mit maßstabsgetreuem Rahmen
  (dünne Linien mindestens 1 px) und Anzeige „alte Größe → neue Größe“.
- Während der Verarbeitung alle Eingaben sperren.
- Tastenkürzel Strg+Enter / ⌘+Enter = Start.
- Einstellungen und Fenstergröße beim Beenden speichern.
- „Info“-Dialog mit Version, Copyright, Idee/Prompt, Umsetzung, Lizenz.

COPYRIGHT (in jeder Quelldatei, README, Info-Dialog, EXE-Eigenschaften, App-Info)
© 2026 Stefan J. Kaiser – Idee und Prompt: Stefan J. Kaiser –
Umsetzung: Claude (Modellname) – Umsetzungsdatum.

CODE & DOKUMENTATION
- Kern (Bildverarbeitung) strikt getrennt von der Oberfläche.
- Versionsnummer an genau einer Stelle (app_info.py).
- Docstrings in allen Modulen/Funktionen.
- README (Benutzer), docs/ENTWICKLER.md (Architektur, Code-Referenz,
  „typische Änderungen Schritt für Schritt“, Testen, Bauen, Veröffentlichen,
  bekannte Grenzen, Fehlersuche), CHANGELOG.md, LICENSE, PROMPT.md.
- selftest.py: alle Eingabeformate × alle Ausgabeformate, Endgrößen,
  Originale byte-gleich, beschädigte Datei, CMYK-Schwarz, Dateinamen.

VORGEHEN
Erst Kern bauen und mit Testbildern prüfen, dann Oberfläche, dann
Build-Pipeline. Am Ende Grenzfälle testen (beschädigte Dateien, 1-Bit, Palette
mit Transparenz, 16-Bit-Grau/RGB/RGBA/CMYK, Float-TIFF, planares und
mehrseitiges TIFF, animiertes GIF/WebP, Unicode-Dateinamen,
EXIF-Orientierung 6).
```

---

## 4. Ideen für spätere Versionen
- Mehrere Rahmen-Voreinstellungen speichern und benennen.
- Textzeile/Signatur im unteren Rand (Schrift, Größe, Position).
- Bilder per Drag & Drop in das Fenster ziehen.
- Ausgabegröße begrenzen (z. B. lange Kante 2048 px für Social Media).
- Abgerundete Ecken oder Schatten (nur für PNG mit Transparenz).
- Zielformat WebP zur Auswahl hinzufügen.
- Signierte und notarisierte Programme (keine Sicherheitswarnung).
