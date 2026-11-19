// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Rahmen und Copyright-Schutz für Fotos
// Copyright (c) 2026 Stefan J. Kaiser
// Idee und Prompt: Stefan J. Kaiser
// Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// Lizenz: GNU GPL v3 – siehe Datei LICENSE
// -----------------------------------------------------------------------------
//
// Alle Einstellungen eines Rahmens (entspricht FrameSettings in rahmen_core.py
// der Desktop-Version) plus Umrechnung in Pixel-Schichten.

import Foundation
import CoreGraphics
import SwiftUI
import UIKit
import UniformTypeIdentifiers

// MARK: - Farbe

/// Farbe als sRGB-Werte 0…1 (speicherbar, unabhängig von SwiftUI/UIKit).
struct RGBColor: Codable, Equatable, Hashable {
    var r: Double
    var g: Double
    var b: Double

    static let white = RGBColor(r: 1, g: 1, b: 1)
    static let black = RGBColor(r: 0, g: 0, b: 0)
    static let darkGray = RGBColor(r: 60.0 / 255, g: 60.0 / 255, b: 60.0 / 255)
    static let anthracite = RGBColor(r: 38.0 / 255, g: 38.0 / 255, b: 38.0 / 255)
    static let orange = RGBColor(r: 242.0 / 255, g: 138.0 / 255, b: 30.0 / 255)

    init(r: Double, g: Double, b: Double) {
        self.r = min(max(r, 0), 1)
        self.g = min(max(g, 0), 1)
        self.b = min(max(b, 0), 1)
    }

    /// Aus einer SwiftUI-Farbe (z. B. vom ColorPicker).
    init(_ color: Color) {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(color).getRed(&r, green: &g, blue: &b, alpha: &a)
        self.init(r: Double(r), g: Double(g), b: Double(b))
    }

    /// Helligkeit nach ITU-R BT.601.
    var luminance: Double { 0.299 * r + 0.587 * g + 0.114 * b }

    /// Schwarz oder Weiß – je nachdem, was sich besser abhebt (Kontrastkante).
    var contrast: RGBColor { luminance > 0.55 ? .black : .white }

    var swiftUIColor: Color { Color(.sRGB, red: r, green: g, blue: b, opacity: 1) }

    func uiColor(alpha: CGFloat = 1) -> UIColor {
        UIColor(red: CGFloat(r), green: CGFloat(g), blue: CGFloat(b), alpha: alpha)
    }

    func cgColor(alpha: CGFloat = 1) -> CGColor {
        CGColor(srgbRed: CGFloat(r), green: CGFloat(g), blue: CGFloat(b), alpha: alpha)
    }
}

// MARK: - Auswahlwerte

enum WidthUnit: String, Codable, CaseIterable, Identifiable {
    case px, pct
    var id: String { rawValue }
    var label: String { self == .px ? "Pixel" : "% lange Kante" }
    var short: String { self == .px ? "px" : "%" }
}

enum TextPosition: String, Codable, CaseIterable, Identifiable {
    case left, center, right
    var id: String { rawValue }
    var label: String {
        switch self {
        case .left: return "Links"
        case .center: return "Mitte"
        case .right: return "Rechts"
        }
    }
}

/// Position des Wasserzeichens (wie WM_POSITIONS der Desktop-Version).
enum WatermarkPosition: String, Codable, CaseIterable, Identifiable {
    case bottomRight = "br", bottomLeft = "bl", topRight = "tr", topLeft = "tl", center = "c", tile
    var id: String { rawValue }
    var label: String {
        switch self {
        case .bottomRight: return "Unten rechts"
        case .bottomLeft: return "Unten links"
        case .topRight: return "Oben rechts"
        case .topLeft: return "Oben links"
        case .center: return "Mitte"
        case .tile: return "Diagonal über das ganze Bild"
        }
    }
}

