#!/usr/bin/env python3
import webview
import os
import re
import uuid
import json
import xml.etree.ElementTree as ET
import sys
# IMPORTANT: Replacing 'pysword' with 'python-sword' for MorphGNT compatibility
try:
    from sword import Sword
except ImportError:
    print("FATAL: 'python-sword' library not found. Please install with 'pip install python-sword'")
    sys.exit(1)


# --- GLOBAL SWORD MODULES (Initialized at startup) ---
MORPHGNT_MODULE = None
STRONGSGK_MODULE = None
GNT_MODULE_ID = "MorphGNT"   # Targeting the MorphGNT module
GLOSS_MODULE_ID = "StrongsGk" # Targeting the StrongsGk module


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

def load_sword_modules():
    """Initializes the SWORD library and loads MorphGNT and StrongsGk."""
    global MORPHGNT_MODULE, STRONGSGK_MODULE 
    
    SWORD_REPO_PATH = find_repo_path('sword_repo')

    try:
        manager = Sword(repository=SWORD_REPO_PATH)
        MORPHGNT_MODULE = manager.get_module(GNT_MODULE_ID)
        STRONGSGK_MODULE = manager.get_module(GLOSS_MODULE_ID)

        if not MORPHGNT_MODULE or not STRONGSGK_MODULE:
            raise ValueError(f"Required module(s) not found: {GNT_MODULE_ID} or {GLOSS_MODULE_ID}. Check case/structure.")
        
        print("SWORD Modules loaded successfully.")

    except Exception as e:
        # FATAL: Exit if resources are missing
        print(f"FATAL SWORD ERROR: {e}")
        print(f"Attempted Repository Path: {SWORD_REPO_PATH}")
        sys.exit(1)


def get_strongs_gloss(strongs_number: str) -> str:
    """Uses the StrongsGk module to get the English gloss."""
    if not STRONGSGK_MODULE:
        return "ERROR: StrongsGk not loaded."
    
    # Remove 'G' prefix if present, as StrongsGk keys are often just the number (e.g., "3056")
    key = strongs_number.lstrip('G') 
    
    try:
        # get_entry returns the full entry, which is usually OSIS XML/text
        gloss_entry = STRONGSGK_MODULE.get_entry(key)
        
        # Simple cleaning: take the first line or a short cleaned version.
        # This part may need tuning based on the exact StrongsGk module's output.
        cleaned_gloss = gloss_entry.split('\n')[0].strip()
        
        return cleaned_gloss if cleaned_gloss else "No definition found"
    except Exception:
        return f"Gloss not found for {strongs_number}"


