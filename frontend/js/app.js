/* PathFinder — SPA controller: routing, auth, analyze flow, results, history. */

const ASHA_SAMPLE = `Asha Kulkarni
Data Entry Operator | Pune, Maharashtra
PROFILE: Detail-oriented Data Entry Operator with 8 years of experience in high-volume data entry, record keeping and document filing.
SKILLS: Data Entry, Typing, Microsoft Excel, Basic MS Office, Filing, Cash Handling, Attention to Detail, Customer Service, Business Communication, Time Management
EXPERIENCE: Senior Data Entry Operator, Acme Logistics (2018-2026). Entered and validated 500+ records daily in Excel. Maintained filing with 99.8% accuracy. Handled customer telephone queries and the billing counter.
EDUCATION: B.Com, Savitribai Phule Pune University (2016)`;

const State = { result: null, selected: 0, lastInput: null, loadTimer: null, catalog: null, pendingAfterAuth: null, auth: null, roadmap: null, roles: null, persona: null, disc: null, pendingDirection: null };

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
    $('#providerText').textContent = cloud.length ? 'Google Cloud AI' : 'AI engine';
    $('#footMeta').textContent = `${m.counts.skills} skills · ${m.counts.courses} courses · reproducible forecasts`;
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
        <button data-act="profile">👤 My profile</button>
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
      else if (a === 'profile') location.hash = '#/profile';
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

/* ---------------- Google Identity Services ---------------- */
let _gisLoading = null;
function loadGis() {
  if (window.google && window.google.accounts && window.google.accounts.id) return Promise.resolve();
  if (_gisLoading) return _gisLoading;
  _gisLoading = new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client';
    s.async = true; s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => resolve();  // email login still works if GIS can't load
    document.head.appendChild(s);
  });
  return _gisLoading;
}
function renderGoogleButton(hostId) {
  if (!State.auth || !State.auth.google_enabled) return;
  loadGis().then(() => {
    const host = document.getElementById(hostId);
    if (!host || !window.google || !google.accounts || !google.accounts.id) return;
    try {
      google.accounts.id.initialize({
        client_id: State.auth.google_client_id,
        callback: (resp) => onGoogleCredential(resp.credential),
      });
      google.accounts.id.renderButton(host, { theme: 'outline', size: 'large', text: 'continue_with', shape: 'pill', width: 320 });
    } catch (e) { /* GIS misconfigured — email login remains available */ }
  });
}
async function onGoogleCredential(credential) {
  try {
    const res = await Api.googleLogin(credential);
    Store.token = res.access_token;
    Store.user = await Api.me();
    $('#authModal').innerHTML = '';
    renderNav();
    toast('Signed in with Google.');
    const after = State.pendingAfterAuth; State.pendingAfterAuth = null;
    if (after) after();
  } catch (e) {
    toast(e.message || 'Google sign-in failed. Please try again.', 'err');
  }
}

