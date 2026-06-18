// ─── State ───────────────────────────────────────────────────────────────────
let currentData = null;
let allClauses  = [];
let batchAnalyzed = {};   // filename -> analysis data
let batchFiles  = [];
let loadStepTimer = null;

// ─── View Switcher ────────────────────────────────────────────────────────────
function switchView(name) {
  document.querySelectorAll('.view').forEach(v => {
    v.classList.remove('active');
    v.classList.add('hidden');
  });
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  
  const target = document.getElementById(`view-${name}`);
  if (target) {
    target.classList.add('active');
    target.classList.remove('hidden');
  }
  
  const tabBtn = document.getElementById(`tab-btn-${name}`);
  if (tabBtn) {
    tabBtn.classList.add('active');
  }
  
  if (name === 'settings') loadSettings();
}

// ─── Drag / Drop ─────────────────────────────────────────────────────────────
function handleDragOver(e) { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }
function handleDragLeave(e) { e.currentTarget.classList.remove('drag-over'); }
function handleDrop(e) {
  e.preventDefault(); e.currentTarget.classList.remove('drag-over');
  const f = e.dataTransfer.files[0]; if (f) processFile(f);
}
function handleFileSelect(e) { const f = e.target.files[0]; if (f) processFile(f); }

// ─── Single Analysis ──────────────────────────────────────────────────────────
function processFile(file) {
  if (!validateFile(file)) return;
  showLoading(true);
  animateSteps();
  const fd = new FormData();
  fd.append('file', file);
  fetch('/api/analyze', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(d => { clearSteps(); if (d.error) { toast(d.error, 'error'); showHero(); } else renderResults(d); })
    .catch(e => { clearSteps(); toast('Network error: ' + e.message, 'error'); showHero(); });
}

function loadDemo() {
  showLoading(true); animateSteps();
  fetch('/api/demo').then(r => r.json()).then(d => { clearSteps(); renderResults(d); })
    .catch(e => { clearSteps(); toast('Demo failed: ' + e.message, 'error'); showHero(); });
}

function validateFile(f) {
  const ext = f.name.split('.').pop().toLowerCase();
  if (!['pdf','docx'].includes(ext)) { toast('Only PDF and DOCX files supported.', 'error'); return false; }
  if (f.size > 52428800) { toast('File too large (max 50MB).', 'error'); return false; }
  return true;
}

// ─── Loading ──────────────────────────────────────────────────────────────────
function animateSteps() {
  const ids = ['ls0','ls1','ls2','ls3'];
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.className = 'lstep'; });
  const el0 = document.getElementById('ls0'); if (el0) el0.classList.add('active');
  let i = 0;
  clearInterval(loadStepTimer);
  loadStepTimer = setInterval(() => {
    const prev = document.getElementById(ids[i]); if (prev) prev.classList.replace('active','done');
    i++;
    if (i < ids.length) { const next = document.getElementById(ids[i]); if (next) next.classList.add('active'); }
    else clearInterval(loadStepTimer);
  }, 3500);
}
function clearSteps() { clearInterval(loadStepTimer); }
function showLoading(on) {
  const hero = document.getElementById('heroSection');
  const load = document.getElementById('loadingState');
  const res  = document.getElementById('resultsSection');
  if (on) { hide(hero); show(load); hide(res); }
  else    { hide(load); }
}
function showHero() { clearSteps(); hide('loadingState'); show('heroSection'); hide('resultsSection'); }
function resetAnalysis() {
  currentData = null; allClauses = [];
  document.getElementById('fileInput').value = '';
  document.getElementById('contractPreview').textContent = '';
  document.getElementById('outlineToggle').style.display = 'none';
  document.getElementById('outlineTree').classList.add('hidden');
  show('heroSection'); hide('resultsSection'); hide('loadingState');
}

