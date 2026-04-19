"""
importer.py — Create a FLEx interlinear text directly via LCM
=============================================================
Receives already-parsed verse data from the JS frontend and writes it
directly into the FLEx LCM database.  No .flextext file is ever created
or shown to the user; this is purely an internal implementation detail.

The flextext XML builder (buildFlexText in the frontend JS) is preserved
in the frontend for reference and debugging but is not called by this module.

For each word token:
  - One gloss part   → WfiAnalysis with one WfiGloss; AnalysesRS → WfiGloss
                        (word approved / shows as green in FLEx)
  - Multiple parts   → WfiAnalysis with multiple WfiGloss objects;
                        AnalysesRS → WfiAnalysis (word blue/unapproved)

After this runs, split_all_slash_glosses() from glosses.py is called to
catch any pre-existing slash glosses in the repository (e.g. if this
wordform has been seen before with a slash gloss that wasn't split yet).

Verse data format received from JS:
    [
      {
        "ref":         "Acts 6:1",
        "words":       [ { "g": "Ἐν", "S": "G1722", "l": "ἐν", "gls": "in/on/among" }, ... ],
        "translation": "Now in these days...",
        "c":  6,
        "v":  1
      },
      ...
    ]
"""

import logging

log = logging.getLogger(__name__)

# LCM imports are deferred to function bodies.  This keeps the module importable
# on non-Windows machines (e.g. macOS development) without crashing.


# ---------------------------------------------------------------------------
# Helper — split a slash-gloss string the same way glosses.split_form() does
# ---------------------------------------------------------------------------

def _split_form(form: str) -> list[str]:
    """Split 'to serve/heal' → ['serve', 'heal']; 'in/on/among' → ['in','on','among']."""
    parts = []
    for raw in form.split('/'):
        p = raw.strip()
        if p.lower().startswith('to '):
            p = p[3:]
        if p:
            parts.append(p)
    return parts or [form.strip()]   # never return empty list


# ---------------------------------------------------------------------------
# WfiWordform lookup / creation
# ---------------------------------------------------------------------------

def _build_wordform_cache(lcm_cache, ws_grc: int) -> dict:
    """
    Build a dict of  Greek surface form (str) → IWfiWordform  from the
    wordform repository.  Call once before processing a text so we can
    reuse existing wordforms rather than creating duplicates.
    """
    from SIL.LCModel import IWfiWordformRepository

    log.info('Building wordform cache from repository...')
    wf_by_form = {}
    repo = lcm_cache.ServiceLocator.GetService(IWfiWordformRepository)
    for wf in repo.AllInstances():
        try:
            ts = wf.Form.get_String(ws_grc)
            if ts and ts.Text:
                wf_by_form[ts.Text] = wf
                log.debug('  cached wf hvo=%s  form=%r', wf.Hvo, ts.Text)
        except Exception:
            log.debug('  skipped wf hvo=%s (unreadable form)', wf.Hvo, exc_info=True)
    log.info('Wordform cache: %d existing form(s)', len(wf_by_form))
    return wf_by_form


def _get_or_create_wordform(surface: str, ws_grc: int,
                             wf_cache: dict, lcm_cache, lp):
    """
    Return an IWfiWordform for *surface*, reusing an existing one if present,
    otherwise creating a new one and adding it to the project.

    *wf_cache* is updated in-place so subsequent calls for the same form
    don't create duplicates.
    """
    from SIL.LCModel        import IWfiWordformFactory
    from SIL.LCModel.Core.Text import TsStringUtils

    if surface in wf_cache:
        log.debug('  wf cache hit: %r → hvo=%s', surface, wf_cache[surface].Hvo)
        return wf_cache[surface]

    log.debug('  creating new WfiWordform for %r', surface)
    factory = lcm_cache.ServiceLocator.GetService(IWfiWordformFactory)
    wf      = factory.Create()

    # Attach to the LangProject.  The exact owner path differs across FLEx
    # versions; try the most common paths in order.
    # FLEx 9.x: lp.WordformsOC  or  lp.AllWordforms (collection)
    # FLEx 8.x: lp.WordformInventoryOA.WordformsOC
    attached = False
    for attempt, add_fn in enumerate([
        lambda: lp.WordformsOC.Add(wf),                          # FLEx 9+
        lambda: lp.WordformInventoryOA.WordformsOC.Add(wf),      # FLEx 8.x
    ]):
        try:
            add_fn()
            log.debug('  attached wf hvo=%s via attempt %d', wf.Hvo, attempt)
            attached = True
            break
        except Exception as e:
            log.debug('  attach attempt %d failed: %s', attempt, e)

    if not attached:
        log.warning('  could not attach WfiWordform hvo=%s for %r — '
                    'it may be unowned; continuing anyway', wf.Hvo, surface)

    wf.Form.set_String(ws_grc, TsStringUtils.MakeString(surface, ws_grc))
    wf_cache[surface] = wf
    log.debug('  created WfiWordform hvo=%s  form=%r', wf.Hvo, surface)
    return wf


