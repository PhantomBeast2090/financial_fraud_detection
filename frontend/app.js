/* ── app.js — FraudGuard AI Frontend ─────────────────────── */
'use strict';

const API = 'http://127.0.0.1:8000';
let TOKEN = localStorage.getItem('fg_token') || '';
let USER_ROLE = localStorage.getItem('fg_role') || '';
let USER_NAME = localStorage.getItem('fg_user') || '';

// Chart references
let chartHourly = null, chartDonut = null, chartType = null,
    chartLocation = null, chartDaily = null;

// Simulator state
let _sseSource = null;
let _simActive = false;

/* ═══════════════════════════ HELPERS ═══════════════════════════ */
const $ = id => document.getElementById(id);
const fmt = n => '₹' + Number(n).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const pct = v => (v * 100).toFixed(1) + '%';
const timeSince = iso => {
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return s + 's ago';
  if (s < 3600) return Math.floor(s/60) + 'm ago';
  return Math.floor(s/3600) + 'h ago';
};

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (TOKEN) headers['Authorization'] = `Bearer ${TOKEN}`;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { doLogout(); throw new Error('Unauthorised'); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

/* ═══════════════════════════ AUTH ═══════════════════════════ */
function applySession() {
  if (!TOKEN) return;
  $('app-shell').classList.remove('hidden');
  $('page-login').classList.add('hidden');
  $('user-name-display').textContent = USER_NAME;
  $('user-role-display').textContent = USER_ROLE;
  $('user-initial').textContent = (USER_NAME[0] || 'U').toUpperCase();
  document.querySelectorAll('.admin-only').forEach(el =>
    el.style.display = USER_ROLE === 'admin' ? '' : 'none');
}

$('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('login-btn'), txt = $('login-btn-text'), spin = $('login-spinner'), err = $('login-error');
  txt.textContent = 'Signing in…'; spin.classList.remove('hidden'); btn.disabled = true; err.classList.add('hidden');
  try {
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('li-user').value, password: $('li-pass').value })
    });
    TOKEN = data.access_token; USER_ROLE = data.role; USER_NAME = data.username;
    localStorage.setItem('fg_token', TOKEN);
    localStorage.setItem('fg_role', USER_ROLE);
    localStorage.setItem('fg_user', USER_NAME);
    applySession();
    navigateTo('dashboard');
  } catch (ex) {
    err.textContent = ex.message; err.classList.remove('hidden');
  } finally {
    txt.textContent = 'Sign In'; spin.classList.add('hidden'); btn.disabled = false;
  }
});

function doLogout() {
  TOKEN = USER_ROLE = USER_NAME = '';
  localStorage.removeItem('fg_token'); localStorage.removeItem('fg_role'); localStorage.removeItem('fg_user');
  location.reload();
}
$('logout-btn').addEventListener('click', doLogout);

/* ═══════════════════════════ NAVIGATION ═══════════════════════════ */
function navigateTo(page) {
  document.querySelectorAll('.content-page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pg = $('page-' + page); if (pg) pg.classList.add('active');
  const ni = $('nav-' + page); if (ni) ni.classList.add('active');
  if (page === 'dashboard') loadDashboard();
  if (page === 'analytics') loadAnalytics();
  if (page === 'alerts') loadAlerts();
  if (page === 'review') loadReviewQueue();
  if (page === 'dbviewer') loadDBViewer();
  if (page === 'admin') loadAdmin();
}

document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', e => { e.preventDefault(); navigateTo(el.dataset.page); });
});

