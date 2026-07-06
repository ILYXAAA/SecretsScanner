let selectedViolations = new Set();
let currentViolation = null;
let lastClickedIndex = -1;
let sortColumns = [];
let allViolations = [];
let filteredViolations = [];
let currentPage = 1;
let pageSize = 2000;
let isFiltersOpen = false;
let activeFilters = {
    status: [],
    blocking: [],
    category: [],
    search: '',
};

let projectRepoUrl = '';
let scanCommit = '';
let hubType = '';

function _decodeHtmlEntities(str) {
    if (!str || typeof str !== 'string') return '';
    const doc = new DOMParser().parseFromString(str, 'text/html');
    return doc.body ? doc.body.textContent : str;
}

function safeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text);
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const str = String(text);
    if (str.includes('&quot;') || str.includes('&lt;') || str.includes('&gt;') || str.includes('&amp;')) {
        return str;
    }
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function getFileNameFromPath(path) {
    if (!path) return '';
    return path.replace(/\\/g, '/').split('/').pop() || '';
}

function loadDataFromAttributes() {
    projectRepoUrl = document.body.dataset.projectRepoUrl || '';
    scanCommit = document.body.dataset.scanCommit || '';
    hubType = document.body.dataset.hubType || '';
}

function loadViolationsData() {
    try {
        const dataElement = document.getElementById('violations-data');
        if (!dataElement) return false;
        const rawData = dataElement.textContent;
        if (!rawData || rawData.trim() === '') return false;
        allViolations = JSON.parse(rawData);
        return true;
    } catch (error) {
        console.error('Error parsing violations data:', error);
        return false;
    }
}

function normalizeViolationPath(path) {
    let normalized = (path || '').replace(/\\/g, '/');
    if (normalized && !normalized.startsWith('/')) {
        normalized = `/${normalized}`;
    }
    return normalized;
}

function normalizeViolations() {
    allViolations.forEach(v => {
        v.path = normalizeViolationPath(_decodeHtmlEntities(v.path));
        v.category = _decodeHtmlEntities(v.category);
        v.language = _decodeHtmlEntities(v.language);
        v.extension = _decodeHtmlEntities(v.extension);
        v.binary_reason = _decodeHtmlEntities(v.binary_reason);
        v.status = _decodeHtmlEntities(v.status);
        v.exception_comment = _decodeHtmlEntities(v.exception_comment);
        v.violation_reasons = (v.violation_reasons || []).map(r => _decodeHtmlEntities(r));
        if (!v.status || v.status === 'null') v.status = 'No status';
        v.blockingLevel = v.is_blocking && !v.is_exception ? 'blocking' : 'non-blocking';
        v.rowSeverity = v.is_blocking && !v.is_exception ? 'high' : 'potential';
    });
}

document.addEventListener('DOMContentLoaded', function () {
    loadDataFromAttributes();

    if (!loadViolationsData()) {
        const tableContainer = document.getElementById('violationsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>Ошибка загрузки данных</h3>
                    <p>Не удалось загрузить данные о нарушениях. Попробуйте обновить страницу.</p>
                    <button onclick="window.location.reload()" class="btn btn-primary">Обновить страницу</button>
                </div>`;
        }
        return;
    }

    if (allViolations.length === 0) {
        const tableContainer = document.getElementById('violationsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>Нарушения не найдены</h3>
                    <p>В этом скане не обнаружено запрещённых файлов.</p>
                </div>`;
        }
        return;
    }

    normalizeViolations();
    initializeFilters();
    applyFiltersSync();
});

function initializeFilters() {
    const uniqueCategories = [...new Set(allViolations.map(v => v.category || 'other'))].sort();
    const categoryFiltersContainer = document.getElementById('categoryFilters');
    if (!categoryFiltersContainer) return;

    categoryFiltersContainer.innerHTML = '';
    uniqueCategories.forEach(category => {
        const div = document.createElement('div');
        div.className = 'checkbox-item';
        const safeId = category.replace(/[^a-zA-Z0-9]/g, '_');
        div.innerHTML = `
            <input type="checkbox" id="category-${safeId}" value="${escapeHtml(category)}" checked onchange="applyFilters()">
            <label for="category-${safeId}">${escapeHtml(category)}</label>`;
        categoryFiltersContainer.appendChild(div);
    });

    const confirmedCb = document.getElementById('status-confirmed');
    const noneCb = document.getElementById('status-none');
    if (confirmedCb) confirmedCb.checked = true;
    if (noneCb) noneCb.checked = true;

    const blockingCb = document.getElementById('blocking-high');
    const nonBlockingCb = document.getElementById('blocking-potential');
    if (blockingCb) blockingCb.checked = true;
    if (nonBlockingCb) nonBlockingCb.checked = true;
}

