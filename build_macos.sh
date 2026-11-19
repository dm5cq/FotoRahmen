#!/bin/bash
# FotoRahmen – Copyright (c) 2026 Stefan J. Kaiser – Lizenz: GPL v3
# Baut FotoRahmen.app im Ordner dist/ (plus FotoRahmen-macOS.zip zum Weitergeben)
# Voraussetzung: Python 3.12 oder neuer von python.org
set -e
cd "$(dirname "$0")"

if [ -z "$SKIP_SETUP" ]; then
  python3 -m pip install --upgrade pip
  python3 -m pip install -r requirements.txt pyinstaller
  python3 selftest.py
fi

python3 -m PyInstaller --noconfirm --clean --windowed \
  --name FotoRahmen \
  --icon assets/icon.icns \
  --add-data "assets:assets" \
  --osx-bundle-identifier de.fotorahmen.app \
  --collect-all pillow_heif \
  --collect-submodules imagecodecs \
  --collect-all tkinterdnd2 \
  fotorahmen.py

APP="dist/FotoRahmen.app"
PLIST="$APP/Contents/Info.plist"
# Dunkles Design: Fenster folgen nicht zwangsweise dem hellen Erscheinungsbild
/usr/libexec/PlistBuddy -c "Add :NSRequiresAquaSystemAppearance bool false" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :NSRequiresAquaSystemAppearance false" "$PLIST"
VERSION=$(python3 -c "import app_info; print(app_info.VERSION)")
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string © 2026 Stefan J. Kaiser" "$PLIST" 2>/dev/null || true
# Nach der Änderung neu (ad-hoc) signieren, sonst startet die App auf Apple-Silicon-Macs nicht
codesign --force --deep --sign - "$APP"

cd dist
rm -f FotoRahmen-macOS.zip
ditto -c -k --keepParent FotoRahmen.app FotoRahmen-macOS.zip
echo
echo "Fertig: dist/FotoRahmen.app  (und dist/FotoRahmen-macOS.zip)"
