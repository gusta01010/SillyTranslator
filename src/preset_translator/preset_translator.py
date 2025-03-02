import json
import re
import os
import locale
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from googletrans import Translator
import sys  # Import sys for system language detection

# --- Configuration Constants ---
CONFIG_FILE = "config.json"
LANGUAGES_FILE = "./lang/lang_data.json"
MAX_CHUNK_SIZE = 8  # Maximum words per chunk
TARGET_FIELDS = {
    "content", "new_group_chat_prompt", "new_example_chat_prompt",
    "continue_nudge_prompt", "wi_format", "personality_format",
    "group_nudge_prompt", "scenario_format", "new_chat_prompt",
    "impersonation_prompt", "bias_preset_selected", "assistant_impersonation"
}


class TranslationConfig:
    """Manages application configuration and language settings."""

    def __init__(self):
        self.data = self._load_config()
        self.full_lang_data = self._load_full_lang_data()  # Load the entire lang_data
        self.languages = self._load_languages()
        self.translations = self._load_translations()
        self.current_lang = self.data.get("last_used_language", "en")

    def _load_config(self):
        """Loads or creates configuration file."""
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Default configuration
            try:
                sys_lang = locale.getlocale()[0][:2] if locale.getlocale()[0] else "en"
            except:
                sys_lang = "en"

            default_config = {
                "silly_tavern_path": "",
                "last_used_language": sys_lang,
                "translate_angle": False,
                "save_location": "silly"
            }

            # Save default config
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)

            return default_config

    def _load_full_lang_data(self):
        """Loads the entire language data JSON."""
        try:
            with open(LANGUAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("Error: Language file not found or malformed.")
            return {}  # Return empty dict in case of error

    def _load_languages(self):
        """Loads language codes from JSON file."""
        languages_data = self.full_lang_data.get("languages", {})  # Get the languages section
        if not languages_data:
            print("Error: Language data not found in lang_data.json. Using defaults.")
            return {"English": "en", "Português": "pt"}  # Default if section is missing
        return languages_data

    def _load_translations(self):
        """Loads UI text translations."""
        translations = {}
        for lang_code in self.full_lang_data.keys():
            if lang_code != "languages" and isinstance(self.full_lang_data[lang_code],
                                                       dict):  # Check if it's a translation section
                translations[lang_code] = self.full_lang_data[lang_code]

        if not translations:
            print("Error: No translations found in lang_data.json. Using English.")
            return {"en": {}}  # Default if no translations found
        return translations

    def get_text(self, key):
        """Retrieves translated text for a given key."""
        return self.translations.get(self.current_lang, {}).get(
            key, self.translations.get("en", {}).get(key, key))

    def save(self):
        """Saves current configuration to file."""
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4)


class TextChunker:
    """Handles text chunking and formatting preservation."""

    def __init__(self, max_chunk_size=MAX_CHUNK_SIZE):
        self.max_chunk_size = max_chunk_size

    def split_into_chunks(self, text):
        """Splits text into chunks respecting formatting and delimiters."""
        if not text:
            return []

        # First split by newlines to preserve them
        chunks = []
        current_chunk = ""

        i = 0
        while i < len(text):
            if text[i:i + 1] == '\n':
                if current_chunk:
                    chunks.append(current_chunk.strip())
                chunks.append('\n')
                current_chunk = ""
                i += 1
            else:
                current_chunk += text[i]
                i += 1

        if current_chunk:
            chunks.append(current_chunk.strip())

        # Process bracket content separately
        intermediate_chunks = []
        for chunk in chunks:
            if chunk == '\n':
                intermediate_chunks.append('\n')
                continue

            processed_chunk = ""
            i = 0
            while i < len(chunk):
                if chunk[i] in '([':
                    # Save any accumulated text before the bracket
                    if processed_chunk.strip():
                        intermediate_chunks.append(processed_chunk.strip())
                        processed_chunk = ""

                    # Determine matching closing bracket
                    opening = chunk[i]
                    closing = ')' if opening == '(' else ']'
                    level = 1
                    start_pos = i
                    i += 1

                    # Find matching closing bracket
                    while i < len(chunk) and level > 0:
                        if chunk[i] == opening:
                            level += 1
                        elif chunk[i] == closing:
                            level -= 1
                        i += 1

                    # Add the bracketed content as a whole chunk
                    if level == 0:
                        intermediate_chunks.append(chunk[start_pos:i])
                    else:
                        # Handle unclosed bracket
                        intermediate_chunks.append(chunk[start_pos:])
                        break
                else:
                    processed_chunk += chunk[i]
                    i += 1

            if processed_chunk.strip():
                intermediate_chunks.append(processed_chunk.strip())

        # Further split by delimiters and respect word limits
        final_chunks = []
        for chunk in intermediate_chunks:
            # Keep special chunks intact
            if chunk == '\n' or chunk.startswith(('(', '[')):
                final_chunks.append(chunk)
                continue

            # Split by punctuation and respect word limit
            segments = re.split(r'([\.,;:])', chunk)
            current_chunk = ""

            for segment in segments:
                if not segment:
                    continue

                # Handle special placeholders
                if "__PLACEHOLDER_" in segment:
                    if current_chunk:
                        final_chunks.append(current_chunk.strip())
                        current_chunk = ""
                    final_chunks.append(segment.strip())
                    continue

                # Keep punctuation with preceding word
                if current_chunk and segment.strip() in [',', '.', ';', ':']:
                    current_chunk += segment
                # Add to current chunk if within word limit
                elif len(current_chunk.split()) + len(segment.split()) <= self.max_chunk_size or not current_chunk:
                    current_chunk += segment
                # Start a new chunk if would exceed word limit
                else:
                    final_chunks.append(current_chunk.strip())
                    current_chunk = segment

            if current_chunk:
                final_chunks.append(current_chunk.strip())

        return final_chunks


