#!/usr/bin/env python3
"""
Export per-book JSON for the browser-only app under docs/assets/data/.

This script reuses the existing SWORD parsing in app.py to extract:
- words: list of { g: Greek word, S: Strong's (e.g., G3056), gls: English gloss, l: lemma }
- translation: phrase-level English (LEB if available; else empty)

Usage examples:
  python3 tools/export_web_data.py --books John
  python3 tools/export_web_data.py --books John,Mark,Matthew

Outputs files like: docs/assets/data/John.json
"""
import os
import sys
import json
import argparse

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as desktop_app  # reuse load_sword_modules, fetch_sword_data, get_phrase_translation


def export_book(book: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{book}.json")
    result = {}

    # Simple discovery: iterate chapters starting at 1, verses from 1, stop when a chapter starts with 3 consecutive empty verses
    # This is resilient across modules without a chapter/verse manifest.
    consecutive_empty_chapters = 0
    chapter = 1
    while True:
        empty_verses_in_row = 0
        any_verse_in_chapter = False
        verse = 1
        while True:
            try:
                vdata = desktop_app.fetch_sword_data(book, chapter, verse)
            except Exception:
                vdata = None
            if not vdata or not vdata.words:
                empty_verses_in_row += 1
                # Heuristic: 3 empty verses in a row means chapter likely ended
                if empty_verses_in_row >= 3:
                    break
            else:
                empty_verses_in_row = 0
                any_verse_in_chapter = True
                # Build verse payload
                words = []
                for w in vdata.words:
                    wd = w.to_dict()
                    words.append({
                        'g': wd.get('greek_word', ''),
                        'S': wd.get('strongs_number', ''),
                        'gls': wd.get('en_gloss', ''),
                        'l': wd.get('lemma', ''),
                    })
                tr = desktop_app.get_phrase_translation(book, chapter, verse) or ''
                key = f"{chapter}:{verse}"
                result[key] = {
                    'words': words,
                    'translation': tr,
                }
            verse += 1

        if any_verse_in_chapter:
            consecutive_empty_chapters = 0
        else:
            consecutive_empty_chapters += 1

        # Stop after two fully empty chapters in a row (end of book)
        if consecutive_empty_chapters >= 2:
            break
        chapter += 1

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Export per-book JSON for web app")
    parser.add_argument('--books', type=str, required=True, help='Comma-separated list of NT books, e.g., John,Mark,Matthew')
    parser.add_argument('--out', type=str, default=os.path.join(ROOT, 'docs', 'assets', 'data'))
    args = parser.parse_args()

    # Initialize SWORD modules once
    desktop_app.load_sword_modules()

    books = [b.strip() for b in args.books.split(',') if b.strip()]
    produced = []
    for b in books:
        print(f"Exporting {b}…")
        path = export_book(b, args.out)
        produced.append(path)
        print(f"  -> {path}")

    print("Done. Files written:")
    for p in produced:
        print(" -", p)


if __name__ == '__main__':
    main()
