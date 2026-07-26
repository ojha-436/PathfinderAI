# PathFinder Apply — browser extension (v1.0.0)

One-click autofill for job applications, from your PathFinder profile — **in your own
browser and login session**. It fills the form, attaches your ATS-clean résumé, flags
judgement-call questions, and logs the application to your PathFinder tracker when you
submit. It **never** submits for you, bypasses CAPTCHAs, or creates accounts.

## What it does

- **Sign in** with your PathFinder account (token stays in the browser; the job site never sees it).
- **Pick a profile** — your master profile or any **role variant**.
- **Autofill** — on supported ATS a floating **⚡ Autofill with PathFinder** button appears; on any
  other page use the popup's *Autofill* button. Fills name/contact/work-history/education/links,
  attaches the résumé PDF (`/api/profile/resume`), and flags dropdowns/knockout questions for you.
- **Tracker sync** — when you submit, the application is logged to `/api/apply` as *applied*.

## Supported ATS (auto-inject) + everywhere else (via popup)

| ATS | Support |
|---|---|
| Greenhouse (`boards`/`job-boards.greenhouse.io`) | ✅ adapter + generic matcher |
| Lever (`jobs.lever.co`) | ✅ adapter + generic |
| Ashby (`jobs.ashbyhq.com`) | ✅ adapter + generic |
| Workday (`*.myworkdayjobs.com`) | ⚠️ partial — name/email/phone via `data-automation-id`; custom dropdowns flagged (Workday's shadow DOM is the hard case) |
| Any other application page | ✅ generic label/name/id matcher, injected on demand from the popup |

## Install

1. Start the PathFinder backend (`:8099`).
2. `chrome://extensions` → **Developer mode** → **Load unpacked** → select this `extension/` folder.
3. Click the **PathFinder Apply** icon → sign in with your PathFinder email + password.

## Try it safely (no real portal)

```bash
python3 -m http.server 8091     # from this folder
```
Open **http://127.0.0.1:8091/test-greenhouse-form.html**, click the extension → **Autofill this
application**. Fields fill (green outline), the résumé attaches, the work-auth dropdown is flagged.
Nothing submits. Then try a real Greenhouse/Lever/Ashby posting.

## Verified

- ✅ Résumé endpoint `/api/profile/resume?fmt=pdf|txt|html` returns a valid ATS-clean PDF, built from the
  selected profile/variant (grounded — content only from the profile).
- ✅ Autofill DOM engine on the mock Greenhouse form: **9 fields** (adapter + generic), **résumé PDF attached**
  via `DataTransfer`, knockout dropdown flagged.
- ⏳ Full popup↔background↔content messaging + declarative injection must be exercised in a real Chrome
  (can't load an unpacked extension in an automated browser). Load it and run the mock-form test above.

## Configure for production

- **API host:** set it in the popup (Settings) or `chrome.storage`. When you deploy the backend to a
  domain, add that origin to `host_permissions` in `manifest.json`.
- **More ATS:** add the host to `content_scripts.matches` + `host_permissions`, and (optionally) a
  selector map in `ADAPTERS` in `content.js`. The generic matcher already covers most fields.

## Architecture

- `background.js` — service worker: holds auth token, makes all PathFinder API calls (login, profile,
  variants, résumé PDF, tracker log), so the page never sees credentials.
- `content.js` — autofill engine: per-ATS adapters → generic label/name/id/type matcher → résumé attach →
  `MutationObserver` re-fill for late/multi-step fields → submit detection → tracker log. Injects the
  floating button on supported ATS.
- `popup.html/js` — login ↔ profile-picker; triggers autofill on the active tab.

## Boundaries (by design)

Never auto-submits · never bypasses CAPTCHA/bot checks · never creates accounts headlessly · uses only the
user's own session and identity · résumé content is grounded to the profile (no fabrication).
