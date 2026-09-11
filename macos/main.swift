// ASCENT - native macOS shell around the bundled Streamlit calculation engine.
//
// The app is self-contained: the Python sources live inside the bundle at
// Contents/Resources/app, and the Python environment is created once, on first
// launch, in ~/Library/Application Support/ASCENT. Nothing outside the bundle
// needs to exist beforehand except a Python 3.9+ interpreter.

import Cocoa
import Darwin
import WebKit

// MARK: - Paths

let bundleAppPath = Bundle.main.resourcePath! + "/app"
let supportDir = NSHomeDirectory() + "/Library/Application Support/ASCENT"
let venvPath = supportDir + "/venv"
let venvPython = venvPath + "/bin/python3"
let venvStreamlit = venvPath + "/bin/streamlit"
let logPath = supportDir + "/launcher.log"
let serverLogPath = supportDir + "/server.log"

func log(_ message: String) {
    let line = "[\(Date())] \(message)\n"
    guard let data = line.data(using: .utf8) else { return }
    try? FileManager.default.createDirectory(atPath: supportDir,
                                             withIntermediateDirectories: true)
    if FileManager.default.fileExists(atPath: logPath),
       let handle = FileHandle(forWritingAtPath: logPath) {
        handle.seekToEndOfFile()
        handle.write(data)
        try? handle.close()
    } else {
        try? line.write(toFile: logPath, atomically: true, encoding: .utf8)
    }
}

// MARK: - Networking helpers

/// True if we can bind the port, i.e. nothing is listening on it.
func portIsFree(_ port: UInt16) -> Bool {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    if fd < 0 { return false }
    defer { close(fd) }
    var reuse: Int32 = 1
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse,
               socklen_t(MemoryLayout<Int32>.size))
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = port.bigEndian
    addr.sin_addr.s_addr = inet_addr("127.0.0.1")
    let bound = withUnsafePointer(to: &addr) { raw in
        raw.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    return bound == 0
}

func serverIsUp(port: Int) -> Bool {
    guard let url = URL(string: "http://127.0.0.1:\(port)/_stcore/health") else {
        return false
    }
    var ok = false
    let done = DispatchSemaphore(value: 0)
    var request = URLRequest(url: url)
    request.timeoutInterval = 1.5
    request.cachePolicy = .reloadIgnoringLocalCacheData
    URLSession.shared.dataTask(with: request) { _, response, _ in
        if let http = response as? HTTPURLResponse, http.statusCode == 200 { ok = true }
        done.signal()
    }.resume()
    _ = done.wait(timeout: .now() + 2.5)
    return ok
}

/// Run a command to completion. Returns its exit status.
@discardableResult
func runSync(_ executable: String, _ arguments: [String],
             cwd: String? = nil, logTo: String? = nil) -> Int32 {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    if let cwd = cwd { process.currentDirectoryURL = URL(fileURLWithPath: cwd) }
    if let logTo = logTo {
        if !FileManager.default.fileExists(atPath: logTo) {
            FileManager.default.createFile(atPath: logTo, contents: nil)
        }
        if let handle = FileHandle(forWritingAtPath: logTo) {
            handle.seekToEndOfFile()
            process.standardOutput = handle
            process.standardError = handle
        }
    }
    do {
        try process.run()
        process.waitUntilExit()
        return process.terminationStatus
    } catch {
        log("failed to run \(executable): \(error)")
        return -1
    }
}

/// First Python 3.9+ interpreter we can find.
func findPython() -> String? {
    var candidates = ["/usr/bin/python3", "/usr/local/bin/python3",
                      "/opt/homebrew/bin/python3"]
    if let path = ProcessInfo.processInfo.environment["PATH"] {
        candidates += path.split(separator: ":").map { "\($0)/python3" }
    }
    let check = "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
    for candidate in candidates
    where FileManager.default.isExecutableFile(atPath: candidate) {
        if runSync(candidate, ["-c", check]) == 0 {
            log("using interpreter \(candidate)")
            return candidate
        }
    }
    return nil
}

// MARK: - Appearance

/// Window/splash background, matched to the web content in each mode so the
/// hand-off from the native splash to the page is seamless. NSColor resolves
/// this per appearance automatically, including live system theme changes.
let backgroundColour = NSColor(name: nil) { appearance in
    let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
    return isDark
        ? NSColor(srgbRed: 0.055, green: 0.067, blue: 0.090, alpha: 1)  // #0e1117
        : NSColor.white
}