function openAuth(mode) {
  const isReg = mode === 'register';
  const googleOn = !!(State.auth && State.auth.google_enabled);
  const googleBlock = googleOn
    ? `<div id="googleBtnHost" class="gbtn-host"></div><div class="auth-divider"><span>or</span></div>`
    : '';
  $('#authModal').innerHTML = `<div class="modal-back" id="modalBack">
    <div class="card modal" style="position:relative">
      <button class="close-x" id="authClose" aria-label="Close">×</button>
      <span class="eyebrow">${isReg ? 'Create your account' : 'Welcome back'}</span>
      <h2>${isReg ? 'Save your career map' : 'Log in'}</h2>
      <p class="muted" style="font-size:.9rem;margin-top:-.4em">${isReg ? 'Free. Your analyses are saved to your history.' : 'Access your saved analyses.'}</p>
      ${googleBlock}
      <form id="authForm">
        <div class="field"><label>Email</label><input type="email" id="authEmail" required autocomplete="email" placeholder="you@example.com"></div>
        <div class="field"><label>Password ${isReg ? '<span class="muted">(min 8 characters)</span>' : ''}</label>
          <input type="password" id="authPass" required autocomplete="${isReg ? 'new-password' : 'current-password'}" placeholder="••••••••"></div>
        ${!isReg ? '<div class="forgot-row"><button type="button" id="forgotLink" class="linklike">Forgot password?</button></div>' : ''}
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
  if (googleOn) renderGoogleButton('googleBtnHost');
  const forgotBtn = $('#forgotLink');
  if (forgotBtn) forgotBtn.onclick = () => openForgot($('#authEmail').value.trim());
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

/* ---------------- forgot / reset password ---------------- */
function openForgot(prefill = '') {
  $('#authModal').innerHTML = `<div class="modal-back" id="modalBack">
    <div class="card modal" style="position:relative">
      <button class="close-x" id="fpClose" aria-label="Close">×</button>
      <span class="eyebrow">Reset password</span>
      <h2>Forgot your password?</h2>
      <p class="muted" style="font-size:.9rem;margin-top:-.4em">Enter your account email and we'll send you a link to set a new password.</p>
      <form id="fpForm">
        <div class="field"><label>Email</label><input type="email" id="fpEmail" required autocomplete="email" placeholder="you@example.com" value="${esc(prefill)}"></div>
        <div class="field err-msg hidden" id="fpMsg"></div>
        <button type="submit" class="btn btn-primary btn-block" id="fpSubmit">Send reset link</button>
      </form>
      <div class="switch"><button id="fpBack">← Back to log in</button></div>
    </div></div>`;
  const close = () => { $('#authModal').innerHTML = ''; };
  $('#fpClose').onclick = close;
  $('#modalBack').onclick = (e) => { if (e.target.id === 'modalBack') close(); };
  $('#fpBack').onclick = () => openAuth('login');
  $('#fpForm').onsubmit = async (e) => {
    e.preventDefault();
    const email = $('#fpEmail').value.trim(), btn = $('#fpSubmit'), msg = $('#fpMsg');
    btn.disabled = true; btn.textContent = 'Sending…';
    try {
      const r = await Api.forgotPassword(email);
      msg.textContent = (r && r.detail) || 'If an account exists for that email, a reset link has been sent.';
      msg.classList.remove('hidden', 'err-msg'); msg.classList.add('ok-msg');
      btn.textContent = 'Sent ✓';
    } catch (err) {
      msg.textContent = err.message || 'Something went wrong. Please try again.';
      msg.classList.remove('hidden');
      btn.disabled = false; btn.textContent = 'Send reset link';
    }
  };
  setTimeout(() => $('#fpEmail')?.focus(), 50);
}

function openReset(token) {
  $('#authModal').innerHTML = `<div class="modal-back" id="modalBack">
    <div class="card modal" style="position:relative">
      <span class="eyebrow">Reset password</span>
      <h2>Set a new password</h2>
      <p class="muted" style="font-size:.9rem;margin-top:-.4em">Choose a new password for your PathFinder account.</p>
      <form id="rpForm">
        <div class="field"><label>New password <span class="muted">(min 8 characters)</span></label>
          <input type="password" id="rpPass" required autocomplete="new-password" placeholder="••••••••"></div>
        <div class="field err-msg hidden" id="rpMsg"></div>
        <button type="submit" class="btn btn-primary btn-block" id="rpSubmit">Update password</button>
      </form>
    </div></div>`;
  const done = () => { $('#authModal').innerHTML = ''; location.hash = '#/'; };
  $('#modalBack').onclick = (e) => { if (e.target.id === 'modalBack') done(); };
  $('#rpForm').onsubmit = async (e) => {
    e.preventDefault();
    const pw = $('#rpPass').value, msg = $('#rpMsg'), btn = $('#rpSubmit');
    if (pw.length < 8) { msg.textContent = 'Password must be at least 8 characters.'; msg.classList.remove('hidden'); return; }
    btn.disabled = true; btn.textContent = 'Updating…';
    try {
      await Api.resetPassword(token, pw);
      $('#authModal').innerHTML = '';
      location.hash = '#/';
      toast('Password updated — please log in.');
      openAuth('login');
    } catch (err) {
      msg.textContent = err.status === 400 ? 'This reset link is invalid or has expired. Request a new one.' : (err.message || 'Reset failed.');
      msg.classList.remove('hidden');
      btn.disabled = false; btn.textContent = 'Update password';
    }
  };
  setTimeout(() => $('#rpPass')?.focus(), 50);
}

/* ---------------- Career goal — guided wizard + reverse roadmap ---------------- */
const SECTORS = ['IT / Software', 'Data & Analytics', 'Finance & Banking', 'Manufacturing',
  'Mechanical / Engineering', 'Design / Creative', 'Healthcare', 'Government / PSU',
  'E-commerce & Retail', 'Marketing / Media', 'Education', 'Legal', 'Operations', 'Other'];
const LEVELS = [
  { id: 'student', icon: '🎓', label: 'Student', desc: 'Still studying or in college' },
  { id: 'fresher', icon: '🌱', label: 'Fresher', desc: 'Graduated, seeking my first role' },
  { id: 'professional', icon: '💼', label: 'Working professional', desc: 'Working now — want to grow or switch' },
];
const WIZ_STEPS = ['Goal', 'Sector', 'Level', 'Confirm'];
const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function renderGoal() {
  if (State.pendingDirection) { const b = State.pendingDirection; State.pendingDirection = null; generateRoadmap(b); return; }
  if (State.roadmap) { renderRoadmapView($('#goalRoot'), State.roadmap); return; }
  if (!State.wiz) State.wiz = { step: 0, goal_text: '', sector: '', level: '', resolved: null };
  if (!State.roles) Api.roles().then((r) => { State.roles = r; if (State.wiz && State.wiz.step === 0) renderWizStep(); }).catch(() => {});
  const root = $('#goalRoot');
  const dots = WIZ_STEPS.map((s, i) => `<div class="wiz-dot${i === State.wiz.step ? ' active' : ''}${i < State.wiz.step ? ' done' : ''}"><span>${i < State.wiz.step ? '✓' : i + 1}</span><label>${s}</label></div>`).join('');
  root.innerHTML = `<div class="wiz-head">
      <span class="eyebrow">AI career counsellor</span>
      <div class="wiz-progress" id="wizProgress">${dots}</div>
    </div>
    <div id="wizBody"></div>`;
  renderWizStep();
}

function renderWizStep() {
  const w = State.wiz, body = $('#wizBody');
  if (!body) return;
  // keep progress dots in sync
  const prog = $('#wizProgress');
  if (prog) prog.innerHTML = WIZ_STEPS.map((s, i) => `<div class="wiz-dot${i === w.step ? ' active' : ''}${i < w.step ? ' done' : ''}"><span>${i < w.step ? '✓' : i + 1}</span><label>${s}</label></div>`).join('');
  const back = w.step > 0 ? '<button class="btn btn-ghost btn-sm wiz-back" id="wizBack">← Back</button>' : '';
  let html = '';
  if (w.step === 0) {
    html = `<div class="wiz-step card">${back}
      <h2 class="wiz-q">What do you want to become?</h2>
      <p class="muted wiz-sub">Tell us your dream role — a title, or just what you'd love to do. We'll ground it to a real, in-demand path.</p>
      <input id="wizGoal" class="goal-input wiz-input" placeholder="e.g. I want to analyse data and build dashboards" autocomplete="off" value="${esc(w.goal_text)}">
      <div class="wiz-actions"><button class="btn btn-primary" id="wizGoalNext">Continue →</button></div>
      <div class="wiz-quick"><span class="muted">Popular:</span> ${(State.roles || []).slice(0, 4).map((r) => `<button class="wiz-chip" data-quick="${esc(r.name)}">${esc(r.name)}</button>`).join('')}</div>`;
  } else if (w.step === 1) {
    const isOther = w.sectorMode === 'other';
    const ready = isOther ? (w.sector || '').trim() : w.sector;
    html = `<div class="wiz-step card">${back}
      <h2 class="wiz-q">Which field excites you?</h2>
      <p class="muted wiz-sub">This frames your roadmap for the right industry — pick one, or choose <b>Other</b> to type your own.</p>
      <div class="wiz-chipgrid">${SECTORS.map((s, i) => `<button class="wiz-chip lg${(isOther && s === 'Other') || (!isOther && w.sector === s) ? ' sel' : ''}" data-sector="${esc(s)}" style="animation-delay:${i * 28}ms">${esc(s)}</button>`).join('')}</div>
      <input id="wizSectorOther" class="goal-input wiz-input" placeholder="Type your field — e.g. Aerospace, Culinary, Architecture…" autocomplete="off" value="${esc(isOther ? (w.sector || '') : '')}" style="${isOther ? '' : 'display:none'};margin-top:2px">
      <div class="wiz-actions"><button class="btn btn-primary" id="wizSectorNext"${ready ? '' : ' disabled'}>Continue →</button></div>`;
  } else if (w.step === 2) {
    html = `<div class="wiz-step card">${back}
      <h2 class="wiz-q">Where are you right now?</h2>
      <p class="muted wiz-sub">So we set the right starting point.</p>
      <div class="wiz-levels">${LEVELS.map((l, i) => `<button class="wiz-level${w.level === l.id ? ' sel' : ''}" data-level="${l.id}" style="animation-delay:${i * 45}ms"><span class="wl-icon">${l.icon}</span><span class="wl-label">${l.label}</span><span class="wl-desc">${l.desc}</span></button>`).join('')}</div>`;
  } else {
    html = `<div class="wiz-step card">${back}
      <div id="confirmBody"><div class="wiz-resolving"><div class="wiz-spinner"></div><p class="muted">Finding your best-fit path…</p></div></div>`;
  }
  body.innerHTML = html + '</div>';
  wireWizStep();
  if (w.step === 3) runResolve();
  else setTimeout(() => body.querySelector('.wiz-input, .wiz-chip, .wiz-level')?.focus?.(), 70);
}

function wireWizStep() {
  const w = State.wiz;
  if ($('#wizBack')) $('#wizBack').onclick = () => { w.step = Math.max(0, w.step - 1); renderWizStep(); };
  if (w.step === 0) {
    const go = () => { const t = $('#wizGoal').value.trim(); if (!t) return $('#wizGoal').focus(); w.goal_text = t; w.step = 1; renderWizStep(); };
    $('#wizGoalNext').onclick = go;
    $('#wizGoal').onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } };
    $('#wizBody').querySelectorAll('[data-quick]').forEach((b) => b.onclick = () => { w.goal_text = b.dataset.quick; w.step = 1; renderWizStep(); });
  } else if (w.step === 1) {
    const other = $('#wizSectorOther'), next = $('#wizSectorNext');
    $('#wizBody').querySelectorAll('[data-sector]').forEach((b) => b.onclick = () => {
      $('#wizBody').querySelectorAll('[data-sector]').forEach((x) => x.classList.toggle('sel', x === b));
      if (b.dataset.sector === 'Other') {
        w.sectorMode = 'other'; w.sector = other.value.trim();
        other.style.display = ''; other.focus(); next.disabled = !w.sector;
      } else {
        w.sectorMode = 'preset'; w.sector = b.dataset.sector;
        other.style.display = 'none'; next.disabled = false;
      }
    });
    other.oninput = () => { if (w.sectorMode === 'other') { w.sector = other.value.trim(); next.disabled = !w.sector; } };
    other.onkeydown = (e) => { if (e.key === 'Enter' && (w.sector || '').trim()) { e.preventDefault(); w.step = 2; renderWizStep(); } };
    next.onclick = () => { w.step = 2; renderWizStep(); };
  } else if (w.step === 2) {
    $('#wizBody').querySelectorAll('[data-level]').forEach((b) => b.onclick = () => { w.level = b.dataset.level; w.step = 3; renderWizStep(); });
  }
}

async function runResolve() {
  const w = State.wiz;
  try {
    if (!State.roles) State.roles = await Api.roles().catch(() => []);
    w.resolved = await Api.resolveGoal({ goal_text: w.goal_text, sector: w.sector, level: w.level });
    renderConfirm(w.resolved);
  } catch (e) {
    const cb = $('#confirmBody');
    if (cb) { cb.innerHTML = `<p class="err-msg" style="display:block">${esc(e.message || 'Could not resolve your goal.')}</p><button class="btn btn-ghost" id="confirmRetry">← Try again</button>`; $('#confirmRetry').onclick = () => { w.step = 0; renderWizStep(); }; }
  }
}

function renderConfirm(res) {
  const w = State.wiz;
  const isAi = res.mode === 'ai';
  const title = isAi ? (res.role_title || w.goal_text) : res.role_name;
  $('#confirmBody').innerHTML = `
    <span class="eyebrow">${isAi ? '✦ AI-guided path' : (res.source === 'gemini' ? '✦ AI-matched to your goal' : 'Best match')}</span>
    <h2 class="wiz-q" style="margin-top:.15em">${isAi ? "We'll build a plan for" : 'We recommend'} <span class="accent-role">${esc(title)}</span></h2>
    ${isAi ? `<div class="ai-note"><span class="ai-badge">AI-guided</span> This field is outside PathFinder's grounded data &amp; analytics catalog — we'll generate an AI plan: skills &amp; sequence from Gemini, resources as suggested searches, and figures as estimates to verify.</div>` : ''}
    <p class="wiz-rationale">${esc(res.rationale)}</p>
    <div class="wiz-actions" style="flex-wrap:wrap">
      <button class="btn btn-primary" id="confirmBuild">${isAi ? 'Build my AI-guided roadmap →' : 'Yes, build my roadmap →'}</button>
      <button class="btn btn-ghost" id="confirmChange">${isAi ? 'Or pick a grounded role' : 'Choose a different role'}</button>
    </div>
    <div id="altList" class="role-grid hidden" style="margin-top:16px">${(res.alternatives || []).map(roleCard).join('')}</div>`;
  const opts = { goal_text: w.goal_text, sector: w.sector, level: w.level };
  $('#confirmBuild').onclick = () => generateRoadmap(isAi
    ? { mode: 'ai', target_role_title: res.role_title || w.goal_text, field: res.field || w.sector, ...opts }
    : { target_role_id: res.role_id, ...opts });
  $('#confirmChange').onclick = () => {
    const list = $('#altList'); list.classList.toggle('hidden');
    list.querySelectorAll('[data-role]').forEach((c) => c.onclick = () => generateRoadmap({ target_role_id: c.dataset.role, ...opts }));
  };
}

function roleCard(r) {
  return `<button class="card role-card" data-role="${esc(r.id)}">
    <div class="rc-name">${esc(r.name)}</div>
    <div class="rc-meta"><span class="rc-growth">▲ ${pct(r.demand_growth_annual)}/yr</span><span class="muted">${inr(r.salary_median_inr)}/yr</span></div>
    <div class="rc-desc">${esc(r.description)}</div>
  </button>`;
}

async function generateRoadmap(body) {
  const root = $('#goalRoot');
  root.innerHTML = `<div class="card wiz-step" style="text-align:center;padding:52px"><div class="wiz-spinner"></div><p class="muted" style="margin-top:14px">${body.mode === 'ai' ? 'Generating your AI-guided roadmap…' : 'Building your grounded roadmap…'}</p></div>`;
  if (Store.user && !body.skills && !body.analysis_id) {
    try { const h = await Api.history(); if (h.length) body.analysis_id = h[0].id; } catch { /* fine */ }
  }
  try {
    State.roadmap = await Api.createRoadmap(body);
    renderRoadmapView(root, State.roadmap);
  } catch (e) {
    root.innerHTML = `<div class="card"><p class="err-msg" style="display:block">${esc(e.message || 'Could not build a roadmap.')}</p><button class="btn btn-ghost" id="goalBack">← Start over</button></div>`;
    $('#goalBack').onclick = () => { State.roadmap = null; State.wiz = null; renderGoal(); };
  }
}

function renderRoadmapView(root, rm) {
  const courseChip = (c) => `<div class="rm-course${c.track === 'free_gov' ? ' is-free' : ''}">
    <div class="rmc-main"><span class="rmc-title">${esc(c.title)}</span><span class="rmc-prov">${esc(c.provider)}${c.free ? ' · Free' : ''}</span></div>
    <div class="rmc-actions">
      <a class="btn btn-ghost btn-sm" href="${esc(c.url)}" target="_blank" rel="noopener">Open ↗</a>
      <button class="btn btn-ghost btn-sm" data-track data-cid="${esc(c.id)}" data-ct="${esc(c.title)}" data-cp="${esc(c.provider)}" data-cu="${esc(c.url)}" data-cs="${esc((c.skills || []).join(','))}">＋ Track</button>
    </div></div>`;
  const phase = (p, i) => `<div class="rm-phase" style="animation-delay:${i * 70}ms">
    <div class="rm-node"><span class="rm-num">${p.index}</span></div>
    <div class="rm-card card">
      <div class="rm-head"><h4>${esc(p.title)}</h4><span class="rm-weeks">~${p.est_weeks} wks</span></div>
      <p class="rm-why">${esc(p.why)}</p>
      <div class="rm-courses">${(p.courses || []).map(courseChip).join('')}</div>
      <div class="rm-project">🛠 ${esc(p.project)}</div>
      <div class="rm-ready"><div class="rm-ready-bar"><span data-fill="${p.readiness_after}" style="transform:scaleX(0)"></span></div><span>You'll be <b>${p.readiness_after}%</b> ready for ${esc(rm.role)}</span></div>
    </div></div>`;
  const isAi = rm.mode === 'ai';
  const tag = [rm.level, rm.sector].filter(Boolean).join(' · ');
  const salaryTile = rm.salary_target_inr
    ? `<div class="wm"><div class="k">${rm.salary_estimated ? 'Salary · AI est.' : 'Salary target'}</div><div class="v" style="color:var(--pine)">${inr(rm.salary_target_inr)}/yr</div></div>`
    : '';
  const upliftTile = (!isAi && rm.salary_uplift_inr)
    ? `<div class="wm"><div class="k">Salary uplift</div><div class="v" style="color:var(--pine)">+${inr(rm.salary_uplift_inr)}</div></div>` : '';
  root.innerHTML = `
    <button class="btn btn-ghost btn-sm" id="rmBack" style="margin-bottom:14px">← Pick another goal</button>
    <div class="card rm-hero${isAi ? ' is-ai' : ''}">
      <span class="eyebrow">${isAi ? 'AI-guided roadmap' : 'Your roadmap to'}${tag ? ` · ${esc(tag)}` : ''}</span>
      <h2 style="margin:.1em 0">${esc(rm.role)}${isAi ? ' <span class="ai-badge">AI-guided</span>' : ''}</h2>
      ${rm.summary ? `<p class="rm-summary">${esc(rm.summary)}</p>` : `<p class="muted" style="max-width:62ch">${esc(rm.role_description)}</p>`}
      ${isAi && rm.ai_notice ? `<div class="ai-note">${esc(rm.ai_notice)}</div>` : ''}
      <div class="why-metrics rm-hero-metrics">
        <div class="wm"><div class="k">Readiness</div><div class="v">${rm.start_readiness}% → <span data-count="${rm.target_readiness}" data-suffix="%">0%</span></div></div>
        <div class="wm"><div class="k">Time to ready</div><div class="v">~<span data-count="${rm.months_estimate}" data-suffix=" mo">0 mo</span></div></div>
        ${salaryTile}${upliftTile}
      </div>
      ${rm.already_have && rm.already_have.length ? `<div style="margin-top:12px"><span class="muted" style="font-size:.8rem">You already bring: </span>${rm.already_have.map((s) => `<span class="pill-have">${esc(s)}</span>`).join(' ')}</div>` : ''}
      <div class="rm-actions"><button class="btn btn-primary" id="rmAdopt">${Store.user ? 'Start this roadmap → add to My Learning' : 'Log in to save & start'}</button></div>
      <div class="datasource">${esc(rm.data_source)}</div>
    </div>
    <div class="subhead" style="margin-top:26px"><h2 style="font-size:1.2rem">${rm.gap_count} steps to job-ready</h2><span class="hint">${isAi ? 'AI-suggested steps · resources are searches to verify' : 'grounded courses · real links · zero fabricated'}</span></div>
    <div class="rm-stepper">${rm.phases.map(phase).join('')}</div>`;
  $('#rmBack').onclick = () => { State.roadmap = null; State.wiz = null; renderGoal(); };
  $('#rmAdopt').onclick = () => adoptCurrentRoadmap();
  animateRoadmap();
}

function animateRoadmap() {
  const rm = reduceMotion();
  document.querySelectorAll('#goalRoot [data-fill]').forEach((el) => {
    const p = Math.max(0, Math.min(100, +el.dataset.fill || 0)) / 100;
    if (rm) { el.style.transform = `scaleX(${p})`; return; }
    requestAnimationFrame(() => requestAnimationFrame(() => { el.style.transform = `scaleX(${p})`; }));
  });
  document.querySelectorAll('#goalRoot [data-count]').forEach((el) => {
    const to = +el.dataset.count || 0, suf = el.dataset.suffix || '';
    if (rm) { el.textContent = to + suf; return; }
    const t0 = performance.now(), dur = 850;
    const tick = (now) => { const k = Math.min(1, (now - t0) / dur); el.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))) + suf; if (k < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
}

async function adoptCurrentRoadmap() {
  if (!Store.user) { State.pendingAfterAuth = () => (location.hash = '#/goal'); toast('Log in to save your roadmap.'); openAuth('login'); return; }
  let rm = State.roadmap;
  if (!rm) return;
  if (!rm.id) {   // guest-generated (unsaved) — save it now under the account
    const body = rm.mode === 'ai'
      ? { mode: 'ai', target_role_title: rm.role, field: rm.sector, goal_text: rm.goal_text, level: rm.level }
      : { target_role_id: rm.role_id, goal_text: rm.goal_text, sector: rm.sector, level: rm.level };
    try { State.roadmap = rm = await Api.createRoadmap(body); }
    catch (e) { return toast(e.message || 'Could not save roadmap.', 'err'); }
  }
  try {
    const r = await Api.adoptRoadmap(rm.id);
    toast(r.detail || 'Added to My Learning ✓');
    State.roadmap = null; State.wiz = null;
    location.hash = '#/learning';
  } catch (e) { toast(e.message || 'Could not start roadmap.', 'err'); }
}

/* ---------------- Discover — guided wizard + sector-aware persona ---------------- */
const DISC_STEPS = ['Interests', 'Field', 'Level'];

function renderDiscover() {
  const root = $('#discoverRoot');
  if (State.persona) { renderPersonaResult(root, State.persona); return; }
  if (!State.disc) State.disc = { step: 0, interests: [], field: '', fieldMode: 'preset', level: '', questions: null };
  if (!State.disc.questions) {
    root.innerHTML = '<div class="card" style="padding:44px;text-align:center"><div class="wiz-spinner"></div></div>';
    Api.intakeQuestions().then((d) => { State.disc.questions = d.questions; renderDiscShell(); })
      .catch(() => { root.innerHTML = '<p class="muted">Could not load the questionnaire. Please refresh.</p>'; });
    return;
  }
  renderDiscShell();
}

function _qById(id) { return (State.disc.questions || []).find((q) => q.id === id) || { options: [] }; }

function renderDiscShell() {
  const d = State.disc;
  const dots = DISC_STEPS.map((s, i) => `<div class="wiz-dot${i === d.step ? ' active' : ''}${i < d.step ? ' done' : ''}"><span>${i < d.step ? '✓' : i + 1}</span><label>${s}</label></div>`).join('');
  $('#discoverRoot').innerHTML = `<div class="wiz-head"><span class="eyebrow">No résumé? Start here</span>
      <div class="wiz-progress" id="discProg">${dots}</div></div>
    <div id="discBody"></div>`;
  renderDiscStep();
}

function renderDiscStep() {
  const d = State.disc, body = $('#discBody');
  const prog = $('#discProg');
  if (prog) prog.innerHTML = DISC_STEPS.map((s, i) => `<div class="wiz-dot${i === d.step ? ' active' : ''}${i < d.step ? ' done' : ''}"><span>${i < d.step ? '✓' : i + 1}</span><label>${s}</label></div>`).join('');
  const back = d.step > 0 ? '<button class="btn btn-ghost btn-sm wiz-back" id="discBack">← Back</button>' : '';
  let html = '';
  if (d.step === 0) {
    const q = _qById('interests');
    html = `<div class="wiz-step card">${back}
      <h2 class="wiz-q">What kind of work excites you?</h2>
      <p class="muted wiz-sub">Pick a few — there are no wrong answers.</p>
      <div class="wiz-chipgrid">${q.options.map((o, i) => `<button class="wiz-chip lg${d.interests.includes(o.v) ? ' sel' : ''}" data-int="${esc(o.v)}" style="animation-delay:${i * 26}ms">${esc(o.label)}</button>`).join('')}</div>
      <div class="wiz-actions"><button class="btn btn-primary" id="discNext0"${d.interests.length ? '' : ' disabled'}>Continue →</button></div>`;
  } else if (d.step === 1) {
    const q = _qById('field');
    const isOther = d.fieldMode === 'other';
    const ready = isOther ? (d.field || '').trim() : d.field;
    html = `<div class="wiz-step card">${back}
      <h2 class="wiz-q">Which field are you drawn to?</h2>
      <p class="muted wiz-sub">Choose one — or pick <b>Other</b> to type your own.</p>
      <div class="wiz-chipgrid">${q.options.map((o, i) => `<button class="wiz-chip lg${(isOther && o.v === 'Other') || (!isOther && d.field === o.v) ? ' sel' : ''}" data-field="${esc(o.v)}" style="animation-delay:${i * 22}ms">${esc(o.label)}</button>`).join('')}</div>
      <input id="discOther" class="goal-input wiz-input" placeholder="Type your field — e.g. Aviation, Culinary Arts, Agriculture…" autocomplete="off" value="${esc(isOther ? (d.field || '') : '')}" style="${isOther ? '' : 'display:none'};margin-top:2px">
      <div class="wiz-actions"><button class="btn btn-primary" id="discNext1"${ready ? '' : ' disabled'}>Continue →</button></div>`;
  } else {
    const q = _qById('level');
    html = `<div class="wiz-step card">${back}
      <h2 class="wiz-q">Where are you right now?</h2>
      <p class="muted wiz-sub">So we set the right starting point.</p>
      <div class="wiz-levels">${q.options.map((o, i) => `<button class="wiz-level" data-level="${esc(o.v)}" style="animation-delay:${i * 45}ms"><span class="wl-label">${esc(o.label)}</span></button>`).join('')}</div>`;
  }
  body.innerHTML = html + '</div>';
  wireDiscStep();
  setTimeout(() => body.querySelector('.wiz-chip, .wiz-level')?.focus?.(), 60);
}

function wireDiscStep() {
  const d = State.disc;
  if ($('#discBack')) $('#discBack').onclick = () => { d.step = Math.max(0, d.step - 1); renderDiscStep(); };
  if (d.step === 0) {
    $('#discBody').querySelectorAll('[data-int]').forEach((b) => b.onclick = () => {
      const v = b.dataset.int, i = d.interests.indexOf(v);
      if (i >= 0) d.interests.splice(i, 1); else d.interests.push(v);
      b.classList.toggle('sel'); $('#discNext0').disabled = !d.interests.length;
    });
    $('#discNext0').onclick = () => { d.step = 1; renderDiscStep(); };
  } else if (d.step === 1) {
    const other = $('#discOther'), next = $('#discNext1');
    $('#discBody').querySelectorAll('[data-field]').forEach((b) => b.onclick = () => {
      $('#discBody').querySelectorAll('[data-field]').forEach((x) => x.classList.toggle('sel', x === b));
      if (b.dataset.field === 'Other') { d.fieldMode = 'other'; d.field = other.value.trim(); other.style.display = ''; other.focus(); next.disabled = !d.field; }
      else { d.fieldMode = 'preset'; d.field = b.dataset.field; other.style.display = 'none'; next.disabled = false; }
    });
    other.oninput = () => { if (d.fieldMode === 'other') { d.field = other.value.trim(); next.disabled = !d.field; } };
    other.onkeydown = (e) => { if (e.key === 'Enter' && (d.field || '').trim()) { e.preventDefault(); d.step = 2; renderDiscStep(); } };
    next.onclick = () => { d.step = 2; renderDiscStep(); };
  } else {
    $('#discBody').querySelectorAll('[data-level]').forEach((b) => b.onclick = () => { d.level = b.dataset.level; submitDiscover(); });
  }
}

async function submitDiscover() {
  const d = State.disc;
  $('#discBody').innerHTML = `<div class="card wiz-step" style="text-align:center;padding:48px"><div class="wiz-spinner"></div><p class="muted" style="margin-top:14px">Mapping your interests to real ${esc(d.field)} careers…</p></div>`;
  try {
    State.persona = await Api.intakeAnalyze({ interests: d.interests, field: d.field, level: d.level });
    renderPersonaResult($('#discoverRoot'), State.persona);
  } catch (e) {
    $('#discBody').innerHTML = `<div class="card"><p class="err-msg" style="display:block">${esc(e.message || 'Something went wrong.')}</p><button class="btn btn-ghost" id="discRetry">← Try again</button></div>`;
    $('#discRetry').onclick = () => { State.persona = null; renderDiscover(); };
  }
}

function personaCardHTML(card, opts = {}) {
  const dir = (x) => {
    const meta = x.grounded
      ? `<div class="pc-dir-meta"><span class="rc-growth">▲ ${pct(x.growth)}/yr</span><span class="muted">${inr(x.salary)}/yr</span></div>`
      : '<div class="pc-dir-meta"><span class="ai-badge">AI-guided</span></div>';
    const btn = opts.interactive
      ? `<button class="btn btn-ghost btn-sm pc-build" data-grounded="${x.grounded ? 1 : 0}" data-role="${esc(x.role_id || '')}" data-title="${esc(x.title)}" data-field="${esc(x.field || card.field || '')}">Build roadmap →</button>` : '';
    return `<div class="pc-dir"><div class="pc-dir-role">${esc(x.title)}</div>${x.why ? `<div class="pc-dir-why">${esc(x.why)}</div>` : ''}${meta}${btn}</div>`;
  };
  return `<div class="card persona-card">
    <span class="eyebrow">✦ Your PathFinder persona${card.field ? ' · ' + esc(card.field) : ''}</span>
    <h2 class="pc-headline">${esc(card.headline)}</h2>
    ${card.strengths && card.strengths.length ? `<div class="pc-strengths">${card.strengths.map((s) => `<span class="pill-have">${esc(s)}</span>`).join(' ')}</div>` : ''}
    ${card.directions && card.directions.length ? `<div class="pc-dirs-label">Directions that fit you</div><div class="pc-dirs">${card.directions.map(dir).join('')}</div>` : ''}
    ${opts.footer || ''}
  </div>`;
}

function renderPersonaResult(root, card) {
  root.innerHTML = `<button class="btn btn-ghost btn-sm" id="discRestart" style="margin-bottom:14px">← Start over</button>
    ${personaCardHTML(card, { interactive: true, footer: `<div class="wiz-actions" style="flex-wrap:wrap;margin-top:18px"><button class="btn btn-ghost" id="pcShare">Share my persona</button></div>` })}`;
  $('#discRestart').onclick = () => { State.persona = null; State.disc = null; renderDiscover(); };
  root.querySelectorAll('.pc-build').forEach((b) => b.onclick = () => buildFromDirection(b.dataset));
  $('#pcShare').onclick = () => sharePersona(card);
}

function buildFromDirection(dset) {
  State.roadmap = null; State.wiz = null;
  State.pendingDirection = (+dset.grounded && dset.role)
    ? { target_role_id: dset.role }
    : { mode: 'ai', target_role_title: dset.title, field: dset.field };
  location.hash = '#/goal';
}

async function sharePersona(card) {
  if (!Store.user) { State.pendingAfterAuth = () => (location.hash = '#/discover'); toast('Log in to save & share your persona.'); openAuth('login'); return; }
  try {
    const r = await Api.shareCard(card);
    const url = (r.url && r.url.startsWith('http')) ? r.url : (location.origin + '/' + (r.url || '').replace(/^\//, ''));
    try { await navigator.clipboard.writeText(url); toast('Share link copied ✓'); }
    catch { toast('Share link: ' + url); }
  } catch (e) { toast(e.message || 'Could not create a share link.', 'err'); }
}

async function renderCard(token) {
  const root = $('#cardRoot');
  root.innerHTML = `<div class="card" style="padding:44px;text-align:center"><div class="wiz-spinner"></div></div>`;
  try {
    const card = await Api.sharedCard(token);
    root.innerHTML = personaCardHTML(card, { footer: `<div class="wiz-actions" style="margin-top:18px"><button class="btn btn-primary" data-nav="#/discover">Discover your own path →</button></div>` });
  } catch (e) {
    root.innerHTML = `<div class="card empty-state"><div class="big">🔗</div><p>${esc(e.message || 'This card link is invalid or has expired.')}</p><button class="btn btn-primary" data-nav="#/discover">Discover your path →</button></div>`;
  }
}

/* ---------------- Legal — privacy & terms ---------------- */
function renderLegal(kind) {
  const root = $('#legalRoot');
  const privacy = `
    <span class="eyebrow">Last updated July 2026</span>
    <h2 style="margin:.15em 0 .3em">Privacy Policy</h2>
    <p class="muted">PathFinder is career decision-support. We collect the minimum needed to give you a saved, personalised experience — nothing more.</p>
    <h3>What we store</h3>
    <ul class="legal-list">
      <li>Your <b>email</b> and a <b>salted hash</b> of your password (never the password itself).</li>
      <li>The <b>analyses, roadmaps, tracked courses and preferences</b> you create.</li>
    </ul>
    <h3>What we don't</h3>
    <ul class="legal-list">
      <li>Your <b>raw résumé text is discarded</b> after we extract skills from it — only the extracted skill list is kept.</li>
      <li>We <b>never sell or share</b> your data for advertising, and use <b>no third-party tracking cookies</b>. Your login is a token stored in your own browser.</li>
    </ul>
    <h3>Third parties that process what you submit</h3>
    <ul class="legal-list">
      <li><b>Google Sign-In</b> — only if you choose "Continue with Google", to authenticate you.</li>
      <li><b>Google Gemini</b> — text you submit (résumé/goal) is sent to extract skills and generate AI-guided plans, under Google's terms.</li>
      <li><b>Job APIs (Adzuna / JSearch)</b> — receive only your search keywords and location to return matching jobs.</li>
    </ul>
    <h3>Your control</h3>
    <p>Delete any analysis, or your entire account and all associated data, at any time from your account menu. Data is processed on Google Cloud (India, asia-south1).</p>
    <p class="muted" style="font-size:.85rem;margin-top:16px">Questions about your data? Reach out via the project's GitHub repository.</p>`;
  const terms = `
    <span class="eyebrow">Last updated July 2026</span>
    <h2 style="margin:.15em 0 .3em">Terms of Use</h2>
    <p class="muted">Please read these terms before relying on PathFinder's guidance.</p>
    <h3>What PathFinder is — and isn't</h3>
    <ul class="legal-list">
      <li>It provides <b>career decision-support</b> and learning guidance. It is <b>not</b> professional career counselling, financial, or investment advice.</li>
      <li>Outcomes such as jobs or salaries are <b>estimates, not guarantees</b>.</li>
      <li><b>Grounded</b> data/analytics roadmaps use curated public datasets; <b>AI-guided</b> plans for other fields are AI-generated and should be <b>verified</b> before you act on them.</li>
    </ul>
    <h3>Using the service</h3>
    <ul class="legal-list">
      <li>For personal, non-abusive use. Don't attempt to disrupt, overload, or scrape the service.</li>
      <li>You're responsible for keeping your account credentials safe.</li>
    </ul>
    <h3>No warranty</h3>
    <p>The service is provided "as is", without warranty. Features and these terms may change. Governing region: India.</p>`;
  root.innerHTML = `<button class="btn btn-ghost btn-sm" data-nav="#/" style="margin-bottom:14px">← Back home</button>
    <div class="card legal-doc">${kind === 'terms' ? terms : privacy}</div>`;
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
}

