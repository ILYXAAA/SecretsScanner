// Global variables
let autoRefreshInterval;
let systemStatsCache = null;
let lastUpdateTime = null;
let currentTasksFilter = '';
// let currentTab = 'all';
let tasksData = [];
let filteredTasksData = [];
let currentPage = 1;
let tasksPerPage = 20; // Изменено с 50 на 20
let totalPages = 1;
let availableWorkers = [];
let searchQuery = '';
let workerFilter = '';
let taskTypeFilter = '';
let availableTaskTypes = [];

function getIcon(name, size = 24) {
    return `<img src="/secret_scanner/static/icons/${name}.svg" 
                 alt="${name}" 
                 width="${size}" 
                 height="${size}" 
                 style="vertical-align: middle;">`;
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    initializePage();
});

function initializePage() {
    // Load initial data
    refreshWorkersData();
    refreshSystemStats();
    refreshTasks();
    
    // Start auto-refresh for workers and queue data
    startAutoRefresh();
    
    // Setup auto-refresh toggle
    setupAutoRefreshToggle();
}

function setupAutoRefreshToggle() {
    const toggle = document.getElementById('autoRefreshToggle');
    if (toggle) {
        toggle.addEventListener('change', function() {
            if (this.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
    }
}

function startAutoRefresh() {
    // Stop existing interval if any
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    // Refresh workers and queue data every 5 seconds
    autoRefreshInterval = setInterval(() => {
        refreshWorkersData();
        // Also refresh tasks if we're showing current data
        // if (currentTab !== 'completed') {
        //     refreshTasks();
        // }
        if (currentTasksFilter !== 'completed') {
            refreshTasks();
        }
    }, 5000);
    
    updateRefreshStatus('🔄 Автообновление активно');
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
    updateRefreshStatus('⏸️ Автообновление остановлено');
}

function updateRefreshStatus(status) {
    const statusElement = document.getElementById('refresh-status');
    const lastUpdateElement = document.getElementById('last-update');
    
    if (statusElement) {
        statusElement.textContent = status;
    }
    
    if (lastUpdateElement && lastUpdateTime) {
        lastUpdateElement.textContent = `Последнее обновление: ${formatTime(lastUpdateTime)}`;
    }
}

function formatTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString('ru-RU');
}

function formatUptime(seconds) {
    const days = Math.floor(seconds / (24 * 3600));
    const hours = Math.floor((seconds % (24 * 3600)) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) {
        return `${days}д ${hours}ч ${minutes}м`;
    } else if (hours > 0) {
        return `${hours}ч ${minutes}м`;
    } else {
        return `${minutes}м`;
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString('ru-RU');
}

function formatTimeAgo(timestamp) {
    if (!timestamp) return '-';
    const now = Date.now() / 1000;
    const diff = now - timestamp;
    
    if (diff < 60) {
        return `${Math.floor(diff)} сек назад`;
    } else if (diff < 3600) {
        return `${Math.floor(diff / 60)} мин назад`;
    } else if (diff < 86400) {
        return `${Math.floor(diff / 3600)} ч назад`;
    } else {
        return `${Math.floor(diff / 86400)} дн назад`;
    }
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '-';
    
    if (seconds < 60) {
        return `${seconds.toFixed(1)}с`;
    } else if (seconds < 3600) {
        return `${Math.floor(seconds / 60)}м ${(seconds % 60).toFixed(0)}с`;
    } else {
        return `${Math.floor(seconds / 3600)}ч ${Math.floor((seconds % 3600) / 60)}м`;
    }
}

function showLoading(message = 'Выполняется операция...') {
    const overlay = document.getElementById('loadingOverlay');
    const messageElement = document.getElementById('loading-message');
    
    if (messageElement) {
        messageElement.textContent = message;
    }
    
    if (overlay) {
        overlay.style.display = 'flex';
    }
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

function showConfirmDialog(title, message, onConfirm, confirmText = 'Подтвердить') {
    const dialog = document.getElementById('confirmationDialog');
    const titleElement = document.getElementById('dialog-title');
    const messageElement = document.getElementById('dialog-message');
    const confirmBtn = document.getElementById('confirmBtn');
    
    if (titleElement) titleElement.textContent = title;
    if (messageElement) messageElement.textContent = message;
    if (confirmBtn) {
        confirmBtn.textContent = confirmText;
        confirmBtn.onclick = () => {
            hideConfirmDialog();
            onConfirm();
        };
    }
    
    if (dialog) {
        dialog.style.display = 'flex';
    }
}

function hideConfirmDialog() {
    const dialog = document.getElementById('confirmationDialog');
    if (dialog) {
        dialog.style.display = 'none';
    }
}

// API calls
async function refreshWorkersData() {
    try {
        const response = await fetch('/secret_scanner/admin/workers-status');
        const data = await response.json();
        
        if (data.status === 'success') {
            updateWorkersDisplay(data.workers || []);
            updateQueueStats(data.queue || {});
            updateWorkerFilter(data.workers || []);
            lastUpdateTime = Date.now();
            updateRefreshStatus('🔄 Автообновление активно');
        } else {
            console.error('Error refreshing workers data:', data.message);
            updateRefreshStatus('❌ Ошибка обновления');
        }
    } catch (error) {
        console.error('Error fetching workers data:', error);
        updateRefreshStatus('❌ Ошибка сети');
    }
}

async function refreshSystemStats() {
    try {
        showLoading('Загрузка системной статистики...');
        
        const response = await fetch('/secret_scanner/admin/service-stats');
        const data = await response.json();
        
        if (data.status === 'success') {
            systemStatsCache = data;
            updateSystemStats(data);
            updateQueueStats(data.queue || {});
        } else {
            console.error('Error refreshing system stats:', data.message);
        }
    } catch (error) {
        console.error('Error fetching system stats:', error);
    } finally {
        hideLoading();
    }
}

async function refreshTasks() {
    try {
        const status = currentTasksFilter || '';
        const limitInput = document.getElementById('tasksLimit');
        const limit = limitInput ? parseInt(limitInput.value) || 0 : 200;
        
        let url = '/secret_scanner/admin/tasks';
        const params = [];
        if (status) params.push(`status=${encodeURIComponent(status)}`);
        if (limit && limit > 0) params.push(`limit=${limit}`);
        if (params.length > 0) url += '?' + params.join('&');
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'success') {
            tasksData = data.tasks || [];
            updateTaskTypeFilter();
            applyFiltersAndPagination();
            updateTasksAnalytics();
        } else {
            console.error('Error refreshing tasks:', data.message);
        }
    } catch (error) {
        console.error('Error fetching tasks:', error);
    }
}

function updateTaskTypeFilter() {
    // Собираем уникальные типы задач из текущих данных
    const types = [...new Set(tasksData.map(task => task.task_type).filter(Boolean))];
    availableTaskTypes = types;
    
    const taskTypeFilterSelect = document.getElementById('taskTypeFilter');
    if (taskTypeFilterSelect) {
        const currentValue = taskTypeFilterSelect.value;
        taskTypeFilterSelect.innerHTML = '<option value="">Все типы</option>';
        
        availableTaskTypes.forEach(taskType => {
            const option = document.createElement('option');
            option.value = taskType;
            option.textContent = getTaskTypeText(taskType);
            if (taskType === currentValue) {
                option.selected = true;
            }
            taskTypeFilterSelect.appendChild(option);
        });
    }
}

function getTaskTypeText(taskType) {
    const texts = {
        'scan': '🔍 Scan',
        'multi_scan': '🔄 Multi Scan',
        'local_scan': '🔍 Local Scan'
    };
    return texts[taskType] || taskType;
}

function updateSystemStats(data) {
    const uptimeElement = document.getElementById('uptime');
    const cpuElement = document.getElementById('cpu-usage');
    const memoryElement = document.getElementById('memory-usage');
    
    if (uptimeElement && data.uptime_seconds) {
        uptimeElement.textContent = formatUptime(data.uptime_seconds);
    }
    
    if (cpuElement && data.system) {
        cpuElement.textContent = `${data.system.cpu_percent.toFixed(1)}%`;
    }
    
    if (memoryElement && data.system) {
        const memoryPercent = data.system.memory_percent.toFixed(1);
        const memoryUsed = data.system.memory_used_gb.toFixed(1);
        const memoryTotal = data.system.memory_total_gb.toFixed(1);
        memoryElement.textContent = `${memoryPercent}% (${memoryUsed}/${memoryTotal} GB)`;
    }
}

function updateQueueStats(data) {
    const pendingElement = document.getElementById('pending-tasks');
    const pendingQuickNumElement = document.getElementById('pending-tasks-quicknum');
    const processingElement = document.getElementById('processing-tasks');
    const completedElement = document.getElementById('completed-tasks');
    const failedElement = document.getElementById('failed-tasks');
    
    if (pendingElement) {
        const value = data.pending || 0;
        pendingElement.textContent = value;
        if (pendingQuickNumElement) {
            pendingQuickNumElement.textContent = value;
        }
    }
    
    // Fix processing count - calculate from individual status counts
    if (processingElement) {
        const processingCount = (data.downloading || 0) + (data.unpacking || 0) + 
                              (data.scanning || 0) + (data.ml_validation || 0);
        processingElement.textContent = processingCount;
    }
    
    if (completedElement) completedElement.textContent = data.completed || 0;
    if (failedElement) failedElement.textContent = data.failed || 0;
}

function updateWorkersDisplay(workers) {
    const workersGrid = document.getElementById('workers-grid');
    const emptyState = document.getElementById('empty-workers');
    const workersTitle = document.getElementById('workers-title');
    
    // Update title with worker count
    if (workersTitle) {
        const count = workers ? workers.length : 0;
        workersTitle.textContent = `👷 Список воркеров (${count})`;
    }
    
    if (!workers || workers.length === 0) {
        if (workersGrid) workersGrid.style.display = 'none';
        if (emptyState) emptyState.style.display = 'block';
        return;
    }
    
    if (workersGrid) workersGrid.style.display = 'grid';
    if (emptyState) emptyState.style.display = 'none';
    
    const workersHtml = workers.map(worker => createWorkerCard(worker)).join('');
    if (workersGrid) {
        workersGrid.innerHTML = workersHtml;
    }
}

function updateWorkerFilter(workers) {
    availableWorkers = workers.map(w => w.worker_id);
    const workerFilterSelect = document.getElementById('workerFilter');
    if (workerFilterSelect) {
        const currentValue = workerFilterSelect.value;
        workerFilterSelect.innerHTML = '<option value="">Все воркеры</option>';
        
        availableWorkers.forEach(workerId => {
            const option = document.createElement('option');
            option.value = workerId;
            option.textContent = workerId;
            if (workerId === currentValue) {
                option.selected = true;
            }
            workerFilterSelect.appendChild(option);
        });
    }
}

function createWorkerCard(worker) {
    const statusIcon = getStatusIcon(worker.status);
    const heartbeatClass = worker.process_alive ? 'alive' : 'dead';
    
    // Get progress information
    const progress = worker.current_task_progress;
    const progressDetail = worker.current_task_detail;
    const statusText = getStatusText(worker.status, progress, progressDetail);
    
    // Create progress bar if there's progress info
    let progressBarHtml = '';
    if (['unpacking', 'scanning', 'ml_validation'].includes(worker.status) && progress !== null && progress >= 0) {
        const progressPercent = Math.max(0, Math.min(100, progress));
        progressBarHtml = `
            <div class="worker-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progressPercent}%"></div>
                </div>
                <div class="progress-text">${Math.round(progressPercent)}%</div>
            </div>
        `;
        if (progressDetail) {
            progressBarHtml += `<div class="progress-detail">${progressDetail}</div>`;
        }
    }
    
    return `
        <div class="worker-card">
            <div class="worker-header">
                <div class="worker-id">🤖 ${worker.worker_id}</div>
                <div class="worker-status ${worker.status}">
                    ${statusIcon} ${statusText}
                    <span class="heartbeat-indicator ${heartbeatClass}"></span>
                </div>
            </div>
            
            ${progressBarHtml}
            
            <div class="worker-info">
                <div class="worker-info-left">
                    <div class="worker-info-item">
                        <span class="worker-info-icon">🔟</span>
                        PID: <span style="background-color: rgba(0,0,0,0.05); padding: 2px 4px; border-radius: 4px;">${worker.pid || '-'}</span>
                    </div>
                    <div class="worker-info-item">
                        <span class="worker-info-icon">📋</span>
                        Задача: <span style="background-color: rgba(0,0,0,0.05); padding: 2px 4px; border-radius: 4px;">${worker.current_task_id || '-'}</span>
                    </div>
                    <div class="worker-info-item">
                        <span class="worker-info-icon">🛜</span>
                        Пинг: <span style="background-color: rgba(0,0,0,0.05); padding: 2px 4px; border-radius: 4px;">${formatTimeAgo(worker.last_heartbeat)}</span>
                    </div>
                </div>
                <div class="worker-info-right">
                    <div class="worker-info-item">
                        <span class="worker-info-icon">🕒</span>
                        Запущен <span style="background-color: rgba(0,0,0,0.05); padding: 2px 4px; border-radius: 4px;">${formatTimeAgo(worker.started_at)}</span>
                    </div>
                    <div class="worker-info-item">
                        <span class="worker-info-icon">✅</span>
                        <span class="worker-info-value">${worker.tasks_completed || 0} задач выполнено</span>
                    </div>
                    <div class="worker-info-item">
                        <span class="worker-info-icon">❌</span>
                        <span class="worker-info-value">${worker.tasks_failed || 0} задач провалено</span>
                    </div>
                </div>
            </div>
            
            <div class="worker-actions">
                ${createWorkerActions(worker)}
            </div>
        </div>
    `;
}

function getStatusIcon(status) {
    const icons = {
        'free': '🟢',
        'busy': '🟡',
        'starting': '🔵',
        'stopping': '🟠',
        'not_responding': '🔴',
        'paused': '⏸️',
        'downloading': '⬇️',
        'unpacking': '📦',
        'scanning': '🔍',
        'ml_validation': '🤖'
    };
    return icons[status] || '❓';
}

function getStatusText(status, progress = null, progressDetail = null) {
    const texts = {
        'free': 'Свободен',
        'busy': 'Занят',
        'starting': 'Запускается',
        'stopping': 'Останавливается',
        'not_responding': 'Не отвечает',
        'paused': 'Приостановлен',
        'downloading': 'Скачивание',
        'unpacking': 'Распаковка',
        'scanning': 'Сканирование',
        'ml_validation': 'ML валидация'
    };
    
    let baseText = texts[status] || status;
    
    // Add progress for relevant statuses only if progress is valid and > 0
    // For workers - only percentage, no details
    if (['unpacking', 'scanning', 'ml_validation'].includes(status) && 
        progress !== null && progress >= 0 && progress <= 100) {
        baseText += ` (${Math.round(progress)}%)`;
    }
    
    return baseText;
}

function createWorkerActions(worker) {
    const actions = [];
    
    switch (worker.status) {
        case 'free':
        case 'busy':
        case 'downloading':
        case 'unpacking':
        case 'scanning':
        case 'ml_validation':
            actions.push(`<button class="btn btn-warning btn-small" onclick="pauseWorker('${worker.worker_id}')">⏸️ Pause</button>`);
            actions.push(`<button class="btn btn-info btn-small" onclick="restartWorker('${worker.worker_id}')">🔄 Restart</button>`);
            actions.push(`<button class="btn btn-secondary btn-small" onclick="stopWorker('${worker.worker_id}')">⏹️ Stop</button>`);
            actions.push(`<button class="btn btn-danger btn-small" onclick="killWorker('${worker.worker_id}')">💀 Kill</button>`);
            break;
            
        case 'paused':
            actions.push(`<button class="btn btn-primary btn-small" onclick="resumeWorker('${worker.worker_id}')">▶️ Resume</button>`);
            actions.push(`<button class="btn btn-secondary btn-small" onclick="stopWorker('${worker.worker_id}')">⏹️ Stop</button>`);
            actions.push(`<button class="btn btn-danger btn-small" onclick="killWorker('${worker.worker_id}')">💀 Kill</button>`);
            break;
            
        case 'not_responding':
            actions.push(`<button class="btn btn-info btn-small" onclick="restartWorker('${worker.worker_id}')">🔄 Restart</button>`);
            actions.push(`<button class="btn btn-danger btn-small" onclick="killWorker('${worker.worker_id}')">💀 Kill</button>`);
            break;
            
        case 'starting':
        case 'stopping':
            actions.push(`<button class="btn btn-danger btn-small" onclick="killWorker('${worker.worker_id}')">💀 Kill</button>`);
            break;
    }
    
    return actions.join('');
}

// Search and filtering functions
function searchTasks() {
    const searchInput = document.getElementById('projectSearch');
    if (searchInput) {
        searchQuery = searchInput.value.toLowerCase().trim();
        currentPage = 1;
        applyFiltersAndPagination();
    }
}

function filterTasks() {
    const filterSelect = document.getElementById('tasksFilter');
    const workerFilterSelect = document.getElementById('workerFilter');
    const taskTypeFilterSelect = document.getElementById('taskTypeFilter');
    
    if (filterSelect) {
        currentTasksFilter = filterSelect.value;
    }
    
    if (workerFilterSelect) {
        workerFilter = workerFilterSelect.value;
    }
    
    if (taskTypeFilterSelect) {
        taskTypeFilter = taskTypeFilterSelect.value;
    }
    
    currentPage = 1;
    refreshTasks();
}

function applyFiltersAndPagination() {
    // Start with all tasks
    let filtered = [...tasksData];
    
    // Apply tab filter
    // if (currentTab !== 'all') {
    //     filtered = filtered.filter(task => {
    //         switch (currentTab) {
    //             case 'pending':
    //                 return task.status === 'pending';
    //             case 'processing':
    //                 return ['downloading', 'unpacking', 'scanning', 'ml_validation'].includes(task.status);
    //             case 'completed':
    //                 return task.status === 'completed';
    //             case 'failed':
    //                 return task.status === 'failed';
    //             default:
    //                 return true;
    //         }
    //     });
    // }
    
    // Apply search filter - только по проекту и коммиту
    if (searchQuery) {
        filtered = filtered.filter(task => {
            const searchableText = (
                (task.project_name || '') + ' ' +
                (task.commit || '')
            ).toLowerCase();
            return searchableText.includes(searchQuery);
        });
    }
    
    // Apply worker filter
    if (workerFilter) {
        filtered = filtered.filter(task => task.worker_id === workerFilter);
    }
    
    // Apply task type filter
    if (taskTypeFilter) {
        filtered = filtered.filter(task => task.task_type === taskTypeFilter);
    }
    
    filteredTasksData = filtered;
    totalPages = Math.ceil(filteredTasksData.length / tasksPerPage);
    
    // Ensure current page is valid
    if (currentPage > totalPages) {
        currentPage = Math.max(1, totalPages);
    }
    
    updateTasksDisplay();
    updatePagination();
}

// function switchTab(tab) {
//     // Update active tab
//     document.querySelectorAll('.task-tab').forEach(btn => {
//         btn.classList.remove('active');
//     });
//     document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    
//     currentTab = tab;
//     currentPage = 1;
//     applyFiltersAndPagination();
// }

function updateTasksDisplay() {
    const tasksList = document.getElementById('tasks-list');
    const emptyTasks = document.getElementById('empty-tasks');
    
    if (!filteredTasksData || filteredTasksData.length === 0) {
        if (tasksList) tasksList.style.display = 'none';
        if (emptyTasks) emptyTasks.style.display = 'block';
        return;
    }
    
    if (tasksList) tasksList.style.display = 'flex';
    if (emptyTasks) emptyTasks.style.display = 'none';
    
    // Get tasks for current page
    const startIndex = (currentPage - 1) * tasksPerPage;
    const endIndex = startIndex + tasksPerPage;
    const tasksForPage = filteredTasksData.slice(startIndex, endIndex);
    
    const tasksHtml = tasksForPage.map(task => createTaskCard(task)).join('');
    if (tasksList) {
        tasksList.innerHTML = tasksHtml;
    }
}

function createTaskCard(task) {
    const statusIcon = getTaskStatusIcon(task.status);
    const taskTypeIcon = getTaskTypeIcon(task.task_type);
    const errorHtml = task.error ? `<div class="task-error">💥 ${task.error}</div>` : '';
    const retryButton = task.status === 'failed' ? `<button class="btn btn-warning btn-small" onclick="retryTask('${task.task_id}')">🔄 Повторить</button>` : '';
    
    // Get progress information
    const progress = task.progress;
    const progressDetail = task.progress_detail;
    const statusText = getTaskStatusText(task.status, progress, progressDetail);
    
    // Generate main title based on task type
    let mainTitle = '';
    const projectName = task.project_name || task.description || 'Задача';
    
    switch (task.task_type) {
        case 'scan':
            mainTitle = `🔍 Scan ${projectName}`;
            break;
        case 'local_scan':
            mainTitle = `📁 Local Scan ${projectName}`;
            break;
        case 'multi_scan':
            mainTitle = `🔄 Multi Scan ${projectName}`;
            break;
        default:
            mainTitle = `${taskTypeIcon} ${projectName}`;
    }
    
    // Create inline progress bar if there's progress info
    let progressBarHtml = '';
    if (['unpacking', 'scanning', 'ml_validation'].includes(task.status) && 
        progress !== null && progress > 0 && progress <= 100) {
        const progressPercent = Math.max(0, Math.min(100, progress));
        progressBarHtml = `
            <div class="task-progress-inline">
                <div class="progress-bar-inline">
                    <div class="progress-fill" style="width: ${progressPercent}%"></div>
                </div>
                <span class="progress-text-inline">${Math.round(progressPercent)}%</span>
            </div>
        `;
    }
    
    // Generate left details
    const leftDetails = [];
    if (task.worker_id) {
        leftDetails.push(`<div class="task-detail">
            <span class="task-detail-icon">🤖</span>
            <span class="task-detail-value">${task.worker_id}</span>
        </div>`);
    }
    if (task.execution_time) {
        leftDetails.push(`<div class="task-detail">
            <span class="task-detail-icon">⌛</span>
            <span class="task-detail-value">${formatDuration(task.execution_time)}</span>
        </div>`);
    }
    if (task.repo_url) {
        const repoLink = task.commit ? `${task.repo_url}/commit/${task.commit}` : task.repo_url;
        leftDetails.push(`<div class="task-detail">
            <span class="task-detail-icon">📂</span>
            <a href="${repoLink}" target="_blank" class="task-detail-value link">${task.repo_url}</a>
        </div>`);
    }
    if (task.commit) {
        leftDetails.push(`<div class="task-detail">
            <span class="task-detail-icon">🔗</span>
            <span class="task-detail-value">${task.commit}</span>
        </div>`);
    }
    
    // Generate right details - название задачи перед перезапусками
    const rightDetails = [];
    rightDetails.push(`<div class="task-detail">
        <span class="task-detail-icon">🔄</span>
        <span class="task-detail-value">${task.task_id}</span>
    </div>`);
    rightDetails.push(`<div class="task-detail">
        <span class="task-detail-icon">🔄</span>
        <span class="task-detail-value">${task.retry_count || 0} перезапусков</span>
    </div>`);
    rightDetails.push(`<div class="task-detail">
        <span class="task-detail-icon">⭐</span>
        <span class="task-detail-value">Приоритет ${task.priority || 1}</span>
    </div>`);
    rightDetails.push(`<div class="task-detail">
        <span class="task-detail-icon">📅</span>
        <span class="task-detail-value">Создана ${formatTimeAgo(task.created_at)}</span>
    </div>`);
    
    return `
        <div class="task-item">
            <div class="task-header">
                <div class="task-title-section">
                    <div class="task-main-title">${mainTitle}</div>
                </div>
                <div class="task-status-with-progress">
                    <div class="task-status ${task.status}">
                        ${statusIcon} ${statusText}
                    </div>
                    ${progressBarHtml}
                </div>
            </div>
            
            <div class="task-details">
                <div class="task-left-details">
                    ${leftDetails.join('')}
                </div>
                <div class="task-right-details">
                    ${rightDetails.join('')}
                </div>
            </div>
            
            ${errorHtml}
            
            <div class="task-actions">
                ${retryButton}
            </div>
        </div>
    `;
}

function getTaskStatusIcon(status) {
    const icons = {
        'pending': '⌛',
        'downloading': '⬇️',
        'unpacking': '📦',
        'scanning': '🔍',
        'ml_validation': '🤖',
        'completed': '✅',
        'failed': '❌'
    };
    return icons[status] || '❓';
}

function getTaskTypeIcon(taskType) {
    const icons = {
        'scan': '🔍',
        'multi_scan': '🔄',
        'local_scan': '🔍'
    };
    return icons[taskType] || '📋';
}

function getTaskStatusText(status, progress = null, progressDetail = null) {
    const texts = {
        'pending': 'В ожидании',
        'downloading': 'Скачивание',
        'unpacking': 'Распаковка',
        'scanning': 'Сканирование',
        'ml_validation': 'ML валидация',
        'completed': 'Завершено',
        'failed': 'Провалено'
    };
    
    let baseText = texts[status] || status;
    
    // Add progress for relevant statuses only if progress is valid and > 0
    // For tasks - percentage + details
    if (['unpacking', 'scanning', 'ml_validation'].includes(status) && 
        progress !== null && progress >= 0 && progress <= 100) {
        baseText += ` (${Math.round(progress)}%)`;
        if (progressDetail) {
            baseText += ` - ${progressDetail}`;
        }
    }
    
    return baseText;
}

function updatePagination() {
    const pagination = document.getElementById('pagination');
    const pageInfo = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    
    if (!pagination) return;
    
    if (totalPages <= 1) {
        pagination.style.display = 'none';
        return;
    }
    
    pagination.style.display = 'flex';
    
    if (pageInfo) {
        pageInfo.textContent = `Страница ${currentPage} из ${totalPages}`;
    }
    
    if (prevBtn) {
        prevBtn.disabled = currentPage <= 1;
    }
    
    if (nextBtn) {
        nextBtn.disabled = currentPage >= totalPages;
    }
}

function goToPage(page) {
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        updateTasksDisplay();
        updatePagination();
    }
}

function updateTasksAnalytics() {
    const analyticsContainer = document.getElementById('tasks-analytics');
    if (!analyticsContainer || !filteredTasksData) return;
    
    // Calculate analytics
    const completedTasks = filteredTasksData.filter(t => t.status === 'completed' && t.execution_time);
    const averageTime = completedTasks.length > 0 
        ? completedTasks.reduce((sum, t) => sum + t.execution_time, 0) / completedTasks.length
        : 0;
    
    const maxTime = completedTasks.length > 0
        ? Math.max(...completedTasks.map(t => t.execution_time))
        : 0;
    
    const minTime = completedTasks.length > 0
        ? Math.min(...completedTasks.map(t => t.execution_time))
        : 0;
    
    const totalTasks = filteredTasksData.length;
    const successRate = totalTasks > 0 
        ? ((filteredTasksData.filter(t => t.status === 'completed').length / totalTasks) * 100).toFixed(1)
        : 0;
    
    analyticsContainer.innerHTML = `
        <div class="analytics-item">
            <span class="analytics-value">${formatDuration(averageTime)}</span>
            <span class="analytics-label">Среднее время выполнения</span>
        </div>
        <div class="analytics-item">
            <span class="analytics-value">${formatDuration(maxTime)}</span>
            <span class="analytics-label">Максимальное время</span>
        </div>
        <div class="analytics-item">
            <span class="analytics-value">${formatDuration(minTime)}</span>
            <span class="analytics-label">Минимальное время</span>
        </div>
        <div class="analytics-item">
            <span class="analytics-value">${successRate}%</span>
            <span class="analytics-label">Успешность выполнения</span>
        </div>
        <div class="analytics-item">
            <span class="analytics-value">${totalTasks}</span>
            <span class="analytics-label">Всего задач</span>
        </div>
    `;
}

// Worker management functions
async function addWorker() {
    try {
        showLoading('Добавление нового воркера...');
        
        const response = await fetch('/secret_scanner/admin/workers', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            await refreshWorkersData();
        } else {
            alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Error adding worker:', error);
        alert('Ошибка сети при добавлении воркера');
    } finally {
        hideLoading();
    }
}

async function stopWorker(workerId) {
    showConfirmDialog(
        'Остановка воркера',
        `Вы уверены, что хотите остановить воркер ${workerId}? Это выполнит graceful shutdown.`,
        async () => {
            try {
                showLoading('Остановка воркера...');

                const response = await fetch(
                    `/secret_scanner/admin/workers/${workerId}/stop`,
                    { method: 'POST' }
                );

                const data = await response.json();

                if (data.status === 'success') {
                    await refreshWorkersData();
                } else {
                    alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Error stopping worker:', error);
                alert('Ошибка сети при остановке воркера');
            } finally {
                hideLoading();
            }
        },
        'Остановить'
    );
}

async function killWorker(workerId) {
    showConfirmDialog(
        'Принудительная остановка воркера',
        `Вы уверены, что хотите принудительно остановить воркер ${workerId}? Это действие может привести к потере данных текущей задачи.`,
        async () => {
            try {
                showLoading('Принудительная остановка воркера...');
                
                const response = await fetch(`/secret_scanner/admin/workers/${workerId}/kill`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    await refreshWorkersData();
                } else {
                    alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Error killing worker:', error);
                alert('Ошибка сети при принудительной остановке воркера');
            } finally {
                hideLoading();
            }
        },
        'Принудительно остановить'
    );
}

async function pauseWorker(workerId) {
    try {
        showLoading('Приостановка воркера...');
        
        const response = await fetch(`/secret_scanner/admin/workers/${workerId}/pause`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            await refreshWorkersData();
        } else {
            alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Error pausing worker:', error);
        alert('Ошибка сети при приостановке воркера');
    } finally {
        hideLoading();
    }
}

async function resumeWorker(workerId) {
    try {
        showLoading('Возобновление работы воркера...');
        
        const response = await fetch(`/secret_scanner/admin/workers/${workerId}/resume`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            await refreshWorkersData();
        } else {
            alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Error resuming worker:', error);
        alert('Ошибка сети при возобновлении работы воркера');
    } finally {
        hideLoading();
    }
}

async function restartWorker(workerId) {
    showConfirmDialog(
        'Перезапуск воркера',
        `Вы уверены, что хотите перезапустить воркер ${workerId}?`,
        async () => {
            try {
                showLoading('Перезапуск воркера...');
                
                const response = await fetch(`/secret_scanner/admin/workers/${workerId}/restart`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    await refreshWorkersData();
                } else {
                    alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Error restarting worker:', error);
                alert('Ошибка сети при перезапуске воркера');
            } finally {
                hideLoading();
            }
        },
        'Перезапустить'
    );
}

async function retryTask(taskId) {
    showConfirmDialog(
        'Повтор задачи',
        `Вы уверены, что хотите повторить выполнение задачи ${taskId}?`,
        async () => {
            try {
                showLoading('Повтор задачи...');
                
                const response = await fetch(`/secret_scanner/admin/tasks/${taskId}/retry`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    await refreshTasks();
                } else {
                    alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Error retrying task:', error);
                alert('Ошибка сети при повторе задачи');
            } finally {
                hideLoading();
            }
        },
        'Повторить'
    );
}

async function cleanupOldTasks() {
    showConfirmDialog(
        'Очистка старых задач',
        'Вы уверены, что хотите удалить старые завершенные и проваленные задачи? Это действие необратимо.',
        async () => {
            try {
                showLoading('Очистка старых задач...');
                
                const response = await fetch('/secret_scanner/admin/maintenance/cleanup', {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    alert(`Успешно очищено ${data.cleaned_count || 0} старых задач`);
                    await refreshTasks();
                    await refreshWorkersData(); // Update queue stats
                } else {
                    alert('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
                }
            } catch (error) {
                console.error('Error cleaning up tasks:', error);
                alert('Ошибка сети при очистке задач');
            } finally {
                hideLoading();
            }
        },
        'Очистить'
    );
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});