// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Lesen und Schreiben von Bilddateien über ImageIO – inklusive EXIF, GPS,
// Farbprofil, DPI sowie Urheber/Copyright (TIFF, IPTC, PNG).

import Foundation
import ImageIO
import UIKit
import UniformTypeIdentifiers

enum RenderError: LocalizedError {
    case unreadable
    case renderFailed
    case writeFailed
    case notAvailableOffline

    var errorDescription: String? {
        switch self {
        case .unreadable: return "Datei ist beschädigt oder kein unterstütztes Bild"
        case .renderFailed: return "Bild konnte nicht verarbeitet werden (zu wenig Speicher?)"
        case .writeFailed: return "Datei konnte nicht gespeichert werden"
        case .notAvailableOffline: return "Datei ist nicht auf dem Gerät (iCloud) – bitte zuerst laden"
        }
    }
}

/// Ein vollständig geladenes Quellbild.
struct LoadedImage {
    let image: CGImage
    let orientation: CGImagePropertyOrientation
    let properties: [String: Any]
    /// Größe nach Anwendung der EXIF-Drehung (Breite, Höhe).
    let orientedSize: (Int, Int)
}

/// Verkleinertes, bereits gedrehtes Vorschaubild + Originalgröße.
struct PreviewSource {
    let image: CGImage
    let width: Int
    let height: Int
}

extension CGImagePropertyOrientation {
    var swapsSides: Bool { self == .left || self == .leftMirrored || self == .right || self == .rightMirrored }

    var uiOrientation: UIImage.Orientation {
        switch self {
        case .up: return .up
        case .upMirrored: return .upMirrored
        case .down: return .down
        case .downMirrored: return .downMirrored
        case .left: return .left
        case .leftMirrored: return .leftMirrored
        case .right: return .right
        case .rightMirrored: return .rightMirrored
        }
    }
}

enum ImageIOHelpers {
    private static func orientation(of props: [String: Any]) -> CGImagePropertyOrientation {
        let raw = (props[kCGImagePropertyOrientation as String] as? NSNumber)?.uint32Value ?? 1
        return CGImagePropertyOrientation(rawValue: raw) ?? .up
    }

