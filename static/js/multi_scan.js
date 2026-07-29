function deriveProjectNameFromRepoUrl(baseRepoUrl) {
    let url = (baseRepoUrl || '').trim().replace(/\/$/, '');
    if (!url) {
        throw new Error('Пустой URL репозитория');
    }

    let segment = url.split('/').pop() || '';
    if (segment.toLowerCase().endsWith('.git')) {
        segment = segment.slice(0, -4);
    }
    if (!segment) {
        throw new Error('Не удалось извлечь имя репозитория из URL');
    }

    return segment.replace(/-/g, '_').replace(/\./g, '_');
}

function parseAzureDevOpsUrl(repoUrl) {
    const urlObj = new URL(repoUrl);
    
    // Check if it's a GitHub URL
    if (urlObj.hostname === 'github.com') {
        const pathParts = urlObj.pathname.split('/').filter(part => part !== '');
        
        if (pathParts.length < 2) {
            throw new Error('GitHub URL должен содержать владельца и имя репозитория');
        }
        
        const owner = pathParts[0];
        const repository = pathParts[1];
        
        let refType = 'branch';
        let ref = 'main';
        
        const commitIndex = pathParts.indexOf('commit');
        if (commitIndex !== -1 && commitIndex === 2) {
            refType = 'commit';
            ref = pathParts[3];
            if (!ref) {
                throw new Error('URL некорректен: отсутствует хеш коммита после "/commit/"');
            }
        } else if (pathParts.length > 3) {
            if (pathParts[2] === 'tree') {
                refType = 'branch';
                ref = pathParts.slice(3).join('/');
            } else if (pathParts[2] === 'releases' && pathParts[3] === 'tag') {
                refType = 'tag';
                ref = pathParts[4];
            }
        }
        
        const baseRepoUrl = `${urlObj.protocol}//${urlObj.host}/${owner}/${repository}`;
        
        return {
            server: urlObj.hostname,
            collection: owner,
            project: owner,
            repository: repository,
            refType: refType,
            ref: ref,
            baseRepoUrl: baseRepoUrl
        };
    }
    
    // Azure DevOps parsing logic
    const server = urlObj.hostname;
    const pathParts = urlObj.pathname.split('/').filter(part => part !== '');
    
    if (!pathParts.includes('_git')) {
        throw new Error('URL не содержит "_git"');
    }
    
    const gitIndex = pathParts.indexOf('_git');
    if (gitIndex + 1 >= pathParts.length) {
        throw new Error('URL некорректен: отсутствует имя репозитория после "_git"');
    }
    
    const repository = pathParts[gitIndex + 1];
    
    if (gitIndex < 1) {
        throw new Error('Недостаточно информации до "_git"');
    }
    
    const project = pathParts[gitIndex - 1];
    const collectionParts = pathParts.slice(0, gitIndex - 1);
    const collection = collectionParts.join('/');
    
    // Проверяем, что проект не является UUID
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (uuidPattern.test(project)) {
        throw new Error('URL содержит UUID в качестве имени проекта. Используйте URL с читаемым именем проекта вместо UUID.');
    }
    
    // Parse ref information
    let refType = 'branch';
    let ref = 'main';
    
    // Check for commit in path (format: /commit/hash)
    const commitIndex = pathParts.indexOf('commit');
    if (commitIndex !== -1 && commitIndex === gitIndex + 2) {
        // Проверяем, что нет других параметров
        if (urlObj.searchParams.has('version')) {
            throw new Error('URL содержит одновременно commit в пути и параметр version');
        }
        refType = 'commit';
        ref = pathParts[gitIndex + 3];
        if (!ref) {
            throw new Error('URL некорректен: отсутствует хеш коммита после "/commit/"');
        }
    }
    // Check for version parameter
    else if (urlObj.searchParams.has('version')) {
        const version = urlObj.searchParams.get('version');
        if (version.startsWith('GB')) {
            refType = 'branch';
            ref = version.substring(2);
        } else if (version.startsWith('GT')) {
            refType = 'tag';
            ref = version.substring(2);
        } else if (version.startsWith('GC')) {
            refType = 'commit';
            ref = version.substring(2);
            // Проверяем, что в пути нет /commit/
            if (pathParts.includes('commit')) {
                throw new Error('URL содержит одновременно параметр version=GC и commit в пути');
            }
        } else {
            throw new Error('Неподдерживаемый формат параметра version: ' + version);
        }
        
        if (!ref) {
            throw new Error('Пустое значение после префикса в параметре version');
        }
    }
    
    // Clean base repo URL - remove commit path and all query parameters
    let cleanPath = urlObj.pathname;
    if (cleanPath.includes('/commit/')) {
        cleanPath = cleanPath.split('/commit/')[0];
    }
    const baseRepoUrl = `${urlObj.protocol}//${urlObj.host}${cleanPath}`;
    
    return {
        server,
        collection,
        project,
        repository,
        refType,
        ref,
        baseRepoUrl
    };
}