class TextFormatter:
    """Handles text formatting preservation during translation."""

    @staticmethod
    def preserve_case(original, translated):
        """Preserves case pattern from original text in translated text."""
        if not original or not translated:
            return translated

        # Direct case handling for single-word chunks
        if original.isupper() and original.strip():
            return translated.upper()
        if original.islower() and original.strip():
            return translated.lower()

        # Handle newlines by processing each line separately
        if '\n' in original:
            orig_lines = original.split('\n')
            trans_lines = translated.split('\n')
            min_lines = min(len(orig_lines), len(trans_lines))

            result_lines = [
                trans_lines[i].upper() if orig_lines[i].isupper() and orig_lines[i].strip() else
                trans_lines[i].lower() if orig_lines[i].islower() and orig_lines[i].strip() else
                trans_lines[i] for i in range(min_lines)
            ]

            # Add any remaining translated lines
            result_lines.extend(trans_lines[min_lines:])
            return '\n'.join(result_lines)

        # Process text with brackets
        result = translated
        patterns = [(r'\[([^\]]+)\]', r'\[(.*?)\]'), (r'\(([^\)]+)\)', r'\((.*?)\)')]

        for orig_pattern, trans_pattern in patterns:
            for match_orig in re.finditer(orig_pattern, original):
                content_orig = match_orig.group(1)
                if not content_orig.strip():
                    continue

                if content_orig.isupper():
                    for match_trans in re.finditer(trans_pattern, result):
                        content_trans = match_trans.group(1)
                        content_upper = content_trans.upper()
                        start_pos = match_trans.start(1)
                        end_pos = match_trans.end(1)
                        result = result[:start_pos] + content_upper + result[end_pos:]
                        break
                elif content_orig.islower():
                    for match_trans in re.finditer(trans_pattern, result):
                        content_trans = match_trans.group(1)
                        content_lower = content_trans.lower()
                        start_pos = match_trans.start(1)
                        end_pos = match_trans.end(1)
                        result = result[:start_pos] + content_lower + result[end_pos:]
                        break

        # Handle special uppercase patterns like "MAO:"
        uppercase_patterns = re.findall(r'([A-Z]{2,}:)', original)
        for pattern in uppercase_patterns:
            pattern_no_colon = pattern[:-1]
            for match in re.finditer(rf'({re.escape(pattern_no_colon)}:)', result, re.IGNORECASE):
                result = result[:match.start(1)] + pattern + result[match.end(1):]

        # Match case of individual words when possible
        orig_words = re.findall(r'\b([a-zA-Z0-9]+)\b', original)
        trans_words = re.findall(r'\b([a-zA-Z0-9]+)\b', result)

        if len(orig_words) == len(trans_words):
            for i, orig_word in enumerate(orig_words):
                if i < len(trans_words):
                    trans_word = trans_words[i]
                    if orig_word.isupper():
                        result = re.sub(r'\b' + re.escape(trans_word) + r'\b',
                                        trans_word.upper(), result, count=1)
                    elif orig_word[0].isupper():
                        result = re.sub(r'\b' + re.escape(trans_word) + r'\b',
                                        trans_word.capitalize(), result, count=1)

        # Capitalize first letter after sentence-ending punctuation
        result = re.sub(r'([.!?]\s*)([a-z])', lambda m: m.group(1) + m.group(2).upper(), result)

        return result

    @staticmethod
    def preserve_spacing(original, translated):
        """Preserves original spacing around brackets and punctuation."""
        spacing_map = {}
        context_map = {}

        # Map spacing and context around closing brackets
        for match in re.finditer(r'([a-zA-Z0-9]*)(\s*)([\]\)])(\s*)([a-zA-Z0-9]*)', original):
            prefix, pre_space, bracket, post_space, suffix = match.groups()
            pos = match.start(3)

            spacing_map[pos] = {
                'type': 'closing',
                'char': bracket,
                'pre_space': len(pre_space) > 0,
                'post_space': len(post_space) > 0,
                'has_prefix': bool(prefix),
                'has_suffix': bool(suffix)
            }

            context_map[pos] = {
                'pattern': f"{prefix}{pre_space}{bracket}{post_space}{suffix}",
                'context': 'closing'
            }

        # Map spacing and context around opening brackets
        for match in re.finditer(r'([a-zA-Z0-9]*)(\s*)([\[\(])(\s*)([a-zA-Z0-9]*)', original):
            prefix, pre_space, bracket, post_space, suffix = match.groups()
            pos = match.start(3)

            spacing_map[pos] = {
                'type': 'opening',
                'char': bracket,
                'pre_space': len(pre_space) > 0,
                'post_space': len(post_space) > 0,
                'has_prefix': bool(prefix),
                'has_suffix': bool(suffix)
            }

            context_map[pos] = {
                'pattern': f"{prefix}{pre_space}{bracket}{post_space}{suffix}",
                'context': 'opening'
            }

        result = translated

        # Apply spacing for closing brackets based on original context
        for match in re.finditer(r'([a-zA-Z0-9]*)(\s*)([\]\)])(\s*)([a-zA-Z0-9]*)', result):
            prefix, pre_space, bracket, post_space, suffix = match.groups()
            pos = match.start(3)

            # Find matching context in original
            for orig_pos, info in spacing_map.items():
                if info['type'] == 'closing' and info['char'] == bracket:
                    # Reproduce spacing pattern from original
                    has_pre_space_original = info['pre_space']
                    has_post_space_original = info['post_space']
                    has_pre_space_translated = len(pre_space) > 0
                    has_post_space_translated = len(post_space) > 0

                    # Fix prefix spacing
                    if info['has_prefix'] and not has_pre_space_original and has_pre_space_translated:
                        # Remove space when original had none
                        result = result[:match.start(2)] + result[match.end(2):]
                        # Adjust match indices for subsequent replacements
                        post_space_start = match.start(4) - len(pre_space)
                        post_space_end = match.end(4) - len(pre_space)
                    elif info['has_prefix'] and has_pre_space_original and not has_pre_space_translated:
                        # Add space when original had one
                        result = result[:match.start(2)] + ' ' + result[match.start(2):]
                        # Adjust match indices
                        post_space_start = match.start(4) + 1
                        post_space_end = match.end(4) + 1
                    else:
                        post_space_start = match.start(4)
                        post_space_end = match.end(4)

                    # Fix suffix spacing
                    if info['has_suffix'] and not has_post_space_original and has_post_space_translated:
                        # Remove space when original had none
                        result = result[:post_space_start] + result[post_space_end:]
                    elif info['has_suffix'] and has_post_space_original and not has_post_space_translated:
                        # Add space when original had one
                        result = result[:post_space_start] + ' ' + result[post_space_start:]

                    break

        # Apply spacing for opening brackets based on original context
        for match in re.finditer(r'([a-zA-Z0-9]*)(\s*)([\[\(])(\s*)([a-zA-Z0-9]*)', result):
            prefix, pre_space, bracket, post_space, suffix = match.groups()
            pos = match.start(3)

            # Find matching context in original
            for orig_pos, info in spacing_map.items():
                if info['type'] == 'opening' and info['char'] == bracket:
                    # Reproduce spacing pattern from original
                    has_pre_space_original = info['pre_space']
                    has_post_space_original = info['post_space']
                    has_pre_space_translated = len(pre_space) > 0
                    has_post_space_translated = len(post_space) > 0

                    # Fix prefix spacing
                    if info['has_prefix'] and not has_pre_space_original and has_pre_space_translated:
                        # Remove space when original had none
                        result = result[:match.start(2)] + result[match.end(2):]
                        # Adjust match indices for subsequent replacements
                        post_space_start = match.start(4) - len(pre_space)
                        post_space_end = match.end(4) - len(pre_space)
                    elif info['has_prefix'] and has_pre_space_original and not has_pre_space_translated:
                        # Add space when original had one
                        result = result[:match.start(2)] + ' ' + result[match.start(2):]
                        # Adjust match indices
                        post_space_start = match.start(4) + 1
                        post_space_end = match.end(4) + 1
                    else:
                        post_space_start = match.start(4)
                        post_space_end = match.end(4)

                    # Fix suffix spacing
                    if info['has_suffix'] and not has_post_space_original and has_post_space_translated:
                        # Remove space when original had none
                        result = result[:post_space_start] + result[post_space_end:]
                    elif info['has_suffix'] and has_post_space_original and not has_post_space_translated:
                        # Add space when original had one
                        result = result[:post_space_start] + ' ' + result[post_space_start:]

                    break

        # Fix consecutive punctuation
        for match in re.finditer(r'([.,:;])([.,:;])', original):
            pattern = match.group(0)
            pattern_with_space = re.escape(match.group(1)) + r'\s+' + re.escape(match.group(2))
            result = re.sub(pattern_with_space, pattern, result)

        # Fix acronyms with periods
        for match in re.finditer(r'\b([A-Z](\.[A-Z])+(\.)?)(\b|\s)', original):
            original_acronym = match.group(0)
            acronym_pattern = ''.join(
                r'\.+\s*' if char == '.' else
                char + r'\s*' if char.isalpha() else
                re.escape(char) + r'\s*'
                for char in original_acronym
            )

            for match_trans in re.finditer(acronym_pattern, result):
                translated_acronym = match_trans.group(0)
                if ' ' in translated_acronym and ' ' not in original_acronym:
                    result = result.replace(translated_acronym, ''.join(translated_acronym.split()))

        return result

    @staticmethod
    def handle_backticks(original, translated):
        """Preserves content within backtick code blocks while translating surrounding text."""
        # Extract all backtick code blocks from original text
        code_blocks = []
        positions = []

        # Find triple backtick blocks
        for match in re.finditer(r'```(?:\w+)?\n([\s\S]*?)\n```', original):
            code_blocks.append(match.group(0))
            positions.append((match.start(), match.end()))

        # Find inline code with single backticks
        for match in re.finditer(r'`([^`]+)`', original):
            if any((start <= match.start() and match.end() <= end) for start, end in positions):
                # Skip if already inside a triple-backtick block
                continue
            code_blocks.append(match.group(0))
            positions.append((match.start(), match.end()))

        # Sort positions by start index
        positions_blocks = sorted(zip(positions, code_blocks), key=lambda x: x[0][0])

        # Create placeholders for code blocks
        placeholders = {}
        modified_text = original
        offset = 0

        for (start, end), block in positions_blocks:
            placeholder = f"__CODE_BLOCK_{len(placeholders)}__"
            placeholders[placeholder] = block

            # Replace code block with placeholder
            adjusted_start = start - offset
            adjusted_end = end - offset
            modified_text = modified_text[:adjusted_start] + placeholder + modified_text[adjusted_end:]

            # Update offset for next replacement
            offset += (end - start) - len(placeholder)

        # Process translated text to maintain code blocks
        result = translated

        # Parse translated text to find where placeholders should be
        for placeholder, block in placeholders.items():
            if placeholder in result:
                # Replace placeholder with original code block
                result = result.replace(placeholder, block)
            else:
                # Try to find most likely position for code block
                # This could be improved with more sophisticated matching
                result += f"\n\n{block}"

        return result

    @staticmethod
    def adjust_punctuation_spacing(text):
        """Adjusts spacing around punctuation marks."""
        # Add space after exclamation/question marks if none exists
        text = re.sub(r'([?!]+)([^\s?!])', r'\1 \2', text)

        # Remove space before punctuation
        text = re.sub(r'\s+([.,;:])', r'\1', text)

        # Add space after punctuation (unless followed by close bracket or newline)
        text = re.sub(r'([.,;:])([^\s.,;:\]\)\n])', r'\1 \2', text)

        # Remove space between punctuation and closing brackets
        text = re.sub(r'([.,;:])\s+([)\]])', r'\1\2', text)

        # Fix hyphenated words (no spaces around hyphen)
        text = re.sub(r'(\w+)\s+-\s*(\w+)', r'\1-\2', text)

        # Fix words incorrectly joined with punctuation
        text = re.sub(r'(\w+)([.,;:])(\w+)', r'\1\2 \3', text)

        return text

    @staticmethod
    def fix_capitalization(text):
        """Ensures proper capitalization after sentence-ending punctuation."""
        return re.sub(r'([.!?]\s*)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)


class TranslationEngine:
    """Handles the core translation functionality with improved handling of code blocks."""

    def __init__(self):
        self.translator = Translator()
        self.chunker = TextChunker()
        self.formatter = TextFormatter()

    def protect_variables(self, text):
        """Replaces character and user variables with placeholders."""
        return text.replace("{{char}}", "Jane").replace("{{user}}", "James")

    def restore_variables(self, text):
        """Restores character and user variables from placeholders."""
        return text.replace("Jane", "{{char}}").replace("James", "{{user}}")

    def extract_code_blocks(self, text):
        """
        Extracts code blocks surrounded by backticks and replaces with placeholders.
        Returns modified text and a dictionary of placeholders to code blocks.
        """
        code_blocks = {}

        # Extract triple backtick blocks first (they might contain inline backticks)
        def replace_triple_backtick(match):
            placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
            code_blocks[placeholder] = match.group(0)
            return placeholder

        # Find and replace triple backtick blocks
        modified_text = re.sub(
            r'```(?:\w+)?\n([\s\S]*?)\n```',
            replace_triple_backtick,
            text
        )

        # Then extract inline code
        def replace_inline_code(match):
            placeholder = f"__INLINE_CODE_{len(code_blocks)}__"
            code_blocks[placeholder] = match.group(0)
            return placeholder

        # Find and replace inline backtick code
        modified_text = re.sub(r'`([^`]+)`', replace_inline_code, modified_text)

        return modified_text, code_blocks

    def restore_code_blocks(self, text, code_blocks):
        """
        Restores code blocks from placeholders.
        """
        result = text
        for placeholder, code_block in code_blocks.items():
            result = result.replace(placeholder, code_block)
        return result

    def protect_and_translate_braces(self, text, target_lang):
        """Protects content within braces/brackets while translating surrounding text."""
        placeholders = {}

        # Replace content in braces with placeholders
        def replace_with_placeholder(match):
            placeholder = f"__BRACE_PLACEHOLDER_{len(placeholders)}__"
            placeholders[placeholder] = match.group(0)
            return placeholder

        # Find and replace all brace content
        modified_text = re.sub(r'({{[^}]+}}|{[^}]+})', replace_with_placeholder, text)

        # Translate text between placeholders
        chunks = []
        last_pos = 0

        for placeholder in sorted(placeholders.keys(), key=lambda p: modified_text.find(p)):
            pos = modified_text.find(placeholder, last_pos)

            # Translate text before placeholder
            if pos > last_pos:
                chunk_to_translate = modified_text[last_pos:pos]
                if chunk_to_translate.strip():
                    try:
                        translated_chunk = self.translator.translate(
                            chunk_to_translate, dest=target_lang).text
                        chunks.append(translated_chunk)
                    except Exception as e:
                        print(f"Error translating: {e}")
                        chunks.append(chunk_to_translate)
                else:
                    chunks.append(chunk_to_translate)

            # Keep placeholder intact
            chunks.append(placeholder)
            last_pos = pos + len(placeholder)

        # Translate any remaining text
        if last_pos < len(modified_text):
            chunk_to_translate = modified_text[last_pos:]
            if chunk_to_translate.strip():
                try:
                    translated_chunk = self.translator.translate(
                        chunk_to_translate, dest=target_lang).text
                    chunks.append(translated_chunk)
                except Exception as e:
                    print(f"Error translating: {e}")
                    chunks.append(chunk_to_translate)
            else:
                chunks.append(chunk_to_translate)

        # Combine and restore placeholders
        result = ''.join(chunks)
        for placeholder, original in placeholders.items():
            result = result.replace(placeholder, original)

        return result

    def translate_text(self, text, target_lang, translate_angle=False):
        """
        Main translation function with formatting preservation.

        Args:
            text: The text to translate
            target_lang: Target language code
            translate_angle: Whether to translate content in angle brackets

        Returns:
            Translated text with preserved formatting
        """
        if not isinstance(text, str) or not text.strip():
            return text

        # Save original for reference
        original_text = text

        # Extract code blocks and replace with placeholders
        processed_text, code_blocks = self.extract_code_blocks(text)

        # Replace variables with placeholders
        processed_text = self.protect_variables(processed_text)

        # Split text by segments that should be preserved intact
        segments = re.split(
            r'(\s*\{\{.*?\}\}\'?s?\s*|\s*\{.*?\}|<.*?>\'?s?\s*|__CODE_BLOCK_\d+__|__INLINE_CODE_\d+__)',
            processed_text)
        result = []

        for segment in segments:
            if not segment:
                continue

            # Skip translating template variables, bracketed content, and code blocks
            if (re.fullmatch(r'\s*(\{\{.*?\}\}|\{.*?\})(\'s)?\s*', segment, re.IGNORECASE) or
                    re.fullmatch(r'__CODE_BLOCK_\d+__|__INLINE_CODE_\d+__', segment)):
                result.append(segment)
                continue

            # Skip angle brackets content if not translating angle content
            if not translate_angle and re.fullmatch(r'\s*(<.*?>)(\'s)?\s*', segment, re.IGNORECASE):
                result.append(segment)
                continue

            # Split segment into smaller chunks
            chunks = self.chunker.split_into_chunks(segment)

            for chunk in chunks:
                if chunk == '\n':
                    result.append('\n')
                    continue

                if not chunk.strip():
                    result.append(chunk)
                    continue

                try:
                    # Pause between translations to avoid rate limiting
                    time.sleep(0.2)

                    # Store original for case preservation
                    original_chunk = chunk

                    # Translate chunk
                    translation = self.translator.translate(chunk, dest=target_lang).text
                    print(f"Original: {original_chunk}\nTranslated: {translation}\n")

                    # Apply formatting preservation
                    translation = self.formatter.preserve_case(original_chunk, translation)
                    translation = self.formatter.fix_capitalization(translation)

                    # Add spacing and join with previous chunks
                    words = translation.split()
                    if result and len(words) > 0:
                        prev_text = result[-1]

                        # Capitalize if previous chunk ended with period
                        if prev_text.strip().endswith('.'):
                            words[0] = words[0].capitalize()
                        # Uppercase if previous words were uppercase
                        elif len(prev_text) >= 2 and prev_text[-2:].isupper():
                            words[0] = words[0].upper()

                        # Add space if needed
                        translation = (
                            (" " if not prev_text.endswith((" ", "\n")) else "") +
                            " ".join(words)
                        )
                    else:
                        translation = " ".join(words)

                    # Improve spacing around punctuation
                    translation_spaced = ""
                    for i, char in enumerate(translation):
                        translation_spaced += char
                        if (char in ['.', ',', ';', ':'] and
                                i + 1 < len(translation) and
                                not translation[i + 1].isspace() and
                                translation[i + 1] not in [' ', ')', ']', '"', '\'']):
                            translation_spaced += ' '

                    result.append(translation_spaced.strip())

                except Exception as e:
                    print(f"Error translating chunk: {e}")
                    result.append(chunk)

        # Join chunks and apply initial formatting
        final_text = ''.join(result)
        final_text = self.formatter.adjust_punctuation_spacing(final_text)

        # Restore code blocks from placeholders
        final_text = self.restore_code_blocks(final_text, code_blocks)

        # Restore variables
        final_text = self.restore_variables(final_text)

        # Preserve the original spacing patterns
        final_text = self.formatter.preserve_spacing(original_text, final_text)

        return final_text

    def translate_json(self, data, target_lang, translate_angle=False, on_progress=None):
        """
        Recursively translates fields in a JSON structure.

        Args:
            data: JSON data structure (dict or list)
            target_lang: Target language code
            translate_angle: Whether to translate content in angle brackets
            on_progress: Callback function for progress updates

        Returns:
            Translated JSON structure
        """

        # Count total translatable fields
        def count_fields(data):
            count = 0
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in TARGET_FIELDS and isinstance(value, str):
                        count += 1
                    else:
                        count += count_fields(value)
            elif isinstance(data, list):
                for item in data:
                    count += count_fields(item)
            return count

        total_fields = count_fields(data)
        translated_fields = 0

        # Process the data recursively
        def process_data(data):
            nonlocal translated_fields

            if isinstance(data, dict):
                for key, value in data.items():
                    # Fix malformed placeholders in specific fields
                    if key in ["wi_format", "scenario_format"] and isinstance(value, str):
                        value = re.sub(r'{\s*{', "{{", value)
                        value = re.sub(r'}\s*}', "}}", value)
                        data[key] = value

                    # Translate target fields
                    if key in TARGET_FIELDS and isinstance(value, str):
                        if not value.strip():  # Skip empty fields
                            continue

                        try:
                            data[key] = self.translate_text(
                                value, target_lang, translate_angle)
                            translated_fields += 1

                            if on_progress:
                                on_progress(translated_fields, total_fields)

                        except Exception as e:
                            print(f"Error translating field {key}: {str(e)}")

                    # Process nested structures
                    elif isinstance(value, dict) or isinstance(value, list):
                        process_data(value)

            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) or isinstance(item, list):
                        process_data(item)

            return data

        return process_data(data)


