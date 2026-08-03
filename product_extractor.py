import re
import json
import logging
import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
from deep_translator import GoogleTranslator

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

RESERVED_WORDS = {
    "fetch", "method", "function", "script", "header", "stylesheet", "content", "gtm",
    "null", "undefined", "true", "false", "produkt", "produktu", "tovaru", "nohavice",
    "klavesnica", "notebook", "edition", "sivy", "cierna", "com", "sandisk", "logitech",
    "makita", "bosch", "dewalt", "lenovo", "apple", "samsung", "asus", "acer"
}

def extract_sku_from_soup_or_text(soup, html_text, clean_url, title_sk=""):
    """
    Extracción universal de SKU / Referencia / Part Number / Kód tovaru usando
    estándares HTML (Meta, JSON-LD, Microdata, patrones de texto y URL).
    """
    # 1. Metadatos Estándar (Meta Tags)
    meta_sku = (
        soup.find('meta', attrs={'itemprop': 'sku'}) or
        soup.find('meta', property='product:retailer_item_id') or
        soup.find('meta', attrs={'name': 'sku'}) or
        soup.find('meta', attrs={'name': 'code'}) or
        soup.find('meta', attrs={'name': 'product_code'}) or
        soup.find('meta', property='og:sku')
    )
    if meta_sku and meta_sku.get('content'):
        val = meta_sku['content'].strip().upper()
        if val and val.lower() not in RESERVED_WORDS and len(val) >= 2:
            return val

    # 2. JSON-LD (Schema.org / Product / Offer)
    for s in soup.find_all('script', type='application/ld+json'):
        if s.string:
            try:
                data = json.loads(s.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict):
                        if '@graph' in item and isinstance(item['@graph'], list):
                            items.extend(item['@graph'])
                        for key in ['sku', 'mpn', 'gtin13', 'gtin8', 'gtin', 'code', 'productID', 'model']:
                            val = item.get(key)
                            if val and isinstance(val, (str, int)):
                                s_val = str(val).strip().upper()
                                if s_val and s_val.lower() not in RESERVED_WORDS and len(s_val) >= 2:
                                    return s_val
            except Exception:
                pass

    # 3. Shoptet, PrestaShop, WooCommerce y estructuras HTML comunes (Kód tovaru / Kód produktu / SKU / Ref)
    for label_str in ['Kód tovaru', 'Kód produktu', 'Kód výrobcu', 'Číslo výrobku', 'Kód', 'SKU:', 'Ref:']:
        for el in soup.find_all(text=re.compile(re.escape(label_str), re.IGNORECASE)):
            parent = el.parent
            if parent:
                full_txt = parent.get_text(separator=' ', strip=True)
                m = re.search(r'(?:Kód[^\:]*|SKU|Ref|Číslo[^\:]*)\s*:?\s*([A-Z0-9\-_]{3,30})', full_txt, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip().upper()
                    if candidate.lower() not in RESERVED_WORDS and (not candidate.isdigit() or len(candidate) >= 4):
                        return candidate
                next_el = parent.find_next_sibling()
                if next_el:
                    s_txt = next_el.get_text(strip=True).upper()
                    if s_txt and len(s_txt) >= 3 and s_txt.lower() not in RESERVED_WORDS:
                        m_sub = re.search(r'([A-Z0-9\-_]{3,30})', s_txt)
                        if m_sub:
                            return m_sub.group(1).strip().upper()

    # 4. Regex directa sobre el HTML raw para Kód tovaru / PrestaShop / Shoptet item_id / code
    m_raw_code = (
        re.search(r'"item_id"\s*:\s*"([^"]+)"', html_text) or
        re.search(r'"code"\s*:\s*"([A-Z0-9\-_]{3,30})"', html_text, re.IGNORECASE) or
        re.search(r'"reference"\s*:\s*"([A-Z0-9\-_]{3,30})"', html_text, re.IGNORECASE) or
        re.search(r'data-product-code=["\']([^"\']+)["\']', html_text, re.IGNORECASE) or
        re.search(r'data-sku=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    )
    if m_raw_code:
        val = m_raw_code.group(1).strip().upper()
        if val.lower() not in RESERVED_WORDS and len(val) >= 2:
            return val

    # 5. SKU entre paréntesis en el título (ej: "(SDDDC3-064G-G46)")
    if title_sk:
        m_paren = re.search(r'\(([A-Z0-9\-_]{5,25})\)', title_sk, re.IGNORECASE)
        if m_paren:
            val = m_paren.group(1).strip().upper()
            if val.lower() not in RESERVED_WORDS:
                return val

    # 6. SKU explícito dentro del slug o path de la URL (ej: "sandisk-...-sdddc3-064g-g46/")
    m_partnum = re.search(r'([A-Z0-9]{2,6}-[A-Z0-9]{3,8}(?:-[A-Z0-9]{2,8})?)', clean_url, re.IGNORECASE) or \
                re.search(r'([A-Z0-9]{2,6}-[A-Z0-9]{3,8}(?:-[A-Z0-9]{2,8})?)', title_sk, re.IGNORECASE)
    if m_partnum:
        val = m_partnum.group(1).strip().upper()
        if val.lower() not in RESERVED_WORDS and any(c.isdigit() for c in val):
            return val

    # Fallback: Tipo de producto o palabra principal si no hay SKU explícito
    clean_title = re.sub(r'^[^\w\s]+', '', title_sk).strip()
    words = clean_title.split()
    if words:
        first_w = words[0].capitalize()
        if len(words) >= 2 and (first_w.endswith(('á', 'é', 'ý', 'í', 'ové', 'ová', 'ný', 'ná', 'né')) or len(first_w) <= 3):
            return f"{words[0].capitalize()} {words[1].lower()}".capitalize()
        return first_w

    return "Produkt"

def extract_price_from_soup_or_text(soup, html_text, clean_url, domain_clean):
    """
    Extracción universal de Importe Unitario (con IVA) usando Meta Tags,
    JSON-LD, Microdatos HTML5, elementos CSS de precio y expresiones regulares.
    """
    if "metro" in domain_clean or "metro" in clean_url:
        return "Necesario registro para ver precio"

    found_prices = []

    # 1. Metadatos Estándar (Meta Tags)
    meta_price = (
        soup.find('meta', attrs={'itemprop': 'price'}) or
        soup.find('meta', property='product:price:amount') or
        soup.find('meta', property='og:price:amount') or
        soup.find('meta', attrs={'name': 'price'}) or
        soup.find('meta', attrs={'name': 'product:price:amount'})
    )
    if meta_price and meta_price.get('content'):
        try:
            val = float(str(meta_price['content']).strip().replace(',', '.'))
            if val > 0:
                return f"{val:.2f}".replace('.', ',')
        except Exception:
            pass

    # 2. JSON-LD (Schema.org / Product / Offer)
    for s in soup.find_all('script', type='application/ld+json'):
        if s.string:
            try:
                data = json.loads(s.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict):
                        if '@graph' in item and isinstance(item['@graph'], list):
                            items.extend(item['@graph'])
                        offers = item.get('offers')
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p_val = offers.get('price') or offers.get('lowPrice')
                            if p_val:
                                val = float(str(p_val).replace(',', '.'))
                                if val > 0:
                                    return f"{val:.2f}".replace('.', ',')
            except Exception:
                pass

    # 3. Elementos HTML de precio (PrestaShop, WooCommerce, Shoptet, etc.)
    soup_clean = BeautifulSoup(html_text, 'html.parser')
    for old_tag in soup_clean.find_all(['del', 's', 'strike'], class_=re.compile(r'old|povodna|crossed|strikethrough|was', re.I)):
        old_tag.decompose()

    price_selectors = [
        '.price', '.product-price', '.priceValue', '.current-price',
        '.price-box', '.amount', '.woocommerce-Price-amount',
        '[data-price]', '[data-product-price]', '[itemprop="price"]'
    ]
    for sel in price_selectors:
        for el in soup_clean.select(sel):
            txt = el.get_text(strip=True)
            m = re.search(r'([\d\s]+[\.,]\d{2})\s*(?:€|EUR)?', txt)
            if m:
                try:
                    val = float(m.group(1).replace('&nbsp;', '').replace(' ', '').replace(',', '.'))
                    if 0.01 <= val <= 100000:
                        found_prices.append(val)
                except Exception:
                    pass

    if found_prices:
        return f"{max(found_prices):.2f}".replace('.', ',')

    # 4. Regex sobre texto completo buscando patron NNN,NN € s DPH o €NN,NN
    raw_matches = re.findall(r'€?\s*([\d\s]+[\.,]\d{2})\s*(?:&nbsp;)?\s*(?:€|EUR)?\s*(?:s\s*DPH|Con\s*IVA)?', html_text, re.IGNORECASE)
    for p_str in raw_matches:
        try:
            val = float(p_str.replace('&nbsp;', '').replace(' ', '').replace(',', '.'))
            if 0.01 <= val <= 100000:
                found_prices.append(val)
        except Exception:
            pass

    if found_prices:
        return f"{max(found_prices):.2f}".replace('.', ',')

    if re.search(r'Cena\s+až\s+po\s+prihlášen[íi]', html_text, re.IGNORECASE):
        return "Necesario registro para ver precio"

    return "Servicio / Lista de Precios / Contacto"

def extract_product_data(url):
    """
    Motor universal avanzado para extraer Código, Referencia, Nomenclatura (ES/SK)
    e Importe (con IVA) de cualquier e-commerce.
    """
    clean_url = unquote((url or '').strip())
    if not clean_url:
        return {"error": "La URL ingresada está vacía."}

    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed = urlparse(clean_url)
    domain_clean = parsed.netloc.lower().replace("www.", "")
    codigo = domain_clean.split('.')[0].lower() or "tienda"

    req_headers = HEADERS.copy()
    req_headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        session = requests.Session()
        session.headers.update(req_headers)
        r = None
        try:
            r = session.get(clean_url, timeout=12)
        except Exception:
            try:
                r = session.get(clean_url, timeout=12, verify=False)
            except Exception:
                pass

        if not r or r.status_code != 200 or len(r.text) < 500:
            logging.info(f"Petición directa falló ({r.status_code if r else 'Error'}). Intentando proxy Google Translate...")
            try:
                proxy_url = f"https://translate.google.com/translate?sl=sk&tl=es&u={clean_url}"
                r_proxy = session.get(proxy_url, timeout=12)
                if r_proxy.status_code == 200 and len(r_proxy.text) > 3000:
                    r = r_proxy
            except Exception as ex_p:
                logging.warning(f"Fallback proxy Google Translate falló: {ex_p}")

        if not r or r.status_code != 200:
            return generate_fallback_result(clean_url, codigo, f"Producto en {codigo.capitalize()}")

        html_text = r.text
        soup = BeautifulSoup(html_text, 'html.parser')

        # 1. TÍTULO EN ESLOVACO
        title_sk = ""
        h1 = soup.find('h1')
        if h1 and len(h1.get_text(strip=True)) > 2:
            title_sk = h1.get_text(separator=' ', strip=True)
        else:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title_sk = og_title['content'].strip()
            else:
                title_tag = soup.find('title')
                if title_tag:
                    title_sk = title_tag.get_text(strip=True)

        if not title_sk:
            path_parts = [p for p in parsed.path.strip('/').split('/') if p]
            title_sk = path_parts[-1].replace('-', ' ').replace('.html', '').capitalize() if path_parts else "Producto"

        title_sk = re.sub(rf'\s*([\|:-]|::)\s*{re.escape(domain_clean)}.*$', '', title_sk, flags=re.IGNORECASE).strip()
        title_sk = re.sub(r'\s*([\|:-]|::)\s*(smart|obi|nay|decathlon|ikea|jysk|vercajch).*$', '', title_sk, flags=re.IGNORECASE).strip()

        # 2. REFERENCIA / SKU
        referencia = extract_sku_from_soup_or_text(soup, html_text, clean_url, title_sk)

        if referencia and len(referencia) > 3 and referencia in title_sk:
            title_sk = title_sk.replace(f"({referencia})", "").replace(referencia, '').strip(' -()/:')
            title_sk = re.sub(r'\s+', ' ', title_sk).strip()

        # 3. TRADUCCIÓN AL ESPAÑOL
        title_es = title_sk
        if title_sk:
            try:
                translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
                if translated and len(translated.strip()) > 0:
                    title_es = translated.strip()
            except Exception:
                pass

        title_es = title_es.strip(' -()/:')
        title_sk = title_sk.strip(' -()/:')
        nomenclatura = f"{title_es} / {title_sk}"

        # 4. IMPORTE UNITARIO
        price_formatted = extract_price_from_soup_or_text(soup, html_text, clean_url, domain_clean)

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
    clean_url = unquote(url or '')
    parsed = urlparse(clean_url)
    path_parts = [p for p in parsed.path.strip('/').split('/') if p and p.lower() not in ['p', 'product', 'detail', 'shop', 'pv', 'kategoria', 'sk', 'cz']]
    
    slug = path_parts[-1].replace('.html', '') if path_parts else ""

    m_partnum = re.search(r'([A-Z0-9]{2,6}-[A-Z0-9]{3,8}(?:-[A-Z0-9]{2,8})?)', clean_url, re.IGNORECASE)
    referencia = m_partnum.group(1).upper() if m_partnum else "REF-" + codigo.upper()

    title_sk = slug.replace('-', ' ').strip().capitalize() or default_title
    title_es = title_sk
    try:
        translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
        if translated:
            title_es = translated.strip()
    except Exception:
        pass

    fallback_price = "Necesario registro para ver precio" if "metro" in clean_url else "Servicio / Lista de Precios / Contacto"

    formatted_text = f"""Codigo:  {codigo}
Referencia: {referencia}
Nomenclatura: {title_es} / {title_sk}
Importe unitario (con iva): {fallback_price}"""

    return {
        "codigo": codigo,
        "referencia": referencia,
        "nomenclatura": f"{title_es} / {title_sk}",
        "title_es": title_es,
        "title_sk": title_sk,
        "importe_unitario": fallback_price,
        "formatted_text": formatted_text,
        "url": clean_url
    }
