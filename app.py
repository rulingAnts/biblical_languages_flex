#!/usr/bin/env python3
import webview
import os
import re
import uuid
import json
import xml.etree.ElementTree as ET
import sys

# Backend selection: try python-sword first; if unavailable, fall back to pysword
BACKEND = None  # 'python-sword' | 'pysword'
SWORD_AVAILABLE = False
try:
    from sword import Sword  # python-sword binding for libsword
    SWORD_AVAILABLE = True
    BACKEND = 'python-sword'
except Exception:
    # Fall back to pysword for Bible text; will use local JSON for glosses
    try:
        from pysword.modules import SwordModules as PySwordModules
        BACKEND = 'pysword'
    except Exception:
        print("FATAL: Neither 'python-sword' nor 'pysword' is available. Please install one of them.")
        sys.exit(1)


# --- GLOBAL SWORD MODULES (Initialized at startup) ---
MORPHGNT_MODULE = None   # python-sword module handle OR pysword SwordBible
STRONGSGK_MODULE = None  # python-sword lexicon module handle
TRANSLATION_MODULES = {}  # id -> module handle
SELECTED_TRANSLATION_ID = None  # currently selected translation id
GNT_MODULE_ID = "MorphGNT"
# Match your config header: mods.d/StrongsGk.conf defines [StrongsGreek]
GLOSS_MODULE_ID = "StrongsGreek"
TRANSLATION_MODULE_IDS = ["LEB"]  # Only LEB supported

# Optional local Strong's JSON (public domain) fallback
LOCAL_STRONGS = None  # dict like {"3056": "word, message"}


# --- 1. Data Structure Classes (Unchanged) ---

class InterlinearWord:
    """Holds all extracted interlinear data for a single Greek word."""
    def __init__(self, greek_word, lemma, morphology, strongs_number, en_gloss, tr_transliteration=None):
        self.greek_word = greek_word
        self.lemma = lemma
        self.morphology = morphology
        self.strongs_number = strongs_number
        self.en_gloss = en_gloss
        self.tr_transliteration = tr_transliteration if tr_transliteration else ""

    def to_dict(self):
        """Converts the word data into a dictionary for JSON serialization (for the HTML frontend)."""
        return {
            'greek_word': self.greek_word,
            'lemma': self.lemma,
            'morphology': self.morphology,
            'strongs_number': self.strongs_number,
            'en_gloss': self.en_gloss,
            'tr_transliteration': self.tr_transliteration
        }

class InterlinearVerse:
    """Holds all interlinear data for a single Bible verse."""
    def __init__(self, book, chapter, verse, free_translation="", literal_translation=""):
        self.book = book
        self.chapter = chapter
        self.verse = verse
        self.words = []
        self.free_translation = free_translation
        self.literal_translation = literal_translation

    def get_verse_ref(self):
        return f"{self.book} {self.chapter}:{self.verse}"

    def to_dict(self):
        return {
            'verse_ref': self.get_verse_ref(),
            'free_translation': self.free_translation,
            'literal_translation': self.literal_translation,
            'words': [word.to_dict() for word in self.words]
        }

    @classmethod
    def from_dict(cls, data):
        """Reconstructs the Python object from the JSON data sent by the frontend."""
        ref_parts = re.split(r'[ :]', data['verse_ref'])
        book, chapter, verse = ref_parts[0], int(ref_parts[1]), int(ref_parts[2])
        
        verse_obj = cls(book, chapter, verse, 
                            free_translation=data['free_translation'],
                            literal_translation=data['literal_translation'])
                        
        for word_data in data['words']:
            verse_obj.add_word(InterlinearWord(**word_data))
        return verse_obj
        
    def add_word(self, word_object):
        self.words.append(word_object)


# --- 2. SWORD Initialization and Data Extraction (UPDATED) ---

