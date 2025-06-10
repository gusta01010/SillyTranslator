import json
import re
import os
import locale
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from deep_translator import GoogleTranslator as Translator
from groq import Groq, APIError as GroqAPIError, AuthenticationError as GroqAuthError, RateLimitError as GroqRateLimitError, APIConnectionError as GroqConnectionError
from openai import OpenAI, APIError, AuthenticationError, RateLimitError, APIConnectionError
import sys  # Import sys for system language detection

CONFIG_FILE = "./config.json"
LANGUAGES_FILE = "./lang/lang_data.json"
MAX_CHUNK_SIZE = 8
TARGET_FIELDS = {
    "content", "new_group_chat_prompt", "new_example_chat_prompt",
    "continue_nudge_prompt", "wi_format", "personality_format",
    "group_nudge_prompt", "scenario_format", "new_chat_prompt",
    "impersonation_prompt", "bias_preset_selected", "assistant_impersonation"
}

CODE_BLOCK_PLACEHOLDER_PREFIX = "__CODE_BLOCK_"
INLINE_CODE_PLACEHOLDER_PREFIX = "__INLINE_CODE_"
VAR_PLACEHOLDERS = {"{{char}}": "Jane", "{{user}}": "James"} # Define this too if missing
REVERSED_VAR_PLACEHOLDERS = {v: k for k, v in VAR_PLACEHOLDERS.items()} # And this

