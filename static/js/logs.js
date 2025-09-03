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
let lastLogHash = '';
let currentLogSource = 'main';
let selectedStartDate = '';
let selectedEndDate = '';

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initializeDatePickers();
    startAutoRefresh();
    refreshLogs();
});

function initializeDatePickers() {
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    
    // Set default dates (last 7 days)
    const today = new Date();
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
    
    startDateInput.value = weekAgo.toISOString().split('T')[0];
    endDateInput.value = today.toISOString().split('T')[0];
}

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
    
    const logInfo = document.getElementById('logInfo');
    if (currentLogSource === 'main') {
        logInfo.textContent = 'secrets_scanner.log';
    } else if (currentLogSource === 'microservice') {
        logInfo.textContent = 'microservice.log';
    } else if (currentLogSource === 'user_actions') {
        logInfo.textContent = 'user_actions.log';
    }
    
    clearDisplay();
    currentLogLines = [];
    lastDisplayedLines = [];
    lastLogHash = '';
    
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
    linesLimit = select.value === 'all' ? 0 : parseInt(select.value);
    filterLogs();
}

function showDatePicker() {
    const modal = document.getElementById('datePickerModal');
    modal.classList.add('visible');
}

function hideDatePicker() {
    const modal = document.getElementById('datePickerModal');
    modal.classList.remove('visible');
}

function applyDateFilter() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    if (startDate && endDate && startDate > endDate) {
        alert('Начальная дата не может быть позже конечной даты');
        return;
    }
    
    selectedStartDate = startDate;
    selectedEndDate = endDate;
    
    // Update UI to show selected dates
    updateDateDisplays();
    
    hideDatePicker();
    
    // Clear current data and refresh with date filter
    clearDisplay();
    currentLogLines = [];
    lastDisplayedLines = [];
    lastLogHash = '';
    refreshLogs();
}

function clearDateFilter() {
    selectedStartDate = '';
    selectedEndDate = '';
    
    // Clear the date inputs
    document.getElementById('startDate').value = '';
    document.getElementById('endDate').value = '';
    
    updateDateDisplays();
    hideDatePicker();
    
    // Refresh without date filter
    clearDisplay();
    currentLogLines = [];
    lastDisplayedLines = [];
    lastLogHash = '';
    refreshLogs();
}

function updateDateDisplays() {
    const dateRangeInfo = document.getElementById('dateRangeInfo');
    if (selectedStartDate || selectedEndDate) {
        let rangeText = 'Filtered: ';
        if (selectedStartDate && selectedEndDate) {
            rangeText += selectedStartDate + ' — ' + selectedEndDate;
        } else if (selectedStartDate) {
            rangeText += 'from ' + selectedStartDate;
        } else if (selectedEndDate) {
            rangeText += 'until ' + selectedEndDate;
        }
        dateRangeInfo.textContent = rangeText;
        dateRangeInfo.style.display = 'block';
    } else {
        dateRangeInfo.style.display = 'none';
    }
}

