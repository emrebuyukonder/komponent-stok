// Fotoğraftaki / PDF'teki metni macOS Vision ile okur ve JSON olarak yazar.
// Kullanım: ocr <resim-veya-pdf>
// Çıktı: {"pages": [[{"text": "...", "x": .., "y": .., "w": .., "h": .., "conf": ..}, ...], ...]}
// (koordinatlar 0-1, sol üst köşe orijin; resimler tek sayfalıdır)
import CoreGraphics
import Foundation
import ImageIO
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

func recognize(_ image: CGImage, orientation: CGImagePropertyOrientation = .up) -> [[String: Any]] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false  // parça kodlarını "düzeltmesin"
    if #available(macOS 12, *) {
        let langs = (try? request.supportedRecognitionLanguages()) ?? []
        request.recognitionLanguages = ["tr-TR", "en-US"].filter { langs.contains($0) }
    }
    do {
        try VNImageRequestHandler(cgImage: image, orientation: orientation, options: [:]).perform([request])
    } catch {
        fail("Metin tanıma başarısız: \(error.localizedDescription)")
    }
    var out: [[String: Any]] = []
    for obs in request.results ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        let b = obs.boundingBox
        out.append(["text": cand.string, "conf": cand.confidence,
                    "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
    }
    return out
}

// PDF sayfasını beyaz zemin üzerine yüksek çözünürlükte (uzun kenar ~3000 px) çizer.
func render(_ page: CGPDFPage) -> CGImage? {
    let box = page.getBoxRect(.cropBox)
    let rotated = page.rotationAngle % 180 != 0
    let (pw, ph) = rotated ? (box.height, box.width) : (box.width, box.height)
    let scale = min(4.0, 3000 / max(pw, ph))
    let w = Int(pw * scale), h = Int(ph * scale)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.interpolationQuality = .high
    // getDrawingTransform sayfayı büyütmez; önce ölçekle, sonra sayfayı 1:1 alana oturt.
    ctx.scaleBy(x: scale, y: scale)
    ctx.concatenate(page.getDrawingTransform(.cropBox, rect: CGRect(x: 0, y: 0, width: pw, height: ph),
                                             rotate: 0, preserveAspectRatio: true))
    ctx.drawPDFPage(page)
    return ctx.makeImage()
}

guard CommandLine.arguments.count > 1 else { fail("Kullanım: ocr <resim-veya-pdf>") }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
var pages: [[[String: Any]]] = []

let head = (try? FileHandle(forReadingFrom: url).readData(ofLength: 5)) ?? Data()
if head == Data("%PDF-".utf8) {
    guard let doc = CGPDFDocument(url as CFURL) else { fail("PDF açılamadı.") }
    if doc.isEncrypted && !doc.unlockWithPassword("") { fail("PDF şifreli, açılamadı.") }
    let count = min(doc.numberOfPages, 30)
    for i in 1...max(count, 1) {
        guard let page = doc.page(at: i), let img = render(page) else { continue }
        pages.append(recognize(img))
    }
} else {
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(src, 0, nil) else { fail("Resim açılamadı.") }
    var orientation = CGImagePropertyOrientation.up
    if let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
       let raw = props[kCGImagePropertyOrientation] as? UInt32,
       let o = CGImagePropertyOrientation(rawValue: raw) {
        orientation = o
    }
    pages.append(recognize(image, orientation: orientation))
}

let data = try! JSONSerialization.data(withJSONObject: ["pages": pages], options: [])
FileHandle.standardOutput.write(data)
