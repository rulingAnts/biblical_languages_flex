# biblical_languages_flex
This project's aim is to linguistic tools found in Fieldworks Language Explorer for exegesis and Bible study, especially through Discourse Analysis and especially in preparation for Bible Translation

For reference:

/your_project_folder
|-- app.py
|-- index.html
|-- /sword_repo
    |-- /mods.d
    |   |-- SBLGNT.conf
    |   |-- RobGNT.conf
    |   |-- StrongsGk.conf
    |   |-- ... (and potentially other SWORD config files)
    |-- /modules
        |-- /texts
            |-- SBLGNT.bbl
            |-- RobGNT.bbl
            |-- StrongsGk.dict
            |-- ... (and potentially other SWORD module files)

## Setup

1) Python dependencies

- Install Python 3.9+ and then install the Python packages:

```
pip3 install -r requirements.txt
```

2) Optional: SWORD (libsword) for dictionary lookups

- On macOS:

```
brew install sword
```

- A Python binding that exposes `from sword import Sword` is optional. If not present, the app will still run using `pysword` for MorphGNT text and a local JSON for Strong’s glosses. Place a mapping file at `data/strongs_greek.json` to enable English glosses.

## Running the app

```
python3 app.py
```

The app will try to use `python-sword` + libsword if available; otherwise it falls back to `pysword` for text and a JSON file for glosses.

Supports references:
- Single verse: `John 1:1`
- Intra-chapter range: `John 1:1-18`
- Cross-chapter range (same book): `John 1:1-5:14`

Enter the reference in the input box and click “Load Data,” then generate the `.flextext` file. For ranges, each verse becomes a separate phrase in the FlexText output.

## Strong's glosses (JSON fallback)

The app will look for a JSON file at:

- `data/strongs_greek.json` (preferred)
- or `data/strongs_greek.sample.json` (included demo)

Format:

```
{
    "3056": "word, message, statement, matter",
    "2316": "God, deity, divine being"
}
```

You can generate this file from an open dataset using the helper script:

```
python3 tools/strongs_to_json.py \
    --input path/to/strongs_greek.csv \
    --output data/strongs_greek.json \
    --num-field id --gloss-field gloss
```

Supported inputs:
- CSV or TSV (use `--tsv` if tab-delimited). If no header, add `--no-header`.
- JSON mapping (key -> gloss) or a JSON array of objects (`--num-field/--gloss-field` can help map keys).

Numbers may be given as `G3056` or `3056`; they are normalized to digits only in output keys.

### Using STEPBible TBESG (recommended open source)

If you have the Tyndale Brief lexicon of Extended Strong’s for Greek (TBESG) from STEPBible (CC BY 4.0), you can convert it directly:

1) Place the TBESG TSV/text file in the project root (or note its path). It usually has a header like:

```
EStrong#\tGreek\tTransliteration\tGloss\tMorph\tMeaning
```

2) Run the converter (it auto-detects header and column order variants):

```
python3 tools/strongs_to_json.py \
    --input "TBESG.-.Tyndale.Brief.lexicon.of.Extended.Strongs.for.Greek.-.CC.BY.txt" \
    --output data/strongs_greek.json \
    --tsv
```

This produces `data/strongs_greek.json` with English glosses (e.g., 746 → "beginning", 3056 → "word").

Attribution (required by CC BY 4.0): If you use TBESG in your app or outputs, please include a note such as:

> Strong’s glosses derived from TBESG – Tyndale Brief lexicon of Extended Strong’s for Greek. Data created for www.STEPBible.org by Tyndale House Cambridge and others (CC BY 4.0).

You can find STEPBible datasets and license information at https://github.com/tyndale/STEPBible-Data.

## Packaging (optional)

The included `bundle.sh` shows an example `pyinstaller` command. Update the `--add-data` paths for your environment. The app includes logic to find bundled resources at runtime.

## Notes

- The repository contains `sword_repo/` with module configs and data for MorphGNT and Strong’s. The `.conf` files are adjusted to match the included folder layout.
- If you later install a Python binding to libsword (exposing `from sword import Sword`), the app will automatically prefer it for Strong’s lexicon lookups.
