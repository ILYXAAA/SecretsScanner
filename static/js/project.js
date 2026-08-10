const fileUploadArea = document.getElementById('fileUploadArea');
const fileInput = document.getElementById('zip_file');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const refTypeSelect = document.getElementById('ref_type');
const refInput = document.getElementById('ref');

const ICON_BASE = '/secret_scanner/static/icons/new/';
const CHEVRON_DOWN = `${ICON_BASE}AltArrowDownLineDuotone.svg`;
const CHEVRON_UP = `${ICON_BASE}AltArrowUpLineDuotone.svg`;

const placeholders = {
    'Branch': 'master',
    'Tag': 'v1.1.3',
    'Commit': 'ab12c3d...'
};

function setIconSelectChevron(wrapper, isOpen) {
    const chevron = wrapper.querySelector('.icon-select-chevron');
    if (!chevron) return;
    chevron.src = isOpen ? CHEVRON_UP : CHEVRON_DOWN;
}

function syncIconSelectTrigger(wrapper) {
    const select = wrapper.querySelector('select');
    const option = select?.options[select.selectedIndex];
    const triggerIcon = wrapper.querySelector('.icon-select-trigger-icon');
    const triggerLabel = wrapper.querySelector('.icon-select-trigger-label');

    if (!option || !triggerIcon || !triggerLabel) return;

    triggerIcon.src = `${ICON_BASE}${option.dataset.icon || ''}`;
    triggerIcon.className = `icon-select-trigger-icon ui-icon ${option.dataset.tint || ''}`.trim();
    triggerLabel.textContent = option.textContent;
}

function updateIconSelectOptions(wrapper) {
    const select = wrapper.querySelector('select');
    if (!select) return;

    wrapper.querySelectorAll('.icon-select-option').forEach(li => {
        const isSelected = li.dataset.value === select.value;
        li.classList.toggle('selected', isSelected);
        li.setAttribute('aria-selected', isSelected ? 'true' : 'false');
    });
}

function closeIconSelectMenu(wrapper) {
    const menu = wrapper.querySelector('.icon-select-menu');
    const trigger = wrapper.querySelector('.icon-select-trigger');
    if (menu) menu.hidden = true;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    wrapper.classList.remove('open');
    setIconSelectChevron(wrapper, false);
}

function closeAllIconSelectMenus(exceptWrapper = null) {
    document.querySelectorAll('.select-with-icon.open').forEach(wrapper => {
        if (wrapper !== exceptWrapper) {
            closeIconSelectMenu(wrapper);
        }
    });
}

function toggleIconSelectMenu(wrapper) {
    const menu = wrapper.querySelector('.icon-select-menu');
    const trigger = wrapper.querySelector('.icon-select-trigger');
    if (!menu || !trigger) return;

    const willOpen = menu.hidden;
    closeAllIconSelectMenus();

    if (willOpen) {
        menu.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        wrapper.classList.add('open');
        setIconSelectChevron(wrapper, true);
    }
}

function selectIconSelectOption(wrapper, value) {
    const select = wrapper.querySelector('select');
    if (!select) return;

    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    syncIconSelectTrigger(wrapper);
    updateIconSelectOptions(wrapper);
    closeIconSelectMenu(wrapper);
}

function buildIconSelect(wrapper) {
    const select = wrapper.querySelector('select');
    if (!select || wrapper.dataset.iconSelectBuilt === 'true') return;
    wrapper.dataset.iconSelectBuilt = 'true';

    select.classList.add('icon-select-native');
    select.tabIndex = -1;

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'icon-select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');

    const triggerIcon = document.createElement('img');
    triggerIcon.className = 'icon-select-trigger-icon ui-icon';
    triggerIcon.width = 16;
    triggerIcon.height = 16;
    triggerIcon.alt = '';

    const triggerLabel = document.createElement('span');
    triggerLabel.className = 'icon-select-trigger-label';

    const triggerChevron = document.createElement('img');
    triggerChevron.src = CHEVRON_DOWN;
    triggerChevron.className = 'icon-select-chevron ui-icon';
    triggerChevron.width = 16;
    triggerChevron.height = 16;
    triggerChevron.alt = '';

    trigger.append(triggerIcon, triggerLabel, triggerChevron);

    const menu = document.createElement('ul');
    menu.className = 'icon-select-menu';
    menu.setAttribute('role', 'listbox');
    menu.hidden = true;

    Array.from(select.options).forEach(option => {
        const item = document.createElement('li');
        item.className = 'icon-select-option';
        item.setAttribute('role', 'option');
        item.dataset.value = option.value;
        if (option.selected) {
            item.classList.add('selected');
        }
        item.setAttribute('aria-selected', option.selected ? 'true' : 'false');

        const optionIcon = document.createElement('img');
        optionIcon.className = `icon-select-option-icon ui-icon ${option.dataset.tint || ''}`.trim();
        optionIcon.src = `${ICON_BASE}${option.dataset.icon || ''}`;
        optionIcon.width = 16;
        optionIcon.height = 16;
        optionIcon.alt = '';

        const optionLabel = document.createElement('span');
        optionLabel.className = 'icon-select-option-label';
        optionLabel.textContent = option.textContent;

        item.append(optionIcon, optionLabel);
        item.addEventListener('click', (event) => {
            event.stopPropagation();
            selectIconSelectOption(wrapper, option.value);
        });
        menu.appendChild(item);
    });

    select.insertAdjacentElement('afterend', trigger);
    trigger.insertAdjacentElement('afterend', menu);

    menu.addEventListener('click', (event) => {
        event.stopPropagation();
    });

    const label = wrapper.closest('.form-group')?.querySelector(`label[for="${select.id}"]`);
    if (label) {
        label.addEventListener('click', (event) => {
            event.preventDefault();
            trigger.focus();
            toggleIconSelectMenu(wrapper);
        });
    }

    trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleIconSelectMenu(wrapper);
    });

    select.addEventListener('change', () => {
        syncIconSelectTrigger(wrapper);
        updateIconSelectOptions(wrapper);
    });

    syncIconSelectTrigger(wrapper);
}

