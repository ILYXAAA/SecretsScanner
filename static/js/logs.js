let autoRefreshEnabled = true;
let autoScrollEnabled = true;
let refreshInterval;
let lastLogSize = 0;
let currentLogLines = [];
let filteredLines = [];
let linesLimit = 500;
let searchTerm = '';
let currentLogLevel = '';
let lastDisplayedLines = [];
let lastLogHash = ''; // Для более точного сравнения изменений
let currentLogSource = 'main';

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    startAutoRefresh();
    refreshLogs();
});

function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    
    if (autoRefreshEnabled) {
        refreshInterval = setInterval(refreshLogs, 2000);
    }
}

function changeLogSource() {
    const select = document.getElementById('logSourceSelect');
    currentLogSource = select.value;
    
    // Обновляем информацию о файле
    const logInfo = document.getElementById('logInfo');
    logInfo.textContent = currentLogSource === 'main' ? 'secrets_scanner.log' : 'microservice.log';
    
    // Очищаем текущие логи и перезагружаем
    clearDisplay();
    currentLogLines = [];
    lastDisplayedLines = [];
    lastLogHash = '';
    
    // Обновляем логи для нового источника
    refreshLogs();
}

function toggleAutoRefresh() {
    autoRefreshEnabled = !autoRefreshEnabled;
    const btn = document.getElementById('autoRefreshBtn');
    
    if (autoRefreshEnabled) {
        btn.textContent = 'ON';
        btn.classList.add('active');
        startAutoRefresh();
        updateStatus('Auto-refresh enabled');
    } else {
        btn.textContent = 'OFF';
        btn.classList.remove('active');
        clearInterval(refreshInterval);
        updateStatus('Auto-refresh disabled');
    }
}

function toggleAutoScroll() {
    autoScrollEnabled = !autoScrollEnabled;
    const btn = document.getElementById('autoScrollBtn');
    const indicator = document.getElementById('autoScrollIndicator');
    
    if (autoScrollEnabled) {
        btn.textContent = 'ON';
        btn.classList.add('active');
        scrollToBottom();
        updateStatus('Auto-scroll enabled');
    } else {
        btn.textContent = 'OFF';
        btn.classList.remove('active');
        indicator.classList.remove('visible');
        updateStatus('Auto-scroll disabled');
    }
}

function setLinesLimit() {
    const select = document.getElementById('linesLimit');
    linesLimit = select.value === 'all' ? 'all' : parseInt(select.value);
    filterLogs();
}

function updateStatus(message) {
    document.getElementById('connectionStatus').textContent = message;
}

function showLoading(show) {
    const loadingElement = document.getElementById('loadingIndicator');
    if (show) {
        loadingElement.classList.add('visible');
    } else {
        loadingElement.classList.remove('visible');
    }
}

// Создаем простой хеш для сравнения содержимого
function createHash(lines) {
    return lines.join('').length + '_' + (lines.length > 0 ? lines[lines.length - 1].substring(0, 50) : '');
}

async function refreshLogs() {
    try {
        showLoading(true);
        
        const apiLogs = document.body.dataset.apiLogs;
        const apiMicroserviceLogs = document.body.dataset.apiMicroserviceLogs;
        
        const endpoint = currentLogSource === 'main' ? apiLogs : apiMicroserviceLogs;
        
        const response = await fetch(endpoint);
        const data = await response.json();
        
        if (data.status === 'success') {
            const newSize = data.size;
            const newLines = data.lines;
            const newHash = createHash(newLines);
            
            // Update stats
            document.getElementById('fileSize').textContent = formatFileSize(newSize);
            document.getElementById('lastUpdated').textContent = new Date().toLocaleTimeString();
            
            // Проверяем, действительно ли изменились данные
            if (newHash !== lastLogHash) {
                lastLogHash = newHash;
                const oldLinesCount = currentLogLines.length;
                currentLogLines = newLines;
                
                // Применяем фильтры
                const newFilteredLines = applyFilters(newLines);
                
                // Проверяем, есть ли новые строки для добавления
                const newLinesCount = newFilteredLines.length - lastDisplayedLines.length;
                
                if (newLinesCount > 0 && canAppendNewLines(lastDisplayedLines, newFilteredLines)) {
                    // Добавляем только новые строки
                    appendNewLines(newFilteredLines.slice(-newLinesCount));
                } else if (!arraysEqual(newFilteredLines, lastDisplayedLines)) {
                    // Полная перерисовка только если действительно нужно
                    displayLogs(newFilteredLines, true);
                }
                
                lastDisplayedLines = [...newFilteredLines];
                updateStatus('Connected');
            } else {
                updateStatus('Up to date');
            }
        } else {
            updateStatus('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error refreshing logs:', error);
        updateStatus('Connection error');
    } finally {
        showLoading(false);
    }
}

function arraysEqual(a, b) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
        if (a[i] !== b[i]) return false;
    }
    return true;
}

function canAppendNewLines(oldLines, newLines) {
    // Проверяем, можно ли просто добавить новые строки
    if (newLines.length <= oldLines.length) return false;
    
    const overlap = Math.min(oldLines.length, newLines.length);
    if (overlap === 0) return true;
    
    // Проверяем совпадение последних строк
    for (let i = 0; i < overlap; i++) {
        if (oldLines[oldLines.length - 1 - i] !== newLines[newLines.length - 1 - i - (newLines.length - oldLines.length)]) {
            return false;
        }
    }
    return true;
}