/* ═══════════════════════════ DASHBOARD ═══════════════════════════ */
async function loadDashboard() {
  try {
    const d = await api('/api/analytics/dashboard');
    $('kpi-total').textContent = d.total_transactions.toLocaleString();
    $('kpi-fraud').textContent = d.total_fraud.toLocaleString();
    $('kpi-legit').textContent = d.total_legitimate.toLocaleString();
    $('kpi-rate').textContent = d.fraud_rate.toFixed(1) + '%';
    $('alert-badge').textContent = d.total_alerts;
    $('kpi-amount-approved').textContent = fmt(d.amount_approved || 0);
    $('kpi-amount-blocked').textContent = fmt(d.amount_blocked || 0);
    renderFeed(d.recent_transactions);
    renderHourlyChart(d.hourly_trend);
    renderDonutChart(d.total_fraud, d.total_legitimate);
  } catch (ex) { console.warn('Dashboard load error:', ex.message); }
}

function renderFeed(txns) {
  const feed = $('live-feed'); feed.innerHTML = '';
  if (!txns.length) { feed.innerHTML = '<p style="color:var(--muted);text-align:center;padding:30px">No transactions yet.</p>'; return; }
  txns.forEach(t => {
    const isFraud = t.label === 'Fraud';
    const div = document.createElement('div');
    div.className = `feed-item ${isFraud ? 'fraud' : 'legit'}`;
    div.innerHTML = `
      <div class="fi-left">
        <span class="fi-amount">${fmt(t.amount)}</span>
        <span class="fi-meta">📍 ${t.location} · ${t.transaction_type}</span>
      </div>
      <div style="text-align:right">
        <span class="fi-badge ${isFraud ? 'fraud' : 'legit'}">${isFraud ? '🚨 Fraud' : '✅ Legit'}</span>
        <div class="fi-risk">${pct(t.fraud_probability || 0)} risk · ${timeSince(t.created_at)}</div>
      </div>`;
    feed.appendChild(div);
  });
}

function renderHourlyChart(data) {
  const ctx = $('chart-hourly').getContext('2d');
  if (chartHourly) chartHourly.destroy();
  const labels = data.map(d => String(d.hour).padStart(2,'0') + ':00');
  chartHourly = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Total', data: data.map(d => d.total), borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,.1)', tension: 0.4, fill: true, pointRadius: 3 },
        { label: 'Fraud', data: data.map(d => d.fraud), borderColor: '#ff4757', backgroundColor: 'rgba(255,71,87,.08)', tension: 0.4, fill: true, pointRadius: 3 },
      ]
    },
    options: chartOpts()
  });
}

function renderDonutChart(fraud, legit) {
  const ctx = $('chart-donut').getContext('2d');
  if (chartDonut) chartDonut.destroy();
  chartDonut = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Fraud', 'Legitimate'],
      datasets: [{ data: [fraud, legit], backgroundColor: ['rgba(255,71,87,.8)','rgba(0,229,160,.7)'],
                   borderColor: ['#ff4757','#00e5a0'], borderWidth: 2, hoverOffset: 8 }]
    },
    options: { ...chartOpts(), cutout: '70%', plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af', padding: 16, font: { size: 12 } } } } }
  });
}

/* ═══════════════════════════ PREDICT ═══════════════════════════ */
$('predict-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('predict-btn'), txt = $('predict-btn-text'), spin = $('predict-spinner');
  txt.textContent = 'Analyzing…'; spin.classList.remove('hidden'); btn.disabled = true;
  const payload = {
    account_id: parseInt($('pf-account').value),
    amount: parseFloat($('pf-amount').value),
    location: $('pf-location').value,
    transaction_type: $('pf-type').value,
    time_of_day: parseInt($('pf-time').value),
    distance_from_home: parseFloat($('pf-distance').value),
    device_trust_score: parseFloat($('pf-trust').value),
    failed_attempts_24h: parseInt($('pf-failed').value),
    txn_velocity_1h: parseInt($('pf-velocity').value),
    merchant_risk_score: parseFloat($('pf-mrisk').value),
    is_international: parseInt($('pf-intl').value),
    card_present: parseInt($('pf-card').value),
  };
  try {
    const r = await api('/api/transactions/predict', { method: 'POST', body: JSON.stringify(payload) });
    showResult(r);
  } catch (ex) { alert('Prediction error: ' + ex.message); }
  finally { txt.textContent = 'Analyze Transaction'; spin.classList.add('hidden'); btn.disabled = false; }
});

