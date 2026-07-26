"""Master-profile builder — résumé text → ordered, typed, editable sections.

The keystone of the Apply Assistant (plan-apply.md, Phase A). Local default is a
deterministic heuristic section-split + `taxonomy` skill grounding, so it works
with **zero cloud credentials**. When GEMINI_API_KEY is set, Gemini structures the
résumé instead — but strictly **grounded to the résumé text** (it structures, it
never invents), and it falls back to the local split on any error.

Return shape (see ARCHITECTURE-apply.md §3):
    {"sections": [ {"type","title", ...}, ... ],
     "full_name": str, "email": str, "phone": str}
where a section is one of:
    personal   {"type","title","fields":{name,email,phone,location,links[]}}
    summary    {"type","title","text"}
    experience {"type","title","items":[{role,org,start,end,bullets[]}]}
    education  {"type","title","items":[{degree,institution,year,score}]}
    skills     {"type","title","items":[str,...]}
    generic    {"type","title","items":[{heading,detail}]}   # projects/certs/custom/…
"""
from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional

from app.config import settings
from app.engines import datasets as ds
from app.engines import taxonomy

# --- Contact-info extractors (grounded: only what's literally in the text) ----
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d\s().\-]{6,16}\d(?![\w])")
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s,;)]+"                                   # explicit http(s):// or www.
    r"|\b[\w.-]+\.(?:com|org|net|io|dev|me|co|in|ai|app|xyz)/[^\s,;)]+",  # bare domain WITH a path (github.com/user)
    re.I,
)
_YEAR_RANGE_RE = re.compile(r"(\b(?:19|20)\d{2}\b)\s*(?:[-–—]|to)\s*((?:19|20)\d{2}\b|present|current|now)", re.I)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# Section-heading aliases → canonical section type.
_HEADINGS: List[tuple] = [
    ("summary", ["professional summary", "career objective", "summary", "objective", "profile", "about me", "about"]),
    ("experience", ["work experience", "professional experience", "employment history", "work history", "experience", "employment"]),
    ("education", ["education", "academic background", "academics", "qualifications", "educational qualifications"]),
    ("skills", ["technical skills", "core competencies", "core skills", "key skills", "competencies", "skills"]),
    ("projects", ["personal projects", "key projects", "projects", "academic projects"]),
    ("certifications", ["certifications", "certificates", "licenses & certifications", "licenses"]),
    ("hackathons", ["hackathons", "competitions", "hackathons & competitions"]),
    ("achievements", ["achievements", "awards & honors", "awards", "honors", "accomplishments"]),
    ("publications", ["publications", "research"]),
    ("volunteering", ["volunteering", "volunteer experience", "community"]),
    ("languages", ["languages", "languages known"]),
]
_TITLE = {
    "summary": "Summary", "experience": "Experience", "education": "Education",
    "skills": "Skills", "projects": "Projects", "certifications": "Certifications",
    "hackathons": "Hackathons / Competitions", "achievements": "Achievements / Awards",
    "publications": "Publications", "volunteering": "Volunteering", "languages": "Languages",
}
_BULLET_RE = re.compile(r"^\s*[-•*·▪◦]\s+")


def _norm_head(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().rstrip(":").lower())


def _match_heading(line: str) -> Optional[str]:
    """Return the canonical section type if this line is a section heading, else None."""
    s = line.strip()
    if not s or len(s) > 42 or "@" in s or _URL_RE.search(s):
        return None
    # A heading is a short line (few words) that equals a known alias.
    if len(s.split()) > 5:
        return None
    n = _norm_head(s)
    for canon, aliases in _HEADINGS:
        if n in aliases:
            return canon
    return None


def _looks_like_name(line: str) -> bool:
    s = line.strip()
    if not s or "@" in s or _URL_RE.search(s) or any(ch.isdigit() for ch in s):
        return False
    lower = s.lower()
    skip_keywords = ["resume", "curriculum vitae", "cv", "profile", "contact", "summary", "experience", "education", "skills", "page"]
    if any(kw in lower for kw in skip_keywords):
        return False
    words = s.split()
    return 1 <= len(words) <= 4 and _match_heading(s) is None


