#!/usr/bin/env python3
"""
extract_guid_map.py — One-time developer tool
==============================================
Reads the pre-populated template (.fwbackup or .fwdata) and writes
guid_map.json to docs/assets/data/.

guid_map.json maps each Greek surface form to the GUID of the best
IAnalysis object to use in a .flextext import:

  Single WfiGloss   → WfiGloss GUID    (FLEx shows as approved/green)
  Multiple WfiGloss → WfiAnalysis GUID (FLEx shows as candidate/blue)
  No analyses       → WfiWordform GUID (FLEx shows as unanalysed/red)

Run this once whenever the template is updated, then commit the output.

Usage:
  python extract_guid_map.py
  python extract_guid_map.py --fwdata "C:/path/to/project.fwdata"
  python extract_guid_map.py --fwbackup "C:/path/to/project.fwbackup"
"""

import argparse
import json
import os
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))

DEFAULT_BACKUP = os.path.join(
    REPO_ROOT, 'docs', 'assets', 'NT Greek blank project v1.fwbackup'
)
DEFAULT_OUT = os.path.join(REPO_ROOT, 'docs', 'assets', 'data', 'guid_map.json')


# ---------------------------------------------------------------------------
# Parse fwdata XML → guid_map
# ---------------------------------------------------------------------------

def build_guid_map(fwdata_bytes: bytes) -> dict:
    """
    Parse raw .fwdata XML and return:
        { NFC_surface_form: {"guid": "...", "type": "WfiGloss|WfiAnalysis|WfiWordform", "gls": "..."} }
    """
    print('Parsing fwdata XML…')
    root = ET.fromstring(fwdata_bytes)

    wf_index  = {}   # wf_guid  -> {surface, ana_guids: []}
    ana_index = {}   # ana_guid -> {owner_guid, gloss_guids: []}
    gls_index = {}   # gls_guid -> gloss_text

    for elem in root.findall('rt'):
        cls = elem.get('class')

        if cls == 'WfiWordform':
            form_el      = elem.find('.//AUni[@ws="grc"]')
            analyses_el  = elem.find('Analyses')
            if form_el is None or not form_el.text:
                continue
            surface    = unicodedata.normalize('NFC', form_el.text)
            ana_guids  = [
                o.get('guid')
                for o in (analyses_el.findall('objsur') if analyses_el is not None else [])
            ]
            wf_index[elem.get('guid')] = {
                'surface':   surface,
                'ana_guids': ana_guids,
            }

        elif cls == 'WfiAnalysis':
            meanings_el  = elem.find('Meanings')
            gloss_guids  = [
                o.get('guid')
                for o in (meanings_el.findall('objsur') if meanings_el is not None else [])
            ]
            ana_index[elem.get('guid')] = {
                'owner_guid':  elem.get('ownerguid'),
                'gloss_guids': gloss_guids,
            }

        elif cls == 'WfiGloss':
            auni = elem.find('.//AUni[@ws="en"]')
            gls_index[elem.get('guid')] = (auni.text or '') if auni is not None else ''

    print(f'  {len(wf_index):,} WfiWordform  '
          f'{len(ana_index):,} WfiAnalysis  '
          f'{len(gls_index):,} WfiGloss')

    # Build the map
    guid_map = {}
    n_gloss = n_analysis = n_wordform = n_skip = 0

    for wf_guid, wf in wf_index.items():
        surface   = wf['surface']
        ana_guids = wf['ana_guids']

        if not ana_guids:
            # No analysis — point to WfiWordform (red/unanalysed in FLEx)
            guid_map[surface] = {'guid': wf_guid, 'type': 'WfiWordform', 'gls': ''}
            n_wordform += 1
            continue

        ana_guid    = ana_guids[0]
        ana         = ana_index.get(ana_guid)
        if ana is None:
            n_skip += 1
            continue

        gloss_guids = ana['gloss_guids']

        if len(gloss_guids) == 1:
            # Single gloss — point to WfiGloss (approved/green)
            gls_guid  = gloss_guids[0]
            gls_text  = gls_index.get(gls_guid, '')
            guid_map[surface] = {
                'guid': gls_guid,
                'type': 'WfiGloss',
                'gls':  gls_text,
            }
            n_gloss += 1
        else:
            # Multiple glosses — point to WfiAnalysis (candidate/blue)
            # Use the first gloss text as display hint
            first_gls = gls_index.get(gloss_guids[0], '') if gloss_guids else ''
            guid_map[surface] = {
                'guid': ana_guid,
                'type': 'WfiAnalysis',
                'gls':  first_gls,
            }
            n_analysis += 1

    print(f'  guid_map: {n_gloss:,} WfiGloss  '
          f'{n_analysis:,} WfiAnalysis  '
          f'{n_wordform:,} WfiWordform  '
          f'({n_skip} skipped)')
    return guid_map


# ---------------------------------------------------------------------------
# Load fwdata bytes from .fwdata file or .fwbackup zip
# ---------------------------------------------------------------------------

def load_fwdata_bytes(path: str) -> bytes:
    if path.endswith('.fwbackup'):
        print(f'Opening .fwbackup: {path}')
        with zipfile.ZipFile(path) as z:
            fwdata_names = [n for n in z.namelist() if n.endswith('.fwdata')]
            if not fwdata_names:
                raise ValueError('No .fwdata found inside .fwbackup')
            print(f'  Reading {fwdata_names[0]}…')
            return z.read(fwdata_names[0])
    else:
        print(f'Reading .fwdata: {path}')
        with open(path, 'rb') as f:
            return f.read()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group()
    src.add_argument('--fwdata',   help='Path to .fwdata file')
    src.add_argument('--fwbackup', help='Path to .fwbackup file')
    parser.add_argument('--out', default=DEFAULT_OUT,
                        help=f'Output JSON path (default: {DEFAULT_OUT})')
    args = parser.parse_args()

    if args.fwdata:
        src_path = args.fwdata
    elif args.fwbackup:
        src_path = args.fwbackup
    elif os.path.isfile(DEFAULT_BACKUP):
        src_path = DEFAULT_BACKUP
        print(f'Using default backup: {src_path}')
    else:
        print('ERROR: No .fwdata or .fwbackup specified and default not found.')
        print(f'  Expected: {DEFAULT_BACKUP}')
        sys.exit(1)

    fwdata_bytes = load_fwdata_bytes(src_path)
    guid_map     = build_guid_map(fwdata_bytes)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(guid_map, f, ensure_ascii=False, indent=None, separators=(',', ':'))

    size_kb = os.path.getsize(args.out) / 1024
    print(f'\nWrote {len(guid_map):,} entries → {args.out}  ({size_kb:.0f} KB)')


if __name__ == '__main__':
    main()
