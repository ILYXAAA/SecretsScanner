// Global variables
let allSecrets = [];
let allSecretsData = [];
let filteredSecrets = [];
let currentPage = 1;
let pageSize = 100;
let isFiltersOpen = false;
let sortColumns = [];
let selectedSecret = null;
let activeFilters = {
    status: ['refuted', 'resolved', 'active'],
    severity: ['High', 'Potential'],
    type: [],
    search: ''
};

// Server-side data - загружаем из data-атрибутов
let projectRepoUrl = '';
let latestCommit = '';
let hubType = '';

function getFileNameFromPath(path) {
    if (!path) return '';
    return path.replace(/\\/g, '/').split('/').pop() || '';
}

// Получаем данные из data-атрибутов
function loadDataFromAttributes() {
    projectRepoUrl = document.body.dataset.projectRepoUrl || '';
    latestCommit = document.body.dataset.latestCommit || '';
    hubType = document.body.dataset.hubType || '';
}

function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    
    const str = String(text);
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function safeHtml(text) {
    return escapeHtml(text);
}

// Load data from script tags
function loadSecretsData() {
    try {
        const confirmedDataElement = document.getElementById('secrets-data');
        const allDataElement = document.getElementById('secrets-all-data');
        
        if (confirmedDataElement) {
            const confirmedData = JSON.parse(confirmedDataElement.textContent);
            console.log('Loaded confirmed secrets:', confirmedData.length);
        }
        
        if (allDataElement) {
            allSecretsData = JSON.parse(allDataElement.textContent);
            console.log('Loaded all secrets:', allSecretsData.length);
        }
        
        allSecrets = allSecretsData.slice();
        return true;
        
    } catch (error) {
        console.error('Error loading secrets data:', error);
        return false;
    }
}

function initializeFilters() {
    const uniqueTypes = [...new Set(allSecretsData.map(s => s.type))].sort();
    
    const typeFiltersContainer = document.getElementById('typeFilters');
    if (!typeFiltersContainer) {
        console.error('typeFilters container not found');
        return;
    }
    
    typeFiltersContainer.innerHTML = '';
    
    uniqueTypes.forEach(type => {
        const div = document.createElement('div');
        div.className = 'checkbox-item';
        const safeId = type.replace(/[^a-zA-Z0-9]/g, '_');
        div.innerHTML = `
            <input type="checkbox" id="type-${safeId}" value="${safeHtml(type)}" onchange="applyFilters()" checked>
            <label for="type-${safeId}">${safeHtml(type)}</label>
        `;
        typeFiltersContainer.appendChild(div);
    });

    activeFilters.type = uniqueTypes.slice();
}

function updateStatusFilters() {
    const filtersContent = document.querySelector('.filters-content');
    if (!filtersContent) return;
    
    // Найти и заменить блок статусов
    const statusGroup = filtersContent.querySelector('.filter-group');
    if (statusGroup) {
        statusGroup.innerHTML = `
            <h4>📊 Статус</h4>
            <div class="checkbox-item">
                <input type="checkbox" id="status-refuted" value="refuted" onchange="applyFilters()" checked>
                <label for="status-refuted">✅ Refuted</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="status-resolved" value="resolved" onchange="applyFilters()" checked>
                <label for="status-resolved">⚠️ Resolved</label>
            </div>
            <div class="checkbox-item">
                <input type="checkbox" id="status-active" value="active" onchange="applyFilters()" checked>
                <label for="status-active">❌ Active</label>
            </div>
        `;
    }
}