function validateUrls(urls) {
    const results = [];
    const errors = [];
    
    for (let i = 0; i < urls.length; i++) {
        const url = urls[i].trim();
        if (!url) continue;
        
        try {
            const parsed = parseAzureDevOpsUrl(url);
            results.push({
                originalUrl: url,
                parsed: parsed,
                projectName: deriveProjectNameFromRepoUrl(parsed.baseRepoUrl)
            });
        } catch (error) {
            errors.push({
                url: url,
                error: error.message,
                line: i + 1
            });
        }
    }
    
    return { results, errors };
}

function showAlert(type, message) {
    const alertContainer = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = message;
    alertContainer.innerHTML = '';
    alertContainer.appendChild(alert);
    
    // Auto-hide success alerts after 5 seconds
    if (type === 'success') {
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }
}

function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

function showConfirmationDialog(missingProjects) {
    const dialog = document.getElementById('confirmationDialog');
    const messageEl = document.getElementById('dialogMessage');
    const listEl = document.getElementById('missingProjectsList');
    
    messageEl.textContent = `Для ${missingProjects.length} ссылок не найдено соответствующих проектов. Хотите автоматически создать для них проекты?`;
    
    listEl.innerHTML = missingProjects.map(item => 
        `<div>${item.parsed.baseRepoUrl} → ${item.projectName}</div>`
    ).join('');
    
    dialog.style.display = 'flex';
    
    return new Promise((resolve) => {
        document.getElementById('confirmBtn').onclick = () => {
            dialog.style.display = 'none';
            resolve(true);
        };
        
        document.getElementById('cancelBtn').onclick = () => {
            dialog.style.display = 'none';
            resolve(false);
        };
    });
}

async function createProjects(missingProjects) {
    for (const item of missingProjects) {
        try {
            const response = await fetch('/secret_scanner/projects/add-from-url', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    repo_url: item.parsed.baseRepoUrl
                })
            });

            const data = await response.json();
            if (!response.ok || data.status !== 'success') {
                throw new Error(data.message || `Не удалось создать проект для ${item.parsed.baseRepoUrl}`);
            }

            item.projectName = data.project_name;
        } catch (error) {
            console.error('Error creating project:', error);
            throw error;
        }
    }
}

async function checkProjectsExist(validatedUrls) {
    const existing = [];
    const missing = [];
    
    for (const item of validatedUrls) {
        try {
            const response = await fetch(`/secret_scanner/api/project/check?repo_url=${encodeURIComponent(item.parsed.baseRepoUrl)}`);
            if (response.ok) {
                const data = await response.json();
                if (data.exists) {
                    existing.push({ ...item, projectName: data.project_name });
                } else {
                    missing.push(item);
                }
            } else {
                missing.push(item);
            }
        } catch (error) {
            missing.push(item);
        }
    }
    
    return { existing, missing };
}

