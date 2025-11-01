// Stats Dashboard JavaScript with Professional Canvas Charts

// Global state
let currentTrendsPeriod = 30;

// Utility: Format numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Show/Hide loading overlay
function showLoading() {
    document.getElementById('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

// Fetch KPI data
async function loadKPIData() {
    try {
        const response = await fetch('/secret_scanner/api/stats/kpi');
        const data = await response.json();

        document.getElementById('kpiActiveConfirmed').textContent = formatNumber(data.active_confirmed);
        document.getElementById('kpiNew24h').textContent = formatNumber(data.new_24h);
        document.getElementById('kpiNew7d').textContent = formatNumber(data.new_7d);
        document.getElementById('kpiNoStatus').textContent = formatNumber(data.no_status_count);
    } catch (error) {
        console.error('Error loading KPI data:', error);
    }
}

// Fetch and render trends chart
async function loadTrendsData(days = 30) {
    try {
        const response = await fetch(`/secret_scanner/api/stats/trends?days=${days}`);
        const data = await response.json();

        renderTrendsChart(data.data);
    } catch (error) {
        console.error('Error loading trends data:', error);
    }
}

// Render professional line chart
function renderTrendsChart(data) {
    const canvas = document.getElementById('trendsChart');
    if (!canvas) return;
    
    // Get actual container size
    const containerWidth = canvas.offsetWidth;
    const containerHeight = canvas.offsetHeight;
    
    // Wait for canvas to be visible if it's in a hidden tab
    if (containerWidth === 0 || containerHeight === 0) {
        // Canvas is hidden, retry after a short delay
        setTimeout(() => renderTrendsChart(data), 100);
        return;
    }
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    // Set canvas size accounting for device pixel ratio
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    
    // Scale context to account for device pixel ratio
    ctx.scale(dpr, dpr);
    
    const width = containerWidth;
    const height = containerHeight;
    
    // Dynamic padding based on canvas size - use more space
    const padding = {
        top: Math.max(15, height * 0.03),
        right: Math.max(10, width * 0.01),
        bottom: Math.max(40, height * 0.08),
        left: Math.max(50, width * 0.08)
    };

    ctx.clearRect(0, 0, width, height);

    if (!data || data.length === 0) {
        ctx.fillStyle = '#a0aec0';
        ctx.font = '14px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных за выбранный период', width / 2, height / 2);
        return;
    }

    const dates = data.map(d => d.date);
    const highValues = data.map(d => d.high);
    const potentialValues = data.map(d => d.potential);

    const maxValue = Math.max(...highValues, ...potentialValues, 10);
    const xScale = (width - padding.left - padding.right) / Math.max(dates.length - 1, 1);
    const yScale = (height - padding.top - padding.bottom) / maxValue;

    // Draw grid
    ctx.strokeStyle = '#edf2f7';
    ctx.lineWidth = 1;

    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
        const y = height - padding.bottom - (i * (height - padding.top - padding.bottom) / ySteps);
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        // Y-axis labels
        ctx.fillStyle = '#718096';
        ctx.font = 'bold 13px -apple-system, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        const value = Math.round((maxValue * i) / ySteps);
        ctx.fillText(value.toString(), padding.left - 10, y);
    }

    // Axes
    ctx.strokeStyle = '#cbd5e0';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    ctx.lineTo(width - padding.right, height - padding.bottom);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, height - padding.bottom);
    ctx.stroke();

    // X-axis labels
    const labelStep = Math.max(1, Math.ceil(dates.length / 15));
    ctx.fillStyle = '#718096';
    ctx.font = 'bold 12px -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    dates.forEach((date, i) => {
        if (i % labelStep === 0 || i === dates.length - 1) {
            const x = padding.left + (i * xScale);
            const dateObj = new Date(date);
            const label = `${dateObj.getDate()}.${dateObj.getMonth() + 1}`;

            ctx.save();
            ctx.translate(x, height - padding.bottom + 5);
            ctx.rotate(-0.4);
            ctx.fillText(label, 0, 0);
            ctx.restore();
        }
    });

    // Draw High line with area fill
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#f56565';
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    highValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + ((highValues.length - 1) * xScale), height - padding.bottom);
    ctx.closePath();
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.strokeStyle = '#e53e3e';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    highValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw High points
    highValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.beginPath();
        ctx.fillStyle = '#fff';
        ctx.strokeStyle = '#e53e3e';
        ctx.lineWidth = 2.5;
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
    });

    // Draw Potential line with area fill
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#ed8936';
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    potentialValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + ((potentialValues.length - 1) * xScale), height - padding.bottom);
    ctx.closePath();
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.strokeStyle = '#dd6b20';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    potentialValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Draw Potential points
    potentialValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.beginPath();
        ctx.fillStyle = '#fff';
        ctx.strokeStyle = '#dd6b20';
        ctx.lineWidth = 2.5;
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
    });
}

