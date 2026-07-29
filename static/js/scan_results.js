// Global variables
let selectedSecrets = new Set();
let currentSecret = null;
let lastClickedIndex = -1;
let sortColumns = [];
let allSecrets = [];
let filteredSecrets = [];
let currentPage = 1;
let pageSize = 2000;
let isFiltersOpen = false;
let activeFilters = {
    status: [],
    severity: [],
    type: [],
    secretValue: ''
};

// Server-side data - БЕЗОПАСНАЯ загрузка через data-атрибуты
let secretsData = [];
let projectRepoUrl = '';
let scanCommit = '';
let hubType = '';

// Ограничение контекста в деталях: окно вокруг секрета (строк до/после), полный контекст — в модалке
const CONTEXT_PREVIEW_LINES_BEFORE = 2;
const CONTEXT_PREVIEW_LINES_AFTER = 2;
const CONTEXT_PREVIEW_MAX_LINES = 15;  // макс. строк в превью, если секрет не найден
const CONTEXT_PREVIEW_MAX_CHARS = 500;

function getFileNameFromPath(path) {
    if (!path) return '';
    return path.replace(/\\/g, '/').split('/').pop() || '';
}

/** Превью контекста: окно вокруг строки с секретом (по подстроке или по середине блока). Секрет всегда в видимой части. */
function truncateContextAroundSecret(rawContext, rawSecret) {
    if (!rawContext || typeof rawContext !== 'string') return { text: '', hasMore: false };
    const decoded = _decodeHtmlEntities(rawContext).replace(/\r\n/g, '\n');
    const lines = decoded.split('\n');
    if (lines.length === 0) {
        return { text: decoded || rawContext, hasMore: false };
    }

    const decodedSecret = _decodeHtmlEntities(rawSecret || '').trim();
    const pos = decodedSecret ? decoded.indexOf(decodedSecret) : -1;
    let secretLineIndex;

    if (pos !== -1) {
        let charCount = 0;
        secretLineIndex = 0;
        for (let i = 0; i < lines.length; i++) {
            if (charCount + lines[i].length >= pos) {
                secretLineIndex = i;
                break;
            }
            charCount += lines[i].length + 1;
        }
    } else {
        // Секрет не найден подстрокой — контекст обычно "N строк до + строка с секретом + M строк после", берём окно вокруг середины
        secretLineIndex = Math.floor(lines.length / 2);
    }

    const start = Math.max(0, secretLineIndex - CONTEXT_PREVIEW_LINES_BEFORE);
    const end = Math.min(lines.length, secretLineIndex + CONTEXT_PREVIEW_LINES_AFTER + 1);
    const previewLines = lines.slice(start, end);
    let text = previewLines.join('\n');
    if (text.length > CONTEXT_PREVIEW_MAX_CHARS) {
        const secretStartInPreview = decodedSecret ? text.indexOf(decodedSecret) : -1;
        const half = Math.floor(CONTEXT_PREVIEW_MAX_CHARS / 2);
        const from = secretStartInPreview >= 0
            ? Math.max(0, secretStartInPreview - half)
            : 0;
        text = (from > 0 ? '...' : '') + text.slice(from, from + CONTEXT_PREVIEW_MAX_CHARS) + (from + CONTEXT_PREVIEW_MAX_CHARS < text.length ? '...' : '');
    }
    const hasMore = start > 0 || end < lines.length || text.length < decoded.length;
    const prefix = start > 0 ? '...\n' : '';
    const suffix = end < lines.length ? '\n...' : '';
    return { text: prefix + text + suffix, hasMore };
}

function _decodeHtmlEntities(str) {
    if (!str || typeof str !== 'string') return '';
    const doc = new DOMParser().parseFromString(str, 'text/html');
    return doc.body ? doc.body.textContent : str;
}

function openContextModal() {
    const full = (typeof window._detailPanelFullContext === 'string') ? window._detailPanelFullContext : '';
    const secretValue = (typeof window._detailPanelFullContextSecret === 'string') ? window._detailPanelFullContextSecret : '';
    const el = document.getElementById('contextModalContent');
    if (el) {
        try {
            let decoded = _decodeHtmlEntities(full).replace(/\r\n/g, '\n');
            const toHighlight = _decodeHtmlEntities(secretValue).trim();
            const pos = toHighlight ? decoded.indexOf(toHighlight) : -1;
            if (pos !== -1) {
                const highlightLen = toHighlight.length;
                const before = escapeHtml(decoded.slice(0, pos));
                const match = escapeHtml(decoded.slice(pos, pos + highlightLen));
                const after = escapeHtml(decoded.slice(pos + highlightLen));
                el.innerHTML = before + '<mark class="context-secret-highlight">' + match + '</mark>' + after;
            } else {
                el.textContent = decoded;
            }
        } catch (_) {
            el.textContent = full;
        }
    }
    const modal = document.getElementById('contextModal');
    if (modal) modal.style.display = 'block';
}

function closeContextModal() {
    const modal = document.getElementById('contextModal');
    if (modal) modal.style.display = 'none';
}

const GROUP_COLLAPSE_THRESHOLD = 50;
const GROUP_MODAL_PAGE_SIZE = 100;

let displayRows = [];
let currentGroup = null;

function normalizeSecretStatus(status) {
    if (!status || status === '' || status === 'null') return 'No status';
    return status;
}

function buildGroupKey(path, status) {
    return `${path || ''}|||${normalizeSecretStatus(status)}`;
}

function buildDisplayRows(secrets) {
    const groupsMap = new Map();
    for (const secret of secrets) {
        const key = buildGroupKey(secret.path, secret.status);
        if (!groupsMap.has(key)) {
            groupsMap.set(key, []);
        }
        groupsMap.get(key).push(secret);
    }

    const displayRowsResult = [];
    const processedKeys = new Set();

    for (const secret of secrets) {
        const key = buildGroupKey(secret.path, secret.status);
        if (processedKeys.has(key)) continue;
        processedKeys.add(key);

        const members = groupsMap.get(key) || [];
        if (members.length > GROUP_COLLAPSE_THRESHOLD) {
            displayRowsResult.push({
                isGroup: true,
                groupKey: key,
                path: secret.path,
                status: normalizeSecretStatus(secret.status),
                memberIds: members.map(m => m.id),
                members,
                count: members.length,
            });
        } else {
            displayRowsResult.push(...members);
        }
    }

    return displayRowsResult;
}

function getGroupTypeLabel(members) {
    const types = [...new Set(members.map(m => m.type).filter(Boolean))];
    if (types.length === 0) return '—';
    if (types.length === 1) return types[0];
    return `Разные (${types.length})`;
}

function getGroupSeverityLabel(members) {
    const severities = [...new Set(members.map(m => m.severity).filter(Boolean))];
    if (severities.length === 0) return '—';
    if (severities.length === 1) return severities[0];
    return 'Mixed';
}

function getGroupConfidenceLabel(members) {
    const values = members.map(m => parseConfidence(m.confidence, 0));
    if (!values.length) return '—';
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return `${Math.round(min * 100)}%`;
    return `${Math.round(min * 100)}–${Math.round(max * 100)}%`;
}

function getDisplayRowByIndex(index) {
    return displayRows[index] || null;
}

function findGroupByKey(groupKey) {
    return displayRows.find(row => row.isGroup && row.groupKey === groupKey) || null;
}

function refreshCurrentGroup() {
    if (!currentGroup) return null;
    const updated = findGroupByKey(currentGroup.groupKey);
    currentGroup = updated;
    window._currentGroup = updated;
    return updated;
}

function updateGroupModalCountLabel() {
    const countEl = document.getElementById('secretsDetailsCount');
    if (!countEl || !currentGroup) return;
    countEl.textContent = `Всего: ${currentGroup.count} | Статус: ${normalizeSecretStatus(currentGroup.status)}`;
}

