# PyInstaller runtime hook for tkinter
import os
import sys

def _set_if_exists(env_key: str, path: str):
    if os.path.isdir(path):
        os.environ[env_key] = path

# Set TCL/TK environment variables and DLL search paths for bundled app
if hasattr(sys, '_MEIPASS'):
    base = sys._MEIPASS
    internal = os.path.join(base, '_internal')

    # Add DLL search directories for Windows (OpenSSL and friends)
    try:
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(base)
            if os.path.isdir(internal):
                os.add_dll_directory(internal)
    except Exception:
        # Fallback to PATH update
        os.environ['PATH'] = base + os.pathsep + os.environ.get('PATH', '')
        if os.path.isdir(internal):
            os.environ['PATH'] = internal + os.pathsep + os.environ['PATH']

    # Preferred locations we bundle to (root and _internal)
    tcl_candidates = [
        os.path.join(base, 'tcl8.6'),
        os.path.join(base, 'tcl', 'tcl8.6'),
        os.path.join(base, '_tcl_data'),  # PyInstaller default data name
        os.path.join(internal, 'tcl8.6'),
        os.path.join(internal, 'tcl', 'tcl8.6'),
        os.path.join(internal, '_tcl_data'),
    ]
    tk_candidates = [
        os.path.join(base, 'tk8.6'),
        os.path.join(base, 'tcl', 'tk8.6'),
        os.path.join(base, '_tk_data'),   # PyInstaller default data name
        os.path.join(internal, 'tk8.6'),
        os.path.join(internal, 'tcl', 'tk8.6'),
        os.path.join(internal, '_tk_data'),
    ]

    for p in tcl_candidates:
        if os.path.isdir(p):
            os.environ['TCL_LIBRARY'] = p
            break
    for p in tk_candidates:
        if os.path.isdir(p):
            os.environ['TK_LIBRARY'] = p
            break