// Fetch and render top projects
async function loadTopProjects() {
    try {
        const response = await fetch('/secret_scanner/api/stats/top-projects?limit=5');
        const data = await response.json();

        const tbody = document.getElementById('topProjectsBody');
        tbody.innerHTML = '';

        if (data.top_projects.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="loading-cell">Нет данных</td></tr>';
            return;
        }

        data.top_projects.forEach((project, index) => {
            const row = document.createElement('tr');
            const projectLink = `/secret_scanner/project/${encodeURIComponent(project.project_name)}`;
            row.innerHTML = `
                <td>${index + 1}</td>
                <td><a href="${projectLink}">${escapeHtml(project.project_name)}</a></td>
                <td>${formatNumber(project.secret_count)}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Error loading top projects:', error);
    }
}

// Fetch and render secret types donut chart
let lastSecretTypesData = null;

async function loadSecretTypes() {
    try {
        const response = await fetch('/secret_scanner/api/stats/secret-types?limit=10');
        const data = await response.json();
        
        lastSecretTypesData = data.secret_types;
        renderDonutChart(data.secret_types);
    } catch (error) {
        console.error('Error loading secret types:', error);
    }
}

// Render professional donut chart
function renderDonutChart(data) {
    const canvas = document.getElementById('secretTypesChart');
    if (!canvas) return;
    
    // Wait for canvas to be visible if it's in a hidden tab
    const containerWidth = canvas.offsetWidth;
    const containerHeight = canvas.offsetHeight;
    
    if (containerWidth === 0 || containerHeight === 0) {
        // Canvas is hidden, retry after a short delay with same data
        setTimeout(() => {
            if (data) {
                renderDonutChart(data);
            } else if (lastSecretTypesData) {
                renderDonutChart(lastSecretTypesData);
            }
        }, 100);
        return;
    }
    
    // Use provided data or fallback to last loaded data
    const chartData = data || lastSecretTypesData;
    if (!chartData) {
        console.warn('No data available for secret types chart');
        return;
    }
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    // Set canvas size accounting for device pixel ratio
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    
    // Scale context to account for device pixel ratio
    ctx.scale(dpr, dpr);
    
    const width = containerWidth;
    const height = containerHeight;
    const centerX = width / 2;
    const centerY = height / 2;
    
    // Use maximum space - minimal margin
    const maxRadius = Math.min(width, height) / 2;
    const radius = maxRadius * 0.95;
    const innerRadius = radius * 0.55;

    ctx.clearRect(0, 0, width, height);

    if (!chartData || chartData.length === 0) {
        ctx.fillStyle = '#a0aec0';
        ctx.font = '14px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных', centerX, centerY);
        return;
    }

    const colors = [
        '#e53e3e', '#dd6b20', '#d69e2e', '#38a169', '#319795',
        '#3182ce', '#5a67d8', '#805ad5', '#d53f8c', '#718096'
    ];

    const total = chartData.reduce((sum, item) => sum + item.count, 0);
    let currentAngle = -Math.PI / 2;

    // Draw segments
    chartData.forEach((item, index) => {
        const sliceAngle = (item.count / total) * Math.PI * 2;

        ctx.beginPath();
        ctx.fillStyle = colors[index % colors.length];
        ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + sliceAngle);
        ctx.arc(centerX, centerY, innerRadius, currentAngle + sliceAngle, currentAngle, true);
        ctx.closePath();
        ctx.fill();

        // Subtle stroke
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

        currentAngle += sliceAngle;
    });

    // Center text - scale with chart size
    const fontSize = Math.max(32, Math.min(width, height) * 0.08);
    const labelSize = Math.max(14, Math.min(width, height) * 0.035);
    
    ctx.fillStyle = '#2d3748';
    ctx.font = `bold ${fontSize}px -apple-system, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total.toString(), centerX, centerY - labelSize * 0.6);

    ctx.font = `${labelSize}px -apple-system, sans-serif`;
    ctx.fillStyle = '#718096';
    ctx.fillText('секретов', centerX, centerY + fontSize * 0.4);

    // Legend
    const legendContainer = document.getElementById('secretTypesLegend');
    legendContainer.innerHTML = '';

    chartData.forEach((item, index) => {
        const legendItem = document.createElement('div');
        legendItem.className = 'legend-item';
        legendItem.innerHTML = `
            <span class="legend-color" style="background: ${colors[index % colors.length]}"></span>
            <span class="legend-label">${escapeHtml(item.type)} (${item.percentage}%)</span>
        `;
        legendContainer.appendChild(legendItem);
    });
}

// Fetch and render status distribution
async function loadStatusDistribution() {
    try {
        const response = await fetch('/secret_scanner/api/stats/status-distribution');
        const data = await response.json();

        document.getElementById('confirmedCount').textContent = formatNumber(data.confirmed);
        document.getElementById('confirmedPct').textContent = data.confirmed_pct;
        document.getElementById('refutedCount').textContent = formatNumber(data.refuted);
        document.getElementById('refutedPct').textContent = data.refuted_pct;
        document.getElementById('noStatusCount').textContent = formatNumber(data.no_status);
        document.getElementById('noStatusPct').textContent = data.no_status_pct;
        document.getElementById('fpRate').textContent = data.fp_rate;

        renderPieChart(data);
    } catch (error) {
        console.error('Error loading status distribution:', error);
    }
}

// Render professional pie chart
function renderPieChart(data) {
    const canvas = document.getElementById('statusChart');
    if (!canvas) return;
    
    // Get actual container size
    const containerWidth = canvas.offsetWidth;
    const containerHeight = canvas.offsetHeight;
    
    // Wait for canvas to be visible if it's in a hidden tab
    if (containerWidth === 0 || containerHeight === 0) {
        // Canvas is hidden, retry after a short delay
        setTimeout(() => renderPieChart(data), 100);
        return;
    }
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    // Set canvas size accounting for device pixel ratio
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    
    // Scale context to account for device pixel ratio
    ctx.scale(dpr, dpr);
    
    const width = containerWidth;
    const height = containerHeight;
    const centerX = width / 2;
    const centerY = height / 2;
    
    // Use maximum space - minimal margin
    const maxRadius = Math.min(width, height) / 2;
    const radius = maxRadius * 0.95;

    ctx.clearRect(0, 0, width, height);

    const segments = [
        { label: 'Confirmed', value: data.confirmed, color: '#48bb78' },
        { label: 'Refuted', value: data.refuted, color: '#f56565' },
        { label: 'No status', value: data.no_status, color: '#ed8936' }
    ];

    const total = data.total;
    let currentAngle = -Math.PI / 2;

    if (total === 0) {
        ctx.fillStyle = '#a0aec0';
        ctx.font = '14px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных', centerX, centerY);
        return;
    }

    // Draw segments
    segments.forEach(segment => {
        if (segment.value === 0) return;

        const sliceAngle = (segment.value / total) * Math.PI * 2;
        const percentage = ((segment.value / total) * 100);

        ctx.beginPath();
        ctx.fillStyle = segment.color;
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + sliceAngle);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 3;
        ctx.stroke();

        // Only show percentage label if segment is large enough (>= 5%)
        if (percentage >= 5) {
            // Percentage label - scale with chart size
            const labelAngle = currentAngle + sliceAngle / 2;
            const labelRadius = radius * 0.65;
            const labelX = centerX + Math.cos(labelAngle) * labelRadius;
            const labelY = centerY + Math.sin(labelAngle) * labelRadius;
            
            // Dynamic font size based on chart size
            const labelFontSize = Math.max(16, Math.min(width, height) * 0.045);

            ctx.fillStyle = '#fff';
            ctx.font = `bold ${labelFontSize}px -apple-system, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';

            // Shadow for better readability
            ctx.shadowColor = 'rgba(0,0,0,0.5)';
            ctx.shadowBlur = 8;
            ctx.fillText(percentage.toFixed(1) + '%', labelX, labelY);
            ctx.shadowBlur = 0;
        }

        currentAngle += sliceAngle;
    });
}

// Tabs functionality
let currentScanActivityPeriod = 30;
let loadedTabs = new Set(['overview']); // Track which tabs have been loaded
let loadedInternalTabs = new Set(['low-confidence']); // Track which internal tabs have been loaded

// Pagination state for secrets tables
const secretsPerPage = 50;
let lowConfidenceSecrets = [];
let highConfidenceSecrets = [];
let lowConfidenceCurrentPage = 1;
let highConfidenceCurrentPage = 1;

function switchTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.stats-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    // Remove active class from all tabs
    document.querySelectorAll('.stats-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    const content = document.getElementById(`${tabName}-content`);
    if (content) {
        content.classList.add('active');
    }
    
    // Add active class to corresponding tab button
    document.querySelectorAll('.stats-tab').forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        }
    });
    
    // Save to localStorage
    localStorage.setItem('statsActiveTab', tabName);
    
    // Lazy load tab data if not loaded
    if (!loadedTabs.has(tabName)) {
        loadTabData(tabName);
        loadedTabs.add(tabName);
    } else {
        // Если вкладка уже загружена, но нужно перерисовать графики (особенно для overview)
        if (tabName === 'overview') {
            loadTabData(tabName); // Перерисовка графиков при возврате на вкладку
        }
    }
}

function loadTabData(tabName) {
    switch(tabName) {
        case 'overview':
            // Перерисовка графиков при возврате на вкладку (на случай если canvas был скрыт)
            setTimeout(() => {
                if (currentTrendsPeriod) {
                    loadTrendsData(currentTrendsPeriod);
                }
                loadStatusDistribution();
            }, 50);
            break;
        case 'secrets':
            // Небольшая задержка для того, чтобы вкладка стала видимой
            setTimeout(() => {
                Promise.all([
                    loadSecretTypes(), // Перерисовка при переключении вкладки
                    loadTopFileExtensions()
                ]).catch(error => console.error('Error loading secrets tab:', error));
            }, 50);
            break;
        case 'scans':
            setTimeout(() => {
                loadScanActivity(currentScanActivityPeriod);
            }, 50);
            break;
        case 'analytics':
            setTimeout(() => {
                Promise.all([
                    loadConfidenceAccuracy(),
                    loadLowConfidenceConfirmed() // Загружаем первую вкладку по умолчанию
                ]).catch(error => console.error('Error loading analytics tab:', error));
            }, 50);
            break;
    }
}


// Fetch and render scan activity
async function loadScanActivity(days = 30) {
    try {
        const response = await fetch(`/secret_scanner/api/stats/scan-activity?days=${days}`);
        const data = await response.json();
        renderScanActivityChart(data.data);
    } catch (error) {
        console.error('Error loading scan activity:', error);
    }
}

// Render scan activity line chart
function renderScanActivityChart(data) {
    const canvas = document.getElementById('scanActivityChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    const containerWidth = canvas.offsetWidth;
    const containerHeight = canvas.offsetHeight;
    
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    ctx.scale(dpr, dpr);
    
    const width = containerWidth;
    const height = containerHeight;
    
    const padding = {
        top: Math.max(15, height * 0.03),
        right: Math.max(10, width * 0.01),
        bottom: Math.max(40, height * 0.08),
        left: Math.max(50, width * 0.08)
    };
    
    ctx.clearRect(0, 0, width, height);
    
    if (!data || data.length === 0) {
        ctx.fillStyle = '#a0aec0';
        ctx.font = '14px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных за выбранный период', width / 2, height / 2);
        return;
    }
    
    const dates = data.map(d => d.date);
    const completedValues = data.map(d => d.completed || 0);
    const failedValues = data.map(d => d.failed || 0);
    const runningValues = data.map(d => d.running || 0);
    
    const maxValue = Math.max(...completedValues, ...failedValues, ...runningValues, 10);
    const xScale = (width - padding.left - padding.right) / Math.max(dates.length - 1, 1);
    const yScale = (height - padding.top - padding.bottom) / maxValue;
    
    // Draw grid
    ctx.strokeStyle = '#edf2f7';
    ctx.lineWidth = 1;
    
    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
        const y = height - padding.bottom - (i * (height - padding.top - padding.bottom) / ySteps);
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();
        
        ctx.fillStyle = '#718096';
        ctx.font = 'bold 13px -apple-system, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        const value = Math.round((maxValue * i) / ySteps);
        ctx.fillText(value.toString(), padding.left - 10, y);
    }
    
    // Axes
    ctx.strokeStyle = '#cbd5e0';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    ctx.lineTo(width - padding.right, height - padding.bottom);
    ctx.stroke();
    
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, height - padding.bottom);
    ctx.stroke();
    
    // X-axis labels
    const labelStep = Math.max(1, Math.ceil(dates.length / 15));
    ctx.fillStyle = '#718096';
    ctx.font = 'bold 12px -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    
    dates.forEach((date, i) => {
        if (i % labelStep === 0 || i === dates.length - 1) {
            const x = padding.left + (i * xScale);
            const dateObj = new Date(date);
            const label = `${dateObj.getDate()}.${dateObj.getMonth() + 1}`;
            
            ctx.save();
            ctx.translate(x, height - padding.bottom + 5);
            ctx.rotate(-0.4);
            ctx.fillText(label, 0, 0);
            ctx.restore();
        }
    });
    
    // Draw Completed line
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#48bb78';
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    completedValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + ((completedValues.length - 1) * xScale), height - padding.bottom);
    ctx.closePath();
    ctx.fill();
    
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.strokeStyle = '#48bb78';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    
    completedValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // Draw Failed line
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#f56565';
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    failedValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + ((failedValues.length - 1) * xScale), height - padding.bottom);
    ctx.closePath();
    ctx.fill();
    
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.strokeStyle = '#f56565';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    
    failedValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // Draw Running line
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#ed8936';
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    runningValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + ((runningValues.length - 1) * xScale), height - padding.bottom);
    ctx.closePath();
    ctx.fill();
    
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.strokeStyle = '#ed8936';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    
    runningValues.forEach((value, i) => {
        const x = padding.left + (i * xScale);
        const y = height - padding.bottom - (value * yScale);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
}

// Fetch and render top file extensions
async function loadTopFileExtensions() {
    try {
        const response = await fetch('/secret_scanner/api/stats/top-file-extensions?limit=10');
        const data = await response.json();
        renderExtensionsChart(data.extensions);
    } catch (error) {
        console.error('Error loading file extensions:', error);
    }
}

// Render horizontal bar chart for file extensions
function renderExtensionsChart(data) {
    const canvas = document.getElementById('fileExtensionsChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    const containerWidth = canvas.offsetWidth;
    const containerHeight = canvas.offsetHeight;
    
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    ctx.scale(dpr, dpr);
    
    const width = containerWidth;
    const height = containerHeight;
    
    const padding = {
        top: Math.max(20, height * 0.05),
        right: Math.max(80, width * 0.15),
        bottom: Math.max(40, height * 0.08),
        left: Math.max(100, width * 0.2)
    };
    
    ctx.clearRect(0, 0, width, height);
    
    if (!data || data.length === 0) {
        ctx.fillStyle = '#a0aec0';
        ctx.font = '14px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных', width / 2, height / 2);
        return;
    }
    
    const maxValue = Math.max(...data.map(d => d.count), 10);
    const barHeight = (height - padding.top - padding.bottom) / data.length;
    const xScale = (width - padding.left - padding.right) / maxValue;
    
    // Draw bars
    data.forEach((item, index) => {
        const barY = padding.top + (index * barHeight);
        const barWidth = item.count * xScale;
        const barCenterY = barY + barHeight / 2;
        
        // Bar background
        ctx.fillStyle = '#4299e1';
        ctx.fillRect(padding.left, barY + barHeight * 0.2, barWidth, barHeight * 0.6);
        
        // Extension label
        ctx.fillStyle = '#2d3748';
        ctx.font = 'bold 13px -apple-system, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(item.extension, padding.left - 10, barCenterY);
        
        // Count label
        ctx.fillStyle = '#2d3748';
        ctx.font = 'bold 12px -apple-system, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(formatNumber(item.count), padding.left + barWidth + 10, barCenterY);
    });
    
    // X-axis
    ctx.strokeStyle = '#cbd5e0';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    ctx.lineTo(width - padding.right, height - padding.bottom);
    ctx.stroke();
    
    // X-axis labels
    const xSteps = 5;
    ctx.fillStyle = '#718096';
    ctx.font = 'bold 12px -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    
    for (let i = 0; i <= xSteps; i++) {
        const x = padding.left + (i * (width - padding.left - padding.right) / xSteps);
        const value = Math.round((maxValue * i) / xSteps);
        ctx.fillText(value.toString(), x, height - padding.bottom + 5);
    }
}

// Fetch and render confidence accuracy
async function loadConfidenceAccuracy() {
    try {
        const response = await fetch('/secret_scanner/api/stats/confidence-accuracy');
        const data = await response.json();
        renderConfidenceChart(data.ranges);
    } catch (error) {
        console.error('Error loading confidence accuracy:', error);
    }
}

// Render stacked bar chart for confidence accuracy
function renderConfidenceChart(data) {
    const canvas = document.getElementById('confidenceChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    const containerWidth = canvas.offsetWidth;
    const containerHeight = canvas.offsetHeight;
    
    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    ctx.scale(dpr, dpr);
    
    const width = containerWidth;
    const height = containerHeight;
    
    const padding = {
        top: Math.max(20, height * 0.05),
        right: Math.max(20, width * 0.03),
        bottom: Math.max(60, height * 0.12), // Увеличено для подписи оси X
        left: Math.max(70, width * 0.12) // Увеличено для подписи оси Y
    };
    
    ctx.clearRect(0, 0, width, height);
    
    if (!data || data.length === 0) {
        ctx.fillStyle = '#a0aec0';
        ctx.font = '14px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных', width / 2, height / 2);
        return;
    }
    
    const maxValue = Math.max(...data.map(d => d.confirmed + d.refuted), 10);
    const barWidth = (width - padding.left - padding.right) / data.length * 0.8;
    const barSpacing = (width - padding.left - padding.right) / data.length * 0.2;
    const yScale = (height - padding.top - padding.bottom) / maxValue;
    
    // Draw bars
    data.forEach((item, index) => {
        const barX = padding.left + (index * (barWidth + barSpacing));
        const confirmedCount = item.confirmed || 0;
        const refutedCount = item.refuted || 0;
        const confirmedHeight = confirmedCount * yScale;
        const refutedHeight = refutedCount * yScale;
        const totalHeight = confirmedHeight + refutedHeight;
        
        // Пропускаем столбцы с нулевыми значениями, но только если оба равны нулю
        if (totalHeight === 0) {
            return;
        }
        
        // Минимальная высота для видимости столбца (увеличена для лучшей видимости)
        const minBarHeight = 8;
        const minConfirmedHeight = confirmedCount > 0 ? Math.max(confirmedHeight, 8) : 0;
        const minRefutedHeight = refutedCount > 0 ? Math.max(refutedHeight, 8) : 0;
        const finalTotalHeight = minConfirmedHeight + minRefutedHeight;
        
        // Вычисляем позицию начала столбца
        const barStartY = height - padding.bottom - finalTotalHeight;
        
        // Draw confirmed (green) at bottom
        if (confirmedCount > 0) {
            ctx.fillStyle = '#48bb78';
            ctx.fillRect(barX, barStartY, barWidth, minConfirmedHeight);
            
            // Всегда добавляем текст с количеством Confirmed
            // Если столбец маленький - выводим над ним, иначе - внутри
            const textY = minConfirmedHeight > 18 
                ? barStartY + minConfirmedHeight / 2  // Внутри столбца
                : barStartY - 8;  // Над столбцом
            
            ctx.fillStyle = minConfirmedHeight > 18 ? '#fff' : '#2d3748';
            ctx.font = minConfirmedHeight > 18 
                ? 'bold 11px -apple-system, sans-serif'
                : 'bold 10px -apple-system, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = minConfirmedHeight > 18 ? 'middle' : 'bottom';
            
            if (minConfirmedHeight > 18) {
                ctx.shadowColor = 'rgba(0,0,0,0.5)';
                ctx.shadowBlur = 4;
            }
            
            ctx.fillText(
                formatNumber(confirmedCount),
                barX + barWidth / 2,
                textY
            );
            
            if (minConfirmedHeight > 18) {
                ctx.shadowBlur = 0;
            }
        }
        
        // Draw refuted (red) on top of confirmed
        if (refutedCount > 0) {
            const refutedY = confirmedCount > 0 
                ? barStartY + minConfirmedHeight 
                : barStartY;
            
            ctx.fillStyle = '#f56565';
            ctx.fillRect(barX, refutedY, barWidth, minRefutedHeight);
            
            // Всегда добавляем текст с количеством Refuted
            // Если столбец маленький - выводим над ним, иначе - внутри
            const textY = minRefutedHeight > 18 
                ? refutedY + minRefutedHeight / 2  // Внутри столбца
                : refutedY - 8;  // Над столбцом
            
            ctx.fillStyle = minRefutedHeight > 18 ? '#fff' : '#2d3748';
            ctx.font = minRefutedHeight > 18 
                ? 'bold 11px -apple-system, sans-serif'
                : 'bold 10px -apple-system, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = minRefutedHeight > 18 ? 'middle' : 'bottom';
            
            if (minRefutedHeight > 18) {
                ctx.shadowColor = 'rgba(0,0,0,0.5)';
                ctx.shadowBlur = 4;
            }
            
            ctx.fillText(
                formatNumber(refutedCount),
                barX + barWidth / 2,
                textY
            );
            
            if (minRefutedHeight > 18) {
                ctx.shadowBlur = 0;
            }
        }
        
        // Bar outline - только если есть данные
        if (totalHeight > 0) {
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.strokeRect(barX, barStartY, barWidth, finalTotalHeight);
        }
        
        // X-axis label (confidence range)
        ctx.fillStyle = '#718096';
        ctx.font = 'bold 11px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.save();
        ctx.translate(barX + barWidth / 2, height - padding.bottom + 5);
        ctx.rotate(-0.4);
        ctx.fillText(item.range, 0, 0);
        ctx.restore();
    });
    
    // Axes
    ctx.strokeStyle = '#cbd5e0';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding.left, height - padding.bottom);
    ctx.lineTo(width - padding.right, height - padding.bottom);
    ctx.stroke();
    
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, height - padding.bottom);
    ctx.stroke();
    
    // Y-axis labels
    const ySteps = 5;
    ctx.fillStyle = '#718096';
    ctx.font = 'bold 13px -apple-system, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    
    for (let i = 0; i <= ySteps; i++) {
        const y = height - padding.bottom - (i * (height - padding.top - padding.bottom) / ySteps);
        const value = Math.round((maxValue * i) / ySteps);
        ctx.fillText(value.toString(), padding.left - 10, y);
    }
    
    // Axis labels
    ctx.fillStyle = '#4a5568';
    ctx.font = 'bold 14px -apple-system, sans-serif';
    
    // Y-axis label (Количество секретов)
    ctx.save();
    ctx.translate(20, height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Количество секретов', 0, 0);
    ctx.restore();
    
    // X-axis label (Диапазон confidence, %)
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('Диапазон confidence (%)', width / 2, height - padding.bottom + 35);
}

// Render secret table with pagination (helper function)
function renderSecretTable(tbodyId, allSecrets, currentPage, startIndex = 0) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (allSecrets.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">Нет данных</td></tr>';
        return;
    }
    
    // Вычисляем диапазон секретов для текущей страницы
    const start = (currentPage - 1) * secretsPerPage;
    const end = start + secretsPerPage;
    const pageSecrets = allSecrets.slice(start, end);
    
    pageSecrets.forEach((secret, index) => {
        const row = document.createElement('tr');
        const projectLink = `/secret_scanner/project/${encodeURIComponent(secret.project_name)}`;
        const globalIndex = start + index + 1; // Глобальный номер с учетом страницы
        
        // Извлекаем расширение файла из path
        let extension = '.no_extension';
        if (secret.path) {
            const lastDotIndex = secret.path.lastIndexOf('.');
            if (lastDotIndex !== -1 && lastDotIndex < secret.path.length - 1) {
                extension = secret.path.substring(lastDotIndex);
            }
        }
        
        // Обрезаем секрет для отображения (первые 50 символов)
        const secretValue = secret.secret || '';
        const displaySecret = secretValue.length > 50 
            ? secretValue.substring(0, 50) + '...' 
            : secretValue;
        
        row.innerHTML = `
            <td>${globalIndex}</td>
            <td><a href="${projectLink}">${escapeHtml(secret.project_name || 'Unknown')}</a></td>
            <td title="${escapeHtml(secret.path)}">${escapeHtml(extension)}</td>
            <td>${escapeHtml(secret.type)}</td>
            <td title="${escapeHtml(secret.secret)}">${escapeHtml(displaySecret)}</td>
            <td><strong>${secret.confidence.toFixed(1)}%</strong></td>
        `;
        tbody.appendChild(row);
    });
    
    return {
        totalPages: Math.ceil(allSecrets.length / secretsPerPage),
        currentPage: currentPage
    };
}

// Update pagination controls
function updatePagination(paginationId, pageInfoId, prevBtnId, nextBtnId, currentPage, totalPages) {
    const pagination = document.getElementById(paginationId);
    const pageInfo = document.getElementById(pageInfoId);
    const prevBtn = document.getElementById(prevBtnId);
    const nextBtn = document.getElementById(nextBtnId);
    
    if (pagination && pageInfo && prevBtn && nextBtn) {
        pagination.style.display = totalPages > 1 ? 'flex' : 'none';
        pageInfo.textContent = `Страница ${currentPage} из ${totalPages}`;
        prevBtn.disabled = currentPage === 1;
        nextBtn.disabled = currentPage === totalPages;
    }
}

// Fetch and render low confidence confirmed secrets
async function loadLowConfidenceConfirmed() {
    try {
        const response = await fetch('/secret_scanner/api/stats/low-confidence-confirmed?limit=400');
        const data = await response.json();
        lowConfidenceSecrets = data.secrets;
        lowConfidenceCurrentPage = 1;
        
        const pagination = renderSecretTable('lowConfidenceBody', lowConfidenceSecrets, lowConfidenceCurrentPage);
        if (pagination) {
            updatePagination(
                'lowConfidencePagination',
                'lowConfidencePageInfo',
                'lowConfidencePrevBtn',
                'lowConfidenceNextBtn',
                pagination.currentPage,
                pagination.totalPages
            );
        }
    } catch (error) {
        console.error('Error loading low confidence confirmed:', error);
        const tbody = document.getElementById('lowConfidenceBody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">Ошибка загрузки данных</td></tr>';
        }
    }
}

// Fetch and render high confidence refuted secrets
async function loadHighConfidenceRefuted() {
    try {
        const response = await fetch('/secret_scanner/api/stats/high-confidence-refuted?limit=400');
        const data = await response.json();
        highConfidenceSecrets = data.secrets;
        highConfidenceCurrentPage = 1;
        
        const pagination = renderSecretTable('highConfidenceBody', highConfidenceSecrets, highConfidenceCurrentPage);
        if (pagination) {
            updatePagination(
                'highConfidencePagination',
                'highConfidencePageInfo',
                'highConfidencePrevBtn',
                'highConfidenceNextBtn',
                pagination.currentPage,
                pagination.totalPages
            );
        }
    } catch (error) {
        console.error('Error loading high confidence refuted:', error);
        const tbody = document.getElementById('highConfidenceBody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">Ошибка загрузки данных</td></tr>';
        }
    }
}

// Pagination handlers
function goToPageLowConfidence(page) {
    if (page < 1 || lowConfidenceSecrets.length === 0) return;
    const totalPages = Math.ceil(lowConfidenceSecrets.length / secretsPerPage);
    if (page > totalPages) return;
    
    lowConfidenceCurrentPage = page;
    const pagination = renderSecretTable('lowConfidenceBody', lowConfidenceSecrets, lowConfidenceCurrentPage);
    if (pagination) {
        updatePagination(
            'lowConfidencePagination',
            'lowConfidencePageInfo',
            'lowConfidencePrevBtn',
            'lowConfidenceNextBtn',
            pagination.currentPage,
            pagination.totalPages
        );
    }
}

function goToPageHighConfidence(page) {
    if (page < 1 || highConfidenceSecrets.length === 0) return;
    const totalPages = Math.ceil(highConfidenceSecrets.length / secretsPerPage);
    if (page > totalPages) return;
    
    highConfidenceCurrentPage = page;
    const pagination = renderSecretTable('highConfidenceBody', highConfidenceSecrets, highConfidenceCurrentPage);
    if (pagination) {
        updatePagination(
            'highConfidencePagination',
            'highConfidencePageInfo',
            'highConfidencePrevBtn',
            'highConfidenceNextBtn',
            pagination.currentPage,
            pagination.totalPages
        );
    }
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Period selector event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Trends period selector
    document.querySelectorAll('.period-btn').forEach(btn => {
        if (btn.dataset.period) {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.period-btn').forEach(b => {
                    if (b.dataset.period) b.classList.remove('active');
                });
                this.classList.add('active');
                currentTrendsPeriod = parseInt(this.dataset.period);
                loadTrendsData(currentTrendsPeriod);
            });
        }
    });
    
    // Tab switching event listeners
    const tabs = document.querySelectorAll('.stats-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const targetTab = this.dataset.tab;
            switchTab(targetTab);
        });
    });
    
    // Restore active tab from localStorage
    const savedTab = localStorage.getItem('statsActiveTab') || 'overview';
    switchTab(savedTab);
    
    // Scan activity period selector
    document.querySelectorAll('[data-period-scan]').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('[data-period-scan]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentScanActivityPeriod = parseInt(this.dataset.periodScan);
            loadScanActivity(currentScanActivityPeriod);
        });
    });
    
    // Internal tabs switching (внутри блока аналитики)
    const internalTabs = document.querySelectorAll('.stats-tab-internal');
    internalTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const targetTab = this.dataset.tabInternal;
            switchInternalTab(targetTab);
        });
    });
    
    // Pagination buttons for low confidence
    const lowConfidencePrevBtn = document.getElementById('lowConfidencePrevBtn');
    const lowConfidenceNextBtn = document.getElementById('lowConfidenceNextBtn');
    if (lowConfidencePrevBtn) {
        lowConfidencePrevBtn.addEventListener('click', () => goToPageLowConfidence(lowConfidenceCurrentPage - 1));
    }
    if (lowConfidenceNextBtn) {
        lowConfidenceNextBtn.addEventListener('click', () => goToPageLowConfidence(lowConfidenceCurrentPage + 1));
    }
    
    // Pagination buttons for high confidence
    const highConfidencePrevBtn = document.getElementById('highConfidencePrevBtn');
    const highConfidenceNextBtn = document.getElementById('highConfidenceNextBtn');
    if (highConfidencePrevBtn) {
        highConfidencePrevBtn.addEventListener('click', () => goToPageHighConfidence(highConfidenceCurrentPage - 1));
    }
    if (highConfidenceNextBtn) {
        highConfidenceNextBtn.addEventListener('click', () => goToPageHighConfidence(highConfidenceCurrentPage + 1));
    }
});

// Switch internal tabs (внутри блока аналитики)
function switchInternalTab(tabName) {
    // Hide all internal tab contents
    document.querySelectorAll('.stats-tab-content-internal').forEach(content => {
        content.classList.remove('active');
    });
    
    // Remove active class from all internal tabs
    document.querySelectorAll('.stats-tab-internal').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    const content = document.getElementById(`${tabName}-content`);
    if (content) {
        content.classList.add('active');
    }
    
    // Add active class to corresponding tab button
    document.querySelectorAll('.stats-tab-internal').forEach(tab => {
        if (tab.dataset.tabInternal === tabName) {
            tab.classList.add('active');
        }
    });
    
    // Lazy load tab data if not loaded
    if (!loadedInternalTabs.has(tabName)) {
        if (tabName === 'low-confidence') {
            loadLowConfidenceConfirmed();
        } else if (tabName === 'high-confidence') {
            loadHighConfidenceRefuted();
        }
        loadedInternalTabs.add(tabName);
    }
}

// Window resize handler
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        const activeTab = localStorage.getItem('statsActiveTab') || 'overview';
        if (activeTab === 'overview') {
            if (currentTrendsPeriod) {
                loadTrendsData(currentTrendsPeriod);
            }
            loadStatusDistribution();
        } else if (activeTab === 'secrets') {
            loadSecretTypes();
            if (loadedTabs.has('secrets')) {
                loadTopFileExtensions();
            }
        } else if (activeTab === 'scans') {
            if (loadedTabs.has('scans') && currentScanActivityPeriod) {
                loadScanActivity(currentScanActivityPeriod);
            }
        } else if (activeTab === 'analytics') {
            if (loadedTabs.has('analytics')) {
                loadConfidenceAccuracy();
            }
        }
    }, 250);
});

// Initialize dashboard
async function initDashboard() {
    showLoading();

    try {
        await Promise.all([
            loadKPIData(),
            loadTrendsData(currentTrendsPeriod),
            loadTopProjects(),
            loadSecretTypes(),
            loadStatusDistribution()
        ]);
    } catch (error) {
        console.error('Error initializing dashboard:', error);
    } finally {
        hideLoading();
    }
}

// Load dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});
