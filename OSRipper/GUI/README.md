# OSRipper GUI

A local web-based GUI for OSRipper — works on **Termux, proot, Android, Linux, and macOS**.  
No display server or desktop environment required. Just open a browser.

---

## Quick Start

### Option A — one command (recommended)

```bash
cd OSRipper/GUI
bash run.sh
```

Then open **http://127.0.0.1:7070** in any browser.

### Option B — manual

```bash
cd OSRipper/GUI
pip3 install flask
python3 app.py
```

---

## Termux / Android Setup

```bash
# Install dependencies
pkg update && pkg install python git

# Clone if you haven't already
git clone https://github.com/SubGlitch1/OSRipper.git
cd OSRipper

# Install OSRipper
pip3 install -e .

# Start the GUI
bash GUI/run.sh
```

Open **http://127.0.0.1:7070** in your mobile browser (Firefox, Chrome, etc.).

For proot-distro (Debian/Ubuntu):

```bash
proot-distro login debian
# ... same steps as above
```

---

## LAN Access (serve to other devices on same Wi-Fi)

```bash
OSRIPPER_HOST=0.0.0.0 bash run.sh
```

Then open `http://<your-phone-ip>:7070` on any device on the same network.

---

## Custom Port

```bash
OSRIPPER_PORT=8888 bash run.sh
# or
python3 app.py --port 8888
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Bind Shell** | Port field, all payload options |
| **Reverse Shell** | IP + port fields, all options |
| **Staged Payload** | IP + port, all options |
| **DoH C2 Agent** | Domain field, all options |
| **Custom Crypter** | File upload (.py), all options |
| **C2 Server** | Domain, port, HTTPS toggle, debug toggle |
| **First-time Setup** | Installs pyngrok + Nuitka (required for `--ngrok` / `--compile`) |
| **Live terminal** | Streaming output as the command runs |
| **Result files** | Lists and lets you download everything in `results/` |
| **Kill running job** | Red Stop button while a job is active |

### Payload options (checkboxes)

| Option | What it does |
|--------|-------------|
| **Obfuscate** | Multi-layer code encoding |
| **Enhanced** | + anti-debug, VM detection, junk code (requires Obfuscate) |
| **Compile** | Compile to standalone binary via Nuitka (requires `setup` first) |
| **Stealth Delay** | Add 5–15 s random startup delay |
| **Fixed Name** | Keep exact output filename (no random suffix) |

---

## File Locations

```
OSRipper/
├── GUI/
│   ├── app.py          ← Flask server
│   ├── run.sh          ← One-command launcher
│   ├── requirements.txt
│   ├── uploads/        ← Temp storage for uploaded .py files
│   ├── templates/
│   │   └── index.html  ← Web UI
│   └── static/js/
│       └── app.js      ← Frontend logic
└── results/            ← All generated payload files (downloaded from GUI)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `flask` not found | `pip3 install flask` |
| `osripper-cli` not found | `pip3 install -e .` from OSRipper root |
| `--compile` fails | Click **Run Setup** in the GUI (installs Nuitka) |
| Page won't load | Make sure `run.sh` is still running; check the port |
| File upload fails | Ensure the file is a `.py` file under 32 MB |
| Can't reach from phone | Use `OSRIPPER_HOST=0.0.0.0 bash run.sh` |

---

## Security Note

The GUI runs **locally only** by default (`127.0.0.1`). Do not expose it to the internet.  
All payloads are for **authorized penetration testing only**.
