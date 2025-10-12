#!/usr/bin/env python3
import webview
import os
import re
import uuid
import json
import xml.etree.ElementTree as ET
from pysword.modules import SwordModules
# NOTE: The pysword implementation below is conceptual and relies on the exact 
# structure of the installed SWORD module (e.g., SBLGNT) containing the tags.

# --- 1. Data Structure Classes ---

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


# --- 2. SWORD Data Extraction (Conceptual, Critical Text Focused) ---

GNT_MODULE_ID = "SBLGNT" # Target a critical text
GLOSS_MODULE_ID = "Thayer" # Example lexicon for glosses

def get_placeholder_gloss(strongs_number: str) -> str:
    """A dummy function to simulate a dictionary lookup."""
    gloss_map = {
        'G1722': 'in, on, with', 'G746': 'beginning', 'G2258': 'was, existed',
        'G3588': 'the (article)', 'G3056': 'word, reason', 'G2532': 'and, also',
        'G4314': 'to, with, toward', 'G2316': 'God, god'
    }
    return gloss_map.get(strongs_number, 'N/A')

def fetch_sword_data(book: str, chapter: int, verse: int) -> InterlinearVerse:
    """Retrieves and parses interlinear data for a given verse from SWORD modules."""
    try:
        sm = SwordModules()
        gnt_module = sm.get_bible(GNT_MODULE_ID)
        
        # --- Conceptual Mock Data (Replace with real pysword logic) ---
        if book == "John" and verse == 1:
            raw_text_with_tags = (
                '<w lemma="G1722" morph="P" strong="G1722">ἐν</w> <w lemma="G746" morph="N-DSF" strong="G746">ἀρχῇ</w> '
                '<w lemma="G2258" morph="V-IXA-3S" strong="G2258">ἦν</w> <w lemma="G3588" morph="T-NSM" strong="G3588">ὁ</w> '
                '<w lemma="G3056" morph="N-NSM" strong="G3056">λόγος</w> <w lemma="G2532" morph="C" strong="G2532">καὶ</w> '
                '<w lemma="G3588" morph="T-NSM" strong="G3588">ὁ</w> <w lemma="G3056" morph="N-NSM" strong="G3056">λόγος</w> '
                '<w lemma="G2258" morph="V-IXA-3S" strong="G2258">ἦν</w> <w lemma="G4314" morph="P" strong="G4314">πρὸς</w> '
                '<w lemma="G3588" morph="T-ASM" strong="G3588">τὸν</w> <w lemma="G2316" morph="N-ASM" strong="G2316">Θεόν</w> '
                '<w lemma="G2532" morph="C" strong="G2532">καὶ</w> <w lemma="G2316" morph="N-NSM" strong="G2316">Θεός</w> '
                '<w lemma="G2258" morph="V-IXA-3S" strong="G2258">ἦν</w> <w lemma="G3588" morph="T-NSM" strong="G3588">ὁ</w> <w lemma="G3056" morph="N-NSM" strong="G3056">λόγος</w>.'
            )
            free_translation = "In the beginning was the Word, and the Word was with God, and the Word was God."
            literal_translation = "In beginning was the Word, and the Word was toward the God, and God was the Word."
        else:
            # Attempt real lookup or fail gracefully
            raw_text_with_tags = gnt_module.get_raw_verse(book, chapter, verse)
            free_translation = gnt_module.get_raw_verse(book, chapter, verse, markup="plain") # Simplified Free Trans
            literal_translation = ""

        # Initialize verse object
        verse_data = InterlinearVerse(book, chapter, verse, free_translation, literal_translation)
        
    except Exception as e:
        # NOTE: A real app needs robust error handling for SWORD modules not found or parse errors
        raise Exception(f"SWORD Data Error: {e}")
        
    # Regex to find word tags and extract attributes
    word_pattern = re.compile(
        r'<w(?:\s+lemma="(?P<lemma>[^"]*)")?'
        r'(?:\s+morph="(?P<morph>[^"]*)")?'
        r'(?:\s+strong="(?P<strongs>[^"]*)")?'
        r'>(?P<greek_word>[^<]+)</w>'
    )
    
    # Simple roman transliteration for demo purposes
    def transliterate(greek):
        mapping = {'α':'a', 'β':'b', 'γ':'g', 'δ':'d', 'ε':'e', 'ζ':'z', 'η':'ē', 'θ':'th', 'ι':'i', 
                   'κ':'k', 'λ':'l', 'μ':'m', 'ν':'n', 'ξ':'x', 'ο':'o', 'π':'p', 'ρ':'r', 'σ':'s', 
                   'τ':'t', 'υ':'u', 'φ':'ph', 'χ':'ch', 'ψ':'ps', 'ω':'ō', 'ς':'s'}
        return ''.join(mapping.get(c.lower(), c) for c in greek)

    for match in word_pattern.finditer(raw_text_with_tags):
        data = match.groupdict()
        strongs = data.get('strongs', '').strip()
        greek_word = data.get('greek_word').strip()

        word = InterlinearWord(
            greek_word=greek_word,
            lemma=data.get('lemma', '').strip(),
            morphology=data.get('morph', '').strip(),
            strongs_number=strongs,
            en_gloss=get_placeholder_gloss(strongs),
            tr_transliteration=transliterate(greek_word)
        )
        verse_data.add_word(word)

    return verse_data