def _extract_contact(text: str) -> Dict[str, Any]:
    email_m = _EMAIL_RE.search(text)
    email = email_m.group(0) if email_m else ""
    
    # Extract phone numbers, avoiding date ranges like 2020-2024
    phone = ""
    for m in _PHONE_RE.finditer(text):
        p = m.group(0).strip()
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15 and not re.search(r"^(19|20)\d{2}[-\s](19|20)\d{2}$", p):
            phone = p
            break

    links = []
    github = ""
    linkedin = ""
    portfolio = ""
    for m in _URL_RE.finditer(text):
        u = m.group(0).rstrip(".,);")
        if u not in links:
            links.append(u)
        u_low = u.lower()
        if "github.com" in u_low and not github:
            github = u
        elif "linkedin.com" in u_low and not linkedin:
            linkedin = u
        elif not portfolio and "github.com" not in u_low and "linkedin.com" not in u_low:
            portfolio = u

    city = ""
    country = ""
    lines = [ln.strip() for ln in text.splitlines()[:20] if ln.strip()]
    loc_pat = re.compile(r"^[📍\s]*([A-Z][a-zA-Z\s\.]{1,25}),\s*([A-Z][a-zA-Z\s\.]{1,25})$")
    for ln in lines:
        if "@" in ln or "http" in ln or _PHONE_RE.search(ln):
            continue
        lm = loc_pat.search(ln)
        if lm:
            c1, c2 = lm.group(1).strip(), lm.group(2).strip()
            if not _match_heading(c1) and not _match_heading(c2):
                city, country = c1, c2
                break

    return {
        "email": email,
        "phone": phone,
        "mobile": phone,
        "city": city,
        "country": country,
        "github": github,
        "linkedin": linkedin,
        "portfolio": portfolio,
        "links": links
    }



_COMPANY_HINTS = re.compile(
    r"\b(inc|ltd|llc|pvt|corp|technologies|technology|works|systems|solutions|labs|"
    r"university|institute|college|gmbh|company|industries|enterprises|consulting|"
    r"services|group|softwares?|infotech|pvt\.? ltd)\b", re.I)


def _mk_experience_entry(header_lines: List[str], start: str, end: str) -> Dict[str, Any]:
    hs = [h.strip(" \t|,·–—-") for h in header_lines if h and h.strip(" \t|,·–—-")]
    role = org = ""
    if len(hs) >= 2:
        # Two header lines: one is the company, the other the role. Prefer the
        # company-hint match; else assume "Company \n Title" (the common ATS layout).
        if _COMPANY_HINTS.search(hs[0]) and not _COMPANY_HINTS.search(hs[1]):
            org, role = hs[0], hs[1]
        elif _COMPANY_HINTS.search(hs[1]) and not _COMPANY_HINTS.search(hs[0]):
            role, org = hs[0], hs[1]
        else:
            org, role = hs[0], hs[1]
    elif hs:
        parts = re.split(r"\s+(?:at|,|\||–|—|·)\s+", hs[0], maxsplit=1)
        role = parts[0].strip()
        org = parts[1].strip() if len(parts) > 1 else ""
    return {"role": role, "org": org, "start": start, "end": end, "bullets": []}


