# Gemini Accounts

[English](README.md) | [Русский](README_RU.md)

---

## 🇬🇧 English

Google Antigravity account manager with Gemini / Claude quota monitoring and a local gateway for Claude Code and Codex. Available as a **Windows desktop app** and a **terminal app for Windows, macOS and Linux**.

### 🚀 What is this?
**Gemini Accounts** is a local account manager and routing gateway that multiplexes multiple Google Antigravity accounts. It provides a unified local API endpoint that AI clients (like Claude Code and Codex) can connect to without needing to manage multiple API keys manually.

#### Key Features
- **Automatic Account Rotation & Failover:** Monitors quota limits across multiple Google accounts and automatically routes requests to accounts with available quota.
- **Quota Monitoring:** Tracks Google's 5-hour and 1-week quota buckets for Gemini and Claude models, complete with visual progress bars and countdowns.
- **Seamless Integration:** Automatically configures supported third-party AI clients (Claude Desktop, Claude Code CLI, Codex) to point to its local gateway.
- **Local Proxy & Queueing:** Holds requests in a local queue if quota is temporarily exhausted, preventing request failures and keeping upstream clients alive via streaming keep-alives.
- **Privacy First:** All sensitive local data (backups, management keys, verification states) is encrypted using DPAPI on Windows and Fernet on macOS/Linux.

#### Supported Models
- **Gemini Family:** `gemini-3.1-pro-low`, `gemini-3.1-pro-high`, `gemini-3-flash`, `gemini-3-flash-lite`, `gemini-pro-agent`
- **Claude Family (via Antigravity):** `claude-sonnet-4-5`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `claude-haiku-4-5`

*Note: You can use Gemini Pro through Jio for as little as $1!*

### 📦 Installation (Windows Desktop)

<img src="docs/compact-panel.png" alt="Compact panel with verification controls, model names, independent Gemini and Claude selections, and pooled quotas" width="320">

1. [**Download GeminiAccounts-Setup.exe**](https://github.com/stasevboris/Gemini_Accounts/releases/latest/download/GeminiAccounts-Setup.exe) and click **Install**. No Python or administrator access required.
2. Click **Add Google account** and complete browser sign-in.
3. Open **Connect applications** and approve setup of installed clients. Original configs are backed up.

*A desktop shortcut is created. Updates preserve accounts and configurations.*

### 💻 Terminal: Windows, macOS and Linux

Download the matching CLI archive from [Releases](https://github.com/stasevboris/Gemini_Accounts/releases/latest), extract it and open a terminal in that folder.

| Platform | Archive | Start Command |
| --- | --- | --- |
| Windows x64 | `GeminiAccounts-CLI-windows-x64.zip` | `.\GeminiAccounts-CLI.exe` |
| Mac with Apple Silicon | `GeminiAccounts-CLI-macos-arm64.tar.gz` | `./gemini-accounts` |
| Mac with Intel | `GeminiAccounts-CLI-macos-x64.tar.gz` | `./gemini-accounts` |
| Linux x64 | `GeminiAccounts-CLI-linux-x64.tar.gz` | `./gemini-accounts` |

Use the interactive menu for sign-in, quotas, verification, client setup, and restoration. **Ctrl+C / Exit** stops services started by that terminal.

### 🛠 Tech Stack
- **Language:** Python 3.12+
- **GUI Framework:** PySide6 (Qt for Python)
- **Core Libraries:** `bcrypt`, `cryptography` (Fernet), `PyYAML`, `ctypes` (DPAPI)
- **Native Proxy Service:** External Go binary (`CLIProxyAPI`) running on `127.0.0.1:8318`
- **Local Gateway:** `ThreadingHTTPServer` running on `127.0.0.1:8317`

### ⚙️ Connections and Restoration

| Client | Changes after approval |
| --- | --- |
| **Claude Desktop (Windows)** | Local gateway preset for the Code tab. Ordinary web chats retain their own connection. |
| **Claude Code CLI (All)** | Gateway URL, local key, model defaults merged into `~/.claude/settings.json`. |
| **Codex (Windows / CLI)** | Responses API provider and local model catalog injected into `~/.codex/config.toml`. |

**Restore:** desktop **☰ → Connect applications → Restore previous settings / reset preferences**, or terminal `./gemini-accounts restore`. Google sign-ins are kept.

### 🛡️ Privacy & Storage
- Gateway (`127.0.0.1:8317`) and native service (`127.0.0.1:8318`) are local-only.
- Each installation receives random keys. **Releases contain no personal sign-ins, private keys, or history.**
- Windows uses DPAPI to protect management keys and backups.
- Mac / Linux encrypt these files with Fernet and a user-only local storage key.

### 🔨 Development
Requirements: Python 3.12+
```sh
python -m pip install -r requirements-cli.txt
python console.py --help
python -m unittest discover -s tests
```

*This is an independent project, not an official Google, Anthropic or OpenAI application.*
