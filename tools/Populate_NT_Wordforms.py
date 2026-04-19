"""
Populate NT Wordforms — FLExTools Module
=========================================
One-time developer script run against the NT Greek project template.

Reads the pre-processed NT Greek JSON data files (one per book) and
creates WfiWordform / WfiAnalysis / WfiGloss objects in the FLEx project
for every unique surface form in the New Testament.

After running this:
  - 22,519 WfiWordform objects exist (one per unique Greek surface form)
  - 22,580 WfiAnalysis objects exist (22,519 + 61 homographs with two
    analyses per wordform because they map to two different Strong's numbers)
  - WfiGloss objects with individual split glosses (never slash-separated)
  - Words with multiple gloss choices are left unapproved (blue in FLEx)
  - Words with a single gloss are approved (green)

This only needs to be run ONCE against the template project.  After it
runs, save/export the project as the new template .fwbackup.

The standalone import app then only needs to create the text structure
(IText / IStTxtPara / ISegment) and look up existing analyses — no
analysis creation happens at import time.

DATA SOURCE
  The JSON files are expected alongside this script in a sibling 'data'
  folder, or in the web app's docs/assets/data folder.  The script
  searches several candidate locations and asks the user to pick if none
  are found automatically.

  JSON format (per book):
    { "C:V": { "words": [{"g":"surface","S":"G1234","l":"lemma","gls":"gloss"}],
               "translation": "..." }, ... }

LOGGING
  %APPDATA%\\SIL\\FLExGlossSplitter\\Logs\\PopulateNTWordforms_YYYYMMDD_HHMMSS.log
"""

import json
import logging
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _init_log():
    log_dir = os.path.join(
        os.environ.get('APPDATA', os.path.expanduser('~')),
        'SIL', 'FLExGlossSplitter', 'Logs'
    )
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = os.path.join(log_dir, f'PopulateNTWordforms_{ts}.log')

    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s.%(msecs)03d  %(levelname)-8s  %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return log_path

LOG_PATH = _init_log()
log      = logging.getLogger(__name__)

log.info('=' * 70)
log.info('Populate NT Wordforms — module loaded')
log.info('Python %s', sys.version)

# ---------------------------------------------------------------------------
# FLExTools imports
# ---------------------------------------------------------------------------

try:
    from flextoolslib import (
        FlexToolsModuleClass,
        FTM_Name, FTM_Version, FTM_ModifiesDB,
        FTM_Synopsis, FTM_Help, FTM_Description,
    )
    log.info('flextoolslib imported OK')
except ImportError as e:
    log.critical('flextoolslib not found: %s', e)
    raise

try:
    from SIL.LCModel import (
        IWfiWordformRepository,
        IWfiWordformFactory,
        IWfiAnalysisFactory,
        IWfiGlossFactory,
    )
    from SIL.LCModel.Core.Text import TsStringUtils
    log.info('SIL.LCModel imports OK')
except ImportError as e:
    log.critical('SIL.LCModel not found: %s', e)
    raise

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    log.info('tkinter imported OK')
except ImportError as e:
    log.critical('tkinter not available: %s', e)
    raise

# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------

docs = {
    FTM_Name:        'Populate NT Wordforms',
    FTM_Version:     1,
    FTM_ModifiesDB:  True,
    FTM_Synopsis:    'One-time: pre-populate all NT surface form analyses in the template project.',
    FTM_Help:        None,
    FTM_Description: __doc__,
}

