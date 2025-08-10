// Получаем оригинальный контент из data-атрибутов
function loadOriginalContent() {
    return {
        rules: document.body.dataset.originalRules || '',
        fp_rules: document.body.dataset.originalFpRules || '',
        extensions: document.body.dataset.originalExtensions || '',
        files: document.body.dataset.originalFiles || ''
    };
}

// Получаем информацию о SQLite из data-атрибута
function getIsSqlite() {
    try {
        return JSON.parse(document.body.dataset.isSqlite || 'false');
    } catch (e) {
        return false;
    }
}

let originalContent = {};
let isSqlite = false;

// Tab switching functionality
document.addEventListener('DOMContentLoaded', function() {
    // Загружаем данные из data-атрибутов
    originalContent = loadOriginalContent();
    isSqlite = getIsSqlite();
    
    const tabs = document.querySelectorAll('.config-tab');
    const contents = document.querySelectorAll('.config-content');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', function(e) {
            e.preventDefault(); // Предотвращаем скролл
            const targetTab = this.dataset.tab;
            
            // Remove active class from all tabs and contents
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            // Add active class to clicked tab and corresponding content
            this.classList.add('active');
            document.getElementById(targetTab + '-content').classList.add('active');
        });
    });
    
    // Load backups on page load
    loadBackups();
    
    // Initialize unsaved changes tracking
    initializeChangeTracking();
});

document.getElementById('passwordChangeForm')?.addEventListener('submit', function(e) {
    const newPassword = document.getElementById('new_password').value;
    const confirmPassword = document.getElementById('confirm_password').value;
    const btn = document.getElementById('changePasswordBtn');
    
    if (newPassword !== confirmPassword) {
        e.preventDefault();
        alert('Новые пароли не совпадают');
        return false;
    }
    
    if (newPassword.length < 8) {
        e.preventDefault();
        alert('Пароль должен содержать минимум 8 символов');
        return false;
    }
    
    // Show loading state
    btn.disabled = true;
    btn.innerHTML = '⏳ Изменение пароля...';
    
    // Re-enable button after timeout
    setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = '🔐 Изменить пароль';
    }, 30000);
});

const apiKeyInput = document.getElementById('api_key');
if (apiKeyInput) {
    apiKeyInput.addEventListener('focus', () => {
        apiKeyInput.type = 'text';
    });
    apiKeyInput.addEventListener('blur', () => {
        apiKeyInput.type = 'password';
    });
}

// Show/hide password for token input (уже существует, но для ясности)
const tokenInput = document.getElementById('token');
if (tokenInput) {
    tokenInput.addEventListener('focus', () => {
        tokenInput.type = 'text';
    });
    tokenInput.addEventListener('blur', () => {
        tokenInput.type = 'password';
    });
}

// Change tracking for unsaved indicators
function initializeChangeTracking() {
    const textareas = [
        { element: 'rules_content', type: 'rules', indicator: 'rules-unsaved' },
        { element: 'fp_rules_content', type: 'fp_rules', indicator: 'fp-rules-unsaved' },
        { element: 'excluded_extensions_content', type: 'extensions', indicator: 'extensions-unsaved' },
        { element: 'excluded_files_content', type: 'files', indicator: 'files-unsaved' }
    ];
    
    textareas.forEach(({ element, type, indicator }) => {
        const textarea = document.getElementById(element);
        const indicatorEl = document.getElementById(indicator);
        
        if (textarea && indicatorEl) {
            textarea.addEventListener('input', function() {
                const hasChanges = this.value !== originalContent[type];
                indicatorEl.style.display = hasChanges ? 'inline-block' : 'none';
            });
        }
    });
}

