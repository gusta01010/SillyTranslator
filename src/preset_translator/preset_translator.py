import json
import re
import os
import locale
import threading
from googletrans import Translator
import tkinter as tk
from tkinter import filedialog, ttk, messagebox

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
            # File does not exist: create default config using system language or fallback to English
            try:
                sys_lang = locale.getdefaultlocale()[0]
                default_lang = sys_lang[:2] if sys_lang else "en"
            except:
                default_lang = "en"
            self.data = {
                "silly_tavern_path": "",
                "last_used_language": default_lang,
                "translate_angle": False
            }
            self.save_config()
        # Garantir que todas as chaves existam:
        if "last_used_language" not in self.data:
            self.data["last_used_language"] = "en"
        if "translate_angle" not in self.data:
            self.data["translate_angle"] = False

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.data, f, indent=4)

class UI:
    def __init__(self):
        self.load_translations()
        self.config = Config()
        # Carrega preferencia de idioma e translate_angle do config
        self.current_lang = self.config.data.get("last_used_language", "en")
        self.default_translate_angle = self.config.data.get("translate_angle", False)
        
    def load_translations(self):
        with open('.\\lang\\lang_data.json', 'r', encoding='utf-8') as f:
            self.translations = json.load(f)
        
        # Get system language
        sys_lang = locale.getlocale()[0][:2]
        self.current_lang = sys_lang if sys_lang in self.translations else "en"

    def get_text(self, key):
        return self.translations[self.current_lang].get(key, self.translations["en"][key])

def get_case_pattern(text):
    """Determina se o texto está todo em maiúsculas, minúsculas ou misto."""
    if text.isupper():
        return 'upper'
    elif text.islower():
        return 'lower'
    return 'mixed'

def apply_case(text, case_type):
    """Aplica o case especificado ao texto."""
    if case_type == 'upper':
        return text.upper()
    elif case_type == 'lower':
        return text.lower()
    return text

def extract_special_contents(text, translate_angle):
    """Extrai conteúdos dentro de delimitadores especiais e suas posições."""
    delimiters = [
        (r'`([^`]+)`', '`'),                    # Backticks (``)
        (r'"([^"]+)"', '"'),                    # Aspas duplas ("")
        (r'\*\*([^*]+)\*\*', '**'),             # **texto**
        (r'\*\*\*\*([^*]+)\*\*\*\*', '****'),   # ****texto****
        (r'\*\*\*\*\*\*([^*]+)\*\*\*\*\*\*', '******'),  # ******texto******
        (r'\[([^\]]+)\]', '[]'),                # [texto]
        (r'\(([^\)]+)\)', '()')                 # (texto)
    ]
    
    if translate_angle:
        delimiters.append((r'<([^>]+)>', '<>'))  # <texto>
    
    contents = []
    for pattern, delimiter_type in delimiters:
        matches = re.finditer(pattern, text)
        for match in matches:
            content = match.group(1)
            start, end = match.span()
            contents.append({
                'content': content,
                'start': start,
                'end': end,
                'delimiter': delimiter_type,
                'case': get_case_pattern(content)
            })
    return contents

def adjust_special_cases(original_text, translated_text, translate_angle):
    """Ajusta o case dos conteúdos especiais na tradução para corresponder ao original."""
    original_contents = extract_special_contents(original_text, translate_angle)
    translated_contents = extract_special_contents(translated_text, translate_angle)
    
    # Ordenar por posição para manter a correspondência
    original_contents.sort(key=lambda x: x['start'])
    translated_contents.sort(key=lambda x: x['start'])
    
    # Agrupar conteúdos por tipo de delimitador
    orig_by_delimiter = {}
    trans_by_delimiter = {}
    
    for content in original_contents:
        delim = content['delimiter']
        if delim not in orig_by_delimiter:
            orig_by_delimiter[delim] = []
        orig_by_delimiter[delim].append(content)
    
    for content in translated_contents:
        delim = content['delimiter']
        if delim not in trans_by_delimiter:
            trans_by_delimiter[delim] = []
        trans_by_delimiter[delim].append(content)
    
    result_text = translated_text
    
    # Ajustar casos para cada tipo de delimitador
    for delim in orig_by_delimiter:
        if delim not in trans_by_delimiter:
            continue
        
        orig_contents = orig_by_delimiter[delim]
        trans_contents = trans_by_delimiter[delim]
        
        # Ajustar com base na ordem de ocorrência
        for orig, trans in zip(orig_contents, trans_contents):
            trans_content = trans['content']
            case_type = orig['case']
            
            if case_type in ['upper', 'lower']:
                adjusted_content = apply_case(trans_content, case_type)
                # Substituir na string traduzida
                start = trans['start']
                end = trans['end']
                result_text = result_text[:start] + result_text[start:end].replace(trans_content, adjusted_content) + result_text[end:]
    
    return result_text