function showResult(r) {
  $('result-placeholder').classList.add('hidden');
  const card = $('result-card'); card.classList.remove('hidden');
  const isFraud = r.label === 'Fraud';
  const v = $('result-verdict');
  v.className = 'result-verdict ' + (isFraud ? 'fraud' : 'legit');
  v.innerHTML = isFraud ? '🚨 FRAUD DETECTED — Transaction Blocked' : '✅ LEGITIMATE — Transaction Approved';
  const prob = r.fraud_probability;
  $('gauge-pct').textContent = (prob * 100).toFixed(1) + '%';
  drawGauge(prob);
  const reasons = $('result-reasons'); reasons.innerHTML = '';
  (r.reasons || []).forEach(rs => {
    const d = document.createElement('div'); d.className = 'reason-pill'; d.textContent = rs;
    reasons.appendChild(d);
  });
  $('res-model').textContent = r.model_version || '—';
  $('res-status').textContent = r.status;
  $('res-risk').textContent = r.risk_level;
  $('res-risk').style.color = r.risk_level === 'High' ? 'var(--red)' : r.risk_level === 'Medium' ? 'var(--orange)' : 'var(--green)';
}

function drawGauge(prob) {
  const canvas = $('gauge-canvas'), ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const cx = canvas.width / 2, cy = canvas.height - 10;
  const R = 90, start = Math.PI, end = 2 * Math.PI;
  // Track
  ctx.beginPath(); ctx.arc(cx, cy, R, start, end);
  ctx.lineWidth = 14; ctx.lineCap = 'round'; ctx.strokeStyle = 'rgba(255,255,255,.08)'; ctx.stroke();
  // Fill
  const fillEnd = start + prob * Math.PI;
  const color = prob >= .75 ? '#ff4757' : prob >= .5 ? '#ffa502' : '#00e5a0';
  const grad = ctx.createLinearGradient(cx - R, cy, cx + R, cy);
  grad.addColorStop(0, '#00e5a0'); grad.addColorStop(0.5, '#ffa502'); grad.addColorStop(1, '#ff4757');
  ctx.beginPath(); ctx.arc(cx, cy, R, start, fillEnd);
  ctx.lineWidth = 14; ctx.lineCap = 'round'; ctx.strokeStyle = grad; ctx.stroke();
}

/* ═══════════════════════════ ANALYTICS ═══════════════════════════ */
async function loadAnalytics() {
  try {
    const [dash, metrics] = await Promise.all([
      api('/api/analytics/dashboard'),
      api('/api/analytics/model-metrics'),
    ]);
    // Metric strip
    const pct2 = v => v != null ? (v * 100).toFixed(1) + '%' : '—';
    $('m-accuracy').textContent = pct2(metrics.accuracy);
    $('m-precision').textContent = pct2(metrics.precision);
    $('m-recall').textContent = pct2(metrics.recall);
    $('m-f1').textContent = pct2(metrics.f1_score);
    $('m-auc').textContent = pct2(metrics.roc_auc);
    $('m-threshold').textContent = metrics.threshold != null ? metrics.threshold.toFixed(3) : '—';
    // Charts
    renderTypeChart(dash.fraud_by_type);
    renderLocationChart(dash.fraud_by_location);
    renderDailyChart(dash.daily_amounts);
    renderLeaderboard(metrics.leaderboard);
  } catch (ex) { console.warn('Analytics error:', ex.message); }
}

function renderTypeChart(data) {
  const ctx = $('chart-by-type').getContext('2d');
  if (chartType) chartType.destroy();
  const colors = ['#ff4757','#ffa502','#6366f1','#00e5a0','#2ed573','#a78bfa'];
  chartType = new Chart(ctx, {
    type: 'bar',
    data: { labels: data.map(d=>d.type), datasets: [{ label: 'Fraud Count', data: data.map(d=>d.count), backgroundColor: colors, borderRadius: 8 }] },
    options: { ...chartOpts(), plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,.05)' } }, y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,.05)' } } } }
  });
}

