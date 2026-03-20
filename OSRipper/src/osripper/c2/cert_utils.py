#!/usr/bin/env python3
"""
Certificate Utilities
Generate self-signed certificates for HTTPS C2 server
"""

import os
import ssl
import socket
from datetime import datetime, timedelta

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


def generate_self_signed_cert(hostname='localhost', cert_file='c2_server.crt', key_file='c2_server.key', days_valid=365):
    """
    Generate self-signed certificate and private key.
    
    Args:
        hostname: Hostname for the certificate
        cert_file: Path to save certificate file
        key_file: Path to save private key file
        days_valid: Number of days certificate is valid
        
    Returns:
        tuple: (cert_file_path, key_file_path)
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        # Fallback if cryptography not available - use openssl command
        import subprocess
        
        # Generate certificate using openssl
        cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', key_file, '-out', cert_file,
            '-days', str(days_valid), '-nodes',
            '-subj', f'/C=US/ST=CA/L=San Francisco/O=OSRipper C2/CN={hostname}'
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise Exception(f"OpenSSL failed: {result.stderr.decode()}")
        
        return cert_file, key_file
    
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OSRipper C2"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])
        
        # Build certificate
        cert_builder = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=days_valid)
        )
        
        # Add SAN extension
        san_list = [
            x509.DNSName(hostname),
            x509.DNSName("localhost"),
        ]
        
        # Try to add IP address (may fail on some systems)
        try:
            from ipaddress import ip_address
            san_list.append(x509.IPAddress(ip_address("127.0.0.1")))
        except:
            pass
        
        cert_builder = cert_builder.add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        
        cert = cert_builder.sign(private_key, hashes.SHA256())
        
        # Write certificate
        with open(cert_file, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        # Write private key
        with open(key_file, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        return cert_file, key_file
        
    except Exception as e:
        # Fallback to openssl if cryptography fails
        import subprocess
        
        cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', key_file, '-out', cert_file,
            '-days', str(days_valid), '-nodes',
            '-subj', f'/C=US/ST=CA/L=San Francisco/O=OSRipper C2/CN={hostname}'
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise Exception(f"Certificate generation failed: {e}")
        
        return cert_file, key_file


def get_certificate_fingerprint(cert_file):
    """
    Get SHA256 fingerprint of certificate file.
    
    Args:
        cert_file: Path to certificate file
        
    Returns:
        str: SHA256 fingerprint (hex, lowercase)
    """
    try:
        import hashlib
        
        with open(cert_file, 'rb') as f:
            cert_data = f.read()
        
        # Parse PEM certificate
        if cert_data.startswith(b'-----BEGIN'):
            # Extract base64 part (remove headers and whitespace)
            import base64
            lines = cert_data.split(b'\n')
            base64_lines = [line.strip() for line in lines 
                           if line.strip() and not line.startswith(b'-----')]
            base64_data = b''.join(base64_lines)
            cert_der = base64.b64decode(base64_data)
        else:
            cert_der = cert_data
        
        # Calculate SHA256 fingerprint
        fingerprint = hashlib.sha256(cert_der).hexdigest()
        return fingerprint.lower()
        
    except Exception:
        return None


def get_certificate_fingerprint_from_url(url):
    """
    Get SHA256 fingerprint from live HTTPS server.
    
    Args:
        url: HTTPS URL (e.g., "https://example.com")
        
    Returns:
        str: SHA256 fingerprint (hex, lowercase) or None
    """
    try:
        import socket
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or 443
        
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert_der = ssock.getpeercert(binary_form=True)
                import hashlib
                fingerprint = hashlib.sha256(cert_der).hexdigest()
                return fingerprint.lower()
                
    except Exception:
        return None

