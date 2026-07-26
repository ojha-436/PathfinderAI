from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import Body
from app.deps import get_db, get_current_user
from app.models import User, Profile, ProfileVariant
from app.engines.resume_parser import extract_text_from_pdf
from app.engines.profile_builder import build_profile

router = APIRouter()


def _variant_dict(v: ProfileVariant) -> Dict[str, Any]:
    return {
        "id": v.id, "name": v.name, "role_target": v.role_target or "",
        "summary_override": v.summary_override or "",
        "emphasized_skills": v.emphasized_skills or [],
        "hidden_sections": v.hidden_sections or [],
        "is_default": bool(v.is_default),
    }

@router.post("/from-resume")
async def extract_from_resume(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    if not file and not text:
        raise HTTPException(status_code=400, detail="Must provide either a file or text.")
    
    content = ""
    if file:
        file_bytes = await file.read()
        if file.filename.lower().endswith(".pdf"):
            content = extract_text_from_pdf(file_bytes)
        else:
            content = file_bytes.decode("utf-8", errors="ignore")
    elif text:
        content = text
        
    if not content.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from input.")
        
    sections = build_profile(content)
    return {"sections": sections}

@router.get("/")
def get_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        return {"sections_json": []}
    return {
        "sections_json": profile.sections_json,
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone,
        "updated_at": profile.updated_at
    }

@router.put("/")
def update_profile(
    sections: List[Dict[str, Any]],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    
    full_name, email, phone = "", "", ""
    for sec in sections:
        if sec.get("type") == "personal" and "fields" in sec:
            fields = sec["fields"]
            full_name = fields.get("name", "")
            email = fields.get("email", "")
            phone = fields.get("phone", "")
            break
            
    if not profile:
        profile = Profile(
            user_id=current_user.id,
            sections_json=sections,
            full_name=full_name,
            email=email,
            phone=phone
        )
        db.add(profile)
    else:
        profile.sections_json = sections
        profile.full_name = full_name
        profile.email = email
        profile.phone = phone
        profile.updated_at = datetime.now(timezone.utc)
        
    db.commit()
    return {"status": "ok"}


# ---------------- Role variants (curated views of the master profile) ----------------
@router.get("/variants")
def list_variants(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    vs = db.query(ProfileVariant).filter(ProfileVariant.user_id == current_user.id).order_by(ProfileVariant.is_default.desc(), ProfileVariant.created_at).all()
    return [_variant_dict(v) for v in vs]


@router.post("/variants")
def create_variant(data: Dict[str, Any] = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    make_default = bool(data.get("is_default"))
    if make_default:
        db.query(ProfileVariant).filter(ProfileVariant.user_id == current_user.id).update({ProfileVariant.is_default: 0})
    v = ProfileVariant(
        user_id=current_user.id,
        name=data.get("name", "Untitled role") or "Untitled role",
        role_target=data.get("role_target", "") or "",
        summary_override=data.get("summary_override", "") or "",
        emphasized_skills=data.get("emphasized_skills", []) or [],
        hidden_sections=data.get("hidden_sections", []) or [],
        is_default=1 if make_default else 0,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return _variant_dict(v)


@router.put("/variants/{variant_id}")
def update_variant(variant_id: str, data: Dict[str, Any] = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    v = db.query(ProfileVariant).filter(ProfileVariant.id == variant_id, ProfileVariant.user_id == current_user.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Variant not found.")
    if data.get("is_default") and not v.is_default:
        db.query(ProfileVariant).filter(ProfileVariant.user_id == current_user.id).update({ProfileVariant.is_default: 0})
        v.is_default = 1
    elif "is_default" in data and not data.get("is_default"):
        v.is_default = 0
    for f in ("name", "role_target", "summary_override"):
        if f in data:
            setattr(v, f, data[f] or "")
    for f in ("emphasized_skills", "hidden_sections"):
        if f in data:
            setattr(v, f, data[f] or [])
    v.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _variant_dict(v)


@router.delete("/variants/{variant_id}", status_code=204)
def delete_variant(variant_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    v = db.query(ProfileVariant).filter(ProfileVariant.id == variant_id, ProfileVariant.user_id == current_user.id).first()
    if v:
        db.delete(v)
        db.commit()
    return None