    private static func source(_ url: URL) -> CGImageSource? {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil), CGImageSourceGetCount(src) > 0 else {
            return nil
        }
        return src
    }

    /// Quellbild in voller Auflösung laden (Bittiefe und Farbraum bleiben erhalten).
    static func load(url: URL) throws -> LoadedImage {
        guard let src = source(url) else {
            if url.lastPathComponent.hasSuffix(".icloud") { throw RenderError.notAvailableOffline }
            throw RenderError.unreadable
        }
        let props = (CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any]) ?? [:]
        let options = [kCGImageSourceShouldCacheImmediately: true] as CFDictionary
        guard let image = CGImageSourceCreateImageAtIndex(src, 0, options) else { throw RenderError.unreadable }
        let o = orientation(of: props)
        let size = o.swapsSides ? (image.height, image.width) : (image.width, image.height)
        return LoadedImage(image: image, orientation: o, properties: props, orientedSize: size)
    }

    /// Schnelles, gedrehtes Vorschaubild (max. `maxPixel` lange Kante) + Originalgröße.
    static func previewSource(url: URL, maxPixel: Int) -> PreviewSource? {
        guard let src = source(url) else { return nil }
        let props = (CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any]) ?? [:]
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixel,
        ]
        guard let thumb = CGImageSourceCreateThumbnailAtIndex(src, 0, options as CFDictionary) else { return nil }
        var w = (props[kCGImagePropertyPixelWidth as String] as? NSNumber)?.intValue ?? thumb.width
        var h = (props[kCGImagePropertyPixelHeight as String] as? NSNumber)?.intValue ?? thumb.height
        if orientation(of: props).swapsSides { swap(&w, &h) }
        return PreviewSource(image: thumb, width: w, height: h)
    }

    /// Kleines Vorschaubild für die Bilderleiste.
    static func thumbnail(url: URL, maxPixel: Int = 240) -> UIImage? {
        guard let p = previewSource(url: url, maxPixel: maxPixel) else { return nil }
        return UIImage(cgImage: p.image)
    }

    /// Dateiendung passend zum Inhalt (für Fotos aus der Mediathek / Drag & Drop).
    static func preferredExtension(for data: Data) -> String? {
        guard let src = CGImageSourceCreateWithData(data as CFData, nil),
              let type = CGImageSourceGetType(src) as String?,
              let ut = UTType(type) else { return nil }
        return ut.preferredFilenameExtension
    }

    /// Bild schreiben – zuerst als temporäre Datei, dann umbenennen (Originale bleiben unberührt).
    static func write(_ image: CGImage, to url: URL, format: ImageFormat, sourceProperties: [String: Any],
                      settings: FrameSettings, values: TextValues) throws {
        let fm = FileManager.default
        let dir = url.deletingLastPathComponent()
        try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        let stem = (url.lastPathComponent as NSString).deletingPathExtension
        let tmp = dir.appendingPathComponent(".\(stem).fotorahmen-tmp.\(url.pathExtension)")
        try? fm.removeItem(at: tmp)
        defer { try? fm.removeItem(at: tmp) }

        guard let dest = CGImageDestinationCreateWithURL(tmp as CFURL, format.utType.identifier as CFString, 1, nil)
        else { throw RenderError.writeFailed }
        let props = metadata(for: image, format: format, source: sourceProperties, settings: settings, values: values)
        CGImageDestinationAddImage(dest, image, props as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { throw RenderError.writeFailed }

        if fm.fileExists(atPath: url.path) {
            _ = try fm.replaceItemAt(url, withItemAt: tmp)
        } else {
            try fm.moveItem(at: tmp, to: url)
        }
    }

    /// Metadaten der Ausgabe: EXIF/GPS/IPTC/TIFF/DPI der Quelle, Orientierung = 1
    /// (Pixel sind bereits gedreht), dazu Urheber und Copyright.
    static func metadata(for image: CGImage, format: ImageFormat, source: [String: Any],
                         settings: FrameSettings, values: TextValues) -> [String: Any] {
        var props: [String: Any] = [:]
        let copyKeys = [kCGImagePropertyExifDictionary, kCGImagePropertyGPSDictionary, kCGImagePropertyIPTCDictionary,
                        kCGImagePropertyDPIWidth, kCGImagePropertyDPIHeight]
        for key in copyKeys {
            if let value = source[key as String] { props[key as String] = value }
        }
        props[kCGImagePropertyOrientation as String] = 1

        var tiff = (source[kCGImagePropertyTIFFDictionary as String] as? [String: Any]) ?? [:]
        tiff[kCGImagePropertyTIFFOrientation as String] = 1
        var exif = (props[kCGImagePropertyExifDictionary as String] as? [String: Any]) ?? [:]
        exif[kCGImagePropertyExifPixelXDimension as String] = image.width
        exif[kCGImagePropertyExifPixelYDimension as String] = image.height
        props[kCGImagePropertyExifDictionary as String] = exif
        var iptc = (props[kCGImagePropertyIPTCDictionary as String] as? [String: Any]) ?? [:]
        var png: [String: Any] = [:]

        if settings.metaOn {
            let author = values.expand(settings.metaAuthor).trimmingCharacters(in: .whitespaces)
            let copyright = values.expand(settings.metaCopyright).trimmingCharacters(in: .whitespaces)
            if !author.isEmpty {
                tiff[kCGImagePropertyTIFFArtist as String] = author
                iptc[kCGImagePropertyIPTCByline as String] = [author]
                png[kCGImagePropertyPNGAuthor as String] = author
            }
            if !copyright.isEmpty {
                tiff[kCGImagePropertyTIFFCopyright as String] = copyright
                iptc[kCGImagePropertyIPTCCopyrightNotice as String] = copyright
                png[kCGImagePropertyPNGCopyright as String] = copyright
            }
        }
        props[kCGImagePropertyTIFFDictionary as String] = tiff
        if !iptc.isEmpty { props[kCGImagePropertyIPTCDictionary as String] = iptc }
        if format == .png, !png.isEmpty { props[kCGImagePropertyPNGDictionary as String] = png }
        if format.isLossy {
            props[kCGImageDestinationLossyCompressionQuality as String] = min(max(settings.quality, 1), 100) / 100
        }
        return props
    }
}
