#!/usr/bin/env python3
"""
OSRipper entry point for python -m osripper
"""

import sys

from .main import main

if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 6):
        print("[!] Python 3.6 or higher is required")
        sys.exit(1)
    
    main()

