import os
import json
import base64
import hashlib
import subprocess
import re
import time
import msvcrt  # Para capturar entrada do teclado no Windows
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image, PngImagePlugin  # novo
from colorama import init, Fore, Style
from typing import Dict, Any
import tkinter as tk
from tkinter import filedialog

init(autoreset=True)  # Initialize colorama

# Configuration
CHARACTERS_DIR = Path(r"E:\Games\SillyTavern-1.12.11\data\default-user\characters")
ORIGINAL_DIR = Path(".\\Original")
DB_FILE = Path(".\\translation_db.json")
TRANSLATION_SETTINGS_FILE = Path(".\\translation_settings.json")
INTERFACE_LANG_FILE = Path(".\\lang\\interface_languages.json")

LANGUAGES = {
    'pt': 'Português',
    'en': 'English',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch',
    'it': 'Italiano',
    'ja': '日本語',
    'zh-cn': '中文',
    'ko': '한국어',
    'ru': 'Русский'
}

PLACEHOLDER_MAP = {
    'pt': {
        'usuário': 'user',
        'usuario': 'user',
        'personagem': 'char',
        'caractere': 'char',
        'caracter': 'char',
        "usuário's": "user's",
        "usuario's": "user's",
        "personagem's": "char's",
        "caractere's": "char's",
        "caracter's": "char's"
    },
    'es': {
        'usuario': 'user',
        'personaje': 'char',
        'caracter': 'char',
        "usuario's": "user's",
        "personaje's": "char's",
        "caracter's": "char's"
    },
    'fr': {
        'utilisateur': 'user',
        'personnage': 'char',
        'caractère': 'char',
        'caractere': 'char',
        "utilisateur's": "user's",
        "personnage's": "char's",
        "caractère's": "char's",
        "caractere's": "char's"
    },
    'de': {
        'benutzer': 'user',
        'charakter': 'char',
        'benutzers': "user's",
        'charakters': "char's"
    },
    'it': {
        'utente': 'user',
        'personaggio': 'char',
        "utente's": "user's",
        "personaggio's": "char's"
    },
    'ja': {
        'ユーザー': 'user',
        'キャラクター': 'char',
        'ユーザーの': "user's",
        'キャラクターの': "char's"
    },
    'zh-cn': {
        '用户': 'user',
        '角色': 'char',
        '用户的': "user's",
        '角色的': "char's"
    },
    'ko': {
        '사용자': 'user',
        '캐릭터': 'char',
        '사용자의': "user's",
        '캐릭터의': "char's"
    },
    'ru': {
        'пользователь': 'user',
        'персонаж': 'char',
        'пользователя': "user's",
        'персонажа': "char's"
    }
}