# --- CRITICAL: PyInstaller Path-Finding Logic ---
def find_repo_path(relative_path):
    """Determines the correct path to the bundled files in a PyInstaller executable."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    return os.path.join(base_path, relative_path)

def _try_load_local_strongs_json():
    """Load a local JSON Strong's Greek lexicon if present."""
    global LOCAL_STRONGS
    candidates = [
        find_repo_path(os.path.join('data', 'strongs_greek.json')),
        find_repo_path(os.path.join('data', 'strongs_greek.sample.json')),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Normalize keys to digits only (e.g., "3056")
                LOCAL_STRONGS = {str(k).lstrip('Gg'): v for k, v in data.items()}
                print(f"Loaded local Strong's lexicon from {p} with {len(LOCAL_STRONGS)} entries.")
                return
            except Exception as e:
                print(f"Warning: Failed to load local Strong's JSON at {p}: {e}")
    print("No local Strong's JSON found; glosses will use SWORD if available or fallback text.")


def load_sword_modules():
    """Initialize text and lexicon sources based on available backends."""
    global MORPHGNT_MODULE, STRONGSGK_MODULE, BACKEND, TRANSLATION_MODULES, SELECTED_TRANSLATION_ID

    SWORD_REPO_PATH = find_repo_path('sword_repo')

    if BACKEND == 'python-sword' and SWORD_AVAILABLE:
        try:
            manager = Sword(repository=SWORD_REPO_PATH)
            MORPHGNT_MODULE = manager.get_module(GNT_MODULE_ID)
            # Lexicon is optional—keep app running even if not found
            try:
                STRONGSGK_MODULE = manager.get_module(GLOSS_MODULE_ID)
            except Exception:
                STRONGSGK_MODULE = None
            # Optional English translations
            TRANSLATION_MODULES = {}
            SELECTED_TRANSLATION_ID = None
            for mid in TRANSLATION_MODULE_IDS:
                try:
                    mod = manager.get_module(mid)
                    if mod:
                        TRANSLATION_MODULES[mid] = mod
                        if not SELECTED_TRANSLATION_ID:
                            SELECTED_TRANSLATION_ID = mid
                        print(f"Detected translation module: {mid}")
                except Exception:
                    continue

            if not MORPHGNT_MODULE:
                raise ValueError(f"Module not found: {GNT_MODULE_ID}")

            print("python-sword backend loaded.")
        except Exception as e:
            print(f"python-sword failed: {e}. Falling back to pysword backend.")
            BACKEND = 'pysword'

    if BACKEND == 'pysword':
        try:
            mods = PySwordModules(paths=SWORD_REPO_PATH)
            mods.parse_modules()
            MORPHGNT_MODULE = mods.get_bible_from_module(GNT_MODULE_ID)
            # pysword does not provide lexicon access; rely on local JSON
            STRONGSGK_MODULE = None
            # Try to load optional English translations
            TRANSLATION_MODULES = {}
            SELECTED_TRANSLATION_ID = None
            for mid in TRANSLATION_MODULE_IDS:
                try:
                    tmod = mods.get_bible_from_module(mid)
                    if tmod:
                        TRANSLATION_MODULES[mid] = tmod
                        if not SELECTED_TRANSLATION_ID:
                            SELECTED_TRANSLATION_ID = mid
                        print(f"Detected translation module: {mid}")
                except Exception:
                    continue
            print("pysword backend loaded.")
        except Exception as e:
            print(f"FATAL: Could not initialize pysword backend: {e}")
            sys.exit(1)

    # Load local Strong's JSON fallback if present
    _try_load_local_strongs_json()


def get_strongs_gloss(strongs_number: str) -> str:
    """Retrieve an English gloss for a Strong's number.
    Priority: python-sword lexicon -> local JSON -> fallback string.
    """
    num = (strongs_number or '').strip()
    if not num:
        return ""

    key_digits = num.lstrip('Gg')

    # 1) Use python-sword lexicon if available
    if STRONGSGK_MODULE is not None and BACKEND == 'python-sword':
        try:
            gloss_entry = STRONGSGK_MODULE.get_entry(key_digits)
            cleaned_gloss = gloss_entry.split('\n')[0].strip()
            if cleaned_gloss:
                return cleaned_gloss
        except Exception:
            pass

    # 2) Local Strong's JSON fallback
    if LOCAL_STRONGS and key_digits in LOCAL_STRONGS:
        return LOCAL_STRONGS[key_digits]

    # 3) Final fallback
    return f"{num}"  # at least show the Strong's number


def fetch_sword_data(book: str, chapter: int, verse: int) -> InterlinearVerse:
    """Retrieve and parse interlinear data for a given verse from available backend."""
    if not MORPHGNT_MODULE:
        raise Exception("MorphGNT module not loaded.")

    verse_ref_str = f"{book} {chapter}:{verse}"

    try:
        if BACKEND == 'python-sword':
            raw_text_with_tags = MORPHGNT_MODULE.get_entry(verse_ref_str)
        else:
            # pysword path: get raw OSIS/GBF/ThML with tags intact
            raw_text_with_tags = MORPHGNT_MODULE.get(books=book, chapters=chapter, verses=verse, clean=False)

        verse_data = InterlinearVerse(book, chapter, verse)
    except Exception as e:
        raise Exception(f"SWORD Data Lookup Error for {verse_ref_str}: {e}")
            
    # Regex to find word tags and extract attributes (UNCHANGED)
    # The 'strong' attribute in MorphGNT typically contains the G-number (e.g., G3056)
    word_pattern = re.compile(
        r'<w(?:\s+lemma="(?P<lemma>[^"]*)")?'
        r'(?:\s+morph="(?P<morph>[^"]*)")?'
        r'>(?P<greek_word>[^<]+)</w>'
    )
    
    # Simple roman transliteration for demo purposes (UNCHANGED)
    def transliterate(greek):
        mapping = {'α':'a', 'β':'b', 'γ':'g', 'δ':'d', 'ε':'e', 'ζ':'z', 'η':'ē', 'θ':'th', 'ι':'i', 
                   'κ':'k', 'λ':'l', 'μ':'m', 'ν':'n', 'ξ':'x', 'ο':'o', 'π':'p', 'ρ':'r', 'σ':'s', 
                   'τ':'t', 'υ':'u', 'φ':'ph', 'χ':'ch', 'ψ':'ps', 'ω':'ō', 'ς':'s'}
        return ''.join(mapping.get(c.lower(), c) for c in greek)

    for match in word_pattern.finditer(raw_text_with_tags):
        data = match.groupdict()
        greek_word = (data.get('greek_word') or '').strip()

        lemma_attr = (data.get('lemma') or '').strip()
        morph_attr = (data.get('morph') or '').strip()

        # Extract Greek lemma (after 'lemma.Strong:') if present
        lemma_match = re.search(r'lemma\.Strong:([^\s]+)', lemma_attr)
        lemma_val = lemma_match.group(1) if lemma_match else ''

        # Extract Strong's number embedded in lemma attribute: strong:G0746 -> G746
        strong_match = re.search(r'strong: *G0*(\d+)', lemma_attr, flags=re.I)
        strongs = f"G{strong_match.group(1)}" if strong_match else ''
        
        # --- CRITICAL: Lookup Gloss using the Strongs number ---
        en_gloss = get_strongs_gloss(strongs)
        # --------------------------------------------------------

        word = InterlinearWord(
            greek_word=greek_word,
            lemma=lemma_val,
            morphology=morph_attr,
            strongs_number=strongs,
            en_gloss=en_gloss,
            tr_transliteration=transliterate(greek_word)
        )
        verse_data.add_word(word)

    # Note: Free and Literal translation fields remain blank unless you add another translation module
    return verse_data


def get_phrase_translation(book: str, chapter: int, verse: int) -> str:
    """Return an English translation for the verse if a translation module is available; else ''."""
    if not TRANSLATION_MODULES or not SELECTED_TRANSLATION_ID:
        return ''
    module = TRANSLATION_MODULES.get(SELECTED_TRANSLATION_ID)
    if not module:
        return ''
    ref = f"{book} {chapter}:{verse}"
    try:
        if BACKEND == 'python-sword':
            # python-sword may include markup; strip tags crudely
            text = module.get_entry(ref)
            # Remove simple tags
            text = re.sub(r"<[^>]+>", "", text)
            return text.strip()
        else:
            # pysword supports clean output
            return module.get(books=book, chapters=chapter, verses=verse, clean=True).strip()
    except Exception:
        return ''


# --- Range Parsing and Passage Fetching (NEW) ---

def parse_reference_range(ref: str):
    """Parse references like 'John 1:1', 'John 1:1-1:5', or 'John 1:1-5:14' (same book).
    Returns (book, (start_ch, start_vs), (end_ch, end_vs))
    """
    s = (ref or '').strip()
    # Normalize multiple spaces
    s = re.sub(r"\s+", " ", s)

    # Try cross-chapter range first: Book X:Y-A:B
    m = re.match(r"^([1-3]?[A-Za-z]+)\s+(\d+):(\d+)\s*-\s*(\d+):(\d+)$", s)
    if m:
        book = m.group(1)
        sc, sv, ec, ev = map(int, (m.group(2), m.group(3), m.group(4), m.group(5)))
        return book, (sc, sv), (ec, ev)

    # Same-chapter range: Book X:Y-Z
    m = re.match(r"^([1-3]?[A-Za-z]+)\s+(\d+):(\d+)\s*-\s*(\d+)$", s)
    if m:
        book = m.group(1)
        sc, sv, ev = map(int, (m.group(2), m.group(3), m.group(4)))
        return book, (sc, sv), (sc, ev)

    # Single verse: Book X:Y
    m = re.match(r"^([1-3]?[A-Za-z]+)\s+(\d+):(\d+)$", s)
    if m:
        book = m.group(1)
        sc, sv = map(int, (m.group(2), m.group(3)))
        return book, (sc, sv), (sc, sv)

    raise ValueError("Invalid reference. Try formats like 'John 1:1', 'John 1:1-18', or 'John 1:1-5:14'.")


def fetch_passage_data(book: str, start_ch: int, start_vs: int, end_ch: int, end_vs: int):
    """Fetch multiple verses inclusive. Assumes all within the same book.
    Iterates verses, rolling chapters when verse stops returning content.
    """
    verses = []
    cur_ch, cur_vs = start_ch, start_vs
    # Safety guard to avoid infinite loops
    MAX_VERSES = 5000
    count = 0
    while (cur_ch < end_ch) or (cur_ch == end_ch and cur_vs <= end_vs):
        count += 1
        if count > MAX_VERSES:
            break
        try:
            vdata = fetch_sword_data(book, cur_ch, cur_vs)
        except Exception:
            # If we cannot fetch, assume boundary exceeded for this chapter; jump to next chapter
            cur_ch += 1
            cur_vs = 1
            continue

        # Heuristic: if no words returned, consider verse invalid and move to next chapter
        if not vdata.words:
            cur_ch += 1
            cur_vs = 1
            # Skip adding
        else:
            verses.append(vdata)
            cur_vs += 1

    return verses


# --- 3. FlexText XML Generation (Unchanged) ---

def build_flextext_xml(verse_data: InterlinearVerse, config_map: dict) -> str:
    """Generates FlexText for a single verse in the expected <document> format, without morpheme blocks."""

    def make_title_and_abbrev(v: InterlinearVerse):
        title = v.get_verse_ref()
        abbrev = title.replace(' ', '').replace(':', '_')
        return title, abbrev

    baseline_key = config_map.get('baseline_data_key', 'greek_word')
    gloss_key = config_map.get('word_gloss_data_key', 'en_gloss')

    # Root document and interlinear-text
    doc = ET.Element('document', version='2')
    root = ET.SubElement(doc, 'interlinear-text', guid=str(uuid.uuid4()))

    # Title metadata
    title, abbrev = make_title_and_abbrev(verse_data)
    ET.SubElement(root, 'item', type='title', lang='en').text = title
    ET.SubElement(root, 'item', type='title-abbreviation', lang='en').text = abbrev

    # Paragraph structure
    paragraphs = ET.SubElement(root, 'paragraphs')
    paragraph = ET.SubElement(paragraphs, 'paragraph')
    phrases = ET.SubElement(paragraph, 'phrases')
    phrase = ET.SubElement(phrases, 'phrase', guid=str(uuid.uuid4()))

    # Phrase-level Greek text (concatenate baseline words)
    greek_phrase = ' '.join([w.to_dict().get(baseline_key, '') for w in verse_data.words]).strip()
    ET.SubElement(phrase, 'item', type='txt', lang='grc').text = greek_phrase
    # Verse number
    ET.SubElement(phrase, 'item', type='segnum', lang='en').text = str(verse_data.verse)

    # Words
    words_element = ET.SubElement(phrase, 'words')
    for word_obj in verse_data.words:
        word = ET.SubElement(words_element, 'word', guid=str(uuid.uuid4()))
        wd = word_obj.to_dict()
        ET.SubElement(word, 'item', type='txt', lang='grc').text = wd.get(baseline_key, '')
        ET.SubElement(word, 'item', type='gls', lang='en').text = wd.get(gloss_key, '')

    # Phrase-level English translation (prefer module; fallback to provided literal or gloss concat)
    literal = get_phrase_translation(verse_data.book, verse_data.chapter, verse_data.verse)
    if not literal:
        literal = verse_data.literal_translation.strip() if verse_data.literal_translation else ''
    if not literal:
        literal = ' '.join([w.to_dict().get(gloss_key, '') for w in verse_data.words]).strip()
    ET.SubElement(phrase, 'item', type='gls', lang='en').text = literal

    # Finalize
    tree = ET.ElementTree(doc)
    if sys.version_info >= (3, 9):
        ET.indent(tree, space="  ")
    return ET.tostring(doc, encoding='utf-8', xml_declaration=True).decode('utf-8')


def build_flextext_xml_for_passage(verses: list, config_map: dict) -> str:
    """Generates FlexText for multiple verses as separate phrases in one paragraph, wrapped in <document>."""
    if not verses:
        return build_flextext_xml(InterlinearVerse('','',0), config_map)

    baseline_key = config_map.get('baseline_data_key', 'greek_word')
    gloss_key = config_map.get('word_gloss_data_key', 'en_gloss')

    # Title from first and last verse
    first, last = verses[0], verses[-1]
    title = f"{first.book} {first.chapter}:{first.verse}"
    if (first.chapter, first.verse) != (last.chapter, last.verse):
        title = f"{first.book} {first.chapter}:{first.verse}-{last.chapter}:{last.verse}"
    abbrev = title.replace(' ', '').replace(':', '_')

    doc = ET.Element('document', version='2')
    root = ET.SubElement(doc, 'interlinear-text', guid=str(uuid.uuid4()))
    ET.SubElement(root, 'item', type='title', lang='en').text = title
    ET.SubElement(root, 'item', type='title-abbreviation', lang='en').text = abbrev

    paragraphs = ET.SubElement(root, 'paragraphs')
    paragraph = ET.SubElement(paragraphs, 'paragraph')
    phrases = ET.SubElement(paragraph, 'phrases')

    for v in verses:
        phrase = ET.SubElement(phrases, 'phrase', guid=str(uuid.uuid4()))

        # Phrase-level baseline (full Greek text)
        greek_phrase = ' '.join([w.to_dict().get(baseline_key, '') for w in v.words]).strip()
        ET.SubElement(phrase, 'item', type='txt', lang='grc').text = greek_phrase
        # Verse number
        ET.SubElement(phrase, 'item', type='segnum', lang='en').text = str(v.verse)

        words_element = ET.SubElement(phrase, 'words')
        for word_obj in v.words:
            word = ET.SubElement(words_element, 'word', guid=str(uuid.uuid4()))
            wd = word_obj.to_dict()
            ET.SubElement(word, 'item', type='txt', lang='grc').text = wd.get(baseline_key, '')
            ET.SubElement(word, 'item', type='gls', lang='en').text = wd.get(gloss_key, '')

        # Phrase-level English translation (prefer module; fallback to provided literal or gloss concat)
        literal = get_phrase_translation(v.book, v.chapter, v.verse)
        if not literal:
            literal = v.literal_translation.strip() if v.literal_translation else ''
        if not literal:
            literal = ' '.join([w.to_dict().get(gloss_key, '') for w in v.words]).strip()
        ET.SubElement(phrase, 'item', type='gls', lang='en').text = literal

    tree = ET.ElementTree(doc)
    if sys.version_info >= (3, 9):
        ET.indent(tree, space="  ")
    return ET.tostring(doc, encoding='utf-8', xml_declaration=True).decode('utf-8')


# --- 4. PyWebView API Class (Unchanged, relies on updated functions) ---

class Api:
    """The bridge between JavaScript and Python."""

    def get_interlinear_data_for_json(self, book, chapter, verse):
        """Called by JS to retrieve one verse (legacy)."""
        try:
            chapter = int(chapter)
            verse = int(verse)
            verse_data = fetch_sword_data(book, chapter, verse)
            return verse_data.to_dict()
        except Exception as e:
            return {'error': f"Python Error: {str(e)}"}

    def get_interlinear_data_for_reference(self, reference_str):
        """Called by JS to retrieve data for a single verse or a range like 'John 1:1-5:14'."""
        try:
            book, (sc, sv), (ec, ev) = parse_reference_range(reference_str)
            if (sc, sv) == (ec, ev):
                v = fetch_sword_data(book, sc, sv)
                return {
                    'passage_ref': v.get_verse_ref(),
                    'verses': [v.to_dict()]
                }
            verses = fetch_passage_data(book, sc, sv, ec, ev)
            if not verses:
                return {'error': f"No data found for {reference_str}"}
            return {
                'passage_ref': reference_str,
                'verses': [v.to_dict() for v in verses]
            }
        except Exception as e:
            return {'error': f"Python Error: {str(e)}"}

    def get_available_translations(self):
        """Return list of available translation IDs and which is selected."""
        try:
            return {
                'available': list(TRANSLATION_MODULES.keys()),
                'selected': SELECTED_TRANSLATION_ID
            }
        except Exception as e:
            return {'error': f"Python Error: {str(e)}"}

    def set_translation(self, module_id):
        """Set the currently selected translation by module id, or disable with 'NONE'."""
        try:
            global SELECTED_TRANSLATION_ID
            if module_id == 'NONE':
                SELECTED_TRANSLATION_ID = None
                return {'ok': True, 'selected': None}
            if module_id in TRANSLATION_MODULES:
                SELECTED_TRANSLATION_ID = module_id
                return {'ok': True, 'selected': module_id}
            return {'ok': False, 'error': f"Translation '{module_id}' not available."}
        except Exception as e:
            return {'ok': False, 'error': f"Python Error: {str(e)}"}

    def generate_flextext(self, verse_ref, config_map, verse_data_json):
        """Called by JS to generate the XML and save the file."""
        try:
            # 1. Reconstruct Verse Object from JSON
            # pywebview passes JSON-serializable JS objects as Python dicts
            # Accept dict directly; keep backward-compat if stringified
            if isinstance(config_map, str):
                config_map = json.loads(config_map)
            # Support single-verse (legacy) or passage data ({ verses: [...] })
            if isinstance(verse_data_json, dict) and 'verses' in verse_data_json:
                verse_list = [InterlinearVerse.from_dict(v) for v in verse_data_json['verses']]
                flextext_xml = build_flextext_xml_for_passage(verse_list, config_map)
            else:
                verse_data = InterlinearVerse.from_dict(verse_data_json)
                flextext_xml = build_flextext_xml(verse_data, config_map)

            # 3. Trigger File Save Dialog (PyWebView built-in)
            filename = f"{verse_ref.replace(' ', '_').replace(':', '-')}.flextext"
            file_path = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=os.path.expanduser('~'),  # Default to user's home directory
                allow_multiple=False,
                save_filename=filename,
                file_types=('FlexText Files (*.flextext)',)
            )

            # Normalize selection result across platforms
            if not file_path:
                return "File generation cancelled."
            selected = file_path[0] if isinstance(file_path, (list, tuple)) else file_path
            if isinstance(selected, tuple):
                selected = selected[0]
            if not selected:
                return "File generation cancelled."

            final_path = selected

            # If a directory was returned (some OS behaviors), place the default filename inside it
            if os.path.isdir(final_path):
                final_path = os.path.join(final_path, filename)

            # Ensure .flextext extension
            if not final_path.lower().endswith('.flextext'):
                final_path += '.flextext'

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(final_path) or '.', exist_ok=True)

            try:
                with open(final_path, 'w', encoding='utf-8') as f:
                    f.write(flextext_xml)
            except IsADirectoryError:
                return "❌ Generation Failed: Selected path is a folder. Please choose a file name inside a writable folder."
            except PermissionError:
                return "❌ Generation Failed: Permission denied for the selected location. Choose a writable folder (e.g., your home folder)."

            return f"✅ Successfully saved FlexText to: {final_path}"

        except Exception as e:
            return f"❌ Generation Failed: {e}"


# --- 5. PyWebView Application Bootstrap ---

def start_app():
    # Instantiate the API class
    api = Api()
    
    # Check if we are running as a bundled executable (PyInstaller)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        html_path = os.path.join(sys._MEIPASS, 'index.html')
    else:
        html_path = 'index.html'

    # Create the webview window
    webview.create_window(
        'SWORD to FlexText Interlinear Generator', 
        url=html_path, 
        js_api=api,
        width=850, 
        height=950,
        resizable=True
    )
    
    # Start the PyWebView event loop
    webview.start()

if __name__ == '__main__':
    # 1. Load modules before starting the webview (critical)
    load_sword_modules() 
    
    # 2. Start the webview application
    start_app()