/// Vom Benutzer gewähltes Ausgabeformat.
enum OutputFormat: String, Codable, CaseIterable, Identifiable {
    case original, jpeg, png, heic, tiff
    var id: String { rawValue }
    var label: String {
        switch self {
        case .original: return "Wie Original"
        case .jpeg: return "JPEG (.jpg)"
        case .png: return "PNG (.png)"
        case .heic: return "HEIC (.heic)"
        case .tiff: return "TIFF (.tif)"
        }
    }
    /// Festes Zielformat (nil = wie Original).
    var fixed: ImageFormat? {
        switch self {
        case .original: return nil
        case .jpeg: return .jpeg
        case .png: return .png
        case .heic: return .heic
        case .tiff: return .tiff
        }
    }
}

/// Tatsächlich geschriebenes Dateiformat.
enum ImageFormat: String, Codable {
    case jpeg, png, heic, tiff, gif

    /// Format aus einer Dateiendung (nil = iOS kann es nicht schreiben, z. B. WebP).
    init?(ext: String) {
        switch ext.lowercased() {
        case "jpg", "jpeg", "jpe", "jfif": self = .jpeg
        case "png": self = .png
        case "heic", "heif": self = .heic
        case "tif", "tiff": self = .tiff
        case "gif": self = .gif
        default: return nil
        }
    }

    var utType: UTType {
        switch self {
        case .jpeg: return .jpeg
        case .png: return .png
        case .heic: return .heic
        case .tiff: return .tiff
        case .gif: return .gif
        }
    }

    var ext: String {
        switch self {
        case .jpeg: return "jpg"
        case .png: return "png"
        case .heic: return "heic"
        case .tiff: return "tif"
        case .gif: return "gif"
        }
    }

    /// Transparenz möglich (sonst wird unter dem Bild weiß gefüllt).
    var supportsAlpha: Bool { self == .png || self == .tiff || self == .gif }
    /// Verlustbehaftet (Qualitätseinstellung gilt).
    var isLossy: Bool { self == .jpeg || self == .heic }
    /// 16 Bit je Kanal bleiben erhalten.
    var keeps16Bit: Bool { self == .png || self == .tiff }
    /// Abgerundete Ecken und Schatten (brauchen Transparenz) – wie Desktop: nur PNG.
    var allowsEffects: Bool { self == .png }
}

enum ConflictMode: String, Codable, CaseIterable, Identifiable {
    case number, overwrite, skip
    var id: String { rawValue }
    var label: String {
        switch self {
        case .number: return "Nummer anhängen (_2, _3 …)"
        case .overwrite: return "Überschreiben"
        case .skip: return "Überspringen"
        }
    }
}

/// Eine Rahmenschicht: Breite oben/links/rechts, Breite unten, Farbe.
struct Layer: Equatable {
    var width: Int
    var bottom: Int
    var color: RGBColor
}

// MARK: - Einstellungen

struct FrameSettings: Codable, Equatable {
    // Rahmen
    var double = false
    var unit: WidthUnit = .pct
    var outerPx: Double = 60
    var outerPct: Double = 3
    var innerPx: Double = 6
    var innerPct: Double = 0.3
    var bottomPx: Double = 0
    var bottomPct: Double = 0
    var outerColor: RGBColor = .white
    var innerColor: RGBColor = .black
    // Textzeile / Signatur im unteren Rand
    var text = ""
    var textSize: Double = 45            // % der unteren Randhöhe
    var textPos: TextPosition = .center
    var textColor: RGBColor = .darkGray
    var textFont = ""                    // PostScript-Name, leer = Systemschrift
    // Schutz: Wasserzeichen
    var wmOn = false
    var wmText = "© {jahr}"
    var wmOpacity: Double = 35           // %
    var wmSize: Double = 5               // % der kurzen Bildkante
    var wmPos: WatermarkPosition = .bottomRight
    var wmColor: RGBColor = .white
    var wmOutline = true
    // Schutz: Metadaten
    var metaOn = false
    var metaAuthor = ""
    var metaCopyright = "© {jahr}"
    // Effekte (nur PNG)
    var cornerRadius: Double = 0         // % der kurzen Kante
    var shadow: Double = 0               // % der langen Kante
    // Ausgabe
    var format: OutputFormat = .original
    var quality: Double = 92
    var limitOn = false
    var maxEdge: Double = 2048
    var template = "{name}_rahmen"
    var conflict: ConflictMode = .number

