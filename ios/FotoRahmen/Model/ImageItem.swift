// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------

import Foundation
import UIKit

/// Status eines Bildes in der Liste.
enum ItemStatus: Equatable {
    case ready
    case working
    case done(String)      // z. B. „2048×1365“
    case skipped
    case failed(String)    // Fehlermeldung

    var label: String {
        switch self {
        case .ready: return "bereit"
        case .working: return "in Arbeit …"
        case .done(let size): return "fertig ✓ \(size)"
        case .skipped: return "übersprungen (existiert)"
        case .failed(let message): return "Fehler: \(message)"
        }
    }
}

/// Ein Bild der Stapelverarbeitung.
///
/// `url` zeigt auf die Originaldatei (Ordner/Dateien) bzw. auf eine temporäre
/// Kopie (Fotos-Mediathek, Drag & Drop). Originale werden nur gelesen.
struct ImageItem: Identifiable, Equatable {
    let id = UUID()
    let url: URL
    /// Originaler Dateiname inkl. Endung, z. B. „IMG_1234.HEIC“.
    let displayName: String
    /// Unterordner relativ zum Eingabe-Ordner („“ = direkt im Ordner).
    var relativeDir: String = ""
    /// Eigener Ausgabename (ohne Endung), nil = Namensvorlage.
    var customStem: String?
    var status: ItemStatus = .ready
    var thumbnail: UIImage?
    /// true = temporäre Kopie, die beim Leeren der Liste gelöscht wird.
    var isTemporary = false

    var stem: String { (displayName as NSString).deletingPathExtension }
    var ext: String { (displayName as NSString).pathExtension }

    static func == (lhs: ImageItem, rhs: ImageItem) -> Bool {
        lhs.id == rhs.id && lhs.customStem == rhs.customStem && lhs.status == rhs.status
            && (lhs.thumbnail == nil) == (rhs.thumbnail == nil)
    }
}

/// Woher die Bilder stammen – bestimmt das automatische Ziel.
enum SourceKind: Equatable {
    case none
    case photos            // Fotos-Mediathek → Album „mit Rahmen“
    case folder(URL)       // Ordner → Unterordner „mit Rahmen“
    case files             // einzelne Dateien / Drag & Drop → App-Ordner „mit Rahmen“
}

/// Wohin die Ergebnisse gespeichert werden.
enum OutputTarget: String, Codable, CaseIterable, Identifiable {
    case automatic, photos, folder
    var id: String { rawValue }
    var label: String {
        switch self {
        case .automatic: return "Automatisch („mit Rahmen“)"
        case .photos: return "Fotos-Mediathek (Album)"
        case .folder: return "Eigener Ordner …"
        }
    }
}

/// Ergebnis eines Stapellaufs (für das Abschlussfenster).
struct BatchResult: Identifiable {
    let id = UUID()
    var ok = 0
    var failed = 0
    var skipped = 0
    var cancelled = false
    var destinationText = ""
    var folder: URL?
    var savedToPhotos = false
    var outputFiles: [URL] = []

    var summary: String {
        var parts = ["\(ok) Bild\(ok == 1 ? "" : "er") mit Rahmen gespeichert"]
        if skipped > 0 { parts.append("\(skipped) übersprungen") }
        if failed > 0 { parts.append("\(failed) mit Fehler") }
        return (cancelled ? "Abgebrochen. " : "") + parts.joined(separator: ", ") + "."
    }
}