function displayScanResults(scans, multiScanId = null, baseRepoUrls = null) {
    const scanResultsDiv = document.getElementById('scanResults');
    const scanListDiv = document.getElementById('scanList');
    
    scanListDiv.innerHTML = '';
    
    // Store multi-scan ID if provided
    if (multiScanId) {
        sessionStorage.setItem('currentMultiScanId', multiScanId);
    }
    
    // Store base repo URLs for later use
    if (baseRepoUrls) {
        sessionStorage.setItem('baseRepoUrls', JSON.stringify(baseRepoUrls));
    }
    
    // Determine current scan position for sequential animation
    let currentScanIndex = -1;
    const completedScans = scans.filter(scan => scan.status === 'completed' || scan.status === 'failed' || scan.status === 'timeout').length;
    const runningScans = scans.filter(scan => scan.status === 'running').length;
    
    if (runningScans > 0 && completedScans < scans.length) {
        currentScanIndex = completedScans;
    }
    
    scans.forEach((scan, index) => {
        const scanItem = document.createElement('a');
        scanItem.className = 'scan-item';
        scanItem.href = scan.status === 'completed' ? `/secret_scanner/scan/${scan.scan_id}/results` : `/secret_scanner/scan/${scan.scan_id}`;
        scanItem.dataset.scanId = scan.scan_id;
        
        let statusHtml = '';
        let statsHtml = '';
        
        if (scan.status === 'completed') {
            statusHtml = '<span class="scan-status completed">✅ Завершено</span>';
            statsHtml = `
                <div class="secrets-summary">
                    <div class="secret-count high">
                        <div class="number">${scan.high_count || 0}</div>
                        <div class="label">High</div>
                    </div>
                    <div class="secret-count potential">
                        <div class="number">${scan.potential_count || 0}</div>
                        <div class="label">Potential</div>
                    </div>
                </div>
            `;
        } else if (scan.status === 'failed') {
            statusHtml = '<span class="scan-status failed">❌ Ошибка</span>';
        } else if (scan.status === 'timeout') {
            statusHtml = '<span class="scan-status timeout">⏸️ Таймаут</span>';
        } else if (scan.status === 'running') {
            if (index === currentScanIndex) {
                statusHtml = `
                    <span class="scan-progress">
                        <div class="scan-loading">
                            <div class="scan-spinner"></div>
                            Выполняется
                        </div>
                    </span>
                `;
            } else {
                statusHtml = '<span class="scan-status running">⏳ Выполняется</span>';
            }
        } else {
            // pending or other status
            if (index === currentScanIndex) {
                statusHtml = `
                    <span class="scan-progress">
                        <div class="scan-loading">
                            <div class="scan-spinner"></div>
                            Запускается
                        </div>
                    </span>
                `;
            } else if (index > currentScanIndex) {
                statusHtml = '<span class="scan-queue">📋 В очереди</span>';
            } else {
                statusHtml = '<span class="scan-status running">⏳ Выполняется</span>';
            }
        }
        
        scanItem.innerHTML = `
            <div class="scan-main">
                <div class="scan-project">${scan.project_name}</div>
                <div class="scan-meta">
                    ${statusHtml}
                </div>
                <div class="scan-meta">
                    🕒 ${scan.started_at || new Date().toLocaleString('ru-RU')}
                    • ⚙️ ${scan.commit ? scan.commit.substring(0, 7) : 'Ожидание...'}
                    • 📂 ${scan.ref_type}: ${scan.ref}
                </div>
            </div>
            ${statsHtml ? `<div class="scan-stats">${statsHtml}</div>` : ''}
        `;
        
        scanListDiv.appendChild(scanItem);
    });
    
    scanResultsDiv.style.display = 'block';
    document.getElementById('scanForm').style.display = 'none';
    
    // Always show repo list if there are scans with commits
    displayCompletedRepos(scans);
    
    // Автоматически запускаем автообновление если есть запущенные сканы
    const hasRunning = scans.some(scan => scan.status === 'running' || scan.status === 'pending');
    if (hasRunning) {
        startAutoRefresh();
    } else {
        updateRefreshStatus('Все сканирования завершены');
    }
}

function displayCompletedRepos(scans) {
    const completedReposDiv = document.getElementById('completedRepos');
    const repoListDiv = document.getElementById('repoList');
    
    // Build repo URLs with commits for all scans that have commits (regardless of status)
    const scansWithCommits = scans.filter(scan => scan.commit && scan.commit !== 'not_found' && scan.commit !== 'Ожидание...');
    
    if (scansWithCommits.length === 0) {
        completedReposDiv.style.display = 'none';
        return;
    }
    
    // Get stored base repo URLs
    let baseRepoUrls = {};
    try {
        const stored = sessionStorage.getItem('baseRepoUrls');
        if (stored) {
            baseRepoUrls = JSON.parse(stored);
        }
    } catch (e) {
        console.warn('Could not parse stored base repo URLs');
    }
    
    // Build repo URLs with commits
    const repoUrls = scansWithCommits.map(scan => {
        // Try to get base repo URL from stored data first
        let baseUrl = baseRepoUrls[scan.project_name] || scan.base_repo_url;
        
        // If still no base URL, try to construct from project name (fallback)
        if (!baseUrl || baseUrl === 'Unknown') {
            baseUrl = `[${scan.project_name}]`;
        }
        
        return `${baseUrl}/commit/${scan.commit}`;
    });
    
    repoListDiv.innerHTML = repoUrls.map(url => 
        `<div class="repo-item">${url}</div>`
    ).join('');
    
    completedReposDiv.style.display = 'block';
}