// ─── Render Results ───────────────────────────────────────────────────────────
function renderResults(data) {
  currentData = data;
  allClauses  = data.clauses || [];
  clearSteps();
  hide('loadingState'); hide('heroSection'); show('resultsSection');

  setText('rFilename', data.filename || 'Contract');
  setText('rMeta', `${(data.full_text || '').split(/\s+/).length.toLocaleString()} words · ${allClauses.length} clauses extracted`);

  renderBanner(data);
  renderOutline(data);
  matchClausesToSections(allClauses, data.full_text);
  renderClauses(allClauses);
  renderSummary(data.executive_summary || {});
  const pre = document.getElementById('contractPreview');
  pre.textContent = (data.full_text || '').substring(0, 3000) + (data.full_text?.length > 3000 ? '\n…' : '');
  toast('✅ Analysis complete!', 'success');
}

// ─── Match Clauses to Sections ────────────────────────────────────────────────
function normWs(s) {
  return String(s).replace(/\s+/g, ' ').trim();
}

function matchClausesToSections(clauses, fullText) {
  if (!clauses || !fullText) return;

  const normFull = normWs(fullText);

  // Build a flat sorted list of headings with normalized positions
  const lines = fullText.split('\n');
  const headings = [];
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    if (!t) continue;
    const level = detectHeadingLevel(t);
    if (level > 0) {
      const pos = normFull.indexOf(normWs(t));
      if (pos >= 0) headings.push({ text: t, pos, level });
    }
  }
  if (!headings.length) return;
  headings.sort((a, b) => a.pos - b.pos);

  // For each clause, find the nearest heading before it
  for (const c of clauses) {
    const clausePos = normFull.indexOf(normWs(c.clause_text || ''));
    if (clausePos === -1) continue;

    let parent = null;
    for (const h of headings) {
      if (h.pos < clausePos) parent = h;
      else break;
    }
    c.parentSection = parent ? parent.text : null;
  }
}

// ─── Risk Banner ──────────────────────────────────────────────────────────────
function renderBanner(data) {
  const score    = data.overall_risk_score || 0;
  const catRisks = data.category_risks || {};
  const verdict  = riskVerdict(score);
  const vEl = document.getElementById('rbVerdict');
  vEl.textContent = verdict;
  vEl.className = 'rb-verdict v-' + verdict.toLowerCase().split(' ')[0];
  setText('rbScoreLine', `Score: ${score}/100`);

  // Gauge
  setTimeout(() => {
    const arc = document.getElementById('gaugeArc');
    if (arc) arc.style.strokeDashoffset = 251 - (score / 100) * 251;
    setText('gScore', score);
  }, 80);

  // Quadrants
  ['Financial','Operational','Legal','Reputational'].forEach(cat => {
    const val = catRisks[cat] || 0;
    const fill = document.getElementById(`qf-${cat}`);
    const valEl = document.getElementById(`qv-${cat}`);
    if (valEl) valEl.textContent = val;
    setTimeout(() => { if (fill) fill.style.width = val + '%'; }, 150);
  });
}

function riskVerdict(s) {
  if (s >= 75) return 'Critical Risk';
  if (s >= 55) return 'High Risk';
  if (s >= 35) return 'Moderate Risk';
  return 'Low Risk';
}

// ─── Clauses ──────────────────────────────────────────────────────────────────
function renderClauses(clauses) {
  const list = document.getElementById('clauseList');
  setText('clauseCount', `(${clauses.length})`);
  if (!clauses.length) {
    list.innerHTML = '<p style="color:var(--muted);padding:.8rem;">No clauses extracted.</p>';
    return;
  }
  list.innerHTML = clauses.map((c, i) => clauseCard(c, i)).join('');
}

