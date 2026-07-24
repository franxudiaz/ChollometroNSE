import os
import re
import json
import logging
import pandas as pd
from urllib.parse import quote_plus, urlparse
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Diccionario de traducción común español -> eslovaco para términos de búsqueda
TRANSLATION_DICT = {
    "alicates": "kliešte",
    "destornillador": "skrutkovač",
    "carraca": "račňa",
    "cinta": "páska",
    "aislante": "izolačná",
    "llave": "kľúč",
    "martillo": "kladivo",
    "taladro": "vŕtačka",
    "sierra": "píla",
    "tornillo": "skrutka",
    "tuerca": "matica",
    "arandela": "podložka",
    "cable": "kábel",
    "batería": "batéria",
    "disco": "kotúč",
    "lijadora": "brúska",
    "soldadura": "zváračka",
    "herramientas": "náradie",
    "limpieza": "čistenie",
    "ropa": "oblečenie",
    "marcos": "rámy",
    "papelería": "papiernictvo"
}

def translate_to_slovak(text):
    if not text:
        return ""
    words = text.lower().split()
    translated_words = []
    for w in words:
        clean_w = re.sub(r'[^\w]', '', w)
        if clean_w in TRANSLATION_DICT:
            translated_words.append(TRANSLATION_DICT[clean_w])
        else:
            translated_words.append(w)
    return " ".join(translated_words)

# Configuración de búsqueda del archivo Excel de proveedores
def find_excel_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, 'Proveedores SVK V (VERSIÓN 1.1).xlsx'),
        os.path.join(base_dir, 'data', 'Proveedores SVK V (VERSIÓN 1.1).xlsx'),
    ]
    for folder in [base_dir, os.path.join(base_dir, 'data')]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith('.xlsx') and 'proveed' in f.lower():
                    candidates.append(os.path.join(folder, f))
    
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

providers_df = None

def load_providers():
    global providers_df
    excel_path = find_excel_file()
    if excel_path:
        try:
            df = pd.read_excel(excel_path)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.fillna('')
            df['Proveedor'] = df['Proveedor'].astype(str).str.strip()
            df['tipo'] = df['tipo'].astype(str).str.strip()
            df['WEB'] = df['WEB'].astype(str).str.strip()
            providers_df = df
            logging.info(f"Cargados {len(df)} proveedores desde {excel_path}")
        except Exception as e:
            logging.error(f"Error al cargar el Excel de proveedores ({excel_path}): {e}")
            providers_df = pd.DataFrame(columns=['Proveedor', 'tipo', 'WEB'])
    else:
        logging.warning("No se encontró ningún archivo Excel de proveedores.")
        providers_df = pd.DataFrame(columns=['Proveedor', 'tipo', 'WEB'])

load_providers()

