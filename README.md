# Chollometro NSE - Asistente de Compras SVK 🇸🇰

**Chollometro NSE** es una aplicación web responsiva diseñada para buscar, comparar y gestionar la compra de materiales, herramientas, repuestos y suministros en proveedores locales de Eslovaquia.

Utiliza el catálogo oficial de proveedores autorizados (`Proveedores SVK V (VERSIÓN 1.1).xlsx`) e integra **Google GenAI (Gemini)** para realizar la traducción automática al eslovaco y la extracción inteligente de datos de productos.

---

## 🚀 Características Principales

- **Diseño Móvil Primero (Mobile-First)**: Interfaz oscura de alto contraste, moderna y optimizada para uso en smartphones, tablets y pantallas de escritorio.
- **Filtro de Proveedores y Categorías**: Carga dinámica del catálogo Excel de proveedores (OBI, Nay, Decathlon, Vercajch, Hagard-Hal, Stavebniny Dado, Metro, etc.).
- **Búsqueda Inteligente con Gemini**: Traducción automática de términos de búsqueda al eslovaco para consultar catálogos locales y obtener el nombre traducido, referencia y precio.
- **Fichas Desplegables / Acordeón**: Visualización clara con detalles completos de cada producto.
- **Botón "Copiar Ficha"**: Copia formateada en 1 solo clic para pegar directamente en chats de la misión o informes.
- **Enlaces Directos (`target="_blank"`)**: Acceso inmediato a la ficha del producto en la tienda oficial del proveedor en una pestaña nueva.
- **Despliegue Sencillo**: Configuración lista para ser alojada en **PythonAnywhere** o cualquier servidor WSGI (Gunicorn).

---

## 🛠️ Requisitos Previos e Instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/franxudiaz/ChollometroNSE.git
cd ChollometroNSE
```

### 2. Crear y activar el entorno virtual
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno
Crea un archivo `.env` en la raíz del proyecto basándote en `.env.example`:

```env
GEMINI_API_KEY=tu_api_key_de_google_ai_studio
PORT=5000
```
> *(Nota: Si no se configura `GEMINI_API_KEY`, la aplicación utilizará el modo de demostración/fallback estructurado para garantizar la prueba de la interfaz).*

---

## 💻 Ejecución Local

Para iniciar el servidor de desarrollo Flask:

```bash
python app.py
```

Abre tu navegador en `http://localhost:5000`.

---

## 🌐 Guía de Despliegue en PythonAnywhere

1. **Crear una cuenta en PythonAnywhere** (https://www.pythonanywhere.com).
2. Abrir una consola Bash en PythonAnywhere y clonar el repositorio:
   ```bash
   git clone https://github.com/franxudiaz/ChollometroNSE.git
   cd ChollometroNSE
   ```
3. Crear el entorno virtual e instalar los requerimientos:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 chollometro-venv
   pip install -r requirements.txt
   ```
4. En el panel de control de PythonAnywhere, ve a la pestaña **Web**:
   - Crea una nueva aplicación web seleccionando **Manual Configuration** (Python 3.10).
   - En **Code**, configura:
     - **Source code:** `/home/tu_usuario/ChollometroNSE`
     - **Working directory:** `/home/tu_usuario/ChollometroNSE`
   - En **Virtualenv**, introduce la ruta a tu entorno virtual:
     `/home/tu_usuario/.virtualenvs/chollometro-venv`
5. Edita el archivo de configuración **WSGI** de PythonAnywhere para que apunte a `wsgi.py`:
   ```python
   import sys
   import os

   project_home = '/home/tu_usuario/ChollometroNSE'
   if project_home not in sys.path:
       sys.path.insert(0, project_home)

   from wsgi import application
   ```
6. Haz clic en **Reload tu_usuario.pythonanywhere.com** ¡y tu aplicación estará online! 🚀

---

## 📄 Estructura del Proyecto

```
ChollometroNSE/
├── app.py                      # Servidor Flask e integración con Gemini AI
├── wsgi.py                     # Punto de entrada para PythonAnywhere
├── requirements.txt            # Dependencias del proyecto
├── README.md                   # Documentación principal
├── .gitignore                  # Exclusiones de Git
├── .env.example                # Ejemplo de variables de entorno
├── data/
│   └── Proveedores SVK V (VERSIÓN 1.1).xlsx # Excel de proveedores
├── templates/
│   └── index.html              # Plantilla HTML5 principal
└── static/
    ├── css/
    │   └── style.css           # Estilos Dark Mode Mobile-First
    └── js/
        └── main.js             # Lógica cliente y portapapeles
```

---

## 🛡️ Licencia y Créditos
Desarrollado para la gestión de compras en Eslovaquia (NSE SVK 🇸🇰) - 2026.
