// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Info-Fenster (Copyright) und Abschlussfenster nach der Stapelverarbeitung.

import SwiftUI

/// „Über FotoRahmen“ – Version, Copyright, Idee/Prompt, Umsetzung, Lizenz.
struct AboutView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 10)
            Image("Logo")
                .resizable()
                .frame(width: 110, height: 110)
                .shadow(color: .black.opacity(0.5), radius: 10, y: 4)
            Text("FotoRahmen")
                .font(.largeTitle.weight(.bold))
                .foregroundStyle(Theme.fg)
            Text("Version \(AppInfo.version)")
                .font(.headline)
                .foregroundStyle(Theme.accent)
            Text("Rahmen und Copyright-Schutz für Fotos")
                .font(.subheadline)
                .foregroundStyle(Theme.fgDim)
            VStack(spacing: 4) {
                Text(AppInfo.copyright)
                Text(AppInfo.idea)
                Text(AppInfo.implementation)
            }
            .font(.footnote)
            .foregroundStyle(Theme.fg)
            .multilineTextAlignment(.center)
            .padding(.top, 8)
            Text("Lizenz: \(AppInfo.license) – der Quellcode ist öffentlich.")
                .font(.caption)
                .foregroundStyle(Theme.fgDim)
                .multilineTextAlignment(.center)
            Spacer()
            Button("Schließen") { dismiss() }
                .buttonStyle(AccentButtonStyle())
                .frame(maxWidth: 280)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.panel.ignoresSafeArea())
        .presentationDetents([.medium, .large])
        .preferredColorScheme(.dark)
    }
}

/// Zusammenfassung nach dem Stapellauf mit „Öffnen“ und „Teilen“.
struct ResultView: View {
    let result: BatchResult
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: result.failed > 0 ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                .font(.system(size: 52))
                .foregroundStyle(result.failed > 0 ? Theme.err : Theme.accent)
                .padding(.top, 20)
            Text(result.summary)
                .font(.headline)
                .foregroundStyle(Theme.fg)
                .multilineTextAlignment(.center)
            if result.ok > 0 {
                Label(result.destinationText, systemImage: result.savedToPhotos ? "photo.on.rectangle" : "folder")
                    .font(.subheadline)
                    .foregroundStyle(Theme.fgDim)
                    .multilineTextAlignment(.center)
            }
            if result.failed > 0 {
                Text("Details zu den Fehlern stehen in der Liste „Namen & Status“.")
                    .font(.caption)
                    .foregroundStyle(Theme.fgDim)
            }
            Spacer()
            VStack(spacing: 10) {
                if result.ok > 0 {
                    Button {
                        model.openDestination(result)
                    } label: {
                        Label(result.savedToPhotos ? "In Fotos öffnen" : "In Dateien öffnen",
                              systemImage: "arrow.up.forward.app")
                    }
                    .buttonStyle(AccentButtonStyle())
                    if !result.outputFiles.isEmpty {
                        ShareLink(items: result.outputFiles) {
                            Label("Teilen …", systemImage: "square.and.arrow.up")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(DarkButtonStyle())
                    }
                }
                Button("Schließen") { dismiss() }
                    .buttonStyle(DarkButtonStyle())
            }
            .frame(maxWidth: 360)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.panel.ignoresSafeArea())
        .presentationDetents([.medium])
        .preferredColorScheme(.dark)
    }
}
