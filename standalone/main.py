"""
main.py — NT Greek FLEx Import Tool, standalone entry point
============================================================
Launches a pywebview window containing the passage-selection frontend.
The JS frontend handles all SWORD/JSON data loading; when the user clicks
"Import to FLEx" the processed verse data is passed to this Python backend
which writes the text directly into the FLEx LCM database.

Usage:
    python main.py                  # windowed only, log to file
    python main.py --console        # windowed + console output (debug mode)

PyInstaller build: --onedir, windowed (no console by default).
With --console flag at runtime the app allocates a console window.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Logging — must be set up before any other imports so we capture everything
# ---------------------------------------------------------------------------

APP_NAME    = 'NT Greek FLEx Import Tool'
APP_VERSION = '0.1.0-dev'
LOG_DIR     = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')),
    'BiblicalLanguages', 'Logs'
)

def _attach_console():
    """
    When running as a PyInstaller windowed .exe with --console, allocate or
    attach a console window so that log output is visible.
    Has no effect on non-Windows or when already running in a console.
    """
    if sys.platform != 'win32':
        return
    if not getattr(sys, 'frozen', False):
        return  # not a PyInstaller build — already in a terminal
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        # Try to attach to the parent process console (e.g. cmd.exe that launched us)
        if not k32.AttachConsole(0xFFFFFFFF):   # ATTACH_PARENT_PROCESS
            k32.AllocConsole()
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
    except Exception:
        pass  # best-effort; don't crash if console attach fails


def setup_logging(console: bool) -> str:
    """
    Configure the root logger.

    Always:  DEBUG → rotating log file in %APPDATA%\\BiblicalLanguages\\Logs\\
    Optional (--console): DEBUG → stderr  (after attaching/allocating console)

    Returns the path of the log file for display in the UI.
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass

    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = os.path.join(LOG_DIR, f'import_{ts}.log')

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        '%(asctime)s.%(msecs)03d  %(levelname)-8s  %(name)-35s  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # --- File handler (always) ---
    try:
        fh = logging.FileHandler(log_path, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        # If log file fails, keep going — just lose file logging
        print(f'Warning: could not open log file {log_path}: {e}', file=sys.stderr)
        log_path = '(log file unavailable)'

    # --- Console handler (--console only) ---
    if console:
        _attach_console()
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    return log_path


# ---------------------------------------------------------------------------
# pywebview API — methods callable from JavaScript
# ---------------------------------------------------------------------------

class Api:
    """
    Bridge between the JavaScript frontend and Python backend.
    All public methods are callable from JS as window.pywebview.api.<method>().
    Return values must be JSON-serialisable.
    """

    def __init__(self, log_path: str):
        self._log_path    = log_path
        self._project_path = None
        self._log          = logging.getLogger(f'{__name__}.Api')
        self._log.info('Api initialised  log_path=%s', log_path)

    # -- Info -----------------------------------------------------------------

    def get_log_path(self) -> str:
        """Return the path to the current log file so the UI can display it."""
        return self._log_path

    def get_app_version(self) -> str:
        return APP_VERSION

    # -- FLEx state checks ----------------------------------------------------

    def is_flex_running(self) -> bool:
        """
        Return True if FieldWorks Language Explorer is currently running.
        Must be False before opening the LCM project — LCM uses exclusive
        file locking.
        """
        self._log.debug('is_flex_running() called')
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                name = (proc.info.get('name') or '').lower()
                if 'fieldworks' in name or 'flex' in name:
                    self._log.info('FLEx process detected: %s', proc.info['name'])
                    return True
            self._log.debug('No FLEx process found')
            return False
        except Exception:
            self._log.warning('psutil check failed', exc_info=True)
            return False   # can't tell — let the import attempt fail gracefully

    def find_flex_projects(self) -> list:
        """
        Return a list of likely .fwdata paths from the default FLEx project
        directory (%LOCALAPPDATA%\\SIL\\FieldWorks\\Projects) so the UI can
        suggest them.  Returns [] if nothing found.
        """
        self._log.debug('find_flex_projects() called')
        candidates = []
        base = os.path.join(
            os.environ.get('LOCALAPPDATA', ''),
            'SIL', 'FieldWorks', 'Projects'
        )
        self._log.debug('Scanning for projects under: %s', base)
        try:
            if os.path.isdir(base):
                for entry in os.scandir(base):
                    if entry.is_dir():
                        fwdata = os.path.join(entry.path, entry.name + '.fwdata')
                        if os.path.isfile(fwdata):
                            self._log.debug('Found project: %s', fwdata)
                            candidates.append(fwdata)
        except Exception:
            self._log.warning('Project scan failed', exc_info=True)
        self._log.info('find_flex_projects: %d project(s) found', len(candidates))
        return candidates

    # -- Project selection ----------------------------------------------------

    def select_project(self) -> str | None:
        """
        Open a file-picker dialog and return the chosen .fwdata path,
        or None if cancelled.
        """
        self._log.info('select_project() — opening file dialog')
        import webview
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=('FLEx Projects (*.fwdata)', 'All files (*.*)')
        )
        if not result:
            self._log.info('select_project: cancelled')
            return None
        path = result[0] if isinstance(result, (list, tuple)) else result
        self._log.info('select_project: chose %s', path)
        self._project_path = path
        return path

    # -- Import ---------------------------------------------------------------

    def save_template(self) -> dict:
        """
        Save the bundled NT Greek project template (.fwbackup) to a
        user-chosen location.  Returns {'ok': True, 'path': ...} or
        {'ok': False, 'error': ...}.
        """
        log = self._log
        log.info('save_template() called')
        import webview, shutil

        # Locate the bundled template
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'docs', 'assets')
        template_src = os.path.join(base, 'NT Greek blank project.fwbackup')
        log.debug('template_src: %s  exists=%s', template_src,
                  os.path.isfile(template_src))

        if not os.path.isfile(template_src):
            msg = f'Template file not found at {template_src}'
            log.error(msg)
            return {'ok': False, 'error': msg}

        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory    = os.path.expanduser('~'),
            save_filename= 'NT Greek blank project.fwbackup',
            file_types   = ('FLEx Backup (*.fwbackup)', 'All files (*.*)')
        )
        if not result:
            log.info('save_template: cancelled')
            return {'ok': False, 'error': 'Cancelled.'}

        dest = result[0] if isinstance(result, (list, tuple)) else result
        if not dest.lower().endswith('.fwbackup'):
            dest += '.fwbackup'

        try:
            shutil.copy2(template_src, dest)
            log.info('Template saved to: %s', dest)
            return {'ok': True, 'path': dest}
        except Exception as e:
            log.error('Template save failed: %s', e, exc_info=True)
            return {'ok': False, 'error': str(e)}

    def get_writing_systems(self, project_path: str) -> dict:
        """
        Open the FLEx project briefly (FLEx must be closed), read the
        available writing system IDs, and return them.

        Returns:
            { 'vernacular': str, 'analysis': str,
              'all_vernacular': [...], 'all_analysis': [...] }
        or  { 'error': str }
        """
        log = self._log
        log.info('get_writing_systems: %s', project_path)

        if self.is_flex_running():
            return {'error': 'FLEx is running — please close it first.'}

        if not project_path or not os.path.isfile(project_path):
            return {'error': f'Project file not found: {project_path}'}

        try:
            from core.flex_project import FLExProject
            with FLExProject(project_path) as proj:
                lp = proj.lp

                def ws_info(ws_obj):
                    try:
                        return {'id': ws_obj.Id, 'label': ws_obj.DisplayLabel}
                    except Exception:
                        return {'id': str(ws_obj), 'label': ''}

                def_vern = ws_info(lp.DefaultVernacularWritingSystem)
                def_anal = ws_info(lp.DefaultAnalysisWritingSystem)

                all_vern = [ws_info(ws) for ws in lp.CurrentVernacularWritingSystems]
                all_anal = [ws_info(ws) for ws in lp.CurrentAnalysisWritingSystems]

                log.info('  vernacular=%s  analysis=%s', def_vern['id'], def_anal['id'])
                return {
                    'vernacular':     def_vern['id'],
                    'analysis':       def_anal['id'],
                    'all_vernacular': all_vern,
                    'all_analysis':   all_anal,
                }
        except Exception as e:
            log.error('get_writing_systems failed', exc_info=True)
            return {'error': str(e)}

    def import_to_flex(self, project_path: str,
                       passage_ref: str,
                       verses_json: str,
                       ws_grc: str = '',
                       ws_en: str  = '',
                       ws_trans: str = '') -> dict:
        """
        Main import entry point called from JS when the user clicks
        "Import to FLEx".

        Args:
            project_path:  absolute path to the .fwdata file
            passage_ref:   human-readable title, e.g. 'Acts 6:1-7'
            verses_json:   JSON string — list of verse dicts with the shape:
                           [ { ref, words:[{g, S, l, gls}], translation }, ... ]

        Returns a dict with at minimum:
            { 'ok': bool, 'message': str }
        plus extra fields on success (n_tokens, n_split, log_path).
        """
        log = self._log
        log.info('=' * 60)
        log.info('import_to_flex START')
        log.info('  project_path = %s', project_path)
        log.info('  passage_ref  = %s', passage_ref)
        log.info('  ws_grc=%r  ws_en=%r  ws_trans=%r', ws_grc, ws_en, ws_trans)

        # -- Pre-flight checks -----------------------------------------------

        if not project_path or not os.path.isfile(project_path):
            msg = f'Project file not found: {project_path}'
            log.error(msg)
            return {'ok': False, 'message': msg}

        if self.is_flex_running():
            msg = ('FieldWorks Language Explorer is running. '
                   'Please close FLEx before importing.')
            log.warning(msg)
            return {'ok': False, 'message': msg}

        # -- Parse verse data ------------------------------------------------

        log.info('Parsing verses_json...')
        try:
            if isinstance(verses_json, str):
                verses = json.loads(verses_json)
            else:
                verses = verses_json   # already a list if pywebview passed it as object
            log.info('  %d verse(s) received', len(verses))
            for i, v in enumerate(verses[:3]):
                log.debug('  verse[%d]: ref=%s  words=%d  translation=%r',
                          i, v.get('ref'), len(v.get('words', [])),
                          (v.get('translation') or '')[:60])
        except Exception as e:
            msg = f'Failed to parse verse data: {e}'
            log.error(msg, exc_info=True)
            return {'ok': False, 'message': msg}

        if not verses:
            return {'ok': False, 'message': 'No verse data provided.'}

        # -- Open project and run import -------------------------------------

        log.info('Opening FLEx project: %s', project_path)
        try:
            # Import here (not at module level) so that import errors on non-Windows
            # only surface at call time, not at module load.
            from core.flex_project import FLExProject
            from core.importer   import create_flex_text, get_or_create_wordform
            from core.glosses    import split_all_slash_glosses
        except ImportError as e:
            msg = f'Could not load LCM modules: {e}'
            log.critical(msg, exc_info=True)
            return {'ok': False, 'message': msg}

        try:
            with FLExProject(project_path) as project:
                log.info('Project opened OK')

                # Writing systems — use caller-supplied IDs if given,
                # otherwise fall back to project defaults
                try:
                    lp = project.lp
                    def _resolve_ws(ws_id_hint, default_ws_obj):
                        """Return the integer handle for a WS, optionally by ID string."""
                        if ws_id_hint:
                            # Search the project's WSs for a match by Id
                            for ws in list(lp.CurrentVernacularWritingSystems) + \
                                      list(lp.CurrentAnalysisWritingSystems):
                                if ws.Id == ws_id_hint:
                                    log.debug('  resolved WS %r → handle %s',
                                              ws_id_hint, ws.Handle)
                                    return ws.Handle
                            log.warning('  WS id %r not found in project — '
                                        'using project default', ws_id_hint)
                        return default_ws_obj.Handle

                    ws_en_handle    = _resolve_ws(ws_en,    lp.DefaultAnalysisWritingSystem)
                    ws_grc_handle   = _resolve_ws(ws_grc,   lp.DefaultVernacularWritingSystem)
                    ws_trans_handle = _resolve_ws(ws_trans,  lp.DefaultAnalysisWritingSystem)
                    log.info('ws_en=%s  ws_grc=%s  ws_trans=%s',
                             ws_en_handle, ws_grc_handle, ws_trans_handle)
                except Exception as e:
                    raise RuntimeError(f'Could not read writing systems: {e}') from e

                cache = project.project   # raw LcmCache

                # Create the text (wrapped in an undo task)
                log.info('Creating interlinear text: %r', passage_ref)
                cache.BeginUndoTask(
                    f'Import {passage_ref}',
                    f'Import {passage_ref}'
                )
                try:
                    n_tokens = create_flex_text(
                        cache, project.lp,
                        ws_en_handle, ws_grc_handle,
                        passage_ref, verses,
                        ws_trans=ws_trans_handle,
                    )
                    log.info('Text created: %d token(s)', n_tokens)

                    # Split slash glosses across the whole project
                    n_split, n_total = split_all_slash_glosses(cache, ws_en)
                    log.info('Gloss split: %d/%d', n_split, n_total)

                    cache.EndUndoTask()
                    log.info('Undo task committed')
                except Exception:
                    log.error('Exception during import — cancelling undo task',
                              exc_info=True)
                    try:
                        cache.CancelUndoTask()
                    except Exception:
                        log.error('CancelUndoTask also failed', exc_info=True)
                    raise

        except Exception as e:
            msg = f'Import failed: {e}'
            log.error(msg, exc_info=True)
            return {'ok': False, 'message': msg, 'log_path': self._log_path}

        msg = (f'Imported {n_tokens} words from {passage_ref}. '
               f'{n_split} slash glosses split into individual choices. '
               f'Close this app and open FLEx to begin analysis.')
        log.info('import_to_flex SUCCESS: %s', msg)
        log.info('=' * 60)
        return {
            'ok':       True,
            'message':  msg,
            'n_tokens': n_tokens,
            'n_split':  n_split,
            'log_path': self._log_path,
        }


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------

