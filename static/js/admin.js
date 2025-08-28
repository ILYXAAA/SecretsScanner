let currentPage = 1;
let totalPages = 1;
let currentTokensPage = 1;
let totalTokensPages = 1;
let currentUserSearch = '';
let currentTokenSearch = '';

// Load users on page load
// Load API tokens on page load
document.addEventListener('DOMContentLoaded', function() {
    loadUsers();
    loadApiTokens();
    
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