/* ---------------- router ---------------- */
const VIEWS = ['landing', 'analyze', 'discover', 'card', 'goal', 'history', 'learning', 'legal', 'profile', 'apply'];
function showView(name) {
  VIEWS.forEach((v) => $(`#view-${v}`).classList.toggle('hidden', v !== name));
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
}
function route() {
  const hash = location.hash || '#/';
  if (hash === '#/' || hash === '') { showView('landing'); return; }
  if (hash.startsWith('#/reset')) {
    const qs = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
    const token = new URLSearchParams(qs).get('token');
    showView('landing');
    if (token) openReset(token); else toast('That reset link is invalid or incomplete.', 'err');
    return;
  }
  if (hash.startsWith('#/analyze')) { showView('analyze'); if (!State.result) renderAnalyzeIntro(); return; }
  if (hash.startsWith('#/discover')) { showView('discover'); renderDiscover(); return; }
  if (hash.startsWith('#/card/')) { showView('card'); renderCard(hash.slice('#/card/'.length)); return; }
  if (hash.startsWith('#/privacy')) { showView('legal'); renderLegal('privacy'); return; }
  if (hash.startsWith('#/terms')) { showView('legal'); renderLegal('terms'); return; }
  if (hash.startsWith('#/goal')) { showView('goal'); renderGoal(); return; }
  if (hash.startsWith('#/history')) {
    if (!Store.user) { toast('Log in to see your saved analyses.'); State.pendingAfterAuth = () => location.hash = '#/history'; openAuth('login'); location.hash = '#/'; return; }
    showView('history'); renderHistory(); return;
  }
  if (hash.startsWith('#/learning')) {
    if (!Store.user) { toast('Log in to see your learning.'); State.pendingAfterAuth = () => (location.hash = '#/learning'); openAuth('login'); location.hash = '#/'; return; }
    showView('learning'); renderLearning(); return;
  }
  if (hash.startsWith('#/profile')) {
    if (!Store.user) { toast('Log in to manage your profile.'); State.pendingAfterAuth = () => (location.hash = '#/profile'); openAuth('login'); location.hash = '#/'; return; }
    showView('profile'); renderProfile(); return;
  }
  if (hash.startsWith('#/apply')) {
    if (!Store.user) { toast('Log in to use Apply Studio.'); State.pendingAfterAuth = () => (location.hash = '#/apply'); openAuth('login'); location.hash = '#/'; return; }
    showView('apply'); renderApply(); return;
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
        <button class="btn btn-amber" id="sampleBtn">See a live example</button>
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
        <button class="btn btn-ghost btn-sm" id="pasteSample">Load example text</button>
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
        <span class="muted" style="font-size:.82rem">Live openings from Adzuna &amp; partner job sources.</span>
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
    <p class="datasource" style="margin-top:14px">Resume analysis via <b>${esc(r.provider_status.skill_extraction === 'gemini' ? 'Gemini' : "PathFinder's engine")}</b> · forecasts &amp; course grounding are reproducible and grounded in real data. Powered by Google Cloud.</p>`;

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
      <p class="muted" style="font-size:.82rem;margin:.4em 0 .2em">Hit <b>＋ Track</b> on any course, then mark it <b>✓ complete</b> under <a href="#/learning">🎓 My learning</a> — your <b>${pw.overlap_percentage}% skill coverage</b> above climbs as you finish them.</p>
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
    if (!res.matches.length) { panel.innerHTML = '<p class="muted">No matching openings found — try a different location.</p>'; return; }
    panel.innerHTML = `<p class="muted" style="font-size:.82rem;margin-bottom:12px">${res.count} live openings from <b>${esc(sourceName(res.source))}</b>, ranked by your match</p>
      <div class="jobs-grid">${res.matches.map(jobCard).join('')}</div>`;
  } catch (e) { panel.innerHTML = `<p class="muted">Could not load jobs: ${esc(e.message)}</p>`; }
}
function sourceName(s) {
  return { adzuna: 'Adzuna', jsearch: 'Google Jobs', 'adzuna+jsearch': 'Adzuna + Google Jobs', 'jsearch+adzuna': 'Adzuna + Google Jobs', sample: 'the curated set' }[s] || s;
}
function jobCard(m) {
  const j = m.job;
  const have = m.matched_skills.slice(0, 6).map((s) => `<span class="pill-have">${esc(s)}</span>`).join('') || '<span class="muted" style="font-size:.8rem">—</span>';
  const gap = m.gap_skills.slice(0, 5).map((s) => `<span class="pill-gap">${esc(s)}</span>`).join('');
  const courses = (m.courses || []).slice(0, 3).map((c) => `<div class="mini-course"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>
      <button class="btn btn-ghost btn-sm" data-track data-cid="${esc(c.id)}" data-ct="${esc(c.title)}" data-cp="${esc(c.provider)}" data-cu="${esc(c.url)}" data-cs="${esc((c.skills || []).join(','))}">＋ Track</button></div>`).join('');
  return `<div class="card job-card">
    <div class="path-top">
      <div><div class="job-src">${esc(sourceName(j.source))}</div><h3 style="margin:.15em 0">${esc(j.title)}</h3><div class="job-meta">${esc(j.company)}${j.location ? ' · ' + esc(j.location) : ''}</div></div>
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
    <div id="journeyBox"></div>
    <div id="progressBox"></div>
    <div class="subhead" style="margin-top:26px"><h2 style="font-size:1.3rem">Tracked courses</h2></div>
    <div id="learnList"><p class="muted">Loading…</p></div>`;
  await refreshLearning();
  renderJourney();
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

async function renderJourney() {
  const box = $('#journeyBox'); if (!box) return;
  let j;
  try { j = await Api.journey(); } catch { return; }
  const acq = (j.acquired || []).slice().reverse();  // newest first
  const dots = (p) => p === 'advanced' ? '●●●' : p === 'intermediate' ? '●●○' : '●○○';
  const timeline = acq.length
    ? acq.map((a) => `<div class="tl-item"><span class="tl-dot"></span><div class="tl-body"><span class="tl-skill">${esc(a.skill)}</span><span class="tl-meta"><span class="tl-prof">${dots(a.proficiency)}</span> ${esc(a.proficiency)}${a.at ? ' · ' + new Date(a.at).toLocaleDateString() : ''}</span></div></div>`).join('')
    : '<p class="muted" style="font-size:.85rem;margin:4px 0 0">Complete a tracked course to start building your skill timeline.</p>';
  box.innerHTML = `<div class="card journey-card">
    <div class="jc-head">
      <div class="jc-streak"><div class="jc-streak-n">${j.streak_weeks}🔥</div><div class="jc-streak-l">week${j.streak_weeks === 1 ? '' : 's'} streak</div></div>
      <div class="jc-stats">
        <div class="jc-stat"><div class="k">Skills acquired</div><div class="v">${(j.acquired || []).length}</div></div>
        <div class="jc-stat"><div class="k">Courses done</div><div class="v">${j.completed_total}</div></div>
        <div class="jc-stat"><div class="k">This week</div><div class="v">${j.completed_this_week ? '✓' : '—'}</div></div>
      </div>
      <label class="jc-digest"><input type="checkbox" id="digestToggle"> <span>Weekly email nudge</span></label>
    </div>
    <div class="jc-tl-label">Your skill timeline</div>
    <div class="tl">${timeline}</div>
  </div>`;
  try {
    const prefs = await Api.getPrefs();
    const t = $('#digestToggle');
    if (t) {
      t.checked = !!prefs.digest_opt_in;
      t.onchange = async () => {
        try { await Api.putPrefs({ digest_opt_in: t.checked }); toast(t.checked ? 'Weekly nudge on ✓' : 'Weekly nudge off'); }
        catch (e) { t.checked = !t.checked; toast(e.message || 'Could not update.', 'err'); }
      };
    }
  } catch { /* prefs optional */ }
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
  list.querySelectorAll('[data-ldone]').forEach((b) => b.onclick = async () => {
    const next = b.dataset.cur === 'completed' ? 'saved' : 'completed';
    try {
      await Api.patchLearning(b.dataset.ldone, next);
      toast(next === 'completed' ? 'Marked complete — your coverage just updated below.' : 'Marked as not done.');
      renderLearning();
    } catch (e) { toast(e.message, 'err'); }
  });
  list.querySelectorAll('[data-ldel]').forEach((b) => b.onclick = async () => {
    try { await Api.deleteLearning(b.dataset.ldel); toast('Removed.'); renderLearning(); }
    catch (e) { toast(e.message, 'err'); }
  });
}
function learnRow(it) {
  const opt = (v, l) => `<option value="${v}"${it.status === v ? ' selected' : ''}>${l}</option>`;
  const done = it.status === 'completed';
  return `<div class="card learn-item${done ? ' is-done' : ''}">
    <div style="font-size:1.3rem">${done ? '✅' : '📘'}</div>
    <div class="li-body"><div class="hi-title" style="font-size:1.02rem">${esc(it.title)}</div><div class="hi-date mono">${esc(it.provider || '')}</div></div>
    <button class="btn btn-sm ${done ? 'btn-ghost' : 'btn-primary'}" data-ldone="${esc(it.id)}" data-cur="${esc(it.status)}">${done ? '↩ Mark not done' : '✓ Mark complete'}</button>
    <select data-ls="${esc(it.id)}" class="li-status" title="Set learning status">${opt('saved', 'Saved')}${opt('in_progress', 'In progress')}${opt('completed', 'Completed')}</select>
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

/* ---------------- Apply Assistant: Profile (Phase A) ---------------- */
const ICONS = {
  all: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>`,
  personal: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  summary: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
  experience: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>`,
  education: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>`,
  skills: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  projects: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
  certifications: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>`,
  phone: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>`,
  location: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`,
  globe: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
  upload: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`,
  edit: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  plus: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  trash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
  check: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><polyline points="20 6 9 17 4 12"/></svg>`,
  x: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px; margin-right:4px;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`
};

async function renderProfile(draftSections = null, editingSecType = null, activeTab = 'all', showReupload = false) {
  const root = $('#profileRoot');
  if (!draftSections && editingSecType === null) {
    root.innerHTML = `<div class="card" style="padding:40px; text-align:center">
      <h2>Loading profile...</h2>
    </div>`;
  }
  
  try {
    let sections = draftSections;
    let isDraft = !!draftSections && editingSecType === null;
    
    if (!draftSections && editingSecType === null) {
      const profile = await Api.getProfile();
      sections = profile.sections_json || [];
    }

    const renderUploadBox = () => `
      <div class="card" style="max-width:800px; margin:0 auto 24px auto; background:rgba(255,255,255,0.9); border:1px solid rgba(13,148,136,0.3); border-radius:16px; padding:24px; box-shadow:0 8px 30px rgba(0,0,0,0.06);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
          <h3 style="margin:0; font-family:'Inter', sans-serif; color:#0f172a; font-size:1.2rem;">Upload / Re-upload Resume</h3>
          ${sections.length ? `<button class="btn btn-ghost btn-sm" id="closeReuploadBtn">${ICONS.x} Close</button>` : ''}
        </div>
        <div class="dropzone" id="profDropzone" style="margin-bottom: 20px; position:relative; padding:24px; border:2px dashed rgba(13,148,136,0.3); border-radius:12px; text-align:center;">
          <div class="big" style="margin-bottom: 8px; color: #0d9488;">${ICONS.upload}</div>
          <h4 style="margin:0 0 4px 0; font-family:'Inter', sans-serif;">Drag & drop your resume here</h4>
          <p class="muted" style="font-size: 0.85rem; margin-bottom:12px;">PDF or TXT up to 5MB</p>
          <button class="btn btn-primary btn-sm" id="profBrowseBtn" style="position:relative; z-index:10;">Browse Files</button>
          <input type="file" id="profFile" accept=".pdf,.txt" style="position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:pointer;">
        </div>
        <div style="text-align: left;">
          <label class="muted" style="font-size: 0.8rem; display:block; margin-bottom:6px; font-weight:600; text-transform:uppercase;">Or paste resume text</label>
          <textarea class="paste" id="profText" placeholder="Paste your resume text here..." rows="3" style="width:100%; padding:10px; border:1px solid rgba(109,122,119,0.3); border-radius:8px; box-sizing:border-box;"></textarea>
          <button class="btn btn-ghost btn-sm" id="profExtractTextBtn" style="margin-top: 10px; width:100%; border:1px solid rgba(13,148,136,0.3); color:#0d9488;">Extract from text</button>
        </div>
      </div>`;

    const renderSectionsUI = () => {
      if (!sections.length || showReupload) {
        return renderUploadBox();
      }
      
      const tabs = [
        { id: 'all', label: `${ICONS.all} All` },
        { id: 'personal', label: `${ICONS.personal} Personal` },
        { id: 'summary', label: `${ICONS.summary} Summary` },
        { id: 'experience', label: `${ICONS.experience} Experience` },
        { id: 'education', label: `${ICONS.education} Education` },
        { id: 'skills', label: `${ICONS.skills} Skills` },
        { id: 'projects', label: `${ICONS.projects} Projects` },
        { id: 'certifications', label: `${ICONS.certifications} Certifications` }
      ];

      let html = `<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
          <h2 style="margin:0; font-family:'Inter', sans-serif; font-size:28px; font-weight:700; color:#0f172a;">Master Profile ${isDraft ? '<span class="pill-have" style="background:#e11d48;color:white;margin-left:8px;font-size:0.75rem; vertical-align:middle; padding:4px 10px; border-radius:999px;">Unsaved Draft</span>' : ''}</h2>
          <div>
            <button class="btn btn-ghost btn-sm" id="profReuploadBtn" style="border:1px solid rgba(13,148,136,0.3); color:#0d9488;">${ICONS.upload} Re-upload Resume</button>
          </div>
        </div>
        <p class="muted" style="margin-bottom:20px; font-size:0.95rem;">This data grounds all AI-generated application materials to prevent hallucinations.</p>

        <!-- Section Navigation Tabs -->
        <div class="prof-tabs-bar" style="display:flex; gap:8px; overflow-x:auto; padding-bottom:12px; margin-bottom:28px; border-bottom:1px solid rgba(13, 148, 136, 0.2);">
          ${tabs.map(t => `<button class="btn btn-sm prof-tab-btn" data-tab="${t.id}" style="${activeTab === t.id ? 'background:#0d9488; color:white; font-weight:600; border:none; box-shadow:0 2px 8px rgba(13,148,136,0.3);' : 'background:rgba(255,255,255,0.7); color:#475569; border:1px solid rgba(109,122,119,0.3);'} padding:8px 16px; border-radius:8px; cursor:pointer; transition:all 0.2s;">${t.label}</button>`).join('')}
        </div>

        <div style="display:flex; flex-direction:column; gap:24px;">`;

      const visibleSections = sections.filter(sec => {
        if (activeTab === 'all') return true;
        if (activeTab === 'personal') return sec.type === 'personal';
        if (activeTab === 'summary') return sec.type === 'summary';
        if (activeTab === 'experience') return sec.type === 'experience';
        if (activeTab === 'education') return sec.type === 'education';
        if (activeTab === 'skills') return sec.type === 'skills';
        if (activeTab === 'projects') return sec.type === 'projects';
        if (activeTab === 'certifications') return sec.type === 'certifications';
        return true;
      });

      if (!visibleSections.length) {
        html += `<div class="card" style="text-align:center; padding:32px; color:#64748b; background:rgba(255,255,255,0.8); border-radius:16px;">No items in this section tab yet. Click "Edit Section" to add content.</div>`;
      }
        
      visibleSections.forEach(sec => {
        const isEditingThisSec = editingSecType === sec.type;
        html += `<div class="card" style="border:1px solid rgba(13, 148, 136, 0.2); background:rgba(255,255,255,0.85); backdrop-filter:blur(20px); box-shadow:0 4px 20px rgba(0,0,0,0.04); border-radius:16px; padding:28px;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(13, 148, 136, 0.15); padding-bottom:12px; margin-bottom:20px;">
            <h3 style="margin:0; color:#0d9488; font-family:'Inter', sans-serif; font-size:1.3rem; font-weight:700; display:flex; align-items:center; gap:8px;">${ICONS[sec.type] || ICONS.projects} ${esc(sec.title)}</h3>
            <div style="display:flex; gap:8px;">
              ${isEditingThisSec 
                ? `<button class="btn btn-ghost btn-sm sec-cancel-btn" data-type="${sec.type}">${ICONS.x} Cancel</button>
                   <button class="btn btn-primary btn-sm sec-save-btn" data-type="${sec.type}">${ICONS.check} Save Section</button>`
                : `<button class="btn btn-ghost btn-sm sec-edit-btn" data-type="${sec.type}" style="border:1px solid rgba(13,148,136,0.3); color:#0d9488;">${ICONS.edit} Edit Section</button>`
              }
            </div>
          </div>`;
        
        if (sec.type === 'personal' && sec.fields) {
          const mob = sec.fields.mobile || sec.fields.phone || '';
          const cityVal = sec.fields.city || (sec.fields.location ? sec.fields.location.split(',')[0].trim() : '');
          const countryVal = sec.fields.country || (sec.fields.location && sec.fields.location.includes(',') ? sec.fields.location.split(',')[1].trim() : '');
          const gh = sec.fields.github || '';
          const li = sec.fields.linkedin || '';
          const port = sec.fields.portfolio || '';
          const locStr = [cityVal, countryVal].filter(Boolean).join(', ') || sec.fields.location || '—';

          if (isEditingThisSec) {
             html += `<div style="display:flex; flex-direction:column; gap:20px;">
               <!-- Card 1: Contact Information -->
               <div style="background:rgba(248, 250, 252, 0.9); border:1px solid rgba(13, 148, 136, 0.15); border-radius:12px; padding:20px;">
                 <h4 style="margin:0 0 14px 0; color:#0d9488; font-family:'Inter', sans-serif; font-size:0.95rem; font-weight:600; display:flex; align-items:center;">${ICONS.phone} Contact Information</h4>
                 <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Full Name</div> <input type="text" id="edit-personal-name" value="${esc(sec.fields.name || '')}" placeholder="John Doe" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Mobile / Phone</div> <input type="text" id="edit-personal-mobile" value="${esc(mob)}" placeholder="+1 234 567 8900" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Email Address</div> <input type="text" id="edit-personal-email" value="${esc(sec.fields.email || '')}" placeholder="user@example.com" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                 </div>
               </div>

               <!-- Card 2: Location Details -->
               <div style="background:rgba(248, 250, 252, 0.9); border:1px solid rgba(13, 148, 136, 0.15); border-radius:12px; padding:20px;">
                 <h4 style="margin:0 0 14px 0; color:#0d9488; font-family:'Inter', sans-serif; font-size:0.95rem; font-weight:600; display:flex; align-items:center;">${ICONS.location} Location & Region</h4>
                 <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">City</div> <input type="text" id="edit-personal-city" value="${esc(cityVal)}" placeholder="San Francisco" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Country</div> <input type="text" id="edit-personal-country" value="${esc(countryVal)}" placeholder="USA" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                 </div>
               </div>

               <!-- Card 3: Web & Profiles -->
               <div style="background:rgba(248, 250, 252, 0.9); border:1px solid rgba(13, 148, 136, 0.15); border-radius:12px; padding:20px;">
                 <h4 style="margin:0 0 14px 0; color:#0d9488; font-family:'Inter', sans-serif; font-size:0.95rem; font-weight:600; display:flex; align-items:center;">${ICONS.globe} Web & Social Links</h4>
                 <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">GitHub Profile</div> <input type="text" id="edit-personal-github" value="${esc(gh)}" placeholder="https://github.com/username" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">LinkedIn Profile</div> <input type="text" id="edit-personal-linkedin" value="${esc(li)}" placeholder="https://linkedin.com/in/username" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Portfolio Website</div> <input type="text" id="edit-personal-portfolio" value="${esc(port)}" placeholder="https://myportfolio.com" style="width:100%; padding:9px; border:1px solid var(--line); border-radius:6px; font:inherit; background:var(--paper); box-sizing:border-box;"></div>
                 </div>
               </div>
             </div>`;
          } else {
             html += `<div style="display:flex; flex-direction:column; gap:20px;">
               <!-- Card 1: Contact Information -->
               <div style="background:rgba(248, 250, 252, 0.9); border:1px solid rgba(13, 148, 136, 0.15); border-radius:12px; padding:20px;">
                 <h4 style="margin:0 0 14px 0; color:#0d9488; font-family:'Inter', sans-serif; font-size:0.95rem; font-weight:600; display:flex; align-items:center;">${ICONS.phone} Contact Information</h4>
                 <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Full Name</div> <div style="font-size:1.1rem; font-weight:600; color:#0f172a;">${esc(sec.fields.name || '—')}</div></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Mobile / Phone</div> <div style="font-size:1.05rem; color:#0f172a;">${esc(mob || '—')}</div></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Email Address</div> <div style="font-size:1.05rem; color:#0f172a;">${esc(sec.fields.email || '—')}</div></div>
                 </div>
               </div>

               <!-- Card 2: Location Details -->
               <div style="background:rgba(248, 250, 252, 0.9); border:1px solid rgba(13, 148, 136, 0.15); border-radius:12px; padding:20px;">
                 <h4 style="margin:0 0 14px 0; color:#0d9488; font-family:'Inter', sans-serif; font-size:0.95rem; font-weight:600; display:flex; align-items:center;">${ICONS.location} Location & Region</h4>
                 <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">City</div> <div style="font-size:1.05rem; color:#0f172a;">${esc(cityVal || '—')}</div></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Country</div> <div style="font-size:1.05rem; color:#0f172a;">${esc(countryVal || '—')}</div></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Full Location</div> <div style="font-size:1.05rem; color:#0f172a;">${esc(locStr)}</div></div>
                 </div>
               </div>

               <!-- Card 3: Web & Profiles -->
               <div style="background:rgba(248, 250, 252, 0.9); border:1px solid rgba(13, 148, 136, 0.15); border-radius:12px; padding:20px;">
                 <h4 style="margin:0 0 14px 0; color:#0d9488; font-family:'Inter', sans-serif; font-size:0.95rem; font-weight:600; display:flex; align-items:center;">${ICONS.globe} Web & Social Links</h4>
                 <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">GitHub</div> <div style="font-size:1rem;">${gh ? `<a href="${esc(gh)}" target="_blank" style="color:#0d9488; text-decoration:none; font-weight:500;">${esc(gh)} ↗</a>` : '—'}</div></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">LinkedIn</div> <div style="font-size:1rem;">${li ? `<a href="${esc(li)}" target="_blank" style="color:#0d9488; text-decoration:none; font-weight:500;">${esc(li)} ↗</a>` : '—'}</div></div>
                   <div><div class="muted" style="font-size:0.75rem; text-transform:uppercase; font-weight:600; margin-bottom:4px;">Portfolio Website</div> <div style="font-size:1rem;">${port ? `<a href="${esc(port)}" target="_blank" style="color:#0d9488; text-decoration:none; font-weight:500;">${esc(port)} ↗</a>` : '—'}</div></div>
                 </div>
               </div>
             </div>`;
          }
        } else if (sec.type === 'skills' && Array.isArray(sec.items)) {
          if (isEditingThisSec) {
            html += `<textarea id="edit-skills" rows="4" style="width:100%; padding:10px; border:1px solid var(--line); border-radius:8px; font:inherit; background:var(--paper); box-sizing:border-box;">${esc(sec.items.join(', '))}</textarea>
            <div class="muted" style="font-size:0.8rem; margin-top:6px;">Comma separated skill tags</div>`;
          } else {
            html += `<div style="display:flex; flex-wrap:wrap; gap:10px;">
              ${sec.items.map(s => `<span class="pill-have" style="background:rgba(13, 148, 136, 0.1); color:#0d9488; border:1px solid rgba(13,148,136,0.2); font-weight:500; padding:8px 16px; border-radius:999px; font-size:0.95rem;">${esc(s)}</span>`).join('')}
            </div>`;
          }
        } else if (sec.type === 'education') {
          const items = sec.items || [];
          if (isEditingThisSec) {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach((item, idx) => {
              html += `<div style="position:relative; padding:16px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #f59e0b; border:1px solid rgba(245,158,11,0.2);">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                  <span style="font-weight:600; font-size:0.85rem; color:#d97706;">Degree Entry #${idx + 1}</span>
                  <button class="btn btn-ghost btn-sm remove-item-btn" data-sectype="education" data-idx="${idx}" style="color:#e11d48; padding:2px 8px;">${ICONS.trash} Remove</button>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:8px;">
                  <div><div class="muted" style="font-size:0.75rem;">Degree Name</div><input type="text" id="edit-edu-deg-${idx}" value="${esc(item.degree || '')}" placeholder="B.S. Computer Science" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                  <div><div class="muted" style="font-size:0.75rem;">Institution / University</div><input type="text" id="edit-edu-inst-${idx}" value="${esc(item.institution || '')}" placeholder="Stanford University" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                  <div><div class="muted" style="font-size:0.75rem;">Graduation Year</div><input type="text" id="edit-edu-year-${idx}" value="${esc(item.year || '')}" placeholder="2022" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                  <div><div class="muted" style="font-size:0.75rem;">Score / GPA</div><input type="text" id="edit-edu-score-${idx}" value="${esc(item.score || '')}" placeholder="3.8 / 4.0 or 85%" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                </div>
              </div>`;
            });
            html += `<button class="btn btn-ghost btn-sm add-item-btn" data-sectype="education" style="border:1px dashed #d97706; color:#d97706; width:100%; padding:10px;">${ICONS.plus} Add Degree Entry</button></div>`;
          } else {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach(item => {
              html += `<div style="position:relative; padding:20px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #f59e0b; box-shadow:0 2px 10px rgba(0,0,0,0.02);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <div style="font-size:1.15rem; font-weight:700; color:#0f172a;">${esc(item.degree || 'Degree')}</div>
                    <div style="font-size:1rem; color:#d97706; font-weight:600; margin-top:2px;">${esc(item.institution || 'University')}</div>
                  </div>
                  <div style="text-align:right;">
                    ${item.year ? `<div class="mono" style="font-size:0.85rem; background:rgba(245, 158, 11, 0.1); color:#d97706; padding:4px 10px; border-radius:6px; font-weight:500;">Year: ${esc(item.year)}</div>` : ''}
                    ${item.score ? `<div style="font-size:0.85rem; color:#64748b; margin-top:4px;">Score: ${esc(item.score)}</div>` : ''}
                  </div>
                </div>
              </div>`;
            });
            html += `</div>`;
          }
        } else if (sec.type === 'projects') {
          const items = sec.items || [];
          if (isEditingThisSec) {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach((item, idx) => {
              html += `<div style="position:relative; padding:16px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #0284c7; border:1px solid rgba(2,132,199,0.2);">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                  <span style="font-weight:600; font-size:0.85rem; color:#0284c7;">Project Entry #${idx + 1}</span>
                  <button class="btn btn-ghost btn-sm remove-item-btn" data-sectype="projects" data-idx="${idx}" style="color:#e11d48; padding:2px 8px;">${ICONS.trash} Remove</button>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:8px;">
                  <div><div class="muted" style="font-size:0.75rem;">Project Title</div><input type="text" id="edit-proj-head-${idx}" value="${esc(item.heading || '')}" placeholder="AI Pathfinder" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                  <div><div class="muted" style="font-size:0.75rem;">Tech Stack / Role</div><input type="text" id="edit-proj-tech-${idx}" value="${esc(item.tech_stack || '')}" placeholder="Python, React, FastAPI" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                </div>
                <div style="margin-bottom:8px;"><div class="muted" style="font-size:0.75rem;">Description / Details</div><textarea id="edit-proj-detail-${idx}" rows="3" placeholder="Project description and key outcomes..." style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;">${esc(item.detail || '')}</textarea></div>
                <div><div class="muted" style="font-size:0.75rem;">Project Link / Demo URL</div><input type="text" id="edit-proj-link-${idx}" value="${esc(item.link || '')}" placeholder="https://github.com/myproject" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
              </div>`;
            });
            html += `<button class="btn btn-ghost btn-sm add-item-btn" data-sectype="projects" style="border:1px dashed #0284c7; color:#0284c7; width:100%; padding:10px;">${ICONS.plus} Add Project Entry</button></div>`;
          } else {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach(item => {
              html += `<div style="position:relative; padding:20px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #0284c7; box-shadow:0 2px 10px rgba(0,0,0,0.02);">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                  <div>
                    <div style="font-size:1.15rem; font-weight:700; color:#0f172a;">${esc(item.heading || 'Project Name')}</div>
                    ${item.tech_stack ? `<div style="font-size:0.85rem; color:#0284c7; font-weight:600; margin-top:2px;">Tech Stack: ${esc(item.tech_stack)}</div>` : ''}
                  </div>
                  ${item.link ? `<a href="${esc(item.link)}" target="_blank" style="color:#0284c7; font-size:0.85rem; font-weight:600; text-decoration:none;">View Project ↗</a>` : ''}
                </div>
                ${item.detail ? `<div style="font-size:0.95rem; color:#334155; margin-top:10px; line-height:1.5;">${esc(item.detail)}</div>` : ''}
              </div>`;
            });
            html += `</div>`;
          }
        } else if (sec.type === 'certifications') {
          const items = sec.items || [];
          if (isEditingThisSec) {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach((item, idx) => {
              html += `<div style="position:relative; padding:16px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #8b5cf6; border:1px solid rgba(139,92,246,0.2);">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                  <span style="font-weight:600; font-size:0.85rem; color:#8b5cf6;">Certification #${idx + 1}</span>
                  <button class="btn btn-ghost btn-sm remove-item-btn" data-sectype="certifications" data-idx="${idx}" style="color:#e11d48; padding:2px 8px;">${ICONS.trash} Remove</button>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:8px;">
                  <div><div class="muted" style="font-size:0.75rem;">Certification Name</div><input type="text" id="edit-cert-head-${idx}" value="${esc(item.heading || '')}" placeholder="AWS Solutions Architect" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                  <div><div class="muted" style="font-size:0.75rem;">Issuing Organization</div><input type="text" id="edit-cert-issuer-${idx}" value="${esc(item.issuer || '')}" placeholder="Amazon Web Services" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                  <div><div class="muted" style="font-size:0.75rem;">Issue Year / Date</div><input type="text" id="edit-cert-year-${idx}" value="${esc(item.year || '')}" placeholder="2023" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                  <div><div class="muted" style="font-size:0.75rem;">Credential Link / ID</div><input type="text" id="edit-cert-link-${idx}" value="${esc(item.link || '')}" placeholder="https://aws.amazon.com/verify/123" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;"></div>
                </div>
              </div>`;
            });
            html += `<button class="btn btn-ghost btn-sm add-item-btn" data-sectype="certifications" style="border:1px dashed #8b5cf6; color:#8b5cf6; width:100%; padding:10px;">${ICONS.plus} Add Certification Entry</button></div>`;
          } else {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach(item => {
              html += `<div style="position:relative; padding:20px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #8b5cf6; box-shadow:0 2px 10px rgba(0,0,0,0.02);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <div style="font-size:1.15rem; font-weight:700; color:#0f172a;">${esc(item.heading || 'Certification Title')}</div>
                    ${item.issuer ? `<div style="font-size:0.95rem; color:#8b5cf6; font-weight:600; margin-top:2px;">Issued by: ${esc(item.issuer)}</div>` : ''}
                  </div>
                  <div style="text-align:right;">
                    ${item.year ? `<div class="mono" style="font-size:0.85rem; background:rgba(139, 92, 246, 0.1); color:#8b5cf6; padding:4px 10px; border-radius:6px; font-weight:500;">Year: ${esc(item.year)}</div>` : ''}
                    ${item.link ? `<a href="${esc(item.link)}" target="_blank" style="color:#8b5cf6; font-size:0.85rem; font-weight:600; text-decoration:none; display:block; margin-top:4px;">Credential ↗</a>` : ''}
                  </div>
                </div>
              </div>`;
            });
            html += `</div>`;
          }
        } else if (sec.type === 'experience') {
          const items = sec.items || [];
          if (isEditingThisSec) {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach((item, idx) => {
              html += `<div style="position:relative; padding:16px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #0d9488;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                  <span style="font-weight:600; font-size:0.85rem; color:#0d9488;">Experience Entry #${idx + 1}</span>
                  <button class="btn btn-ghost btn-sm remove-item-btn" data-sectype="experience" data-idx="${idx}" style="color:#e11d48; padding:2px 8px;">${ICONS.trash} Remove</button>
                </div>
                <input type="text" id="edit-exp-role-${idx}" value="${esc(item.role || '')}" placeholder="Role Title" style="width:100%; margin-bottom:8px; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;">
                <input type="text" id="edit-exp-org-${idx}" value="${esc(item.org || '')}" placeholder="Organization / Company" style="width:100%; margin-bottom:8px; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;">
                <div style="display:flex; gap:8px; margin-bottom:8px;">
                  <input type="text" id="edit-exp-start-${idx}" value="${esc(item.start || '')}" placeholder="Start Date" style="flex:1; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;">
                  <input type="text" id="edit-exp-end-${idx}" value="${esc(item.end || '')}" placeholder="End Date" style="flex:1; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;">
                </div>
                <textarea id="edit-exp-bullets-${idx}" rows="4" placeholder="Bullet points (one per line)" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; box-sizing:border-box;">${esc((item.bullets || []).join('\n'))}</textarea>
              </div>`;
            });
            html += `<button class="btn btn-ghost btn-sm add-item-btn" data-sectype="experience" style="border:1px dashed #0d9488; color:#0d9488; width:100%; padding:10px;">${ICONS.plus} Add Experience Entry</button></div>`;
          } else {
            html += `<div style="display:flex; flex-direction:column; gap:16px;">`;
            items.forEach(item => {
              html += `<div style="position:relative; padding:20px; background:rgba(248, 250, 252, 0.9); border-radius:12px; border-left:4px solid #0d9488; box-shadow:0 2px 10px rgba(0,0,0,0.02);">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                  <div>
                    <div style="font-size:1.15rem; font-weight:700; color:#0f172a;">${esc(item.role || '')}</div>
                    <div style="font-size:1rem; color:#0d9488; font-weight:600; margin-top:2px;">${esc(item.org || '')}</div>
                  </div>
                  <div class="mono" style="font-size:0.85rem; background:rgba(13, 148, 136, 0.1); color:#0d9488; padding:4px 10px; border-radius:6px; font-weight:500;">${esc(item.start || '')} - ${esc(item.end || 'Present')}</div>
                </div>
                ${item.bullets && item.bullets.length ? `<ul style="margin-top:14px; padding-left:20px; font-size:0.95rem; color:#334155; line-height:1.6;">` + item.bullets.map(b => `<li style="margin-bottom:6px;">${esc(b)}</li>`).join('') + `</ul>` : ''}
              </div>`;
            });
            html += `</div>`;
          }
        } else if (sec.type === 'summary') {
          if (isEditingThisSec) {
            html += `<textarea id="edit-summary-text" rows="5" style="width:100%; padding:12px; border:1px solid var(--line); border-radius:8px; font:inherit; background:var(--paper); box-sizing:border-box;">${esc(sec.text || '')}</textarea>`;
          } else {
            html += `<div style="font-size:1rem; line-height:1.6; color:#334155; background:rgba(248, 250, 252, 0.9); padding:20px; border-radius:12px; border:1px solid rgba(13, 148, 136, 0.15);">${esc(sec.text || '')}</div>`;
          }
        } else {
          html += `<pre class="mono" style="font-size:0.85rem; white-space:pre-wrap; background:var(--paper); padding:16px; border-radius:var(--r); border:1px solid var(--line-soft);">${esc(JSON.stringify(sec, null, 2))}</pre>`;
        }
        
        html += `</div>`;
      });
      
      html += `</div>`;
      return html;
    };

    root.innerHTML = `<div style="max-width:950px; margin:0 auto; padding: 20px 0;">${renderSectionsUI()}</div>`;

    // Bind tab switcher
    root.querySelectorAll('.prof-tab-btn').forEach(btn => {
      btn.onclick = () => renderProfile(sections, editingSecType, btn.dataset.tab, false);
    });

    // Bind Re-upload button
    const reupBtn = $('#profReuploadBtn');
    if (reupBtn) {
      reupBtn.onclick = () => renderProfile(sections, editingSecType, activeTab, !showReupload);
    }
    const closeReupBtn = $('#closeReuploadBtn');
    if (closeReupBtn) {
      closeReupBtn.onclick = () => renderProfile(sections, editingSecType, activeTab, false);
    }

    // Bind Section Edit buttons
    root.querySelectorAll('.sec-edit-btn').forEach(btn => {
      btn.onclick = () => renderProfile(sections, btn.dataset.type, activeTab, false);
    });

    // Bind Section Cancel buttons
    root.querySelectorAll('.sec-cancel-btn').forEach(btn => {
      btn.onclick = () => renderProfile(isDraft ? sections : null, null, activeTab, false);
    });

    // Bind Section Add Entry buttons
    root.querySelectorAll('.add-item-btn').forEach(btn => {
      btn.onclick = () => {
        const stype = btn.dataset.sectype;
        const targetSec = sections.find(s => s.type === stype);
        if (targetSec && Array.isArray(targetSec.items)) {
          if (stype === 'education') targetSec.items.push({ degree: '', institution: '', year: '', score: '' });
          else if (stype === 'experience') targetSec.items.push({ role: '', org: '', start: '', end: '', bullets: [] });
          else if (stype === 'projects') targetSec.items.push({ heading: '', tech_stack: '', detail: '', link: '' });
          else if (stype === 'certifications') targetSec.items.push({ heading: '', issuer: '', year: '', link: '' });
          renderProfile(sections, stype, activeTab, false);
        }
      };
    });

    // Bind Section Remove Entry buttons
    root.querySelectorAll('.remove-item-btn').forEach(btn => {
      btn.onclick = () => {
        const stype = btn.dataset.sectype;
        const idx = parseInt(btn.dataset.idx, 10);
        const targetSec = sections.find(s => s.type === stype);
        if (targetSec && Array.isArray(targetSec.items)) {
          targetSec.items.splice(idx, 1);
          renderProfile(sections, stype, activeTab, false);
        }
      };
    });

    // Bind Section Save buttons
    root.querySelectorAll('.sec-save-btn').forEach(btn => {
      btn.onclick = async () => {
        const stype = btn.dataset.type;
        btn.disabled = true;
        btn.textContent = "Saving...";
        
        try {
          const updated = JSON.parse(JSON.stringify(sections));
          const sec = updated.find(s => s.type === stype);

          if (sec) {
            if (stype === 'personal') {
              sec.fields.name = $('#edit-personal-name').value.trim();
              sec.fields.mobile = $('#edit-personal-mobile').value.trim();
              sec.fields.phone = $('#edit-personal-mobile').value.trim();
              sec.fields.email = $('#edit-personal-email').value.trim();
              sec.fields.city = $('#edit-personal-city').value.trim();
              sec.fields.country = $('#edit-personal-country').value.trim();
              sec.fields.location = [sec.fields.city, sec.fields.country].filter(Boolean).join(', ');
              sec.fields.github = $('#edit-personal-github').value.trim();
              sec.fields.linkedin = $('#edit-personal-linkedin').value.trim();
              sec.fields.portfolio = $('#edit-personal-portfolio').value.trim();
              sec.fields.links = [sec.fields.github, sec.fields.linkedin, sec.fields.portfolio].filter(Boolean);
            } else if (stype === 'summary') {
              sec.text = $('#edit-summary-text').value.trim();
            } else if (stype === 'skills') {
              sec.items = $('#edit-skills').value.split(',').map(s => s.trim()).filter(Boolean);
            } else if (stype === 'experience') {
              sec.items.forEach((item, idx) => {
                item.role = $(`#edit-exp-role-${idx}`).value.trim();
                item.org = $(`#edit-exp-org-${idx}`).value.trim();
                item.start = $(`#edit-exp-start-${idx}`).value.trim();
                item.end = $(`#edit-exp-end-${idx}`).value.trim();
                item.bullets = $(`#edit-exp-bullets-${idx}`).value.split('\n').filter(b => b.trim());
              });
            } else if (stype === 'education') {
              sec.items.forEach((item, idx) => {
                item.degree = $(`#edit-edu-deg-${idx}`).value.trim();
                item.institution = $(`#edit-edu-inst-${idx}`).value.trim();
                item.year = $(`#edit-edu-year-${idx}`).value.trim();
                item.score = $(`#edit-edu-score-${idx}`) ? $(`#edit-edu-score-${idx}`).value.trim() : '';
              });
            } else if (stype === 'projects') {
              sec.items.forEach((item, idx) => {
                item.heading = $(`#edit-proj-head-${idx}`).value.trim();
                item.tech_stack = $(`#edit-proj-tech-${idx}`).value.trim();
                item.detail = $(`#edit-proj-detail-${idx}`).value.trim();
                item.link = $(`#edit-proj-link-${idx}`).value.trim();
              });
            } else if (stype === 'certifications') {
              sec.items.forEach((item, idx) => {
                item.heading = $(`#edit-cert-head-${idx}`).value.trim();
                item.issuer = $(`#edit-cert-issuer-${idx}`).value.trim();
                item.year = $(`#edit-cert-year-${idx}`).value.trim();
                item.link = $(`#edit-cert-link-${idx}`).value.trim();
              });
            }
          }

          await Api.updateProfile(updated);
          toast(`${sec ? sec.title : 'Section'} saved successfully!`);
          renderProfile(null, null, activeTab, false);
        } catch (e) {
          toast("Save failed: " + e.message, "err");
          btn.disabled = false;
          btn.textContent = "Save Section";
        }
      };
    });

    // Handle extraction dropzone/paste if shown
    if (!sections.length || showReupload) {
      const handleExtract = async (file, text) => {
        if (!file && !text) { toast("Provide a file or text.", "err"); return; }
        const btn = file ? $('#profBrowseBtn') : $('#profExtractTextBtn');
        const oldText = btn.textContent;
        btn.textContent = "Extracting...";
        
        try {
          const res = await Api.uploadResume(file, text);
          const extracted = res.sections.sections || res.sections;
          toast("Profile extracted successfully! Review your sections below.");
          renderProfile(extracted, null, activeTab, false);
        } catch (e) {
          toast(e.message, "err");
          btn.textContent = oldText;
        }
      };

      const fileInput = $('#profFile');
      if (fileInput) {
        fileInput.onchange = () => {
          const file = fileInput.files[0];
          if (file) handleExtract(file, '');
        };
      }

      const dz = $('#profDropzone');
      if (dz) {
        dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('drag'); };
        dz.ondragleave = (e) => { e.preventDefault(); dz.classList.remove('drag'); };
        dz.ondrop = (e) => {
          e.preventDefault(); dz.classList.remove('drag');
          if (e.dataTransfer.files.length) {
            $('#profFile').files = e.dataTransfer.files;
            handleExtract(e.dataTransfer.files[0], '');
          }
        };
      }

      const extBtn = $('#profExtractTextBtn');
      if (extBtn) {
        extBtn.onclick = () => {
          handleExtract(null, $('#profText').value.trim());
        };
      }
    }

  } catch (e) {
    root.innerHTML = `<div class="card err-msg">Failed to load profile.</div>`;
  }
}
    
    if (!sections.length) {
      const handleExtract = async (file, text) => {
        if (!file && !text) { toast("Provide a file or text.", "err"); return; }
        const btn = file ? $('#profDropzone') : $('#profExtractTextBtn');
        const oldHtml = btn.innerHTML;
        if (!file) btn.textContent = "Extracting...";
        else {
          $('#profDropzone h3').textContent = "Extracting Profile...";
          $('#profDropzone .muted').textContent = "This might take a few seconds.";
        }
        
        try {
          const res = await Api.uploadResume(file, text);
          const extracted = res.sections.sections || res.sections;
          toast("Profile extracted. Review and save below.");
          renderProfile(extracted); // Re-render with draft sections
        } catch (e) {
          toast(e.message, "err");
          if (!file) btn.textContent = "Extract from text";
          else {
            btn.innerHTML = oldHtml;
          }
        }
      };

      $('#profFile').onchange = () => {
        const file = $('#profFile').files[0];
        if (file) handleExtract(file, '');
      };
      
      const dz = $('#profDropzone');
      dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('drag'); };
      dz.ondragleave = (e) => { e.preventDefault(); dz.classList.remove('drag'); };
      dz.ondrop = (e) => {
        e.preventDefault(); dz.classList.remove('drag');
        if (e.dataTransfer.files.length) {
          $('#profFile').files = e.dataTransfer.files;
          handleExtract(e.dataTransfer.files[0], '');
        }
      };

      $('#profExtractTextBtn').onclick = () => {
        handleExtract(null, $('#profText').value.trim());
      };
    } else if (isEditMode) {
      $('#profCancelBtn').onclick = () => renderProfile(isDraft ? sections : null, false);
      $('#profSaveEditBtn').onclick = async () => {
        $('#profSaveEditBtn').disabled = true;
        $('#profSaveEditBtn').textContent = "Saving...";
        try {
          // Rebuild sections array from DOM
          const updated = JSON.parse(JSON.stringify(sections)); // deep copy to be safe
          updated.forEach(sec => {
            if (sec.type === 'personal') {
              sec.fields.name = $('#edit-personal-name').value.trim();
              sec.fields.mobile = $('#edit-personal-mobile').value.trim();
              sec.fields.phone = $('#edit-personal-mobile').value.trim();
              sec.fields.email = $('#edit-personal-email').value.trim();
              sec.fields.city = $('#edit-personal-city').value.trim();
              sec.fields.country = $('#edit-personal-country').value.trim();
              sec.fields.location = [sec.fields.city, sec.fields.country].filter(Boolean).join(', ');
              sec.fields.github = $('#edit-personal-github').value.trim();
              sec.fields.linkedin = $('#edit-personal-linkedin').value.trim();
              sec.fields.portfolio = $('#edit-personal-portfolio').value.trim();
              sec.fields.links = [sec.fields.github, sec.fields.linkedin, sec.fields.portfolio].filter(Boolean);
            } else if (sec.type === 'skills') {
              sec.items = $('#edit-skills').value.split(',').map(s => s.trim()).filter(s => s);
            } else if (sec.type === 'experience') {
              sec.items.forEach((item, idx) => {
                item.role = $(`#edit-exp-role-${idx}`).value;
                item.org = $(`#edit-exp-org-${idx}`).value;
                item.start = $(`#edit-exp-start-${idx}`).value;
                item.end = $(`#edit-exp-end-${idx}`).value;
                item.bullets = $(`#edit-exp-bullets-${idx}`).value.split('\\n').filter(b => b.trim());
              });
            } else if (sec.type === 'education') {
              sec.items.forEach((item, idx) => {
                item.degree = $(`#edit-edu-deg-${idx}`).value;
                item.institution = $(`#edit-edu-inst-${idx}`).value;
                item.year = $(`#edit-edu-year-${idx}`).value;
              });
            }
          });
          await Api.updateProfile(updated);
          toast("Profile saved successfully!");
          renderProfile(null, false); // Reload from server
        } catch (e) {
          toast("Save failed.", "err");
          $('#profSaveEditBtn').disabled = false;
          $('#profSaveEditBtn').textContent = "Save Changes";
        }
      };
    } else {
      $('#profEditBtn').onclick = async () => {
        if (isDraft) {
          $('#profEditBtn').disabled = true;
          $('#profEditBtn').textContent = "Saving...";
          try {
            await Api.updateProfile(sections);
            toast("Profile saved successfully!");
            renderProfile(null, false); // Reload from server to confirm
          } catch (e) {
            toast("Save failed.", "err");
            $('#profEditBtn').disabled = false;
            $('#profEditBtn').textContent = "Save Extracted Profile";
          }
        } else {
          renderProfile(sections, true); // Enter edit mode
        }
      };
    }
  } catch (e) {
    root.innerHTML = `<div class="card err-msg">Failed to load profile.</div>`;
  }
}