function initIconSelects() {
    document.querySelectorAll('.select-with-icon.icon-select').forEach(buildIconSelect);
}

document.addEventListener('click', () => closeAllIconSelectMenus());
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeAllIconSelectMenus();
    }
});

// при изменении типа ссылки обновляем placeholder
if (refTypeSelect && refInput) {
    refTypeSelect.addEventListener('change', function () {
        const selectedType = this.value;
        refInput.placeholder = placeholders[selectedType] || '';
    });
}

// Устанавливаем placeholder при загрузке
document.addEventListener('DOMContentLoaded', function () {
    if (refTypeSelect && refInput) {
        refInput.placeholder = placeholders[refTypeSelect.value];
    }

    initIconSelects();
    
    document.querySelectorAll('.history-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.historyTab;
            document.querySelectorAll('.history-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.history-tab-panel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            const panel = document.getElementById(`history-${target}`);
            if (panel) panel.classList.add('active');
        });
    });

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

function closeProjectActionsMenu() {
    const menu = document.getElementById('projectActionsMenu');
    const trigger = document.getElementById('projectActionsMoreBtn');
    const wrapper = document.querySelector('.actions-more');
    if (!menu || !trigger || !wrapper) return;

    menu.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    wrapper.classList.remove('open');
}

function toggleProjectActionsMenu() {
    const menu = document.getElementById('projectActionsMenu');
    const trigger = document.getElementById('projectActionsMoreBtn');
    const wrapper = document.querySelector('.actions-more');
    if (!menu || !trigger || !wrapper) return;

    const willOpen = menu.hidden;
    closeAllIconSelectMenus();
    closeProjectActionsMenu();

    if (willOpen) {
        menu.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        wrapper.classList.add('open');
    }
}

function handleMoreAction(action) {
    closeProjectActionsMenu();

    if (action === 'edit') {
        toggleEditForm();
        return;
    }

    if (action === 'merge') {
        toggleMergeForm();
        return;
    }

    if (action === 'delete') {
        const projectId = document.body.dataset.projectId;
        if (projectId) {
            deleteProject(projectId);
        }
    }
}

function toggleScanForm() {
    const form = document.getElementById('scanForm');
    const editForm = document.getElementById('editProjectForm');
    const localForm = document.getElementById('localScanForm');
    const mergeForm = document.getElementById('mergeProjectForm');
    editForm.classList.remove('show');
    localForm.classList.remove('show');
    mergeForm.classList.remove('show');
    form.classList.toggle('show');
    closeProjectActionsMenu();
}

function toggleEditForm() {
    const form = document.getElementById('editProjectForm');
    const scanForm = document.getElementById('scanForm');
    const localForm = document.getElementById('localScanForm');
    const mergeForm = document.getElementById('mergeProjectForm');
    scanForm.classList.remove('show');
    localForm.classList.remove('show');
    mergeForm.classList.remove('show');
    form.classList.toggle('show');
    closeProjectActionsMenu();
}

function toggleLocalScanForm() {
    const form = document.getElementById('localScanForm');
    const scanForm = document.getElementById('scanForm');
    const editForm = document.getElementById('editProjectForm');
    const mergeForm = document.getElementById('mergeProjectForm');
    scanForm.classList.remove('show');
    editForm.classList.remove('show');
    mergeForm.classList.remove('show');
    form.classList.toggle('show');
    closeProjectActionsMenu();
}

