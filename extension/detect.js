/* Runs only on the PathFinder web app origin. Two jobs:
 *
 * 1. Presence beacon — tell the page the extension is installed (sets a DOM flag the
 *    page can read synchronously, and fires an event for live updates).
 * 2. Auto-connect relay — when the signed-in page hands us credentials via a trusted
 *    window.postMessage, forward them to the background service worker so the extension
 *    is instantly connected to the right server AND signed in. No "server" URL, no
 *    second login — the extension inherits the web session.
 *
 * This content script is only injected on PathFinder origins (see manifest matches),
 * so any message it relays necessarily originates from a real PathFinder page.
 */
try {
  const v = chrome.runtime.getManifest().version;
  document.documentElement.setAttribute('data-pf-apply', v);
  window.dispatchEvent(new CustomEvent('pf-apply-installed', { detail: { version: v } }));
} catch (e) { /* not in extension context */ }

window.addEventListener('message', (event) => {
  // Only accept messages from this same page (same window + same origin) — never from
  // embedded iframes or other origins.
  if (event.source !== window) return;
  if (event.origin !== window.location.origin) return;
  const d = event.data;
  if (!d || d.source !== 'pathfinder-web' || d.type !== 'PF_CONNECT') return;
  if (!d.token) return;
  try {
    chrome.runtime.sendMessage({
      type: 'PF_CONNECT',
      apiBase: d.apiBase || window.location.origin,
      token: d.token,
    });
  } catch (e) { /* extension context gone (e.g. reloaded) — page will retry next load */ }
});
