from deep_translator import MyMemoryTranslator

class MyMemoryTranslatorService:
    def translate(self, text, dest):
        try:
            translated_text = MyMemoryTranslator(target=dest).translate(text)
        except Exception as e:
            print(f"MyMemory translation error: {e}")
            translated_text = text
        return type("Translation", (), {"text": translated_text})()