# ---------------------------------------------------------------------------
# Per-word analysis creation
# ---------------------------------------------------------------------------

def _create_analysis_for_token(token: dict, ws_en: int, ws_grc: int,
                                wf_cache: dict, lcm_cache, lp) -> tuple:
    """
    For one word token from the JS verse data, create or reuse:
      - IWfiWordform  (one per unique Greek surface form)
      - IWfiAnalysis  (one per word occurrence — analyses share a wordform)
      - IWfiGloss(es) (one per slash-separated gloss part)

    Returns:
        (analysis_object, point_to_analysis: bool)

        point_to_analysis=True  → AnalysesRS should point to the WfiAnalysis
                                   (multiple gloss choices → word is blue)
        point_to_analysis=False → AnalysesRS should point to the single WfiGloss
                                   (one choice → word is approved/green)
    """
    from SIL.LCModel        import IWfiAnalysisFactory, IWfiGlossFactory
    from SIL.LCModel.Core.Text import TsStringUtils

    surface = (token.get('g') or '').strip()
    gls_raw = (token.get('gls') or '').strip()

    log.debug('    token: surface=%r  gls=%r', surface, gls_raw)

    if not surface:
        log.warning('    token has no Greek surface form — skipping')
        return None, False

    # Wordform
    wf = _get_or_create_wordform(surface, ws_grc, wf_cache, lcm_cache, lp)

    # Analysis
    analysis_factory = lcm_cache.ServiceLocator.GetService(IWfiAnalysisFactory)
    analysis         = analysis_factory.Create()
    wf.AnalysesOC.Add(analysis)
    log.debug('    created WfiAnalysis hvo=%s on wf hvo=%s', analysis.Hvo, wf.Hvo)

    # Gloss(es)
    parts         = _split_form(gls_raw) if gls_raw else []
    gloss_factory = lcm_cache.ServiceLocator.GetService(IWfiGlossFactory)

    for part in parts:
        tss   = TsStringUtils.MakeString(part, ws_en)
        gloss = gloss_factory.Create()
        analysis.MeaningsOC.Add(gloss)
        gloss.Form.set_String(ws_en, tss)
        log.debug('    created WfiGloss hvo=%s  form=%r', gloss.Hvo, part)

    # Decide what the segment should point to
    multi_gloss = len(parts) > 1
    log.debug('    parts=%s  point_to_analysis=%s', parts, multi_gloss)
    return analysis, multi_gloss


# ---------------------------------------------------------------------------
# Text / paragraph / segment creation
# ---------------------------------------------------------------------------

