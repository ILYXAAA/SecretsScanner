// Global variables
let refreshInterval;
let taskStatusData = null;
let elapsedInterval = null;

function getScanData() {
    return {
        status: document.body.dataset.scanStatus,
        id: document.body.dataset.scanId,
        scanType: document.body.dataset.scanType || 'secrets',
        projectName: document.body.dataset.projectName,
        callbackUrl: document.body.dataset.callbackUrl,
        startedAt: document.body.dataset.scanStartedAt,
        startedAtDisplay: document.body.dataset.scanStartedAtDisplay,
    };
}

function getResultsUrl(scanId, scanType) {
    if ((scanType || 'secrets') === 'forbidden') {
        return `/secret_scanner/scan/${scanId}/forbidden-results`;
    }
    return `/secret_scanner/scan/${scanId}/results`;
}

function setVisible(element, visible) {
    if (!element) return;
    if (visible) {
        element.removeAttribute('hidden');
    } else {
        element.setAttribute('hidden', '');
    }
}

function buildStatusHero(icon, tint, badgeClass, title, desc, showSpinner) {
    return `
        ${showSpinner ? '<div class="loading-spinner"></div>' : ''}
        <div class="status-hero">
            <span class="status-hero-badge ${badgeClass}">
                ${uiIcon(icon, `status-hero-icon ${tint}`, 32)}
            </span>
            <h1 class="status-title">${title}</h1>
            <p class="status-description">${desc}</p>
        </div>
    `;
}

function buildButtonLabel(icon, tint, text) {
    return `${uiIcon(icon, `btn-icon ${tint}`, 14)}<span>${text}</span>`;
}

