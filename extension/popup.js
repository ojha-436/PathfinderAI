/* PathFinder Apply — popup. Login ↔ profile-picker, then autofill the current tab. */
const root = document.getElementById('root');
const send = (msg) => chrome.runtime.sendMessage(msg);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function getApiBase() { return (await chrome.storage.local.get('apiBase')).apiBase || 'http://localhost:8099'; }

function status(html) { const s = document.getElementById('status'); if (s) s.innerHTML = html; }

async function init() {
  const apiBase = await getApiBase();
  const me = await send({ type: 'PF_ME' }).catch(() => null);
  if (me && me.ok) renderApp(me.user, apiBase);
  else renderLogin(apiBase, me);
}

function renderLogin(apiBase, me) {
  root.innerHTML = `
    <label>PathFinder server</label>
    <input id="apiBase" type="text" value="${esc(apiBase)}">
    <label>Email</label>
    <input id="email" type="email" placeholder="you@example.com" autocomplete="username">
    <label>Password</label>
    <input id="password" type="password" placeholder="••••••••" autocomplete="current-password">
    <button class="primary" id="login">Sign in</button>
    <div id="status"></div>
    <div class="hint">Use your PathFinder account. Your login stays in this browser; the page you're applying on never sees it.</div>`;
  document.getElementById('login').onclick = async () => {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    await chrome.storage.local.set({ apiBase: document.getElementById('apiBase').value.trim() });
    if (!email || !password) { status('<span class="err">Enter your email and password.</span>'); return; }
    status('<span class="ok">Signing in…</span>');
    const r = await send({ type: 'PF_LOGIN', email, password });
    if (r && r.ok) init(); else status(`<span class="err">${esc((r && r.error) || 'Login failed.')}</span>`);
  };
}

async function renderApp(user, apiBase) {
  const vr = await send({ type: 'PF_VARIANTS' }).catch(() => ({ variants: [] }));
  const variants = (vr && vr.variants) || [];
  const { selectedVariant = '' } = await chrome.storage.local.get('selectedVariant');
  const opts = ['<option value="">Master profile</option>']
    .concat(variants.map((v) => `<option value="${esc(v.id)}"${v.id === selectedVariant ? ' selected' : ''}>${esc(v.name)}${v.is_default ? ' (default)' : ''}</option>`))
    .join('');
  root.innerHTML = `
    <div class="who"><span>Signed in as <b>${esc(user.email)}</b></span><button class="link" id="logout">Log out</button></div>
    <label>Apply with</label>
    <select id="variant">${opts}</select>
    <button class="primary" id="fill">Autofill this application</button>
    <div id="status"></div>
    <div class="hint">Open a job application page, pick a profile, then Autofill. Review everything and click the site's own <b>Submit</b> — PathFinder never submits for you.</div>
    <details><summary>Settings</summary><label>PathFinder server</label><input id="apiBase" type="text" value="${esc(apiBase)}"></details>`;

  document.getElementById('logout').onclick = async () => { await send({ type: 'PF_LOGOUT' }); init(); };
  document.getElementById('variant').onchange = (e) => chrome.storage.local.set({ selectedVariant: e.target.value });
  const apiInput = document.getElementById('apiBase');
  if (apiInput) apiInput.onchange = () => chrome.storage.local.set({ apiBase: apiInput.value.trim() });

  document.getElementById('fill').onclick = async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id || /^(chrome|edge|about|chrome-extension):/.test(tab.url || '')) {
      status('<span class="err">Open a job application page first.</span>'); return;
    }
    status('<span class="ok">Filling…</span>');
    // Ensure the content script is present (declarative on ATS hosts; injected elsewhere).
    let alive = false;
    try { const p = await chrome.tabs.sendMessage(tab.id, { type: 'PF_PING' }); alive = !!(p && p.ok); } catch (e) { alive = false; }
    if (!alive) {
      try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] }); }
      catch (e) { status(`<span class="err">Can't run on this page: ${esc(e.message)}</span>`); return; }
    }
    try {
      await chrome.tabs.sendMessage(tab.id, { type: 'PF_START_FILL' });
      status('<span class="ok">Done — check the page, review, and submit yourself.</span>');
    } catch (e) { status(`<span class="err">${esc(e.message)}</span>`); }
  };
}

init();
