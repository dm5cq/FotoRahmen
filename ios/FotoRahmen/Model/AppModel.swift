// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Zentrale App-Logik (entspricht der Klasse App der Desktop-Version, ohne Oberfläche):
// Bilderliste, Quellen, Ziele, Namensplanung, Vorschau, Stapelverarbeitung, Voreinstellungen.
// Alle Änderungen an @Published-Werten passieren im Haupt-Thread (@MainActor);
// Laden und Rendern laufen in Hintergrund-Tasks.

import Foundation
import Photos
import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

@MainActor
final class AppModel: ObservableObject {

    // MARK: Zustand

    @Published var settings: FrameSettings {
        didSet {
            guard settings != oldValue else { return }
            saveSettings()
            replan()
            schedulePreview()
        }
    }
    @Published var items: [ImageItem] = [] {
        didSet { replan() }
    }
    @Published var selectedID: UUID? {
        didSet { if selectedID != oldValue { schedulePreview() } }
    }
    @Published private(set) var source: SourceKind = .none
    @Published var includeSubfolders = false {
        didSet {
            UserDefaults.standard.set(includeSubfolders, forKey: Keys.recursive)
            if case .folder(let url) = source { loadFolder(url) }
        }
    }
    @Published var outputTarget: OutputTarget = .automatic {
        didSet {
            UserDefaults.standard.set(outputTarget.rawValue, forKey: Keys.target)
            replan()
        }
    }
    @Published private(set) var customFolder: URL?
    @Published private(set) var planned: [UUID: PlannedJob] = [:]

    @Published private(set) var previewImage: UIImage?
    @Published private(set) var previewInfo = ""
    @Published private(set) var isLoading = false

    @Published private(set) var isProcessing = false
    @Published private(set) var progress: Double = 0
    @Published var statusText = "Bereit."
    @Published var result: BatchResult?

    @Published private(set) var presets: [String: FrameSettings] = [:]
    @Published var currentPreset = ""
    @Published var message: String?
    /// Wird vom Tab AUSGABE gesetzt, die Oberfläche öffnet dann die Ordnerauswahl.
    @Published var showOutputFolderPicker = false

    // MARK: Intern

    private enum Keys {
        static let settings = "settings.v1"
        static let presets = "presets.v1"
        static let target = "outputTarget.v1"
        static let folderBookmark = "outputFolderBookmark.v1"
        static let recursive = "includeSubfolders.v1"
    }

    private var scopedURLs: [URL] = []
    private var previewCache: [UUID: PreviewSource] = [:]
    private var previewTask: Task<Void, Never>?
    private var cancelRequested = false
    private let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent("FotoRahmen-Import",
                                                                                          isDirectory: true)

    init() {
        let defaults = UserDefaults.standard
        if let data = defaults.data(forKey: Keys.settings),
           let stored = try? JSONDecoder().decode(FrameSettings.self, from: data) {
            settings = stored
        } else {
            settings = FrameSettings()
        }
        if let data = defaults.data(forKey: Keys.presets),
           let stored = try? JSONDecoder().decode([String: FrameSettings].self, from: data) {
            presets = stored
        } else {
            presets = BuiltinPresets.all
        }
        includeSubfolders = defaults.bool(forKey: Keys.recursive)
        outputTarget = OutputTarget(rawValue: defaults.string(forKey: Keys.target) ?? "") ?? .automatic
        restoreCustomFolder()
        try? FileManager.default.removeItem(at: tempRoot)   // Reste früherer Importe
    }

    // MARK: Einstellungen & Voreinstellungen

    private func saveSettings() {
        if let data = try? JSONEncoder().encode(settings) {
            UserDefaults.standard.set(data, forKey: Keys.settings)
        }
    }

    private func savePresets() {
        if let data = try? JSONEncoder().encode(presets) {
            UserDefaults.standard.set(data, forKey: Keys.presets)
        }
    }