async function fetchTaskStatus() {
    const scanData = getScanData();

    if (!scanData.callbackUrl) {
        return fetchTaskStatusAlternative();
    }

    try {
        const response = await fetch(`/secret_scanner/task-status?callback_url=${encodeURIComponent(scanData.callbackUrl)}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.status === 'success') {
            return data;
        }

        console.error('Task status error:', data.message);
        return null;
    } catch (error) {
        console.error('Error fetching task status:', error);
        return fetchTaskStatusAlternative();
    }
}

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
        }

        console.error('Alternative task status error:', data.message);
        return null;
    } catch (error) {
        console.error('Error fetching alternative task status:', error);
        return null;
    }
}

function updateStatusDisplay(statusData) {
    if (!statusData) {
        displayError('Не удалось получить статус задачи');
        return;
    }

    taskStatusData = statusData;

    const currentStatus = statusData.current_status;
    const progress = statusData.progress || 0;
    const progressDetail = statusData.progress_detail || '';
    const statusDescription = statusData.status_description || currentStatus;
    const progressFormatted = statusData.progress_formatted || statusDescription;

    const statusCard = document.getElementById('scanStatusCard');
    if (statusCard) {
        statusCard.dataset.status = currentStatus;
    }

    updateMainStatus(currentStatus, statusDescription, progressFormatted);
    updateProgressSection(currentStatus, progress, progressDetail, progressFormatted);
    updateTimestamps(statusData);
    updateActionButtons(currentStatus, statusData);
    updateAdditionalInfo(currentStatus, statusData);
}

function updateMainStatus(status, description, progressFormatted) {
    const statusContent = document.getElementById('status-content');

    const statusConfig = {
        pending: {
            icon: 'QueryQueue.svg',
            tint: 'icon-tint-warn',
            badge: 'badge-amber',
            title: 'Задача в очереди',
            desc: 'Ожидает освобождения воркера для обработки...',
            showSpinner: false,
        },
        downloading: {
            icon: 'ArrowDownload.svg',
            tint: 'icon-tint-info',
            badge: 'badge-blue',
            title: 'Загрузка репозитория',
            desc: 'Скачивание исходного кода из репозитория...',
            showSpinner: true,
        },
        unpacking: {
            icon: 'Files.svg',
            tint: 'icon-tint-warn',
            badge: 'badge-amber',
            title: 'Распаковка архива',
            desc: progressFormatted,
            showSpinner: true,
        },
        scanning: {
            icon: 'BarcodeScanDuotone.svg',
            tint: 'icon-tint-info',
            badge: 'badge-blue',
            title: 'Сканирование файлов',
            desc: progressFormatted,
            showSpinner: true,
        },
        ml_validation: {
            icon: 'Robot.svg',
            tint: 'icon-tint-purple',
            badge: 'badge-purple',
            title: 'ML валидация результатов',
            desc: progressFormatted,
            showSpinner: true,
        },
        analyzing: {
            icon: 'Extensions.svg',
            tint: 'icon-tint-purple',
            badge: 'badge-purple',
            title: 'Анализ языков и расширений',
            desc: progressFormatted || 'Анализ языков и расширений',
            showSpinner: true,
        },
        completed: {
            icon: 'CheckboxCheckedFilled.svg',
            tint: 'icon-tint-success',
            badge: 'badge-green',
            title: 'Сканирование завершено',
            desc: 'Сканирование репозитория успешно завершено.',
            showSpinner: false,
        },
        failed: {
            icon: 'Error.svg',
            tint: 'icon-tint-error',
            badge: 'badge-red',
            title: 'Сканирование провалено',
            desc: 'Произошла ошибка во время сканирования.',
            showSpinner: false,
        },
    };

    const config = statusConfig[status] || {
        icon: 'AlertErrorStroke16.svg',
        tint: 'icon-tint-muted',
        badge: 'badge-blue',
        title: 'Неизвестный статус',
        desc: description,
        showSpinner: false,
    };

    statusContent.innerHTML = buildStatusHero(
        config.icon,
        config.tint,
        config.badge,
        config.title,
        config.desc,
        config.showSpinner
    );
}

function updateProgressSection(status, progress, progressDetail, progressFormatted) {
    const progressSection = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressPercentage = document.getElementById('progress-percentage');
    const progressDetailElement = document.getElementById('progress-detail');
    const progressStatusText = document.getElementById('progress-status-text');

    if (['unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status) && progress > 0) {
        setVisible(progressSection, true);

        const progressPercent = Math.max(0, Math.min(100, progress));
        progressFill.style.width = `${progressPercent}%`;
        progressPercentage.textContent = `${Math.round(progressPercent)}%`;
        progressStatusText.textContent = progressFormatted;

        if (progressDetail) {
            progressDetailElement.textContent = progressDetail;
            setVisible(progressDetailElement, true);
        } else {
            setVisible(progressDetailElement, false);
        }
    } else {
        setVisible(progressSection, false);
    }
}

function updateTimestamps(statusData) {
    const startedAtDetail = document.getElementById('started-at-detail');
    const completedAtDetail = document.getElementById('completed-at-detail');
    const completedAtValue = document.getElementById('completed-at-value');
    const executionTimeDetail = document.getElementById('execution-time-detail');
    const executionTimeValue = document.getElementById('execution-time-value');

    if (statusData.started_at && startedAtDetail) {
        const startedDate = new Date(statusData.started_at * 1000);
        startedAtDetail.querySelector('.scan-detail-value').textContent =
            startedDate.toLocaleString('ru-RU');
    }

    if (statusData.completed_at) {
        const completedDate = new Date(statusData.completed_at * 1000);
        completedAtValue.textContent = completedDate.toLocaleString('ru-RU');
        setVisible(completedAtDetail, true);

        if (statusData.execution_time_seconds) {
            executionTimeValue.textContent = formatDuration(statusData.execution_time_seconds);
            setVisible(executionTimeDetail, true);
        } else {
            setVisible(executionTimeDetail, false);
        }
    } else {
        setVisible(completedAtDetail, false);
        setVisible(executionTimeDetail, false);
    }
}

function updateActionButtons(status, statusData) {
    const dynamicButtons = document.getElementById('dynamic-buttons');
    const refreshBtn = document.getElementById('refresh-btn');

    dynamicButtons.innerHTML = '';

    if (status === 'completed') {
        const scanData = getScanData();
        const resultsBtn = document.createElement('a');
        resultsBtn.href = getResultsUrl(scanData.id, scanData.scanType);
        resultsBtn.className = 'btn btn-success';
        resultsBtn.innerHTML = buildButtonLabel('BarcodeScanDuotone.svg', 'btn-icon-light', 'Посмотреть результаты');
        dynamicButtons.appendChild(resultsBtn);
        setVisible(refreshBtn, false);
    } else if (status === 'failed') {
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'btn btn-danger';
        deleteBtn.innerHTML = buildButtonLabel('FolderTrash.svg', 'btn-icon-light', 'Удалить скан');
        deleteBtn.onclick = () => deleteScan();
        dynamicButtons.appendChild(deleteBtn);
        setVisible(refreshBtn, true);
    } else if (['pending', 'downloading', 'unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status)) {
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'btn btn-danger';
        cancelBtn.innerHTML = buildButtonLabel('Error.svg', 'btn-icon-light', 'Отменить скан');
        cancelBtn.onclick = () => deleteScan();
        dynamicButtons.appendChild(cancelBtn);
        setVisible(refreshBtn, true);
    } else {
        setVisible(refreshBtn, true);
    }
}

function updateAdditionalInfo(status, statusData) {
    const resultsSection = document.getElementById('results-section');
    const errorSection = document.getElementById('error-section');
    const elapsedTime = document.getElementById('elapsedTime');
    const logsInfo = document.getElementById('logs-info');
    const logsInfoText = document.getElementById('logs-info-text');

    setVisible(resultsSection, false);
    setVisible(errorSection, false);
    setVisible(elapsedTime, false);
    setVisible(logsInfo, false);

    if (elapsedInterval) {
        clearInterval(elapsedInterval);
        elapsedInterval = null;
    }

    if (status === 'completed') {
        const resultsInfo = document.getElementById('results-info');
        let resultsText = 'Сканирование завершено успешно';

        if (statusData.results_count !== undefined) {
            resultsText = `Найдено результатов: ${statusData.results_count}`;
        }

        resultsInfo.innerHTML = `${uiIcon('CheckboxCheckedFilled.svg', 'banner-icon icon-tint-success', 18)}<span>${resultsText}</span>`;
        setVisible(resultsSection, true);
    } else if (status === 'failed') {
        const errorMessage = document.getElementById('error-message');
        errorMessage.textContent = statusData.error || 'Неизвестная ошибка';
        setVisible(errorSection, true);

        logsInfoText.innerHTML = `
            Произошла ошибка во время сканирования. Детальную информацию об ошибке можно найти в логах сервиса.<br><br>
            <strong>ID сканирования для поиска в логах сервиса:</strong><br>
            <code>${statusData.task_id || getScanData().id}</code><br><br>
            <strong>Имя проекта для поиска в логах микросервиса:</strong><br>
            <code>${statusData.project_name || getScanData().projectName}</code>
        `;
        setVisible(logsInfo, true);
    } else if (['pending', 'downloading', 'unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status)) {
        if (statusData.started_at) {
            setVisible(elapsedTime, true);
            elapsedInterval = updateElapsedTime(statusData.started_at);
        }

        if (['downloading', 'unpacking', 'scanning', 'ml_validation', 'analyzing'].includes(status)) {
            logsInfoText.textContent = 'Если скан завис или работает слишком долго, вы можете посмотреть логи сервиса для диагностики проблемы.';
            setVisible(logsInfo, true);
        }
    }
}

function updateElapsedTime(startedAtTimestamp) {
    const elapsedTimeElement = document.getElementById('elapsedTime');
    const scanData = getScanData();

    function updateTime() {
        const startTime = new Date(startedAtTimestamp * 1000);
        const now = new Date();
        const elapsed = Math.max(0, Math.floor((now - startTime) / 1000));

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
            Прошло времени: <strong>${timeStr}</strong>
        `;
    }

    updateTime();
    return setInterval(updateTime, 1000);
}

function displayError(message) {
    const statusContent = document.getElementById('status-content');
    statusContent.innerHTML = buildStatusHero(
        'AlertErrorStroke16.svg',
        'icon-tint-warn',
        'badge-amber',
        'Ошибка получения статуса',
        message,
        false
    );
}

async function refreshStatus() {
    const refreshBtn = document.getElementById('refresh-btn');
    const originalHtml = refreshBtn.innerHTML;

    refreshBtn.innerHTML = buildButtonLabel('ArrowSync.svg', 'icon-tint-info', 'Обновление...');
    refreshBtn.disabled = true;

    const statusData = await fetchTaskStatus();
    updateStatusDisplay(statusData);

    refreshBtn.innerHTML = originalHtml;
    refreshBtn.disabled = false;
}

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

function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }

    refreshInterval = setInterval(async () => {
        if (!taskStatusData) return;

        const currentStatus = taskStatusData.current_status;

        if (['completed', 'failed'].includes(currentStatus)) {
            stopAutoRefresh();

            if (currentStatus === 'completed') {
                const scanData = getScanData();
                setTimeout(() => {
                    window.location.href = getResultsUrl(scanData.id, scanData.scanType);
                }, 2000);
            }
            return;
        }

        const statusData = await fetchTaskStatus();
        if (statusData) {
            updateStatusDisplay(statusData);
        }
    }, 3000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '—';

    if (seconds < 60) {
        return `${seconds.toFixed(1)}с`;
    }
    if (seconds < 3600) {
        return `${Math.floor(seconds / 60)}м ${(seconds % 60).toFixed(0)}с`;
    }
    return `${Math.floor(seconds / 3600)}ч ${Math.floor((seconds % 3600) / 60)}м`;
}

document.addEventListener('DOMContentLoaded', async () => {
    const statusData = await fetchTaskStatus();
    updateStatusDisplay(statusData);

    if (statusData && !['completed', 'failed'].includes(statusData.current_status)) {
        startAutoRefresh();
    }
});

window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
    if (elapsedInterval) {
        clearInterval(elapsedInterval);
    }
});
