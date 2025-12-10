let currentPage = 1;
let totalPages = 1;
let currentTokensPage = 1;
let totalTokensPages = 1;
let currentUserSearch = '';
let currentTokenSearch = '';
let currentProjectsTaskId = null;
let maintenanceModeToggleInProgress = false;

// Tab switching function
function switchTab(tabName) {
    // Hide all tab contents and explicitly hide their children
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => {
        content.classList.remove('active');
        content.style.display = 'none';
    });
    
    // Remove active class from all tab buttons
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => {
        button.classList.remove('active');
    });
    
    // Show selected tab content
    const selectedTab = document.getElementById(`tab-${tabName}`);
    if (selectedTab) {
        selectedTab.classList.add('active');
        selectedTab.style.display = 'block';
    }
    
    // Add active class to selected tab button
    const selectedButton = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedButton) {
        selectedButton.classList.add('active');
    }
    
    // Load models info when switching to scanning tab
    if (tabName === 'scanning') {
        loadModelsInfo();
    }
}

// Load users on page load
// Load API tokens on page load
document.addEventListener('DOMContentLoaded', function() {
    loadUsers();
    loadApiTokens();

    const projectsForm = document.getElementById('exportProjectsForm');
    if (projectsForm) {
        projectsForm.addEventListener('submit', handleProjectsExport);
    }
    
    // Handle form submission for permissions
    const form = document.querySelector('form[action="/secret_scanner/admin/create-api-token"]');
    if (form) {
        form.addEventListener('submit', function(e) {
            const checkboxes = form.querySelectorAll('input[name^="perm_"]');
            const permissions = {};
            
            checkboxes.forEach(cb => {
                const permName = cb.name.replace('perm_', '');
                permissions[permName] = cb.checked;
            });
            
            // Create hidden input with permissions JSON
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = 'permissions';
            hiddenInput.value = JSON.stringify(permissions);
            form.appendChild(hiddenInput);
        });
    }
});