    var presetNames: [String] {
        presets.keys.sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    /// Voreinstellung laden – Dateiname-Vorlage und Konfliktverhalten bleiben wie eingestellt.
    func applyPreset(_ name: String) {
        guard var preset = presets[name] else { return }
        preset.template = settings.template
        preset.conflict = settings.conflict
        settings = preset
        currentPreset = name
        statusText = "Voreinstellung „\(name)“ geladen."
    }

    func savePreset(named rawName: String) {
        let name = String(rawName.trimmingCharacters(in: .whitespaces).prefix(60))
        guard !name.isEmpty else { return }
        presets[name] = settings
        savePresets()
        currentPreset = name
        statusText = "Voreinstellung „\(name)“ gespeichert."
    }

    func deletePreset(_ name: String) {
        presets[name] = nil
        savePresets()
        if currentPreset == name { currentPreset = "" }
    }

    func restoreBuiltinPresets() {
        for (name, preset) in BuiltinPresets.all { presets[name] = preset }
        savePresets()
    }

    // MARK: Quellen

    /// Liste leeren (temporäre Kopien löschen, Ordnerzugriffe beenden).
    func clear() {
        guard !isProcessing else { return }
        for url in scopedURLs { url.stopAccessingSecurityScopedResource() }
        scopedURLs.removeAll()
        for item in items where item.isTemporary {
            try? FileManager.default.removeItem(at: item.url.deletingLastPathComponent())
        }
        items = []
        previewCache.removeAll()
        selectedID = nil
        source = .none
        previewImage = nil
        previewInfo = ""
    }

    private func beginAccess(_ url: URL) {
        if url.startAccessingSecurityScopedResource() { scopedURLs.append(url) }
    }

    private func setItems(_ new: [ImageItem], source newSource: SourceKind, append: Bool) {
        if !append || source != newSource { clear() }
        source = newSource
        items.append(contentsOf: new)
        if selectedID == nil { selectedID = items.first?.id }
        statusText = "\(items.count) Bild\(items.count == 1 ? "" : "er") geladen."
        loadThumbnails()
    }

    /// Fotos aus der Mediathek übernehmen (als temporäre Kopien mit Originalnamen).
    func addPhotos(_ picks: [PhotosPickerItem]) async {
        guard !picks.isEmpty, !isProcessing else { return }
        isLoading = true
        defer { isLoading = false }
        let named = await PhotoLibrary.requestAccess()
        var new: [ImageItem] = []
        let start = source == .photos ? items.count : 0
        for (index, pick) in picks.enumerated() {
            guard let data = try? await pick.loadTransferable(type: Data.self) else { continue }
            let ext = ImageIOHelpers.preferredExtension(for: data) ?? "jpg"
            var filename = "Foto_\(String(format: "%03d", start + index + 1)).\(ext)"
            if named, let id = pick.itemIdentifier, let original = PhotoLibrary.originalFilename(localIdentifier: id) {
                // Originalnamen behalten; Endung an den tatsächlichen Inhalt anpassen
                let originalFormat = ImageFormat(ext: (original as NSString).pathExtension)
                if originalFormat != nil && originalFormat == ImageFormat(ext: ext) {
                    filename = original
                } else {
                    filename = (original as NSString).deletingPathExtension + "." + ext
                }
            }
            if let url = storeTemporary(data: data, filename: filename) {
                var item = ImageItem(url: url, displayName: filename)
                item.isTemporary = true
                new.append(item)
            }
        }
        setItems(new, source: .photos, append: true)
    }

    private func storeTemporary(data: Data, filename: String) -> URL? {
        let dir = tempRoot.appendingPathComponent(UUID().uuidString, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let url = dir.appendingPathComponent(filename)
            try data.write(to: url)
            return url
        } catch {
            return nil
        }
    }

    /// Ordner aus der Dateien-App: alle Bilder darin (optional mit Unterordnern).
    func addFolder(_ url: URL) {
        guard !isProcessing else { return }
        clear()
        beginAccess(url)
        loadFolder(url)
    }

    private func loadFolder(_ folder: URL) {
        guard !isProcessing else { return }
        let keys: [URLResourceKey] = [.isRegularFileKey, .isDirectoryKey]
        var options: FileManager.DirectoryEnumerationOptions = [.skipsHiddenFiles, .skipsPackageDescendants]
        if !includeSubfolders { options.insert(.skipsSubdirectoryDescendants) }
        var found: [URL] = []
        if let enumerator = FileManager.default.enumerator(at: folder, includingPropertiesForKeys: keys,
                                                           options: options) {
            for case let url as URL in enumerator {
                let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .isDirectoryKey])
                if values?.isDirectory == true {
                    if url.lastPathComponent == Naming.autoOutputName { enumerator.skipDescendants() }
                    continue
                }
                guard values?.isRegularFile == true,
                      Naming.inputExtensions.contains(url.pathExtension.lowercased()) else { continue }
                found.append(url)
            }
        }
        let base = folder.resolvingSymlinksInPath().standardizedFileURL.pathComponents
        found.sort { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
        let new: [ImageItem] = found.map { url in
            let comps = url.deletingLastPathComponent().resolvingSymlinksInPath().standardizedFileURL.pathComponents
            let rel = comps.count > base.count ? comps[base.count...].joined(separator: "/") : ""
            return ImageItem(url: url, displayName: url.lastPathComponent, relativeDir: rel)
        }
        items = []
        previewCache.removeAll()
        selectedID = nil
        source = .folder(folder)
        setItems(new, source: .folder(folder), append: true)
        if new.isEmpty { statusText = "Im Ordner wurden keine Bilder gefunden." }
    }