def _parse_experience(block: List[str]) -> List[Dict[str, Any]]:
    """Group lines into jobs, anchored on DATES so a job's description sentences
    attach as bullets rather than being mis-split into separate jobs.

    A line with a year / date range completes an entry header (optionally paired with
    a preceding company/role line). Any other non-bullet line, once inside an entry,
    is treated as a description bullet — never a new job."""
    items: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    pending: List[str] = []   # header lines (company/role) seen before a date anchor

    for raw in block:
        line = raw.rstrip()
        if not line.strip():
            continue
        if _BULLET_RE.match(line):
            b = _BULLET_RE.sub("", line).strip()
            if cur is not None:
                cur["bullets"].append(b)
            elif pending:
                cur = _mk_experience_entry(pending, "", "")
                cur["bullets"].append(b)
                pending = []
            continue

        m = _YEAR_RANGE_RE.search(line)
        ym = _YEAR_RE.search(line) if not m else None
        if m or ym:
            if cur is not None:
                items.append(cur)
            if m:
                start, end, header = m.group(1), m.group(2), _YEAR_RANGE_RE.sub("", line)
            else:
                start, end, header = ym.group(0), "", _YEAR_RE.sub("", line)
            header = header.strip(" \t|,·–—-")
            cur = _mk_experience_entry(pending + ([header] if header else []), start, end)
            pending = []
        elif cur is None:
            pending.append(line)          # header awaiting a date (company/role)
        else:
            cur["bullets"].append(line)   # inside an entry → description, NOT a new job

    if cur is not None:
        items.append(cur)
    elif pending:
        items.append(_mk_experience_entry(pending, "", ""))
    return items


