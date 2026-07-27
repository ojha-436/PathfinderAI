/* PathFinder Apply — popup.
 * Normally there's nothing to do here: the extension auto-connects from the PathFinder
 * web app (you sign in there once, it links itself). This popup just shows the connected
 * state and the Autofill button. Manual server + login live under "Advanced" for
 * developers / self-hosted setups. */
const root = document.getElementById('root');
const send = (msg) => chrome.runtime.sendMessage(msg);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const PROD = 'https://pathfinder-383713992026.asia-south1.run.app';
async function getApiBase() { return (await chrome.storage.local.get('apiBase')).apiBase || PROD; }

function status(html) { const s = document.getElementById('status'); if (s) s.innerHTML = html; }

let _poll = null;
function stopPoll() { if (_poll) { clearInterval(_poll); _poll = null; } }

async function init() {
  const apiBase = await getApiBase();
  const me = await send({ type: 'PF_ME' }).catch(() => null);
  if (me && me.ok) { stopPoll(); renderApp(me.user, apiBase); }
  else renderConnect(apiBase);
}

// Default / disconnected state. The extension links itself automatically from the web app —
// so this screen's job is a friendly one-click reconnect, not a login form.
async function renderConnect(apiBase) {
  // If the active tab is a PathFinder page we can reconnect straight through it — and for
  // developers, prefer its origin (e.g. localhost) over the production default so the
  // Advanced field and manual login never silently point at the wrong server.
  let pfTab = null, pfOrigin = null;
  try {
    const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (t && t.url) {
      const u = new URL(t.url);
      const isPF = u.hostname === 'localhost' || u.hostname === '127.0.0.1' ||
        u.hostname.endsWith('.pathfinder.app') || u.hostname === 'pathfinder-383713992026.asia-south1.run.app';
      if (isPF) { pfTab = t; pfOrigin = u.origin; }
    }
  } catch (e) { /* activeTab URL may be unavailable */ }
  const advBase = pfOrigin || apiBase;

  root.innerHTML = `
    <p class="lead">Not connected. The extension links to your PathFinder account <b>automatically</b> — just make sure you're signed in on the website.</p>
    <button class="primary" id="reconnect">${pfTab ? 'Reconnect via this tab' : 'Open PathFinder & connect'}</button>
    <div class="waiting" id="waiting">Waiting…</div>
    <details class="adv"><summary>Advanced — developer / self-hosted</summary>
      <label>PathFinder server</label>
      <input id="apiBase" type="text" value="${esc(advBase)}">
      <label>Email</label>
      <input id="email" type="email" placeholder="you@example.com" autocomplete="username">
      <label>Password</label>
      <input id="password" type="password" placeholder="••••••••" autocomplete="current-password">
      <button class="primary" id="login">Sign in manually</button>
      <div id="advStatus"></div>
    </details>`;

  document.getElementById('reconnect').onclick = async () => {
    await send({ type: 'PF_RECONNECT' });   // clear the explicit-disconnect flag first
    const w = document.getElementById('waiting');
    if (pfTab && pfTab.id) {
      await chrome.storage.local.set({ apiBase: pfOrigin });
      chrome.tabs.reload(pfTab.id);          // re-runs the page → it re-hands credentials to us
      if (w) w.textContent = 'Reconnecting via your PathFinder tab…';
    } else {
      const base = (document.getElementById('apiBase').value.trim() || apiBase).replace(/\/$/, '');
      await chrome.storage.local.set({ apiBase: base });
      chrome.tabs.create({ url: base });     // open the web app → it hands credentials on load
      if (w) w.textContent = 'Opened PathFinder — sign in there if needed; this connects on its own.';
    }
  };

  document.getElementById('login').onclick = async () => {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    await chrome.storage.local.set({ apiBase: document.getElementById('apiBase').value.trim().replace(/\/$/, ''), disconnected: false });
    const st = (h) => { const e = document.getElementById('advStatus'); if (e) e.innerHTML = h; };
    if (!email || !password) { st('<span class="err">Enter your email and password.</span>'); return; }
    st('<span class="ok">Signing in…</span>');
    const r = await send({ type: 'PF_LOGIN', email, password });
    if (r && r.ok) init(); else st(`<span class="err">${esc((r && r.error) || 'Login failed.')}</span>`);
  };

  // If the web app hands over credentials while this popup is open, PF_ME starts succeeding —
  // flip to the connected view on its own.
  stopPoll();
  _poll = setInterval(async () => {
    const me = await send({ type: 'PF_ME' }).catch(() => null);
    if (me && me.ok) init();
  }, 1500);
}

async function renderApp(user, apiBase) {
  const vr = await send({ type: 'PF_VARIANTS' }).catch(() => ({ variants: [] }));
  const variants = (vr && vr.variants) || [];
  const { selectedVariant = '' } = await chrome.storage.local.get('selectedVariant');
  const opts = ['<option value="">Master profile</option>']
    .concat(variants.map((v) => `<option value="${esc(v.id)}"${v.id === selectedVariant ? ' selected' : ''}>${esc(v.name)}${v.is_default ? ' (default)' : ''}</option>`))
    .join('');
  root.innerHTML = `
    <div class="who"><span>Connected as <b>${esc(user.email)}</b></span><button class="link" id="logout">Disconnect</button></div>
    <label>Apply with</label>
    <select id="variant">${opts}</select>
    <button class="primary" id="fill">Autofill this application</button>
    <div id="status"></div>
    <div class="hint">Open a job application page, pick a profile, then Autofill. Review everything and click the site's own <b>Submit</b> — PathFinder never submits for you.</div>
    <details><summary>Settings</summary><label>PathFinder server</label><input id="apiBase" type="text" value="${esc(apiBase)}"><div class="hint">Auto-set from the PathFinder site you signed in on. Change only for a self-hosted server.</div></details>`;

  document.getElementById('logout').onclick = async () => { await send({ type: 'PF_LOGOUT' }); init(); };
  document.getElementById('variant').onchange = (e) => chrome.storage.local.set({ selectedVariant: e.target.value });
  const apiInput = document.getElementById('apiBase');
  if (apiInput) apiInput.onchange = () => chrome.storage.local.set({ apiBase: apiInput.value.trim().replace(/\/$/, '') });

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
