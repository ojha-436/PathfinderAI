/* PathFinder — SPA controller: routing, auth, analyze flow, results, history. */

const ASHA_SAMPLE = `Asha Kulkarni
Data Entry Operator | Pune, Maharashtra
PROFILE: Detail-oriented Data Entry Operator with 8 years of experience in high-volume data entry, record keeping and document filing.
SKILLS: Data Entry, Typing, Microsoft Excel, Basic MS Office, Filing, Cash Handling, Attention to Detail, Customer Service, Business Communication, Time Management
EXPERIENCE: Senior Data Entry Operator, Acme Logistics (2018-2026). Entered and validated 500+ records daily in Excel. Maintained filing with 99.8% accuracy. Handled customer telephone queries and the billing counter.
EDUCATION: B.Com, Savitribai Phule Pune University (2016)`;

const State = { result: null, selected: 0, lastInput: null, loadTimer: null, catalog: null, pendingAfterAuth: null };

/* ---------------- helpers ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function inr(n) {
  n = Math.round(n || 0);
  const s = String(n);
  if (s.length <= 3) return '₹' + s;
  let head = s.slice(0, -3), tail = s.slice(-3), parts = [];
  while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
  parts.unshift(head);
  return '₹' + parts.join(',') + ',' + tail;
}
function pct(g) { const v = Math.round((g || 0) * 100); return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) + '%'; }
function arrow(dir) { return dir === 'up' ? '▲' : dir === 'down' ? '▼' : '→'; }

function toast(msg, type = 'ok') {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .4s'; setTimeout(() => t.remove(), 400); }, 3800);
}

/* ---------------- meta / provider badge ---------------- */
async function loadMeta() {
  try {
    const m = await Api.meta();
    const ps = m.provider_status || {};
    const active = Object.values(ps);
    const cloud = active.filter((v) => v !== 'local');
    const label = cloud.length ? [...new Set(cloud)].join(' · ') : 'local engine';
    $('#providerText').textContent = label;
    $('#footMeta').textContent = `${label} · ${m.counts.skills} skills · ${m.counts.courses} courses · reproducible`;
  } catch { /* offline meta is non-fatal */ }
}

/* ---------------- auth / nav ---------------- */
function renderNav() {
  const el = $('#navAuth');
  const u = Store.user;
  if (u) {
    const initial = (u.email || '?')[0].toUpperCase();
    el.innerHTML = `<div class="menu">
      <div class="avatar" id="avatarBtn" title="${esc(u.email)}">${esc(initial)}</div>
      <div class="menu-pop hidden" id="menuPop">
        <div class="who">Signed in as<br><strong>${esc(u.email)}</strong></div>
        <button data-act="history">📁 My analyses</button>
        <button data-act="learning">🎓 My learning</button>
        <button data-act="logout">↩ Log out</button>
        <button data-act="delacct" class="danger">🗑 Delete account</button>
      </div>
    </div>`;
    $('#avatarBtn').onclick = (e) => { e.stopPropagation(); $('#menuPop').classList.toggle('hidden'); };
    el.querySelectorAll('[data-act]').forEach((b) => b.onclick = () => {
      $('#menuPop').classList.add('hidden');
      const a = b.dataset.act;
      if (a === 'history') location.hash = '#/history';
      else if (a === 'learning') location.hash = '#/learning';
      else if (a === 'logout') { Store.clear(); renderNav(); toast('Logged out.'); location.hash = '#/'; }
      else if (a === 'delacct') confirmDeleteAccount();
    });
  } else {
    el.innerHTML = `<button class="btn btn-ghost btn-sm" id="loginBtn">Log in</button>
      <button class="btn btn-primary btn-sm" id="signupBtn" style="margin-left:8px">Sign up</button>`;
    $('#loginBtn').onclick = () => openAuth('login');
    $('#signupBtn').onclick = () => openAuth('register');
  }
}
document.addEventListener('click', () => { const m = $('#menuPop'); if (m) m.classList.add('hidden'); });

function openAuth(mode) {
  const isReg = mode === 'register';
  $('#authModal').innerHTML = `<div class="modal-back" id="modalBack">
    <div class="card modal" style="position:relative">
      <button class="close-x" id="authClose" aria-label="Close">×</button>
      <span class="eyebrow">${isReg ? 'Create your account' : 'Welcome back'}</span>
      <h2>${isReg ? 'Save your career map' : 'Log in'}</h2>
      <p class="muted" style="font-size:.9rem;margin-top:-.4em">${isReg ? 'Free. Your analyses are saved to your history.' : 'Access your saved analyses.'}</p>
      <form id="authForm">
        <div class="field"><label>Email</label><input type="email" id="authEmail" required autocomplete="email" placeholder="you@example.com"></div>
        <div class="field"><label>Password ${isReg ? '<span class="muted">(min 8 characters)</span>' : ''}</label>
          <input type="password" id="authPass" required autocomplete="${isReg ? 'new-password' : 'current-password'}" placeholder="••••••••"></div>
        <div class="field err-msg hidden" id="authErr"></div>
        <button type="submit" class="btn btn-primary btn-block" id="authSubmit">${isReg ? 'Create account' : 'Log in'}</button>
      </form>
      <div class="switch">${isReg ? 'Already have an account?' : "New here?"}
        <button id="authToggle">${isReg ? 'Log in' : 'Create one'}</button></div>
    </div></div>`;

  const close = () => { $('#authModal').innerHTML = ''; };
  $('#authClose').onclick = close;
  $('#modalBack').onclick = (e) => { if (e.target.id === 'modalBack') close(); };
  $('#authToggle').onclick = () => openAuth(isReg ? 'login' : 'register');
  $('#authForm').onsubmit = async (e) => {
    e.preventDefault();
    const email = $('#authEmail').value.trim(), pass = $('#authPass').value;
    const errEl = $('#authErr'), btn = $('#authSubmit');
    errEl.classList.add('hidden');
    if (isReg && pass.length < 8) { errEl.textContent = 'Password must be at least 8 characters.'; errEl.classList.remove('hidden'); return; }
    btn.disabled = true; btn.textContent = isReg ? 'Creating…' : 'Logging in…';
    try {
      const res = isReg ? await Api.register(email, pass) : await Api.login(email, pass);
      Store.token = res.access_token;
      Store.user = await Api.me();
      close(); renderNav();
      toast(isReg ? 'Account created — welcome!' : 'Logged in.');
      const after = State.pendingAfterAuth; State.pendingAfterAuth = null;
      if (after) after();
    } catch (err) {
      errEl.textContent = err.status === 409 ? 'That email is already registered. Try logging in.' :
        err.status === 401 ? 'Invalid email or password.' : (err.message || 'Something went wrong.');
      errEl.classList.remove('hidden');
      btn.disabled = false; btn.textContent = isReg ? 'Create account' : 'Log in';
    }
  };
  setTimeout(() => $('#authEmail')?.focus(), 50);
}