    enum CodingKeys: String, CodingKey {
        case double, unit, outerPx, outerPct, innerPx, innerPct, bottomPx, bottomPct, outerColor, innerColor
        case text, textSize, textPos, textColor, textFont
        case wmOn, wmText, wmOpacity, wmSize, wmPos, wmColor, wmOutline
        case metaOn, metaAuthor, metaCopyright
        case cornerRadius, shadow
        case format, quality, limitOn, maxEdge, template, conflict
    }

    // Breiten der aktuell gewählten Einheit (Werte je Einheit werden getrennt gemerkt)
    var outerWidth: Double {
        get { unit == .px ? outerPx : outerPct }
        set { if unit == .px { outerPx = newValue } else { outerPct = newValue } }
    }
    var innerWidth: Double {
        get { unit == .px ? innerPx : innerPct }
        set { if unit == .px { innerPx = newValue } else { innerPct = newValue } }
    }
    var bottomExtra: Double {
        get { unit == .px ? bottomPx : bottomPct }
        set { if unit == .px { bottomPx = newValue } else { bottomPct = newValue } }
    }

    /// Einstellungswert in Pixel für ein Bild der Größe w × h.
    func toPx(_ value: Double, _ w: Int, _ h: Int) -> Int {
        guard value > 0 else { return 0 }
        if unit == .pct {
            return max(1, Int((Double(max(w, h)) * value / 100).rounded()))
        }
        return Int(value.rounded())
    }

    /// Rahmenschichten von innen nach außen (wie layers() der Desktop-Version).
    func layers(w: Int, h: Int) -> [Layer] {
        var result: [Layer] = []
        if double {
            let p = toPx(innerWidth, w, h)
            result.append(Layer(width: p, bottom: p, color: innerColor))
        }
        let p = toPx(outerWidth, w, h)
        result.append(Layer(width: p, bottom: p, color: outerColor))
        result = result.filter { $0.width > 0 }
        let extra = toPx(bottomExtra, w, h)
        if extra > 0 {
            if var last = result.popLast() {
                last.bottom += extra
                result.append(last)
            } else {
                result.append(Layer(width: 0, bottom: extra, color: outerColor))
            }
        }
        return result
    }

    /// Größe inklusive Rahmen (ohne Größenbegrenzung/Effekte).
    func framedSize(w: Int, h: Int) -> (Int, Int) {
        let ls = layers(w: w, h: h)
        return (w + ls.reduce(0) { $0 + 2 * $1.width }, h + ls.reduce(0) { $0 + $1.width + $1.bottom })
    }

    /// Lange Kante des Ergebnisses höchstens … px (0 = aus).
    var effectiveMaxEdge: Int { limitOn ? max(16, Int(maxEdge.rounded())) : 0 }

    /// Verkleinerungsfaktor für „lange Kante begrenzen“ (sonst 1).
    func limitScale(w: Int, h: Int) -> Double {
        let m = effectiveMaxEdge
        guard m > 0 else { return 1 }
        let (fw, fh) = framedSize(w: w, h: h)
        return min(1, Double(m) / Double(max(fw, fh)))
    }

    /// Gelten Ecken/Schatten für dieses Zielformat?
    func effectsActive(_ format: ImageFormat?) -> Bool {
        guard let format, format.allowsEffects else { return false }
        return cornerRadius > 0 || shadow > 0
    }

    /// Ist überhaupt etwas zu tun (Rahmen, Text, Schutz, Größe, Effekte)?
    var hasAnyEffect: Bool {
        !layers(w: 1000, h: 1000).isEmpty || effectiveMaxEdge > 0 || cornerRadius > 0 || shadow > 0
            || (wmOn && !wmText.trimmingCharacters(in: .whitespaces).isEmpty) || metaOn
    }
}

