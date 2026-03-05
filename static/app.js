/**
 * MH-1 Signal Dashboard — Frontend Logic
 */

const API = '';  // Same origin

// ═══════════════════════════════════════════════════════════════════════════════
//  State
// ═══════════════════════════════════════════════════════════════════════════════
let state = {
  signals: [],
  approved: [],
  enriched: [],
  allSources: {},
  processing: false,
  sourceFilter: null,  // null = all, or a Set of active source names
};

// ═══════════════════════════════════════════════════════════════════════════════
//  Utilities
// ═══════════════════════════════════════════════════════════════════════════════

function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const colors = {
    success: 'bg-emerald-600', error: 'bg-red-600',
    info: 'bg-orange-500', warning: 'bg-amber-500'
  };
  const el = document.createElement('div');
  el.className = `toast ${colors[type] || colors.info} text-white px-4 py-2 rounded-lg shadow-lg text-sm`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function scoreColor(score) {
  if (score >= 80) return 'score-high';
  if (score >= 60) return 'score-mid';
  return 'score-low';
}

function scoreHexColor(score) {
  if (score >= 80) return '#16a34a';
  if (score >= 60) return '#ea580c';
  return '#dc2626';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, len = 220) {
  if (!str) return '';
  return str.length > len ? str.slice(0, len) + '…' : str;
}

async function api(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function setProcessing(active, label = 'Processing…') {
  state.processing = active;
  const el = document.getElementById('process-status');
  const lbl = document.getElementById('process-label');
  if (active) {
    el.classList.remove('hidden');
    el.classList.add('flex');
    lbl.textContent = label;
  } else {
    el.classList.add('hidden');
    el.classList.remove('flex');
  }
  // Disable action buttons
  document.querySelectorAll('#btn-collect, #btn-enrich').forEach(b => b.disabled = active);
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => toast('Copied!', 'success')).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); toast('Copied!', 'success'); }
    catch { toast('Failed to copy', 'error'); }
    document.body.removeChild(ta);
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Tab Navigation
// ═══════════════════════════════════════════════════════════════════════════════

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
    document.getElementById(`tab-${tab}`).classList.remove('hidden');

    // Refresh data when switching tabs
    if (tab === 'approved') loadApproved();
    if (tab === 'enriched') loadEnriched();
    if (tab === 'sources') loadSourcesConfig();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
//  Slider value displays
// ═══════════════════════════════════════════════════════════════════════════════

