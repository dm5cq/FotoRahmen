# FotoRahmen für iPhone und iPad

Die iOS-Version von FotoRahmen 2.0 – gleiche Funktionen, gleiches dunkles Design im Stil von Capture One, gleiches Logo.

> © 2026 **Stefan J. Kaiser** · Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026 · Lizenz: GNU GPL v3

## Funktionen (wie Desktop 2.0)

| Bereich | iPhone / iPad |
|---|---|
| **Quelle** | **Fotos** aus der Mediathek (Mehrfachauswahl, Originalnamen wie „IMG_1234.HEIC“), **Ordner** aus der Dateien-App (iCloud Drive, „Auf meinem iPhone“, USB-Stick …, optional mit Unterordnern), einzelne **Dateien**, auf dem iPad zusätzlich **Drag & Drop** |
| **Ziel (automatisch)** | Ordner → Unterordner **„mit Rahmen“** im Ordner · Fotos → neues Album **„mit Rahmen“** · Dateien → Dateien-App › Auf meinem iPhone › FotoRahmen › „mit Rahmen“. Alternativ immer Fotos-Album oder eigener Ordner. **Originale bleiben unverändert.** |
| **RAHMEN** | einfach/doppelt, Pixel oder % der langen Kante, „Unten extra“, Weiß/Schwarz/beliebige Farbe |
| **TEXT** | Textzeile/Signatur im unteren Rand, `{name}` `{datum}` `{jahr}`, Größe, Position, Farbe, 10 Schriften (u. a. Snell Roundhand für Signaturen) |
| **SCHUTZ** | transparentes Copyright-Wasserzeichen (Ecken, Mitte, **diagonal über das ganze Bild**), Deckkraft, Größe, Farbe, Kontrastkante; Urheber/Copyright in den Metadaten (EXIF/TIFF, IPTC, PNG) |
| **EFFEKTE** | abgerundete Ecken, weicher Schatten (PNG) |
| **AUSGABE** | Wie Original, JPEG, PNG, HEIC, TIFF; Qualität; lange Kante begrenzen; Dateinamen-Vorlage `{name}` `{nr}` `{datum}`; vorhandene Dateien nummerieren/überschreiben/überspringen |
| **Bedienung** | Live-Vorschau mit Größe alt → neu, Bilderleiste, Namen einzeln ändern („Namen & Status“), Voreinstellungen (6 mitgeliefert, eigene speichern/löschen), Fortschritt mit Abbrechen, Info mit Copyright |
| **Qualität** | EXIF, GPS, Farbprofil (z. B. Display P3), DPI bleiben erhalten; Hochformat-Drehung wird berücksichtigt; 16 Bit bleibt bei PNG/TIFF erhalten |

**Unterschiede zur Desktop-Version** (Grenzen von iOS): WebP, BMP und JPEG 2000 werden gelesen, aber als JPEG gespeichert (iOS kann diese Formate nicht schreiben). CMYK-Bilder werden in RGB umgewandelt. Animierte GIFs: es wird das erste Bild gerahmt. Eigene Schriftdateien sind nicht möglich – dafür gibt es eine Auswahl der in iOS enthaltenen Schriften.

## App auf das eigene iPhone bringen

Voraussetzungen: ein **Mac mit Xcode 16 oder neuer** (kostenlos im Mac App Store) und ein iPhone/iPad mit **iOS/iPadOS 17 oder neuer**.

1. Ordner `ios/` öffnen und **`FotoRahmen.xcodeproj`** doppelklicken.
2. Links das Projekt **FotoRahmen** wählen → Reiter **Signing & Capabilities** → bei **Team** die eigene Apple-ID auswählen (Xcode › Einstellungen › Accounts › „+“, falls noch keine eingetragen ist).
3. Falls Xcode meldet, die **Bundle-ID** sei vergeben: unter *Bundle Identifier* etwas Eigenes eintragen, z. B. `de.kaiser-burghausen.FotoRahmen2`.
4. iPhone per Kabel anschließen (beim ersten Mal: „Vertrauen“ tippen; am iPhone *Einstellungen › Datenschutz & Sicherheit › Entwicklermodus* einschalten).
5. Oben in Xcode das iPhone als Ziel wählen und **▶ (Run)** drücken.
6. Mit einer kostenlosen Apple-ID: am iPhone *Einstellungen › Allgemein › VPN & Geräteverwaltung* → Entwickler-App vertrauen.

Mit einer kostenlosen Apple-ID läuft die App **7 Tage** und muss dann einfach erneut aus Xcode installiert werden. Mit dem **Apple Developer Program** (99 €/Jahr) gilt sie ein Jahr.

## An Freunde weitergeben (nicht öffentlich im App Store)