async function confirmDeleteAccount() {
  if (!confirm('Delete your account and ALL saved analyses? This cannot be undone.')) return;
  try { await Api.deleteAccount(); Store.clear(); renderNav(); toast('Account deleted.'); location.hash = '#/'; }
  catch (e) { toast(e.message || 'Could not delete account.', 'err'); }
}

/* ---------------- router ---------------- */
const VIEWS = ['landing', 'analyze', 'history', 'learning'];
function showView(name) {
  VIEWS.forEach((v) => $(`#view-${v}`).classList.toggle('hidden', v !== name));
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
}
function route() {
  const hash = location.hash || '#/';
  if (hash === '#/' || hash === '') { showView('landing'); return; }
  if (hash.startsWith('#/analyze')) { showView('analyze'); if (!State.result) renderAnalyzeIntro(); return; }
  if (hash.startsWith('#/history')) {
    if (!Store.user) { toast('Log in to see your saved analyses.'); State.pendingAfterAuth = () => location.hash = '#/history'; openAuth('login'); location.hash = '#/'; return; }
    showView('history'); renderHistory(); return;
  }
  if (hash.startsWith('#/learning')) {
    if (!Store.user) { toast('Log in to see your learning.'); State.pendingAfterAuth = () => (location.hash = '#/learning'); openAuth('login'); location.hash = '#/'; return; }
    showView('learning'); renderLearning(); return;
  }
  showView('landing');
}
window.addEventListener('hashchange', route);
document.addEventListener('click', (e) => {
  const nav = e.target.closest('[data-nav]');
  if (nav) { e.preventDefault(); location.hash = nav.getAttribute('data-nav') || nav.getAttribute('href'); }
});
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-track]');
  if (!b) return;
  if (!Store.user) { toast('Log in to track your learning.'); openAuth('login'); return; }
  const skills = (b.dataset.cs || '').split(',').filter(Boolean);
  Api.addLearning({ course_id: b.dataset.cid, title: b.dataset.ct, provider: b.dataset.cp, url: b.dataset.cu, skill_ids: skills })
    .then(() => { toast('Added to My Learning ✓'); b.textContent = '✓ Tracking'; b.disabled = true; })
    .catch((err) => toast(err.message || 'Could not track.', 'err'));
});

/* ---------------- analyze: intro (tabs) ---------------- */
function renderAnalyzeIntro() {
  const root = $('#analyzeRoot');
  root.innerHTML = `
    <div class="analyze-head">
      <div><span class="eyebrow">Step 1 — Build your profile</span><h2 style="margin:.2em 0 0">Let's map your skills</h2></div>
      <div class="tabs" role="tablist">
        <button class="tab active" data-tab="upload">Upload PDF</button>
        <button class="tab" data-tab="connect">🔗 Connect platform</button>
        <button class="tab" data-tab="paste">Paste text</button>
        <button class="tab" data-tab="manual">Enter skills</button>
      </div>
    </div>
    <div id="tabBody"></div>`;
  root.querySelectorAll('.tab').forEach((t) => t.onclick = () => {
    root.querySelectorAll('.tab').forEach((x) => x.classList.toggle('active', x === t));
    renderTab(t.dataset.tab);
  });
  renderTab('upload');
}

