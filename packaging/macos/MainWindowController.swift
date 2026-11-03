import Cocoa
import Foundation

class MainWindowController: NSWindowController, NSWindowDelegate {
    private var statusDot: NSView!
    private var statusLabel: NSTextField!
    private var portField: NSTextField!
    private var startStopButton: NSButton!
    private var openBrowserButton: NSButton!
    private var viewLogsButton: NSButton!
    private var urlButton: NSButton!

    private var updateStatusLabel: NSTextField!
    private var updateButton: NSButton!
    private var progressIndicator: NSProgressIndicator!

    private var pendingUpdateURL: URL?

    init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 420),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "MCP Browser"
        window.center()
        window.isReleasedWhenClosed = false
        super.init(window: window)
        window.delegate = self

        setupUI()
        setupBindings()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupUI() {
        guard let window = self.window, let contentView = window.contentView else { return }

        // --- Header ---
        let iconView = NSImageView(frame: NSRect(x: 24, y: 340, width: 56, height: 56))
        if let appIcon = NSImage(named: "AppIcon") {
            iconView.image = appIcon
        } else if let icon = NSApp.applicationIconImage {
            iconView.image = icon
        }
        contentView.addSubview(iconView)

        let titleLabel = NSTextField(labelWithString: "MCP Browser")
        titleLabel.frame = NSRect(x: 92, y: 364, width: 200, height: 26)
        titleLabel.font = NSFont.systemFont(ofSize: 20, weight: .bold)
        contentView.addSubview(titleLabel)

        let subtitleLabel = NSTextField(labelWithString: "Local Multi-Client MCP Server Manager")
        subtitleLabel.frame = NSRect(x: 92, y: 344, width: 340, height: 18)
        subtitleLabel.font = NSFont.systemFont(ofSize: 12)
        subtitleLabel.textColor = .secondaryLabelColor
        contentView.addSubview(subtitleLabel)

        let versionLabel = NSTextField(labelWithString: "v\(AppUpdater.shared.currentVersion)")
        versionLabel.frame = NSRect(x: 360, y: 368, width: 76, height: 18)
        versionLabel.alignment = .right
        versionLabel.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        versionLabel.textColor = .tertiaryLabelColor
        contentView.addSubview(versionLabel)

        // --- Status Box ---
        let statusBox = NSBox(frame: NSRect(x: 24, y: 170, width: 412, height: 155))
        statusBox.title = "Server Status"
        statusBox.boxType = .primary
        contentView.addSubview(statusBox)

        statusDot = NSView(frame: NSRect(x: 16, y: 104, width: 12, height: 12))
        statusDot.wantsLayer = true
        statusDot.layer?.cornerRadius = 6
        statusDot.layer?.backgroundColor = NSColor.systemGray.cgColor
        statusBox.addSubview(statusDot)

        statusLabel = NSTextField(labelWithString: "Checking server...")
        statusLabel.frame = NSRect(x: 36, y: 100, width: 350, height: 20)
        statusLabel.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        statusBox.addSubview(statusLabel)

        let portLabel = NSTextField(labelWithString: "Port:")
        portLabel.frame = NSRect(x: 16, y: 64, width: 40, height: 20)
        portLabel.font = NSFont.systemFont(ofSize: 12)
        statusBox.addSubview(portLabel)

        portField = NSTextField(frame: NSRect(x: 60, y: 62, width: 68, height: 22))
        portField.stringValue = String(ServerController.shared.port)
        portField.target = self
        portField.action = #selector(portChanged)
        statusBox.addSubview(portField)

        urlButton = NSButton(frame: NSRect(x: 140, y: 62, width: 250, height: 22))
        urlButton.isBordered = false
        urlButton.contentTintColor = .linkColor
        urlButton.font = NSFont.systemFont(ofSize: 12, weight: .medium)
        urlButton.target = self
        urlButton.action = #selector(openBrowserClicked)
        urlButton.alignment = .left
        statusBox.addSubview(urlButton)

        // Action Buttons inside box
        startStopButton = NSButton(frame: NSRect(x: 16, y: 14, width: 120, height: 32))
        startStopButton.bezelStyle = .rounded
        startStopButton.title = "Start Server"
        startStopButton.target = self
        startStopButton.action = #selector(startStopClicked)
        statusBox.addSubview(startStopButton)

        openBrowserButton = NSButton(frame: NSRect(x: 144, y: 14, width: 135, height: 32))
        openBrowserButton.bezelStyle = .rounded
        openBrowserButton.title = "Open in Browser"
        openBrowserButton.target = self
        openBrowserButton.action = #selector(openBrowserClicked)
        statusBox.addSubview(openBrowserButton)

        viewLogsButton = NSButton(frame: NSRect(x: 287, y: 14, width: 105, height: 32))
        viewLogsButton.bezelStyle = .rounded
        viewLogsButton.title = "View Logs"
        viewLogsButton.target = self
        viewLogsButton.action = #selector(viewLogsClicked)
        statusBox.addSubview(viewLogsButton)

        // --- Updates Box ---
        let updateBox = NSBox(frame: NSRect(x: 24, y: 24, width: 412, height: 130))
        updateBox.title = "Software Updates"
        contentView.addSubview(updateBox)

        updateStatusLabel = NSTextField(labelWithString: "Ready to check for updates.")
        updateStatusLabel.frame = NSRect(x: 16, y: 65, width: 380, height: 20)
        updateStatusLabel.font = NSFont.systemFont(ofSize: 12)
        updateStatusLabel.textColor = .secondaryLabelColor
        updateBox.addSubview(updateStatusLabel)

        progressIndicator = NSProgressIndicator(frame: NSRect(x: 16, y: 46, width: 380, height: 14))
        progressIndicator.isIndeterminate = false
        progressIndicator.minValue = 0.0
        progressIndicator.maxValue = 1.0
        progressIndicator.isHidden = true
        updateBox.addSubview(progressIndicator)

        updateButton = NSButton(frame: NSRect(x: 16, y: 12, width: 160, height: 30))
        updateButton.bezelStyle = .rounded
        updateButton.title = "Check for Updates"
        updateButton.target = self
        updateButton.action = #selector(updateButtonClicked)
        updateBox.addSubview(updateButton)
    }

    private func setupBindings() {
        ServerController.shared.onStateChanged = { [weak self] isRunning, pid in
            self?.updateServerUI(isRunning: isRunning, pid: pid)
        }

        AppUpdater.shared.onStatusChanged = { [weak self] status in
            self?.updateUpdaterUI(status: status)
        }

        updateServerUI(isRunning: ServerController.shared.isRunning, pid: ServerController.shared.currentPid)
    }

    func updateServerUI(isRunning: Bool, pid: Int?) {
        let port = ServerController.shared.port
        if isRunning {
            statusDot.layer?.backgroundColor = NSColor.systemGreen.cgColor
            let pidStr = pid != nil ? " (PID: \(pid!))" : ""
            statusLabel.stringValue = "Server running on port \(port)\(pidStr)"
            startStopButton.title = "Stop Server"
            openBrowserButton.isEnabled = true
            portField.isEnabled = false
            urlButton.title = "http://127.0.0.1:\(port)/"
            urlButton.isHidden = false
        } else {
            statusDot.layer?.backgroundColor = NSColor.systemGray.cgColor
            statusLabel.stringValue = "Server is stopped"
            startStopButton.title = "Start Server"
            openBrowserButton.isEnabled = false
            portField.isEnabled = true
            urlButton.isHidden = true
        }
    }

    func updateUpdaterUI(status: UpdateStatus) {
        switch status {
        case .idle:
            updateStatusLabel.stringValue = "Ready to check for updates."
            updateButton.title = "Check for Updates"
            updateButton.isEnabled = true
            progressIndicator.isHidden = true
            pendingUpdateURL = nil

        case .checking:
            updateStatusLabel.stringValue = "Checking GitHub Releases..."
            updateButton.isEnabled = false
            progressIndicator.isHidden = true

        case .upToDate(let version):
            updateStatusLabel.stringValue = "You are up to date! (v\(version))"
            updateButton.title = "Check for Updates"
            updateButton.isEnabled = true
            progressIndicator.isHidden = true
            pendingUpdateURL = nil

        case .updateAvailable(let version, let downloadURL):
            updateStatusLabel.stringValue = "Update available: v\(version) 🎉"
            updateButton.title = "Update & Restart"
            updateButton.isEnabled = true
            progressIndicator.isHidden = true
            pendingUpdateURL = downloadURL

        case .downloading(let progress):
            updateStatusLabel.stringValue = String(format: "Downloading update... %.0f%%", progress * 100)
            updateButton.isEnabled = false
            progressIndicator.isHidden = false
            progressIndicator.doubleValue = progress

        case .readyToRestart:
            updateStatusLabel.stringValue = "Restarting and applying update..."
            updateButton.isEnabled = false
            progressIndicator.isHidden = true

        case .error(let message):
            updateStatusLabel.stringValue = "Update error: \(message)"
            updateButton.title = "Check for Updates"
            updateButton.isEnabled = true
            progressIndicator.isHidden = true
            pendingUpdateURL = nil
        }
    }

    @objc private func portChanged() {
        if let newPort = Int(portField.stringValue), newPort > 0 && newPort < 65536 {
            ServerController.shared.port = newPort
        } else {
            portField.stringValue = String(ServerController.shared.port)
        }
    }

    @objc private func startStopClicked() {
        if ServerController.shared.isRunning {
            statusLabel.stringValue = "Stopping server..."
            startStopButton.isEnabled = false
            ServerController.shared.stopServer { [weak self] success, error in
                self?.startStopButton.isEnabled = true
                if !success, let error = error {
                    let alert = NSAlert()
                    alert.messageText = "Stop Failed"
                    alert.informativeText = error
                    alert.runModal()
                }
            }
        } else {
            statusLabel.stringValue = "Starting server..."
            startStopButton.isEnabled = false
            ServerController.shared.startServer { [weak self] success, error in
                self?.startStopButton.isEnabled = true
                if !success, let error = error {
                    let alert = NSAlert()
                    alert.messageText = "Start Failed"
                    alert.informativeText = error
                    alert.runModal()
                }
            }
        }
    }

    @objc private func openBrowserClicked() {
        ServerController.shared.openBrowser()
    }

    @objc private func viewLogsClicked() {
        ServerController.shared.viewLogs()
    }

    @objc private func updateButtonClicked() {
        if let url = pendingUpdateURL {
            AppUpdater.shared.startUpdate(downloadURL: url)
        } else {
            AppUpdater.shared.checkForUpdates(interactive: true)
        }
    }
}
