import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
from deep_translator import GoogleTranslator

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'sk-SK,sk;q=0.9,es-ES;q=0.8,es;q=0.7,en-US;q=0.6,en;q=0.5',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}

RESERVED_JS_WORDS = {"fetch", "method", "function", "script", "header", "stylesheet", "content", "gtm", "null", "undefined", "true", "false", "produkt", "produktu", "nohavice", "klavesnica"}

def extract_sku_from_text_or_url(clean_url, html_text, codigo):
    """
    Extrae con máxima precisión la referencia/SKU real del producto (priorizando códigos del fabricante como 920-013033, 920-011590, 580-AKOX, 306560-136504).
    """
    parsed = urlparse(clean_url)
    
    # 1. Prioridad Absoluta: Formato SKU numérico de fabricante (ej: 920-013033, 920-011590, 306560-136504, 580-AKOX) en URL
    m_num_sku = re.search(r'(\d{3,6}-\d{5,8})', clean_url)
    if m_num_sku:
        return m_num_sku.group(1).upper()

    # 2. Fragmento Hash (#3679)
    if parsed.fragment and re.search(r'\d{3,}', parsed.fragment):
        m = re.search(r'(\d{3,})', parsed.fragment)
        return f"ID {m.group(1)}"
        
    path = parsed.path.strip('/')
    parts = path.split('/')
    
    # 3. Buscar en el HTML por metadatos o texto explícito (Kód výrobcu / Code / SKU)
    if html_text:
        # p.ej: Kód výrobcu: 920-013033 o Part Number / MPN
        mpn_match = re.search(r'(?:Kód výrobcu|Kód|Part Number|MPN|SKU|Art\.?\s*č\.?)\s*:?\s*</?[^>]+>\s*([A-Z0-9\-_]{4,20})', html_text, re.IGNORECASE) or \
                    re.search(r'(?:Kód výrobcu|Kód|Part Number|MPN|SKU|Art\.?\s*č\.?)\s*:?\s*([A-Z0-9\-_]{4,20})', html_text, re.IGNORECASE)
        if mpn_match:
            code_val = mpn_match.group(1).strip()
            if code_val.lower() not in RESERVED_JS_WORDS and len(code_val) >= 4:
                return code_val.upper()

    # 4. Buscar códigos numéricos o alfanuméricos en el path de la URL
    for p in reversed(parts):
        # Alfanumérico tipo 580-AKOX
        m1 = re.search(r'(\d{3,6}-[A-Za-z0-9]{3,8})', p)
        if m1 and m1.group(1).lower() not in RESERVED_JS_WORDS:
            return m1.group(1).upper()
            
        # Código numérico directo largo (ej: 4932492462, 4007875, 8666242)
        m2 = re.search(r'-(\d{5,12})(?:-|\.html|#|$)', p) or re.search(r'/p/(\d{5,12})', clean_url) or re.search(r'(\d{6,12})', p)
        if m2:
            code = m2.group(1)
            return f"ID {code}" if len(code) < 8 else code

    return f"REF-{codigo.upper()}"

