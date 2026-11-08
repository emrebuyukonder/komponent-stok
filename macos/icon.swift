// Uygulama simgesini çizer: swift icon.swift cikti.png
import Cocoa

let size: CGFloat = 1024
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext

// Arka plan
let bgRect = CGRect(x: 100, y: 100, width: 824, height: 824)
let bg = NSBezierPath(roundedRect: bgRect, xRadius: 185, yRadius: 185)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -14), blur: 34, color: NSColor.black.withAlphaComponent(0.3).cgColor)
NSColor.black.setFill()
bg.fill()
ctx.restoreGState()
NSGradient(starting: NSColor(calibratedRed: 0.27, green: 0.50, blue: 0.98, alpha: 1),
           ending: NSColor(calibratedRed: 0.11, green: 0.20, blue: 0.58, alpha: 1))!.draw(in: bg, angle: -90)

// Entegre bacakları
let chip = CGRect(x: 312, y: 312, width: 400, height: 400)
NSColor(calibratedWhite: 0.93, alpha: 1).setFill()
for i in 0..<4 {
    let c = chip.minX + chip.width * (CGFloat(i) + 0.5) / 4
    let w: CGFloat = 38, l: CGFloat = 86
    for r in [CGRect(x: c - w / 2, y: chip.maxY - 10, width: w, height: l),
              CGRect(x: c - w / 2, y: chip.minY - l + 10, width: w, height: l),
              CGRect(x: chip.minX - l + 10, y: c - w / 2, width: l, height: w),
              CGRect(x: chip.maxX - 10, y: c - w / 2, width: l, height: w)] {
        NSBezierPath(roundedRect: r, xRadius: 10, yRadius: 10).fill()
    }
}

// Entegre gövdesi
NSColor(calibratedRed: 0.10, green: 0.12, blue: 0.17, alpha: 1).setFill()
NSBezierPath(roundedRect: chip, xRadius: 46, yRadius: 46).fill()
NSColor(calibratedWhite: 1, alpha: 0.25).setFill()
NSBezierPath(ovalIn: CGRect(x: chip.minX + 36, y: chip.maxY - 76, width: 40, height: 40)).fill()

// Stok çubukları
let bars: [(CGFloat, NSColor)] = [
    (250, NSColor(calibratedRed: 0.37, green: 0.86, blue: 0.56, alpha: 1)),
    (180, NSColor(calibratedRed: 0.37, green: 0.86, blue: 0.56, alpha: 1)),
    (110, NSColor(calibratedRed: 0.98, green: 0.72, blue: 0.33, alpha: 1)),
]
for (i, (w, color)) in bars.enumerated() {
    color.setFill()
    let y = chip.midY + 40 - CGFloat(i) * 78
    NSBezierPath(roundedRect: CGRect(x: chip.minX + 72, y: y - 22, width: w, height: 44), xRadius: 22, yRadius: 22).fill()
}

NSGraphicsContext.restoreGraphicsState()
let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon.png"
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