function applyFiltersFromMain() {
    applyFilters();
}

function applyFiltersSync() {
    activeFilters.status = [];
    activeFilters.blocking = [];
    activeFilters.category = [];
    activeFilters.search = (document.getElementById('violationSearchMain')?.value || '').toLowerCase();

    document.querySelectorAll('#filtersPanel input[type="checkbox"]:checked').forEach(cb => {
        const value = cb.value;
        if (['Confirmed', 'No status', 'Refuted'].includes(value)) {
            activeFilters.status.push(value);
        } else if (['blocking', 'non-blocking'].includes(value)) {
            activeFilters.blocking.push(value);
        }
    });

    document.querySelectorAll('#categoryFilters input[type="checkbox"]:checked').forEach(cb => {
        activeFilters.category.push(cb.value);
    });

    if (
        activeFilters.status.length === 0 ||
        activeFilters.blocking.length === 0 ||
        activeFilters.category.length === 0
    ) {
        filteredViolations = [];
    } else {
        filteredViolations = allViolations.filter(v => {
            const statusMatch = activeFilters.status.includes(v.status);
            const blockingMatch = activeFilters.blocking.includes(v.blockingLevel);
            const categoryMatch = activeFilters.category.includes(v.category || 'other');
            const searchTerm = activeFilters.search;
            const searchMatch = !searchTerm || (
                (v.path && v.path.toLowerCase().includes(searchTerm)) ||
                (v.extension && v.extension.toLowerCase().includes(searchTerm)) ||
                (v.language && v.language.toLowerCase().includes(searchTerm)) ||
                (v.category && v.category.toLowerCase().includes(searchTerm)) ||
                getFileNameFromPath(v.path).toLowerCase().includes(searchTerm)
            );
            return statusMatch && blockingMatch && categoryMatch && searchMatch;
        });
    }

    currentPage = 1;
    selectedViolations.clear();
    showEmptyDetail();
    sortViolations();
    updateStats();
    renderTable();
    renderPagination();
}

function applyFilters() {
    applyFiltersSync();
}

function clearAllFilters() {
    document.querySelectorAll('#filtersPanel input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    const searchInput = document.getElementById('violationSearchMain');
    if (searchInput) searchInput.value = '';
    activeFilters = { status: [], blocking: [], category: [], search: '' };
    applyFilters();
}

function updateStats() {
    const totalCount = filteredViolations.length;
    const blockingCount = filteredViolations.filter(v => v.blockingLevel === 'blocking').length;
    const nonBlockingCount = filteredViolations.filter(v => v.blockingLevel === 'non-blocking').length;

    const totalEl = document.getElementById('totalViolationsCount');
    const highEl = document.getElementById('highViolationsCount');
    const potentialEl = document.getElementById('potentialViolationsCount');

    if (totalEl) totalEl.textContent = totalCount;
    if (highEl) highEl.textContent = blockingCount;
    if (potentialEl) potentialEl.textContent = nonBlockingCount;
}

function renderTable() {
    const tableContainer = document.getElementById('violationsTable');
    if (!tableContainer) return;

    if (filteredViolations.length === 0) {
        tableContainer.innerHTML = `
            <div class="empty-results">
                <h3>No violations found</h3>
                <p>No violations match the current filters.</p>
            </div>`;
        return;
    }

    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, filteredViolations.length);
    const pageItems = filteredViolations.slice(startIndex, endIndex);

    let tableHTML = `
        <table class="secrets-table">
            <thead class="table-header">
                <tr>
                    <th class="sortable" data-sort="path">📁 Path</th>
                    <th class="sortable" data-sort="extension">📎 Extension</th>
                    <th class="sortable" data-sort="category">🏷️ Category</th>
                    <th class="sortable" data-sort="language">🌐 Language</th>
                    <th class="sortable" data-sort="status">📊 Status</th>
                </tr>
            </thead>
            <tbody>`;

    pageItems.forEach((violation, index) => {
        const globalIndex = startIndex + index;
        tableHTML += `
            <tr class="secret-row ${safeHtml(violation.rowSeverity)}" data-violation-id="${violation.id}" data-violation-index="${globalIndex}">
                <td class="path-cell">
                    <span class="secret-file path-truncate" title="${escapeHtml(violation.path)}">${escapeHtml(violation.path)}</span>
                </td>
                <td>
                    <span class="secret-type">${escapeHtml(violation.extension || '')}</span>
                </td>
                <td>
                    <span class="secret-type">${escapeHtml(violation.category || '')}</span>
                </td>
                <td>${escapeHtml(violation.language || '')}</td>
                <td class="status-cell">
                    <div class="secret-status">${getStatusHTML(violation)}</div>
                </td>
            </tr>`;
    });

    tableHTML += '</tbody></table>';
    tableContainer.innerHTML = tableHTML;
    initializeTableEventListeners();
    setTimeout(updateSortIndicators, 0);
}

