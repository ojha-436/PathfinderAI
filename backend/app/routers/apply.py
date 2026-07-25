from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import json

from app.deps import get_db, get_current_user
from app.models import User, Profile, Application, GeneratedDoc
from app.engines import jd_extract, jd_parser, matching, apply_gen

router = APIRouter()

def _get_profile(db: Session, user_id: str) -> Profile:
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Master profile not found. Please create a profile first.")
    return profile

def _get_skill_names(profile: Profile) -> List[str]:
    # Need string names for apply_gen text insertion
    skills = []
    for sec in profile.sections_json:
        if sec.get("type") == "skills" or sec.get("kind") == "skills":
            skills.extend(sec.get("items", []))
    return skills

def _get_skill_ids_from_names(names: List[str]) -> List[str]:
    # Resolve names back to IDs for matching engine
    from app.engines import datasets as ds
    ids = []
    for nm in names:
        sid = ds.resolve_skill_id(nm.strip())
        if sid:
            ids.append(sid)
    return ids

@router.post("/extract")
def extract_job(
    url: Optional[str] = Body(None),
    jd_text: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = _get_profile(db, current_user.id)
    
    extracted = jd_extract.extract(url=url, jd_text=jd_text)
    if extracted.get("blocked"):
        return {"extracted": extracted, "skills": [], "match": {}}
        
    jd = extracted.get("jd_text", "")
    req_skill_ids = jd_parser.parse_jd(jd)
    
    user_skill_names = _get_skill_names(profile)
    user_skill_ids = _get_skill_ids_from_names(user_skill_names)
    
    match_res = matching.match(user_skill_ids, req_skill_ids)
    
    # Resolve match skill IDs to names for the frontend
    from app.engines import datasets as ds
    def resolve_names(ids):
        return [ds.SKILL_NAME.get(sid, sid) for sid in ids]
        
    match_frontend = {
        "match_pct": match_res.get("match_pct", 0),
        "matched": resolve_names(match_res.get("matched", [])),
        "gaps": resolve_names(match_res.get("gaps", []))
    }
    
    return {
        "extracted": extracted,
        "skills": resolve_names(req_skill_ids),
        "match": match_frontend
    }

@router.get("/")
def list_applications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    apps = db.query(Application).filter(Application.user_id == current_user.id).order_by(Application.updated_at.desc()).all()
    return [{"id": a.id, "company": a.company, "job_title": a.job_title, "status": a.status, "updated_at": a.updated_at, "match_pct": a.match_json.get("match_pct", 0)} for a in apps]

@router.post("/")
def save_application(
    data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    app_id = data.get("id")
    if app_id:
        app = db.query(Application).filter(Application.id == app_id, Application.user_id == current_user.id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")
        app.company = data.get("company", app.company)
        app.job_title = data.get("job_title", app.job_title)
        app.job_url = data.get("job_url", app.job_url)
        app.jd_text = data.get("jd_text", app.jd_text)
        app.jd_skills_json = data.get("jd_skills", app.jd_skills_json)
        app.match_json = data.get("match", app.match_json)
        app.status = data.get("status", app.status)
        app.updated_at = datetime.now(timezone.utc)
    else:
        app = Application(
            user_id=current_user.id,
            company=data.get("company", ""),
            job_title=data.get("job_title", ""),
            job_url=data.get("job_url", ""),
            jd_text=data.get("jd_text", ""),
            jd_skills_json=data.get("jd_skills", []),
            match_json=data.get("match", {}),
            status=data.get("status", "draft")
        )
        db.add(app)
        
    db.commit()
    db.refresh(app)
    return {"id": app.id}

@router.get("/{app_id}")
def get_application(app_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
        
    docs = db.query(GeneratedDoc).filter(GeneratedDoc.application_id == app.id).all()
    
    res = {
        "id": app.id,
        "company": app.company,
        "job_title": app.job_title,
        "job_url": app.job_url,
        "jd_text": app.jd_text,
        "jd_skills": app.jd_skills_json,
        "match": app.match_json,
        "status": app.status,
        "docs": [{"id": d.id, "kind": d.kind, "content": d.content_json} for d in docs]
    }
    return res

@router.post("/generate")
def generate_docs(
    data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    app_id = data.get("application_id")
    kinds = data.get("kinds", ["resume", "cover_letter"])
    questions = data.get("questions", [])
    tailor_mode = data.get("tailor_mode", "moderate")
    
    app_record = db.query(Application).filter(Application.id == app_id, Application.user_id == current_user.id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found.")
        
    profile = _get_profile(db, current_user.id)
    profile_dict = {
        "sections": profile.sections_json,
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone
    }
    
    matched = app_record.match_json.get("matched", [])
    gaps = app_record.match_json.get("gaps", [])
    
    generated = []
    
    for kind in kinds:
        res = apply_gen.generate(
            profile=profile_dict,
            jd_text=app_record.jd_text,
            kind=kind,
            company=app_record.company,
            role=app_record.job_title,
            matched_skills=matched,
            gap_skills=gaps,
            questions=questions,
            tailor_mode=tailor_mode
        )
        
        # Save or update doc
        doc = db.query(GeneratedDoc).filter(GeneratedDoc.application_id == app_record.id, GeneratedDoc.kind == kind).first()
        if not doc:
            doc = GeneratedDoc(application_id=app_record.id, kind=kind, content_json=res["content"], format="json")
            db.add(doc)
        else:
            doc.content_json = res["content"]
            doc.created_at = datetime.now(timezone.utc)
            
        generated.append({"kind": kind, "content": res["content"], "grounding": res.get("grounding", {})})
        
    app_record.status = "generated"
    app_record.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"status": "ok", "docs": generated}

@router.get("/{app_id}/export")
def export_doc(
    app_id: str,
    kind: str = "resume",
    fmt: str = "txt",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    app_record = db.query(Application).filter(Application.id == app_id, Application.user_id == current_user.id).first()
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found.")
        
    doc = db.query(GeneratedDoc).filter(GeneratedDoc.application_id == app_id, GeneratedDoc.kind == kind).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    # The frontend is handling the HTML rendering and copying to clipboard.
    # The API can return the raw json for the client to render, but the spec says export HTML/TXT.
    # I'll just return the JSON and let frontend use _resume_html if needed, or I can import the renderer here.
    # Let's import the renderer from apply_gen for completeness if fmt != 'json'.
    if fmt == "html":
        from fastapi.responses import HTMLResponse
        if kind == "resume":
            html = apply_gen._resume_html(doc.content_json)
            return HTMLResponse(html)
        elif kind == "cover_letter":
            html = apply_gen._cover_letter_html(doc.content_json)
            return HTMLResponse(html)
            
    if fmt == "txt":
        from fastapi.responses import PlainTextResponse
        if kind == "resume":
            txt = apply_gen._resume_txt(doc.content_json)
            return PlainTextResponse(txt)
        elif kind == "cover_letter":
            txt = apply_gen._cover_letter_txt(doc.content_json)
            return PlainTextResponse(txt)
            
    if fmt == "pdf":
        from fastapi.responses import Response
        if kind == "resume":
            pdf_bytes = apply_gen._resume_pdf(doc.content_json)
        elif kind == "cover_letter":
            pdf_bytes = apply_gen._cover_letter_pdf(doc.content_json)
        else:
            raise HTTPException(400, "PDF not supported for this kind")
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{kind}.pdf"'})

    if fmt == "docx":
        from fastapi.responses import Response
        if kind == "resume":
            docx_bytes = apply_gen._resume_docx(doc.content_json)
        elif kind == "cover_letter":
            docx_bytes = apply_gen._cover_letter_docx(doc.content_json)
        else:
            raise HTTPException(400, "DOCX not supported for this kind")
        return Response(content=docx_bytes, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{kind}.docx"'})

    return {"content": doc.content_json}