async function loadApiTokens(page = 1, search = '') {
    const loading = document.getElementById('tokensLoading');
    const table = document.getElementById('tokensTable');
    const tbody = document.getElementById('tokensTableBody');
    const pagination = document.getElementById('tokensPagination');
    
    loading.style.display = 'block';
    table.style.display = 'none';
    pagination.style.display = 'none';
    
    try {
        const params = new URLSearchParams({
            page: page.toString(),
            search: search
        });
        
        const response = await fetch(`/secret_scanner/admin/api-tokens?${params}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            tbody.innerHTML = '';
            
            if (data.tokens.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="9" class="empty-state">
                            <div>${search ? 'API токены не найдены по запросу' : 'API токены не найдены'}</div>
                        </td>
                    </tr>
                `;
            } else {
                data.tokens.forEach(token => {
                    const permissions = Object.entries(token.permissions)
                        .filter(([key, value]) => value)
                        .map(([key]) => key.replace('_', ' '))
                        .join(', ') || 'Нет';
                    
                    const statusColor = token.is_active ? '#28a745' : '#dc3545';
                    const statusText = token.is_active ? 'Активен' : 'Отключен';
                    
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><strong>${token.name}</strong></td>
                        <td><code style="font-size: 0.85rem;">${token.prefix}</code></td>
                        <td>${token.created_at}<br><small>${token.created_by}</small></td>
                        <td>${token.expires_at || 'Бессрочный'}</td>
                        <td>${token.last_used_at}</td>
                        <td><span style="color: ${statusColor}; font-weight: 600;">${statusText}</span></td>
                        <td style="font-size: 0.85rem;">${permissions}</td>
                        <td style="font-size: 0.85rem;">
                            ${token.requests_per_minute}/мин<br>
                            ${token.requests_per_hour}/час<br>
                            ${token.requests_per_day}/день
                        </td>
                        <td>
                            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                                <button type="button" class="btn ${token.is_active ? 'btn-warning' : 'btn-success'}" 
                                        onclick="toggleApiToken(${token.id})" style="padding: 0.25rem 0.5rem; font-size: 0.85rem;">
                                    ${token.is_active ? 'Отключить' : 'Включить'}
                                </button>
                                <button type="button" class="btn btn-danger" 
                                        onclick="deleteApiToken(${token.id}, '${token.name}')" style="padding: 0.25rem 0.5rem; font-size: 0.85rem;">
                                    Удалить
                                </button>
                            </div>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }
            
            // Update pagination for tokens
            if (data.pagination && data.pagination.total_pages > 1) {
                currentTokensPage = data.pagination.current_page;
                totalTokensPages = data.pagination.total_pages;
                
                document.getElementById('tokensPageInfo').textContent = 
                    `Страница ${currentTokensPage} из ${totalTokensPages}`;
                document.getElementById('tokensTotalInfo').textContent = 
                    `Всего токенов: ${data.pagination.total_tokens}`;
                
                document.getElementById('prevTokensPage').disabled = currentTokensPage <= 1;
                document.getElementById('nextTokensPage').disabled = currentTokensPage >= totalTokensPages;
                
                pagination.style.display = 'block';
            }
            
            table.style.display = 'table';
        } else {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="empty-state">
                        <div style="color: #dc3545;">Ошибка загрузки токенов</div>
                    </td>
                </tr>
            `;
            table.style.display = 'table';
        }
    } catch (error) {
        console.error('Error loading API tokens:', error);
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="empty-state">
                    <div style="color: #dc3545;">Ошибка соединения</div>
                </td>
            </tr>
        `;
        table.style.display = 'table';
    } finally {
        loading.style.display = 'none';
    }
}

function changeTokensPage(direction) {
    const newPage = currentTokensPage + direction;
    if (newPage >= 1 && newPage <= totalTokensPages) {
        loadApiTokens(newPage, currentTokenSearch);
    }
}

let userSearchTimeout = null;
let tokenSearchTimeout = null;

function searchUsers() {
    // Очистить предыдущий таймер
    if (userSearchTimeout) {
        clearTimeout(userSearchTimeout);
    }
    
    // Установить новый таймер с задержкой 500ms
    userSearchTimeout = setTimeout(() => {
        const searchInput = document.getElementById('userSearch');
        currentUserSearch = searchInput.value.trim();
        currentPage = 1; // Reset to first page
        loadUsers(1, currentUserSearch);
    }, 500);
}

function searchTokens() {
    // Очистить предыдущий таймер
    if (tokenSearchTimeout) {
        clearTimeout(tokenSearchTimeout);
    }
    
    // Установить новый таймер с задержкой 500ms
    tokenSearchTimeout = setTimeout(() => {
        const searchInput = document.getElementById('tokenSearch');
        currentTokenSearch = searchInput.value.trim();
        currentTokensPage = 1; // Reset to first page
        loadApiTokens(1, currentTokenSearch);
    }, 500);
}

async function deleteApiToken(tokenId, tokenName) {
    if (!confirm(`Вы уверены, что хотите удалить API токен "${tokenName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/secret_scanner/admin/delete-api-token/${tokenId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadApiTokens(currentTokensPage, currentTokenSearch); // Reload with current search
        } else {
            alert('Ошибка при удалении токена');
        }
    } catch (error) {
        console.error('Error deleting API token:', error);
        alert('Ошибка соединения');
    }
}

async function toggleMaintenanceMode(enabled) {
    if (maintenanceModeToggleInProgress) {
        return;
    }
    
    const statusDiv = document.getElementById('maintenanceModeStatus');
    const switchElement = document.getElementById('maintenanceModeSwitch');
    
    // Show confirmation
    const action = enabled ? 'включить' : 'выключить';
    const confirmMessage = enabled 
        ? 'Вы уверены, что хотите включить режим технических работ? Все обычные пользователи будут перенаправлены на страницу технического обслуживания.'
        : 'Вы уверены, что хотите выключить режим технических работ?';
    
    if (!confirm(confirmMessage)) {
        // Revert switch state
        switchElement.checked = !enabled;
        return;
    }
    
    maintenanceModeToggleInProgress = true;
    switchElement.disabled = true;
    statusDiv.style.display = 'block';
    statusDiv.className = 'maintenance-status info';
    statusDiv.textContent = enabled ? 'Проверка активных сканирований...' : 'Выключение режима технических работ...';
    
    try {
        const formData = new FormData();
        formData.append('enabled', enabled.toString());
        
        const response = await fetch('/secret_scanner/admin/toggle-maintenance-mode', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === 'success') {
            statusDiv.className = 'maintenance-status success';
            statusDiv.textContent = data.message;
            
            // Hide status after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        } else {
            // Revert switch state on error
            switchElement.checked = !enabled;
            statusDiv.className = 'maintenance-status error';
            statusDiv.textContent = data.message || 'Ошибка при изменении режима технических работ';
        }
    } catch (error) {
        console.error('Error toggling maintenance mode:', error);
        // Revert switch state on error
        switchElement.checked = !enabled;
        statusDiv.className = 'maintenance-status error';
        statusDiv.textContent = 'Ошибка соединения с сервером';
    } finally {
        maintenanceModeToggleInProgress = false;
        switchElement.disabled = false;
    }
}

async function toggleApiToken(tokenId) {
    try {
        const response = await fetch(`/secret_scanner/admin/toggle-api-token/${tokenId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadApiTokens(currentTokensPage, currentTokenSearch); // Reload with current search
        } else {
            alert('Ошибка при изменении статуса токена');
        }
    } catch (error) {
        console.error('Error toggling API token:', error);
        alert('Ошибка соединения');
    }
}

function toggleCollapsible(id) {
    const content = document.getElementById(id);
    const header = content.previousElementSibling;
    const chevron = header.querySelector('.chevron');
    
    if (content.classList.contains('active')) {
        content.classList.remove('active');
        header.classList.remove('active');
        chevron.classList.remove('down');
    } else {
        content.classList.add('active');
        header.classList.add('active');
        chevron.classList.add('down');
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Временно изменить текст кнопки
        const button = event.target;
        const originalText = button.textContent;
        button.textContent = 'Скопировано!';
        setTimeout(() => {
            button.textContent = originalText;
        }, 2000);
    });
}

async function loadUsers(page = 1, search = '') {
    const loading = document.getElementById('usersLoading');
    const table = document.getElementById('usersTable');
    const tbody = document.getElementById('usersTableBody');
    const pagination = document.getElementById('pagination');
    
    loading.style.display = 'block';
    table.style.display = 'none';
    pagination.style.display = 'none';
    
    try {
        const params = new URLSearchParams({
            page: page.toString(),
            search: search
        });
        
        const response = await fetch(`/secret_scanner/admin/users?${params}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            tbody.innerHTML = '';
            
            if (data.users.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-state">
                            <div>${search ? 'Пользователи не найдены по запросу' : 'Пользователи не найдены'}</div>
                        </td>
                    </tr>
                `;
            } else {
                data.users.forEach(user => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>
                            <div class="user-info">
                                <div class="user-avatar">
                                    ${user.username.charAt(0).toUpperCase()}
                                </div>
                                <div class="user-details">
                                    <div class="username">${user.username}</div>
                                </div>
                            </div>
                        </td>
                        <td>
                            <div class="user-date">${user.created_at}</div>
                        </td>
                        <td>
                            <span style="font-weight: 600; color: #333;">${user.scan_count}</span>
                        </td>
                        <td>
                            <span style="font-weight: 600; color: #333;">${user.project_count}</span>
                        </td>
                        <td>
                            ${user.username === 'admin' ? 
                                '<span style="color: #666; font-style: italic;">Администратор</span>' :
                                `<button type="button" class="btn btn-danger" onclick="deleteUser('${user.username}')">Удалить</button>`
                            }
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }
            
            // Update pagination
            if (data.pagination.total_pages > 1) {
                currentPage = data.pagination.current_page;
                totalPages = data.pagination.total_pages;
                
                document.getElementById('pageInfo').textContent = 
                    `Страница ${currentPage} из ${totalPages}`;
                document.getElementById('totalInfo').textContent = 
                    `Всего пользователей: ${data.pagination.total_users}`;
                
                document.getElementById('prevPage').disabled = currentPage <= 1;
                document.getElementById('nextPage').disabled = currentPage >= totalPages;
                
                pagination.style.display = 'block';
            }
            
            table.style.display = 'table';
        } else {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" class="empty-state">
                        <div style="color: #dc3545;">Ошибка загрузки пользователей</div>
                    </td>
                </tr>
            `;
            table.style.display = 'table';
        }
    } catch (error) {
        console.error('Error loading users:', error);
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="empty-state">
                    <div style="color: #dc3545;">Ошибка соединения</div>
                </td>
            </tr>
        `;
        table.style.display = 'table';
    } finally {
        loading.style.display = 'none';
    }
}

function changePage(direction) {
    const newPage = currentPage + direction;
    if (newPage >= 1 && newPage <= totalPages) {
        loadUsers(newPage, currentUserSearch);
    }
}

async function deleteUser(username) {
    if (!confirm(`Вы уверены, что хотите удалить пользователя "${username}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/secret_scanner/admin/delete-user/${username}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadUsers(currentPage, currentUserSearch); // Reload with current search
            // Show success message
            window.location.href = '/secret_scanner/admin?success=user_deleted';
        } else {
            alert('Ошибка при удалении пользователя');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        alert('Ошибка соединения');
    }
}

// Export functionality
let currentTaskId = null;

// Global variables for user selection
let allUsers = [];
let selectedExcludedUsers = new Set();
let filteredUsers = [];

async function loadAllUsers() {
    try {
        const response = await fetch('/secret_scanner/admin/users/all');
        const data = await response.json();
        if (data.status === 'success') {
            allUsers = data.users.map(u => u.username);
            filteredUsers = [...allUsers];
        }
    } catch (error) {
        console.error('Error loading users:', error);
    }
}

function toggleExcludedUsers() {
    const statusFilter = document.getElementById('status_filter').value;
    const excludedUsersGroup = document.getElementById('excludedUsersGroup');
    
    if (statusFilter === 'confirmed' || statusFilter === 'refuted') {
        excludedUsersGroup.style.display = 'block';
        if (allUsers.length === 0) {
            loadAllUsers();
        }
    } else {
        excludedUsersGroup.style.display = 'none';
        selectedExcludedUsers.clear();
        updateSelectedUsersList();
    }
}

function filterUsers(searchTerm) {
    const searchLower = searchTerm.toLowerCase();
    filteredUsers = allUsers.filter(username => 
        username.toLowerCase().includes(searchLower) && !selectedExcludedUsers.has(username)
    );
    showUsersDropdown();
}

function showUsersDropdown() {
    const dropdown = document.getElementById('usersDropdown');
    if (filteredUsers.length === 0) {
        dropdown.style.display = 'none';
        return;
    }
    
    dropdown.innerHTML = filteredUsers.map(username => `
        <div style="padding: 0.5rem; cursor: pointer; border-bottom: 1px solid #f0f0f0;" 
             onmouseover="this.style.background='#f8f9fa'" 
             onmouseout="this.style.background='white'"
             onclick="selectUser('${username}')">
            ${username}
        </div>
    `).join('');
    dropdown.style.display = 'block';
}

function selectUser(username) {
    selectedExcludedUsers.add(username);
    updateSelectedUsersList();
    document.getElementById('excludedUsersSearch').value = '';
    filterUsers('');
    showUsersDropdown();
}

function removeUser(username) {
    selectedExcludedUsers.delete(username);
    updateSelectedUsersList();
    filterUsers(document.getElementById('excludedUsersSearch').value);
}

function updateSelectedUsersList() {
    const list = document.getElementById('selectedUsersList');
    if (selectedExcludedUsers.size === 0) {
        list.innerHTML = '';
        return;
    }
    
    list.innerHTML = Array.from(selectedExcludedUsers).map(username => `
        <span style="display: inline-flex; align-items: center; gap: 0.5rem; background: #e9ecef; padding: 0.25rem 0.75rem; border-radius: 16px; font-size: 0.9rem;">
            ${username}
            <button type="button" onclick="removeUser('${username}')" style="background: none; border: none; cursor: pointer; color: #666; font-size: 1.1rem; line-height: 1; padding: 0;">×</button>
        </span>
    `).join('');
}

// Hide dropdown when clicking outside
document.addEventListener('click', function(e) {
    const container = document.getElementById('excludedUsersContainer');
    const dropdown = document.getElementById('usersDropdown');
    if (container && dropdown && !container.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = 'none';
    }
});

document.getElementById('exportForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const statusFilter = document.getElementById('status_filter').value;
    const exportBtn = document.getElementById('exportBtn');
    const exportProgress = document.getElementById('exportProgress');
    const exportMessage = document.getElementById('exportMessage');
    const downloadSection = document.getElementById('downloadSection');
    
    // Disable form and show progress
    exportBtn.disabled = true;
    exportProgress.style.display = 'block';
    downloadSection.style.display = 'none';
    exportMessage.textContent = 'Инициализация...';
    
    // Reset spinner visibility
    const spinner = exportProgress.querySelector('.spinner');
    const checkmark = exportProgress.querySelector('.checkmark');
    if (spinner) spinner.style.display = 'inline-block';
    if (checkmark) checkmark.style.display = 'none';
    
    try {
        const formData = new FormData();
        formData.append('status_filter', statusFilter);
        
        // Add excluded users if any
        if (selectedExcludedUsers.size > 0) {
            formData.append('excluded_users', Array.from(selectedExcludedUsers).join(','));
        }
        
        const response = await fetch('/secret_scanner/admin/export-secrets', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            currentTaskId = data.task_id;
            checkExportStatus();
        } else {
            throw new Error(data.message || 'Export failed');
        }
        
    } catch (error) {
        console.error('Export error:', error);
        exportMessage.textContent = `Ошибка: ${error.message}`;
        exportBtn.disabled = false;
        // Hide spinner on error
        const spinner = exportProgress.querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
    }
});

async function checkExportStatus() {
    if (!currentTaskId) return;
    
    try {
        const response = await fetch(`/secret_scanner/admin/export-status/${currentTaskId}`);
        const data = await response.json();
        
        const exportMessage = document.getElementById('exportMessage');
        const downloadSection = document.getElementById('downloadSection');
        const exportBtn = document.getElementById('exportBtn');
        const spinner = document.getElementById('exportProgress').querySelector('.spinner');
        const checkmark = document.getElementById('exportProgress').querySelector('.checkmark');
        
        exportMessage.textContent = data.message;
        
        if (data.status === 'ready') {
            // Hide spinner and show checkmark
            if (spinner) spinner.style.display = 'none';
            if (checkmark) checkmark.style.display = 'inline-block';
            
            downloadSection.style.display = 'block';
            exportBtn.disabled = false;
            
            document.getElementById('downloadBtn').onclick = function() {
                window.location.href = `/secret_scanner/admin/download/${currentTaskId}`;
                document.getElementById('exportProgress').style.display = 'none';
                currentTaskId = null;
            };
            
        } else if (data.status === 'error') {
            // Hide spinner on error
            if (spinner) spinner.style.display = 'none';
            exportBtn.disabled = false;
        } else {
            // Still processing, check again
            setTimeout(checkExportStatus, 1000);
        }
        
    } catch (error) {
        console.error('Status check error:', error);
        document.getElementById('exportMessage').textContent = 'Ошибка проверки статуса';
        document.getElementById('exportBtn').disabled = false;
        // Hide spinner on error
        const spinner = document.getElementById('exportProgress').querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
    }
}

async function handleProjectsExport(e) {
    e.preventDefault();
    
    const exportBtn = document.getElementById('exportProjectsBtn');
    const exportProgress = document.getElementById('exportProjectsProgress');
    const exportMessage = document.getElementById('exportProjectsMessage');
    const downloadSection = document.getElementById('downloadProjectsSection');
    
    // Get selected technologies
    const selectedTechs = [];
    const checkboxes = document.querySelectorAll('input[name="tech_filter"]:checked');
    checkboxes.forEach(cb => {
        selectedTechs.push(cb.value);
    });
    
    if (selectedTechs.length === 0) {
        alert('Выберите хотя бы одну технологию для поиска');
        return;
    }
    
    // Disable form and show progress
    exportBtn.disabled = true;
    exportProgress.style.display = 'block';
    downloadSection.style.display = 'none';
    exportMessage.textContent = 'Инициализация...';
    
    // Reset spinner visibility
    const spinner = exportProgress.querySelector('.spinner');
    const checkmark = exportProgress.querySelector('.checkmark');
    if (spinner) spinner.style.display = 'inline-block';
    if (checkmark) checkmark.style.display = 'none';
    
    try {
        const formData = new FormData();
        selectedTechs.forEach(tech => {
            formData.append('technologies[]', tech);
        });
        
        const response = await fetch('/secret_scanner/admin/export-projects', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            currentProjectsTaskId = data.task_id;
            checkProjectsExportStatus();
        } else {
            throw new Error(data.message || 'Export failed');
        }
        
    } catch (error) {
        console.error('Projects export error:', error);
        exportMessage.textContent = `Ошибка: ${error.message}`;
        exportBtn.disabled = false;
        // Hide spinner on error
        const spinner = exportProgress.querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
    }
}

async function checkProjectsExportStatus() {
    if (!currentProjectsTaskId) return;
    
    try {
        const response = await fetch(`/secret_scanner/admin/export-projects-status/${currentProjectsTaskId}`);
        const data = await response.json();
        
        const exportMessage = document.getElementById('exportProjectsMessage');
        const downloadSection = document.getElementById('downloadProjectsSection');
        const exportBtn = document.getElementById('exportProjectsBtn');
        const spinner = document.getElementById('exportProjectsProgress').querySelector('.spinner');
        const checkmark = document.getElementById('exportProjectsProgress').querySelector('.checkmark');
        
        exportMessage.textContent = data.message;
        
        if (data.status === 'ready') {
            // Hide spinner and show checkmark
            if (spinner) spinner.style.display = 'none';
            if (checkmark) checkmark.style.display = 'inline-block';
            
            downloadSection.style.display = 'block';
            exportBtn.disabled = false;
            
            document.getElementById('downloadProjectsBtn').onclick = function() {
                window.location.href = `/secret_scanner/admin/download-projects/${currentProjectsTaskId}`;
                document.getElementById('exportProjectsProgress').style.display = 'none';
                currentProjectsTaskId = null;
            };
            
        } else if (data.status === 'error') {
            // Hide spinner on error
            if (spinner) spinner.style.display = 'none';
            exportBtn.disabled = false;
        } else {
            // Still processing, check again
            setTimeout(checkProjectsExportStatus, 1000);
        }
        
    } catch (error) {
        console.error('Projects status check error:', error);
        document.getElementById('exportProjectsMessage').textContent = 'Ошибка проверки статуса';
        document.getElementById('exportProjectsBtn').disabled = false;
        // Hide spinner on error
        const spinner = document.getElementById('exportProjectsProgress').querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
    }
}

// Models management functions
async function loadModelsInfo() {
    const loading = document.getElementById('modelsLoading');
    const info = document.getElementById('modelsInfo');
    const error = document.getElementById('modelsError');
    
    if (loading) loading.style.display = 'block';
    if (info) info.style.display = 'none';
    if (error) error.style.display = 'none';
    
    try {
        const response = await fetch('/secret_scanner/admin/models/info');
        
        // Проверяем Content-Type перед парсингом JSON
        const contentType = response.headers.get('content-type') || '';
        let data;
        
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else {
            // Если ответ не JSON, пытаемся прочитать как текст для диагностики
            const text = await response.text();
            throw new Error(`Сервер вернул некорректный ответ (${response.status}). Возможно, микросервис недоступен.`);
        }
        
        if (loading) loading.style.display = 'none';
        
        if (data.status === 'success' && data.data) {
            if (info) info.style.display = 'block';
            displayModelsInfo(data.data);
        } else {
            if (error) {
                error.style.display = 'block';
                const errorMsg = document.getElementById('modelsErrorMessage');
                if (errorMsg) {
                    errorMsg.textContent = data.message || data.detail || 'Ошибка получения информации о моделях';
                }
            }
        }
    } catch (err) {
        if (loading) loading.style.display = 'none';
        if (error) {
            error.style.display = 'block';
            const errorMsg = document.getElementById('modelsErrorMessage');
            if (errorMsg) {
                // Улучшенное сообщение об ошибке
                let errorText = 'Ошибка сети';
                if (err.message) {
                    errorText = err.message;
                } else if (err instanceof TypeError && err.message && err.message.includes('JSON')) {
                    errorText = 'Сервер вернул некорректный ответ. Возможно, микросервис недоступен.';
                }
                errorMsg.textContent = errorText;
            }
        }
    }
}

function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    const dropZone = document.getElementById('datasetFileDropZone');
    if (dropZone) {
        dropZone.classList.add('drag-over');
    }
}

function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();
    const dropZone = document.getElementById('datasetFileDropZone');
    if (dropZone) {
        dropZone.classList.remove('drag-over');
    }
}

function handleFileDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    const dropZone = document.getElementById('datasetFileDropZone');
    if (dropZone) {
        dropZone.classList.remove('drag-over');
    }
    
    const files = event.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        if (file.name.endsWith('.zip')) {
            const fileInput = document.getElementById('datasetFileInput');
            if (fileInput) {
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                fileInput.files = dataTransfer.files;
                updateFileDisplay(file);
            }
        } else {
            alert('Пожалуйста, выберите .zip файл');
        }
    }
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        if (file.name.endsWith('.zip')) {
            updateFileDisplay(file);
        } else {
            alert('Пожалуйста, выберите .zip файл');
            event.target.value = '';
        }
    }
}

function updateFileDisplay(file) {
    const dropZoneContent = document.getElementById('dropZoneContent');
    const dropZoneFileInfo = document.getElementById('dropZoneFileInfo');
    const dropZoneFileName = document.getElementById('dropZoneFileName');
    
    if (dropZoneContent) dropZoneContent.style.display = 'none';
    if (dropZoneFileInfo) dropZoneFileInfo.style.display = 'block';
    if (dropZoneFileName) {
        dropZoneFileName.textContent = file.name;
    }
}

function clearFileSelection(event) {
    event.stopPropagation();
    const fileInput = document.getElementById('datasetFileInput');
    const dropZoneContent = document.getElementById('dropZoneContent');
    const dropZoneFileInfo = document.getElementById('dropZoneFileInfo');
    
    if (fileInput) fileInput.value = '';
    if (dropZoneContent) dropZoneContent.style.display = 'block';
    if (dropZoneFileInfo) dropZoneFileInfo.style.display = 'none';
}

async function switchModelVersion() {
    const versionSelect = document.getElementById('switchVersionSelect');
    const btn = document.getElementById('switchVersionBtn');
    
    if (!versionSelect || !versionSelect.value) {
        alert('Пожалуйста, выберите версию модели');
        return;
    }
    
    const version = versionSelect.value;
    
    if (!confirm(`Вы уверены, что хотите сменить версию модели на ${version}?`)) {
        return;
    }
    
    if (btn) btn.disabled = true;
    
    try {
        const formData = new FormData();
        formData.append('version', version);
        
        const response = await fetch('/secret_scanner/admin/models/switch', {
            method: 'POST',
            body: formData
        });
        
        // Проверяем Content-Type перед парсингом JSON
        const contentType = response.headers.get('content-type') || '';
        let data;
        
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else {
            // Если ответ не JSON, пытаемся прочитать как текст для диагностики
            const text = await response.text();
            throw new Error(`Сервер вернул некорректный ответ (${response.status}). Возможно, микросервис недоступен.`);
        }
        
        if (btn) btn.disabled = false;
        
        if (response.ok && data.status === 'success') {
            const message = data.message || `Версия модели изменена на ${data.current_version}`;
            const fullMessage = `${message}\n\n⚠️ ВАЖНО: Необходимо вручную перезапустить воркеры на странице "Сервис" для применения новой версии модели.`;
            alert(fullMessage);
            versionSelect.value = '';
            // Reload models info to update current version
            loadModelsInfo();
        } else {
            alert(data.message || data.detail || 'Ошибка смены версии модели');
        }
    } catch (err) {
        if (btn) btn.disabled = false;
        let errorMessage = 'Ошибка сети';
        if (err.message) {
            errorMessage = err.message;
        } else if (err instanceof TypeError && err.message && err.message.includes('JSON')) {
            errorMessage = 'Сервер вернул некорректный ответ. Возможно, микросервис недоступен.';
        }
        alert(errorMessage);
    }
}

async function trainModels() {
    const loading = document.getElementById('trainModelsLoading');
    const success = document.getElementById('trainModelsSuccess');
    const error = document.getElementById('trainModelsError');
    const btn = document.getElementById('trainModelsBtn');
    
    // Hide previous messages
    if (success) success.style.display = 'none';
    if (error) error.style.display = 'none';
    if (loading) loading.style.display = 'block';
    if (btn) btn.disabled = true;
    
    try {
        const response = await fetch('/secret_scanner/admin/models/train', {
            method: 'POST'
        });
        
        // Проверяем Content-Type перед парсингом JSON
        const contentType = response.headers.get('content-type') || '';
        let data;
        
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else {
            // Если ответ не JSON, пытаемся прочитать как текст для диагностики
            const text = await response.text();
            throw new Error(`Сервер вернул некорректный ответ (${response.status}). Возможно, микросервис недоступен.`);
        }
        
        if (loading) loading.style.display = 'none';
        if (btn) btn.disabled = false;
        
        if (response.ok) {
            if (success) {
                success.style.display = 'block';
                const successMsg = document.getElementById('trainModelsSuccessMessage');
                if (successMsg) {
                    successMsg.textContent = data.message || 'Обучение завершено';
                }
                
                // Display trained versions
                const trainedEl = document.getElementById('trainModelsTrained');
                if (trainedEl && data.trained && data.trained.length > 0) {
                    trainedEl.innerHTML = `<strong>✅ Обучено:</strong> ${data.trained.join(', ')}`;
                    trainedEl.style.color = '#155724';
                } else if (trainedEl) {
                    trainedEl.innerHTML = '';
                }
                
                // Display failed versions
                const failedEl = document.getElementById('trainModelsFailed');
                if (failedEl && data.failed && data.failed.length > 0) {
                    let failedHtml = `<strong>❌ Ошибки:</strong> ${data.failed.join(', ')}`;
                    if (data.errors && data.errors.length > 0) {
                        failedHtml += '<ul style="margin-top: 0.5rem; margin-left: 1.5rem;">';
                        data.errors.forEach(err => {
                            failedHtml += `<li style="margin-top: 0.25rem;">${err}</li>`;
                        });
                        failedHtml += '</ul>';
                    }
                    failedEl.innerHTML = failedHtml;
                    failedEl.style.color = '#721c24';
                } else if (failedEl) {
                    failedEl.innerHTML = '';
                }
                
                // Update success message style based on status
                if (data.status === 'partial') {
                    success.style.background = '#fff3cd';
                    success.style.borderColor = '#ffc107';
                    success.style.color = '#856404';
                }
            }
            
            // Reload models info after a short delay
            setTimeout(() => {
                loadModelsInfo();
            }, 1000);
        } else {
            if (error) {
                error.style.display = 'block';
                const errorMsg = document.getElementById('trainModelsErrorMessage');
                if (errorMsg) {
                    errorMsg.textContent = data.detail || data.message || 'Ошибка обучения моделей';
                }
            }
        }
    } catch (err) {
        if (loading) loading.style.display = 'none';
        if (btn) btn.disabled = false;
        if (error) {
            error.style.display = 'block';
            const errorMsg = document.getElementById('trainModelsErrorMessage');
            if (errorMsg) {
                // Улучшенное сообщение об ошибке
                let errorText = 'Ошибка сети';
                if (err.message) {
                    errorText = err.message;
                } else if (err instanceof TypeError && err.message && err.message.includes('JSON')) {
                    errorText = 'Сервер вернул некорректный ответ. Возможно, микросервис недоступен.';
                }
                errorMsg.textContent = errorText;
            }
        }
    }
}

async function uploadDatasets(event) {
    event.preventDefault();
    
    const fileInput = document.getElementById('datasetFileInput');
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        const error = document.getElementById('uploadDatasetsError');
        const errorMsg = document.getElementById('uploadDatasetsErrorMessage');
        if (error) error.style.display = 'block';
        if (errorMsg) errorMsg.textContent = 'Пожалуйста, выберите ZIP файл';
        return;
    }
    
    const form = document.getElementById('uploadDatasetsForm');
    const formData = new FormData(form);
    
    const loading = document.getElementById('uploadDatasetsLoading');
    const success = document.getElementById('uploadDatasetsSuccess');
    const error = document.getElementById('uploadDatasetsError');
    const btn = document.getElementById('uploadDatasetsBtn');
    
    // Hide previous messages
    if (success) success.style.display = 'none';
    if (error) error.style.display = 'none';
    if (loading) loading.style.display = 'block';
    if (btn) btn.disabled = true;
    
    try {
        const response = await fetch('/secret_scanner/admin/models/datasets/upload', {
            method: 'POST',
            body: formData
        });
        
        // Проверяем Content-Type перед парсингом JSON
        const contentType = response.headers.get('content-type') || '';
        let data;
        
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else {
            // Если ответ не JSON, пытаемся прочитать как текст для диагностики
            const text = await response.text();
            throw new Error(`Сервер вернул некорректный ответ (${response.status}). Возможно, микросервис недоступен.`);
        }
        
        if (loading) loading.style.display = 'none';
        if (btn) btn.disabled = false;
        
        if (response.ok && data.status === 'success') {
            if (success) {
                success.style.display = 'block';
                const successMsg = document.getElementById('uploadDatasetsSuccessMessage');
                if (successMsg) {
                    successMsg.textContent = data.message || `Версия ${data.version} успешно загружена`;
                }
            }
            // Reset form
            form.reset();
            clearFileSelection({ stopPropagation: () => {} });
            // Reload models info after a short delay
            setTimeout(() => {
                loadModelsInfo();
            }, 1000);
        } else {
            if (error) {
                error.style.display = 'block';
                const errorMsg = document.getElementById('uploadDatasetsErrorMessage');
                if (errorMsg) {
                    errorMsg.textContent = data.detail || data.message || 'Ошибка загрузки датасетов';
                }
            }
        }
    } catch (err) {
        if (loading) loading.style.display = 'none';
        if (btn) btn.disabled = false;
        if (error) {
            error.style.display = 'block';
            const errorMsg = document.getElementById('uploadDatasetsErrorMessage');
            if (errorMsg) {
                errorMsg.textContent = `Ошибка сети: ${err.message}`;
            }
        }
    }
}

function displayModelsInfo(data) {
    // Display summary
    const currentVersionEl = document.getElementById('currentVersion');
    if (currentVersionEl) {
        currentVersionEl.textContent = data.current_version || 'Не установлена';
    }
    
    const modelsCountEl = document.getElementById('modelsCount');
    if (modelsCountEl && data.models) {
        modelsCountEl.textContent = data.models.length;
    }
    
    const datasetsCountEl = document.getElementById('datasetsCount');
    if (datasetsCountEl && data.datasets) {
        datasetsCountEl.textContent = data.datasets.length;
    }
    
    const missingCountEl = document.getElementById('missingModelsCount');
    const missingCountContainer = document.getElementById('missingModelsCountContainer');
    if (data.missing_models && data.missing_models.length > 0) {
        if (missingCountEl) missingCountEl.textContent = data.missing_models.length;
        if (missingCountContainer) missingCountContainer.style.display = 'block';
    } else {
        if (missingCountContainer) missingCountContainer.style.display = 'none';
    }
    
    // Populate version select for switching
    const versionSelect = document.getElementById('switchVersionSelect');
    if (versionSelect && data.models) {
        // Clear existing options except the first one
        versionSelect.innerHTML = '<option value="">Выберите версию...</option>';
        
        // Get current version
        const currentVersion = data.current_version || '';
        
        // Add model versions (only trained models with date)
        const availableVersions = data.models
            .filter(model => model.date && model.version !== currentVersion)
            .map(model => model.version)
            .sort();
        
        availableVersions.forEach(version => {
            const option = document.createElement('option');
            option.value = version;
            option.textContent = version;
            versionSelect.appendChild(option);
        });
        
        // Disable select if no versions available
        if (availableVersions.length === 0) {
            versionSelect.disabled = true;
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Нет доступных версий';
            option.disabled = true;
            versionSelect.appendChild(option);
        } else {
            versionSelect.disabled = false;
        }
    }
    
    // Create combined table
    const tableBody = document.getElementById('modelsDatasetsTableBody');
    if (tableBody) {
        tableBody.innerHTML = '';
        
        // Create a map of datasets by version
        const datasetsMap = {};
        if (data.datasets) {
            data.datasets.forEach(dataset => {
                datasetsMap[dataset.version] = dataset;
            });
        }
        
        // Create a map of models by version
        const modelsMap = {};
        if (data.models) {
            data.models.forEach(model => {
                modelsMap[model.version] = model;
            });
        }
        
        // Get all versions (from datasets and models)
        const allVersions = new Set();
        if (data.datasets) data.datasets.forEach(d => allVersions.add(d.version));
        if (data.models) data.models.forEach(m => allVersions.add(m.version));
        
        // Sort versions
        const sortedVersions = Array.from(allVersions).sort();
        
        // Create table rows
        sortedVersions.forEach(version => {
            const dataset = datasetsMap[version];
            const model = modelsMap[version];
            const isCurrent = data.current_version === version;
            
            const row = document.createElement('tr');
            if (isCurrent) {
                row.style.backgroundColor = '#e8f5e8';
            }
            
            // Version
            let versionCell = `<td style="font-weight: 600; vertical-align: middle; white-space: nowrap;">${version}`;
            if (isCurrent) {
                versionCell += ' <span style="background: #28a745; color: white; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem; display: inline-block; vertical-align: middle;">Текущая</span>';
            }
            versionCell += '</td>';
            
            // Type
            let typeCell = '<td style="vertical-align: middle;">';
            if (dataset && model) {
                typeCell += '<div style="line-height: 1.4;">📦 Модель<br><span style="font-size: 0.85rem; color: #666;">📊 Датасет</span></div>';
            } else if (model) {
                typeCell += '📦 Модель';
            } else if (dataset) {
                typeCell += '📊 Датасет';
            }
            typeCell += '</td>';
            
            // Status
            let statusCell = '<td style="vertical-align: middle;">';
            if (model) {
                if (model.date) {
                    statusCell += '<span style="background: #28a745; color: white; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; display: inline-block; white-space: nowrap;">✅ Обучена</span>';
                } else if (model.status) {
                    statusCell += `<span style="background: #ffc107; color: #333; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; display: inline-block; white-space: nowrap;">⚠️ ${model.status}</span>`;
                } else if (model.error) {
                    statusCell += `<span style="background: #dc3545; color: white; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; display: inline-block; white-space: nowrap;">❌ Ошибка</span>`;
                } else if (model.note) {
                    statusCell += `<span style="background: #ffc107; color: #333; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; display: inline-block; white-space: nowrap;">⚠️ ${model.note}</span>`;
                }
            } else {
                statusCell += '<span style="color: #666; font-size: 0.85rem;">Нет модели</span>';
            }
            statusCell += '</td>';
            
            // Date
            let dateCell = '<td style="font-size: 0.85rem; color: #666; vertical-align: middle;">';
            if (model && model.date) {
                const date = new Date(model.date);
                dateCell += date.toLocaleDateString('ru-RU');
            } else {
                dateCell += '-';
            }
            dateCell += '</td>';
            
            // Description
            let descCell = '<td style="font-size: 0.85rem; color: #666; max-width: 300px; vertical-align: middle;">';
            if (model && model.description) {
                descCell += model.description.substring(0, 100) + (model.description.length > 100 ? '...' : '');
            } else if (dataset && dataset.description) {
                descCell += dataset.description.substring(0, 100) + (dataset.description.length > 100 ? '...' : '');
            } else {
                descCell += '-';
            }
            descCell += '</td>';
            
            // Sizes
            let sizesCell = '<td style="font-size: 0.85rem; vertical-align: middle;">';
            if (model && model.SecretsSize !== undefined && model.NonSecretsSize !== undefined) {
                sizesCell += `<span style="color: #dc3545;">${model.SecretsSize.toLocaleString()}</span> / <span style="color: #28a745;">${model.NonSecretsSize.toLocaleString()}</span>`;
            } else {
                sizesCell += '-';
            }
            sizesCell += '</td>';
            
            // Files
            let filesCell = '<td style="font-size: 0.8rem; vertical-align: middle;">';
            if (dataset) {
                const files = [];
                if (dataset.has_secrets_file) files.push('Secrets');
                if (dataset.has_non_secrets_file) files.push('NonSecrets');
                if (dataset.has_zip) files.push('ZIP');
                filesCell += files.map(f => `<span style="background: #e9ecef; padding: 0.15rem 0.4rem; border-radius: 3px; margin-right: 0.25rem; display: inline-block;">${f}</span>`).join('');
            } else {
                filesCell += '-';
            }
            filesCell += '</td>';
            
            row.innerHTML = versionCell + typeCell + statusCell + dateCell + descCell + sizesCell + filesCell;
            tableBody.appendChild(row);
        });
        
        if (sortedVersions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #666; padding: 2rem;">Нет данных</td></tr>';
        }
    }
    
    // Display missing models
    const missingModelsSection = document.getElementById('missingModelsSection');
    const missingModelsList = document.getElementById('missingModelsList');
    if (data.missing_models && data.missing_models.length > 0) {
        if (missingModelsSection) missingModelsSection.style.display = 'block';
        if (missingModelsList) {
            missingModelsList.innerHTML = data.missing_models.map(version => 
                `<span style="background: white; padding: 0.35rem 0.75rem; border-radius: 4px; border: 1px solid #ffc107; font-size: 0.85rem;">${version}</span>`
            ).join('');
        }
    } else {
        if (missingModelsSection) missingModelsSection.style.display = 'none';
    }
}

// Load models info when scanning tab is opened on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load models info when page loads if we're on scanning tab
    const scanningTab = document.getElementById('tab-scanning');
    if (scanningTab && scanningTab.classList.contains('active')) {
        loadModelsInfo();
    }
});