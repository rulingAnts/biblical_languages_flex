#!/usr/bin/env python3
"""
Convert an open Strong's dataset into the JSON format expected by this app.

Input formats supported:
- CSV/TSV with two columns: strongs_number, gloss (header row optional)
- JSON mapping of strongs_number -> gloss
- JSON array of objects (keys auto-detected or supplied via CLI)

Output:
- JSON file mapping digits-only Strong's number (e.g., "3056") to a short English gloss

Examples:
  # CSV with headers: id, gloss
  python tools/strongs_to_json.py \
      --input path/to/strongs_greek.csv \
      --output data/strongs_greek.json \
      --num-field id --gloss-field gloss

  # TSV with no headers
  python tools/strongs_to_json.py --input path/to/strongs_greek.tsv --output data/strongs_greek.json --tsv

  # JSON mapping already
  python tools/strongs_to_json.py --input path/to/strongs_greek.json --output data/strongs_greek.json

Notes:
- Strong's numbers may be provided as "G3056", "3056", or with leading zeros. They will be normalized to digits only: "3056".
- If multiple glosses exist, pick a concise summary (first phrase) before punctuation like ';' or '\n'.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
from typing import Dict, Any, Iterable


def normalize_strongs(num: str) -> str:
    s = (num or '').strip()
    s = re.sub(r'^[Gg]\s*0*', '', s)  # strip leading G/g and zeros
    s = re.sub(r'\D', '', s)  # keep digits only
    return s


def normalize_gloss(text: str) -> str:
    if text is None:
        return ''
    t = str(text).strip()
    # Take a concise first segment before semicolon or newline
    t = re.split(r'[;\n\r]+', t)[0].strip()
    return t


def load_from_csv(path: str, has_header: bool, delimiter: str, num_field: str = None, gloss_field: str = None) -> Dict[str, str]:
    out = {}
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    # If header is expected but the file has a preamble, find the real header line
    start_idx = 0
    if has_header:
        def looks_like_header(cols):
            cols_lower = [c.strip().lower() for c in cols]
            candidates_num = [num_field, 'estrong#', 'strong', 'strongs', 'id', 'num', 'key']
            candidates_gls = [gloss_field, 'gloss', 'definition', 'def', 'short', 'english']
            found_num = any(c and c.lower() in cols_lower for c in candidates_num)
            found_gls = any(c and c.lower() in cols_lower for c in candidates_gls)
            return found_num and found_gls

        for i, ln in enumerate(lines):
            cols = [c for c in ln.split(delimiter)]
            if len(cols) >= 2 and looks_like_header(cols):
                start_idx = i
                break
        else:
            # Fallback: find first data row starting with G-digits
            for i, ln in enumerate(lines):
                if ln and ln[0] in ('G', 'g'):
                    start_idx = i
                    has_header = False
                    break

    # Build a reader from the detected start
    buf = io.StringIO("\n".join(lines[start_idx:]) + "\n")
    rdr = csv.reader(buf, delimiter=delimiter)

    if has_header:
        header = next(rdr)
        header_lower = [h.strip().lower() for h in header]

        def idx_of(name_opts: Iterable[str]) -> int:
            for name in name_opts:
                if name and name.lower() in header_lower:
                    return header_lower.index(name.lower())
            return -1

        ni = idx_of([num_field, 'estrong#', 'strong', 'strongs', 'id', 'num', 'key'])
        gi = idx_of([gloss_field, 'gloss', 'definition', 'def', 'short', 'english'])
        greek_i = idx_of(['greek'])
        translit_i = idx_of(['transliteration', 'translit'])
        if ni < 0 or gi < 0:
            raise ValueError(f"Could not detect num/gloss columns. Header: {header}")
        # Heuristic: some STEPBible files label columns 'Greek, Transliteration, Gloss' but actual data order is 'Gloss, Greek, Transliteration'.
        # Probe the next ~100 rows to see which column looks most like an English gloss.
        sample_rows = []
        for _ in range(100):
            try:
                row = next(rdr)
            except StopIteration:
                break
            sample_rows.append(row)
        # Rewind reader for actual processing
        buf2 = io.StringIO("\n".join([delimiter.join(header)] + [delimiter.join(r) for r in sample_rows] + list(buf.readlines())))
        rdr = csv.reader(buf2, delimiter=delimiter)
        next(rdr)  # skip header

        def is_greek_text(s: str) -> bool:
            return any('\u0370' <= ch <= '\u03FF' for ch in s)

        def looks_like_gloss(s: str) -> bool:
            if not s:
                return False
            if is_greek_text(s):
                return False
            if re.search(r'[A-Za-z]', s) is None:
                return False
            # Allow spaces and punctuation; discourage colon patterns typical of morph tags
            if ':' in s and re.match(r'^[A-Za-z]+[:\-]', s):
                return False
            return True

        # First: check if the header-labelled 'Greek' column actually contains Greek.
        def frac_has_greek(col_idx: int) -> float:
            if col_idx is None or col_idx < 0:
                return 0.0
            tot = 0
            hit = 0
            for row in sample_rows:
                if len(row) <= col_idx:
                    continue
                tot += 1
                if is_greek_text((row[col_idx] or '')):
                    hit += 1
            return (hit / tot) if tot else 0.0

        greek_frac = frac_has_greek(greek_i)
        gloss_header_frac = frac_has_greek(gi)

        # If the 'Greek' column rarely has Greek text but the 'Gloss' header column never has Greek,
        # assume the file's actual order is 'Gloss, Greek, Transliteration' and pick the header 'Greek' position as gloss.
        if greek_i >= 0 and gi >= 0:
            if greek_frac < 0.3 and gloss_header_frac < 0.1:
                gi = greek_i
        
        # Otherwise, fall back to content-based scoring between candidates
        candidates = [c for c in [gi, greek_i, translit_i] if c >= 0]
        def score_col(c: int) -> int:
            score = 0
            for row in sample_rows:
                if len(row) <= c:
                    continue
                s = (row[c] or '').strip()
                if not s:
                    continue
                # English-like tokens
                if looks_like_gloss(s):
                    score += 1
                # Prefer phrases with spaces/hyphens (more likely English gloss than transliteration)
                if ' ' in s or '-' in s:
                    score += 1
                # Penalize macrons/diacritics that suggest transliteration (āēīōū ḗ ṓ etc.)
                if re.search(r'[ĀāĒēĪīŌōŪūḗḕḖḕȳȲ]', s):
                    score -= 1
            return score

        if candidates:
            scores = {c: score_col(c) for c in candidates}
            gi = max(scores, key=lambda k: scores[k])
        for row in rdr:
            if not row:
                continue
            # skip separator or comment lines
            first = (row[0] or '').strip()
            if not first or first.startswith('=') or first.startswith('-'):
                continue
            if len(row) <= max(ni, gi):
                continue
            num = normalize_strongs(row[ni])
            gloss = normalize_gloss(row[gi])
            if num:
                out[num] = gloss
    else:
        for row in rdr:
            if not row:
                continue
            if len(row) < 2:
                continue
            num = normalize_strongs(row[0])
            gloss = normalize_gloss(row[1])
            if num:
                out[num] = gloss
    return out


def load_from_json(path: str, num_field: str = None, gloss_field: str = None) -> Dict[str, str]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    out: Dict[str, str] = {}
    if isinstance(data, dict):
        # mapping already
        for k, v in data.items():
            num = normalize_strongs(str(k))
            gloss = normalize_gloss(v)
            if num:
                out[num] = gloss
    elif isinstance(data, list):
        # array of objects
        for obj in data:
            if not isinstance(obj, dict):
                continue
            # try explicit keys first
            keys_num = [num_field, 'strong', 'strongs', 'id', 'num', 'key']
            keys_gls = [gloss_field, 'gloss', 'definition', 'def', 'short', 'english']
            num_val = None
            gls_val = None
            for k in keys_num:
                if k and k in obj:
                    num_val = obj[k]
                    break
            for k in keys_gls:
                if k and k in obj:
                    gls_val = obj[k]
                    break
            if num_val is None or gls_val is None:
                # try to detect fields heuristically
                for k, v in obj.items():
                    if num_val is None and isinstance(v, (str, int)) and re.match(r'^[Gg]?\d+$', str(v)):
                        num_val = v
                    if gls_val is None and isinstance(v, str) and len(v) > 0:
                        gls_val = v
            num = normalize_strongs(str(num_val) if num_val is not None else '')
            gloss = normalize_gloss(gls_val)
            if num:
                out[num] = gloss
    else:
        raise ValueError('Unsupported JSON structure')
    return out


def main():
    ap = argparse.ArgumentParser(description="Convert Strong's datasets to app JSON format")
    ap.add_argument('--input', '-i', required=True, help='Path to input dataset (csv/tsv/json)')
    ap.add_argument('--output', '-o', required=True, help='Path to output JSON file')
    ap.add_argument('--no-header', action='store_true', help='CSV/TSV has no header row')
    ap.add_argument('--tsv', action='store_true', help='Input is TSV (tab-separated)')
    ap.add_argument('--num-field', help='Name of Strong\'s number column/key (e.g., strong, id)')
    ap.add_argument('--gloss-field', help='Name of gloss column/key (e.g., gloss, definition)')
    args = ap.parse_args()

    in_path = args.input
    out_path = args.output

    if not os.path.exists(in_path):
        print(f"ERROR: Input file not found: {in_path}")
        sys.exit(1)

    ext = os.path.splitext(in_path)[1].lower()
    if ext in ('.csv', '.tsv') or args.tsv:
        delimiter = '\t' if (ext == '.tsv' or args.tsv) else ','
        data = load_from_csv(in_path, has_header=(not args.no_header), delimiter=delimiter,
                             num_field=args.num_field, gloss_field=args.gloss_field)
    elif ext == '.json':
        data = load_from_json(in_path, num_field=args.num_field, gloss_field=args.gloss_field)
    else:
        print('ERROR: Unsupported input extension. Use .csv, .tsv, or .json')
        sys.exit(1)

    # Write out JSON
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(data)} entries to {out_path}")


if __name__ == '__main__':
    main()
