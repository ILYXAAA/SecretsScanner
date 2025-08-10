const fileUploadArea = document.getElementById('fileUploadArea');
const fileInput = document.getElementById('zip_file');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const refTypeSelect = document.getElementById('ref_type');
const refInput = document.getElementById('ref');

const placeholders = {
    'Branch': 'master',
    'Tag': 'v1.1.3',
    'Commit': 'ab12c3d...'
};

// при изменении типа ссылки обновляем placeholder
refTypeSelect.addEventListener('change', function () {
    const selectedType = this.value;
    refInput.placeholder = placeholders[selectedType] || '';
});

// Устанавливаем placeholder при загрузке
document.addEventListener('DOMContentLoaded', function () {
    refInput.placeholder = placeholders[refTypeSelect.value];
    
    // Создание круговой диаграммы
    const languageData = getLanguageStats();
    if (languageData && languageData.length > 0) {
        // Диаграмма создается только при раскрытии блока
    }
});

// Получаем данные языков из data-атрибута
function getLanguageStats() {
    try {
        const data = document.body.dataset.languageStats;
        // console.log('Raw language stats data:', data);
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error parsing language stats:', e);
        console.log('Failed data:', document.body.dataset.languageStats);
        return [];
    }
}

fileUploadArea.addEventListener('click', () => {
    fileInput.click();
});

fileUploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileUploadArea.classList.add('dragover');
});

fileUploadArea.addEventListener('dragleave', () => {
    fileUploadArea.classList.remove('dragover');
});

fileUploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    fileUploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        if (file.name.endsWith('.zip')) {
            fileInput.files = files;
            showFileInfo(file.name);
        } else {
            alert('Пожалуйста, выберите ZIP-файл');
        }
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        showFileInfo(e.target.files[0].name);
    }
});

function showFileInfo(name) {
    fileName.textContent = name;
    fileUploadArea.style.display = 'none';
    fileInfo.style.display = 'flex';
}

function removeFile() {
    fileInput.value = '';
    fileUploadArea.style.display = 'block';
    fileInfo.style.display = 'none';
}

function toggleScanForm() {
    const form = document.getElementById('scanForm');
    const editForm = document.getElementById('editProjectForm');
    const localForm = document.getElementById('localScanForm');
    editForm.classList.remove('show');
    localForm.classList.remove('show');
    form.classList.toggle('show');
}

function toggleEditForm() {
    const form = document.getElementById('editProjectForm');
    const scanForm = document.getElementById('scanForm');
    const localForm = document.getElementById('localScanForm');
    scanForm.classList.remove('show');
    localForm.classList.remove('show');
    form.classList.toggle('show');
}

function toggleLocalScanForm() {
    const form = document.getElementById('localScanForm');
    const scanForm = document.getElementById('scanForm');
    const editForm = document.getElementById('editProjectForm');
    scanForm.classList.remove('show');
    editForm.classList.remove('show');
    form.classList.toggle('show');
}

function deleteProject(id) {
    const confirmed = confirm('Вы уверены, что хотите удалить этот проект и все его сканирования?');
    if (!confirmed) return;

    fetch(`/secret_scanner/projects/${id}/delete`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => {
        if (response.ok) {
            // Redirect to dashboard after successful deletion
            window.location.href = '/secret_scanner/dashboard?success=project_deleted';
        } else {
            alert('Failed to delete project.');
        }
    })
    .catch(error => {
        console.error('Error deleting project:', error);
        alert('Something went wrong.');
    });
}

function toggleLanguageStats() {
    const statsBlock = document.getElementById('languageStats');
    const toggleButton = document.querySelector('.language-stats-toggle');
    const buttonText = toggleButton.querySelector('span:first-child');
    
    if (statsBlock.classList.contains('show')) {
        // Скрываем
        statsBlock.classList.remove('show');
        toggleButton.classList.remove('expanded');
        buttonText.textContent = '📊 Показать распределение по языкам';
    } else {
        // Показываем
        statsBlock.classList.add('show');
        toggleButton.classList.add('expanded');
        buttonText.textContent = '📊 Скрыть распределение по языкам';
        
        // Создаем диаграмму при первом показе
        const chartElement = document.getElementById('languagePieChart');
        if (chartElement && !chartElement.hasChildNodes()) {
            const languageData = getLanguageStats();
            if (languageData && languageData.length > 0) {
                // console.log('Language data:', languageData);
                createPieChart(languageData);
            }
        }
    }
}