function clauseCard(c, idx) {
  const dev = c.deviation || 'standard';
  const score = c.risk_score || 0;
  const flagClass = `cc-${dev}`;
  const badgeClass = `f-${dev.charAt(0).toUpperCase() + dev.slice(1)}`;
  return `
    <div class="clause-card ${flagClass}" onclick="openModal(${idx})">
      <div class="cc-head">
        <span class="cc-type">${esc(c.clause_type)}</span>
        <span class="cc-flag ${badgeClass}">${esc(dev)}</span>
      </div>
      <div class="cc-title">${esc(c.clause_type)}</div>
      ${c.parentSection ? `<div class="cc-parent">📍 ${esc(c.parentSection)}</div>` : ''}
      <div class="cc-exp">${esc(c.comparison_explanation || '')}</div>
      <div class="cc-foot">
        <div class="cc-score">
          <div class="pips">${buildPips(score)}</div>
          <span>${score}/100</span>
        </div>
        <div style="display:flex;gap:.4rem;align-items:center;">
          <span class="cc-cat">${esc(c.risk_category || '')}</span>
          <span class="cc-pri pri-${c.risk_level || 'Low'}">${esc(c.risk_level || '')} Risk</span>
        </div>
      </div>
    </div>`;
}

function buildPips(score) {
  return Array.from({length:10}, (_,i) => {
    let cls = 'pip';
    if (i < Math.round(score/10)) {
      if (score >= 75) cls += ' p-red';
      else if (score >= 50) cls += ' p-orange';
      else if (score >= 30) cls += ' p-yellow';
      else cls += ' p-green';
    }
    return `<div class="${cls}"></div>`;
  }).join('');
}