def adjust_punctuation_spacing(text):
    """Adiciona espaço após '.', ';', ':' se o terceiro caractere após a pontuação não for um espaço."""
    def add_space_if_needed(match):
        punctuation = match.group(0)
        pos = match.start()
        
        # Verificar o terceiro caractere após a pontuação
        third_char_pos = pos + len(punctuation) + 1
        if third_char_pos < len(text):
            # Se já existe um espaço após a pontuação, não faz nada
            if text[pos + len(punctuation)] == ' ':
                return punctuation
            # Se o próximo caractere é válido (letra, número, {, <, etc.), adiciona espaço
            elif text[pos + len(punctuation)].strip():
                return punctuation + ' '
        return punctuation

    # Aplicar a substituição para '.', ';', ':'
    text = re.sub(r'[\.;:]', add_space_if_needed, text)
    return text

def proteger_e_traduzir(texto, tradutor, lang_destino, placeholder_pattern, translate_angle):
    if not isinstance(texto, str) or not texto.strip():
        return texto

    # ETAPA: Pré-processamento para espaços críticos
    texto = re.sub(r'(`)\s*(\w)', r'\1 \2', texto)  # Espaço após `
    texto = re.sub(r'(\w)(\{)', r'\1 \2', texto)     # Espaço antes de {

    # --- ETAPA: Ajuste de espaçamento em pontuações no texto original ---
    texto = adjust_punctuation_spacing(texto)


    # --- ETAPA: Substituição de placeholders com 's por tokens
    texto = re.sub(r"(\{\{char\}\})'s", "Jane", texto)
    texto = re.sub(r"(\{\{user\}\})'s", "John", texto)


    # Dividir o texto em segmentos, preservando placeholders
    segments = re.split(r'(\s*\{\{.*?\}\}\'?s?\s*|\s*\{.*?\}|<.*?>\'?s?\s*)', texto)
    resultado = []

    for segmento in segments:
        if not segmento:
            continue
            
        # Verifica se o segmento é um placeholder (com ou sem 's)
        m = re.fullmatch(r'\s*(\{\{.*?\}\}|<.*?>)(\'s)?\s*', segmento, re.IGNORECASE)
        if m:
            if m.group(2):
                try:
                    traducao = tradutor.translate(segmento, dest=lang_destino).text
                    resultado.append(traducao)
                except Exception as e:
                    print(f"Erro na tradução do segmento (placeholder com 's): {str(e)}")
                    resultado.append(segmento)
            else:
                resultado.append(segmento)
            continue

        try:
            segment_mod = segmento
            traducao = tradutor.translate(segment_mod, dest=lang_destino).text
            # Correções pós-tradução: ajustes de espaçamento
            traducao = re.sub(r'([`])\s*([^ \n])', r'\1 \2', traducao)
            traducao = re.sub(r'([^ ])(\{)', r'\1 \2', traducao)
            traducao = re.sub(r'(\})([^ \n])', r'\1 \2', traducao)
            resultado.append(traducao)
        except Exception as e:
            print(f"Erro na tradução: {str(e)}")
            resultado.append(segmento)

    texto_final = ''.join(resultado)
    texto_final = re.sub(r'(`)\s*([,.:;])', r'\1\2', texto_final)

    # --- NOVA ETAPA: Ajuste de espaçamento em pontuações no texto traduzido ---
    texto_final = adjust_punctuation_spacing(texto_final)


    # --- ETAPA 2: Restauração dos tokens temporários ---
    texto_final = texto_final.replace("Jane", "{{char}}")
    texto_final = texto_final.replace("John", "{{user}}")


    # --- ETAPA 3: Ajuste de casos especiais ---
    texto_final = adjust_special_cases(texto, texto_final, translate_angle)


    return texto_final