function updateGroupModalPagination(total, page, totalPages) {
    const pageInfo = document.getElementById('secretsDetailsPageInfo');
    const prevBtn = document.getElementById('secretsDetailsPrevBtn');
    const nextBtn = document.getElementById('secretsDetailsNextBtn');
    const pagination = document.querySelector('.secrets-details-pagination');

    if (pagination) {
        pagination.style.display = totalPages > 1 ? 'flex' : 'none';
    }
    if (pageInfo) {
        pageInfo.textContent = totalPages > 0 ? `Страница ${page} из ${totalPages}` : 'Нет данных';
    }
    if (prevBtn) prevBtn.disabled = page <= 1;
    if (nextBtn) nextBtn.disabled = page >= totalPages;
}

function renderGroupModalPage(page) {
    if (!currentGroup) return;

    const members = currentGroup.members || [];
    const total = members.length;
    const totalPages = Math.max(1, Math.ceil(total / GROUP_MODAL_PAGE_SIZE));
    const currentPage = Math.max(1, Math.min(page || 1, totalPages));
    const start = (currentPage - 1) * GROUP_MODAL_PAGE_SIZE;
    const pageMembers = members.slice(start, start + GROUP_MODAL_PAGE_SIZE);

    window._groupModalPage = currentPage;
    window._groupModalTotalPages = totalPages;

    updateGroupModalCountLabel();
    updateGroupModalPagination(total, currentPage, totalPages);

    const tbody = document.getElementById('secretsDetailsTableBody');
    if (!tbody) return;

    tbody.innerHTML = pageMembers.map(member => {
        const line = member.line || 0;
        const secretVal = safeHtml(member.secret || '');
        const secretType = safeHtml(member.type || '');
        const isConfirmed = normalizeSecretStatus(member.status) === 'Confirmed';
        const actionCell = isConfirmed
            ? '<span class="secrets-details-added-label">✅ Подтверждён</span>'
            : `<button type="button" class="secrets-details-add-btn" onclick="confirmGroupMember(${member.id})" title="Подтвердить секрет">✅</button>`;

        return `<tr data-secret-id="${member.id}">
            <td class="col-line">${line}</td>
            <td class="col-secret">${secretVal}</td>
            <td class="col-type">${secretType}</td>
            <td class="col-action">${actionCell}</td>
        </tr>`;
    }).join('');
}

function openGroupSecretsModal() {
    if (!currentGroup || !currentGroup.members || currentGroup.members.length === 0) return;
    window._groupModalPage = 1;
    const modal = document.getElementById('secretsDetailsModal');
    if (modal) modal.style.display = 'block';
    renderGroupModalPage(1);
}

function closeSecretsDetailsModal() {
    const modal = document.getElementById('secretsDetailsModal');
    if (modal) modal.style.display = 'none';
}

function changeSecretsDetailsPage(delta) {
    const nextPage = (window._groupModalPage || 1) + delta;
    const totalPages = window._groupModalTotalPages || 1;
    if (nextPage < 1 || nextPage > totalPages) return;
    renderGroupModalPage(nextPage);
}

