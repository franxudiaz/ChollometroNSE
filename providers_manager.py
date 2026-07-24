import os
import logging
import pandas as pd
from urllib.parse import quote_plus, urlparse

STANDARD_CATEGORIES = [
    "🛠️ Ferretería y Herramientas",
    "⚡ Electricidad e Iluminación",
    "💻 Informática, Tecnología y Electrónica",
    "🚗 Automoción y Recambios",
    "🏗️ Materiales de Construcción y Obra",
    "📄 Papelería, Impresión y Oficina",
    "🧹 Limpieza y Protección / PRL",
    "🏠 Mobiliario y Hogar",
    "⚽ Deportes, Escalada y Táctico",
    "🎨 Costura, Arte y Protocolo",
    "🛒 Alimentación y Mayorista",
    "💊 Farmacia y Salud",
    "✉️ Envíos y Correo"
]

def find_excel_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, 'Proveedores SVK V (VERSIÓN 1.1).xlsx'),
        os.path.join(base_dir, 'data', 'Proveedores SVK V (VERSIÓN 1.1).xlsx'),
    ]
    for folder in [base_dir, os.path.join(base_dir, 'data')]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith('.xlsx') and 'proveed' in f.lower():
                    candidates.append(os.path.join(folder, f))
    
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

class ProvidersManager:
    def __init__(self):
        self.providers = []
        self.load_providers()

    def load_providers(self):
        excel_path = find_excel_file()
        if not excel_path:
            logging.warning("No se encontró el archivo Excel de proveedores.")
            return

        try:
            df = pd.read_excel(excel_path)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.fillna('')
            
            self.providers = []
            for _, r in df.iterrows():
                name = str(r.get('Proveedor', '')).strip()
                tipo = str(r.get('tipo', '')).strip()
                web = str(r.get('WEB', '')).strip()
                if name and web:
                    category_group = self.assign_category_group(name, tipo)
                    self.providers.append({
                        "id": name.lower().replace(" ", "_"),
                        "nombre": name,
                        "tipo": tipo,
                        "categoria_grupo": category_group,
                        "web": web if web.startswith("http") else f"https://{web}"
                    })
            logging.info(f"Cargados {len(self.providers)} proveedores desde Excel.")
        except Exception as e:
            logging.error(f"Error cargando proveedores desde Excel: {e}")

    def assign_category_group(self, name, tipo):
        t = (tipo + " " + name).lower()
        if any(x in t for x in ["ferreteria", "herramental", "maquinaria", "tornilleria", "soldadura", "vercajch", "hyriak", "vkp", "valtec"]):
            return "🛠️ Ferretería y Herramientas"
        elif any(x in t for x in ["electricidad", "sonido", "copper", "hagard"]):
            return "⚡ Electricidad e Iluminación"
        elif any(x in t for x in ["informática", "tecnología", "mediamarkt", "nay", "smart", "agartha"]):
            return "💻 Informática, Tecnología y Electrónica"
        elif any(x in t for x in ["automovil", "recambios", "autopiko", "autotechna", "scania"]):
            return "🚗 Automoción y Recambios"
        elif any(x in t for x in ["construcción", "metales", "obra", "hidraulica", "gufero", "hansa", "dado", "stavivo", "technik"]):
            return "🏗️ Materiales de Construcción y Obra"
        elif any(x in t for x in ["papeleria", "copisteria", "toner", "empaque", "xepap", "fax", "technopack"]):
            return "📄 Papelería, Impresión y Oficina"
        elif any(x in t for x in ["limpieza", "prl", "ropa prl", "scandi", "gatial", "t-tech"]):
            return "🧹 Limpieza y Protección / PRL"
        elif any(x in t for x in ["muebles", "mobiliario", "ikea", "jysk", "leroymerlin", "obi"]):
            return "🏠 Mobiliario y Hogar"
        elif any(x in t for x in ["deportivo", "escalada", "ranger", "decathlon", "outland", "army"]):
            return "⚽ Deportes, Escalada y Táctico"
        elif any(x in t for x in ["merceria", "pintura", "protocolo", "kapex", "dk framing", "promodesign"]):
            return "🎨 Costura, Arte y Protocolo"
        elif "farmacia" in t or "benulekaren" in t:
            return "💊 Farmacia y Salud"
        elif "correo" in t or "posta" in t:
            return "✉️ Envíos y Correo"
        elif "alimentación" in t or "metro" in t:
            return "🛒 Alimentación y Mayorista"
        return "🛠️ Ferretería y Herramientas"

    def get_categories(self):
        return STANDARD_CATEGORIES

    def filter_providers(self, category_group="", query=""):
        filtered = []
        for p in self.providers:
            if category_group and category_group != "Todas las categorías":
                if category_group.lower() not in p["categoria_grupo"].lower() and category_group.lower() not in p["tipo"].lower():
                    continue
            filtered.append(p)
        return filtered

    def get_provider_search_url(self, web_url, term_sk):
        """
        Construye la URL verificada y exacta del buscador interno del proveedor.
        """
        if not web_url:
            return "https://www.google.sk"
            
        term_encoded = quote_plus(term_sk.strip())
        parsed = urlparse(web_url if web_url.startswith("http") else f"https://{web_url}")
        domain = parsed.netloc.lower()
        
        if "decathlon.sk" in domain:
            return f"https://www.decathlon.sk/search/?query={term_encoded}"
        elif "obi.sk" in domain:
            return f"https://www.obi.sk/search/{term_encoded}/"
        elif "vercajch.sk" in domain:
            return f"https://vercajch.sk/?s={term_encoded}"
        elif "autotechna.sk" in domain:
            return f"https://www.autotechna.sk/?s={term_encoded}"
        elif "nay.sk" in domain:
            return f"https://www.nay.sk/vyhladavanie?q={term_encoded}"
        elif "hagard.sk" in domain:
            return f"https://www.hagard.sk/?s={term_encoded}"
        elif "copper.sk" in domain:
            return f"https://www.copper.sk/?s={term_encoded}"
        elif "outland.sk" in domain:
            return f"https://www.outland.sk/?s={term_encoded}"
        elif "stavebninydado.sk" in domain:
            return f"https://www.stavebninydado.sk/?s={term_encoded}"
        elif "ikea.com" in domain:
            return f"https://www.ikea.com/sk/sk/search/?q={term_encoded}"
        elif "jysk.sk" in domain:
            return f"https://jysk.sk/search?query={term_encoded}"
        elif "benulekaren.sk" in domain:
            return f"https://www.benulekaren.sk/vyhladavanie?q={term_encoded}"
        elif "xepap.sk" in domain:
            return f"https://www.xepap.sk/vyhladavanie?q={term_encoded}"
        elif "eshop.vkpsteel.com" in domain:
            return f"https://www.eshop.vkpsteel.com/vyhladavanie?q={term_encoded}"
        elif "smart.sk" in domain:
            return f"https://www.smart.sk/vyhladavanie?q={term_encoded}"
        elif "gufero.sk" in domain:
            return f"https://www.gufero.sk/search?q={term_encoded}"
        elif "autopiko.sk" in domain:
            return f"https://www.autopiko.sk/search?q={term_encoded}"
        elif "hyriak.sk" in domain:
            return f"https://www.hyriak.sk/hladaj/{term_encoded}"
        elif "technopack.sk" in domain:
            return f"https://www.technopack.sk/sk/katalog/?query={term_encoded}"
        else:
            clean_domain = domain.replace("www.", "")
            return f"https://www.google.com/search?q=site:{clean_domain}+{term_encoded}"

providers_mgr = ProvidersManager()