['limit', 'days', 'min-engagement', 'threshold'].forEach(id => {
  const el = document.getElementById(id);
  const valId = id === 'min-engagement' ? 'engage-val' : `${id}-val`;
  const valEl = document.getElementById(valId);
  if (el && valEl) {
    el.addEventListener('input', () => valEl.textContent = el.value);
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
//  Source Checkboxes
// ═══════════════════════════════════════════════════════════════════════════════

async function initSources() {
  try {
    state.allSources = await api('GET', '/api/sources/all');
    const container = document.getElementById('source-checkboxes');
    container.innerHTML = '';
    for (const [key, label] of Object.entries(state.allSources)) {
      container.innerHTML += `
        <label class="flex items-center gap-1.5 text-sm">
          <input type="checkbox" class="source-cb checkbox-custom" value="${key}" checked>
          <span>${escapeHtml(label)}</span>
        </label>`;
    }
  } catch (e) {
    console.error('Failed to load sources:', e);
  }
}

function getSelectedSources() {
  return Array.from(document.querySelectorAll('.source-cb:checked')).map(cb => cb.value);
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Signal Card Rendering
// ═══════════════════════════════════════════════════════════════════════════════

function renderSignalCard(sig, index, mode = 'collect') {
  const rk = sig.ranking || {};
  const sc = rk.total_score || 0;
  const scores = rk.scores || {};
  const newsType = rk.news_type || 'unknown';
  const summary = rk.news_summary || '';
  const source = sig.collection_source || sig.type || '';
  const url = sig.url || '';
  const title = sig.title || 'Untitled';
  const content = sig.content || '';
  const datePosted = sig.date_posted || '';
  const id = sig.id || '';

  const isApproved = state.approved.some(a => a.id === id);
  const icp = scores.icp_interest || scores.context_relevance || scores.is_news || 0;
  const timeliness = scores.timeliness || 0;
  const newsQuality = scores.news_quality || scores.marketing_relevance || 0;

  let actionButtons = '';
  if (mode === 'collect') {
    if (isApproved) {
      actionButtons = `<span class="text-emerald-600 text-sm font-medium">✅ Approved</span>`;
    } else {
      actionButtons = `<button class="btn btn-secondary text-xs py-1 px-3" onclick="approveSignal('${id}')">✅ Approve</button>`;
    }
  } else if (mode === 'approved') {
    actionButtons = `
      <button class="btn btn-secondary text-xs py-1 px-3" onclick="copyToClipboard('${escapeHtml(url)}')">📋 Copy</button>
      <button class="btn btn-danger text-xs py-1 px-3" onclick="removeApproved('${id}')">❌ Remove</button>
    `;
  }

  const openLink = url && url !== '#'
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="btn btn-secondary text-xs py-1 px-3 no-underline inline-block">🔗 Open</a>`
    : '';

  return `
    <div class="card p-4 mb-3">
      <!-- Preview row: always visible -->
      <div class="flex items-start gap-4">
        <div class="text-2xl font-bold ${scoreColor(sc)} flex-shrink-0 w-12 text-center" style="color:${scoreHexColor(sc)}">${Math.round(sc)}</div>
        <div class="flex-1 min-w-0">
          <div class="font-semibold text-sm mb-1">${escapeHtml(truncate(title, 100))}</div>
          <div class="flex gap-1.5 mb-1">
            <span class="badge badge-source">${escapeHtml(source)}</span>
            <span class="badge badge-type">${escapeHtml(newsType)}</span>
          </div>
          ${summary ? `<p class="text-xs text-gray-500 leading-relaxed">${escapeHtml(truncate(summary, 400))}</p>` : ''}
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          ${actionButtons}
          ${openLink}
        </div>
      </div>

      <!-- Details dropdown -->
      <details class="mt-3">
        <summary class="text-xs text-gray-400 font-medium py-1">Details</summary>
        <div class="mt-2 pt-2 border-t border-gray-200">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="md:col-span-3">
              ${content ? `<p class="text-xs text-gray-500 mb-2"><strong class="text-gray-700">Article Content:</strong><br>${escapeHtml(truncate(content, 500))}</p>` : ''}
              ${datePosted ? `<p class="text-xs text-gray-400">📅 Posted: ${escapeHtml(datePosted)}</p>` : ''}
              ${sig.approved_at ? `<p class="text-xs text-gray-400">✅ Approved: ${escapeHtml(sig.approved_at.slice(0, 19))}</p>` : ''}
            </div>
            <div>
              <p class="text-xs text-gray-600">🎯 ICP Interest: <strong>${icp}</strong></p>
              <p class="text-xs text-gray-600">⏰ Timeliness: <strong>${timeliness}</strong></p>
              <p class="text-xs text-gray-600">📰 News Quality: <strong>${newsQuality}</strong></p>
            </div>
          </div>
        </div>
      </details>
    </div>`;
}

function renderEnrichedCard(sd, index) {
  const orig = sd.original_signal || {};
  const enr = sd.enrichment || {};
  const rk = orig.ranking || {};
  const sc = rk.total_score || 0;
  const source = orig.collection_source || '';
  const url = orig.url || '';
  const title = orig.title || 'Untitled';
  const newsType = rk.news_type || '';
  const hasFailed = !enr || Object.keys(enr).length === 0;

  if (hasFailed) {
    return `
      <div class="card p-4 mb-3 border-red-200">
        <div class="flex items-start gap-4">
          <div class="text-2xl font-bold text-red-500 flex-shrink-0 w-12 text-center">${Math.round(sc)}</div>
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-sm mb-1">❌ ${escapeHtml(truncate(title, 80))}</div>
            <div class="flex gap-1.5 mb-1">
              <span class="badge badge-source">${escapeHtml(source)}</span>
            </div>
            <p class="text-xs text-red-500">${escapeHtml(sd.error || 'Unknown error')}</p>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            ${url ? `<a href="${escapeHtml(url)}" target="_blank" class="btn btn-secondary text-xs py-1 px-3 no-underline inline-block">🔗 Open</a>` : ''}
          </div>
        </div>
      </div>`;
  }

  const impact = enr.market_impact || {};
  const angles = enr.content_angles || [];
  const dataPts = enr.key_data_points || [];
  const talkPts = enr.founder_talking_points || [];
  const related = (enr.related_sources || []).slice(0, 5);

  return `
    <div class="card p-4 mb-3">
      <div class="flex items-start gap-4">
        <div class="text-2xl font-bold ${scoreColor(sc)} flex-shrink-0 w-12 text-center" style="color:${scoreHexColor(sc)}">${Math.round(sc)}</div>
        <div class="flex-1 min-w-0">
          <div class="font-semibold text-sm mb-1">✅ ${escapeHtml(truncate(title, 80))}</div>
          <div class="flex gap-1.5 mb-1">
            <span class="badge badge-source">${escapeHtml(source)}</span>
            <span class="badge badge-type">${escapeHtml(newsType)}</span>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          ${url ? `<a href="${escapeHtml(url)}" target="_blank" class="btn btn-secondary text-xs py-1 px-3 no-underline inline-block">🔗 Open</a>` : ''}
        </div>
      </div>

      <details class="mt-3" ${index < 2 ? 'open' : ''}>
        <summary class="text-xs text-gray-400 font-medium py-1">Enrichment Details</summary>
        <div class="mt-2 pt-2 border-t border-gray-200 space-y-3">
          <!-- Research Summary -->
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">Research Summary</h4>
            <p class="text-xs text-gray-500">${escapeHtml(enr.deep_research_summary || 'N/A')}</p>
          </div>

          <!-- Key Data Points -->
          ${dataPts.length ? `
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">Key Data Points</h4>
            <ul class="text-xs text-gray-500 list-disc list-inside">${dataPts.map(dp => `<li>${escapeHtml(dp)}</li>`).join('')}</ul>
          </div>` : ''}

          <!-- Market Impact -->
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">Market Impact</h4>
            <div class="grid grid-cols-3 gap-2 text-xs">
              <div><strong class="text-gray-700">CMOs:</strong> <span class="text-gray-500">${escapeHtml(impact.for_cmos || 'N/A')}</span></div>
              <div><strong class="text-gray-700">Growth Teams:</strong> <span class="text-gray-500">${escapeHtml(impact.for_growth_teams || 'N/A')}</span></div>
              <div><strong class="text-gray-700">Agencies:</strong> <span class="text-gray-500">${escapeHtml(impact.for_agencies || 'N/A')}</span></div>
            </div>
          </div>

          <!-- MH-1 Angle -->
          ${enr.mh1_angle ? `
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">MH-1 Angle</h4>
            <div class="bg-orange-50 border border-orange-200 rounded p-2 text-xs text-orange-700">${escapeHtml(enr.mh1_angle)}</div>
          </div>` : ''}

          <!-- Talking Points -->
          ${talkPts.length ? `
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">Talking Points</h4>
            <ol class="text-xs text-gray-500 list-decimal list-inside">${talkPts.map(tp => `<li>${escapeHtml(tp)}</li>`).join('')}</ol>
          </div>` : ''}

          <!-- Content Angles -->
          ${angles.length ? `
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">Content Angles</h4>
            ${angles.map((a, i) => `
              <div class="mb-2 text-xs">
                <strong class="text-gray-700">Angle ${i + 1}:</strong> ${escapeHtml(a.hook || '')}
                <br><span class="text-gray-500">Message: ${escapeHtml(a.key_message || '')}</span>
                <br><span class="text-gray-500">CTA: ${escapeHtml(a.cta_direction || '')}</span>
              </div>`).join('')}
          </div>` : ''}

          <!-- Related Sources -->
          ${related.length ? `
          <div>
            <h4 class="text-xs font-semibold text-gray-700 mb-1">Related Sources</h4>
            <ul class="text-xs text-gray-500">${related.map(l => `<li><a href="${escapeHtml(l)}" target="_blank" class="text-orange-500 hover:text-orange-600">${escapeHtml(truncate(l, 60))}</a></li>`).join('')}</ul>
          </div>` : ''}

          <p class="text-xs text-gray-400">Enriched at: ${escapeHtml(sd.enriched_at || 'Unknown')}</p>
        </div>
      </details>
    </div>`;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Data Loading
// ═══════════════════════════════════════════════════════════════════════════════

async function loadSignals() {
  try {
    const threshold = parseInt(document.getElementById('threshold').value);
    const data = await api('GET', `/api/signals?min_score=${threshold}`);
    state.signals = data.signals || [];
    // Also refresh approved
    const appData = await api('GET', '/api/signals/approved');
    state.approved = appData.signals || [];
    renderSignals();
    updateApprovedBadge();
    toast(`Loaded ${state.signals.length} signals`, 'success');
  } catch (e) {
    toast('Failed to load signals: ' + e.message, 'error');
  }
}

async function loadApproved() {
  try {
    const data = await api('GET', '/api/signals/approved');
    state.approved = data.signals || [];
    renderApproved();
    updateApprovedBadge();
  } catch (e) {
    toast('Failed to load approved: ' + e.message, 'error');
  }
}

async function loadEnriched() {
  try {
    const data = await api('GET', '/api/enriched');
    state.enriched = data.signals || [];
    renderEnriched(data.ok_count || 0, data.fail_count || 0);
  } catch (e) {
    toast('Failed to load enriched: ' + e.message, 'error');
  }
}

function updateApprovedBadge() {
  document.getElementById('approved-count-badge').textContent = state.approved.length;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Source Filter
// ═══════════════════════════════════════════════════════════════════════════════

function buildSourceFilterPills() {
  const filterContainer = document.getElementById('source-filter');
  const pillsContainer = document.getElementById('source-filter-pills');

  // Extract unique sources from current signals
  const sources = [...new Set(state.signals.map(s => s.collection_source || s.type || 'unknown'))].sort();

  if (sources.length <= 1) {
    filterContainer.classList.add('hidden');
    return;
  }

  filterContainer.classList.remove('hidden');

  // Count signals per source (above threshold)
  const threshold = parseInt(document.getElementById('threshold').value);
  const counts = {};
  for (const s of state.signals) {
    if ((s.ranking?.total_score || 0) >= threshold) {
      const src = s.collection_source || s.type || 'unknown';
      counts[src] = (counts[src] || 0) + 1;
    }
  }

  // Build pills
  pillsContainer.innerHTML = sources.map(src => {
    const count = counts[src] || 0;
    const isActive = !state.sourceFilter || state.sourceFilter.has(src);
    const cls = isActive
      ? 'bg-orange-100 text-orange-700 border-orange-300'
      : 'bg-gray-100 text-gray-400 border-gray-200';
    return `<button class="text-xs py-0.5 px-2.5 rounded-full border transition-colors ${cls}" onclick="toggleSourceFilter('${escapeHtml(src)}')">${escapeHtml(src)} <span class="opacity-60">(${count})</span></button>`;
  }).join('');

  // Update "All" button style
  const allBtn = filterContainer.querySelector('.source-filter-all');
  if (!state.sourceFilter) {
    allBtn.className = 'source-filter-all btn text-xs py-0.5 px-2.5 rounded-full bg-orange-500 text-white border border-orange-500';
  } else {
    allBtn.className = 'source-filter-all btn text-xs py-0.5 px-2.5 rounded-full bg-gray-100 text-gray-500 border border-gray-200';
  }
}

function setSourceFilter(source) {
  if (!source) {
    state.sourceFilter = null; // Show all
  } else {
    state.sourceFilter = new Set([source]);
  }
  renderSignals();
}

function toggleSourceFilter(source) {
  const sources = [...new Set(state.signals.map(s => s.collection_source || s.type || 'unknown'))];

  if (!state.sourceFilter) {
    // Currently "All" — switch to only this source
    state.sourceFilter = new Set([source]);
  } else if (state.sourceFilter.has(source)) {
    // Deselect this source
    state.sourceFilter.delete(source);
    if (state.sourceFilter.size === 0) {
      state.sourceFilter = null; // All deselected → show all
    }
  } else {
    // Select this source too
    state.sourceFilter.add(source);
    // If all sources now selected, reset to null (all)
    if (state.sourceFilter.size >= sources.length) {
      state.sourceFilter = null;
    }
  }
  renderSignals();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Render functions
// ═══════════════════════════════════════════════════════════════════════════════

function renderSignals() {
  const threshold = parseInt(document.getElementById('threshold').value);
  let filtered = state.signals.filter(s => (s.ranking?.total_score || 0) >= threshold);

  // Apply source filter
  if (state.sourceFilter) {
    filtered = filtered.filter(s => state.sourceFilter.has(s.collection_source || s.type || 'unknown'));
  }

  filtered.sort((a, b) => (b.ranking?.total_score || 0) - (a.ranking?.total_score || 0));

  const totalAboveThreshold = state.signals.filter(s => (s.ranking?.total_score || 0) >= threshold).length;
  const filterNote = state.sourceFilter ? ` (filtered ${filtered.length} of ${totalAboveThreshold})` : '';
  document.getElementById('signals-header').textContent =
    `Ranked Signals — ${totalAboveThreshold} of ${state.signals.length} ≥ ${threshold}${filterNote}`;

  // Rebuild filter pills (to update counts and active states)
  buildSourceFilterPills();

  const container = document.getElementById('signals-list');
  if (!filtered.length) {
    container.innerHTML = '<p class="text-sm text-gray-400 text-center py-8">No signals above threshold. Collect signals or lower the threshold.</p>';
    return;
  }
  container.innerHTML = filtered.map((sig, i) => renderSignalCard(sig, i, 'collect')).join('');
}

function renderApproved() {
  const container = document.getElementById('approved-list');
  const summary = document.getElementById('approved-summary');
  if (!state.approved.length) {
    summary.textContent = 'No approved signals yet. Approve signals from the Collect & Rank tab.';
    container.innerHTML = '';
    return;
  }
  summary.textContent = `${state.approved.length} signals approved`;
  container.innerHTML = state.approved.map((sig, i) => renderSignalCard(sig, i, 'approved')).join('');
}

function renderEnriched(okCount, failCount) {
  const container = document.getElementById('enriched-list');
  const summary = document.getElementById('enriched-summary');
  const retryBtn = document.getElementById('btn-retry');

  if (!state.enriched.length) {
    summary.textContent = 'No enriched signals yet. Approve signals and run enrichment.';
    container.innerHTML = '';
    retryBtn.classList.add('hidden');
    return;
  }

  const ok = state.enriched.filter(s => s.enrichment && Object.keys(s.enrichment).length > 0);
  const fail = state.enriched.filter(s => !s.enrichment || Object.keys(s.enrichment).length === 0);

  summary.textContent = `${ok.length} enriched · ${fail.length} failed · ${state.enriched.length} total`;
  retryBtn.textContent = `🔄 Retry Failed (${fail.length})`;
  retryBtn.classList.toggle('hidden', fail.length === 0);

  // Render OK first, then failed
  let html = ok.map((sd, i) => renderEnrichedCard(sd, i)).join('');
  if (fail.length) {
    html += `<hr class="border-gray-200 my-4"><h3 class="text-sm font-semibold text-red-500 mb-3">⚠️ Failed (${fail.length})</h3>`;
    html += fail.map((sd, i) => renderEnrichedCard(sd, ok.length + i)).join('');
  }
  container.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Actions
// ═══════════════════════════════════════════════════════════════════════════════

async function approveSignal(signalId) {
  try {
    await api('POST', `/api/signals/${signalId}/approve`);
    // Refresh both signal lists
    const appData = await api('GET', '/api/signals/approved');
    state.approved = appData.signals || [];
    renderSignals();
    updateApprovedBadge();
    toast('Signal approved', 'success');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

async function removeApproved(signalId) {
  try {
    await api('POST', `/api/signals/${signalId}/unapprove`);
    const appData = await api('GET', '/api/signals/approved');
    state.approved = appData.signals || [];
    renderApproved();
    renderSignals();
    updateApprovedBadge();
    toast('Signal removed', 'info');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

function clearSignals() {
  state.signals = [];
  state.sourceFilter = null;
  document.getElementById('source-filter').classList.add('hidden');
  renderSignals();
}

function copyAllLinks() {
  const links = state.approved.map(s => s.url).filter(u => u && u !== '#');
  if (!links.length) { toast('No links to copy', 'warning'); return; }
  copyToClipboard(links.join('\n'));
}

async function clearApproved() {
  if (!confirm('Clear all approved signals?')) return;
  try {
    await api('DELETE', '/api/signals/approved');
    state.approved = [];
    renderApproved();
    renderSignals();
    updateApprovedBadge();
    toast('Approved signals cleared', 'info');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

async function clearEnriched() {
  if (!confirm('Clear all enriched signals?')) return;
  try {
    await api('DELETE', '/api/enriched');
    state.enriched = [];
    renderEnriched(0, 0);
    toast('Enriched signals cleared', 'info');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

// ── SSE-based collection ────────────────────────────────────────────────────

async function collectAndRank() {
  const sources = getSelectedSources();
  if (!sources.length) { toast('Select at least one source', 'warning'); return; }
  if (state.processing) return;

  setProcessing(true, 'Collecting & Ranking…');
  const progressEl = document.getElementById('collect-progress');
  const progressBar = document.getElementById('collect-progress-bar');
  const progressLabel = document.getElementById('collect-progress-label');
  const progressDetail = document.getElementById('collect-progress-detail');
  progressEl.classList.remove('hidden');
  progressBar.style.width = '0%';
  progressLabel.textContent = 'Starting collection…';
  progressDetail.textContent = '';

  try {
    const body = {
      sources,
      limit: parseInt(document.getElementById('limit').value),
      days: parseInt(document.getElementById('days').value),
      min_engagement: parseInt(document.getElementById('min-engagement').value),
      use_keywords: document.getElementById('use-keywords').checked,
    };

    const response = await fetch(`${API}/api/collect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || response.statusText);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentPhase = 'collection';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));

          // Phase transitions
          if (data.phase === 'collection') {
            currentPhase = 'collection';
            progressLabel.textContent = 'Step 1/2 — Collecting signals…';
            continue;
          }
          if (data.phase === 'ranking') {
            currentPhase = 'ranking';
            progressLabel.textContent = 'Step 2/2 — Ranking signals…';
            progressBar.style.width = '0%';
            progressBar.classList.remove('bg-orange-500');
            progressBar.classList.add('bg-emerald-500');
            continue;
          }
          if (data.phase === 'complete') {
            progressBar.style.width = '100%';
            progressLabel.textContent = 'Complete!';
            continue;
          }

          // Progress updates
          if (currentPhase === 'collection' && data.total_sources) {
            const pct = Math.min(data.completed_sources / data.total_sources * 100, 100);
            progressBar.style.width = pct + '%';
            progressLabel.textContent = `Collecting: ${data.completed_sources}/${data.total_sources} sources`;
            // Format source status
            const parts = [];
            for (const [src, info] of Object.entries(data.source_results || {})) {
              const icon = info.error ? '❌' : '✅';
              parts.push(`${icon} ${src}: ${info.count || 0}`);
            }
            if (data.total_signals) parts.push(`📊 Total: ${data.total_signals}`);
            progressDetail.textContent = parts.join('  ·  ');
          }

          if (currentPhase === 'ranking' && data.total) {
            const pct = Math.min(data.completed / data.total * 100, 100);
            progressBar.style.width = pct + '%';
            progressLabel.textContent = `Ranking: ${data.completed}/${data.total} (${Math.round(pct)}%)`;
            progressDetail.textContent = `OpenAI: ${data.openai_count || 0}  ·  Keyword: ${data.keyword_count || 0}  ·  Errors: ${data.errors || 0}`;
          }
        } catch (e) {
          // Skip unparseable lines
        }
      }
    }

    // Load results — reset source filter for fresh data
    state.sourceFilter = null;
    await loadSignals();
    toast('Collection & ranking complete!', 'success');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  } finally {
    setProcessing(false);
    setTimeout(() => progressEl.classList.add('hidden'), 3000);
  }
}