function renderTab(tab) {
  const body = $('#tabBody');
  if (tab === 'upload') {
    body.innerHTML = `
      <div class="dropzone card" id="dropzone" tabindex="0" role="button" aria-label="Upload a resume PDF">
        <div class="big">📄</div>
        <h3>Drop your resume PDF here</h3>
        <p class="muted">or click to browse · PDF up to 10 MB · never stored after parsing</p>
        <div class="or">— OR —</div>
        <button class="btn btn-amber" id="sampleBtn">Try Asha's sample resume</button>
        <input type="file" id="fileInput" accept="application/pdf,.pdf" hidden>
      </div>`;
    const dz = $('#dropzone'), fi = $('#fileInput');
    dz.onclick = (e) => { if (e.target.id !== 'sampleBtn') fi.click(); };
    dz.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fi.click(); } };
    fi.onchange = () => { if (fi.files[0]) runAnalysis('file', fi.files[0]); };
    ['dragover', 'dragenter'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => { const f = e.dataTransfer.files[0]; if (f) runAnalysis('file', f); });
    $('#sampleBtn').onclick = (e) => { e.stopPropagation(); runAnalysis('text', ASHA_SAMPLE); };
  } else if (tab === 'paste') {
    body.innerHTML = `
      <textarea class="paste" id="pasteText" placeholder="Paste your resume or a description of your experience and skills…">${esc('')}</textarea>
      <div style="display:flex;gap:10px;margin-top:12px;align-items:center">
        <button class="btn btn-primary" id="pasteBtn">Analyze →</button>
        <button class="btn btn-ghost btn-sm" id="pasteSample">Fill Asha's sample</button>
      </div>`;
    $('#pasteBtn').onclick = () => { const t = $('#pasteText').value.trim(); if (t.length < 10) return toast('Please paste a bit more text.', 'err'); runAnalysis('text', t); };
    $('#pasteSample').onclick = () => { $('#pasteText').value = ASHA_SAMPLE; };
  } else if (tab === 'connect') {
    renderConnect(body);
  } else {
    renderManual(body);
  }
}

const PLATFORMS = [
  { id: 'LinkedIn', icon: '💼', color: '#0a66c2', hint: 'Open your LinkedIn profile → <b>More → Save to PDF</b> (or copy your <b>About</b> + <b>Skills</b>), then paste/upload below.' },
  { id: 'Indeed', icon: '🔎', color: '#2557a7', hint: 'Open your Indeed profile / resume → <b>Download</b> it, or copy your skills & experience, then paste/upload below.' },
  { id: 'Naukri', icon: '📋', color: '#4a90d9', hint: 'Open your Naukri profile → <b>Download CV</b> or copy your key skills & roles, then paste/upload below.' },
];

function renderConnect(body) {
  body.innerHTML = `
    <p class="muted" style="max-width:60ch;margin-bottom:16px">Import your profile from a job platform. Pick one, then paste your profile/skills or upload the profile export it gives you — PathFinder reads your real skills and analyzes them. <span style="color:var(--ink-faint)">(Your data stays yours; nothing is scraped on your behalf.)</span></p>
    <div class="paths" style="grid-template-columns:repeat(3,1fr)">
      ${PLATFORMS.map((p) => `<div class="card path-card" data-plat="${p.id}" style="cursor:pointer">
        <div style="font-size:1.8rem">${p.icon}</div>
        <h3 style="margin:.2em 0">${p.id}</h3>
        <div class="muted" style="font-size:.85rem">Import skills from ${p.id}</div>
        <div class="cta-row">Connect ${p.id} →</div>
      </div>`).join('')}
    </div>
    <div id="connectPanel" style="margin-top:18px"></div>`;
  body.querySelectorAll('[data-plat]').forEach((c) => c.onclick = () => showConnectPanel(c.dataset.plat));
}

function showConnectPanel(platform) {
  const p = PLATFORMS.find((x) => x.id === platform);
  body_highlight(platform);
  $('#connectPanel').innerHTML = `
    <div class="card" style="padding:22px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:1.5rem">${p.icon}</span>
        <h3 style="margin:0">Import from ${p.id}</h3>
      </div>
      <div class="coverage-note" style="background:#eef4fb;border-color:#cfe0f2;color:#274b73">${p.hint}</div>
      <label style="font-size:.85rem;font-weight:600;color:var(--ink-soft)">Paste your ${p.id} profile / skills</label>
      <textarea class="paste" id="connectText" placeholder="Paste your headline, About section, skills and experience from ${p.id}…" style="min-height:150px;margin-top:6px"></textarea>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;align-items:center">
        <button class="btn btn-primary" id="connectImport">Import &amp; analyze →</button>
        <span class="muted" style="font-size:.82rem">or upload your ${p.id} export</span>
        <button class="btn btn-ghost btn-sm" id="connectUploadBtn">Upload PDF</button>
        <input type="file" id="connectFile" accept="application/pdf,.pdf" hidden>
      </div>
    </div>`;
  $('#connectImport').onclick = () => {
    const t = $('#connectText').value.trim();
    if (t.length < 10) return toast(`Paste your ${p.id} profile text first.`, 'err');
    runAnalysis('text', t, p.id);
  };
  $('#connectUploadBtn').onclick = () => $('#connectFile').click();
  $('#connectFile').onchange = () => { if ($('#connectFile').files[0]) runAnalysis('file', $('#connectFile').files[0], p.id); };
}

function body_highlight(platform) {
  document.querySelectorAll('[data-plat]').forEach((c) => c.classList.toggle('sel', c.dataset.plat === platform));
}

