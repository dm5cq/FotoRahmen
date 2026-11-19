// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Werkzeug-Tabs RAHMEN · TEXT · SCHUTZ · EFFEKTE · AUSGABE (wie in der Desktop-Version).

import SwiftUI

enum ToolTab: String, CaseIterable, Identifiable {
    case frame = "Rahmen", text = "Text", protect = "Schutz", effects = "Effekte", output = "Ausgabe"
    var id: String { rawValue }
}

/// Tab-Leiste im Stil der Capture-One-Werkzeug-Tabs: aktiver Tab orange mit Unterstrich.
struct ToolTabBar: View {
    @Binding var selection: ToolTab

    var body: some View {
        HStack(spacing: 0) {
            ForEach(ToolTab.allCases) { tab in
                Button { selection = tab } label: {
                    VStack(spacing: 5) {
                        Text(tab.rawValue.uppercased())
                            .font(.caption.weight(.bold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                            .foregroundStyle(selection == tab ? Theme.accent : Theme.fgDim)
                        Rectangle()
                            .fill(selection == tab ? Theme.accent : Color.clear)
                            .frame(height: 2)
                    }
                    .padding(.top, 9)
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .background(Theme.bar)
    }
}

/// Inhalt des gewählten Tabs.
struct ToolTabContent: View {
    let tab: ToolTab

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            switch tab {
            case .frame: FrameTab()
            case .text: TextTab()
            case .protect: ProtectTab()
            case .effects: EffectsTab()
            case .output: OutputTab()
            }
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 18)
    }
}

// MARK: - RAHMEN

struct FrameTab: View {
    @EnvironmentObject private var model: AppModel

    private var unit: WidthUnit { model.settings.unit }
    private var range: ClosedRange<Double> { unit == .pct ? 0...50 : 0...10_000 }
    private var step: Double { unit == .pct ? 0.1 : 1 }

    var body: some View {
        Group {
            SectionTitle("Art")
            Picker("Art", selection: $model.settings.double) {
                Text("Einfach").tag(false)
                Text("Doppelt (innen + außen)").tag(true)
            }
            .pickerStyle(.segmented)

            SectionTitle("Breite in")
            Picker("Einheit", selection: $model.settings.unit) {
                ForEach(WidthUnit.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            HintText("Prozent der langen Bildkante: gleich wirkender Rahmen bei unterschiedlich großen Bildern.")
        }
        Group {
            SectionTitle(model.settings.double ? "Äußerer Rahmen" : "Rahmen")
            NumberRow(label: "Breite", value: $model.settings.outerWidth, unit: unit.short, range: range, step: step)
            NumberRow(label: "Unten extra", value: $model.settings.bottomExtra, unit: unit.short, range: range, step: step)
            ColorRow(label: "Farbe", color: $model.settings.outerColor)
            HintText("„Unten extra“ verbreitert den unteren Rand – Galerie-Look und Platz für die Textzeile.")
        }
        if model.settings.double {
            SectionTitle("Innerer Rahmen (direkt am Bild)")
            NumberRow(label: "Breite", value: $model.settings.innerWidth, unit: unit.short, range: range, step: step)
            ColorRow(label: "Farbe", color: $model.settings.innerColor)
        }
    }
}

// MARK: - TEXT

struct TextTab: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            SectionTitle("Textzeile / Signatur")
            TextRow(label: "Text", text: $model.settings.text, placeholder: "z. B. © {jahr} Name")
            HintText("Platzhalter: {name} = Dateiname, {datum} = heute, {jahr} = Jahr. Der Text steht im unteren "
                + "Rand – dafür im Tab RAHMEN „Unten extra“ vergrößern (z. B. 5 %).")
            NumberRow(label: "Größe", value: $model.settings.textSize, unit: "%", range: 5...100, step: 5)
            HintText("Schrifthöhe in % der unteren Randhöhe.")
            HStack {
                Text("Position").foregroundStyle(Theme.fg)
                Spacer()
                Picker("Position", selection: $model.settings.textPos) {
                    ForEach(TextPosition.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 230)
            }
            ColorRow(label: "Farbe", color: $model.settings.textColor)
        }
        SectionTitle("Schrift")
        MenuRow(label: "Schrift", selection: $model.settings.textFont, options: FontChoice.all.map(\.id),
            title: { id in FontChoice.all.first { $0.id == id }?.label ?? id })
        HintText("Gilt auch für das Wasserzeichen im Tab SCHUTZ.")
    }
}

// MARK: - SCHUTZ

struct ProtectTab: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            SectionTitle("Sichtbares Wasserzeichen")
            ToggleRow(label: "Transparentes Copyright ins Bild setzen", isOn: $model.settings.wmOn)
            TextRow(label: "Text", text: $model.settings.wmText, placeholder: "© {jahr} Vorname Nachname")
            HintText("Platzhalter: {jahr}, {datum}, {name}.")
            NumberRow(label: "Deckkraft", value: $model.settings.wmOpacity, unit: "%", range: 5...100, step: 5)
            NumberRow(label: "Größe", value: $model.settings.wmSize, unit: "%", range: 1...30, step: 0.5)
            HintText("Deckkraft 20–40 % wirkt dezent. Größe in % der kurzen Bildkante.")
            MenuRow(label: "Position", selection: $model.settings.wmPos, options: WatermarkPosition.allCases,
                title: { $0.label })
            ColorRow(label: "Farbe", color: $model.settings.wmColor)
            ToggleRow(label: "Kontrastkante (überall lesbar)", isOn: $model.settings.wmOutline)
            HintText("„Diagonal über das ganze Bild“ schützt am besten – das Wasserzeichen lässt sich nicht "
                + "einfach wegschneiden.")
        }
        Group {
            SectionTitle("Copyright in den Metadaten")
            ToggleRow(label: "Urheber und Copyright in die Datei schreiben", isOn: $model.settings.metaOn)
            TextRow(label: "Urheber", text: $model.settings.metaAuthor, placeholder: "Vorname Nachname")
            TextRow(label: "Copyright", text: $model.settings.metaCopyright, placeholder: "© {jahr} Vorname Nachname")
            HintText("Wird als EXIF/TIFF (Artist, Copyright), IPTC (Urheber, Copyright-Vermerk) bzw. PNG-Feld "
                + "gespeichert – sichtbar z. B. in Lightroom, Capture One und Fotos (Info).")
        }
    }
}