def create_flex_text(lcm_cache, lp, ws_en: int, ws_grc: int,
                     passage_ref: str, verses: list,
                     ws_trans: int | None = None) -> int:
    """
    Create a new interlinear IText in the FLEx project from the verse data.

    One paragraph per text, one ISegment (phrase) per verse, one IAnalysis
    reference per word in AnalysesRS.

    The paragraph baseline text is the Greek surface forms joined with spaces.
    Segment offsets are calculated from the concatenated baseline.

    Args:
        lcm_cache:    LcmCache (project.project in flex_project terms)
        lp:           LangProject (project.lp)
        ws_en:        int  English analysis WS handle
        ws_grc:       int  Greek vernacular WS handle
        passage_ref:  str  text title displayed in FLEx
        verses:       list of verse dicts from the JS frontend

    Returns:
        int  total number of word tokens written

    NOTE: Must be called inside an undo task (BeginUndoTask already called
    by the caller in main.py).
    """
    from SIL.LCModel import (
        ITextFactory,
        IStTextFactory,
        IStTxtParaFactory,
        ISegmentFactory,
    )
    from SIL.LCModel.Core.Text import TsStringUtils

    log.info('create_flex_text: %r  (%d verse(s))', passage_ref, len(verses))

    # Pre-build wordform cache so we reuse existing forms
    wf_cache = _build_wordform_cache(lcm_cache, ws_grc)

    sl = lcm_cache.ServiceLocator

    # ---- IText -------------------------------------------------------------
    log.info('Creating IText...')
    text_factory = sl.GetService(ITextFactory)
    text         = text_factory.Create()
    lp.TextsOC.Add(text)
    text.Name.set_String(ws_en, TsStringUtils.MakeString(passage_ref, ws_en))
    log.info('  IText hvo=%s  name=%r', text.Hvo, passage_ref)

    # ---- IStText -----------------------------------------------------------
    log.info('Creating IStText...')
    sttext_factory = sl.GetService(IStTextFactory)
    sttext         = sttext_factory.Create()
    text.ContentsOA = sttext
    log.info('  IStText hvo=%s', sttext.Hvo)

    # ---- One paragraph to hold all segments --------------------------------
    log.info('Creating IStTxtPara...')
    para_factory = sl.GetService(IStTxtParaFactory)
    para         = para_factory.Create()
    sttext.ParagraphsOS.Add(para)
    log.info('  IStTxtPara hvo=%s', para.Hvo)

    # Build the baseline text for the whole paragraph (all verses concatenated)
    # Each verse's words become one contiguous block, verses separated by '\n'.
    # We track char offsets so each segment can set BeginOffset/EndOffset.
    log.info('Building paragraph baseline text from %d verse(s)...', len(verses))
    baseline_parts = []
    for v in verses:
        words = v.get('words') or []
        baseline_parts.append(' '.join((w.get('g') or '') for w in words))

    baseline_text = '\n'.join(baseline_parts)
    log.info('  baseline length=%d chars', len(baseline_text))
    log.debug('  baseline preview: %r', baseline_text[:120])

    para.Contents = TsStringUtils.MakeString(baseline_text, ws_grc)
    log.info('  paragraph Contents set')

    # ---- Segments (one per verse) + analyses -------------------------------
    seg_factory = sl.GetService(ISegmentFactory)
    n_tokens    = 0
    offset      = 0   # current position in the paragraph baseline string

    for verse_idx, verse in enumerate(verses):
        ref      = verse.get('ref', f'verse {verse_idx+1}')
        words    = verse.get('words') or []
        trans    = (verse.get('translation') or '').strip()
        verse_baseline = baseline_parts[verse_idx]

        log.info('  Segment %d: ref=%r  words=%d  trans=%r',
                 verse_idx, ref, len(words), trans[:60])

        seg = seg_factory.Create()
        para.SegmentsOS.Add(seg)

        seg_begin = offset
        seg_end   = offset + len(verse_baseline)
        seg.BeginOffset = seg_begin
        seg.EndOffset   = seg_end
        log.debug('    seg hvo=%s  offsets=[%d, %d]', seg.Hvo, seg_begin, seg_end)

        # Free translation on the segment
        if trans:
            _ws_tr = ws_trans if ws_trans is not None else ws_en
            seg.FreeTranslation.set_String(_ws_tr,
                TsStringUtils.MakeString(trans, _ws_tr))
            log.debug('    free translation set: %r', trans[:60])

        # Analyses for each word
        for w_idx, token in enumerate(words):
            log.debug('    word[%d]: %r', w_idx, token.get('g'))
            analysis, point_to_analysis = _create_analysis_for_token(
                token, ws_en, ws_grc, wf_cache, lcm_cache, lp
            )
            if analysis is None:
                log.warning('    word[%d] skipped (no surface form)', w_idx)
                continue

            if point_to_analysis:
                # Multiple gloss choices — word appears blue/unapproved
                seg.AnalysesRS.Append(analysis)
                log.debug('    AnalysesRS[%d] → WfiAnalysis hvo=%s  (blue)',
                          w_idx, analysis.Hvo)
            else:
                # Single gloss — point directly to the WfiGloss (approved/green)
                meanings = list(analysis.MeaningsOC)
                if meanings:
                    seg.AnalysesRS.Append(meanings[0])
                    log.debug('    AnalysesRS[%d] → WfiGloss hvo=%s  (green)',
                              w_idx, meanings[0].Hvo)
                else:
                    # No gloss at all — point to WfiAnalysis (blue, no choices)
                    seg.AnalysesRS.Append(analysis)
                    log.debug('    AnalysesRS[%d] → WfiAnalysis hvo=%s  (no gloss)',
                              w_idx, analysis.Hvo)
            n_tokens += 1

        # Advance offset: verse text + 1 for the '\n' separator
        offset = seg_end + 1
        log.debug('    offset advanced to %d', offset)

    log.info('create_flex_text complete: %d token(s) written', n_tokens)
    return n_tokens


# ---------------------------------------------------------------------------
# Convenience wrapper used by main.py
# ---------------------------------------------------------------------------

def import_passage(flex_project, passage_ref: str, verses: list) -> dict:
    """
    Thin wrapper called by main.py.Api.import_to_flex().
    flex_project is an open FLExProject instance.
    The caller is responsible for BeginUndoTask / EndUndoTask.
    """
    log.info('import_passage: %r  %d verse(s)', passage_ref, len(verses))
    from core.glosses import split_all_slash_glosses

    lcm_cache = flex_project.project
    lp        = flex_project.lp
    ws_en     = lp.DefaultAnalysisWritingSystem.Handle
    ws_grc    = lp.DefaultVernacularWritingSystem.Handle

    n_tokens = create_flex_text(lcm_cache, lp, ws_en, ws_grc, passage_ref, verses)
    n_split, n_total = split_all_slash_glosses(lcm_cache, ws_en)

    return {
        'n_tokens': n_tokens,
        'n_split':  n_split,
        'n_total':  n_total,
    }