function copyRepoList() {
    const repoItems = document.querySelectorAll('#repoList .repo-item');
    const repoUrls = Array.from(repoItems).map(item => item.textContent);
    const textToCopy = repoUrls.join('\n');
    
    navigator.clipboard.writeText(textToCopy).then(() => {
        showAlert('success', 'Список репозиториев скопирован в буфер обмена');
    }).catch(err => {
        console.error('Error copying to clipboard:', err);
        showAlert('error', 'Не удалось скопировать в буфер обмена');
    });
}

function displayValidationErrors(errors) {
    const errorHtml = `
        <div class="validation-error-list">
            <h4 style="margin-bottom: 1rem; color: #721c24;">Ошибки валидации:</h4>
            ${errors.map(error => 
                `<div class="validation-error-item">Строка ${error.line}: ${error.url}<br>Ошибка: ${error.error}</div>`
            ).join('')}
        </div>
    `;
    showAlert('error', errorHtml);
}

function displayResolutionErrors(data) {
    const errorItems = data.filter(item => item.commit === 'not_found');
    const errorHtml = `
        <div class="validation-error-list">
            <h4 style="margin-bottom: 1rem; color: #721c24;">Не удалось отрезолвить коммиты для следующих репозиториев:</h4>
            ${errorItems.map(item => 
                `<div class="validation-error-item">Проект: ${item.ProjectName}<br>Тип: ${item.RefType}, Значение: ${item.Ref}</div>`
            ).join('')}
        </div>
    `;
    showAlert('error', errorHtml);
}

document.getElementById('multiScanForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const repoUrlsText = document.getElementById('repoUrls').value;
    const urls = repoUrlsText.split('\n').filter(url => url.trim());
    
    if (urls.length === 0) {
        showAlert('error', 'Введите хотя бы одну ссылку на репозиторий');
        return;
    }
    
    // Validate URLs
    const { results: validatedUrls, errors } = validateUrls(urls);

    if (errors.length > 0) {
        displayValidationErrors(errors);
        return;
    }
    
    if (validatedUrls.length === 0) {
        showAlert('error', 'Не найдено валидных ссылок на репозитории');
        return;
    }
    
    showLoading();
    
    try {
        // Check which projects exist
        const { existing, missing } = await checkProjectsExist(validatedUrls);
        
        // If some projects are missing, ask user for confirmation
        if (missing.length > 0) {
            hideLoading();
            const confirmed = await showConfirmationDialog(missing);
            
            if (!confirmed) {
                return;
            }
            
            showLoading();
            await createProjects(missing);
        }
        
        // Prepare scan requests
        const allProjects = [...existing, ...missing];
        const scanRequests = allProjects.map(item => ({
            ProjectName: item.projectName,
            RepoUrl: item.parsed.baseRepoUrl,
            RefType: item.parsed.refType,
            Ref: item.parsed.ref,
            CallbackUrl: `${window.location.origin}/secret_scanner/get_results/${item.projectName}/${generateUUID()}`
        }));
        
        // Send multi-scan request
        const response = await fetch('/secret_scanner/multi_scan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(scanRequests),
            signal: AbortSignal.timeout(300000) // 5 minutes timeout
        });
        
        const result = await response.json();
        
        if (result.status === 'accepted') {
            hideLoading();
            showAlert('success', 'Сканирования успешно запущены!');
            
            // Create base repo URLs mapping
            const baseRepoUrls = {};
            allProjects.forEach(item => {
                baseRepoUrls[item.projectName] = item.parsed.baseRepoUrl;
            });
            
            // Display scan results with multi-scan ID and base repo URLs
            const scans = result.data.map((item, index) => ({
                project_name: item.ProjectName,
                ref_type: item.RefType,
                ref: item.Ref,
                commit: item.commit,
                scan_id: scanRequests[index].CallbackUrl.split('/').pop(),
                base_repo_url: scanRequests[index].RepoUrl,
                status: 'running', // Set initial status
                started_at: new Date().toLocaleString('ru-RU')
            }));
            
            displayScanResults(scans, result.multi_scan_id, baseRepoUrls);
            
            // Сразу запускаем автообновление после успешного запуска
            setTimeout(() => {
                startAutoRefresh();
            }, 2000); // Начинаем обновление через 2 секунды
        }
        else if (result.status === 'validation_failed') {
            hideLoading();
            showAlert('error', result.message);
            displayResolutionErrors(result.data);
        } else {
            hideLoading();
            showAlert('error', result.message || 'Произошла ошибка при запуске сканирований');
        }
        
    } catch (error) {
        hideLoading();
        if (error.name === 'AbortError') {
            showAlert('error', 'Таймаут запроса. Попробуйте еще раз.');
        } else {
            console.error('Error:', error);
            showAlert('error', 'Произошла ошибка при отправке запроса');
        }
    }
});

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

