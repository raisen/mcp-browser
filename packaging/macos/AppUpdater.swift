import Cocoa
import Foundation

enum UpdateStatus: Equatable {
    case idle
    case checking
    case upToDate(version: String)
    case updateAvailable(version: String, downloadURL: URL)
    case downloading(progress: Double)
    case readyToRestart
    case error(message: String)

    static func == (lhs: UpdateStatus, rhs: UpdateStatus) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle), (.checking, .checking), (.readyToRestart, .readyToRestart):
            return true
        case (.upToDate(let v1), .upToDate(let v2)):
            return v1 == v2
        case (.updateAvailable(let v1, let u1), .updateAvailable(let v2, let u2)):
            return v1 == v2 && u1 == u2
        case (.downloading(let p1), .downloading(let p2)):
            return abs(p1 - p2) < 0.001
        case (.error(let m1), .error(let m2)):
            return m1 == m2
        default:
            return false
        }
    }
}

class AppUpdater: NSObject, URLSessionDownloadDelegate {
    static let shared = AppUpdater()

    private(set) var status: UpdateStatus = .idle {
        didSet {
            onStatusChanged?(status)
        }
    }

    var onStatusChanged: ((UpdateStatus) -> Void)?

    private var downloadTask: URLSessionDownloadTask?
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.default
        return URLSession(configuration: config, delegate: self, delegateQueue: OperationQueue.main)
    }()

    var currentVersion: String {
        return Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.1.0"
    }

    var machineArch: String {
        #if arch(arm64)
        return "arm64"
        #else
        return "x86_64"
        #endif
    }

    func isVersion(_ v1: String, greaterThan v2: String) -> Bool {
        let clean1 = v1.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
        let clean2 = v2.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))

        let parts1 = clean1.split(separator: ".").compactMap { Int($0) }
        let parts2 = clean2.split(separator: ".").compactMap { Int($0) }

        let count = max(parts1.count, parts2.count)
        for i in 0..<count {
            let p1 = i < parts1.count ? parts1[i] : 0
            let p2 = i < parts2.count ? parts2[i] : 0
            if p1 > p2 { return true }
            if p1 < p2 { return false }
        }
        return false
    }

    func checkForUpdates(interactive: Bool = false) {
        guard status != .checking else { return }
        status = .checking

        guard let url = URL(string: "https://api.github.com/repos/raisen/mcp-browser/releases/latest") else {
            status = .error(message: "Invalid releases API URL")
            return
        }

        var req = URLRequest(url: url)
        req.setValue("MCP-Browser-App/\(currentVersion)", forHTTPHeaderField: "User-Agent")
        req.setValue("application/vnd.github.v3+json", forHTTPHeaderField: "Accept")
        req.timeoutInterval = 10.0

        let task = URLSession.shared.dataTask(with: req) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let error = error {
                    self.status = .error(message: error.localizedDescription)
                    if interactive {
                        self.showAlert(title: "Update Check Failed", message: error.localizedDescription)
                    }
                    return
                }

                guard let http = response as? HTTPURLResponse, http.statusCode == 200,
                      let data = data,
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let tagName = json["tag_name"] as? String else {
                    self.status = .error(message: "Could not retrieve latest release info.")
                    return
                }

                let remoteVer = tagName.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
                let localVer = self.currentVersion.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))

                if self.isVersion(remoteVer, greaterThan: localVer) {
                    let assets = json["assets"] as? [[String: Any]] ?? []
                    let archSuffix = "-macos-\(self.machineArch).dmg"
                    var matchedURL: URL? = nil

                    for asset in assets {
                        if let name = asset["name"] as? String,
                           name.hasSuffix(archSuffix),
                           let urlStr = asset["browser_download_url"] as? String,
                           let dUrl = URL(string: urlStr) {
                            matchedURL = dUrl
                            break
                        }
                    }

                    if let dUrl = matchedURL {
                        self.status = .updateAvailable(version: remoteVer, downloadURL: dUrl)
                    } else {
                        self.status = .error(message: "Release v\(remoteVer) found, but no matching \(self.machineArch) .dmg asset.")
                    }
                } else {
                    self.status = .upToDate(version: localVer)
                    if interactive {
                        self.showAlert(title: "You are up to date!", message: "MCP Browser v\(localVer) is currently the latest version.")
                    }
                }
            }
        }
        task.resume()
    }

    func startUpdate(downloadURL: URL) {
        status = .downloading(progress: 0.0)
        downloadTask = session.downloadTask(with: downloadURL)
        downloadTask?.resume()
    }

    // MARK: - URLSessionDownloadDelegate
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        if totalBytesExpectedToWrite > 0 {
            let progress = Double(totalBytesWritten) / Double(totalBytesExpectedToWrite)
            status = .downloading(progress: progress)
        }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        let tempDMG = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("mcp-browser-update.dmg")
        try? FileManager.default.removeItem(at: tempDMG)

        do {
            try FileManager.default.moveItem(at: location, to: tempDMG)
            DispatchQueue.main.async {
                self.installDownloadedDMG(dmgPath: tempDMG.path)
            }
        } catch {
            DispatchQueue.main.async {
                self.status = .error(message: "Failed to store downloaded update: \(error.localizedDescription)")
            }
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            DispatchQueue.main.async {
                self.status = .error(message: "Download failed: \(error.localizedDescription)")
            }
        }
    }

    private func installDownloadedDMG(dmgPath: String) {
        status = .readyToRestart

        let targetAppPath = Bundle.main.bundleURL.path
        let currentPid = ProcessInfo.processInfo.processIdentifier
        let mountPoint = "/tmp/mcp-browser-mount-\(currentPid)"
        let helperScript = "/tmp/mcp-browser-upgrade-\(currentPid).sh"

        let script = """
        #!/bin/bash
        PID="\(currentPid)"
        TARGET="\(targetAppPath)"
        MOUNT="\(mountPoint)"
        DMG="\(dmgPath)"

        mkdir -p "$MOUNT"
        hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT" "$DMG" >/dev/null 2>&1

        SOURCE_APP="$MOUNT/MCP Browser.app"
        if [ ! -d "$SOURCE_APP" ]; then
            # fallback: find first .app on mount
            SOURCE_APP=$(find "$MOUNT" -maxdepth 1 -name "*.app" | head -n 1)
        fi

        # Wait for the current running app to terminate
        while kill -0 "$PID" 2>/dev/null; do
            sleep 0.2
        done

        if [ -d "$SOURCE_APP" ] && [ -n "$TARGET" ]; then
            rm -rf "$TARGET"
            cp -R "$SOURCE_APP" "$TARGET"
        fi

        # Unmount DMG and cleanup
        hdiutil detach "$MOUNT" -force >/dev/null 2>&1 || true
        rm -rf "$MOUNT" "$DMG"

        # Re-launch the updated application
        open -a "$TARGET"
        rm -f "\(helperScript)"
        """

        do {
            try script.write(toFile: helperScript, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: helperScript)

            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/bin/bash")
            proc.arguments = [helperScript]
            try proc.run()

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                NSApplication.shared.terminate(nil)
            }
        } catch {
            status = .error(message: "Failed to run update installer: \(error.localizedDescription)")
        }
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = .informational
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}
