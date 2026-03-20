"""
Helper for OSRipper's optional-deps venv (avoids externally-managed-environment on Linux).
Setup creates a venv and installs pyngrok, nuitka, sandboxed there; we add it to sys.path
and use its Python for subprocess (nuitka) when present.
"""
import os
import sys


def _venv_dir():
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "osripper", "venv")


def venv_exists():
    d = _venv_dir()
    py = _venv_python(d)
    return py is not None and os.path.isfile(py)


def _venv_python(venv_dir=None):
    if venv_dir is None:
        venv_dir = _venv_dir()
    # bin/python3, bin/python on Unix; Scripts/python.exe on Windows
    for name in ("bin", "Scripts"):
        for exe in ("python3", "python", "python.exe"):
            path = os.path.join(venv_dir, name, exe)
            if os.path.isfile(path):
                return path
    return None


def _venv_site_packages(venv_dir=None):
    if venv_dir is None:
        venv_dir = _venv_dir()
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    for lib in ("lib", "Lib"):
        path = os.path.join(venv_dir, lib, f"python{ver}", "site-packages")
        if os.path.isdir(path):
            return path
    return None


def get_venv_python():
    """Return venv python path if our venv exists, else sys.executable."""
    if not venv_exists():
        return sys.executable
    return _venv_python()


def ensure_venv_on_path():
    """If our optional-deps venv exists, prepend its site-packages to sys.path."""
    if not venv_exists():
        return
    site = _venv_site_packages()
    if site and site not in sys.path:
        sys.path.insert(0, site)


def get_venv_dir():
    """Return the venv directory path (for setup to create/use)."""
    return _venv_dir()