function renderManual(body) {
  const chosen = [];
  body.innerHTML = `
    <div class="manual-box">
      <label style="font-size:.85rem;font-weight:600;color:var(--ink-soft)">Your skills</label>
      <div class="chips-input" id="chipsInput"><input id="skillInput" placeholder="Type a skill and press Enter…" autocomplete="off"></div>
      <div class="suggest" id="suggest"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px">
        <div><label style="font-size:.85rem;font-weight:600;color:var(--ink-soft)">Current role (optional)</label>
          <input id="mRole" placeholder="e.g. Data Entry Operator"></div>
        <div><label style="font-size:.85rem;font-weight:600;color:var(--ink-soft)">Years of experience</label>
          <input id="mYears" type="number" min="0" max="50" placeholder="e.g. 8"></div>
      </div>
      <button class="btn btn-primary" id="manualBtn" style="margin-top:16px">Analyze →</button>
    </div>`;
  const wrap = $('#chipsInput'), input = $('#skillInput');
  const redraw = () => {
    wrap.querySelectorAll('.chip-x').forEach((c) => c.remove());
    chosen.forEach((s, i) => {
      const c = document.createElement('span'); c.className = 'chip-x';
      c.innerHTML = `${esc(s)}<button aria-label="remove">×</button>`;
      c.querySelector('button').onclick = () => { chosen.splice(i, 1); redraw(); };
      wrap.insertBefore(c, input);
    });
  };
  const add = (v) => { v = v.trim(); if (v && !chosen.includes(v)) { chosen.push(v); redraw(); } input.value = ''; };
  input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); add(input.value); } else if (e.key === 'Backspace' && !input.value && chosen.length) { chosen.pop(); redraw(); } };
  // suggestions from catalog (rising skills)
  const sug = $('#suggest');
  const cats = (State.catalog || []).filter((s) => s.category === 'rising').slice(0, 10);
  sug.innerHTML = cats.map((s) => `<button data-s="${esc(s.name)}">+ ${esc(s.name)}</button>`).join('');
  sug.querySelectorAll('button').forEach((b) => b.onclick = () => add(b.dataset.s));
  $('#manualBtn').onclick = () => {
    if (!chosen.length) return toast('Add at least one skill.', 'err');
    const years = parseInt($('#mYears').value, 10);
    runAnalysis('manual', { skills: chosen, roles: $('#mRole').value ? [$('#mRole').value] : [], years_experience: isNaN(years) ? null : years });
  };
}

/* ---------------- analyze: run + loading ---------------- */
const PIPE = ['SkillsExtractor', 'MarketAnalyst', 'PathwayPlanner', 'ROIForecaster', 'CourseGrounder'];
function renderLoading() {
  $('#analyzeRoot').innerHTML = `
    <span class="eyebrow">Running the decision pipeline</span>
    <h2 style="margin:.2em 0 0">Analyzing your profile…</h2>
    <div class="pipeline-load card" style="padding:26px;margin-top:20px">
      ${PIPE.map((n, i) => `<div class="pl-step" id="pl-${i}"><span class="pl-dot"></span><span><strong>${n}</strong></span></div>`).join('')}
    </div>`;
  let i = 0;
  $('#pl-0').classList.add('on');
  State.loadTimer = setInterval(() => {
    const cur = $(`#pl-${i}`); if (cur) { cur.classList.remove('on'); cur.classList.add('done'); }
    i++;
    const nxt = $(`#pl-${i}`); if (nxt) nxt.classList.add('on');
    if (i >= PIPE.length) { clearInterval(State.loadTimer); State.loadTimer = null; }
  }, 170);
}

async function runAnalysis(kind, payload, platform = '') {
  State.lastInput = { kind, payload, platform };
  location.hash = '#/analyze'; showView('analyze');
  renderLoading();
  const started = Date.now();
  const call = kind === 'file' ? Api.analyzeFile(payload, platform)
    : kind === 'text' ? Api.analyzeText(payload, platform)
    : Api.analyzeManual(payload);
  try {
    const res = await call;
    const wait = 950 - (Date.now() - started);
    if (wait > 0) await delay(wait);
    if (State.loadTimer) { clearInterval(State.loadTimer); State.loadTimer = null; }
    State.result = res; State.selected = 0;
    renderResults(res);
  } catch (e) {
    if (State.loadTimer) { clearInterval(State.loadTimer); State.loadTimer = null; }
    toast(e.message || 'Analysis failed.', 'err');
    renderAnalyzeIntro();
  }
}

