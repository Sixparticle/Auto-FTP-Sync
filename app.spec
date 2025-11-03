# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files
import os
import tkinter
import sys

# Manually collect Tcl/Tk runtime for tkinter on Windows/conda
_tk_datas = []
try:
    import sys
    # For conda environments, Tcl/Tk is in Library/lib
    conda_root = os.path.dirname(os.path.dirname(sys.executable))
    lib_path = os.path.join(conda_root, 'Library', 'lib')
    
    # Try conda location first
    _tcl86 = os.path.join(lib_path, 'tcl8.6')
    _tk86 = os.path.join(lib_path, 'tk8.6')
    _tcl8 = os.path.join(lib_path, 'tcl8')
    
    if os.path.isdir(_tcl86):
        _tk_datas.append((_tcl86, 'tcl8.6'))
    if os.path.isdir(_tk86):
        _tk_datas.append((_tk86, 'tk8.6'))
    if os.path.isdir(_tcl8):
        _tk_datas.append((_tcl8, 'tcl8'))
    
    # Also try standard location as fallback
    if not _tk_datas:
        _tcl_root = os.path.join(os.path.dirname(tkinter.__file__), 'tcl')
        _tcl86_alt = os.path.join(_tcl_root, 'tcl8.6')
        _tk86_alt = os.path.join(_tcl_root, 'tk8.6')
        if os.path.isdir(_tcl86_alt):
            _tk_datas.append((_tcl86_alt, 'tcl8.6'))
        if os.path.isdir(_tk86_alt):
            _tk_datas.append((_tk86_alt, 'tk8.6'))
except Exception as e:
    print(f"Warning: Could not collect Tcl/Tk data: {e}")

# Collect tkinter DLLs
_tk_binaries = []
try:
    import sys
    conda_root = os.path.dirname(sys.executable)
    
    # Check multiple locations for DLLs
    dll_locations = [
        os.path.join(conda_root, 'Library', 'bin'),
        os.path.join(conda_root, 'DLLs'),
    ]
    
    dll_names = ['tcl86t.dll', 'tk86t.dll', '_tkinter.pyd']
    
    for dll_name in dll_names:
        found = False
        for dll_path in dll_locations:
            dll_file = os.path.join(dll_path, dll_name)
            if os.path.exists(dll_file):
                _tk_binaries.append((dll_file, '.'))
                print(f"Found {dll_name} at {dll_file}")
                found = True
                break
        if not found:
            print(f"Warning: Could not find {dll_name}")
            
except Exception as e:
    print(f"Warning: Could not collect tkinter DLLs: {e}")

# Collect essential DLLs for ssl/expat/lzma/bz2/ffi
_extra_binaries = []
try:
    import glob
    conda_root = os.path.dirname(sys.executable)
    bin_dir = os.path.join(conda_root, 'Library', 'bin')
    if os.path.isdir(bin_dir):
        extra_names = [
            'libssl-3-x64.dll',
            'libcrypto-3-x64.dll',
            'libexpat.dll',
            'liblzma.dll',
            'LIBBZ2.dll',
            'ffi.dll',
        ]
        for name in extra_names:
            cand = os.path.join(bin_dir, name)
            if os.path.exists(cand):
                _extra_binaries.append((cand, '.'))
                print(f"Found {name} at {cand}")
            else:
                for match in glob.glob(os.path.join(bin_dir, name), recursive=False):
                    _extra_binaries.append((match, '.'))
                    print(f"Found {os.path.basename(match)} at {match}")
except Exception as e:
    print(f"Warning: Could not collect extra DLLs: {e}")

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=(_tk_binaries + _extra_binaries),
    datas=(collect_data_files('ttkthemes') + _tk_datas),
    hiddenimports=['ttkthemes', 'tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.scrolledtext', '_tkinter', 'ssl'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_tkinter.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AutoFTPSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='sync_icon.ico',
)
