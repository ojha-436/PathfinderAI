/* Presence beacon — runs only on the PathFinder web app origin. Lets the app know
 * the extension is installed so it can show "Installed ✓" and hide the install CTA.
 * Sets a DOM flag (readable synchronously) and fires an event (for live updates). */
try {
  const v = chrome.runtime.getManifest().version;
  document.documentElement.setAttribute('data-pf-apply', v);
  window.dispatchEvent(new CustomEvent('pf-apply-installed', { detail: { version: v } }));
} catch (e) { /* not in extension context */ }