def extract_product_data(url):
    """
    Motor avanzado para extraer Código, Referencia, Nomenclatura (ES/SK) e Importe (con IVA)
    de cualquier e-commerce en Eslovaquia.
    """
    clean_url = (url or '').strip()
    if not clean_url:
        return {"error": "La URL ingresada está vacía."}

    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed = urlparse(clean_url)
    domain_clean = parsed.netloc.lower().replace("www.", "")
    codigo = domain_clean.split('.')[0].lower() or "tienda"

    # Preparar cabeceras con Referer dinámico del propio dominio
    req_headers = HEADERS.copy()
    req_headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        r = requests.get(clean_url, headers=req_headers, timeout=8)
        if r.status_code != 200:
            logging.warning(f"Respuesta HTTP {r.status_code} al acceder a {clean_url}")
            return generate_fallback_result(clean_url, codigo, f"Producto en {codigo.capitalize()}")

        html_text = r.text
        soup = BeautifulSoup(html_text, 'html.parser')

        # -------------------------------------------------------------
        # 1. TÍTULO EN ESLOVACO (Title SK)
        # -------------------------------------------------------------
        title_sk = ""
        try:
            h1 = soup.find('h1')
            if h1:
                title_sk = h1.get_text(strip=True)
            else:
                og_title = soup.find('meta', property='og:title')
                if og_title and og_title.get('content'):
                    title_sk = og_title['content'].strip()
                else:
                    title_tag = soup.find('title')
                    if title_tag:
                        title_sk = title_tag.get_text(strip=True)
        except Exception:
            pass

        if not title_sk:
            path_parts = parsed.path.strip('/').split('/')
            title_sk = path_parts[-1].replace('-', ' ').replace('.html', '').capitalize() if path_parts else "Producto"

        # Limpiar marcas comerciales en el título
        title_sk = re.sub(r'\s*([\|:-]|::)\s*(Decathlon|NAY|OBI|VERCAJCH|AUTOTECHNA|Smart|Stroje|Valtec|Outland|Creative).*$', '', title_sk, flags=re.IGNORECASE).strip()

        # -------------------------------------------------------------
        # 2. REFERENCIA / SKU / CÓDIGO DE FABRICANTE
        # -------------------------------------------------------------
        referencia = extract_sku_from_text_or_url(clean_url, html_text, codigo)

        # Si la referencia está dentro del título, limpiarla para no duplicarla
        if referencia and referencia in title_sk:
            clean_title_sk = title_sk.replace(f"({referencia})", "").replace(referencia, '').strip(' -()')
            if len(clean_title_sk) > 3:
                title_sk = clean_title_sk

        # -------------------------------------------------------------
        # 3. TRADUCCIÓN AL ESPAÑOL (Title ES)
        # -------------------------------------------------------------
        title_es = title_sk
        if title_sk:
            try:
                translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
                if translated and len(translated.strip()) > 0:
                    title_es = translated.strip()
            except Exception:
                pass

        nomenclatura = f"{title_es} / {title_sk}"

        # -------------------------------------------------------------
        # 4. IMPORTE UNITARIO (CON IVA EN EUROS)
        # -------------------------------------------------------------
        price_formatted = ""
        
        # a) Buscar 'Cena s DPH' contemplando etiquetas HTML intermedias (ej. NAY: <span class="sr-only">Cena s DPH: </span> 109,90 €)
        price_match = re.search(r'Cena\s*(?:s\s*DPH)?\s*:?\s*(?:<[^>]+>\s*)*([\d\s\.,]+)\s*(?:€|EUR)', html_text, re.IGNORECASE)
        if price_match:
            p_val = price_match.group(1).strip().replace(" ", "")
            price_formatted = p_val.replace('.', ',')

        # b) Buscar en JSON-LD (Schema.org)
        if not price_formatted:
            for s in soup.find_all('script', type='application/ld+json'):
                if s.string:
                    try:
                        js_data = json.loads(s.string)
                        if isinstance(js_data, dict):
                            offers = js_data.get('offers', {})
                            if isinstance(offers, list) and len(offers) > 0:
                                offers = offers[0]
                            if isinstance(offers, dict):
                                p_num = offers.get('price') or offers.get('lowPrice')
                                if p_num:
                                    price_formatted = str(p_num).replace('.', ',')
                                    break
                    except Exception:
                        pass

        # c) Buscar en Meta Tags
        if not price_formatted:
            price_meta = soup.find('meta', property='product:price:amount') or \
                         soup.find('meta', attrs={'itemprop': 'price'}) or \
                         soup.find('meta', attrs={'name': 'price'}) or \
                         soup.find('meta', property='og:price:amount')
            
            if price_meta and price_meta.get('content'):
                p_val = price_meta['content'].strip()
                price_formatted = p_val.replace('.', ',')

        # d) Buscar por clases CSS de precio
        if not price_formatted:
            price_match_css = re.search(r'class=["\'][^"\']*(?:price-finally|price|cena|dph|amount)[^"\']*["\'][^>]*>\s*([\d\s\.,]+)\s*(?:€|EUR)', html_text, re.IGNORECASE) or \
                              re.search(r'([\d\s\.,]{2,8})\s*(?:€|EUR)\s*(?:s\s*DPH)?', html_text, re.IGNORECASE)
            
            if price_match_css:
                p_val = price_match_css.group(1).strip().replace(" ", "")
                price_formatted = p_val.replace('.', ',')

        if not price_formatted:
            price_formatted = "Consultar en tienda online (€)"

        # Formato final exacto solicitado por el usuario
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
        return generate_fallback_result(clean_url, codigo, "Producto")

def generate_fallback_result(url, codigo, default_title):
    """
    Extractor inteligente desde la estructura de la URL si la web bloquea peticiones de servidor.
    """
    parsed = urlparse(url)
    slug = unquote(parsed.path.strip('/').split('/')[-1]).replace('.html', '')

    referencia = extract_sku_from_text_or_url(url, "", codigo)
    if referencia and "REF-" not in referencia:
        slug = slug.replace(referencia.replace("ID ", ""), "").strip('-')

    title_sk = slug.replace('-', ' ').strip().capitalize()
    if not title_sk or len(title_sk) < 3:
        title_sk = default_title

    title_es = title_sk
    try:
        translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
        if translated:
            title_es = translated.strip()
    except Exception:
        pass

    formatted_text = f"""Codigo:  {codigo}
Referencia: {referencia}
Nomenclatura: {title_es} / {title_sk}
Importe unitario (con iva): Consultar en tienda online (€)"""

    return {
        "codigo": codigo,
        "referencia": referencia,
        "nomenclatura": f"{title_es} / {title_sk}",
        "title_es": title_es,
        "title_sk": title_sk,
        "importe_unitario": "Consultar en tienda online (€)",
        "formatted_text": formatted_text,
        "url": url
    }