// ── SSE-based enrichment ────────────────────────────────────────────────────

async function enrichAll() {
  if (state.processing) return;
  if (!state.approved.length) { toast('No approved signals to enrich', 'warning'); return; }

  setProcessing(true, 'Enriching…');
  const progressEl = document.getElementById('enrich-progress');
  const progressBar = document.getElementById('enrich-progress-bar');
  const progressLabel = document.getElementById('enrich-progress-label');
  const progressDetail = document.getElementById('enrich-progress-detail');
  progressEl.classList.remove('hidden');
  progressBar.style.width = '0%';

  const deep = document.getElementById('deep-research').checked;
  const modeLabel = deep ? 'deep research (sonar-deep-research)' : 'standard (sonar-pro)';
  progressLabel.textContent = `Enriching with ${modeLabel}…`;

  try {
    const response = await fetch(`${API}/api/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deep }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || response.statusText);
    }

    await processSSEStream(response, progressBar, progressLabel, progressDetail, 'enrich');
    await loadEnriched();
    toast('Enrichment complete!', 'success');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  } finally {
    setProcessing(false);
    setTimeout(() => progressEl.classList.add('hidden'), 3000);
  }
}

async function retryFailed() {
  if (state.processing) return;
  const fail = state.enriched.filter(s => !s.enrichment || Object.keys(s.enrichment).length === 0);
  if (!fail.length) { toast('No failed signals to retry', 'info'); return; }

  const signalIds = fail.map(s => {
    const orig = s.original_signal || {};
    return orig.id;
  }).filter(Boolean);

  if (!signalIds.length) { toast('No valid signals to retry', 'warning'); return; }

  setProcessing(true, 'Retrying failed…');
  const progressEl = document.getElementById('retry-progress');
  const progressBar = document.getElementById('retry-progress-bar');
  const progressDetail = document.getElementById('retry-progress-detail');
  progressEl.classList.remove('hidden');
  progressBar.style.width = '0%';

  try {
    const response = await fetch(`${API}/api/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signal_ids: signalIds }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || response.statusText);
    }

    await processSSEStream(response, progressBar, null, progressDetail, 'enrich');
    await loadEnriched();
    toast('Retry complete!', 'success');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  } finally {
    setProcessing(false);
    setTimeout(() => progressEl.classList.add('hidden'), 3000);
  }
}

