import os
import re
import json
import logging
import pandas as pd
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

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
    # Buscar cualquier archivo Excel que contenga 'Proveedores' en la raíz o en data/
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
    
    # Extraer tipos únicos y limpiarlos
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

    # Filtrar proveedores relevantes del Excel según la categoría o búsqueda
    filtered_providers = providers_df.copy()
    if category and not category.lower().startswith('tod'):
        filtered_providers = filtered_providers[filtered_providers['tipo'].str.contains(category, case=False, na=False)]

    providers_list = filtered_providers.to_dict(orient='records')
    domains_list = [p['WEB'] for p in providers_list if p.get('WEB')]

    # Intentar búsqueda mediante Gemini API
    client = get_gemini_client()
    results = []
    source = "gemini"

    if client:
        try:
            results = perform_gemini_search(client, query, category, providers_list, domains_list)
        except Exception as e:
            logging.error(f"Error durante la búsqueda con Gemini: {e}")
            results = []

    # Fallback a búsqueda simulada si no hay API Key o falla Gemini
    if not results:
        source = "fallback"
        results = perform_fallback_search(query, category, providers_list)

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

INSTRUCCIONES:
1. Traduce la consulta "{query}" al eslovaco para buscar coincidencias exactas en catálogos de tiendas eslovacas.
2. Identifica entre 3 y 5 productos reales o altamente representativos que coincidan con la búsqueda dentro de las tiendas locales eslovacas mencionadas (p. ej. OBI, Nay, Decathlon, Vercajch, Hagard-Hal, Stavebniny Dado, Metro, Copper, etc.).
3. Devuelve los resultados ESTRICTAMENTE en formato JSON con la siguiente estructura de lista de objetos:

[
  {{
    "proveedor": "Nombre del Proveedor (ej. OBI, NAY, Vercajch Centrum)",
    "nombre_es": "Nombre completo del producto traducido al español",
    "nombre_sk": "Nombre completo del producto en eslovaco (según catálogo)",
    "referencia": "Código, modelo o número de referencia (ej. VDE-1000V-01 o N/A)",
    "precio_eur": "Precio unitario estimado con IVA en € (ej. 18.50 €)",
    "url": "Enlace directo URL a la tienda o al dominio del proveedor (ej. https://www.obi.sk)"
  }}
]

Responde ÚNICAMENTE con el bloque JSON válido, sin texto explicativo previo ni posterior.
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        text = response.text.strip()
        # Limpiar etiquetas markdown de bloques de código json si existen
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
    Genera resultados estructurados de demostración/fallback basados en los proveedores del Excel.
    """
    if not providers_list:
        providers_list = providers_df.to_dict(orient='records') if providers_df is not None else []
    
    # Seleccionar hasta 4 proveedores acordes
    sample_providers = providers_list[:4] if providers_list else [
        {"Proveedor": "VERCAJCH CENTRUM", "tipo": "Ferretería", "WEB": "http://vercajch.sk/"},
        {"Proveedor": "OBI", "tipo": "Leroy Merlin local", "WEB": "https://www.obi.sk"},
        {"Proveedor": "HAGARD-HAL", "tipo": "Electricidad", "WEB": "http://www.hagard.sk/"},
        {"Proveedor": "NAY", "tipo": "Electrónica y Tecnología", "WEB": "https://www.nay.sk"}
    ]

    simulated_results = []
    for idx, p in enumerate(sample_providers, 1):
        prov_name = p.get('Proveedor', 'Proveedor SVK')
        web_url = p.get('WEB', 'https://www.google.sk')

        simulated_results.append({
            "proveedor": prov_name,
            "nombre_es": f"{query.title()} (Modelo Profesional SVK-{idx})",
            "nombre_sk": f"{query.capitalize()} profesionálny SK-{idx}00",
            "referencia": f"SK-REF-{idx}0948",
            "precio_eur": f"{12.50 + (idx * 6.80):.2f} €",
            "url": web_url if web_url.startswith("http") else f"https://{web_url}"
        })

    return simulated_results

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