class TranslatorApp:
    """Main application class."""

    def __init__(self, root):
        self.root = root
        self.config = TranslationConfig()
        self.engine = TranslationEngine()
        self.setup_ui()

    def ask_for_silly_tavern_path(self):
        """Ask user for SillyTavern root directory."""
        path = filedialog.askdirectory(
            title=self.config.get_text("select_silly_dir"),
            initialdir=os.path.expanduser("~")
        )
        if path:
            # Update path to include the OpenAI Settings folder structure
            settings_path = os.path.join(path, "data", "default-user", "OpenAI Settings")
            
            # Create the directory structure if it doesn't exist
            os.makedirs(settings_path, exist_ok=True)
            
            # Save the root path
            self.config.data["silly_tavern_path"] = path
            self.config.save()
            return True
        return False

    def save_location_preference(self, *args):
        """Saves the preferred save location."""
        new_location = self.save_location_var.get()
        self.config.data["save_location"] = new_location
        self.config.save()

    def setup_ui(self):
        """Sets up the user interface."""
        # Set window title with translation
        self.root.title(self.config.get_text("window_title"))

        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top section with language settings
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X)

        # Language selection area
        lang_frame = ttk.Frame(top_frame)
        lang_frame.pack(side=tk.LEFT, padx=(0, 200))

        ttk.Label(
            lang_frame,
            text=self.config.get_text("target_language"),
            font=("Arial", 10)
        ).pack(anchor=tk.W)

        self.lang_combobox = ttk.Combobox(
            lang_frame,
            values=list(self.config.languages.values()),  # Use native language names from config
            state="readonly",
            width=30
        )
        self.lang_combobox.pack(pady=(5, 0))

        # Set initial language selection using language codes as keys now
        current_lang = self.config.current_lang
        lang_names = list(self.config.languages.values())  # Native names
        lang_codes = list(self.config.languages.keys())  # Codes
        if current_lang in lang_codes:
            self.lang_combobox.set(lang_names[lang_codes.index(current_lang)])  # Set by index of code
        else:
            # Default to English if last used language is not found
            self.lang_combobox.set(lang_names[lang_codes.index("en")]) if "en" in lang_codes else self.lang_combobox.set(
                lang_names[0])

        self.lang_combobox.bind('<<ComboboxSelected>>', self.update_language)

        # Translation options
        self.translate_angle_var = tk.BooleanVar(value=self.config.data.get("translate_angle", False))
        self.angle_checkbox = ttk.Checkbutton(
            lang_frame,
            text=self.config.get_text("translate_angle"),
            variable=self.translate_angle_var
        )
        self.angle_checkbox.pack(pady=(5, 0), anchor=tk.W)
        self.translate_angle_var.trace('w', self.save_angle_preference)

        # Save location options
        save_frame = ttk.Frame(top_frame)
        save_frame.pack(side=tk.LEFT, fill=tk.X)

        self.save_location_var = tk.StringVar(value=self.config.data.get("save_location", "silly"))

        self.silly_radio = ttk.Radiobutton(
            save_frame,
            text=self.config.get_text("save_silly"),
            variable=self.save_location_var,
            value="silly"
        )
        self.silly_radio.pack(anchor=tk.W)

        self.custom_radio = ttk.Radiobutton(
            save_frame,
            text=self.config.get_text("save_custom"),
            variable=self.save_location_var, value="custom"
        )
        self.custom_radio.pack(anchor=tk.W)
        self.save_location_var.trace('w', self.save_location_preference)

        # File selection
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=tk.X, pady=(10, 5))

        ttk.Label(file_frame, text=self.config.get_text("select_files"), font=("Arial", 10, "bold")).pack(anchor=tk.W)

        self.file_list = tk.Listbox(file_frame, selectmode="multiple", height=5, width=50)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(file_frame)
        button_frame.pack(side=tk.LEFT, padx=(5, 0))

        select_button = ttk.Button(button_frame, text=self.config.get_text("select_files"),
                                   command=self.select_files)  # Changed button text to "select_files"
        select_button.pack(pady=2, fill=tk.X)

        remove_button = ttk.Button(button_frame, text=self.config.get_text("remove_button"),
                                   command=self.remove_selected_files)
        remove_button.pack(pady=2, fill=tk.X)

        # Progress bar
        self.progress_bar = ttk.Progressbar(main_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(10, 2))

        # Status label
        self.status_label = ttk.Label(main_frame, text="", font=("Arial", 9))
        self.status_label.pack(pady=(0, 10))

        # Translate button
        self.translate_button = ttk.Button(main_frame, text=self.config.get_text("start_translation"),
                                           command=self.start_translation)  # Changed button text to "start_translation"
        self.translate_button.pack()

        # Bind resize event
        self.root.bind("<Configure>", self.on_resize)

        # Initialize UI text based on current language
        self.reload_ui_text()

    def reload_ui_text(self):
        """Updates UI text elements with current language."""
        self.root.title(self.config.get_text("window_title"))

        lang_frame = self.lang_combobox.master
        for widget in lang_frame.winfo_children():
            if isinstance(widget, ttk.Label) and widget.winfo_ismapped():
                widget.config(text=self.config.get_text("target_language"))
        self.angle_checkbox.config(text=self.config.get_text("translate_angle"))
        save_frame = self.silly_radio.master
        self.silly_radio.config(text=self.config.get_text("save_silly"))
        self.custom_radio.config(text=self.config.get_text("save_custom"))
        file_frame = self.file_list.master
        for widget in file_frame.winfo_children():
            if isinstance(widget, ttk.Label) and widget.winfo_ismapped():
                widget.config(text=self.config.get_text("select_files"))
        button_frame = self.file_list.master.winfo_children()[1]
        for widget in button_frame.winfo_children():
            if isinstance(widget, ttk.Button):
                if widget == button_frame.winfo_children()[0]:  # First button
                    widget.config(text=self.config.get_text("select_files"))
                elif widget == button_frame.winfo_children()[1]:  # Second button
                    widget.config(text=self.config.get_text("remove_button"))
        self.translate_button.config(text=self.config.get_text("start_translation"))

    def on_resize(self, event=None):
        """Handles window resizing."""
        self.file_list.configure(width=int(self.root.winfo_width() / 8))

    def update_language(self, event=None):
        """Updates the UI language based on selection."""
        selected_lang_native_name = self.lang_combobox.get()
        lang_code = ""
        for code, native_name in self.config.languages.items():
            if native_name == selected_lang_native_name:
                lang_code = code
                break

        if lang_code:
            self.config.current_lang = lang_code
            self.config.data["last_used_language"] = self.config.current_lang
            self.config.save()

            # Reload UI elements to apply changes
            self.reload_ui_text()

        else:
            print("Error: Selected language not found in language data.")

    def reload_ui(self):
        """Destroys and recreates UI elements to apply language."""
        for widget in self.root.winfo_children():
            widget.destroy()

        self.setup_ui()

    def save_angle_preference(self, *args):
        """Saves the preference for translating content in angle."""
        self.config.data["translate_angle"] = self.translate_angle_var.get()
        self.config.save()

    def select_files(self):
        """Opens file dialog to select JSON files."""
        # Set initial directory based on save location
        if self.save_location_var.get() == "silly" and self.config.data.get("silly_tavern_path"):
            initial_dir = os.path.join(
                self.config.data["silly_tavern_path"],
                "data", "default-user", "OpenAI Settings"
            )
        else:
            initial_dir = os.path.expanduser("~")

        if not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")

        filetypes = (
            (self.config.get_text("json_filetype"), "*.json"),
            (self.config.get_text("all_filetype"), "*.*")
        )

        filenames = filedialog.askopenfilenames(
            initialdir=initial_dir,
            title=self.config.get_text("select_files"),
            filetypes=filetypes
        )

        for filename in filenames:
            if filename not in self.file_list.get(0, tk.END):
                self.file_list.insert(tk.END, filename)

    def remove_selected_files(self):
        """Removes selected files from the list."""
        selected_indices = self.file_list.curselection()
        for index in reversed(selected_indices):
            self.file_list.delete(index)

    def start_translation(self):
        """Starts the translation process, handling SillyTavern path."""
        selected_files = self.file_list.get(0, tk.END)
        if not selected_files:
            messagebox.showwarning(
                self.config.get_text("no_files_selected_title"),
                self.config.get_text("no_files_selected_message")
            )
            return

        # Check for SillyTavern path if saving to SillyTavern
        save_location = self.save_location_var.get()
        if save_location == "silly" and not self.config.data["silly_tavern_path"]:
            if not self.ask_for_silly_tavern_path():
                return  # Don't proceed if path not set

        target_language_native_name = self.lang_combobox.get()
        target_language_code = ""
        for code, native_name in self.config.languages.items():
            if native_name == target_language_native_name:
                target_language_code = code
                break

        translate_angle = self.translate_angle_var.get()

        self.progress_bar['value'] = 0
        self.translate_button.config(state=tk.DISABLED)

        translation_thread = threading.Thread(
            target=self.translate_selected_files,
            args=(selected_files, target_language_code, translate_angle, save_location)
        )
        translation_thread.start()

    def translate_selected_files(self, files, target_lang, translate_angle, save_location):
        """Translates selected JSON files and saves them."""
        total_files = len(files)

        for file_index, file_path in enumerate(files):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                def update_progress(translated_fields, total_fields):
                    """Updates progress for the current file."""
                    file_progress = (translated_fields / total_fields) * 100
                    overall_progress = ((file_index + (file_progress / 100)) / total_files) * 100

                    self.progress_bar['value'] = overall_progress
                    self.status_label.config(
                        text=self.config.get_text("translating_file_status").format(
                            os.path.basename(file_path),
                            file_index + 1,
                            total_files,
                            int(file_progress)
                        )
                    )
                    self.root.update_idletasks()

                translated_data = self.engine.translate_json(
                    data, target_lang, translate_angle, update_progress)

                # Determine save path
                if save_location == "custom":
                    save_path = filedialog.asksaveasfilename(
                        defaultextension=".json",
                        filetypes=((self.config.get_text("json_filetype"), "*.json"),
                                   (self.config.get_text("all_filetype"), "*.*")),
                        initialfile=os.path.basename(file_path),
                        title=self.config.get_text("save_translated_title")
                    )

                    if not save_path:
                        continue  # Skip if user cancels save dialog

                elif save_location == "silly":
                    # Use the OpenAI Settings path directly
                    settings_path = os.path.join(
                        self.config.data["silly_tavern_path"],
                        "data", "default-user", "OpenAI Settings"
                    )
                    
                    # Create directory if it doesn't exist
                    os.makedirs(settings_path, exist_ok=True)
                    
                    # Create save path with _translated suffix
                    original_filename = os.path.basename(file_path)
                    filename_no_ext = os.path.splitext(original_filename)[0]
                    save_path = os.path.join(settings_path, f"{filename_no_ext}_translated.json")

                # Save the translated file
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(translated_data, f, indent=4, ensure_ascii=False)

            except Exception as e:
                messagebox.showerror(
                    self.config.get_text("translation_error_title"),
                    self.config.get_text("translation_error_message").format(file_path, str(e))
                )
                self.status_label.config(text=self.config.get_text("translation_failed"))
                self.translate_button.config(state=tk.NORMAL)
                return  # Stop if an error occurs

        # Completion
        self.status_label.config(text=self.config.get_text("translation_complete"))
        self.progress_bar['value'] = 100
        self.translate_button.config(state=tk.NORMAL)
        messagebox.showinfo(
            self.config.get_text("translation_done_title"),
            self.config.get_text("translation_done_message")
        )


if __name__ == "__main__":
    root = tk.Tk()
    root.title("SillyTavern JSON Translator")
    root.geometry("600x400")
    app = TranslatorApp(root)
    root.mainloop()