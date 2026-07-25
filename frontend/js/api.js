/* PathFinderAI API client + token/session management. */
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

  authConfig: () => fetch(`${API}/auth/config`).then(handle),
  googleLogin: (credential) => fetch(`${API}/auth/google`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ credential }),
  }).then(handle),
  forgotPassword: (email) => fetch(`${API}/auth/forgot`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }),
  }).then(handle),
  resetPassword: (token, password) => fetch(`${API}/auth/reset`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, password }),
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

  // Professional dashboard — job matching
  matchJobs: (body) => fetch(`${API}/jobs/match`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body),
  }).then(handle),

  // Learning tracker (Phase 3)
  learning: () => fetch(`${API}/learning/`, { headers: authHeaders() }).then(handle),
  addLearning: (item) => fetch(`${API}/learning/`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(item),
  }).then(handle),
  patchLearning: (id, status) => fetch(`${API}/learning/${id}`, {
    method: 'PATCH', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ status }),
  }).then(handle),
  deleteLearning: (id) => fetch(`${API}/learning/${id}`, { method: 'DELETE', headers: authHeaders() }).then(handle),
  progress: (analysisId) => fetch(`${API}/learning/progress?analysis_id=${encodeURIComponent(analysisId)}`, { headers: authHeaders() }).then(handle),
  journey: () => fetch(`${API}/learning/journey`, { headers: authHeaders() }).then(handle),
  getPrefs: () => fetch(`${API}/learning/prefs`, { headers: authHeaders() }).then(handle),
  putPrefs: (body) => fetch(`${API}/learning/prefs`, {
    method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body),
  }).then(handle),

  updatePersona: (persona) => fetch(`${API}/auth/me`, {
    method: 'PATCH', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ persona }),
  }).then(handle),

  // Goal-first reverse roadmap (Phase 1, v2)
  roles: () => fetch(`${API}/catalog/roles`).then(handle),
  resolveGoal: (body) => fetch(`${API}/roadmap/resolve`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body),
  }).then(handle),
  createRoadmap: (body) => fetch(`${API}/roadmap/`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body),
  }).then(handle),
  listRoadmaps: () => fetch(`${API}/roadmap/`, { headers: authHeaders() }).then(handle),
  adoptRoadmap: (id) => fetch(`${API}/roadmap/${encodeURIComponent(id)}/adopt`, {
    method: 'POST', headers: authHeaders(),
  }).then(handle),

  // Guided intake + persona card (Phase 2, v2)
  intakeQuestions: () => fetch(`${API}/intake/questions`).then(handle),
  intakeAnalyze: (answers) => fetch(`${API}/intake/analyze`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ answers }),
  }).then(handle),
  shareCard: (card) => fetch(`${API}/intake/card/share`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ card }),
  }).then(handle),
  sharedCard: (token) => fetch(`${API}/intake/card/shared/${encodeURIComponent(token)}`).then(handle),

  // Apply Assistant: Master Profile (Phase A)
  getProfile: () => fetch(`${API}/profile/`, { headers: authHeaders() }).then(handle),
  updateProfile: (sections) => fetch(`${API}/profile/`, {
    method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(sections),
  }).then(handle),
  uploadResume: (file, text = '') => {
    const fd = new FormData();
    if (file) fd.append('file', file);
    if (text) fd.append('text', text);
    return fetch(`${API}/profile/from-resume`, { method: 'POST', headers: authHeaders(), body: fd }).then(handle);
  },

  // Apply Assistant: Apply Studio (Phase B)
  getApplications: () => fetch(`${API}/apply/`, { headers: authHeaders() }).then(handle),
  getApplication: (id) => fetch(`${API}/apply/${id}`, { headers: authHeaders() }).then(handle),
  createApplication: (data) => fetch(`${API}/apply/`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(data),
  }).then(handle),
  extractJd: (url, jd_text) => fetch(`${API}/apply/extract`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ url, jd_text }),
  }).then(handle),
  generateApplyDocs: (data) => fetch(`${API}/apply/generate`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(data),
  }).then(handle),
};