// Backup Management Functions
async function loadBackups() {
    if (!isSqlite) return;
    
    const backupList = document.getElementById('backup-list');
    
    // Show loading state
    backupList.innerHTML = `
        <div style="padding: 2rem; text-align: center; color: #666;">
            <div class="spinner"></div>
            Загрузка бэкапов...
        </div>
    `;
    
    try {
        // Add timestamp to prevent caching
        const timestamp = new Date().getTime();
        const response = await fetch(`/secret_scanner/admin/backup-status?t=${timestamp}`, {
            method: 'GET',
            headers: {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            updateBackupDisplay(data);
        } else {
            showBackupError(data.message || 'Failed to load backups');
        }
    } catch (error) {
        console.error('Backup loading error:', error);
        showBackupError('Network error: ' + error.message);
    }
}

function updateBackupDisplay(data) {
    // Update stats with total count
    document.getElementById('backup-count').textContent = data.total_backups || data.backups.length;
    
    // Update backup list
    const backupList = document.getElementById('backup-list');
    
    if (data.backups.length === 0) {
        backupList.innerHTML = `
            <div style="padding: 2rem; text-align: center; color: #666;">
                📂 No backups found
            </div>
        `;
        return;
    }
    
    let listHtml = data.backups.map(backup => `
        <div class="backup-item">
            <div>
                <div class="backup-filename">${backup.filename}</div>
                <div class="backup-info">Created: ${backup.created}</div>
            </div>
            <div class="backup-info">
                ${backup.size_mb} MB
            </div>
        </div>
    `).join('');
    
    // Add note if showing limited results
    if (data.total_backups > data.backups.length) {
        listHtml += `
            <div style="padding: 1rem; text-align: center; color: #666; font-style: italic; border-top: 1px solid #e1e5e9;">
                Showing latest ${data.backups.length} of ${data.total_backups} backups
            </div>
        `;
    }
    
    backupList.innerHTML = listHtml;
}

function showBackupError(message) {
    const backupList = document.getElementById('backup-list');
    backupList.innerHTML = `
        <div style="padding: 2rem; text-align: center; color: #dc3545;">
            ❌ ${message}
        </div>
    `;
}

async function createBackup() {
    if (!isSqlite) return;
    
    const btn = document.getElementById('createBackupBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Creating backup...';
    
    try {
        const response = await fetch('/secret_scanner/admin/backup', { method: 'POST' });
        const data = await response.json();
        
        if (data.status === 'success') {
            // Refresh the backup list
            await loadBackups();
            
            // Show success message
            showNotification('✅ Backup created successfully!', 'success');
        } else {
            showNotification('❌ Failed to create backup: ' + (data.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('❌ Network error: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function refreshBackups() {
    if (!isSqlite) return;
    
    const btn = document.getElementById('refreshBtn');
    const originalText = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Refreshing...';
    
    try {
        await loadBackups();
        showNotification('✅ Backup list refreshed', 'success');
    } catch (error) {
        showNotification('❌ Failed to refresh: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'error'}`;
    notification.textContent = message;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '1000';
    notification.style.maxWidth = '400px';
    
    document.body.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

// Form submission handling for all forms
const forms = [
    { form: 'rulesForm', btn: 'updateRulesBtn', content: 'rules_content', indicator: 'rules-unsaved' },
    { form: 'fpRulesForm', btn: 'updateFpRulesBtn', content: 'fp_rules_content', indicator: 'fp-rules-unsaved' },
    { form: 'excludedExtensionsForm', btn: 'updateExtensionsBtn', content: 'excluded_extensions_content', indicator: 'extensions-unsaved' },
    { form: 'excludedFilesForm', btn: 'updateFilesBtn', content: 'excluded_files_content', indicator: 'files-unsaved' }
];

forms.forEach(({ form, btn, content, indicator }) => {
    const formElement = document.getElementById(form);
    const updateBtn = document.getElementById(btn);
    const contentElement = document.getElementById(content);
    const indicatorElement = document.getElementById(indicator);
    
    if (formElement && updateBtn && contentElement) {
        formElement.addEventListener('submit', function(e) {
            const contentValue = contentElement.value.trim();
            if (!contentValue) {
                e.preventDefault();
                alert('Configuration content cannot be empty');
                return false;
            }
            
            // Show loading state
            updateBtn.disabled = true;
            updateBtn.innerHTML = '⏳ Updating...';
            
            // Hide unsaved indicator since we're saving
            if (indicatorElement) {
                indicatorElement.style.display = 'none';
            }
            
            // Re-enable button after some time in case of error
            setTimeout(() => {
                updateBtn.disabled = false;
                updateBtn.innerHTML = updateBtn.innerHTML.replace('⏳ Updating...', '💾 Update');
            }, 30000);
        });
    }
});

function resetContent(type) {
    const contentMap = {
        'rules': 'rules_content',
        'fp_rules': 'fp_rules_content',
        'extensions': 'excluded_extensions_content',
        'files': 'excluded_files_content'
    };
    
    const indicatorMap = {
        'rules': 'rules-unsaved',
        'fp_rules': 'fp-rules-unsaved',
        'extensions': 'extensions-unsaved',
        'files': 'files-unsaved'
    };
    
    const elementId = contentMap[type];
    const indicatorId = indicatorMap[type];
    const element = document.getElementById(elementId);
    const indicator = document.getElementById(indicatorId);
    
    if (element && confirm('Are you sure you want to reset to the current saved content? Any unsaved changes will be lost.')) {
        element.value = originalContent[type];
        if (indicator) {
            indicator.style.display = 'none';
        }
    }
}

// Add syntax highlighting effect for all textareas
document.querySelectorAll('.config-textarea').forEach(textarea => {
    textarea.addEventListener('input', function() {
        this.style.backgroundColor = this.value.trim() ? '#f8f9fa' : '#fff3cd';
    });
});

// Auto-save warning
let hasUnsavedChanges = false;
document.querySelectorAll('.config-textarea').forEach((textarea, index) => {
    const type = ['rules', 'fp_rules', 'extensions', 'files'][index];
    textarea.addEventListener('input', function() {
        const hasChanges = (this.value !== originalContent[type]);
        if (hasChanges && !hasUnsavedChanges) {
            hasUnsavedChanges = true;
        } else if (!hasChanges) {
            // Check if any other textarea has changes
            hasUnsavedChanges = document.querySelectorAll('.config-textarea').some((ta, i) => {
                const t = ['rules', 'fp_rules', 'extensions', 'files'][i];
                return ta.value !== originalContent[t];
            });
        }
    });
});

window.addEventListener('beforeunload', function(e) {
    if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        return e.returnValue;
    }
});

// Mark as saved when any form is submitted
forms.forEach(({ form }) => {
    const formElement = document.getElementById(form);
    if (formElement) {
        formElement.addEventListener('submit', function() {
            hasUnsavedChanges = false;
        });
    }
});