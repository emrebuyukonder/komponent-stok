#!/bin/bash
# "Komponent Stok.app" uygulamasını derler. stok.py veya web/ değişince tekrar çalıştırın.
set -euo pipefail
cd "$(dirname "$0")"

APP="Komponent Stok.app"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

echo "Derleniyor…"
# Önce arm64 derlenir; Intel (x86_64) derlemesi denenir, araç zinciri desteklemiyorsa (yeni Swift
# sürümleri eski macOS hedefi için x86_64 bağlayamayabiliyor) yalnızca arm64 ile devam edilir.
build() {  # build <kaynak> <çıktı adı> <framework...>
  local src=$1 out=$2; shift 2
  local fw=() archs=()
  for f in "$@"; do fw+=(-framework "$f"); done
  swiftc -O -swift-version 5 -target arm64-apple-macos11.3 "$src" -o "$BUILD/$out-arm64" "${fw[@]}"
  archs+=("$BUILD/$out-arm64")
  if swiftc -O -swift-version 5 -target x86_64-apple-macos11.3 "$src" -o "$BUILD/$out-x86_64" "${fw[@]}" \
      2>"$BUILD/$out-x86_64.log"; then
    archs+=("$BUILD/$out-x86_64")
  else
    echo "Uyarı: $out için Intel (x86_64) derlenemedi; yalnızca Apple Silicon sürümü oluşturuluyor." >&2
  fi
  lipo -create "${archs[@]}" -output "$BUILD/$out"
}
build macos/main.swift KomponentStok Cocoa WebKit
build macos/ocr.swift ocr Vision
mkdir -p bin
cp "$BUILD/ocr" bin/ocr   # terminal sürümü (python3 stok.py) için

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