function getStatusHTML(violation) {
    if (violation.status === 'Confirmed') {
        return '<span class="status-confirmed">✅ Confirmed</span>';
    }
    if (violation.status === 'Refuted') {
        return '<span class="status-refuted">❌ Refuted</span>';
    }
    return '<span class="status-none">⚪ Без статуса</span>';
}

function initializeTableEventListeners() {
    document.querySelectorAll('.secret-row').forEach(row => {
        row.addEventListener('click', function (e) {
            const violationId = parseInt(row.dataset.violationId, 10);
            const globalIndex = parseInt(row.dataset.violationIndex, 10);
            handleViolationClick(e, violationId, globalIndex);
        });
    });

    document.querySelectorAll('.sortable').forEach(header => {
        header.addEventListener('click', function () {
            handleSort(this.dataset.sort);
        });
    });
}

function renderPagination() {
    const totalPages = Math.max(1, Math.ceil(filteredViolations.length / pageSize));
    const startIndex = filteredViolations.length === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, filteredViolations.length);

    const paginationInfo = document.getElementById('paginationInfo');
    if (paginationInfo) {
        paginationInfo.textContent = `Показаны ${startIndex}-${endIndex} из ${filteredViolations.length} нарушений`;
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
        if (startPage > 2) controlsHTML += `<span style="padding: 0.5rem;">...</span>`;
    }

    for (let i = startPage; i <= endPage; i++) {
        const activeClass = i === currentPage ? 'active' : '';
        controlsHTML += `<button class="pagination-btn ${activeClass}" onclick="goToPage(${i})">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) controlsHTML += `<span style="padding: 0.5rem;">...</span>`;
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
    const totalPages = Math.ceil(filteredViolations.length / pageSize) || 1;
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        selectedViolations.clear();
        showEmptyDetail();
        renderTable();
        renderPagination();
    }
}

function changePageSize() {
    pageSize = parseInt(document.getElementById('pageSize').value, 10);
    currentPage = 1;
    selectedViolations.clear();
    showEmptyDetail();
    renderTable();
    renderPagination();
}

function toggleFiltersPanel() {
    const filtersPanel = document.getElementById('filtersPanel');
    const filtersToggleBtn = document.getElementById('filtersToggleBtn');
    if (!filtersPanel || !filtersToggleBtn) return;

    isFiltersOpen = !isFiltersOpen;
    if (isFiltersOpen) {
        filtersPanel.classList.add('open');
        filtersToggleBtn.textContent = '✖️ Закрыть';
    } else {
        filtersPanel.classList.remove('open');
        filtersToggleBtn.textContent = '🔍 Фильтры';
    }
}

function handleViolationClick(e, violationId, index) {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
        toggleMultiSelection(violationId, index);
        return;
    }
    if (e.shiftKey && lastClickedIndex !== -1 && selectedViolations.size > 0) {
        selectRange(lastClickedIndex, index);
        return;
    }
    clearMultiSelection();
    selectSingleViolation(violationId, index);
}

function toggleMultiSelection(violationId, index) {
    const row = document.querySelector(`[data-violation-id="${violationId}"]`);
    if (!row) return;

    if (selectedViolations.has(violationId)) {
        selectedViolations.delete(violationId);
        row.classList.remove('multi-selected', 'selected');
    } else {
        selectedViolations.add(violationId);
        row.classList.remove('selected');
        row.classList.add('multi-selected');
    }
    lastClickedIndex = index;
    updateSelectionView();
}

function selectRange(startIndex, endIndex) {
    const start = Math.min(startIndex, endIndex);
    const end = Math.max(startIndex, endIndex);
    const pageStartIndex = (currentPage - 1) * pageSize;
    const pageEndIndex = Math.min(pageStartIndex + pageSize, filteredViolations.length);

    for (let i = start; i <= end; i++) {
        if (i >= pageStartIndex && i < pageEndIndex) {
            const violation = filteredViolations[i];
            if (!violation) continue;
            const row = document.querySelector(`[data-violation-id="${violation.id}"]`);
            if (row) {
                selectedViolations.add(violation.id);
                row.classList.add('multi-selected');
                row.classList.remove('selected');
            }
        }
    }
    lastClickedIndex = endIndex;
    updateSelectionView();
}

function selectSingleViolation(violationId, index) {
    clearMultiSelection();
    const row = document.querySelector(`[data-violation-id="${violationId}"]`);
    if (!row) return;
    row.classList.add('selected');
    selectedViolations.add(violationId);
    currentViolation = violationId;
    lastClickedIndex = index;
    loadViolationDetails(violationId);
}

function clearMultiSelection() {
    selectedViolations.clear();
    document.querySelectorAll('.secret-row').forEach(row => {
        row.classList.remove('selected', 'multi-selected');
    });
}

function updateSelectionView() {
    if (selectedViolations.size > 1) {
        showBulkDetail();
    } else if (selectedViolations.size === 1) {
        loadViolationDetails(Array.from(selectedViolations)[0]);
    } else {
        showEmptyDetail();
    }
}

function showBulkDetail() {
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;

    detailPanel.innerHTML = `
        <div class="bulk-detail-panel">
            <h3 class="bulk-title">📌 Выбрано файлов: <span class="bulk-count">${selectedViolations.size}</span></h3>
            <div class="bulk-section">
                <button class="bulk-btn select-all-btn" onclick="selectAllVisibleViolations()">
                    ✅ Выделить все на странице
                </button>
            </div>
            <div class="bulk-section status-panel">
                <h4>📊 Изменение статуса</h4>
                <div class="bulk-buttons status-buttons">
                    <button class="bulk-btn status-confirmed-btn" onclick="performBulkAction('status', 'Confirmed')">
                        ✅ Подтвердить
                    </button>
                    <button class="bulk-btn status-none-btn" onclick="performBulkAction('status', 'No status')">
                        ⚪ Без статуса
                    </button>
                    <button class="bulk-btn status-refuted-btn" onclick="performBulkAction('status', 'Refuted')">
                        ❌ Опровергнуть
                    </button>
                </div>
            </div>
            <div class="bulk-section">
                <button class="bulk-btn btn-secondary" onclick="clearMultiSelection(); showEmptyDetail();" style="width: 100%;">
                    ❌ Отменить выделение
                </button>
            </div>
        </div>`;
}

function showEmptyDetail() {
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;

    detailPanel.innerHTML = `
        <div class="detail-empty">
            <div style="text-align: center; padding: 2rem;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">👈</div>
                <h3>Выберите файл, чтобы просмотреть подробную информацию</h3>
                <p>Нажмите на любой файл из списка, чтобы просмотреть подробную информацию, управлять его статусом и получить доступ к расположению файла.</p>
                <div style="margin-top: 2rem; padding: 1rem; background: #f0f9ff; border-radius: 8px; border-left: 4px solid #3b82f6;">
                    <strong>💡 Совет:</strong> Используйте <kbd>Ctrl</kbd> для выделения нескольких файлов или <kbd>Shift</kbd> для выделения диапазона.
                </div>
            </div>
        </div>`;
}

function selectAllVisibleViolations() {
    document.querySelectorAll('.secret-row').forEach(row => {
        const violationId = parseInt(row.dataset.violationId, 10);
        selectedViolations.add(violationId);
        row.classList.add('multi-selected');
        row.classList.remove('selected');
    });
    showBulkDetail();
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
        sortColumns = [{ column, direction: 'asc' }];
    }
    sortViolations();
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

function sortViolations() {
    if (sortColumns.length === 0) {
        filteredViolations.sort((a, b) => (a.path || '').localeCompare(b.path || ''));
        return;
    }

    filteredViolations.sort((a, b) => {
        for (const sort of sortColumns) {
            let valueA;
            let valueB;
            switch (sort.column) {
                case 'path':
                    valueA = (a.path || '').toLowerCase();
                    valueB = (b.path || '').toLowerCase();
                    break;
                case 'extension':
                    valueA = (a.extension || '').toLowerCase();
                    valueB = (b.extension || '').toLowerCase();
                    break;
                case 'category':
                    valueA = (a.category || '').toLowerCase();
                    valueB = (b.category || '').toLowerCase();
                    break;
                case 'language':
                    valueA = (a.language || '').toLowerCase();
                    valueB = (b.language || '').toLowerCase();
                    break;
                case 'status': {
                    const statusOrder = { Confirmed: 3, 'No status': 2, Refuted: 1 };
                    valueA = statusOrder[a.status] || 0;
                    valueB = statusOrder[b.status] || 0;
                    break;
                }
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

function formatFileSize(bytes) {
    if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return '—';
    const size = Number(bytes);
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function buildFileUrl(violation) {
    try {
        if (projectRepoUrl.includes('devzone.local')) {
            return `${projectRepoUrl}/-/blob/${scanCommit}/${encodeURIComponent(violation.path || '')}`;
        }
        if (hubType === 'Azure') {
            return `${projectRepoUrl}?path=${encodeURIComponent(violation.path || '')}&version=GC${scanCommit}&_a=contents`;
        }
        const safePath = (violation.path || '').split('/').map(encodeURIComponent).join('/');
        return `${projectRepoUrl}/blob/${scanCommit}${safePath}?plain=1`;
    } catch (error) {
        console.error('Error building file URL:', error);
        return '#';
    }
}

function loadViolationDetails(violationId) {
    const violation = allViolations.find(v => v.id === violationId);
    if (!violation) return;

    const fileUrl = buildFileUrl(violation);
    const safePath = safeHtml(violation.path || '');
    const safeComment = safeHtml(violation.exception_comment || '');
    const safeHash = escapeHtml(violation.hash_from_ci || '');
    const reasonsHtml = (violation.violation_reasons || [])
        .map(r => `• ${escapeHtml(r)}`)
        .join('<br>') || '—';
    const binaryText = violation.is_binary
        ? `да${violation.binary_reason ? ` (${escapeHtml(violation.binary_reason)})` : ''}`
        : 'нет';

    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;

    detailPanel.innerHTML = `
        <div class="detail-content">
            <h3>Violation Details</h3>

            <div class="detail-section">
                <h4>📁 Path</h4>
                <a href="${fileUrl}" target="_blank" class="detail-field clickable path-truncate" style="display: block; text-decoration: none; color: inherit;" title="${escapeHtml(violation.path || '')}">
                    ${safePath}
                </a>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Нажмите чтобы открыть в репозитории
                </div>
            </div>

            <div class="status-controls">
                <h4 style="margin-bottom: 8px;">Статус</h4>
                <div class="status-buttons">
                    <button class="status-btn ${violation.status === 'Confirmed' ? 'active' : ''}"
                            onclick="updateViolationStatus(${violationId}, 'Confirmed')">
                        ✅ Подтвердить
                    </button>
                    <button class="status-btn ${violation.status === 'No status' ? 'active' : ''}"
                            onclick="updateViolationStatus(${violationId}, 'No status')">
                        ⚪ Без статуса
                    </button>
                    <button class="status-btn ${violation.status === 'Refuted' ? 'active' : ''}"
                            onclick="updateViolationStatus(${violationId}, 'Refuted')">
                        ❌ Опровергнуть
                    </button>
                </div>
                <div class="comment-section" style="display: ${violation.status === 'Refuted' ? 'block' : 'none'};">
                    <label for="comment-${violationId}">Комментарий:</label>
                    <textarea id="comment-${violationId}" placeholder="Explain why this is not a violation...">${safeComment}</textarea>
                    <button class="btn btn-primary" style="margin-top: 0.5rem; font-size: 0.8rem;"
                            onclick="updateViolationStatus(${violationId}, 'Refuted')">
                        💾 Update Comment
                    </button>
                </div>
            </div>

            <div class="detail-section">
                <h4>📝 Причины нарушения</h4>
                <div class="detail-field" style="white-space: pre-wrap;">${reasonsHtml}</div>
            </div>

            <div class="detail-section">
                <h4>📦 Размер файла</h4>
                <div class="detail-field">${formatFileSize(violation.size)}</div>
            </div>

            <div class="detail-section">
                <h4>🧩 Binary</h4>
                <div class="detail-field">${binaryText}</div>
            </div>

            <div class="detail-section">
                <h4>⚠️ Уровень</h4>
                <div class="secret-severity ${violation.rowSeverity}">
                    ${violation.blockingLevel === 'blocking' ? 'Blocking' : 'Non-blocking'}
                </div>
            </div>

            <div class="detail-section">
                <h4>📎 Extension</h4>
                <div class="detail-field">${escapeHtml(violation.extension || '—')}</div>
            </div>

            <div class="detail-section">
                <h4>🏷️ Category</h4>
                <div class="detail-field">${escapeHtml(violation.category || '—')}</div>
            </div>

            <div class="detail-section">
                <h4>🌐 Language</h4>
                <div class="detail-field">${escapeHtml(violation.language || '—')}</div>
            </div>

            <div class="detail-section">
                <h4>🔐 CI Hash</h4>
                <div class="detail-field hash-field" style="font-family: monospace; font-size: 0.75rem; word-break: break-all; user-select: all;">
                    ${safeHash || '—'}
                </div>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Хеш для CI (language_search_falses.txt): repo_suffix + relative_path
                </div>
            </div>
        </div>`;
}

async function updateViolationStatus(violationId, status) {
    const comment = document.getElementById(`comment-${violationId}`)?.value || '';
    try {
        const response = await fetch(`/secret_scanner/forbidden-violations/${violationId}/update-status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ status, comment }),
        });
        if (!response.ok) {
            alert('Error updating status');
            return;
        }

        const violation = allViolations.find(v => v.id === violationId);
        if (violation) {
            violation.status = status;
            violation.exception_comment = status === 'Refuted' ? comment : '';
            violation.is_exception = status === 'Refuted';
            violation.blockingLevel = violation.is_blocking && !violation.is_exception ? 'blocking' : 'non-blocking';
            violation.rowSeverity = violation.is_blocking && !violation.is_exception ? 'high' : 'potential';
        }

        applyFiltersSync();
        loadViolationDetails(violationId);
    } catch (error) {
        console.error('Error updating status:', error);
        alert('Error updating status');
    }
}

async function performBulkAction(action, value) {
    const comment = '';
    try {
        const response = await fetch('/secret_scanner/forbidden-violations/bulk-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                violation_ids: [...selectedViolations],
                action,
                value,
                comment,
            }),
        });
        if (!response.ok) {
            alert('Error performing bulk action');
            return;
        }

        selectedViolations.forEach(violationId => {
            const violation = allViolations.find(v => v.id === violationId);
            if (!violation || action !== 'status') return;
            violation.status = value;
            violation.is_exception = value === 'Refuted';
            violation.blockingLevel = violation.is_blocking && !violation.is_exception ? 'blocking' : 'non-blocking';
            violation.rowSeverity = violation.is_blocking && !violation.is_exception ? 'high' : 'potential';
        });

        selectedViolations.clear();
        showEmptyDetail();
        applyFiltersSync();
    } catch (error) {
        console.error('Error performing bulk action:', error);
        alert('Error performing bulk action');
    }
}
