"""
Populate NT Wordforms (direct XML method)
==========================================
Standalone Python script — no FLExTools, no Python.NET required.

Writes WfiWordform / WfiAnalysis / WfiGloss objects with gloss text
directly into a FLEx .fwdata XML file, bypassing the LCM API entirely.

The LCM-based FLExTools module cannot reliably persist WfiGloss.Form text
for newly created objects in a large undo task. Direct XML manipulation
has no such restriction.

Two-step workflow
-----------------
  Step 1 — build the master gloss list (inspect before committing):

      python Populate_NT_Wordforms_XML.py --build-json

      Reads the NT book JSON files + strongs_greek.json and writes:
          wordform_glosses.json   in the same folder as this script
      Format: { "surface_form": ["gloss1", "gloss2", ...], ... }
      One entry per unique Greek surface form in the NT.
      All gloss choices are pooled across all Strong's numbers for that form.

  Step 2 — populate the .fwdata:

      python Populate_NT_Wordforms_XML.py  <path_to_project.fwdata>
          [--glosses  path/to/wordform_glosses.json]
          [--test]    # adds only one entry (ἐν) for quick verification

      Reads wordform_glosses.json (built in Step 1, or auto-found),
      removes any existing WfiWordform/WfiAnalysis/WfiGloss objects,
      and writes new ones with correct gloss text into the XML.
      A .bak backup of the original .fwdata is kept alongside it.

FLEx MUST be closed before running Step 2.

FWDATA XML structure written
-----------------------------
  <rt class="WfiWordform"  guid="A"  ownerguid="LangProject-guid">
    <Form><AUni ws="grc">ἐν</AUni></Form>
    <AnalysesOC><objsur t="o" guid="B"/></AnalysesOC>
  </rt>
  <rt class="WfiAnalysis"  guid="B"  ownerguid="A">
    <MeaningsOC>
      <objsur t="o" guid="C"/>
      <objsur t="o" guid="D"/>
      <objsur t="o" guid="E"/>
    </MeaningsOC>
  </rt>
  <rt class="WfiGloss"  guid="C"  ownerguid="B">
    <Form><AUni ws="en">among</AUni></Form>
  </rt>
  ...

One WfiAnalysis per surface form.  All unique gloss choices for that form
(pooled across all its Strong's numbers) become WfiGloss objects.
"""

import argparse
import json
import logging
import os
import shutil
import sys
import uuid
from collections import defaultdict
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
    log_path = os.path.join(log_dir, f'PopulateNTWordformsXML_{ts}.log')
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

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(SCRIPT_DIR, 'wordform_glosses.json')

BOOK_NAMES = [
    'Matthew','Mark','Luke','John','Acts','Romans',
    '1Corinthians','2Corinthians','Galatians','Ephesians','Philippians',
    'Colossians','1Thessalonians','2Thessalonians','1Timothy','2Timothy',
    'Titus','Philemon','Hebrews','James','1Peter','2Peter',
    '1John','2John','3John','Jude','Revelation',
]

# ---------------------------------------------------------------------------
# Data location helpers
# ---------------------------------------------------------------------------

def _candidate_data_dirs():
    return [
        os.path.join(SCRIPT_DIR, 'data'),
        os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'docs', 'assets', 'data')),
    ]

def _find_data_dir():
    for d in _candidate_data_dirs():
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, 'Acts.json')):
            return d
    return None

def _find_strongs_file(data_dir):
    for p in [
        os.path.normpath(os.path.join(data_dir, '..', 'strongs_greek.json')),
        os.path.join(data_dir, 'strongs_greek.json'),
    ]:
        if os.path.isfile(p):
            return p
    return None

def _pick_folder(title):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        folder = filedialog.askdirectory(title=title, initialdir=os.path.expanduser('~'))
        root.destroy()
        return folder or None
    except Exception:
        return input(f'{title}\nEnter path: ').strip() or None

def _pick_file(title, filetypes):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return path or None
    except Exception:
        return input(f'{title}\nEnter path: ').strip() or None

# ---------------------------------------------------------------------------
# Gloss helpers
# ---------------------------------------------------------------------------

def _split_form(gls):
    parts = []
    for raw in gls.split('/'):
        p = raw.strip()
        if p.lower().startswith('to '):
            p = p[3:]
        if p:
            parts.append(p)
    return parts or ([gls.strip()] if gls.strip() else [])