function downloadLogs() {
    const apiLogs = document.body.dataset.apiLogs;
    const apiMicroserviceLogs = document.body.dataset.apiMicroserviceLogs;
    const apiUserActionsLogs = document.body.dataset.apiUserActionsLogs;
    
    // Determine which endpoint to use
    let baseEndpoint;
    if (currentLogSource === 'main') {
        baseEndpoint = apiLogs.replace('/api/logs', '/api/download-logs');
    } else if (currentLogSource === 'microservice') {
        baseEndpoint = apiMicroserviceLogs.replace('/api/microservice-logs', '/api/download-microservice-logs');
    } else if (currentLogSource === 'user_actions') {
        baseEndpoint = apiUserActionsLogs.replace('/api/user-actions-logs', '/api/download-user-actions-logs');
    }
    
    // Build query parameters for date filtering
    const params = new URLSearchParams();
    if (selectedStartDate) {
        params.append('start_date', selectedStartDate);
    }
    if (selectedEndDate) {
        params.append('end_date', selectedEndDate);
    }
    
    const downloadUrl = params.toString() ? baseEndpoint + '?' + params : baseEndpoint;
    
    // Show loading indicator
    updateStatus('Preparing download...');
    
    // Create temporary link to trigger download
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Update status
    setTimeout(function() {
        updateStatus('Download initiated');
    }, 1000);
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

function createHash(lines) {
    return lines.join('').length + '_' + (lines.length > 0 ? lines[lines.length - 1].substring(0, 50) : '');
}

async function refreshLogs() {
    try {
        showLoading(true);
        
        const apiLogs = document.body.dataset.apiLogs;
        const apiMicroserviceLogs = document.body.dataset.apiMicroserviceLogs;
        const apiUserActionsLogs = document.body.dataset.apiUserActionsLogs;
        
        let endpoint;
        if (currentLogSource === 'main') {
            endpoint = apiLogs;
        } else if (currentLogSource === 'microservice') {
            endpoint = apiMicroserviceLogs;
        } else if (currentLogSource === 'user_actions') {
            endpoint = apiUserActionsLogs;
        }
        
        // Build query parameters
        const params = new URLSearchParams();
        if (linesLimit > 0) {
            params.append('lines', linesLimit);
        } else {
            params.append('lines', '0'); // 0 means all lines
        }
        
        if (selectedStartDate) {
            params.append('start_date', selectedStartDate);
        }
        if (selectedEndDate) {
            params.append('end_date', selectedEndDate);
        }
        
        const response = await fetch(endpoint + '?' + params);
        const data = await response.json();
        
        if (data.status === 'success') {
            const newSize = data.size;
            const newLines = data.lines;
            const newHash = createHash(newLines);
            
            // Update stats
            document.getElementById('fileSize').textContent = formatFileSize(newSize);
            document.getElementById('lastUpdated').textContent = new Date().toLocaleTimeString();
            
            if (newHash !== lastLogHash) {
                lastLogHash = newHash;
                const oldLinesCount = currentLogLines.length;
                currentLogLines = newLines;
                
                const newFilteredLines = applyFilters(newLines);
                
                const newLinesCount = newFilteredLines.length - lastDisplayedLines.length;
                
                if (newLinesCount > 0 && canAppendNewLines(lastDisplayedLines, newFilteredLines)) {
                    appendNewLines(newFilteredLines.slice(-newLinesCount));
                } else if (!arraysEqual(newFilteredLines, lastDisplayedLines)) {
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
    if (newLines.length <= oldLines.length) return false;
    
    const overlap = Math.min(oldLines.length, newLines.length);
    if (overlap === 0) return true;
    
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
    
    const fragment = document.createDocumentFragment();
    
    newLines.forEach(function(line) {
        const lineDiv = createLogLineElement(line, true);
        fragment.appendChild(lineDiv);
    });
    
    container.appendChild(fragment);
    
    document.getElementById('totalLines').textContent = lastDisplayedLines.length;
    
    if (linesLimit > 0) {
        while (container.children.length > linesLimit) {
            container.removeChild(container.firstChild);
        }
    }
    
    if (autoScrollEnabled && wasAtBottom) {
        scrollToBottom();
    }
}

function applyFilters(lines) {
    let filteredLines = [...lines];
    
    if (currentLogLevel) {
        filteredLines = filteredLines.filter(function(line) {
            return line.includes('- ' + currentLogLevel + ' -');
        });
    }
    
    if (searchTerm) {
        filteredLines = filteredLines.filter(function(line) {
            return line.toLowerCase().includes(searchTerm.toLowerCase());
        });
    }
    
    return filteredLines;
}

function filterLogs() {
    const newFilteredLines = applyFilters(currentLogLines);
    displayLogs(newFilteredLines, false);
    lastDisplayedLines = [...newFilteredLines];
    document.getElementById('totalLines').textContent = newFilteredLines.length;
}

function createLogLineElement(line, isNew) {
    if (isNew === undefined) isNew = false;
    
    const lineDiv = document.createElement('div');
    lineDiv.className = 'log-line';
    
    if (isNew) {
        lineDiv.classList.add('new-line');
        setTimeout(function() {
            lineDiv.classList.remove('new-line');
        }, 1500);
    }
    
    // Handle multi-line log entries
    const lines = line.split('\n');
    const firstLine = lines[0];
    
    // Detect log level from the first line
    let logLevel = '';
    if (firstLine.includes(' - INFO - ')) logLevel = 'INFO';
    else if (firstLine.includes(' - WARNING - ')) logLevel = 'WARNING';
    else if (firstLine.includes(' - ERROR - ')) logLevel = 'ERROR';
    else if (firstLine.includes(' - DEBUG - ')) logLevel = 'DEBUG';
    else if (firstLine.includes(' - CRITICAL - ')) logLevel = 'CRITICAL';
    
    if (logLevel) {
        lineDiv.classList.add(logLevel);
    }
    
    // Format the entire log entry (including multiline parts)
    let formattedContent = '';
    lines.forEach(function(singleLine, index) {
        if (index === 0) {
            // Format the main log line
            formattedContent += formatLogLine(singleLine);
        } else {
            // Additional lines (stack traces, etc.)
            formattedContent += '<br><span class="additional-line">' + escapeHtml(singleLine) + '</span>';
        }
    });
    
    // Apply search highlighting
    if (searchTerm) {
        formattedContent = highlightSearch(formattedContent, searchTerm);
    }
    
    lineDiv.innerHTML = formattedContent;
    return lineDiv;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function displayLogs(lines, preserveScroll) {
    if (preserveScroll === undefined) preserveScroll = true;
    
    const container = document.getElementById('logContent');
    const wasAtBottom = preserveScroll ? isScrolledToBottom() : false;
    const scrollTop = preserveScroll ? container.scrollTop : 0;
    
    if (lines.length === 0) {
        container.innerHTML = '<div style="color: #6b7280; text-align: center; padding: 40px;">No logs match the current filters</div>';
        return;
    }
    
    const fragment = document.createDocumentFragment();
    
    lines.forEach(function(line) {
        const lineDiv = createLogLineElement(line, false);
        fragment.appendChild(lineDiv);
    });
    
    container.innerHTML = '';
    container.appendChild(fragment);
    
    if (preserveScroll && !wasAtBottom) {
        container.scrollTop = scrollTop;
    }
    
    if (autoScrollEnabled && (wasAtBottom || !preserveScroll)) {
        scrollToBottom();
    }
}

function formatLogLine(line) {
    const logPattern = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[^-]*) - ([^-]+) - ([^-]+) - (.*)$/;
    const match = line.match(logPattern);
    
    if (match) {
        let timestamp = match[1].trim();
        const loggerName = match[2];
        const level = match[3];
        let message = match[4];
        
        // Преобразуем формат времени из 2025-09-03 18:23:07,693 в 03.09.2025 18:23:07
        const timeMatch = timestamp.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2})/);
        if (timeMatch) {
            const year = timeMatch[1];
            const month = timeMatch[2];
            const day = timeMatch[3];
            const time = timeMatch[4];
            timestamp = `${day}.${month}.${year} ${time}`;
        }
        
        // Выделяем слова в одинарных кавычках жирным без самих кавычек
        message = message.replace(/'([^']+)'/g, '<span class="quoted-text">$1</span>');
        
        return '<span class="timestamp">' + timestamp + '</span><span class="logger-name">' + loggerName.trim() + '</span><strong>' + level.trim() + '</strong> - ' + message;
    }
    
    // Для строк без стандартного формата тоже применяем выделение кавычек
    let formattedLine = escapeHtml(line);
    formattedLine = formattedLine.replace(/'([^']+)'/g, '<span class="quoted-text">$1</span>');
    
    return formattedLine;
}

function highlightSearch(text, term) {
    if (!term) return text;
    
    const regex = new RegExp('(' + term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
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
    setTimeout(function() {
        indicator.classList.remove('visible');
    }, 1000);
}

function searchLogs() {
    searchTerm = document.getElementById('searchInput').value;
    filterLogs();
}

function filterLogsByLevel() {
    currentLogLevel = document.getElementById('logLevelFilter').value;
    filterLogs();
}

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

// Close modal when clicking outside
document.getElementById('datePickerModal').addEventListener('click', function(e) {
    if (e.target === this) {
        hideDatePicker();
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});