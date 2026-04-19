# Biblical Languages for FLEx

Tools for preparing New Testament Greek interlinear texts in [FieldWorks Language Explorer (FLEx)](https://software.sil.org/fieldworks/) for discourse analysis and Bible study.

**Live web app:** [rulingants.github.io/biblical_languages_flex](https://rulingants.github.io/biblical_languages_flex/)

---

## What this is

A two-part workflow for getting NT Greek interlinear texts into FLEx with pre-populated morphological analysis and gloss options:

1. **Web app** — select a passage, generate a `.flextext` file, import it into FLEx. Works in any modern browser, offline-capable. No installation required.
2. **FLEx project template** — a pre-configured FLEx project with all 21,397 NT Greek surface forms pre-loaded with gloss options, so imported texts are immediately ready for analysis.

The generated `.flextext` links each word token to its pre-populated analysis in the template project:
- Single-gloss words → **approved (green)** immediately
- Multi-gloss words → **candidate glosses (blue)** — user selects the right sense in context
- The free translation (LEB) appears as the segment-level English

---

## Roadmap

### Now available
- **Web app** — passage selection, `.flextext` download, offline support
- **FLEx project template** — 21,397 wordforms with pre-populated analyses and gloss options
- **Split Slash Glosses FLExTools module** — splits slash-separated glosses into individual candidates

### Coming soon — Standalone desktop app (Windows)
The web app currently requires a manual import step: generate the `.flextext`, then go into FLEx and run File → Import. A standalone Windows app is in development that will eliminate this step:

- Pick your FLEx project, select a passage, click **Import** — done
- The app uses FLEx's own LCM library directly, so the text is created inside FLEx in one click with no `.flextext` file to manage
- Requires FLEx to be installed; everything else is bundled

The standalone app uses the same pre-populated template project and produces the same analysis links — it is just a more seamless delivery mechanism.

---

## Quick start

1. [Download and install FLEx](https://software.sil.org/fieldworks/) (Windows only)
2. Download the [NT Greek blank project template](https://rulingants.github.io/biblical_languages_flex/assets/NT%20Greek%20blank%20project.fwbackup) and restore it in FLEx (File → Project Management → Restore a Project)
3. Open the [web app](https://rulingants.github.io/biblical_languages_flex/), select a book and passage, click **Generate .flextext**
4. In FLEx: File → Import → FLEx Interlinear Text → select the downloaded file
5. The passage appears in Texts & Words with Greek text, free translation, and gloss options ready

> **Template compatibility:** The word-analysis links in the generated `.flextext` only connect to pre-populated analyses in projects created from the NT Greek blank project template **dated 2026-04-19 or later**. Importing into any other project still creates a readable interlinear text, but words will be unlinked.

---

## Repository layout

```
docs/                          GitHub Pages web app
  index.html                   Web UI (passage picker, .flextext generator)
  assets/
    data/                      Pre-built per-book JSON (27 NT books)
      Acts.json, John.json …
      guid_map.json            Surface form → WfiGloss/WfiAnalysis GUID map
    NT Greek blank project v1.fwbackup   FLEx template (pre-populated wordforms)

tools/
  Import_NT_Text.py            FLExTools module — imports NT books via LCM (dev/testing)
  Populate_NT_Wordforms_XML.py Developer tool — populated the template wordforms
  Split_Slash_Glosses.py       FLExTools module — splits slash-separated glosses
  extract_guid_map.py          Developer tool — regenerates guid_map.json from template

standalone/                    Standalone desktop app (in development)
  main.py                      pywebview entry point
  core/
    importer.py                LCM-based text import
    flextext_generator.py      .flextext generator (shared with web app logic)
    flex_project.py            Lightweight LCM project wrapper
```

---

## Updating the template

If the template `.fwbackup` is updated (new wordforms added, glosses changed), regenerate `guid_map.json`:

```
python3 tools/extract_guid_map.py
```

Then commit the updated `docs/assets/data/guid_map.json`. The web app will pick it up automatically.

> **Backward compatibility:** The template was first shipped 2026-04-19. All future updates must be additive — new wordforms can be added, but existing GUIDs must never change, as users may already have imported texts that reference them.

---

## Attributions

- **Greek text and morphology:** MorphGNT lemmatization and parsing by James Tauber (CC BY-SA). Base text: SBLGNT © 2010 Logos Bible Software and the Society of Biblical Literature.
- **Strong's glosses:** TBESG – Tyndale Brief lexicon of Extended Strong's for Greek, from www.STEPBible.org by Tyndale House Cambridge and others (CC BY 4.0).
- **English translation:** Lexham English Bible (LEB) © Logos Bible Software. Used under the LEB license: http://www.lexhamenglishbible.com/license/
- **LCM wrapper:** Derived from [FLExTools](https://github.com/rmlockwood/FLExTools) by Richard Louw (LGPL-3.0).
