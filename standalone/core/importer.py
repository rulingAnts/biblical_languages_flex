"""
importer.py — Create FLEx interlinear texts via LCM
====================================================
Uses pre-populated WfiWordform / WfiAnalysis / WfiGloss objects that already
exist in the template project.  Does NOT create new analysis objects — it
looks up the existing ones by Greek surface form.

For each word token:
  WfiGloss   (single gloss)   → AnalysesRS → WfiGloss   (green / approved)
  WfiAnalysis (multiple glosses) → AnalysesRS → WfiAnalysis (blue / user picks)
  WfiWordform (no glosses)    → AnalysesRS → WfiWordform (red / unanalysed)
  Not found in cache          → token skipped with warning

Verse data format received from the JS frontend:
    [
      {
        "ref":         "Acts 6:1",
        "words":       [ { "g": "Ἐν", "S": "G1722", "l": "ἐν" }, … ],
        "translation": "Now in these days…",
        "c":  6,
        "v":  1
      },
      …
    ]
"""

import logging

log = logging.getLogger(__name__)

# LCM imports are deferred to function bodies so this module stays importable
# on non-Windows machines (macOS dev) without crashing.


# ---------------------------------------------------------------------------
# Analysis cache
# ---------------------------------------------------------------------------

def build_analysis_cache(lcm_cache, ws_grc: int) -> dict:
    """
    Build a dict of Greek surface form (str) → IAnalysis.

    IAnalysis is:
      WfiGloss    if exactly one gloss exists  → approved/green when linked
      WfiAnalysis if multiple glosses exist     → candidate/blue when linked
      WfiWordform if no analyses exist          → unanalysed/red when linked

    Call once before processing a passage to avoid repeated repository scans.
    """
    from SIL.LCModel import IWfiWordformRepository

    log.info('Building analysis cache…')
    repo  = lcm_cache.ServiceLocator.GetService(IWfiWordformRepository)
    cache = {}
    n_single = n_multi = n_none = 0

    for wf in repo.AllInstances():
        try:
            form_ts = wf.Form.get_String(ws_grc)
            if not form_ts or not form_ts.Text:
                continue
            surface  = form_ts.Text
            analyses = list(wf.AnalysesOC)

            if not analyses:
                cache[surface] = wf          # WfiWordform fallback
                n_none += 1
            else:
                ana     = analyses[0]
                glosses = list(ana.MeaningsOC)
                if len(glosses) == 1:
                    cache[surface] = glosses[0]  # WfiGloss → approved
                    n_single += 1
                else:
                    cache[surface] = ana         # WfiAnalysis → candidate
                    n_multi += 1
        except Exception:
            log.debug('Error reading wf hvo=%s', wf.Hvo, exc_info=True)

    log.info('Analysis cache: %d single  %d multi  %d none  → %d total',
             n_single, n_multi, n_none, len(cache))
    return cache


# ---------------------------------------------------------------------------
# Text creation
# ---------------------------------------------------------------------------

def create_flex_text(lcm_cache, lp, ws_en: int, ws_grc: int,
                     book_name: str, verses: list,
                     analysis_cache: dict | None = None) -> dict:
    """
    Create a new IText in the FLEx project for *book_name*.

    One IStTxtPara per verse, one ISegment per paragraph (BeginOffset=0),
    IAnalysis references in AnalysesRS per word token.

    Args:
        lcm_cache:      LcmCache (project.project)
        lp:             LangProject (project.lp)
        ws_en:          int  English analysis WS handle
        ws_grc:         int  Greek vernacular WS handle
        book_name:      str  displayed as the text title in FLEx
        verses:         list of verse dicts from the JS frontend
        analysis_cache: pre-built dict from build_analysis_cache(); if None,
                        it is built here (slower for repeated calls)

    Returns:
        dict with keys n_tokens, n_found, n_missing
    """
    from SIL.LCModel import (
        ITextFactory,
        IStTextFactory,
        IStTxtParaFactory,
        ISegmentFactory,
    )
    from SIL.LCModel.Core.Text import TsStringUtils

    if analysis_cache is None:
        analysis_cache = build_analysis_cache(lcm_cache, ws_grc)

    sl = lcm_cache.ServiceLocator
    log.info('create_flex_text: %r  %d verse(s)', book_name, len(verses))

    # ── IText ────────────────────────────────────────────────────────────
    text = sl.GetService(ITextFactory).Create()
    try:
        lp.TextsOC.Add(text)
    except Exception as e:
        log.warning('lp.TextsOC.Add failed (%s) — trying lp.Texts', e)
        lp.Texts.Add(text)
    text.Name.set_String(ws_en, TsStringUtils.MakeString(book_name, ws_en))
    log.info('IText hvo=%s  name=%r', text.Hvo, book_name)

    # ── IStText ───────────────────────────────────────────────────────────
    sttext = sl.GetService(IStTextFactory).Create()
    text.ContentsOA = sttext

    para_factory = sl.GetService(IStTxtParaFactory)
    seg_factory  = sl.GetService(ISegmentFactory)

    n_tokens = n_found = n_missing = 0

    for verse in verses:
        words = verse.get('words') or []
        trans = (verse.get('translation') or '').strip()

        greek_text = ' '.join(w.get('g', '') for w in words if w.get('g', '').strip())

        # ── IStTxtPara ────────────────────────────────────────────────────
        para = para_factory.Create()
        sttext.ParagraphsOS.Add(para)
        para.Contents = TsStringUtils.MakeString(greek_text, ws_grc)

        # ── ISegment ──────────────────────────────────────────────────────
        seg = seg_factory.Create()
        para.SegmentsOS.Add(seg)
        seg.BeginOffset = 0

        if trans:
            seg.FreeTranslation.set_String(
                ws_en, TsStringUtils.MakeString(trans, ws_en))

        # ── AnalysesRS — one reference per word token ─────────────────────
        for w in words:
            surface = (w.get('g') or '').strip()
            if not surface:
                continue
            n_tokens += 1
            ianalysis = analysis_cache.get(surface)
            if ianalysis is not None:
                seg.AnalysesRS.Append(ianalysis)
                n_found += 1
            else:
                n_missing += 1
                log.debug('Surface not in cache: %r', surface)

    log.info('create_flex_text done: tokens=%d  found=%d  missing=%d',
             n_tokens, n_found, n_missing)
    return {'n_tokens': n_tokens, 'n_found': n_found, 'n_missing': n_missing}


# ---------------------------------------------------------------------------
# Convenience wrapper used by main.py
# ---------------------------------------------------------------------------

def import_passage(flex_project, book_name: str, verses: list,
                   analysis_cache: dict | None = None) -> dict:
    """
    Thin wrapper called by main.py  Api.import_to_flex().
    flex_project is an open FLExProject instance.
    The caller is responsible for BeginUndoTask / EndUndoTask.

    Pass a pre-built analysis_cache for speed when importing multiple books
    in one session.
    """
    log.info('import_passage: %r  %d verse(s)', book_name, len(verses))

    lcm_cache = flex_project.project
    lp        = flex_project.lp
    ws_en     = int(lp.DefaultAnalysisWritingSystem.Handle)
    ws_grc    = int(lp.DefaultVernacularWritingSystem.Handle)

    return create_flex_text(
        lcm_cache, lp, ws_en, ws_grc,
        book_name, verses, analysis_cache
    )
