import logging
from translator import translate_es_to_sk
from providers_manager import providers_mgr

def execute_search(query_es, category_group=""):
    """
    Motor principal de generación de catálogos y búsquedas directas en e-commerce sin API keys.
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

    # 3. Construir enlaces directos y limpios a cada proveedor
    results = []
    for prov in target_providers:
        prov_name = prov["nombre"]
        prov_tipo = prov["tipo"]
        web_url = prov["web"]
        
        # Generar URL de búsqueda directa en el motor interno de la tienda oficial
        search_url = providers_mgr.get_provider_search_url(web_url, query_sk)
        
        results.append({
            "proveedor": prov_name,
            "tipo": prov_tipo,
            "categoria_grupo": prov["categoria_grupo"],
            "web_oficial": web_url,
            "nombre_es": clean_query_es.capitalize(),
            "nombre_sk": query_sk,
            "search_url": search_url
        })

    return {
        "query_es": clean_query_es,
        "query_sk": query_sk,
        "category_group": category_group or "Todas las categorías",
        "results": results
    }