    /// Einzelne Dateien aus der Dateien-App.
    func addFiles(_ urls: [URL]) {
        guard !isProcessing else { return }
        var new: [ImageItem] = []
        for url in urls where Naming.inputExtensions.contains(url.pathExtension.lowercased()) {
            beginAccess(url)
            new.append(ImageItem(url: url, displayName: url.lastPathComponent))
        }
        if new.isEmpty {
            message = "Keine unterstützten Bilder in der Auswahl."
            return
        }
        setItems(new, source: .files, append: true)
    }

    /// Drag & Drop (iPad): Bilder aus Fotos, Dateien oder anderen Apps.
    func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !isProcessing else { return false }
        let imageType = UTType.image.identifier
        var accepted = false
        for provider in providers where provider.hasItemConformingToTypeIdentifier(imageType) {
            accepted = true
            let suggested = provider.suggestedName
            _ = provider.loadFileRepresentation(forTypeIdentifier: imageType) { [weak self] url, _ in
                guard let url else { return }
                // Datei muss sofort kopiert werden – sie wird nach dem Rückruf gelöscht
                let ext = url.pathExtension.isEmpty ? "jpg" : url.pathExtension
                var name = suggested ?? url.deletingPathExtension().lastPathComponent
                if (name as NSString).pathExtension.isEmpty { name += "." + ext }
                guard let data = try? Data(contentsOf: url) else { return }
                Task { @MainActor in
                    guard let self, let stored = self.storeTemporary(data: data, filename: name) else { return }
                    var item = ImageItem(url: stored, displayName: name)
                    item.isTemporary = true
                    self.setItems([item], source: .files, append: true)
                }
            }
        }
        return accepted
    }

    func remove(_ id: UUID) {
        guard !isProcessing, let index = items.firstIndex(where: { $0.id == id }) else { return }
        let item = items.remove(at: index)
        if item.isTemporary { try? FileManager.default.removeItem(at: item.url.deletingLastPathComponent()) }
        previewCache[id] = nil
        if selectedID == id { selectedID = items.first?.id }
        if items.isEmpty { clear() }
    }

    func resetNames() {
        for i in items.indices { items[i].customStem = nil }
    }

    private func loadThumbnails() {
        let pending = items.filter { $0.thumbnail == nil }.map { ($0.id, $0.url) }
        guard !pending.isEmpty else { return }
        Task.detached(priority: .utility) { [weak self] in
            for (id, url) in pending {
                let thumb = ImageIOHelpers.thumbnail(url: url)
                await MainActor.run {
                    guard let self, let i = self.items.firstIndex(where: { $0.id == id }) else { return }
                    self.items[i].thumbnail = thumb
                }
            }
        }
    }

    // MARK: Ziel

    /// Gewählten eigenen Ausgabe-Ordner merken (Lesezeichen, damit er beim nächsten Start bleibt).
    func setCustomFolder(_ url: URL) {
        customFolder?.stopAccessingSecurityScopedResource()
        _ = url.startAccessingSecurityScopedResource()
        customFolder = url
        if let data = try? url.bookmarkData(options: [], includingResourceValuesForKeys: nil, relativeTo: nil) {
            UserDefaults.standard.set(data, forKey: Keys.folderBookmark)
        }
        outputTarget = .folder
        replan()
    }

    private func restoreCustomFolder() {
        guard let data = UserDefaults.standard.data(forKey: Keys.folderBookmark) else { return }
        var stale = false
        if let url = try? URL(resolvingBookmarkData: data, options: [], relativeTo: nil, bookmarkDataIsStale: &stale) {
            _ = url.startAccessingSecurityScopedResource()
            customFolder = url
        }
    }

    /// App-eigener Ordner (sichtbar in der Dateien-App unter „Auf meinem iPhone › FotoRahmen“).
    var appFolder: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(Naming.autoOutputName, isDirectory: true)
    }

    /// Zielordner (nil = Fotos-Mediathek).
    var destinationFolder: URL? {
        switch outputTarget {
        case .photos:
            return nil
        case .folder:
            return customFolder ?? appFolder
        case .automatic:
            switch source {
            case .folder(let url): return url.appendingPathComponent(Naming.autoOutputName, isDirectory: true)
            case .photos: return nil
            case .files, .none: return appFolder
            }
        }
    }

    var destinationDescription: String {
        if let folder = destinationFolder {
            if folder.path.hasPrefix(appFolder.deletingLastPathComponent().path) {
                return "Dateien › Auf meinem iPhone › FotoRahmen › \(Naming.autoOutputName)"
            }
            if case .folder(let src) = source, outputTarget == .automatic {
                return "Ordner „\(src.lastPathComponent)“ › \(Naming.autoOutputName)"
            }
            return "Ordner „\(folder.lastPathComponent)“"
        }
        return "Fotos › Album „\(Naming.autoOutputName)“"
    }

    /// Ausgabenamen neu planen (nicht während der Verarbeitung – die Namen des Laufs bleiben sichtbar).
    func replan() {
        guard !isProcessing else { return }
        planned = Naming.plan(items: items, settings: settings, baseDirectory: destinationFolder)
    }

    func plannedName(_ id: UUID) -> String { planned[id]?.fileName ?? "" }

    // MARK: Vorschau

    func format(for item: ImageItem) -> ImageFormat {
        Naming.outputFormat(sourceExt: item.ext, choice: settings.format)
    }

    var effectsHint: String {
        guard settings.cornerRadius > 0 || settings.shadow > 0 else { return "" }
        switch settings.format {
        case .png: return "✓ Effekte aktiv"
        case .original: return "Effekte nur für PNG-Originale aktiv"
        default: return "Effekte inaktiv – Ausgabe als PNG wählen"
        }
    }

    func schedulePreview() {
        previewTask?.cancel()
        guard let id = selectedID, let item = items.first(where: { $0.id == id }) else {
            previewImage = nil
            previewInfo = ""
            return
        }
        let settings = self.settings
        let format = self.format(for: item)
        let cached = previewCache[id]
        let url = item.url
        let values = TextValues(name: item.stem)
        previewTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 120_000_000)
            if Task.isCancelled { return }
            let rendered = await Task.detached(priority: .userInitiated) { () -> (PreviewSource, CGImage)? in
                guard let src = cached ?? ImageIOHelpers.previewSource(url: url, maxPixel: 1600),
                      let img = FrameRenderer.preview(source: src, settings: settings,
                                                      box: CGSize(width: 1500, height: 1500),
                                                      format: format, values: values)
                else { return nil }
                return (src, img)
            }.value
            guard let self, !Task.isCancelled else { return }
            guard let rendered else {
                self.previewImage = nil
                self.previewInfo = "Bild kann nicht gelesen werden"
                return
            }
            let (src, img) = rendered
            self.previewCache[id] = src
            if self.previewCache.count > 12, let first = self.previewCache.keys.first(where: { $0 != id }) {
                self.previewCache[first] = nil
            }
            self.previewImage = UIImage(cgImage: img)
            let (ow, oh) = FrameRenderer.outputSize(settings: settings, w: src.width, h: src.height, format: format)
            self.previewInfo = "\(src.width) × \(src.height)  →  \(ow) × \(oh) px"
        }
    }

    // MARK: Stapelverarbeitung

    func cancel() {
        cancelRequested = true
        statusText = "Wird nach dem aktuellen Bild abgebrochen …"
    }

    func start() {
        guard !items.isEmpty, !isProcessing else { return }
        replan()
        let jobs = items.compactMap { item in planned[item.id].map { (item, $0) } }
        let settings = self.settings
        let folder = destinationFolder
        let destinationText = destinationDescription
        isProcessing = true
        cancelRequested = false
        progress = 0
        statusText = "Starte Verarbeitung von \(jobs.count) Bildern …"
        UIApplication.shared.isIdleTimerDisabled = true
        let backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "FotoRahmen") {}

        Task { [weak self] in
            guard let self else { return }
            var result = BatchResult(destinationText: destinationText, folder: folder, savedToPhotos: folder == nil)
            var album: PHAssetCollection?
            if folder == nil {
                if await PhotoLibrary.requestAccess() {
                    album = await PhotoLibrary.album(named: Naming.autoOutputName)
                } else if !(await PhotoLibrary.requestAddAccess()) {
                    self.message = "Kein Zugriff auf die Fotos-Mediathek. Bitte in den Einstellungen erlauben "
                        + "oder als Ziel einen Ordner wählen."
                    self.finish(result, backgroundTask: backgroundTask)
                    return
                }
            }
            let tempOut = FileManager.default.temporaryDirectory.appendingPathComponent("FotoRahmen-Export",
                                                                                        isDirectory: true)
            for (index, (item, job)) in jobs.enumerated() {
                if self.cancelRequested { result.cancelled = true; break }
                self.progress = Double(index) / Double(max(jobs.count, 1))
                self.statusText = "Bild \(index + 1) von \(jobs.count): \(item.displayName)"
                self.setStatus(item.id, .working)
                if job.skip {
                    result.skipped += 1
                    self.setStatus(item.id, .skipped)
                    continue
                }
                let target = job.url ?? tempOut.appendingPathComponent(job.fileName)
                let values = TextValues(name: item.stem)
                let sourceURL = item.url
                let format = job.format
                do {
                    let size = try await Task.detached(priority: .userInitiated) { () throws -> (Int, Int) in
                        try autoreleasepool {
                            try FrameRenderer.process(source: sourceURL, destination: target, format: format,
                                                      settings: settings, values: values)
                        }
                    }.value
                    if folder == nil {
                        try await PhotoLibrary.save(fileURL: target, filename: job.fileName, album: album)
                        try? FileManager.default.removeItem(at: target)
                    } else {
                        result.outputFiles.append(target)
                    }
                    result.ok += 1
                    self.setStatus(item.id, .done("\(size.0)×\(size.1)"))
                } catch {
                    result.failed += 1
                    self.setStatus(item.id, .failed(error.localizedDescription))
                }
            }
            try? FileManager.default.removeItem(at: tempOut)
            self.progress = 1
            self.finish(result, backgroundTask: backgroundTask)
        }
    }

    private func setStatus(_ id: UUID, _ status: ItemStatus) {
        if let i = items.firstIndex(where: { $0.id == id }) { items[i].status = status }
    }

    private func finish(_ result: BatchResult, backgroundTask: UIBackgroundTaskIdentifier) {
        isProcessing = false
        UIApplication.shared.isIdleTimerDisabled = false
        statusText = result.summary
        self.result = result
        UIApplication.shared.endBackgroundTask(backgroundTask)
    }

    /// Dateien-App am Zielordner öffnen bzw. die Fotos-App.
    func openDestination(_ result: BatchResult) {
        var url: URL?
        if let folder = result.folder {
            url = URL(string: "shareddocuments://" + folder.path(percentEncoded: true))
        } else {
            url = URL(string: "photos-redirect://")
        }
        if let url { UIApplication.shared.open(url) }
    }
}