/* ---------------- results ---------------- */
function renderResults(r) {
  const root = $('#analyzeRoot');
  const p = r.profile;
  const savedTag = r.saved ? `<span class="tag" style="color:var(--pine)">✓ Saved to your history</span>`
    : `<span class="tag">Guest run — not saved</span>`;
  const profBits = [];
  if (p.roles && p.roles.length) profBits.push(esc(p.roles[0]));
  if (p.years_experience != null) profBits.push(`${p.years_experience} yrs`);
  if (p.education) profBits.push(esc(p.education));

  const chips = p.skills.map((sid) => {
    const f = r.forecasts[sid]; if (!f) return '';
    const cls = f.trend_direction === 'up' ? 'is-up' : f.trend_direction === 'down' ? 'is-down' : '';
    const spark = Charts.sparkline(f.data_points.map((d) => d.value), { color: Charts.colorFor(f.trend_direction) });
    return `<div class="card skill-chip ${cls}">
      <div class="spark">${spark}</div>
      <div class="sc-body">
        <div class="sc-name">${esc(f.skill_label)}</div>
        <div class="sc-tag ${f.trend_direction === 'up' ? 'up' : f.trend_direction === 'down' ? 'down' : 'flat'}">${arrow(f.trend_direction)} ${pct(f.growth_rate_annual)}/yr</div>
      </div></div>`;
  }).join('');

  const recs = (p.recommended_skills || []).map((sid) => esc((p.recommended_skill_labels || {})[sid] || sid));
  const recHtml = recs.length ? `<div style="margin-bottom:22px"><span class="hint" style="color:var(--ink-faint);font-size:.84rem">Worth adding to future-proof your profile: </span>
    ${recs.map((n) => `<span class="pill-gap" style="margin:2px">${n}</span>`).join('')}</div>` : '';

  const cards = r.pathways.map((pw, i) => pathwayCard(pw, i)).join('');

  root.innerHTML = `
    <div class="result-head">
      <div>
        <span class="eyebrow">Your career map</span>
        <div class="result-title serif">${esc(r.title)}</div>
        <div class="result-meta">${savedTag}
          <span class="tag mono">⚡ ${r.generated_ms}ms</span>
          <span class="tag mono">${esc(Object.values(r.provider_status || {}).every((v) => v === 'local') ? 'local engine' : 'cloud providers')}</span>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <div class="persona-toggle" id="personaToggle">
          <button data-persona="student">🎓 Student</button>
          <button data-persona="professional">💼 Professional</button>
        </div>
        ${!r.saved ? `<button class="btn btn-amber btn-sm" id="saveBtn">🔒 Log in to save</button>` : ''}
        ${r.saved ? `<button class="btn btn-ghost btn-sm" id="delBtn">🗑 Delete</button>` : ''}
        <button class="btn btn-ghost btn-sm" id="newBtn">＋ New analysis</button>
      </div>
    </div>
    ${profBits.length ? `<div class="profile-line">${profBits.join(' &nbsp;·&nbsp; ')}</div>` : ''}
    ${p.coverage_note ? `<div class="coverage-note">⚠️ ${esc(p.coverage_note)}</div>` : ''}

    <div class="subhead"><h2>Your skills, forecast</h2><span class="hint">3-year demand trend per skill · ▲ rising ▼ declining</span></div>
    <div class="chips-grid">${chips || '<p class="muted">No in-domain skills detected.</p>'}</div>
    ${recHtml}

    <div class="subhead" style="margin-top:38px"><h2>3 future-proof pathways</h2><span class="hint">ranked by coverage × demand × payoff × achievability</span></div>
    <div class="paths">${cards}</div>

    <div id="drill"></div>

    <div class="subhead" id="jobsHead" style="margin-top:38px">
      <h2>💼 Jobs matched to you</h2><span class="hint">real openings ranked by your skill match</span>
    </div>
    <div id="jobsPanel">
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <input id="jobLoc" placeholder="Location (e.g. Pune)" style="padding:.6em .9em;border:1px solid var(--line);border-radius:var(--r);font:inherit;background:var(--card)">
        <button class="btn btn-primary" id="findJobsBtn">Find matching jobs →</button>
        <span class="muted" style="font-size:.82rem">Live via JSearch/Adzuna when keyed · sample fallback otherwise.</span>
      </div>
    </div>

    <div class="card trace-strip" style="margin-top:34px">
      <h4>🧠 How PathFinder decided — ${r.trace.length}-agent trace</h4>
      <div class="trace-flow">
        ${r.trace.map((t) => `<div class="trace-node">
          <div class="tn">${esc(t.agent_name)}</div>
          <div class="tms">${t.ms_taken} ms</div>
          <div class="tout">${esc(summarize(t.outputs_summary))}</div>
        </div>`).join('')}
      </div>
    </div>
    <p class="datasource" style="margin-top:14px">Providers this run — extraction: <b>${esc(r.provider_status.skill_extraction)}</b> · forecast: <b>${esc(r.provider_status.forecast)}</b> · courses: <b>${esc(r.provider_status.course_grounding)}</b>. Set GEMINI_API_KEY / BQML_DATASET / VERTEX_* to switch these to Google Cloud.</p>`;

  root.querySelectorAll('.path-card').forEach((c) => c.onclick = () => { State.selected = +c.dataset.i; renderDrill(); highlightCards(); });
  $('#newBtn').onclick = () => { State.result = null; renderAnalyzeIntro(); };
  if ($('#delBtn')) $('#delBtn').onclick = () => deleteCurrent();
  if ($('#saveBtn')) $('#saveBtn').onclick = () => {
    State.pendingAfterAuth = () => { if (State.lastInput) runAnalysis(State.lastInput.kind, State.lastInput.payload, State.lastInput.platform || ''); };
    openAuth('register');
  };
  renderDrill(); highlightCards();
  initPersona(r);
  if ($('#findJobsBtn')) $('#findJobsBtn').onclick = renderJobsPanel;
}

function summarize(o) {
  if (o == null) return '';
  if (typeof o === 'string') return o;
  try {
    const parts = [];
    for (const [k, v] of Object.entries(o)) {
      const val = Array.isArray(v) ? (v.length > 3 ? v.slice(0, 3).join(', ') + '…' : v.join(', ')) : v;
      parts.push(`${k}: ${val}`);
    }
    return parts.join(' · ').slice(0, 120);
  } catch { return ''; }
}

function pathwayCard(pw, i) {
  const spark = pw.signal_forecast ? Charts.sparkline(pw.signal_forecast.data_points.map((d) => d.value), { w: 100, h: 34, color: Charts.colorFor(pw.signal_forecast.trend_direction) }) : '';
  return `<div class="card path-card" data-i="${i}">
    <div class="path-top">
      <div><div class="rank">PATHWAY #${pw.rank}</div><h3>${esc(pw.role)}</h3></div>
      ${Charts.matchRing(pw.match_score)}
    </div>
    <div class="path-spark">${spark}</div>
    <div class="path-stats">
      <div class="stat"><div class="k">Salary uplift</div><div class="v pos">+${inr(pw.salary_uplift_inr)}</div></div>
      <div class="stat"><div class="k">Demand</div><div class="v pos">${pct(pw.demand_growth_annual)}/yr</div></div>
      <div class="stat"><div class="k">Time to ready</div><div class="v">~${pw.time_to_ready_months} mo</div></div>
      <div class="stat"><div class="k">You cover</div><div class="v">${pw.overlap_percentage}%</div></div>
    </div>
    <div class="cta-row">See why &amp; courses →</div>
  </div>`;
}
function highlightCards() {
  document.querySelectorAll('.path-card').forEach((c) => c.classList.toggle('sel', +c.dataset.i === State.selected));
}

