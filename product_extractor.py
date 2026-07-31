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

RESERVED_JS_WORDS = {"fetch", "method", "function", "script", "header", "stylesheet", "content", "gtm", "null", "undefined", "true", "false", "produkt", "produktu", "tovaru", "nohavice", "klavesnica", "notebook", "edition", "sivy", "cierna", "com"}

def extract_product_type_fallback(title_sk):
    """
    Si un producto no tiene referencia/SKU explícito del fabricante,
    extrae el tipo de producto o sustantivo principal en eslovaco desde el título
    (ej: "Blok Artistico..." -> "Blok", "Akrylová fixa Liquitex" -> "Akrylová fixa", "Obuv..." -> "Obuv").
    """
    if not title_sk or title_sk.lower() in ["producto", "product", "náhradný diel"]:
        return "Produkt"
        
    clean_title = re.sub(r'^[^\w\s]+', '', title_sk).strip()
    words = clean_title.split()
    if not words:
        return "Produkt"

    first_w = words[0].capitalize()
    if len(words) >= 2 and (first_w.endswith(('á', 'é', 'ý', 'í', 'ové', 'ová', 'ný', 'ná', 'né')) or len(first_w) <= 3):
        return f"{words[0].capitalize()} {words[1].lower()}".capitalize()
    
    return first_w

def extract_sku_from_text_or_url(clean_url, html_text, codigo, title_sk=""):
    """
    Extrae la referencia/SKU exacta del fabricante (priorizando IKEA XXX.XXX.XX, OBI /p/CODE, Kód tovaru, Kód produktu, Interný kód, product-reference, kód: , Katalógové číslo, Obj.číslo, Objednávací kód, Código de pedido, item_id, codes).
    """
    parsed = urlparse(clean_url)
    
    # 0a. Prioridad Específica IKEA: Formato XXX.XXX.XX (ej: 603.127.15, 895.010.65, 404.887.96)
    if "ikea" in clean_url or "ikea" in codigo:
        if html_text:
            m_ikea_txt = re.search(r'\b(\d{3}\.\d{3}\.\d{2})\b', html_text)
            if m_ikea_txt:
                return m_ikea_txt.group(1)
        m_ikea_url = re.search(r'-s?(\d{8})(?:/|\?|#|$)', clean_url)
        if m_ikea_url:
            n = m_ikea_url.group(1)
            return f"{n[0:3]}.{n[3:6]}.{n[6:8]}"

    # 0a2. Prioridad Específica METRO Eslovaquia: BTY-X483155 -> 483155
    if "metro" in clean_url or "metro" in codigo:
        m_metro_sku = re.search(r'BTY-X(\d+)', clean_url, re.IGNORECASE)
        if m_metro_sku:
            return m_metro_sku.group(1)

    # 0b. Prioridad Específica Decathlon: ID 9004900, ID 8734341
    if "decathlon" in clean_url or "decathlon" in codigo:
        if html_text:
            m_dec_ref = re.search(r'data-testid=["\']product-reference["\'][^>]*>\s*(\d{6,8})\s*<', html_text) or \
                        re.search(r'"modelId"\s*:\s*"(\d{6,8})"', html_text) or \
                        re.search(r'data-reference=?(\d{6,8})', html_text)
            if m_dec_ref:
                return f"ID {m_dec_ref.group(1)}"

    # 0b. Prioridad URL Directa Hybris / OBI / Hansa-Flex: /p/CODE (ej: /p/4866760, /p/2004083, /p/HKEPMS160C)
    m_p_path = re.search(r'/p/([A-Z0-9\-_]{3,30})(?:\?|#|$)', clean_url, re.IGNORECASE)
    if m_p_path:
        val = m_p_path.group(1).strip().upper()
        if val.lower() not in RESERVED_JS_WORDS:
            return val

    # 1. Prioridad Absoluta HTML: Outland variante hash, JYSK SKU, Kód tovaru, Kód produktu, Interný kód, PrestaShop product-reference, kód: , PrestaShop "reference", Kód, Katalógové číslo, Obj.číslo, Objednávací kód
    if html_text:
        # Outland variant option hash: #2026 -> AP7520006041SML
        if "#" in clean_url:
            opt_id = clean_url.split('#')[-1]
            if opt_id.isdigit():
                m_opt_code = re.search(r'"id"\s*:\s*"' + opt_id + r'"\s*,\s*"code"\s*:\s*"([^"]+)"', html_text)
                if m_opt_code:
                    return m_opt_code.group(1).strip().upper()

        # PROMO DESIGN SKU: P328.719, P463.813
        m_promodes_sku = re.search(r'\b([A-Z]{1,3}\d{3}\.\d{3})\b', html_text)
        if m_promodes_sku:
            return m_promodes_sku.group(1)

        # JYSK SKU: 6426073, 4912249
        m_jysk_sku = re.search(r'SKU:\s*(\d{7})', html_text, re.IGNORECASE) or re.search(r'"sku"\s*:\s*"(\d{7})"', html_text)
        if m_jysk_sku:
            return m_jysk_sku.group(1)

        # Xepap / OBI / E-Commerce Kód tovaru / Kód produktu / Kód výrobcu / Číslo výrobku: 511.2070.00, 4866760
        m_tovaru_code = re.search(r'(?:Número de producto|Číslo výrobku|Código de producto|Kód tovaru|Kód produktu|Kód výrobcu|Číslo produktu|Katal[oó]gov[eé]\s*č[íi]slo|Katal[oó]gov[eé]\s*č\.?|Obj\.?\s*č[íi]slo|Objedn[^\s]*\s*(?:k[oó]d|č[íi]slo|č\.?)|C[oó]digo de pedido|K[oó]d objedn[^\s]+)\s*:?\s*(?:<[^>]+>\s*)*([A-Z0-9\s\._,\-]{1,40})', html_text, re.IGNORECASE)
        if m_tovaru_code:
            val = m_tovaru_code.group(1).strip().upper()
            if val.lower() not in RESERVED_JS_WORDS and len(val) >= 1:
                return val

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

        # Copper.sk / E-Commerce / Stavivo IBV kód: 60551001, DMP180Z, DTD153Z
        m_kod_simple = re.search(r'k[oó]d\s*:\s*([A-Z0-9\-_]{3,25})', html_text, re.IGNORECASE) or \
                       re.search(r'>\s*K[oó]d\s*<\s*/[^>]+>\s*<\s*[^>]+>\s*([A-Z0-9\-_]{3,25})\s*<', html_text, re.IGNORECASE)
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
            
        m2 = re.search(r'/p/(\d{1,12})', clean_url) or re.search(r'-(\d{4,12})(?:-|\.html|#|$)', p) or re.search(r'(\d{4,12})', p)
        if m2:
            code = m2.group(1)
            return f"ID {code}"

    return None