async function confirmGroupMember(secretId) {
    const btn = document.querySelector(`#secretsDetailsTableBody tr[data-secret-id="${secretId}"] .secrets-details-add-btn`);
    if (btn) {
        btn.disabled = true;
        btn.textContent = '...';
    }

    try {
        const response = await fetch(`/secret_scanner/secrets/${secretId}/update-status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ status: 'Confirmed', comment: '' }),
        });

        if (!response.ok) {
            alert('Ошибка при подтверждении секрета');
            if (btn) {
                btn.disabled = false;
                btn.textContent = '✅';
            }
            return;
        }

        const secret = allSecrets.find(s => s.id === secretId);
        if (secret) {
            secret.status = 'Confirmed';
            secret.is_exception = false;
            secret.exception_comment = null;
            secret.refuted_at = null;
        }

        applyFiltersSync();

        const updatedGroup = refreshCurrentGroup();
        if (!updatedGroup || updatedGroup.count <= GROUP_COLLAPSE_THRESHOLD) {
            closeSecretsDetailsModal();
            if (updatedGroup && updatedGroup.count > 0) {
                showEmptyDetail();
            }
            return;
        }

        const totalPages = Math.max(1, Math.ceil(updatedGroup.count / GROUP_MODAL_PAGE_SIZE));
        const page = Math.min(window._groupModalPage || 1, totalPages);
        renderGroupModalPage(page);

        if (currentGroup) {
            loadGroupDetails(currentGroup);
        }
    } catch (error) {
        console.error('Error confirming group member:', error);
        alert('Ошибка при подтверждении секрета');
        if (btn) {
            btn.disabled = false;
            btn.textContent = '✅';
        }
    }
}

async function updateGroupStatus(status) {
    if (!currentGroup || !currentGroup.memberIds || currentGroup.memberIds.length === 0) return;

    let comment = '';
    if (status === 'Refuted') {
        const input = prompt('Введите комментарий (опционально):');
        if (input === null) return;
        comment = input;
    }

    try {
        const response = await fetch('/secret_scanner/secrets/bulk-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                secret_ids: currentGroup.memberIds,
                action: 'status',
                value: status,
                comment,
            }),
        });

        if (!response.ok) {
            alert('Ошибка при обновлении статуса группы');
            return;
        }

        currentGroup.memberIds.forEach(secretId => {
            const secret = allSecrets.find(s => s.id === secretId);
            if (!secret) return;
            secret.status = status;
            if (status === 'Refuted') {
                secret.is_exception = true;
                secret.exception_comment = comment;
                secret.refuted_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
            } else {
                secret.is_exception = false;
                secret.exception_comment = null;
                secret.refuted_at = null;
            }
        });

        closeSecretsDetailsModal();
        applyFiltersSync();
        showEmptyDetail();
    } catch (error) {
        console.error('Error updating group status:', error);
        alert('Ошибка при обновлении статуса группы');
    }
}

function parseConfidence(value, defaultValue = 1.0) {
    if (value === undefined || value === null || value === '') {
        return defaultValue;
    }
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : defaultValue;
}

function normalizeSecretRecord(secret) {
    if (secret.status === null || secret.status === undefined || secret.status === '' || secret.status === 'null') {
        secret.status = 'No status';
    }
    secret.confidence = parseConfidence(secret.confidence, 1.0);
    return secret;
}

function appendAddedSecret(addedSecret, ensureTypes) {
    const normalized = normalizeSecretRecord({ ...addedSecret });
    allSecrets.push(normalized);
    secretsData = allSecrets.slice();

    const previouslyCheckedTypes = getCheckedTypeFilters();
    initializeFilters({
        preserveTypes: previouslyCheckedTypes,
        ensureTypes: ensureTypes || [normalized.type],
    });
    applyFiltersSync();
    return normalized;
}

function refreshSecretsData(newSecretsData, options = {}) {
    const previouslyCheckedTypes = getCheckedTypeFilters();
    secretsData = newSecretsData || [];
    allSecrets = secretsData.slice();

    allSecrets.forEach(secret => normalizeSecretRecord(secret));

    initializeFilters({
        preserveTypes: previouslyCheckedTypes,
        ensureTypes: options.ensureTypes || [],
    });
    applyFiltersSync();
}

// Получаем данные из data-атрибутов
function loadDataFromAttributes() {
    projectRepoUrl = document.body.dataset.projectRepoUrl || '';
    scanCommit = document.body.dataset.scanCommit || '';
    hubType = document.body.dataset.hubType || '';
}

function openAddSecretModal() {
    document.getElementById('addSecretModal').style.display = 'block';
    // Очистить форму
    document.getElementById('addSecretForm').reset();
}

function closeAddSecretModal() {
    document.getElementById('addSecretModal').style.display = 'none';
}

async function submitCustomSecret(event) {
    event.preventDefault();
    
    const pathParts = window.location.pathname.split('/');
    const scanId = pathParts[pathParts.length - 2];
    const formData = new FormData();
    
    formData.append('scan_id', scanId);
    formData.append('secret_value', document.getElementById('secretValue').value);
    formData.append('context', document.getElementById('secretContext').value);
    formData.append('line', document.getElementById('secretLine').value);
    formData.append('secret_type', document.getElementById('secretType').value);
    formData.append('file_path', document.getElementById('secretPath').value);
    formData.append('lightweight', 'true');
    
    try {
        const response = await fetch('/secret_scanner/secrets/add-custom', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            alert('Секрет успешно добавлен!');
            closeAddSecretModal();

            const addedType = document.getElementById('secretType').value;
            if (result.added_secret) {
                appendAddedSecret(result.added_secret, [addedType]);
            } else if (result.secrets_data) {
                refreshSecretsData(result.secrets_data, { ensureTypes: [addedType] });
            }
            
        } else {
            alert('Ошибка: ' + result.message);
        }
    } catch (error) {
        console.error('Error adding custom secret:', error);
        alert('Ошибка при добавлении секрета');
    }
}

// Закрытие модального окна при клике вне его
document.addEventListener('click', function(event) {
    const modal = document.getElementById('addSecretModal');
    if (event.target === modal) {
        closeAddSecretModal();
    }
});

// Функция для безопасного отображения HTML
function safeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    return String(text);
}

// Функция для экранирования HTML (для создания новых элементов)
function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    
    const str = String(text);
    
    // Если текст уже содержит HTML entities, не экранируем повторно
    if (str.includes('&quot;') || str.includes('&lt;') || str.includes('&gt;') || str.includes('&amp;')) {
        return str;
    }
    
    // Только для неэкранированного текста применяем экранирование
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Загрузка данных из скрытого элемента
function loadSecretsData() {
    try {
        const dataElement = document.getElementById('secrets-data');
        if (!dataElement) {
            console.error('Secrets data element not found');
            return false;
        }
        
        const rawData = dataElement.textContent;
        if (!rawData || rawData.trim() === '') {
            console.error('No data in secrets data element');
            return false;
        }
        
        secretsData = JSON.parse(rawData);
        // console.log('Successfully loaded', secretsData.length, 'secrets');
        return true;
        
    } catch (error) {
        console.error('Error parsing secrets data:', error);
        console.error('Raw data length:', document.getElementById('secrets-data')?.textContent?.length || 'N/A');
        return false;
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    // console.log('Page loading...');
    
    // Загружаем данные из атрибутов
    loadDataFromAttributes();
    
    // Загружаем данные
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
    
    if (secretsData.length === 0) {
        // console.log('No secrets found in scan');
        const tableContainer = document.getElementById('secretsTable');
        if (tableContainer) {
            tableContainer.innerHTML = `
                <div class="empty-results">
                    <h3>Секреты не найдены</h3>
                    <p>В этом скане не обнаружено секретов.</p>
                </div>
            `;
        }
        return;
    }
    
    // Normalize statuses immediately
    secretsData.forEach(secret => normalizeSecretRecord(secret));
    
    allSecrets = secretsData.slice();
    
    // console.log('Initializing with', allSecrets.length, 'secrets');
    
    // Initialize filters synchronously
    initializeFilters();
    
    // Apply filters immediately
    applyFiltersSync();
});

function getCheckedTypeFilters() {
    return Array.from(document.querySelectorAll('#typeFilters input[type="checkbox"]:checked')).map(cb => cb.value);
}

function getAllTypeFilterValues() {
    return Array.from(document.querySelectorAll('#typeFilters input[type="checkbox"]')).map(cb => cb.value);
}

function initializeFilters(options = {}) {
    const { preserveTypes = null, ensureTypes = [] } = options;
    const previouslyChecked = preserveTypes;
    const previousAllTypes = preserveTypes !== null
        ? new Set(getAllTypeFilterValues())
        : null;
    // Get unique types
    const uniqueTypes = [...new Set(allSecrets.map(s => s.type))].sort();
    
    // Populate type filters
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
            <input type="checkbox" id="type-${safeId}" value="${escapeHtml(type)}" onchange="applyFilters()">
            <label for="type-${safeId}">${escapeHtml(type)}</label>
        `;
        typeFiltersContainer.appendChild(div);
    });

    // Initialize filters from URL parameters or defaults
    const urlParams = new URLSearchParams(window.location.search);
    
    // Status filters - DEFAULT: Confirmed and No status
    const statusFilters = urlParams.getAll('status_filter');
    if (statusFilters.length > 0) {
        statusFilters.forEach(status => {
            const checkbox = document.querySelector(`#filtersPanel input[value="${status}"]`);
            if (checkbox) {
                checkbox.checked = true;
                activeFilters.status.push(status);
            }
        });
    } else {
        // Default: Confirmed and No status
        const confirmedCb = document.getElementById('status-confirmed');
        const noneCb = document.getElementById('status-none');
        if (confirmedCb) {
            confirmedCb.checked = true;
            activeFilters.status.push('Confirmed');
        }
        if (noneCb) {
            noneCb.checked = true;
            activeFilters.status.push('No status');
        }
    }

    // Severity filters - DEFAULT: High and Potential
    const severityFilters = urlParams.getAll('severity_filter');
    if (severityFilters.length > 0) {
        severityFilters.forEach(severity => {
            const checkbox = document.querySelector(`#filtersPanel input[value="${severity}"]`);
            if (checkbox) {
                checkbox.checked = true;
                activeFilters.severity.push(severity);
            }
        });
    } else {
        // Default: High and Potential
        const highCb = document.getElementById('severity-high');
        const potentialCb = document.getElementById('severity-potential');
        if (highCb) {
            highCb.checked = true;
            activeFilters.severity.push('High');
        }
        if (potentialCb) {
            potentialCb.checked = true;
            activeFilters.severity.push('Potential');
        }
    }

    // Type filters
    const typeFilters = urlParams.getAll('type_filter');
    if (previouslyChecked !== null) {
        const typesToCheck = new Set([...previouslyChecked, ...ensureTypes]);
        uniqueTypes.forEach(type => {
            if (previousAllTypes && !previousAllTypes.has(type)) {
                typesToCheck.add(type);
            }
        });
        activeFilters.type = [];
        uniqueTypes.forEach(type => {
            const safeId = type.replace(/[^a-zA-Z0-9]/g, '_');
            const checkbox = document.getElementById(`type-${safeId}`);
            if (checkbox) {
                checkbox.checked = typesToCheck.has(type);
                if (checkbox.checked) {
                    activeFilters.type.push(type);
                }
            }
        });
    } else if (typeFilters.length > 0) {
        typeFilters.forEach(type => {
            const checkbox = document.querySelector(`#typeFilters input[value="${type}"]`);
            if (checkbox) {
                checkbox.checked = true;
                activeFilters.type.push(type);
            }
        });
    } else {
        // Default: All types (включая только что добавленные)
        activeFilters.type = [];
        uniqueTypes.forEach(type => {
            const checkbox = document.querySelector(`#typeFilters input[value="${type}"]`);
            if (checkbox) {
                checkbox.checked = true;
                activeFilters.type.push(type);
            }
        });
    }
}

function applyFiltersFromMain() {
    // Синхронизировать с основным фильтром
    const mainInput = document.getElementById('secretValueFilterMain');
    const panelInput = document.getElementById('secretValueFilter');
    
    if (mainInput && panelInput) {
        panelInput.value = mainInput.value;
    }
    
    // Применить фильтры
    applyFilters();
}

