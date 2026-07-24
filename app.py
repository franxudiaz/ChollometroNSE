import os
import json
import logging
import pandas as pd
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from scraper import search_live_products, translate_query_to_slovak

# Cargar variables de entorno desde .env si existe
load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

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

    # Si no hay cliente Gemini configurado en el servidor o falla, usar el raspador en tiempo real
    if not results:
        source = "live_scraper"
        results = search_live_products(query, providers_list, max_results=5)

    return jsonify({
        "query": query,
        "category": category,
        "source": source,
        "count": len(results),
        "results": results
    })

def perform_gemini_search(client, query, category, providers_list, domains_list):
    """
    Utiliza el cliente Google GenAI SDK en el servidor con Gemini y Google Search Grounding para encontrar productos reales
    en e-commerce eslovacos con sus datos reales (referencia, precio y URL a la página del producto).
    """
    providers_text = "\n".join([f"- {p['Proveedor']} ({p['tipo']}): {p['WEB']}" for p in providers_list[:25]])
    
    prompt = f"""
Eres 'Chollometro NSE', el asistente oficial de compras para la misión en Eslovaquia.

El usuario busca el producto: "{query}"
Categoría filtrada (si aplica): "{category if category else 'Cualquiera'}"

Proveedores de confianza disponibles en Eslovaquia (con sus sitios web oficiales):
{providers_text}

INSTRUCCIONES CRÍTICAS:
1. Traduce la consulta "{query}" al eslovaco para buscar coincidencias exactas mediante la herramienta Google Search (Google Search Grounding).
2. Identifica entre 3 y 5 productos REALES existentes actualmente en las tiendas de Eslovaquia indicadas en la lista (ej: OBI obi.sk, VERCAJCH CENTRUM vercajch.sk, NAY nay.sk, AUTOTECHNA autotechna.sk, DECATHLON decathlon.sk, HAGARD-HAL hagard.sk, etc.).
3. Para cada producto extrae los datos reales de su ficha en la web:
   - Proveedor: Nombre exacto de la empresa de la lista (ej. OBI, VERCAJCH CENTRUM, AUTOTECHNA)
   - Nombre (ES): Nombre traducido o limpio en español del producto
   - Nombre (SK): Nombre completo real del producto en eslovaco tal como figura en la tienda
   - Referencia / Código: El código, número de artículo o referencia de catálogo REAL extraído de la web del proveedor (ej. OBI-4007875347502, VRC-180-KLI, KNIPEX-0306180). NUNCA inventes o utilices marcadores de posición genéricos.
   - Precio (€): El precio real unitario con IVA en euros (ej. 5.59 €, 31.99 €)
   - URL: La URL REAL y DIRECTA a la ficha del producto específico en el sitio web del proveedor (ej. https://www.obi.sk/p/4007875347502 o https://vercajch.sk/produkt/...). La URL debe abrir la página del producto directamente.

Devuelve la respuesta ÚNICAMENTE en formato JSON con la siguiente estructura de lista de objetos:

[
  {{
    "proveedor": "OBI",
    "nombre_es": "Alicates universales 180 mm",
    "nombre_sk": "Kombinované kliešte 180 mm",
    "referencia": "OBI-4007875347502",
    "precio_eur": "5.59 €",
    "url": "https://www.obi.sk/p/4007875347502"
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
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
