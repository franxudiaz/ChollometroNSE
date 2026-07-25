import logging
import re
from deep_translator import GoogleTranslator

# Diccionario offline extendido para informática, herramientas y suministros frecuentes
OFFLINE_DICT = {
    # Informática y Electrónica
    "memoria ram": "RAM pamäť",
    "memoria": "pamäť",
    "memorias": "pamäte",
    "raton": "myš",
    "ratón": "myš",
    "ratones": "myši",
    "teclado": "klávesnica",
    "teclados": "klávesnice",
    "pendrive": "USB kľúč",
    "memoria usb": "USB kľúč",
    "usb": "USB",
    "monitor": "monitor",
    "pantalla": "monitor",
    "monitores": "monitory",
    "disco duro": "pevný disk",
    "hdd": "HDD disk",
    "ssd": "SSD disk",
    "disco ssd": "SSD disk",
    "altavoz bluetooth": "bluetooth reproduktor",
    "altavoz": "reproduktor",
    "altavoces": "reproduktory",
    "crimpadora rj45": "krimpovač rj45",
    "crimpadora": "krimpovacie kliešte",
    "rj45": "RJ45 konektor",
    "conector rj45": "RJ45 konektor",
    "cable utp": "UTP kábel",
    "cable de red": "sieťový kábel",
    "cable": "kábel",
    "cables": "káblov",

    # Ferretería y Suministros
    "alicates": "kliešte",
    "alicate": "kliešte",
    "destornillador": "skrutkovač",
    "destornillador vde": "VDE skrutkovač",
    "carraca": "račňa",
    "cinta aislante": "izolačná páska",
    "cinta": "páska",
    "llave": "kľúč",
    "llaves": "kľúče",
    "martillo": "kladivo",
    "taladro": "vŕtačka",
    "sierra": "píla",
    "tornillo": "skrutka",
    "tuerca": "matica",
    "arandela": "podložka",
    "batería": "batéria",
    "disco": "kotúč",
    "lijadora": "brúska",
    "soldadura": "zváračka",
    "herramientas": "náradie",
    "limpieza": "čistenie",
    "ropa": "oblečenie",
    "pantalon": "nohavice",
    "pantalones": "nohavice",
    "marcos": "rámy",
    "papelería": "papiernictvo",
    "toner": "tóner"
}

def translate_es_to_sk(query_es):
    """
    Traduce una consulta del español al eslovaco usando el diccionario informático/industrial offline,
    con fallback a GoogleTranslator libre sin claves si no está en el diccionario.
    """
    clean_query = (query_es or '').strip().lower()
    if not clean_query:
        return ""
    
    # 1. Comprobar diccionario offline directo
    if clean_query in OFFLINE_DICT:
        return OFFLINE_DICT[clean_query]
        
    # 2. Intentar traducción con deep_translator
    try:
        translated = GoogleTranslator(source='es', target='sk').translate(clean_query)
        if translated and len(translated.strip()) > 0:
            return translated.strip()
    except Exception as e:
        logging.warning(f"Error en traducción en línea para '{clean_query}': {e}")
        
    # 3. Fallback palabra por palabra con el diccionario offline
    words = clean_query.split()
    translated_words = []
    for w in words:
        w_clean = re.sub(r'[^\w]', '', w)
        if w_clean in OFFLINE_DICT:
            translated_words.append(OFFLINE_DICT[w_clean])
        else:
            translated_words.append(w)
            
    return " ".join(translated_words)