function renderLocationChart(data) {
  const ctx = $('chart-by-location').getContext('2d');
  if (chartLocation) chartLocation.destroy();
  chartLocation = new Chart(ctx, {
    type: 'bar',
    data: { labels: data.map(d=>d.location), datasets: [{ label: 'Fraud Count', data: data.map(d=>d.count), backgroundColor: 'rgba(99,102,241,.7)', borderRadius: 8, borderColor: '#6366f1', borderWidth: 1 }] },
    options: { ...chartOpts(), indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,.05)' } }, y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,.05)' } } } }
  });
}

function renderDailyChart(data) {
  const ctx = $('chart-daily').getContext('2d');
  if (chartDaily) chartDaily.destroy();
  chartDaily = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.day),
      datasets: [
        { label: 'Volume (₹)', data: data.map(d=>d.total), borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,.1)', tension: 0.4, fill: true, yAxisID: 'y' },
        { label: 'Risk Sum', data: data.map(d=>d.risk_sum), borderColor: '#ff4757', backgroundColor: 'rgba(255,71,87,.05)', tension: 0.4, fill: true, yAxisID: 'y1' },
      ]
    },
    options: { ...chartOpts(), scales: { y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,.05)' }, position: 'left' }, y1: { ticks: { color: '#9ca3af' }, grid: { drawOnChartArea: false }, position: 'right' }, x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,.05)' } } } }
  });
}

function renderLeaderboard(rows) {
  const el = $('leaderboard-table');
  if (!rows || !rows.length) { el.innerHTML = '<p style="color:var(--muted);padding:20px">No leaderboard data yet.</p>'; return; }
  let html = '<table><thead><tr><th>Model</th><th>Avg Precision</th><th>Recall</th><th>Precision</th><th>F1</th><th>Threshold</th><th>Score</th></tr></thead><tbody>';
  rows.forEach((r, i) => {
    const m = r.metrics || {};
    html += `<tr class="${i===0?'best':''}"><td>${r.name}</td><td>${(m.average_precision||0).toFixed(4)}</td><td>${(m.recall||0).toFixed(4)}</td><td>${(m.precision||0).toFixed(4)}</td><td>${(m.f1||0).toFixed(4)}</td><td>${(m.threshold||0).toFixed(3)}</td><td>${(r.score||0).toFixed(4)}</td></tr>`;
  });
  el.innerHTML = html + '</tbody></table>';
}

/* ═══════════════════════════ ALERTS ═══════════════════════════ */
async function loadAlerts() {
  try {
    const alerts = await api('/api/analytics/alerts');
    const el = $('alerts-list'); el.innerHTML = '';
    if (!alerts.length) { el.innerHTML = '<p style="color:var(--muted);padding:30px 0">No alerts found.</p>'; return; }
    $('alert-badge').textContent = alerts.filter(a => !a.is_resolved).length;
    alerts.forEach(a => {
      const div = document.createElement('div'); div.className = 'alert-row';
      div.innerHTML = `
        <span class="risk-badge ${a.risk_level}">${a.risk_level}</span>
        <div class="alert-info">
          <div class="alert-txn">TXN: ${a.transaction_id}</div>
          <div class="alert-reason">${a.reason}</div>
        </div>
        <span class="alert-time">${timeSince(a.created_at)}</span>
        ${USER_ROLE === 'admin' && !a.is_resolved ? `<button class="alert-resolve" onclick="resolveAlert(${a.id}, this)">Resolve</button>` : a.is_resolved ? '<span style="color:var(--green);font-size:.8rem">✓ Resolved</span>' : ''}`;
      el.appendChild(div);
    });
  } catch (ex) { console.warn('Alerts error:', ex.message); }
}

