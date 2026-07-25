from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.deps import get_db, get_current_user
from app.models import User, Profile
from app.engines.resume_parser import extract_text_from_pdf
from app.engines.profile_builder import build_profile

router = APIRouter()

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
