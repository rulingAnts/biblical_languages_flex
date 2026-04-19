"""
glosses.py — Core gloss-splitting logic (FLExTools-independent)
===============================================================
Contains the pure LCM logic extracted from tools/Split_Slash_Glosses.py.
No FLExTools UI, no Tkinter, no report object — just functions that
accept an LCM cache and operate on it.

Called by:
  - tools/Split_Slash_Glosses.py  (FLExTools module entry point)
  - standalone/core/importer.py   (standalone app entry point)

Both callers pass the raw LCM cache (LcmCache) and a writing-system handle.
The FLExTools caller gets those from its project wrapper; the standalone app
gets them from flex_project.FLExProject.
"""

import logging

log = logging.getLogger(__name__)

# SIL.LCModel imports are deferred to function bodies so this module can be
# imported on non-Windows / non-FLEx machines without crashing (e.g. for
# unit tests with mocks, or CI environments).


# ---------------------------------------------------------------------------
# Phase 1 — find all slash glosses in the wordform repository
# ---------------------------------------------------------------------------

def find_slash_glosses(lcm_cache, ws_en):
    """
    Scan all WfiWordform → WfiAnalysis → WfiGloss objects in the project
    and return every WfiGloss whose English form contains '/'.

    Args:
        lcm_cache:  LcmCache  (project.project in FLExTools terms)
        ws_en:      int       writing-system handle for English (analysis WS)

    Returns:
        dict  gloss_hvo (int) ->
            { 'gloss':        IWfiGloss,
              'analysis':     IWfiAnalysis,
              'wordform':     IWfiWordform,
              'wordform_str': str,
              'form':         str,
              'occurrences':  []   # populated by find_text_occurrences()
            }
    """
    from SIL.LCModel import IWfiWordformRepository

    log.info('Phase 1: scanning wordform repository for slash glosses...')
    found = {}
    sl = lcm_cache.ServiceLocator
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
                    log.debug('Could not read gloss hvo=%s', gloss.Hvo, exc_info=True)
                    continue

                if form_text and '/' in form_text:
                    found[gloss.Hvo] = {
                        'gloss':        gloss,
                        'analysis':     analysis,
                        'wordform':     wf,
                        'wordform_str': wf_str,
                        'form':         form_text,
                        'occurrences':  [],
                    }

    log.info('Phase 1 complete: %d slash gloss(es) found', len(found))
    return found


# ---------------------------------------------------------------------------
# Phase 2 — find segment occurrences of each slash gloss
# ---------------------------------------------------------------------------

def find_text_occurrences(lcm_cache, slash_glosses):
    """
    Scan every ISegment in the project (via ISegmentRepository) and record
    which segments/positions reference each slash gloss.

    Matches are attempted three ways:
      1. Direct WfiGloss hvo match (word has an approved slash gloss)
      2. WfiAnalysis hvo → slash WfiGloss (word has a tentative slash gloss)
      3. WfiWordform hvo → slash WfiGloss (word is unanalyzed; wordform has
         a slash-gloss analysis in the repository)

    Populates slash_glosses[hvo]['occurrences'] in-place.
    """
    from SIL.LCModel import ISegmentRepository

    log.info('Phase 2: scanning segments for occurrences...')

    slash_hvo_set     = set(slash_glosses.keys())
    analysis_to_gloss = {v['analysis'].Hvo: hvo
                         for hvo, v in slash_glosses.items()}
    wordform_to_gloss = {}
    for hvo, v in slash_glosses.items():
        wordform_to_gloss.setdefault(v['wordform'].Hvo, hvo)

    n_seg = 0
    for seg in lcm_cache.ServiceLocator.GetService(ISegmentRepository).AllInstances():
        n_seg += 1
        for idx in range(seg.AnalysesRS.Count):
            a_hvo = seg.AnalysesRS[idx].Hvo
            if a_hvo in slash_hvo_set:
                g_hvo = a_hvo
            elif a_hvo in analysis_to_gloss:
                g_hvo = analysis_to_gloss[a_hvo]
            elif a_hvo in wordform_to_gloss:
                g_hvo = wordform_to_gloss[a_hvo]
            else:
                continue
            slash_glosses[g_hvo]['occurrences'].append((seg, idx))

    total = sum(len(v['occurrences']) for v in slash_glosses.values())
    log.info('Phase 2 complete: %d segment(s), %d occurrence(s)', n_seg, total)


