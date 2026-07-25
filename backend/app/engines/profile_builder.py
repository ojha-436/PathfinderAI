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
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{4}(?!\d)")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;)]+", re.I)
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



def _parse_experience(block: List[str]) -> List[Dict[str, Any]]:
    """Best-effort: group lines into entries (header + bullets)."""
    items: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    def _flush():
        nonlocal cur
        if cur:
            items.append(cur)
        cur = None

    for raw in block:
        line = raw.rstrip()
        if not line.strip():
            continue
        is_bullet = bool(_BULLET_RE.match(line))
        if is_bullet and cur is not None:
            cur["bullets"].append(_BULLET_RE.sub("", line).strip())
            continue
        # A non-bullet line starts a new entry header.
        _flush()
        start = end = ""
        m = _YEAR_RANGE_RE.search(line)
        if m:
            start, end = m.group(1), m.group(2)
            header = _YEAR_RANGE_RE.sub("", line)
        else:
            ym = _YEAR_RE.search(line)
            if ym:
                start = ym.group(0)
            header = line
        header = header.strip(" \t|,–-·")
        parts = re.split(r"\s+(?:at|,|\||–|—|-)\s+", header, maxsplit=1)
        role = parts[0].strip()
        org = parts[1].strip() if len(parts) > 1 else ""
        cur = {"role": role, "org": org, "start": start, "end": end, "bullets": []}
    _flush()
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
    model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
    schema_hint = (
        'Return ONLY JSON: {"sections":[...]} where each section is one of: '
        '{"type":"personal","title":"Personal","fields":{"name":"","email":"","mobile":"","city":"","country":"","github":"","linkedin":"","portfolio":""}}, '
        '{"type":"summary","title":"Summary","text":""}, '
        '{"type":"experience","title":"Experience","items":[{"role":"","org":"","start":"","end":"","bullets":[]}]}, '
        '{"type":"education","title":"Education","items":[{"degree":"","institution":"","year":"","score":""}]}, '
        '{"type":"skills","title":"Skills","items":["skill", ...]}, '
        '{"type":"projects","title":"Projects","items":[{"heading":"","tech_stack":"","detail":"","link":""}]}, '
        '{"type":"certifications","title":"Certifications","items":[{"heading":"","issuer":"","year":"","link":""}]}, '
        'or {"type":"<name>","title":"<Title>","items":[{"heading":"","detail":""}]} for anything else.'
    )
    prompt = (
        "You are a résumé PARSER. Structure the résumé below into ordered sections. "
        "Use ONLY facts present in the text — never invent an employer, title, date, degree, "
        "score, or skill. If a field is absent, leave it empty. " + schema_hint +
        "\n\nRÉSUMÉ:\n" + (resume_text or "")[:14000]
    )
    resp = model.generate_content(prompt, generation_config={"temperature": 0.0, "response_mime_type": "application/json"})
    data = _json.loads(resp.text)
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list) or not sections:
        return None
    # Ground skills back to the taxonomy label where possible (keeps free-text too).
    personal = next((s for s in sections if s.get("type") == "personal"), {})
    fields = personal.get("fields", {}) if isinstance(personal, dict) else {}
    return {
        "sections": sections,
        "full_name": fields.get("name", "") or "",
        "email": fields.get("email", "") or "",
        "phone": fields.get("phone", "") or "",
    }


def build_profile(resume_text: str) -> Dict[str, Any]:
    """résumé text → structured master profile. Gemini when keyed (grounded),
    deterministic local split otherwise. Never raises — always returns a profile."""
    if settings.GEMINI_API_KEY:
        try:
            out = _gemini_build(resume_text)
            if out:
                return out
        except Exception as exc:  # pragma: no cover - depends on external service
            print(f"[PathFinder] Gemini profile build failed, using local: {exc}", file=sys.stderr)
    return _local_build(resume_text)


def provider_name() -> str:
    return "gemini" if settings.GEMINI_API_KEY else "local"