def _find_frontend() -> str:
    """Return absolute path to the frontend index.html."""
    if getattr(sys, 'frozen', False):
        # PyInstaller: files are in _MEIPASS
        base = sys._MEIPASS
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
    path = os.path.join(base, 'index.html')
    logging.getLogger(__name__).debug('Frontend path: %s', path)
    return path


def main():
    parser = argparse.ArgumentParser(
        description=f'{APP_NAME} v{APP_VERSION}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python main.py               # normal windowed mode\n'
            '  python main.py --console     # window + console debug output\n'
        )
    )
    parser.add_argument(
        '--console', action='store_true',
        help='Enable verbose console output alongside the log file (debug mode)'
    )
    args = parser.parse_args()

    log_path = setup_logging(console=args.console)
    log = logging.getLogger(__name__)

    log.info('=' * 70)
    log.info('%s  v%s', APP_NAME, APP_VERSION)
    log.info('Python  %s', sys.version)
    log.info('Platform  %s', sys.platform)
    log.info('Frozen  %s', getattr(sys, 'frozen', False))
    log.info('Log file  %s', log_path)
    log.info('--console  %s', args.console)

    # Validate frontend exists before launching the window
    frontend = _find_frontend()
    if not os.path.isfile(frontend):
        log.critical('Frontend not found at %s', frontend)
        sys.exit(f'Error: frontend not found at {frontend}')

    api = Api(log_path=log_path)

    import webview
    log.info('Creating pywebview window')
    webview.create_window(
        title      = APP_NAME,
        url        = frontend,
        js_api     = api,
        width      = 920,
        height     = 820,
        resizable  = True,
        min_size   = (720, 540),
    )

    log.info('Starting pywebview event loop  debug=%s', args.console)
    # debug=True in pywebview opens the browser dev tools — useful with --console
    webview.start(debug=args.console)
    log.info('pywebview exited cleanly')


if __name__ == '__main__':
    main()