async function processSSEStream(response, progressBar, progressLabel, progressDetail, type) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));

        if (type === 'enrich' && data.total) {
          const pct = Math.min(data.completed / data.total * 100, 100);
          progressBar.style.width = pct + '%';
          if (progressLabel) {
            progressLabel.textContent = `Enriching: ${data.completed}/${data.total} (${Math.round(pct)}%)`;
          }
          const parts = [`✅ ${data.success_count || 0} enriched`, `❌ ${data.error_count || 0} failed`];
          if (data.current_title) parts.push(`📝 ${data.current_title.slice(0, 60)}`);
          if (progressDetail) progressDetail.textContent = parts.join('  ·  ');
        }
      } catch (e) { /* skip */ }
    }
  }
}

// ── Export ───────────────────────────────────────────────────────────────────

async function exportApproved() {
  try {
    toast('Exporting…', 'info');
    const data = await api('POST', '/api/export/approved');
    toast(`Exported ${data.count} signals!`, 'success');
    if (data.url) window.open(data.url, '_blank');
  } catch (e) {
    toast('Export failed: ' + e.message, 'error');
  }
}

async function exportEnriched() {
  try {
    toast('Exporting…', 'info');
    const data = await api('POST', '/api/export/enriched');
    toast(`Exported ${data.count} signals!`, 'success');
    if (data.url) window.open(data.url, '_blank');
  } catch (e) {
    toast('Export failed: ' + e.message, 'error');
  }
}

