// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Platzhalter, Dateinamen und Planung der Ausgabedateien
// (entspricht render_template / sanitize_stem / plan_jobs der Desktop-Version).

import Foundation

/// Werte für Platzhalter {name}, {datum}, {jahr} in Text, Wasserzeichen und Metadaten.
struct TextValues {
    var name: String
    var date: Date = Date()

    func expand(_ text: String) -> String {
        guard !text.isEmpty else { return "" }
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.dateFormat = "yyyy-MM-dd"
        let year = Calendar(identifier: .gregorian).component(.year, from: date)
        return text
            .replacingOccurrences(of: "{name}", with: name)
            .replacingOccurrences(of: "{datum}", with: df.string(from: date))
            .replacingOccurrences(of: "{jahr}", with: String(year))
    }
}

enum Naming {
    /// Name des automatischen Ausgabe-Ordners bzw. Fotos-Albums.
    static let autoOutputName = "mit Rahmen"

    /// Lesbare Bildformate (ImageIO kann sie unter iOS dekodieren).
    static let inputExtensions: Set<String> = [
        "jpg", "jpeg", "jpe", "jfif", "png", "tif", "tiff", "heic", "heif", "gif", "webp", "bmp", "jp2",
    ]

    private static let reserved: Set<String> = {
        var s: Set<String> = ["CON", "PRN", "AUX", "NUL"]
        for i in 1...9 { s.insert("COM\(i)"); s.insert("LPT\(i)") }
        return s
    }()

    /// Dateinamen (ohne Endung) für iOS, Windows und macOS gültig machen.
    static func sanitize(_ stem: String) -> String {
        let illegal = CharacterSet(charactersIn: "<>:\"/\\|?*").union(.controlCharacters)
        var out = String(stem.unicodeScalars.map { illegal.contains($0) ? "_" : Character($0) })
        out = out.trimmingCharacters(in: .whitespaces)
        while out.hasSuffix(".") || out.hasSuffix(" ") { out.removeLast() }
        if reserved.contains(out.uppercased()) { out += "_" }
        if out.count > 200 { out = String(out.prefix(200)) }
        return out
    }

    /// Namensvorlage ausfüllen: {name}, {nr} (001 …), {datum}.
    static func render(template: String, name: String, number: Int, date: Date = Date()) -> String {
        let t = template.isEmpty ? "{name}" : template
        let nr = String(format: "%03d", number)
        let filled = TextValues(name: name, date: date).expand(t.replacingOccurrences(of: "{nr}", with: nr))
        let s = sanitize(filled)
        if !s.isEmpty { return s }
        let fallback = sanitize(name)
        return fallback.isEmpty ? "bild" : fallback
    }

    /// Ausgabeformat für eine Quelldatei (bei „Wie Original“ das Originalformat, sonst JPEG).
    static func outputFormat(sourceExt: String, choice: OutputFormat) -> ImageFormat {
        if let fixed = choice.fixed { return fixed }
        return ImageFormat(ext: sourceExt) ?? .jpeg
    }

    /// Endung der Ausgabedatei – bei „Wie Original“ bleibt die Schreibweise der Quelle (z. B. „JPG“).
    static func outputExtension(sourceExt: String, choice: OutputFormat) -> String {
        if choice == .original, ImageFormat(ext: sourceExt) != nil { return sourceExt.lowercased() }
        return outputFormat(sourceExt: sourceExt, choice: choice).ext
    }
}

/// Eine geplante Verarbeitung.
struct PlannedJob: Equatable {
    var fileName: String          // mit Endung
    var directory: URL?           // nil = Fotos-Mediathek
    var skip: Bool
    var format: ImageFormat

    var stem: String { (fileName as NSString).deletingPathExtension }
    var url: URL? { directory?.appendingPathComponent(fileName) }
}

extension Naming {
    /// Zielnamen für alle Bilder festlegen; doppelte Namen erhalten _2, _3 …
    /// Ein Ziel ist nie eine der Quelldateien.
    static func plan(items: [ImageItem], settings: FrameSettings, baseDirectory: URL?) -> [UUID: PlannedJob] {
        var used = Set<String>()
        let sources = Set(items.map { $0.url.standardizedFileURL.path })
        var result: [UUID: PlannedJob] = [:]
        let fm = FileManager.default
        for (index, item) in items.enumerated() {
            var stem = sanitize(item.customStem ?? "")
            if stem.isEmpty {
                stem = render(template: settings.template, name: item.stem, number: index + 1)
            }
            let ext = outputExtension(sourceExt: item.ext, choice: settings.format)
            let format = outputFormat(sourceExt: item.ext, choice: settings.format)
            var dir = baseDirectory
            if let base = baseDirectory, !item.relativeDir.isEmpty {
                dir = base.appendingPathComponent(item.relativeDir, isDirectory: true)
            }
            var name = "\(stem).\(ext)"
            var n = 2
            func clashes(_ candidate: String) -> Bool {
                let key = ((dir?.path ?? "fotos") + "/" + candidate).lowercased()
                if used.contains(key) { return true }
                guard let dir else { return false }
                let url = dir.appendingPathComponent(candidate)
                if sources.contains(url.standardizedFileURL.path) { return true }
                return settings.conflict == .number && fm.fileExists(atPath: url.path)
            }
            while clashes(name) {
                name = "\(stem)_\(n).\(ext)"
                n += 1
            }
            used.insert(((dir?.path ?? "fotos") + "/" + name).lowercased())
            var skip = false
            if settings.conflict == .skip, let dir, fm.fileExists(atPath: dir.appendingPathComponent(name).path) {
                skip = true
            }
            result[item.id] = PlannedJob(fileName: name, directory: dir, skip: skip, format: format)
        }
        return result
    }
}