async function resolveAlert(id, btn) {
  try { await api(`/api/analytics/alerts/${id}/resolve`, { method: 'POST' }); btn.textContent = '✓ Resolved'; btn.disabled = true; btn.style.opacity = '.5'; }
  catch (ex) { alert('Error: ' + ex.message); }
}
window.resolveAlert = resolveAlert;

/* ═══════════════════════════ ADMIN ═══════════════════════════ */
async function loadAdmin() {
  try {
    const info = await api('/api/model/info');
    const el = $('admin-model-info');
    el.innerHTML = `
      <div class="info-row"><span>Model</span><strong>${info.model_name || '—'}</strong></div>
      <div class="info-row"><span>Version</span><strong>${info.model_version || '—'}</strong></div>
      <div class="info-row"><span>Threshold</span><strong>${info.threshold != null ? info.threshold.toFixed(4) : '—'}</strong></div>
      <div class="info-row"><span>Training Rows</span><strong>${(info.training_rows||0).toLocaleString()}</strong></div>`;
    loadTrainHistory();
  } catch (ex) { $('admin-model-info').innerHTML = '<p style="color:var(--muted)">Could not load model info.</p>'; }
}

async function loadTrainHistory() {
  try {
    const runs = await api('/api/model/history');
    const el = $('train-history-table');
    if (!runs.length) { el.innerHTML = '<p style="color:var(--muted);padding:16px">No training runs recorded yet.</p>'; return; }
    let html = '<table><thead><tr><th>#</th><th>Model</th><th>Accuracy</th><th>F1</th><th>ROC-AUC</th><th>Rows</th><th>By</th><th>When</th></tr></thead><tbody>';
    runs.forEach((r, i) => {
      html += `<tr><td>#${r.id}</td><td>${r.model_name}</td><td>${r.accuracy != null ? (r.accuracy*100).toFixed(2)+'%' : '—'}</td><td>${r.f1_score != null ? (r.f1_score*100).toFixed(2)+'%' : '—'}</td><td>${r.roc_auc != null ? (r.roc_auc*100).toFixed(2)+'%' : '—'}</td><td>${(r.training_rows||0).toLocaleString()}</td><td>${r.trained_by||'—'}</td><td>${r.trained_at ? new Date(r.trained_at+'Z').toLocaleString() : '—'}</td></tr>`;
    });
    el.innerHTML = html + '</tbody></table>';
  } catch (ex) { $('train-history-table').innerHTML = '<p style="color:var(--muted);padding:16px">Admin access required.</p>'; }
}

$('retrain-btn').addEventListener('click', async () => {
  const btn = $('retrain-btn'), status = $('train-status');
  btn.disabled = true; btn.textContent = '⏳ Triggering…';
  status.className = 'train-status running'; status.classList.remove('hidden');
  status.textContent = '🔄 Training started in background. This may take 1–3 minutes…';
  try {
    await api('/api/model/train', { method: 'POST' });
    pollTrainStatus();
  } catch (ex) {
    status.className = 'train-status error'; status.textContent = '❌ Error: ' + ex.message;
    btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15A9 9 0 1118.74 7.64"/></svg> Trigger Retraining';
  }
});

async function pollTrainStatus() {
  const status = $('train-status'), btn = $('retrain-btn');
  const interval = setInterval(async () => {
    try {
      const s = await api('/api/model/status');
      if (s.running) {
        status.className = 'train-status running';
        status.textContent = '🔄 Training in progress…';
      } else {
        clearInterval(interval);
        btn.disabled = false;
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15A9 9 0 1118.74 7.64"/></svg> Trigger Retraining';
        if (s.last_result?.success) {
          status.className = 'train-status success';
          const tm = s.last_result.test_metrics || {};
          status.innerHTML = `✅ Training complete! Model: <strong>${s.last_result.model_name}</strong> · Accuracy: ${tm.accuracy != null ? (tm.accuracy*100).toFixed(2)+'%' : '—'} · F1: ${tm.f1 != null ? (tm.f1*100).toFixed(2)+'%' : '—'}`;
          loadAdmin();
        } else {
          status.className = 'train-status error';
          status.textContent = '❌ Training failed: ' + (s.last_result?.error || 'Unknown error');
        }
      }
    } catch { clearInterval(interval); }
  }, 4000);
}