let refreshTimer = null;

// Auto-refresh scan statuses if there are running scans
async function refreshScanStatuses() {
    const multiScanId = sessionStorage.getItem('currentMultiScanId');
    if (!multiScanId) return false;
    
    try {
        const response = await fetch('/secret_scanner/api/multi-scans');
        if (!response.ok) return false;
        
        const data = await response.json();
        if (data.status !== 'success') return false;
        
        // Find current multi-scan
        const currentMultiScan = data.multi_scans.find(ms => ms.multi_scan_id === multiScanId);
        if (!currentMultiScan) return false;
        
        // Update display
        displayScanResults(currentMultiScan.scans);
        
        // Check if there are still running scans
        return currentMultiScan.scans.some(scan => scan.status === 'running' || scan.status === 'pending');
        
    } catch (error) {
        console.error('Error refreshing scan statuses:', error);
        return false;
    }
}

function startAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }
    
    updateRefreshStatus('Автообновление активно');
    
    refreshTimer = setInterval(async () => {
        const hasRunningScans = await refreshScanStatuses();
        if (!hasRunningScans) {
            clearInterval(refreshTimer);
            refreshTimer = null;
            updateRefreshStatus('Все сканирования завершены');
        } else {
            updateRefreshStatus('Автообновление активно (обновлено ' + new Date().toLocaleTimeString() + ')');
        }
    }, 5000); // Check every 5 seconds
}

// Restore scan results on page load
window.addEventListener('DOMContentLoaded', async function() {
    // Проверяем есть ли сохраненный multi-scan ID
    const savedMultiScanId = sessionStorage.getItem('currentMultiScanId');
    
    if (!savedMultiScanId) {
        // Если нет сохраненного ID, не загружаем предыдущие результаты
        return;
    }
    
    try {
        const response = await fetch('/secret_scanner/api/multi-scans');
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'success' && data.multi_scans.length > 0) {
                // Ищем сохраненный multi-scan
                const savedMultiScan = data.multi_scans.find(ms => ms.multi_scan_id === savedMultiScanId);
                
                if (savedMultiScan) {
                    displayScanResults(savedMultiScan.scans, savedMultiScan.multi_scan_id);
                } else {
                    // Если сохраненный multi-scan не найден, очищаем sessionStorage
                    sessionStorage.removeItem('currentMultiScanId');
                    sessionStorage.removeItem('baseRepoUrls');
                }
            }
        }
    } catch (error) {
        console.error('Error loading multi-scans:', error);
        // При ошибке очищаем sessionStorage
        sessionStorage.removeItem('currentMultiScanId');
        sessionStorage.removeItem('baseRepoUrls');
    }
});

function updateRefreshStatus(text) {
    const statusEl = document.getElementById('refreshStatus');
    if (statusEl) {
        statusEl.textContent = text;
        statusEl.style.color = text.includes('Обновляется') ? '#28a745' : '#666';
    }
}

// async function manualRefresh() {
//     updateRefreshStatus('Обновляется...');
//     const hasRunning = await refreshScanStatuses();
//     updateRefreshStatus(hasRunning ? 'Автообновление активно' : 'Все сканирования завершены');
    
//     if (hasRunning && !refreshTimer) {
//         startAutoRefresh();
//     }
// }

function clearScanResults() {
    // Очищаем сессионное хранилище
    sessionStorage.removeItem('currentMultiScanId');
    sessionStorage.removeItem('baseRepoUrls');
    
    // Скрываем результаты
    document.getElementById('scanResults').style.display = 'none';
    document.getElementById('completedRepos').style.display = 'none';
    document.getElementById('scanForm').style.display = 'block';
    
    // Останавливаем автообновление
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
    
    // Очищаем поле ввода
    document.getElementById('repoUrls').value = '';
    
    showAlert('success', 'Результаты мультисканирования очищены с экрана');
}