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
# NEW: English language names as defined in the "en" block
EN_INTERFACE_OTHERS = {
    "pt": "Portuguese",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ja": "Japanese",
    "zh-cn": "Chinese",
    "ko": "Korean",
    "ru": "Russian"
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
        # Initialize translation cache to fix AttributeError
        self._translation_cache = {}

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
            'use_char_name': False, # Changed from use_jane to use_char_name
            'api_key_groq': "",
            'api_key_openrouter': "",
            'inference': "groq",
            'model_groq': "llama-3.1",       # novo
            'model_openrouter': "",          # novo
            'llm_char': "{{char}}"
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
        self.use_char_name = self.translation_settings.get('use_char_name', False) # Changed from use_jane to use_char_name
        self.api_key_groq = self.translation_settings.get('api_key_groq', "")
        self.api_key_openrouter = self.translation_settings.get('api_key_openrouter', "")
        self.inference = self.translation_settings.get('inference', "groq")
        # Use o modelo correspondente ao provider:
        if self.inference == "groq":
            self.model = self.translation_settings.get('model_groq', "")
        else:
            self.model = self.translation_settings.get('model_openrouter', "")
        self.llm_char = self.translation_settings.get('llm_char', "{{char}}")

    def set_translator_service(self):
        if self.translation_service == 'google':
            from lib.free_translator import GoogleTranslatorService
            self.translator = GoogleTranslatorService()
        elif self.translation_service == 'mymemory':
            from lib.mymemory_translator import MyMemoryTranslatorService
            self.translator = MyMemoryTranslatorService()
        elif self.translation_service == 'llm':
            # Use a chave e o modelo do provider atual:
            api_key = self.api_key_groq if self.inference=="groq" else self.api_key_openrouter
            self.translator = LLMTranslatorService(api_key, self.inference, self.model)
        else:
            from lib.free_translator import GoogleTranslatorService
            self.translator = GoogleTranslatorService()

    def save_translation_settings(self):
        # Salve também os modelos para cada provider
        self.translation_settings.update({
            'target_lang': self.target_lang,
            'translate_angle': self.translate_angle,
            'translate_name': self.translate_name,
            'interface_lang': self.interface_lang,
            'translation_service': self.translation_service,
            'characters_dir': self.characters_dir,
            'use_char_name': self.use_char_name, # Changed from use_jane to use_char_name
            'api_key_groq': self.api_key_groq,
            'api_key_openrouter': self.api_key_openrouter,
            'inference': self.inference,
            'model_groq': self.model if self.inference=="groq" else self.translation_settings.get('model_groq', ""),
            'model_openrouter': self.model if self.inference=="openrouter" else self.translation_settings.get('model_openrouter', ""),
            'llm_char': self.llm_char
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

    def recursive_translate(self, text, char_name=None):
        """Traduz texto preservando delimitadores de qualquer comprimento"""
        if not text or text.isspace():
            return text

        MAX_LENGTH = 4000
        if len(text) > MAX_LENGTH:
            return self.translate_segment(text, char_name) # Pass char_name

        # Identificar padrões de delimitação que podem ter qualquer comprimento
        # Procura por um dos caracteres delimitadores especiais repetido uma ou mais vezes
        delimiter_patterns = [
            (r'\*+', r'\*+'),    # Um ou mais asteriscos
            (r'"+', r'"+'),      # Uma ou mais aspas
        ]

        for open_pattern, close_pattern in delimiter_patterns:
            # Procurar o padrão de abertura
            open_match = re.search(open_pattern, text)
            if not open_match:
                continue

            # Capturar o delimitador exato de abertura
            opening = open_match.group(0)
            start_pos = open_match.start()

            # Buscar o delimitador de fechamento correspondente
            # Para asteriscos e aspas, procuramos a mesma sequência que foi usada para abrir
            close_search = re.search(re.escape(opening), text[start_pos + len(opening):])

            if not close_search:
                # Não encontrou fechamento correspondente, continue para o próximo padrão
                continue

            # Calcular a posição absoluta do fechamento
            end_pos = start_pos + len(opening) + close_search.start()
            closing = close_search.group(0)

            # Dividir o texto em partes
            before = text[:start_pos]
            content = text[start_pos + len(opening):end_pos]
            after = text[end_pos + len(closing):]

            # Traduzir o texto antes dos delimitadores
            translated_before = ""
            if before.strip():
                try:
                    translated_before = self.translator.translate(before, dest=self.target_lang).text
                except Exception as e:
                    print(f"Erro ao traduzir texto antes do delimitador: {e}")
                    translated_before = before
            else:
                translated_before = before  # Preservar espaços/quebras

            # Traduzir o conteúdo dentro dos delimitadores recursivamente
            translated_content = self.recursive_translate(content, char_name)

            # Traduzir o texto após os delimitadores recursivamente
            translated_after = self.recursive_translate(after, char_name)

            # Combinar mantendo os delimitadores originais exatos
            return f"{translated_before}{opening}{translated_content}{closing}{translated_after}"

        # Se não encontrar delimitadores, traduzir o texto normalmente
        try:
            # Contar quebras de linha para preservação exata
            original_newlines = text.count('\n')

            translated = self.translator.translate(text, dest=self.target_lang).text

            # Garantir que o número de quebras de linha seja preservado
            translated_newlines = translated.count('\n')

            if original_newlines != translated_newlines:
                if original_newlines > translated_newlines:
                    # Adicionar quebras de linha faltantes ao final
                    translated += '\n' * (original_newlines - translated_newlines)
                elif translated_newlines > original_newlines:
                    # Remover quebras de linha excedentes do final
                    while translated.count('\n') > original_newlines and translated.endswith('\n'):
                        translated = translated[:-1]

            return translated if translated and translated != "None" else text
        except Exception as e:
            print(f"Erro na tradução recursiva: {e}")
            return text

    def translate_character_card(self, text, char_name=None):
        """Traduz um cartão de personagem preservando a estrutura corretamente"""
        if not text or not isinstance(text, str):
            return text

        # Verifica se é um cartão com formato [conteúdo]
        if text.startswith('[') and text.endswith(']'):
            inner_content = text[1:-1]
            lines = inner_content.split('\n')
            translated_lines = []

            for line in lines:
                # Procura pelo padrão {{char}} propriedade(valor);
                match = re.match(r'(\{\{char\}\})\s+([^(]+)\(([^)]+)\)(.*)', line)
                if match:
                    tag = match.group(1)  # {{char}}
                    prop_name = match.group(2).strip()  # nome da propriedade
                    prop_value = match.group(3)  # valor da propriedade
                    suffix = match.group(4)  # restante após o parêntese (;)

                    # Traduz o nome da propriedade
                    translated_name = self.translator.translate(prop_name, dest=self.target_lang).text

                    # Determina se o valor deve ser traduzido
                    non_translatable = ['name', 'age']
                    should_translate = not any(nt.lower() in prop_name.lower() for nt in non_translatable)

                    if should_translate:
                        # Para valores separados por vírgula (como traços de personalidade)
                        if ',' in prop_value:
                            values = [v.strip() for v in prop_value.split(',')]
                            translated_values = []
                            for v in values:
                                try:
                                    translated_values.append(self.translator.translate(v, dest=self.target_lang).text)
                                except Exception as e:
                                    print(f"Erro ao traduzir valor: {e}")
                                    translated_values.append(v)
                            translated_value = ', '.join(translated_values)
                        else:
                            try:
                                translated_value = self.translator.translate(prop_value, dest=self.target_lang).text
                            except Exception as e:
                                print(f"Erro ao traduzir valor: {e}")
                                translated_value = prop_value
                    else:
                        translated_value = prop_value

                    # Reconstrói a linha preservando a estrutura exata
                    translated_line = f"{tag} {translated_name}({translated_value}){suffix}"
                    translated_lines.append(translated_line)
                else:
                    # Para linhas que não seguem o padrão, traduza normalmente
                    try:
                        translated_line = self.translator.translate(line, dest=self.target_lang).text
                        translated_lines.append(translated_line)
                    except Exception as e:
                        print(f"Erro ao traduzir linha: {e}")
                        translated_lines.append(line)

            # Reconstrói o cartão com os colchetes
            return f"[{chr(10).join(translated_lines)}]"

        # Para texto regular, use a tradução normal
        return self.translate_text(text, char_name)

    def load_llm_instructions(self) -> Dict[str, Any]:
                    try:
                        if INTERFACE_LANG_FILE.exists():
                            data = json.loads(INTERFACE_LANG_FILE.read_text(encoding='utf-8'))
                            # Tenta carregar as instruções do idioma da tradução; senão, usa o bloco 'en'
                            lang_section = data.get(self.target_lang, data.get('en', {}))
                            return lang_section.get('llm_instructions', {})
                        else:
                            return {}
                    except Exception as e:
                        print(f"Error loading LLM instructions: {e}")
                        return {}

    def translate_text(self, text, char_name=None):
        if not text or not isinstance(text, str):
            return text

        if self.translation_service == "llm":
            key = (text, char_name)
            if not hasattr(self, '_llm_cache'):
                self._llm_cache = {}
            if key in self._llm_cache:
                return self._llm_cache[key]
            name_part = f"{char_name}" if char_name else ""
            
            # Verifica se a flag use_english_instructions está ativa nas configurações
            if self.translation_settings.get('use_english_instructions', True):
                # Versão fixa em inglês
                if self.translate_angle:
                    angle_instruction = "Translate also texts inside <...>."
                else:
                    angle_instruction = ("Do not translate texts inside <>; Maintain <...> original. "
                                        "Do not translate texts inside {{}}; Maintain {{...}} original.")
                if name_part:
                    if self.translate_name:
                        name_instruction = "Include names translation"
                    else:
                        name_instruction = f"Do not translate the text: {name_part}."
                else:
                    name_instruction = ""
                target_lang_label = EN_INTERFACE_OTHERS.get(self.target_lang, self.target_lang)
                choice_gender_val = self.translation_settings.get('choice_gender', "3")
                if choice_gender_val == "1":
                    user_gender = "{{user}} is male."
                elif choice_gender_val == "2":
                    user_gender = "{{user}} is female."
                else:
                    user_gender = ""
                
                system_instruction = (
                    f"You're a translator. Translate the content to {target_lang_label} using the same formatting used in Roleplay."
                    f"{angle_instruction} {name_instruction}"
                )
                # Na versão fixa, usamos um padrão direto para o conteúdo do usuário:
                user_content = f"Content:\n```{text}```"
            else:
                # Versão usando as instruções do JSON, caso existam
                instructions = self.load_llm_instructions()
                if self.translate_angle:
                    angle_instruction = instructions.get('translate_angle', "Translate also texts inside <...>.")
                else:
                    angle_instruction = instructions.get('no_translate_angle', 
                        "Do not translate texts inside <>; Maintain <...> original. Do not translate texts inside {{}}; Maintain {{...}} original.")
                if name_part:
                    if self.translate_name:
                        name_instruction = instructions.get('translate_name', "Include names translation")
                    else:
                        name_instruction = instructions.get('no_translate_name', "Do not translate the text: {name_part}.").format(name_part=name_part)
                else:
                    name_instruction = ""
                system_prefix = instructions.get(
                    'system_prefix',
                    f"You're a translator. Translate the content to {EN_INTERFACE_OTHERS.get(self.target_lang, self.target_lang)} using the same formatting used in Roleplay."
                )
                raw_user_content_prefix = instructions.get('user_content_prefix', "Content:\n```{text}```")
                # Garantir que qualquer "{}" seja substituído por "{text}"
                raw_user_content_prefix = raw_user_content_prefix.replace("{}", "{text}")
                user_content = raw_user_content_prefix.format(text=text)
                system_instruction = f"{system_prefix} {angle_instruction} {name_instruction}"
                user_gender = self.translation_settings.get('user_gender_instruction', '')
            
            if user_gender:
                system_instruction += f" {user_gender}"
            
            prompt = f"System: {system_instruction}\nUser: {user_content}"
            try:
                response = self.translator.translate(prompt, dest=self.target_lang)
                m = re.search(r"```([^`]+)```", response.text, re.DOTALL)
                if m:
                    result = m.group(1).strip()
                else:
                    result = response.text.strip()
                if char_name:
                    result = result.replace(char_name, "{{char}}")
                self._llm_cache[key] = result
                return result
            except Exception as e:
                print(f"LLM translation error: {e}")
                return text
        else:
            if text.startswith('[') and text.endswith(']'):
                result = self.translate_character_card(text, char_name)
            else:
                result = self.translate_segment(text, char_name)
            self._translation_cache[hash(text)] = result
            return result

    def translate_segment(self, text, char_name=None): # Added char_name parameter
        """Traduz segmentos preservando delimitadores, variáveis e formatação"""
        if not text or not isinstance(text, str):
            return text

        # Primeiro, substituir \n por um placeholder único
        newline_placeholder = "XZNEWLINEZX"
        processed_text = text.replace("\\n", newline_placeholder)

        # Preservar links de imagens no formato markdown ![img](url)
        image_links = {}
        img_pattern = r'(!\[[^\]]*\]\([^)]+\))'

        for i, match in enumerate(re.finditer(img_pattern, processed_text)):
            image = match.group(0)
            placeholder = f"XZIMG{i}ZX"
            image_links[placeholder] = image
            processed_text = processed_text.replace(image, placeholder, 1)

        # Preservar variáveis {{user}} e {{char}}
        has_user_var = "{{user}}" in processed_text
        has_char_var = "{{char}}" in processed_text

        user_placeholder_name = "James" # Default placeholder name
        char_placeholder_name = "Jane"  # Default placeholder name

        if char_name and self.use_char_name: # Use char_name if available and setting is enabled
            char_placeholder_name = char_name

        if has_user_var:
            processed_text = processed_text.replace("{{user}}", user_placeholder_name)
        if has_char_var:
            processed_text = processed_text.replace("{{char}}", char_placeholder_name)

        # Preservar outras variáveis {{...}}
        var_pattern = r'(\{\{[^{}]+\}\})'
        protected_vars = {}

        for i, match in enumerate(re.finditer(var_pattern, processed_text)):
            var = match.group(0)
            placeholder = f"XZVAR{i}ZX"
            protected_vars[placeholder] = var
            processed_text = processed_text.replace(var, placeholder, 1)

        # Preservar conteúdo entre delimitadores angulares <...>
        angular_pattern = r'(<[^<>]*>)'
        protected_angular = {}

        if self.translate_angle: # Only process angular brackets if translate_angle is enabled
            for i, match in enumerate(re.finditer(angular_pattern, processed_text)):
                angular_content = match.group(0)
                placeholder = f"XZANGULAR{i}ZX"
                protected_angular[placeholder] = angular_content
                processed_text = processed_text.replace(angular_content, placeholder, 1)

        # Processar delimitadores normalmente
        delimiter_patterns = [
            r'\*[^\*]+?\*',          # *texto* (itálico)
            r'\*\*[^\*]+?\*\*',      # **texto** (negrito)
            r'`[^`]+?`',             # `texto` (código inline)
            r'```[\s\S]+?```',       # ```texto``` (bloco de código)
            r'"[^"]+?"',             # "texto" (aspas)
            r'_[^_]+?_',             # _texto_ (itálico)
            r'__[^_]+?__'            # __texto__ (negrito)
        ]

        combined_pattern = '|'.join(f'({pattern})' for pattern in delimiter_patterns)

        parts = []
        last_end = 0

        for match in re.finditer(combined_pattern, processed_text):
            start, end = match.span()

            if start > last_end:
                raw_text = processed_text[last_end:start]
                leading_spaces = len(raw_text) - len(raw_text.lstrip())
                trailing_spaces = len(raw_text) - len(raw_text.rstrip())
                stripped_text = raw_text.strip()

                parts.append(('text', raw_text, leading_spaces, trailing_spaces, stripped_text))

            parts.append(('delimiter', match.group(0)))
            last_end = end

        if last_end < len(processed_text):
            raw_text = processed_text[last_end:]
            leading_spaces = len(raw_text) - len(raw_text.lstrip())
            trailing_spaces = len(raw_text) - len(raw_text.rstrip())
            stripped_text = raw_text.strip()

            parts.append(('text', raw_text, leading_spaces, trailing_spaces, stripped_text))

        # Processar cada parte
        result = []
        for part in parts:
            if part[0] == 'text':
                _, raw_text, leading_spaces, trailing_spaces, stripped_text = part

                if stripped_text:
                    contains_newline = newline_placeholder in stripped_text
                    contains_img_placeholder = any(placeholder in stripped_text for placeholder in image_links)
                    contains_var_placeholder = any(placeholder in stripped_text for placeholder in protected_vars)
                    contains_angular_placeholder = any(placeholder in stripped_text for placeholder in protected_angular)

                    if contains_newline or contains_img_placeholder or contains_var_placeholder or contains_angular_placeholder:
                        result.append(raw_text)
                    else:
                        try:
                            # Verificar o caso do texto original
                            is_all_uppercase = stripped_text.isupper()
                            is_all_lowercase = stripped_text.islower()

                            translated = self.translator.translate(stripped_text, dest=self.target_lang).text

                            # Aplicar o mesmo caso do original ao traduzido
                            if is_all_uppercase:
                                translated = translated.upper()
                            elif is_all_lowercase:
                                translated = translated.lower()

                            result.append(' ' * leading_spaces + translated + ' ' * trailing_spaces)
                        except Exception as e:
                            print(f"Erro ao traduzir texto: {e}")
                            result.append(raw_text)
                else:
                    result.append(raw_text)

            elif part[0] == 'delimiter':
                part_text = part[1]

                if newline_placeholder in part_text:
                    result.append(part_text)
                else:
                    # Processar delimitadores como antes...
                    if part_text.startswith('`'):
                        if part_text.startswith('```') and part_text.endswith('```'):
                            content = part_text[3:-3]
                            try:
                                # Verificar caso do conteúdo
                                is_all_uppercase = content.isupper()
                                is_all_lowercase = content.islower()

                                translated_content = self.translator.translate(content, dest=self.target_lang).text

                                # Aplicar caso apropriado
                                if is_all_uppercase:
                                    translated_content = translated_content.upper()
                                elif is_all_lowercase:
                                    translated_content = translated_content.lower()

                                result.append(f"```{translated_content}```")
                            except Exception as e:
                                print(f"Erro ao traduzir bloco de código: {e}")
                                result.append(part_text)
                        else:
                            content = part_text[1:-1]
                            try:
                                # Verificar caso do conteúdo
                                is_all_uppercase = content.isupper()
                                is_all_lowercase = content.islower()

                                translated_content = self.translator.translate(content, dest=self.target_lang).text

                                # Aplicar caso apropriado
                                if is_all_uppercase:
                                    translated_content = translated_content.upper()
                                elif is_all_lowercase:
                                    translated_content = translated_content.lower()

                                result.append(f"`{translated_content}`")
                            except Exception as e:
                                print(f"Erro ao traduzir código inline: {e}")
                                result.append(part_text)
                    else:
                        if part_text.startswith('*') and part_text.endswith('*'):
                            if part_text.startswith('**') and part_text.endswith('**'):
                                opening = closing = '**'
                                content = part_text[2:-2]
                            else:
                                opening = closing = '*'
                                content = part_text[1:-1]
                        elif part_text.startswith('_') and part_text.endswith('_'):
                            if part_text.startswith('__') and part_text.endswith('__'):
                                opening = closing = '__'
                                content = part_text[2:-2]
                            else:
                                opening = closing = '_'
                                content = part_text[1:-1]
                        elif part_text.startswith('"') and part_text.endswith('"'):
                            opening = closing = '"'
                            content = part_text[1:-1]
                        else:
                            result.append(part_text)
                            continue

                        try:
                            # Verificar caso do conteúdo
                            is_all_uppercase = content.isupper()
                            is_all_lowercase = content.islower()

                            translated_content = self.translator.translate(content, dest=self.target_lang).text

                            # Aplicar caso apropriado
                            if is_all_uppercase:
                                translated_content = translated_content.upper()
                            elif is_all_lowercase:
                                translated_content = translated_content.lower()

                            result.append(f"{opening}{translated_content}{closing}")
                        except Exception as e:
                            print(f"Erro ao traduzir conteúdo delimitado: {e}")
                            result.append(part_text)

        # Juntar o resultado
        final_text = ''.join(result)

        # Restaurar quebras de linha
        final_text = final_text.replace(newline_placeholder, "\n")

        # Restaurar placeholders na ordem correta
        for placeholder, original in protected_vars.items():
            final_text = final_text.replace(placeholder, original)

        if self.translate_angle: # Only restore angular if translate_angle is enabled
            for placeholder, original in protected_angular.items():
                final_text = final_text.replace(placeholder, original)

        for placeholder, original in image_links.items():
            final_text = final_text.replace(placeholder, original)

        if has_user_var:
            final_text = final_text.replace(user_placeholder_name, "{{user}}")
        if has_char_var:
            final_text = final_text.replace(char_placeholder_name, "{{char}}")

        # ETAPA FINAL: Detectar e substituir espaços duplos entre delimitadores e texto por quebras de linha
        # Padrão 1: Fim de delimitador + 2+ espaços + início de texto
        final_text = re.sub(r'([*_"`\)])[ ]{2,}([^*_"`\)])', r'\1\n\2', final_text)

        # Padrão 2: Fim de texto + 2+ espaços + início de delimitador
        final_text = re.sub(r'([^*_"`\(])[ ]{2,}([*_"`\(])', r'\1\n\2', final_text)

        return final_text

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
            print(f"{Fore.RED}{self.get_text('error.extracting_data', 'Failed to extract character data from')} {original_file}{Style.RESET_ALL}")
            return

        # Make a deep copy of the character data for translation
        translated_data = self.deep_copy_data(char_data)

        # Get the original character name
        original_name = self.get_character_name(char_data)
        if not original_name:
            original_name = original_file.stem

        # Translate fields
        self.translate_character_data(translated_data, original_name) # Pass original_name

        # Save the translated character card
        self.save_translated_card(original_file, translated_data)

        # Update the database
        self.db[original_file.name] = self.get_file_hash(original_file)
        self.save_db()

        print(f"{Fore.GREEN}{self.get_text('success.translated_file', 'Successfully translated')} {original_file.name}{Style.RESET_ALL}")

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

    def translate_character_data(self, data, original_name): # Pass original_name
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
            if field in data and isinstance(data[field], str):
                # For the 'name' field, do not substitute {{char}}
                if field == "name" and not self.translate_name:
                    continue
                substitute = None if field == "name" else original_name
                data[field] = self.translate_text(data[field], substitute)

        # Process fields in the 'data' dictionary if it exists
        if 'data' in data and isinstance(data['data'], dict):
            for field, should_translate in translatable_fields.items():
                if field in data['data'] and isinstance(data['data'][field], str) and should_translate:
                    substitute = None if field == "name" else original_name
                    data['data'][field] = self.translate_text(data['data'][field], substitute)

        # Translate "depth_prompt" prompt if in root level
        if 'depth_prompt' in data and isinstance(data['depth_prompt'], dict):
            if 'prompt' in data['depth_prompt'] and isinstance(data['depth_prompt']['prompt'], str):
                data['depth_prompt']['prompt'] = self.translate_text(data['depth_prompt']['prompt'], original_name)

        # Translate depth_prompt in data.extensions
        if 'data' in data and isinstance(data['data'], dict):
            if 'extensions' in data['data'] and isinstance(data['data']['extensions'], dict):
                if 'depth_prompt' in data['data']['extensions'] and isinstance(data['data']['extensions']['depth_prompt'], dict):
                    if 'prompt' in data['data']['extensions']['depth_prompt'] and isinstance(data['data']['extensions']['depth_prompt']['prompt'], str):
                        data['data']['extensions']['depth_prompt']['prompt'] = self.translate_text(
                            data['data']['extensions']['depth_prompt']['prompt'], 
                            original_name
                        )

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
                print(f"{Fore.BLUE}{self.get_text('debug.file_moved', 'File moved')}: {image_path.name} {self.get_text('debug.to')} {ORIGINAL_DIR}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{self.get_text('error.moving_file', 'Error moving file')}: {e}")
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

            print(f"{Fore.GREEN}{self.get_text('success.card_saved', 'Translated card saved')}: {new_image_path}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}{self.get_text('error.saving_card', 'Error saving translated card')}: {e}{Style.RESET_ALL}")

    def save_db(self):
        """Save the translation database"""
        try:
            DB_FILE.write_text(json.dumps(self.db, indent=2))
        except Exception as e:
            print(f"{self.get_text('error.saving_db', 'Error saving database')}: {e}")

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
                print(f"{self.get_text('error.interface_file_not_found', 'Interface language file not found!')}")
                return {}
        except Exception as e:
            print(f"{self.get_text('error.loading_interface_texts', 'Error loading interface texts')}: {e}")
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

class LLMTranslatorService:
    def __init__(self, api_key, inference, model):
        self.api_key = api_key
        self.inference = inference
        self.model = model

    def translate(self, prompt, dest):
        if self.inference == "groq":
            from groq import Groq
            client = Groq(api_key=self.api_key)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model
            )
            print (prompt)
            class SimpleResponse:
                pass
            simple = SimpleResponse()
            simple.text = chat_completion.choices[0].message.content
            print (simple)
            return simple
        elif self.inference == "openrouter":
            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key
            )
            completion = client.chat.completions.create(
                model=self.model,
                max_completion_tokens = 0,
                max_tokens = 0,

                messages=[{"role": "user", "content": prompt}],
                extra_headers={
                }
            )
            class SimpleResponse:
                pass
            
            print (prompt)
            simple = SimpleResponse()
            simple.text = completion.choices[0].message.content
            print (simple.text)
            return simple
        else:
            class SimpleResponse:
                pass
            simple = SimpleResponse()
            simple.text = "Translation error: unsupported inference method."
            return simple

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

    service_display = processor.translation_service
    if processor.translation_service == "llm":
        service_display = f"{processor.model} (LLM)"
    print(f"{processor.get_text('translation_service')}: {service_display}")

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
        print(f"{Fore.GREEN}8.{Style.RESET_ALL} Selecionar modelo")
        print(f"{Fore.GREEN}9.{Style.RESET_ALL} Sair")

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
            configure_model(processor)
        elif choice == '9':
            break

def configure_translation_language(processor):
    # Replace direct string prompt for LLM choice with interface text key
    choice_llm = input(processor.get_text('prompts.ask_use_llm')).strip().lower() or "n"
    if choice_llm.startswith("s"):
        processor.translation_service = "llm"
    else:
        processor.translation_service = "google"
    
    # NEW: Move available languages block immediately after choice_llm
    print(f"\n{processor.get_text('debug.available_languages')}:")
    for code, name in LANGUAGES.items():
        display_name = processor.interface_texts.get('others', {}).get(code, name)
        print(f"{code.upper()}: {display_name}")
    current_lang = processor.interface_texts.get('others', {}).get(processor.target_lang, LANGUAGES.get(processor.target_lang, 'Unknown'))
    new_lang = input(f"\n{processor.get_text('prompts.choose')} ({processor.get_text('prompts.keep_current')} {current_lang}): ").lower() or processor.target_lang
    if new_lang in LANGUAGES:
        processor.target_lang = new_lang

    # Use interface texts for names translation prompt
    choice_names = input(processor.get_text('prompts.translate_names') + " (S/N ou Enter para manter sim): ").strip().lower() or "s"
    processor.translate_name = choice_names.startswith("s")
    # Use interface text for angle translation prompt
    choice_angle = input(processor.get_text('prompts.translate_angles') + " (S/N ou Enter para manter não): ").strip().lower() or "n"
    processor.translate_angle = choice_angle.startswith("s")
    # Prompt for using character name via interface text
    current_use = processor.get_text('prompts.yes') if processor.use_char_name else processor.get_text('prompts.no')
    prompt_text = processor.get_text('prompts.use_char_name_keep').format(current_use)
    choice_char = input(prompt_text).strip().lower() or current_use[0].lower()
    processor.use_char_name = choice_char.startswith(processor.get_text('prompts.yes')[0].lower())

    processor.save_translation_settings()
    processor.apply_translation_settings()
    
    print("\n" + processor.get_text('prompts.select_user_profile') + ":")
    with open(INTERFACE_LANG_FILE, encoding='utf-8') as f:
        lang_data = json.loads(f.read())
    target_texts = lang_data.get(processor.target_lang, lang_data.get('en', {}))
    prompts_target = target_texts.get('prompts', {})

    print("1. {{user}} " + prompts_target.get('user_profile_male', "male") + ".")
    print("2. {{user}} " + prompts_target.get('user_profile_female', "female") + ".")
    print("3. " + prompts_target.get('user_profile_ignore', "ignore"))
    choice_gender = input(processor.get_text('prompts.choose_option') + ": ").strip()
    # Salvar tanto o texto quanto o número da opção escolhida
    if choice_gender == "1":
        processor.translation_settings['user_gender_instruction'] = "{{user}} " + prompts_target.get('user_profile_male', "male") + "."
    elif choice_gender == "2":
        processor.translation_settings['user_gender_instruction'] = "{{user}} " + prompts_target.get('user_profile_female', "female") + "."
    else:
        processor.translation_settings['user_gender_instruction'] = ""
    # Armazena também o valor numérico escolhido
    processor.translation_settings['choice_gender'] = choice_gender
    processor.save_translation_settings()
def configure_translation_service(processor):
    print(f"\n{Fore.BLUE}{processor.get_text('prompts.translation_services_available')}:{Style.RESET_ALL}")
    services = {
        '1': 'google',
        '2': 'mymemory'
    } # Removed libre, linguee and pons as in original code only google and mymemory are used

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
    # Antes de iniciar, verifique se a chave e o modelo do provider atual estão definidos
    current_api = processor.api_key_groq if processor.inference == "groq" else processor.api_key_openrouter
    if not current_api:
        print(f"\n{Fore.RED}Erro: Chave API para o provider '{processor.inference}' não foi configurada!{Style.RESET_ALL}")
        return
    if not processor.model:
        print(f"\n{Fore.RED}Erro: Modelo para o provider '{processor.inference}' não foi selecionado!{Style.RESET_ALL}")
        return
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

def update_gender_instruction(processor):
    """
    Atualiza automaticamente a instrução de gênero (user_gender_instruction)
    conforme o valor de use_english_instructions.
    Se True, utiliza os textos do bloco 'prompts' de 'en';
    se False, utiliza os textos do bloco do idioma de tradução (target_lang).
    """
    with open(INTERFACE_LANG_FILE, encoding='utf-8') as f:
        lang_data = json.loads(f.read())
    if processor.translation_settings.get('use_english_instructions', True):
        prompts_src = lang_data.get('en', {}).get('prompts', {})
    else:
        prompts_src = lang_data.get(processor.target_lang, lang_data.get('en', {})).get('prompts', {})
    
    # Supondo que já exista alguma indicação do gênero (por exemplo, se no valor atual
    # constar "male" ou "女性"/"feminine", etc.), atualize; caso contrário, mantenha vazio.
    current = processor.translation_settings.get('user_gender_instruction', '')
    if "male" in current.lower() or "Male" in current:
        new_text = "{{user}} " + prompts_src.get('user_profile_male', "male") + "."
    elif "female" in current.lower() or "Female" in current:
        new_text = "{{user}} " + prompts_src.get('user_profile_female', "female") + "."
    else:
        new_text = ""
    
    processor.translation_settings['user_gender_instruction'] = new_text
    processor.save_translation_settings()

def configure_model(processor):
    available_models = {
        "groq": ["llama-3.3-70b-versatile", "qwen-2.5-32b", "mistral-saba-24b", "gemma2-9b-it", "llama-3.1-8b-instant"],
        "openrouter": ["cognitivecomputations/dolphin3.0-mistral-24b:free", "google/gemini-2.0-pro-exp-02-05:free", "moonshotai/moonlight-16b-a3b-instruct:free", "sophosympatheia/rogue-rose-103b-v0.2:free", "microsoft/phi-3-mini-128k-instruct:free"]
    }
    provider_options = {"1": "groq", "2": "openrouter"}
    while True:
        print("\n--- " + processor.get_text('menu.model_configuration') + " ---")
        print(processor.get_text('prompts.select_provider') + ":")
        for num, prov in provider_options.items():
            sel = f" {Fore.YELLOW}({processor.get_text('prompts.selected')}){Style.RESET_ALL}" if processor.inference == prov else ""
            print(f"{num}. {prov}{sel}")
        print("\n---- API KEY ----")
        cur_key = processor.api_key_groq if processor.inference == "groq" else processor.api_key_openrouter
        key_disp = f" {Fore.RED}({processor.get_text('prompts.required')}){Style.RESET_ALL}" if not cur_key else f" ({cur_key})"
        print("3. " + processor.get_text('prompts.type_api_key') + key_disp)
        print("\n---- " + processor.get_text('menu.model') + " ----")
        models = available_models.get(processor.inference, [])
        base = 4
        for idx, m in enumerate(models):
            option = base + idx
            sel = f" {Fore.YELLOW}({processor.get_text('prompts.selected')}){Style.RESET_ALL}" if processor.model == m else ""
            print(f"{option}. {m}{sel}")
        # Adiciona a opção de toggle para USE_EN_INSTRUCT
        current_flag = processor.translation_settings.get('use_english_instructions', True)
        color = Fore.GREEN if current_flag else Fore.RED
        option_toggle = base + len(models)
        print(f"{option_toggle}. USE_EN_INSTRUCT = {color}{current_flag}{Style.RESET_ALL}")
        exit_option = option_toggle + 1
        print(f"\n{exit_option}. " + processor.get_text('menu.exit'))
        
        choice = input(processor.get_text('prompts.choose_option') + ": ").strip()
        if choice in provider_options:
            processor.inference = provider_options[choice]
            if processor.inference == "groq":
                processor.model = processor.translation_settings.get('model_groq', "")
            else:
                processor.model = processor.translation_settings.get('model_openrouter', "")
        elif choice == "3":
            new_key = input(processor.get_text('prompts.type_api_key') + ": ").strip()
            if processor.inference == "groq":
                processor.api_key_groq = new_key
            else:
                processor.api_key_openrouter = new_key
        else:
            try:
                num_choice = int(choice)
                if base <= num_choice < base + len(models):
                    processor.model = models[num_choice - base]
                elif num_choice == option_toggle:
                    # Toggle da flag use_english_instructions
                    processor.translation_settings['use_english_instructions'] = not current_flag
                    processor.save_translation_settings()
                    update_gender_instruction(processor)
                    print(f"USE_EN_INSTRUCT set to {processor.translation_settings['use_english_instructions']}")
                elif num_choice == exit_option:
                    break
                else:
                    print(processor.get_text('error.invalid_option'))
            except Exception as e:
                print(f"{processor.get_text('error.invalid_input')}: {e}")
        processor.save_translation_settings()
        processor.set_translator_service()

if __name__ == "__main__":
    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    processor = CharacterProcessor()
    show_menu(processor)