function applyFilters() {
    console.log('Applying filters to', allSecrets.length, 'secrets');
    
    activeFilters.status = [];
    activeFilters.severity = [];
    activeFilters.type = [];
    activeFilters.search = document.getElementById('searchInput')?.value?.toLowerCase() || '';

    const showUnconfirmed = document.getElementById('showAllSecrets')?.checked || false;
    
    // Status filters
    if (document.getElementById('status-refuted')?.checked) {
        activeFilters.status.push('refuted');
    }
    if (document.getElementById('status-resolved')?.checked) {
        activeFilters.status.push('resolved');
    }
    if (document.getElementById('status-active')?.checked) {
        activeFilters.status.push('active');
    }

    // Severity filters
    if (document.getElementById('severity-high')?.checked) {
        activeFilters.severity.push('High');
    }
    if (document.getElementById('severity-potential')?.checked) {
        activeFilters.severity.push('Potential');
    }

    // Type filters
    document.querySelectorAll('#typeFilters input[type="checkbox"]:checked').forEach(cb => {
        activeFilters.type.push(cb.value);
    });

    console.log('Active filters:', activeFilters);

    filteredSecrets = allSecrets.filter(secret => {
        // Search filter
        if (activeFilters.search && !secret.current_secret.toLowerCase().includes(activeFilters.search)) {
            return false;
        }

        // Show unconfirmed checkbox
        if (!showUnconfirmed && !secret.has_confirmed) {
            return false;
        }

        // Status filter - проверяем что статус существует
        if (secret.status && !activeFilters.status.includes(secret.status)) {
            return false;
        }

        // Severity filter
        if (!activeFilters.severity.includes(secret.severity)) {
            return false;
        }

        // Type filter
        if (!activeFilters.type.includes(secret.type)) {
            return false;
        }

        return true;
    });

    console.log('Filtered secrets:', filteredSecrets.length);

    currentPage = 1;
    selectedSecret = null;
    showEmptyDetail();
    sortSecrets();
    updateStats();
    renderTable();
    renderPagination();
    updateURL();
}

function clearAllFilters() {
    document.querySelectorAll('#filtersPanel input[type="checkbox"]').forEach(cb => {
        cb.checked = true;
    });
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.value = '';
    }
    
    applyFilters();
}

function updateStats() {
    const totalCount = allSecrets.length;
    const filteredCount = filteredSecrets.length;

    const totalEl = document.getElementById('totalCount');
    const filteredEl = document.getElementById('filteredCount');
    
    if (totalEl) totalEl.textContent = totalCount;
    if (filteredEl) filteredEl.textContent = filteredCount;
}

function updateURL() {
    const params = new URLSearchParams();
    params.set('page', currentPage);
    params.set('page_size', pageSize);
    
    const newURL = window.location.pathname + '?' + params.toString();
    history.replaceState(null, '', newURL);
}

function renderTable() {
    const tableContainer = document.getElementById('secretsTable');
    
    if (filteredSecrets.length === 0) {
        tableContainer.innerHTML = `
            <div class="empty-results">
                <h3>📭 Нет секретов</h3>
                <p>Нет секретов, соответствующих текущим фильтрам.</p>
            </div>
        `;
        return;
    }

    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, filteredSecrets.length);
    const pageSecrets = filteredSecrets.slice(startIndex, endIndex);

    let tableHTML = `
        <table class="secrets-table">
            <thead class="table-header">
                <tr>
                    <th class="sortable" data-sort="secret">🔑 Secret</th>
                    <th class="sortable" data-sort="file">📁 File</th>
                    <th class="sortable" data-sort="type">🏷️ Type</th>
                    <th class="sortable" data-sort="severity">⚠️ Severity</th>
                    <th class="sortable" data-sort="status">📊 Status</th>
                    <th class="sortable" data-sort="history">📊 История</th>
                </tr>
            </thead>
            <tbody>
    `;

    pageSecrets.forEach((secret, index) => {
        const globalIndex = startIndex + index;
        
        // Определяем иконку и класс статуса
        let statusIcon = '❌';
        let statusClass = 'active';
        
        if (secret.status === 'refuted') {
            statusIcon = '✅';
            statusClass = 'refuted';
        } else if (secret.status === 'resolved') {
            statusIcon = '⚠️';
            statusClass = 'resolved';
        } else if (secret.status === 'active') {
            statusIcon = '❌';
            statusClass = 'active';
        }
        
        tableHTML += `
            <tr class="secret-row" data-secret-id="${secret.id}" data-secret-index="${globalIndex}">
                <td>
                    <div class="secret-value">${safeHtml(secret.current_secret)}</div>
                </td>
                <td>
                    <div class="secret-file">${safeHtml((secret.path || '').split('/').pop())}</div>
                    <div class="secret-line">Line ${secret.line}</div>
                </td>
                <td>
                    <div class="secret-type">${safeHtml(secret.type)}</div>
                </td>
                <td>
                    <div class="secret-severity ${(secret.severity || '').toLowerCase()}">${safeHtml(secret.severity)}</div>
                </td>
                <td>
                    <div class="resolved-status status-${statusClass}">
                        ${statusIcon}
                    </div>
                </td>
                <td>
                    <div class="scan-info">
                        <div class="scan-id">${(secret.unique_commits || []).length} коммит${(secret.unique_commits || []).length !== 1 ? 'ов' : ''}</div>
                    </div>
                </td>
            </tr>
        `;
    });

    tableHTML += '</tbody></table>';
    tableContainer.innerHTML = tableHTML;

    initializeTableEventListeners();
}

