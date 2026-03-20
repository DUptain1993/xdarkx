#!/usr/bin/env python3
"""
Session Manager Module
SQLite-based session management for C2 server
"""

import sqlite3
import json
import time
import threading
from datetime import datetime, timedelta


class SessionManager:
    """Session management with SQLite persistence."""
    
    def __init__(self, db_path='c2_sessions.db'):
        """
        Initialize session manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    hostname TEXT,
                    username TEXT,
                    platform TEXT,
                    command_queue TEXT,
                    response_data TEXT
                )
            ''')
            
            # Commands table (history)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    command TEXT,
                    response TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            ''')
            
            conn.commit()
            conn.close()
    
    def create_session(self, session_id, hostname=None, username=None, platform=None):
        """
        Create new session.
        
        Args:
            session_id: Unique session identifier
            hostname: Hostname of agent
            username: Username on agent system
            platform: Platform information
            
        Returns:
            bool: True if created successfully
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO sessions (session_id, hostname, username, platform, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                ''', (session_id, hostname, username, platform, datetime.now()))
                
                conn.commit()
                conn.close()
                return True
            except sqlite3.IntegrityError:
                # Session already exists, update last_seen
                self.update_last_seen(session_id)
                return True
            except Exception:
                return False
    
    def get_session(self, session_id):
        """
        Get session information.
        
        Args:
            session_id: Session identifier
            
        Returns:
            dict: Session information or None
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM sessions WHERE session_id = ?
                ''', (session_id,))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    return dict(row)
                return None
            except Exception:
                return None
    
    def update_last_seen(self, session_id):
        """
        Update last seen timestamp for session.
        
        Args:
            session_id: Session identifier
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE sessions SET last_seen = ? WHERE session_id = ?
                ''', (datetime.now(), session_id))
                
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def update_session_info(self, session_id, hostname=None, username=None, platform=None):
        """
        Update session system information.
        
        Args:
            session_id: Session identifier
            hostname: Hostname to update (only if not None)
            username: Username to update (only if not None)
            platform: Platform info to update (only if not None)
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Build update query dynamically based on what's provided
                updates = []
                params = []
                
                if hostname:
                    updates.append('hostname = ?')
                    params.append(hostname)
                if username:
                    updates.append('username = ?')
                    params.append(username)
                if platform:
                    updates.append('platform = ?')
                    params.append(platform)
                
                if updates:
                    params.append(session_id)
                    cursor.execute(f'''
                        UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?
                    ''', params)
                    
                    conn.commit()
                conn.close()
            except Exception:
                pass
    
    def queue_command(self, session_id, command):
        """
        Queue command for session.
        
        Args:
            session_id: Session identifier
            command: Command string to queue
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get existing queue
                cursor.execute('''
                    SELECT command_queue FROM sessions WHERE session_id = ?
                ''', (session_id,))
                
                row = cursor.fetchone()
                queue = json.loads(row[0]) if row and row[0] else []
                
                # Add command to queue
                queue.append({
                    'command': command,
                    'queued_at': datetime.now().isoformat()
                })
                
                # Update queue
                cursor.execute('''
                    UPDATE sessions SET command_queue = ? WHERE session_id = ?
                ''', (json.dumps(queue), session_id))
                
                # Also save to history immediately with empty response (will be updated when response arrives)
                cursor.execute('''
                    INSERT INTO commands (session_id, command, response)
                    VALUES (?, ?, ?)
                ''', (session_id, command, 'Waiting for response...'))
                
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def get_next_command(self, session_id):
        """
        Get next command from queue for session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            str: Command string or None if queue is empty
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get queue
                cursor.execute('''
                    SELECT command_queue FROM sessions WHERE session_id = ?
                ''', (session_id,))
                
                row = cursor.fetchone()
                if not row or not row[0]:
                    conn.close()
                    return None
                
                queue = json.loads(row[0])
                
                if not queue:
                    conn.close()
                    return None
                
                # Pop first command
                command_data = queue.pop(0)
                command = command_data['command']
                
                # Update queue
                cursor.execute('''
                    UPDATE sessions SET command_queue = ? WHERE session_id = ?
                ''', (json.dumps(queue), session_id))
                
                conn.commit()
                conn.close()
                
                return command
            except Exception:
                return None
    
    def save_response(self, session_id, command, response):
        """
        Save command response to history.
        
        Args:
            session_id: Session identifier
            command: Command that was executed
            response: Response from agent
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO commands (session_id, command, response)
                    VALUES (?, ?, ?)
                ''', (session_id, command, response))
                
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def update_response(self, session_id, command, response):
        """
        Update existing command response in history.
        
        Args:
            session_id: Session identifier
            command: Command that was executed
            response: Response from agent
            
        Returns:
            int: Number of rows updated (0 if no matching entry found)
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # First, find the ID of the most recent entry that matches
                cursor.execute('''
                    SELECT id FROM commands 
                    WHERE session_id = ? AND command = ? AND response = 'Waiting for response...'
                    ORDER BY id DESC
                    LIMIT 1
                ''', (session_id, command))
                
                result = cursor.fetchone()
                if result:
                    # Update the specific entry by ID
                    entry_id = result[0]
                    cursor.execute('''
                        UPDATE commands 
                        SET response = ?, executed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (response, entry_id))
                    rows_updated = cursor.rowcount
                    conn.commit()
                    conn.close()
                    return rows_updated
                else:
                    conn.close()
                    return 0
            except Exception as e:
                # Log error for debugging
                import traceback
                traceback.print_exc()
                return 0
    
    def get_all_sessions(self):
        """
        Get all active sessions.
        
        Returns:
            list: List of session dictionaries
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM sessions WHERE status = 'active' OR status IS NULL
                    ORDER BY last_seen DESC
                ''')
                
                rows = cursor.fetchall()
                conn.close()
                
                return [dict(row) for row in rows]
            except Exception:
                return []
    
    def get_session_history(self, session_id, limit=100):
        """
        Get command history for session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of commands to return
            
        Returns:
            list: List of command dictionaries
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM commands WHERE session_id = ?
                    ORDER BY executed_at DESC LIMIT ?
                ''', (session_id, limit))
                
                rows = cursor.fetchall()
                conn.close()
                
                return [dict(row) for row in rows]
            except Exception:
                return []
    
    def mark_session_inactive(self, session_id):
        """
        Mark session as inactive.
        
        Args:
            session_id: Session identifier
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE sessions SET status = 'inactive' WHERE session_id = ?
                ''', (session_id,))
                
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def cleanup_old_sessions(self, days=7):
        """
        Clean up sessions inactive for specified days.
        
        Args:
            days: Number of days of inactivity before cleanup
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cutoff = datetime.now() - timedelta(days=days)
                
                cursor.execute('''
                    UPDATE sessions SET status = 'inactive'
                    WHERE last_seen < ? AND status = 'active'
                ''', (cutoff,))
                
                conn.commit()
                conn.close()
            except Exception:
                pass
    
    def delete_session(self, session_id):
        """
        Delete session (mark as deleted).
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if deleted successfully, False if not found
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Mark as deleted instead of actually deleting (so we can detect it on beacon)
                cursor.execute('''
                    UPDATE sessions SET status = 'deleted' WHERE session_id = ?
                ''', (session_id,))
                
                rows_affected = cursor.rowcount
                conn.commit()
                conn.close()
                
                return rows_affected > 0
            except Exception:
                return False
    
    def is_session_deleted(self, session_id):
        """
        Check if session has been deleted.
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if session is deleted, False otherwise
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT status FROM sessions WHERE session_id = ?
                ''', (session_id,))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    return row[0] == 'deleted'
                return False
            except Exception:
                return False

