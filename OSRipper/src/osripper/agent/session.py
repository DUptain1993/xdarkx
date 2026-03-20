#!/usr/bin/env python3
"""
Session Management Module
Handles session persistence and reconnection
"""

import os
import json
import time
import base64
import secrets


class SessionManager:
    """Session persistence and management."""
    
    def __init__(self, config_dir=None):
        """
        Initialize session manager.
        
        Args:
            config_dir: Directory to store session data (default: hidden location)
        """
        if config_dir is None:
            # Use hidden directory in home folder
            home = os.path.expanduser('~')
            if os.name == 'nt':  # Windows
                self.config_dir = os.path.join(home, 'AppData', 'Local', '.systemd')
            else:  # Linux/Mac
                self.config_dir = os.path.join(home, '.config', '.systemd')
        else:
            self.config_dir = config_dir
        
        # Create config directory if it doesn't exist
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.session_file = os.path.join(self.config_dir, '.session')
        self.session_id = None
        self.last_contact = None
        self.reconnect_count = 0
    
    def load_session(self):
        """
        Load existing session from disk.
        
        Returns:
            str: Session ID or None if no session exists
        """
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    self.session_id = data.get('session_id')
                    self.last_contact = data.get('last_contact')
                    self.reconnect_count = data.get('reconnect_count', 0)
                    return self.session_id
        except Exception:
            pass
        
        return None
    
    def create_session(self):
        """
        Create new session.
        
        Returns:
            str: New session ID
        """
        # Generate cryptographically random session ID
        self.session_id = base64.urlsafe_b64encode(
            secrets.token_bytes(16)
        ).decode('ascii').rstrip('=')
        
        self.last_contact = time.time()
        self.reconnect_count = 0
        
        self.save_session()
        return self.session_id
    
    def save_session(self):
        """Save session to disk."""
        try:
            data = {
                'session_id': self.session_id,
                'last_contact': self.last_contact,
                'reconnect_count': self.reconnect_count
            }
            
            with open(self.session_file, 'w') as f:
                json.dump(data, f)
            
            # Hide file on Unix systems
            if os.name != 'nt':
                os.chmod(self.session_file, 0o600)
                
        except Exception:
            pass
    
    def update_contact(self):
        """Update last contact time."""
        self.last_contact = time.time()
        self.reconnect_count = 0
        self.save_session()
    
    def increment_reconnect(self):
        """Increment reconnect counter."""
        self.reconnect_count += 1
        self.save_session()
    
    def get_reconnect_delay(self):
        """
        Get exponential backoff delay for reconnection.
        
        Returns:
            int: Delay in seconds
        """
        # Exponential backoff: 5s, 10s, 20s, 40s, max 60s
        delays = [5, 10, 20, 40, 60]
        index = min(self.reconnect_count, len(delays) - 1)
        return delays[index]
    
    def get_session_id(self):
        """Get current session ID."""
        return self.session_id
    
    def clear_session(self):
        """Clear session data."""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            self.session_id = None
            self.last_contact = None
            self.reconnect_count = 0
        except Exception:
            pass