def load_strongs(strongs_path):
    with open(strongs_path, encoding='utf-8') as f:
        raw = json.load(f)
    strongs = {}
    for k, v in raw.items():
        strongs[k]                = v
        strongs[f'G{k}']          = v
        strongs[f'G{k.zfill(4)}'] = v
    log.info('Strongs: %d entries from %s', len(raw), strongs_path)
    return strongs

# ---------------------------------------------------------------------------
# Step 1 — build master wordform_glosses.json
# ---------------------------------------------------------------------------

def build_gloss_json(output_path):
    """
    Read all NT book JSON files + strongs_greek.json and write:
        { surface_form: [gloss1, gloss2, ...], ... }
    to output_path.  One entry per unique Greek surface form;
    gloss choices pooled across all Strong's numbers for that form.
    """
    data_dir = _find_data_dir()
    if not data_dir:
        print('Data directory not found automatically — please select it.')
        data_dir = _pick_folder('Select folder containing Acts.json, Matthew.json, etc.')
    if not data_dir or not os.path.isfile(os.path.join(data_dir, 'Acts.json')):
        print('ERROR: NT Greek JSON data not found.')
        sys.exit(1)

    strongs_path = _find_strongs_file(data_dir)
    strongs      = load_strongs(strongs_path) if strongs_path else {}
    if not strongs:
        print('WARNING: strongs_greek.json not found — using baked-in gls field only.')

    # surface_form → set of gloss parts
    wf_glosses     = defaultdict(set)
    total_tokens   = 0
    no_gloss_count = 0

    for book in BOOK_NAMES:
        path = os.path.join(data_dir, f'{book}.json')
        if not os.path.isfile(path):
            log.warning('Missing: %s', path)
            continue
        with open(path, encoding='utf-8') as f:
            book_data = json.load(f)
        for verse in book_data.values():
            for w in verse.get('words', []):
                g = (w.get('g') or '').strip()
                S = (w.get('S') or '').strip()
                if not g:
                    continue
                gls = (strongs.get(S) or '').strip()
                if not gls:
                    gls = (w.get('gls') or '').strip()
                if not gls:
                    no_gloss_count += 1
                for part in (_split_form(gls) if gls else []):
                    wf_glosses[g].add(part)
                total_tokens += 1

    # Convert to sorted lists for deterministic output
    result = {surface: sorted(parts) for surface, parts in sorted(wf_glosses.items())}

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    n_wf  = len(result)
    n_gls = sum(len(v) for v in result.values())
    print(f'Written: {output_path}')
    print(f'  {n_wf:,} unique surface forms')
    print(f'  {n_gls:,} total gloss choices')
    print(f'  {no_gloss_count:,} tokens had no gloss (skipped)')
    print()
    print('Inspect the JSON file, then run:')
    print(f'  python {os.path.basename(__file__)}  <path/to/project.fwdata>')
    log.info('build_gloss_json done: wf=%d  gls=%d', n_wf, n_gls)

# ---------------------------------------------------------------------------
# Step 2 — populate .fwdata XML
# ---------------------------------------------------------------------------

def _parse_fwdata(fwdata_path):
    from xml.etree import ElementTree as ET
    log.info('Parsing: %s', fwdata_path)
    tree = ET.parse(fwdata_path)
    root = tree.getroot()
    log.info('Parsed: root=%s  children=%d', root.tag, len(root))
    return tree, root

def _remove_existing_wordforms(root):
    removed = 0
    for cls in ('WfiWordform', 'WfiAnalysis', 'WfiGloss', 'WfiMorphBundle'):
        for rt in root.findall(f'rt[@class="{cls}"]'):
            root.remove(rt)
            removed += 1
    log.info('Removed %d existing Wfi* elements', removed)
    return removed

def _get_langproject_guid(root):
    lp = root.find('rt[@class="LangProject"]')
    if lp is None:
        raise RuntimeError('LangProject element not found in .fwdata')
    return lp.get('guid')