function renderDrill() {
  const pw = State.result.pathways[State.selected]; if (!pw) return;
  const f = pw.signal_forecast;
  const chart = f ? Charts.forecastChart(f.data_points, { direction: f.trend_direction }) : '';
  const have = (pw.transferable_skills || []).map((s) => `<span class="pill-have">${esc(s)}</span>`).join('') || '<span class="muted" style="font-size:.85rem">Starting fresh here.</span>';
  const gap = (pw.gap_skills || []).slice(0, 6).map((s) => `<span class="pill-gap">${esc(s)}</span>`).join('');
  const courseCard = (c) => `
    <div class="card course">
      <div class="prov">${esc(c.provider)}${c.free ? ' · Free' : ''}</div>
      <h4>${esc(c.title)}</h4>
      <div class="reason">${esc(c.match_reason)}</div>
      <div class="meta"><span>${c.hours}h</span><span>${esc(c.level)}</span><span class="rating">★ ${c.rating}</span><span>${esc(c.cost)}</span></div>
      <div style="display:flex;gap:6px;margin-top:6px">
        <a class="btn btn-ghost btn-sm" href="${esc(c.url)}" target="_blank" rel="noopener">Open ↗</a>
        <button class="btn btn-ghost btn-sm" data-track data-cid="${esc(c.id)}" data-ct="${esc(c.title)}" data-cp="${esc(c.provider)}" data-cu="${esc(c.url)}" data-cs="${esc((c.skills || []).join(','))}">＋ Track</button>
      </div>
    </div>`;
  const freeC = (pw.courses || []).filter((c) => c.track === 'free_gov');
  const paidC = (pw.courses || []).filter((c) => c.track !== 'free_gov');
  const courseGroup = (label, sub, list) => list.length ? `
    <div style="margin-top:14px">
      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:2px">
        <span class="eyebrow">${label}</span><span class="muted" style="font-size:.76rem">${sub}</span>
      </div>
      <div class="course-list">${list.map(courseCard).join('')}</div>
    </div>` : '';

  $('#drill').innerHTML = `<div class="card drill">
    <div class="drill-grid">
      <div class="chart-box">
        <span class="eyebrow">Demand forecast — ${esc(pw.signal_skill)}</span>
        <p class="muted" style="font-size:.85rem;margin:.3em 0 .6em">A core skill for <b>${esc(pw.role)}</b>, forecast ${pct(f ? f.growth_rate_annual : 0)}/yr.</p>
        ${chart}
        <div class="chart-legend">
          <span class="leg"><span class="swatch" style="background:${Charts.colorFor(f ? f.trend_direction : 'flat')}"></span> history</span>
          <span class="leg"><span class="swatch" style="background:${Charts.colorFor(f ? f.trend_direction : 'flat')};opacity:.6"></span> forecast + band</span>
          <span class="leg muted">${esc(f ? f.data_source : '')}</span>
        </div>
      </div>
      <div class="why">
        <h4>Why this fits you</h4>
        <div class="explain">${esc(pw.explanation)}</div>
        <div class="why-metrics">
          <div class="wm"><div class="k">Skill coverage</div><div class="v">${pw.overlap_percentage}%</div></div>
          <div class="wm"><div class="k">Demand growth</div><div class="v" style="color:var(--pine)">${pct(pw.demand_growth_annual)}/yr</div></div>
          <div class="wm"><div class="k">Salary uplift</div><div class="v" style="color:var(--pine)">+${inr(pw.salary_uplift_inr)}</div></div>
          <div class="wm"><div class="k">Time to ready</div><div class="v">~${pw.time_to_ready_months} mo</div></div>
        </div>
        <div style="font-size:.8rem;color:var(--ink-faint);text-transform:uppercase;letter-spacing:.08em;font-family:var(--font-mono);margin-bottom:4px">Skills you already bring</div>
        <div class="skill-pills">${have}</div>
        ${gap ? `<div style="font-size:.8rem;color:var(--ink-faint);text-transform:uppercase;letter-spacing:.08em;font-family:var(--font-mono);margin:12px 0 4px">Skills to build</div><div class="skill-pills">${gap}</div>` : ''}
        <div class="datasource">${esc(pw.data_source)} · Salary basis: public India salary bands (${inr(pw.salary_current_inr)} → ${inr(pw.salary_target_inr)}/yr).</div>
      </div>
    </div>
    <div class="courses">
      <span class="eyebrow" style="font-size:.8rem">Start here — grounded courses (real links · zero fabricated)</span>
      ${courseGroup('🆓 Free · Govt, YouTube &amp; Public', 'SWAYAM · NPTEL · YouTube · freeCodeCamp · Kaggle · MS Learn — ₹0 to learn', freeC)}
      ${courseGroup('🎓 Paid · Certificate courses', 'Coursera · edX — pay for the course / certificate', paidC)}
    </div>
  </div>`;
  $('#drill').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function deleteCurrent() {
  if (!State.result || !State.result.id) return;
  if (!confirm('Delete this saved analysis?')) return;
  try { await Api.deleteAnalysis(State.result.id); toast('Analysis deleted.'); State.result = null; location.hash = '#/history'; }
  catch (e) { toast(e.message || 'Could not delete.', 'err'); }
}

/* ---------------- history ---------------- */
async function renderHistory() {
  const root = $('#historyRoot');
  root.innerHTML = `<span class="eyebrow">Your account</span><h2 style="margin:.2em 0 20px">My analyses</h2><div id="histList" class="hist-list"><p class="muted">Loading…</p></div>`;
  try {
    const items = await Api.history();
    const list = $('#histList');
    if (!items.length) { list.innerHTML = `<div class="empty-state card"><div class="big">🗺️</div><p>No saved analyses yet.</p><button class="btn btn-primary" data-nav="#/analyze">Run your first analysis →</button></div>`; return; }
    list.innerHTML = items.map((it) => `<div class="card hist-item" data-id="${esc(it.id)}">
      <div style="font-size:1.4rem">🧭</div>
      <div class="hi-body"><div class="hi-title">${esc(it.title)}</div><div class="hi-date mono">${new Date(it.created_at).toLocaleString()}</div></div>
      <button class="btn btn-ghost btn-sm" data-open="${esc(it.id)}">Open</button>
      <button class="btn btn-ghost btn-sm" data-del="${esc(it.id)}" style="color:var(--terracotta)">Delete</button>
    </div>`).join('');
    list.querySelectorAll('[data-open]').forEach((b) => b.onclick = (e) => { e.stopPropagation(); openHistory(b.dataset.open); });
    list.querySelectorAll('.hist-item').forEach((c) => c.onclick = () => openHistory(c.dataset.id));
    list.querySelectorAll('[data-del]').forEach((b) => b.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm('Delete this analysis?')) return;
      try { await Api.deleteAnalysis(b.dataset.del); toast('Deleted.'); renderHistory(); }
      catch (err) { toast(err.message, 'err'); }
    });
  } catch (e) {
    $('#histList').innerHTML = `<p class="muted">Could not load history: ${esc(e.message)}</p>`;
  }
}
async function openHistory(id) {
  try { const res = await Api.getAnalysis(id); State.result = res; State.selected = 0; showView('analyze'); location.hash = '#/analyze'; renderResults(res); }
  catch (e) { toast(e.message || 'Could not open.', 'err'); }
}

