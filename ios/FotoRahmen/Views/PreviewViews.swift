// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Vorschau, Bilderleiste, Statusleiste und Namensliste.

import SwiftUI

/// VORSCHAU: das gewählte Bild mit Rahmen, Text, Wasserzeichen und Effekten.
struct PreviewPanel: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            PanelHeader(title: "Vorschau") {
                Text(model.previewInfo.uppercased())
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(Theme.fgDim)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            ZStack {
                Theme.viewer
                if let image = model.previewImage {
                    Image(uiImage: image)
                        .resizable()
                        .interpolation(.high)
                        .aspectRatio(contentMode: .fit)
                        .padding(14)
                } else if model.items.isEmpty {
                    VStack(spacing: 10) {
                        Image("Logo")
                            .resizable()
                            .frame(width: 64, height: 64)
                            .opacity(0.85)
                        Text("Fotos, einen Ordner oder Dateien wählen")
                            .font(.subheadline.weight(.semibold))
                        Text("Die Originale bleiben unverändert.")
                            .font(.caption)
                    }
                    .foregroundStyle(Theme.fg.opacity(0.75))
                    .multilineTextAlignment(.center)
                    .padding()
                } else {
                    ProgressView().tint(Theme.fg)
                }
            }
            .clipped()
        }
    }
}

/// Bilderleiste: Vorschaubilder mit Ausgabenamen und Status; Tippen = in der Vorschau zeigen.
struct ThumbnailStrip: View {
    @EnvironmentObject private var model: AppModel
    @Binding var showList: Bool

    var body: some View {
        VStack(spacing: 0) {
            PanelHeader(title: "Bilder") {
                if !model.items.isEmpty {
                    Button { showList = true } label: {
                        Label("Namen & Status", systemImage: "list.bullet")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Theme.accent)
                    }
                }
            }
            ScrollViewReader { proxy in
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 8) {
                        ForEach(model.items) { item in
                            ThumbnailCell(item: item, selected: item.id == model.selectedID,
                                          outputName: model.plannedName(item.id))
                                .id(item.id)
                                .onTapGesture { model.selectedID = item.id }
                                .contextMenu {
                                    Button { model.selectedID = item.id; showList = true } label: {
                                        Label("Umbenennen …", systemImage: "pencil")
                                    }
                                    Button(role: .destructive) { model.remove(item.id) } label: {
                                        Label("Aus der Liste entfernen", systemImage: "minus.circle")
                                    }
                                }
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                }
                .onChange(of: model.selectedID) { _, id in
                    if let id { withAnimation { proxy.scrollTo(id, anchor: .center) } }
                }
            }
            .frame(height: 112)
            .background(Theme.panel)
        }
    }
}

struct ThumbnailCell: View {
    let item: ImageItem
    let selected: Bool
    let outputName: String

    var body: some View {
        VStack(spacing: 4) {
            ZStack(alignment: .topTrailing) {
                Group {
                    if let thumb = item.thumbnail {
                        Image(uiImage: thumb).resizable().aspectRatio(contentMode: .fill)
                    } else {
                        Theme.input
                    }
                }
                .frame(width: 84, height: 62)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4)
                    .stroke(selected ? Theme.accent : Theme.border, lineWidth: selected ? 2.5 : 0.5))
                statusBadge.padding(3)
            }
            Text(outputName.isEmpty ? item.displayName : outputName)
                .font(.system(size: 10))
                .foregroundStyle(item.customStem != nil ? Theme.accent : Theme.fgDim)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(width: 84)
        }
    }

    @ViewBuilder private var statusBadge: some View {
        switch item.status {
        case .done:
            Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.ok)
        case .failed:
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.err)
        case .working:
            ProgressView().scaleEffect(0.6).tint(Theme.accent)
        case .skipped:
            Image(systemName: "arrow.uturn.right.circle.fill").foregroundStyle(Theme.fgDim)
        case .ready:
            EmptyView()
        }
    }
}

/// Statusleiste unten: Fortschritt, Status und „RAHMEN ERSTELLEN“.
struct BottomBar: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        VStack(spacing: 8) {
            if model.isProcessing {
                ProgressView(value: model.progress).tint(Theme.accent)
            }
            if sizeClass == .regular {
                HStack(spacing: 12) {
                    status
                    Spacer()
                    cancelButton
                    startButton.frame(width: 260)
                }
            } else {
                HStack {
                    status
                    Spacer()
                    cancelButton
                }
                startButton
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(Theme.bar)
    }

    private var status: some View {
        Text(model.statusText)
            .font(.caption)
            .foregroundStyle(Theme.fgDim)
            .lineLimit(2)
    }

    @ViewBuilder private var cancelButton: some View {
        if model.isProcessing {
            Button("Abbrechen") { model.cancel() }.buttonStyle(DarkButtonStyle())
        }
    }

    private var startButton: some View {
        Button { model.start() } label: {
            Text("RAHMEN ERSTELLEN")
        }
        .buttonStyle(AccentButtonStyle())
        .disabled(model.items.isEmpty || model.isProcessing)
    }
}

/// Liste aller Bilder: Ausgabenamen einzeln ändern (wie Doppelklick in der Desktop-Liste), Status sehen.
struct ImageListView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach($model.items) { $item in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(item.relativeDir.isEmpty ? item.displayName
                                     : item.relativeDir + "/" + item.displayName)
                                    .font(.caption)
                                    .foregroundStyle(Theme.fgDim)
                                Spacer()
                                Text(item.status.label)
                                    .font(.caption2)
                                    .foregroundStyle(statusColor(item.status))
                                    .lineLimit(2)
                            }
                            HStack(spacing: 4) {
                                TextField(planStem(item.id),
                                          text: Binding(get: { item.customStem ?? "" },
                                                        set: { item.customStem = $0.isEmpty ? nil : $0 }))
                                    .autocorrectionDisabled()
                                    .textInputAutocapitalization(.never)
                                    .foregroundStyle(item.customStem != nil ? Theme.accent : Theme.fg)
                                Text("." + (model.plannedName(item.id) as NSString).pathExtension)
                                    .foregroundStyle(Theme.fgDim)
                            }
                        }
                        .listRowBackground(item.id == model.selectedID ? Theme.accentDim : Theme.panel)
                    }
                    .onDelete { offsets in
                        let ids = offsets.map { model.items[$0].id }
                        for id in ids { model.remove(id) }
                    }
                } footer: {
                    Text("Leeres Feld = Namensvorlage aus dem Tab AUSGABE. Eigene Namen erscheinen orange. "
                         + "Ziel: \(model.destinationDescription)")
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.app)
            .navigationTitle("Bilder & Ausgabenamen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Alle zurücksetzen") { model.resetNames() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Fertig") { dismiss() }.fontWeight(.bold)
                }
            }
            .disabled(model.isProcessing)
        }
        .preferredColorScheme(.dark)
        .tint(Theme.accent)
    }

    private func planStem(_ id: UUID) -> String {
        (model.plannedName(id) as NSString).deletingPathExtension
    }

    private func statusColor(_ status: ItemStatus) -> Color {
        switch status {
        case .done: return Theme.ok
        case .failed: return Theme.err
        default: return Theme.fgDim
        }
    }
}