def traduzir_objeto(data, tradutor, lang_destino, placeholder_pattern, translate_angle):
    if isinstance(data, dict):
        for chave in list(data.keys()):
            valor = data[chave]
            if chave in TARGET_FIELDS:
                if isinstance(valor, str):
                    data[chave] = proteger_e_traduzir(valor, tradutor, lang_destino, placeholder_pattern, translate_angle)
                elif valor is None:
                    data[chave] = ""
            else:
                traduzir_objeto(valor, tradutor, lang_destino, placeholder_pattern, translate_angle)
    elif isinstance(data, list):
        for item in data:
            traduzir_objeto(item, tradutor, lang_destino, placeholder_pattern, translate_angle)

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.ui = UI()
        
        # Frame principal
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Frame superior para idioma e opções
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X)
        
        # Frame para seleção de idioma
        lang_frame = ttk.Frame(top_frame)
        lang_frame.pack(side=tk.LEFT, padx=(0, 200))
        
        ttk.Label(lang_frame, text=self.ui.get_text("target_language"), 
                 font=("Arial", 10)).pack(anchor=tk.W)
        
        self.lang_combobox = ttk.Combobox(lang_frame, values=list(LINGUAGENS.keys()), 
                                         state="readonly", width=30)
        self.lang_combobox.pack(pady=(5, 0))
        self.lang_combobox.set(list(LINGUAGENS.keys())[list(LINGUAGENS.values()).index(self.ui.current_lang)])
        self.lang_combobox.bind('<<ComboboxSelected>>', self.update_interface_language)
        
        # Inicializa a opcao de translate_angle conforme preferencia
        self.translate_angle_var = tk.BooleanVar(value=self.ui.default_translate_angle)
        self.angle_checkbox = ttk.Checkbutton(
            lang_frame, 
            text=self.ui.get_text("translate_angle"),
            variable=self.translate_angle_var
        )
        self.angle_checkbox.pack(pady=(5, 0), anchor=tk.W)
        # Vincula mudança para salvar a preferencia
        self.translate_angle_var.trace('w', self.save_translate_angle_pref)
        
        # Frame para opções de salvamento
        save_frame = ttk.Frame(top_frame)
        save_frame.pack(side=tk.LEFT, fill=tk.X)
        
        self.save_location_var = tk.StringVar(value="silly")
        self.silly_radio = ttk.Radiobutton(save_frame, 
                                         text=self.ui.get_text("save_silly"),
                                         variable=self.save_location_var, 
                                         value="silly")
        self.silly_radio.pack(anchor=tk.W)
        
        self.custom_radio = ttk.Radiobutton(save_frame, 
                                          text=self.ui.get_text("save_custom"),
                                          variable=self.save_location_var, 
                                          value="custom")
        self.custom_radio.pack(anchor=tk.W)
        
        # Frame para configurações do SillyTavern
        self.silly_frame = ttk.Frame(save_frame)
        self.silly_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.change_dir_button = ttk.Button(self.silly_frame, 
                                          text=self.ui.get_text("change_silly_dir"),
                                          command=self.change_silly_dir)
        self.change_dir_button.pack(anchor=tk.W)
        
        self.silly_path_label = ttk.Label(self.silly_frame, text="", wraplength=200)
        self.silly_path_label.pack(anchor=tk.W, pady=(5, 0))
        self.update_silly_path_label()
        
        # Frame inferior para botão e progresso
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(20, 0))
        
        # Botão de iniciar
        self.start_button = ttk.Button(bottom_frame, 
                                     text=self.ui.get_text("start_translation"),
                                     command=self.start_translation)
        self.start_button.pack()
        
        # Barra de progresso
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(bottom_frame, 
                                          variable=self.progress_var, 
                                          maximum=100)
        
        self.save_location_var.trace('w', self.update_silly_frame_visibility)
    
    def update_interface_language(self, event=None):
        selected_lang = LINGUAGENS[self.lang_combobox.get()]
        self.ui.current_lang = selected_lang
        # Salvar preferencia de idioma no config
        self.ui.config.data["last_used_language"] = selected_lang
        self.ui.config.save_config()
        # Atualizar todos os textos da interface
        self.root.title(self.ui.get_text("window_title"))
        self.angle_checkbox.config(text=self.ui.get_text("translate_angle"))
        self.silly_radio.config(text=self.ui.get_text("save_silly"))
        self.custom_radio.config(text=self.ui.get_text("save_custom"))
        self.change_dir_button.config(text=self.ui.get_text("change_silly_dir"))
        self.start_button.config(text=self.ui.get_text("start_translation"))
        self.update_silly_path_label()

    def save_translate_angle_pref(self, *args):
        # Atualiza e salva a preferencia translate_angle
        self.ui.config.data["translate_angle"] = self.translate_angle_var.get()
        self.ui.config.save_config()

    def update_silly_path_label(self):
        path = self.ui.config.data.get("silly_tavern_path", 
                                     self.ui.get_text("not_configured"))
        self.silly_path_label.config(
            text=f"{self.ui.get_text('current_location')}{path}")

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
            
            full_path = os.path.join(self.ui.config.data["silly_tavern_path"],
                                   "data", "default-user", "OpenAI Settings", filename)
            
            if os.path.exists(full_path):
                if messagebox.askyesno(self.ui.get_text("filename_dialog_title"), 
                                     self.ui.get_text("file_exists")):
                    result["filename"] = filename
                    dialog.destroy()
            else:
                result["filename"] = filename
                dialog.destroy()
        
        ttk.Button(dialog, text=self.ui.get_text("save"), command=on_save).pack(pady=10)
        return result["filename"]
    
    def start_translation(self):
        arquivo_origem = filedialog.askopenfilename(
            title=self.ui.get_text("select_json_original"),
            filetypes=[(self.ui.get_text("json_filetype"), "*.json"), (self.ui.get_text("all_filetype"), "*.*")]
        )
        
        if not arquivo_origem:
            return
        original_name = os.path.basename(arquivo_origem)
        
        try:
            if self.save_location_var.get() == "silly":
                if not self.ui.config.data.get("silly_tavern_path"):
                    messagebox.showerror(self.ui.get_text("error"), self.ui.get_text("configure_silly_dir"))
                    return
                filename = self.ask_filename(original_name)
                if not filename:
                    return
                novo_arquivo = os.path.join(self.ui.config.data["silly_tavern_path"],
                                          "data", "default-user", "OpenAI Settings", filename)
            else:
                novo_arquivo = filedialog.asksaveasfilename(
                    title=self.ui.get_text("save_as"),
                    defaultextension=".json",
                    filetypes=[(self.ui.get_text("json_filetype"), "*.json")]
                )
                if not novo_arquivo:
                    return

            # Desabilitar botão enquanto carrega
            self.start_button.config(state='disabled')
            # Configurar barra de progresso em modo indeterminate
            self.progress_bar.config(mode='indeterminate')
            self.progress_bar.pack(fill=tk.X, pady=10)
            self.progress_bar.start(10)

            def translation_task():
                try:
                    with open(arquivo_origem, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    tradutor = Translator()
                    lang_destino = self.ui.current_lang
                    translate_angle = self.translate_angle_var.get()
                    placeholder_pattern = None
                    traduzir_objeto(data, tradutor, lang_destino, placeholder_pattern, translate_angle)
                    with open(novo_arquivo, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    self.root.after(0, lambda: messagebox.showinfo(self.ui.get_text("success"), self.ui.get_text("translation_success")))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror(self.ui.get_text("error"), str(e)))
                finally:
                    self.root.after(0, lambda: self.progress_bar.stop())
                    self.root.after(0, lambda: self.progress_bar.pack_forget())
                    # Reabilitar o botão após tradução
                    self.root.after(0, lambda: self.start_button.config(state='normal'))

            threading.Thread(target=translation_task).start()
        except Exception as e:
            messagebox.showerror(self.ui.get_text("error"), str(e))
            self.progress_bar.pack_forget()
            self.start_button.config(state='normal')

def main():
    root = tk.Tk()
    root.title("Preset Translator")
    root.geometry("600x300")  # Reduzido o tamanho vertical
    
    MainWindow(root)
    
    # Centralizar janela
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()

if __name__ == "__main__":
    main()
