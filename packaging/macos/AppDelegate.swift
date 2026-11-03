import Cocoa
import Foundation

class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var statusMenuItem: NSMenuItem!
    private var startMenuItem: NSMenuItem!
    private var stopMenuItem: NSMenuItem!
    private var openBrowserMenuItem: NSMenuItem!
    private var updateMenuItem: NSMenuItem!

    var mainWindowController: MainWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupStatusItem()

        mainWindowController = MainWindowController()
        mainWindowController?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)

        setupObserver()

        // Background update check after launch
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            AppUpdater.shared.checkForUpdates(interactive: false)
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showMainWindow()
        return true
    }

    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            if let img = NSImage(systemSymbolName: "server.rack", accessibilityDescription: "MCP Browser") {
                img.isTemplate = true
                button.image = img
            } else {
                button.title = "MCP"
            }
            button.toolTip = "MCP Browser Manager"
        }

        let menu = NSMenu()

        statusMenuItem = NSMenuItem(title: "MCP Browser: Checking...", action: nil, keyEquivalent: "")
        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)

        menu.addItem(NSMenuItem.separator())

        startMenuItem = NSMenuItem(title: "Start Server", action: #selector(startServer), keyEquivalent: "s")
        startMenuItem.target = self
        menu.addItem(startMenuItem)

        stopMenuItem = NSMenuItem(title: "Stop Server", action: #selector(stopServer), keyEquivalent: "t")
        stopMenuItem.target = self
        menu.addItem(stopMenuItem)

        openBrowserMenuItem = NSMenuItem(title: "Open in Browser", action: #selector(openBrowser), keyEquivalent: "o")
        openBrowserMenuItem.target = self
        menu.addItem(openBrowserMenuItem)

        let viewLogsItem = NSMenuItem(title: "View Logs", action: #selector(viewLogs), keyEquivalent: "l")
        viewLogsItem.target = self
        menu.addItem(viewLogsItem)

        menu.addItem(NSMenuItem.separator())

        updateMenuItem = NSMenuItem(title: "Check for Updates...", action: #selector(checkForUpdates), keyEquivalent: "u")
        updateMenuItem.target = self
        menu.addItem(updateMenuItem)

        let showItem = NSMenuItem(title: "Show Control Panel...", action: #selector(showMainWindow), keyEquivalent: "m")
        showItem.target = self
        menu.addItem(showItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "Quit MCP Browser", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    private func setupObserver() {
        let updateUI: (Bool, Int?) -> Void = { [weak self] isRunning, pid in
            guard let self = self else { return }
            let port = ServerController.shared.port
            if isRunning {
                let pidStr = pid != nil ? " (PID: \(pid!))" : ""
                self.statusMenuItem.title = "MCP Browser: Running on port \(port)\(pidStr)"
                self.startMenuItem.isEnabled = false
                self.stopMenuItem.isEnabled = true
                self.openBrowserMenuItem.isEnabled = true
            } else {
                self.statusMenuItem.title = "MCP Browser: Stopped"
                self.startMenuItem.isEnabled = true
                self.stopMenuItem.isEnabled = false
                self.openBrowserMenuItem.isEnabled = false
            }
        }

        ServerController.shared.onStateChanged = { [weak self] isRunning, pid in
            updateUI(isRunning, pid)
            self?.mainWindowController?.updateServerUI(isRunning: isRunning, pid: pid)
        }

        AppUpdater.shared.onStatusChanged = { [weak self] status in
            guard let self = self else { return }
            self.mainWindowController?.updateUpdaterUI(status: status)
            switch status {
            case .updateAvailable(let version, _):
                self.updateMenuItem.title = "Update Available: v\(version)..."
            default:
                self.updateMenuItem.title = "Check for Updates..."
            }
        }

        updateUI(ServerController.shared.isRunning, ServerController.shared.currentPid)
    }

    @objc func showMainWindow() {
        if mainWindowController == nil {
            mainWindowController = MainWindowController()
        }
        mainWindowController?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func startServer() {
        ServerController.shared.startServer()
    }

    @objc func stopServer() {
        ServerController.shared.stopServer()
    }

    @objc func openBrowser() {
        ServerController.shared.openBrowser()
    }

    @objc func viewLogs() {
        ServerController.shared.viewLogs()
    }

    @objc func checkForUpdates() {
        showMainWindow()
        AppUpdater.shared.checkForUpdates(interactive: true)
    }

    @objc func quitApp() {
        NSApp.terminate(nil)
    }
}
