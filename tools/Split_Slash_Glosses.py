"""
Split Slash Glosses — FLExTools Module
=======================================
Splits slash-separated word glosses (e.g. "in/on/at") in a FLEx project
into individual candidate glosses on the same WfiAnalysis, then redirects
each word occurrence to the WfiAnalysis rather than any one WfiGloss.
This causes FLEx to display the word in blue (unapproved) so the analyst
can navigate to each word and confirm the correct gloss.

The slash glosses live on WfiAnalysis.MeaningsOC (WfiGloss objects), which
is the "Word Gloss" field visible in Texts & Words → Wordforms.  Text
segments are scanned only to find where each slash gloss is currently used,
so those occurrences can be redirected to the parent WfiAnalysis.

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

    # Do NOT use basicConfig — FLExTools already configures the root logger,
    # making basicConfig a no-op.  Attach a handler directly to our logger.
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(asctime)s  %(levelname)-8s  %(message)s'))

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False   # don't forward to FLExTools' root logger

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
        IWfiGlossFactory,
        IWfiWordformRepository,
        ISegmentRepository,
    )
    from SIL.LCModel.Core.Text import TsStringUtils
    log.info('SIL.LCModel imports OK')
except ImportError as e:
    log.critical('SIL.LCModel not found — is FLEx installed? %s', e)
    raise

try:
    import tkinter as tk
    from tkinter import ttk
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
# Gloss-selection dialog
# ---------------------------------------------------------------------------

def _choose_glosses(gloss_entries):
    """
    Show a dialog listing all slash glosses found across the project.

    gloss_entries: list of dicts with keys:
        hvo, wordform_str, gloss_form, occurrence_count

    Returns list of selected hvos, or None if cancelled.
    """
    log.debug('Opening gloss-selection dialog with %d gloss(es)', len(gloss_entries))

    selected_hvos = []

    # FLExTools already has a running Tk() root — use Toplevel() to avoid
    # creating a second root window.
    root = tk.Toplevel()
    root.title('Split Slash Glosses')
    root.resizable(True, True)
    root.geometry('660x440')
    root.grab_set()

    ttk.Label(root, text='Slash glosses found in this project:',
              font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', padx=12, pady=(12, 4))

    hint = ('Select the glosses you want to split. Each slash gloss (e.g. "in/on/at") '
            'will be replaced by individual glosses and the word marked blue for your approval.')
    ttk.Label(root, text=hint, wraplength=620, justify='left').pack(
        anchor='w', padx=12, pady=(0, 8))

    frame = ttk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

    cols = ('wordform', 'gloss', 'occurrences')
    tree = ttk.Treeview(frame, columns=cols, show='headings', selectmode='extended')
    tree.heading('wordform',    text='Word (Greek)')
    tree.heading('gloss',       text='Current gloss')
    tree.heading('occurrences', text='Occurrences in texts')
    tree.column('wordform',    width=180, anchor='w')
    tree.column('gloss',       width=280, anchor='w')
    tree.column('occurrences', width=140, anchor='center')

    sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)

    hvo_map = {}
    for entry in gloss_entries:
        occ = str(entry['occurrence_count']) if entry['occurrence_count'] else 'none in texts'
        iid = tree.insert('', tk.END, values=(entry['wordform_str'],
                                               entry['gloss_form'],
                                               occ))
        hvo_map[iid] = entry['hvo']
        log.debug('  Listed gloss hvo=%s  wf=%r  form=%r  occ=%s',
                  entry['hvo'], entry['wordform_str'], entry['gloss_form'], occ)

    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill=tk.X, padx=12, pady=(4, 12))

    def select_all():
        tree.selection_set(tree.get_children())

    def on_ok():
        sel = tree.selection()
        log.debug('User selected %d gloss(es)', len(sel))
        for iid in sel:
            selected_hvos.append(hvo_map[iid])
        root.destroy()

    def on_cancel():
        log.debug('User cancelled gloss selection dialog')
        root.destroy()

    ttk.Button(btn_frame, text='Select All', command=select_all).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_frame, text='Cancel', command=on_cancel).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text='Split Glosses →', command=on_ok).pack(side=tk.RIGHT, padx=(0, 6))

    root.wait_window()
    log.debug('Gloss-selection dialog closed; selected hvos: %s', selected_hvos)
    return selected_hvos if selected_hvos else None

# ---------------------------------------------------------------------------
# Phase 1 — find slash glosses in wordform analyses
# ---------------------------------------------------------------------------

def _find_slash_glosses(project, ws_en):
    """
    Scan all WfiWordform → WfiAnalysis → WfiGloss in the project and return
    every WfiGloss whose English form contains '/'.

    Returns:
        dict  gloss_hvo ->
            { 'gloss':        IWfiGloss,
              'analysis':     IWfiAnalysis,
              'wordform':     IWfiWordform,
              'wordform_str': str,
              'form':         str,
              'occurrences':  []   # filled in Phase 2
            }
    """
    log.info('Phase 1: scanning wordform analyses for slash glosses...')
    found = {}

    try:
        sl      = project.project.ServiceLocator
        wf_repo = sl.GetService(IWfiWordformRepository)

        for wf in wf_repo.AllInstances():
            try:
                wf_str = wf.Form.BestVernacularAlternative.Text or f'[hvo {wf.Hvo}]'
            except Exception:
                wf_str = f'[hvo {wf.Hvo}]'

            for analysis in wf.AnalysesOC:
                for gloss in analysis.MeaningsOC:
                    try:
                        tss = gloss.Form.get_String(ws_en)
                        form_text = tss.Text if tss else None
                    except Exception:
                        log.debug('Could not read gloss form hvo=%s', gloss.Hvo,
                                  exc_info=True)
                        continue

                    if form_text and '/' in form_text:
                        log.debug('  Found slash gloss: wf=%r  form=%r  hvo=%s',
                                  wf_str, form_text, gloss.Hvo)
                        found[gloss.Hvo] = {
                            'gloss':        gloss,
                            'analysis':     analysis,
                            'wordform':     wf,
                            'wordform_str': wf_str,
                            'form':         form_text,
                            'occurrences':  [],
                        }
    except Exception:
        log.error('Error during wordform scan', exc_info=True)
        raise

    log.info('Phase 1 complete: %d slash gloss(es) found', len(found))
    return found

# ---------------------------------------------------------------------------
# Phase 2 — find segment occurrences of each slash gloss
# ---------------------------------------------------------------------------

def _find_text_occurrences(project, slash_glosses):
    """
    Iterate every ISegment in the project using ISegmentRepository
    (the same pattern used by FLExTools' own Incomplete_Analyses module).
    This avoids the IStPara / IStTxtPara interface-cast problem entirely.

    For each word position in each segment, match against the slash-gloss
    set in three ways:
      • WfiGloss hvo   — direct match (word has approved slash gloss)
      • WfiAnalysis hvo — the analysis owns a slash WfiGloss (tentative)
      • WfiWordform hvo — the wordform's analysis contains a slash WfiGloss
    """
    log.info('Phase 2: scanning segments via ISegmentRepository...')

    slash_hvo_set     = set(slash_glosses.keys())
    analysis_to_gloss = {v['analysis'].Hvo: hvo
                         for hvo, v in slash_glosses.items()}
    wordform_to_gloss = {}
    for hvo, v in slash_glosses.items():
        wordform_to_gloss.setdefault(v['wordform'].Hvo, hvo)

    n_seg = 0
    try:
        for seg in project.ObjectsIn(ISegmentRepository):
            n_seg += 1
            for idx in range(seg.AnalysesRS.Count):
                a     = seg.AnalysesRS[idx]
                a_hvo = a.Hvo

                if a_hvo in slash_hvo_set:
                    g_hvo = a_hvo                        # WfiGloss direct
                elif a_hvo in analysis_to_gloss:
                    g_hvo = analysis_to_gloss[a_hvo]     # WfiAnalysis
                elif a_hvo in wordform_to_gloss:
                    g_hvo = wordform_to_gloss[a_hvo]     # WfiWordform
                else:
                    continue

                slash_glosses[g_hvo]['occurrences'].append((seg, idx))
                log.debug('    Occurrence: seg_hvo=%s  idx=%d  gloss_hvo=%s',
                          seg.Hvo, idx, g_hvo)

    except Exception:
        log.error('Error during segment scan', exc_info=True)
        raise

    total_occ = sum(len(v['occurrences']) for v in slash_glosses.values())
    log.info('Phase 2 complete: %d segment(s) examined, %d occurrence(s)',
             n_seg, total_occ)

# ---------------------------------------------------------------------------
# Gloss normalisation
# ---------------------------------------------------------------------------

def _split_form(form):
    """
    Split a slash-separated gloss form into clean individual parts.
    Strips the infinitive marker 'to ' from the start of each part so that
    e.g. 'to serve/heal' → ['serve', 'heal']  and
         'to come/go down' → ['come', 'go down'].
    A bare 'to' with nothing after it is left intact (valid gloss for ἵνα).
    """
    parts = []
    for raw in form.split('/'):
        p = raw.strip()
        if p.lower().startswith('to '):
            p = p[3:]          # remove 'to ' prefix (3 chars)
        if p:
            parts.append(p)
    return parts

# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def _split_one(entry, ws_en, cache, report):
    """
    Split one slash-gloss entry:
      1. Create a new WfiGloss for each slash-separated part.
      2. Redirect every text-segment occurrence from the slash WfiGloss
         to its parent WfiAnalysis (making the word blue / unapproved).
      3. Delete the original slash WfiGloss from MeaningsOC.

    Returns True on success.
    """
    original_gloss = entry['gloss']
    original_form  = entry['form']
    wfi_analysis   = entry['analysis']
    occurrences    = entry['occurrences']
    parts = _split_form(original_form)

    log.info('  Splitting %r → %s  (analysis_hvo=%s  occurrences=%d)',
             original_form, parts, wfi_analysis.Hvo, len(occurrences))

    try:
        factory = cache.ServiceLocator.GetService(IWfiGlossFactory)

        for part in parts:
            tss       = TsStringUtils.MakeString(part, ws_en)
            new_gloss = factory.Create()
            wfi_analysis.MeaningsOC.Add(new_gloss)
            new_gloss.Form.set_String(ws_en, tss)
            log.debug('    Created WfiGloss hvo=%s  form=%r', new_gloss.Hvo, part)

        # Redirect segment occurrences → WfiAnalysis (word appears blue).
        # Try indexed assignment first; fall back to Replace() if the
        # Python.NET binding doesn't expose a set_Item on this sequence type.
        for seg, idx in occurrences:
            log.debug('    Redirecting seg_hvo=%s  idx=%d → analysis_hvo=%s',
                      seg.Hvo, idx, wfi_analysis.Hvo)
            try:
                seg.AnalysesRS[idx] = wfi_analysis
            except (TypeError, AttributeError):
                seg.AnalysesRS.Replace(idx, 1, [wfi_analysis])

        # Delete the original slash WfiGloss
        log.debug('    Removing original WfiGloss hvo=%s', original_gloss.Hvo)
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
    report.Info(f'Log file: {LOG_PATH}')

    # Writing system handle
    try:
        ws_en = project.lp.DefaultAnalysisWritingSystem.Handle
        log.info('DefaultAnalysisWritingSystem handle: %s', ws_en)
    except Exception:
        log.critical('Could not get DefaultAnalysisWritingSystem', exc_info=True)
        report.Error(f'Could not read project writing systems. See log: {LOG_PATH}')
        return

    # ---- Phase 1: find slash glosses in wordform analyses ------------------

    try:
        slash_glosses = _find_slash_glosses(project, ws_en)
    except Exception:
        report.Error(f'Error scanning wordform analyses. See log: {LOG_PATH}')
        return

    if not slash_glosses:
        report.Info('No slash glosses found in this project.')
        log.info('No slash glosses found — nothing to do')
        return

    report.Info(f'Found {len(slash_glosses)} slash gloss(es) in wordform analyses.')

    # ---- Phase 2: find text-segment occurrences ----------------------------

    try:
        _find_text_occurrences(project, slash_glosses)
    except Exception:
        report.Error(f'Error scanning text segments. See log: {LOG_PATH}')
        return

    total_occ = sum(len(v['occurrences']) for v in slash_glosses.values())
    report.Info(f'{total_occ} total occurrence(s) found in text segments.')

    # ---- Build list for dialog ---------------------------------------------

    gloss_entries = []
    for hvo, v in slash_glosses.items():
        gloss_entries.append({
            'hvo':              hvo,
            'wordform_str':     v['wordform_str'],
            'gloss_form':       v['form'],
            'occurrence_count': len(v['occurrences']),
        })
    # Sort alphabetically by gloss form for readability
    gloss_entries.sort(key=lambda e: e['gloss_form'].lower())

    # ---- Let the user choose which glosses to split ------------------------

    chosen_hvos = _choose_glosses(gloss_entries)
    if not chosen_hvos:
        report.Info('Cancelled — no glosses selected.')
        log.info('User cancelled or selected nothing')
        return

    log.info('User selected %d gloss(es): %s', len(chosen_hvos), chosen_hvos)

    # ---- Preview or Apply --------------------------------------------------

    cache         = project.project
    total_split   = 0
    total_chosen  = len(chosen_hvos)

    if not modifyAllowed:
        # Preview: report what would change
        report.Info(f'\nPreview — {total_chosen} gloss(es) selected:')
        for hvo in chosen_hvos:
            v     = slash_glosses[hvo]
            parts = _split_form(v['form'])
            occ   = len(v['occurrences'])
            report.Info(f'  \u201c{v["form"]}\u201d ({v["wordform_str"]}) \u2192 {parts}'
                        f'  [{occ} occurrence(s) in texts]')
        report.Info('\nRun again with \u201cModify\u201d enabled to apply changes.')
        log.info('Preview complete')
        return

    # Modify mode — FLExTools already opened an undo task for us; just make modifications
    log.info('Applying modifications (undo task managed by FLExTools)')
    try:
        for hvo in chosen_hvos:
            ok = _split_one(slash_glosses[hvo], ws_en, cache, report)
            if ok:
                total_split += 1
    except Exception:
        log.error('Exception during modification', exc_info=True)
        report.Error(f'Error during modification — see log: {LOG_PATH}')
        return

    # ---- Summary -----------------------------------------------------------

    report.Info(f'\nDone. Split {total_split} of {total_chosen} slash gloss(es).')
    if total_split:
        report.Info('Words in texts now show as blue (unapproved). '
                    'Open each word in FLEx\u2019s interlinear view to approve '
                    'the correct gloss.')
    log.info('Finished: %d/%d glosses split', total_split, total_chosen)
    log.info('Main() finished')
    log.info('=' * 70)


# ---------------------------------------------------------------------------
# FLExTools module registration (required)
# ---------------------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(runFunction=Main, docs=docs)

if __name__ == '__main__':
    print(FlexToolsModule.Help())
