document.addEventListener('DOMContentLoaded', () => {
    const searchForm = document.getElementById('search-form');
    const searchInput = document.getElementById('search-input');
    const categorySelect = document.getElementById('category-select');
    const searchBtn = document.getElementById('search-btn');
    const statusBar = document.getElementById('status-bar');
    const statusText = document.getElementById('status-text');
    const resultsContainer = document.getElementById('results-container');
    const toast = document.getElementById('toast');

    // 1. Cargar categorías dinámicas desde el backend
    async function loadCategories() {
        try {
            const res = await fetch('/api/categories');
            if (res.ok) {
                const data = await res.json();
                if (data.categories && data.categories.length > 0) {
                    data.categories.forEach(cat => {
                        const opt = document.createElement('option');
                        opt.value = cat;
                        opt.textContent = cat;
                        categorySelect.appendChild(opt);
                    });
                }
            }
        } catch (err) {
            console.error("Error al cargar categorías:", err);
        }
    }

    loadCategories();

    // 2. Controlar la búsqueda de productos
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = searchInput.value.trim();
        const category = categorySelect.value;

        if (!query) return;

        // UI en estado de carga
        setLoadingState(true, `Buscando "${query}" en catálogos eslovacos...`);
        resultsContainer.innerHTML = '';

        try {
            const res = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query, category })
            });

            if (!res.ok) {
                throw new Error("Error en la respuesta del servidor");
            }

            const data = await res.json();
            renderResults(data.results, query);

        } catch (err) {
            console.error("Error realizando la búsqueda:", err);
            resultsContainer.innerHTML = `
                <div class="card-item" style="padding: 20px; text-align: center; color: #f87171;">
                    ❌ No se pudo completar la búsqueda. Por favor inténtalo de nuevo.
                </div>
            `;
        } finally {
            setLoadingState(false);
        }
    });

    function setLoadingState(isLoading, message = '') {
        if (isLoading) {
            searchBtn.disabled = true;
            searchBtn.querySelector('.btn-text').textContent = 'Buscando...';
            statusBar.classList.remove('hidden');
            statusText.textContent = message;
        } else {
            searchBtn.disabled = false;
            searchBtn.querySelector('.btn-text').textContent = 'Buscar Chollo 🔍';
            statusBar.classList.add('hidden');
        }
    }

    // 3. Renderizar resultados como acordeones interactivos
    function renderResults(results, query) {
        if (!results || results.length === 0) {
            resultsContainer.innerHTML = `
                <div class="card-item" style="padding: 24px; text-align: center; color: var(--text-secondary);">
                    🔍 No se encontraron coincidencias directas para "${query}". Intenta ajustar el término o seleccionar "Todas las categorías".
                </div>
            `;
            return;
        }

        results.forEach((item, index) => {
            const card = document.createElement('div');
            card.className = `card-item ${index === 0 ? 'open' : ''}`; // Abrir la primera por defecto

            const itemTextFormatted = `📌 PROVEEDOR: ${item.proveedor}
🇪🇸 PRODUCTO: ${item.nombre_es}
🇸🇰 PRODUCTO (SK): ${item.nombre_sk}
🔢 REF / CÓDIGO: ${item.referencia}
💶 PRECIO (IVA inc.): ${item.precio_eur}
🔗 ENLACE TIENDA: ${item.url}`;

            card.innerHTML = `
                <div class="card-header">
                    <div class="card-header-left">
                        <span class="provider-badge">🏬 ${escapeHtml(item.proveedor)}</span>
                        <h3 class="product-title-es">${escapeHtml(item.nombre_es)}</h3>
                    </div>
                    <div class="card-header-right">
                        <span class="price-tag">${escapeHtml(item.precio_eur)}</span>
                        <span class="chevron-icon">▼</span>
                    </div>
                </div>
                
                <div class="card-body">
                    <div class="details-grid">
                        <div class="detail-box">
                            <span class="detail-label">Nombre en Eslovaco (SK)</span>
                            <span class="detail-value">${escapeHtml(item.nombre_sk)}</span>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Referencia / Código</span>
                            <span class="detail-value">${escapeHtml(item.referencia)}</span>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Proveedor / Empresa</span>
                            <span class="detail-value">${escapeHtml(item.proveedor)}</span>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Precio Unitario (IVA inc.)</span>
                            <span class="detail-value" style="color: var(--accent-green); font-weight:700;">${escapeHtml(item.precio_eur)}</span>
                        </div>
                    </div>

                    <div class="actions-row">
                        <button class="btn-copy" data-text="${escapeAttribute(itemTextFormatted)}">
                            📋 Copiar Ficha
                        </button>
                        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="btn-link">
                            🔗 Ver Producto en Tienda Directa ↗
                        </a>
                    </div>
                </div>
            `;

            // Toggle acordeón
            const header = card.querySelector('.card-header');
            header.addEventListener('click', () => {
                card.classList.toggle('open');
            });

            // Botón Copiar Ficha
            const copyBtn = card.querySelector('.btn-copy');
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const textToCopy = copyBtn.getAttribute('data-text');
                copyToClipboard(textToCopy, copyBtn);
            });

            resultsContainer.appendChild(card);
        });
    }

    // 4. Copiar al portapapeles
    function copyToClipboard(text, btnElement) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                showToast("¡Ficha copiada al portapapeles! 📋");
            }).catch(err => {
                fallbackCopyText(text);
            });
        } else {
            fallbackCopyText(text);
        }
    }

    function fallbackCopyText(text) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showToast("¡Ficha copiada al portapapeles! 📋");
        } catch (err) {
            console.error('No se pudo copiar:', err);
        }
        document.body.removeChild(textArea);
    }

    function showToast(msg) {
        toast.textContent = msg;
        toast.classList.remove('hidden');
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 2500);
    }

    function escapeHtml(str) {
        return (str || '').replace(/&/g, "&amp;")
                           .replace(/</g, "&lt;")
                           .replace(/>/g, "&gt;")
                           .replace(/"/g, "&quot;")
                           .replace(/'/g, "&#039;");
    }

    function escapeAttribute(str) {
        return (str || '').replace(/"/g, '&quot;');
    }
});
