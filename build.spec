# PyInstaller spec file for OBS Remote
# Build: pyinstaller build.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        # Include the entire UI directory
        ('ui', 'ui'),
        # Include version file
        ('version.py', '.'),
    ],
    hiddenimports=[
        # obsws-python
        'obsws_python',
        'obsws_python.baseclient',
        'obsws_python.callback',
        'obsws_python.error',
        'obsws_python.reqs',
        'obsws_python.subs',
        # FastAPI / Starlette internals
        'fastapi',
        'fastapi.staticfiles',
        'fastapi.responses',
        'starlette',
        'starlette.routing',
        'starlette.staticfiles',
        'starlette.responses',
        'starlette.middleware.cors',
        # uvicorn
        'uvicorn',
        'uvicorn.main',
        'uvicorn.config',
        'uvicorn.lifespan.on',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.http.auto',
        'uvicorn.logging',
        'websockets',
        'websockets.legacy',
        'websockets.legacy.server',
        # Windows service
        'win32serviceutil',
        'win32service',
        'win32event',
        'servicemanager',
        # Tray
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        # misc
        'requests',
        'packaging',
        'packaging.version',
        'multipart',
        'email.mime.multipart',
        'anyio',
        'anyio._backends._asyncio',
        'sniffio',
        # Update dialog
        'tkinter',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OBSRemote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OBSRemote',
)