function appendNewLines(newLines) {
    const container = document.getElementById('logContent');
    const wasAtBottom = isScrolledToBottom();
    
    // Создаем fragment для эффективной вставки
    const fragment = document.createDocumentFragment();
    
    newLines.forEach((line) => {
        const lineDiv = createLogLineElement(line, true); // Помечаем как новую строку
        fragment.appendChild(lineDiv);
    });
    
    container.appendChild(fragment);
    
    // Обновляем счетчик
    document.getElementById('totalLines').textContent = lastDisplayedLines.length;
    
    // Удаляем старые строки если превышен лимит
    if (linesLimit !== 'all') {
        while (container.children.length > linesLimit) {
            container.removeChild(container.firstChild);
        }
    }
    
    // Auto-scroll если нужно
    if (autoScrollEnabled && wasAtBottom) {
        scrollToBottom();
    }
}

function applyFilters(lines) {
    let filteredLines = [...lines];
    
    // Apply log level filter
    if (currentLogLevel) {
        filteredLines = filteredLines.filter(line => line.includes(`- ${currentLogLevel} -`));
    }
    
    // Apply search filter
    if (searchTerm) {
        filteredLines = filteredLines.filter(line => 
            line.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }
    
    // Apply lines limit
    if (linesLimit !== 'all') {
        filteredLines = filteredLines.slice(-linesLimit);
    }
    
    return filteredLines;
}

function filterLogs() {
    const newFilteredLines = applyFilters(currentLogLines);
    displayLogs(newFilteredLines, false);
    lastDisplayedLines = [...newFilteredLines];
    document.getElementById('totalLines').textContent = newFilteredLines.length;
}

function createLogLineElement(line, isNew = false) {
    const lineDiv = document.createElement('div');
    lineDiv.className = 'log-line';
    
    // Добавляем анимацию только для действительно новых строк
    if (isNew) {
        lineDiv.classList.add('new-line');
        // Убираем класс после завершения анимации
        setTimeout(() => {
            lineDiv.classList.remove('new-line');
        }, 1500);
    }
    
    // Detect log level and apply appropriate class
    let logLevel = '';
    if (line.includes(' - INFO - ')) logLevel = 'INFO';
    else if (line.includes(' - WARNING - ')) logLevel = 'WARNING';
    else if (line.includes(' - ERROR - ')) logLevel = 'ERROR';
    else if (line.includes(' - DEBUG - ')) logLevel = 'DEBUG';
    else if (line.includes(' - CRITICAL - ')) logLevel = 'CRITICAL';
    
    if (logLevel) {
        lineDiv.classList.add(logLevel);
    }
    
    // Format line with syntax highlighting
    let formattedLine = formatLogLine(line);
    
    // Apply search highlighting
    if (searchTerm) {
        formattedLine = highlightSearch(formattedLine, searchTerm);
    }
    
    lineDiv.innerHTML = formattedLine;
    return lineDiv;
}

function displayLogs(lines, preserveScroll = true) {
    const container = document.getElementById('logContent');
    const wasAtBottom = preserveScroll ? isScrolledToBottom() : false;
    const scrollTop = preserveScroll ? container.scrollTop : 0;
    
    if (lines.length === 0) {
        container.innerHTML = '<div style="color: #6b7280; text-align: center; padding: 40px;">No logs match the current filters</div>';
        return;
    }
    
    // Используем DocumentFragment для эффективной вставки
    const fragment = document.createDocumentFragment();
    
    lines.forEach((line) => {
        const lineDiv = createLogLineElement(line, false); // Не помечаем как новые при полной перерисовке
        fragment.appendChild(lineDiv);
    });
    
    // Одна операция замены содержимого
    container.innerHTML = '';
    container.appendChild(fragment);
    
    // Восстанавливаем позицию скролла
    if (preserveScroll && !wasAtBottom) {
        container.scrollTop = scrollTop;
    }
    
    // Auto-scroll если нужно
    if (autoScrollEnabled && (wasAtBottom || !preserveScroll)) {
        scrollToBottom();
    }
}

function formatLogLine(line) {
    const logPattern = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[^-]*) - ([^-]+) - ([^-]+) - (.*)$/;
    const match = line.match(logPattern);
    
    if (match) {
        const [, timestamp, loggerName, level, message] = match;
        return `<span class="timestamp">${timestamp.trim()}</span><span class="logger-name">${loggerName.trim()}</span><strong>${level.trim()}</strong> - ${message}`;
    }
    
    return line;
}

function highlightSearch(text, term) {
    if (!term) return text;
    
    const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return text.replace(regex, '<span class="search-highlight">$1</span>');
}

function isScrolledToBottom() {
    const container = document.getElementById('logContent');
    return container.scrollTop + container.clientHeight >= container.scrollHeight - 10;
}

function scrollToBottom() {
    const container = document.getElementById('logContent');
    container.scrollTop = container.scrollHeight;
    
    const indicator = document.getElementById('autoScrollIndicator');
    indicator.classList.add('visible');
    setTimeout(() => indicator.classList.remove('visible'), 1000);
}

function searchLogs() {
    searchTerm = document.getElementById('searchInput').value;
    filterLogs();
}

function filterLogsByLevel() {
    currentLogLevel = document.getElementById('logLevelFilter').value;
    filterLogs();
}

// Bind the filter function to the select element
document.getElementById('logLevelFilter').addEventListener('change', filterLogsByLevel);

function clearDisplay() {
    document.getElementById('logContent').innerHTML = '<div style="color: #6b7280; text-align: center; padding: 40px;">Display cleared. Refresh to reload logs.</div>';
    currentLogLines = [];
    lastDisplayedLines = [];
    lastLogHash = '';
    document.getElementById('totalLines').textContent = '0';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Handle scroll events to control auto-scroll indicator
document.getElementById('logContent').addEventListener('scroll', function() {
    const indicator = document.getElementById('autoScrollIndicator');
    
    if (autoScrollEnabled && !isScrolledToBottom()) {
        indicator.classList.remove('visible');
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});