def _parse_education(block: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in block:
        line = raw.strip()
        if not line or _BULLET_RE.match(line) is None and len(line) < 3:
            continue
        line = _BULLET_RE.sub("", line).strip()
        if not line:
            continue
        year = ""
        ym = _YEAR_RE.search(line)
        if ym:
            year = ym.group(0)
        score = ""
        sm = re.search(r"(\d{1,2}\.\d{1,2}\s*(?:cgpa|gpa)?|\d{1,3}\s*%|\b[Ff]irst [Cc]lass\b)", line)
        if sm:
            score = sm.group(0).strip()
        rest = _YEAR_RANGE_RE.sub("", line)
        parts = re.split(r"\s*[,|–—]\s*|\s+at\s+", rest, maxsplit=1)
        degree = parts[0].strip()
        institution = parts[1].strip() if len(parts) > 1 else ""
        # Trim a trailing year/score fragment left in institution.
        institution = _YEAR_RE.sub("", institution).strip(" ,|–—-")
        items.append({"degree": degree, "institution": institution, "year": year, "score": score})
    return items


def _parse_skills(block: List[str], full_text: str) -> List[str]:
    """Grounded skill names (taxonomy) first, then the free-text skills the résumé lists."""
    joined = " ".join(block)
    grounded = [ds.SKILL_NAME[sid] for sid in taxonomy.match_skill_ids(joined or full_text)]
    out: List[str] = list(dict.fromkeys(grounded))
    raw = re.split(r"[,;|•·\n]|\s{2,}", joined)
    have_norm = {re.sub(r"[^a-z0-9]", "", s.lower()) for s in out}
    for tok in raw:
        t = _BULLET_RE.sub("", tok).strip()
        if 1 < len(t) <= 40 and re.sub(r"[^a-z0-9]", "", t.lower()) not in have_norm and not t.endswith(":"):
            out.append(t)
            have_norm.add(re.sub(r"[^a-z0-9]", "", t.lower()))
    return out[:40]


def _parse_projects(block: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for raw in block:
        line = raw.strip()
        if not line:
            continue
        url_m = _URL_RE.search(line)
        link = url_m.group(0) if url_m else ""
        if _BULLET_RE.match(line):
            detail = _BULLET_RE.sub("", line).strip()
            if cur:
                cur["detail"] = (cur["detail"] + " " + detail).strip()
                if link and not cur.get("link"):
                    cur["link"] = link
            else:
                items.append({"heading": detail, "tech_stack": "", "detail": "", "link": link})
        else:
            if cur:
                items.append(cur)
            cur = {"heading": line, "tech_stack": "", "detail": "", "link": link}
    if cur:
        items.append(cur)
    return items


def _parse_certifications(block: List[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in block:
        line = raw.strip()
        if not line:
            continue
        line = _BULLET_RE.sub("", line).strip()
        year = ""
        ym = _YEAR_RE.search(line)
        if ym:
            year = ym.group(0)
        url_m = _URL_RE.search(line)
        link = url_m.group(0) if url_m else ""
        
        parts = re.split(r"\s*[-–—|]\s*|\s+by\s+|\s+from\s+", line, maxsplit=1)
        heading = parts[0].strip()
        issuer = parts[1].strip() if len(parts) > 1 else ""
        issuer = _YEAR_RE.sub("", issuer).strip(" -–—|")
        items.append({"heading": heading, "issuer": issuer, "year": year, "link": link})
    return items


def _generic_items(block: List[str]) -> List[Dict[str, str]]:
    """Projects / certifications / custom → {heading, detail} entries."""
    items: List[Dict[str, str]] = []
    cur: Optional[Dict[str, str]] = None
    for raw in block:
        line = raw.strip()
        if not line:
            continue
        if _BULLET_RE.match(line):
            detail = _BULLET_RE.sub("", line).strip()
            if cur:
                cur["detail"] = (cur["detail"] + " " + detail).strip()
            else:
                items.append({"heading": detail, "detail": ""})
        else:
            if cur:
                items.append(cur)
            cur = {"heading": line, "detail": ""}
    if cur:
        items.append(cur)
    return items


def _local_build(resume_text: str) -> Dict[str, Any]:
    text = resume_text or ""
    lines = text.splitlines()
    contact = _extract_contact(text)

    # Name = first name-like line before the first heading.
    name = ""
    for ln in lines[:8]:
        if _looks_like_name(ln):
            name = ln.strip()
            break
    # Relaxed fallback: first non-empty top line that isn't contact/heading/URL.
    if not name:
        for ln in lines[:6]:
            s = ln.strip()
            if not s or "@" in s or _URL_RE.search(s) or _PHONE_RE.search(s) or _match_heading(s):
                continue
            words = s.split()
            if 1 <= len(words) <= 6 and sum(c.isdigit() for c in s) <= 2:
                name = re.split(r"\s{2,}|\s[|•·]\s", s)[0].strip()
                break
    location = ""
    loc_m = re.search(r"\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),\s*([A-Z][a-zA-Z]+)\b", text)
    if loc_m:
        location = loc_m.group(0)

    # Split the body into (heading_type, [lines]) blocks.
    blocks: List[tuple] = []
    cur_type = "_preamble"
    cur_lines: List[str] = []
    for ln in lines:
        h = _match_heading(ln)
        if h:
            blocks.append((cur_type, cur_lines))
            cur_type, cur_lines = h, []
        else:
            cur_lines.append(ln)
    blocks.append((cur_type, cur_lines))

    sections: List[Dict[str, Any]] = [{
        "type": "personal", "title": "Personal",
        "fields": {
            "name": name,
            "email": contact["email"],
            "mobile": contact["phone"],
            "phone": contact["phone"],
            "city": contact["city"],
            "country": contact["country"],
            "location": f"{contact['city']}, {contact['country']}".strip(" ,") if (contact['city'] or contact['country']) else location,
            "github": contact["github"],
            "linkedin": contact["linkedin"],
            "portfolio": contact["portfolio"],
            "links": contact["links"]
        },
    }]

    seen_skills = False
    for btype, blines in blocks:
        body = [line for line in blines if line.strip()]
        if btype in ("_preamble",):
            continue
        if btype == "summary":
            txt = " ".join(line.strip() for line in body).strip()
            if txt:
                sections.append({"type": "summary", "title": _TITLE["summary"], "text": txt})
        elif btype == "experience":
            items = _parse_experience(blines)
            if items:
                sections.append({"type": "experience", "title": _TITLE["experience"], "items": items})
        elif btype == "education":
            items = _parse_education(blines)
            if items:
                sections.append({"type": "education", "title": _TITLE["education"], "items": items})
        elif btype == "skills":
            skills = _parse_skills(blines, text)
            seen_skills = True
            if skills:
                sections.append({"type": "skills", "title": _TITLE["skills"], "items": skills})
        elif btype == "projects":
            items = _parse_projects(blines)
            if items:
                sections.append({"type": "projects", "title": _TITLE["projects"], "items": items})
        elif btype == "certifications":
            items = _parse_certifications(blines)
            if items:
                sections.append({"type": "certifications", "title": _TITLE["certifications"], "items": items})
        else:
            items = _generic_items(blines)
            if items:
                sections.append({"type": btype, "title": _TITLE.get(btype, btype.title()), "items": items})

    # Guarantee a grounded Skills section even if the résumé had no explicit header.
    if not seen_skills:
        skills = [ds.SKILL_NAME[sid] for sid in taxonomy.match_skill_ids(text)]
        if skills:
            sections.append({"type": "skills", "title": _TITLE["skills"], "items": skills})

    return {"sections": sections, "full_name": name, "email": contact["email"], "phone": contact["phone"]}


def _gemini_build(resume_text: str) -> Optional[Dict[str, Any]]:  # pragma: no cover - external service
    """Structure the résumé into typed sections with Gemini — grounded to the text."""
    import json as _json

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    # A capable extraction model; override with GEMINI_MODEL if desired.
    model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
    schema_hint = (
        'Return ONLY JSON: {"sections":[...]} where each section is one of: '
        '{"type":"personal","title":"Personal","fields":{"name":"","email":"","mobile":"","city":"","country":"","github":"","linkedin":"","portfolio":""}}, '
        '{"type":"summary","title":"Summary","text":""}, '
        '{"type":"experience","title":"Experience","items":[{"role":"","org":"","start":"","end":"","bullets":[]}]}, '
        '{"type":"education","title":"Education","items":[{"degree":"","institution":"","year":"","score":""}]}, '
        '{"type":"projects","title":"Projects","items":[{"heading":"","tech_stack":"","detail":"","link":""}]}, '
        '{"type":"skills","title":"Skills","items":["skill", ...]}, '
        '{"type":"certifications","title":"Certifications","items":[{"heading":"","issuer":"","year":"","link":""}]}, '
        'or {"type":"<name>","title":"<Title>","items":[{"heading":"","detail":""}]} for anything else.'
    )
    prompt = (
        "You are an expert résumé PARSER. Read the résumé and structure it into typed sections.\n"
        "RULES:\n"
        "1. The candidate's NAME is almost always the most prominent line at the very top — "
        "extract it into personal.fields.name. Never leave name empty if a name appears anywhere.\n"
        "2. Put every piece of information in the section it BELONGS to: job history → experience, "
        "degrees/schools → education, built things → projects, courses/licenses → certifications, "
        "a profile/objective paragraph → summary, technologies/tools → skills.\n"
        "2b. EXPERIENCE: group each job as ONE entry with role, org, start, end, and ALL of that "
        "job's responsibility/description lines as bullets. NEVER split a single job's description "
        "sentences into multiple experience entries. A new entry begins only at a new employer/role.\n"
        "3. Extract ALL links and route them: a github.com URL → personal.fields.github, a "
        "linkedin.com URL → personal.fields.linkedin, any other personal site → personal.fields.portfolio, "
        "and a link that belongs to a specific project → that project's \"link\".\n"
        "4. ALWAYS include these sections even if empty: summary, experience, education, projects, skills, certifications.\n"
        "5. GROUNDING: use ONLY facts present in the text — never invent an employer, title, date, "
        "degree, score, skill, or link. Leave a field \"\" if absent.\n" + schema_hint +
        "\n\nRÉSUMÉ:\n" + (resume_text or "")[:16000]
    )
    resp = model.generate_content(prompt, generation_config={"temperature": 0.0, "response_mime_type": "application/json"})
    data = _json.loads(resp.text)
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list) or not sections:
        return None
    personal = next((s for s in sections if s.get("type") == "personal"), {})
    fields = personal.get("fields", {}) if isinstance(personal, dict) else {}
    # Belt-and-braces: if the model missed the name/links, recover them locally from the text.
    if not fields.get("name"):
        fields["name"] = _local_build(resume_text)["full_name"]
    contact = _extract_contact(resume_text)
    for k in ("github", "linkedin", "portfolio", "email", "mobile"):
        if not fields.get(k) and contact.get(k):
            fields[k] = contact[k]
    if isinstance(personal, dict):
        personal["fields"] = fields
    return {
        "sections": sections,
        "full_name": fields.get("name", "") or "",
        "email": fields.get("email", "") or "",
        "phone": fields.get("mobile", "") or fields.get("phone", "") or "",
    }


# Canonical sections that MUST exist in every profile (scaffolded empty if the
# résumé lacks them) — so the builder always shows a consistent, fillable shape.
_CANONICAL_ORDER = ["personal", "summary", "experience", "education", "projects", "skills", "certifications"]
_PERSONAL_KEYS = ("name", "email", "mobile", "phone", "city", "country", "location", "github", "linkedin", "portfolio")


def _empty_section(t: str) -> Dict[str, Any]:
    if t == "personal":
        return {"type": "personal", "title": "Personal",
                "fields": {**{k: "" for k in _PERSONAL_KEYS}, "links": []}}
    if t == "summary":
        return {"type": "summary", "title": _TITLE["summary"], "text": ""}
    return {"type": t, "title": _TITLE.get(t, t.title()), "items": []}


def _ensure_canonical_sections(result: Dict[str, Any]) -> Dict[str, Any]:
    """Guarantee every canonical section exists (empty if absent), in order; keep
    any extra/custom sections appended after. Sync convenience name/email/phone."""
    sections = result.get("sections") or []
    by_type: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        t = s.get("type")
        if t in _CANONICAL_ORDER and t not in by_type:
            by_type[t] = s
        else:
            extras.append(s)
    ordered: List[Dict[str, Any]] = []
    for t in _CANONICAL_ORDER:
        sec = by_type.get(t) or _empty_section(t)
        if t == "personal":
            fields = sec.setdefault("fields", {})
            for k in _PERSONAL_KEYS:
                fields.setdefault(k, "")
            fields.setdefault("links", [])
            if not fields.get("location") and (fields.get("city") or fields.get("country")):
                fields["location"] = ", ".join(x for x in (fields.get("city"), fields.get("country")) if x)
        ordered.append(sec)
    ordered.extend(extras)
    result["sections"] = ordered
    pf = ordered[0].get("fields", {})
    result["full_name"] = result.get("full_name") or pf.get("name", "")
    result["email"] = result.get("email") or pf.get("email", "")
    result["phone"] = result.get("phone") or pf.get("mobile") or pf.get("phone", "")
    return result


def build_profile(resume_text: str) -> Dict[str, Any]:
    """résumé text → structured master profile. Gemini when keyed (grounded), else the
    deterministic local split. Canonical sections are always guaranteed. Never raises."""
    out: Optional[Dict[str, Any]] = None
    if settings.GEMINI_API_KEY:
        try:
            out = _gemini_build(resume_text)
        except Exception as exc:  # pragma: no cover - depends on external service
            print(f"[PathFinder] Gemini profile build failed, using local: {exc}", file=sys.stderr)
            out = None
    if not out:
        out = _local_build(resume_text)
    return _ensure_canonical_sections(out)


def resolve_effective_profile(master_sections: List[Dict[str, Any]],
                              variant: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply a role VARIANT on top of the master profile → the effective sections used
    to generate an application's docs. A variant only CURATES the master's real facts:
    an optional role-specific summary, skills reordered (emphasized first), and sections
    hidden for that role. It never adds anything not already in the master, so grounding
    is preserved."""
    import copy

    sections = copy.deepcopy(master_sections or [])
    if not variant:
        return sections
    hidden = set(variant.get("hidden_sections") or [])
    summary_override = (variant.get("summary_override") or "").strip()
    emphasized = [str(s).lower() for s in (variant.get("emphasized_skills") or [])]

    out: List[Dict[str, Any]] = []
    for sec in sections:
        t = sec.get("type")
        if t in hidden and t != "personal":   # never hide the personal/contact section
            continue
        if t == "summary" and summary_override:
            sec = {**sec, "text": summary_override}
        if t == "skills" and emphasized:
            items = sec.get("items") or []
            first = [it for it in items if str(it).lower() in emphasized]
            rest = [it for it in items if str(it).lower() not in emphasized]
            sec = {**sec, "items": first + rest}
        out.append(sec)
    return out


def provider_name() -> str:
    return "gemini" if settings.GEMINI_API_KEY else "local"