def _add_wordforms_to_xml(root, wf_glosses, lp_guid, ws_grc='grc', ws_en='en'):
    """
    For each entry in wf_glosses { surface: [gloss, ...] }:
      - Create one WfiWordform  (with Checksum, SpellingStatus)
      - Create one WfiAnalysis  (with MorphBundles + Meanings)
      - Create one WfiMorphBundle carrying the surface form
      - Create one WfiGloss per gloss choice

    Element names and structure match what FLEx writes natively:
      WfiWordform  → <Analyses>   (not AnalysesOC)
      WfiAnalysis  → <Meanings>   (not MeaningsOC)
      WfiMorphBundle.Form uses <AStr><Run> (not <AUni>)
    """
    from xml.etree import ElementTree as ET

    total = len(wf_glosses)
    n_wf  = n_ana = n_gls = 0

    for i, (surface, parts) in enumerate(sorted(wf_glosses.items()), 1):
        if i % 2000 == 0 or i == total:
            print(f'  {i:,} / {total:,} wordforms...')
            log.info('  %d/%d', i, total)

        wf_guid   = str(uuid.uuid4()).lower()
        ana_guid  = str(uuid.uuid4()).lower()
        morph_guid = str(uuid.uuid4()).lower()

        # ── WfiWordform ──────────────────────────────────────────────────
        # No ownerguid — WfiWordform is a root-level object in FLEx.
        wf_rt = ET.SubElement(root, 'rt')
        wf_rt.set('class', 'WfiWordform')
        wf_rt.set('guid',  wf_guid)

        analyses_el = ET.SubElement(wf_rt, 'Analyses')
        ref = ET.SubElement(analyses_el, 'objsur')
        ref.set('guid', ana_guid); ref.set('t', 'o')

        ET.SubElement(wf_rt, 'Checksum').set('val', '0')

        form_el = ET.SubElement(wf_rt, 'Form')
        auni    = ET.SubElement(form_el, 'AUni')
        auni.set('ws', ws_grc)
        auni.text = surface

        ET.SubElement(wf_rt, 'SpellingStatus').set('val', '0')

        n_wf += 1

        # ── WfiAnalysis ──────────────────────────────────────────────────
        ana_rt = ET.SubElement(root, 'rt')
        ana_rt.set('class',     'WfiAnalysis')
        ana_rt.set('guid',      ana_guid)
        ana_rt.set('ownerguid', wf_guid)

        # MorphBundles — one bundle carrying the surface form
        morph_bundles_el = ET.SubElement(ana_rt, 'MorphBundles')
        ref = ET.SubElement(morph_bundles_el, 'objsur')
        ref.set('guid', morph_guid); ref.set('t', 'o')

        # Meanings (= WfiGloss objects)
        meanings_el = ET.SubElement(ana_rt, 'Meanings')
        n_ana += 1

        # ── WfiMorphBundle ───────────────────────────────────────────────
        morph_rt = ET.SubElement(root, 'rt')
        morph_rt.set('class',     'WfiMorphBundle')
        morph_rt.set('guid',      morph_guid)
        morph_rt.set('ownerguid', ana_guid)

        mb_form = ET.SubElement(morph_rt, 'Form')
        astr    = ET.SubElement(mb_form, 'AStr')
        astr.set('ws', ws_grc)
        run     = ET.SubElement(astr, 'Run')
        run.set('ws', ws_grc)
        run.text = surface

        # ── WfiGloss (one per gloss part) ────────────────────────────────
        for part in parts:
            gls_guid = str(uuid.uuid4()).lower()

            ref = ET.SubElement(meanings_el, 'objsur')
            ref.set('guid', gls_guid); ref.set('t', 'o')

            gls_rt = ET.SubElement(root, 'rt')
            gls_rt.set('class',     'WfiGloss')
            gls_rt.set('guid',      gls_guid)
            gls_rt.set('ownerguid', ana_guid)

            form_el = ET.SubElement(gls_rt, 'Form')
            auni    = ET.SubElement(form_el, 'AUni')
            auni.set('ws', ws_en)
            auni.text = part

            n_gls += 1

    log.info('XML written: wf=%d  ana=%d  gls=%d', n_wf, n_ana, n_gls)
    return n_wf, n_ana, n_gls

def _save_fwdata(tree, fwdata_path):
    bak_path = fwdata_path + '.bak'
    if not os.path.isfile(bak_path):
        shutil.copy2(fwdata_path, bak_path)
        log.info('Backup: %s', bak_path)
    from xml.etree import ElementTree as ET
    try:
        ET.indent(tree.getroot(), space='  ')   # Python 3.9+
    except AttributeError:
        pass   # Python < 3.9 — skip indenting, still valid XML
    tree.write(fwdata_path, encoding='utf-8', xml_declaration=True)
    log.info('Saved: %s', fwdata_path)