/* ══════════════════════════════ SIMULATOR ══════════════════════════════ */
function startSimulator() {
  if (_sseSource) return;
  _simActive = true;
  const btn = $('sim-toggle-btn'), label = $('sim-toggle-label');
  btn.classList.remove('sim-off'); btn.classList.add('sim-on');
  label.textContent = 'Auto-Feed Running…';

  // Open SSE connection — each event is a fully-processed transaction from the backend
  _sseSource = new EventSource(`${API}/api/simulate/stream?token=${encodeURIComponent(TOKEN)}`);

  _sseSource.onmessage = (e) => {
    try {
      const t = JSON.parse(e.data);
      if (t.error) return;
      // Prepend to live feed
      prependFeedItem(t);
      // Update KPI counts (lightweight, no full reload)
      const kpiTotal = $('kpi-total');
      if (kpiTotal && kpiTotal.textContent !== '—') {
        kpiTotal.textContent = (parseInt(kpiTotal.textContent.replace(/,/g,''))||0) + 1;
      }
      // If fraud, bump badge and possibly add to review queue badge
      if (t.label === 'Fraud') {
        const badge = $('alert-badge');
        badge.textContent = (parseInt(badge.textContent)||0) + 1;
        const rb = $('review-badge');
        rb.textContent = (parseInt(rb.textContent)||0) + 1;
      }
    } catch { /* ignore parse error */ }
  };

  _sseSource.onerror = () => { stopSimulator(); };
}

function stopSimulator() {
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  _simActive = false;
  const btn = $('sim-toggle-btn'), label = $('sim-toggle-label');
  btn.classList.remove('sim-on'); btn.classList.add('sim-off');
  label.textContent = 'Start Auto-Feed';
}

function prependFeedItem(t) {
  const feed = $('live-feed');
  if (!feed) return;
  const isFraud = t.label === 'Fraud';
  const div = document.createElement('div');
  div.className = `feed-item ${isFraud ? 'fraud' : 'legit'}`;
  div.innerHTML = `
    <div class="fi-left">
      <span class="fi-amount">${fmt(t.amount)}</span>
      <span class="fi-meta">📍 ${t.location} · ${t.transaction_type} · Acct #${t.account_id}</span>
    </div>
    <div style="text-align:right">
      <span class="fi-badge ${isFraud ? 'fraud' : 'legit'}">${isFraud ? '🚨 Fraud' : '✅ Legit'}</span>
      <div class="fi-risk">${pct(t.fraud_probability)} risk · now</div>
    </div>`;
  feed.prepend(div);
  // Keep feed trimmed to 50 items
  while (feed.children.length > 50) feed.lastChild.remove();
}

$('sim-toggle-btn').addEventListener('click', () => {
  if (_simActive) stopSimulator(); else startSimulator();
});

