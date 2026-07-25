import os
import logging
from flask import Flask, render_template, request, jsonify
from search_engine import execute_search
from providers_manager import providers_mgr
from product_extractor import extract_product_data

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    categories = providers_mgr.get_categories()
    return jsonify({"categories": categories})

@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    category = data.get('category', '').strip()

    if not query:
        return jsonify({"error": "La consulta de búsqueda no puede estar vacía"}), 400

    search_result = execute_search(query, category)

    return jsonify({
        "query_es": search_result["query_es"],
        "query_sk": search_result["query_sk"],
        "category_group": search_result["category_group"],
        "count": len(search_result["results"]),
        "results": search_result["results"]
    })

@app.route('/api/extract_product', methods=['POST'])
def extract_product():
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({"error": "Debes proporcionar una URL válida de la ficha del producto."}), 400

    result = extract_product_data(url)
    if "error" in result:
        return jsonify({"error": result["error"]}), 400

    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