def build_direct_search_url(web_url, clean_search_term):
    """
    Construye una URL directa válida al buscador del e-commerce del proveedor.
    """
    if not web_url:
        return "https://www.google.sk"
    
    # Limpiar cualquier texto o sufijo de prueba
    clean_term = re.sub(r'Modelo\s+Profesional.*', '', clean_search_term, flags=re.IGNORECASE)
    clean_term = re.sub(r'Opción\s+\d+.*', '', clean_term, flags=re.IGNORECASE)
    clean_term = re.sub(r'SK-\d+.*', '', clean_term, flags=re.IGNORECASE)
    clean_term = clean_term.strip()

    # Traducir los términos limpios al eslovaco
    slovak_term = translate_to_slovak(clean_term)
    term_encoded = quote_plus(slovak_term)
    
    parsed = urlparse(web_url if web_url.startswith("http") else f"https://{web_url}")
    domain = parsed.netloc.lower()
    
    if "autotechna.sk" in domain:
        return f"https://www.autotechna.sk/?s={term_encoded}"
    elif "vercajch.sk" in domain:
        return f"https://vercajch.sk/?s={term_encoded}"
    elif "obi.sk" in domain:
        return f"https://www.obi.sk/search/{term_encoded}/"
    elif "nay.sk" in domain:
        return f"https://www.nay.sk/vyhladavanie?q={term_encoded}"
    elif "decathlon.sk" in domain:
        return f"https://www.decathlon.sk/search?Ntt={term_encoded}"
    elif "ikea.com" in domain:
        return f"https://www.ikea.com/sk/sk/search/?q={term_encoded}"
    elif "jysk.sk" in domain:
        return f"https://jysk.sk/search?query={term_encoded}"
    elif "benulekaren.sk" in domain:
        return f"https://www.benulekaren.sk/vyhladavanie?q={term_encoded}"
    else:
        clean_domain = domain.replace("www.", "")
        return f"https://www.google.com/search?q=site:{clean_domain}+{term_encoded}"

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        logging.error(f"Error al inicializar el cliente de Gemini GenAI: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    if providers_df is None or providers_df.empty:
        return jsonify({"categories": []})
    
    raw_types = providers_df['tipo'].dropna().tolist()
    categories = sorted(list(set([t for t in raw_types if t])))
    return jsonify({"categories": categories})

@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    category = data.get('category', '').strip()

    if not query:
        return jsonify({"error": "La consulta de búsqueda no puede estar vacía"}), 400

    filtered_providers = providers_df.copy()
    if category and not category.lower().startswith('tod'):
        filtered_providers = filtered_providers[filtered_providers['tipo'].str.contains(category, case=False, na=False)]

    providers_list = filtered_providers.to_dict(orient='records')
    domains_list = [p['WEB'] for p in providers_list if p.get('WEB')]

    client = get_gemini_client()
    results = []
    source = "gemini"

    if client:
        try:
            results = perform_gemini_search(client, query, category, providers_list, domains_list)
        except Exception as e:
            logging.error(f"Error durante la búsqueda con Gemini: {e}")
            results = []

    if not results:
        source = "fallback"
        results = perform_fallback_search(query, category, providers_list)

    # Post-procesar para asegurar URLs limpias y operativas a la tienda
    for r in results:
        url = r.get('url', '').strip()
        prov_web = ""
        for p in providers_list:
            if p.get('Proveedor', '').lower() in r.get('proveedor', '').lower() or r.get('proveedor', '').lower() in p.get('Proveedor', '').lower():
                prov_web = p.get('WEB', '')
                break
        if not prov_web:
            prov_web = url

        parsed_url = urlparse(url if url.startswith("http") else f"https://{url}")
        if not parsed_url.path or parsed_url.path == "/" or url.endswith(".sk") or url.endswith(".com") or url.endswith(".sk/"):
            r['url'] = build_direct_search_url(prov_web or url, query)

    return jsonify({
        "query": query,
        "category": category,
        "source": source,
        "count": len(results),
        "results": results
    })

def perform_gemini_search(client, query, category, providers_list, domains_list):
    """
    Utiliza el cliente Google GenAI SDK con Gemini para buscar y formatear los productos.
    """
    providers_text = "\n".join([f"- {p['Proveedor']} ({p['tipo']}): {p['WEB']}" for p in providers_list[:25]])
    
    prompt = f"""
Eres 'Chollometro NSE', un asistente especializado en búsqueda y compras de material industrial, herramientas y suministros en Eslovaquia.

El usuario busca el producto: "{query}"
Categoría filtrada (si aplica): "{category if category else 'Cualquiera'}"

Proveedores de confianza disponibles en Eslovaquia (con sus sitios web oficiales):
{providers_text}

INSTRUCCIONES CRÍTICAS:
1. Traduce la consulta "{query}" al eslovaco para buscar coincidencias exactas en catálogos de tiendas eslovacas.
2. Identifica entre 3 y 5 productos reales que coincidan con la búsqueda en las tiendas locales eslovacas.
3. REQUISITO OBLIGATORIO DE URL DIRECTA: El campo 'url' DEBE SER LA URL DIRECTA Y VÁLIDA A LA FICHA DEL PRODUCTO O AL BUSCADOR DEL PRODUCTO en la e-commerce. NUNCA devuelvas solo el dominio principal o la portada genérica.
4. Devuelve los resultados ESTRICTAMENTE en formato JSON con la siguiente estructura:

[
  {{
    "proveedor": "Nombre del Proveedor (ej. OBI, NAY, Vercajch Centrum)",
    "nombre_es": "Nombre completo del producto traducido al español",
    "nombre_sk": "Nombre completo del producto en eslovaco (según catálogo)",
    "referencia": "Código, modelo o número de referencia (ej. VDE-1000V-01 o N/A)",
    "precio_eur": "Precio unitario estimado con IVA en € (ej. 18.50 €)",
    "url": "URL directa a la ficha o buscador de este producto específico"
  }}
]

Responde ÚNICAMENTE con el bloque JSON válido, sin texto explicativo previo ni posterior.
"""
    try:
        from google.genai import types
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}]
            )
        )
        
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception as e:
        logging.error(f"Error procesando respuesta JSON de Gemini: {e}")
        
    return []

def perform_fallback_search(query, category, providers_list):
    """
    Genera resultados estructurados de demostración/fallback limpios basados en los proveedores del Excel,
    con URLs directas y totalmente funcionales al e-commerce del proveedor.
    """
    if not providers_list:
        providers_list = providers_df.to_dict(orient='records') if providers_df is not None else []
    
    sample_providers = providers_list[:4] if providers_list else [
        {"Proveedor": "VERCAJCH CENTRUM", "tipo": "Ferretería", "WEB": "http://vercajch.sk/"},
        {"Proveedor": "OBI", "tipo": "Leroy Merlin local", "WEB": "https://www.obi.sk"},
        {"Proveedor": "AUTOTECHNA", "tipo": "Recambios automóvil", "WEB": "https://www.autotechna.sk/"},
        {"Proveedor": "NAY", "tipo": "Electrónica y Tecnología", "WEB": "https://www.nay.sk"}
    ]

    sk_query_translated = translate_to_slovak(query)

    simulated_results = []
    for idx, p in enumerate(sample_providers, 1):
        prov_name = p.get('Proveedor', 'Proveedor SVK')
        web_url = p.get('WEB', 'https://www.google.sk')
        
        # Generar enlace directo a la búsqueda limpia del producto en la tienda
        direct_url = build_direct_search_url(web_url, query)

        simulated_results.append({
            "proveedor": prov_name,
            "nombre_es": f"{query.capitalize()} (Opción {idx})",
            "nombre_sk": f"{sk_query_translated.capitalize()} (SK Catálogo {idx})",
            "referencia": f"REF-SVK-00{idx}",
            "precio_eur": f"{12.50 + (idx * 6.80):.2f} €",
            "url": direct_url
        })

    return simulated_results

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
