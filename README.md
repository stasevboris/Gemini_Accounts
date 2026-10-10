# Gemini Accounts

[English](#english) | [Русский](#русский)

---

<a name="english"></a>
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

1. [**Download GeminiAccounts-Setup.exe**](https://github.com/nikitaeight24family/GeminiAccounts/releases/latest/download/GeminiAccounts-Setup.exe) and click **Install**. No Python or administrator access required.
2. Click **Add Google account** and complete browser sign-in.
3. Open **Connect applications** and approve setup of installed clients. Original configs are backed up.

*A desktop shortcut is created. Updates preserve accounts and configurations.*

### 💻 Terminal: Windows, macOS and Linux

Download the matching CLI archive from [Releases](https://github.com/nikitaeight24family/GeminiAccounts/releases/latest), extract it and open a terminal in that folder.

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

---

<a name="русский"></a>
## 🇷🇺 Русский

Менеджер аккаунтов Google Antigravity с мониторингом квот Gemini / Claude и локальным шлюзом для Claude Code и Codex. Доступен в виде **Windows desktop приложения** и **терминального приложения для Windows, macOS и Linux**.

### 🚀 Что это такое?
**Gemini Accounts** — это локальный менеджер аккаунтов и шлюз маршрутизации, который объединяет несколько аккаунтов Google Antigravity. Он предоставляет единый локальный API, к которому могут подключаться ИИ-клиенты (такие как Claude Code и Codex), избавляя от необходимости вручную управлять множеством API-ключей.

#### Основные возможности
- **Автоматическая ротация и переключение:** Отслеживает лимиты квот для нескольких аккаунтов Google и автоматически направляет запросы на аккаунты с доступной квотой.
- **Мониторинг квот:** Отслеживает 5-часовые и недельные квоты для моделей Gemini и Claude, отображая визуальные прогресс-бары и обратный отсчет.
- **Бесшовная интеграция:** Автоматически настраивает поддерживаемые ИИ-клиенты (Claude Desktop, Claude Code CLI, Codex) для работы с локальным шлюзом.
- **Локальный прокси и очереди:** Удерживает запросы в локальной очереди при временном исчерпании квот, предотвращая сбои запросов и поддерживая соединение с клиентами с помощью keep-alive пакетов.
- **Конфиденциальность:** Все конфиденциальные локальные данные (резервные копии, ключи управления, статусы верификации) надежно шифруются с использованием DPAPI в Windows и Fernet в macOS/Linux.

#### Поддерживаемые модели
- **Семейство Gemini:** `gemini-3.1-pro-low`, `gemini-3.1-pro-high`, `gemini-3-flash`, `gemini-3-flash-lite`, `gemini-pro-agent`
- **Семейство Claude (через Antigravity):** `claude-sonnet-4-5`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `claude-haiku-4-5`

*Примечание: Вы можете использовать подписку Gemini Pro от Jio всего за ~1$!*

### 📦 Установка (Windows Desktop)

<img src="docs/compact-panel.png" alt="Панель аккаунтов и квот" width="320">

1. [**Скачайте GeminiAccounts-Setup.exe**](https://github.com/nikitaeight24family/GeminiAccounts/releases/latest/download/GeminiAccounts-Setup.exe) и нажмите **Install**. Python или права администратора не требуются.
2. Нажмите **Add Google account** и выполните вход в браузере.
3. Откройте **Connect applications** и подтвердите настройку установленных клиентов. Оригинальные конфиги будут сохранены.

*Ярлык будет создан на рабочем столе. При обновлении аккаунты и настройки сохраняются.*

### 💻 Терминал: Windows, macOS и Linux

Скачайте подходящий архив из [Releases](https://github.com/nikitaeight24family/GeminiAccounts/releases/latest), распакуйте его и откройте терминал в этой папке.

| Платформа | Архив | Команда запуска |
| --- | --- | --- |
| Windows x64 | `GeminiAccounts-CLI-windows-x64.zip` | `.\GeminiAccounts-CLI.exe` |
| Mac (Apple Silicon) | `GeminiAccounts-CLI-macos-arm64.tar.gz` | `./gemini-accounts` |
| Mac (Intel) | `GeminiAccounts-CLI-macos-x64.tar.gz` | `./gemini-accounts` |
| Linux x64 | `GeminiAccounts-CLI-linux-x64.tar.gz` | `./gemini-accounts` |

Используйте интерактивное меню для входа, проверки квот, верификации и настройки клиентов. Нажатие **Ctrl+C** или **Exit** останавливает сервисы.

### 🛠 Стек технологий
- **Язык:** Python 3.12+
- **GUI Фреймворк:** PySide6 (Qt for Python)
- **Библиотеки:** `bcrypt`, `cryptography` (Fernet), `PyYAML`, `ctypes` (DPAPI)
- **Нативный прокси:** Внешний Go-бинарник (`CLIProxyAPI`), работающий на `127.0.0.1:8318`
- **Локальный шлюз:** `ThreadingHTTPServer`, работающий на `127.0.0.1:8317`

### ⚙️ Подключения и восстановление

| Клиент | Изменения после подтверждения |
| --- | --- |
| **Claude Desktop (Windows)** | Локальный пресет шлюза для вкладки Code. Обычные веб-чаты сохраняют свое собственное подключение. |
| **Claude Code CLI (Все)** | URL шлюза, локальный ключ и дефолтные модели интегрируются в `~/.claude/settings.json`. |
| **Codex (Windows / CLI)** | Настраивается провайдер API и локальный каталог моделей в `~/.codex/config.toml`. |

**Восстановление:** в десктоп-версии **☰ → Connect applications → Restore previous settings / reset preferences**, или в терминале `./gemini-accounts restore`. Входы в Google сохраняются.

### 🛡️ Конфиденциальность и хранение
- Шлюз (`127.0.0.1:8317`) и нативный сервис (`127.0.0.1:8318`) работают исключительно локально.
- Каждая установка генерирует случайные ключи. **Релизы не содержат личных входов, закрытых ключей или истории.**
- Windows использует DPAPI для защиты ключей управления и бэкапов.
- Mac / Linux шифруют файлы с помощью Fernet и локального ключа хранилища пользователя.

### 🔨 Разработка
Требования: Python 3.12+
```sh
python -m pip install -r requirements-cli.txt
python console.py --help
python -m unittest discover -s tests
```

*Это независимый проект, не являющийся официальным приложением Google, Anthropic или OpenAI.*