// Decodierung mit Standardwerten für fehlende Schlüssel (ältere gespeicherte Einstellungen)
extension FrameSettings {
    init(from decoder: Decoder) throws {
        self.init()
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func v<T: Decodable>(_ key: CodingKeys, _ current: T) -> T {
            (try? c.decodeIfPresent(T.self, forKey: key)) ?? current
        }
        double = v(.double, double)
        unit = v(.unit, unit)
        outerPx = v(.outerPx, outerPx)
        outerPct = v(.outerPct, outerPct)
        innerPx = v(.innerPx, innerPx)
        innerPct = v(.innerPct, innerPct)
        bottomPx = v(.bottomPx, bottomPx)
        bottomPct = v(.bottomPct, bottomPct)
        outerColor = v(.outerColor, outerColor)
        innerColor = v(.innerColor, innerColor)
        text = v(.text, text)
        textSize = v(.textSize, textSize)
        textPos = v(.textPos, textPos)
        textColor = v(.textColor, textColor)
        textFont = v(.textFont, textFont)
        wmOn = v(.wmOn, wmOn)
        wmText = v(.wmText, wmText)
        wmOpacity = v(.wmOpacity, wmOpacity)
        wmSize = v(.wmSize, wmSize)
        wmPos = v(.wmPos, wmPos)
        wmColor = v(.wmColor, wmColor)
        wmOutline = v(.wmOutline, wmOutline)
        metaOn = v(.metaOn, metaOn)
        metaAuthor = v(.metaAuthor, metaAuthor)
        metaCopyright = v(.metaCopyright, metaCopyright)
        cornerRadius = v(.cornerRadius, cornerRadius)
        shadow = v(.shadow, shadow)
        format = v(.format, format)
        quality = v(.quality, quality)
        limitOn = v(.limitOn, limitOn)
        maxEdge = v(.maxEdge, maxEdge)
        template = v(.template, template)
        conflict = v(.conflict, conflict)
    }
}

// MARK: - Mitgelieferte Voreinstellungen (wie BUILTIN_PRESETS der Desktop-Version)

enum BuiltinPresets {
    static var all: [String: FrameSettings] {
        var galerie = FrameSettings()
        galerie.double = true
        galerie.unit = .pct
        galerie.outerPct = 4
        galerie.innerPct = 0.2
        galerie.bottomPct = 2

        var schwarz = FrameSettings()
        schwarz.unit = .pct
        schwarz.outerPct = 1.5
        schwarz.outerColor = .black

        var signatur = FrameSettings()
        signatur.unit = .pct
        signatur.outerPct = 3
        signatur.bottomPct = 5
        signatur.text = "© {jahr}"
        signatur.textSize = 40
        signatur.textPos = .right

        var social = FrameSettings()
        social.unit = .pct
        social.outerPct = 3
        social.format = .jpeg
        social.quality = 92
        social.limitOn = true
        social.maxEdge = 2048

        var schutz = FrameSettings()
        schutz.unit = .pct
        schutz.outerPct = 2
        schutz.wmOn = true
        schutz.wmPos = .tile
        schutz.wmOpacity = 25
        schutz.wmSize = 4
        schutz.metaOn = true
        schutz.format = .jpeg
        schutz.quality = 90
        schutz.limitOn = true
        schutz.maxEdge = 2048

        var schatten = FrameSettings()
        schatten.unit = .pct
        schatten.outerPct = 3
        schatten.cornerRadius = 2
        schatten.shadow = 1.5
        schatten.format = .png

        return [
            "Galerie – Linie + Weiß": galerie,
            "Schwarzer Rand schmal": schwarz,
            "Signatur unten": signatur,
            "Social Media 2048 px": social,
            "Copyright-Schutz Web": schutz,
            "PNG mit Schatten": schatten,
        ]
    }
}
