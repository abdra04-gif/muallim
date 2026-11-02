// Рисует арабский текст в PNG через CoreText (правильное соединение букв).
// artext <текст> <размер> <файл> [цвет_hex] [шрифт]
import AppKit
let a = CommandLine.arguments
let text = a[1], size = CGFloat(Double(a[2])!), out = a[3]
let hex = a.count > 4 ? a[4] : "FFFFFF", fname = a.count > 5 ? a[5] : "Geeza Pro"
let v = UInt32(hex, radix: 16)!
let color = NSColor(srgbRed: CGFloat((v>>16)&255)/255, green: CGFloat((v>>8)&255)/255, blue: CGFloat(v&255)/255, alpha: 1)
let font = NSFont(name: fname, size: size) ?? NSFont.systemFont(ofSize: size)
let s = NSMutableAttributedString(string: text, attributes: [.font: font, .foregroundColor: color])
// дальше — диапазоны «начало:длина:цвет» (индексы UTF-16)
if a.count > 6 {
    for r in a[6...] {
        let p = r.split(separator: ":")
        let c = UInt32(p[2], radix: 16)!
        let col = NSColor(srgbRed: CGFloat((c>>16)&255)/255, green: CGFloat((c>>8)&255)/255, blue: CGFloat(c&255)/255, alpha: 1)
        s.addAttribute(.foregroundColor, value: col, range: NSRange(location: Int(p[0])!, length: Int(p[1])!))
    }
}
let b = s.boundingRect(with: NSSize(width: 10000, height: 10000), options: [.usesLineFragmentOrigin, .usesFontLeading])
let w = Int(ceil(b.width)) + 20, h = Int(ceil(b.height)) + 20
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
s.draw(with: NSRect(x: 10, y: 10, width: b.width, height: b.height), options: [.usesLineFragmentOrigin, .usesFontLeading])
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
