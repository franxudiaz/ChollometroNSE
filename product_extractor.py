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

RESERVED_JS_WORDS = {"fetch", "method", "function", "script", "header", "stylesheet", "content", "gtm", "null", "undefined", "true", "false", "produkt", "produktu", "nohavice", "klavesnica", "notebook", "edition", "sivy", "cierna", "com"}

def extract_sku_from_text_or_url(clean_url, html_text, codigo, title_sk=""):
    """
    Extrae la referencia/SKU exacta del fabricante (priorizando Interný kód, product-reference, kód: , Kód produktu, Katalógové číslo, Obj.číslo, Objednávací kód, Código de pedido, item_id, codes).
    """
    parsed = urlparse(clean_url)
    
    # 1. Prioridad Absoluta HTML: Interný kód, PrestaShop product-reference, kód: , PrestaShop "reference", Kód produktu, Kód, Katalógové číslo, Obj.číslo, Objednávací kód
    if html_text:
        # Autotechna / E-Commerce Interný kód: MOL13300126, NEO11-102
        m_int_code = re.search(r'Intern[yý]\s*k[oó]d\s*:?\s*(?:<[^>]+>\s*)*([A-Z0-9\-_]{3,30})', html_text, re.IGNORECASE)
        if m_int_code:
            val = m_int_code.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS:
                return val

        # PrestaShop product-reference (ej: Truckershop <div class="product-reference"><label class="label">Kód </label><span>04729</span></div>)
        m_ps_class = re.search(r'class=["\']product-reference["\'][^>]*>\s*<label[^>]*>[^<]*</label>\s*<span>([^<]+)</span>', html_text, re.IGNORECASE)
        if m_ps_class:
            val = m_ps_class.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS and len(val) >= 1:
                return val

        # Copper.sk / E-Commerce kód: 60551001
        m_kod_simple = re.search(r'k[oó]d\s*:\s*([A-Z0-9\-_]{3,25})', html_text, re.IGNORECASE)
        if m_kod_simple:
            val = m_kod_simple.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS:
                return val

        # PrestaShop / VKP Steel: "reference":"11FRIUL05030" o itemprop="gtin13"
        m_ps_ref = re.search(r'"reference"\s*:\s*"([^"]+)"', html_text) or \
                   re.search(r'itemprop=["\'](?:gtin13|sku)["\']\s+content=["\']([^"\']+)["\']', html_text)
        if m_ps_ref:
            val = m_ps_ref.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS and len(val) >= 1:
                return val

        m_prod_code = re.search(r'(?:Código de producto|Kód produktu|Kód výrobcu|Číslo produktu|Katal[oó]gov[eé]\s*č[íi]slo|Katal[oó]gov[eé]\s*č\.?|Obj\.?\s*č[íi]slo|Objedn[^\s]*\s*(?:k[oó]d|č[íi]slo|č\.?)|C[oó]digo de pedido|K[oó]d objedn[^\s]+|K[oó]d|C[oó]digo)\s*:?\s*(?:<[^>]+>\s*)*([A-Z0-9\s\._,\-]{1,40})', html_text, re.IGNORECASE)
        if m_prod_code:
            val = m_prod_code.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS and len(val) >= 1:
                return val

        # Shoptet / Smart.sk JS: "item_id" o "code"
        m_item_id = re.search(r'"item_id"\s*:\s*"([^"]+)"', html_text) or re.search(r'"code"\s*:\s*"([^"]+)"', html_text)
        if m_item_id:
            val = m_item_id.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS and len(val) >= 1:
                return val

    # 2. Prioridad: Código entre paréntesis en el título (ej: "(21NU002CCK)", "(920-013033)", "(580-AKOX)")
    if title_sk:
        m_paren = re.search(r'\(([A-Z0-9\-_]{5,15})\)', title_sk, re.IGNORECASE)
        if m_paren:
            val = m_paren.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS:
                return val

    # 3. Código en formato numérico/alfanumérico estándar en la URL
    # a) Part Number Logitech / Decathlon / Milwaukee / Valtec / VKP (ej: 4932478654, 920-013033, 920-011590, 306560-136504)
    m_num_sku = re.search(r'(\d{3,6}-\d{5,8})', clean_url)
    if m_num_sku:
        return m_num_sku.group(1).upper()

    # b) Código Lenovo / HP / Asus / Dell / Valtec en la URL
    m_part_url = re.search(r'-([a-z0-9]{8,14})(?:-[a-z]+|/|\.html|#|$)', clean_url, re.IGNORECASE) or \
                 re.search(r'-(\d{2}[a-z0-9]{6,10})-', clean_url, re.IGNORECASE)
    if m_part_url:
        val = m_part_url.group(1).upper()
        if val.lower() not in RESERVED_JS_WORDS and re.search(r'\d', val) and re.search(r'[A-Z]', val):
            return val

    # 4. Fragmento Hash (#3679)
    if parsed.fragment and re.search(r'\d{3,}', parsed.fragment):
        m = re.search(r'(\d{3,})', parsed.fragment)
        return f"ID {m.group(1)}"

    # 5. Segmentos del path de la URL
    path = parsed.path.strip('/')
    parts = path.split('/')
    for p in reversed(parts):
        m1 = re.search(r'(\d{3,6}-[A-Za-z0-9]{3,8})', p)
        if m1 and m1.group(1).lower() not in RESERVED_JS_WORDS:
            return m1.group(1).upper()
            
        m2 = re.search(r'-(\d{5,12})(?:-|\.html|#|$)', p) or re.search(r'/p/(\d{5,12})', clean_url) or re.search(r'(\d{4,12})', p)
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
    codigo = "agharta" if "agharta" in domain_clean else ("vkpsteel" if "vkpsteel" in domain_clean else (domain_clean.split('.')[0].lower() or "tienda"))

    req_headers = HEADERS.copy()
    req_headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        r = requests.get(clean_url, headers=req_headers, timeout=8, verify=False)
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

        # Limpiar kód: 60551001 y marcas comerciales del título
        title_sk = re.sub(r'k[oó]d\s*:?\s*[A-Z0-9]+', '', title_sk, flags=re.IGNORECASE).strip()
        title_sk = re.sub(r'\s*([\|:-]|::)\s*(Decathlon|NAY|OBI|VERCAJCH|AUTOTECHNA|Smart|Stroje|Valtec|Outland|Creative|Agharta|Hyriak|VKP STEEL|COPPER|HAGARD|TRUCKERSHOP).*$', '', title_sk, flags=re.IGNORECASE).strip()

        # -------------------------------------------------------------
        # 2. REFERENCIA / SKU / CÓDIGO DE FABRICANTE O PEDIDO
        # -------------------------------------------------------------
        referencia = extract_sku_from_text_or_url(clean_url, html_text, codigo, title_sk)

        # Si la referencia está dentro del título, limpiarla para no duplicarla
        if referencia and referencia in title_sk:
            title_sk = title_sk.replace(f"({referencia})", "").replace(f"/{referencia}/", "").replace(referencia, '').strip(' -()/:')

        title_sk = re.sub(r'/[0-9A-Z\-_]+/?$', '', title_sk, flags=re.IGNORECASE).strip(' -()/:')

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

        title_es = title_es.strip(' -()/:')
        title_sk = title_sk.strip(' -()/:')
        nomenclatura = f"{title_es} / {title_sk}"

        # -------------------------------------------------------------
        # 4. IMPORTE UNITARIO (CON IVA EN EUROS)
        # -------------------------------------------------------------
        price_formatted = ""

        # Verificar si la tienda exige registro previo para mostrar el precio (ej: Hagard HAL: "Cena sa zobrazí až po prihlásení")
        if re.search(r'zobraz[ií]\s*až\s*po\s*prihl[aá]sen[ií]', html_text, re.IGNORECASE):
            price_formatted = "Necesario registro para ver precio"
        elif "gufero" in domain_clean or "gufero.sk" in clean_url:
            price_formatted = "Venta bajo catálogo (sin precios públicos)"

        # a) Elemento priceValue (ej: Autotechna <span class='priceValue'>78,24</span>)
        if not price_formatted:
            pv = soup.find(class_='priceValue')
            if pv:
                try:
                    p_txt = pv.get_text(strip=True).replace('€', '').replace(' ', '').replace(',', '.').strip()
                    val = float(p_txt)
                    if val > 0:
                        price_formatted = f"{val:.2f}".replace('.', ',')
                except Exception:
                    pass

        # b) E-Commerce WooCommerce (ej: Vercajch) -> Contenedor p.price -> primer woocommerce-Price-amount
        if not price_formatted:
            price_p = soup.find('p', class_='price')
            if price_p:
                for wo_tax in price_p.find_all(class_='content-product-price-wo-tax'):
                    wo_tax.decompose()
                amt_span = price_p.find(class_='woocommerce-Price-amount')
                if amt_span:
                    try:
                        p_txt = amt_span.get_text().replace('€', '').replace(' ', '').replace(',', '.').strip()
                        val = float(p_txt)
                        if val > 0:
                            price_formatted = f"{val:.2f}".replace('.', ',')
                    except Exception:
                        pass

        # c) Buscar 'Cena s DPH' / 'Precio con IVA' / 's DPH' / 'Con IVA' (soporta €38,28 o 14.60€ s DPH)
        if not price_formatted:
            price_match = re.search(r'(?:Cena\s*s\s*DPH|Precio\s*con\s*IVA)\s*:?\s*(?:<[^>]+>\s*)*€?\s*([\d\s\.,]+)\s*(?:€|EUR)?', html_text, re.IGNORECASE) or \
                          re.search(r'([\d\s]+[\.,]\d{2})\s*(?:&nbsp;)?\s*€\s*(?:s\s*DPH|Con\s*IVA)', html_text, re.IGNORECASE)
            
            if price_match:
                try:
                    val = float(price_match.group(1).strip().replace(" ", "").replace(',', '.'))
                    if val > 0:
                        price_formatted = f"{val:.2f}".replace('.', ',')
                except Exception:
                    pass

        # d) Meta tag explicit itemprop="price" / product:price:amount
        if not price_formatted:
            price_meta = soup.find('meta', attrs={'itemprop': 'price'}) or \
                         soup.find('meta', property='product:price:amount') or \
                         soup.find('meta', attrs={'name': 'price'}) or \
                         soup.find('meta', property='og:price:amount')
            
            if price_meta and price_meta.get('content'):
                try:
                    val = float(price_meta['content'].strip().replace(',', '.'))
                    if val > 0:
                        price_formatted = f"{val:.2f}".replace('.', ',')
                except Exception:
                    pass

        # e) JSON-LD (Schema.org)
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
                                    val = float(str(p_num).replace(',', '.'))
                                    if val > 0:
                                        price_formatted = f"{val:.2f}".replace('.', ',')
                                        break
                    except Exception:
                        pass

        # f) Buscar elementos de precio en HTML excluyendo elementos tachados
        if not price_formatted:
            for old in soup.find_all(['del', 's', 'strike'], class_=re.compile(r'old|original|crossed|strikethrough', re.I)):
                old.decompose()

            found_prices = []
            for p_match in re.finditer(r'€?\s*([\d\s]+[\.,]\d{2})\s*(?:&nbsp;)?\s*(?:€|EUR)?\s*(?:s\s*DPH|Con\s*IVA)?', html_text, re.IGNORECASE):
                try:
                    p_clean = p_match.group(1).replace('&nbsp;', '').replace(' ', '').replace(',', '.')
                    val = float(p_clean)
                    if 0.01 <= val <= 50000:
                        found_prices.append(val)
                except Exception:
                    pass

            if found_prices:
                max_price = max(found_prices)
                price_formatted = f"{max_price:.2f}".replace('.', ',')

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

    referencia = extract_sku_from_text_or_url(url, "", codigo, "")
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
