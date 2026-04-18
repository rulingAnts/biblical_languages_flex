"""
Launcher wrapper for FLExTools.

Checks whether FieldWorks Language Explorer (FLEx) is running before
opening FLExTools, and shows a clear warning if it is.  FLExTools opens
the FLEx project database directly; FLEx must be fully closed first.

FLExTools entry point: %LOCALAPPDATA%\FLExTools\scripts\RunFlexTools.py
(FlexTools.vbs -> scripts\FlexToolsCommands.vbs RUN -> py scripts\RunFlexTools.py)
We invoke RunFlexTools.py directly so cmd.exe / VBScript is never needed.
"""
import ctypes
import os
import subprocess
import sys

FLEXTOOLS_DIR    = os.path.join(os.environ['LOCALAPPDATA'], 'FLExTools')
FLEXTOOLS_SCRIPT = os.path.join(FLEXTOOLS_DIR, 'scripts', 'RunFlexTools.py')

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
        return False


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
        try:
            contents = '\n'.join(sorted(os.listdir(FLEXTOOLS_DIR)))
        except Exception:
            contents = '(could not read directory)'
        _msgbox(
            'FLExTools Not Found',
            'Could not find RunFlexTools.py at:\n'
            + FLEXTOOLS_SCRIPT + '\n\n'
            'Contents of ' + FLEXTOOLS_DIR + ':\n'
            + contents + '\n\n'
            'Try re-running the FLEx Gloss Splitter installer.',
            MB_OK | MB_ICONERROR
        )
        return

    # Run via the same interpreter (pyw.exe — no console window).
    # Working dir must be the FLExTools root so relative imports in
    # RunFlexTools.py (e.g. "from Version import Title") resolve correctly.
    subprocess.Popen([sys.executable, FLEXTOOLS_SCRIPT], cwd=FLEXTOOLS_DIR)


if __name__ == '__main__':
    main()
