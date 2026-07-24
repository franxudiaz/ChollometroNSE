import requests
import re
import json
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus, urlparse

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'sk-SK,sk;q=0.9,en;q=0.8'
}

# Diccionario ampliado de traducción español -> eslovaco
TRANSLATION_MAP = {
    "alicates": "kliešte",
    "alicate": "kliešte",
    "destornillador": "skrutkovač",
    "carraca": "račňa",
    "cinta": "páska",
    "aislante": "izolačná",
    "llave": "kľúč",
    "llaves": "kľúče",
    "martillo": "kladivo",
    "taladro": "vŕtačka",
    "sierra": "píla",
    "tornillo": "skrutka",
    "tornillos": "skrutky",
    "tuerca": "matica",
    "tuercas": "matice",
    "arandela": "podložka",
    "cable": "kábel",
    "cables": "káblov",
    "batería": "batéria",
    "baterias": "batérie",
    "disco": "kotúč",
    "lijadora": "brúska",
    "soldadura": "zváračka",
    "herramientas": "náradie",
    "herramienta": "náradie",
    "limpieza": "čistenie",
    "ropa": "oblečenie",
    "marcos": "rámy",
    "papelería": "papiernictvo",
    "guantes": "rukavice",
    "casco": "prilba",
    "bota": "obuv",
    "botas": "obuv",
    "pintura": "farba",
    "brocha": "štetec",
    "rodillo": "valček",
    "cúter": "nôž",
    "cuter": "nôž",
    "flexómetro": "meter",
    "metro": "meter"
}

def translate_query_to_slovak(text_es):
    if not text_es:
        return ""
    words = text_es.lower().split()
    translated = []
    for w in words:
        clean_w = re.sub(r'[^\w]', '', w)
        if clean_w in TRANSLATION_MAP:
            translated.append(TRANSLATION_MAP[clean_w])
        else:
            translated.append(w)
    return " ".join(translated)

def search_live_products(query_es, providers_list, max_results=5):
    """
    Realiza una búsqueda real en tiempo real rastreando las webs de los proveedores del Excel.
    """
    query_sk = translate_query_to_slovak(query_es)
    results = []
    
    # Filtrar hasta 6 proveedores relevantes
    suppliers_to_search = providers_list[:8] if providers_list else []
    
    for provider in suppliers_to_search:
        prov_name = provider.get('Proveedor', 'Proveedor SVK')
        web_url = provider.get('WEB', '')
        if not web_url:
            continue
            
        parsed = urlparse(web_url if web_url.startswith('http') else f'https://{web_url}')
        domain = parsed.netloc.lower()
        
        try:
            shop_results = scrape_single_supplier(prov_name, domain, web_url, query_es, query_sk)
            for item in shop_results:
                if item['url'] not in [r['url'] for r in results]:
                    results.append(item)
                    if len(results) >= max_results:
                        break
        except Exception as e:
            logging.error(f"Error raspando proveedor {prov_name}: {e}")
            
        if len(results) >= max_results:
            break
            
    # Si tras raspado en vivo no se obtuvieron fichas específicas, generar enlaces de búsqueda limpia directa para cada proveedor
    if len(results) < 3:
        for provider in suppliers_to_search:
            prov_name = provider.get('Proveedor', 'Proveedor SVK')
            web_url = provider.get('WEB', '')
            if not web_url: continue
            
            clean_url = build_clean_search_url(web_url, query_sk)
            
            # Verificar si este proveedor ya tiene un resultado
            if not any(r['proveedor'].lower() == prov_name.lower() for r in results):
                results.append({
                    "proveedor": prov_name,
                    "nombre_es": f"{query_es.title()} en {prov_name}",
                    "nombre_sk": f"{query_sk.capitalize()} ({prov_name})",
                    "referencia": "Catálogo " + prov_name.upper(),
                    "precio_eur": "Consultar catálogo €",
                    "url": clean_url
                })
                if len(results) >= max_results:
                    break

    return results

def scrape_single_supplier(prov_name, domain, web_url, query_es, query_sk):
    results = []
    
    # 1. VERCAJCH CENTRUM
    if 'vercajch.sk' in domain:
        url = f"https://vercajch.sk/?s={quote_plus(query_sk)}"
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/produkt/' in href and href not in [x['url'] for x in results]:
                title = a.get_text(strip=True)
                if not title or len(title) < 4:
                    slug = href.strip('/').split('/')[-1]
                    title = slug.replace('-', ' ').capitalize()
                
                # Buscar el precio en el contenedor padre
                price = "Consultar en tienda €"
                parent = a.find_parent(['div', 'li', 'article'])
                if parent:
                    pr_el = parent.select_one('.price, .amount, span.woocommerce-Price-amount')
                    if pr_el:
                        price = pr_el.get_text(strip=True)

                results.append({
                    "proveedor": prov_name,
                    "nombre_es": f"{title} (Ferretería)",
                    "nombre_sk": title,
                    "referencia": "SKU-" + href.strip('/').split('/')[-1][:12].upper(),
                    "precio_eur": price if '€' in price else f"{price} €",
                    "url": href
                })

    # 2. OBI
    elif 'obi.sk' in domain:
        url = f"https://www.obi.sk/search/{quote_plus(query_sk)}/"
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if ('/p/' in href or '/skrutkovac' in href or '/klies' in href) and href not in [x['url'] for x in results]:
                title = a.get_text(strip=True) or "Producto OBI Eslovaquia"
                full_url = urljoin(url, href)
                results.append({
                    "proveedor": prov_name,
                    "nombre_es": title,
                    "nombre_sk": title,
                    "referencia": "OBI-SK-" + href.strip('/').split('/')[-1][:10].upper(),
                    "precio_eur": "Ver en OBI €",
                    "url": full_url
                })

    # 3. AUTOTECHNA / OTROS E-COMMERCE
    elif 'autotechna.sk' in domain:
        clean_url = f"https://www.autotechna.sk/?s={quote_plus(query_sk)}"
        results.append({
            "proveedor": prov_name,
            "nombre_es": f"Recambios {query_es} (Autotechna)",
            "nombre_sk": f"Autodiely {query_sk} (Autotechna)",
            "referencia": "CAT-AUTOTECHNA",
            "precio_eur": "Consultar catálogo €",
            "url": clean_url
        })
        
    return results

def build_clean_search_url(web_url, query_sk):
    term_encoded = quote_plus(query_sk.strip())
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