function initializeTableEventListeners() {
    const secretRows = document.querySelectorAll('.secret-row');
    secretRows.forEach((row, index) => {
        row.addEventListener('click', function(e) {
            const secretId = parseInt(row.dataset.secretId);
            const globalIndex = parseInt(row.dataset.secretIndex);
            selectSecret(secretId);
        });
    });

    const sortableHeaders = document.querySelectorAll('.sortable');
    sortableHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const column = this.dataset.sort;
            handleSort(column);
        });
    });
}

function selectSecret(secretId) {
    document.querySelectorAll('.secret-row').forEach(row => {
        row.classList.remove('selected');
    });
    
    const row = document.querySelector(`[data-secret-id="${secretId}"]`);
    if (row) {
        row.classList.add('selected');
        selectedSecret = secretId;
        showSecretDetails(secretId);
    }
}

function showEmptyDetail() {
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;
    
    detailPanel.innerHTML = `
        <div class="detail-empty">
            <div style="font-size: 3rem; margin-bottom: 1rem;">👈</div>
            <h3>Выберите секрет</h3>
            <p>Кликните на любой секрет из списка для просмотра подробной информации.</p>
        </div>
    `;
}

function showSecretDetails(secretId) {
    const secret = allSecrets.find(s => s.id === secretId);
    if (!secret) return;
    
    let fileUrl = '#';
    try {
        if (projectRepoUrl && projectRepoUrl.includes('devzone.local')) {
            fileUrl = `${projectRepoUrl}/-/blob/${latestCommit || 'main'}/${encodeURIComponent(secret.path)}#L${secret.line}-${secret.line}`;
        } else if (hubType === 'Azure') {
            const startColumn = 1;
            const secretLength = secret.current_secret ? secret.current_secret.length : 0;
            const endColumn = secretLength + 1;
            fileUrl = `${projectRepoUrl}?path=${encodeURIComponent(secret.path)}&version=GC${latestCommit || 'main'}&line=${secret.line}&lineEnd=${secret.line}&lineStartColumn=${startColumn}&lineEndColumn=${endColumn}&_a=contents`;
        } else if (projectRepoUrl) {
            const safePath = secret.path.split('/').map(encodeURIComponent).join('/');
            fileUrl = `${projectRepoUrl}/blob/${latestCommit || 'main'}${safePath}?plain=1#L${secret.line}`;
        }
    } catch (error) {
        console.error('Error building file URL:', error);
    }

    // Filter timeline to show only scans AFTER first detection
    let filteredTimeline = [];
    if (secret.timeline && secret.timeline.length > 0) {
        const sortedTimeline = secret.timeline.slice().sort((a, b) => 
            new Date(a.scan_date) - new Date(b.scan_date)
        );
        
        const firstDetectionIndex = sortedTimeline.findIndex(item => item.found_secret);
        
        if (firstDetectionIndex !== -1) {
            filteredTimeline = sortedTimeline.slice(firstDetectionIndex);
        } else {
            filteredTimeline = sortedTimeline;
        }
    }

    let timelineHtml = '';
    if (filteredTimeline && filteredTimeline.length > 0) {
        timelineHtml = filteredTimeline.map((item, index) => {
            const date = new Date(item.scan_date).toLocaleString('ru-RU');
            const statusClass = item.status.toLowerCase().replace(' ', '-');
            
            let statusDisplay = '';
            let userInfo = '';
            let commentHtml = '';
            
            if (item.status === 'Confirmed') {
                statusDisplay = 'Подтвержден';
                if (item.confirmed_by) {
                    userInfo = `👤 ${safeHtml(item.confirmed_by)}`;
                }
            } else if (item.status === 'Refuted') {
                statusDisplay = 'В исключениях';
                if (item.refuted_by) {
                    userInfo = `👤 ${safeHtml(item.refuted_by)}`;
                }
                if (item.exception_comment) {
                    commentHtml = `<div class="timeline-comment">💬 ${safeHtml(item.exception_comment)}</div>`;
                }
            } else if (item.status === 'Not Found') {
                statusDisplay = 'Не найден';
            } else {
                statusDisplay = 'Обнаружен';
            }
            
            let actionsHtml = '';
            const scanBtn = `<a href="/secret_scanner/scan/${item.scan_id}/results" target="_blank" class="timeline-btn scan">📊 Скан</a>`;
            
            let compareBtn = '';
            if (latestCommit && item.commit && item.commit !== latestCommit) {
                let compareUrl = '#';
                try {
                    if (hubType === 'Azure') {
                        const urlParts = projectRepoUrl.split('/');
                        if (urlParts.length >= 6) {
                            const org = urlParts[3];
                            const project = urlParts[4];
                            const repo = urlParts[6];
                            compareUrl = `${projectRepoUrl}?_a=compare&path=${encodeURIComponent(secret.path)}&mversion=GC${item.commit}&oversion=GC${latestCommit}`;
                        }
                    } else if (projectRepoUrl && projectRepoUrl.includes('github.com')) {
                        compareUrl = `${projectRepoUrl}/compare/${item.commit}...${latestCommit}`;
                    }
                } catch (error) {
                    console.error('Error building compare URL:', error);
                }
                
                if (compareUrl !== '#') {
                    compareBtn = `<a href="${compareUrl}" target="_blank" class="timeline-btn compare">🔗 Сравнить с текущим</a>`;
                }
            }
            
            actionsHtml = `<div class="timeline-actions">${scanBtn}${compareBtn}</div>`;
            
            let contentHtml = '';
            if (item.found_secret) {
                contentHtml = `
                    <div class="timeline-content">
                        <div class="timeline-secret">🔑 ${safeHtml(item.secret_value)}</div>
                        <div class="timeline-commit">🔗 ${safeHtml(item.commit || 'unknown')}</div>
                    </div>
                `;
            } else {
                contentHtml = `
                    <div class="timeline-content">
                        <div class="timeline-secret" style="color: #9ca3af; font-style: italic;">🔍 Секрет не обнаружен в этом скане</div>
                        <div class="timeline-commit">🔗 ${safeHtml(item.commit || 'unknown')}</div>
                        <div style="font-size: 0.75rem; color: #f59e0b; margin-top: 0.5rem; padding: 0.5rem; background: #fef3c7; border-radius: 4px; border-left: 3px solid #f59e0b;">
                            ⚠️ <strong>Возможное переименование:</strong> Секрет мог быть переименован (например, SECRET → VARIABLE), но значение осталось тем же.
                        </div>
                    </div>
                `;
            }
            
            return `
                <div class="timeline-item status-${statusClass}">
                    <div class="timeline-date-badge">
                        <div class="timeline-date-external">📅 ${date}</div>
                        ${userInfo ? `<div class="timeline-user-external">${userInfo}</div>` : ''}
                    </div>
                    <div class="timeline-header">
                        <div class="timeline-status ${statusClass}">${statusDisplay}</div>
                    </div>
                    ${contentHtml}
                    ${commentHtml}
                    ${actionsHtml}
                </div>
            `;
        }).join('');
    }
    
    let resolutionBanner = '';
    if (secret.status === 'refuted') {
        resolutionBanner = `
            <div class="resolution-banner refuted">
                <div class="icon">🛡️</div>
                <div class="text">
                    <strong>В исключениях:</strong> Данный секрет был проанализирован и добавлен в исключения как ложное срабатывание или обоснованное использование. 
                    <br><small><strong>Пример:</strong> конфигурационный параметр, тестовые данные, публичный ключ</small>
                </div>
            </div>
        `;
    } else if (secret.status === 'resolved') {
        resolutionBanner = `
            <div class="resolution-banner">
                <div class="icon">⚠️</div>
                <div class="text">
                    <strong>Требует внимания:</strong> Данный секрет был подтвержден ранее, но не обнаружен в последних сканированиях. 
                    <br><small><strong>Возможные причины:</strong> удален разработчиками, переименована переменная, изменен формат</small>
                </div>
            </div>
        `;
    } else {
        resolutionBanner = `
            <div style="background: #fee2e2; color: #991b1b; padding: 0.75rem; border-radius: 6px; margin-bottom: 1.5rem; border-left: 4px solid #dc2626;">
                <strong>❌ Активен:</strong> Данный секрет все еще присутствует в текущей версии кода и требует внимания.
                <br><small>Необходимо либо удалить секрет, либо добавить в исключения если это ложное срабатывание.</small>
            </div>
        `;
    }
    
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;
    
    detailPanel.innerHTML = `
        <div class="detail-content">
            ${resolutionBanner}
            
            <div class="detail-section">
                <h4>🔑 Последнее выявленное значение секрета</h4>
                <div class="detail-field" style="background: #fef3c7; border: 1px solid #f59e0b; color: #92400e; font-weight: 600;">
                    ${safeHtml(secret.current_secret || 'Значение недоступно')}
                </div>
            </div>
            
            <div class="detail-section">
                <h4>📁 Расположение</h4>
                <div style="margin-bottom: 1rem;">
                    <a href="${fileUrl}" target="_blank" class="detail-field clickable" style="text-decoration: none; color: #059669;">
                        ${safeHtml(secret.path)}
                    </a>
                </div>
                <div style="margin-bottom: 1rem;">
                    <div class="detail-field">
                        <strong>Строка:</strong> ${secret.line}
                    </div>
                </div>
                <div style="font-size: 0.8rem; color: #666; padding: 0.5rem 0;">
                    🔗 Нажмите чтобы открыть в репозитории (строка выделяется при открытии)
                </div>
            </div>
            
            <div class="detail-section">
                <h4>📝 Последний контекст</h4>
                <div class="detail-field" style="white-space: pre-wrap;">
                    ${safeHtml(secret.current_context || 'Нет контекста')}
                </div>
            </div>
            
            <div class="detail-section">
                <h4>🔄 История секрета (с момента первого обнаружения)</h4>
                <div class="timeline-container">
                    <div class="timeline">
                        ${timelineHtml || '<div style="text-align: center; color: #6b7280; padding: 2rem;">Нет данных о истории</div>'}
                    </div>
                </div>
            </div>
            
            <div class="detail-section">
                <h4>📊 Сводная информация</h4>
                <div class="detail-field">
                    <strong>Первое обнаружение:</strong> ${new Date(secret.first_scan_date).toLocaleString('ru-RU')}<br>
                    <strong>Последнее обнаружение:</strong> ${new Date(secret.last_scan_date).toLocaleString('ru-RU')}<br>
                    <strong>Уникальных коммитов:</strong> ${(secret.unique_commits || []).length}
                </div>
            </div>
        </div>
    `;
}