def fetch_sword_data(book: str, chapter: int, verse: int) -> InterlinearVerse:
    """Retrieves and parses interlinear data for a given verse from SWORD modules."""
    
    if not MORPHGNT_MODULE:
        raise Exception("MorphGNT module not loaded.")

    verse_ref_str = f"{book} {chapter}:{verse}"
    
    try:
        # Retrieve the raw tagged text from MorphGNT
        raw_text_with_tags = MORPHGNT_MODULE.get_entry(verse_ref_str)
        
        # Initialize verse object with blank translations (MorphGNT doesn't provide them)
        verse_data = InterlinearVerse(book, chapter, verse)
        
    except Exception as e:
        raise Exception(f"SWORD Data Lookup Error for {verse_ref_str}: {e}")
            
    # Regex to find word tags and extract attributes (UNCHANGED)
    # The 'strong' attribute in MorphGNT typically contains the G-number (e.g., G3056)
    word_pattern = re.compile(
        r'<w(?:\s+lemma="(?P<lemma>[^"]*)")?'
        r'(?:\s+morph="(?P<morph>[^"]*)")?'
        r'(?:\s+strong="(?P<strongs>[^"]*)")?'
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
        strongs = data.get('strongs', '').strip()
        greek_word = data.get('greek_word').strip()
        
        # --- CRITICAL: Lookup Gloss using the Strongs number ---
        en_gloss = get_strongs_gloss(strongs)
        # --------------------------------------------------------

        word = InterlinearWord(
            greek_word=greek_word,
            lemma=data.get('lemma', '').strip(),
            morphology=data.get('morph', '').strip(),
            strongs_number=strongs,
            en_gloss=en_gloss,
            tr_transliteration=transliterate(greek_word)
        )
        verse_data.add_word(word)

    # Note: Free and Literal translation fields remain blank unless you add another translation module
    return verse_data


# --- 3. FlexText XML Generation (Unchanged) ---

def build_flextext_xml(verse_data: InterlinearVerse, config_map: dict) -> str:
    """Generates the FlexText XML string based on verse data and user configuration."""
    
    # --- Setup XML Root ---
    root = ET.Element('interlinear-text', guid=str(uuid.uuid4()))
    paragraphs = ET.SubElement(root, 'paragraphs')
    paragraph = ET.SubElement(paragraphs, 'paragraph')
    phrases = ET.SubElement(paragraph, 'phrases')
    phrase = ET.SubElement(phrases, 'phrase', guid=str(uuid.uuid4()))
    
    # 1. Free Translation Line (Item type="gls" for phrase)
    ET.SubElement(phrase, 'item', type='gls', lang='en').text = verse_data.free_translation
    
    # 2. Literal Translation Line (Item type="lit" for phrase)
    if config_map.get('include_literal') and verse_data.literal_translation:
        ET.SubElement(phrase, 'item', type='lit', lang='en').text = verse_data.literal_translation
        
    words_element = ET.SubElement(phrase, 'words')
    
    # --- Process WORDS ---
    for word_obj in verse_data.words:
        word = ET.SubElement(words_element, 'word', guid=str(uuid.uuid4()))
        word_data = word_obj.to_dict()

        # 3. BASELINE TEXT (Item type="txt")
        baseline_key = config_map.get('baseline_data_key', 'greek_word')
        baseline_text = word_data.get(baseline_key, '')
        ET.SubElement(word, 'item', type='txt', lang='grc').text = baseline_text # Use 'grc' as a default WS ID
        
        # 4. WORD GLOSS (Item type="gls")
        gloss_key = config_map.get('word_gloss_data_key', 'en_gloss')
        gloss_text = word_data.get(gloss_key, '')
        ET.SubElement(word, 'item', type='gls', lang='en').text = gloss_text # Use 'en' as a default WS ID
        
        # 5. ANALYSIS LAYERS (Item type="msa" under morphemes)
        if config_map.get('analysis_map'):
            morphemes_element = ET.SubElement(word, 'morphemes')
            morph_element = ET.SubElement(morphemes_element, 'morph') # Treat as single word-morpheme

            for data_key, ws_id in config_map['analysis_map'].items():
                value = word_data.get(data_key)
                if value:
                    # Add a morphological analysis item for each selected layer
                    ET.SubElement(morph_element, 'item', type='msa', lang=ws_id).text = value

    # --- Finalize and Return XML ---
    tree = ET.ElementTree(root)
    # Note: ET.indent requires Python 3.9+
    if sys.version_info >= (3, 9):
        ET.indent(tree, space="  ") 
    
    return ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')


# --- 4. PyWebView API Class (Unchanged, relies on updated functions) ---

class Api:
    """The bridge between JavaScript and Python."""

    def get_interlinear_data_for_json(self, book, chapter, verse):
        """Called by JS to retrieve data and return it as JSON."""
        try:
            # We must convert book/chapter/verse to standard Python types first
            chapter = int(chapter)
            verse = int(verse)
            verse_data = fetch_sword_data(book, chapter, verse)
            return verse_data.to_dict()
        except Exception as e:
            # Send error back to JS
            return {'error': f"Python Error: {str(e)}"}

    def generate_flextext(self, verse_ref, config_map, verse_data_json):
        """Called by JS to generate the XML and save the file."""
        try:
            # 1. Reconstruct Verse Object from JSON
            config_map = json.loads(config_map) # config_map is passed as a JSON string from JS
            verse_data = InterlinearVerse.from_dict(verse_data_json)

            # 2. Generate XML String
            flextext_xml = build_flextext_xml(verse_data, config_map)

            # 3. Trigger File Save Dialog (PyWebView built-in)
            filename = f"{verse_ref.replace(' ', '_').replace(':', '-')}.flextext"
            file_path = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG, 
                directory=os.path.expanduser('~'), # Default to user's home directory
                allow_multiple=False,
                save_filename=filename,
                file_types=('FlexText Files (*.flextext)',)
            )
            
            if file_path and file_path[0]:
                final_path = file_path[0]
                if isinstance(final_path, tuple): # PyWebView sometimes returns a tuple
                    final_path = final_path[0]
                    
                with open(final_path, 'w', encoding='utf-8') as f:
                    f.write(flextext_xml)
                
                return f"✅ Successfully saved FlexText to: {final_path}"
            
            return "File generation cancelled."

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