/* ══════════════════════════════ REVIEW QUEUE ═════════════════════════════ */
async function loadReviewQueue() {
  try {
    const items = await api('/api/review/queue');
    const list = $('review-list'), empty = $('review-empty');
    list.innerHTML = '';
    if (!items.length) {
      empty.classList.remove('hidden'); return;
    }
    empty.classList.add('hidden');
    $('review-badge').textContent = items.length;
    items.forEach(t => {
      const card = document.createElement('div');
      card.className = 'review-card';
      card.id = `rc-${t.transaction_id}`;
      const reasons = (t.reasons || []).map(r => `<div class="review-reason">${r}</div>`).join('');
      const riskColor = t.risk_level === 'High' ? 'var(--red)' : t.risk_level === 'Medium' ? 'var(--orange)' : 'var(--green)';
      card.innerHTML = `
        <div class="review-left">
          <div class="review-txn-id">${t.transaction_id}</div>
          <div class="review-amount" style="color:var(--red)">${fmt(t.amount)}</div>
          <div class="review-meta">
            <span class="review-meta-item">📍 ${t.location}</span>
            <span class="review-meta-item">💳 ${t.transaction_type}</span>
            <span class="review-meta-item">🕒 ${t.time_of_day}:00</span>
            <span class="review-meta-item">🌐 ${t.is_international ? 'International' : 'Domestic'}</span>
            <span class="review-meta-item" style="color:${riskColor}">⚠ ${t.risk_level} Risk • ${(t.fraud_probability*100).toFixed(1)}%</span>
          </div>
          <div class="review-reasons">${reasons}</div>
          <div class="review-risk-bar" style="width:${Math.round(t.fraud_probability*100)}%"></div>
        </div>
        <div class="review-actions">
          <button class="btn-approve" onclick="reviewAction('${t.transaction_id}','approve',this)">✅ Approve</button>
          <button class="btn-reject" onclick="reviewAction('${t.transaction_id}','reject',this)">❌ Reject</button>
        </div>`;
      list.appendChild(card);
    });
  } catch (ex) { console.warn('Review queue error:', ex.message); }
}

async function reviewAction(txnId, action, btn) {
  btn.disabled = true; btn.textContent = action === 'approve' ? 'Approving…' : 'Rejecting…';
  try {
    const r = await api(`/api/review/${txnId}/${action}`, { method: 'POST' });
    const card = $(`rc-${txnId}`);
    if (card) {
      card.style.opacity = '.4';
      card.style.pointerEvents = 'none';
      const actions = card.querySelector('.review-actions');
      actions.innerHTML = `<div style="color:${action==='approve'?'var(--green)':'var(--red)'}; font-weight:700; padding:8px">${action==='approve'?'✅ Approved':'❌ Rejected'}</div>`;
    }
    const rb = $('review-badge');
    const n = parseInt(rb.textContent) - 1;
    rb.textContent = Math.max(0, n);
  } catch (ex) { btn.disabled = false; alert('Error: ' + ex.message); }
}
window.reviewAction = reviewAction;

$('review-refresh-btn').addEventListener('click', loadReviewQueue);

/* ══════════════════════════════ DB VIEWER ═══════════════════════════════ */
let _dbCurrentTable = null;
let _dbCurrentPage  = 1;

