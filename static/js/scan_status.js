function refreshPage() {
    window.location.reload();
}

// Получаем данные из data-атрибутов
function getScanData() {
    return {
        status: document.body.dataset.scanStatus,
        id: document.body.dataset.scanId,
        startedAt: document.body.dataset.scanStartedAt,
        startedAtDisplay: document.body.dataset.scanStartedAtDisplay
    };
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    const scanData = getScanData();
    
    // Auto-refresh every 3 seconds if scan is running
    if (scanData.status === 'running') {
        setInterval(() => {
            window.location.reload();
        }, 3000);

        // Update elapsed time
        function updateElapsedTime() {
            const startTime = new Date(scanData.startedAt);
            const now = new Date();
            const elapsed = Math.floor((now - startTime) / 1000);
            
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            
            const elapsedElement = document.getElementById('elapsedTime');
            if (elapsedElement) {
                elapsedElement.innerHTML = `
                    Started: ${scanData.startedAtDisplay}<br>
                    Elapsed: ${minutes}m ${seconds}s
                `;
            }
        }

        // Update elapsed time every second
        updateElapsedTime();
        setInterval(updateElapsedTime, 1000);
    }

    // Auto-redirect to results after 2 seconds if completed
    if (scanData.status === 'completed') {
        setTimeout(() => {
            window.location.href = `/secret_scanner/scan/${scanData.id}/results`;
        }, 2000);
    }
});