import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
from engine import TranslationConfig, TranslationEngine, load_json_safe, save_json

class TranslatorApp:
    def __init__(self, root):
        self.root = root
        self.config = TranslationConfig()
        self.engine = TranslationEngine()

        self.root.title("SillyTavern Character Translator")
        self.root.geometry("850x500")
        self.root.minsize(850, 500)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.translate_angle_var = tk.BooleanVar(value=self.config.data.get("translate_angle"))
        self.save_location_var = tk.StringVar(value=self.config.data.get("save_location"))
        self.use_llm_var = tk.BooleanVar(value=self.config.data.get("use_llm_translation"))
        self.llm_provider_var = tk.StringVar(value=self.config.data.get("llm_provider"))
        
        self.openrouter_api_key_var = tk.StringVar(value=self.config.data.get("openrouter_api_key"))
        self.openrouter_model_var = tk.StringVar(value=self.config.data.get("openrouter_model"))
        self.groq_api_key_var = tk.StringVar(value=self.config.data.get("groq_api_key"))
        self.groq_model_var = tk.StringVar(value=self.config.data.get("groq_model"))

        main_frame = ttk.Frame(root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        self._create_top_options_frame(main_frame)
        self._create_llm_frame(main_frame)
        self._create_file_list_frame(main_frame)
        self._create_status_and_action_frame(main_frame)
        
        self._update_llm_ui_visibility()

    def on_closing(self):
        self._save_config()
        self.root.destroy()

    def _create_top_options_frame(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)

        lang_frame = ttk.Frame(frame)
        lang_frame.grid(row=0, column=0, sticky="w")
        ttk.Label(lang_frame, text="Target Language:").pack(side=tk.LEFT, padx=(0, 5))
        self.lang_combobox = ttk.Combobox(lang_frame, values=list(self.config.languages.values()), state="readonly", width=15)
        self.lang_combobox.set(self.config.get_native_name(self.config.current_lang))
        self.lang_combobox.pack(side=tk.LEFT)
        self.lang_combobox.bind('<<ComboboxSelected>>', self._update_language_config)

        options_frame = ttk.Frame(frame)
        options_frame.grid(row=0, column=1, sticky="e")
        ttk.Checkbutton(options_frame, text="Translate content inside <...> brackets (LLM only)", variable=self.translate_angle_var).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Label(options_frame, text="Save Location:").pack(side=tk.LEFT, padx=(0,5))
        
        save_loc_container = ttk.Frame(options_frame)
        save_loc_container.pack(side=tk.LEFT)
        
        st_frame = ttk.Frame(save_loc_container)
        st_frame.pack(side=tk.LEFT)
        self.silly_radio = ttk.Radiobutton(st_frame, text="SillyTavern folder", variable=self.save_location_var, value="silly", command=self._update_save_location_ui)
        self.silly_radio.pack(side=tk.LEFT)
        self.change_st_path_button = ttk.Button(st_frame, text="Change", command=self._select_silly_tavern_path)
        self.change_st_path_button.pack(side=tk.LEFT, padx=(2, 5))

        self.custom_radio = ttk.Radiobutton(save_loc_container, text="Custom folder", variable=self.save_location_var, value="custom", command=self._update_save_location_ui)
        self.custom_radio.pack(side=tk.LEFT)
        
        self._update_save_location_ui()

    def _create_llm_frame(self, parent):
        llm_container = ttk.Frame(parent)
        llm_container.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        llm_container.columnconfigure(0, weight=1)

        self.use_llm_checkbox = ttk.Checkbutton(llm_container, text="ON: Use LLM for Translation (RECOMMENDED!)\nOFF: Use Google Translate", variable=self.use_llm_var, command=self._update_llm_ui_visibility)
        self.use_llm_checkbox.grid(row=0, column=0, sticky="w")

        self.llm_options_frame = ttk.LabelFrame(llm_container, text="LLM Settings", padding=(10, 5))
        self.llm_options_frame.columnconfigure(1, weight=1)
        
        provider_frame = ttk.Frame(self.llm_options_frame)
        provider_frame.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 5))
        ttk.Label(provider_frame, text="Provider:").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(provider_frame, text="OpenRouter", variable=self.llm_provider_var, value="openrouter", command=self._update_llm_provider_ui).pack(side=tk.LEFT)
        ttk.Radiobutton(provider_frame, text="Groq", variable=self.llm_provider_var, value="groq", command=self._update_llm_provider_ui).pack(side=tk.LEFT, padx=10)

        self.or_api_label = ttk.Label(self.llm_options_frame, text="OpenRouter API Key:")
        self.or_model_label = ttk.Label(self.llm_options_frame, text="OpenRouter Model:")
        self.or_api_entry = ttk.Entry(self.llm_options_frame, textvariable=self.openrouter_api_key_var, show='*', width=40)
        self.or_model_entry = ttk.Entry(self.llm_options_frame, textvariable=self.openrouter_model_var, width=40)

        self.groq_api_label = ttk.Label(self.llm_options_frame, text="Groq API Key:")
        self.groq_model_label = ttk.Label(self.llm_options_frame, text="Groq Model:")
        self.groq_api_entry = ttk.Entry(self.llm_options_frame, textvariable=self.groq_api_key_var, show='*', width=40)
        self.groq_model_entry = ttk.Entry(self.llm_options_frame, textvariable=self.groq_model_var, width=40)
        
        self._update_llm_provider_ui()

    def _update_llm_ui_visibility(self):
        if self.use_llm_var.get():
            self.llm_options_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        else:
            self.llm_options_frame.grid_forget()

    def _create_file_list_frame(self, parent):
        list_container = ttk.Frame(parent)
        list_container.grid(row=3, column=0, sticky="nsew", pady=(5,0))
        list_container.rowconfigure(1, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        ttk.Label(list_container, text="Files to Translate:", font=("", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky='w', pady=(5,2))

        list_frame = ttk.Frame(list_container)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.file_list = tk.Listbox(list_frame, selectmode="extended", yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.file_list.yview)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        button_frame = ttk.Frame(list_container)
        button_frame.grid(row=1, column=1, sticky="ns", padx=(10, 0))
        self.select_button = ttk.Button(button_frame, text="Select Files", command=self.select_files)
        self.select_button.pack(pady=2, fill=tk.X)
        self.remove_button = ttk.Button(button_frame, text="Remove", command=self.remove_selected_files)
        self.remove_button.pack(pady=2, fill=tk.X)

    def _create_status_and_action_frame(self, parent):
        self.progress_bar = ttk.Progressbar(parent, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=4, column=0, sticky="ew", pady=(10, 2))
        self.status_label = ttk.Label(parent, text="Idle", anchor="center")
        self.status_label.grid(row=5, column=0, sticky="ew")
        self.translate_button = ttk.Button(parent, text="Start Translation", command=self.start_translation)
        self.translate_button.grid(row=6, column=0, pady=(10, 0))

    def _update_language_config(self, event=None):
        selected_lang_name = self.lang_combobox.get()
        lang_code = self.config.get_lang_code(selected_lang_name)
        if lang_code and lang_code != self.config.current_lang:
            self.config.current_lang = lang_code

    def _update_llm_provider_ui(self):
        provider = self.llm_provider_var.get()
        for widget in [self.or_api_label, self.or_api_entry, self.or_model_label, self.or_model_entry,
                       self.groq_api_label, self.groq_api_entry, self.groq_model_label, self.groq_model_entry]:
            widget.grid_forget()

        if provider == 'openrouter':
            self.or_api_label.grid(row=1, column=0, sticky='w', pady=2, padx=5)
            self.or_api_entry.grid(row=1, column=1, sticky='ew', pady=2)
            self.or_model_label.grid(row=2, column=0, sticky='w', pady=2, padx=5)
            self.or_model_entry.grid(row=2, column=1, sticky='ew', pady=2)
        elif provider == 'groq':
            self.groq_api_label.grid(row=1, column=0, sticky='w', pady=2, padx=5)
            self.groq_api_entry.grid(row=1, column=1, sticky='ew', pady=2)
            self.groq_model_label.grid(row=2, column=0, sticky='w', pady=2, padx=5)
            self.groq_model_entry.grid(row=2, column=1, sticky='ew', pady=2)

    def _update_save_location_ui(self):
        if self.save_location_var.get() == "silly":
            self.change_st_path_button.pack(side=tk.LEFT, padx=(2, 5))
        else:
            self.change_st_path_button.pack_forget()

    def _select_silly_tavern_path(self):
        path = filedialog.askdirectory(title="Select Your SillyTavern Root Folder")
        if path:
            self.config.data['silly_tavern_path'] = path
            messagebox.showinfo("Path Set", f"SillyTavern path set to:\n{path}")

    def _save_config(self):
        self.config.data.update({
            "last_used_language": self.config.current_lang,
            "translate_angle": self.translate_angle_var.get(),
            "save_location": self.save_location_var.get(),
            "use_llm_translation": self.use_llm_var.get(),
            "llm_provider": self.llm_provider_var.get(),
            "openrouter_api_key": self.openrouter_api_key_var.get(),
            "openrouter_model": self.openrouter_model_var.get(),
            "groq_api_key": self.groq_api_key_var.get(),
            "groq_model": self.groq_model_var.get()
        })
        self.config.save()
        print("Configuration saved.")

    def select_files(self):
        filepaths = filedialog.askopenfilenames(
            title="Select Character Files",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        current_files = set(self.file_list.get(0, tk.END))
        for fp in filepaths:
            if fp not in current_files:
                self.file_list.insert(tk.END, fp)

    def remove_selected_files(self):
        for index in reversed(self.file_list.curselection()):
            self.file_list.delete(index)

    def set_ui_state(self, is_enabled):
        state = "normal" if is_enabled else "disabled"
        
        # Action buttons
        for btn in [self.select_button, self.remove_button, self.translate_button, self.change_st_path_button]:
            btn.config(state=state)
            
        # Selects and Options
        for widget in [self.lang_combobox, self.silly_radio, self.custom_radio, self.use_llm_checkbox]:
            widget.config(state=state)

        # LLM specific inputs
        for entry in [self.or_api_entry, self.or_model_entry, self.groq_api_entry, self.groq_model_entry]:
            entry.config(state=state)
        
        # Provider radios
        for child in self.llm_options_frame.winfo_children():
            if isinstance(child, ttk.Frame):
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Radiobutton):
                        sub.config(state=state)

    def start_translation(self):
        self._save_config()
        files = self.file_list.get(0, tk.END)
        if not files:
            messagebox.showwarning("Warning", "No files selected for translation.")
            return

        save_dir = ""
        save_location = self.config.data["save_location"]
        if save_location == "silly":
            save_dir = self.config.data.get("silly_tavern_path")
            if not save_dir or not os.path.isdir(save_dir):
                messagebox.showerror("Error", "SillyTavern path is not set or is invalid. Please set it using the 'Change' button.")
                return
        elif save_location == "custom":
            save_dir = filedialog.askdirectory(title="Select a Folder to Save Translated Files")
            if not save_dir:
                self.status_label.config(text="Idle")
                return

        provider = self.config.data['llm_provider']
        kwargs = {
            "target_lang_code": self.config.current_lang,
            "target_lang_name": self.config.get_native_name(self.config.current_lang),
            "use_llm": self.config.data["use_llm_translation"],
            "translate_angle": self.config.data.get("translate_angle"),
            "llm_config": {
                "provider": provider,
                "api_key": self.config.data.get(f"{provider}_api_key"),
                "model": self.config.data.get(f"{provider}_model")
            } if self.config.data["use_llm_translation"] else None
        }

        if kwargs["use_llm"] and (not kwargs["llm_config"]["api_key"] or not kwargs["llm_config"]["model"]):
            messagebox.showerror("Error", "LLM provider API key and model must be configured.")
            return

        self.set_ui_state(False)
        self.progress_bar['value'] = 0
        self.status_label.config(text="Starting translation...")

        thread = threading.Thread(target=self._translation_worker, args=(files, save_dir, kwargs), daemon=True)
        thread.start()

    def _update_progress(self, current_file, total_files, filename, current_field, total_fields):
        """Callback to update the progress bar and status label with detailed info."""
        if total_files > 0:
            # calculate overall progress percentage
            progress_per_file = 100 / total_files
            progress_for_completed_files = current_file * progress_per_file
            
            progress_for_current_file = 0
            if total_fields > 0:
                progress_for_current_file = (current_field / total_fields) * progress_per_file

            total_percentage = progress_for_completed_files + progress_for_current_file
            self.progress_bar['value'] = total_percentage

            current_file_num = current_file + 1
            if total_fields > 0:
                status_msg = f"Translating: {os.path.basename(filename)} ({current_file_num}/{total_files}) ({current_field}/{total_fields})"
            else:
                status_msg = f"Processing: {os.path.basename(filename)} ({current_file_num}/{total_files}) (0 fields found)"
            
            self.status_label.config(text=status_msg)

    def _translation_worker(self, files, save_dir, kwargs):
        try:
            total_files = len(files)
            for i, file_path in enumerate(files):
                filename = os.path.basename(file_path)
                
                def field_progress_callback(current_field, total_fields):
                    self.root.after(0, self._update_progress, i, total_files, file_path, current_field, total_fields)

                kwargs_with_progress = kwargs.copy()
                kwargs_with_progress['on_progress'] = field_progress_callback

                self.root.after(0, lambda f=filename: self.status_label.config(text=f"Loading: {f}..."))
                json_data = load_json_safe(file_path)
                if not json_data:
                    print(f"Failed to load or empty JSON: {file_path}")
                    self.root.after(0, self._update_progress, i, total_files, file_path, 0, 0)
                    continue
                
                # Perform translation
                translated_data = self.engine.translate_json_data(data=json_data, **kwargs_with_progress)
                
                # Save result
                base, ext = os.path.splitext(filename)
                new_filename = f"{base}_{kwargs['target_lang_code']}{ext}"
                
                potential_char_dir = os.path.join(save_dir, "public", "characters")
                output_dir = potential_char_dir if os.path.isdir(potential_char_dir) else save_dir
                
                output_path = os.path.join(output_dir, new_filename)
                if not save_json(output_path, translated_data):
                    raise IOError(f"Failed to save translated file to {output_path}")

            self.root.after(0, lambda: self.progress_bar.config(value=100))
            self.root.after(0, lambda: self.status_label.config(text=f"Completed {total_files}/{total_files} files."))
            self.root.after(0, lambda: messagebox.showinfo("Success", "Translation completed successfully."))
        except Exception as e:
            print(f"Translation Error: {e}")
            self.root.after(0, lambda e=e: messagebox.showerror("Translation Error", f"An error occurred during translation:\n\n{str(e)}"))
        finally:
            self.root.after(0, lambda: self.set_ui_state(True))
            self.root.after(0, lambda: self.status_label.config(text="Idle"))


if __name__ == "__main__":
    root = tk.Tk()
    app = TranslatorApp(root)
    root.mainloop()