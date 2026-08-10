let allSecrets = [];
let allSecretsData = [];
let filteredSecrets = [];
let currentPage = 1;
let pageSize = 100;
let isFiltersOpen = false;
let sortColumns = [];
let selectedSecret = null;
let filtersToggleBtnClosedHtml = '';
let filtersToggleBtnOpenHtml = '';
let emptyDetailHtml = '';
let activeFilters = {
    status: ['refuted', 'resolved', 'active'],
    severity: ['High', 'Potential'],
    type: [],
    search: '',
};

let projectRepoUrl = '';
let latestCommit = '';
let hubType = '';

function getFileNameFromPath(path) {
    if (!path) return '';
    return path.replace(/\\/g, '/').split('/').pop() || '';
}

function loadDataFromAttributes() {
    projectRepoUrl = document.body.dataset.projectRepoUrl || '';
    latestCommit = document.body.dataset.latestCommit || '';
    hubType = document.body.dataset.hubType || '';
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function safeHtml(text) {
    return escapeHtml(text);
}

function getHistoryStatusHtml(status) {
    if (status === 'refuted') {
        return `<span class="status-refuted status-with-icon">${uiIcon('CheckboxCheckedFilled.svg', 'icon-tint-success', 14)}<span>Refuted</span></span>`;
    }
    if (status === 'resolved') {
        return `<span class="status-resolved status-with-icon">${uiIcon('CloudAlerting.svg', 'icon-tint-warn', 14)}<span>Resolved</span></span>`;
    }
    return `<span class="status-active status-with-icon">${uiIcon('Error.svg', 'icon-tint-error', 14)}<span>Active</span></span>`;
}

function loadSecretsData() {
    try {
        const allDataElement = document.getElementById('secrets-all-data');
        if (!allDataElement) return false;

        allSecretsData = JSON.parse(allDataElement.textContent);
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
    if (!typeFiltersContainer) return;

    typeFiltersContainer.innerHTML = '';
    uniqueTypes.forEach(type => {
        const div = document.createElement('div');
        div.className = 'checkbox-item';
        const safeId = type.replace(/[^a-zA-Z0-9]/g, '_');
        div.innerHTML = `
            <input type="checkbox" id="type-${safeId}" value="${safeHtml(type)}" onchange="applyFilters()" checked>
            <label for="type-${safeId}">${safeHtml(type)}</label>`;
        typeFiltersContainer.appendChild(div);
    });

    activeFilters.type = uniqueTypes.slice();
}

function applyFilters() {
    activeFilters.status = [];
    activeFilters.severity = [];
    activeFilters.type = [];
    activeFilters.search = document.getElementById('searchInput')?.value?.toLowerCase() || '';

    const showUnconfirmed = document.getElementById('showAllSecrets')?.checked || false;

    if (document.getElementById('status-refuted')?.checked) activeFilters.status.push('refuted');
    if (document.getElementById('status-resolved')?.checked) activeFilters.status.push('resolved');
    if (document.getElementById('status-active')?.checked) activeFilters.status.push('active');
    if (document.getElementById('severity-high')?.checked) activeFilters.severity.push('High');
    if (document.getElementById('severity-potential')?.checked) activeFilters.severity.push('Potential');

    document.querySelectorAll('#typeFilters input[type="checkbox"]:checked').forEach(cb => {
        activeFilters.type.push(cb.value);
    });

    filteredSecrets = allSecrets.filter(secret => {
        if (activeFilters.search && !secret.current_secret.toLowerCase().includes(activeFilters.search)) {
            return false;
        }
        if (!showUnconfirmed && !secret.has_confirmed) {
            return false;
        }
        if (secret.status && !activeFilters.status.includes(secret.status)) {
            return false;
        }
        if (!activeFilters.severity.includes(secret.severity)) {
            return false;
        }
        if (!activeFilters.type.includes(secret.type)) {
            return false;
        }
        return true;
    });

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
    if (searchInput) searchInput.value = '';
    applyFilters();
}

function updateStats() {
    const totalEl = document.getElementById('totalCount');
    const filteredEl = document.getElementById('filteredCount');
    if (totalEl) totalEl.textContent = allSecrets.length;
    if (filteredEl) filteredEl.textContent = filteredSecrets.length;
}

function updateURL() {
    const params = new URLSearchParams();
    params.set('page', currentPage);
    params.set('page_size', pageSize);
    history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
}

function renderTable() {
    const tableContainer = document.getElementById('secretsTable');

    if (filteredSecrets.length === 0) {
        tableContainer.innerHTML = `
            <div class="empty-results">
                <h3>Нет секретов</h3>
                <p>Нет секретов, соответствующих текущим фильтрам.</p>
            </div>`;
        return;
    }

    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, filteredSecrets.length);
    const pageSecrets = filteredSecrets.slice(startIndex, endIndex);

    let tableHTML = `
        <table class="secrets-table">
            <thead class="table-header">
                <tr>
                    <th class="sortable" data-sort="secret">${uiTh('LockPassword.svg', 'icon-tint-muted', 'Secret')}</th>
                    <th class="sortable file-col" data-sort="file">${uiTh('Files.svg', 'icon-tint-muted', 'File')}</th>
                    <th class="sortable" data-sort="type">${uiTh('ReviewCheckmark.svg', 'icon-tint-muted', 'Type')}</th>
                    <th class="sortable" data-sort="severity">${uiTh('AlertErrorStroke16.svg', 'icon-tint-muted', 'Severity')}</th>
                    <th class="sortable" data-sort="status">${uiTh('Analysis.svg', 'icon-tint-muted', 'Status')}</th>
                    <th class="sortable" data-sort="history">${uiTh('BaselineHistory.svg', 'icon-tint-muted', 'История')}</th>
                </tr>
            </thead>
            <tbody>`;

    pageSecrets.forEach((secret, index) => {
        const globalIndex = startIndex + index;
        const commitsCount = (secret.unique_commits || []).length;
        const commitsLabel = `${commitsCount} коммит${commitsCount !== 1 ? 'ов' : ''}`;

        tableHTML += `
            <tr class="secret-row" data-secret-id="${secret.id}" data-secret-index="${globalIndex}">
                <td>
                    <div class="secret-value">${safeHtml(secret.current_secret)}</div>
                </td>
                <td class="file-cell">
                    <span class="secret-file path-truncate" title="${escapeHtml(secret.path || '')}">${safeHtml(getFileNameFromPath(secret.path))}</span>
                    <div class="secret-line">Line ${secret.line}</div>
                </td>
                <td>
                    <span class="secret-type">${safeHtml(secret.type)}</span>
                </td>
                <td>
                    <div class="secret-severity ${(secret.severity || '').toLowerCase()}">${safeHtml(secret.severity)}</div>
                </td>
                <td class="status-cell">
                    <div class="resolved-status">${getHistoryStatusHtml(secret.status)}</div>
                </td>
                <td>
                    <div class="scan-info">
                        <div class="scan-id">${commitsLabel}</div>
                    </div>
                </td>
            </tr>`;
    });

    tableHTML += '</tbody></table>';
    tableContainer.innerHTML = tableHTML;
    initializeTableEventListeners();
    setTimeout(updateSortIndicators, 0);
}

function initializeTableEventListeners() {
    document.querySelectorAll('.secret-row').forEach(row => {
        row.addEventListener('click', () => {
            selectSecret(parseInt(row.dataset.secretId, 10));
        });
    });

    document.querySelectorAll('.sortable').forEach(header => {
        header.addEventListener('click', function () {
            handleSort(this.dataset.sort);
        });
    });
}

function selectSecret(secretId) {
    document.querySelectorAll('.secret-row').forEach(row => row.classList.remove('selected'));
    const row = document.querySelector(`[data-secret-id="${secretId}"]`);
    if (!row) return;
    row.classList.add('selected');
    selectedSecret = secretId;
    showSecretDetails(secretId);
}

function showEmptyDetail() {
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;
    detailPanel.innerHTML = emptyDetailHtml || '';
}

function buildResolutionBanner(secret) {
    if (secret.status === 'refuted') {
        return `
            <div class="resolution-banner refuted">
                <span class="resolution-banner-icon">${uiIcon('AddShieldHalf.svg', 'icon-tint-success', 22)}</span>
                <div class="resolution-banner-text">
                    <strong>В исключениях</strong>
                    Секрет проанализирован и добавлен в исключения как ложное срабатывание или обоснованное использование.
                    <small>Пример: конфигурационный параметр, тестовые данные, публичный ключ</small>
                </div>
            </div>`;
    }
    if (secret.status === 'resolved') {
        return `
            <div class="resolution-banner resolved">
                <span class="resolution-banner-icon">${uiIcon('CloudAlerting.svg', 'icon-tint-warn', 22)}</span>
                <div class="resolution-banner-text">
                    <strong>Требует внимания</strong>
                    Секрет был подтверждён ранее, но не обнаружен в последних сканированиях.
                    <small>Возможные причины: удалён, переименована переменная, изменён формат</small>
                </div>
            </div>`;
    }
    return `
        <div class="resolution-banner active">
            <span class="resolution-banner-icon">${uiIcon('Error.svg', 'icon-tint-error', 22)}</span>
            <div class="resolution-banner-text">
                <strong>Активен</strong>
                Секрет всё ещё присутствует в текущей версии кода и требует внимания.
                <small>Необходимо удалить секрет или добавить в исключения, если это ложное срабатывание</small>
            </div>
        </div>`;
}

function showSecretDetails(secretId) {
    const secret = allSecrets.find(s => s.id === secretId);
    if (!secret) return;

    let fileUrl = '#';
    try {
        if (projectRepoUrl && projectRepoUrl.includes('devzone.local')) {
            fileUrl = `${projectRepoUrl}/-/blob/${latestCommit || 'main'}/${encodeURIComponent(secret.path)}#L${secret.line}-${secret.line}`;
        } else if (hubType === 'Azure') {
            const secretLength = secret.current_secret ? secret.current_secret.length : 0;
            fileUrl = `${projectRepoUrl}?path=${encodeURIComponent(secret.path)}&version=GC${latestCommit || 'main'}&line=${secret.line}&lineEnd=${secret.line}&lineStartColumn=1&lineEndColumn=${secretLength + 1}&_a=contents`;
        } else if (projectRepoUrl) {
            const safePath = secret.path.split('/').map(encodeURIComponent).join('/');
            fileUrl = `${projectRepoUrl}/blob/${latestCommit || 'main'}${safePath}?plain=1#L${secret.line}`;
        }
    } catch (error) {
        console.error('Error building file URL:', error);
    }

    let filteredTimeline = [];
    if (secret.timeline && secret.timeline.length > 0) {
        const sortedTimeline = secret.timeline.slice().sort((a, b) => new Date(a.scan_date) - new Date(b.scan_date));
        const firstDetectionIndex = sortedTimeline.findIndex(item => item.found_secret);
        filteredTimeline = firstDetectionIndex !== -1
            ? sortedTimeline.slice(firstDetectionIndex)
            : sortedTimeline;
    }

    const timelineHtml = filteredTimeline.length > 0
        ? filteredTimeline.map(item => buildTimelineItem(item, secret)).join('')
        : '<div class="detail-empty" style="padding: 2rem 1rem;">Нет данных о истории</div>';

    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;

    detailPanel.innerHTML = `
        <div class="detail-content">
            ${buildResolutionBanner(secret)}

            <div class="detail-section">
                ${uiDetailHeading('LockPassword.svg', 'icon-tint-warn', 'Последнее выявленное значение')}
                <div class="detail-field detail-field-secret">${safeHtml(secret.current_secret || 'Значение недоступно')}</div>
            </div>

            <div class="detail-section">
                ${uiDetailHeading('Files.svg', 'icon-tint-muted', 'Расположение')}
                <a href="${fileUrl}" target="_blank" rel="noopener noreferrer" class="detail-field clickable path-truncate">${safeHtml(secret.path)}</a>
                <div class="detail-field" style="margin-top: 0.5rem;">
                    <strong>Строка:</strong> ${secret.line}
                </div>
                <div class="detail-hint">Нажмите путь, чтобы открыть в репозитории</div>
            </div>

            <div class="detail-section">
                ${uiDetailHeading('Files.svg', 'icon-tint-muted', 'Последний контекст')}
                <div class="detail-field detail-field-prose">${safeHtml(secret.current_context || 'Нет контекста')}</div>
            </div>

            <div class="detail-section">
                ${uiDetailHeading('BaselineHistory.svg', 'icon-tint-info', 'История (с первого обнаружения)')}
                <div class="timeline-container">
                    <div class="timeline">${timelineHtml}</div>
                </div>
            </div>

            <div class="detail-section">
                ${uiDetailHeading('AppDashboard.svg', 'icon-tint-muted', 'Сводная информация')}
                <div class="detail-field detail-field-prose">
                    <strong>Первое обнаружение:</strong> ${new Date(secret.first_scan_date).toLocaleString('ru-RU')}<br>
                    <strong>Последнее обнаружение:</strong> ${new Date(secret.last_scan_date).toLocaleString('ru-RU')}<br>
                    <strong>Уникальных коммитов:</strong> ${(secret.unique_commits || []).length}
                </div>
            </div>
        </div>`;
}

function buildTimelineItem(item, secret) {
    const date = new Date(item.scan_date).toLocaleString('ru-RU');
    const statusClass = item.status.toLowerCase().replace(' ', '-');

    let statusDisplay = 'Обнаружен';
    if (item.status === 'Confirmed') statusDisplay = 'Подтвержден';
    else if (item.status === 'Refuted') statusDisplay = 'В исключениях';
    else if (item.status === 'Not Found') statusDisplay = 'Не найден';

    let userInfo = '';
    if (item.status === 'Confirmed' && item.confirmed_by) {
        userInfo = `<div class="timeline-user-external">👤 ${safeHtml(item.confirmed_by)}</div>`;
    } else if (item.status === 'Refuted' && item.refuted_by) {
        userInfo = `<div class="timeline-user-external">👤 ${safeHtml(item.refuted_by)}</div>`;
    }

    const commentHtml = item.exception_comment
        ? `<div class="timeline-comment">💬 ${safeHtml(item.exception_comment)}</div>`
        : '';

    const scanBtn = `<a href="/secret_scanner/scan/${item.scan_id}/results" target="_blank" rel="noopener noreferrer" class="timeline-btn scan">📊 Скан</a>`;

    let compareBtn = '';
    if (latestCommit && item.commit && item.commit !== latestCommit && projectRepoUrl) {
        let compareUrl = '#';
        try {
            if (hubType === 'Azure') {
                compareUrl = `${projectRepoUrl}?_a=compare&path=${encodeURIComponent(secret.path)}&mversion=GC${item.commit}&oversion=GC${latestCommit}`;
            } else if (projectRepoUrl.includes('github.com')) {
                compareUrl = `${projectRepoUrl}/compare/${item.commit}...${latestCommit}`;
            }
        } catch (error) {
            console.error('Error building compare URL:', error);
        }
        if (compareUrl !== '#') {
            compareBtn = `<a href="${compareUrl}" target="_blank" rel="noopener noreferrer" class="timeline-btn compare">🔗 Сравнить с текущим</a>`;
        }
    }

    let contentHtml;
    if (item.found_secret) {
        contentHtml = `
            <div class="timeline-content">
                <div class="timeline-secret">🔑 ${safeHtml(item.secret_value)}</div>
                <div class="timeline-commit">🔗 ${safeHtml(item.commit || 'unknown')}</div>
            </div>`;
    } else {
        contentHtml = `
            <div class="timeline-content">
                <div class="timeline-secret muted">🔍 Секрет не обнаружен в этом скане</div>
                <div class="timeline-commit">🔗 ${safeHtml(item.commit || 'unknown')}</div>
                <div class="timeline-rename-hint">
                    ⚠️ <strong>Возможное переименование:</strong> Секрет мог быть переименован (например, SECRET → VARIABLE), но значение осталось тем же.
                </div>
            </div>`;
    }

    return `
        <div class="timeline-item status-${statusClass}">
            <div class="timeline-date-badge">
                <div class="timeline-date-external">📅 ${date}</div>
                ${userInfo}
            </div>
            <div class="timeline-header">
                <div class="timeline-status ${statusClass}">${statusDisplay}</div>
            </div>
            ${contentHtml}
            ${commentHtml}
            <div class="timeline-actions">${scanBtn}${compareBtn}</div>
        </div>`;
}

function renderPagination() {
    const totalPages = Math.max(1, Math.ceil(filteredSecrets.length / pageSize));
    const startIndex = filteredSecrets.length === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, filteredSecrets.length);

    const paginationInfo = document.getElementById('paginationInfo');
    if (paginationInfo) {
        paginationInfo.textContent = `Показаны ${startIndex}-${endIndex} из ${filteredSecrets.length} секретов`;
    }

    const paginationControls = document.getElementById('paginationControls');
    if (!paginationControls) return;

    let controlsHTML = '';
    if (currentPage > 1) {
        controlsHTML += `<button type="button" class="pagination-btn" onclick="goToPage(${currentPage - 1})">← Предыдущая</button>`;
    } else {
        controlsHTML += `<button type="button" class="pagination-btn disabled">← Предыдущая</button>`;
    }

    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    if (startPage > 1) {
        controlsHTML += `<button type="button" class="pagination-btn" onclick="goToPage(1)">1</button>`;
        if (startPage > 2) controlsHTML += `<span class="pagination-ellipsis">...</span>`;
    }

    for (let i = startPage; i <= endPage; i++) {
        controlsHTML += `<button type="button" class="pagination-btn ${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) controlsHTML += `<span class="pagination-ellipsis">...</span>`;
        controlsHTML += `<button type="button" class="pagination-btn" onclick="goToPage(${totalPages})">${totalPages}</button>`;
    }

    if (currentPage < totalPages) {
        controlsHTML += `<button type="button" class="pagination-btn" onclick="goToPage(${currentPage + 1})">Следующая →</button>`;
    } else {
        controlsHTML += `<button type="button" class="pagination-btn disabled">Следующая →</button>`;
    }

    paginationControls.innerHTML = controlsHTML;
}

function goToPage(page) {
    const totalPages = Math.ceil(filteredSecrets.length / pageSize) || 1;
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
    pageSize = parseInt(document.getElementById('pageSize').value, 10);
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
    if (!filtersPanel || !filtersToggleBtn) return;

    isFiltersOpen = !isFiltersOpen;
    if (isFiltersOpen) {
        filtersPanel.classList.add('open');
        filtersToggleBtn.innerHTML = filtersToggleBtnOpenHtml;
    } else {
        filtersPanel.classList.remove('open');
        filtersToggleBtn.innerHTML = filtersToggleBtnClosedHtml;
    }
}

function handleSort(column) {
    const existingSort = sortColumns.find(sort => sort.column === column);
    if (existingSort) {
        if (existingSort.direction === 'asc') existingSort.direction = 'desc';
        else sortColumns = [];
    } else {
        sortColumns = [{ column, direction: 'asc' }];
    }

    sortSecrets();
    renderTable();
    renderPagination();
    setTimeout(updateSortIndicators, 0);
}

function updateSortIndicators() {
    document.querySelectorAll('.sortable').forEach(header => header.classList.remove('sort-asc', 'sort-desc'));
    if (sortColumns.length > 0) {
        const sort = sortColumns[0];
        const header = document.querySelector(`[data-sort="${sort.column}"]`);
        if (header) header.classList.add(sort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
    }
}

function sortSecrets() {
    if (sortColumns.length === 0) {
        filteredSecrets.sort((a, b) => new Date(b.last_scan_date) - new Date(a.last_scan_date));
        return;
    }

    filteredSecrets.sort((a, b) => {
        for (const sort of sortColumns) {
            let valueA;
            let valueB;

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
                case 'severity': {
                    const severityOrder = { High: 2, Potential: 1 };
                    valueA = severityOrder[a.severity] || 0;
                    valueB = severityOrder[b.severity] || 0;
                    break;
                }
                case 'status': {
                    const statusOrder = { active: 3, resolved: 2, refuted: 1 };
                    valueA = statusOrder[a.status] || 0;
                    valueB = statusOrder[b.status] || 0;
                    break;
                }
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

document.addEventListener('DOMContentLoaded', () => {
    const filtersToggleBtn = document.getElementById('filtersToggleBtn');
    if (filtersToggleBtn) {
        filtersToggleBtnClosedHtml = filtersToggleBtn.innerHTML;
        filtersToggleBtnOpenHtml = `${uiIcon('Error.svg', 'btn-icon icon-tint-error', 14)}<span>Закрыть</span>`;
    }

    const detailPanel = document.getElementById('detailPanel');
    if (detailPanel) emptyDetailHtml = detailPanel.innerHTML;

    loadDataFromAttributes();

    if (!loadSecretsData()) {
        const tableContainer = document.getElementById('secretsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>Ошибка загрузки данных</h3>
                    <p>Не удалось загрузить данные о секретах. Попробуйте обновить страницу.</p>
                    <button type="button" onclick="window.location.reload()" class="btn btn-primary">Обновить страницу</button>
                </div>`;
        }
        return;
    }

    if (allSecretsData.length === 0) {
        const tableContainer = document.getElementById('secretsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>Секреты не найдены</h3>
                    <p>В истории этого проекта нет секретов.</p>
                </div>`;
        }
        return;
    }

    initializeFilters();
    applyFilters();
});

document.addEventListener('click', (e) => {
    const filtersPanel = document.getElementById('filtersPanel');
    const filtersToggleBtn = document.getElementById('filtersToggleBtn');
    if (isFiltersOpen && filtersPanel && filtersToggleBtn
        && !filtersPanel.contains(e.target) && !filtersToggleBtn.contains(e.target)) {
        toggleFiltersPanel();
    }
});

window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    currentPage = parseInt(urlParams.get('page'), 10) || 1;
    pageSize = parseInt(urlParams.get('page_size'), 10) || 100;
    const pageSizeSelect = document.getElementById('pageSize');
    if (pageSizeSelect) pageSizeSelect.value = String(pageSize);
});
