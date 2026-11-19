# Prompt – FotoRahmen

> © 2026 Stefan J. Kaiser · Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 3.–4. November 2026

Diese Datei enthält die ursprünglichen Prompts (unverändert) und einen überarbeiteten Prompt, der alle Anforderungen der Version 2.0 (Desktop und iOS) vollständig beschreibt. Mit dem verbesserten Prompt lässt sich die Anwendung reproduzierbar neu erstellen oder erweitern.

---

## 1. Ursprünglicher Prompt (Version 1.0)

> Ich benötige eine Windows und MacOS App welche eigenständig lauffähig ist. Nur eine EXE unter Windows oder App in MacOS. Die Anwendung soll für Bilder einen Rahmen ergänzen. Es sollen alle Bildformate wie JPG, TIFF, GIF, PNG untersütz werden die bei Fotografen verwendung finden. Die Rahmen sollen entweder ein einfacher schwarzer oder weisser Rahmen sein. Die Breite soll einzustellen sein. Es soll auch die möglichkeit geben z.B. einen kleineren inneren und grösseren äusseren Rahmen um die Bilder zu erstellen. In einer weiteren Option soll ggf. auch die Farbe der Rahmen angegeben werden können,. Es soll ein Input Verzeichnis geben - und ein Ausgabe Verzeichnis. die Bilddateien im Input Verzeichnis werden dabei nicht verändert. Nur im Ausgabeverzeichnis wird der Rahmen um das Bild ergänzt. Es werden in der Stapelverarbeitung alle Bilder nacheinander Bearbeite und im Ausgabeverzeichnis ausgegeben. Der Ausgabenahme kann dabei vor start der Bearbeitung umbenannt werden. Die App soll eine Einfache aber klare gut lesbare Oberfläche haben. Vorschaufunktion der Bilder mit ergänztem Rahmen.

## 2. Folge-Prompt (Version 1.1)

> Validiere und prüfe die Apps auf Fehler - berichtige diese, erstelle eine saubere Programm und Code Dokumentation um auch nachträglich änderungen vornehmen zu können. Ergänze bitte den Copyright Hinweis, Idee und Promt Stefan J. Kaiser, Umsetzung durch Claude Modell und Umsetzungsdatum. Der Code ist öffentlich. Exportiere zusätzlich noch den Promt - ergänze ggf. Verbesserungen und erstelle eine neue Version - erstelle bitte auch die fertigen Programme - also für windows die EXE und MacOS die App damit die sofort lauffähig sind!

## 3. Folge-Prompts (Version 1.5)

> ändere für die GUI das Layout im Style von Capture One - Dark Mode also Dunkler Hintergrund - Schrift in Weiss und Orange. siehe screenshot - passe den Code an und erstelle es als Version 1.5.

(Beigefügt war ein Screenshot der Capture-One-Oberfläche: dunkle Werkzeugleiste, Werkzeug-Tabs mit orange markiertem aktivem Tab.)

> * Mehrere Rahmen-Voreinstellungen speichern und benennen.
> * Textzeile/Signatur im unteren Rand (Schrift, Größe, Position).
> * Bilder per Drag & Drop in das Fenster ziehen.
> * Ausgabegröße begrenzen (z. B. lange Kante 2048 px für Social Media).
> * Abgerundete Ecken oder Schatten (nur für PNG mit Transparenz).
> * Zielformat WebP zur Auswahl hinzufügen.

## 4. Folge-Prompt (Version 2.0)

> Die Vers 2.0 soll auch den Copyright Schutz transparent in das Bild ergänzbar sein. Es n ansprechendes Logo in orange zu no schwarz soll auch unter Windows und Mac OS im taskmanager oder der menüzeile angezeigt werden. Die Anwendung bitte fertig codieren


> Oben unter Windows sollte auch noch das ICON so angezeigt werden! ändere aber nicht die Versionsnummer - es bleibt bei 2.0

> verifiziere den Code auf Fehler - per default soll das Eingabeverzeichnis dann automatisch gleich das Ausgabeverzeichnis mit dem Unterverzeichnis /mit Rahmen sein. erstelle auch eine Dokumentation mit Beispielbildern als PDF. Beschreibe den Code um nachträglich Änderungen vornehmen zu können. fürhre es aus und stelle alles in einer ZIP Datei zum Download bereit!

## 4b. Folge-Prompt (iOS)

> Ich brauche genau diese App auf iOS

---

## 5. Verbesserter Prompt (vollständige Spezifikation für Version 2.0)