def extract_product_data(url):
    """
    Motor avanzado para extraer Código, Referencia, Nomenclatura (ES/SK) e Importe (con IVA)
    de cualquier e-commerce en Eslovaquia.
    """
    clean_url = unquote((url or '').strip())
    if not clean_url:
        return {"error": "La URL ingresada está vacía."}

    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    parsed = urlparse(clean_url)
    domain_clean = parsed.netloc.lower().replace("www.", "")
    
    if "agharta" in domain_clean:
        codigo = "agharta"
    elif "vkpsteel" in domain_clean:
        codigo = "vkpsteel"
    elif "ibv" in domain_clean or "stavivo" in domain_clean:
        codigo = "stavivo"
    elif "hansa-flex" in domain_clean:
        codigo = "hansa-flex"
    elif "dk-ramovanie" in domain_clean:
        codigo = "dk-ramovanie"
    elif "metro" in domain_clean:
        codigo = "metro"
    else:
        codigo = domain_clean.split('.')[0].lower() or "tienda"

    req_headers = HEADERS.copy()
    req_headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        session = requests.Session()
        session.headers.update(req_headers)
        r = None
        try:
            r = session.get(clean_url, timeout=8)
        except Exception:
            try:
                r = session.get(clean_url, timeout=8, verify=False)
            except Exception:
                pass

        if not r or r.status_code != 200 or len(r.text) < 10000:
            logging.info(f"Petición directa falló ({r.status_code if r else 'Error'}). Intentando proxy de Google Translate para {clean_url}...")
            try:
                proxy_url = f"https://translate.google.com/translate?sl=sk&tl=es&u={clean_url}"
                r_proxy = session.get(proxy_url, timeout=10)
                if r_proxy.status_code == 200 and len(r_proxy.text) > 5000:
                    r = r_proxy
            except Exception as ex_p:
                logging.warning(f"Fallback proxy Google Translate falló: {ex_p}")

        if not r or r.status_code != 200:
            logging.warning(f"Respuesta HTTP {r.status_code if r else 'Sin respuesta'} al acceder a {clean_url}")
            return generate_fallback_result(clean_url, codigo, f"Producto en {codigo.capitalize()}")

        html_text = r.text
        soup = BeautifulSoup(html_text, 'html.parser')

        # -------------------------------------------------------------
        # 1. TÍTULO EN ESLOVACO (Title SK)
        # -------------------------------------------------------------
        title_sk = ""
        try:
            if "promodes" in domain_clean or "e-present" in domain_clean:
                h2_promodes = soup.find('h2')
                if h2_promodes:
                    title_sk = h2_promodes.get_text(separator=' ', strip=True)
                    title_sk = re.sub(r',\s*(?:Brown|Black|White|Red|Blue|Green|Yellow|Orange|Grey|Silver|Gold).*$', '', title_sk, flags=re.IGNORECASE).strip()
            
            if not title_sk:
                h1 = soup.find('h1')
                if h1 and len(h1.get_text(separator=' ', strip=True)) > 2:
                    title_sk = h1.get_text(separator=' ', strip=True)
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
        title_sk = re.sub(r'\s*([\|:-]|::)\s*(Decathlon|NAY|OBI|VERCAJCH|AUTOTECHNA|Smart|Stroje|Valtec|Outland|Creative|Agharta|Hyriak|VKP STEEL|COPPER|HAGARD|TRUCKERSHOP|HANSA-FLEX|STAVIVO IBV|STAVIVO|XEPAP|IKEA|JYSK|DK-Rámovanie|DK Rámovanie|DKRAMOVANIE).*$', '', title_sk, flags=re.IGNORECASE).strip()

        # Limpiar marca duplicada al inicio (ej: "VALTER Fotorámik VALTER...", "ALKEKONGE Stojan ALKEKONGE...")
        parts_t = title_sk.split(maxsplit=1)
        if len(parts_t) > 1 and parts_t[0].isupper() and len(parts_t[0]) >= 3 and parts_t[0] in parts_t[1]:
            title_sk = parts_t[1]

        # -------------------------------------------------------------
        # 2. REFERENCIA / SKU / CÓDIGO DE FABRICANTE O PEDIDO
        # -------------------------------------------------------------
        referencia = extract_sku_from_text_or_url(clean_url, html_text, codigo, title_sk)
        is_fallback_ref = False
        if not referencia or referencia.startswith("REF-"):
            referencia = extract_product_type_fallback(title_sk)
            is_fallback_ref = True

        # Si la referencia es un código explícito y está dentro del título, limpiarla para no duplicarla
        if referencia and not is_fallback_ref and referencia in title_sk:
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
        # -------------------------------------------------------------
        # 4. IMPORTE UNITARIO (CON IVA EN EUROS)
        # -------------------------------------------------------------
        price_formatted = ""

        # Verificar si la tienda exige registro previo (ej: METRO, Hagard HAL, Stavivo IBV: "Cena po prihlásení")
        if "metro" in domain_clean or "metro" in clean_url or "metro" in codigo or re.search(r'po\s*prihl[aá]sen[ií]', html_text, re.IGNORECASE) or re.search(r'zobraz[ií]\s*až\s*po\s*prihl[aá]sen[ií]', html_text, re.IGNORECASE):
            price_formatted = "Necesario registro para ver precio"
        elif any(k in domain_clean or k in clean_url for k in ["gufero", "stavebninydado", "hansa-flex", "tonerservis", "technopack", "faxacopy", "gatial"]):
            price_formatted = "Servicio / Lista de Precios / Contacto"

        # a) Opción seleccionada en desplegable (ej: DK Rámovanie 28,70 EUR / 3,40 EUR)
        if not price_formatted:
            opt_sel = soup.find('option', selected=True) or soup.find('option')
            if opt_sel:
                m_p_opt = re.search(r'([\d\s]+[\.,]\d{2})\s*(?:EUR|€)', opt_sel.get_text())
                if m_p_opt:
                    try:
                        val = float(m_p_opt.group(1).replace('&nbsp;', '').replace(' ', '').replace(',', '.'))
                        if val > 0:
                            price_formatted = f"{val:.2f}".replace('.', ',')
                    except Exception:
                        pass

        # a) PROMO DESIGN Price sin IVA (ej: 19,67 (SIN IVA), 2,89 (SIN IVA))
        if not price_formatted and ("promodes" in domain_clean or "e-present" in domain_clean or "promodes" in codigo):
            for tr in soup.find_all('tr'):
                txt_tr = tr.get_text(separator=' | ', strip=True)
                if re.search(r'\b[A-Z]{1,3}\d{3}\.\d{3}\b', txt_tr):
                    eur_matches = re.findall(r'([\d\s]+[\.,]\d{2})\s*EUR', txt_tr)
                    if eur_matches:
                        active_val = eur_matches[-1].replace(' ', '').replace('.', ',')
                        price_formatted = f"{active_val} (SIN IVA)"
                        break

        # a) Regla Específica OBI (ej: 24,99 EUR*, 4,29 EUR*, 299,99 EUR*)
        if not price_formatted and ("obi" in domain_clean or "obi" in clean_url or "obi" in codigo):
            soup_obi = BeautifulSoup(html_text, 'html.parser')
            for tag in soup_obi.find_all(['script', 'style', 'del', 's', 'strike']):
                tag.decompose()
            for p_match in re.finditer(r'([\d\s]+[\.,]\d{2})\s*EUR\*', soup_obi.get_text()):
                try:
                    val = float(p_match.group(1).replace('&nbsp;', '').replace(' ', '').replace(',', '.'))
                    if 0.01 <= val <= 50000:
                        price_formatted = f"{val:.2f}".replace('.', ',')
                        break
                except Exception:
                    pass

        # b) Buscar contenedor .price específico que contenga "s DPH" (ej: Xepap <p class="price">66,43 € s DPH</p>)
        if not price_formatted:
            for p_el in soup.find_all(['p', 'div', 'span'], class_='price'):
                if 's dph' in p_el.get_text().lower() or 'con iva' in p_el.get_text().lower():
                    m_val = re.search(r'([\d\s]+[\.,]\d{2})', p_el.get_text())
                    if m_val:
                        try:
                            val = float(m_val.group(1).replace('&nbsp;', '').replace(' ', '').replace(',', '.'))
                            if val > 0:
                                price_formatted = f"{val:.2f}".replace('.', ',')
                                break
                        except Exception:
                            pass

        # c) Elemento priceValue (ej: Autotechna <span class='priceValue'>78,24</span>)
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

        # d) E-Commerce WooCommerce (ej: Vercajch, Scandi) -> Contenedor p.price -> primer woocommerce-Price-amount activo
        if not price_formatted:
            price_p = soup.find('p', class_='price')
            if price_p:
                for d in price_p.find_all(['del', 'small', 's', 'strike']):
                    d.decompose()
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

        # e) Buscar 'Cena s DPH' / 'Precio con IVA' / 's DPH' / 'Con IVA' (soporta €38,28 o 14.60€ s DPH)
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

        # f) Meta tag explicit itemprop="price" / product:price:amount
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

        # g) JSON-LD (Schema.org)
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

        # h) Buscar elementos de precio en HTML excluyendo elementos tachados
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
            price_formatted = "Servicio / Lista de Precios / Contacto"

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
    clean_url = unquote(url or '')
    parsed = urlparse(clean_url)
    path_parts = [p for p in parsed.path.strip('/').split('/') if p and p.lower() not in ['p', 'product', 'detail', 'shop', 'pv', 'kategoria', 'sk', 'cz']]
    
    slug = ""
    if path_parts:
        if path_parts[-1].isdigit() and len(path_parts) > 1:
            slug = path_parts[-2].replace('.html', '')
        else:
            slug = path_parts[-1].replace('.html', '')
            
    referencia = extract_sku_from_text_or_url(clean_url, "", codigo, "")
    is_fallback_ref = False
    if not referencia or referencia.startswith("REF-"):
        referencia = extract_product_type_fallback(slug.replace('-', ' '))
        is_fallback_ref = True

    if referencia and not is_fallback_ref and referencia in slug:
        slug = slug.replace(referencia.replace("ID ", ""), "").strip('-')

    title_sk = slug.replace('-', ' ').strip().capitalize()
    if not title_sk or len(title_sk) < 3 or title_sk.isdigit():
        title_sk = default_title

    title_es = title_sk
    try:
        translated = GoogleTranslator(source='sk', target='es').translate(title_sk)
        if translated:
            title_es = translated.strip()
    except Exception:
        pass

    fallback_price = "Servicio / Lista de Precios / Contacto"
    if "metro" in clean_url or "metro" in codigo:
        fallback_price = "Necesario registro para ver precio"

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