function createPieChart(data) {
    const chartElement = document.getElementById('languagePieChart');
    if (!chartElement || !data || data.length === 0) return;
    
    // Цвета для диаграммы
    const colors = [
        '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
        '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6b7280',
        '#14b8a6', '#f43f5e', '#8b5cf6', '#22d3ee', '#a3a3a3'
    ];
    
    // Установка CSS переменных для цветов
    const root = document.documentElement;
    data.forEach((item, index) => {
        root.style.setProperty(`--color-${index}`, colors[index % colors.length]);
    });
    
    // Создание SVG
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '200');
    svg.setAttribute('height', '200');
    svg.setAttribute('viewBox', '0 0 200 200');
    
    const centerX = 100;
    const centerY = 100;
    const radius = 90;
    
    let currentAngle = -90; // Начинаем сверху
    
    data.forEach((item, index) => {
        const angle = (item.percentage / 100) * 360;
        const startAngle = (currentAngle * Math.PI) / 180;
        const endAngle = ((currentAngle + angle) * Math.PI) / 180;
        
        const x1 = centerX + radius * Math.cos(startAngle);
        const y1 = centerY + radius * Math.sin(startAngle);
        const x2 = centerX + radius * Math.cos(endAngle);
        const y2 = centerY + radius * Math.sin(endAngle);
        
        const largeArcFlag = angle > 180 ? 1 : 0;
        
        const pathData = [
            `M ${centerX} ${centerY}`,
            `L ${x1} ${y1}`,
            `A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2}`,
            'Z'
        ].join(' ');
        
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathData);
        path.setAttribute('fill', colors[index % colors.length]);
        path.setAttribute('stroke', '#ffffff');
        path.setAttribute('stroke-width', '2');
        
        // Добавляем hover эффект для диаграммы
        path.style.cursor = 'pointer';
        
        // Связываем элементы диаграммы и легенды
        const legendItem = document.querySelector(`.legend-item[data-language="${item.language}"]`);
        
        function highlightLanguage() {
            path.style.opacity = '0.8';
            path.style.transform = 'scale(1.05)';
            path.style.transformOrigin = '100px 100px';
            
            if (legendItem) {
                legendItem.style.boxShadow = '0 4px 8px rgba(0,0,0,0.2)';
                legendItem.style.background = '#f0f9ff';
            }
        }
        
        function unhighlightLanguage() {
            path.style.opacity = '1';
            path.style.transform = 'scale(1)';
            
            if (legendItem) {
                legendItem.style.boxShadow = '';
                legendItem.style.background = 'white';
            }
        }
        
        path.addEventListener('mouseenter', highlightLanguage);
        path.addEventListener('mouseleave', unhighlightLanguage);
        
        if (legendItem) {
            legendItem.addEventListener('mouseenter', function() {
                highlightLanguage();
                // Показать расширения в tooltip
                const extensions = item.extensions && item.extensions.length > 0 ? item.extensions.join(', ') : 'нет данных';
                legendItem.title = `Расширения: ${extensions}`;
            });
            legendItem.addEventListener('mouseleave', function() {
                unhighlightLanguage();
                legendItem.removeAttribute('title');
            });
        }
        
        // Добавляем tooltip для диаграммы
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        const extensions = item.extensions && item.extensions.length > 0 ? item.extensions.join(', ') : 'нет данных';
        title.textContent = `${item.language}: ${item.count} файлов (${item.percentage}%)\nРасширения: ${extensions}`;
        path.appendChild(title);
        
        svg.appendChild(path);
        currentAngle += angle;
    });
    
    chartElement.appendChild(svg);
}

function toggleFrameworkDetails(framework) {
    const detailsElement = document.getElementById(`framework-details-${framework}`);
    const button = document.querySelector(`[onclick="toggleFrameworkDetails('${framework}')"]`);
    
    if (detailsElement.style.display === 'none') {
        detailsElement.style.display = 'block';
        button.textContent = '📋 Скрыть';
        button.style.background = '#fee2e2';
        button.style.borderColor = '#ef4444';
        button.style.color = '#ef4444';
    } else {
        detailsElement.style.display = 'none';
        button.textContent = '📋 Подробнее';
        button.style.background = '#f0f9ff';
        button.style.borderColor = '#0ea5e9';
        button.style.color = '#0ea5e9';
    }
}

function openFrameworkFile(filePath, framework) {
    const projectRepoUrl = document.body.dataset.projectRepoUrl;
    const scanCommit = document.body.dataset.latestScanCommit;
    const hubType = document.body.dataset.hubType;
    
    let fileUrl;
    
    if (projectRepoUrl.includes('devzone.local')) {
        // DevZone/GitLab URL format
        fileUrl = `${projectRepoUrl}/-/blob/${scanCommit}/${encodeURIComponent(filePath)}`;
    } else if (hubType === 'Azure') {
        // Azure DevOps URL format
        fileUrl = `${projectRepoUrl}?path=${encodeURIComponent(filePath)}&version=GC${scanCommit}&_a=contents`;
    } else {
        // Default/GitHub URL format
        fileUrl = `${projectRepoUrl}/blob/${scanCommit}/${encodeURIComponent(filePath)}`;
    }
    
    window.open(fileUrl, '_blank');
}

// Auto-refresh if there's a running scan
document.addEventListener('DOMContentLoaded', function() {
    const latestScanStatus = document.body.dataset.latestScanStatus;
    if (latestScanStatus === 'running') {
        setTimeout(() => {
            window.location.reload();
        }, 5000);
    }
});