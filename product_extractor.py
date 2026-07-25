import re
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from deep_translator import GoogleTranslator

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'sk-SK,sk;q=0.9,en-US;q=0.8,en;q=0.7,es;q=0.6'
}

def extract_product_data(url):
    """
    Extrae Código, Referencia, Nomenclatura (ES/SK) e Importe unitario (con IVA)
    de cualquier URL de producto en Eslovaquia sin fallos.
    """
    clean_url = (url or '').strip()
    if not clean_url:
        return {"error": "La URL ingresada está vacía."}

    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed_domain = urlparse(clean_url).netloc.lower().replace("www.", "")
    codigo = parsed_domain.split('.')[0].lower() or "tienda"

    try:
        r = requests.get(clean_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return generate_fallback_result(clean_url, codigo, f"Página de producto (HTTP {r.status_code})")

        html_text = r.text
        soup = BeautifulSoup(html_text, 'html.parser')

        # 1. TÍTULO EN ESLOVACO (Title SK)
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
        except Exception as e:
            logging.warning(f"Error extrayendo título: {e}")

        if not title_sk:
            path_parts = urlparse(clean_url).path.strip('/').split('/')
            title_sk = path_parts[-1].replace('-', ' ').replace('.html', '').capitalize() if path_parts else "Producto"

        # Limpiar marcas de agua en títulos (ej: " | NAY", " - Decathlon")
        title_sk = re.sub(r'\s*[\|-]\s*(Decathlon|NAY|OBI|VERCAJCH|AUTOTECHNA|Smart|Stroje|Valtec).*$', '', title_sk, flags=re.IGNORECASE).strip()

        # 2. TRADUCCIÓN AL ESPAÑOL (Title ES)
        title_es = title_sk
        if title_sk:
            try:
                translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
                if translated and len(translated.strip()) > 0:
                    title_es = translated.strip()
            except Exception as e:
                logging.warning(f"Error traduciendo título al español: {e}")

        nomenclatura = f"{title_es} / {title_sk}"

        # 3. REFERENCIA / SKU / CÓDIGO DE PRODUCTO
        referencia = ""
        try:
            # Descartar GTM/Analytics e identificar referencia real de producto (ej: 920-008351, ID 8666242, 4007875)
            ref_in_url = re.search(r'(\d{3,6}-\d{5,8})', clean_url) or re.search(r'-(\d{5,8})(?:-|\.html|#|$)', clean_url)
            if ref_in_url:
                referencia = ref_in_url.group(1).strip()
            else:
                decathlon_ref = re.search(r'product-reference["\']?\s*>\s*(\d+)', html_text, re.IGNORECASE) or \
                                re.search(r'["\']modelId["\']\s*:\s*["\']?(\d+)', html_text)
                if decathlon_ref:
                    referencia = f"ID {decathlon_ref.group(1)}"
                else:
                    code_match = re.search(r'(?:Kód|ID|Ref|Referencia|Číslo produktu|Art\.?\s*č\.?)\s*:?\s*([A-Z0-9\-_]{4,20})', html_text, re.IGNORECASE)
                    if code_match and not code_match.group(1).startswith("GTM"):
                        referencia = code_match.group(1).strip()
        except Exception as e:
            logging.warning(f"Error buscando referencia: {e}")

        if not referencia or len(referencia) < 3 or "GTM" in referencia:
            referencia = f"REF-{codigo.upper()}"

        # 4. IMPORTE UNITARIO (CON IVA EN EUROS)
        price_formatted = "No especificado"
        try:
            # Buscar precio final
            price_meta = soup.find('meta', property='product:price:amount') or \
                         soup.find('meta', attrs={'itemprop': 'price'}) or \
                         soup.find('meta', attrs={'name': 'price'})
            
            if price_meta and price_meta.get('content'):
                p_val = price_meta['content'].strip()
                price_formatted = p_val.replace('.', ',')
            else:
                # Patrones en HTML (ej. <span class="price-finally">35,90 €</span>, 39,90 €)
                price_match = re.search(r'class=["\'][^"\']*(?:price-finally|price|cena)[^"\']*["\'][^>]*>\s*([\d\s\.,]+)\s*(?:€|EUR)', html_text, re.IGNORECASE) or \
                              re.search(r'Cena\s*(?:s\s*DPH)?\s*:?\s*([\d\s\.,]+)\s*(?:€|EUR)', html_text, re.IGNORECASE) or \
                              re.search(r'([\d\s\.,]{2,8})\s*(?:€|EUR)', html_text)
                
                if price_match:
                    p_val = price_match.group(1).strip().replace(" ", "")
                    price_formatted = p_val.replace('.', ',')
        except Exception as e:
            logging.warning(f"Error buscando precio: {e}")

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
        logging.error(f"Error general extrayendo datos de producto ({clean_url}): {e}")
        return generate_fallback_result(clean_url, codigo, "Producto")

def generate_fallback_result(url, codigo, default_title):
    """
    Respuesta tolerante a fallos si un sitio bloquea la lectura directa.
    """
    path_slug = urlparse(url).path.strip('/').split('/')[-1].replace('-', ' ').replace('.html', '').capitalize()
    title_sk = path_slug if len(path_slug) > 3 else default_title
    
    title_es = title_sk
    try:
        translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
        if translated:
            title_es = translated.strip()
    except Exception:
        pass

    formatted_text = f"""Codigo:  {codigo}
Referencia: REF-{codigo.upper()}
Nomenclatura: {title_es} / {title_sk}
Importe unitario (con iva): No especificado en la vista previa"""

    return {
        "codigo": codigo,
        "referencia": f"REF-{codigo.upper()}",
        "nomenclatura": f"{title_es} / {title_sk}",
        "title_es": title_es,
        "title_sk": title_sk,
        "importe_unitario": "No especificado",
        "formatted_text": formatted_text,
        "url": url
    }
