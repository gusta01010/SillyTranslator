import json
import re
import os
import locale
import threading
from googletrans import Translator
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from difflib import SequenceMatcher
import time

# Configurações de tradução
TARGET_FIELDS = {
    "content", "new_group_chat_prompt", "new_example_chat_prompt",
    "continue_nudge_prompt", "wi_format", "personality_format",
    "group_nudge_prompt", "scenario_format", "new_chat_prompt",
    "impersonation_prompt", "bias_preset_selected", "assistant_impersonation"
}

LINGUAGENS = {
    'Português Brasileiro': 'pt',
    'English': 'en',
    'Español': 'es',
    'Français': 'fr',
    'Deutsch': 'de',
    'Italiano': 'it',
    '日本語': 'ja',
    '中文': 'zh-cn',
    '한국어': 'ko',
    'Русский': 'ru'
}

class Config:
    def __init__(self):
        self.config_file = "config.json"
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.data = json.load(f)
        except:
            # Arquivo não existe: criar configuração padrão
            try:
                sys_lang = locale.getlocale()[0]
                default_lang = sys_lang[:2] if sys_lang else "en"
            except:
                default_lang = "en"
            self.data = {
                "silly_tavern_path": "",
                "last_used_language": default_lang,
                "translate_angle": False,
                "save_location": "silly"
            }
            self.save_config()
        # Garantir que todas as chaves existam
        for key in ["silly_tavern_path", "last_used_language", "translate_angle", "save_location"]:
            if key not in self.data:
                self.data[key] = "" if key != "translate_angle" else False
        if "save_location" not in self.data:
            self.data["save_location"] = "silly"

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.data, f, indent=4)

class UI:
    def __init__(self):
        self.load_translations()
        self.config = Config()
        self.current_lang = self.config.data.get("last_used_language", "en")
        self.default_translate_angle = self.config.data.get("translate_angle", False)

    def load_translations(self):
        try:
            with open('.\\lang\\lang_data.json', 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        except FileNotFoundError:
            print("Error: lang_data.json not found.")  # Error handling
            self.translations = {"en": {}}  # Fallback
        sys_lang = locale.getlocale()[0][:2] if locale.getlocale()[0] else "en"
        self.current_lang = sys_lang if sys_lang in self.translations else "en"

    def get_text(self, key):
        return self.translations.get(self.current_lang, {}).get(key, self.translations.get("en", {}).get(key, key))

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def get_case_from_surroundings(text, index):
    """Determina o case com base no contexto, verificando maiúsculas consecutivas."""
    if index == 0:
        return 'upper'
    elif index > 0 and text[index - 1] in ['.', '?', '!']:
        return 'upper'
    # Verifica duas letras maiúsculas anteriores:
    elif index >= 2 and text[index-1].isupper() and text[index-2].isupper():
        return 'upper'
    else:
        return 'lower'

def adjust_punctuation_spacing(text):
    """Adiciona espaço após '.', ';', ':' se necessário."""
    def add_space(match):
        punctuation = match.group(0)
        pos = match.start()
        if pos + len(punctuation) < len(text) and text[pos + len(punctuation)] != ' ' and text[pos + len(punctuation)].strip():
            return punctuation + ' '
        return punctuation
    return re.sub(r'[\.;:]', add_space, text)

def get_case_pattern(text):
    """Determina o case."""
    if text.isupper():
        return 'upper'
    elif text.islower():
        return 'lower'
    return 'mixed'

def apply_case(text, case_type):
    """Aplica o case."""
    if case_type == 'upper':
        return text.upper()
    elif case_type == 'lower':
        return text.lower()
    return text

def split_into_chunks(text, max_chunk_size=20):
    """Divide o texto em chunks respeitando \n, placeholders e separadores."""
    if not text:
        return []
    
    # Primeiro divide por quebras de linha
    chunks = []
    current_chunk = ""
    i = 0
    while i < len(text):
        if text[i:i+1] == '\n':
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            chunks.append('\n')
            i += 1
        else:
            current_chunk += text[i]
            i += 1
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # Processa cada chunk que não é \n
    final_chunks = []
    for chunk in chunks:
        if chunk == '\n':
            final_chunks.append('\n')
            continue
            
        # Divide pelos separadores mencionados, mas protege placeholders
        separators = r'([\.,:;])'
        segments = re.split(separators, chunk)
        
        current_chunk = ""
        for segment in segments:
            if not segment:
                continue
                
            # Verifica se o segmento contém placeholders
            if "__PLACEHOLDER_" in segment:
                if current_chunk:
                    final_chunks.append(current_chunk.strip())
                    current_chunk = ""
                final_chunks.append(segment.strip())
                continue
                
            # Evita que o próximo chunk comece com vírgula
            if current_chunk and segment.strip().startswith(','):
                current_chunk += segment
            elif len(current_chunk) + len(segment) <= max_chunk_size or not current_chunk:
                current_chunk += segment
            else:
                final_chunks.append(current_chunk.strip())
                current_chunk = segment
                
        if current_chunk:
            final_chunks.append(current_chunk.strip())
            
    return final_chunks

def split_camel_case(text):
    # Separa palavras coladas no estilo CamelCase
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)

