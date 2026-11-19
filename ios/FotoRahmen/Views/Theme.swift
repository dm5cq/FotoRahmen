// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Dunkles Design im Stil von Capture One – dieselbe Farbpalette wie theme.py der Desktop-Version.
// Farben ändern: nur die Werte in `Theme` anpassen.

import SwiftUI
import UIKit

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
}

enum Theme {
    static let app = Color(hex: 0x1C1C1C)        // Hintergrund / Zwischenräume
    static let panel = Color(hex: 0x262626)      // Paletten
    static let bar = Color(hex: 0x2E2E2E)        // Kopfzeilen, Leisten
    static let input = Color(hex: 0x383838)      // Eingabefelder
    static let button = Color(hex: 0x3A3A3A)
    static let border = Color(hex: 0x454545)
    static let viewer = Color(hex: 0x474747)     // Vorschau (neutralgrau)
    static let fg = Color(hex: 0xECECEC)         // Text (weiß)
    static let fgDim = Color(hex: 0x9B9B9B)      // Nebentext
    static let fgOff = Color(hex: 0x626262)
    static let accent = Color(hex: 0xF28A1E)     // Orange
    static let accentHi = Color(hex: 0xFFA244)
    static let accentDim = Color(hex: 0x5C3A14)
    static let onAccent = Color(hex: 0x1A1A1A)
    static let ok = Color(hex: 0x7CC47F)
    static let err = Color(hex: 0xFF6F61)

    /// UIKit-Elemente (Segmente, Listen) an das dunkle Design anpassen.
    static func configureAppearance() {
        let seg = UISegmentedControl.appearance()
        seg.selectedSegmentTintColor = UIColor(accent)
        seg.backgroundColor = UIColor(input)
        seg.setTitleTextAttributes([.foregroundColor: UIColor(onAccent)], for: .selected)
        seg.setTitleTextAttributes([.foregroundColor: UIColor(fg)], for: .normal)
    }
}

// MARK: - Bausteine

/// Kopfzeile einer Palette (Großbuchstaben, gedämpft) – wie „ORDNER“, „VORSCHAU“ am Computer.
struct PanelHeader<Trailing: View>: View {
    let title: String
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack {
            Text(title.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(Theme.fgDim)
            Spacer()
            trailing()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Theme.bar)
    }
}

extension PanelHeader where Trailing == EmptyView {
    init(_ title: String) {
        self.title = title
        self.trailing = { EmptyView() }
    }
}

/// Orangefarbene Abschnittsüberschrift in den Werkzeug-Tabs.
struct SectionTitle: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(.caption.weight(.bold))
            .foregroundStyle(Theme.accent)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 14)
            .padding(.bottom, 2)
    }
}

/// Grauer Hinweistext.
struct HintText: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.caption2)
            .foregroundStyle(Theme.fgDim)
            .frame(maxWidth: .infinity, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// Orange Hauptschaltfläche („RAHMEN ERSTELLEN“).
struct AccentButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        AccentButtonBody(configuration: configuration)
    }

    private struct AccentButtonBody: View {
        let configuration: ButtonStyleConfiguration
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            configuration.label
                .font(.headline.weight(.bold))
                .foregroundStyle(isEnabled ? Theme.onAccent : Theme.fgOff)
                .padding(.vertical, 12)
                .padding(.horizontal, 22)
                .frame(maxWidth: .infinity)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(isEnabled ? (configuration.isPressed ? Theme.accentHi : Theme.accent) : Theme.accentDim)
                )
        }
    }
}

/// Flache Schaltfläche im dunklen Stil.
struct DarkButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline)
            .foregroundStyle(configuration.isPressed ? Theme.accent : Theme.fg)
            .padding(.vertical, 7)
            .padding(.horizontal, 12)
            .background(RoundedRectangle(cornerRadius: 6).fill(configuration.isPressed ? Theme.border : Theme.button))
    }
}

/// Dunkles Eingabefeld.
struct DarkField: ViewModifier {
    func body(content: Content) -> some View {
        content
            .textFieldStyle(.plain)
            .foregroundStyle(Theme.fg)
            .padding(.vertical, 7)
            .padding(.horizontal, 9)
            .background(RoundedRectangle(cornerRadius: 6).fill(Theme.input))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.border, lineWidth: 0.5))
    }
}

extension View {
    func darkField() -> some View { modifier(DarkField()) }

    /// Tastatur schließen.
    func hideKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
}
