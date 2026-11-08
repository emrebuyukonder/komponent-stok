// Komponent Stok — macOS uygulama kabuğu.
// Uygulama paketindeki stok.py sunucusunu arka planda başlatır ve arayüzü kendi penceresinde gösterir.
import Cocoa
import WebKit

let dataDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/Komponent Stok")

let loadingHTML = """
<html><head><meta charset="utf-8"><style>
html,body{height:100%;margin:0;display:flex;align-items:center;justify-content:center;
font:15px -apple-system,sans-serif;color:#6a7385;background:#f5f6f8}
@media (prefers-color-scheme: dark){html,body{background:#12151b;color:#9098a8}}
</style></head><body>Başlatılıyor…</body></html>
"""

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var server: Process?
    var output = ""
    var loaded = false
    var quitting = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        webView.navigationDelegate = self
        webView.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Komponent Stok"
        window.minSize = NSSize(width: 720, height: 480)
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("AnaPencere")
        window.makeKeyAndOrderFront(nil)
        webView.loadHTMLString(loadingHTML, baseURL: nil)
        NSApp.activate(ignoringOtherApps: true)
        startServer()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        server?.terminate()
    }

    // MARK: Python sunucusu

    func findPython() -> String? {
        let candidates = [
            "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    func startServer() {
        guard let python = findPython() else {
            fatal("Python 3 bulunamadı. python.org adresinden Python 3 kurup uygulamayı yeniden açın.")
            return
        }
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        let script = Bundle.main.resourceURL!.appendingPathComponent("stok.py").path
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-u", script, "--no-browser"]
        var env = ProcessInfo.processInfo.environment
        env["STOK_DB"] = dataDir.appendingPathComponent("stok.db").path
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty else { h.readabilityHandler = nil; return }
            let s = String(decoding: d, as: UTF8.self)
            DispatchQueue.main.async { self?.handleOutput(s) }
        }
        p.terminationHandler = { [weak self] proc in
            DispatchQueue.main.async { self?.serverExited(proc.terminationStatus) }
        }
        do {
            try p.run()
            server = p
        } catch {
            fatal("Sunucu başlatılamadı: \(error.localizedDescription)")
        }
    }

    func handleOutput(_ s: String) {
        output += s
        if output.count > 20000 { output = String(output.suffix(10000)) }
        guard !loaded,
              let r = output.range(of: #"http://127\.0\.0\.1:\d+"#, options: .regularExpression),
              let url = URL(string: String(output[r])) else { return }
        loaded = true
        webView.load(URLRequest(url: url))
    }

    func serverExited(_ status: Int32) {
        if quitting { return }
        fatal("Arka plandaki sunucu beklenmedik şekilde kapandı (kod \(status)).\n\n" + String(output.suffix(1500)))
    }

    func fatal(_ message: String) {
        let a = NSAlert()
        a.alertStyle = .critical
        a.messageText = "Komponent Stok çalıştırılamadı"
        a.informativeText = message
        a.addButton(withTitle: "Kapat")
        a.runModal()
        quitting = true
        NSApp.terminate(nil)
    }

    // MARK: Menü

    func buildMenu() {
        let main = NSMenu()

        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Komponent Stok Hakkında",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Veri klasörünü Finder'da göster", action: #selector(showData), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Komponent Stok'u Gizle", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Komponent Stok'tan Çık", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        addSubmenu(appMenu, to: main)

        let edit = NSMenu(title: "Düzen")
        edit.addItem(withTitle: "Geri Al", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = edit.addItem(withTitle: "Yinele", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "Kes", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Kopyala", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Yapıştır", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Tümünü Seç", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        addSubmenu(edit, to: main)

        let view = NSMenu(title: "Görünüm")
        view.addItem(withTitle: "Yenile", action: #selector(reload), keyEquivalent: "r")
        addSubmenu(view, to: main)

        let win = NSMenu(title: "Pencere")
        win.addItem(withTitle: "Küçült", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Büyüt", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        win.addItem(withTitle: "Kapat", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        addSubmenu(win, to: main)
        NSApp.windowsMenu = win

        NSApp.mainMenu = main
    }

    func addSubmenu(_ menu: NSMenu, to main: NSMenu) {
        let item = NSMenuItem()
        item.submenu = menu
        main.addItem(item)
    }

    @objc func showData() {
        let db = dataDir.appendingPathComponent("stok.db")
        if FileManager.default.fileExists(atPath: db.path) {
            NSWorkspace.shared.activateFileViewerSelecting([db])
        } else {
            NSWorkspace.shared.open(dataDir)
        }
    }

    @objc func reload() { if loaded { webView.reload() } }

    // MARK: JavaScript diyalogları ve dosya seçici

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "Tamam")
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "Tamam")
        a.addButton(withTitle: "Vazgeç")
        a.beginSheetModal(for: window) { r in completionHandler(r == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { r in completionHandler(r == .OK ? panel.urls : nil) }
    }

    // MARK: Bağlantılar ve indirmeler (CSV dışa aktarma, eksik listesi)

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.shouldPerformDownload {
            decisionHandler(.download)
            return
        }
        if let url = navigationAction.request.url, navigationAction.navigationType == .linkActivated,
           url.scheme?.hasPrefix("http") == true, url.host != "127.0.0.1" {
            NSWorkspace.shared.open(url)  // dış bağlantılar varsayılan tarayıcıda açılır
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let http = navigationResponse.response as? HTTPURLResponse,
           let cd = http.value(forHTTPHeaderField: "Content-Disposition"), cd.contains("attachment") {
            decisionHandler(.download)
            return
        }
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        panel.beginSheetModal(for: window) { r in
            guard r == .OK, let url = panel.url else { completionHandler(nil); return }
            try? FileManager.default.removeItem(at: url)  // üzerine yazma panelde onaylandı
            completionHandler(url)
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let a = NSAlert()
        a.messageText = "Dosya kaydedilemedi"
        a.informativeText = error.localizedDescription
        a.beginSheetModal(for: window)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
