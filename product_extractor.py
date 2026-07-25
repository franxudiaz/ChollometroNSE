import re
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from deep_translator import GoogleTranslator

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def extract_product_data(url):
    """
    Extrae automáticamente Código, Referencia, Nomenclatura (ES/SK) e Importe unitario (con IVA)
    de cualquier URL de producto en Eslovaquia.
    """
    clean_url = (url or '').strip()
    if not clean_url:
        return {"error": "La URL ingresada está vacía"}

    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed_domain = urlparse(clean_url).netloc.lower().replace("www.", "")
    codigo = parsed_domain.split('.')[0].lower()

    try:
        r = requests.get(clean_url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return {"error": f"No se pudo acceder a la página del producto (Código HTTP {r.status_code})"}

        html_text = r.text
        soup = BeautifulSoup(html_text, 'html.parser')

        # 1. Extraer Título (Nombre en Eslovaco)
        title_sk = ""
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title_sk = og_title['content'].strip()
        else:
            h1 = soup.find('h1')
            if h1:
                title_sk = h1.get_text(strip=True)
            else:
                title_tag = soup.find('title')
                if title_tag:
                    title_sk = title_tag.get_text(strip=True)

        # Limpiar sufijos comunes en títulos (ej. " | Decathlon", " - OBI.sk")
        title_sk = re.sub(r'\s*[\|-]\s*(Decathlon|OBI|NAY|VERCAJCH|AUTOTECHNA|Smart|Stroje|Valtec).*$', '', title_sk, flags=re.IGNORECASE).strip()

        # 2. Traducir Título al Español
        title_es = title_sk
        if title_sk:
            try:
                translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
                if translated and len(translated.strip()) > 0:
                    title_es = translated.strip()
            except Exception as e:
                logging.warning(f"Error traduciendo título al español: {e}")

        nomenclatura = f"{title_es} / {title_sk}"

        # 3. Extraer Referencia / SKU / Código de Artículo
        referencia = "REF-N/A"
        
        # Estrategias por tienda / meta tags / expresiones regulares
        # Decathlon: "product-reference">8666242</span> o "modelId":"8666242"
        decathlon_ref = re.search(r'product-reference["\']?\s*>\s*(\d+)', html_text, re.IGNORECASE) or \
                        re.search(r'["\']modelId["\']\s*:\s*["\']?(\d+)', html_text) or \
                        re.search(r'data-reference\s*=\s*["\']?(\d+)', html_text)
        
        if "decathlon" in codigo and decathlon_ref:
            referencia = f"ID {decathlon_ref.group(1)}"
        else:
            # Meta tags de SKU o ID de producto
            sku_meta = soup.find('meta', property='product:retailer_item_id') or \
                       soup.find('meta', itemprop='sku') or \
                       soup.find('meta', name='sku')
            
            if sku_meta and sku_meta.get('content'):
                referencia = sku_meta['content'].strip()
            else:
                # Patrón en texto (ej. ID: 12345, Kód: 12345, Ref: 12345)
                code_match = re.search(r'(?:Kód|ID|Ref|Referencia|Číslo produktu|Art\.?\s*č\.?)\s*:?\s*([A-Z0-9\-_]{4,20})', html_text, re.IGNORECASE)
                if code_match:
                    referencia = code_match.group(1).strip()
                else:
                    # Intento por URL (ej. /p/4007875347502)
                    url_code = re.search(r'/p/(\d{6,})', clean_url) or re.search(r'-(\d{5,})\.html', clean_url)
                    if url_code:
                        referencia = f"ID {url_code.group(1)}"
                    else:
                        referencia = f"REF-{codigo.upper()}"

        # 4. Extraer Precio (con IVA en Euros)
        price_val = "N/A"
        price_meta = soup.find('meta', property='product:price:amount') or \
                     soup.find('meta', itemprop='price')
        
        if price_meta and price_meta.get('content'):
            price_val = price_meta['content'].strip()
        else:
            # Buscar patrones de precio en el HTML (ej: 35,95 €, 35.95 EUR)
            price_match = re.search(r'([\d\s\.,]+)\s*(?:€|EUR)', html_text)
            if price_match:
                price_val = price_match.group(1).strip()

        # Formatear precio con coma europea (ej. 35,95)
        price_clean = price_val.replace(" ", "").replace("€", "").replace("EUR", "").strip()
        price_formatted = price_clean.replace(".", ",")

        # Formato final listo para copiar y pegar
        formatted_result = f"""Codigo:  {codigo}
Referencia: {referencia}
Nomenclatura: {nomenclatura}
Importe unitario (con iva): {price_formatted}"""

        return {
            "codigo": codigo,
            "referencia": referencia,
            "nomenclatura": nomenclatura,
            "title_es": title_es,
            "title_sk": title_sk,
            "importe_unitario": price_formatted,
            "formatted_text": formatted_result,
            "url": clean_url
        }

    except Exception as e:
        logging.error(f"Error extrayendo datos de producto ({clean_url}): {e}")
        return {"error": f"Ocurrió un error al procesar la página del producto: {str(e)}"}