BOOK_NAMES = [
    'Matthew','Mark','Luke','John','Acts','Romans',
    '1Corinthians','2Corinthians','Galatians','Ephesians','Philippians',
    'Colossians','1Thessalonians','2Thessalonians','1Timothy','2Timothy',
    'Titus','Philemon','Hebrews','James','1Peter','2Peter',
    '1John','2John','3John','Jude','Revelation',
]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _candidate_data_dirs():
    """Return candidate paths where the book JSON files might live."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return [
        # Alongside the script in a 'data' subfolder
        os.path.join(script_dir, 'data'),
        # Web app docs folder (development layout)
        os.path.normpath(os.path.join(script_dir, '..', 'docs', 'assets', 'data')),
        # Standalone app frontend folder
        os.path.normpath(os.path.join(script_dir, '..', 'standalone', 'frontend', 'assets', 'data')),
    ]


def _find_data_dir():
    """
    Return the first candidate directory that contains at least one book JSON,
    or None if none found.
    """
    for d in _candidate_data_dirs():
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, 'Acts.json')):
            log.info('Found data directory: %s', d)
            return d
    log.warning('No data directory found in candidates: %s', _candidate_data_dirs())
    return None


def _pick_data_dir_dialog():
    """Ask the user to pick the data folder via a dialog."""
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(
        title='Select the folder containing the NT Greek JSON data files '
              '(Acts.json, Matthew.json, etc.)',
        initialdir=os.path.expanduser('~'),
    )
    root.destroy()
    return folder or None


def _split_form(gls):
    """Split 'to serve/heal' → ['serve','heal']; 'in/on/among' → ['in','on','among']."""
    parts = []
    for raw in gls.split('/'):
        p = raw.strip()
        if p.lower().startswith('to '):
            p = p[3:]
        if p:
            parts.append(p)
    return parts or ([gls.strip()] if gls.strip() else [])


def load_nt_data(data_dir):
    """
    Load all 27 book JSON files and return a dict:
        (surface_form, strongs_number) -> list_of_gloss_parts

    Gloss parts are already split (no slashes).
    """
    log.info('Loading NT data from: %s', data_dir)
    # (surface, strongs) -> set of individual gloss parts
    from collections import defaultdict
    combo_glosses = defaultdict(set)
    total_tokens  = 0
    missing_books = []

    for book in BOOK_NAMES:
        path = os.path.join(data_dir, f'{book}.json')
        if not os.path.isfile(path):
            log.warning('Missing book JSON: %s', path)
            missing_books.append(book)
            continue

        with open(path, encoding='utf-8') as f:
            book_data = json.load(f)

        book_tokens = 0
        for verse_key, verse in book_data.items():
            for w in verse.get('words', []):
                g   = (w.get('g') or '').strip()
                S   = (w.get('S') or '').strip()
                gls = (w.get('gls') or '').strip()
                if not g:
                    continue
                for part in (_split_form(gls) if gls else []):
                    combo_glosses[(g, S)].add(part)
                book_tokens += 1

        total_tokens += book_tokens
        log.info('  %-20s  %5d verses  %6d tokens', book,
                 len(book_data), book_tokens)

    if missing_books:
        log.warning('Missing books: %s', missing_books)

    log.info('Total tokens: %d  Unique (surface, strongs) combos: %d',
             total_tokens, len(combo_glosses))

    # Convert sets to sorted lists for deterministic output
    return {k: sorted(v) for k, v in combo_glosses.items()}


# ---------------------------------------------------------------------------
# Confirmation dialog
# ---------------------------------------------------------------------------

def _confirm_dialog(combo_count, wf_count, existing_wf_count):
    """
    Show a summary and ask the user to confirm before modifying the database.

    Returns (confirmed: bool, clean_first: bool).
    """
    root = tk.Toplevel()
    root.title('Populate NT Wordforms')
    root.geometry('560x400')
    root.grab_set()
    result = [False, False]   # [confirmed, clean_first]

    ttk.Label(root,
              text='Populate NT Wordforms',
              font=('TkDefaultFont', 11, 'bold')).pack(anchor='w', padx=16, pady=(14, 4))

    msg = (
        f'This will create:\n'
        f'  • {wf_count:,} WfiWordform objects (one per unique Greek surface form)\n'
        f'  • {combo_count:,} WfiAnalysis objects\n'
        f'    ({combo_count - wf_count} wordforms have two analyses — homographs)\n'
        f'  • WfiGloss objects with individual split glosses\n\n'
        f'Run this ONCE against the template project before distributing it.\n'
        f'The project must be the NT Greek template (not a working project).\n\n'
        f'This cannot be easily undone. Make sure you have a backup.'
    )
    ttk.Label(root, text=msg, justify='left', wraplength=520).pack(
        anchor='w', padx=16, pady=(0, 8))

    # ── "Clean first" option ─────────────────────────────────────────────────
    ttk.Separator(root, orient='horizontal').pack(fill=tk.X, padx=16, pady=4)

    clean_var = tk.BooleanVar(value=existing_wf_count > 0)

    clean_frame = ttk.Frame(root)
    clean_frame.pack(fill=tk.X, padx=16, pady=(4, 2))

    ttk.Checkbutton(
        clean_frame,
        text='Clean first — delete ALL existing wordforms and analyses before populating',
        variable=clean_var,
    ).pack(anchor='w')

    clean_note_text = (
        f'  Currently {existing_wf_count:,} WfiWordform(s) in the project. '
        f'Checking this deletes them\n'
        f'  all (and their owned analyses/glosses) before recreating from the JSON data.\n'
        f'  ⚠ Only safe on the template project — any existing texts will lose their\n'
        f'  analysis links.  Do not use on a working project.'
    )
    ttk.Label(root, text=clean_note_text, justify='left',
              foreground='#884400').pack(anchor='w', padx=16, pady=(0, 8))

    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill=tk.X, padx=16, pady=(0, 14))

    def on_ok():
        result[0] = True
        result[1] = clean_var.get()
        root.destroy()

    def on_cancel():
        root.destroy()

    ttk.Button(btn_frame, text='Cancel',    command=on_cancel).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text='Proceed →', command=on_ok).pack(side=tk.RIGHT, padx=(0, 6))

    root.wait_window()
    return result[0], result[1]


# ---------------------------------------------------------------------------
# Clean (delete all existing wordforms)
# ---------------------------------------------------------------------------

def _clear_all_wordforms(cache, report):
    """
    Delete every WfiWordform in the project, which cascade-deletes all owned
    WfiAnalysis and WfiGloss objects.

    Safe assumptions:
      - The project is the blank NT Greek template — no interlinear texts exist,
        so there are no ISegment.AnalysesRS references to become dangling.
      - Called inside FLExTools' undo task, so the operation is atomic.

    HVOs are collected first to avoid modifying the repository while iterating.

    Returns the number of WfiWordform objects deleted.
    """
    log.info('_clear_all_wordforms: collecting existing wordforms...')
    repo    = cache.ServiceLocator.GetService(IWfiWordformRepository)
    wf_list = list(repo.AllInstances())
    n       = len(wf_list)

    log.info('  %d WfiWordform(s) found — deleting...', n)
    report.Info(f'  Deleting {n:,} existing WfiWordform(s) '
                f'(and their analyses/glosses)…')

    deleted  = 0
    failed   = 0
    for wf in wf_list:
        hvo = wf.Hvo
        try:
            wf.Delete()
            deleted += 1
            if deleted % 2000 == 0:
                log.info('  … deleted %d / %d', deleted, n)
                report.Info(f'  … {deleted:,} / {n:,} deleted')
        except Exception as e:
            failed += 1
            log.warning('  Failed to delete WfiWordform hvo=%s: %s', hvo, e)

    log.info('_clear_all_wordforms done: deleted=%d  failed=%d', deleted, failed)
    if failed:
        report.Warning(f'  {failed} wordform(s) could not be deleted — see log.')
    return deleted


# ---------------------------------------------------------------------------
# Core population logic
# ---------------------------------------------------------------------------

def _build_existing_wf_cache(cache, ws_grc):
    """
    Return dict: greek_surface_form (str) -> IWfiWordform
    for all wordforms already in the project.
    """
    log.info('Building existing wordform cache...')
    repo     = cache.ServiceLocator.GetService(IWfiWordformRepository)
    existing = {}
    for wf in repo.AllInstances():
        try:
            ts = wf.Form.get_String(ws_grc)
            if ts and ts.Text:
                existing[ts.Text] = wf
        except Exception:
            pass
    log.info('  %d existing wordform(s) found', len(existing))
    return existing


def _populate(combo_glosses, cache, lp, ws_en, ws_grc, report):
    """
    Create WfiWordform / WfiAnalysis / WfiGloss objects for every
    (surface, strongs) combo.  Skips combos whose wordform + analysis
    already exist (idempotent — safe to re-run if interrupted).

    Returns (n_wf_created, n_analysis_created, n_gloss_created).
    """
    wf_factory  = cache.ServiceLocator.GetService(IWfiWordformFactory)
    ana_factory = cache.ServiceLocator.GetService(IWfiAnalysisFactory)
    gls_factory = cache.ServiceLocator.GetService(IWfiGlossFactory)

    existing_wf  = _build_existing_wf_cache(cache, ws_grc)
    n_wf         = 0
    n_ana        = 0
    n_gls        = 0
    n_skipped    = 0

    # Group combos by surface form for logging
    from collections import defaultdict
    by_surface = defaultdict(list)
    for (surface, strongs), parts in combo_glosses.items():
        by_surface[surface].append((strongs, parts))

    total = len(by_surface)
    log.info('Processing %d unique surface forms...', total)

    for i, (surface, analyses) in enumerate(sorted(by_surface.items()), 1):
        if i % 500 == 0 or i == total:
            pct = 100 * i / total
            log.info('  Progress: %d/%d  (%.1f%%)  wf=%d  ana=%d  gls=%d',
                     i, total, pct, n_wf, n_ana, n_gls)
            report.Info(f'  Progress: {i}/{total} surface forms processed...')

        # Get or create WfiWordform
        if surface in existing_wf:
            wf = existing_wf[surface]
            log.debug('  [%d] reusing WfiWordform hvo=%s for %r', i, wf.Hvo, surface)
        else:
            wf = wf_factory.Create()

            # Attach to LangProject — try FLEx 9+ path first, then 8.x
            attached = False
            for add_fn in [
                lambda: lp.WordformsOC.Add(wf),
                lambda: lp.WordformInventoryOA.WordformsOC.Add(wf),
            ]:
                try:
                    add_fn()
                    attached = True
                    break
                except Exception:
                    pass
            if not attached:
                log.warning('  [%d] could not attach WfiWordform for %r', i, surface)

            wf.Form.set_String(ws_grc, TsStringUtils.MakeString(surface, ws_grc))
            existing_wf[surface] = wf
            n_wf += 1
            log.debug('  [%d] created WfiWordform hvo=%s  form=%r', i, wf.Hvo, surface)

        # For each (strongs, gloss_parts) on this wordform
        for strongs, parts in analyses:
            # Check if an analysis with these exact glosses already exists
            # (simple check: if any analysis has same number of meanings with same forms)
            already_exists = False
            for existing_ana in wf.AnalysesOC:
                existing_parts = set()
                for g in existing_ana.MeaningsOC:
                    try:
                        ts = g.Form.get_String(ws_en)
                        if ts and ts.Text:
                            existing_parts.add(ts.Text)
                    except Exception:
                        pass
                if existing_parts == set(parts):
                    already_exists = True
                    log.debug('    analysis already exists for %r  strongs=%s  parts=%s',
                              surface, strongs, parts)
                    n_skipped += 1
                    break

            if already_exists:
                continue

            # Create WfiAnalysis
            ana = ana_factory.Create()
            wf.AnalysesOC.Add(ana)
            n_ana += 1
            log.debug('    created WfiAnalysis hvo=%s  strongs=%s  parts=%s',
                      ana.Hvo, strongs, parts)

            # Create WfiGloss for each part
            for part in parts:
                tss = TsStringUtils.MakeString(part, ws_en)
                gls = gls_factory.Create()
                ana.MeaningsOC.Add(gls)
                gls.Form.set_String(ws_en, tss)
                n_gls += 1
                log.debug('      WfiGloss hvo=%s  %r', gls.Hvo, part)

    log.info('Population complete: wf_created=%d  ana_created=%d  gls_created=%d  skipped=%d',
             n_wf, n_ana, n_gls, n_skipped)
    return n_wf, n_ana, n_gls


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def Main(project, report, modifyAllowed):
    log.info('Main() called  modifyAllowed=%s', modifyAllowed)
    report.Info(f'Log: {LOG_PATH}')

    # Writing systems
    try:
        ws_en  = project.lp.DefaultAnalysisWritingSystem.Handle
        ws_grc = project.lp.DefaultVernacularWritingSystem.Handle
        log.info('ws_en=%s  ws_grc=%s', ws_en, ws_grc)
    except Exception:
        log.critical('Could not read writing systems', exc_info=True)
        report.Error(f'Could not read writing systems. See log: {LOG_PATH}')
        return

    # Find data directory
    data_dir = _find_data_dir()
    if not data_dir:
        report.Info('Data directory not found automatically — please select it.')
        data_dir = _pick_data_dir_dialog()
        if not data_dir:
            report.Info('Cancelled — no data directory selected.')
            return
        if not os.path.isfile(os.path.join(data_dir, 'Acts.json')):
            report.Error(f'Selected folder does not contain Acts.json: {data_dir}')
            return

    report.Info(f'Data directory: {data_dir}')
    log.info('Data directory: %s', data_dir)

    # Load all NT data
    try:
        combo_glosses = load_nt_data(data_dir)
    except Exception:
        log.error('Failed to load NT data', exc_info=True)
        report.Error(f'Failed to load NT data. See log: {LOG_PATH}')
        return

    from collections import defaultdict
    by_surface = defaultdict(list)
    for (surface, strongs) in combo_glosses:
        by_surface[surface].append(strongs)
    wf_count    = len(by_surface)
    combo_count = len(combo_glosses)

    report.Info(f'Data loaded: {wf_count:,} unique surface forms, '
                f'{combo_count:,} analyses to create.')
    log.info('wf_count=%d  combo_count=%d', wf_count, combo_count)

    # Count existing wordforms for the dialog
    cache = project.project
    try:
        repo = cache.ServiceLocator.GetService(IWfiWordformRepository)
        existing_wf_count = sum(1 for _ in repo.AllInstances())
    except Exception:
        existing_wf_count = 0
    log.info('existing_wf_count=%d', existing_wf_count)

    # Preview mode
    if not modifyAllowed:
        report.Info(f'\nPreview — would create:')
        report.Info(f'  {wf_count:,} WfiWordform objects')
        report.Info(f'  {combo_count:,} WfiAnalysis objects')
        report.Info(f'  {combo_count - wf_count} homograph wordforms (two analyses each)')
        report.Info(f'\nExisting wordforms in project: {existing_wf_count:,}')
        report.Info(f'Run again with Modify enabled to apply.')
        log.info('Preview complete')
        return

    # Confirm with the user
    confirmed, clean_first = _confirm_dialog(combo_count, wf_count, existing_wf_count)
    if not confirmed:
        report.Info('Cancelled by user.')
        log.info('User cancelled')
        return

    log.info('confirmed=True  clean_first=%s', clean_first)

    # Optionally clean existing wordforms first
    if clean_first:
        report.Info('\nCleaning existing wordforms…')
        log.info('Clean-first requested — calling _clear_all_wordforms')
        try:
            n_deleted = _clear_all_wordforms(cache, report)
            report.Info(f'  Deleted {n_deleted:,} existing WfiWordform(s).')
        except Exception:
            log.error('_clear_all_wordforms failed', exc_info=True)
            report.Error(f'Clean step failed — see log: {LOG_PATH}')
            return

    # Run population inside FLExTools' undo task
    report.Info('\nPopulating wordforms — this may take a few minutes…')
    log.info('Starting population...')

    try:
        n_wf, n_ana, n_gls = _populate(
            combo_glosses, cache, project.lp, ws_en, ws_grc, report
        )
    except Exception:
        log.error('Population failed', exc_info=True)
        report.Error(f'Population failed — see log: {LOG_PATH}')
        return

    report.Info(f'\nDone.')
    report.Info(f'  Created {n_wf:,} WfiWordform object(s)')
    report.Info(f'  Created {n_ana:,} WfiAnalysis object(s)')
    report.Info(f'  Created {n_gls:,} WfiGloss object(s)')
    report.Info(f'\nNext steps:')
    report.Info(f'  1. Close FLExTools.')
    report.Info(f'  2. Open FLEx and verify the wordforms look correct.')
    report.Info(f'  3. File → Project Management → Back Up This Project')
    report.Info(f'     to save this as the new template .fwbackup.')
    log.info('Main() finished  wf=%d  ana=%d  gls=%d', n_wf, n_ana, n_gls)
    log.info('=' * 70)


# ---------------------------------------------------------------------------
# FLExTools registration
# ---------------------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(runFunction=Main, docs=docs)

if __name__ == '__main__':
    print(FlexToolsModule.Help())
