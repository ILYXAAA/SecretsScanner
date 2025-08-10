function switchTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    document.getElementById(tabName).classList.add('active');
    
    // Add active class to clicked tab
    event.target.classList.add('active');
    
    // Save active tab to localStorage
    localStorage.setItem('activeTab', tabName);
}

function toggleAddForm() {
    const form = document.getElementById('addProjectForm');
    form.classList.toggle('show');
    
    // Сохраняем состояние формы в localStorage
    const isVisible = form.classList.contains('show');
    localStorage.setItem('addFormVisible', isVisible);
    
    // Если форма открывается, блокируем автообновление
    if (isVisible) {
        blockAutoRefresh = true;
        console.log('Auto-refresh blocked: project form opened');
    } else {
        blockAutoRefresh = false;
        console.log('Auto-refresh unblocked: project form closed');
    }
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
            location.reload();
        } else {
            alert('Failed to delete project.');
        }
    })
    .catch(error => {
        console.error('Error deleting project:', error);
        alert('Something went wrong.');
    });
}

// Auto-submit search form on input (only on projects tab)
const searchInput = document.querySelector('input[name="search"]');
if (searchInput) {
    searchInput.addEventListener('input', function() {
        // Check if projects tab is active
        const projectsTab = document.getElementById('projects');
        if (projectsTab && projectsTab.classList.contains('active')) {
            // Only submit if there's actual content or if clearing a previous search
            const currentValue = this.value.trim();
            const urlParams = new URLSearchParams(window.location.search);
            const hasExistingSearch = urlParams.has('search') && urlParams.get('search').trim() !== '';
            
            if (currentValue !== '' || hasExistingSearch) {
                setTimeout(() => {
                    this.closest('form').submit();
                }, 500);
            }
        }
    });
    
    // Focus search input after page load if on projects tab and has search
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('search')) {
        setTimeout(() => {
            searchInput.focus();
            // Set cursor to end of text
            searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
        }, 100);
    }
}

// Remember active tab after page reload
const urlParams = new URLSearchParams(window.location.search);
const savedTab = localStorage.getItem('activeTab');

if (urlParams.has('search') && urlParams.get('search').trim() !== '') {
    // If there's a search parameter, show projects tab
    switchTabSilent('projects');
} else if (savedTab) {
    // Restore saved tab
    switchTabSilent(savedTab);
}

// Восстанавливаем состояние формы добавления проекта
const addFormVisible = localStorage.getItem('addFormVisible');
if (addFormVisible === 'true') {
    const form = document.getElementById('addProjectForm');
    if (form) {
        form.classList.add('show');
        blockAutoRefresh = true;
        console.log('Auto-refresh blocked: project form restored as open');
    }
}

function switchTabSilent(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    document.getElementById(tabName).classList.add('active');
    
    // Add active class to corresponding tab button
    const tabs = document.querySelectorAll('.tab');
    if (tabName === 'projects') {
        tabs[1].classList.add('active');
    } else {
        tabs[0].classList.add('active');
    }
}

let blockAutoRefresh = false;


// Auto-refresh if there are running scans
const runningScans = document.querySelectorAll('.scan-status.running');
if (runningScans.length > 0) {
    setTimeout(() => {
        if (!blockAutoRefresh) {
            console.log('Auto-refreshing page...');
            window.location.reload();
        } else {
            console.log('Auto-refresh skipped: blocked by user interaction');
            // Повторная проверка через 10 секунд
            setTimeout(() => {
                if (!blockAutoRefresh) {
                    window.location.reload();
                }
            }, 10000);
        }
    }, 10000); // Refresh every 10 seconds
}

const projectForm = document.getElementById('addProjectForm');
if (projectForm) {
    // Блокируем автообновление при фокусе на полях формы
    const formInputs = projectForm.querySelectorAll('input, textarea');
    formInputs.forEach(input => {
        input.addEventListener('focus', () => {
            blockAutoRefresh = true;
            console.log('Auto-refresh blocked: user focused on form input');
        });
        
        input.addEventListener('blur', () => {
            // Разблокируем только если форма закрыта
            if (!projectForm.classList.contains('show')) {
                blockAutoRefresh = false;
                console.log('Auto-refresh unblocked: user left form input and form is closed');
            }
        });
    });
    
    // Обработчик отправки формы
    const form = projectForm.querySelector('form');
    if (form) {
        form.addEventListener('submit', () => {
            // Очищаем состояние формы при отправке
            localStorage.removeItem('addFormVisible');
            blockAutoRefresh = false;
        });
    }
}