// Сохранить текущую сортировку перед применением фильтров
function applyFiltersSync() {
    // Update active filters from checkboxes
    activeFilters.status = [];
    activeFilters.severity = [];
    activeFilters.type = [];
    const mainInput = document.getElementById('secretValueFilterMain');
    const panelInput = document.getElementById('secretValueFilter');
    activeFilters.secretValue = (mainInput?.value || panelInput?.value || '');

    // Синхронизировать оба поля
    if (mainInput && panelInput) {
        if (mainInput.value !== panelInput.value) {
            if (mainInput.value) {
                panelInput.value = mainInput.value;
            } else {
                mainInput.value = panelInput.value;
            }
        }
    }
    
    // Get status filters
    document.querySelectorAll('#filtersPanel input[type="checkbox"]:checked').forEach(cb => {
        const value = cb.value;
        if (['Confirmed', 'No status', 'Refuted'].includes(value)) {
            activeFilters.status.push(value);
        } else if (['High', 'Potential'].includes(value)) {
            activeFilters.severity.push(value);
        }
    });
    
    // Get type filters
    document.querySelectorAll('#typeFilters input[type="checkbox"]:checked').forEach(cb => {
        activeFilters.type.push(cb.value);
    });

    // Filter logic
    if (activeFilters.status.length === 0 || activeFilters.severity.length === 0 || activeFilters.type.length === 0) {
        filteredSecrets = [];
    } else {
        filteredSecrets = allSecrets.filter(secret => {
            // Normalize status
            let secretStatus = secret.status;
            if (!secretStatus || secretStatus === '' || secretStatus === null) {
                secretStatus = 'No status';
            }
            
            // ALL conditions must be true
            const statusMatch = activeFilters.status.includes(secretStatus);
            const severityMatch = activeFilters.severity.includes(secret.severity);
            const typeMatch = activeFilters.type.includes(secret.type);
            
            // Secret / file name filter
            const searchTerm = activeFilters.secretValue.toLowerCase();
            const secretValueMatch = !searchTerm || (
                (secret.secret && secret.secret.toLowerCase().includes(searchTerm)) ||
                getFileNameFromPath(secret.path).toLowerCase().includes(searchTerm)
            );
            
            return statusMatch && severityMatch && typeMatch && secretValueMatch;
        });
    }

    // Reset to first page and clear selections
    currentPage = 1;
    selectedSecrets.clear();
    showEmptyDetail();

    // Apply sorting to filtered results, then build display rows
    sortSecrets();
    displayRows = buildDisplayRows(filteredSecrets);
    sortDisplayRows();

    // Update URL, stats, and render
    updateURL();
    updateStats();
    renderTable();
    renderPagination();
}

function applyFilters() {
    applyFiltersSync();
}

function clearAllFilters() {
    // Uncheck all checkboxes
    document.querySelectorAll('#filtersPanel input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    
    // Clear text input
    const secretValueFilter = document.getElementById('secretValueFilter');
    if (secretValueFilter) {
        secretValueFilter.value = '';
    }
    
    // Clear active filters
    activeFilters = { status: [], severity: [], type: [], secretValue: '' };
    
    // Apply filters
    applyFilters();
}

function updateStats() {
    const totalCount = filteredSecrets.length;
    const highCount = filteredSecrets.filter(s => s.severity === 'High').length;
    const potentialCount = filteredSecrets.filter(s => s.severity === 'Potential').length;

    const totalEl = document.getElementById('totalSecretsCount');
    const highEl = document.getElementById('highSecretsCount');
    const potentialEl = document.getElementById('potentialSecretsCount');
    
    if (totalEl) totalEl.textContent = totalCount;
    if (highEl) highEl.textContent = highCount;
    if (potentialEl) potentialEl.textContent = potentialCount;
}

function updateURL() {
    const params = new URLSearchParams();
    
    activeFilters.status.forEach(status => params.append('status_filter', status));
    activeFilters.severity.forEach(severity => params.append('severity_filter', severity));
    activeFilters.type.forEach(type => params.append('type_filter', type));
    
    params.set('page', currentPage);
    params.set('page_size', pageSize);
    
    // Update URL without reload
    const newURL = window.location.pathname + '?' + params.toString();
    history.replaceState(null, '', newURL);
}

function renderTable() {
    const tableContainer = document.getElementById('secretsTable');
    
    if (displayRows.length === 0) {
        tableContainer.innerHTML = `
            <div class="empty-results">
                <h3>No secrets found</h3>
                <p>No secrets match the current filters.</p>
            </div>
        `;
        return;
    }

    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, displayRows.length);
    const pageRows = displayRows.slice(startIndex, endIndex);

    let tableHTML = `
        <table class="secrets-table">
            <thead class="table-header">
                <tr>
                    <th class="sortable" data-sort="secret">🔑 Secret</th>
                    <th class="sortable" data-sort="file">📁 File</th>
                    <th class="sortable" data-sort="type">🏷️ Type</th>
                    <th class="sortable" data-sort="status">📊 Status</th>
                    <th class="sortable" data-sort="confidence">🎯</th>
                    <th class="sortable" data-sort="severity">⚠️ Level</th>
                </tr>
            </thead>
            <tbody>
    `;

    pageRows.forEach((row, index) => {
        const globalIndex = startIndex + index;
        if (row.isGroup) {
            const severityLabel = getGroupSeverityLabel(row.members);
            const severityClass = severityLabel.toLowerCase() === 'mixed' ? 'potential' : severityLabel.toLowerCase();
            tableHTML += `
            <tr class="secret-row group-row ${severityClass}" data-is-group="true" data-group-key="${encodeURIComponent(row.groupKey)}" data-row-index="${globalIndex}">
                <td>
                    <div class="secret-value">${row.count} секретов в файле</div>
                </td>
                <td>
                    <span class="secret-file">${escapeHtml((row.path || '').split('/').pop())}</span>
                </td>
                <td>
                    <span class="secret-type">${escapeHtml(getGroupTypeLabel(row.members))}</span>
                </td>
                <td>
                    <div class="secret-status">
                        ${getStatusHTML({ status: row.status })}
                    </div>
                </td>
                <td>
                    <div class="secret-confidence" style="font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace; font-weight: 600; color: #6b7280; text-align: center;">
                        ${escapeHtml(getGroupConfidenceLabel(row.members))}
                    </div>
                </td>
                <td>
                    <div class="secret-severity ${escapeHtml(severityLabel).toLowerCase()}">${escapeHtml(severityLabel)}</div>
                </td>
            </tr>
        `;
        } else {
            tableHTML += `
            <tr class="secret-row ${safeHtml(row.severity).toLowerCase()}" data-secret-id="${row.id}" data-row-index="${globalIndex}">
                <td>
                    <div class="secret-value">${safeHtml(row.secret)}</div>
                </td>
                <td>
                    <span class="secret-file">${escapeHtml((row.path || '').split('/').pop())}</span>
                </td>
                <td>
                    <span class="secret-type">${escapeHtml(row.type)}</span>
                </td>
                <td>
                    <div class="secret-status">
                        ${getStatusHTML(row)}
                    </div>
                </td>
                <td>
                    <div class="secret-confidence" style="font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace; font-weight: 600; color: ${row.confidence >= 0.8 ? '#059669' : row.confidence >= 0.5 ? '#d97706' : '#dc2626'}; text-align: center;">
                        ${(row.confidence * 100).toFixed(0)}%
                    </div>
                </td>
                <td>
                    <div class="secret-severity ${safeHtml(row.severity).toLowerCase()}">${escapeHtml(row.severity)}</div>
                </td>
            </tr>
        `;
        }
    });

    tableHTML += '</tbody></table>';
    tableContainer.innerHTML = tableHTML;
    initializeTableEventListeners();
}

function getStatusHTML(secret) {
    if (secret.status === 'Confirmed') {
        return '<span class="status-confirmed">✅ Confirmed</span>';
    } else if (secret.status === 'Refuted') {
        let html = '<span class="status-refuted">❌ Refuted</span>';
        if (secret.refuted_at) {
            html += `<div class="refuted-date">${escapeHtml(secret.refuted_at)}</div>`;
        }
        return html;
    } else {
        return '<span class="status-none">⚪ Без статуса</span>';
    }
}

