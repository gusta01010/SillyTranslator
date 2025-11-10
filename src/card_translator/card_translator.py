import os
import json
import base64
import hashlib
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import httpcore
setattr(httpcore, 'SyncHTTPTransport', Any) #fixes http transport error
from colorama import init, Fore, Style
import asyncio

init(autoreset=True)

@dataclass
class Config:
    """Configuration settings"""
    characters_dir: str = ""
    target_lang: str = "pt"
    translate_names: bool = False
    translate_greetings: bool = True # new setting to switch between alternate greetings to be translated or not
    translate_angles: bool = False
    service: str = "google"
    use_char_name: bool = False
    api_key: str = ""
    model: str = "llama-3.3-70b-versatile"
    provider: str = "groq"  # groq or openrouter

class Translator:
    """Base translator class"""
    def translate(self, text: str, target_lang: str) -> str:
        raise NotImplementedError

class GoogleTranslator(Translator):
    """Free Google Translate service with chunking support"""
    
    def __init__(self):
        try:
            from googletrans import Translator as GT
            self.translator = GT()
            self.max_chunk_size = 4500
            
            # create a dedicated event loop for translations
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self.thread.start()
            
        except ImportError:
            print("googletrans not installed. Run: pip install googletrans==4.0.0rc1")
            self.translator = None
            self.loop = None
    
    def _run_event_loop(self):
        """Run the event loop in a separate thread"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def translate(self, text: str, target_lang: str) -> str:
        if not self.translator or not text or not text.strip() or not self.loop:
            return text
            
        try:
            # If text is short enough, translate directly
            if len(text) <= self.max_chunk_size:
                future = asyncio.run_coroutine_threadsafe(
                    self.translator.translate(text, dest=target_lang),
                    self.loop
                )
                result = future.result(timeout=30)  # 30 second timeout
                return result.text if result and hasattr(result, 'text') else text
            
            # for long texts, split into chunks
            return self._translate_chunked(text, target_lang)
                
        except Exception as e:
            print(f"Translation error: {e}")
            return text
    
    def _translate_chunked(self, text: str, target_lang: str) -> str:
        """Translate long text by splitting into chunks"""
        # Split by paragraphs first (double newlines)
        paragraphs = text.split('\n\n')
        translated_paragraphs = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit, translate current chunk
            if len(current_chunk) + len(paragraph) + 2 > self.max_chunk_size and current_chunk:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.translator.translate(current_chunk.strip(), dest=target_lang),
                        self.loop
                    )
                    result = future.result(timeout=30)
                    translated_paragraphs.append(result.text if result and hasattr(result, 'text') else current_chunk.strip())
                    current_chunk = paragraph
                except Exception as e:
                    print(f"Chunk translation error: {e}")
                    translated_paragraphs.append(current_chunk.strip())
                    current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Translate remaining chunk
        if current_chunk:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.translator.translate(current_chunk.strip(), dest=target_lang),
                    self.loop
                )
                result = future.result(timeout=30)
                translated_paragraphs.append(result.text if result and hasattr(result, 'text') else current_chunk.strip())
            except Exception as e:
                print(f"Final chunk translation error: {e}")
                translated_paragraphs.append(current_chunk.strip())
        
        return '\n\n'.join(translated_paragraphs)
    
    def __del__(self):
        """Clean up the event loop when the translator is destroyed"""
        if hasattr(self, 'loop') and self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

class LLMTranslator(Translator):
    """LLM-based translator (Groq/OpenRouter)"""
    def __init__(self, api_key: str, provider: str, model: str):
        self.api_key = api_key
        self.provider = provider
        self.model = model
        
    def translate(self, text: str, target_lang: str) -> str:
        if not self.api_key:
            return text
            
        prompt = f"""Translate the following text to {target_lang}. 
        Preserve formatting, keep {{{{char}}}} and {{{{user}}}} unchanged, respecting their respective genders.
        Do not translate any content inside <> or {{{{}}}} brackets. Translate the content below and output only the desired translated result according to the rules, without any kind of additional comment:
        
        {text}"""
        
        try:
            if self.provider == "groq":
                return self._groq_translate(prompt)
            elif self.provider == "openrouter":
                return self._openrouter_translate(prompt)
        except Exception as e:
            print(f"LLM translation error: {e}")
            return text
    
    def _groq_translate(self, prompt: str) -> str:
        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model
            )
            return response.choices[0].message.content
        except ImportError:
            print("Groq library not installed. Run: pip install groq")
            return ""
    
    def _openrouter_translate(self, prompt: str) -> str:
        try:
            import openai
            client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except ImportError:
            print("OpenAI library not installed. Run: pip install openai")
            return ""

class CharacterProcessor:
    """Main character card processor"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self.config = self.load_config()
        self.db_file = Path("translation_db.json")
        self.db = self.load_db()
        self.translator = self.setup_translator()
        self.monitoring = False
        
        # Create necessary directories
        self.original_dir = Path("./Original")
        self.original_dir.mkdir(exist_ok=True)
        
    def load_config(self) -> Config:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return Config(**data)
            except Exception as e:
                print(f"Error loading config: {e}")
        
        # Create default config
        config = Config()
        self.save_config(config)
        return config
    
    def save_config(self, config: Config = None):
        """Save configuration to file"""
        if config is None:
            config = self.config
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(config), f, indent=2, ensure_ascii=False)
    
    def load_db(self) -> Dict[str, str]:
        """Load translation database"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def save_db(self):
        """Save translation database"""
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, indent=2)
    
    def setup_translator(self) -> Translator:
        """Setup the appropriate translator"""
        if self.config.service == "llm":
            return LLMTranslator(self.config.api_key, self.config.provider, self.config.model)
        else:
            return GoogleTranslator()
    
    def get_file_hash(self, file_path: Path) -> str:
        """Get MD5 hash of file"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def extract_character_data(self, image_path: Path) -> Optional[Dict]:
        """Extract character data from PNG image using PIL"""
        try:
            with Image.open(image_path) as img:
                # Check for 'chara' metadata in PNG text chunks
                if hasattr(img, 'text') and 'chara' in img.text:
                    chara_data = img.text['chara']
                elif hasattr(img, 'info') and 'chara' in img.info:
                    chara_data = img.info['chara']
                else:
                    print(f"No 'chara' metadata found in {image_path.name}")
                    return None
                
                # Decode base64 and parse JSON
                try:
                    decoded_data = base64.b64decode(chara_data).decode('utf-8')
                    char_data = json.loads(decoded_data)
                    print(f"✓ Successfully extracted character data from {image_path.name}")
                    return char_data
                except (base64.binascii.Error, json.JSONDecodeError) as e:
                    print(f"Error decoding character data from {image_path.name}: {e}")
                    return None
                    
        except Exception as e:
            print(f"Error opening image {image_path}: {e}")
        
        return None
    
    def translate_text(self, text: str, char_name: Optional[str] = None, field_name: Optional[str] = None) -> str:
        """Translate text while preserving formatting"""
        if not text or not isinstance(text, str):
            return text
        
        # Skip translation for very short text or placeholders
        if len(text.strip()) < 3 or text.strip() in ['{{char}}', '{{user}}']:
            return text
        
        # Replace character name temporarily if needed
        original_text = text
        if char_name and self.config.use_char_name:
            text = text.replace('{{char}}', char_name)
        
        # Add special instruction for mes_example
        if field_name == 'mes_example':
            text = """IMPORTANT INSTRUCTIONS:
    1. Before each dialogue example, add the <START> tag in plain english  on its own line if it does not exist yet, example:
    <START>
    {{user}}:..
    {{char}}:..
    ...
    2. Preserve all markdown formatting"""
        
        # Translate
        translated = self.translator.translate(text, self.config.target_lang)
        
        # Restore character placeholder
        if char_name and self.config.use_char_name:
            translated = translated.replace(char_name, '{{char}}')
        
        return translated if translated != original_text else original_text
    
    def fields_are_identical(self, field1: str, field2: str) -> bool:
        """Check if two fields contain identical content (ignoring whitespace)"""
        if not field1 or not field2:
            return False
        return field1.strip() == field2.strip()
    
    def translate_character_data(self, data: Dict, char_name: Optional[str] = None) -> Dict:
        """Translate character data fields with duplicate detection"""
        # Create a deep copy to avoid modifying original
        original_data = json.loads(json.dumps(data))  # Keep original for comparison
        translated_data = json.loads(json.dumps(data))
        
        # Main translatable fields at root level
        root_translatable_fields = [
            'description', 'personality', 'scenario', 'first_mes', 'mes_example'
        ]
        
        # Check if we have both root and data fields
        has_data_object = 'data' in translated_data and isinstance(translated_data['data'], dict)
        
        # Dictionary to store translations to avoid duplicate work
        translation_cache = {}
        
        # Translate root level fields first
        for field in root_translatable_fields:
            if field in translated_data and isinstance(translated_data[field], str) and translated_data[field].strip():
                print(f"  Translating {field}...")
                translated_text = self.translate_text(translated_data[field], char_name)
                translated_data[field] = translated_text
                # Cache the translation using original text as key
                translation_cache[original_data[field]] = translated_text
        
        # Translate name if enabled
        if self.config.translate_names and 'name' in translated_data and translated_data['name'].strip():
            print(f"  Translating name...")
            translated_name = self.translate_text(translated_data['name'])
            translated_data['name'] = translated_name
            translation_cache[original_data.get('name', '')] = translated_name
        
        # Handle alternate greetings at root level
        if self.config.translate_greetings and 'alternate_greetings' in translated_data and isinstance(translated_data['alternate_greetings'], list):
            print(f"  Translating {len(translated_data['alternate_greetings'])} root alternate greetings...")
            translated_greetings = []
            for i, greeting in enumerate(translated_data['alternate_greetings']):
                if isinstance(greeting, str) and greeting.strip():
                    # Check cache first
                    if greeting in translation_cache:
                        translated_greetings.append(translation_cache[greeting])
                    else:
                        translated_greeting = self.translate_text(greeting, char_name)
                        translated_greetings.append(translated_greeting)
                        translation_cache[greeting] = translated_greeting
                else:
                    translated_greetings.append(greeting)
            translated_data['alternate_greetings'] = translated_greetings
        
        # Handle the nested 'data' object with duplicate detection
        if has_data_object:
            data_obj = translated_data['data']
            original_data_obj = original_data['data']
            
            # Translatable fields in data object
            data_translatable_fields = [
                'description', 'personality', 'scenario', 'first_mes', 'mes_example',
                'creator_notes', 'system_prompt', 'post_history_instructions'
            ]
            
            # Translate data object fields, checking for duplicates
            for field in data_translatable_fields:
                if field in data_obj and isinstance(data_obj[field], str) and data_obj[field].strip():
                    # Check if this field is identical to ORIGINAL root field
                    original_root_value = original_data.get(field, '')
                    original_data_value = original_data_obj.get(field, '')
                    
                    if self.fields_are_identical(original_root_value, original_data_value):
                        # Copy the already translated root field
                        #print(f"  Copying translated {field} from root to data...")
                        data_obj[field] = translated_data[field]
                    else:
                        # Check translation cache
                        if original_data_value in translation_cache:
                            print(f"  Using cached translation for data.{field}...")
                            data_obj[field] = translation_cache[original_data_value]
                        else:
                            # Translate separately
                            print(f"  Translating data.{field}...")
                            translated_text = self.translate_text(data_obj[field], char_name)
                            data_obj[field] = translated_text
                            translation_cache[original_data_value] = translated_text
            
            # Handle data.name with duplicate detection
            if self.config.translate_names and 'name' in data_obj and data_obj['name'].strip():
                original_root_name = original_data.get('name', '')
                original_data_name = original_data_obj.get('name', '')
                
                if self.fields_are_identical(original_root_name, original_data_name):
                    print(f"  Copying translated name from root to data...")
                    data_obj['name'] = translated_data['name']
                else:
                    if original_data_name in translation_cache:
                        data_obj['name'] = translation_cache[original_data_name]
                    else:
                        print(f"  Translating data.name...")
                        translated_name = self.translate_text(data_obj['name'])
                        data_obj['name'] = translated_name
                        translation_cache[original_data_name] = translated_name
            
            # Handle data.alternate_greetings with duplicate detection
            if self.config.translate_greetings and 'alternate_greetings' in data_obj and isinstance(data_obj['alternate_greetings'], list):
                original_root_greetings = original_data.get('alternate_greetings', [])
                original_data_greetings = original_data_obj.get('alternate_greetings', [])
                
                # Check if greetings arrays are identical
                if (isinstance(original_root_greetings, list) and 
                    len(original_root_greetings) == len(original_data_greetings) and
                    all(self.fields_are_identical(str(r), str(d)) for r, d in zip(original_root_greetings, original_data_greetings))):
                    print(f"  Copying translated alternate greetings from root to data...")
                    data_obj['alternate_greetings'] = translated_data['alternate_greetings']
                else:
                    print(f"  Translating {len(data_obj['alternate_greetings'])} data alternate greetings...")
                    translated_greetings = []
                    for greeting in data_obj['alternate_greetings']:
                        if isinstance(greeting, str) and greeting.strip():
                            if greeting in translation_cache:
                                translated_greetings.append(translation_cache[greeting])
                            else:
                                translated_greeting = self.translate_text(greeting, char_name)
                                translated_greetings.append(translated_greeting)
                                translation_cache[greeting] = translated_greeting
                        else:
                            translated_greetings.append(greeting)
                    data_obj['alternate_greetings'] = translated_greetings
            
            # Handle extensions.depth_prompt.prompt
            if ('extensions' in data_obj and 
                isinstance(data_obj['extensions'], dict) and
                'depth_prompt' in data_obj['extensions'] and
                isinstance(data_obj['extensions']['depth_prompt'], dict) and
                'prompt' in data_obj['extensions']['depth_prompt']):
                
                depth_prompt = data_obj['extensions']['depth_prompt']['prompt']
                if isinstance(depth_prompt, str) and depth_prompt.strip():
                    if depth_prompt in translation_cache:
                        data_obj['extensions']['depth_prompt']['prompt'] = translation_cache[depth_prompt]
                    else:
                        print(f"  Translating depth_prompt...")
                        translated_prompt = self.translate_text(depth_prompt, char_name)
                        data_obj['extensions']['depth_prompt']['prompt'] = translated_prompt
                        translation_cache[depth_prompt] = translated_prompt
        
        return translated_data
        
    def save_translated_card(self, original_file: Path, translated_data: Dict):
        """Save translated card as PNG with metadata in chara_card_v2 format"""
        try:
            # Clean up fields that should be reset
            if 'chat' in translated_data:
                translated_data['chat'] = None
            if 'create_date' in translated_data:
                translated_data['create_date'] = None
            
            # Ensure spec version is maintained
            if 'spec' not in translated_data:
                translated_data['spec'] = 'chara_card_v2'
            if 'spec_version' not in translated_data:
                translated_data['spec_version'] = '2.0'
            
            # Encode data as base64
            json_str = json.dumps(translated_data, ensure_ascii=False, separators=(',', ':'))
            b64_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            
            # Open original image and save with new metadata
            with Image.open(original_file) as img:
                # Create new metadata
                metadata = PngInfo()
                metadata.add_text("chara", b64_data)
                metadata.add_text("Ccv3", b64_data) 
                
                # Copy other existing metadata if present (except chara and Ccv3)
                if hasattr(img, 'text'):
                    for key, value in img.text.items():
                        if key not in ['chara', 'Ccv3']:  # Don't copy old chara/Ccv3 data
                            metadata.add_text(key, value)
                
                # Save to characters directory
                characters_dir = Path(self.config.characters_dir)
                output_path = characters_dir / original_file.name
                
                # Ensure output directory exists
                characters_dir.mkdir(parents=True, exist_ok=True)
                
                # Save with new metadata
                img.save(output_path, "PNG", pnginfo=metadata)
                
                print(f"{Fore.GREEN}✓ Translated card saved: {output_path.name}{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"{Fore.RED}✗ Error saving translated card {original_file.name}: {e}{Style.RESET_ALL}")
            raise
    
    def process_character(self, image_path: Path):
        """Process a single character card"""
        # Check if already processed
        file_hash = self.get_file_hash(image_path)
        if image_path.name in self.db and self.db[image_path.name] == file_hash:
            return
        
        print(f"{Fore.YELLOW}📝 Processing: {image_path.name}{Style.RESET_ALL}")
        
        # Move to original directory
        original_file = self.original_dir / image_path.name
        if not original_file.exists():
            os.rename(image_path, original_file)
        
        # Extract character data
        char_data = self.extract_character_data(original_file)
        if not char_data:
            print(f"{Fore.RED}✗ Failed to extract data from {image_path.name}{Style.RESET_ALL}")
            return
        
        # Get character name
        char_name = None
        if isinstance(char_data, dict):
            char_name = char_data.get('name') or char_data.get('data', {}).get('name')
        
        # Translate
        translated_data = self.translate_character_data(char_data.copy(), char_name)
        
        # Save translated card
        self.save_translated_card(original_file, translated_data)
        
        # Update database
        self.db[original_file.name] = file_hash
        self.save_db()
    
    def process_existing_files(self):
        """Process all existing files in directory"""
        characters_dir = Path(self.config.characters_dir)
        if not characters_dir.exists():
            print(f"{Fore.RED}Characters directory does not exist!{Style.RESET_ALL}")
            return
        
        png_files = list(characters_dir.glob('*.png'))
        if not png_files:
            print(f"{Fore.YELLOW}No PNG files found in directory{Style.RESET_ALL}")
            return
            
        print(f"{Fore.BLUE}📁 Found {len(png_files)} PNG files{Style.RESET_ALL}")
        
        # Filter files that need processing (only new files not in database)
        files_to_process = []
        for file_path in png_files:
            try:
                if file_path.name not in self.db:
                    files_to_process.append(file_path)
            except Exception as e:
                print(f"{Fore.RED}✗ Error checking {file_path.name}: {e}{Style.RESET_ALL}")
        
        if not files_to_process:
            print(f"{Fore.GREEN}✓ All files are already in translation database{Style.RESET_ALL}")
            return
            
        print(f"{Fore.BLUE}🔄 Processing {len(files_to_process)} new files not yet translated...{Style.RESET_ALL}")
        
        processed = 0
        for file_path in files_to_process:
            try:
                self.process_character(file_path)
                processed += 1
            except Exception as e:
                print(f"{Fore.RED}✗ Error processing {file_path.name}: {e}{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}✅ Completed processing {processed}/{len(files_to_process)} files{Style.RESET_ALL}")

class FileHandler(FileSystemEventHandler):
    """File system event handler"""
    
    def __init__(self, processor: CharacterProcessor):
        self.processor = processor
        
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.png'):
            self._handle_new_file(event.src_path)
    
    def on_moved(self, event):
        if not event.is_directory and event.dest_path.endswith('.png'):
            self._handle_new_file(event.dest_path)
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.png'):
            # Check if it's a new file (not in database)
            file_path = Path(event.src_path)
            if file_path.name not in self.processor.db:
                self._handle_new_file(event.src_path)
    
    def _handle_new_file(self, file_path_str):
        """Handle new PNG file detection"""
        file_path = Path(file_path_str)
        
        # Small delay to ensure file is fully written
        time.sleep(2)
        
        # Check if file still exists and is not in database
        if file_path.exists() and file_path.name not in self.processor.db:
            print(f"{Fore.CYAN}🔔 New file detected: {file_path.name}{Style.RESET_ALL}")
            try:
                self.processor.process_character(file_path)
            except Exception as e:
                print(f"{Fore.RED}✗ Error processing new file {file_path.name}: {e}{Style.RESET_ALL}")

def show_current_status(processor: CharacterProcessor):
    """Show current translation settings in a compact format"""
    print(f"\n{Fore.BLUE}=== Current Settings ==={Style.RESET_ALL}")
    
    if processor.config.characters_dir and Path(processor.config.characters_dir).exists():
        dir_name = Path(processor.config.characters_dir).name
        print(f"📁 Directory: .../{dir_name}")
    else:
        print(f"📁 Directory: {Fore.YELLOW}Not configured (REQUIRED!){Style.RESET_ALL}")
    
    # Translation service and details
    if processor.config.service == "llm":
        status = f"🤖 LLM: {processor.config.provider.upper()} - {processor.config.model}"
        if not processor.config.api_key:
            status += f" {Fore.RED}(No API Key){Style.RESET_ALL}"
    else:
        status = f"🌐 Service: Google Translate"
    
    print(status)
    
    lang_upper = processor.config.target_lang.upper()
    options = []
    if processor.config.translate_names:
        options.append("Names")
    if processor.config.translate_greetings:
        options.append("Greetings")
    if processor.config.use_char_name:
        options.append("Use char name")
    
    options_str = f" ({', '.join(options)})" if options else ""
    print(f"🌍 Target: {lang_upper}{options_str}")
    
    # Database status
    db_count = len(processor.db)
    print(f"📊 Processed: {db_count} files")

def configure_settings(processor: CharacterProcessor):
    """Interactive configuration menu"""
    while True:
        print(f"\n{Fore.BLUE}=== Configuration ==={Style.RESET_ALL}")
        print(f"1. Characters Directory: {processor.config.characters_dir or 'Not set'}")
        print(f"2. Target Language: {processor.config.target_lang}")
        print(f"3. Translation Service: {processor.config.service}")
        print(f"4. Translate Names: {processor.config.translate_names}")
        print(f"5. Translate Alternate Greetings: {processor.config.translate_greetings}")
        print(f"6. Use Character Name: {processor.config.use_char_name}")
        if processor.config.service == "llm":
            print(f"7. API Provider: {processor.config.provider}")
            print(f"8. Model: {processor.config.model}")
            print(f"9. API Key: {'Set' if processor.config.api_key else 'Not set'}")
        print("10. Back to main menu")
        
        choice = input(f"\n{Fore.GREEN}Choose option: {Style.RESET_ALL}").strip()
        
        if choice == "1":
            new_dir = input("Enter SillyTavern root or characters directory path: ").strip()
            if new_dir:
                dir_path = Path(new_dir)
                
                # Check if it's SillyTavern root directory
                if dir_path.exists() and dir_path.is_dir():
                    # Look for characters directory
                    possible_chars_dir = dir_path / 'data' / 'default-user' / 'characters'
                    
                    if possible_chars_dir.exists():
                        # It's SillyTavern root, use the characters subdirectory
                        processor.config.characters_dir = str(possible_chars_dir)
                        print(f"{Fore.GREEN}✓ Found SillyTavern characters directory: {possible_chars_dir}{Style.RESET_ALL}")
                    elif dir_path.name == 'characters' or any(f.suffix == '.png' for f in dir_path.glob('*.png')):
                        # It's likely the characters directory itself
                        processor.config.characters_dir = str(dir_path)
                        print(f"{Fore.GREEN}✓ Using characters directory: {dir_path}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}⚠️  Directory found but no characters folder detected. Using as-is.{Style.RESET_ALL}")
                        processor.config.characters_dir = str(dir_path)
                    
                    processor.save_config()
                else:
                    print(f"{Fore.RED}Directory not found!{Style.RESET_ALL}")
                
        elif choice == "2":
            langs = {"1": "pt-BR", "2": "en-US", "3": "es-US", "4": "fr-FR", "5": "it-IT", "6": "de-DE", "7": "ja-JP", "8": "zh-CN", "9": "ru-RU", "10": "ko-KR"}
            print("Languages: 1=Portuguese, 2=English, 3=Spanish, 4=French, 5=Italian, 6=German, 7=Japanese, 8=Chinese, 9=Russian, 10=Korean")
            lang_choice = input("Choose language: ").strip()
            if lang_choice in langs:
                processor.config.target_lang = langs[lang_choice]
                processor.save_config()
                
        elif choice == "3":
            services = {"1": "google", "2": "llm"}
            print("Services: 1=Google Translate, 2=LLM")
            service_choice = input("Choose service: ").strip()
            if service_choice in services:
                processor.config.service = services[service_choice]
                processor.translator = processor.setup_translator()
                processor.save_config()
                
        elif choice == "4":
            processor.config.translate_names = input("Translate names? (y/n): ").lower().startswith('y')
            processor.save_config()

        elif choice == "5":
            processor.config.translate_greetings = input("Translate alternate greetings? (y/n): ").lower().startswith('y')
            processor.save_config()
            
        elif choice == "6":
            processor.config.use_char_name = input("Use character name in translation? (replaces {{char}} in translation) (y/n): ").lower().startswith('y')
            processor.save_config()
            
        elif choice == "7" and processor.config.service == "llm":
            providers = {"1": "groq", "2": "openrouter"}
            print("Providers: 1=Groq, 2=OpenRouter")
            prov_choice = input("Choose provider: ").strip()
            if prov_choice in providers:
                processor.config.provider = providers[prov_choice]
                processor.save_config()
                
        elif choice == "8" and processor.config.service == "llm":
            if processor.config.provider == "groq":
                models = ["meta-llama/llama-4-scout-17b-16e-instruct", "openai/gpt-oss-20b", "meta-llama/llama-4-maverick-17b-128e-instruct"]
            else:
                models = ["google/gemini-2.0-pro-exp-02-05:free", "microsoft/phi-3-mini-128k-instruct:free"]
            
            for i, model in enumerate(models, 1):
                print(f"{i}. {model}")
            
            model_choice = input("Choose model number: ").strip()
            try:
                idx = int(model_choice) - 1
                if 0 <= idx < len(models):
                    processor.config.model = models[idx]
                    processor.save_config()
            except ValueError:
                print(f"{Fore.RED}Invalid choice!{Style.RESET_ALL}")
                
        elif choice == "9" and processor.config.service == "llm":
            api_key = input("Enter API key: ").strip()
            processor.config.api_key = api_key
            processor.translator = processor.setup_translator()
            processor.save_config()
            
        elif choice == "10":
            break

def main():
    """Main application"""
    print(f"{Fore.CYAN}🎭 Character Card Translator{Style.RESET_ALL}")
    
    processor = CharacterProcessor()
    
    while True:
        show_current_status(processor)
        
        dir_not_set = not processor.config.characters_dir or not Path(processor.config.characters_dir).exists()
        
        print(f"\n{Fore.BLUE}=== Main Menu ==={Style.RESET_ALL}")
        print("1. Start Monitoring")
        print("2. Process Existing Files")

        if dir_not_set:
            print(f"{Fore.RED}3. Configure Settings{Style.RESET_ALL}")
        else:
            print("3. Configure Settings")

        print("4. Restore Originals")
        print("5. Clear Database")
        print("6. Exit")
        
        choice = input(f"\n{Fore.GREEN}Choose option: {Style.RESET_ALL}").strip()
        
        if choice == "1":
            if dir_not_set: # Use the pre-checked variable
                print(f"{Fore.RED}Please configure characters directory first!{Style.RESET_ALL}")
                continue
            
            if processor.config.service == "llm" and not processor.config.api_key:
                print(f"{Fore.RED}Please configure API key for LLM service first!{Style.RESET_ALL}")
                continue
                
            print(f"{Fore.BLUE}🔍 Starting monitoring of {processor.config.characters_dir}{Style.RESET_ALL}")
            
            # Process existing files first
            processor.process_existing_files()
            
            print(f"{Fore.BLUE}👀 Now monitoring for new files... (Place PNG files in the directory){Style.RESET_ALL}")
            print(f"{Fore.RED}Press Ctrl+C to stop monitoring{Style.RESET_ALL}")
            
            observer = Observer()
            event_handler = FileHandler(processor)
            observer.schedule(event_handler, processor.config.characters_dir, recursive=False)
            observer.start()
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
                print(f"\n{Fore.YELLOW}Monitoring stopped{Style.RESET_ALL}")
            
            observer.join()
            
        elif choice == "2":
            processor.process_existing_files()
            
        elif choice == "3":
            configure_settings(processor)

        elif choice == "4":
            # Restore originals
            count = 0
            for backup_file in processor.original_dir.glob('*.png'):
                target_file = Path(processor.config.characters_dir) / backup_file.name
                try:
                    # os.replace() will overwrite existing files
                    os.replace(backup_file, target_file)
                    count += 1
                except Exception as e:
                    print(f"{Fore.RED}Error restoring {backup_file.name}: {e}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}Restored {count} original files{Style.RESET_ALL}")
                    
        elif choice == "5":
            processor.db.clear()
            processor.save_db()
            print(f"{Fore.GREEN}Database cleared{Style.RESET_ALL}")
            
        elif choice == "6":
            break

if __name__ == "__main__":
    main()