/* PathFinder Apply — background service worker.
 * Central place for auth + all PathFinder API calls, so the page/content script
 * never sees the token. Content script and popup talk to it via messages.
 */
const DEFAULT_API = 'http://localhost:8099';

async function cfg() {
  const s = await chrome.storage.local.get(['apiBase', 'token', 'selectedVariant']);
  return { apiBase: (s.apiBase || DEFAULT_API).replace(/\/$/, ''), token: s.token || '', selectedVariant: s.selectedVariant || '' };
}

async function api(path, opts = {}) {
  const { apiBase, token } = await cfg();
  const headers = Object.assign({ Accept: 'application/json' }, opts.headers || {});
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(apiBase + path, { ...opts, headers });
}

async function login(email, password) {
  const { apiBase } = await cfg();
  const res = await fetch(`${apiBase}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(res.status === 401 ? 'Wrong email or password.' : `Login failed (${res.status}).`);
  const d = await res.json();
  await chrome.storage.local.set({ token: d.access_token });
  return true;
}

function flatten(p) {
  const secs = p.sections_json || [];
  const per = (secs.find((s) => s.type === 'personal') || {}).fields || {};
  const exp = (secs.find((s) => s.type === 'experience') || {}).items || [];
  const edu = (secs.find((s) => s.type === 'education') || {}).items || [];
  const nm = (per.name || '').trim();
  return {
    full_name: nm, first_name: nm.split(' ')[0] || '', last_name: nm.split(' ').slice(1).join(' ') || '',
    email: per.email || '', phone: per.mobile || per.phone || '', location: per.location || '',
    country: per.country || '', linkedin: per.linkedin || '', github: per.github || '', website: per.portfolio || '',
    company: (exp[0] || {}).org || '', title: (exp[0] || {}).role || '',
    school: (edu[0] || {}).institution || '', degree: (edu[0] || {}).degree || '',
  };
}

function bufToB64(buf) {
  let s = ''; const b = new Uint8Array(buf);
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s);
}

async function getFillData() {
  const { token, selectedVariant } = await cfg();
  if (!token) return { error: 'Not signed in — open the PathFinder Apply popup and log in.' };
  const pr = await api('/api/profile/');
  if (pr.status === 401) return { error: 'Session expired — log in again from the popup.' };
  if (!pr.ok) return { error: `Could not load your profile (${pr.status}).` };
  const profile = await pr.json();
  if (!profile.sections_json || !profile.sections_json.length) return { error: 'Your master profile is empty — build it in PathFinder first.' };

  const flat = flatten(profile);
  let resume = null;
  try {
    const q = selectedVariant ? `?variant_id=${encodeURIComponent(selectedVariant)}&fmt=pdf` : '?fmt=pdf';
    const rr = await api('/api/profile/resume' + q);
    if (rr.ok) {
      resume = { filename: `${(flat.full_name || 'resume').replace(/\s+/g, '_')}.pdf`, mime: 'application/pdf', content: bufToB64(await rr.arrayBuffer()) };
    }
  } catch (e) { /* résumé is best-effort; fields still fill */ }
  return { profile: flat, resume };
}

async function logApply(meta) {
  try {
    await api('/api/apply/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company: meta.company || '', job_title: meta.title || '', job_url: meta.url || '', jd_text: '', status: 'applied' }),
    });
    return true;
  } catch (e) { return false; }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case 'PF_LOGIN': await login(msg.email, msg.password); sendResponse({ ok: true }); break;
        case 'PF_LOGOUT': await chrome.storage.local.remove('token'); sendResponse({ ok: true }); break;
        case 'PF_ME': { const r = await api('/api/auth/me'); sendResponse(r.ok ? { ok: true, user: await r.json() } : { ok: false }); break; }
        case 'PF_VARIANTS': { const r = await api('/api/profile/variants'); sendResponse({ ok: true, variants: r.ok ? await r.json() : [] }); break; }
        case 'PF_GET_FILLDATA': sendResponse(await getFillData()); break;
        case 'PF_LOG_APPLY': sendResponse({ ok: await logApply(msg.meta || {}) }); break;
        default: sendResponse({ error: 'unknown message' });
      }
    } catch (e) { sendResponse({ error: e.message }); }
  })();
  return true; // async response
});