/* ---------------- Apply Assistant: Apply Studio (Phase B) ---------------- */
async function renderApply() {
  const root = $('#applyRoot');
  root.innerHTML = `<div class="card" style="text-align:center; padding:40px;"><h2>Loading Apply Studio...</h2></div>`;
  try {
    const apps = await Api.getApplications();
    const listHtml = apps.length ? apps.map(a => `
      <div class="card learn-item" style="cursor:pointer; background:rgba(255, 255, 255, 0.7); backdrop-filter:blur(20px); border:1px solid rgba(13, 148, 136, 0.2); box-shadow:0 4px 15px rgba(0,0,0,0.05); border-radius:12px; margin-bottom:12px; padding:16px; display:flex; justify-content:space-between; align-items:center; transition:transform 0.2s, box-shadow 0.2s;" data-appid="${esc(a.id)}" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 8px 25px rgba(13,148,136,0.15)';" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 15px rgba(0,0,0,0.05)';">
        <div class="li-body">
          <div class="hi-title" style="font-family:'Inter', sans-serif; font-size:18px; font-weight:600; color:#0f172a; margin-bottom:4px;">${esc(a.job_title)}</div>
          <div class="hi-date mono" style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a;">${esc(a.company)} &middot; Match: ${a.match_pct}% &middot; Status: ${a.status}</div>
        </div>
        <button class="btn btn-ghost btn-sm" style="color:#0d9488; font-family:'Inter', sans-serif; font-weight:500;">View →</button>
      </div>`).join('') : '<p style="text-align:center; color:#5c647a; font-family:\\\'Inter\\\', sans-serif;">No applications yet.</p>';
      
    root.innerHTML = `<div class="card" style="max-width:800px; margin:0 auto; background:rgba(248, 249, 255, 0.9); backdrop-filter:blur(40px); border:1px solid rgba(13, 148, 136, 0.15); border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,0.08); padding:40px;">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid rgba(13, 148, 136, 0.2); padding-bottom:16px; margin-bottom:24px;">
        <h2 style="margin:0; font-family:'Inter', sans-serif; font-size:32px; font-weight:700; color:#0f172a; letter-spacing:-0.01em;">Apply Studio</h2>
        <button class="btn btn-primary" id="newAppBtn" style="background:linear-gradient(135deg, #0d9488 0%, #00685f 100%); border:none; padding:10px 20px; border-radius:8px; font-family:'Inter', sans-serif; font-weight:600; box-shadow:0 4px 15px rgba(13, 148, 136, 0.3); color:white; cursor:pointer;">New Application</button>
      </div>
      <div class="hist-list">${listHtml}</div>
    </div>`;
    
    root.querySelectorAll('[data-appid]').forEach(el => {
      el.onclick = () => renderApplicationDetail(el.dataset.appid);
    });
    
    $('#newAppBtn').onclick = () => {
      root.innerHTML = `<div class="card" style="max-width:800px; margin:0 auto; background:rgba(248, 249, 255, 0.9); backdrop-filter:blur(40px); border:1px solid rgba(13, 148, 136, 0.15); border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,0.08); padding:40px;">
        <h2 style="margin:0 0 24px 0; font-family:'Inter', sans-serif; font-size:32px; font-weight:700; color:#0f172a; letter-spacing:-0.01em; border-bottom:2px solid rgba(13, 148, 136, 0.2); padding-bottom:16px;">New Application</h2>
        
        <div class="field" style="margin-bottom:24px;">
          <label style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a; font-weight:500; display:block; margin-bottom:4px;">JOB DESCRIPTION URL OR PASTED TEXT</label>
          <input type="text" id="newAppUrl" placeholder="https://..." style="width:100%; padding:12px; border:1px solid rgba(109, 122, 119, 0.3); border-radius:8px; font-family:'Inter', sans-serif; background:rgba(255,255,255,0.7); box-sizing:border-box;">
          <textarea id="newAppText" rows="6" placeholder="Or paste the full job description here..." style="width:100%; padding:12px; border:1px solid rgba(109, 122, 119, 0.3); border-radius:8px; font-family:'Inter', sans-serif; background:rgba(255,255,255,0.7); box-sizing:border-box; margin-top:8px;"></textarea>
        </div>
        
        <div style="display:flex; gap:16px; margin-bottom:32px;">
          <div class="field" style="flex:1;">
            <label style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a; font-weight:500; display:block; margin-bottom:4px;">COMPANY NAME (OPTIONAL)</label>
            <input type="text" id="newAppCompany" style="width:100%; padding:12px; border:1px solid rgba(109, 122, 119, 0.3); border-radius:8px; font-family:'Inter', sans-serif; background:rgba(255,255,255,0.7); box-sizing:border-box;">
          </div>
          <div class="field" style="flex:1;">
            <label style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a; font-weight:500; display:block; margin-bottom:4px;">JOB TITLE (OPTIONAL)</label>
            <input type="text" id="newAppTitle" style="width:100%; padding:12px; border:1px solid rgba(109, 122, 119, 0.3); border-radius:8px; font-family:'Inter', sans-serif; background:rgba(255,255,255,0.7); box-sizing:border-box;">
          </div>
        </div>
        
        <div style="display:flex; gap:12px; justify-content:flex-end;">
          <button class="btn btn-ghost" onclick="renderApply()" style="color:#64748b; font-family:'Inter', sans-serif; padding:10px 20px; cursor:pointer;">Cancel</button>
          <button class="btn btn-primary" id="extractBtn" style="background:linear-gradient(135deg, #0d9488 0%, #00685f 100%); border:none; padding:10px 24px; border-radius:8px; font-family:'Inter', sans-serif; font-weight:600; box-shadow:0 4px 15px rgba(13, 148, 136, 0.3); color:white; cursor:pointer;">Extract & Match</button>
        </div>
      </div>`;
      
      $('#extractBtn').onclick = async () => {
        const url = $('#newAppUrl').value.trim();
        const text = $('#newAppText').value.trim();
        if (!url && !text) { toast("Provide a URL or text.", "err"); return; }
        $('#extractBtn').disabled = true; $('#extractBtn').textContent = "Extracting...";
        try {
          const res = await Api.extractJd(url, text);
          if (res.extracted.blocked) {
             toast(res.extracted.message, "err");
             $('#extractBtn').disabled = false; $('#extractBtn').textContent = "Extract & Match";
             return;
          }
          const saved = await Api.createApplication({
            company: $('#newAppCompany').value.trim() || res.extracted.source || 'Unknown',
            job_title: $('#newAppTitle').value.trim() || 'Role',
            job_url: url,
            jd_text: res.extracted.jd_text,
            jd_skills: res.skills,
            match: res.match,
            status: 'draft'
          });
          toast("Application matched & saved!");
          renderApplicationDetail(saved.id);
        } catch (e) {
          toast(e.message, "err");
          $('#extractBtn').disabled = false; $('#extractBtn').textContent = "Extract & Match";
        }
      };
    };
  } catch (e) {
    root.innerHTML = `<div class="card err-msg">Failed to load Apply Studio.</div>`;
  }
}

