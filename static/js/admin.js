let currentPage = 1;
let totalPages = 1;

// Load users on page load
document.addEventListener('DOMContentLoaded', function() {
    loadUsers();
});

async function loadUsers(page = 1) {
    const loading = document.getElementById('usersLoading');
    const table = document.getElementById('usersTable');
    const tbody = document.getElementById('usersTableBody');
    const pagination = document.getElementById('pagination');
    
    loading.style.display = 'block';
    table.style.display = 'none';
    pagination.style.display = 'none';
    
    try {
        const response = await fetch(`/secret_scanner/admin/users?page=${page}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            tbody.innerHTML = '';
            
            if (data.users.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-state">
                            <div>Пользователи не найдены</div>
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
        loadUsers(newPage);
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
            loadUsers(); // Reload users list
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