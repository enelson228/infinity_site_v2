'use strict';

const REFRESH_INTERVAL_MS = 5000;

// Previous network snapshot for rate calculation
let prevNet = null;
let prevTimestamp = null;

/**
 * Scramble count-up animation for metric values.
 * @param {HTMLElement} el - Element to animate
 * @param {string} finalValue - The real value to display (e.g. "94.7")
 */
function scrambleValue(el, finalValue) {
    // Only play once per page load
    if (el.dataset.scrambled) {
        el.textContent = finalValue;
        return;
    }
    el.dataset.scrambled = 'true';

    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@$%';
    const len = String(finalValue).length;
    const numericVal = parseFloat(finalValue);
    const duration = (isNaN(numericVal) || numericVal < 100) ? 400 : 600;

    el.classList.add('scrambling');

    const interval = setInterval(() => {
        el.textContent = Array.from({ length: len }, () =>
            chars[Math.floor(Math.random() * chars.length)]
        ).join('');
    }, 40);

    setTimeout(() => {
        clearInterval(interval);
        el.classList.remove('scrambling');
        el.textContent = finalValue;
    }, duration);
}

function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function formatBytesPerSec(bytesPerSec) {
    return formatBytes(bytesPerSec) + '/s';
}

function formatUptime(seconds) {
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const parts = [];
    if (d > 0) parts.push(d + 'd');
    if (h > 0) parts.push(h + 'h');
    if (m > 0) parts.push(m + 'm');
    parts.push(s + 's');
    return parts.join(' ');
}

function setBar(barId, fillId, percent) {
    const bar = document.getElementById(barId);
    const fill = document.getElementById(fillId);
    if (!bar || !fill) return;
    fill.style.width = Math.min(percent, 100) + '%';
    bar.classList.remove('warn', 'critical');
    if (percent >= 90) {
        bar.classList.add('critical');
    } else if (percent >= 70) {
        bar.classList.add('warn');
    }
}

function updateCpu(cpu) {
    scrambleValue(document.getElementById('cpu-percent'), String(cpu.percent));
    setBar('cpu-bar', 'cpu-bar-fill', cpu.percent);

    const coresText = cpu.cores_logical !== null
        ? cpu.cores_logical + (cpu.cores_physical ? ' logical / ' + cpu.cores_physical + ' physical' : '')
        : '—';
    document.getElementById('cpu-cores').textContent = coresText;

    document.getElementById('cpu-freq').textContent = cpu.freq_current !== null
        ? cpu.freq_current + ' MHz'
        : '—';
    const freqMaxEl = document.getElementById('cpu-freq-max'); if (freqMaxEl) freqMaxEl.textContent = cpu.freq_max !== null ? cpu.freq_max + ' MHz' : '—';
}

function updateRam(ram) {
    scrambleValue(document.getElementById('ram-percent'), String(ram.percent));
    setBar('ram-bar', 'ram-bar-fill', ram.percent);
    document.getElementById('ram-used').textContent = formatBytes(ram.used);
    const ramAvailEl = document.getElementById('ram-available'); if (ramAvailEl) ramAvailEl.textContent = formatBytes(ram.available);
    document.getElementById('ram-total').textContent = formatBytes(ram.total);
}

function updateDisk(disk) {
    scrambleValue(document.getElementById('disk-percent'), String(disk.percent));
    setBar('disk-bar', 'disk-bar-fill', disk.percent);
    document.getElementById('disk-used').textContent = formatBytes(disk.used);
    const diskFreeEl = document.getElementById('disk-free'); if (diskFreeEl) diskFreeEl.textContent = formatBytes(disk.free);
    document.getElementById('disk-total').textContent = formatBytes(disk.total);
}

function updateNetwork(network, timestamp) {
    document.getElementById('net-rx-total').textContent = formatBytes(network.bytes_recv);
    document.getElementById('net-tx-total').textContent = formatBytes(network.bytes_sent);

    if (prevNet !== null && prevTimestamp !== null) {
        const dt = timestamp - prevTimestamp;
        if (dt > 0) {
            const rxRate = (network.bytes_recv - prevNet.bytes_recv) / dt;
            const txRate = (network.bytes_sent - prevNet.bytes_sent) / dt;
            document.getElementById('net-rx-rate').textContent = formatBytesPerSec(Math.max(0, rxRate));
            document.getElementById('net-tx-rate').textContent = formatBytesPerSec(Math.max(0, txRate));
        }
    }

    const pktsRxEl = document.getElementById('net-pkts-rx'); if (pktsRxEl) pktsRxEl.textContent = network.packets_recv?.toLocaleString() ?? '—';
    const pktsTxEl = document.getElementById('net-pkts-tx'); if (pktsTxEl) pktsTxEl.textContent = network.packets_sent?.toLocaleString() ?? '—';

    prevNet = network;
    prevTimestamp = timestamp;
}

function updateSystem(uptimeSeconds, loadAvg) {
    document.getElementById('sys-uptime').textContent = formatUptime(uptimeSeconds);
    document.getElementById('load-1').textContent = loadAvg.one;
    document.getElementById('load-5').textContent = loadAvg.five;
}

function updateLastUpdate(timestamp) {
    const d = new Date(timestamp * 1000);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    document.getElementById('last-update').textContent = hh + ':' + mm + ':' + ss;
}

function drawChart(pathId, data, maxVal = 100) {
    const path = document.querySelector('.' + pathId);
    if (!path || !data || data.length < 2) return;
    
    // Reverse data so it's left-to-right (newest on right)
    const points = [...data].reverse();
    const width = 100;
    const height = 40;
    const step = width / (points.length - 1);
    
    let d = `M 0,${height - (points[0] / maxVal) * height}`;
    for (let i = 1; i < points.length; i++) {
        d += ` L ${i * step},${height - (points[i] / maxVal) * height}`;
    }
    path.setAttribute('d', d);
}

function showError(msg) {
    const banner = document.getElementById('error-banner');
    const msgEl = document.getElementById('error-message');
    if (msg) {
        msgEl.textContent = msg;
        banner.classList.add('visible');
    } else {
        banner.classList.remove('visible');
    }
}

async function fetchTelemetry() {
    try {
        const resp = await fetch('/api/telemetry');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        showError(null);
        updateCpu(data.cpu);
        updateRam(data.ram);
        updateDisk(data.disk);
        updateNetwork(data.network, data.timestamp);
        updateSystem(data.uptime_seconds, data.load_avg);
        updateLastUpdate(data.timestamp);
        
        if (data.history) {
            drawChart('chart-path-cpu', data.history.map(h => h.cpu_usage));
            drawChart('chart-path-ram', data.history.map(h => h.ram_usage));
        }
    } catch (err) {
        showError('SENSOR FEED INTERRUPTED — RETRYING... (' + err.message + ')');
    }
}

async function fetchAudit() {
    try {
        const res = await fetch('/api/telemetry/audit');
        if (!res.ok) return;
        const data = await res.json();
        const feed = document.getElementById('audit-feed');
        if (!feed) return;
        
        feed.innerHTML = data.events.map(e => {
            const time = e.created_at.split('T')[1].split('.')[0];
            return `
                <div class="audit-entry">
                    <span class="time">[${time}]</span>
                    <span class="type">${e.event_type.toUpperCase()}</span>
                    <span class="detail">${e.detail || ''}</span>
                </div>
            `;
        }).join('');
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
    fetchTelemetry();
    fetchAudit();
    setInterval(fetchTelemetry, REFRESH_INTERVAL_MS);
    setInterval(fetchAudit, 10000);
});