def populate_fwdata(fwdata_path, glosses_path, test_mode=False):
    if test_mode:
        # Single hardcoded test entry — no JSON file needed
        wf_glosses = {'λόγος': ['message', 'word']}
        print(f"TEST MODE: writing only 'λόγος' → {wf_glosses['λόγος']}")
        log.info('Test mode: %s', wf_glosses)
    else:
        # Load gloss JSON
        if not glosses_path or not os.path.isfile(glosses_path):
            # Fall back to auto-build from data files
            print('wordform_glosses.json not found — building from NT data...')
            build_gloss_json(DEFAULT_JSON)
            glosses_path = DEFAULT_JSON

        print(f'Loading glosses from: {glosses_path}')
        with open(glosses_path, encoding='utf-8') as f:
            wf_glosses = json.load(f)
        log.info('Loaded %d entries from %s', len(wf_glosses), glosses_path)

    n_wf  = len(wf_glosses)
    n_gls = sum(len(v) for v in wf_glosses.values())
    print(f'{n_wf:,} surface forms  {n_gls:,} total gloss choices')

    print('Parsing .fwdata XML...')
    tree, root = _parse_fwdata(fwdata_path)

    existing = sum(
        len(root.findall(f'rt[@class="{cls}"]'))
        for cls in ('WfiWordform', 'WfiAnalysis', 'WfiGloss')
    )
    log.info('Existing Wfi* elements: %d', existing)

    # Confirm
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        ok = messagebox.askyesno(
            'Populate NT Wordforms (XML)',
            f'Write {n_wf:,} wordforms and {n_gls:,} gloss choices to:\n'
            f'{fwdata_path}\n\n'
            f'(Removes {existing:,} existing Wfi* objects first.\n'
            f'A .bak backup will be kept alongside.)\n\n'
            f'FLEx must be closed.  Continue?'
        )
        r.destroy()
    except Exception:
        ans = input(f'Write {n_wf:,} wordforms to {fwdata_path}? [y/N] ').strip().lower()
        ok  = (ans == 'y')

    if not ok:
        print('Cancelled.')
        return

    if existing:
        print(f'Removing {existing:,} existing Wfi* elements...')
        _remove_existing_wordforms(root)

    lp_guid = _get_langproject_guid(root)
    log.info('LangProject guid: %s', lp_guid)

    print('Writing to XML...')
    n_wf_done, n_ana_done, n_gls_done = _add_wordforms_to_xml(root, wf_glosses, lp_guid)

    print('Saving .fwdata...')
    _save_fwdata(tree, fwdata_path)

    print()
    print('Done.')
    print(f'  {n_wf_done:,} WfiWordform objects')
    print(f'  {n_ana_done:,} WfiAnalysis objects')
    print(f'  {n_gls_done:,} WfiGloss objects with gloss text')
    print()
    print('Next steps:')
    print('  1. Open FLEx and verify wordforms and glosses look correct.')
    print('  2. File → Project Management → Back Up This Project')
    print('     to save as the new template .fwbackup.')
    print(f'\nLog: {LOG_PATH}')

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print(f'Log: {LOG_PATH}')
    log.info('=' * 70)
    log.info('Populate NT Wordforms XML  Python %s', sys.version)

    parser = argparse.ArgumentParser(
        description='Populate NT Greek wordform analyses directly in a FLEx .fwdata XML file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  # Step 1 — build master gloss JSON (inspect before writing)\n'
            '  python Populate_NT_Wordforms_XML.py --build-json\n\n'
            '  # Step 2 — write to .fwdata (FLEx must be closed)\n'
            '  python Populate_NT_Wordforms_XML.py "C:\\...\\NT Greek.fwdata"\n\n'
            '  # Quick test — adds only \\u03b5\\u1f30 to verify XML approach works\n'
            '  python Populate_NT_Wordforms_XML.py "C:\\...\\NT Greek.fwdata" --test\n'
        )
    )
    parser.add_argument('fwdata', nargs='?', help='Path to .fwdata file')
    parser.add_argument('--build-json', action='store_true',
                        help='Build wordform_glosses.json and exit (Step 1)')
    parser.add_argument('--glosses', default=DEFAULT_JSON,
                        help=f'Path to wordform_glosses.json (default: {DEFAULT_JSON})')
    parser.add_argument('--test', action='store_true',
                        help='Test mode: write only \\u03b5\\u1f30 (\\u1f10\\u03bd) as a single entry')
    args = parser.parse_args()

    if args.build_json:
        build_gloss_json(DEFAULT_JSON)
        return

    # Need a .fwdata path for populate mode
    fwdata_path = args.fwdata
    if not fwdata_path:
        fwdata_path = _pick_file(
            'Select the NT Greek FLEx project (.fwdata)',
            [('FLEx project', '*.fwdata'), ('All files', '*.*')]
        )
    if not fwdata_path or not os.path.isfile(fwdata_path):
        print('ERROR: No .fwdata file selected.')
        sys.exit(1)

    populate_fwdata(fwdata_path, args.glosses, test_mode=args.test)


if __name__ == '__main__':
    main()