# Helper Functions
def load_json_safe(filepath, default=None):
    """Loads JSON file safely, returning default on error."""
    try:
        # Ensure directory exists before trying to open file
        if not os.path.exists(filepath):
             print(f"Warning: File not found at {filepath}, returning default.")
             return default if default is not None else {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e: # Catch OSError too
        print(f"Error loading JSON from {filepath}: {e}. Returning default.")
        return default if default is not None else {}
    except Exception as e: # Catch any other unexpected error
        print(f"Unexpected error loading JSON from {filepath}: {e}. Returning default.")
        return default if default is not None else {}


def save_json(filepath, data):
    """Saves data to JSON file."""
    try:
        # Ensure the directory exists before writing
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except (IOError, OSError) as e: # Catch OS related errors
        print(f"Error saving JSON to {filepath}: {e}")
        return False
    except Exception as e: # Catch any other unexpected error
        print(f"Unexpected error saving JSON to {filepath}: {e}")
        return False


def get_system_lang():
    """Gets the system language code (e.g., 'en') safely."""
    try:
        # Try getting default locale
        lang = locale.getlocale()
        # Fallback if default locale is None
        if lang is None:
             lang = locale.getlocale() # Try current locale
        # Final fallback or if locale methods fail
        if lang is None:
             lang = os.environ.get('LANG', 'en_US') # Check environment variable

        return lang[:2] if lang else "en" # Extract first 2 chars
    except Exception as e: # Broad catch for any locale issue
        print(f"Could not determine system language, defaulting to 'en'. Error: {e}")
        return "en"


class TranslationConfig:
    """Manages application configuration and language settings."""
    def __init__(self):
        self.data = self._load_config()
        # --- Load language data (keep existing code) ---
        self.full_lang_data = load_json_safe(LANGUAGES_FILE, {"languages": {"en": "English"}, "en": {}})
        self.languages = self.full_lang_data.get("languages", {"en": "English"})
        self.translations = {k: v for k, v in self.full_lang_data.items() if k != "languages"}
        self.current_lang = self.data.get("last_used_language", "en")
        if self.current_lang not in self.languages: # Fallback if saved lang is invalid
             self.current_lang = get_system_lang()
             if self.current_lang not in self.languages:
                 self.current_lang = "en"
             self.data["last_used_language"] = self.current_lang
             self.save() # Save corrected language immediately


    def _load_config(self):
        """Loads or creates configuration file."""
        config = load_json_safe(CONFIG_FILE)
        # Define default values including new LLM settings
        defaults = {
            "silly_tavern_path": "",
            "last_used_language": get_system_lang(),
            "translate_angle": False,
            "save_location": "silly",
            "use_llm_translation": False,
            "llm_provider": "openrouter",
            "openrouter_api_key": "",
            "openrouter_model": "mistralai/mistral-7b-instruct:free",
            "groq_api_key": "",
            "groq_model": "llama3-8b-8192",
        }
        # Merge loaded config with defaults, prioritizing loaded values
        loaded_config = load_json_safe(CONFIG_FILE)
        config = {**defaults, **loaded_config} # Loaded values overwrite defaults

        # Save back if file didn't exist or was missing keys
        if not loaded_config or any(key not in loaded_config for key in defaults):
            save_json(CONFIG_FILE, config)
        return config

    def get_text(self, key, lang=None):
        """Retrieves translated UI text for a given key."""
        target_lang = lang or self.current_lang
        # Fallback chain: Current Lang -> English -> Key itself
        return self.translations.get(target_lang, {}).get(key,
               self.translations.get("en", {}).get(key, key))

    def save(self):
        """Saves current configuration to file."""
        # Ensure boolean value is saved correctly
        self.data["use_llm_translation"] = bool(self.data.get("use_llm_translation", False))
        save_json(CONFIG_FILE, self.data)

    def get_lang_code(self, native_name):
        """Gets language code from native name."""
        for code, name in self.languages.items():
            if name == native_name:
                return code
        return None

    def get_native_name(self, code):
        """Gets native language name from code."""
        return self.languages.get(code, "English")

class TranslationEngine:
    """Handles text chunking, translation, and formatting preservation."""
    def __init__(self, max_chunk_size=MAX_CHUNK_SIZE):
        # Google Translator can be optional if LLM is always used, but keep for fallback/default
        try:
            self.google_translator = Translator(source='auto')
        except Exception as e:
            print(f"Warning: Could not initialize Google Translator: {e}")
            self.google_translator = None

        self.max_chunk_size = max_chunk_size

        self.openrouter_client = None
        self.groq_client = None

    def _replace_vars(self, text, mapping):
        """Replaces variables using the provided mapping."""
        # Ensure mapping is applied correctly
        temp_text = text
        for k, v in mapping.items():
            # Use regex for whole word replacement to avoid partial matches if placeholders are substrings
            # Using simple replace for now as placeholders are distinct {{...}}
            temp_text = temp_text.replace(k, v)
        return temp_text

    def _extract_and_protect(self, text):
        """Extracts code blocks and variables, replacing with placeholders."""
        code_blocks = {}
        modified_text = text # Start with original text

        # Protect variables first using the instance method _replace_vars
        modified_text = self._replace_vars(modified_text, VAR_PLACEHOLDERS)

        # Regex patterns for code blocks
        triple_backtick_pattern = r'```(?:[^\n]*?\n)?[\s\S]*?\n```'
        inline_backtick_pattern = r'`[^`\n]+`' # Avoid matching across newlines

        # --- Extract triple backticks ---
        # Need a function for re.sub to handle placeholder generation correctly
        processed_indices = set() # To avoid replacing inside already replaced blocks
        def repl_triple(match):
            if match.start() in processed_indices: # Check if already processed (unlikely here but safe)
                return match.group(0)
            placeholder = f"{CODE_BLOCK_PLACEHOLDER_PREFIX}{len(code_blocks)}"
            code_blocks[placeholder] = match.group(0)
            # Mark indices covered by this match as processed
            for i in range(match.start(), match.end()):
                 processed_indices.add(i)
            return placeholder

        # Apply triple backtick replacement iteratively if needed (safer for overlapping potential)
        # Though the regex should handle non-overlapping cases well
        modified_text = re.sub(triple_backtick_pattern, repl_triple, modified_text)


        # --- Extract inline backticks ---
        matches = []
        # Find triple backticks
        for match in re.finditer(triple_backtick_pattern, modified_text):
            matches.append({'start': match.start(), 'end': match.end(), 'text': match.group(0), 'type': 'block'})
        # Find inline backticks
        for match in re.finditer(inline_backtick_pattern, modified_text):
             # Check if inside a triple backtick match
             is_inside = False
             for block_match in matches:
                 if block_match['type'] == 'block' and block_match['start'] <= match.start() and match.end() <= block_match['end']:
                     is_inside = True
                     break
             if not is_inside:
                matches.append({'start': match.start(), 'end': match.end(), 'text': match.group(0), 'type': 'inline'})

        # Sort matches by start position, longest first if they start at the same place
        matches.sort(key=lambda m: (m['start'], -(m['end'] - m['start'])))

        # Replace non-overlapping matches from right to left (avoids index issues)
        final_processed_text = modified_text
        # Create a separate dictionary for code blocks identified in this pass
        current_code_blocks = {}

        processed_ranges = [] # Keep track of ranges already replaced

        for match_info in reversed(matches):
             start, end = match_info['start'], match_info['end']
             original_match_text = match_info['text']
             match_type = match_info['type']

             # Check for overlap with already processed ranges
             is_overlapping = False
             for p_start, p_end in processed_ranges:
                 if max(start, p_start) < min(end, p_end): # Overlap condition
                     is_overlapping = True
                     break
             if is_overlapping:
                 continue # Skip this match if it overlaps

             # Generate placeholder
             placeholder_prefix = CODE_BLOCK_PLACEHOLDER_PREFIX if match_type == 'block' else INLINE_CODE_PLACEHOLDER_PREFIX
             placeholder = f"{placeholder_prefix}{len(current_code_blocks)}"
             current_code_blocks[placeholder] = original_match_text

             # Replace in the text
             final_processed_text = final_processed_text[:start] + placeholder + final_processed_text[end:]

             # Record the range replaced by the *placeholder* in original coordinates (tricky)
             # Let's simplify - record the original range that was replaced
             processed_ranges.append((start, end))

        # Use the newly generated code blocks
        return final_processed_text, current_code_blocks


    def _restore_protected(self, text, code_blocks):
        """Restores code blocks and variables from placeholders."""
        restored_text = text
        # Restore code blocks first (placeholders are unique)
        # Sort by placeholder number potentially? Or just iterate.
        # Iterating should be fine as placeholders are distinct.
        for placeholder, block in code_blocks.items():
            restored_text = restored_text.replace(placeholder, block)

        # Restore variables using the instance method _replace_vars with reversed mapping
        restored_text = self._replace_vars(restored_text, REVERSED_VAR_PLACEHOLDERS)
        return restored_text


    def _split_into_chunks(self, text):
        """Splits text into chunks respecting formatting and delimiters. (Simplified)"""
        if not text: return []

        # Pre-split by delimiters that should remain separate or with neighbors
        # Keep newlines, code placeholders, and bracketed content mostly intact
        # Regex to find potential chunk boundaries or special content
        # This is complex - using a simpler approach for now
        processed_chunks = []

        # Basic split by newline first to preserve structure
        lines = text.split('\n')
        raw_chunks_from_lines = []
        for i, line in enumerate(lines):
             if line: raw_chunks_from_lines.append(line)
             if i < len(lines) - 1: raw_chunks_from_lines.append('\n') # Keep newline marker

        # Process each raw chunk
        for chunk in raw_chunks_from_lines:
            if chunk == '\n':
                 processed_chunks.append('\n')
                 continue

            # Simple split by spaces for word count check (crude but fast)
            words = chunk.split(' ')
            if len(words) <= self.max_chunk_size:
                processed_chunks.append(chunk) # Keep small chunks whole
            else:
                 # Break larger chunks (needs smarter splitting by punctuation etc.)
                 # Very basic split by word limit for now
                 current_sub_chunk = []
                 for word in words:
                     current_sub_chunk.append(word)
                     if len(current_sub_chunk) >= self.max_chunk_size:
                          processed_chunks.append(" ".join(current_sub_chunk))
                          current_sub_chunk = []
                 if current_sub_chunk: # Add any remainder
                     processed_chunks.append(" ".join(current_sub_chunk))

        return [c for c in processed_chunks if c] # Filter empty strings


    def _preserve_case(self, original, translated):
        """Applies basic case preservation."""
        if not original or not translated or not isinstance(original, str) or not isinstance(translated, str):
             return translated # Basic safety checks

        try:
            if original.isupper(): return translated.upper()
            if original.islower(): return translated.lower()

            # Capitalize first letter if original was capitalized (basic)
            if len(original) > 0 and original[0].isupper() and len(translated) > 0 and translated[0].islower():
                return translated[0].upper() + translated[1:]

        except Exception as e:
            print(f"Warning: Error during case preservation: {e}")
            # Fallback to translated text if error occurs
            return translated

        return translated


    def _post_process_formatting(self, text):
        """Applies common punctuation spacing and capitalization rules."""
        if not isinstance(text, str): return text # Safety check

        try:
            # Remove space before common punctuation
            text = re.sub(r'\s+([.,;:])', r'\1', text)
            # Ensure space after common punctuation (if not followed by space, certain chars, or end)
            text = re.sub(r'([.,;:])(?=[^\s\)\}\].,;:\'"]|$)', r'\1 ', text)
            # Ensure space after sentence end punctuation
            text = re.sub(r'([.!?])(?=[^\s\)\}\]\"\'{\[])', r'\1 ', text) # Added { and [ to exclusion
            # Capitalize after sentence end
            text = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
            # Remove space inside brackets immediately after open / before close
            text = re.sub(r'([\[({])\s+', r'\1', text)
            text = re.sub(r'\s+([\])}])', r'\1', text)
            # Handle potential double spacing introduced
            text = re.sub(r' +', ' ', text)
            # Remove spaces at beginning/end of lines within the text
            text = re.sub(r'^ +| +$', '', text, flags=re.MULTILINE)

        except Exception as e:
             print(f"Warning: Error during post-process formatting: {e}")
             # Return text as is if regex fails

        return text.strip() # Final strip

    def _initialize_llm_clients(self, llm_config):
        """Initializes LLM clients based on config if not already done."""
        provider = llm_config.get('provider')
        api_key = llm_config.get('api_key')

        if provider == 'openrouter' and not self.openrouter_client and OpenAI:
            if api_key:
                 try:
                     self.openrouter_client = OpenAI(
                         base_url="https://openrouter.ai/api/v1",
                         api_key=api_key,
                     )
                     print("OpenRouter client initialized.")
                 except Exception as e:
                      print(f"Error initializing OpenRouter client: {e}")
            else:
                print("Warning: OpenRouter API key missing.")

        elif provider == 'groq' and not self.groq_client and Groq:
            if api_key:
                try:
                    self.groq_client = Groq(api_key=api_key)
                    print("Groq client initialized.")
                except Exception as e:
                    print(f"Error initializing Groq client: {e}")
            else:
                print("Warning: Groq API key missing.")

    def _clean_llm_response(self, text):
        """Removes potential artifacts like backticks from LLM response."""
        text = text.strip()
        # Remove ``` block markers if present
        if text.startswith("```") and text.endswith("```"):
             # Find the first newline after ``` and the last newline before ```
             start_index = text.find('\n') + 1 if text.find('\n') != -1 else 3
             end_index = text.rfind('\n') if text.rfind('\n') != -1 else -3
             if start_index < end_index : # Basic sanity check
                  text = text[start_index:end_index].strip()
             else: # If markers are there but no content, or weird format
                  text = text.replace("```", "").strip() # Fallback: just remove markers

        # Remove potential single backticks if they wrap the whole response
        if text.startswith('`') and text.endswith('`'):
            text = text[1:-1]
        return text

    def _translate_with_llm(self, text_chunk, target_lang_code, target_lang_name, llm_config):
        """Translates a single chunk using the configured LLM provider."""
        provider = llm_config.get('provider')
        api_key = llm_config.get('api_key')
        model_name = llm_config.get('model')

        if not api_key or not model_name:
            print(f"Warning: Missing API key or model for {provider}. Falling back.")
            return text_chunk # Fallback to original

        self._initialize_llm_clients(llm_config)

        client = None
        error_types = ()
        if provider == 'openrouter':
            client = self.openrouter_client
            if all([APIError, AuthenticationError, RateLimitError, APIConnectionError]):
                 error_types = (APIError, AuthenticationError, RateLimitError, APIConnectionError)
            else: error_types = (Exception,)
        elif provider == 'groq':
            client = self.groq_client
            if all([GroqAPIError, GroqAuthError, GroqRateLimitError, GroqConnectionError]):
                 error_types = (GroqAPIError, GroqAuthError, GroqRateLimitError, GroqConnectionError)
            else: error_types = (Exception,)

        if not client:
            print(f"Error: {provider} client not initialized. Cannot translate.")
            return text_chunk

        prompt = (
            f"Translate the following text to {target_lang_name} ({target_lang_code}). "
            f"Return ONLY the translated text, without any introductory phrases, explanations, or the original text. "
            f"Text to translate: ```\n{text_chunk}\n```"
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            print(f"DEBUG: Sending to {provider} ({model_name}): '{text_chunk[:50]}...'") # Debug
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=int(len(text_chunk) * 2.5) + 50
            )
            print(f"DEBUG: Received response object from {provider}: {type(completion)}") # Debug response type

            translated_text = None # Default value
            if completion and isinstance(completion.choices, list) and completion.choices:
                 # Check the first choice object exists
                 first_choice = completion.choices[0]
                 if first_choice and first_choice.message:
                      # Check the message object exists
                      message_content = first_choice.message.content
                      # Check the content itself is a non-empty string
                      if message_content and isinstance(message_content, str):
                           translated_text = message_content
                      else:
                           print(f"Warning: LLM ({provider}) returned None or non-string content.")
                           print(f"DEBUG: Full Choice Object: {first_choice}") # Debug
                 else:
                      print(f"Warning: LLM ({provider}) response missing 'message' object in first choice.")
                      print(f"DEBUG: Full Choices List: {completion.choices}") # Debug
            else:
                 print(f"Warning: LLM ({provider}) response missing 'choices' list or list is empty.")
                 print(f"DEBUG: Full Completion Object: {completion}") # Debug entire object if choices missing
            # --- End Robust Checks ---


            # Now process the result based on whether translated_text was successfully extracted
            if translated_text:
                print(f"DEBUG: Extracted translation: '{translated_text[:50]}...'") # Debug
                return self._clean_llm_response(translated_text)
            else:
                # This path is taken if any check above failed
                print(f"Warning: Could not extract valid translation from LLM ({provider}) response for chunk: {text_chunk[:50]}...")
                return text_chunk # Fallback

        except error_types as e:
            # (Keep existing specific error handling)
            error_message = str(e)
            if isinstance(e, (AuthenticationError, GroqAuthError)):
                 error_message = f"Authentication Error with {provider}. Check your API key."
            # ... (other specific error messages) ...
            elif "model_not_found" in error_message.lower():
                 error_message = f"Model '{model_name}' not found or unavailable on {provider}."

            print(f"Error translating chunk via {provider} API: {error_message}")
            print(f"Chunk: {text_chunk[:100]}...")
            time.sleep(1)
            return text_chunk

        except Exception as e: # Catch any other unexpected errors, including potential TypeErrors from bad responses
            # This will now catch TypeErrors if the checks above somehow miss a case,
            # OR if the error happens *before* the checks (e.g., during the API call itself
            # in a way not caught by specific exceptions)
            print(f"Unexpected error during LLM translation ({provider}): {e}")
            print(f"Chunk: {text_chunk[:100]}...")
            # Optionally log the raw completion object if available at this point
            try:
                 print(f"DEBUG: Completion object before error: {completion}")
            except NameError:
                 print("DEBUG: Completion object was not assigned before error.")
            return text_chunk


    # Modify translate_text to accept LLM config and conditionally translate
    def translate_text(self, text, target_lang_code, target_lang_name, translate_angle=False, use_llm=False, llm_config=None):
        """Translates text, preserving formatting and code blocks, optionally using LLM."""
        if not isinstance(text, str) or not text.strip(): return text

        # --- Protection (Extract placeholders FIRST) ---
        processed_text, code_blocks = self._extract_and_protect(text) # Protect variables & code blocks

        # --- CONDITIONAL: LLM translates the whole processed text ---
        if use_llm and llm_config:
            print(f"DEBUG: Translating whole field via LLM ({llm_config.get('provider')})...")
            # Translate the entire text after placeholder extraction
            # Ensure we have a valid target language name for the prompt
            if not target_lang_name:
                print("Error: Target language name missing for LLM prompt.")
                # Attempt to restore and return original if name is missing
                return self._restore_protected(processed_text, code_blocks)

            try:
                # Call LLM translation method directly with the whole processed text
                final_processed_translation = self._translate_with_llm(
                    processed_text, target_lang_code, target_lang_name, llm_config
                )

                # Basic case preservation on the *whole* result might be less accurate,
                # but let's apply it simply for now.
                # Consider if case preservation is needed differently for whole-text LLM.
                final_processed_translation = self._preserve_case(processed_text, final_processed_translation)

            except Exception as e:
                 # Catch any unexpected error during the whole-text LLM call
                 print(f"Error during whole-text LLM translation: {e}")
                 final_processed_translation = processed_text # Fallback to processed (untranslated) text

            # Restore placeholders on the translated (or fallback) text
            final_text = self._restore_protected(final_processed_translation, code_blocks)
            # Apply post-processing formatting
            final_text = self._post_process_formatting(final_text)
            return final_text

        # --- ELSE (Not LLM): Use existing chunking logic for Google Translate ---
        else:
            print("DEBUG: Using Google Translate with chunking...")
            # (Use the corrected regex splitting logic from previous answers)
            escaped_code_prefix = re.escape(CODE_BLOCK_PLACEHOLDER_PREFIX)
            escaped_inline_prefix = re.escape(INLINE_CODE_PLACEHOLDER_PREFIX)
            pattern_parts = [
                r'\n', r'\{\{[^}}]*?\}\}', r'\{[^}]*?\}',
                rf'{escaped_code_prefix}\d+', rf'{escaped_inline_prefix}\d+'
            ]
            if not translate_angle: pattern_parts.append(r'<.*?>')
            split_pattern_string = '(' + '|'.join(pattern_parts) + ')'
            try: split_pattern = re.compile(split_pattern_string)
            except re.error as e:
                print(f"FATAL REGEX ERROR compiling split pattern: {e}")
                return self._restore_protected(processed_text, code_blocks) # Restore before returning original

            segments = split_pattern.split(processed_text) # Split the protected text

            translated_segments = []
            for segment in segments:
                if not segment: continue
                if split_pattern.fullmatch(segment): # Keep delimiters/placeholders
                    translated_segments.append(segment)
                    continue

                # --- Chunk Processing Loop (Only for Google Translate) ---
                chunks = self._split_into_chunks(segment) # Chunk the segment
                translated_chunk_parts = []
                for chunk in chunks:
                    if chunk == '\n':
                        translated_chunk_parts.append('\n')
                        continue
                    if not chunk.strip():
                        translated_chunk_parts.append(chunk)
                        continue

                    original_chunk = chunk
                    translation = None
                    try:
                        # Use Google Translate (check if initialized)
                        if self.google_translator:
                             time.sleep(0.15) # Rate limiting for Google
                             translation = self.google_translator.translate(text=chunk)
                             # Apply case preservation per chunk
                             translation = self._preserve_case(original_chunk, translation)
                        else:
                             print("Warning: Google Translate not available. Skipping translation.")
                             translation = chunk # Fallback

                        translated_chunk_parts.append(translation)

                    except Exception as e:
                        print(f"Error translating Google chunk: '{chunk[:50]}...'. Error: {e}")
                        translated_chunk_parts.append(chunk) # Keep original on error
                # --- End Chunk Processing Loop ---

                # --- Segment Reassembly (Only for Google Translate) ---
                translated_segment = ""
                for i, part in enumerate(translated_chunk_parts):
                     if i > 0 and not translated_segment.endswith(('\n', ' ')) and not part.startswith(' '):
                         translated_segment += " "
                     translated_segment += str(part) if part is not None else ""
                translated_segments.append(translated_segment)
                # --- End Segment Reassembly ---

            # --- Final Assembly and Formatting (Only for Google Translate) ---
            final_chunked_translation = "".join(translated_segments)
            # Restore placeholders on the combined translated chunks
            final_text = self._restore_protected(final_chunked_translation, code_blocks)
            # Apply post-processing formatting
            final_text = self._post_process_formatting(final_text)
            return final_text

    # Modify translate_json to pass LLM config down
    def translate_json(self, data, target_lang_code, target_lang_name, translate_angle=False, on_progress=None, use_llm=False, llm_config=None):
        """Recursively translates target fields in a JSON structure, optionally using LLM."""
        items_to_translate = []
        def find_items(current_data):
            if isinstance(current_data, dict):
                for key, value in current_data.items():
                    if key in TARGET_FIELDS and isinstance(value, str) and value.strip():
                        items_to_translate.append({"dict": current_data, "key": key})
                    elif key in ["wi_format", "scenario_format"] and isinstance(value, str):
                         current_data[key] = value.replace('{ {', '{{').replace('} }', '}}')
                    if isinstance(value, (dict, list)): find_items(value)
            elif isinstance(current_data, list):
                for item in current_data: find_items(item)

        find_items(data)
        total_items = len(items_to_translate)

        for i, item in enumerate(items_to_translate):
            container, key = item["dict"], item["key"]
            original_value = container[key]
            # print(f"Translating field: {key} ({i+1}/{total_items})") # Debug
            try:
                # Pass LLM flags and config to translate_text
                container[key] = self.translate_text(
                    original_value, target_lang_code, target_lang_name, translate_angle,
                    use_llm=use_llm, llm_config=llm_config
                )
                if on_progress: on_progress(i + 1, total_items)
            except Exception as e:
                print(f"Error translating field '{key}': {str(e)}")
                print(f"Original Value: {original_value[:100]}...") # Log original value on error
            # Optional: add a small delay between fields if using LLM to help rate limits
            # if use_llm and i > 0 and i % 10 == 0:
            #     time.sleep(0.5)

        return data
class TranslatorApp:
    def __init__(self, root):
        self.root = root
        self.config = TranslationConfig()
        self.engine = TranslationEngine()
        # --- StringVars for LLM settings ---
        self.llm_provider_var = tk.StringVar(value=self.config.data.get("llm_provider", "openrouter"))
        self.openrouter_api_key_var = tk.StringVar(value=self.config.data.get("openrouter_api_key", ""))
        self.openrouter_model_var = tk.StringVar(value=self.config.data.get("openrouter_model", ""))
        self.groq_api_key_var = tk.StringVar(value=self.config.data.get("groq_api_key", ""))
        self.groq_model_var = tk.StringVar(value=self.config.data.get("groq_model", ""))
        # Link StringVars to config saving
        self.llm_provider_var.trace_add('write', self._save_llm_choice)
        self.openrouter_api_key_var.trace_add('write', lambda: self._save_llm_detail('openrouter_api_key', self.openrouter_api_key_var.get()))
        self.openrouter_model_var.trace_add('write', lambda: self._save_llm_detail('openrouter_model', self.openrouter_model_var.get()))
        self.groq_api_key_var.trace_add('write', lambda: self._save_llm_detail('groq_api_key', self.groq_api_key_var.get()))
        self.groq_model_var.trace_add('write', lambda: self._save_llm_detail('groq_model', self.groq_model_var.get()))

        self.setup_ui()

    def _get_ui_text(self, key):
        return self.config.get_text(key)

    # --- Add methods to manage LLM UI visibility and save settings ---
    def _toggle_llm_options(self):
        """Shows/hides LLM provider selection and input fields."""
        show_llm = self.use_llm_var.get()
        if show_llm:
            self.llm_options_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(5, 5), padx=5)
            self._toggle_provider_fields() # Show fields for the currently selected provider
        else:
            self.llm_options_frame.grid_remove()
            # Also hide specific provider frames if they were visible
            self.openrouter_frame.grid_remove()
            self.groq_frame.grid_remove()
        # Save the checkbox state
        self.config.data['use_llm_translation'] = show_llm
        self.config.save()


    def _toggle_provider_fields(self):
        """Shows input fields for the selected LLM provider."""
        provider = self.llm_provider_var.get()
        if self.use_llm_var.get(): # Only toggle if LLM is enabled
            if provider == 'openrouter':
                self.openrouter_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 5), padx=15)
                self.groq_frame.grid_remove()
            elif provider == 'groq':
                self.groq_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 5), padx=15)
                self.openrouter_frame.grid_remove()
            else: # Should not happen
                 self.openrouter_frame.grid_remove()
                 self.groq_frame.grid_remove()

    def _save_llm_choice(self):
        """Saves the selected LLM provider and toggles fields."""
        provider = self.llm_provider_var.get()
        self.config.data['llm_provider'] = provider
        self.config.save()
        self._toggle_provider_fields() # Update visible fields

    def _save_llm_detail(self, key, value):
         """Saves a specific LLM detail (key or model) to config."""
         if key in self.config.data:
              self.config.data[key] = value
              # No need to call self.config.save() here constantly,
              # trace triggers it, or it happens on exit/major actions.
              # Let's save explicitly when needed or rely on traces.
              self.config.save() # Save on every keystroke for simplicity now


    def setup_ui(self):
        """Sets up the user interface."""
        self.root.title(self._get_ui_text("window_title"))
        self.root.geometry("900x450") # Increased height for LLM options
        self.root.minsize(800, 400)  # Set a minimum window size for better layout
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1) # Make list expand horizontally

        # --- Top Row: Language & Google Options (Row 0) ---
        google_options_frame = ttk.Frame(main_frame)
        google_options_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        google_options_frame.columnconfigure(0, weight=1)
        google_options_frame.columnconfigure(1, weight=1)

        # Language Selection
        lang_frame = ttk.Frame(google_options_frame)
        lang_frame.grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(lang_frame, text=self._get_ui_text("target_language")+":").pack(side=tk.LEFT, anchor=tk.W, padx=(0, 5))
        self.lang_combobox = ttk.Combobox(
            lang_frame, values=list(self.config.languages.values()),
            state="readonly", width=20
        )
        self.lang_combobox.set(self.config.get_native_name(self.config.current_lang))
        self.lang_combobox.pack(side=tk.LEFT, anchor=tk.W)
        self.lang_combobox.bind('<<ComboboxSelected>>', self.update_language)

        # Google Translate Options Frame (Angle Bracket, Save Location)
        options_frame = ttk.Frame(google_options_frame)
        options_frame.grid(row=0, column=1, sticky="e")
        self.translate_angle_var = tk.BooleanVar(value=self.config.data.get("translate_angle", False))
        self.angle_checkbox = ttk.Checkbutton(
            options_frame, text=self._get_ui_text("translate_angle"),
            variable=self.translate_angle_var, command=self.save_angle_preference
        )
        self.angle_checkbox.pack(side=tk.LEFT, padx=(0, 15))
        self.save_location_var = tk.StringVar(value=self.config.data.get("save_location", "silly"))
        self.save_location_var.trace('w', self.save_location_preference)
        ttk.Label(options_frame, text=self._get_ui_text("save_location")+":").pack(side=tk.LEFT, padx=(0,5))
        self.silly_radio = ttk.Radiobutton(options_frame, text=self._get_ui_text("save_silly"), variable=self.save_location_var, value="silly")
        self.silly_radio.pack(side=tk.LEFT)
        self.custom_radio = ttk.Radiobutton(options_frame, text=self._get_ui_text("save_custom"), variable=self.save_location_var, value="custom")
        self.custom_radio.pack(side=tk.LEFT, padx=(5,0))

        # --- LLM Options Section (Row 1) ---
        self.use_llm_var = tk.BooleanVar(value=self.config.data.get("use_llm_translation", False))
        self.use_llm_checkbox = ttk.Checkbutton(
            main_frame, text=self._get_ui_text("use_llm_translation"),
            variable=self.use_llm_var, command=self._toggle_llm_options # Command toggles visibility
        )
        # Place it below Google options, above file list
        self.use_llm_checkbox.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        # Frame for LLM provider choice + specific provider details
        self.llm_options_frame = ttk.LabelFrame(main_frame, text=self._get_ui_text("LLM"), padding=(10, 5))
        # This frame is initially hidden by grid_remove() at the end of setup_ui or by _toggle_llm_options

        # Provider selection (inside llm_options_frame)
        provider_frame = ttk.Frame(self.llm_options_frame)
        provider_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        ttk.Label(provider_frame, text=self._get_ui_text("llm_provider_label")+":").pack(side=tk.LEFT, padx=(0, 10))
        self.openrouter_radio = ttk.Radiobutton(
            provider_frame, text="OpenRouter", variable=self.llm_provider_var,
            value="openrouter", command=self._toggle_provider_fields
        )
        self.openrouter_radio.pack(side=tk.LEFT, padx=5)
        self.groq_radio = ttk.Radiobutton(
            provider_frame, text="Groq", variable=self.llm_provider_var,
            value="groq", command=self._toggle_provider_fields
        )
        self.groq_radio.pack(side=tk.LEFT, padx=5)

        # OpenRouter specific fields (inside llm_options_frame)
        self.openrouter_frame = ttk.Frame(self.llm_options_frame)
        ttk.Label(self.openrouter_frame, text="OpenRouter API Key:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.openrouter_key_entry = ttk.Entry(self.openrouter_frame, textvariable=self.openrouter_api_key_var, width=40, show='*')
        self.openrouter_key_entry.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        ttk.Label(self.openrouter_frame, text="OpenRouter Model:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.openrouter_model_entry = ttk.Entry(self.openrouter_frame, textvariable=self.openrouter_model_var, width=40)
        self.openrouter_model_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=2)
        self.openrouter_frame.columnconfigure(1, weight=1)
        # Initially hidden via grid_remove()

        # Groq specific fields (inside llm_options_frame)
        self.groq_frame = ttk.Frame(self.llm_options_frame)
        ttk.Label(self.groq_frame, text="Groq API Key:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.groq_key_entry = ttk.Entry(self.groq_frame, textvariable=self.groq_api_key_var, width=40, show='*')
        self.groq_key_entry.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        ttk.Label(self.groq_frame, text="Groq Model:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.groq_model_entry = ttk.Entry(self.groq_frame, textvariable=self.groq_model_var, width=40)
        self.groq_model_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=2)
        self.groq_frame.columnconfigure(1, weight=1)
        # Initially hidden via grid_remove()


        # --- File List Section (Adjust row index to 2) ---
        ttk.Label(main_frame, text=self._get_ui_text("select_files"), font=("Arial", 10, "bold")) .grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 2))
        list_frame = ttk.Frame(main_frame)
        list_frame.grid(row=3, column=0, sticky="nsew", padx=(0, 5)) # Changed row to 3
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1) # Changed row to 3 - Allow listbox row to expand vertically

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.file_list = tk.Listbox(list_frame, selectmode="multiple", height=8, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.file_list.yview)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=1, sticky="ns", pady=(0, 5)) # Changed row to 3
        self.select_button = ttk.Button(button_frame, text=self._get_ui_text("select_files"), command=self.select_files)
        self.select_button.pack(pady=3, fill=tk.X)
        self.remove_button = ttk.Button(button_frame, text=self._get_ui_text("remove_button"), command=self.remove_selected_files)
        self.remove_button.pack(pady=3, fill=tk.X)

        # --- Bottom Row: Progress & Translate Button (Adjust row index to 4, 5, 6) ---
        self.progress_bar = ttk.Progressbar(main_frame, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2)) # Changed row to 4
        self.status_label = ttk.Label(main_frame, text="", anchor="center")
        self.status_label.grid(row=5, column=0, columnspan=2, sticky="ew") # Changed row to 5
        self.translate_button = ttk.Button(main_frame, text=self._get_ui_text("start_translation"), command=self.start_translation)
        self.translate_button.grid(row=6, column=0, columnspan=2, pady=(5, 10)) # Changed row to 6


        # --- Map widgets to their text keys for easy update ---
        # (Add new LLM widget keys)
        self.widgets_to_translate = {
            "window_title": self.root,
            "target_language": lang_frame.winfo_children()[0],
            "translate_angle": self.angle_checkbox,
            "save_location_label": options_frame.winfo_children()[2],
            "save_silly": self.silly_radio,
            "save_custom": self.custom_radio,
            "use_llm_translation": self.use_llm_checkbox, # New
            "LLM": self.llm_options_frame, # New - LabelFrame uses 'text'
            "llm_provider_label": provider_frame.winfo_children()[0], # New
            # Radio button text ("OpenRouter", "Groq") is static
            # Labels for API keys/models are static
            "select_files_label": main_frame.grid_slaves(row=2, column=0)[0], # Get label by grid position
            "select_files_button": self.select_button,
            "remove_button": self.remove_button,
            "start_translation": self.translate_button,
        }

        # Initial UI state based on config
        self._toggle_llm_options()

    def update_language(self, *args):
        """Updates the UI language based on selection."""
        selected_lang_name = self.lang_combobox.get()
        lang_code = self.config.get_lang_code(selected_lang_name)
        if lang_code and lang_code != self.config.current_lang:
            self.config.current_lang = lang_code
            self.config.data["last_used_language"] = lang_code
            self.config.save()
            self.reload_ui_text() # Update text on existing widgets

    def save_angle_preference(self, *args): # Added *args to handle potential trace callback args
        """Saves the preference for translating angle brackets."""
        self.config.data["translate_angle"] = self.translate_angle_var.get()
        self.config.save()

    def save_location_preference(self, *args): # Added *args to handle potential trace callback args
        """Saves the preferred save location."""
        self.config.data["save_location"] = self.save_location_var.get()
        self.config.save()

    def get_silly_openai_settings_path(self):
        """Gets the SillyTavern OpenAI Settings path, prompting if needed."""
        st_path = self.config.data.get("silly_tavern_path")
        if not st_path or not os.path.isdir(st_path):
             messagebox.showinfo(self._get_ui_text("info_title"), self._get_ui_text("ask_silly_path_msg"))
             st_path = filedialog.askdirectory(title=self._get_ui_text("select_silly_dir"))
             if not st_path: return None # User cancelled
             self.config.data["silly_tavern_path"] = st_path
             self.config.save()

        # Construct the path robustly
        settings_path = os.path.join(st_path, "data", "default-user", "OpenAI Settings")
        try:
            os.makedirs(settings_path, exist_ok=True) # Ensure it exists
            return settings_path
        except OSError as e:
            messagebox.showerror(self._get_ui_text("error_title"), f"Could not create or access settings directory:\n{settings_path}\nError: {e}")
            return None


    def select_files(self):
        """Opens file dialog to select JSON files."""
        initial_dir = os.path.expanduser("~") # Default
        if self.save_location_var.get() == "silly":
             silly_settings_path = self.get_silly_openai_settings_path()
             # Use Silly path only if successfully retrieved and is a directory
             if silly_settings_path and os.path.isdir(silly_settings_path):
                 initial_dir = silly_settings_path
             elif silly_settings_path is None: # User cancelled path selection
                 return # Don't open file dialog if path selection was cancelled

        filetypes = ( (self._get_ui_text("json_filetype"), "*.json"),
                      (self._get_ui_text("all_filetype"), "*.*") )

        # Make sure root window is used for the dialog
        filenames = filedialog.askopenfilenames( parent=self.root,
                                                 initialdir=initial_dir,
                                                 title=self._get_ui_text("select_files"),
                                                 filetypes=filetypes)

        # Add files to the listbox
        current_files = set(self.file_list.get(0, tk.END))
        for fn in filenames:
            if fn not in current_files:
                self.file_list.insert(tk.END, fn)
        # print(f"Added {added_count} files.") # Optional debug


    def remove_selected_files(self):
        """Removes selected files from the list."""
        selected_indices = self.file_list.curselection()
        # Delete in reverse order to avoid index shifting issues
        for index in reversed(selected_indices):
            self.file_list.delete(index)


    def reload_ui_text(self):
        """Updates UI text elements with current language."""
        for key, widget in self.widgets_to_translate.items():
            text = self._get_ui_text(key)
            if key == "window_title": widget.title(text)
            elif isinstance(widget, ttk.LabelFrame): widget.config(text=text) # Handle LabelFrame
            elif isinstance(widget, (ttk.Button, ttk.Label, ttk.Checkbutton, ttk.Radiobutton)):
                widget.config(text=text)


    # --- Keep existing methods ---
    # update_language, save_angle_preference, save_location_preference,
    # get_silly_openai_settings_path, select_files, remove_selected_files

    def set_ui_state(self, enabled):
        """Enable/disable UI elements during processing."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.translate_button.config(state=state)
        self.select_button.config(state=state)
        self.remove_button.config(state=state)
        self.lang_combobox.config(state="readonly" if enabled else tk.DISABLED)
        self.angle_checkbox.config(state=state)
        self.silly_radio.config(state=state)
        self.custom_radio.config(state=state)
        # Also disable LLM options during processing
        self.use_llm_checkbox.config(state=state)
        for widget in self.llm_options_frame.winfo_children():
             # Disable radio buttons and entry fields inside LLM frames
             if isinstance(widget, (ttk.Radiobutton, ttk.Entry, ttk.Frame)):
                  try: # Frames don't have state, but their children might
                      widget.config(state=state)
                  except tk.TclError: # Ignore if widget doesn't support state
                      pass
        # Specifically disable entry fields within provider frames too
        self.openrouter_key_entry.config(state=state)
        self.openrouter_model_entry.config(state=state)
        self.groq_key_entry.config(state=state)
        self.groq_model_entry.config(state=state)


    def start_translation(self):
        """Starts the translation process in a separate thread."""
        selected_files = self.file_list.get(0, tk.END)
        if not selected_files:
            messagebox.showwarning(self._get_ui_text("warning_title"), self._get_ui_text("no_files_selected_msg"))
            return

        # --- Save Location Handling (Keep existing) ---
        save_location = self.save_location_var.get()
        silly_settings_path = None
        if save_location == "silly":
            silly_settings_path = self.get_silly_openai_settings_path()
            if not silly_settings_path: return

        # --- Target Language (Keep existing) ---
        target_lang_name = self.lang_combobox.get() # Native name
        target_lang_code = self.config.get_lang_code(target_lang_name)
        if not target_lang_code:
             messagebox.showerror(self._get_ui_text("error_title"), "Invalid target language selected.")
             return

        translate_angle = self.translate_angle_var.get()

        # --- LLM Configuration ---
        use_llm = self.use_llm_var.get()
        llm_config = None
        if use_llm:
             # Save current values just before starting
             self.config.save()
             # Retrieve validated details
             provider = self.config.data.get('llm_provider')
             api_key = ""
             model = ""
             if provider == 'openrouter':
                 api_key = self.config.data.get('openrouter_api_key')
                 model = self.config.data.get('openrouter_model')
             elif provider == 'groq':
                 api_key = self.config.data.get('groq_api_key')
                 model = self.config.data.get('groq_model')

             # Validate API Key and Model presence
             if not api_key or not model:
                  messagebox.showerror(
                      self._get_ui_text("error_title"),
                      self._get_ui_text("llm_missing_credentials_msg").format(provider.capitalize())
                  )
                  return # Stop if key or model is missing

             llm_config = {
                 "provider": provider,
                 "api_key": api_key,
                 "model": model,
             }
             print(f"Using LLM Translation via {provider.capitalize()} (Model: {model})") # Info
        else:
             print("Using Google Translate") # Info

        # --- Start Thread ---
        self.set_ui_state(False)
        self.progress_bar['value'] = 0
        self.status_label.config(text=self._get_ui_text("status_starting"))

        thread = threading.Thread(
            target=self._translation_thread_func,
            args=(
                selected_files, target_lang_code, target_lang_name, # Pass code and name
                translate_angle, save_location, silly_settings_path,
                use_llm, llm_config # Pass LLM flags
            ),
            daemon=True
        )
        thread.start()

    def _update_progress(self, current_file_idx, total_files, filename, field_progress, total_fields):
        """Callback for progress updates from the engine."""
        file_perc = (field_progress / total_fields) * 100 if total_fields > 0 else 0
        overall_perc = ((current_file_idx + (file_perc / 100)) / total_files) * 100
        status_msg = self._get_ui_text("translating_file_status").format(
            os.path.basename(filename), current_file_idx + 1, total_files, int(file_perc)
        )

        if self.progress_bar['value'] != overall_perc or self.status_label.cget("text") != status_msg:
             self.progress_bar['value'] = overall_perc
             self.status_label.config(text=status_msg)
             self.root.update_idletasks()


    # Modify _translation_thread_func to accept and pass LLM args
    def _translation_thread_func(self, files, target_lang_code, target_lang_name, translate_angle, save_location, silly_path, use_llm, llm_config):
        """Worker thread function for translation."""
        total_files = len(files)
        current_file_path = "N/A" # Keep track for error message
        try:
            for i, file_path in enumerate(files):
                current_file_path = file_path # Update for error reporting
                filename = os.path.basename(file_path)
                # Use lambda to capture current file index 'i' for the callback
                update_ui_callback = lambda: self.status_label.config(text=self._get_ui_text("loading").format(filename))
                self.root.after(0, update_ui_callback) # Schedule UI update in main thread


                data = load_json_safe(file_path)
                if not data:
                    print(f"Skipping invalid or empty JSON: {filename}")
                    continue

                def progress_callback(fields_done, total_fields):
                     # Schedule progress update in main thread using lambda to capture vars
                     update_prog_callback = lambda fd=fields_done, tf=total_fields: self._update_progress(i, total_files, file_path, fd, tf)
                     self.root.after(0, update_prog_callback)


                # Pass LLM args to translate_json
                translated_data = self.engine.translate_json(
                    data, target_lang_code, target_lang_name, translate_angle,
                    progress_callback, use_llm=use_llm, llm_config=llm_config
                )

                # --- Save Path Determination (Keep existing) ---
                save_path = None
                if save_location == "custom":
                    base, ext = os.path.splitext(file_path)
                    # Add language code to filename for clarity
                    save_path = f"{base}_translated_{target_lang_code}{ext}"
                    print(f"Custom save: saving to {save_path}")
                elif save_location == "silly" and silly_path:
                    base, ext = os.path.splitext(filename)
                    save_path = os.path.join(silly_path, f"{base}_translated_{target_lang_code}{ext}")

                # --- Save Translated File (Keep existing) ---
                if save_path:
                    if not save_json(save_path, translated_data):
                         raise IOError(f"Failed to save {save_path}")
                else:
                    print(f"Error: Could not determine save path for {filename}")

            # --- Completion ---
            completion_callback = lambda: (
                 self.status_label.config(text=self._get_ui_text("translation_complete")),
                 messagebox.showinfo("Preset Translator", self._get_ui_text("translation_success"))
            )
            self.root.after(0, completion_callback)

        except Exception as e:
             # Use current_file_path in the error message
             error_msg = self._get_ui_text("translation_error_msg").format(os.path.basename(current_file_path), str(e))
             print(f"Translation Thread Error: {error_msg}")
             # Schedule error message display in main thread
             error_callback = lambda: (
                 messagebox.showerror(self._get_ui_text("error_title"), error_msg),
                 self.status_label.config(text=self._get_ui_text("translation_failed"))
             )
             self.root.after(0, error_callback)
        finally:
            # Ensure UI is re-enabled regardless of success or failure
            # Schedule UI enabling in main thread
             self.root.after(0, lambda: self.set_ui_state(True))


# --- Main Execution ---
if __name__ == "__main__":
    # Add checks for libraries needed for LLM
    if OpenAI is None: print("Reminder: OpenRouter functionality requires 'openai' library.")
    if Groq is None: print("Reminder: Groq functionality requires 'groq' library.")

    root = tk.Tk()
    app = TranslatorApp(root)
    root.mainloop()