from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.deps import get_db, get_current_user

from app.models import User, Analysis
from app.schemas import HistoryItemSummary, AnalysisResult

router = APIRouter()

@router.get("/", response_model=List[HistoryItemSummary])
def list_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analyses = db.query(Analysis).filter(Analysis.user_id == current_user.id).order_by(Analysis.created_at.desc()).all()
    return analyses

@router.get("/{analysis_id}", response_model=AnalysisResult)
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
        
    return AnalysisResult(
        id=analysis.id,
        title=analysis.title,
        created_at=analysis.created_at.isoformat(),
        saved=True,
        profile=analysis.profile_json,
        forecasts=analysis.forecasts_json,
        pathways=analysis.pathways_json,
        trace=analysis.trace_json,
    )

@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
        
    db.delete(analysis)
    db.commit()
    return None
