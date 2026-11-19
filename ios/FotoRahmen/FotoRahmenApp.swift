// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Rahmen und Copyright-Schutz für Fotos
// Copyright (c) 2026 Stefan J. Kaiser
// Idee und Prompt: Stefan J. Kaiser
// Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// Lizenz: GNU GPL v3 – siehe Datei LICENSE
// -----------------------------------------------------------------------------
//
// Einstiegspunkt der App. Aufbau des Projekts: siehe ios/README.md.

import SwiftUI

/// Zentrale Programm-Informationen (entspricht app_info.py der Desktop-Version).
enum AppInfo {
    static var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "2.0.0"
    }
    static let author = "Stefan J. Kaiser"
    static let copyright = "© 2026 Stefan J. Kaiser"
    static let idea = "Idee und Prompt: Stefan J. Kaiser"
    static let implementation = "Umsetzung: Claude Opus 5.5 (Anthropic), 3.–6. November 2026"
    static let license = "GNU General Public License v3 (Open Source)"
}

@main
struct FotoRahmenApp: App {
    @StateObject private var model = AppModel()

    init() {
        Theme.configureAppearance()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .preferredColorScheme(.dark)
                .tint(Theme.accent)
        }
    }
}
