/* PathFinder API client + token/session management. */
const API = '/api';

const Store = {
  get token() { return localStorage.getItem('pf_token') || ''; },
  set token(v) { v ? localStorage.setItem('pf_token', v) : localStorage.removeItem('pf_token'); },
  get user() { try { return JSON.parse(localStorage.getItem('pf_user') || 'null'); } catch { return null; } },
  set user(u) { u ? localStorage.setItem('pf_user', JSON.stringify(u)) : localStorage.removeItem('pf_user'); },
  clear() { this.token = ''; this.user = null; },
};

function authHeaders(extra = {}) {
  const h = { Accept: 'application/json', ...extra };
  if (Store.token) h.Authorization = `Bearer ${Store.token}`;
  return h;
}

async function handle(res) {
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return data;
}

const Api = {
  meta: () => fetch(`${API}/meta/`).then(handle),

  register: (email, password) =>
    fetch(`${API}/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }).then(handle),

  login: (email, password) =>
    fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }).then(handle),

  me: () => fetch(`${API}/auth/me`, { headers: authHeaders() }).then(handle),
  deleteAccount: () => fetch(`${API}/auth/me`, { method: 'DELETE', headers: authHeaders() }).then(handle),

  analyzeFile: (file, platform = '') => {
    const fd = new FormData(); fd.append('file', file);
    if (platform) fd.append('platform', platform);
    return fetch(`${API}/analysis/`, { method: 'POST', headers: authHeaders(), body: fd }).then(handle);
  },
  analyzeText: (text, platform = '') => {
    const fd = new FormData(); fd.append('resume_text', text);
    if (platform) fd.append('platform', platform);
    return fetch(`${API}/analysis/`, { method: 'POST', headers: authHeaders(), body: fd }).then(handle);
  },
  analyzeManual: (profile) => {
    const fd = new FormData(); fd.append('manual_profile', JSON.stringify(profile));
    return fetch(`${API}/analysis/`, { method: 'POST', headers: authHeaders(), body: fd }).then(handle);
  },

  history: () => fetch(`${API}/history/`, { headers: authHeaders() }).then(handle),
  getAnalysis: (id) => fetch(`${API}/history/${id}`, { headers: authHeaders() }).then(handle),
  deleteAnalysis: (id) => fetch(`${API}/history/${id}`, { method: 'DELETE', headers: authHeaders() }).then(handle),

  skills: () => fetch(`${API}/catalog/skills`).then(handle),
};