# ---------------------------------------------------------------------------
# Gloss form normalisation
# ---------------------------------------------------------------------------

def split_form(form):
    """
    Split a slash-separated gloss string into clean individual parts.

    'to serve/heal'    → ['serve', 'heal']
    'to come/go down'  → ['come', 'go down']
    'in/on/among'      → ['in', 'on', 'among']
    'to'               → ['to']   (bare 'to' left intact — valid gloss)
    """
    parts = []
    for raw in form.split('/'):
        p = raw.strip()
        if p.lower().startswith('to '):
            p = p[3:]
        if p:
            parts.append(p)
    return parts


# ---------------------------------------------------------------------------
# Phase 3 — split one gloss entry
# ---------------------------------------------------------------------------

def split_one(entry, ws_en, lcm_cache):
    """
    Split a single slash-gloss entry in the LCM database:
      1. Create a new WfiGloss for each slash-separated part.
      2. Redirect every text-segment occurrence to the parent WfiAnalysis
         (makes the word appear blue / unapproved in FLEx).
      3. Delete the original slash WfiGloss.

    Args:
        entry:      one value from the find_slash_glosses() result dict
        ws_en:      int  English writing-system handle
        lcm_cache:  LcmCache

    Returns:
        True on success, False on error (error is logged).
    """
    from SIL.LCModel import IWfiGlossFactory
    from SIL.LCModel.Core.Text import TsStringUtils

    original_gloss = entry['gloss']
    original_form  = entry['form']
    wfi_analysis   = entry['analysis']
    occurrences    = entry['occurrences']
    parts = split_form(original_form)

    log.info('  Splitting %r → %s  (%d occurrence(s))',
             original_form, parts, len(occurrences))

    try:
        factory = lcm_cache.ServiceLocator.GetService(IWfiGlossFactory)

        for part in parts:
            tss       = TsStringUtils.MakeString(part, ws_en)
            new_gloss = factory.Create()
            wfi_analysis.MeaningsOC.Add(new_gloss)
            new_gloss.Form.set_String(ws_en, tss)
            log.debug('    Created WfiGloss hvo=%s  form=%r', new_gloss.Hvo, part)

        for seg, idx in occurrences:
            try:
                seg.AnalysesRS[idx] = wfi_analysis
            except (TypeError, AttributeError):
                seg.AnalysesRS.Replace(idx, 1, [wfi_analysis])
            log.debug('    Redirected seg_hvo=%s idx=%d → analysis_hvo=%s',
                      seg.Hvo, idx, wfi_analysis.Hvo)

        wfi_analysis.MeaningsOC.Remove(original_gloss)
        log.debug('    Removed original WfiGloss hvo=%s', original_gloss.Hvo)
        return True

    except Exception:
        log.error('    FAILED to split %r', original_form, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Convenience: run all three phases together
# ---------------------------------------------------------------------------

def split_all_slash_glosses(lcm_cache, ws_en, chosen_hvos=None):
    """
    Run the full pipeline: find → scan occurrences → split.

    Args:
        lcm_cache:    LcmCache
        ws_en:        int  English writing-system handle
        chosen_hvos:  list of gloss hvos to process, or None to process all

    Returns:
        (n_split, n_total)  counts of successfully split glosses
    """
    slash_glosses = find_slash_glosses(lcm_cache, ws_en)
    if not slash_glosses:
        log.info('No slash glosses found — nothing to do')
        return 0, 0

    find_text_occurrences(lcm_cache, slash_glosses)

    targets = chosen_hvos if chosen_hvos is not None else list(slash_glosses.keys())
    n_split = 0
    for hvo in targets:
        if hvo in slash_glosses:
            if split_one(slash_glosses[hvo], ws_en, lcm_cache):
                n_split += 1

    log.info('split_all_slash_glosses complete: %d/%d split', n_split, len(targets))
    return n_split, len(targets)
