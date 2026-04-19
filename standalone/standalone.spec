# standalone.spec — PyInstaller build configuration
#
# Build with:
#   cd standalone
#   pyinstaller standalone.spec
#
# Output:  dist/NTGreekFLExImport/   (onedir, no console window by default)
# Runtime: --console flag allocates a console for debug output

import sys, os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# ── Data files to bundle ────────────────────────────────────────────────────

# Pre-processed NT Greek JSON data (one file per book, ~27 files)
json_data = [
    (os.path.join('frontend', 'assets', 'data', '*.json'),
     os.path.join('assets', 'data')),
]

# Strongs gloss JSON (attribution: TBESG, CC BY 4.0)
strongs_data = [
    (os.path.join('..', 'docs', 'assets', 'strongs_greek.json'),
     'assets'),
]

# Bundled FLEx project template
template_data = [
    (os.path.join('..', 'docs', 'assets', 'NT Greek blank project.fwbackup'),
     '.'),   # placed at _MEIPASS root; main.py looks there
]

# Frontend HTML
frontend_data = [
    (os.path.join('frontend', 'index.html'), '.'),
]

datas = json_data + strongs_data + template_data + frontend_data

# ── Analysis ────────────────────────────────────────────────────────────────

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'pythonnet',
        'clr',
        'psutil',
        'webview',
        'core.flex_project',
        'core.importer',
        'core.glosses',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Executable ──────────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NTGreekFLExImport',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed — no console window by default
                            # use --console at runtime to allocate one
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='frontend/assets/icon.ico',  # add when icon is ready
)

# ── onedir collection ───────────────────────────────────────────────────────

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NTGreekFLExImport',
)