| Weg | Voraussetzung | Für Freunde |
|---|---|---|
| **TestFlight** (empfohlen) | Apple Developer Program (99 €/Jahr) | Freunde installieren die App **TestFlight** und tippen auf deinen **Einladungslink**. Bis zu 10 000 Tester, jede Version 90 Tage gültig, kein öffentlicher Store-Eintrag. In Xcode: *Product › Archive › Distribute App › TestFlight & App Store* → in App Store Connect unter TestFlight eine externe Gruppe mit öffentlichem Link anlegen (die erste Version prüft Apple kurz). |
| **Ad-hoc** | Apple Developer Program | Bis zu 100 Geräte je Jahr; UDID der Geräte registrieren, IPA per Link/AirDrop verteilen. |
| **Unlisted App** | Apple Developer Program | Echte App-Store-App, aber nur über einen direkten Link auffindbar (Antrag bei Apple). |
| **Unsignierte IPA + eigene Apple-ID** | nichts | Der GitHub-Build erzeugt `FotoRahmen-iOS-unsigniert.ipa`. Jeder Freund kann sie mit **Sideloadly** oder **AltStore** (Mac/PC) und seiner eigenen kostenlosen Apple-ID installieren – gilt 7 Tage, dann erneuern. |

## Automatischer Build auf GitHub

Der Workflow `.github/workflows/build.yml` baut bei jedem Push zusätzlich die iOS-App:

1. **Prüf-Build für den iOS-Simulator** – zeigt sofort, ob der Code fehlerfrei kompiliert.
2. **Unsignierte IPA** (`FotoRahmen-iOS-unsigniert`) unter *Actions › Artifacts* bzw. im Release bei Tags `v*`.

## Aufbau des Codes

```
ios/
├── FotoRahmen.xcodeproj         Xcode-Projekt (Xcode 16+, Ordner wird automatisch synchronisiert)
├── Support/Info.plist           Dateien-App-Freigabe, Verschlüsselungs-Angabe
└── FotoRahmen/
    ├── FotoRahmenApp.swift      Einstieg (@main), AppInfo (Version, Copyright)
    ├── Model/
    │   ├── FrameSettings.swift  alle Einstellungen, Rahmenschichten, Formate, mitgelieferte Voreinstellungen
    │   ├── ImageItem.swift      Bild in der Liste, Status, Quelle, Ziel, Ergebnis
    │   └── AppModel.swift       App-Logik: Quellen, Ziele, Namensplanung, Vorschau, Stapelverarbeitung
    ├── Core/
    │   ├── FrameRenderer.swift  Zeichnen: Rahmen, Bild, Wasserzeichen, Textzeile, Ecken/Schatten
    │   ├── ImageIOHelpers.swift Laden/Speichern mit Metadaten (EXIF, GPS, IPTC, Copyright)
    │   ├── Naming.swift         Platzhalter, Dateinamen, Zielplanung („mit Rahmen“, _2, _3 …)
    │   └── PhotoLibrary.swift   Fotos-Mediathek: Originalnamen, Album „mit Rahmen“, Speichern
    ├── Views/
    │   ├── Theme.swift          Farben (wie theme.py), Schaltflächen- und Feldstile
    │   ├── Controls.swift       Zahlen-, Farb-, Schalter-, Auswahl- und Textzeilen
    │   ├── ToolTabs.swift       Tabs RAHMEN · TEXT · SCHUTZ · EFFEKTE · AUSGABE
    │   ├── ContentView.swift    Hauptfenster (iPhone untereinander, iPad nebeneinander)
    │   ├── PreviewViews.swift   Vorschau, Bilderleiste, Statusleiste, Namensliste
    │   └── InfoViews.swift      Info (Copyright) und Abschlussfenster
    └── Assets.xcassets          App-Symbol (Orange → Schwarz), Logo, Akzentfarbe
```

**Entsprechungen zur Desktop-Version:** `FrameSettings` ↔ `rahmen_core.FrameSettings`, `FrameRenderer.render` ↔ `compose()`, `Naming.plan` ↔ `plan_jobs()`, `ImageIOHelpers.metadata` ↔ `_exif_with_copyright`/`xmp_packet`, `Theme` ↔ `theme.C`, `AppModel` ↔ `App`.

### Typische Änderungen

| Aufgabe | Wo |
|---|---|
| Neue Rahmen-Option | Feld in `FrameSettings` (+ `CodingKeys` und `init(from:)`), Schicht in `layers()`, Zeile im passenden Tab in `ToolTabs.swift` |
| Neue Schrift | `FontChoice.all` in `FrameRenderer.swift` (PostScript-Name) |
| Neue Wasserzeichen-Position | `WatermarkPosition` + `drawWatermark()` |
| Neue Voreinstellung | `BuiltinPresets.all` in `FrameSettings.swift` |
| Farben | `Theme` in `Theme.swift` (und `AccentColor` im Asset-Katalog) |
| Name des Ausgabe-Ordners/Albums | `Naming.autoOutputName` |
| Version | in Xcode: Target › General › Version (`MARKETING_VERSION`) |
| App-Symbol | `python make_icons.py` im Projektordner erzeugt auch `AppIcon.png` und `Logo.png` neu |

Neue `.swift`-Dateien im Ordner `ios/FotoRahmen/` werden von Xcode automatisch in das Projekt übernommen.
