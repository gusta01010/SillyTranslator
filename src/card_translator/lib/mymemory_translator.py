from deep_translator import MyMemoryTranslator
from langdetect import detect  # novo

def split_text(text, chunk_size):
    # Divide o texto em blocos, sem quebrar palavras quando possível.
    words = text.split()
    chunks = []
    current = ""
    for word in words:
        # Se a palavra em si for maior que o chunk_size, divida-a:
        if len(word) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(word), chunk_size):
                chunks.append(word[i:i+chunk_size])
            continue
        if current:
            if len(current) + len(word) + 1 <= chunk_size:
                current += " " + word
            else:
                chunks.append(current)
                current = word
        else:
            current = word
    if current:
        chunks.append(current)
    return chunks

class MyMemoryTranslatorService:
    def translate(self, text, dest):
        lang_map = {
            'pt': 'pt-BR',
            'en': 'en-US',
            'es': 'eo-EU',
            'fr': 'fr-FR',
            'de': 'de-DE',
            'it': 'it-IT',
            'ja': 'ja-JP',
            'zh-cn': 'zh-CN',
            'ko': 'ko-KR',
            'ru': 'ru-RU'
        }
        target = lang_map.get(dest, dest)
        chunk_size = 499
        # Detecta o idioma de origem de forma dinâmica
        src = detect(text)
        translator = MyMemoryTranslator(source=src, target=target)
        if len(text) <= chunk_size:
            translated_text = translator.translate(text)
        else:
            chunks = split_text(text, chunk_size)
            translated_chunks = [translator.translate(chunk) for chunk in chunks]
            translated_text = ''.join(translated_chunks)
        return type("Translation", (), {"text": translated_text})()