function initializeTableEventListeners() {
    const secretRows = document.querySelectorAll('.secret-row');
    secretRows.forEach((row) => {
        row.addEventListener('click', function(e) {
            const rowIndex = parseInt(row.dataset.rowIndex, 10);
            const isGroup = row.dataset.isGroup === 'true';
            const secretId = row.dataset.secretId ? parseInt(row.dataset.secretId, 10) : null;
            const groupKey = row.dataset.groupKey ? decodeURIComponent(row.dataset.groupKey) : null;
            handleRowClick(e, { rowIndex, isGroup, secretId, groupKey });
        });
    });

    // Sort headers
    const sortableHeaders = document.querySelectorAll('.sortable');
    sortableHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const column = this.dataset.sort;
            handleSort(column);
        });
    });
}

function renderPagination() {
    const totalPages = Math.ceil(displayRows.length / pageSize);
    const startIndex = (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, displayRows.length);

    const paginationInfo = document.getElementById('paginationInfo');
    if (paginationInfo) {
        paginationInfo.textContent = `Показаны ${displayRows.length === 0 ? 0 : startIndex}-${endIndex} из ${displayRows.length} строк (${filteredSecrets.length} секретов)`;
    }

    // Pagination controls
    const paginationControls = document.getElementById('paginationControls');
    if (!paginationControls) return;
    
    let controlsHTML = '';

    // Previous button
    if (currentPage > 1) {
        controlsHTML += `<button class="pagination-btn" onclick="goToPage(${currentPage - 1})">← Предыдущая</button>`;
    } else {
        controlsHTML += `<button class="pagination-btn disabled">← Предыдущая</button>`;
    }

    // Page numbers
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

    // Next button
    if (currentPage < totalPages) {
        controlsHTML += `<button class="pagination-btn" onclick="goToPage(${currentPage + 1})">Следующая →</button>`;
    } else {
        controlsHTML += `<button class="pagination-btn disabled">Следующая →</button>`;
    }

    paginationControls.innerHTML = controlsHTML;
}

function goToPage(page) {
    const totalPages = Math.ceil(displayRows.length / pageSize);
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        selectedSecrets.clear();
        showEmptyDetail();
        updateURL();
        renderTable();
        renderPagination();
    }
}

