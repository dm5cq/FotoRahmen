// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Hauptfenster. Aufbau wie die Desktop-Version:
//
//   Kopfleiste: Logo · FotoRahmen 2.0 · Voreinstellungen · Info
//   QUELLE: Fotos | Ordner | Dateien
//   VORSCHAU (+ Bilderleiste)            ← iPad: rechts, Werkzeug-Tabs links
//   RAHMEN | TEXT | SCHUTZ | EFFEKTE | AUSGABE
//   Statusleiste: Fortschritt · RAHMEN ERSTELLEN

import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// Welche Auswahl die Dateien-App gerade anzeigt.
enum ImporterMode {
    case folder, files, outputFolder

    var types: [UTType] {
        switch self {
        case .folder, .outputFolder: return [.folder]
        case .files: return [.image]
        }
    }
}

struct ContentView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.horizontalSizeClass) private var sizeClass

    @State private var tab: ToolTab = .frame
    @State private var pickerItems: [PhotosPickerItem] = []
    @State private var importerMode: ImporterMode = .folder
    @State private var showImporter = false
    @State private var showAbout = false
    @State private var showList = false
    @State private var showSavePreset = false
    @State private var newPresetName = ""
    @State private var presetToDelete: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                header
                if sizeClass == .regular {
                    HStack(spacing: 0) {
                        VStack(spacing: 0) {
                            ToolTabBar(selection: $tab)
                            toolScroll
                        }
                        .frame(width: 400)
                        .background(Theme.panel)
                        Rectangle().fill(Theme.app).frame(width: 6)
                        VStack(spacing: 0) {
                            sourceBar
                            PreviewPanel()
                            ThumbnailStrip(showList: $showList)
                        }
                    }
                } else {
                    sourceBar
                    PreviewPanel()
                        .frame(maxHeight: .infinity)
                        .layoutPriority(1)
                    ThumbnailStrip(showList: $showList)
                    ToolTabBar(selection: $tab)
                    toolScroll
                        .frame(maxHeight: .infinity)
                        .layoutPriority(1)
                }
                BottomBar()
            }
            .background(Theme.app.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Fertig") { hideKeyboard() }
                }
            }
        }
        .onChange(of: pickerItems) { _, newItems in
            guard !newItems.isEmpty else { return }
            let picks = newItems
            pickerItems = []
            Task { await model.addPhotos(picks) }
        }
        .onChange(of: model.showOutputFolderPicker) { _, show in
            if show {
                model.showOutputFolderPicker = false
                importerMode = .outputFolder
                showImporter = true
            }
        }
        .fileImporter(isPresented: $showImporter, allowedContentTypes: importerMode.types,
                      allowsMultipleSelection: importerMode == .files) { result in
            guard case .success(let urls) = result, !urls.isEmpty else { return }
            switch importerMode {
            case .folder: model.addFolder(urls[0])
            case .files: model.addFiles(urls)
            case .outputFolder: model.setCustomFolder(urls[0])
            }
        }
        .onDrop(of: [.image], isTargeted: nil) { providers in model.handleDrop(providers) }
        .sheet(isPresented: $showAbout) { AboutView() }
        .sheet(isPresented: $showList) { ImageListView().environmentObject(model) }
        .sheet(item: $model.result) { result in ResultView(result: result).environmentObject(model) }
        .alert("Voreinstellung speichern", isPresented: $showSavePreset) {
            TextField("Name", text: $newPresetName)
            Button("Speichern") { model.savePreset(named: newPresetName) }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Rahmen, Text, Schutz, Effekte und Ausgabeformat werden unter diesem Namen gespeichert.")
        }
        .alert("Voreinstellung löschen?", isPresented: Binding(get: { presetToDelete != nil },
                                                                 set: { if !$0 { presetToDelete = nil } })) {
            Button("Löschen", role: .destructive) {
                if let name = presetToDelete { model.deletePreset(name) }
            }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text(presetToDelete ?? "")
        }
        .alert("FotoRahmen", isPresented: Binding(get: { model.message != nil },
                                                  set: { if !$0 { model.message = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.message ?? "")
        }
    }

    // MARK: Teile

    private var header: some View {
        HStack(spacing: 10) {
            Image("Logo")
                .resizable()
                .interpolation(.high)
                .frame(width: 30, height: 30)
            Text("FotoRahmen")
                .font(.title3.weight(.bold))
                .foregroundStyle(Theme.fg)
            Text(AppInfo.version)
                .font(.caption.weight(.bold))
                .foregroundStyle(Theme.accent)
            Spacer()
            presetMenu
            Button { showAbout = true } label: {
                Image(systemName: "info.circle").font(.title3)
            }
            .foregroundStyle(Theme.fg)
            .accessibilityLabel("Info")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(Theme.bar)
    }

    private var presetMenu: some View {
        Menu {
            Section("Voreinstellung laden") {
                ForEach(model.presetNames, id: \.self) { name in
                    Button {
                        model.applyPreset(name)
                    } label: {
                        if name == model.currentPreset {
                            Label(name, systemImage: "checkmark")
                        } else {
                            Text(name)
                        }
                    }
                }
            }
            Section {
                Button {
                    newPresetName = model.currentPreset
                    showSavePreset = true
                } label: { Label("Aktuelle Einstellungen speichern …", systemImage: "square.and.arrow.down") }
                if !model.currentPreset.isEmpty {
                    Button(role: .destructive) { presetToDelete = model.currentPreset } label: {
                        Label("„\(model.currentPreset)“ löschen", systemImage: "trash")
                    }
                }
                Button { model.restoreBuiltinPresets() } label: {
                    Label("Mitgelieferte wiederherstellen", systemImage: "arrow.counterclockwise")
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "square.stack.3d.up")
                if sizeClass == .regular {
                    Text(model.currentPreset.isEmpty ? "Voreinstellung" : model.currentPreset)
                        .lineLimit(1)
                }
            }
            .font(.subheadline)
            .foregroundStyle(Theme.fg)
            .padding(.vertical, 6)
            .padding(.horizontal, 10)
            .background(RoundedRectangle(cornerRadius: 6).fill(Theme.button))
        }
        .accessibilityLabel("Voreinstellungen")
    }

    private var sourceBar: some View {
        VStack(spacing: 0) {
            PanelHeader(title: "Quelle") {
                Text(countText)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(Theme.fgDim)
            }
            HStack(spacing: 8) {
                PhotosPicker(selection: $pickerItems, maxSelectionCount: nil, selectionBehavior: .ordered,
                             matching: .images, preferredItemEncoding: .current, photoLibrary: .shared()) {
                    SourceChip(title: "Fotos", icon: "photo.on.rectangle")
                }
                Button { importerMode = .folder; showImporter = true } label: {
                    SourceChip(title: "Ordner", icon: "folder")
                }
                Button { importerMode = .files; showImporter = true } label: {
                    SourceChip(title: "Dateien", icon: "doc.on.doc")
                }
                Spacer(minLength: 0)
                if model.isLoading { ProgressView().tint(Theme.accent) }
                if !model.items.isEmpty && !model.isProcessing {
                    Button { model.clear() } label: {
                        Image(systemName: "xmark.circle.fill").font(.title3).foregroundStyle(Theme.fgDim)
                    }
                    .accessibilityLabel("Liste leeren")
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Theme.panel)
            .disabled(model.isProcessing)
        }
    }

    private var countText: String {
        let n = model.items.count
        guard n > 0 else { return "" }
        switch model.source {
        case .folder(let url): return "\(n) BILD\(n == 1 ? "" : "ER") · \(url.lastPathComponent.uppercased())"
        case .photos: return "\(n) FOTO\(n == 1 ? "" : "S") AUS DER MEDIATHEK"
        default: return "\(n) DATEI\(n == 1 ? "" : "EN")"
        }
    }

    private var toolScroll: some View {
        ScrollView {
            ToolTabContent(tab: tab)
                .disabled(model.isProcessing)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Theme.panel)
    }
}

/// Schaltfläche für eine Quelle.
struct SourceChip: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(Theme.fg)
            .padding(.vertical, 7)
            .padding(.horizontal, 11)
            .background(RoundedRectangle(cornerRadius: 7).fill(Theme.button))
            .overlay(RoundedRectangle(cornerRadius: 7).stroke(Theme.border, lineWidth: 0.5))
    }
}