def extract_special_contents(text, translate_angle):
    """Extrai conteúdos especiais. Não inclui {{...}}."""
    delimiters = [
        (r'`([^`]+)`', '`'),
        (r'"([^"]+)"', '"'),
        (r'\*\*([^*]+)\*\*', '**'),
        (r'\*\*\*\*([^*]+)\*\*\*\*', '****'),
        (r'\*\*\*\*\*\*([^*]+)\*\*\*\*\*\*', '******'),
        (r'\[([^\]]+)\]', '[]'),
        (r'\(([^\)]+)\)', '()')
    ]
    if translate_angle:
        delimiters.append((r'<([^>]+)>', '<>'))
    contents = []
    for pattern, delimiter_type in delimiters:
        for match in re.finditer(pattern, text):
            contents.append({
                'content': match.group(1),
                'start': match.start(),
                'end': match.end(),
                'delimiter': delimiter_type,
                'case': get_case_pattern(match.group(1))
            })
    return contents

def adjust_special_cases(original_text, translated_text, translate_angle):
    """Ajusta o case dos conteúdos especiais sem mexer em {{...}}."""
    original_contents = extract_special_contents(original_text, translate_angle)
    translated_contents = extract_special_contents(translated_text, translate_angle)
    original_contents.sort(key=lambda x: x['start'])
    translated_contents.sort(key=lambda x: x['start'])
    orig_by_delimiter = {}
    trans_by_delimiter = {}
    for content in original_contents:
        orig_by_delimiter.setdefault(content['delimiter'], []).append(content)
    for content in translated_contents:
        trans_by_delimiter.setdefault(content['delimiter'], []).append(content)

    result_text = translated_text
    for delim in orig_by_delimiter:
        if delim not in trans_by_delimiter:
            continue
        for orig, trans in zip(orig_by_delimiter[delim], trans_by_delimiter[delim]):
            if orig['case'] in ['upper', 'lower']:
                adjusted_content = apply_case(trans['content'], orig['case'])
                result_text = result_text[:trans['start']] + result_text[trans['start']:trans['end']].replace(trans['content'], adjusted_content) + result_text[trans['end']:]
    return result_text


def preprocess_text(text):
    """Preprocessa o texto ANTES de enviar para a API."""
    text = text.replace("{{char}}", "Jane")
    text = text.replace("{{user}}", "James")
    text = re.sub(r'\n', ' ', text)  # Remove \n *antes* da tradução

    # Espaçamento (mas *NÃO* mexe em {{...}}):
    text = re.sub(r'([.,;:])([^\s])', r'\1 \2', text)  # Espaço após pontuação
    text = adjust_punctuation_spacing(text)
    return text

