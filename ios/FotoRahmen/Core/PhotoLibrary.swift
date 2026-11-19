// -----------------------------------------------------------------------------
// FotoRahmen für iOS – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
// Idee und Prompt: Stefan J. Kaiser · Umsetzung: Claude Opus 5.5 (Anthropic), 6. November 2026
// -----------------------------------------------------------------------------
//
// Zugriff auf die Fotos-Mediathek: Originalnamen lesen, Ergebnisse in ein Album speichern.
// Originalfotos werden nie verändert – es entstehen immer neue Fotos.

import Foundation
import Photos

enum PhotoLibrary {
    /// Lese- und Schreibzugriff anfragen (für Originaldateinamen und das Album).
    static func requestAccess() async -> Bool {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        return status == .authorized || status == .limited
    }

    /// Nur-Hinzufügen-Zugriff (reicht zum Speichern ohne Album).
    static func requestAddAccess() async -> Bool {
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        return status == .authorized || status == .limited
    }

    /// Originaler Dateiname eines Fotos (z. B. „IMG_1234.HEIC“), falls Zugriff besteht.
    static func originalFilename(localIdentifier: String) -> String? {
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [localIdentifier], options: nil).firstObject
        else { return nil }
        let resources = PHAssetResource.assetResources(for: asset)
        let photo = resources.first { $0.type == .photo } ?? resources.first
        return photo?.originalFilename
    }

    private final class Box { var id: String? }

    /// Album mit diesem Namen holen oder anlegen (nil bei eingeschränktem Zugriff).
    static func album(named name: String) async -> PHAssetCollection? {
        let options = PHFetchOptions()
        options.predicate = NSPredicate(format: "title = %@", name)
        if let existing = PHAssetCollection.fetchAssetCollections(with: .album, subtype: .any, options: options).firstObject {
            return existing
        }
        let box = Box()
        do {
            try await PHPhotoLibrary.shared().performChanges {
                let request = PHAssetCollectionChangeRequest.creationRequestForAssetCollection(withTitle: name)
                box.id = request.placeholderForCreatedAssetCollection.localIdentifier
            }
        } catch {
            return nil
        }
        guard let id = box.id else { return nil }
        return PHAssetCollection.fetchAssetCollections(withLocalIdentifiers: [id], options: nil).firstObject
    }

    /// Bilddatei als neues Foto speichern (optional in einem Album).
    static func save(fileURL: URL, filename: String, album: PHAssetCollection?) async throws {
        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetCreationRequest.forAsset()
            let options = PHAssetResourceCreationOptions()
            options.originalFilename = filename
            request.addResource(with: .photo, fileURL: fileURL, options: options)
            if let album, let placeholder = request.placeholderForCreatedAsset,
               let change = PHAssetCollectionChangeRequest(for: album) {
                change.addAssets([placeholder] as NSArray)
            }
        }
    }
}