/// Accent for the splash wordmark. Lifts in dark so it stays legible, matching
/// the --a-accent token in utils/theme.py.
let accentColour = NSColor(name: nil) { appearance in
    let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
    return isDark
        ? NSColor(srgbRed: 0.478, green: 0.702, blue: 0.910, alpha: 1)  // #7ab3e8
        : NSColor(srgbRed: 0.122, green: 0.306, blue: 0.475, alpha: 1)  // #1f4e79
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var loadingView: NSView!
    var statusLabel: NSTextField!
    var spinner: NSProgressIndicator!
    var server: Process?
    var port = 8501

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        log("native window shown")
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            if self.ensureRuntime() { self.startServer() }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let server = server, server.isRunning {
            log("stopping engine (app quitting)")
            server.terminate()
            let deadline = Date().addingTimeInterval(3)
            while server.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.1)
            }
        }
    }

    // MARK: First-run setup

    /// Create the Python environment if this is the first launch.
    func ensureRuntime() -> Bool {
        if FileManager.default.isExecutableFile(atPath: venvStreamlit) { return true }

        log("first run - building the Python environment")
        setStatus("First run: setting up. This takes a minute…")
        guard let python = findPython() else {
            fail("Python 3.9 or newer is required.",
                 "ASCENT needs Python to run its calculation engine.\n\n"
                 + "Install Apple's developer tools by running this in Terminal:\n"
                 + "    xcode-select --install\n\n"
                 + "…or install Python from python.org, then open ASCENT again.")
            return false
        }

        try? FileManager.default.createDirectory(atPath: supportDir,
                                                 withIntermediateDirectories: true)
        if runSync(python, ["-m", "venv", venvPath], logTo: serverLogPath) != 0 {
            fail("Could not create the Python environment.",
                 "See server.log in\n\(supportDir)")
            return false
        }

        setStatus("Installing components (numpy, matplotlib, streamlit)…")
        runSync(venvPython, ["-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                logTo: serverLogPath)
        let requirements = bundleAppPath + "/requirements.txt"
        if runSync(venvPython, ["-m", "pip", "install", "--quiet", "-r", requirements],
                   logTo: serverLogPath) != 0 {
            fail("Could not install the required components.",
                 "Check your internet connection, then open ASCENT again.\n\n"
                 + "Details: server.log in\n\(supportDir)")
            return false
        }

        guard FileManager.default.isExecutableFile(atPath: venvStreamlit) else {
            fail("Setup finished but the engine is missing.",
                 "See server.log in\n\(supportDir)")
            return false
        }
        log("environment ready")
        return true
    }

    // MARK: Server

    func startServer() {
        guard let free = (8501...8530).first(where: { portIsFree(UInt16($0)) }) else {
            fail("No free network port.", "Ports 8501-8530 are all in use.")
            return
        }
        port = free
        setStatus("Starting the calculation engine…")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: venvStreamlit)
        process.arguments = ["run", "app.py",
                             "--server.port", "\(port)",
                             "--server.address", "127.0.0.1",
                             "--server.headless", "true"]
        process.currentDirectoryURL = URL(fileURLWithPath: bundleAppPath)
        if !FileManager.default.fileExists(atPath: serverLogPath) {
            FileManager.default.createFile(atPath: serverLogPath, contents: nil)
        }
        if let handle = FileHandle(forWritingAtPath: serverLogPath) {
            handle.seekToEndOfFile()
            process.standardOutput = handle
            process.standardError = handle
        }
        do {
            try process.run()
            server = process
            log("engine started on port \(port) (pid \(process.processIdentifier))")
        } catch {
            fail("Could not start the calculation engine.", "\(error)")
            return
        }

        for _ in 0..<60 {
            if serverIsUp(port: port) {
                log("engine ready")
                DispatchQueue.main.async {
                    self.setStatus("Loading…")
                    if let url = URL(string: "http://127.0.0.1:\(self.port)") {
                        self.webView.load(URLRequest(url: url))
                    }
                }
                return
            }
            Thread.sleep(forTimeInterval: 0.5)
        }
        fail("The calculation engine did not start within 30 seconds.",
             "See server.log in\n\(supportDir)")
    }

    // MARK: UI

    func setStatus(_ text: String) {
        DispatchQueue.main.async { self.statusLabel.stringValue = text }
    }

    func fail(_ message: String, _ detail: String) {
        log("ERROR: \(message) — \(detail)")
        DispatchQueue.main.async {
            self.spinner.stopAnimation(nil)
            self.spinner.isHidden = true
            self.statusLabel.stringValue = message
            let alert = NSAlert()
            alert.alertStyle = .critical
            alert.messageText = message
            alert.informativeText = detail
            alert.addButton(withTitle: "Quit")
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "ASCENT"
        window.minSize = NSSize(width: 900, height: 600)
        window.setFrameAutosaveName("ASCENTMainWindow")
        window.center()
        window.backgroundColor = backgroundColour
        // Quiet chrome: the app names itself in the page header, so the title
        // bar does not need to repeat it.
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden

        let container = NSView(frame: window.contentView!.bounds)
        window.contentView = container

        webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        webView.navigationDelegate = self
        // Without this the web view paints its own white while loading, which
        // flashes against a dark splash. underPageBackgroundColor is the public
        // API for it; the KVC "drawsBackground" trick is private and throws at
        // launch if the key ever goes away.
        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = backgroundColour
        }
        webView.allowsMagnification = true
        webView.isHidden = true
        webView.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(webView)

        loadingView = NSView()
        loadingView.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(loadingView)

        let title = NSTextField(labelWithString: "ASCENT")
        title.font = NSFont.systemFont(ofSize: 30, weight: .bold)
        title.textColor = accentColour
        title.alignment = .center
        title.translatesAutoresizingMaskIntoConstraints = false

        statusLabel = NSTextField(labelWithString: "Starting up…")
        statusLabel.font = NSFont.systemFont(ofSize: 13)
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.alignment = .center
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.startAnimation(nil)
        spinner.translatesAutoresizingMaskIntoConstraints = false

        loadingView.addSubview(title)
        loadingView.addSubview(spinner)
        loadingView.addSubview(statusLabel)

        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: container.topAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            loadingView.topAnchor.constraint(equalTo: container.topAnchor),
            loadingView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            loadingView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            loadingView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            title.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            title.centerYAnchor.constraint(equalTo: loadingView.centerYAnchor,
                                           constant: -30),
            spinner.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            spinner.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 18),
            statusLabel.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            statusLabel.topAnchor.constraint(equalTo: spinner.bottomAnchor,
                                             constant: 14),
        ])

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        log("page loaded")
        spinner.stopAnimation(nil)
        loadingView.isHidden = true
        webView.isHidden = false
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!,
                 withError error: Error) {
        log("navigation failed: \(error.localizedDescription)")
    }

    @objc func reloadPage() { webView.reload() }
    @objc func zoomIn() { webView.pageZoom = min(webView.pageZoom + 0.1, 2.5) }
    @objc func zoomOut() { webView.pageZoom = max(webView.pageZoom - 0.1, 0.5) }
    @objc func zoomReset() { webView.pageZoom = 1.0 }
    @objc func openSupportFolder() {
        NSWorkspace.shared.open(URL(fileURLWithPath: supportDir))
    }

    func buildMenu() {
        let mainMenu = NSMenu()

        let appItem = NSMenuItem()
        mainMenu.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About ASCENT",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)),
                        keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Show Logs & Data Folder",
                        action: #selector(openSupportFolder), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Hide ASCENT",
                        action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Quit ASCENT",
                        action: #selector(NSApplication.terminate(_:)),
                        keyEquivalent: "q")
        appItem.submenu = appMenu

        let viewItem = NSMenuItem()
        mainMenu.addItem(viewItem)
        let viewMenu = NSMenu(title: "View")
        viewMenu.addItem(withTitle: "Reload", action: #selector(reloadPage),
                         keyEquivalent: "r")
        viewMenu.addItem(NSMenuItem.separator())
        viewMenu.addItem(withTitle: "Actual Size", action: #selector(zoomReset),
                         keyEquivalent: "0")
        viewMenu.addItem(withTitle: "Zoom In", action: #selector(zoomIn),
                         keyEquivalent: "+")
        viewMenu.addItem(withTitle: "Zoom Out", action: #selector(zoomOut),
                         keyEquivalent: "-")
        viewItem.submenu = viewMenu

        let windowItem = NSMenuItem()
        mainMenu.addItem(windowItem)
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize",
                           action: #selector(NSWindow.performMiniaturize(_:)),
                           keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom",
                           action: #selector(NSWindow.performZoom(_:)),
                           keyEquivalent: "")
        windowItem.submenu = windowMenu

        NSApp.mainMenu = mainMenu
        NSApp.windowsMenu = windowMenu
    }
}

let delegate = AppDelegate()
let application = NSApplication.shared
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
