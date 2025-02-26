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
init()

# Configurações
CHARACTERS_DIR = Path(r"E:\Games\SillyTavern-1.12.11\data\default-user\characters")
ORIGINAL_DIR = Path(".\\Original")
DB_FILE = Path(".\\translation_db.json")
TRANSLATION_SETTINGS_FILE = Path(".\\translation_settings.json")
INTERFACE_LANG_FILE = Path(".\\lang\\interface_languages.json")

TARGET_TEMPLATE = {
    "char_name": "",
    "char_persona": "",
    "world_scenario": "",
    "char_greeting": "",
    "example_dialogue": "",
    "name": "",
    "description": "",
    "personality": "",
    "scenario": "",
    "first_mes": "",
    "mes_example": "",
    "metadata": {
        "version": 1,
        "created": None,
        "modified": None,
        "source": None,
        "tool": {
            "name": "Card Translator",
            "version": "1.0.0",
            "url": "https://github.com/gusta01010/SillyTranslate/"
        }
    }
}

FIELD_MAPPING = {
    'char_name': ['name', 'data.name', 'char_name', 'spec.name'],
    'name': ['name', 'data.name', 'char_name', 'spec.name'],
    'char_persona': ['description', 'data.description'],
    'world_scenario': ['scenario', 'data.scenario'],
    'char_greeting': ['first_mes', 'data.first_mes'],
    'example_dialogue': ['mes_example', 'data.mes_example'],
    'description': ['description', 'data.description'],
    'scenario': ['scenario', 'data.scenario'],
    'first_mes': ['first_mes', 'data.first_mes'],
    'mes_example': ['mes_example', 'data.mes_example']
}

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
        '用户的': "user's",
        '角色的': "char's"
    },
    'ko': {
        '사용자의': "user's",
        '캐릭터의': "char's"
    },
    'ru': {
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

    def setup_dirs(self):
        ORIGINAL_DIR.mkdir(exist_ok=True, parents=True)

    def load_db(self):
        try:
            if DB_FILE.exists():
                return json.loads(DB_FILE.read_text())
        except Exception as e:
            print(f"Erro ao carregar banco de dados: {e}")
        return {}

    def load_translation_settings(self):
        default_settings = {
            'target_lang': 'pt',
            'translate_angle': False,
            'translate_name': False,
            'interface_lang': 'pt',
            'translation_service': 'google',
            'characters_dir': ''
        }
        try:
            if TRANSLATION_SETTINGS_FILE.exists():
                return json.loads(TRANSLATION_SETTINGS_FILE.read_text())
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")
        
        TRANSLATION_SETTINGS_FILE.write_text(json.dumps(default_settings, indent=2))
        return default_settings

    def apply_translation_settings(self):
        self.target_lang = self.translation_settings.get('target_lang', 'pt')
        self.translate_name = self.translation_settings.get('translate_name', False)
        self.translate_angle = self.translation_settings.get('translate_angle', False)
        self.translation_service = self.translation_settings.get('translation_service', 'google')
        self.interface_lang = self.translation_settings.get('interface_lang', 'pt')

    def set_translator_service(self):
        if self.translation_service == 'google':
            from lib.free_translator import FreeTranslator
            self.translator = FreeTranslator()
        elif self.translation_service == 'mymemory':
            from lib.mymemory_translator import MyMemoryTranslatorService
            self.translator = MyMemoryTranslatorService()
        elif self.translation_service == 'yandex':
            from lib.yandex_translator import YandexTranslator
            self.translator = YandexTranslator()
        elif self.translation_service == 'linguee':
            from lib.linguee_translator import LingueeTranslator
            self.translator = LingueeTranslator()
        elif self.translation_service == 'pons':
            from lib.pons_translator import PonsTranslator
            self.translator = PonsTranslator()
        else:
            from lib.free_translator import FreeTranslator
            self.translator = FreeTranslator()

    def save_translation_settings(self):
        self.translation_settings.update({
            'target_lang': self.target_lang,
            'translate_angle': self.translate_angle,
            'translate_name': self.translate_name,
            'interface_lang': self.interface_lang,
            'translation_service': self.translation_service,
            'characters_dir': self.characters_dir
        })
        TRANSLATION_SETTINGS_FILE.write_text(json.dumps(self.translation_settings, indent=2))

    def get_file_hash(self, file_path):
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def process_existing_files(self):
        print(f"\n{self.get_text('debug.processing_existing')}")
        for file in CHARACTERS_DIR.glob('*.png'):
            if file.name not in self.db or self.db[file.name] != self.get_file_hash(file):
                self.process_character(file)

    def save_db(self):
        try:
            DB_FILE.write_text(json.dumps(self.db, indent=2))
        except Exception as e:
            print(self.get_text('debug.db_save_error').format(e))

    def extract_metadata(self, image_path):
        try:
            # Set encoding to UTF-8 and capture stderr
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            cmd = ['magick', 'identify', '-verbose', str(image_path)]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='ignore'
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                print(self.get_text('debug.metadata_error').format(stderr))
                return None
                
            if not stdout:
                print(self.get_text('debug.no_metadata').format(image_path))
                return None
                
            return self.parse_metadata(stdout)
            
        except Exception as e:
            print(f"Erro ao extrair metadados: {str(e)}")
            return None

    def parse_metadata(self, metadata_str):
        if not metadata_str:
            return {}
            
        try:
            metadata = {}
            stack = []
            
            for line in metadata_str.split('\n'):
                line = line.rstrip()
                if not line:
                    continue

                indent = len(line) - len(line.lstrip())
                line = line.lstrip()

                if ':' not in line:
                    continue

                key, value = map(str.strip, line.split(':', 1))
                
                while stack and stack[-1][1] >= indent:
                    stack.pop()
                
                if value == '':
                    new_section = {}
                    if stack:
                        stack[-1][0][key] = new_section
                    else:
                        metadata[key] = new_section
                    stack.append((new_section, indent))
                else:
                    if stack:
                        stack[-1][0][key] = value
                    else:
                        metadata[key] = value
            
            return metadata
            
        except Exception as e:
            print(self.get_text('debug.metadata_parse_error').format(e))
            return {}

    def extract_character_data(self, metadata):
        char_data = {}
        for field in ['chara', 'ccv3']:
            if field in metadata.get('Image', {}).get('Properties', {}):
                try:
                    encoded_data = metadata['Image']['Properties'][field]
                    decoded_data = base64.b64decode(encoded_data).decode('utf-8')
                    json_data = json.loads(decoded_data)
                    char_data.update(self.flatten_json(json_data))
                    return char_data
                except Exception as e:
                    print(f"Erro ao decodificar {field}: {e}")
        return None

    def flatten_json(self, data):
        flat_data = {}
        for key, value in data.items():
            if isinstance(value, dict):
                flat_data.update(self.flatten_json(value))
            else:
                flat_data[key] = value
        return flat_data

    def map_to_template(self, raw_data):
        template = TARGET_TEMPLATE.copy()
        
        for target_field, source_fields in FIELD_MAPPING.items():
            for source_field in source_fields:
                if '.' in source_field:
                    parts = source_field.split('.')
                    value = raw_data.get(parts[0], {})
                    for part in parts[1:]:
                        value = value.get(part, '')
                else:
                    value = raw_data.get(source_field, '')
                
                if value:
                    template[target_field] = value
                    break

        template['name'] = template['char_name']
        template['metadata']['created'] = raw_data.get('create_date', 1740417962295)
        template['metadata']['modified'] = raw_data.get('create_date', 1740417962295)
        
        return template

    def fix_malformed_brackets(self, text):
        """Corrige chaves malformadas e padroniza os placeholders."""
        if not text:
            return text
            
        # Primeiro remove chaves duplicadas
        text = re.sub(r'\{{2,}', '{{', text)
        text = re.sub(r'\}{2,}', '}}', text)
        
        # Corrige espaços extras dentro das chaves e garante que tenha exatamente duas chaves
        text = re.sub(r'\{+\s*(\w+)\s*\}+', r'{{\1}}', text)
        
        # Substitui variações de assistant por char
        text = re.sub(r'\{\{?\s*assistant\s*\}?\}', '{{char}}', text, flags=re.IGNORECASE)
        
        # Corrige palavras traduzidas dentro das chaves usando o PLACEHOLDER_MAP
        def replace_placeholder(match):
            inner_text = match.group(1).lower().strip()
            for lang_map in PLACEHOLDER_MAP.values():
                if inner_text in lang_map:
                    return '{{' + lang_map[inner_text] + '}}'
            return '{{' + inner_text + '}}'
            
        text = re.sub(r'\{\{?\s*(\w+)\s*\}?\}', replace_placeholder, text)
        
        # Garante que não haja chaves duplicadas no resultado final
        text = re.sub(r'\{{2,}', '{{', text)
        text = re.sub(r'\}{2,}', '}}', text)
        
        return text

    def proteger_e_traduzir(self, texto):
        if not isinstance(texto, str) or not texto.strip():
            return texto
            
        # Corrige chaves malformadas antes da tradução
        texto = self.fix_malformed_brackets(texto)
        
        # Substituir placeholders por nomes temporários e preservar 's
        texto = texto.replace("{{user}}'s", "James's")
        texto = texto.replace("{{char}}'s", "Jane's")
        texto = texto.replace("{{user}}", "James")
        texto = texto.replace("{{char}}", "Jane")
        texto = texto.replace("<user>", "James")
        texto = texto.replace("<char>", "Jane")
            
        try:
            translated = self.translator.translate(texto, dest=self.target_lang).text
            if translated is None:
                return texto
        except Exception as e:
            print(f"Erro na tradução: {str(e)}")
            return texto
            
        # Reverter substituições preservando o 's
        translated = translated.replace("James's", "{{user}}'s")
        translated = translated.replace("Jane's", "{{char}}'s")
        translated = translated.replace("James", "{{user}}")
        translated = translated.replace("Jane", "{{char}}")
        
        # Corrige novamente chaves malformadas após a tradução
        translated = self.fix_malformed_brackets(translated)
        
        # Ajustar espaçamento e pontuação
        translated = self.fix_spacing_around_tags(translated)
        translated = self.fix_punctuation_spacing(translated)
        
        # New: Ajustar consistência dos backticks com base no original
        translated = self.adjust_backticks_consistency(texto, translated)
        
        # New: Remove spaces between backticks based on the pattern (e.g. `` ` becomes ```)
        translated = self.adjust_backticks_spacing(translated)
        
        # New: Ajustar case do texto traduzido para respeitar o original
        translated = self.adjust_translation_case(texto, translated)
        
        return translated

    def fix_spacing_around_tags(self, text):
        # Fix missing spaces after {{char}} or {{user}} when followed by text
        text = re.sub(r'(\{\{(?:char|user)\}\})([a-zA-Z])', r'\1 \2', text)
        
        # Fix missing spaces before {{char}} or {{user}} when preceded by text
        text = re.sub(r'([a-zA-Z])(\{\{(?:char|user)\}\})', r'\1 \2', text)
        
        return text

    def fix_punctuation_spacing(self, text):
        # Add space after punctuation if followed by a letter and not already spaced
        text = re.sub(r'([.,:;!?])([a-zA-Z])', r'\1 \2', text)
        
        # Remove space before punctuation
        text = re.sub(r'(\s+)([.,:;!?])', r'\2', text)
    
        return text

    # New method to adjust backticks consistency using the original text as reference
    def adjust_backticks_consistency(self, original: str, translated: str) -> str:
        orig_ticks = list(re.finditer(r'(`+)', original))
        trans_ticks = list(re.finditer(r'(`+)', translated))
        if len(orig_ticks) != len(trans_ticks):
            # fallback: leave translated unchanged if counts differ
            return translated
        orig_iter = iter([m.group(0) for m in orig_ticks])
        return re.sub(r'(`+)', lambda m: next(orig_iter), translated)
    
    # New method to adjust the case of words in translated text to match the original
    def adjust_translation_case(self, original: str, translated: str) -> str:
        words = set(re.findall(r'\b\w+\b', original))
        for word in words:
            # Replace occurrences in translated text with the original-case word if they match ignoring case.
            translated = re.sub(
                r'\b' + re.escape(word.lower()) + r'\b',
                lambda m: word,
                translated,
                flags=re.IGNORECASE
            )
        return translated

    # New method to adjust spacing around backticks by removing spaces between groups of backticks
    def adjust_backticks_spacing(self, text: str) -> str:
        pattern = re.compile(r'(`+)(\s+)(`+)')
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(lambda m: m.group(1) + m.group(3), text)
        return text

    def move_to_original(self, image_path):
        # Se o arquivo ainda não estiver na pasta ORIGINAL_DIR, mova-o
        dest = ORIGINAL_DIR / image_path.name
        if not dest.exists():
            try:
                os.rename(image_path, dest)
                print(f"{Fore.BLUE}{self.get_text('debug.file_moved').format(image_path.name, ORIGINAL_DIR)}{Style.RESET_ALL}")
            except Exception as e:
                print(self.get_text('debug.move_error').format(e))
        return dest

    def process_character(self, image_path):
        if image_path.name in self.db:
            return

        print(f"{Fore.YELLOW}{self.get_text('debug.processing_file').format(image_path.name)}{Style.RESET_ALL}")
        # Transfere o arquivo original para a pasta ORIGINAL_DIR
        original_file = self.move_to_original(image_path)

        metadata = self.extract_metadata(original_file)
        if not metadata:
            return
        raw_data = self.extract_character_data(metadata)
        if not raw_data:
            return
        template_data = self.map_to_template(raw_data)
        if not template_data['char_name'].strip():
            template_data['char_name'] = original_file.stem

        original_name = original_file.stem
        # Capture original name from metadata if exists, fallback to file stem.
        original_metadata_name = raw_data.get('name') or raw_data.get('char_name') or original_name

        if self.translate_name:
            template_data['char_name'] = self.proteger_e_traduzir(template_data['char_name'])
            template_data['name'] = template_data['char_name']
        else:
            template_data['name'] = original_name

        for field in TARGET_TEMPLATE:
            if field != 'metadata' and template_data[field]:
                if field == 'name' and not self.translate_name:
                    continue  # Skip translating the name if disabled
                template_data[field] = self.proteger_e_traduzir(template_data[field])

        # Safety check: if name translation is disabled but the name changed, restore original
        if not self.translate_name and template_data['name'].lower() != original_metadata_name.lower():
            template_data['name'] = original_metadata_name

        # Se a opção de não traduzir nomes estiver ligada,
        # para campos específicos, garanta que a substring que corresponde ao nome permaneça inalterada.
        if not self.translate_name:
            for key in ("description", "personality", "char_greeting", "example_dialogue"):
                if key in template_data and template_data[key]:
                    # Reverte qualquer tradução da substring do nome do personagem.
                    pattern = re.compile(re.escape(template_data["name"]), flags=re.IGNORECASE)
                    template_data[key] = pattern.sub(template_data["name"], template_data[key])
        
        self.save_as_json(original_file, template_data)
        # Remover o JSON temporário do Original, mantendo somente o PNG original
        json_path = original_file.with_suffix('.json')
        if json_path.exists():
            os.remove(json_path)
        
        self.embed_metadata(original_file, template_data)
        self.db[original_file.name] = True
        self.save_db()

    def embed_metadata(self, original_file, data):
        json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        b64_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        try:
            img = Image.open(original_file)
            meta = PngImagePlugin.PngInfo()
            meta.add_text("chara", b64_data)
            # Salva o arquivo traduzido em CHARACTERS_DIR com o nome original
            new_image_path = CHARACTERS_DIR / original_file.name
            img.save(new_image_path, "PNG", pnginfo=meta)
            print(f"{Fore.GREEN}{self.get_text('debug.metadata_saved').format(new_image_path)}{Style.RESET_ALL}")
        except Exception as e:
            print(self.get_text('debug.metadata_error_save').format(e))

    def save_as_json(self, image_path, data):
        json_path = image_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            # Altered to output compact JSON in one line
            f.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
        print(f"{Fore.YELLOW}{self.get_text('debug.json_generated').format(json_path)}{Style.RESET_ALL}")

    def load_interface_texts(self) -> Dict[str, Any]:
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
        """Verifica se o diretório characters é válido"""
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
    
    processor.save_translation_settings()
    processor.apply_translation_settings()

def configure_translation_service(processor):
    print(f"\n{Fore.BLUE}{processor.get_text('prompts.translation_services_available')}:{Style.RESET_ALL}")
    services = {
        '1': 'google',
        '2': 'mymemory',
        '3': 'yandex',
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