function toggleMergeForm() {
    const form = document.getElementById('mergeProjectForm');
    const scanForm = document.getElementById('scanForm');
    const editForm = document.getElementById('editProjectForm');
    const localForm = document.getElementById('localScanForm');
    scanForm.classList.remove('show');
    editForm.classList.remove('show');
    localForm.classList.remove('show');
    form.classList.toggle('show');
    closeProjectActionsMenu();
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

function mergeProjects() {
    const targetProjectName = document.getElementById('target_project_name').value.trim();
    const newRepoUrl = document.getElementById('new_repo_url').value.trim();
    
    if (!targetProjectName) {
        alert('Пожалуйста, выберите проект для объединения');
        return;
    }
    
    if (!newRepoUrl) {
        alert('Пожалуйста, укажите URL репозитория');
        return;
    }
    
    const confirmed = confirm(`Вы уверены, что хотите объединить проект "${targetProjectName}" с текущим проектом?\n\nВсе сканирования из проекта "${targetProjectName}" будут перенесены в текущий проект, а проект "${targetProjectName}" будет удален.\n\nЭто действие необратимо!`);
    if (!confirmed) return;

    // Submit the merge form
    document.getElementById('mergeProjectForm').querySelector('form').submit();
}

// Autocomplete functionality for project search
let projectSearchTimeout;
function setupProjectAutocomplete() {
    const input = document.getElementById('target_project_name');
    const dropdown = document.getElementById('project_dropdown');
    const currentProjectName = document.body.dataset.currentProjectName;
    
    if (!input || !dropdown) return;
    
    input.addEventListener('input', function() {
        const query = this.value.trim();
        
        clearTimeout(projectSearchTimeout);
        
        if (query.length < 1) {
            dropdown.style.display = 'none';
            return;
        }
        
        projectSearchTimeout = setTimeout(() => {
            fetch(`/secret_scanner/api/projects/search?q=${encodeURIComponent(query)}&current_project=${encodeURIComponent(currentProjectName)}`)
                .then(response => response.json())
                .then(data => {
                    dropdown.innerHTML = '';
                    
                    if (data.projects && data.projects.length > 0) {
                        data.projects.forEach(project => {
                            const item = document.createElement('div');
                            item.className = 'dropdown-item';
                            item.innerHTML = `
                                <div class="project-name">${project.name}</div>
                                <div class="project-url">${project.repo_url}</div>
                            `;
                            item.addEventListener('click', () => {
                                input.value = project.name;
                                document.getElementById('new_repo_url').value = project.repo_url;
                                dropdown.style.display = 'none';
                            });
                            dropdown.appendChild(item);
                        });
                        dropdown.style.display = 'block';
                    } else {
                        dropdown.style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('Error searching projects:', error);
                    dropdown.style.display = 'none';
                });
        }, 300);
    });
    
    // Hide dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
    
    // Handle keyboard navigation
    input.addEventListener('keydown', function(e) {
        const items = dropdown.querySelectorAll('.dropdown-item');
        let selectedIndex = -1;
        
        // Find currently selected item
        items.forEach((item, index) => {
            if (item.classList.contains('selected')) {
                selectedIndex = index;
            }
        });
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
        } else if (e.key === 'Enter' && selectedIndex >= 0) {
            e.preventDefault();
            items[selectedIndex].click();
            return;
        } else if (e.key === 'Escape') {
            dropdown.style.display = 'none';
            return;
        }
        
        // Update selection
        items.forEach((item, index) => {
            if (index === selectedIndex) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        });
    });
}

function toggleLatestScan() {
    const section = document.getElementById('latestScanSection');
    const toggleButton = document.querySelector('.latest-scan-toggle');
    const label = toggleButton.querySelector('.latest-scan-toggle-label');
    const isExpanded = section.classList.toggle('expanded');

    toggleButton.classList.toggle('expanded', isExpanded);
    toggleButton.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
    label.textContent = isExpanded ? 'Скрыть последний скан' : 'Показать последний скан';
}

function toggleLanguageStats() {
    const statsBlock = document.getElementById('languageStats');
    const toggleButton = document.querySelector('.language-stats-toggle');
    const buttonText = toggleButton.querySelector('.language-toggle-label');

    if (statsBlock.classList.contains('show')) {
        statsBlock.classList.remove('show');
        toggleButton.classList.remove('expanded');
        buttonText.textContent = 'Показать распределение по языкам';
    } else {
        statsBlock.classList.add('show');
        toggleButton.classList.add('expanded');
        buttonText.textContent = 'Скрыть распределение по языкам';

        const chartElement = document.getElementById('languagePieChart');
        if (chartElement && !chartElement.hasChildNodes()) {
            const languageData = getLanguageStats();
            if (languageData && languageData.length > 0) {
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
    const button = document.querySelector(`[data-framework-toggle="${framework}"]`);
    const label = button.querySelector('.framework-toggle-label');

    if (!detailsElement.classList.contains('is-open')) {
        detailsElement.classList.add('is-open');
        button.classList.add('is-expanded');
        label.textContent = 'Скрыть';
    } else {
        detailsElement.classList.remove('is-open');
        button.classList.remove('is-expanded');
        label.textContent = 'Подробнее';
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
    const moreBtn = document.getElementById('projectActionsMoreBtn');
    if (moreBtn) {
        moreBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleProjectActionsMenu();
        });
    }

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.actions-more')) {
            closeProjectActionsMenu();
        }
    });

    const latestScanStatus = document.body.dataset.latestScanStatus;
    if (latestScanStatus === 'running') {
        setTimeout(() => {
            window.location.reload();
        }, 5000);
    }
    
    // Setup autocomplete for merge form
    setupProjectAutocomplete();
});