/* ---------------- professional: persona + job matches ---------------- */
function initPersona(r) {
  let persona = (Store.user && Store.user.persona && Store.user.persona !== 'auto') ? Store.user.persona : null;
  if (!persona) persona = (r.profile.years_experience || 0) >= 1 ? 'professional' : 'student';
  applyPersona(persona);
  const tg = $('#personaToggle');
  if (tg) tg.querySelectorAll('[data-persona]').forEach((b) => b.onclick = () => {
    applyPersona(b.dataset.persona);
    if (Store.user) Api.updatePersona(b.dataset.persona).then((u) => { Store.user = u; }).catch(() => {});
  });
}
function applyPersona(persona) {
  document.querySelectorAll('#personaToggle [data-persona]').forEach((b) => b.classList.toggle('on', b.dataset.persona === persona));
  const show = persona === 'professional';
  if ($('#jobsHead')) $('#jobsHead').classList.toggle('hidden', !show);
  if ($('#jobsPanel')) $('#jobsPanel').classList.toggle('hidden', !show);
}
async function renderJobsPanel() {
  const r = State.result, panel = $('#jobsPanel');
  const loc = ($('#jobLoc') && $('#jobLoc').value.trim()) || '';
  panel.innerHTML = '<p class="muted">Finding real jobs matched to your skills…</p>';
  try {
    const body = r.id ? { analysis_id: r.id, location: loc, limit: 6 } : { skills: r.profile.skills, location: loc, limit: 6 };
    const res = await Api.matchJobs(body);
    if (!res.matches.length) { panel.innerHTML = '<p class="muted">No matching jobs found — try a different location.</p>'; return; }
    panel.innerHTML = `<p class="muted" style="font-size:.82rem;margin-bottom:12px">Source: <b>${esc(res.source)}</b> · ${res.count} matches for "${esc(res.query)}"</p>
      <div class="jobs-grid">${res.matches.map(jobCard).join('')}</div>`;
  } catch (e) { panel.innerHTML = `<p class="muted">Could not load jobs: ${esc(e.message)}</p>`; }
}
function jobCard(m) {
  const j = m.job;
  const have = m.matched_skills.slice(0, 6).map((s) => `<span class="pill-have">${esc(s)}</span>`).join('') || '<span class="muted" style="font-size:.8rem">—</span>';
  const gap = m.gap_skills.slice(0, 5).map((s) => `<span class="pill-gap">${esc(s)}</span>`).join('');
  const courses = (m.courses || []).slice(0, 3).map((c) => `<div class="mini-course"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>
      <button class="btn btn-ghost btn-sm" data-track data-cid="${esc(c.id)}" data-ct="${esc(c.title)}" data-cp="${esc(c.provider)}" data-cu="${esc(c.url)}" data-cs="${esc((c.skills || []).join(','))}">＋ Track</button></div>`).join('');
  return `<div class="card job-card">
    <div class="path-top">
      <div><div class="job-src">${esc(j.source)}</div><h3 style="margin:.15em 0">${esc(j.title)}</h3><div class="job-meta">${esc(j.company)}${j.location ? ' · ' + esc(j.location) : ''}</div></div>
      ${Charts.matchRing(m.match_pct)}
    </div>
    ${j.salary ? `<div class="job-meta">💰 ${esc(j.salary)}${j.posted ? ' · ' + esc(j.posted) : ''}</div>` : ''}
    <div><div style="font-size:.72rem;color:var(--ink-faint);font-family:var(--font-mono);text-transform:uppercase;margin-bottom:3px">You have</div><div class="skill-pills">${have}</div></div>
    ${gap ? `<div><div style="font-size:.72rem;color:var(--ink-faint);font-family:var(--font-mono);text-transform:uppercase;margin:6px 0 3px">Learn to qualify</div><div class="skill-pills">${gap}</div></div>` : ''}
    ${courses ? `<div class="job-courses">${courses}</div>` : ''}
    <a class="btn btn-primary btn-sm" href="${esc(j.url)}" target="_blank" rel="noopener" style="margin-top:auto">Apply ↗</a>
  </div>`;
}