function filterClauses(flag, btn) {
  document.querySelectorAll('.fchip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  const filtered = flag === 'all' ? allClauses : allClauses.filter(c => c.deviation === flag);
  renderClauses(filtered);
}

// ─── Summary ──────────────────────────────────────────────────────────────────
function renderSummary(s) {
  const body = document.getElementById('summaryBody');
  if (!s || !s.scope) { body.innerHTML = '<p style="color:var(--muted)">Summary unavailable.</p>'; return; }
  const terms = (s.key_commercial_terms || []).map(t => `<li>${esc(t)}</li>`).join('');
  const issues = (s.top_negotiation_issues || []).map(n => {
    if (typeof n === 'string') return `<div class="neg-issue"><div class="neg-title">⚠️ Issue</div><div class="neg-why">${esc(n)}</div></div>`;
    return `<div class="neg-issue"><div class="neg-title">⚠️ ${esc(n.issue || '')}</div><div class="neg-why">${esc(n.why_it_matters || n.why || '')}</div><div class="neg-action">→ ${esc(n.recommended_action || n.action || '')}</div></div>`;
  }).join('');
  body.innerHTML = `
    <div class="s-block"><div class="s-block-title">Scope</div><p>${esc(s.scope)}</p></div>
    <div class="s-block"><div class="s-block-title">Risk Allocation</div><p>${esc(s.risk_allocation)}</p></div>
    <div class="s-block"><div class="s-block-title">Key Commercial Terms</div><ul class="s-terms">${terms}</ul></div>
    <div class="s-block"><div class="s-block-title">Top 3 Negotiation Issues</div>${issues}</div>
    <div class="s-rec"><div style="font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.09em;color:var(--acc);margin-bottom:.4rem;">Recommendation</div>
      <p>${esc((s.top_negotiation_issues || []).join(' ') || 'See issues above.')}</p></div>`;
}

function copySummary() {
  const text = document.getElementById('summaryBody')?.innerText || '';
  navigator.clipboard.writeText(text).then(() => toast('📋 Copied!', 'success'));
}

function printSummary() { window.print(); }

// ─── Document Outline (client-side hierarchy) ─────────────────────────────────
const HEADING_KEYWORDS = [
  'whereas', 'witnesseth', 'now therefore', 'definitions',
  'representations', 'warranties', 'covenants', 'indemnification',
  'indemnity', 'termination', 'insurance', 'confidentiality',
  'dispute', 'general', 'miscellaneous', 'scope', 'purpose',
  'consideration', 'assignment', 'waiver', 'notices', 'signatures',
  'background', 'recitals'
];

function detectHeadingLevel(text) {
  if (!text || text.length >= 120) return 0;
  const t = text.trim();
  if (!t || t.endsWith(',')) return 0;

  if (/^(article|section|clause|paragraph|exhibit|schedule|appendix)\s+(I|V|X|L|C|D|M|[0-9]+)[\.:]?\s/i.test(t)) return 1;

  let m = t.match(/^(article|section|clause|paragraph)\s+(\d+(?:\.\d+)+)\b/i);
  if (m) return Math.min(m[2].split('.').length, 6);

  if (t === t.toUpperCase() && t.length > 8) return 1;

  m = t.match(/^(\d+(?:\.\d+)*)\.?\s+\w/);
  if (m) return Math.min(m[1].split('.').length, 6);

  if (/^[IVXLCDM]+\.\s+\w/.test(t)) return 1;
  if (/^\(?[a-z]\)\s+\w/.test(t)) return 3;
  if (new RegExp('^(' + HEADING_KEYWORDS.join('|') + ')\\b', 'i').test(t)) return 1;

  return 0;
}

function buildHierarchyFromText(fullText) {
  const lines = fullText.split('\n');
  const elements = [];
  for (let i = 0; i < lines.length; i++) {
    const text = lines[i].trim();
    if (!text) continue;
    const level = detectHeadingLevel(text);
    elements.push({ text, level, type: level > 0 ? 'heading' : 'paragraph' });
  }

  const sections = [];
  const preamble = [];
  const stack = [];

  for (const el of elements) {
    if (el.type === 'heading') {
      const section = { heading: el, content: [], subsections: [] };
      while (stack.length && stack[stack.length - 1].level >= el.level) stack.pop();
      if (stack.length) stack[stack.length - 1].node.subsections.push(section);
      else sections.push(section);
      stack.push({ level: el.level, node: section });
    } else {
      if (stack.length) stack[stack.length - 1].node.content.push(el);
      else preamble.push(el);
    }
  }

  return { preamble, sections };
}

function toggleOutline() {
  const tree = document.getElementById('outlineTree');
  const btn = document.getElementById('outlineToggle');
  const hidden = tree.classList.toggle('hidden');
  btn.textContent = hidden ? '📑 Show Document Outline' : '📑 Hide Document Outline';
}

function scrollToHeading(text) {
  const pre = document.getElementById('contractPreview');
  const idx = pre.textContent.indexOf(text);
  if (idx !== -1) {
    show(pre);
    document.getElementById('previewToggle').textContent = '📄 Hide Contract Text';
    pre.focus();
  }
}

function renderOutline(data) {
  const toggle = document.getElementById('outlineToggle');
  const tree = document.getElementById('outlineTree');
  const fullText = data.full_text || '';
  const h = buildHierarchyFromText(fullText);
  if (!h.sections.length) {
    toggle.style.display = 'none';
    return;
  }
  toggle.style.display = '';
  tree.innerHTML = buildOutlineHTML(h);
  tree.classList.add('hidden');
}

function buildOutlineHTML(h) {
  let html = '';
  if (h.preamble && h.preamble.length) {
    html += '<div class="ot-section"><div class="ot-node ot-preamble"><span class="ot-bullet">📋</span><span class="ot-text">Preamble (' + h.preamble.length + ' lines)</span></div></div>';
  }
  for (const s of h.sections) {
    html += renderSectionNode(s);
  }
  return html;
}

function renderSectionNode(s) {
  const hd = s.heading;
  const level = Math.min(hd.level || 1, 6);
  const label = 'L' + level;
  const hasChildren = s.subsections && s.subsections.length > 0;
  const hasContent = s.content && s.content.length > 0;

  let html = '<div class="ot-section">';
  html += '<div class="ot-node" onclick="scrollToHeading(' + JSON.stringify(hd.text) + ')">';
  html += '<span class="ot-bullet l' + Math.min(level, 3) + '">' + label + '</span>';
  html += '<span class="ot-text">' + (hasContent ? '<strong>' : '') + esc(hd.text) + (hasContent ? '</strong>' : '');
  if (hasContent) html += ' <span style="color:var(--muted);font-size:0.85rem;">(' + s.content.length + ')</span>';
  html += '</span></div>';
  if (hasChildren) {
    html += '<div class="ot-children">';
    for (const sub of s.subsections) html += renderSectionNode(sub);
    html += '</div>';
  }
  html += '</div>';
  return html;
}

// ─── Text Preview ─────────────────────────────────────────────────────────────
function togglePreview() {
  const pre = document.getElementById('contractPreview');
  const btn = document.getElementById('previewToggle');
  const hidden = pre.classList.toggle('hidden');
  btn.textContent = hidden ? '📄 Show Contract Text' : '📄 Hide Contract Text';
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function openModal(idx) {
  const c = allClauses[idx]; if (!c) return;
  const score = c.risk_score || 0;
  const scoreColor = score >= 75 ? 'var(--red)' : score >= 50 ? 'var(--orange)' : score >= 30 ? 'var(--yellow)' : 'var(--green)';
  document.getElementById('modalInner').innerHTML = `
    <div class="m-type">${esc(c.clause_type)}</div>
    <div class="m-title">${esc(c.clause_type)}</div>
    <span class="cc-flag f-${c.deviation || 'standard'}" style="display:inline-block;margin-bottom:.5rem;">${esc(c.deviation || 'Standard')}</span>
    <div class="m-section">Clause Text</div>
    <div class="m-text">${esc(c.clause_text || 'Not extracted.')}</div>
    <div class="m-grid">
      <div class="m-stat"><div class="m-stat-label">Risk Score</div><div class="m-stat-val" style="color:${scoreColor}">${score}/100</div></div>
      <div class="m-stat"><div class="m-stat-label">Risk Level</div><div class="m-stat-val pri-${c.risk_level||'Low'}">${esc(c.risk_level||'—')} Risk</div></div>
      <div class="m-stat"><div class="m-stat-label">Category</div><div class="m-stat-val">${esc(c.risk_category||'—')}</div></div>
      <div class="m-stat"><div class="m-stat-label">Deviation</div><div class="m-stat-val">${esc(c.deviation||'—')}</div></div>
    </div>
    <div class="m-section">Market-Standard Analysis</div>
    <div class="m-text">${esc(c.comparison_explanation||'—')}</div>
    <div class="m-section">Negotiation Tip</div>
    <div class="m-tip">💡 ${esc(c.negotiation_tip||'No tip available.')}</div>`;
  show('modalBg');
  document.getElementById('clauseModal').scrollTop = 0;
}
function closeModal() { hide('modalBg'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ─── Batch Analysis ───────────────────────────────────────────────────────────
function handleBatchDrop(e) {
  e.preventDefault(); e.currentTarget.classList.remove('drag-over');
  addBatchFiles([...e.dataTransfer.files]);
}
function handleBatchSelect(e) { addBatchFiles([...e.target.files]); }

function addBatchFiles(files) {
  files.forEach(f => {
    if (batchFiles.length >= 5) { toast('Max 5 contracts.', 'error'); return; }
    if (!['pdf','docx'].includes(f.name.split('.').pop().toLowerCase())) return;
    if (!batchFiles.find(b => b.name === f.name && b.size === f.size)) batchFiles.push(f);
  });
  renderBatchFiles();
}

function removeBatchFile(i) {
  const fname = batchFiles[i]?.name;
  batchFiles.splice(i, 1);
  if (fname) delete batchAnalyzed[fname];
  renderBatchFiles();
}

function renderBatchFiles() {
  const list = document.getElementById('batchFileList');
  list.innerHTML = batchFiles.map((f, i) => {
    const done = batchAnalyzed[f.name] && !batchAnalyzed[f.name].error;
    const failed = batchAnalyzed[f.name]?.error;
    const cls = done ? 'done' : failed ? 'failed' : '';
    const icon = done ? '✅' : failed ? '❌' : '📄';
    return `<div class="bfile-chip ${cls}">${icon} ${esc(f.name)}<button onclick="removeBatchFile(${i})">✕</button></div>`;
  }).join('');
  const ctrl = document.getElementById('batchAnalyzeControls');
  ctrl.classList.toggle('hidden', batchFiles.length < 2);
}

async function runBatchAnalysis() {
  if (batchFiles.length < 2) { toast('Upload at least 2 contracts.', 'error'); return; }
  show('batchLoadingState');
  hide('batchResultsSection');
  document.getElementById('batchAnalyzeControls').classList.add('hidden');
  batchAnalyzed = {};

  for (const file of batchFiles) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/analyze', { method: 'POST', body: fd });
      const data = await res.json();
      batchAnalyzed[file.name] = data;
    } catch (e) {
      batchAnalyzed[file.name] = { error: e.message, filename: file.name };
    }
    renderBatchFiles();
  }

  hide('batchLoadingState');
  renderBatchResults();
}

function renderBatchResults() {
  const bar = document.getElementById('batchAnalyzedBar');
  bar.innerHTML = Object.entries(batchAnalyzed).map(([fname, data]) => {
    const score = data.overall_risk_score ?? '—';
    const err = data.error ? `<span style="color:var(--red)">Error</span>` : `<strong>${score}/100</strong>`;
    return `<div class="ba-chip">📄 ${esc(fname)} · Risk: ${err}</div>`;
  }).join('');
  show('batchResultsSection');
  toast('✅ All contracts analyzed! Now select a clause to compare.', 'success');
}

async function runComparison() {
  const successfulFiles = batchFiles.filter(f => batchAnalyzed[f.name] && !batchAnalyzed[f.name].error).map(f => f.name);
  if (successfulFiles.length < 2) { toast('Need at least 2 successfully analyzed contracts.', 'error'); return; }
  const clauseType = document.getElementById('compareClauseSelect').value;
  show('compareLoadingState');
  document.getElementById('comparisonResult').innerHTML = '';
  try {
    const res = await fetch('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filenames: successfulFiles, clause_type: clauseType })
    });
    const data = await res.json();
    hide('compareLoadingState');
    if (data.error) { toast(data.error, 'error'); return; }
    renderComparison(data, clauseType);
    toast('✅ Comparison ready!', 'success');
  } catch (e) {
    hide('compareLoadingState');
    toast('Comparison failed: ' + e.message, 'error');
  }
}

function renderComparison(data, clauseType) {
  const baseline = data.baseline_standard || '';
  const comps = data.comparisons || [];
  const summary = data.due_diligence_summary || '';
  document.getElementById('comparisonResult').innerHTML = `
    <div class="comp-block">
      <div class="comp-head">
        <span class="comp-title">${esc(clauseType)}</span>
        <span class="comp-baseline">Baseline: ${esc(baseline)}</span>
      </div>
      <div class="comp-rows">
        ${comps.map(c => `
          <div class="comp-row">
            <div class="comp-row-name">📄 ${esc(c.filename)}</div>
            <div class="comp-row-text">${esc(c.clause_text && c.clause_text !== 'Not Found' ? c.clause_text.substring(0,300) + '…' : 'Clause not found in this contract.')}</div>
            <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;">
              <span class="comp-stance st-${c.deviation||'Neutral'}">${esc(c.deviation||'—')}</span>
              <span style="font-size:.78rem;color:var(--muted);">Risk: ${c.risk_score ?? '—'}/100</span>
              <span style="font-size:.78rem;color:var(--muted);">${esc(c.summary_analysis || '')}</span>
            </div>
          </div>`).join('')}
      </div>
      ${summary ? `<div class="comp-summary">💡 <strong>Due-Diligence Summary:</strong> ${esc(summary)}</div>` : ''}
    </div>`;
}

function resetBatch() {
  batchFiles = []; batchAnalyzed = {};
  document.getElementById('batchInput').value = '';
  renderBatchFiles();
  hide('batchResultsSection'); hide('batchLoadingState');
  document.getElementById('comparisonResult').innerHTML = '';
}

// ─── Settings ─────────────────────────────────────────────────────────────────
async function loadSettings() {
  const statusEl = document.getElementById('apiKeyStatus');
  statusEl.textContent = 'Loading…';
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.api_key_configured) {
      statusEl.textContent = `✅ API key configured (${data.api_key_preview})`;
      statusEl.className = 'api-key-status ok';
    } else {
      statusEl.textContent = '⚠️ No API key set. Enter your API key below.';
      statusEl.className = 'api-key-status';
    }
    renderBaselineEditor(data.baseline || {});
  } catch (e) {
    statusEl.textContent = 'Could not load settings.';
  }
}