// MARK: - EFFEKTE

struct EffectsTab: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        SectionTitle("Abgerundete Ecken")
        NumberRow(label: "Radius", value: $model.settings.cornerRadius, unit: "%", range: 0...50, step: 0.5)
        HintText("In % der kurzen Kante.")
        SectionTitle("Schatten")
        NumberRow(label: "Größe", value: $model.settings.shadow, unit: "%", range: 0...25, step: 0.5)
        HintText("In % der langen Kante (0 = aus). Effekte brauchen Transparenz und werden nur bei Ausgabe "
            + "als PNG angewendet (Tab AUSGABE).")
        if !model.effectsHint.isEmpty {
            Text(model.effectsHint)
                .font(.caption.weight(.bold))
                .foregroundStyle(Theme.accent)
                .padding(.top, 4)
        }
    }
}

// MARK: - AUSGABE

struct OutputTab: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            SectionTitle("Ziel")
            MenuRow(label: "Speichern in", selection: $model.outputTarget, options: OutputTarget.allCases,
                title: { $0.label })
            HStack(alignment: .top) {
                Image(systemName: model.destinationFolder == nil ? "photo.on.rectangle" : "folder")
                    .foregroundStyle(Theme.accent)
                Text(model.destinationDescription)
                    .font(.caption)
                    .foregroundStyle(Theme.fg)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if model.outputTarget == .folder {
                Button { model.showOutputFolderPicker = true } label: {
                    Label(model.customFolder == nil ? "Ordner wählen …" : "Anderen Ordner wählen …",
                    systemImage: "folder.badge.plus")
                }
                .buttonStyle(DarkButtonStyle())
            }
            HintText("Automatisch: Ordner → Unterordner „mit Rahmen“, Fotos → Album „mit Rahmen“, einzelne "
                + "Dateien → App-Ordner „mit Rahmen“ (Dateien-App › Auf meinem iPhone › FotoRahmen). "
                + "Die Originale bleiben immer unverändert.")
        }
        Group {
            SectionTitle("Format")
            MenuRow(label: "Dateiformat", selection: $model.settings.format, options: OutputFormat.allCases,
                title: { $0.label })
            NumberRow(label: "Qualität", value: $model.settings.quality, unit: "", range: 50...100, step: 1)
            HintText("Qualität gilt für JPEG und HEIC (empfohlen 90–95). „Wie Original“: WebP, BMP und "
                + "JPEG 2000 werden als JPEG gespeichert.")

            SectionTitle("Größe")
            ToggleRow(label: "Lange Kante begrenzen", isOn: $model.settings.limitOn)
            if model.settings.limitOn {
                NumberRow(label: "Höchstens", value: $model.settings.maxEdge, unit: "px", range: 100...20_000, step: 64)
            }
            HintText("Gilt für das fertige Bild inklusive Rahmen – nur verkleinern (z. B. 2048 px für Social Media).")
        }
        Group {
            SectionTitle("Dateiname")
            TextRow(label: "Vorlage", text: $model.settings.template, placeholder: "{name}_rahmen")
            HintText("Platzhalter: {name} = Originalname, {nr} = 001, 002 …, {datum} = heute. Einzelne Namen in "
                + "der Bilderliste ändern.")
            MenuRow(label: "Datei existiert", selection: $model.settings.conflict, options: ConflictMode.allCases,
                title: { $0.label })
        }

        if case .folder = model.source {
            SectionTitle("Ordner")
            ToggleRow(label: "Unterordner einbeziehen", isOn: $model.includeSubfolders)
            HintText("Die Ordnerstruktur wird im Ausgabe-Ordner übernommen; „mit Rahmen“ wird nie erneut verarbeitet.")
        }
    }
}