// ── Sources config ──────────────────────────────────────────────────────────

async function loadSourcesConfig() {
  try {
    const data = await api('GET', '/api/sources');
    document.getElementById('src-keywords').value = (data.keywords || []).join('\n');
    document.getElementById('src-linkedin').value = (data['linkedin-thought-leaders'] || []).join('\n');
    document.getElementById('src-rss').value = (data['web-sources-rss'] || []).join('\n');
    document.getElementById('src-reddit').value = (data['reddit-subreddits'] || []).join('\n');

    // Load API status
    const status = await api('GET', '/api/status');
    const statusEl = document.getElementById('api-status');
    statusEl.innerHTML = Object.entries(status).map(([name, ok]) =>
      `<span>${ok ? '✅' : '❌'} ${name.replace('_', ' ')}</span>`
    ).join('');
  } catch (e) {
    console.error('Failed to load sources config:', e);
  }
}

async function saveSources() {
  try {
    const toLines = (id) => document.getElementById(id).value.split('\n').map(l => l.trim()).filter(Boolean);
    await api('PUT', '/api/sources', {
      keywords: toLines('src-keywords'),
      web_sources_rss: toLines('src-rss'),
      linkedin_thought_leaders: toLines('src-linkedin'),
      reddit_subreddits: toLines('src-reddit'),
    });
    toast('Sources saved!', 'success');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

// ── Threshold slider reactivity ─────────────────────────────────────────────

document.getElementById('threshold').addEventListener('input', () => {
  if (state.signals.length) renderSignals();
});

// ═══════════════════════════════════════════════════════════════════════════════
//  Initialization
// ═══════════════════════════════════════════════════════════════════════════════

(async function init() {
  await initSources();
  // Try loading existing data
  try {
    const data = await api('GET', '/api/signals?min_score=0');
    state.signals = data.signals || [];
    const appData = await api('GET', '/api/signals/approved');
    state.approved = appData.signals || [];
    renderSignals();
    updateApprovedBadge();
  } catch (e) {
    console.log('No existing data to load');
  }
})();