function renderBaselineEditor(baseline) {
  const ed = document.getElementById('baselineEditor');
  if (!baseline || !Object.keys(baseline).length) { ed.innerHTML = '<p style="color:var(--muted)">No baseline data found.</p>'; return; }
  ed.innerHTML = Object.entries(baseline).map(([key, val]) => `
    <div class="baseline-item">
      <div class="baseline-item-title">${esc(val.title || key)}</div>
      <textarea class="baseline-textarea" id="bl-${key}" rows="4">${esc(val.standardText || '')}</textarea>
    </div>`).join('');
}

async function saveSettings() {
  const key = document.getElementById('apiKeyInput').value.trim();
  if (!key) { toast('Enter an API key first.', 'error'); return; }
  try {
    const res = await fetch('/api/settings', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ api_key: key, baseline: {} })
    });
    const d = await res.json();
    if (d.error) { toast(d.error, 'error'); return; }
    toast('✅ API key saved!', 'success');
    document.getElementById('apiKeyInput').value = '';
    loadSettings();
  } catch (e) { toast('Save failed: ' + e.message, 'error'); }
}

async function saveBaseline() {
  const ed = document.getElementById('baselineEditor');
  const textareas = ed.querySelectorAll('textarea');
  const baseline = {};
  textareas.forEach(ta => {
    const key = ta.id.replace('bl-','');
    baseline[key] = { title: key.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase()), standardText: ta.value };
  });
  try {
    const res = await fetch('/api/settings', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ api_key: '', baseline })
    });
    const d = await res.json();
    if (d.error) { toast(d.error, 'error'); return; }
    toast('✅ Baseline saved!', 'success');
  } catch (e) { toast('Save failed: ' + e.message, 'error'); }
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function show(elOrId) {
  const el = typeof elOrId === 'string' ? document.getElementById(elOrId) : elOrId;
  if (el) el.classList.remove('hidden');
}
function hide(elOrId) {
  const el = typeof elOrId === 'string' ? document.getElementById(elOrId) : elOrId;
  if (el) el.classList.add('hidden');
}
function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function toast(msg, type='info') {
  const wrap = document.getElementById('toastWrap');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

// ─── Init ─────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  fetch('/api/settings').then(r => r.json()).then(d => {
    if (!d.api_key_configured) {
      const hint = document.querySelector('.upload-hint');
      if (hint) hint.innerHTML += ' <span style="color:var(--yellow);font-size:.78rem;">(No API key — demo mode)</span>';
    }
    document.getElementById('statusDot').style.background = 'var(--green)';
    setText('statusLabel', 'Ready');
  }).catch(() => {
    document.getElementById('statusDot').style.background = 'var(--red)';
    setText('statusLabel', 'Offline');
  });
});
