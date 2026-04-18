"""
Split Slash Glosses — FLExTools Module
=======================================
Splits slash-separated word glosses (e.g. "in/on/at") in imported FLEx
interlinear texts into individual candidate glosses on the same WfiAnalysis,
then redirects each word occurrence to the WfiAnalysis rather than any one
WfiGloss.  This causes FLEx to display the word in blue (unapproved) so the
analyst can navigate to each word and confirm the correct gloss.

FLEx project data is modified through the LCM API (no direct file access),
so full undo/redo support is available inside FLEx after running this module.

INSTALLATION
  Copy this file to the FLExTools Modules folder, e.g.:
    C:\\...\\FLExTools\\Modules\\Biblical Languages\\Split_Slash_Glosses.py

LOGGING
  A verbose debug log is written to:
    %APPDATA%\\SIL\\FLExGlossSplitter\\Logs\\SplitSlashGlosses_YYYYMMDD_HHMMSS.log
  The exact path is printed in the FLExTools report at the start of every run.
"""

import logging
import os
import sys
import traceback
from datetime import datetime

# ---------------------------------------------------------------------------
# Logging setup — runs before any FLEx imports so we capture import errors too
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

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = os.path.join(log_dir, f'SplitSlashGlosses_{ts}.log')

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s  %(levelname)-8s  %(message)s',
        handlers=[logging.FileHandler(log_path, encoding='utf-8')]
    )
    return log_path

LOG_PATH = _init_log()
log = logging.getLogger(__name__)

log.info('=' * 70)
log.info('Split Slash Glosses — module loaded')
log.info('Python %s', sys.version)
log.info('Module file: %s', os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# FLExTools / LCM imports
# (Only resolve on Windows with FLEx + FLExTools installed)
# ---------------------------------------------------------------------------

try:
    from flextoolslib import (
        FlexToolsModuleClass,
        FTM_Name, FTM_Version, FTM_ModifiesDB,
        FTM_Synopsis, FTM_Help, FTM_Description,
    )
    log.info('flextoolslib imported OK')
except ImportError as e:
    log.critical('flextoolslib not found — is FLExTools installed? %s', e)
    raise

try:
    from SIL.LCModel import (
        WfiGlossTags,
        WfiAnalysisTags,
        WfiWordformTags,
        IWfiGlossFactory,
    )
    from SIL.LCModel.Core.Text import TsStringUtils
    log.info('SIL.LCModel imports OK')
except ImportError as e:
    log.critical('SIL.LCModel not found — is FLEx installed? %s', e)
    raise

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    log.info('tkinter imported OK')
except ImportError as e:
    log.critical('tkinter not available: %s', e)
    raise

# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------

docs = {
    FTM_Name:        'Split Slash Glosses',
    FTM_Version:     1,
    FTM_ModifiesDB:  True,
    FTM_Synopsis:    'Splits slash-separated word glosses (e.g. in/on/at) into '
                     'individual unapproved analyses.',
    FTM_Help:        None,
    FTM_Description: __doc__,
}

# ---------------------------------------------------------------------------
# Text-selection dialog
# ---------------------------------------------------------------------------

def _choose_texts(texts_info):
    """
    Show a simple Tk dialog listing all interlinear texts.
    texts_info: list of (hvo, title_str, slash_count_str)
    Returns list of selected hvos, or None if cancelled.
    """
    log.debug('Opening text-selection dialog with %d text(s)', len(texts_info))

    selected_hvos = []

    root = tk.Tk()
    root.title('Split Slash Glosses — Select Texts')
    root.resizable(True, True)
    root.geometry('600x420')

    ttk.Label(root, text='Select interlinear texts to process:',
              font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=12, pady=(12, 4))

    hint = ('Words with slash-separated glosses (e.g. "in/on/at") will be split '
            'into individual glosses and marked blue for your approval.')
    ttk.Label(root, text=hint, wraplength=560, justify='left').pack(
        anchor='w', padx=12, pady=(0, 8))

    frame = ttk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    cols = ('title', 'slash_words')
    tree = ttk.Treeview(frame, columns=cols, show='headings', selectmode='extended')
    tree.heading('title', text='Text')
    tree.heading('slash_words', text='Words with slash glosses')
    tree.column('title', width=340, anchor='w')
    tree.column('slash_words', width=180, anchor='center')

    sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)

    hvo_map = {}
    for hvo, title, slash_count in texts_info:
        iid = tree.insert('', tk.END, values=(title, slash_count))
        hvo_map[iid] = hvo
        log.debug('  Listed text: hvo=%s  title=%r  slash_words=%s', hvo, title, slash_count)

    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill=tk.X, padx=12, pady=(4, 12))

    def select_all():
        tree.selection_set(tree.get_children())

    def on_ok():
        sel = tree.selection()
        log.debug('User selected %d text(s)', len(sel))
        for iid in sel:
            selected_hvos.append(hvo_map[iid])
        root.destroy()

    def on_cancel():
        log.debug('User cancelled text selection dialog')
        root.destroy()

    ttk.Button(btn_frame, text='Select All', command=select_all).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_frame, text='Cancel', command=on_cancel).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text='Split Glosses →', command=on_ok).pack(side=tk.RIGHT, padx=(0, 6))

    root.mainloop()
    log.debug('Text-selection dialog closed; selected hvos: %s', selected_hvos)
    return selected_hvos if selected_hvos else None

# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------

def _gloss_text(gloss, ws_en):
    """Return the English form text of a WfiGloss, or empty string."""
    try:
        tss = gloss.Form.get_String(ws_en)
        return tss.Text or ''
    except Exception:
        log.debug('Could not read gloss form', exc_info=True)
        return ''


def _scan_text(text, ws_en):
    """
    Walk all segments in *text*, collecting every WfiGloss whose English
    form contains a '/'.

    Returns:
        dict mapping gloss_hvo ->
            { 'gloss': IWfiGloss,
              'form':  str,
              'analysis': IWfiAnalysis,
              'occurrences': [(seg, index), ...] }
    """
    log.debug('Scanning text hvo=%s for slash glosses', text.Hvo)
    found = {}

    try:
        sttext = text.ContentsOA
        if sttext is None:
            log.debug('  Text has no ContentsOA (no interlinear content) — skipping')
            return found

        for para_idx, para in enumerate(sttext.ParagraphsOS):
            log.debug('  Paragraph %d', para_idx)
            for seg_idx, seg in enumerate(para.SegmentsOS):
                log.debug('    Segment %d  (%d analyses)', seg_idx,
                          seg.AnalysesRS.Count)
                for ana_idx in range(seg.AnalysesRS.Count):
                    analysis = seg.AnalysesRS[ana_idx]
                    log.debug('      [%d] ClassID=%s', ana_idx, analysis.ClassID)

                    if analysis.ClassID != WfiGlossTags.kClassId:
                        continue

                    gloss = analysis  # IWfiGloss
                    form = _gloss_text(gloss, ws_en)
                    log.debug('      WfiGloss hvo=%s  form=%r', gloss.Hvo, form)

                    if '/' not in form:
                        continue

                    hvo = gloss.Hvo
                    if hvo not in found:
                        # Get the owning WfiAnalysis
                        owner = gloss.Owner
                        if owner is None or owner.ClassID != WfiAnalysisTags.kClassId:
                            log.warning('      WfiGloss hvo=%s has unexpected owner '
                                        'ClassID=%s — skipping',
                                        hvo, owner.ClassID if owner else 'None')
                            continue
                        log.debug('      New slash gloss: hvo=%s  form=%r  '
                                  'analysis_hvo=%s', hvo, form, owner.Hvo)
                        found[hvo] = {
                            'gloss':    gloss,
                            'form':     form,
                            'analysis': owner,
                            'occurrences': [],
                        }
                    found[hvo]['occurrences'].append((seg, ana_idx))
                    log.debug('      Occurrence recorded: seg_hvo=%s  idx=%d',
                              seg.Hvo, ana_idx)
    except Exception:
        log.error('Error scanning text hvo=%s', text.Hvo, exc_info=True)

    log.debug('  Scan complete: %d unique slash gloss(es) found', len(found))
    return found

# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _split_gloss_entry(entry, ws_en, cache, report):
    """
    Split one slash-gloss entry:
      - Create a new WfiGloss for each part
      - Redirect every segment occurrence to the WfiAnalysis (blue/unapproved)
      - Remove (delete) the original slash WfiGloss from MeaningsOC

    Returns True on success.
    """
    original_gloss = entry['gloss']
    original_form  = entry['form']
    wfi_analysis   = entry['analysis']
    occurrences    = entry['occurrences']
    parts = [p.strip() for p in original_form.split('/') if p.strip()]

    log.info('  Splitting %r → %s  (analysis_hvo=%s  occurrences=%d)',
             original_form, parts, wfi_analysis.Hvo, len(occurrences))

    try:
        factory = cache.ServiceLocator.GetInstance(IWfiGlossFactory)
        log.debug('    IWfiGlossFactory obtained')

        for part in parts:
            tss = TsStringUtils.MakeString(part, ws_en)
            new_gloss = factory.Create()
            wfi_analysis.MeaningsOC.Add(new_gloss)
            new_gloss.Form.set_String(ws_en, tss)
            log.debug('    Created WfiGloss hvo=%s  form=%r', new_gloss.Hvo, part)

        # Redirect every segment occurrence from the old WfiGloss → WfiAnalysis
        for seg, idx in occurrences:
            log.debug('    Redirecting seg_hvo=%s  idx=%d  → analysis_hvo=%s',
                      seg.Hvo, idx, wfi_analysis.Hvo)
            seg.AnalysesRS[idx] = wfi_analysis

        # Remove (and thereby delete) the original slash WfiGloss
        log.debug('    Removing original WfiGloss hvo=%s from MeaningsOC',
                  original_gloss.Hvo)
        wfi_analysis.MeaningsOC.Remove(original_gloss)

        report.Info(f'  Split \u201c{original_form}\u201d \u2192 {parts}')
        return True

    except Exception:
        log.error('    FAILED to split %r', original_form, exc_info=True)
        report.Error(f'  Failed to split \u201c{original_form}\u201d — see log: {LOG_PATH}')
        return False

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def Main(project, report, modifyAllowed):
    log.info('Main() called  modifyAllowed=%s', modifyAllowed)

    # Always tell the user (and us) where the log file lives
    report.Info(f'Log file: {LOG_PATH}')

    try:
        ws_en = project.lp.DefaultAnalysisWritingSystem.Handle
        log.info('DefaultAnalysisWritingSystem handle: %s', ws_en)
    except Exception:
        log.critical('Could not get DefaultAnalysisWritingSystem', exc_info=True)
        report.Error(f'Could not read project writing systems. See log: {LOG_PATH}')
        return

    # ---- 1. Collect all interlinear texts with slash-gloss counts ----------

    log.info('Collecting interlinear texts from project...')
    texts_info = []   # (hvo, title, slash_count_str)
    text_scan  = {}   # hvo -> scan dict

    try:
        for text in project.lp.TextsOC:
            title = ''
            try:
                title = text.Name.BestAnalysisAlternative.Text or f'[hvo {text.Hvo}]'
            except Exception:
                title = f'[hvo {text.Hvo}]'
                log.debug('Could not read title for text hvo=%s', text.Hvo, exc_info=True)

            log.info('Found text: %r  hvo=%s', title, text.Hvo)
            scan = _scan_text(text, ws_en)
            text_scan[text.Hvo] = (text, scan)

            count = sum(len(v['occurrences']) for v in scan.values())
            slash_str = str(count) if count else 'none'
            texts_info.append((text.Hvo, title, slash_str))
    except Exception:
        log.critical('Error iterating texts', exc_info=True)
        report.Error(f'Error reading project texts. See log: {LOG_PATH}')
        return

    if not texts_info:
        report.Warning('No interlinear texts found in this project.')
        log.warning('No texts found')
        return

    log.info('Total texts found: %d', len(texts_info))

    # ---- 2. Let the user choose which texts to process ---------------------

    chosen_hvos = _choose_texts(texts_info)
    if not chosen_hvos:
        report.Info('Cancelled — no texts selected.')
        log.info('User cancelled or selected nothing')
        return

    log.info('User selected %d text(s): %s', len(chosen_hvos), chosen_hvos)

    # ---- 3. Preview (modifyAllowed=False) or Apply -------------------------

    cache = project.project   # LCM cache (needed for factories & UOW)

    total_glosses = 0
    total_split   = 0

    for hvo in chosen_hvos:
        if hvo not in text_scan:
            log.warning('Selected hvo %s not in scan dict — skipping', hvo)
            continue

        text, scan = text_scan[hvo]
        title = next((t for h, t, _ in texts_info if h == hvo), str(hvo))

        if not scan:
            report.Info(f'{title}: no slash glosses found.')
            log.info('Text %r has no slash glosses', title)
            continue

        gloss_count = len(scan)
        occ_count   = sum(len(v['occurrences']) for v in scan.values())
        total_glosses += gloss_count

        report.Info(f'{title}: {gloss_count} unique slash gloss(es), '
                    f'{occ_count} total occurrence(s)')
        log.info('Processing text %r: %d unique glosses, %d occurrences',
                 title, gloss_count, occ_count)

        if not modifyAllowed:
            # Preview mode: just list what would be changed
            for entry in scan.values():
                parts = [p.strip() for p in entry['form'].split('/') if p.strip()]
                report.Info(f'  Would split \u201c{entry["form"]}\u201d \u2192 {parts}')
            continue

        # Modify mode: wrap everything in a single undoable task
        try:
            cache.BeginUndoTask(
                f'Split slash glosses in \u201c{title}\u201d',
                f'Split slash glosses in \u201c{title}\u201d'
            )
            log.info('UndoTask begun for text %r', title)

            for entry in scan.values():
                ok = _split_gloss_entry(entry, ws_en, cache, report)
                if ok:
                    total_split += 1

            cache.EndUndoTask()
            log.info('UndoTask committed for text %r', title)

        except Exception:
            log.error('Exception during modification of text %r — cancelling UndoTask',
                      title, exc_info=True)
            try:
                cache.CancelUndoTask()
            except Exception:
                log.error('CancelUndoTask also failed', exc_info=True)
            report.Error(f'Error processing \u201c{title}\u201d — changes rolled back. '
                         f'See log: {LOG_PATH}')

    # ---- 4. Summary --------------------------------------------------------

    if modifyAllowed:
        report.Info(f'\nDone. Split {total_split} of {total_glosses} slash gloss(es).')
        report.Info('Blue words now have multiple gloss options — open each in '
                    'FLEx\u2019s interlinear view to approve the correct one.')
        log.info('Finished: %d/%d glosses split', total_split, total_glosses)
    else:
        report.Info(f'\nPreview complete. {total_glosses} slash gloss(es) would be split.')
        report.Info('Run again with \u201cModify\u201d enabled to apply changes.')
        log.info('Preview complete: %d glosses would be split', total_glosses)

    log.info('Main() finished')
    log.info('=' * 70)


# ---------------------------------------------------------------------------
# FLExTools module registration (required)
# ---------------------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(runFunction=Main, docs=docs)

if __name__ == '__main__':
    print(FlexToolsModule.Help())