async function loadDBViewer() {
  try {
    const tables = await api('/api/db/tables');
    const pills = $('db-table-pills');
    pills.innerHTML = '';
    tables.forEach(t => {
      const pill = document.createElement('button');
      pill.className = 'db-pill' + (_dbCurrentTable === t.table ? ' active' : '');
      pill.dataset.table = t.table;
      pill.innerHTML = `${t.table} <span class="db-pill-count">${t.rows.toLocaleString()}</span>`;
      pill.addEventListener('click', () => {
        _dbCurrentTable = t.table; _dbCurrentPage = 1;
        document.querySelectorAll('.db-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        loadDBTable(t.table, 1);
      });
      pills.appendChild(pill);
    });
    if (tables.length && !_dbCurrentTable) {
      _dbCurrentTable = tables[0].table;
      pills.children[0]?.classList.add('active');
      loadDBTable(_dbCurrentTable, 1);
    } else if (_dbCurrentTable) {
      loadDBTable(_dbCurrentTable, _dbCurrentPage);
    }
  } catch (ex) { console.warn('DB Viewer:', ex.message); }
}

async function loadDBTable(tableName, page) {
  $('db-grid-wrap').innerHTML = '<p style="padding:28px;color:var(--muted);text-align:center">⏳ Loading…</p>';
  try {
    const d = await api(`/api/db/table/${encodeURIComponent(tableName)}?page=${page}&page_size=50`);
    _dbCurrentTable = tableName; _dbCurrentPage = page;
    const bar = $('db-stats-bar');
    bar.classList.remove('hidden');
    $('db-stat-table').innerHTML = `Table: <strong>${d.table}</strong>`;
    $('db-stat-rows').innerHTML  = `Rows: <strong>${d.total.toLocaleString()}</strong>`;
    $('db-stat-cols').innerHTML  = `Columns: <strong>${d.columns.length}</strong>`;
    $('db-page-info').textContent = `Page ${d.page} / ${d.total_pages}`;
    $('db-prev-btn').disabled = d.page <= 1;
    $('db-next-btn').disabled = d.page >= d.total_pages;

    let html = '<table><thead><tr>';
    d.columns.forEach(c => { html += `<th>${c}</th>`; });
    html += '</tr></thead><tbody>';
    if (!d.rows.length) {
      html += `<tr><td colspan="${d.columns.length}" style="text-align:center;padding:30px;color:var(--muted)">No rows found.</td></tr>`;
    } else {
      d.rows.forEach(row => {
        html += '<tr>';
        d.columns.forEach((c, i) => {
          const val = row[c];
          if (val === null || val === undefined) {
            html += `<td><span class="db-null">NULL</span></td>`;
          } else {
            const s = String(val);
            const display = s.length > 60 ? s.substring(0, 60) + '…' : s;
            html += `<td class="${i === 0 ? 'db-pk' : ''}" title="${s.replace(/"/g,'&quot;')}">${display}</td>`;
          }
        });
        html += '</tr>';
      });
    }
    html += '</tbody></table>';
    $('db-grid-wrap').innerHTML = html;
  } catch (ex) {
    $('db-grid-wrap').innerHTML = `<p style="padding:24px;color:var(--red)">Error: ${ex.message}</p>`;
  }
}

$('db-prev-btn').addEventListener('click', () => {
  if (_dbCurrentPage > 1) loadDBTable(_dbCurrentTable, _dbCurrentPage - 1);
});
$('db-next-btn').addEventListener('click', () => {
  loadDBTable(_dbCurrentTable, _dbCurrentPage + 1);
});
$('db-refresh-btn').addEventListener('click', () => { _dbCurrentTable = null; loadDBViewer(); });

/* ══════════════════════════════ CSV EXPORT ═════════════════════════════ */
$('export-csv-btn').addEventListener('click', async () => {
  try {
    const res = await fetch(API + '/api/analytics/export/csv', {
      headers: { 'Authorization': `Bearer ${TOKEN}` }
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'fraud_report.csv'; a.click();
    URL.revokeObjectURL(url);
  } catch { alert('Export failed. Please try again.'); }
});

/* ═══════════════════════════ CHART DEFAULTS ═══════════════════════════ */
function chartOpts() {
  return {
    responsive: true, maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#9ca3af', font: { size: 12 }, padding: 14 } }, tooltip: { backgroundColor: '#1a1f2e', titleColor: '#e8eaf0', bodyColor: '#9ca3af', borderColor: 'rgba(255,255,255,.1)', borderWidth: 1 } },
    scales: { x: { ticks: { color: '#9ca3af', font: { size: 11 } }, grid: { color: 'rgba(255,255,255,.05)' } }, y: { ticks: { color: '#9ca3af', font: { size: 11 } }, grid: { color: 'rgba(255,255,255,.05)' } } }
  };
}

/* ═══════════════════════════ AUTO-REFRESH ═══════════════════════════ */
setInterval(() => {
  const activePage = document.querySelector('.content-page.active');
  if (activePage?.id === 'page-dashboard') loadDashboard();
}, 10000);

/* ═══════════════════════════ INIT ═══════════════════════════ */
if (TOKEN) { applySession(); navigateTo('dashboard'); }
