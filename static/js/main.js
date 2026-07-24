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
                    // Limpiar y poblar selector de categorías
                    categorySelect.innerHTML = '<option value="">Todas las categorías (38 Proveedores SVK)</option>';
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

    // 2. Controlar el formulario de búsqueda
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = searchInput.value.trim();
        const category = categorySelect.value;

        if (!query) return;

        setLoadingState(true, `Traduciendo "${query}" al eslovaco y generando accesos a las e-commerce...`);
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
            renderResults(data);

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
            searchBtn.querySelector('.btn-text').textContent = 'Generando búsquedas...';
            statusBar.classList.remove('hidden');
            statusText.textContent = message;
        } else {
            searchBtn.disabled = false;
            searchBtn.querySelector('.btn-text').textContent = 'Buscar Chollo 🔍';
            statusBar.classList.add('hidden');
        }
    }

    // 3. Renderizar las tarjetas de proveedores y accesos directos
    function renderResults(data) {
        const results = data.results;
        const queryEs = data.query_es;
        const querySk = data.query_sk;

        if (!results || results.length === 0) {
            resultsContainer.innerHTML = `
                <div class="card-item" style="padding: 24px; text-align: center; color: var(--text-secondary);">
                    🔍 No se encontraron proveedores en la categoría seleccionada para "${queryEs}". Intenta seleccionar "Todas las categorías".
                </div>
            `;
            return;
        }

        // Encabezado de traducción realizada
        const summaryBadge = document.createElement('div');
        summaryBadge.style.cssText = `
            background: rgba(59, 130, 246, 0.15);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 12px;
            padding: 12px 18px;
            color: #93c5fd;
            font-size: 0.9rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        `;
        summaryBadge.innerHTML = `
            <span>🇪🇸 <strong>"${escapeHtml(queryEs)}"</strong> ➔ 🇸🇰 Traducido a: <strong style="color: #60a5fa;">"${escapeHtml(querySk)}"</strong></span>
            <span style="font-size: 0.8rem; background: #1e293b; padding: 4px 10px; border-radius: 20px; color: #f8fafc;">${results.length} Tiendas</span>
        `;
        resultsContainer.appendChild(summaryBadge);

        results.forEach((item, index) => {
            const card = document.createElement('div');
            card.className = `card-item ${index < 3 ? 'open' : ''}`; // Desplegar las primeras 3 por defecto

            let liveProductsHtml = '';
            if (item.live_products && item.live_products.length > 0) {
                liveProductsHtml = `
                    <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed rgba(255,255,255,0.1);">
                        <span class="detail-label" style="margin-bottom: 8px; display: block;">Coincidencias encontradas en ${escapeHtml(item.proveedor)}:</span>
                        <div style="display: flex; flex-direction: column; gap: 8px;">
                            ${item.live_products.map(p => `
                                <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-input); padding: 8px 12px; border-radius: 6px; font-size: 0.85rem;">
                                    <span style="color: var(--text-primary); max-width: 65%; font-weight: 500;">${escapeHtml(p.title_sk)}</span>
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <span style="color: var(--accent-green); font-weight: 700;">${escapeHtml(p.price)}</span>
                                        <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener" style="color: #60a5fa; text-decoration: none; font-weight: 600;">Ver Ficha ↗</a>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            const itemTextFormatted = `🏬 PROVEEDOR: ${item.proveedor} (${item.tipo})
🇪🇸 BÚSQUEDA (ES): ${queryEs}
🇸🇰 BÚSQUEDA EN TIENDA (SK): ${querySk}
🔗 ENLACE DIRECTO A CATÁLOGO: ${item.search_url}`;

            card.innerHTML = `
                <div class="card-header">
                    <div class="card-header-left">
                        <span class="provider-badge">🏬 ${escapeHtml(item.proveedor)} • ${escapeHtml(item.categoria_grupo)}</span>
                        <h3 class="product-title-es">${escapeHtml(item.proveedor)} — Catálogo Directo</h3>
                    </div>
                    <div class="card-header-right">
                        <span class="chevron-icon">▼</span>
                    </div>
                </div>
                
                <div class="card-body">
                    <div class="details-grid">
                        <div class="detail-box">
                            <span class="detail-label">Búsqueda en Español (ES)</span>
                            <span class="detail-value">${escapeHtml(queryEs)}</span>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Búsqueda Ejecutada en Tienda (SK)</span>
                            <span class="detail-value" style="color: var(--accent-cyan); font-weight:700;">${escapeHtml(querySk)}</span>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Tipo de Productos en Excel</span>
                            <span class="detail-value">${escapeHtml(item.tipo)}</span>
                        </div>
                    </div>

                    ${liveProductsHtml}

                    <div class="actions-row" style="margin-top: 16px;">
                        <a href="${escapeHtml(item.search_url)}" target="_blank" rel="noopener noreferrer" class="btn-primary" style="flex: 1; text-decoration: none; text-align: center; justify-content: center;">
                            🔍 Abrir Búsqueda Directa en ${escapeHtml(item.proveedor)} ↗
                        </a>
                        <button class="btn-copy" data-text="${escapeAttribute(itemTextFormatted)}">
                            📋 Copiar Enlace
                        </button>
                    </div>
                </div>
            `;

            // Toggle acordeón
            const header = card.querySelector('.card-header');
            header.addEventListener('click', () => {
                card.classList.toggle('open');
            });

            // Botón Copiar Enlace
            const copyBtn = card.querySelector('.btn-copy');
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const textToCopy = copyBtn.getAttribute('data-text');
                copyToClipboard(textToCopy);
            });

            resultsContainer.appendChild(card);
        });
    }

    // 4. Copiar al portapapeles
    function copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                showToast("¡Enlace copiado al portapapeles! 📋");
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
            showToast("¡Enlace copiado al portapapeles! 📋");
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
