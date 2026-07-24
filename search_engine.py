import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
from translator import translate_es_to_sk
from providers_manager import providers_mgr

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# Términos a ignorar en URLs extraídas para evitar enlaces falsos a páginas legales/pie de página
EXCLUDED_PATTERNS = [
    'odstupenie', 'zmluvy', 'kosik', 'blog', 'contact', 'kontakt', 
    'reklamac', 'doprava', 'obchodne-podmienky', 'gdpr', 'suhlas',
    'prihlasenie', 'registracia', 'facebook', 'instagram'
]

def execute_search(query_es, category_group=""):
    """
    Motor principal de búsqueda y generación de catálogos sin API keys.
    """
    clean_query_es = (query_es or '').strip()
    if not clean_query_es:
        return {
            "query_es": "",
            "query_sk": "",
            "category_group": category_group,
            "results": []
        }

    # 1. Traducir consulta de español a eslovaco
    query_sk = translate_es_to_sk(clean_query_es)

    # 2. Filtrar proveedores del Excel según la categoría seleccionada
    target_providers = providers_mgr.filter_providers(category_group, clean_query_es)

    # 3. Rastrear e-commerce en paralelo (hasta 10 proveedores)
    results = []
    
    def process_provider(prov):
        prov_name = prov["nombre"]
        prov_tipo = prov["tipo"]
        web_url = prov["web"]
        
        # Generar enlace directo a la búsqueda en la tienda del proveedor
        search_url = providers_mgr.get_provider_search_url(web_url, query_sk)
        
        # Intentar raspado rápido de productos en vivo
        live_products = scrape_shop_products(prov_name, search_url)
        
        return {
            "proveedor": prov_name,
            "tipo": prov_tipo,
            "categoria_grupo": prov["categoria_grupo"],
            "nombre_es": clean_query_es.capitalize(),
            "nombre_sk": query_sk.capitalize(),
            "search_url": search_url,
            "live_products": live_products
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_provider, p) for p in target_providers]
        for f in futures:
            try:
                res = f.result(timeout=6)
                if res:
                    results.append(res)
            except Exception as e:
                logging.error(f"Error procesando proveedor: {e}")

    return {
        "query_es": clean_query_es,
        "query_sk": query_sk,
        "category_group": category_group or "Todas las categorías",
        "results": results
    }

def scrape_shop_products(prov_name, search_url):
    """
    Lee la página de resultados de la e-commerce y extrae productos concretos si están disponibles.
    """
    live_items = []
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=4)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Raspado genérico de productos en e-commerce WooCommerce / PrestaShop / OBI / WordPress
            for a in soup.find_all('a', href=True):
                href = a['href']
                href_lower = href.lower()
                
                # Ignorar páginas legales o de pie de página
                if any(ex in href_lower for ex in EXCLUDED_PATTERNS):
                    continue
                    
                if any(x in href_lower for x in ['/produkt/', '/p/', 'tovar', 'detail', 'hladaj', 'product']):
                    full_url = urljoin(search_url, href)
                    if full_url not in [item['url'] for item in live_items]:
                        title = a.get_text(strip=True)
                        if not title or len(title) < 4 or any(ex in title.lower() for ex in ['odstúpiť', 'zmluv', 'nákupný', 'košík']):
                            continue
                        
                        # Buscar precio en el contenedor padre
                        price = "Ver precio en tienda €"
                        parent = a.find_parent(['div', 'li', 'article'])
                        if parent:
                            pr_el = parent.select_one('.price, .amount, .woocommerce-Price-amount, span.price')
                            if pr_el:
                                price = pr_el.get_text(strip=True)

                        live_items.append({
                            "title_sk": title,
                            "price": price if '€' in price or 'EUR' in price else f"{price} €",
                            "url": full_url
                        })
                        if len(live_items) >= 4:
                            break
    except Exception as e:
        pass

    return live_items