class CharacterProcessor:
    def __init__(self):
        self.translation_settings = self.load_translation_settings()
        self.apply_translation_settings()
        self.set_translator_service()
        self.db = self.load_db()
        self.setup_dirs()
        self.monitoring = False
        self.interface_texts = self.load_interface_texts()
        self.characters_dir = self.translation_settings.get('characters_dir', '')
        
        # Patterns to exclude from translation
        self.excluded_patterns = [
            r'!\[.*?\]\(.*?\)',  # Image links
            r'https?://\S+',     # URLs
            r'www\.\S+',         # www URLs
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email addresses
        ]
    
    def setup_dirs(self):
        ORIGINAL_DIR.mkdir(exist_ok=True, parents=True)

    def load_db(self):
        try:
            if DB_FILE.exists():
                return json.loads(DB_FILE.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"Error loading database: {e}")
        return {}
    
    def load_translation_settings(self):
        default_settings = {
            'target_lang': 'pt',
            'translate_angle': False,
            'translate_name': False,
            'interface_lang': 'pt',
            'translation_service': 'google',
            'characters_dir': '',
            'translate_parentheses': False,
            'translate_brackets': False,
            'use_jane': False
        }
        try:
            if TRANSLATION_SETTINGS_FILE.exists():
                return json.loads(TRANSLATION_SETTINGS_FILE.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        TRANSLATION_SETTINGS_FILE.write_text(json.dumps(default_settings, indent=2))
        return default_settings
    
    def apply_translation_settings(self):
        self.target_lang = self.translation_settings.get('target_lang', 'pt')
        self.translate_name = self.translation_settings.get('translate_name', False)
        self.translate_angle = self.translation_settings.get('translate_angle', False)
        self.translation_service = self.translation_settings.get('translation_service', 'google')
        self.interface_lang = self.translation_settings.get('interface_lang', 'pt')
        self.translate_parentheses = self.translation_settings.get('translate_parentheses', False)
        self.translate_brackets = self.translation_settings.get('translate_brackets', False)
        self.use_jane = self.translation_settings.get('use_jane', False)

    def set_translator_service(self):
        if self.translation_service == 'google':
            from lib.free_translator import GoogleTranslatorService
            self.translator = GoogleTranslatorService()
        elif self.translation_service == 'mymemory':
            from lib.mymemory_translator import MyMemoryTranslatorService
            self.translator = MyMemoryTranslatorService()
        else:
            from lib.free_translator import GoogleTranslatorService
            self.translator = GoogleTranslatorService()

    def save_translation_settings(self):
        self.translation_settings.update({
            'target_lang': self.target_lang,
            'translate_angle': self.translate_angle,
            'translate_name': self.translate_name,
            'interface_lang': self.interface_lang,
            'translation_service': self.translation_service,
            'characters_dir': self.characters_dir,
            'translate_parentheses': self.translate_parentheses,
            'translate_brackets': self.translate_brackets,
            'use_jane': self.use_jane
        })
        TRANSLATION_SETTINGS_FILE.write_text(json.dumps(self.translation_settings, indent=2))

    def get_file_hash(self, file_path):
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def extract_character_data(self, image_path):
        """Extract character data from PNG image using exiftool"""
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Use exiftool to extract the chara property
            cmd = ['exiftool', '-b', '-chara', str(image_path)]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='ignore'
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0 or not stdout:
                print(f"Error extracting character data: {stderr}")
                return None
            
            # Decode base64 and parse JSON
            decoded_data = base64.b64decode(stdout.strip()).decode('utf-8')
            char_data = json.loads(decoded_data)
            
            return char_data
        except Exception as e:
            print(f"Error extracting character data: {e}")
            return None

    def protect_markdown_links(self, text):
        """Protect markdown image links and URLs from translation with improved handling"""
        protected_segments = {}
        token_count = 0
        
        # Padrão específico para links de imagem markdown
        image_pattern = r'!\[([^\]]*)\]\(([^)]*)\)'
        
        # Substituir links de imagem primeiro
        def replace_image_link(match):
            nonlocal token_count
            token = f"__PROTECTED_{token_count}__"
            token_count += 1
            
            # Armazenar o link completo com alt text e URL
            alt_text = match.group(1)
            url = match.group(2)
            protected_segments[token] = {
                'type': 'image',
                'alt': alt_text,
                'url': url,
                'original': match.group(0)
            }
            return token
        
        text = re.sub(image_pattern, replace_image_link, text)
        
        # Processar outros padrões a serem excluídos da tradução
        other_patterns = [
            r'https?://\S+',     # URLs
            r'www\.\S+',         # www URLs
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email addresses
        ]
        
        for pattern in other_patterns:
            def replace_match(match):
                nonlocal token_count
                token = f"__PROTECTED_{token_count}__"
                token_count += 1
                protected_segments[token] = {
                    'type': 'text',
                    'content': match.group(0),
                    'original': match.group(0)
                }
                return token
            
            text = re.sub(pattern, replace_match, text)
        
        return text, protected_segments
    
    def process_formatting_wrappers(self, text):
        """Recursively process text with nested formatting wrappers"""
        # Define formatting wrappers in order of precedence (outermost to innermost)
        formatters = [
            (r'\[([^\[\]]*)\]', '[', ']'),           # Square brackets
            (r'\{([^\{\}]*)\}', '{', '}'),           # Curly brackets
            (r'```([\s\S]*?)```', '```', '```'),     # Code blocks
            (r'`([^`]*)`', '`', '`'),                # Inline code
            (r'\(([^\(\)]*)\)', '(', ')'),           # Parentheses
            (r'"([^"]*)"', '"', '"'),                # Double quotes
            (r'\*\*(.*?)\*\*', '**', '**'),          # Bold
            (r'\*(.*?)\*', '*', '*')                 # Italic
        ]
        
        protected_map = {}
        token_counter = 0
        
        # First pass - find all matches and protect them
        for pattern, start_delim, end_delim in formatters:
            def process_match(match):
                nonlocal token_counter
                inner_content = match.group(1)
                
                # Recursively process inner content if needed
                processed_inner = self.process_formatting_wrappers(inner_content)
                
                # Generate a unique token
                token = f"__FORMAT_{token_counter}__"
                token_counter += 1
                
                # Store the information needed to restore this later
                protected_map[token] = {
                    'start_delim': start_delim,
                    'end_delim': end_delim,
                    'content': processed_inner
                }
                
                return token
            
            text = re.sub(pattern, process_match, text)
        
        return text, protected_map

    def restore_protected_segments(self, text, protected_segments):
        """Restore protected segments after translation with improved handling"""
        for token, info in protected_segments.items():
            if info['type'] == 'image':
                # Reconstruir o link de imagem com o formato original
                replacement = f"![{info['alt']}]({info['url']})"
            else:
                # Para outros tipos de conteúdo protegido
                replacement = info['original']
            
            text = text.replace(token, replacement)
        
        return text

    def split_by_newlines(self, text):
        """Split text by newlines and preserve the newline character"""
        if not text:
            return []
        
        segments = []
        current_position = 0
        
        for match in re.finditer(r'\n', text):
            end_pos = match.start()
            segment = text[current_position:end_pos]
            segments.append((segment, '\n'))
            current_position = match.end()
        
        # Add the final segment if there is any text remaining
        if current_position < len(text):
            segments.append((text[current_position:], ''))
        
        return segments

    def split_by_delimiters(self, text, delim_open, delim_close):
        """Split text by delimiters with proper handling of multiple occurrences"""
        if not text:
            return []
        
        result = []
        current_pos = 0
        text_length = len(text)
        
        while current_pos < text_length:
            # Find next opening delimiter
            open_pos = text.find(delim_open, current_pos)
            
            if open_pos == -1:
                # No more opening delimiters, add remaining text
                if current_pos < text_length:
                    result.append((text[current_pos:], None))
                break
            
            # Add text before the opening delimiter
            if open_pos > current_pos:
                result.append((text[current_pos:open_pos], None))
            
            # Find matching closing delimiter
            close_pos = text.find(delim_close, open_pos + len(delim_open))
            if close_pos == -1:
                # No matching closing delimiter, treat as regular text
                result.append((text[open_pos:], None))
                break
            
            # Extract the delimited content including delimiters
            delimited_content = text[open_pos:close_pos + len(delim_close)]
            result.append((delimited_content, (delim_open, delim_close)))
            
            # Move position past the closing delimiter
            current_pos = close_pos + len(delim_close)
        
        return result

    def process_placeholders(self, text, char_name=None):
        """Process {{user}} and {{char}} placeholders before translation"""
        processed_text = text
        placeholders = {}
        
        # Mark all placeholders with unique IDs
        for i, match in enumerate(re.finditer(r'\{\{(\w+)(?:\'s)?\}\}', text)):
            full_match = match.group(0)
            placeholder_token = f"__PH_{i}__"
            placeholders[placeholder_token] = full_match
            processed_text = processed_text.replace(full_match, placeholder_token, 1)
        
        # Replace special placeholders with translation-friendly text
        char_replacement = "Jane" if self.use_jane else (char_name if char_name else "{{char}}")
        
        for token, original in placeholders.items():
            if "{{user}}'s" in original:
                processed_text = processed_text.replace(token, "James's")
            elif "{{char}}'s" in original:
                processed_text = processed_text.replace(token, f"{char_replacement}'s")
            elif "{{user}}" in original:
                processed_text = processed_text.replace(token, "James")
            elif "{{char}}" in original or "{{assistant}}" in original:
                processed_text = processed_text.replace(token, char_replacement)
        
        return processed_text, placeholders

    def restore_placeholders(self, text, placeholders, char_name=None):
        """Restore {{user}} and {{char}} placeholders after translation"""
        restored_text = text
        
        # First, replace any direct translations of the placeholder texts
        char_replacement = "Jane" if self.use_jane else (char_name if char_name else "{{char}}")
        
        restored_text = restored_text.replace("James's", "{{user}}'s")
        restored_text = restored_text.replace(f"{char_replacement}'s", "{{char}}'s")
        restored_text = restored_text.replace("James", "{{user}}")
        restored_text = restored_text.replace(char_replacement, "{{char}}")
        
        # Then restore any remaining placeholder tokens
        for token, original in placeholders.items():
            restored_text = restored_text.replace(token, original)
        
        return restored_text
    
    def translate_with_placeholders(self, text, char_name=None):
        """Translate text with placeholder handling"""
        if not text or not text.strip():
            return text
            
        # Process placeholders
        processed_text, placeholders = self.process_placeholders(text, char_name)
        
        try:
            translated = self.translator.translate(processed_text, dest=self.target_lang).text
            if translated is None:
                return text
        except Exception as e:
            print(f"Translation error: {e}")
            return text
        
        # Restore placeholders
        final_text = self.restore_placeholders(translated, placeholders, char_name)
        final_text = self.fix_special_characters(final_text)
        
        return final_text
    
    def restore_formatting(self, text, protected_map):
        """Restore formatting wrappers to translated text"""
        result = text
        
        # Keep restoring until no more tokens are found
        while any(token in result for token in protected_map):
            for token, info in protected_map.items():
                if token in result:
                    # If inner content has its own token, restore that first
                    inner_content = info['content']
                    replacement = f"{info['start_delim']}{inner_content}{info['end_delim']}"
                    result = result.replace(token, replacement)
        
        return result
    
    def fix_malformed_brackets(self, text):
        """Fix and standardize placeholder brackets"""
        if not text:
            return text
        
        # Remove duplicate braces
        text = re.sub(r'\{{2,}', '{{', text)
        text = re.sub(r'\}{2,}', '}}', text)
        
        # Fix spacing inside braces
        text = re.sub(r'\{+\s*(\w+)\s*\}+', r'{{\1}}', text)
        
        # Standardize assistant to char
        text = re.sub(r'\{\{?\s*assistant\s*\}?\}', '{{char}}', text, flags=re.IGNORECASE)
        
        # Ensure no duplicate braces
        text = re.sub(r'\{{2,}', '{{', text)
        text = re.sub(r'\}{2,}', '}}', text)
        
        return text
    
    def translate_inner_segment(self, text, char_name=None):
        """Translate the inner content of a segment without delimiters"""
        if not text or not text.strip():
            return text
        
        # Protect markdown links and other patterns
        protected_text, protected_segments = self.protect_markdown_links(text)
        
        # Process placeholders
        processed_text, placeholders = self.process_placeholders(protected_text, char_name)
        
        # Perform translation
        try:
            translated = self.translator.translate(processed_text, dest=self.target_lang).text
            if translated is None:
                return text
        except Exception as e:
            print(f"Translation error: {e}")
            return text
        
        # Restore placeholders
        restored_text = self.restore_placeholders(translated, placeholders, char_name)
        
        # Restore protected segments
        final_text = self.restore_protected_segments(restored_text, protected_segments)
        
        # Fix any malformed bracket placeholders
        final_text = self.fix_malformed_brackets(final_text)
        
        # Fix special characters like tildes and hyphens
        final_text = self.fix_special_characters(final_text)
        
        return final_text

    def fix_special_characters(self, text):
        """Fix special characters like ~ and - according to the requirements"""
        if not text:
            return text
        
        # Fix tildes attached to characters
        text = re.sub(r'(\S)\s+~', r'\1~', text)
        text = re.sub(r'~\s+(\S)', r'~\1', text)
        
        # Fix hyphens with spaces (capturando todas as variações)
        text = re.sub(r'(\w+)\s+-\s+(\w+)', r'\1-\2', text)  # espaço antes e depois
        text = re.sub(r'(\w+)\s+-(\w+)', r'\1-\2', text)      # espaço só antes
        text = re.sub(r'(\w+)-\s+(\w+)', r'\1-\2', text)      # espaço só depois
        
        return text

    def translate_segment(self, text, char_name=None):
        """Translate a segment of text with proper placeholder handling"""
        if not text or not text.strip():
            return text
        
        # Determine if this segment contains delimiters
        has_open_delim = False
        has_close_delim = False
        
        for delim_pair in [('**', '**'), ('*', '*'), ('"', '"'), ('(', ')'), ('[', ']')]:
            open_delim, close_delim = delim_pair
            if text.startswith(open_delim):
                has_open_delim = True
            if text.endswith(close_delim):
                has_close_delim = True
        
        # If this segment has delimiters, extract the inner content
        if has_open_delim and has_close_delim:
            # Find the opening and closing delimiters
            open_delim = None
            close_delim = None
            
            for delim_pair in [('**', '**'), ('*', '*'), ('"', '"'), ('(', ')'), ('[', ']')]:
                o_delim, c_delim = delim_pair
                if text.startswith(o_delim) and text.endswith(c_delim):
                    open_delim = o_delim
                    close_delim = c_delim
                    break
            
            if open_delim and close_delim:
                inner_text = text[len(open_delim):-len(close_delim)]
                translated_inner = self.translate_inner_segment(inner_text, char_name)
                return f"{open_delim}{translated_inner}{close_delim}"
        
        # Regular segment translation
        return self.translate_inner_segment(text, char_name)

    def process_complex_structure(self, text):
        """Process complex structures like JSON objects with nested delimiters"""
        
        # Regex para detectar padrões complexos de estrutura
        json_pattern = r'(\[|\{)([^\[\]{}]*?(?:\[|\{.*?\}|\])[^\[\]{}]*?)(\]|\})'
        
        # Processa estruturas complexas recursivamente
        def process_recursively(match):
            open_bracket = match.group(1)
            content = match.group(2)
            close_bracket = match.group(3)
            
            # Processa o conteúdo recursivamente
            processed_content = re.sub(json_pattern, process_recursively, content)
            
            # Encontra padrões de atributos-valores (como "character":("texto"))
            attr_pattern = r'(["\'])(\w+)(["\'])\s*:\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)'
            
            def process_attr_value(attr_match):
                attr_quote = attr_match.group(1)
                attr_name = attr_match.group(2)
                attr_end_quote = attr_match.group(3)
                attr_value = attr_match.group(4)
                
                # Traduz apenas o valor dentro dos parênteses sem os parênteses
                translated_value = self.translate_segment(attr_value, None)
                
                return f'{attr_quote}{attr_name}{attr_end_quote}:({translated_value})'
            
            processed_content = re.sub(attr_pattern, process_attr_value, processed_content)
            
            return f'{open_bracket}{processed_content}{close_bracket}'
        
        # Aplica o processamento recursivo a todo o texto
        processed_text = re.sub(json_pattern, process_recursively, text)
        
        return processed_text

    def translate_text(self, text, char_name=None):
        """Translate text with special handling for delimiters and line breaks"""
        if not isinstance(text, str) or not text.strip():
            return text
        
        # Protect markdown links and other patterns first
        protected_text, protected_segments = self.protect_markdown_links(text)
        
        # Split by newlines first
        segments = self.split_by_newlines(protected_text)
        translated_segments = []
        
        for segment, newline in segments:
            # Process segment if it's not empty
            if segment.strip():
                # Process all delimiters in sequence
                # Incluindo underscores (_..._) na lista de delimitadores
                for delim_pair in [('"', '"'), ('**', '**'), ('*', '*'), ('_', '_'), ('(', ')'), ('[', ']')]:
                    delim_open, delim_close = delim_pair
                    quote_segments = self.split_by_delimiters(segment, delim_open, delim_close)
                    processed_parts = []
                    
                    for part, delimiters in quote_segments:
                        if delimiters:
                            # This is a delimited part
                            open_delim, close_delim = delimiters
                            # Extract only inner content
                            inner_text = part[len(open_delim):-len(close_delim)]
                            # Recursively process inner content
                            translated_inner = self.translate_segment(inner_text, char_name)
                            processed_parts.append(f"{open_delim}{translated_inner}{close_delim}")
                        else:
                            processed_parts.append(part)
                    
                    # Update segment for next delimiter processing
                    segment = ''.join(processed_parts)
                
                translated_segments.append(segment + newline)
            else:
                # Keep empty segments
                translated_segments.append(segment + newline)
        
        # Join all segments back together
        result = ''.join(translated_segments)
        
        # Restore protected segments
        result = self.restore_protected_segments(result, protected_segments)
        
        # Fix any special characters
        result = self.fix_special_characters(result)
        
        return result

    def process_character(self, image_path):
        """Process a character card for translation"""
        if image_path.name in self.db:
            return

        print(f"{Fore.YELLOW}{self.get_text('debug.processing_file', 'Processing file')}: {image_path.name}{Style.RESET_ALL}")
        
        # Move the original file to ORIGINAL_DIR
        original_file = self.move_to_original(image_path)
        
        # Extract character data using exiftool
        char_data = self.extract_character_data(original_file)
        if not char_data:
            print(f"{Fore.RED}Failed to extract character data from {original_file}{Style.RESET_ALL}")
            return
        
        # Make a deep copy of the character data for translation
        translated_data = self.deep_copy_data(char_data)
        
        # Get the original character name
        original_name = self.get_character_name(char_data)
        if not original_name:
            original_name = original_file.stem
        
        # Translate fields
        self.translate_character_data(translated_data, original_name)
        
        # Save the translated character card
        self.save_translated_card(original_file, translated_data)
        
        # Update the database
        self.db[original_file.name] = self.get_file_hash(original_file)
        self.save_db()
        
        print(f"{Fore.GREEN}Successfully translated {original_file.name}{Style.RESET_ALL}")

    def deep_copy_data(self, data):
        """Make a deep copy of the character data structure"""
        if isinstance(data, dict):
            return {k: self.deep_copy_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.deep_copy_data(item) for item in data]
        else:
            return data

    def get_character_name(self, data):
        """Extract character name from the data structure"""
        if isinstance(data, dict):
            if 'name' in data:
                return data['name']
            elif 'data' in data and isinstance(data['data'], dict) and 'name' in data['data']:
                return data['data']['name']
        return None

    def translate_character_data(self, data, original_name):
        """Translate all relevant fields in the character data"""
        if not isinstance(data, dict):
            return
        
        # Fields that need to be translated
        translatable_fields = {
            'name': self.translate_name,  # Only translate if enabled
            'description': True,
            'personality': True,
            'scenario': True,
            'first_mes': True,
            'mes_example': True,
            'system_prompt': True,
            'post_history_instructions': True,
            'creator_notes': True
        }
        
        # Process fields in the root level
        for field, should_translate in translatable_fields.items():
            if field in data and isinstance(data[field], str) and should_translate:
                data[field] = self.translate_text(data[field], original_name)
        
        # Process fields in the 'data' dictionary if it exists
        if 'data' in data and isinstance(data['data'], dict):
            for field, should_translate in translatable_fields.items():
                if field in data['data'] and isinstance(data['data'][field], str) and should_translate:
                    data['data'][field] = self.translate_text(data['data'][field], original_name)
        
        # Process alternate_greetings if they exist
        if 'alternate_greetings' in data and isinstance(data['alternate_greetings'], list):
            data['alternate_greetings'] = [
                self.translate_text(greeting, original_name) 
                for greeting in data['alternate_greetings'] 
                if isinstance(greeting, str)
            ]
        
        if 'data' in data and 'alternate_greetings' in data['data'] and isinstance(data['data']['alternate_greetings'], list):
            data['data']['alternate_greetings'] = [
                self.translate_text(greeting, original_name) 
                for greeting in data['data']['alternate_greetings'] 
                if isinstance(greeting, str)
            ]

    def move_to_original(self, image_path):
        """Move the original PNG file to the ORIGINAL_DIR directory"""
        dest = ORIGINAL_DIR / image_path.name
        if not dest.exists():
            try:
                os.rename(image_path, dest)
                print(f"{Fore.BLUE}File moved: {image_path.name} to {ORIGINAL_DIR}{Style.RESET_ALL}")
            except Exception as e:
                print(f"Error moving file: {e}")
        return dest

    def save_translated_card(self, original_file, translated_data):
        """Save the translated character data as a new PNG file"""
        try:
            # Nullify 'chat' and 'create_date' fields
            translated_data['chat'] = None
            translated_data['create_date'] = None
            
            # Convert the data structure to a JSON string
            json_str = json.dumps(translated_data, ensure_ascii=False, separators=(',', ':'))
            
            # Encode the JSON as base64
            b64_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            
            # Open the original image
            img = Image.open(original_file)
            
            # Create PNG metadata container
            meta = PngImagePlugin.PngInfo()
            
            # Add the translated data as 'chara' property
            meta.add_text("chara", b64_data)
            
            # Save the new image to CHARACTERS_DIR
            new_image_path = CHARACTERS_DIR / original_file.name
            img.save(new_image_path, "PNG", pnginfo=meta)
            
            print(f"{Fore.GREEN}Translated card saved: {new_image_path}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Error saving translated card: {e}{Style.RESET_ALL}")

    def save_db(self):
        """Save the translation database"""
        try:
            DB_FILE.write_text(json.dumps(self.db, indent=2))
        except Exception as e:
            print(f"Error saving database: {e}")

    def process_existing_files(self):
        """Process all existing character cards in the directory"""
        print(f"\n{self.get_text('debug.processing_existing', 'Processing existing files')}")
        for file in CHARACTERS_DIR.glob('*.png'):
            if file.name not in self.db or self.db[file.name] != self.get_file_hash(file):
                self.process_character(file)

    def load_interface_texts(self) -> Dict[str, Any]:
        """Load interface texts for the selected language"""
        try:
            if INTERFACE_LANG_FILE.exists():
                data = json.loads(INTERFACE_LANG_FILE.read_text(encoding='utf-8'))
                return data.get(self.interface_lang, data['en'])  # fallback to English
            else:
                print("Interface language file not found!")
                return {}
        except Exception as e:
            print(f"Error loading interface texts: {e}")
            return {}
            
    def get_text(self, key: str, default: str = "") -> str:
        """Get interface text by key path (e.g., 'menu.exit')"""
        try:
            value = self.interface_texts
            for k in key.split('.'):
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def verify_characters_dir(self):
        """Verify if the characters directory is valid"""
        if not self.characters_dir:
            return False
        characters_path = Path(self.characters_dir)
        return (characters_path.exists() and 
                characters_path.is_dir() and 
                characters_path.name == 'characters' and 
                'data' in characters_path.parts and 
                'default-user' in characters_path.parts)

class CharacterHandler(FileSystemEventHandler):
    def __init__(self, processor):
        self.processor = processor

def show_current_settings(processor):
    print(f"\n{Fore.YELLOW}=== {processor.get_text('settings')} ==={Style.RESET_ALL}")
    
    # Interface language uses the native name
    print(f"{processor.get_text('interface_language')}: {LANGUAGES.get(processor.interface_lang, 'Unknown')}")
    
    # Translation language uses the name from 'others' in current interface language
    target_lang_name = processor.interface_texts.get('others', {}).get(processor.target_lang, LANGUAGES.get(processor.target_lang, 'Unknown'))
    print(f"{processor.get_text('translation_language')}: {target_lang_name}")
    
    print(f"{processor.get_text('translation_service')}: {processor.translation_service}")
    status = processor.get_text('status.on') if processor.monitoring else processor.get_text('status.off')
    print(f"{processor.get_text('monitoring')}: {status}")
    backup_count = len(list(ORIGINAL_DIR.glob('*.png')))
    print(f"{processor.get_text('backup_files')}: {backup_count}")

def show_menu(processor):
    while True:
        show_current_settings(processor)
        
        print(f"\n{Fore.BLUE}=== {processor.get_text('main_menu')} ==={Style.RESET_ALL}")
        print(f"{Fore.GREEN}1.{Style.RESET_ALL} {processor.get_text('menu.start_monitoring')}")
        
        print(f"\n{Fore.YELLOW}=== {processor.get_text('settings')} ==={Style.RESET_ALL}")
        print(f"{Fore.GREEN}2.{Style.RESET_ALL} {processor.get_text('menu.clear_translation_data')}")
        print(f"{Fore.GREEN}3.{Style.RESET_ALL} {processor.get_text('menu.restore_originals')}")
        print(f"{Fore.GREEN}4.{Style.RESET_ALL} {processor.get_text('menu.configure_translation')}")
        print(f"{Fore.GREEN}5.{Style.RESET_ALL} {processor.get_text('menu.select_translation_service')}")
        print(f"{Fore.GREEN}6.{Style.RESET_ALL} {processor.get_text('menu.configure_interface')}")
        print(f"{Fore.GREEN}7.{Style.RESET_ALL} {processor.get_text('menu.select_directory')}" + 
              (f" {Fore.RED}{processor.get_text('prompts.directory_required')}{Style.RESET_ALL}" 
               if not processor.verify_characters_dir() else ""))
        print(f"{Fore.GREEN}8.{Style.RESET_ALL} {processor.get_text('menu.exit')}")
        
        choice = input(f"\n{processor.get_text('prompts.choose')}: ")
        
        if choice == '1':
            if processor.verify_characters_dir():
                start_monitoring(processor)
            else:
                print(f"\n{Fore.RED}{processor.get_text('prompts.monitoring_error')}{Style.RESET_ALL}")
        elif choice == '2':
            processor.db = {}
            processor.save_db()
            print(processor.get_text('debug.translation_data_reset'))
        elif choice == '3':
            restore_originals(processor)
        elif choice == '4':
            configure_translation_language(processor)
        elif choice == '5':
            configure_translation_service(processor)
        elif choice == '6':
            configure_interface_language(processor)
        elif choice == '7':
            select_sillytavern_directory(processor)
        elif choice == '8':
            break

def configure_translation_language(processor):
    print(f"\n{processor.get_text('debug.available_languages')}:")
    for code, name in LANGUAGES.items():
        # Use the name from 'others' in current interface language
        display_name = processor.interface_texts.get('others', {}).get(code, name)
        print(f"{code.upper()}: {display_name}")
    
    current_lang = processor.interface_texts.get('others', {}).get(processor.target_lang, 
                  LANGUAGES.get(processor.target_lang, 'Unknown'))
    new_lang = input(f"\n{processor.get_text('prompts.choose')} ({processor.get_text('prompts.keep_current')} {current_lang}): ").lower() or processor.target_lang
    
    if new_lang in LANGUAGES:
        processor.target_lang = new_lang
    
    current_translate_name = processor.get_text('prompts.yes') if processor.translate_name else processor.get_text('prompts.no')
    choice = input(f"{processor.get_text('prompts.translate_names_keep').format(current_translate_name)}: ").lower()
    if choice and choice in processor.get_text('prompts.yes')[0].lower():
        processor.translate_name = True
    elif choice and choice in processor.get_text('prompts.no')[0].lower():
        processor.translate_name = False
    
    current_translate_angle = processor.get_text('prompts.yes') if processor.translate_angle else processor.get_text('prompts.no')
    choice = input(f"{processor.get_text('prompts.translate_angles_keep').format(current_translate_angle)}: ").lower()
    if choice and choice in processor.get_text('prompts.yes')[0].lower():
        processor.translate_angle = True
    elif choice and choice in processor.get_text('prompts.no')[0].lower():
        processor.translate_angle = False

    # NOVAS PERGUNTAS para conteúdo entre parênteses e colchetes
    current_translate_parentheses = processor.get_text('prompts.yes') if processor.translate_parentheses else processor.get_text('prompts.no')
    choice = input(f"{processor.get_text('prompts.translate_parentheses_keep').format(current_translate_parentheses)}: ").lower()
    if choice and choice in processor.get_text('prompts.yes')[0].lower():
        processor.translate_parentheses = True
    elif choice and choice in processor.get_text('prompts.no')[0].lower():
        processor.translate_parentheses = False

    current_translate_brackets = processor.get_text('prompts.yes') if processor.translate_brackets else processor.get_text('prompts.no')
    choice = input(f"{processor.get_text('prompts.translate_brackets_keep').format(current_translate_brackets)}: ").lower()
    if choice and choice in processor.get_text('prompts.yes')[0].lower():
        processor.translate_brackets = True
    elif choice and choice in processor.get_text('prompts.no')[0].lower():
        processor.translate_brackets = False

    current_use_jane = processor.get_text('prompts.yes') if processor.use_jane else processor.get_text('prompts.no')
    choice = input(f"{processor.get_text('prompts.use_jane_keep').format(current_use_jane)}: ").lower()
    if choice and choice in processor.get_text('prompts.yes')[0].lower():
        processor.use_jane = True
    elif choice and choice in processor.get_text('prompts.no')[0].lower():
        processor.use_jane = False

    processor.save_translation_settings()
    processor.apply_translation_settings()

def configure_translation_service(processor):
    print(f"\n{Fore.BLUE}{processor.get_text('prompts.translation_services_available')}:{Style.RESET_ALL}")
    services = {
        '1': 'google',
        '2': 'mymemory',
        '3': 'libre',
        '4': 'linguee',
        '5': 'pons'
    }
    
    for num, service in services.items():
        selected = f"{Fore.YELLOW} ({processor.get_text('prompts.current_service')}){Style.RESET_ALL}" if processor.translation_service == service else ""
        print(f"{num}: {service}{selected}")
    
    choice = input(f"\n{processor.get_text('prompts.choose_service')}: ").strip()
    
    if choice in services:
        processor.translation_service = services[choice]
        processor.save_translation_settings()
        processor.set_translator_service()
        print(f"{processor.get_text('prompts.service_updated')}: {processor.translation_service}")

def configure_interface_language(processor):
    print(f"\n{processor.get_text('debug.available_interface_languages')}:")
    for code, name in LANGUAGES.items():
        selected = f"{Fore.YELLOW} ({processor.get_text('prompts.current_service')}){Style.RESET_ALL}" if processor.interface_lang == code else ""
        print(f"{code.upper()}: {name}{selected}")
    
    current_lang = LANGUAGES.get(processor.interface_lang, 'Português')
    new_lang = input(f"\n{processor.get_text('prompts.choose')} ({processor.get_text('prompts.keep_current')} {current_lang}): ").lower() or processor.interface_lang
    
    if new_lang in LANGUAGES:
        processor.interface_lang = new_lang
        processor.interface_texts = processor.load_interface_texts()
        processor.save_translation_settings()

def start_monitoring(processor):
    processor.monitoring = True
    
    # Mostra mensagem de verificação automática apenas se o DB estiver vazio
    if not processor.db:
        print(f"\n{Fore.BLUE}{processor.get_text('debug.automatic_check')}{Style.RESET_ALL}")
    
    # Mostra as mensagens de monitoramento uma única vez ao iniciar
    print(f"\n{Fore.BLUE}{processor.get_text('debug.monitoring_location').format(CHARACTERS_DIR)}{Style.RESET_ALL}")
    print(f"{Fore.RED}{processor.get_text('debug.press_enter_stop')}{Style.RESET_ALL}")
    
    processor.process_existing_files()
    
    observer = Observer()
    event_handler = CharacterHandler(processor)
    observer.schedule(event_handler, path=CHARACTERS_DIR, recursive=False)
    observer.start()
    
    try:
        last_check = time.time()
        while True:
            if msvcrt.kbhit() and msvcrt.getch() == b'\r':
                break
                
            current_time = time.time()
            if current_time - last_check > 3:
                files = list(CHARACTERS_DIR.glob('*.png'))
                new_files = [f for f in files if processor.db.get(f.name) != processor.get_file_hash(f)]
                
                if new_files:            
                    for file in new_files:
                        processor.process_character(file)
                        
                last_check = current_time
                
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        processor.monitoring = False
        print(processor.get_text('debug.monitoring_stopped'))

def restore_originals(processor):
    print(f"\n{processor.get_text('debug.processing_existing')}")
    for backup_file in ORIGINAL_DIR.glob('*.png'):
        target_file = CHARACTERS_DIR / backup_file.name
        if backup_file.exists():
            # Copy backup to characters folder then remove original file from ORIGINAL_DIR
            import shutil
            shutil.copy(str(backup_file), str(target_file))
            print(processor.get_text('debug.restored_file').format(backup_file.name))
            os.remove(backup_file)
            if backup_file.name in processor.db:
                del processor.db[backup_file.name]
    processor.save_db()

def select_sillytavern_directory(processor):
    root = tk.Tk()
    root.withdraw()  # Esconde a janela principal
    
    folder = filedialog.askdirectory(
        title=processor.get_text('prompts.select_sillytavern')
    )
    
    if folder:
        # Navega automaticamente para data/default-user/characters
        sillytavern_path = Path(folder)
        characters_path = sillytavern_path / 'data' / 'default-user' / 'characters'
        
        if characters_path.exists() and characters_path.is_dir():
            processor.characters_dir = str(characters_path)
            processor.save_translation_settings()
            print(f"\n{Fore.GREEN}{processor.get_text('prompts.directory_set').format(characters_path)}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}{processor.get_text('prompts.directory_invalid')}{Style.RESET_ALL}")
            processor.characters_dir = ''
            processor.save_translation_settings()

if __name__ == "__main__":
    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    processor = CharacterProcessor()
    show_menu(processor)