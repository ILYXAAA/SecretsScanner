function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });

    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');
    localStorage.setItem('activeTab', tabName);
}

function toggleAddForm() {
    const form = document.getElementById('addProjectForm');
    form.classList.toggle('show');

    const isVisible = form.classList.contains('show');
    localStorage.setItem('addFormVisible', isVisible);

    if (isVisible) {
        blockAutoRefresh = true;
        console.log('Auto-refresh blocked: project form opened');
    } else {
        blockAutoRefresh = false;
        console.log('Auto-refresh unblocked: project form closed');
    }
}

let blockAutoRefresh = false;
let searchDebounceTimer = null;
let searchFetchController = null;

async function loadProjectsResults(search, page) {
    const resultsEl = document.getElementById('projects-results');
    if (!resultsEl) return;

    const url = new URL('/secret_scanner/dashboard', window.location.origin);
    if (search) {
        url.searchParams.set('search', search);
    }
    url.searchParams.set('page', String(page || 1));

    if (searchFetchController) {
        searchFetchController.abort();
    }
    searchFetchController = new AbortController();

    blockAutoRefresh = true;
    resultsEl.classList.add('is-updating');

    try {
        const response = await fetch(url.toString(), {
            signal: searchFetchController.signal,
            credentials: 'same-origin',
        });

        if (!response.ok) {
            throw new Error(`Search request failed: ${response.status}`);
        }

        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const newResults = doc.getElementById('projects-results');

        if (newResults) {
            resultsEl.innerHTML = newResults.innerHTML;
        }

        const nextUrl = url.pathname + url.search;
        if (window.location.pathname + window.location.search !== nextUrl) {
            history.replaceState(null, '', nextUrl);
        }
    } catch (error) {
        if (error.name !== 'AbortError') {
            console.error('Error loading projects:', error);
        }
    } finally {
        resultsEl.classList.remove('is-updating');
        blockAutoRefresh = false;
        searchFetchController = null;
    }
}

function initProjectSearch() {
    const searchInput = document.querySelector('input[name="search"]');
    const searchForm = document.getElementById('projectSearchForm');
    const resultsEl = document.getElementById('projects-results');

    if (!searchInput || !searchForm || !resultsEl) {
        return;
    }

    searchForm.addEventListener('submit', function(event) {
        event.preventDefault();
        loadProjectsResults(searchInput.value.trim(), 1);
    });

    searchInput.addEventListener('input', function() {
        const projectsTab = document.getElementById('projects');
        if (!projectsTab || !projectsTab.classList.contains('active')) {
            return;
        }

        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            loadProjectsResults(searchInput.value.trim(), 1);
        }, 350);
    });

    searchInput.addEventListener('focus', () => {
        blockAutoRefresh = true;
    });

    searchInput.addEventListener('blur', () => {
        const addForm = document.getElementById('addProjectForm');
        if (!resultsEl.classList.contains('is-updating') && !addForm?.classList.contains('show')) {
            blockAutoRefresh = false;
        }
    });

    resultsEl.addEventListener('click', function(event) {
        const link = event.target.closest('.pagination a[href]');
        if (!link || link.classList.contains('current')) {
            return;
        }

        event.preventDefault();
        const linkUrl = new URL(link.href, window.location.origin);
        const page = parseInt(linkUrl.searchParams.get('page') || '1', 10);
        const search = linkUrl.searchParams.get('search') || searchInput.value.trim();
        loadProjectsResults(search, page);
    });

    if (window.location.search.includes('search=')) {
        setTimeout(() => {
            searchInput.focus();
            searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
        }, 100);
    }
}

initProjectSearch();

function initSelectableProjectLinks() {
    const resultsEl = document.getElementById('projects-results');
    if (!resultsEl) {
        return;
    }

    let pointerDown = null;

    resultsEl.addEventListener('mousedown', function(event) {
        const link = event.target.closest('.scans-project-name--selectable');
        pointerDown = link
            ? { link: link, x: event.clientX, y: event.clientY }
            : null;
    });

    resultsEl.addEventListener('click', function(event) {
        const link = event.target.closest('.scans-project-name--selectable');
        if (!link) {
            return;
        }

        const selection = window.getSelection();
        if (selection && selection.toString().length > 0) {
            event.preventDefault();
            return;
        }

        if (pointerDown && pointerDown.link === link) {
            const moved = Math.abs(event.clientX - pointerDown.x) > 3
                || Math.abs(event.clientY - pointerDown.y) > 3;
            if (moved) {
                event.preventDefault();
            }
        }
    });
}

initSelectableProjectLinks();

const urlParams = new URLSearchParams(window.location.search);
const savedTab = localStorage.getItem('activeTab');

if (urlParams.has('search') && urlParams.get('search').trim() !== '') {
    switchTabSilent('projects');
} else if (savedTab) {
    switchTabSilent(savedTab);
}

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
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });

    document.getElementById(tabName).classList.add('active');

    const tabs = document.querySelectorAll('.tab');
    if (tabName === 'projects') {
        tabs[1].classList.add('active');
    } else {
        tabs[0].classList.add('active');
    }
}

const runningScans = document.querySelectorAll('.scan-status.running, .scan-status.pending');
if (runningScans.length > 0) {
    setTimeout(() => {
        if (!blockAutoRefresh) {
            console.log('Auto-refreshing page...');
            window.location.reload();
        } else {
            console.log('Auto-refresh skipped: blocked by user interaction');
            setTimeout(() => {
                if (!blockAutoRefresh) {
                    window.location.reload();
                }
            }, 10000);
        }
    }, 10000);
}

const projectForm = document.getElementById('addProjectForm');
if (projectForm) {
    const formInputs = projectForm.querySelectorAll('input, textarea');
    formInputs.forEach(input => {
        input.addEventListener('focus', () => {
            blockAutoRefresh = true;
            console.log('Auto-refresh blocked: user focused on form input');
        });

        input.addEventListener('blur', () => {
            if (!projectForm.classList.contains('show')) {
                blockAutoRefresh = false;
                console.log('Auto-refresh unblocked: user left form input and form is closed');
            }
        });
    });

    const form = projectForm.querySelector('form');
    if (form) {
        form.addEventListener('submit', () => {
            localStorage.removeItem('addFormVisible');
            blockAutoRefresh = false;
        });
    }
}