async function renderApplicationDetail(id) {
  const root = $('#applyRoot');
  root.innerHTML = `<div class="card" style="text-align:center; padding:40px;"><h2>Loading...</h2></div>`;
  try {
    const app = await Api.getApplication(id);
    const m = app.match || {};
    
    let docsHtml = '';
    if (app.docs && app.docs.length) {
      docsHtml = `<div style="margin-top:32px;">
        <h3 style="color:var(--primary); font-family:'Inter', sans-serif; font-weight:600; margin-bottom:16px;">Generated Documents</h3>
        <div style="display:flex; flex-direction:column; gap:16px;">` + app.docs.map(d => {
        return `<div class="card" style="background:rgba(255, 255, 255, 0.7); backdrop-filter:blur(20px); border:1px solid rgba(13, 148, 136, 0.2); box-shadow:0 10px 30px rgba(0,0,0,0.05); border-radius:12px; padding:24px;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(13, 148, 136, 0.1); padding-bottom:12px; margin-bottom:16px;">
            <h4 style="margin:0; color:#0f172a; font-family:'Inter', sans-serif; font-size:18px;">${esc(d.kind.replace('_', ' ').toUpperCase())}</h4>
            <div style="display:flex; gap:8px;">
              <button onclick="Api.exportApplyDoc('${app.id}', '${esc(d.kind)}', 'pdf')" class="btn btn-sm" style="background:#0d9488; color:white; border-radius:8px; border:none; padding:6px 12px; font-family:'Inter', sans-serif; cursor:pointer;">Export PDF</button>
              <button onclick="Api.exportApplyDoc('${app.id}', '${esc(d.kind)}', 'docx')" class="btn btn-sm" style="background:transparent; color:#0d9488; border:1px solid #0d9488; border-radius:8px; padding:6px 12px; font-family:'Inter', sans-serif; cursor:pointer;">Export DOCX</button>
            </div>
          </div>
          <pre style="white-space:pre-wrap; font-size:13px; font-family:'JetBrains Mono', monospace; background:rgba(248, 249, 255, 0.8); border:1px solid rgba(109, 122, 119, 0.2); border-radius:8px; padding:16px; max-height:400px; overflow-y:auto; color:#333;">${esc(JSON.stringify(d.content, null, 2))}</pre>
        </div>`;
      }).join('') + `</div></div>`;
    }
    
    root.innerHTML = `<div class="card" style="max-width:800px; margin:0 auto; background:rgba(248, 249, 255, 0.9); backdrop-filter:blur(40px); border:1px solid rgba(13, 148, 136, 0.15); border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,0.08); padding:40px;">
      <button class="btn btn-ghost btn-sm" onclick="renderApply()" style="margin-bottom:24px; color:#64748b; font-family:'Inter', sans-serif;">← Back to Applications</button>
      
      <div style="border-bottom:2px solid rgba(13, 148, 136, 0.2); padding-bottom:16px; margin-bottom:24px;">
        <h2 style="margin:0; font-family:'Inter', sans-serif; font-size:32px; font-weight:700; color:#0f172a; letter-spacing:-0.01em;">${esc(app.job_title)}</h2>
        <h3 style="margin:4px 0 0 0; font-family:'Inter', sans-serif; font-size:20px; font-weight:500; color:#38bdf8;">at ${esc(app.company)}</h3>
      </div>
      
      <div style="display:flex; gap:12px; align-items:center; font-family:'JetBrains Mono', monospace; font-size:12px; margin-bottom:24px;">
        <span style="background:rgba(13, 148, 136, 0.1); color:#0d9488; padding:4px 10px; border-radius:999px; font-weight:600;">AI Precision: ${m.match_pct || 0}% Match</span>
      </div>
      
      <div class="field" style="margin-bottom:24px; background:rgba(255, 255, 255, 0.6); padding:16px; border-radius:12px; border:1px solid rgba(109, 122, 119, 0.2);">
        <label style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a; font-weight:500; display:block; margin-bottom:4px;">MISSING SKILLS</label>
        <p style="margin:0; font-family:'Inter', sans-serif; font-size:14px; color:#0f172a;">${m.gaps && m.gaps.length ? m.gaps.join(', ') : 'None! 100% Match.'}</p>
      </div>
      
      <div class="field" style="margin-bottom:24px;">
        <label style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a; font-weight:500; display:block; margin-bottom:4px;">SCREENING QUESTIONS (OPTIONAL)</label>
        <textarea id="appQs" rows="3" placeholder="e.g. How many years of Python experience do you have?" style="width:100%; padding:12px; border:1px solid rgba(109, 122, 119, 0.3); border-radius:8px; font-family:'Inter', sans-serif; background:rgba(255,255,255,0.7); box-sizing:border-box;"></textarea>
      </div>
      
      <div class="field" style="margin-bottom:32px;">
        <label style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#5c647a; font-weight:500; display:block; margin-bottom:4px;">TAILORING STRATEGY</label>
        <select id="tailorMode" style="width:100%; padding:12px; border:1px solid rgba(13, 148, 136, 0.4); border-radius:8px; font-family:'Inter', sans-serif; font-size:14px; background:rgba(255,255,255,0.8); color:#0f172a; outline:none; box-shadow:0 0 0 2px rgba(13,148,136,0.1); box-sizing:border-box;">
          <option value="moderate">Moderate (Strict Grounding - Use my actual skills)</option>
          <option value="aggressive">Aggressive (ATS Hacking - Inject missing JD keywords)</option>
        </select>
      </div>
      
      <button class="btn btn-primary" id="generateBtn" style="width:100%; background:linear-gradient(135deg, #0d9488 0%, #00685f 100%); border:none; padding:14px; border-radius:8px; font-family:'Inter', sans-serif; font-weight:600; font-size:16px; box-shadow:0 4px 15px rgba(13, 148, 136, 0.3); color:white; cursor:pointer;">Generate Tailored Docs</button>
      
      ${docsHtml}
    </div>`;
    
    $('#generateBtn').onclick = async () => {
      const qsRaw = $('#appQs').value.trim();
      const qs = qsRaw ? qsRaw.split('\\n').map(s => s.trim()).filter(Boolean) : [];
      const mode = $('#tailorMode').value;
      $('#generateBtn').disabled = true; $('#generateBtn').textContent = "Generating... (this takes ~15s)";
      try {
        await Api.generateApplyDocs({
          application_id: app.id,
          kinds: ["resume", "cover_letter", "answers"],
          questions: qs,
          tailor_mode: mode
        });
        toast("Documents generated & grounded!");
        renderApplicationDetail(app.id); // reload view
      } catch (e) {
        toast(e.message, "err");
        $('#generateBtn').disabled = false; $('#generateBtn').textContent = "Generate Tailored Docs";
      }
    };
  } catch (e) {
    toast(e.message, "err");
    renderApply();
  }
}

/* ---------------- boot ---------------- */
(async function boot() {
  loadMeta();
  Api.authConfig().then((c) => { State.auth = c; if (c && c.google_enabled) loadGis(); }).catch(() => {});
  Api.skills().then((s) => State.catalog = s).catch(() => {});
  if (Store.token) { try { Store.user = await Api.me(); } catch { Store.clear(); } }
  renderNav();
  $('#tryAshaBtn').onclick = () => runAnalysis('text', ASHA_SAMPLE);
  if (!location.hash) location.hash = '#/';
  route();
})();
