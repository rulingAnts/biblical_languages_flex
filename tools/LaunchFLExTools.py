"""
Launcher wrapper for FLExTools.

Checks whether FieldWorks Language Explorer (FLEx) is running before
opening FLExTools, and shows a clear warning if it is.  FLExTools opens
the FLEx project database directly; FLEx must be fully closed first.

This script is installed alongside FLExTools and is the target of the
Start Menu shortcut and installer finish-page "Launch FLExTools" option.
"""
import ctypes
import os
import subprocess
import sys

# Always locate FLExTools via LOCALAPPDATA — do not rely on __file__
# resolution, which can vary depending on how the launcher is invoked.
FLEXTOOLS_DIR    = os.path.join(os.environ['LOCALAPPDATA'], 'FLExTools')
FLEXTOOLS_SCRIPT = os.path.join(FLEXTOOLS_DIR, 'FlexTools.py')

# Windows MessageBox flags
MB_OK          = 0x00
MB_ICONWARNING = 0x30
MB_ICONERROR   = 0x10


def _msgbox(title, text, flags=MB_OK):
    ctypes.windll.user32.MessageBoxW(0, text, title, flags)


def _flex_is_running():
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq FieldWorks.exe', '/NH'],
            capture_output=True, text=True, timeout=5
        )
        return 'FieldWorks.exe' in result.stdout
    except Exception:
        return False  # If we can't check, proceed anyway


def main():
    if _flex_is_running():
        _msgbox(
            'Close FLEx First',
            'FieldWorks Language Explorer (FLEx) is currently running.\n\n'
            'FLExTools opens your project database directly and cannot run '
            'while FLEx is open.\n\n'
            'Please close FLEx completely, then launch FLExTools again.',
            MB_OK | MB_ICONWARNING
        )
        return

    if not os.path.isfile(FLEXTOOLS_SCRIPT):
        # Build a directory listing to help diagnose the problem
        try:
            contents = '\n'.join(sorted(os.listdir(FLEXTOOLS_DIR)))
        except Exception:
            contents = '(could not read directory)'
        _msgbox(
            'FLExTools Not Found',
            'Could not find FlexTools.py at:\n'
            + FLEXTOOLS_SCRIPT + '\n\n'
            'Contents of ' + FLEXTOOLS_DIR + ':\n'
            + contents + '\n\n'
            'Try re-running the FLEx Gloss Splitter installer.',
            MB_OK | MB_ICONERROR
        )
        return

    # Launch FLExTools using the same interpreter (pyw — no console window)
    subprocess.Popen([sys.executable, FLEXTOOLS_SCRIPT], cwd=FLEXTOOLS_DIR)


if __name__ == '__main__':
    main()