function changePageSize() {
    pageSize = parseInt(document.getElementById('pageSize').value);
    currentPage = 1;
    selectedSecrets.clear();
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

function handleRowClick(e, { rowIndex, isGroup, secretId, groupKey }) {
    e.preventDefault();

    const isCtrlPressed = e.ctrlKey || e.metaKey;

    if (isCtrlPressed) {
        toggleMultiSelection(rowIndex, isGroup, secretId, groupKey);
        return;
    }

    if (e.shiftKey && lastClickedIndex !== -1 && selectedSecrets.size > 0) {
        selectRange(lastClickedIndex, rowIndex);
        return;
    }

    clearMultiSelection();
    selectSingleRow(rowIndex, isGroup, secretId, groupKey);
}

function getRowMemberIds(row) {
    if (!row) return [];
    if (row.isGroup) return row.memberIds.slice();
    return [row.id];
}

function toggleMultiSelection(rowIndex, isGroup, secretId, groupKey) {
    const row = getDisplayRowByIndex(rowIndex);
    if (!row) return;

    const memberIds = getRowMemberIds(row);
    const rowEl = isGroup
        ? document.querySelector(`[data-group-key="${encodeURIComponent(groupKey || '')}"]`)
        : document.querySelector(`[data-secret-id="${secretId}"]`);
    const allSelected = memberIds.every(id => selectedSecrets.has(id));

    if (allSelected) {
        memberIds.forEach(id => selectedSecrets.delete(id));
        if (rowEl) rowEl.classList.remove('multi-selected', 'selected');
    } else {
        memberIds.forEach(id => selectedSecrets.add(id));
        if (rowEl) {
            rowEl.classList.remove('selected');
            rowEl.classList.add('multi-selected');
        }
    }

    lastClickedIndex = rowIndex;
    updateSelectionView();
}

function selectSingleRow(rowIndex, isGroup, secretId, groupKey) {
    clearMultiSelection();

    const row = getDisplayRowByIndex(rowIndex);
    if (!row) return;

    const rowEl = isGroup
        ? document.querySelector(`[data-group-key="${encodeURIComponent(groupKey || '')}"]`)
        : document.querySelector(`[data-secret-id="${secretId}"]`);

    if (rowEl) {
        rowEl.classList.add('selected');
        getRowMemberIds(row).forEach(id => selectedSecrets.add(id));
        currentSecret = isGroup ? null : secretId;
        lastClickedIndex = rowIndex;
        if (isGroup) {
            loadGroupDetails(row);
        } else {
            loadSecretDetails(secretId);
        }
    }
}

function selectRange(startIndex, endIndex) {
    const start = Math.min(startIndex, endIndex);
    const end = Math.max(startIndex, endIndex);
    const pageStartIndex = (currentPage - 1) * pageSize;
    const pageEndIndex = Math.min(pageStartIndex + pageSize, displayRows.length);

    for (let i = start; i <= end; i++) {
        if (i < pageStartIndex || i >= pageEndIndex) continue;
        const row = displayRows[i];
        if (!row) continue;
        getRowMemberIds(row).forEach(id => selectedSecrets.add(id));
        const rowEl = row.isGroup
            ? document.querySelector(`[data-group-key="${encodeURIComponent(row.groupKey)}"]`)
            : document.querySelector(`[data-secret-id="${row.id}"]`);
        if (rowEl) {
            rowEl.classList.add('multi-selected');
            rowEl.classList.remove('selected');
        }
    }

    lastClickedIndex = endIndex;
    updateSelectionView();
}

function selectSingleSecret(secretId, index) {
    selectSingleRow(index, false, secretId, null);
}

function clearMultiSelection() {
    selectedSecrets.clear();
    document.querySelectorAll('.secret-row').forEach(row => {
        row.classList.remove('selected', 'multi-selected');
    });
}

function updateSelectionView() {
    if (selectedSecrets.size > 1) {
        showBulkDetail();
    } else if (selectedSecrets.size === 1) {
        const singleSecretId = Array.from(selectedSecrets)[0];
        loadSecretDetails(singleSecretId);
    } else {
        showEmptyDetail();
    }
}

function showBulkDetail() {
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;
    
    detailPanel.innerHTML = `
        <div class="bulk-detail-panel">
            <h3 class="bulk-title">📌 Выбрано секретов: <span class="bulk-count">${selectedSecrets.size}</span></h3>
            
            <div class="bulk-section">
                <button class="bulk-btn select-all-btn" onclick="selectAllVisibleSecrets()">
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
            
            <div class="bulk-section severity-panel">
                <h4>⚠️ Изменение Severity-уровня</h4>
                <div class="bulk-buttons severity-buttons">
                    <button class="bulk-btn severity-high-btn" onclick="performBulkAction('severity', 'High')">
                        🛑 High
                    </button>
                    <button class="bulk-btn severity-potential-btn" onclick="performBulkAction('severity', 'Potential')">
                        🔘 Potential
                    </button>
                </div>
            </div>
            
            <div class="bulk-section">
                <button class="bulk-btn btn-secondary" onclick="clearMultiSelection(); showEmptyDetail();" style="width: 100%;">
                    ❌ Отменить выделение
                </button>
            </div>
        </div>
    `;
}

function showEmptyDetail() {
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;
    
    detailPanel.innerHTML = `
        <div class="detail-empty">
            <div style="text-align: center; padding: 2rem;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">👈</div>
                <h3>Выберите секрет, чтобы просмотреть подробную информацию</h3>
                <p>Нажмите на любой секрет из списка, чтобы просмотреть подробную информацию, управлять его статусом и получить доступ к расположению файла.</p>
                <div style="margin-top: 2rem; padding: 1rem; background: #f0f9ff; border-radius: 8px; border-left: 4px solid #3b82f6;">
                    <strong>💡 Совет:</strong> Используйте <kbd>Ctrl</kbd> для выделения нескольких секретов или <kbd>Shift</kbd> для выделения диапазона.
                </div>
            </div>
        </div>
    `;
}

function selectAllVisibleSecrets() {
    const visibleRows = document.querySelectorAll('.secret-row');
    selectedSecrets.clear();

    visibleRows.forEach(rowEl => {
        const rowIndex = parseInt(rowEl.dataset.rowIndex, 10);
        const row = getDisplayRowByIndex(rowIndex);
        if (!row) return;
        getRowMemberIds(row).forEach(id => selectedSecrets.add(id));
        rowEl.classList.add('multi-selected');
        rowEl.classList.remove('selected');
    });

    showBulkDetail();
}

function handleSort(column) {
    // Простая сортировка - только одна колонка
    const existingSort = sortColumns.find(sort => sort.column === column);
    
    if (existingSort) {
        // Переключаем направление: asc -> desc -> none
        if (existingSort.direction === 'asc') {
            existingSort.direction = 'desc';
        } else {
            // Убираем сортировку
            sortColumns = [];
        }
    } else {
        // Новая сортировка, заменяем предыдущую
        sortColumns = [{ column: column, direction: 'asc' }];
    }
    
    // Применяем сортировку
    sortDisplayRows();
    renderTable();
    renderPagination();
    
    // Обновляем индикаторы после рендера таблицы
    setTimeout(updateSortIndicators, 0);
}

function updateSortIndicators() {
    // Сначала очищаем все
    document.querySelectorAll('.sortable').forEach(header => {
        header.classList.remove('sort-asc', 'sort-desc');
        const indicator = header.querySelector('.sort-indicator');
        if (indicator) indicator.remove();
    });
    
    // Добавляем класс для активной сортировки
    if (sortColumns.length > 0) {
        const sort = sortColumns[0];
        const header = document.querySelector(`[data-sort="${sort.column}"]`);
        if (header) {
            header.classList.add(sort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    }
}

function sortDisplayRows() {
    if (sortColumns.length === 0) {
        displayRows.sort((a, b) => {
            const confA = a.isGroup
                ? Math.max(...a.members.map(m => parseConfidence(m.confidence, 0)))
                : parseConfidence(a.confidence, 0);
            const confB = b.isGroup
                ? Math.max(...b.members.map(m => parseConfidence(m.confidence, 0)))
                : parseConfidence(b.confidence, 0);
            return confB - confA;
        });
        return;
    }

    displayRows.sort((a, b) => {
        for (let sort of sortColumns) {
            let valueA, valueB;

            switch (sort.column) {
                case 'secret':
                    valueA = a.isGroup ? a.count : (a.secret || '').toLowerCase();
                    valueB = b.isGroup ? b.count : (b.secret || '').toLowerCase();
                    break;
                case 'file':
                    valueA = getFileNameFromPath(a.path).toLowerCase();
                    valueB = getFileNameFromPath(b.path).toLowerCase();
                    break;
                case 'type':
                    valueA = a.isGroup
                        ? getGroupTypeLabel(a.members).toLowerCase()
                        : (a.type || '').toLowerCase();
                    valueB = b.isGroup
                        ? getGroupTypeLabel(b.members).toLowerCase()
                        : (b.type || '').toLowerCase();
                    break;
                case 'status':
                    const statusOrder = { 'Confirmed': 3, 'No status': 2, 'Refuted': 1 };
                    valueA = statusOrder[normalizeSecretStatus(a.status)] || 0;
                    valueB = statusOrder[normalizeSecretStatus(b.status)] || 0;
                    break;
                case 'severity':
                    const severityOrder = { 'High': 2, 'Potential': 1, 'Mixed': 0 };
                    valueA = a.isGroup
                        ? severityOrder[getGroupSeverityLabel(a.members)] || 0
                        : severityOrder[a.severity] || 0;
                    valueB = b.isGroup
                        ? severityOrder[getGroupSeverityLabel(b.members)] || 0
                        : severityOrder[b.severity] || 0;
                    break;
                case 'confidence':
                    valueA = a.isGroup
                        ? Math.max(...a.members.map(m => parseConfidence(m.confidence, 0)))
                        : parseConfidence(a.confidence, 0);
                    valueB = b.isGroup
                        ? Math.max(...b.members.map(m => parseConfidence(m.confidence, 0)))
                        : parseConfidence(b.confidence, 0);
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

function sortSecrets() {
    if (sortColumns.length === 0) {
        // Сортировка по умолчанию: по Confidence от высокой к низкой
        filteredSecrets.sort((a, b) => {
            const confA = parseFloat(a.confidence) || 0;
            const confB = parseFloat(b.confidence) || 0;
            return confB - confA; // от высокой к низкой
        });
        return;
    }

    filteredSecrets.sort((a, b) => {
        for (let sort of sortColumns) {
            let valueA, valueB;
            
            switch (sort.column) {
                case 'secret':
                    valueA = (a.secret || '').toLowerCase();
                    valueB = (b.secret || '').toLowerCase();
                    break;
                case 'file':
                    valueA = getFileNameFromPath(a.path).toLowerCase();
                    valueB = getFileNameFromPath(b.path).toLowerCase();
                    break;
                case 'type':
                    valueA = (a.type || '').toLowerCase();
                    valueB = (b.type || '').toLowerCase();
                    break;
                case 'status':
                    const statusOrder = { 'Confirmed': 3, 'No status': 2, 'Refuted': 1 };
                    valueA = statusOrder[a.status] || 0;
                    valueB = statusOrder[b.status] || 0;
                    break;
                case 'severity':
                    const severityOrder = { 'High': 2, 'Potential': 1 };
                    valueA = severityOrder[a.severity] || 0;
                    valueB = severityOrder[b.severity] || 0;
                    break;
                case 'confidence':
                    valueA = parseFloat(a.confidence) || 0;
                    valueB = parseFloat(b.confidence) || 0;
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

function loadGroupDetails(groupRow) {
    currentGroup = groupRow;
    window._currentGroup = groupRow;

    const safePath = safeHtml(groupRow.path || '');
    const safeStatus = safeHtml(groupRow.status || '');
    const count = groupRow.count || 0;

    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;

    detailPanel.innerHTML = `
        <div class="detail-content">
            <h3>Группа секретов</h3>

            <div class="detail-section">
                <h4>📁 Путь до файла</h4>
                <div class="detail-field">${safePath}</div>
            </div>

            <div class="detail-section">
                <h4>📦 Количество секретов</h4>
                <div class="detail-field">${count}</div>
            </div>

            <div class="detail-section">
                <h4>📊 Статус группы</h4>
                <div class="detail-field">${safeStatus}</div>
            </div>

            <div class="status-controls">
                <h4 style="margin-bottom: 8px;">Статус для всей группы</h4>
                <div class="status-buttons">
                    <button class="status-btn ${groupRow.status === 'Confirmed' ? 'active' : ''}"
                            onclick="updateGroupStatus('Confirmed')">
                        ✅ Подтвердить все
                    </button>
                    <button class="status-btn ${groupRow.status === 'No status' ? 'active' : ''}"
                            onclick="updateGroupStatus('No status')">
                        ⚪ Без статуса
                    </button>
                    <button class="status-btn ${groupRow.status === 'Refuted' ? 'active' : ''}"
                            onclick="updateGroupStatus('Refuted')">
                        ❌ Опровергнуть все
                    </button>
                </div>
            </div>

            <div class="detail-section">
                <button type="button" class="btn btn-secondary context-more-btn" onclick="openGroupSecretsModal()" style="margin-top: 0.5rem;">
                    Подробнее (${count} секретов)
                </button>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Просмотрите секреты по отдельности и подтвердите только реальные находки.
                </div>
            </div>
        </div>
    `;
}

function loadSecretDetails(secretId) {
    const secretData = allSecrets.find(s => s.id === secretId);
    if (!secretData) return;
    
    // Build file URL (используем безопасные данные)
    let fileUrl;
    try {
        if (projectRepoUrl.includes('devzone.local')) {
            // DevZone/GitLab URL format
            fileUrl = `${projectRepoUrl}/-/blob/${scanCommit}/${encodeURIComponent(secretData.path || '')}#L${secretData.line}-${secretData.line}`;
        } else if (hubType === 'Azure') {
            // Azure DevOps URL format
            const startColumn = 1;
            const secretLength = secretData.secret ? secretData.secret.length : 0;
            const endColumn = secretLength + 1;
            fileUrl = `${projectRepoUrl}?path=${encodeURIComponent(secretData.path || '')}&version=GC${scanCommit}&line=${secretData.line}&lineEnd=${secretData.line}&lineStartColumn=${startColumn}&lineEndColumn=${endColumn}&_a=contents`;
        } else {
            // Default/GitHub URL format
            const safePath = (secretData.path || '').split('/').map(encodeURIComponent).join('/');
            fileUrl = `${projectRepoUrl}/blob/${scanCommit}${safePath}?plain=1#L${secretData.line}`;
        }
    } catch (error) {
        console.error('Error building file URL:', error);
        fileUrl = '#';
    }
    
    window._detailPanelFullContext = secretData.context || '';
    window._detailPanelFullContextSecret = secretData.secret || '';
    window._detailPanelSecretId = secretId;

    const { text: contextPreview, hasMore: contextHasMore } = truncateContextAroundSecret(secretData.context || '', secretData.secret || '');
    const decodedPreview = _decodeHtmlEntities(contextPreview);
    const decodedSecret = _decodeHtmlEntities(secretData.secret || '').trim();
    let contextDisplayHtml;
    const secretPos = decodedSecret ? decodedPreview.indexOf(decodedSecret) : -1;
    if (secretPos !== -1) {
        const before = escapeHtml(decodedPreview.slice(0, secretPos));
        const match = escapeHtml(decodedPreview.slice(secretPos, secretPos + decodedSecret.length));
        const after = escapeHtml(decodedPreview.slice(secretPos + decodedSecret.length));
        contextDisplayHtml = before + '<mark class="context-secret-highlight">' + match + '</mark>' + after;
    } else {
        contextDisplayHtml = escapeHtml(decodedPreview);
    }

    // Данные уже экранированы на сервере
    const safeSecret = safeHtml(secretData.secret || '');
    const safePath = safeHtml(secretData.path || '');
    const safeType = safeHtml(secretData.type || '');
    const safeComment = safeHtml(secretData.exception_comment || '');
    const safeHash = escapeHtml(secretData.hash_from_ci || '');

    let detailsButtonHtml = '';
    if (contextHasMore) {
        detailsButtonHtml = `
                <button type="button" class="btn btn-secondary context-more-btn" onclick="openContextModal()" style="margin-top: 0.5rem;">
                    Подробнее
                </button>`;
    }
    
    // Добавить информацию о пользователях
    let userInfoHtml = '';
    if ((secretData.confirmed_by && secretData.confirmed_by.trim() !== '') || 
        (secretData.refuted_by && secretData.refuted_by.trim() !== '')) {
        userInfoHtml = `
            <div class="detail-section">
                <h4>👮 Информация об изменениях</h4>
                <div class="detail-field" style="background: #f0f9ff; border-left: 3px solid #3b82f6;">
                    ${secretData.confirmed_by ? `✅ Подтвержден пользователем: <strong>${escapeHtml(secretData.confirmed_by)}</strong>` : ''}
                    ${secretData.refuted_by ? `❌ Опровергнут пользователем: <strong>${escapeHtml(secretData.refuted_by)}</strong>` : ''}
                    ${secretData.refuted_at ? `<br><small>Дата: ${escapeHtml(secretData.refuted_at)}</small>` : ''}
                </div>
            </div>
        `;
    }

    let previousStatusHtml = '';
    if (secretData.previous_status || secretData.previous_severity) {
        let statusPart = '';
        let severityPart = '';
        
        if (secretData.previous_status) {
            const statusIcon = secretData.previous_status === 'Confirmed' ? '✅' : '❌';
            const statusClass = secretData.previous_status === 'Confirmed' ? 'status-confirmed' : 'status-refuted';
            statusPart = `Статус: <span class="${statusClass}">${statusIcon} ${safeHtml(secretData.previous_status)}</span>`;
        }
        
        if (secretData.previous_severity && secretData.previous_severity !== secretData.severity) {
            const severityIcon = secretData.previous_severity === 'High' ? '🔴' : '🟡';
            severityPart = `Уровень: <span style="color: ${secretData.previous_severity === 'High' ? '#dc2626' : '#6b7280'};">${severityIcon} ${safeHtml(secretData.previous_severity)}</span> → <span style="color: ${secretData.severity === 'High' ? '#dc2626' : '#6b7280'};">${secretData.severity === 'High' ? '🔴' : '🟡'} ${safeHtml(secretData.severity)}</span>`;
        }
        
        let content = [statusPart, severityPart].filter(p => p).join('<br>');
        
        previousStatusHtml = `
            <div class="detail-section">
                <h4>📊 Предыдущие изменения</h4>
                <div class="detail-field" style="background: #fef3c7; border-left: 3px solid #f59e0b;">
                    ${content}<br>
                    <small style="color: #666;">Изменено ${safeHtml(secretData.previous_scan_date || '')}</small>
                </div>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Настройки этого секрета были автоматически применены на основе ваших предыдущих решений. При необходимости вы можете изменить их.
                </div>
            </div>
        `;
    }

    let restoreHtml = '';
    if (secretData.status === 'Refuted') {
        restoreHtml = `
            <div class="detail-section">
                <h4>🔄 Quick Restore</h4>
                <button class="btn btn-warning" onclick="restoreSingleSecret(${secretId})" style="width: 100%;">
                    🔄 Restore This Secret
                </button>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Это изменит статус с "Опровергнуто" на "Нет статуса", чтобы он отображался в основном отчете.
                </div>
            </div>
        `;
    }
    
    const detailPanel = document.getElementById('detailPanel');
    if (!detailPanel) return;
    
    detailPanel.innerHTML = `
        <div class="detail-content">
            <h3>Secret Details</h3>
            
            <div class="detail-section">
                <h4>🔑 Значение секрета</h4>
                <div class="detail-field" style="background: #fef3c7; border: 1px solid #f59e0b; color: #92400e; font-weight: 600;">
                    ${safeSecret}
                </div>
            </div>
            
            <div class="status-controls">
                <h4 style="margin-bottom: 8px;">Статус</h4>
                <div class="status-buttons">
                    <button class="status-btn ${secretData.status === 'Confirmed' ? 'active' : ''}" 
                            onclick="updateSecretStatus(${secretId}, 'Confirmed')">
                        ✅ Подтвердить
                    </button>
                    <button class="status-btn ${secretData.status === 'No status' ? 'active' : ''}" 
                            onclick="updateSecretStatus(${secretId}, 'No status')">
                        ⚪ Без статуса
                    </button>
                    <button class="status-btn ${secretData.status === 'Refuted' ? 'active' : ''}" 
                            onclick="updateSecretStatus(${secretId}, 'Refuted')">
                        ❌ Опровергнуть
                    </button>
                </div>
                <div class="comment-section" style="display: ${secretData.status === 'Refuted' ? 'block' : 'none'};">
                    <label for="comment-${secretId}">Комментарий:</label>
                    <textarea id="comment-${secretId}" placeholder="Explain why this is not a real secret...">${safeComment}</textarea>
                    <button class="btn btn-primary" style="margin-top: 0.5rem; font-size: 0.8rem;" 
                            onclick="updateSecretStatus(${secretId}, 'Refuted')">
                        💾 Update Comment
                    </button>
                </div>
            </div>

            <div class="detail-section">
                <h4>⚠️ Severity Уровень</h4>
                <div style="display: flex; gap: 0.5rem;">
                    <button class="status-btn ${secretData.severity === 'High' ? 'active' : ''}" 
                            onclick="updateSecretSeverity(${secretId}, 'High')"
                            style="background: ${secretData.severity === 'High' ? '#dc2626' : '#fff'}; 
                                color: ${secretData.severity === 'High' ? '#fff' : '#dc2626'};">
                        🛑 High
                    </button>
                    <button class="status-btn ${secretData.severity === 'Potential' ? 'active' : ''}" 
                            onclick="updateSecretSeverity(${secretId}, 'Potential')"
                            style="background: ${secretData.severity === 'Potential' ? '#6b7280' : '#fff'}; 
                                color: ${secretData.severity === 'Potential' ? '#fff' : '#6b7280'};">
                        🔘 Potential
                    </button>
                </div>
            </div>
            
            <div class="detail-section">
                <h4>📁 Путь до файла</h4>
                <a href="${fileUrl}" target="_blank" class="detail-field clickable" style="display: block; text-decoration: none; color: inherit;">
                    ${safePath}
                </a>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Нажмите чтобы открыть в репозитории (строка выделяется при открытии)
                </div>
            </div>
            
            <div class="detail-section">
                <h4>📍 Номер строки</h4>
                <div class="detail-field">${secretData.line || 0}</div>
            </div>

            <div class="detail-section">
                <h4>🔐 CI Hash</h4>
                <div class="detail-field hash-field" style="font-family: monospace; font-size: 0.75rem; word-break: break-all; user-select: all;">
                    ${safeHash || '—'}
                </div>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.25rem;">
                    Хеш для CI (falses.txt): path + secret + line
                </div>
            </div>
            
            <div class="detail-section">
                <h4>📝 Контекст</h4>
                <div class="detail-field context-preview" style="white-space: pre-wrap; overflow-x: auto;">
                    ${contextDisplayHtml}
                </div>
                ${detailsButtonHtml}
            </div>
            
            <div class="detail-section">
                <h4>🏷️ Тип</h4>
                <div class="detail-field">${safeType}</div>
            </div>

            ${previousStatusHtml}
            ${userInfoHtml}
            ${restoreHtml}
            <div class="detail-section">
                <button 
                    class="btn btn-danger" 
                    onclick="deleteSecret(${secretId})"
                    style="width: 100%; background: #dc2626; color: white; font-weight: bold; display: flex; align-items: center; justify-content: center;">
                    🗑️ Удалить секрет из БД
                </button>
                <div style="font-size: 0.8rem; color: #666; margin-top: 0.5rem; text-align: center;">
                    ⚠️ Это действие нельзя будет отменить
                </div>
            </div>
        </div>
    `;
}

async function restoreSingleSecret(secretId) {
    if (confirm('Are you sure you want to restore this secret? It will be changed from "Refuted" to "No status".')) {
        try {
            const response = await fetch(`/secret_scanner/secrets/${secretId}/update-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ status: 'No status', comment: '' })
            });
            
            if (response.ok) {
                location.reload();
            } else {
                alert('Error restoring secret');
            }
        } catch (error) {
            console.error('Error restoring secret:', error);
            alert('Error restoring secret');
        }
    }
}

async function deleteSecret(secretId) {
    if (!confirm('Вы уверены, что хотите удалить этот секрет? Это действие нельзя отменить.')) {
        return;
    }
    
    try {
        const response = await fetch(`/secret_scanner/secrets/${secretId}/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            const previouslyCheckedTypes = getCheckedTypeFilters();
            secretsData = result.secrets_data || [];
            allSecrets = secretsData.slice();
            
            allSecrets.forEach(secret => normalizeSecretRecord(secret));
            
            // Очистить выделение и показать пустую панель
            selectedSecrets.clear();
            showEmptyDetail();
            
            // Переинициализировать фильтры и применить их (с сохранением сортировки)
            initializeFilters({ preserveTypes: previouslyCheckedTypes });
            applyFiltersSync();
            
            alert('Секрет успешно удален');
        } else {
            alert('Ошибка: ' + result.message);
        }
    } catch (error) {
        console.error('Error deleting secret:', error);
        alert('Ошибка при удалении секрета');
    }
}

async function updateSecretStatus(secretId, status) {
    const comment = document.getElementById(`comment-${secretId}`)?.value || '';
    
    try {
        const response = await fetch(`/secret_scanner/secrets/${secretId}/update-status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ status: status, comment: comment })
        });
        
        if (response.ok) {
            // Update local data
            const secret = allSecrets.find(s => s.id === secretId);
            if (secret) {
                secret.status = status;
                if (status === 'Refuted') {
                    secret.is_exception = true;
                    secret.exception_comment = comment;
                    secret.refuted_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
                } else {
                    secret.is_exception = false;
                    secret.exception_comment = null;
                    secret.refuted_at = null;
                }
            }
            
            // Reapply filters and reload details (с сохранением сортировки)
            applyFiltersSync();
            loadSecretDetails(secretId);
        }
    } catch (error) {
        console.error('Error updating status:', error);
        alert('Error updating status');
    }
}

async function updateSecretSeverity(secretId, severity) {
    try {
        const response = await fetch('/secret_scanner/secrets/bulk-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                secret_ids: [secretId],
                action: 'severity',
                value: severity
            })
        });
        
        if (response.ok) {
            // Update local data
            const secret = allSecrets.find(s => s.id === secretId);
            if (secret) {
                secret.severity = severity;
            }
            
            // Reapply filters and reload details (с сохранением сортировки)
            applyFiltersSync();
            loadSecretDetails(secretId);
        }
    } catch (error) {
        console.error('Error updating severity:', error);
        alert('Ошибка обновления severity');
    }
}

async function performBulkAction(action, value) {
    if (selectedSecrets.size === 0) {
        alert('Пожалуйста выберите хотя бы один секрет');
        return;
    }

    let comment = '';
    // Если действие "Refuted", запросим комментарий
    if (action === 'status' && value === 'Refuted') {
        const input = prompt('Введите комментарий (опционально):');
        if (input === null) {
            // Пользователь нажал "Отмена" — прекращаем действие
            return;
        }
        comment = input;
    }

    try {
        const response = await fetch('/secret_scanner/secrets/bulk-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                secret_ids: Array.from(selectedSecrets),
                action: action,
                value: value,
                comment: comment
            })
        });

        if (!response.ok) {
            alert('Ошибка при выполнении массового действия');
            return;
        }

        // Обновление локальных данных
        selectedSecrets.forEach(secretId => {
            const secret = allSecrets.find(s => s.id === secretId);
            if (!secret) return;

            if (action === 'status') {
                secret.status = value;

                if (value === 'Refuted') {
                    secret.is_exception = true;
                    secret.exception_comment = comment;
                    secret.refuted_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
                } else {
                    secret.is_exception = false;
                    secret.exception_comment = null;
                    secret.refuted_at = null;
                }
            } else if (action === 'severity') {
                secret.severity = value;
            }
        });

        // Очистка выделенных секретов и обновление UI
        selectedSecrets.clear();
        showEmptyDetail();
        applyFiltersSync();

    } catch (error) {
        console.error('Ошибка при выполнении массового действия:', error);
        alert('Ошибка при выполнении массового действия');
    }
}

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
    const size = parseInt(urlParams.get('page_size')) || 2000; // Изменено с 1000 на 2000
    
    currentPage = page;
    pageSize = size;
    const pageSizeSelect = document.getElementById('pageSize');
    if (pageSizeSelect) {
        pageSizeSelect.value = size;
    }
});