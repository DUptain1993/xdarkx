#!/usr/bin/env python3
"""
OSRipper Setup Script
Proper setuptools configuration for pip installation
"""
import platform
import sys
import os
from pathlib import Path
from setuptools import setup, find_packages

# Read version from package
def get_version():
    """Get version from package __init__.py"""
    init_file = Path(__file__).parent / "src" / "osripper" / "__init__.py"
    if init_file.exists():
        with open(init_file, 'r') as f:
            for line in f:
                if line.startswith('__version__'):
                    return line.split('=')[1].strip().strip('"').strip("'")
    return "0.4.2"

# Read requirements
def get_requirements():
    """Read requirements from requirements.txt"""
    requirements_file = Path(__file__).parent / "requirements.txt"
    if requirements_file.exists():
        with open(requirements_file, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

# Read long description from README
def get_long_description():
    """Read long description from README"""
    readme_file = Path(__file__).parent / "README.MD"
    if readme_file.exists():
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

# Check for Windows (not supported)
if platform.system() == "Windows":
    print("This version does NOT support Windows. Please use an older version.")
    sys.exit(1)

# Optional ngrok configuration via environment variable
# Users can set OSRIPPER_NGROK_AUTH environment variable to configure ngrok
ngrok_auth = os.environ.get('OSRIPPER_NGROK_AUTH')
if ngrok_auth:
    print("Ngrok authentication token detected from environment variable.")
    creds_file = Path(__file__).parent / "creds"
    with open(creds_file, 'w') as creds:
        creds.write(str(ngrok_auth))
    print(f"Ngrok auth token saved to {creds_file}")
    # Note: ngrok authtoken command should be run separately by the user

# Setup configuration
setup(
    name="osripper",
    version=get_version(),
    author="NoahOksuz",
    description="Advanced Payload Generator and Crypter - FUD backdoor generator",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/SubGlitch1/OSRipper",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.6",
    install_requires=get_requirements(),
    entry_points={
        "console_scripts": [
            "osripper=osripper.main:main",
            "osripper-cli=osripper.cli:main_cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
