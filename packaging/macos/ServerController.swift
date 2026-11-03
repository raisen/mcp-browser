import Cocoa
import Foundation

class ServerController: NSObject {
    static let shared = ServerController()

    private(set) var isRunning: Bool = false
    private(set) var currentPid: Int? = nil
    var port: Int = 8765 {
        didSet {
            probeHealth()
        }
    }

    var onStateChanged: ((Bool, Int?) -> Void)?

    private var pollTimer: Timer?
    private var isBusy: Bool = false

    override init() {
        super.init()
        startPolling()
    }

    deinit {
        pollTimer?.invalidate()
    }

    func startPolling() {
        pollTimer?.invalidate()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            self?.probeHealth()
        }
        probeHealth()
    }

    func findCliPath() -> String? {
        if let envPath = ProcessInfo.processInfo.environment["MCP_BROWSER_CLI_PATH"],
           FileManager.default.fileExists(atPath: envPath) {
            return envPath
        }

        if let resURL = Bundle.main.resourceURL {
            let bundled = resURL.appendingPathComponent("mcp-browser/mcp-browser").path
            if FileManager.default.fileExists(atPath: bundled) {
                return bundled
            }
        }

        let candidates = [
            "/usr/local/bin/mcp-browser",
            "/opt/homebrew/bin/mcp-browser",
            FileManager.default.currentDirectoryPath + "/dist/mcp-browser/mcp-browser"
        ]
        for path in candidates {
            if FileManager.default.fileExists(atPath: path) {
                return path
            }
        }
        return nil
    }

    func probeHealth() {
        guard !isBusy else { return }
        let currentPort = port
        guard let url = URL(string: "http://127.0.0.1:\(currentPort)/healthz") else { return }

        var req = URLRequest(url: url)
        req.timeoutInterval = 0.8
        req.httpMethod = "GET"

        let task = URLSession.shared.dataTask(with: req) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let http = response as? HTTPURLResponse, http.statusCode == 200,
                   let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   json["ok"] as? Bool == true {
                    let pid = json["pid"] as? Int
                    self.updateState(running: true, pid: pid)
                } else {
                    self.updateState(running: false, pid: nil)
                }
            }
        }
        task.resume()
    }

    private func updateState(running: Bool, pid: Int?) {
        if isRunning != running || currentPid != pid {
            isRunning = running
            currentPid = pid
            onStateChanged?(running, pid)
        }
    }

    func startServer(completion: ((Bool, String?) -> Void)? = nil) {
        guard let cli = findCliPath() else {
            completion?(false, "mcp-browser executable not found in bundle or PATH.")
            return
        }

        isBusy = true
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: cli)
            proc.arguments = ["start", "--port", String(self.port)]

            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = pipe

            do {
                try proc.run()
                proc.waitUntilExit()
                let outputData = pipe.fileHandleForReading.readDataToEndOfFile()
                let outputStr = String(data: outputData, encoding: .utf8) ?? ""

                DispatchQueue.main.async {
                    self.isBusy = false
                    self.probeHealth()
                    if proc.terminationStatus == 0 {
                        completion?(true, nil)
                    } else {
                        completion?(false, "Server start failed: \(outputStr.trimmingCharacters(in: .whitespacesAndNewlines))")
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    self.isBusy = false
                    completion?(false, error.localizedDescription)
                }
            }
        }
    }

    func stopServer(completion: ((Bool, String?) -> Void)? = nil) {
        guard let cli = findCliPath() else {
            completion?(false, "mcp-browser executable not found.")
            return
        }

        isBusy = true
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: cli)
            proc.arguments = ["stop"]

            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = pipe

            do {
                try proc.run()
                proc.waitUntilExit()
                let outputData = pipe.fileHandleForReading.readDataToEndOfFile()
                let outputStr = String(data: outputData, encoding: .utf8) ?? ""

                DispatchQueue.main.async {
                    self.isBusy = false
                    self.probeHealth()
                    if proc.terminationStatus == 0 {
                        completion?(true, nil)
                    } else {
                        completion?(false, outputStr.trimmingCharacters(in: .whitespacesAndNewlines))
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    self.isBusy = false
                    completion?(false, error.localizedDescription)
                }
            }
        }
    }

    func openBrowser() {
        let tokenPath = ("~/Library/Application Support/mcp-browser/token" as NSString).expandingTildeInPath
        var token: String? = nil
        if let content = try? String(contentsOfFile: tokenPath, encoding: .utf8) {
            let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                token = trimmed
            }
        }

        let urlString: String
        if let t = token {
            urlString = "http://127.0.0.1:\(port)/#token=\(t)"
        } else {
            urlString = "http://127.0.0.1:\(port)/"
        }

        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }
    }

    func viewLogs() {
        let stateDir = ("~/Library/Application Support/mcp-browser" as NSString).expandingTildeInPath
        try? FileManager.default.createDirectory(atPath: stateDir, withIntermediateDirectories: true, attributes: nil)

        let logPath = (stateDir as NSString).appendingPathComponent("server.log")
        if !FileManager.default.fileExists(atPath: logPath) {
            FileManager.default.createFile(atPath: logPath, contents: "".data(using: .utf8), attributes: nil)
        }

        let logURL = URL(fileURLWithPath: logPath)
        NSWorkspace.shared.open(logURL)
    }
}
