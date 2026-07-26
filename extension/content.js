/* PathFinder Apply — content script (production).
 *
 * Autofills the application form in the user's own browser/session from their
 * PathFinder profile, attaches the ATS-clean résumé, flags judgement-call fields,
 * and logs the application to the tracker when the user submits. It NEVER submits,
 * bypasses CAPTCHAs, or creates accounts. Runs on supported ATS hosts (declarative)
 * and can be injected on any page by the popup.
 */
(() => {
  if (window.__pfApplyInit) return;
  window.__pfApplyInit = true;

  // ---- Per-ATS field maps (selector → profile key). Applied first, high confidence.
  const ADAPTERS = {
    greenhouse: {
      '#first_name': 'first_name', '#last_name': 'last_name', '#email': 'email', '#phone': 'phone',
      'input[autocomplete="given-name"]': 'first_name', 'input[autocomplete="family-name"]': 'last_name',
    },
    lever: {
      'input[name="name"]': 'full_name', 'input[name="email"]': 'email', 'input[name="phone"]': 'phone',
      'input[name="org"]': 'company', 'input[name="urls[LinkedIn]"]': 'linkedin', 'input[name="urls[GitHub]"]': 'github',
    },
    ashby: {
      '#_systemfield_name': 'full_name', '#_systemfield_email': 'email',
    },
    workday: {
      '[data-automation-id="legalNameSection_firstName"]': 'first_name',
      '[data-automation-id="legalNameSection_lastName"]': 'last_name',
      'input[data-automation-id="email"]': 'email', 'input[data-automation-id="phone-number"]': 'phone',
      'input[data-automation-id="addressSection_city"]': 'location',
    },
  };
  const adapterFor = (host) => {
    if (host.includes('greenhouse.io')) return ADAPTERS.greenhouse;
    if (host.includes('lever.co')) return ADAPTERS.lever;
    if (host.includes('ashbyhq.com')) return ADAPTERS.ashby;
    if (host.includes('myworkdayjobs.com')) return ADAPTERS.workday;
    return {};
  };

  const SPECS = [
    [/e-?mail/i, 'email'],
    [/(first|given)[\s_-]*name/i, 'first_name'],
    [/(last|family|sur)[\s_-]*name/i, 'last_name'],
    [/linked ?in/i, 'linkedin'],
    [/git ?hub/i, 'github'],
    [/(portfolio|personal (site|website)|website|\burl\b)/i, 'website'],
    [/(phone|mobile|contact number|\btel\b)/i, 'phone'],
    [/(current )?(company|employer|organization|organisation)/i, 'company'],
    [/(current )?(job )?(title|role|position)/i, 'title'],
    [/(school|university|college|institution)/i, 'school'],
    [/(degree|qualification|major|field of study)/i, 'degree'],
    [/(location|city|country|where are you|based)/i, 'location'],
    [/(cover letter|summary|about you|why (do|are) you|tell us|introduce|motivation)/i, 'summary'],
    [/(full[\s_-]*name|your name|^name$|applicant name)/i, 'full_name'],
  ];

  const labelFor = (el) => {
    let t = '';
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t += ' ' + l.textContent; }
    const wrap = el.closest('label'); if (wrap) t += ' ' + wrap.textContent;
    const box = el.closest('div,fieldset,section'); if (box) { const l = box.querySelector('label, .label, legend'); if (l) t += ' ' + l.textContent; }
    return t;
  };
  const ctxText = (el) => [labelFor(el), el.name, el.id, el.placeholder, el.getAttribute('aria-label')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
  const classify = (el) => {
    const c = ctxText(el);
    for (const [re, key] of SPECS) if (re.test(c)) return key;
    const type = (el.type || '').toLowerCase();
    if (type === 'email') return 'email';
    if (type === 'tel') return 'phone';
    if (type === 'url') return 'website';
    return null;
  };
  const setValue = (el, value) => {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype
      : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    for (const ev of ['input', 'change', 'blur']) el.dispatchEvent(new Event(ev, { bubbles: true }));
  };
  const mark = (el, ok) => { el.style.outline = `2px solid ${ok ? '#0e5c48' : '#d69200'}`; el.style.outlineOffset = '1px'; };
  const visible = (el) => el.offsetParent !== null && !el.disabled && !el.readOnly;
  const FILLABLE = (el) => {
    const t = (el.type || 'text').toLowerCase();
    return visible(el) && !['hidden', 'file', 'checkbox', 'radio', 'submit', 'button', 'password'].includes(t);
  };

  const state = { profile: null, filledKeys: new Set(), report: { filled: [], needsYou: [], fileAttached: false } };

  function fillFields() {
    const { profile } = state;
    if (!profile) return;
    const adapter = adapterFor(location.hostname);
    // 1) adapter selectors (high confidence)
    for (const [sel, key] of Object.entries(adapter)) {
      let el; try { el = document.querySelector(sel); } catch (e) { continue; }
      if (el && FILLABLE(el) && !el.value && profile[key]) {
        setValue(el, profile[key]); mark(el, true);
        if (!state.filledKeys.has(key)) { state.filledKeys.add(key); state.report.filled.push(key); }
      }
    }
    // 2) generic label matching for the rest
    for (const el of document.querySelectorAll('input, textarea')) {
      if (!FILLABLE(el) || (el.value && el.value.trim())) continue;
      const key = classify(el);
      if (!key || !profile[key]) continue;
      if (key === 'full_name' && (state.filledKeys.has('first_name') || state.filledKeys.has('last_name'))) continue;
      setValue(el, profile[key]); mark(el, true);
      if (!state.filledKeys.has(key)) { state.filledKeys.add(key); state.report.filled.push(key); }
    }
    // 3) selects: country if known, else flag
    for (const sel of document.querySelectorAll('select')) {
      if (!visible(sel) || sel.value) continue;
      const c = ctxText(sel).toLowerCase();
      if (/country/.test(c) && profile.country) {
        const opt = [...sel.options].find((o) => o.text.toLowerCase().includes(profile.country.toLowerCase()));
        if (opt) { setValue(sel, opt.value); mark(sel, true); continue; }
      }
      const q = 'dropdown: ' + (ctxText(sel).slice(0, 45) || 'select');
      if (!state.report.needsYou.includes(q)) { state.report.needsYou.push(q); mark(sel, false); }
    }
  }

  function attachResume(resume) {
    if (!resume || !resume.content || state.report.fileAttached) return;
    const fi = [...document.querySelectorAll('input[type="file"]')].find(visible) || document.querySelector('input[type="file"]');
    if (!fi) return;
    try {
      const bytes = Uint8Array.from(atob(resume.content), (ch) => ch.charCodeAt(0));
      const file = new File([bytes], resume.filename || 'resume.pdf', { type: resume.mime || 'application/pdf' });
      const dt = new DataTransfer(); dt.items.add(file);
      fi.files = dt.files;
      fi.dispatchEvent(new Event('input', { bubbles: true }));
      fi.dispatchEvent(new Event('change', { bubbles: true }));
      state.report.fileAttached = true; mark(fi, true);
    } catch (e) {
      const q = 'résumé upload (attach manually)';
      if (!state.report.needsYou.includes(q)) state.report.needsYou.push(q);
    }
  }

  function pageMeta() {
    let title = (document.querySelector('h1') || {}).textContent || document.title || '';
    const host = location.hostname; let company = '';
    const seg = location.pathname.split('/').filter(Boolean);
    if (host.includes('greenhouse.io') || host.includes('lever.co') || host.includes('ashbyhq.com')) company = seg[0] || '';
    else if (host.includes('myworkdayjobs.com')) company = host.split('.')[0] || '';
    return { url: location.href, title: title.trim().slice(0, 120), company: company.slice(0, 60) };
  }

  let submitArmed = false;
  function armSubmitLogging() {
    if (submitArmed) return; submitArmed = true;
    let logged = false;
    const log = () => {
      if (logged) return; logged = true;
      try { chrome.runtime.sendMessage({ type: 'PF_LOG_APPLY', meta: pageMeta() }); } catch (e) { /* sw asleep */ }
    };
    document.addEventListener('submit', log, true);
    document.addEventListener('click', (e) => {
      const b = e.target.closest('button, input[type="submit"], a');
      if (b && /submit application|submit|apply now|send application/i.test((b.textContent || b.value || '').trim())) log();
    }, true);
  }

  async function runFill() {
    let data;
    try { data = await chrome.runtime.sendMessage({ type: 'PF_GET_FILLDATA' }); }
    catch (e) { toast('PathFinder: extension not ready — reopen the popup.', true); return; }
    if (!data || data.error) { toast('PathFinder: ' + ((data && data.error) || 'could not load profile'), true); return; }

    state.profile = data.profile;
    state.filledKeys = new Set(); state.report = { filled: [], needsYou: [], fileAttached: false };
    fillFields();
    attachResume(data.resume);

    // Re-fill late-rendering fields (SPA/multi-step ATS) for a short window.
    let ticks = 0;
    const obs = new MutationObserver(() => { clearTimeout(obs._t); obs._t = setTimeout(fillFields, 350); });
    obs.observe(document.documentElement, { childList: true, subtree: true });
    const iv = setInterval(() => { if (++ticks >= 10) { clearInterval(iv); obs.disconnect(); } }, 500);

    armSubmitLogging();
    const r = state.report;
    toast(`Filled ${r.filled.length} field(s)${r.fileAttached ? ' + résumé' : ''}.`
      + (r.needsYou.length ? ` ${r.needsYou.length} need your review.` : '') + ' Review, then Submit yourself.');
  }

  // ---- Floating button (on supported ATS pages) ----
  function injectButton() {
    if (document.getElementById('pf-apply-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'pf-apply-btn';
    btn.textContent = '⚡ Autofill with PathFinder';
    btn.style.cssText = 'position:fixed;z-index:2147483646;right:18px;bottom:18px;background:#0e5c48;color:#fdfbf4;'
      + 'border:none;border-radius:999px;padding:12px 18px;font:600 13px system-ui,sans-serif;cursor:pointer;'
      + 'box-shadow:0 8px 24px rgba(0,0,0,.28)';
    btn.onmouseenter = () => (btn.style.background = '#0a4536');
    btn.onmouseleave = () => (btn.style.background = '#0e5c48');
    btn.onclick = (e) => { e.preventDefault(); runFill(); };
    document.body.appendChild(btn);
  }

  function toast(text, isErr) {
    const t = document.createElement('div');
    t.style.cssText = 'position:fixed;z-index:2147483647;right:18px;bottom:70px;max-width:320px;background:#1b1811;'
      + 'color:#fdfbf4;font:13px/1.5 system-ui,sans-serif;padding:13px 15px;border-radius:12px;'
      + `box-shadow:0 10px 30px rgba(0,0,0,.35);border-left:4px solid ${isErr ? '#bd4a2c' : '#0e5c48'}`;
    t.innerHTML = `<b>PathFinder Apply</b><br>${text}`;
    document.body.appendChild(t); setTimeout(() => t.remove(), 6500);
  }

  // Popup triggers a fill on the active tab (works on any page, incl. non-ATS).
  chrome.runtime.onMessage.addListener((msg, s, resp) => {
    if (msg.type === 'PF_START_FILL') { runFill().then(() => resp({ ok: true })); return true; }
    if (msg.type === 'PF_PING') { resp({ ok: true }); return true; }
  });

  if (/greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com/.test(location.hostname)) {
    if (document.body) injectButton();
    else document.addEventListener('DOMContentLoaded', injectButton);
  }
})();
