// Global variables
let refreshInterval;
let taskStatusData = null;
let lastUpdateTime = null;

// Получаем данные из data-атрибутов
function getScanData() {
    return {
        status: document.body.dataset.scanStatus,
        id: document.body.dataset.scanId,
        scanType: document.body.dataset.scanType || 'secrets',
        projectName: document.body.dataset.projectName,
        callbackUrl: document.body.dataset.callbackUrl,
        startedAt: document.body.dataset.scanStartedAt,
        startedAtDisplay: document.body.dataset.scanStartedAtDisplay
    };
}

function getResultsUrl(scanId, scanType) {
    if ((scanType || 'secrets') === 'forbidden') {
        return `/secret_scanner/scan/${scanId}/forbidden-results`;
    }
    return `/secret_scanner/scan/${scanId}/results`;
}

// Получить статус задачи через новый эндпоинт
async function fetchTaskStatus() {
    const scanData = getScanData();
    
    // Если callback URL недоступен, пытаемся получить статус через альтернативный эндпоинт
    if (!scanData.callbackUrl) {
        console.warn('Callback URL not available, trying alternative endpoint');
        return await fetchTaskStatusAlternative();
    }

    try {
        const response = await fetch(`/secret_scanner/task-status?callback_url=${encodeURIComponent(scanData.callbackUrl)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            return data;
        } else {
            console.error('Task status error:', data.message);
            return null;
        }
    } catch (error) {
        console.error('Error fetching task status:', error);
        // Fallback к альтернативному методу
        return await fetchTaskStatusAlternative();
    }
}

// Альтернативный метод получения статуса через scan ID
async function fetchTaskStatusAlternative() {
    const scanData = getScanData();
    
    if (!scanData.id) {
        console.error('Scan ID not available');
        return null;
    }

    try {
        const response = await fetch(`/secret_scanner/scan/${scanData.id}/task-status`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            return data;
        } else {
            console.error('Alternative task status error:', data.message);
            return null;
        }
    } catch (error) {
        console.error('Error fetching alternative task status:', error);
        return null;
    }
}

// Обновить отображение статуса
function updateStatusDisplay(statusData) {
    if (!statusData) {
        displayError('Не удалось получить статус задачи');
        return;
    }

    taskStatusData = statusData;
    lastUpdateTime = new Date();

    const currentStatus = statusData.current_status;
    const progress = statusData.progress || 0;
    const progressDetail = statusData.progress_detail || '';
    const statusDescription = statusData.status_description || currentStatus;
    const progressFormatted = statusData.progress_formatted || statusDescription;

    // Обновляем основное содержимое статуса
    updateMainStatus(currentStatus, statusDescription, progressFormatted);
    
    // Обновляем прогресс (если есть)
    updateProgressSection(currentStatus, progress, progressDetail, progressFormatted);
    
    // Обновляем временные метки
    updateTimestamps(statusData);
    
    // Обновляем кнопки действий
    updateActionButtons(currentStatus, statusData);
    
    // Показываем дополнительную информацию для завершенных/провалившихся задач
    updateAdditionalInfo(currentStatus, statusData);

    console.log('Status updated:', currentStatus, progress);
}

// Обновить основной статус
function updateMainStatus(status, description, progressFormatted) {
    const statusContent = document.getElementById('status-content');
    
    const statusConfig = {
        'pending': {
            icon: '⌛',
            title: 'Задача в очереди',
            desc: 'Ожидает освобождения воркера для обработки...',
            showSpinner: false
        },
        'downloading': {
            icon: '⬇️',
            title: 'Загрузка репозитория',
            desc: 'Скачивание исходного кода из репозитория...',
            showSpinner: true
        },
        'unpacking': {
            icon: '📦',
            title: 'Распаковка архива',
            desc: progressFormatted,
            showSpinner: true
        },
        'scanning': {
            icon: '🔍',
            title: 'Сканирование файлов',
            desc: progressFormatted,
            showSpinner: true
        },
        'ml_validation': {
            icon: '🤖',
            title: 'ML валидация результатов',
            desc: progressFormatted,
            showSpinner: true
        },
        'analyzing': {
            icon: '🔎',
            title: 'Анализ языков и расширений',
            desc: progressFormatted || 'Анализ языков и расширений',
            showSpinner: true
        },
        'completed': {
            icon: '✅',
            title: 'Сканирование завершено',
            desc: 'Сканирование репозитория успешно завершено.',
            showSpinner: false
        },
        'failed': {
            icon: '❌',
            title: 'Сканирование провалено',
            desc: 'Произошла ошибка во время сканирования.',
            showSpinner: false
        }
    };

    const config = statusConfig[status] || {
        icon: '❓',
        title: 'Неизвестный статус',
        desc: description,
        showSpinner: false
    };

    statusContent.innerHTML = `
        ${config.showSpinner ? '<div class="loading-spinner"></div>' : ''}
        <div class="status-icon">${config.icon}</div>
        <h1 class="status-title">${config.title}</h1>
        <p class="status-description">${config.desc}</p>
    `;
}

// Обновить секцию прогресса
function updateProgressSection(status, progress, progressDetail, progressFormatted) {
    const progressSection = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressPercentage = document.getElementById('progress-percentage');
    const progressDetailElement = document.getElementById('progress-detail');
    const progressStatusText = document.getElementById('progress-status-text');

    // Показываем прогресс только для активных статусов с числовым прогрессом
    if (['unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status) && progress > 0) {
        progressSection.style.display = 'block';
        
        const progressPercent = Math.max(0, Math.min(100, progress));
        progressFill.style.width = `${progressPercent}%`;
        progressPercentage.textContent = `${Math.round(progressPercent)}%`;
        progressStatusText.textContent = progressFormatted;
        
        if (progressDetail) {
            progressDetailElement.textContent = progressDetail;
            progressDetailElement.style.display = 'block';
        } else {
            progressDetailElement.style.display = 'none';
        }
    } else {
        progressSection.style.display = 'none';
    }
}

// Обновить временные метки
function updateTimestamps(statusData) {
    const startedAtDetail = document.getElementById('started-at-detail');
    const completedAtDetail = document.getElementById('completed-at-detail');
    const completedAtValue = document.getElementById('completed-at-value');
    const executionTimeDetail = document.getElementById('execution-time-detail');
    const executionTimeValue = document.getElementById('execution-time-value');

    // Обновляем время запуска
    if (statusData.started_at) {
        const startedDate = new Date(statusData.started_at * 1000);
        startedAtDetail.querySelector('.scan-detail-value').textContent = 
            startedDate.toLocaleString('ru-RU');
    }

    // Показываем время завершения для завершенных задач
    if (statusData.completed_at) {
        const completedDate = new Date(statusData.completed_at * 1000);
        completedAtValue.textContent = completedDate.toLocaleString('ru-RU');
        completedAtDetail.style.display = 'flex';

        // Показываем время выполнения
        if (statusData.execution_time_seconds) {
            executionTimeValue.textContent = formatDuration(statusData.execution_time_seconds);
            executionTimeDetail.style.display = 'flex';
        }
    } else {
        completedAtDetail.style.display = 'none';
        executionTimeDetail.style.display = 'none';
    }
}

// Обновить кнопки действий
function updateActionButtons(status, statusData) {
    const dynamicButtons = document.getElementById('dynamic-buttons');
    const refreshBtn = document.getElementById('refresh-btn');
    
    dynamicButtons.innerHTML = '';

    if (status === 'completed') {
        // Кнопка просмотра результатов
        const scanData = getScanData();
        const resultsBtn = document.createElement('a');
        resultsBtn.href = getResultsUrl(scanData.id, scanData.scanType);
        resultsBtn.className = 'btn btn-primary';
        resultsBtn.innerHTML = '📊 Посмотреть результаты';
        dynamicButtons.appendChild(resultsBtn);

        // Скрываем кнопку обновления для завершенных задач
        refreshBtn.style.display = 'none';

    } else if (status === 'failed') {
        // Кнопка удаления для провалившихся задач
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-danger';
        deleteBtn.innerHTML = '🗑️ Удалить скан';
        deleteBtn.onclick = () => deleteScan();
        dynamicButtons.appendChild(deleteBtn);

    } else if (['pending', 'downloading', 'unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status)) {
        // Кнопка отмены для активных задач
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-danger';
        cancelBtn.innerHTML = '⏹️ Отменить скан';
        cancelBtn.onclick = () => deleteScan();
        dynamicButtons.appendChild(cancelBtn);
    }
}

// Обновить дополнительную информацию
function updateAdditionalInfo(status, statusData) {
    const resultsSection = document.getElementById('results-section');
    const errorSection = document.getElementById('error-section');
    const elapsedTime = document.getElementById('elapsedTime');
    const logsInfo = document.getElementById('logs-info');
    const logsInfoText = document.getElementById('logs-info-text');

    // Скрываем все секции по умолчанию
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
    elapsedTime.style.display = 'none';
    logsInfo.style.display = 'none';

    if (status === 'completed') {
        // Показываем информацию о результатах
        const resultsInfo = document.getElementById('results-info');
        let resultsText = '📊 Сканирование завершено успешно';
        
        if (statusData.results_count !== undefined) {
            resultsText = `📊 Найдено результатов: ${statusData.results_count}`;
        }
        
        resultsInfo.textContent = resultsText;
        resultsSection.style.display = 'block';

    } else if (status === 'failed') {
        // Показываем информацию об ошибке
        const errorMessage = document.getElementById('error-message');
        errorMessage.textContent = statusData.error || 'Неизвестная ошибка';
        errorSection.style.display = 'block';
        
        // Показываем логи для диагностики
        logsInfoText.innerHTML = `
            Произошла ошибка во время сканирования. Детальную информацию об ошибке можно найти в логах сервиса.<br><br>
            <strong>ID сканирования для поиска в логах сервиса:</strong> 
            <br><strong><code style="background: #f8f9fa; padding: 2px 6px; border-radius: 4px; color: #dc3545;">${statusData.task_id}</code></strong><br><br>
            <strong>Имя проекта для поиска в логах микросервиса:</strong> 
            <br><strong><code style="background: #f8f9fa; padding: 2px 6px; border-radius: 4px; color: #dc3545;">${statusData.project_name}</code></strong>
        `;
        logsInfo.style.display = 'block';

    } else if (['pending', 'downloading', 'unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status)) {
        // Показываем время выполнения для активных задач
        if (statusData.started_at) {
            elapsedTime.style.display = 'block';
            updateElapsedTime(statusData.started_at);
        }
        
        // Показываем логи для долго выполняющихся задач
        if (['downloading', 'unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status)) {
            logsInfoText.textContent = 'Если скан завис или работает слишком долго, вы можете посмотреть логи сервиса для диагностики проблемы.';
            logsInfo.style.display = 'block';
        }
    }
}

// Обновить время выполнения
function updateElapsedTime(startedAtTimestamp) {
    const elapsedTimeElement = document.getElementById('elapsedTime');
    const scanData = getScanData();
    
    function updateTime() {
        const startTime = new Date(startedAtTimestamp * 1000);
        const now = new Date();
        const elapsed = Math.floor((now - startTime) / 1000);
        
        const hours = Math.floor(elapsed / 3600);
        const minutes = Math.floor((elapsed % 3600) / 60);
        const seconds = elapsed % 60;
        
        let timeStr = '';
        if (hours > 0) {
            timeStr = `${hours}ч ${minutes}м ${seconds}с`;
        } else if (minutes > 0) {
            timeStr = `${minutes}м ${seconds}с`;
        } else {
            timeStr = `${seconds}с`;
        }
        
        elapsedTimeElement.innerHTML = `
            Запущен: ${scanData.startedAtDisplay}<br>
            Прошло времени: ${timeStr}
        `;
    }

    updateTime();
    return setInterval(updateTime, 1000);
}

// Отобразить ошибку
function displayError(message) {
    const statusContent = document.getElementById('status-content');
    statusContent.innerHTML = `
        <div class="status-icon">⚠️</div>
        <h1 class="status-title">Ошибка получения статуса</h1>
        <p class="status-description">${message}</p>
    `;
}

// Обновить статус вручную
async function refreshStatus() {
    const refreshBtn = document.getElementById('refresh-btn');
    const originalText = refreshBtn.innerHTML;
    
    refreshBtn.innerHTML = '🔄 Обновление...';
    refreshBtn.disabled = true;
    
    const statusData = await fetchTaskStatus();
    updateStatusDisplay(statusData);
    
    refreshBtn.innerHTML = originalText;
    refreshBtn.disabled = false;
}

// Удалить скан
function deleteScan() {
    const scanData = getScanData();
    
    if (confirm('Вы уверены, что хотите удалить это сканирование?')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/secret_scanner/scan/${scanData.id}/delete`;
        
        document.body.appendChild(form);
        form.submit();
    }
}

// Запустить автообновление
function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    
    // Обновляем каждые 3 секунды для активных задач
    refreshInterval = setInterval(async () => {
        if (!taskStatusData) return;
        
        const currentStatus = taskStatusData.current_status;
        
        // Прекращаем автообновление для финальных статусов
        if (['completed', 'failed'].includes(currentStatus)) {
            stopAutoRefresh();
            
            // Автоперенаправление на результаты через 2 секунды для завершенных задач
            if (currentStatus === 'completed') {
                const scanData = getScanData();
                setTimeout(() => {
                    window.location.href = getResultsUrl(scanData.id, scanData.scanType);
                }, 2000);
            }
            return;
        }
        
        // Обновляем статус для активных задач
        const statusData = await fetchTaskStatus();
        if (statusData) {
            updateStatusDisplay(statusData);
        }
    }, 3000);
}

// Остановить автообновление
function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Форматирование длительности
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

// Обновить страницу (fallback)
function refreshPage() {
    window.location.reload();
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Initializing scan status page...');
    
    // Получаем первоначальный статус
    const statusData = await fetchTaskStatus();
    updateStatusDisplay(statusData);
    
    // Запускаем автообновление только для активных задач
    if (statusData && !['completed', 'failed'].includes(statusData.current_status)) {
        startAutoRefresh();
    }
});

// Очистка при закрытии страницы
window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});