# --- 3. FlexText XML Generation ---

def build_flextext_xml(verse_data: InterlinearVerse, config_map: dict) -> str:
    """Generates the FlexText XML string based on verse data and user configuration."""
    
    # --- Setup XML Root ---
    root = ET.Element('interlinear-text', guid=str(uuid.uuid4()))
    paragraphs = ET.SubElement(root, 'paragraphs')
    paragraph = ET.SubElement(paragraphs, 'paragraph')
    phrases = ET.SubElement(paragraph, 'phrases')
    phrase = ET.SubElement(phrases, 'phrase', guid=str(uuid.uuid4()))
    
    # 1. Free Translation Line (Item type="gls" for phrase)
    # The 'gls' at the phrase level is used for the Free Translation line in FLEx
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
    # Create an ElementTree to pretty-print the XML (optional but helpful)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ") # Requires Python 3.9+
    
    # Get XML string with declaration
    return ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')


# --- 4. PyWebView API Class ---

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
            return {'error': str(e)}

    def generate_flextext(self, verse_ref, config_map, verse_data_json):
        """Called by JS to generate the XML and save the file."""
        try:
            # 1. Reconstruct Verse Object from JSON
            verse_data = InterlinearVerse.from_dict(verse_data_json)

            # 2. Generate XML String
            flextext_xml = build_flextext_xml(verse_data, config_map)

            # 3. Trigger File Save Dialog (PyWebView built-in)
            # The save_file_dialog returns None if canceled, or the file path if saved.
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
                # PyWebView returns a tuple, we take the first path element
                if isinstance(final_path, tuple):
                    final_path = final_path[0]
                    
                with open(final_path, 'w', encoding='utf-8') as f:
                    f.write(flextext_xml)
                
                return f"✅ Successfully saved FlexText to: {final_path}"
            
            return "File generation cancelled."

        except Exception as e:
            return f"❌ Generation Failed: {e}"


# --- 5. PyWebView Application Bootstrap ---

# The HTML file content (assuming you put the HTML/JS from the previous step here)
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>SWORD to FlexText Converter</title>
    </head>
<body>
    <script>
        // Placeholder for the JavaScript functions (addRow, removeRow, loadVerseData, generateFile)
        // ... (The JS code from Step 7 Revised must be here) ...
    </script>
</body>
</html>
"""

def start_app():
    # Instantiate the API class
    api = Api()
    
    # Create the webview window
    webview.create_window(
        'SWORD to FlexText Interlinear Generator', 
        html=html_content, 
        js_api=api,
        width=850, 
        height=950,
        resizable=True
    )
    
    # Start the PyWebView event loop
    webview.start()

if __name__ == '__main__':
    # NOTE: In a real deployment, you would ensure the HTML/JS is correctly 
    # bundled and referenced. For this script, we're using an inline placeholder.
    start_app()
