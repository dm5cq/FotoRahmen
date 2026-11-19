// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Gemeinsamer Ablauf für Ausgabe UND Vorschau (entspricht compose() der Desktop-Version):
//
//   Bild auf Zielmaßstab ─► Rahmenschichten ─► Bild (EXIF-Drehung) ─► Wasserzeichen ins Bild
//   ─► Textzeile im unteren Rand ─► Effekte (Ecken/Schatten, nur PNG)
//
// Gezeichnet wird mit Core Graphics in einen Bitmap-Kontext, der Farbraum und – bei
// PNG/TIFF – 16 Bit je Kanal der Quelle übernimmt. Für Text und Bilddrehung wird der
// Kontext auf UIKit-Koordinaten (Ursprung oben links) umgestellt.

import CoreGraphics
import ImageIO
import UIKit

/// Wählbare Schriften für Textzeile und Wasserzeichen (PostScript-Namen, in iOS enthalten).
struct FontChoice: Identifiable, Hashable {
    let id: String     // PostScript-Name, "" = Systemschrift
    let label: String

    static let all: [FontChoice] = [
        FontChoice(id: "", label: "System (SF Pro)"),
        FontChoice(id: "HelveticaNeue", label: "Helvetica Neue"),
        FontChoice(id: "AvenirNext-Regular", label: "Avenir Next"),
        FontChoice(id: "Futura-Medium", label: "Futura"),
        FontChoice(id: "GillSans", label: "Gill Sans"),
        FontChoice(id: "Georgia", label: "Georgia"),
        FontChoice(id: "Baskerville", label: "Baskerville"),
        FontChoice(id: "Didot", label: "Didot"),
        FontChoice(id: "SnellRoundhand", label: "Snell Roundhand (Signatur)"),
        FontChoice(id: "Zapfino", label: "Zapfino (Signatur)"),
    ]

    static func font(named name: String, size: CGFloat) -> UIFont {
        if !name.isEmpty, let f = UIFont(name: name, size: size) { return f }
        return UIFont.systemFont(ofSize: size, weight: .medium)
    }
}

enum FrameRenderer {

    /// Maße eines Ergebnisses.
    struct Geometry {
        var imageW: Int
        var imageH: Int
        var layers: [Layer]
        var frameW: Int
        var frameH: Int
        var radius: Int
        var shadow: Int
        var pad: Int
        var canvasW: Int { frameW + 2 * pad }
        var canvasH: Int { frameH + 2 * pad }
    }

    /// Geometrie für ein Bild der (gedrehten) Größe w × h im Maßstab `scale`.
    static func geometry(settings: FrameSettings, w: Int, h: Int, scale: Double, effects: Bool) -> Geometry {
        var layers = settings.layers(w: w, h: h)
        if scale != 1 {
            func sc(_ v: Int) -> Int { v > 0 ? max(1, Int((Double(v) * scale).rounded())) : 0 }
            layers = layers.map { Layer(width: sc($0.width), bottom: sc($0.bottom), color: $0.color) }
        }
        let iw = max(1, Int((Double(w) * scale).rounded()))
        let ih = max(1, Int((Double(h) * scale).rounded()))
        let fw = iw + layers.reduce(0) { $0 + 2 * $1.width }
        let fh = ih + layers.reduce(0) { $0 + $1.width + $1.bottom }
        var radius = 0
        var shadow = 0
        if effects {
            radius = Int((Double(min(fw, fh)) * min(settings.cornerRadius, 50) / 100).rounded())
            shadow = Int((Double(max(fw, fh)) * min(settings.shadow, 25) / 100).rounded())
        }
        return Geometry(imageW: iw, imageH: ih, layers: layers, frameW: fw, frameH: fh,
                        radius: radius, shadow: shadow, pad: 2 * shadow)
    }

    /// Voraussichtliche Größe der Ausgabedatei (Breite, Höhe).
    static func outputSize(settings: FrameSettings, w: Int, h: Int, format: ImageFormat?) -> (Int, Int) {
        let g = geometry(settings: settings, w: w, h: h, scale: settings.limitScale(w: w, h: h),
                         effects: settings.effectsActive(format))
        var cw = g.canvasW
        var ch = g.canvasH
        let m = settings.effectiveMaxEdge
        if m > 0, max(cw, ch) > m {
            let k = Double(m) / Double(max(cw, ch))
            cw = max(1, Int((Double(cw) * k).rounded()))
            ch = max(1, Int((Double(ch) * k).rounded()))
        }
        return (cw, ch)
    }

