"""
Import NT Text — FLExTools Module
====================================
Creates interlinear text objects in the open FLEx project for selected
NT Greek books, using the pre-populated WfiWordform / WfiAnalysis / WfiGloss
objects that already exist in the template project.

Workflow
--------
  1. Run Populate_NT_Wordforms_XML.py once against the blank template to
     pre-populate all 21,397 surface-form analyses.
  2. Restore the template .fwbackup as the user's working project.
  3. Run this module from FLExTools to import any subset of NT books.

For each selected book the module creates:
  IText  (title = book name)
    IStText
      IStTxtPara  × verses           ← one paragraph per verse
        Contents  = Greek surface forms joined by spaces
        ISegment  (BeginOffset = 0)
          FreeTranslation = English translation
          AnalysesRS  × word tokens  ← one IAnalysis ref per word
            Single gloss  → WfiGloss   (approved / shows green in FLEx)
            Multi-gloss   → WfiAnalysis (user picks in context / blue)
            Not found     → WfiWordform (unanalysed / red)

DATA SOURCE
  The 27 NT book JSON files and strongs_greek.json are searched in the
  same candidate directories as Populate_NT_Wordforms_XML.py.  A folder
  picker is shown if they cannot be found automatically.

WRITING SYSTEMS
  DefaultVernacularWritingSystem  → Greek (grc)
  DefaultAnalysisWritingSystem    → English (en)

BACKWARD COMPATIBILITY
  Each book is only imported once; re-running skips books that already
  exist in the project (checked by text title).  No existing user data
  is ever modified or deleted.

LOGGING
  %APPDATA%\\SIL\\FLExGlossSplitter\\Logs\\ImportNTText_YYYYMMDD_HHMMSS.log
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
    log_path = os.path.join(log_dir, f'ImportNTText_{ts}.log')
    handler  = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s.%(msecs)03d  %(levelname)-8s  %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return log_path, logger

LOG_PATH, log = _init_log()

log.info('=' * 70)
log.info('Import NT Text — module loaded  Python %s', sys.version)

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
        ITextFactory,
        IStTextFactory,
        IStTxtParaFactory,
        ISegmentFactory,
        IWfiWordformRepository,
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
    FTM_Name:        'Import NT Text',
    FTM_Version:     1,
    FTM_ModifiesDB:  True,
    FTM_Synopsis:    'Import NT Greek books as interlinear texts (uses pre-populated analyses).',
    FTM_Help:        None,
    FTM_Description: __doc__,
}

BOOK_NAMES = [
    'Matthew', 'Mark', 'Luke', 'John', 'Acts', 'Romans',
    '1Corinthians', '2Corinthians', 'Galatians', 'Ephesians', 'Philippians',
    'Colossians', '1Thessalonians', '2Thessalonians', '1Timothy', '2Timothy',
    'Titus', 'Philemon', 'Hebrews', 'James', '1Peter', '2Peter',
    '1John', '2John', '3John', 'Jude', 'Revelation',
]

# ---------------------------------------------------------------------------
# Data directory helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _candidate_data_dirs():
    return [
        os.path.join(SCRIPT_DIR, 'data'),
        os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'docs', 'assets', 'data')),
    ]

def _find_data_dir():
    for d in _candidate_data_dirs():
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, 'Acts.json')):
            log.info('Data dir auto-found: %s', d)
            return d
    return None

def _pick_data_dir():
    root = tk.Tk(); root.withdraw()
    folder = filedialog.askdirectory(
        title='Select folder containing NT Greek JSON files (Acts.json, Matthew.json, …)',
        initialdir=os.path.expanduser('~'),
    )
    root.destroy()
    return folder or None

# ---------------------------------------------------------------------------
# Verse-key sorter: "1:9" < "1:10"  (numeric, not lexicographic)
# ---------------------------------------------------------------------------

def _verse_key(ref):
    try:
        c, v = ref.split(':')
        return (int(c), int(v))
    except Exception:
        return (0, 0)

# ---------------------------------------------------------------------------
# Analysis cache
# Build once per run:  Greek surface form  →  IAnalysis to put in AnalysesRS
#
#   Single WfiGloss   → point to WfiGloss   (approved / green in FLEx)
#   Multiple WfiGloss → point to WfiAnalysis (candidate / blue in FLEx)
#   No glosses        → point to WfiWordform (unanalysed / red)
# ---------------------------------------------------------------------------

def _build_analysis_cache(cache, ws_grc, report):
    """
    Return dict: Greek surface form (str) → IAnalysis (WfiGloss, WfiAnalysis,
    or WfiWordform depending on gloss count).
    """
    log.info('Building analysis cache from wordform repository…')
    report.Info('  Building analysis cache from pre-populated wordforms…')

    repo           = cache.ServiceLocator.GetService(IWfiWordformRepository)
    analysis_cache = {}
    n_single       = 0
    n_multi        = 0
    n_none         = 0

    for wf in repo.AllInstances():
        try:
            form_ts = wf.Form.get_String(ws_grc)
            if not form_ts or not form_ts.Text:
                continue
            surface = form_ts.Text

            analyses = list(wf.AnalysesOC)
            if not analyses:
                analysis_cache[surface] = wf   # WfiWordform fallback
                n_none += 1
                continue

            ana     = analyses[0]              # take the first (only) analysis
            glosses = list(ana.MeaningsOC)

            if len(glosses) == 1:
                analysis_cache[surface] = glosses[0]   # WfiGloss → approved
                n_single += 1
            else:
                analysis_cache[surface] = ana           # WfiAnalysis → candidate
                n_multi += 1

        except Exception:
            log.debug('  error reading wf hvo=%s', wf.Hvo, exc_info=True)

    log.info('Analysis cache: %d single-gloss  %d multi-gloss  %d no-gloss',
             n_single, n_multi, n_none)
    report.Info(f'  {n_single + n_multi + n_none:,} wordforms cached '
                f'({n_single:,} single-gloss, {n_multi:,} multi-gloss, '
                f'{n_none:,} no-gloss)')
    return analysis_cache

# ---------------------------------------------------------------------------
# Existing text names — for duplicate detection
# ---------------------------------------------------------------------------

def _existing_text_names(lp, ws_en):
    names = set()
    try:
        for t in lp.TextsOC:
            try:
                ts = t.Name.get_String(ws_en)
                if ts and ts.Text:
                    names.add(ts.Text)
            except Exception:
                pass
    except Exception:
        log.debug('Could not iterate lp.TextsOC', exc_info=True)
    log.info('Existing text names: %s', sorted(names))
    return names

# ---------------------------------------------------------------------------
# Import one book
# ---------------------------------------------------------------------------

def _import_book(book_name, book_data, analysis_cache,
                 lp, cache, ws_grc, ws_en, report):
    """
    Create the full IText hierarchy for one NT book.
    Returns (n_verses, n_tokens, n_found, n_missing).
    """
    sl = cache.ServiceLocator

    # ── IText ─────────────────────────────────────────────────────────────
    text = sl.GetService(ITextFactory).Create()
    try:
        lp.TextsOC.Add(text)
    except Exception as e:
        log.warning('lp.TextsOC.Add failed (%s) — trying WordformInventory path', e)
        # Some FLEx versions use a different collection
        try:
            lp.Texts.Add(text)
        except Exception as e2:
            log.error('Could not add IText to project: %s', e2)
            raise

    text.Name.set_String(ws_en, TsStringUtils.MakeString(book_name, ws_en))
    log.info('IText created hvo=%s  name=%r', text.Hvo, book_name)

    # ── IStText ───────────────────────────────────────────────────────────
    sttext = sl.GetService(IStTextFactory).Create()
    text.ContentsOA = sttext
    log.info('IStText created hvo=%s', sttext.Hvo)

    para_factory = sl.GetService(IStTxtParaFactory)
    seg_factory  = sl.GetService(ISegmentFactory)

    n_verses  = 0
    n_tokens  = 0
    n_found   = 0
    n_missing = 0

    sorted_refs = sorted(book_data.keys(), key=_verse_key)
    total_verses = len(sorted_refs)

    for i, ref in enumerate(sorted_refs, 1):
        if i % 50 == 0 or i == total_verses:
            pct = 100 * i / total_verses
            report.Info(f'  {book_name}: {i}/{total_verses} verses ({pct:.0f}%)…')
            log.info('  %s: %d/%d', book_name, i, total_verses)

        verse  = book_data[ref]
        words  = verse.get('words') or []
        trans  = (verse.get('translation') or '').strip()

        # Greek surface forms joined by spaces
        greek_text = ' '.join(w.get('g', '') for w in words if w.get('g', '').strip())
        log.debug('  %s  greek=%r', ref, greek_text[:80])

        # ── IStTxtPara ────────────────────────────────────────────────────
        para = para_factory.Create()
        sttext.ParagraphsOS.Add(para)
        para.Contents = TsStringUtils.MakeString(greek_text, ws_grc)

        # ── ISegment ──────────────────────────────────────────────────────
        seg = seg_factory.Create()
        para.SegmentsOS.Add(seg)
        seg.BeginOffset = 0

        # Free translation
        if trans:
            seg.FreeTranslation.set_String(
                ws_en, TsStringUtils.MakeString(trans, ws_en))
            log.debug('  %s  trans=%r', ref, trans[:60])

        # ── Word-token analyses ───────────────────────────────────────────
        for w in words:
            surface = (w.get('g') or '').strip()
            if not surface:
                continue

            ianalysis = analysis_cache.get(surface)

            if ianalysis is not None:
                seg.AnalysesRS.Append(ianalysis)
                n_found += 1
                log.debug('    %r → %s hvo=%s',
                          surface, type(ianalysis).__name__, ianalysis.Hvo)
            else:
                # Surface form was not in the pre-populated wordforms.
                # This can happen for textual-variant-marker forms (⸀ἐν etc.)
                # that differ from the canonical surface form.
                n_missing += 1
                log.debug('    %r → NOT IN CACHE (skipped)', surface)

            n_tokens += 1

        n_verses += 1

    log.info('%s: %d verses  %d tokens  %d found  %d missing',
             book_name, n_verses, n_tokens, n_found, n_missing)
    return n_verses, n_tokens, n_found, n_missing

# ---------------------------------------------------------------------------
# Book-selection dialog
# ---------------------------------------------------------------------------

def _book_selection_dialog(existing_names):
    """
    Show a dialog listing the 27 NT books.
    Books already imported are shown with a ✓ and pre-deselected.
    Returns list of selected book names, or None if cancelled.
    """
    root = tk.Toplevel()
    root.title('Import NT Text')
    root.geometry('460x520')
    root.grab_set()
    result = [None]

    # ── Header ────────────────────────────────────────────────────────────
    ttk.Label(root, text='Import NT Text',
              font=('TkDefaultFont', 11, 'bold')).pack(anchor='w', padx=16, pady=(14, 2))
    ttk.Label(root,
              text='Select books to import as interlinear texts.\n'
                   'Books marked ✓ already exist in this project and are deselected.',
              justify='left', wraplength=420).pack(anchor='w', padx=16, pady=(0, 8))

    # ── Listbox ───────────────────────────────────────────────────────────
    frame = ttk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True, padx=16)

    sb  = ttk.Scrollbar(frame, orient=tk.VERTICAL)
    lb  = tk.Listbox(frame, selectmode=tk.EXTENDED,
                     yscrollcommand=sb.set, height=20, font=('TkDefaultFont', 10))
    sb.config(command=lb.yview)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Populate and pre-select
    for book in BOOK_NAMES:
        already = book in existing_names
        lb.insert(tk.END, f'✓ {book}' if already else f'   {book}')
        if not already:
            lb.selection_set(tk.END)

    # ── Select All / None buttons ─────────────────────────────────────────
    btn_frame2 = ttk.Frame(root)
    btn_frame2.pack(fill=tk.X, padx=16, pady=(4, 0))

    def select_all():
        lb.selection_set(0, tk.END)

    def select_none():
        lb.selection_clear(0, tk.END)

    def select_not_imported():
        lb.selection_clear(0, tk.END)
        for idx, book in enumerate(BOOK_NAMES):
            if book not in existing_names:
                lb.selection_set(idx)

    ttk.Button(btn_frame2, text='Select All',          command=select_all).pack(side=tk.LEFT)
    ttk.Button(btn_frame2, text='Deselect All',        command=select_none).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame2, text='Select Not Imported', command=select_not_imported).pack(side=tk.LEFT)

    # ── OK / Cancel ───────────────────────────────────────────────────────
    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill=tk.X, padx=16, pady=(8, 14))

    def on_ok():
        selected = [BOOK_NAMES[i] for i in lb.curselection()]
        # Strip the ✓ prefix from display — BOOK_NAMES indexing handles it
        result[0] = selected
        root.destroy()

    def on_cancel():
        root.destroy()

    ttk.Button(btn_frame, text='Cancel',    command=on_cancel).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text='Import →',  command=on_ok).pack(side=tk.RIGHT, padx=(0, 6))

    root.wait_window()
    return result[0]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def Main(project, report, modifyAllowed):
    log.info('Main() called  modifyAllowed=%s', modifyAllowed)
    report.Info(f'Log: {LOG_PATH}')

    # ── Writing systems ───────────────────────────────────────────────────
    try:
        ws_en  = int(project.lp.DefaultAnalysisWritingSystem.Handle)
        ws_grc = int(project.lp.DefaultVernacularWritingSystem.Handle)
        ws_en_id  = project.lp.DefaultAnalysisWritingSystem.Id
        ws_grc_id = project.lp.DefaultVernacularWritingSystem.Id
        log.info('ws_en=%s (%s)  ws_grc=%s (%s)', ws_en, ws_en_id, ws_grc, ws_grc_id)
        report.Info(f'Writing systems: analysis="{ws_en_id}"  vernacular="{ws_grc_id}"')
    except Exception:
        log.critical('Could not read writing systems', exc_info=True)
        report.Error(f'Could not read writing systems — see log: {LOG_PATH}')
        return

    # ── Data directory ────────────────────────────────────────────────────
    data_dir = _find_data_dir()
    if not data_dir:
        report.Info('NT Greek JSON data not found automatically — please select the folder.')
        data_dir = _pick_data_dir()
    if not data_dir or not os.path.isfile(os.path.join(data_dir, 'Acts.json')):
        report.Error('NT Greek JSON data folder not found or invalid.')
        return
    report.Info(f'Data directory: {data_dir}')
    log.info('Data dir: %s', data_dir)

    # ── Existing texts (for duplicate detection) ──────────────────────────
    cache          = project.project
    existing_names = _existing_text_names(project.lp, ws_en)
    if existing_names:
        report.Info(f'Already imported: {", ".join(sorted(existing_names))}')

    # ── Book selection ────────────────────────────────────────────────────
    selected_books = _book_selection_dialog(existing_names)
    if not selected_books:
        report.Info('Cancelled — no books selected.')
        log.info('User cancelled or selected nothing')
        return

    # Filter out already-imported books (user may have selected them anyway)
    to_import = [b for b in selected_books if b not in existing_names]
    skipped   = [b for b in selected_books if b in existing_names]
    if skipped:
        report.Info(f'Skipping already-imported: {", ".join(skipped)}')
        log.info('Skipping: %s', skipped)
    if not to_import:
        report.Info('All selected books already exist in this project.')
        return

    log.info('Books to import: %s', to_import)
    report.Info(f'Importing {len(to_import)} book(s): {", ".join(to_import)}')

    # ── Preview mode ──────────────────────────────────────────────────────
    if not modifyAllowed:
        report.Info('\nPreview mode — would import:')
        for book in to_import:
            path = os.path.join(data_dir, f'{book}.json')
            if os.path.isfile(path):
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                report.Info(f'  {book}: {len(data):,} verses')
            else:
                report.Info(f'  {book}: JSON not found')
        report.Info('\nRun again with Modify enabled to apply.')
        return

    # ── Build analysis cache ──────────────────────────────────────────────
    report.Info('\nBuilding analysis lookup cache…')
    try:
        analysis_cache = _build_analysis_cache(cache, ws_grc, report)
    except Exception:
        log.error('Failed to build analysis cache', exc_info=True)
        report.Error(f'Failed to build analysis cache — see log: {LOG_PATH}')
        return

    if not analysis_cache:
        report.Warning(
            'Analysis cache is empty — the project may not have been pre-populated '
            'with wordform analyses.  Texts will be created but tokens will be '
            'unanalysed.  Run Populate NT Wordforms (XML) first for best results.')

    # ── Import each book ──────────────────────────────────────────────────
    total_verses = total_tokens = total_missing = 0

    for book in to_import:
        path = os.path.join(data_dir, f'{book}.json')
        if not os.path.isfile(path):
            report.Warning(f'{book}: JSON file not found at {path} — skipped.')
            log.warning('Missing: %s', path)
            continue

        report.Info(f'\nImporting {book}…')
        log.info('Loading %s', path)
        try:
            with open(path, encoding='utf-8') as f:
                book_data = json.load(f)
        except Exception:
            log.error('Failed to load %s', path, exc_info=True)
            report.Error(f'Could not load {book}.json — skipped.')
            continue

        try:
            n_v, n_t, n_f, n_m = _import_book(
                book, book_data, analysis_cache,
                project.lp, cache, ws_grc, ws_en, report
            )
            total_verses  += n_v
            total_tokens  += n_t
            total_missing += n_m
            pct_found = 100 * n_f / n_t if n_t else 0
            report.Info(
                f'  {book}: {n_v:,} verses  {n_t:,} tokens  '
                f'{n_f:,} analysed ({pct_found:.1f}%)  '
                f'{n_m:,} surface forms not in cache'
            )
        except Exception:
            log.error('Failed to import %s', book, exc_info=True)
            report.Error(f'Failed to import {book} — see log: {LOG_PATH}')
            continue

    # ── Summary ───────────────────────────────────────────────────────────
    report.Info(f'\nDone.')
    report.Info(f'  {len(to_import):,} book(s) imported')
    report.Info(f'  {total_verses:,} verse paragraphs created')
    report.Info(f'  {total_tokens:,} word tokens linked')
    if total_missing:
        report.Warning(
            f'  {total_missing:,} tokens had no matching pre-populated wordform '
            f'(variant-marker forms like ⸀ἐν are expected — see log for details).')
    report.Info(f'\nLog: {LOG_PATH}')
    log.info('Main() finished  verses=%d  tokens=%d  missing=%d',
             total_verses, total_tokens, total_missing)
    log.info('=' * 70)


# ---------------------------------------------------------------------------
# FLExTools registration
# ---------------------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(runFunction=Main, docs=docs)

if __name__ == '__main__':
    print(FlexToolsModule.Help())
