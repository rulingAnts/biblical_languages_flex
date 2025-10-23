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

# Candidate module book name variants to handle SWORD/OSIS naming differences
BOOK_NAME_VARIANTS = {
    'Matthew': ['Matthew', 'Matt', 'Mt'],
    'Mark': ['Mark', 'Mk', 'Mrk'],
    'Luke': ['Luke', 'Luk', 'Lk'],
    'John': ['John', 'Jn', 'Jhn'],
    'Acts': ['Acts', 'Act'],
    'Romans': ['Romans', 'Rom', 'Ro'],
    '1Corinthians': ['1Corinthians', '1 Corinthians', '1Cor', '1Co'],
    '2Corinthians': ['2Corinthians', '2 Corinthians', '2Cor', '2Co'],
    'Galatians': ['Galatians', 'Gal'],
    'Ephesians': ['Ephesians', 'Eph'],
    'Philippians': ['Philippians', 'Phil', 'Php'],
    'Colossians': ['Colossians', 'Col'],
    '1Thessalonians': ['1Thessalonians', '1 Thessalonians', '1Thess', '1Th', '1Thes'],
    '2Thessalonians': ['2Thessalonians', '2 Thessalonians', '2Thess', '2Th', '2Thes'],
    '1Timothy': ['1Timothy', '1 Timothy', '1Tim', '1Ti'],
    '2Timothy': ['2Timothy', '2 Timothy', '2Tim', '2Ti'],
    'Titus': ['Titus', 'Tit'],
    'Philemon': ['Philemon', 'Phm', 'Phile'],
    'Hebrews': ['Hebrews', 'Heb'],
    'James': ['James', 'Jas'],
    '1Peter': ['1Peter', '1 Peter', '1Pet', '1Pe', '1Pt'],
    '2Peter': ['2Peter', '2 Peter', '2Pet', '2Pe', '2Pt'],
    '1John': ['1John', '1 John', '1Jn', '1Jhn'],
    '2John': ['2John', '2 John', '2Jn', '2Jhn'],
    '3John': ['3John', '3 John', '3Jn', '3Jhn'],
    'Jude': ['Jude', 'Jud'],
    'Revelation': ['Revelation', 'Rev', 'Apocalypse'],
}

def resolve_module_book_name(preferred_book: str) -> str:
    variants = BOOK_NAME_VARIANTS.get(preferred_book, [preferred_book])
    for name in variants:
        try:
            vdata = desktop_app.fetch_sword_data(name, 1, 1)
            if vdata and vdata.words:
                return name
        except Exception:
            continue
    # Last resort: return the preferred name
    return preferred_book


def export_book(book: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{book}.json")
    result = {}

    module_book = resolve_module_book_name(book)
    if module_book != book:
        print(f"  Using module book name '{module_book}' for '{book}'")

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
                vdata = desktop_app.fetch_sword_data(module_book, chapter, verse)
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
                tr = desktop_app.get_phrase_translation(module_book, chapter, verse) or ''
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