```text
Erstelle die Desktop-Anwendung „FotoRahmen“ für Windows und macOS.

ZIEL
Fotografen sollen allen Bildern eines Ordners in einem Durchgang einen Rahmen
hinzufügen können – mit Vorschau, ohne die Originale zu verändern.

AUSLIEFERUNG
- Windows: eine einzige, ohne Installation lauffähige FotoRahmen.exe (64 Bit).
- macOS: FotoRahmen.app für Apple Silicon und für Intel (je als ZIP).
- Öffentlicher Quellcode (Python 3.12, Tkinter/ttk, Pillow, tkinterdnd2) unter der GNU GPL v3.
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
- Ausgabeformat wählbar: wie Original, JPEG, PNG, TIFF, WebP; Qualität 50–100
  für JPEG/WebP/HEIC.
- Option „Lange Kante begrenzen auf N px“ für das fertige Bild inkl. Rahmen
  (nur verkleinern, auch für 16-Bit-TIFF ohne Verlust der Bittiefe).

RAHMEN
- Einfacher Rahmen oder doppelter Rahmen (innerer, direkt am Bild + äußerer).
- Farbe je Rahmen: Weiß, Schwarz oder frei wählbar (Farbwähler).
- Breite in Pixel oder in % der langen Bildkante; Werte je Einheit getrennt merken.
- Option „Unten extra“: zusätzlicher Rand unten am äußeren Rahmen (Galerie-Look).

TEXTZEILE / SIGNATUR
- Text im unteren Rand mit Platzhaltern {name}, {datum}, {jahr}.
- Größe in % der unteren Randhöhe, Position links/Mitte/rechts (bündig mit
  der Bildkante), Farbe, eingebaute Schrift oder eigene .ttf/.otf-Datei.
- Auch bei 16-Bit-TIFF und gedrehten (EXIF-Orientierung) Bildern aufrecht.

COPYRIGHT-SCHUTZ (eigener Tab „SCHUTZ“)
- Sichtbares, transparentes Wasserzeichen im Bild (nicht im Rahmen):
  Text mit Platzhaltern {jahr}, {datum}, {name}; Deckkraft in %; Größe in %
  der kurzen Bildkante; Farbe; optionale Kontrastkante; Position: vier Ecken,
  Mitte oder diagonal (30°) versetzt über das ganze Bild wiederholt.
- Auch für CMYK und 16-Bit-TIFF (Bittiefe bleibt), aufrecht bei EXIF-Drehung.
- Urheber und Copyright in die Metadaten schreiben – Unicode-sicher:
  EXIF Artist/Copyright/XPAuthor, XMP dc:creator/dc:rights/xmpRights:Marked,
  PNG-Textfelder, TIFF-Tags 315/33432/700.

LOGO & SYSTEMINTEGRATION
- Ansprechendes App-Logo mit Verlauf Orange → Schwarz (gerahmtes Foto mit
  Bergsilhouette), per Skript erzeugt (make_icons.py), klar erkennbar ab 16 px.
- Windows: Symbol in EXE, Explorer, Task-Manager, Taskleiste und oben links
  in der Titelleiste aller Fenster (WM_SETICON, DPI-gerecht; eigene AppUserModelID). macOS: Symbol in Dock/Finder (.icns), eigene
  Menüleiste mit „Über FotoRahmen“, Ablage-Befehlen und Tastenkürzeln.
- Logo auch in der Werkzeugleiste der App.

iOS-APP (iPhone/iPad, SwiftUI, iOS 17+)
- Gleicher Funktionsumfang, gleiches Design und Logo wie die Desktop-Version.
- Quellen: Fotos-Mediathek (Originalnamen), Ordner/Dateien aus der Dateien-App,
  Drag & Drop auf dem iPad. Ziel automatisch „mit Rahmen“ (Unterordner, Album
  in Fotos bzw. App-Ordner); alternativ Fotos-Album oder eigener Ordner.
- Formate, die iOS nicht schreiben kann (WebP, BMP, JPEG 2000), als JPEG.
- Xcode-Projekt + GitHub-Prüf-Build + unsignierte IPA; Anleitung zur Weitergabe
  an Freunde ohne öffentlichen App-Store-Eintrag (TestFlight).

EFFEKTE (nur PNG/WebP mit Transparenz)
- Abgerundete Ecken (Radius in % der kurzen Kante, geglättet).
- Weicher Schatten nach rechts unten (Größe in % der langen Kante).
- Hinweis in der Oberfläche, wenn das gewählte Format keine Effekte erlaubt.

VOREINSTELLUNGEN
- Rahmen, Text, Effekte und Ausgabeformat als benannte Voreinstellung
  speichern, laden, überschreiben (mit Rückfrage), löschen.
- Beim Laden zuerst alle Werte auf Standard setzen (keine Reste der
  vorherigen Voreinstellung).
- Mitgeliefert: Galerie (Linie + Weiß), Schwarzer Rand schmal, Signatur unten,
  Social Media 2048 px, Copyright-Schutz Web, PNG mit Schatten.

ORDNER & STAPELVERARBEITUNG
- Eingabe- und Ausgabe-Ordner wählbar; beide müssen verschieden sein.
- Drag & Drop: einen Ordner (wird Eingabe-Ordner) oder einzelne Bilder (nur
  diese werden verarbeitet) ins Fenster ziehen.
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

OBERFLÄCHE (Dark Mode im Stil von Capture One)
- Dunkle Paletten (#1c1c1c / #262626 / #2e2e2e), Schrift weiß, Akzentfarbe
  Orange (#f28a1e) für aktiven Tab, Abschnittstitel, Auswahl, Fortschritt und
  die Hauptschaltfläche „RAHMEN ERSTELLEN“. Gleiche Optik unter Windows und
  macOS (ttk-Theme „clam“), dunkle Titelleiste, eigene dunkle Dialoge.
- Aufbau: Werkzeugleiste (Titel, Version, Voreinstellungen, Info) · Palette
  ORDNER · links Werkzeug-Tabs RAHMEN | TEXT | EFFEKTE | AUSGABE · rechts
  VORSCHAU und BILDER (Original | Ausgabedatei | Status) · Statusleiste.
  Tabs: RAHMEN | TEXT | SCHUTZ | EFFEKTE | AUSGABE.
- Kopfzeilen der Paletten in Großbuchstaben, Nebentexte gedämpft grau.
- Einfach, klar, gut lesbar, Deutsch; scharf bei Windows-Skalierung 125–200 %.
- Live-Vorschau des gewählten Bildes mit maßstabsgetreuem Rahmen, Text und
  Effekten (dünne Linien mindestens 1 px) und Anzeige „alte → neue Größe“.
- Während der Verarbeitung alle Eingaben sperren.
- Tastenkürzel Strg+Enter / ⌘+Enter = Start.
- Einstellungen und Fenstergröße beim Beenden speichern.
- „Info“-Dialog mit Version, Copyright, Idee/Prompt, Umsetzung, Lizenz.

COPYRIGHT (in jeder Quelldatei, README, Info-Dialog, EXE-Eigenschaften, App-Info)
© 2026 Stefan J. Kaiser – Idee und Prompt: Stefan J. Kaiser –
Umsetzung: Claude (Modellname) – Umsetzungsdatum.

CODE & DOKUMENTATION
- Kern (Bildverarbeitung) strikt getrennt von der Oberfläche; ein gemeinsamer
  Ablauf (compose) für Ausgabe und Vorschau.
- Alle Farben/Styles zentral in theme.py.
- Versionsnummer an genau einer Stelle (app_info.py).
- Docstrings in allen Modulen/Funktionen.
- README (Benutzer), docs/ENTWICKLER.md (Architektur, Code-Referenz,
  „typische Änderungen Schritt für Schritt“, Testen, Bauen, Veröffentlichen,
  bekannte Grenzen, Fehlersuche), CHANGELOG.md, LICENSE, PROMPT.md.
- selftest.py: alle Eingabeformate × alle Ausgabeformate, Endgrößen,
  Originale byte-gleich, beschädigte Datei, CMYK-Schwarz, Dateinamen,
  Text, Größenbegrenzung (exakte Endgröße), Effekte, WebP, Wasserzeichen und
  Copyright-Metadaten (auch 16-Bit-TIFF).

VORGEHEN
Erst Kern bauen und mit Testbildern prüfen, dann Oberfläche, dann
Build-Pipeline. Am Ende Grenzfälle testen (beschädigte Dateien, 1-Bit, Palette
mit Transparenz, 16-Bit-Grau/RGB/RGBA/CMYK, Float-TIFF, planares und
mehrseitiges TIFF, animiertes GIF/WebP, Unicode-Dateinamen,
EXIF-Orientierung 6).
```

---

## 6. Ideen für spätere Versionen
- Mehrere Textzeilen bzw. EXIF-Daten (Kamera, Objektiv, Blende, Zeit, ISO) als Platzhalter.
- Rahmen mit Seitenverhältnis (z. B. Bild mittig auf quadratischer Fläche für Instagram).
- Eigenes Logo-PNG als Wasserzeichen (statt Text).
- Vorher/Nachher-Umschalter in der Vorschau, Zoom auf 100 %.
- Voreinstellungen exportieren/importieren (Datei weitergeben).
- Signierte und notarisierte Programme (keine Sicherheitswarnung).