function renderPagination() {
    const totalPages = Math.ceil(filteredSecrets.length / pageSize);
    const startIndex = (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, filteredSecrets.length);

    const paginationInfo = document.getElementById('paginationInfo');
    if (paginationInfo) {
        paginationInfo.textContent = `Показаны ${startIndex}-${endIndex} из ${filteredSecrets.length} секретов`;
    }

    const paginationControls = document.getElementById('paginationControls');
    if (!paginationControls) return;
    
    let controlsHTML = '';

    if (currentPage > 1) {
        controlsHTML += `<button class="pagination-btn" onclick="goToPage(${currentPage - 1})">← Предыдущая</button>`;
    } else {
        controlsHTML += `<button class="pagination-btn disabled">← Предыдущая</button>`;
    }

    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    if (startPage > 1) {
        controlsHTML += `<button class="pagination-btn" onclick="goToPage(1)">1</button>`;
        if (startPage > 2) {
            controlsHTML += `<span style="padding: 0.5rem;">...</span>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        const activeClass = i === currentPage ? 'active' : '';
        controlsHTML += `<button class="pagination-btn ${activeClass}" onclick="goToPage(${i})">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            controlsHTML += `<span style="padding: 0.5rem;">...</span>`;
        }
        controlsHTML += `<button class="pagination-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;
    }

    if (currentPage < totalPages) {
        controlsHTML += `<button class="pagination-btn" onclick="goToPage(${currentPage + 1})">Следующая →</button>`;
    } else {
        controlsHTML += `<button class="pagination-btn disabled">Следующая →</button>`;
    }

    paginationControls.innerHTML = controlsHTML;
}

function goToPage(page) {
    const totalPages = Math.ceil(filteredSecrets.length / pageSize);
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        selectedSecret = null;
        showEmptyDetail();
        updateURL();
        renderTable();
        renderPagination();
    }
}

function changePageSize() {
    pageSize = parseInt(document.getElementById('pageSize').value);
    currentPage = 1;
    selectedSecret = null;
    showEmptyDetail();
    updateURL();
    renderTable();
    renderPagination();
}

function toggleFiltersPanel() {
    const filtersPanel = document.getElementById('filtersPanel');
    const filtersToggleBtn = document.getElementById('filtersToggleBtn');
    
    if (!filtersPanel || !filtersToggleBtn) {
        console.error('Filters panel elements not found');
        return;
    }
    
    isFiltersOpen = !isFiltersOpen;
    
    if (isFiltersOpen) {
        filtersPanel.classList.add('open');
        filtersToggleBtn.textContent = '✖️ Закрыть';
    } else {
        filtersPanel.classList.remove('open');
        filtersToggleBtn.textContent = '🔍 Фильтры';
    }
}

function handleSort(column) {
    const existingSort = sortColumns.find(sort => sort.column === column);
    
    if (existingSort) {
        if (existingSort.direction === 'asc') {
            existingSort.direction = 'desc';
        } else {
            sortColumns = [];
        }
    } else {
        sortColumns = [{ column: column, direction: 'asc' }];
    }
    
    sortSecrets();
    renderTable();
    renderPagination();
    setTimeout(updateSortIndicators, 0);
}

function updateSortIndicators() {
    document.querySelectorAll('.sortable').forEach(header => {
        header.classList.remove('sort-asc', 'sort-desc');
    });
    
    if (sortColumns.length > 0) {
        const sort = sortColumns[0];
        const header = document.querySelector(`[data-sort="${sort.column}"]`);
        if (header) {
            header.classList.add(sort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    }
}

function sortSecrets() {
    if (sortColumns.length === 0) {
        filteredSecrets.sort((a, b) => {
            const dateA = new Date(a.last_scan_date);
            const dateB = new Date(b.last_scan_date);
            return dateB - dateA;
        });
        return;
    }

    filteredSecrets.sort((a, b) => {
        for (let sort of sortColumns) {
            let valueA, valueB;
            
            switch (sort.column) {
                case 'secret':
                    valueA = (a.current_secret || '').toLowerCase();
                    valueB = (b.current_secret || '').toLowerCase();
                    break;
                case 'file':
                    valueA = getFileNameFromPath(a.path).toLowerCase();
                    valueB = getFileNameFromPath(b.path).toLowerCase();
                    break;
                case 'type':
                    valueA = (a.type || '').toLowerCase();
                    valueB = (b.type || '').toLowerCase();
                    break;
                case 'severity':
                    const severityOrder = { 'High': 2, 'Potential': 1 };
                    valueA = severityOrder[a.severity] || 0;
                    valueB = severityOrder[b.severity] || 0;
                    break;
                case 'status':
                    const statusOrder = { 'active': 3, 'resolved': 2, 'refuted': 1 };
                    valueA = statusOrder[a.status] || 0;
                    valueB = statusOrder[b.status] || 0;
                    break;
                case 'history':
                    valueA = (a.unique_commits || []).length;
                    valueB = (b.unique_commits || []).length;
                    break;
                default:
                    continue;
            }
            
            let comparison = 0;
            if (valueA < valueB) comparison = -1;
            else if (valueA > valueB) comparison = 1;
            
            if (comparison !== 0) {
                return sort.direction === 'asc' ? comparison : -comparison;
            }
        }
        return 0;
    });
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page loading...');
    
    // Загружаем данные из атрибутов
    loadDataFromAttributes();
    
    if (!loadSecretsData()) {
        console.error('Failed to load secrets data');
        const tableContainer = document.getElementById('secretsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>Ошибка загрузки данных</h3>
                    <p>Не удалось загрузить данные о секретах. Попробуйте обновить страницу.</p>
                    <button onclick="window.location.reload()" class="btn btn-primary">Обновить страницу</button>
                </div>
            `;
        }
        return;
    }
    
    if (allSecretsData.length === 0) {
        console.log('No secrets found');
        const tableContainer = document.getElementById('secretsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>📭 Секреты не найдены</h3>
                    <p>В истории этого проекта нет секретов.</p>
                </div>
            `;
        }
        return;
    }
    
    console.log('Initializing with', allSecretsData.length, 'secrets');
    console.log('Sample secret:', allSecretsData[0]);
    
    initializeFilters();
    applyFilters();
});

// Close filters panel when clicking outside
document.addEventListener('click', function(e) {
    const filtersPanel = document.getElementById('filtersPanel');
    const filtersToggleBtn = document.getElementById('filtersToggleBtn');
    
    if (isFiltersOpen && 
        !filtersPanel.contains(e.target) && 
        !filtersToggleBtn.contains(e.target)) {
        toggleFiltersPanel();
    }
});

// Initialize page from URL parameters
window.addEventListener('load', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const page = parseInt(urlParams.get('page')) || 1;
    const size = parseInt(urlParams.get('page_size')) || 100;
    
    currentPage = page;
    pageSize = size;
    const pageSizeSelect = document.getElementById('pageSize');
    if (pageSizeSelect) {
        pageSizeSelect.value = size;
    }
});