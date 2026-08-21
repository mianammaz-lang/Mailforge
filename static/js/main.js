// static/js/main.js

// Quick scan helper for individual scan types
function runScan(endpoint, label) {
    const modal = new bootstrap.Modal(document.getElementById('scanModal'));
    const progress = document.getElementById('scanProgress');
    const steps = document.querySelectorAll('.scan-step');
    
    // Reset modal state
    progress.style.width = '30%';
    progress.className = 'progress-bar progress-bar-striped progress-bar-animated bg-primary';
    steps.forEach(s => {
        s.innerHTML = '<i class="bi bi-circle me-2"></i> ' + (s.getAttribute('data-text') || s.innerText);
        s.className = 'scan-step text-muted mb-2';
    });
    if (steps[0]) {
        const text = steps[0].getAttribute('data-text') || steps[0].innerText;
        steps[0].setAttribute('data-text', text);
        steps[0].innerHTML = '<span class="scanning-dot"></span> ' + label;
        steps[0].classList.remove('text-muted');
        steps[0].classList.add('fw-bold', 'text-primary');
    }
    
    modal.show();
    
    fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(r => r.json())
    .then(data => {
        progress.style.width = '100%';
        progress.classList.remove('progress-bar-animated');
        progress.classList.add('bg-success');
        if (steps[0]) {
            steps[0].innerHTML = '<i class="bi bi-check-circle-fill text-success me-2"></i> ' + label + ' Complete!';
            steps[0].classList.remove('text-primary');
            steps[0].classList.add('text-success');
        }
        setTimeout(() => window.location.reload(), 1500);
    })
    .catch(err => {
        progress.classList.add('bg-danger');
        console.error(err);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // Number Counters
    const counters = document.querySelectorAll('.counter-value');
    counters.forEach(counter => {
        const target = +counter.getAttribute('data-target');
        const duration = 1500;
        const increment = target / (duration / 16);
        let current = 0;

        const updateCounter = () => {
            current += increment;
            if (current < target) {
                counter.innerText = Math.ceil(current);
                requestAnimationFrame(updateCounter);
            } else {
                counter.innerText = Math.round(target * 10) / 10;
            }
        };
        if (target > 0) updateCounter();
    });

    // Table Search
    const searchInputs = document.querySelectorAll('.table-search');
    searchInputs.forEach(input => {
        input.addEventListener('keyup', function() {
            const filter = this.value.toLowerCase();
            const targetId = this.getAttribute('data-target');
            const rows = document.querySelectorAll(`${targetId} tbody tr`);
            
            rows.forEach(row => {
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(filter) ? '' : 'none';
            });
        });
    });
});

// Run Full Scan with real API call
function runFullScan() {
    const modal = new bootstrap.Modal(document.getElementById('scanModal'));
    modal.show();
    
    const progress = document.getElementById('scanProgress');
    const steps = document.querySelectorAll('.scan-step');
    let currentStep = 0;
    let scanDone = false;

    // Animate steps while waiting for the API
    const interval = setInterval(() => {
        if (currentStep < steps.length && !scanDone) {
            steps.forEach((s, i) => {
                const text = s.getAttribute('data-text') || s.innerText;
                s.setAttribute('data-text', text);
                if (i < currentStep) {
                    s.innerHTML = '<i class="bi bi-check-circle-fill text-success me-2"></i> ' + text;
                    s.classList.remove('text-muted', 'text-primary', 'fw-bold');
                    s.classList.add('text-success');
                } else if (i === currentStep) {
                    s.innerHTML = '<span class="scanning-dot"></span> ' + text;
                    s.classList.remove('text-muted');
                    s.classList.add('fw-bold', 'text-primary');
                }
            });
            progress.style.width = ((currentStep + 1) / steps.length * 80) + '%';
            currentStep++;
        }
    }, 2000);

    // Actually call the scan API
    fetch('/api/scan/full', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        scanDone = true;
        clearInterval(interval);
        
        // Mark all steps complete
        steps.forEach(s => {
            const text = s.getAttribute('data-text') || s.innerText;
            s.innerHTML = '<i class="bi bi-check-circle-fill text-success me-2"></i> ' + text;
            s.classList.remove('text-muted', 'text-primary', 'fw-bold');
            s.classList.add('text-success');
        });
        
        progress.style.width = '100%';
        progress.classList.remove('progress-bar-animated');
        progress.classList.add('bg-success');
        
        // Reload after a short delay
        setTimeout(() => {
            window.location.reload();
        }, 1500);
    })
    .catch(error => {
        scanDone = true;
        clearInterval(interval);
        progress.classList.remove('bg-primary', 'progress-bar-animated');
        progress.classList.add('bg-danger');
        progress.style.width = '100%';
        
        const currentStepEl = steps[Math.min(currentStep, steps.length - 1)];
        if (currentStepEl) {
            currentStepEl.innerHTML = '<i class="bi bi-x-circle-fill text-danger me-2"></i> Error during scan';
            currentStepEl.classList.add('text-danger');
        }
        console.error('Scan error:', error);
    });
}

// Chart Init Helpers
function initDoughnutChart(ctxId, data, labels, colors) {
    const ctx = document.getElementById(ctxId);
    if (!ctx) return;
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderWidth: 0
            }]
        },
        options: {
            cutout: '75%',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}

function initLineChart(ctxId, labels, data) {
    const ctx = document.getElementById(ctxId);
    if (!ctx) return;
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Health Score',
                data: data,
                borderColor: '#4f46e5',
                backgroundColor: 'rgba(79, 70, 229, 0.1)',
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#4f46e5',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, max: 100 }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}
