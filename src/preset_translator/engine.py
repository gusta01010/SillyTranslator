import json
import re
import os
from deep_translator import GoogleTranslator as Translator
from groq import Groq, APIError as GroqAPIError
from openai import OpenAI, APIError

CONFIG_FILE = "./config.json"
LANGUAGES_FILE = "./lang/lang_data.json"
MAX_CHUNK_CHAR_LIMIT = 4500

TARGET_FIELDS = {
    "content", "new_group_chat_prompt", "new_example_chat_prompt",
    "continue_nudge_prompt", "wi_format", "personality_format",
    "group_nudge_prompt", "scenario_format", "new_chat_prompt",
    "impersonation_prompt", "bias_preset_selected", "assistant_impersonation"
}

CODE_BLOCK_PLACEHOLDER_PREFIX = "__CODE_BLOCK_"
INLINE_CODE_PLACEHOLDER_PREFIX = "__INLINE_CODE_"
VAR_PLACEHOLDERS = {"{{char}}": "Jane", "{{user}}": "James"}
REVERSED_VAR_PLACEHOLDERS = {v: k for k, v in VAR_PLACEHOLDERS.items()}

def load_json_safe(filepath, default=None):
    """Loads a JSON file safely, returning a default value on error."""
    try:
        if not os.path.exists(filepath):
            return default if default is not None else {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error loading JSON from {filepath}: {e}. Returning default.")
        return default if default is not None else {}

def save_json(filepath, data):
    """Saves data to a JSON file, creating directories if needed."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except (IOError, OSError) as e:
        print(f"Error saving JSON to {filepath}: {e}")
        return False

class TranslationConfig:
    """Manages application configuration and language settings."""
    def __init__(self):
        self.data = self._load_or_create_config()
        lang_data = load_json_safe(LANGUAGES_FILE, {"languages": {"en": "English"}})
        self.languages = lang_data.get("languages", {"en": "English"})
        self.current_lang = self.data.get("last_used_language", "en")
        if self.current_lang not in self.languages:
            self.current_lang = "en"

    def _load_or_create_config(self):
        defaults = {
            "silly_tavern_path": "", "last_used_language": "en",
            "translate_angle": False, "save_location": "silly",
            "use_llm_translation": False, "llm_provider": "openrouter",
            "openrouter_api_key": "", "openrouter_model": "mistralai/mistral-7b-instruct:free",
            "groq_api_key": "", "groq_model": "llama3-8b-8192",
        }
        loaded_config = load_json_safe(CONFIG_FILE)
        config = {**defaults, **loaded_config}
        if not loaded_config or any(key not in loaded_config for key in defaults):
            save_json(CONFIG_FILE, config)
        return config

    def save(self):
        save_json(CONFIG_FILE, self.data)

    def get_lang_code(self, native_name):
        return next((code for code, name in self.languages.items() if name == native_name), None)

    def get_native_name(self, code):
        return self.languages.get(code, "English")

class TranslationEngine:
    """Handles text chunking, translation, and formatting preservation."""
    def __init__(self):
        self.google_translator = Translator(source='auto', target='en')
        self.openrouter_client = None
        self.groq_client = None

    def _extract_and_protect(self, text):
        protected_items = {}
        text = text.replace("{{char}}", VAR_PLACEHOLDERS["{{char}}"])
        text = text.replace("{{user}}", VAR_PLACEHOLDERS["{{user}}"])

        triple_backtick_pattern = r'```(?:[^\n]*?\n)?[\s\S]*?\n```'
        inline_backtick_pattern = r'`[^`\n]+`'
        matches = list(re.finditer(f"({triple_backtick_pattern})|({inline_backtick_pattern})", text))

        for match in reversed(matches):
            is_block = match.group(1) is not None
            placeholder_prefix = CODE_BLOCK_PLACEHOLDER_PREFIX if is_block else INLINE_CODE_PLACEHOLDER_PREFIX
            placeholder = f"{placeholder_prefix}{len(protected_items)}"
            protected_items[placeholder] = match.group(0)
            text = text[:match.start()] + placeholder + text[match.end():]
        return text, protected_items

    def _restore_protected(self, text, protected_items):
        for placeholder, original_text in protected_items.items():
            text = text.replace(placeholder, original_text)
        for placeholder_val, original_key in REVERSED_VAR_PLACEHOLDERS.items():
            text = text.replace(placeholder_val, original_key)
        return text

    def _post_process_formatting(self, text):
        text = re.sub(r'\s+([.,;:])', r'\1', text)
        text = re.sub(r'([.,;:])(?=[^\s\)\}\]])', r'\1 ', text)
        text = re.sub(r'([.!?])(?=[^\s\)\}\]])', r'\1 ', text)
        text = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def _initialize_llm_clients(self, provider, api_key):
        try:
            if provider == 'openrouter' and not self.openrouter_client and api_key:
                self.openrouter_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
            elif provider == 'groq' and not self.groq_client and api_key:
                self.groq_client = Groq(api_key=api_key)
        except Exception as e:
            print(f"Failed to initialize {provider} client: {e}")

    def _clean_llm_response(self, text):
        reasoning_pattern = r'<\w+>[\s\S]*?<\/\w+>'
        cleaned_text = re.sub(reasoning_pattern, '', text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'^```(\w+)?\n', '', cleaned_text)
        cleaned_text = re.sub(r'\n```$', '', cleaned_text)
        return cleaned_text.strip()

    def _translate_with_llm(self, text, target_lang_name, llm_config, translate_angle):
        """
        Translates a text using the configured LLM provider with an improved prompt.
        """
        provider = llm_config['provider']
        self._initialize_llm_clients(provider, llm_config['api_key'])
        client = self.openrouter_client if provider == 'openrouter' else self.groq_client

        if not client:
            raise ValueError(f"{provider.capitalize()} client not initialized. Check API key.")

        angle_instruction = "Also, translate any text wrapped inside angle interior of the angle braces (<...>)." if translate_angle else "Do NOT translate any content inside angle braces (<>). Keep the content within them exactly as it appears in the original text."

        prompt = (
            f"You are a raw text translator. Your sole task is to translate the user's text into {target_lang_name}. "
            f"Provide ONLY the direct translation. Do NOT include explanations, apologies, or any XML-style reasoning tags like `<thinking>` or `<rationale>`."
            f"\n{angle_instruction} "
            f"\nDO NOT translate any content, or text wrapped inside curly brackets or double curly brackets ({{{{..}}}}).\n"
            f"Your entire output must be the translated text and nothing else.\n\n"
            f"Translate the following text:\n\n"
            f"```text\n{text}\n```"
        )

        try:
            completion = client.chat.completions.create(
                model=llm_config['model'],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw_response = completion.choices[0].message.content

            return self._clean_llm_response(raw_response)
        except (APIError, GroqAPIError) as e:
            raise ConnectionError(f"API Error with {provider}: {e}")
        except Exception as e:
            raise RuntimeError(f"An unexpected error occurred during LLM translation: {e}")

    def _translate_with_google(self, text, target_lang_code):
        self.google_translator.target = target_lang_code
        
        sentences = re.split(r'(?<=[.!?])\s+', text)
        translated_text = ""
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) > MAX_CHUNK_CHAR_LIMIT:
                if current_chunk:
                    translated_text += self.google_translator.translate(text=current_chunk) + " "
                current_chunk = sentence
            else:
                current_chunk += sentence + " "

        if current_chunk:
            translated_text += self.google_translator.translate(text=current_chunk.strip())
        return translated_text

    def translate_text(self, text, **kwargs):
        if not isinstance(text, str) or not text.strip():
            return text

        processed_text, protected_items = self._extract_and_protect(text)
        
        translate_angle = kwargs.get('translate_angle', False)

        if kwargs.get('use_llm') and kwargs.get('llm_config'):
            final_translation = self._translate_with_llm(processed_text, kwargs['target_lang_name'], kwargs['llm_config'], translate_angle)
        else:
            final_translation = self._translate_with_google(processed_text, kwargs['target_lang_code'])

        restored_text = self._restore_protected(final_translation, protected_items)
        return self._post_process_formatting(restored_text)
    
    def translate_json_data(self, data, **kwargs):
        items_to_translate = []
        def find_items(current_data):
            if isinstance(current_data, dict):
                for key, value in current_data.items():
                    if key in TARGET_FIELDS and isinstance(value, str) and value.strip():
                        items_to_translate.append((current_data, key))
                    elif isinstance(value, (dict, list)):
                        find_items(value)
            elif isinstance(current_data, list):
                for item in current_data: find_items(item)

        find_items(data)
        on_progress = kwargs.pop('on_progress', None)

        for i, (container, key) in enumerate(items_to_translate):
            if on_progress: on_progress(i, len(items_to_translate))
            original_value = container[key]
            container[key] = self.translate_text(original_value, **kwargs)

        if on_progress: on_progress(len(items_to_translate), len(items_to_translate))
        return data