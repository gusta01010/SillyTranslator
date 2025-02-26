class YandexTranslator:
    def translate(self, text, dest):
        # Dummy implementation without API calls
        translated_text = f"[Yandex {dest} translation] " + text
        return type("Translation", (), {"text": translated_text})()