/* ---------------- learning tracker ---------------- */
async function renderLearning() {
  const root = $('#learningRoot');
  root.innerHTML = `<span class="eyebrow">Your account</span><h2 style="margin:.2em 0 18px">🎓 My learning</h2>
    <div id="progressBox"></div>
    <div class="subhead" style="margin-top:26px"><h2 style="font-size:1.3rem">Tracked courses</h2></div>
    <div id="learnList"><p class="muted">Loading…</p></div>`;
  await refreshLearning();
  try {
    const hist = await Api.history();
    if (hist.length) {
      const pr = await Api.progress(hist[0].id);
      $('#progressBox').innerHTML = progressCard(pr, hist[0].title);
    } else {
      $('#progressBox').innerHTML = '<p class="muted">Run an analysis, then track courses here to watch your pathway match grow as you complete them.</p>';
    }
  } catch { /* progress optional */ }
}
async function refreshLearning() {
  const list = $('#learnList');
  const items = await Api.learning();
  if (!items.length) { list.innerHTML = `<div class="empty-state card"><div class="big">📚</div><p>Nothing tracked yet. Open a pathway or a matched job and hit "＋ Track" on a course.</p><button class="btn btn-primary" data-nav="#/analyze">Run an analysis →</button></div>`; return; }
  list.innerHTML = `<div class="hist-list">${items.map(learnRow).join('')}</div>`;
  list.querySelectorAll('[data-ls]').forEach((sel) => sel.onchange = async () => {
    try { await Api.patchLearning(sel.dataset.ls, sel.value); toast('Updated.'); renderLearning(); }
    catch (e) { toast(e.message, 'err'); }
  });
  list.querySelectorAll('[data-ldel]').forEach((b) => b.onclick = async () => {
    try { await Api.deleteLearning(b.dataset.ldel); toast('Removed.'); renderLearning(); }
    catch (e) { toast(e.message, 'err'); }
  });
}
function learnRow(it) {
  const opt = (v, l) => `<option value="${v}"${it.status === v ? ' selected' : ''}>${l}</option>`;
  return `<div class="card learn-item">
    <div style="font-size:1.3rem">${it.status === 'completed' ? '✅' : '📘'}</div>
    <div class="li-body"><div class="hi-title" style="font-size:1.02rem">${esc(it.title)}</div><div class="hi-date mono">${esc(it.provider || '')}</div></div>
    <select data-ls="${esc(it.id)}">${opt('saved', 'Saved')}${opt('in_progress', 'In progress')}${opt('completed', 'Completed')}</select>
    ${it.url ? `<a class="btn btn-ghost btn-sm" href="${esc(it.url)}" target="_blank" rel="noopener">Open ↗</a>` : ''}
    <button class="btn btn-ghost btn-sm" data-ldel="${esc(it.id)}" style="color:var(--terracotta)">Remove</button>
  </div>`;
}
function progressCard(pr, title) {
  if (!pr.pathways.length) return '<p class="muted">No pathways to track yet.</p>';
  const rows = pr.pathways.map((p) => `
    <div class="prog-row">
      <div class="prog-head"><span class="pn">${esc(p.role)}</span><span>${p.before_pct}% → ${p.after_pct}% ${p.delta > 0 ? `<span class="prog-delta">+${p.delta}</span>` : ''}</span></div>
      <div class="prog-bar"><div class="prog-fill" style="width:${p.after_pct}%"></div><div class="prog-before" style="left:${p.before_pct}%"></div></div>
    </div>`).join('');
  const acq = pr.acquired_skills.length ? `<div style="margin-top:8px;font-size:.85rem;color:var(--ink-soft)">Acquired: ${pr.acquired_skills.map((s) => `<span class="pill-have">${esc(s)}</span>`).join(' ')}</div>` : '';
  return `<div class="card prog-card">
    <span class="eyebrow">Your progress — ${esc(title)}</span>
    <p class="muted" style="font-size:.84rem;margin:.3em 0 .6em">As you complete tracked courses, your skill coverage for each pathway rises. The red line marks where you started.</p>
    ${rows}${acq}
    ${pr.completed_count === 0 ? '<p class="muted" style="font-size:.82rem;margin-top:8px">Mark a tracked course "Completed" to see your coverage jump.</p>' : ''}
  </div>`;
}

/* ---------------- boot ---------------- */
(async function boot() {
  loadMeta();
  Api.skills().then((s) => State.catalog = s).catch(() => {});
  if (Store.token) { try { Store.user = await Api.me(); } catch { Store.clear(); } }
  renderNav();
  $('#tryAshaBtn').onclick = () => runAnalysis('text', ASHA_SAMPLE);
  if (!location.hash) location.hash = '#/';
  route();
})();