    // MARK: Zeichnen

    /// Bitmap-Kontext erzeugen – mit Rückfall auf 8-Bit-sRGB, falls die Kombination nicht unterstützt wird.
    private static func makeContext(width: Int, height: Int, colorSpace: CGColorSpace, gray: Bool,
                                    sixteenBit: Bool) -> CGContext? {
        var attempts: [(CGColorSpace, Int, UInt32)] = []
        if gray {
            attempts.append((colorSpace, sixteenBit ? 16 : 8, CGImageAlphaInfo.none.rawValue))
            attempts.append((colorSpace, 8, CGImageAlphaInfo.none.rawValue))
        } else {
            if sixteenBit { attempts.append((colorSpace, 16, CGImageAlphaInfo.premultipliedLast.rawValue)) }
            attempts.append((colorSpace, 8, CGImageAlphaInfo.premultipliedLast.rawValue))
        }
        if let srgb = CGColorSpace(name: CGColorSpace.sRGB) {
            attempts.append((srgb, 8, CGImageAlphaInfo.premultipliedLast.rawValue))
        }
        for (space, bits, info) in attempts {
            if let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: bits,
                                   bytesPerRow: 0, space: space, bitmapInfo: info) {
                return ctx
            }
        }
        return nil
    }

    /// Bild mit Rahmen, Text, Wasserzeichen und Effekten erzeugen.
    ///
    /// - Parameters:
    ///   - image: Quellbild (ungedreht; `orientation` wird beim Zeichnen angewendet)
    ///   - origSize: gedrehte Originalgröße – darauf beziehen sich alle Einstellungen
    ///   - scale: Maßstab (Größenbegrenzung bzw. Vorschau); `image` darf kleiner sein als origSize
    ///   - format: Zielformat (Effekte nur PNG, Weißfüllung bei Formaten ohne Transparenz)
    ///   - keep16Bit: 16 Bit je Kanal beibehalten, wenn die Quelle 16 Bit hat
    static func render(image: CGImage, orientation: CGImagePropertyOrientation, origSize: (Int, Int),
                       scale: Double, settings: FrameSettings, format: ImageFormat?, values: TextValues,
                       keep16Bit: Bool) -> CGImage? {
        let effects = settings.effectsActive(format)
        let g = geometry(settings: settings, w: origSize.0, h: origSize.1, scale: scale, effects: effects)

        // Farbraum der Quelle übernehmen (RGB/Grau), sonst sRGB (z. B. CMYK)
        let srgb = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        var space = srgb
        var gray = false
        if let cs = image.colorSpace, cs.supportsOutput {
            if cs.model == .rgb {
                space = cs
            } else if cs.model == .monochrome && !effects {
                space = cs
                gray = true
            }
        }
        let sixteen = keep16Bit && image.bitsPerComponent >= 16
        guard let ctx = makeContext(width: g.canvasW, height: g.canvasH, colorSpace: space, gray: gray,
                                    sixteenBit: sixteen) else { return nil }
        ctx.interpolationQuality = .high
        ctx.setShouldAntialias(true)

        // UIKit-Koordinaten: Ursprung oben links
        ctx.translateBy(x: 0, y: CGFloat(g.canvasH))
        ctx.scaleBy(x: 1, y: -1)
        UIGraphicsPushContext(ctx)
        defer { UIGraphicsPopContext() }

        let frameRect = CGRect(x: g.pad, y: g.pad, width: g.frameW, height: g.frameH)
        let framePath = UIBezierPath(roundedRect: frameRect, cornerRadius: CGFloat(g.radius))

        // 1. Schatten (nur PNG): schwarze Fläche mit Schatten unter dem Bild
        if g.shadow > 0 {
            ctx.saveGState()
            let off = CGFloat(max(1, g.shadow / 2))
            // Schatten-Versatz gilt im Geräteraum (y nach oben) → negativ = nach unten
            ctx.setShadow(offset: CGSize(width: off, height: -off), blur: CGFloat(g.shadow),
                          color: UIColor.black.withAlphaComponent(0.55).cgColor)
            ctx.setFillColor(UIColor.black.cgColor)
            ctx.addPath(framePath.cgPath)
            ctx.fillPath()
            ctx.restoreGState()
        }

        ctx.saveGState()
        if g.radius > 0 {
            ctx.addPath(framePath.cgPath)
            ctx.clip()
        }

        // 2. Rahmenschichten von außen nach innen füllen
        var rect = frameRect
        for layer in g.layers.reversed() {
            ctx.setFillColor(layer.color.cgColor())
            ctx.fill(rect)
            rect = CGRect(x: rect.minX + CGFloat(layer.width), y: rect.minY + CGFloat(layer.width),
                          width: rect.width - CGFloat(2 * layer.width),
                          height: rect.height - CGFloat(layer.width + layer.bottom))
        }
        let imageRect = CGRect(x: rect.minX, y: rect.minY, width: CGFloat(g.imageW), height: CGFloat(g.imageH))

        // 3. Bild (Transparenz bei Formaten ohne Alpha auf Weiß legen)
        if let format, !format.supportsAlpha {
            ctx.setFillColor(UIColor.white.cgColor)
            ctx.fill(imageRect)
        }
        UIImage(cgImage: image, scale: 1, orientation: orientation.uiOrientation).draw(in: imageRect)

        // 4. Wasserzeichen ins Bild (Copyright-Schutz)
        if settings.wmOn {
            let wm = values.expand(settings.wmText).trimmingCharacters(in: .whitespaces)
            if !wm.isEmpty { drawWatermark(wm, in: imageRect, context: ctx, settings: settings) }
        }

        // 5. Textzeile im unteren Rand der äußersten Schicht
        let text = values.expand(settings.text).trimmingCharacters(in: .whitespaces)
        if !text.isEmpty, let last = g.layers.last {
            drawTextLine(text, frame: frameRect, bandHeight: CGFloat(last.bottom),
                         side: CGFloat(g.layers.reduce(0) { $0 + $1.width }), settings: settings)
        }
        ctx.restoreGState()
        return ctx.makeImage()
    }

    /// Textzeile/Signatur vertikal mittig im unteren Rand; links/rechts bündig mit der Bildkante.
    private static func drawTextLine(_ text: String, frame: CGRect, bandHeight: CGFloat, side: CGFloat,
                                     settings: FrameSettings) {
        guard bandHeight >= 3 else { return }
        let fontPx = bandHeight * CGFloat(min(max(settings.textSize, 1), 100)) / 100
        guard fontPx >= 2 else { return }
        let font = FontChoice.font(named: settings.textFont, size: fontPx)
        let attr = NSAttributedString(string: text, attributes: [
            .font: font, .foregroundColor: settings.textColor.uiColor(),
        ])
        let size = attr.size()
        let band = CGRect(x: frame.minX, y: frame.maxY - bandHeight, width: frame.width, height: bandHeight)
        let margin = max(side, fontPx / 2)
        let x: CGFloat
        switch settings.textPos {
        case .left: x = band.minX + margin
        case .right: x = band.maxX - margin - size.width
        case .center: x = band.midX - size.width / 2
        }
        attr.draw(at: CGPoint(x: x, y: band.midY - size.height / 2))
    }

    /// Transparentes Wasserzeichen – Ecke, Mitte oder diagonal (30°) über das ganze Bild wiederholt.
    private static func drawWatermark(_ text: String, in rect: CGRect, context ctx: CGContext,
                                      settings s: FrameSettings) {
        let short = min(rect.width, rect.height)
        let fontPx = max(6, short * CGFloat(min(max(s.wmSize, 0.5), 50)) / 100)
        let font = FontChoice.font(named: s.textFont, size: fontPx)
        let alpha = CGFloat(min(max(s.wmOpacity, 1), 100)) / 100
        let fill = NSAttributedString(string: text, attributes: [
            .font: font, .foregroundColor: s.wmColor.uiColor(alpha: alpha),
        ])
        // Kontrastkante erst ab lesbarer Schriftgröße (sonst wirkt kleiner Text grau)
        let outline: NSAttributedString? = (s.wmOutline && fontPx >= 14) ? NSAttributedString(string: text, attributes: [
            .font: font, .strokeColor: s.wmColor.contrast.uiColor(alpha: alpha * 0.55), .strokeWidth: 12.0,
        ]) : nil
        let size = fill.size()

        func draw(at p: CGPoint) {
            outline?.draw(at: p)
            fill.draw(at: p)
        }

        ctx.saveGState()
        ctx.clip(to: rect)
        if s.wmPos == .tile {
            ctx.translateBy(x: rect.midX, y: rect.midY)
            ctx.rotate(by: -.pi / 6)                    // 30° ansteigend
            let du = size.width * 1.6 + fontPx * 2
            let dv = max(size.height * 4, 1)
            let reach = Int(hypot(rect.width, rect.height) / min(du, dv)) + 2
            for j in -reach...reach {
                for i in -reach...reach {
                    let u = CGFloat(i) * du + (j % 2 != 0 ? du / 2 : 0)
                    let v = CGFloat(j) * dv
                    draw(at: CGPoint(x: u - size.width / 2, y: v - size.height / 2))
                }
            }
        } else {
            let margin = short * 0.03
            let x: CGFloat
            let y: CGFloat
            switch s.wmPos {
            case .bottomLeft, .topLeft: x = rect.minX + margin
            case .bottomRight, .topRight: x = rect.maxX - margin - size.width
            default: x = rect.midX - size.width / 2
            }
            switch s.wmPos {
            case .topLeft, .topRight: y = rect.minY + margin
            case .bottomLeft, .bottomRight: y = rect.maxY - margin - size.height
            default: y = rect.midY - size.height / 2
            }
            draw(at: CGPoint(x: x, y: y))
        }
        ctx.restoreGState()
    }

    /// Ergebnis verkleinern, falls die lange Kante `maxEdge` überschreitet.
    static func resized(_ image: CGImage, maxEdge: Int) -> CGImage {
        let m = max(image.width, image.height)
        guard maxEdge > 0, m > maxEdge else { return image }
        let k = Double(maxEdge) / Double(m)
        let w = max(1, Int((Double(image.width) * k).rounded()))
        let h = max(1, Int((Double(image.height) * k).rounded()))
        guard let space = image.colorSpace,
              let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: image.bitsPerComponent,
                                  bytesPerRow: 0, space: space, bitmapInfo: image.bitmapInfo.rawValue)
        else { return image }
        ctx.interpolationQuality = .high
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        return ctx.makeImage() ?? image
    }

    // MARK: Vorschau und Datei

    /// Vorschau, passend in `box` (Pixel) – gleiche Proportionen wie das Ergebnis.
    static func preview(source: PreviewSource, settings: FrameSettings, box: CGSize, format: ImageFormat?,
                        values: TextValues) -> CGImage? {
        let (fw, fh) = settings.framedSize(w: source.width, h: source.height)
        let pad = settings.effectsActive(format) ? 4 * Double(max(fw, fh)) * min(settings.shadow, 25) / 100 : 0
        let scale = max(min(Double(box.width) / (Double(fw) + pad), Double(box.height) / (Double(fh) + pad)), 1e-4)
        return render(image: source.image, orientation: .up, origSize: (source.width, source.height), scale: scale,
                      settings: settings, format: format, values: values, keep16Bit: false)
    }

    /// Eine Datei verarbeiten und speichern. Rückgabe: Größe des Ergebnisses.
    static func process(source url: URL, destination: URL, format: ImageFormat, settings: FrameSettings,
                        values: TextValues) throws -> (Int, Int) {
        let loaded = try ImageIOHelpers.load(url: url)
        let (w, h) = loaded.orientedSize
        guard var out = render(image: loaded.image, orientation: loaded.orientation, origSize: (w, h),
                               scale: settings.limitScale(w: w, h: h), settings: settings, format: format,
                               values: values, keep16Bit: format.keeps16Bit)
        else { throw RenderError.renderFailed }
        out = resized(out, maxEdge: settings.effectiveMaxEdge)
        try ImageIOHelpers.write(out, to: destination, format: format, sourceProperties: loaded.properties,
                                 settings: settings, values: values)
        return (out.width, out.height)
    }
}
