#!/bin/bash
# "Komponent Stok.app" uygulamasını derler. stok.py veya web/ değişince tekrar çalıştırın.
set -euo pipefail
cd "$(dirname "$0")"

APP="Komponent Stok.app"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

echo "Derleniyor…"
swiftc -O -swift-version 5 -target arm64-apple-macos11.3 macos/main.swift -o "$BUILD/arm64" -framework Cocoa -framework WebKit
swiftc -O -swift-version 5 -target x86_64-apple-macos11.3 macos/main.swift -o "$BUILD/x86_64" -framework Cocoa -framework WebKit
lipo -create "$BUILD/arm64" "$BUILD/x86_64" -output "$BUILD/KomponentStok"
swiftc -O -swift-version 5 -target arm64-apple-macos11.3 macos/ocr.swift -o "$BUILD/ocr-arm64" -framework Vision
swiftc -O -swift-version 5 -target x86_64-apple-macos11.3 macos/ocr.swift -o "$BUILD/ocr-x86_64" -framework Vision
mkdir -p bin
lipo -create "$BUILD/ocr-arm64" "$BUILD/ocr-x86_64" -output bin/ocr   # terminal sürümü (python3 stok.py) için

echo "Simge çiziliyor…"
swiftc -O macos/icon.swift -o "$BUILD/icon" -framework Cocoa
"$BUILD/icon" "$BUILD/icon.png"
mkdir "$BUILD/AppIcon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BUILD/icon.png" --out "$BUILD/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$BUILD/icon.png" --out "$BUILD/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$BUILD/AppIcon.iconset" -o "$BUILD/AppIcon.icns"

echo "Paketleniyor…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/KomponentStok" "$APP/Contents/MacOS/"
cp "$BUILD/AppIcon.icns" stok.py bin/ocr "$APP/Contents/Resources/"
cp -R web "$APP/Contents/Resources/"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Komponent Stok</string>
  <key>CFBundleDisplayName</key><string>Komponent Stok</string>
  <key>CFBundleIdentifier</key><string>local.komponentstok</string>
  <key>CFBundleExecutable</key><string>KomponentStok</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleDevelopmentRegion</key><string>tr</string>
  <key>LSMinimumSystemVersion</key><string>11.3</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>Elektronik komponent stok takibi</string>
  <key>NSDocumentsFolderUsageDescription</key><string>Stok veritabanı Belgeler/Komponent Stok klasöründe tutulur.</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST
codesign --force --deep -s - "$APP"
echo "Hazır: $APP"