def postprocess_text(text, original_text):
    """Pós-processa o texto traduzido."""

    # Substituições reversas:
    text = text.replace("Jane", "{{char}}")
    text = text.replace("James", "{{user}}")

    # Correção de hífens (força-tarefa, etc.):
    text = re.sub(r'(\w+)\s*-\s*(\w+)', r'\1-\2', text)
    # Junção caso termine com '-o'
    text = re.sub(r'(\w+)-o\s+(\w+)', r'\1-\2', text)

    # Restaurar quebras de linha originais (aproximado):
    text_lines = text.split()
    original_lines = original_text.split('\n')
    new_text = []
    orig_idx = 0

    for line in text_lines:
        new_text.append(line)
        if orig_idx < len(original_lines):
            # Usa similaridade, mas com um limite MAIOR
            if similar(" ".join(new_text), original_lines[orig_idx]) > 0.7:  # Ajuste o limite conforme necessário
                new_text.append('\n')
                orig_idx += 1
    final_text = " ".join(new_text)
    print(final_text)
    return final_text

def fix_capitalization(text):
    """Corrige a capitalização baseada em pontuação."""
    sentences = re.split(r'(\.\s+)', text)
    result = []
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        if i > 0:  # Não é a primeira sentença
            # Capitaliza a primeira letra após ponto
            if sentence and sentence[0].isalpha():
                sentence = sentence[0].upper() + sentence[1:]
        
        result.append(sentence)
        if i+1 < len(sentences):
            result.append(sentences[i+1])
    
    return ''.join(result)

def match_case_with_original(original_text, translated_text):
    """Mantém o mesmo case entre palavras iguais no original e traduzido."""
    original_words = re.findall(r'\b\w+\b', original_text)
    translated_words = re.findall(r'\b\w+\b', translated_text)
    
    result = translated_text
    
    for orig_word in original_words:
        for trans_word in translated_words:
            # Verifica se as palavras são iguais ignorando o case
            if orig_word.lower() == trans_word.lower() and orig_word != trans_word:
                # Substitui mantendo o mesmo case do original
                pattern = r'\b' + re.escape(trans_word) + r'\b'
                result = re.sub(pattern, orig_word, result)
    
    return result

def translate_braces_content(text, tradutor, lang_destino):
    """Traduz o conteúdo DENTRO de chaves simples {}."""
    def replace_with_translation(match):
        content = match.group(1)
        try:
            translated_content = tradutor.translate(content, dest=lang_destino).text
        except Exception as e:
            print(f"Erro ao traduzir conteúdo entre chaves: {e}")
            translated_content = content  # Mantém original em caso de erro
        return "{" + translated_content + "}"

    return re.sub(r'{([^}]+)}', replace_with_translation, text)

def proteger_e_traduzir(texto, tradutor, lang_destino, translate_angle=True, precise_mode=True, max_chunk_size=12):
    if not isinstance(texto, str) or not texto.strip():
        return texto

    original_text = texto  # Guarda o texto original
    
    # Preserva quebras de linha e substituições básicas
    texto_processado = texto.replace("{{char}}", "Jane")
    texto_processado = texto_processado.replace("{{user}}", "James")
    
    # Traduz conteúdo entre chaves {} se estiver no modo preciso
    if precise_mode:
        texto_processado = translate_braces_content(texto_processado, tradutor, lang_destino)

    # Identifica os placeholders para não traduzi-los
    segments = re.split(r'(\s*\{\{.*?\}\}\'?s?\s*|\s*\{.*?\}|<.*?>\'?s?\s*)', texto_processado)
    resultado = []

    for segmento in segments:
        if not segmento:
            continue

        # Não traduz placeholders {{...}} ou {...}, mas os mantém no resultado
        m = re.fullmatch(r'\s*(\{\{.*?\}\}|\{.*?\})(\'s)?\s*', segmento, re.IGNORECASE)
        if m:
            resultado.append(segmento)
            continue
        
        # Divide o texto em chunks respeitando \n e separadores
        chunks = split_into_chunks(segmento, max_chunk_size)
        
        for chunk in chunks:
            if chunk == '\n':
                resultado.append('\n')  # Preserva \n sem traduzir
                continue
                
            if not chunk.strip():
                resultado.append(chunk)  # Preserva espaços em branco
                continue
                
            try:
                # Pequena pausa para evitar limitações de API
                time.sleep(0.2)
                
                traducao = tradutor.translate(chunk, dest=lang_destino).text
                print (traducao)
                
                # Correção de capitalização baseada em pontuação
                traducao = fix_capitalization(traducao)
                
                # Dividir palavras em CamelCase
                traducao = split_camel_case(traducao)
                
                # Compara com original para manter mesmo case em palavras iguais
                traducao = match_case_with_original(chunk, traducao)
                
                # Ajusta capitalizações após pontos
                words = traducao.split()
                if resultado and len(words) > 0:
                    prev_text = resultado[-1]
                    if prev_text.strip().endswith('.'):
                        words[0] = words[0].capitalize()
                    elif len(prev_text) >= 2 and prev_text[-2:].isupper():
                        words[0] = words[0].upper()
                    
                    if not prev_text.endswith((" ", "\n")):
                        traducao = " " + " ".join(words)
                    else:
                        traducao = " ".join(words)
                else:
                    traducao = " ".join(words)
                
                resultado.append(traducao)
                
            except Exception as e:
                print(f"Erro ao traduzir chunk: {e}")
                resultado.append(chunk)  # Mantém original em caso de erro
    
    texto_final = ''.join(resultado)
    
    # Restaura substituições
    texto_final = texto_final.replace("Jane", "{{char}}")
    texto_final = texto_final.replace("James", "{{user}}")
    
    # Ajusta espaçamento de pontuação
    texto_final = adjust_punctuation_spacing(texto_final)
    
    return texto_final


