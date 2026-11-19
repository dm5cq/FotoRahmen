// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Wiederverwendbare Bedienelemente für die Werkzeug-Tabs.

import SwiftUI

/// Zeile „Beschriftung  [Zahl] Einheit  [– +]“.
struct NumberRow: View {
    let label: String
    @Binding var value: Double
    var unit: String = ""
    var range: ClosedRange<Double> = 0...10_000
    var step: Double = 1

    var body: some View {
        HStack(spacing: 8) {
            Text(label)
                .foregroundStyle(Theme.fg)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 4)
            TextField("", value: $value, format: .number.precision(.fractionLength(0...2)))
                .keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing)
                .frame(width: 62)
                .darkField()
            Text(unit)
                .font(.caption)
                .foregroundStyle(Theme.fgDim)
                .frame(width: 24, alignment: .leading)
            Stepper("", value: clamped, in: range, step: step)
                .labelsHidden()
        }
    }

    /// Werte außerhalb des Bereichs (per Tastatur) werden beim Antippen von –/+ eingefangen.
    private var clamped: Binding<Double> {
        Binding(get: { min(max(value, range.lowerBound), range.upperBound) },
                set: { value = min(max($0, range.lowerBound), range.upperBound) })
    }
}

/// Farbwahl: Weiß / Schwarz / eigene Farbe (System-Farbwähler).
struct ColorRow: View {
    let label: String
    @Binding var color: RGBColor

    var body: some View {
        HStack(spacing: 8) {
            Text(label).foregroundStyle(Theme.fg)
            Spacer(minLength: 4)
            chip("Weiß", .white)
            chip("Schwarz", .black)
            ColorPicker("", selection: Binding(get: { color.swiftUIColor }, set: { color = RGBColor($0) }),
                        supportsOpacity: false)
                .labelsHidden()
                .frame(width: 36)
        }
    }

    private func chip(_ title: String, _ value: RGBColor) -> some View {
        let selected = color == value
        return Button { color = value } label: {
            Text(title)
                .font(.caption.weight(selected ? .bold : .regular))
                .foregroundStyle(selected ? Theme.accent : Theme.fg)
                .padding(.vertical, 6)
                .padding(.horizontal, 10)
                .background(RoundedRectangle(cornerRadius: 6).fill(selected ? Theme.accentDim : Theme.button))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(selected ? Theme.accent : Theme.border,
                                                                   lineWidth: 0.8))
        }
        .buttonStyle(.plain)
    }
}

/// Schalter mit orangem Akzent.
struct ToggleRow: View {
    let label: String
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) { Text(label).foregroundStyle(Theme.fg) }
            .tint(Theme.accent)
    }
}

/// Auswahlmenü in einer Zeile.
struct MenuRow<Option: Hashable>: View {
    let label: String
    @Binding var selection: Option
    let options: [Option]
    let title: (Option) -> String

    var body: some View {
        HStack {
            Text(label).foregroundStyle(Theme.fg)
            Spacer(minLength: 4)
            Picker(label, selection: $selection) {
                ForEach(options, id: \.self) { option in
                    Text(title(option)).tag(option)
                }
            }
            .pickerStyle(.menu)
            .tint(Theme.accent)
        }
    }
}

/// Textfeld mit Beschriftung.
struct TextRow: View {
    let label: String
    @Binding var text: String
    var placeholder: String = ""

    var body: some View {
        HStack(spacing: 8) {
            Text(label).foregroundStyle(Theme.fg)
            TextField(placeholder, text: $text)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .darkField()
        }
    }
}
