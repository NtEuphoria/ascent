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
let settingsPath = supportDir + "/settings.json"
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

/// The appearance the user picked in Settings, or nil to follow the system.
///
/// Without this the window, its title bar and the colour behind the page all
/// follow NSAppearance - the system - so choosing Light on a dark Mac left the
/// app's chrome dark however light the page itself was.
func preferredAppearance() -> NSAppearance? {
    guard let data = FileManager.default.contents(atPath: settingsPath),
          let parsed = try? JSONSerialization.jsonObject(with: data),
          let object = parsed as? [String: Any],
          let choice = object["appearance"] as? String else {
        return nil
    }
    switch choice {
    case "Light": return NSAppearance(named: .aqua)
    case "Dark": return NSAppearance(named: .darkAqua)
    default: return nil          // "Follow system"
    }
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var loadingView: NSView!
    var statusLabel: NSTextField!
    var markHost: NSView!
    var progressHost: NSView!
    var wordmark: NSTextField!
    var markLayer: CAShapeLayer!
    var ringLayer: CAShapeLayer!
    var progressFill: CAShapeLayer!
    /// Set once the page is up, so the slow-boot reveal knows to stay away.
    var splashFinished = false
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
        setProgress(0.15)
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
        setProgress(0.4)
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
        setProgress(0.6)

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

        // Development aid: ASCENT_SPLASH_HOLD=8 keeps the splash up so the
        // startup animation can actually be watched. A warm start is ~1s.
        if let hold = ProcessInfo.processInfo.environment["ASCENT_SPLASH_HOLD"],
           let seconds = Double(hold) {
            Thread.sleep(forTimeInterval: seconds)
        }

        for _ in 0..<60 {
            if serverIsUp(port: port) {
                log("engine ready")
                setProgress(0.85)
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
        // Applied before the background colour resolves, so the dynamic
        // NSColor picks the chosen mode rather than the system's.
        window.appearance = preferredAppearance()
        log("window appearance: "
            + (window.appearance?.name.rawValue ?? "follow system")
            + " (system is "
            + (NSApp.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua])
               == .darkAqua ? "dark" : "light") + ")")
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
        loadingView.wantsLayer = true
        loadingView.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(loadingView)

        // The dart mark, drawn as a stroke rather than shown all at once.
        markHost = NSView()
        markHost.wantsLayer = true
        markHost.translatesAutoresizingMaskIntoConstraints = false
        loadingView.addSubview(markHost)

        let wordmark = NSTextField(labelWithString: "ASCENT")
        wordmark.font = NSFont.systemFont(ofSize: 26, weight: .bold)
        wordmark.textColor = accentColour
        wordmark.alignment = .center
        wordmark.translatesAutoresizingMaskIntoConstraints = false
        wordmark.alphaValue = 0
        loadingView.addSubview(wordmark)
        self.wordmark = wordmark

        // A determinate hairline, driven by real boot phases rather than a
        // spinner that conveys nothing.
        progressHost = NSView()
        progressHost.wantsLayer = true
        progressHost.translatesAutoresizingMaskIntoConstraints = false
        loadingView.addSubview(progressHost)

        statusLabel = NSTextField(labelWithString: "Starting up…")
        statusLabel.font = NSFont.systemFont(ofSize: 12)
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.alignment = .center
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
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

            markHost.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            markHost.centerYAnchor.constraint(equalTo: loadingView.centerYAnchor,
                                              constant: -58),
            markHost.widthAnchor.constraint(equalToConstant: 84),
            markHost.heightAnchor.constraint(equalToConstant: 84),

            wordmark.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            wordmark.topAnchor.constraint(equalTo: markHost.bottomAnchor,
                                          constant: 14),

            progressHost.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            progressHost.topAnchor.constraint(equalTo: wordmark.bottomAnchor,
                                              constant: 22),
            progressHost.widthAnchor.constraint(equalToConstant: 190),
            progressHost.heightAnchor.constraint(equalToConstant: 2),

            statusLabel.centerXAnchor.constraint(equalTo: loadingView.centerXAnchor),
            statusLabel.topAnchor.constraint(equalTo: progressHost.bottomAnchor,
                                             constant: 16),
        ])

        loadingView.layoutSubtreeIfNeeded()
        buildSplashLayers()
        playIntro()

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        watchSettings()
    }

    // MARK: Settings

    var settingsWatcher: Timer?
    var settingsStamp: Date?

    /// Re-read the appearance setting when the file changes.
    ///
    /// Polls rather than using a file-system event source because settings are
    /// written atomically via os.replace: the original inode is unlinked, so a
    /// descriptor-based watcher would stop firing after the first save.
    func watchSettings() {
        applyAppearance()
        settingsWatcher = Timer.scheduledTimer(withTimeInterval: 1.5,
                                               repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let stamp = (try? FileManager.default.attributesOfItem(
                atPath: settingsPath)[.modificationDate]) as? Date
            if stamp != self.settingsStamp {
                self.settingsStamp = stamp
                self.applyAppearance()
            }
        }
    }

    func applyAppearance() {
        let chosen = preferredAppearance()
        guard window.appearance != chosen else { return }
        window.appearance = chosen
        window.backgroundColor = backgroundColour
        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = backgroundColour
        }
        log("appearance applied: \(chosen?.name.rawValue ?? "follow system")")
    }

    // MARK: Splash animation

    /// Whether the user has asked the system to reduce motion.
    var reduceMotion: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }

    func buildSplashLayers() {
        // The dart from the app icon, in an 84pt box. Built as a CGPath rather
        // than NSBezierPath.cgPath, which is macOS 14+ only.
        let path = CGMutablePath()
        let s: CGFloat = 84.0 / 1024.0        // icon artwork is 1024pt
        path.move(to: CGPoint(x: 512 * s, y: 812 * s))
        path.addLine(to: CGPoint(x: 806 * s, y: 236 * s))
        path.addLine(to: CGPoint(x: 512 * s, y: 380 * s))
        path.addLine(to: CGPoint(x: 218 * s, y: 236 * s))
        path.closeSubpath()

        // A ring that passes outward through the mark: a pressure pulse. It is
        // drawn first so it sits behind the dart.
        let ring = CAShapeLayer()
        ring.path = CGPath(ellipseIn: CGRect(x: 12, y: 12, width: 60, height: 60),
                           transform: nil)
        ring.strokeColor = accentColour.cgColor
        ring.fillColor = NSColor.clear.cgColor
        ring.lineWidth = 1.5
        ring.opacity = 0
        // Anchored at its own centre so a scale animation expands about the
        // middle. An AppKit view-backed layer cannot be re-anchored without
        // moving the view, but a sublayer we own can.
        ring.bounds = CGRect(x: 0, y: 0, width: 84, height: 84)
        ring.anchorPoint = CGPoint(x: 0.5, y: 0.5)
        ring.position = CGPoint(x: 42, y: 42)
        markHost.layer?.masksToBounds = false
        markHost.layer?.addSublayer(ring)
        ringLayer = ring

        // Filled, not stroked. The icon is filled and so is the mark inside
        // the app, so a stroked outline here was the one surface out of three
        // that did not match.
        let mark = CAShapeLayer()
        mark.path = path
        mark.fillColor = accentColour.cgColor
        mark.strokeColor = NSColor.clear.cgColor
        mark.lineJoin = .round
        mark.bounds = CGRect(x: 0, y: 0, width: 84, height: 84)
        mark.anchorPoint = CGPoint(x: 0.5, y: 0.5)
        mark.position = CGPoint(x: 42, y: 42)
        mark.opacity = reduceMotion ? 1 : 0
        markHost.layer?.addSublayer(mark)
        markLayer = mark

        let track = CAShapeLayer()
        let trackPath = CGMutablePath()
        trackPath.move(to: CGPoint(x: 0, y: 1))
        trackPath.addLine(to: CGPoint(x: 190, y: 1))
        track.path = trackPath
        track.strokeColor = accentColour.withAlphaComponent(0.18).cgColor
        track.lineWidth = 2
        track.lineCap = .round
        progressHost.layer?.addSublayer(track)

        let fill = CAShapeLayer()
        fill.path = trackPath
        fill.strokeColor = accentColour.cgColor
        fill.lineWidth = 2
        fill.lineCap = .round
        fill.strokeEnd = 0
        progressHost.layer?.addSublayer(fill)
        progressFill = fill

        // Hidden to begin with. A progress bar is a promise that you are going
        // to be waiting, and on a warm start you are not - the whole splash is
        // gone inside a second. It appears only if the boot actually runs long.
        progressHost.alphaValue = 0
        statusLabel.alphaValue = 0
    }

    /// The mark springs in, a pulse passes out through it, the wordmark
    /// follows. Everything is a layer transform or an opacity, so it all runs
    /// on the GPU and none of it touches layout.
    func playIntro() {
        guard !reduceMotion else {
            wordmark.alphaValue = 1
            markLayer.opacity = 1
            scheduleSlowBootReveal()
            return
        }

        // A spring rather than an ease, because the settle is what makes it
        // read as physical instead of as a timed fade. Damping is high enough
        // that it never visibly bounces - it arrives and stops.
        let pop = CASpringAnimation(keyPath: "transform.scale")
        pop.fromValue = 0.62
        pop.toValue = 1.0
        pop.damping = 17
        pop.stiffness = 240
        pop.mass = 0.9
        pop.initialVelocity = 6
        pop.duration = pop.settlingDuration
        pop.fillMode = .forwards
        pop.isRemovedOnCompletion = false
        markLayer.add(pop, forKey: "pop")

        let appear = CABasicAnimation(keyPath: "opacity")
        appear.fromValue = 0
        appear.toValue = 1
        appear.duration = 0.20
        appear.timingFunction = CAMediaTimingFunction(name: .easeOut)
        appear.fillMode = .forwards
        appear.isRemovedOnCompletion = false
        markLayer.opacity = 1
        markLayer.add(appear, forKey: "appear")

        // The pulse. Expands through and past the mark, fading as it goes, so
        // the eye is carried outward rather than left staring at a logo.
        let expand = CABasicAnimation(keyPath: "transform.scale")
        expand.fromValue = 0.30
        expand.toValue = 2.4
        let fade = CABasicAnimation(keyPath: "opacity")
        fade.fromValue = 0.55
        fade.toValue = 0.0
        let pulse = CAAnimationGroup()
        pulse.animations = [expand, fade]
        pulse.duration = 0.62
        pulse.beginTime = CACurrentMediaTime() + 0.05
        // Exponential ease-out: quick away from the mark, long settle at the
        // edge, which is how a pressure wave actually looks.
        pulse.timingFunction = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
        pulse.fillMode = .forwards
        pulse.isRemovedOnCompletion = false
        ringLayer.add(pulse, forKey: "pulse")

        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.30
            context.timingFunction = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
            self.wordmark.animator().alphaValue = 1
        }

        scheduleSlowBootReveal()
    }

    /// Show the hairline only if the boot is slow enough to be worth a
    /// progress indicator. A cold first launch builds a Python environment and
    /// takes a while; a warm one does not, and should not be made to look like
    /// it might.
    func scheduleSlowBootReveal() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) { [weak self] in
            guard let self = self, !self.splashFinished else { return }
            NSAnimationContext.runAnimationGroup { context in
                context.duration = self.reduceMotion ? 0 : 0.25
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                self.progressHost.animator().alphaValue = 1
                self.statusLabel.animator().alphaValue = 1
            }
        }
    }

    /// Advance the hairline. Fractions correspond to real boot milestones, so
    /// the bar means something rather than just moving.
    func setProgress(_ fraction: CGFloat) {
        DispatchQueue.main.async {
            guard let fill = self.progressFill else { return }
            let animation = CABasicAnimation(keyPath: "strokeEnd")
            animation.fromValue = fill.presentation()?.strokeEnd ?? fill.strokeEnd
            animation.toValue = fraction
            animation.duration = self.reduceMotion ? 0 : 0.4
            animation.timingFunction = CAMediaTimingFunction(name: .easeOut)
            animation.fillMode = .forwards
            animation.isRemovedOnCompletion = false
            fill.strokeEnd = fraction
            fill.add(animation, forKey: "progress")
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        log("page loaded")
        splashFinished = true
        setProgress(1.0)
        // A hard isHidden swap here was the most jarring moment in v1.0.0.
        webView.alphaValue = 0
        webView.isHidden = false

        // The mark keeps moving as it goes, drifting very slightly toward the
        // viewer. A layer that freezes and then fades reads as a picture being
        // removed; one that is still moving reads as a hand-off.
        if !reduceMotion {
            let drift = CABasicAnimation(keyPath: "transform.scale")
            drift.fromValue = 1.0
            drift.toValue = 1.06
            drift.duration = 0.26
            drift.timingFunction = CAMediaTimingFunction(controlPoints: 0.4, 0, 1, 1)
            drift.fillMode = .forwards
            drift.isRemovedOnCompletion = false
            markLayer.add(drift, forKey: "handoff")
        }

        NSAnimationContext.runAnimationGroup({ context in
            context.duration = self.reduceMotion ? 0 : 0.24
            context.timingFunction = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
            self.webView.animator().alphaValue = 1
            self.loadingView.animator().alphaValue = 0
        }, completionHandler: {
            self.loadingView.isHidden = true
        })
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!,
                 withError error: Error) {
        log("navigation failed: \(error.localizedDescription)")
    }

    /// Cmd-K. Streamlit cannot listen for a keypress itself, so the native menu
    /// clicks the page's hidden palette trigger. That is an ordinary Streamlit
    /// interaction over the existing websocket - no reload, no round trip
    /// through query parameters.
    @objc func openPalette() {
        webView.evaluateJavaScript("""
            (function () {
              var trigger = document.querySelector(
                  '.st-key-palette_trigger button');
              if (trigger) { trigger.click(); return true; }
              return false;
            })();
            """, completionHandler: { result, error in
                if let error = error {
                    log("palette shortcut failed: \(error.localizedDescription)")
                } else if (result as? Bool) == false {
                    log("palette trigger not found in page")
                }
            })
    }

    /// Show or hide the sidebar from the menu bar.
    ///
    /// Streamlit's own expand control is a small icon in the top-left corner;
    /// a menu item with a shortcut is a more findable way back once it has
    /// been collapsed.
    @objc func toggleSidebar() {
        webView.evaluateJavaScript("""
            (function () {
              var collapse = document.querySelector(
                  '[data-testid="stSidebarCollapseButton"] button');
              var expand = document.querySelector(
                  '[data-testid="stExpandSidebarButton"] button')
                  || document.querySelector('[data-testid="stExpandSidebarButton"]');
              var target = expand || collapse;
              if (target) { target.click(); return true; }
              return false;
            })();
            """, completionHandler: { result, error in
                if let error = error {
                    log("sidebar toggle failed: \(error.localizedDescription)")
                }
            })
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

        let goItem = NSMenuItem()
        mainMenu.addItem(goItem)
        let goMenu = NSMenu(title: "Go")
        goMenu.addItem(withTitle: "Search Calculators…",
                       action: #selector(openPalette), keyEquivalent: "k")
        goItem.submenu = goMenu

        let viewItem = NSMenuItem()
        mainMenu.addItem(viewItem)
        let viewMenu = NSMenu(title: "View")
        viewMenu.addItem(withTitle: "Show / Hide Sidebar",
                         action: #selector(toggleSidebar), keyEquivalent: "\\")
        viewMenu.addItem(NSMenuItem.separator())
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
