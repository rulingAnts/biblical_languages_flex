"""
importer.py — Create a FLEx interlinear text directly via LCM
=============================================================
Fetches Greek NT data for a passage (via MorphGNT / Sword), then writes
the text directly into the FLEx LCM database — no intermediate .flextext
file is created or shown to the user.

For each word token:
  - One gloss part   → created as approved (WfiGloss, word appears green)
  - Multiple parts   → created as unapproved (WfiAnalysis with multiple
                        WfiGloss choices, word appears blue for approval)

After this module runs, the user opens FLEx and finds the passage ready
to work through: blue words have a dropdown of gloss choices.

Pipeline:
  1. fetch_passage()     — fetch MorphGNT tokens for the passage reference
  2. create_flex_text()  — write IText + IStTxtPara + ISegment + analyses
                           into the open LCM project

The flextext XML format is NOT used here; all writes go direct to LCM.
(A flextext intermediate could be used for debugging — see _passage_to_flextext()
below — but it is never saved to disk or shown to the user.)
"""

import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Passage fetching (MorphGNT via Sword / pysword)
# ---------------------------------------------------------------------------

def fetch_passage(book, chapter_start, verse_start, chapter_end, verse_end):
    """
    Return a list of word-token dicts for the given passage range.

    Each dict has:
        'surface'  str   Greek word form as it appears in the text
        'lemma'    str   dictionary lemma
        'strongs'  str   Strong's number (e.g. 'G1722')
        'pos'      str   part-of-speech tag (MorphGNT convention)
        'gloss'    str   English gloss (may contain '/' for multiple options)
        'verse'    str   e.g. 'ACT 6:1'

    Raises ValueError for unrecognised book/chapter/verse references.

    TODO: implement using pysword / MorphGNT data files.
          See app.py (legacy) for the original Sword-based approach,
          but do NOT assume that code works — verify independently.
    """
    raise NotImplementedError('fetch_passage: MorphGNT data source not yet wired up')


def fetch_free_translation(book, chapter_start, verse_start,
                           chapter_end, verse_end, translation='NET'):
    """
    Return a dict mapping verse reference → free translation string.

    translation: Sword module name (e.g. 'NET', 'ESV', 'KJV')

    TODO: implement using pysword.
    """
    raise NotImplementedError('fetch_free_translation: not yet implemented')


# ---------------------------------------------------------------------------
# LCM text creation
# ---------------------------------------------------------------------------

def create_flex_text(lcm_cache, ws_en, ws_grc, passage_ref,
                     tokens, free_translations=None):
    """
    Create a new interlinear IText in the FLEx project from the given tokens.

    Args:
        lcm_cache:         LcmCache (from FLExProject.project)
        ws_en:             int  English analysis writing-system handle
        ws_grc:            int  Greek vernacular writing-system handle
        passage_ref:       str  human-readable title, e.g. 'Acts 6:1-7'
        tokens:            list of word-token dicts (from fetch_passage)
        free_translations: dict verse_ref → str, or None

    Returns:
        IText object that was created.

    This is the core of v4: no .flextext file is written.

    TODO: implement once fetch_passage() is working and we have confirmed
          which LCM factory calls are needed (ITextFactory, IStTxtParaFactory,
          ISegmentFactory, etc.).  Reference: FLExTools source and LCM API docs.
    """
    raise NotImplementedError('create_flex_text: LCM text creation not yet implemented')


# ---------------------------------------------------------------------------
# Top-level entry point called by the app backend
# ---------------------------------------------------------------------------

def import_passage(flex_project, passage_ref,
                   book, chapter_start, verse_start,
                   chapter_end, verse_end,
                   translation='NET'):
    """
    Full pipeline: fetch data → create text in FLEx → split slash glosses.

    Args:
        flex_project:  FLExProject instance (already open, FLEx must be closed)
        passage_ref:   str  display name, e.g. 'Acts 6:1-7'
        book/chapter/verse args: passage boundaries
        translation:   Sword module name for free translation

    Returns:
        dict with keys:
            'success':     bool
            'n_tokens':    int   number of word tokens imported
            'n_split':     int   number of slash glosses split
            'message':     str   human-readable summary for the UI
    """
    from .glosses import split_all_slash_glosses

    lcm_cache = flex_project.project
    lp        = flex_project.lp

    try:
        ws_en  = lp.DefaultAnalysisWritingSystem.Handle
        ws_grc = lp.DefaultVernacularWritingSystem.Handle
    except Exception as e:
        return {'success': False, 'message': f'Could not read writing systems: {e}'}

    # Step 1: fetch passage data
    try:
        tokens = fetch_passage(book, chapter_start, verse_start,
                               chapter_end, verse_end)
        free_tr = fetch_free_translation(book, chapter_start, verse_start,
                                         chapter_end, verse_end, translation)
    except Exception as e:
        return {'success': False, 'message': f'Error fetching passage data: {e}'}

    # Step 2: create text in FLEx
    try:
        create_flex_text(lcm_cache, ws_en, ws_grc,
                         passage_ref, tokens, free_tr)
    except Exception as e:
        return {'success': False, 'message': f'Error writing to FLEx project: {e}'}

    # Step 3: split slash glosses (covers the new text + any pre-existing ones)
    try:
        n_split, n_total = split_all_slash_glosses(lcm_cache, ws_en)
    except Exception as e:
        return {'success': False, 'message': f'Error splitting glosses: {e}'}

    return {
        'success':   True,
        'n_tokens':  len(tokens),
        'n_split':   n_split,
        'message':   (
            f'Imported {len(tokens)} words from {passage_ref}. '
            f'{n_split} slash glosses split into individual choices. '
            f'Open FLEx to begin analysis.'
        ),
    }