# --- Interface Gráfica (modificada) ---

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.ui = UI()
        self.translator = Translator()  # Inicializa o tradutor
        self.total_fields = 0
        self.translated_fields = 0

        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X)
        lang_frame = ttk.Frame(top_frame)
        lang_frame.pack(side=tk.LEFT, padx=(0, 200))

        ttk.Label(lang_frame, text=self.ui.get_text("target_language"), font=("Arial", 10)).pack(anchor=tk.W)
        self.lang_combobox = ttk.Combobox(lang_frame, values=list(LINGUAGENS.keys()), state="readonly", width=30)
        self.lang_combobox.pack(pady=(5, 0))
        self.lang_combobox.set(list(LINGUAGENS.keys())[list(LINGUAGENS.values()).index(self.ui.current_lang)])
        self.lang_combobox.bind('<<ComboboxSelected>>', self.update_interface_language)

        self.translate_angle_var = tk.BooleanVar(value=self.ui.default_translate_angle)
        self.angle_checkbox = ttk.Checkbutton(lang_frame, text=self.ui.get_text("translate_angle"), variable=self.translate_angle_var)
        self.angle_checkbox.pack(pady=(5, 0), anchor=tk.W)
        self.translate_angle_var.trace('w', self.save_translate_angle_pref)

        # Adiciona o checkbox "Modo Preciso"
        self.precise_mode_var = tk.BooleanVar(value=False)  # Começa desativado
        self.precise_checkbox = ttk.Checkbutton(lang_frame, text="Modo Preciso", variable=self.precise_mode_var)
        self.precise_checkbox.pack(pady=(5, 0), anchor=tk.W)


        save_frame = ttk.Frame(top_frame)
        save_frame.pack(side=tk.LEFT, fill=tk.X)
        self.save_location_var = tk.StringVar(value=self.ui.config.data.get("save_location", "silly"))
        self.silly_radio = ttk.Radiobutton(save_frame, text=self.ui.get_text("save_silly"), variable=self.save_location_var, value="silly")
        self.silly_radio.pack(anchor=tk.W)
        self.custom_radio = ttk.Radiobutton(save_frame, text=self.ui.get_text("save_custom"), variable=self.save_location_var, value="custom")
        self.custom_radio.pack(anchor=tk.W)
        self.save_location_var.trace('w', self.update_save_location)

        self.silly_frame = ttk.Frame(save_frame)
        self.silly_frame.pack(fill=tk.X, pady=(5, 0))
        self.change_dir_button = ttk.Button(self.silly_frame, text=self.ui.get_text("change_silly_dir"), command=self.change_silly_dir)
        self.change_dir_button.pack(anchor=tk.W)
        self.silly_path_label = ttk.Label(self.silly_frame, text="", wraplength=200)
        self.silly_path_label.pack(anchor=tk.W, pady=(5, 0))
        self.update_silly_path_label()

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(20, 0))
        self.start_button = ttk.Button(bottom_frame, text=self.ui.get_text("start_translation"), command=self.start_translation)
        self.start_button.pack()

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(bottom_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=10)
        self.status_label = ttk.Label(bottom_frame, text="")
        self.status_label.pack()
        self.save_location_var.trace('w', self.update_silly_frame_visibility)

    def update_save_location(self, *args):
        self.ui.config.data["save_location"] = self.save_location_var.get()
        self.ui.config.save_config()

    def update_interface_language(self, event=None):
        selected_lang = LINGUAGENS[self.lang_combobox.get()]
        self.ui.current_lang = selected_lang
        self.ui.config.data["last_used_language"] = selected_lang
        self.ui.config.save_config()
        self.root.title(self.ui.get_text("window_title"))
        self.angle_checkbox.config(text=self.ui.get_text("translate_angle"))
        self.silly_radio.config(text=self.ui.get_text("save_silly"))
        self.custom_radio.config(text=self.ui.get_text("save_custom"))
        self.change_dir_button.config(text=self.ui.get_text("change_silly_dir"))
        self.start_button.config(text=self.ui.get_text("start_translation"))
        self.update_silly_path_label()

    def save_translate_angle_pref(self, *args):
        self.ui.config.data["translate_angle"] = self.translate_angle_var.get()
        self.ui.config.save_config()

    def update_silly_path_label(self):
        path = self.ui.config.data.get("silly_tavern_path", self.ui.get_text("not_configured"))
        self.silly_path_label.config(text=f"{self.ui.get_text('current_location')}{path}")

    def update_silly_frame_visibility(self, *args):
        if self.save_location_var.get() == "silly":
            self.silly_frame.pack(fill=tk.X, pady=10)
        else:
            self.silly_frame.pack_forget()

    def change_silly_dir(self):
        dir_path = filedialog.askdirectory(title=self.ui.get_text("select_silly_dir"))
        if dir_path:
            self.ui.config.data["silly_tavern_path"] = dir_path
            self.ui.config.save_config()
            self.update_silly_path_label()

    def ask_filename(self, original_name):
        """Solicita um novo nome de arquivo, verificando se já existe."""
        dialog = tk.Toplevel(self.root)
        dialog.title(self.ui.get_text("filename_dialog_title"))
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()
        result = {"filename": None}

        ttk.Label(dialog, text=self.ui.get_text("enter_filename_label")).pack(pady=10)
        entry = ttk.Entry(dialog, width=40)
        entry.insert(0, original_name)
        entry.pack(pady=5)

        def on_save():
            filename = entry.get()
            if not filename.endswith('.json'):
                filename += '.json'
            full_path = os.path.join(self.ui.config.data["silly_tavern_path"], "data", "default-user", "OpenAI Settings", filename)
            if os.path.exists(full_path):
                if messagebox.askyesno(self.ui.get_text("filename_dialog_title"), self.ui.get_text("file_exists")):
                    result["filename"] = filename
                    dialog.destroy()
            else:
                result["filename"] = filename
                dialog.destroy()
        ttk.Button(dialog, text=self.ui.get_text("save"), command=on_save).pack(pady=10)
        dialog.wait_window()
        return result["filename"]
    def _translate_recursive(self, data):
        """Função recursiva para percorrer o JSON e traduzir os campos."""
        if isinstance(data, dict):
            for key, value in data.items():
                #Correção de placeholders zoados
                if key in ["wi_format", "scenario_format"] and isinstance(value, str):
                    value = re.sub(r'{\s*{', "{{", value)
                    value = re.sub(r'}\s*}', "}}", value)
                    data[key] = value #Já aplica a correção

                if key in TARGET_FIELDS and isinstance(value, str):
                    try:
                        data[key] = proteger_e_traduzir(value, self.translator, self.ui.current_lang, self.translate_angle_var.get(), self.precise_mode_var.get())
                        self.translated_fields += 1
                    except Exception as e:
                        print(f"Erro ao traduzir campo {key}: {e}")
                    self.update_progress()  # Atualiza após cada campo
                else:
                    self._translate_recursive(value)
        elif isinstance(data, list):
            for item in data:
                self._translate_recursive(item)

    def _count_fields(self, data):
        """Conta o número total de campos traduzíveis no JSON."""
        count = 0
        if isinstance(data, dict):
            for key, value in data.items():
                if key in TARGET_FIELDS and isinstance(value, str):
                    count += 1
                else:
                    count += self._count_fields(value)
        elif isinstance(data, list):
            for item in data:
                count += self._count_fields(item)
        return count

    def update_progress(self):
        """Atualiza a barra de progresso e a label de status."""
        if self.total_fields > 0:
            progress = (self.translated_fields / self.total_fields) * 100
            self.progress_var.set(progress)
            self.status_label.config(text=f"{self.ui.get_text('loading')}: {int(progress)}%")
            self.root.update_idletasks()

    def start_translation(self):
        source_file = filedialog.askopenfilename(
            title=self.ui.get_text("select_json_original"),
            filetypes=[(self.ui.get_text("json_filetype"), "*.json"), (self.ui.get_text("all_filetype"), "*.*")]
        )
        if not source_file:
            return

        self.progress_var.set(0)
        self.translated_fields = 0
        self.status_label.config(text=self.ui.get_text("loading"))
        self.start_button.config(state=tk.DISABLED)

        def translation_thread():
            try:
                with open(source_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.total_fields = self._count_fields(data)  # Conta antes de começar
                self._translate_recursive(data)  # Traduz

                if self.save_location_var.get() == "silly":
                    if not self.ui.config.data.get("silly_tavern_path"):
                        self.root.after(0, lambda: messagebox.showerror(self.ui.get_text("error"), self.ui.get_text("configure_silly_dir")))
                        return
                    original_filename = os.path.basename(source_file)
                    new_filename = self.ask_filename(original_filename) # Pergunta o nome
                    if not new_filename:
                        return
                    save_path = os.path.join(self.ui.config.data["silly_tavern_path"], "data", "default-user", "OpenAI Settings", new_filename)
                else:
                    save_path = filedialog.asksaveasfilename(
                        title=self.ui.get_text("select_save_location"), defaultextension=".json",
                        filetypes=[(self.ui.get_text("json_filetype"), "*.json"), (self.ui.get_text("all_filetype"), "*.*")]
                    )
                    if not save_path: return

                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                self.root.after(0, lambda: messagebox.showinfo(self.ui.get_text("success"), self.ui.get_text("translation_success")))

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(self.ui.get_text("error"), f"{self.ui.get_text('translation_error')}{str(e)}"))
            finally:
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

        thread = threading.Thread(target=translation_thread)
        thread.start()

#Função para importar as linguagens
def load_languages():
    try:
        with open('.\\lang\\languages.json', 'r', encoding='utf-8') as f:
            languages = json.load(f)
            # Garante que 'pt' (Português) esteja presente e mapeado corretamente
            if "Português" not in languages:
                languages["Português"] = "pt"
            if "pt" not in languages.values(): # Se 'pt' não for um valor, adiciona
               for k,v in languages.items():
                   if v == 'pt-BR': #Tenta achar o pt-BR
                       languages[k] = "pt" #Altera

            return languages
    except FileNotFoundError:
        print("Erro: languages.json não encontrado. Usando padrão.")
        return {"English": "en", "Português": "pt"}  # Fallback
    except json.JSONDecodeError:
        print("languages.json está malformado.")
        return {"English": "en", "Português": "pt"}

# --- Código Principal (mantido) ---
if __name__ == "__main__":
    import json
    import locale
    import threading
    from googletrans import Translator

    #Carrega linguagens
    LINGUAGENS = load_languages()


    root = tk.Tk()
    root.title("Preset Translator")
    root.geometry("600x350")
    MainWindow(root)
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    root.mainloop()
